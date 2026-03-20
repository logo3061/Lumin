import discord
from discord.ext import commands, tasks
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import json
import os
import asyncio
import logging
from dotenv import load_dotenv

# ----------------------------
# Load Token aus .env (push-sicher)
# ----------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")  # GitHub scannt nichts

# ----------------------------
# Konstanten
# ----------------------------
FORUM_CHANNEL_ID = 1484443811181756466
GUILD_ID = 1483894598102290533
DATA_FILE = "bot_data.json"

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("lumin.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ----------------------------
# Discord Bot
# ----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# JSON Funktionen
# ----------------------------
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        default = {"commands": [], "daily_posts": []}
        save_data(default)
        return default
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ----------------------------
# Bild generieren
# ----------------------------
def create_image() -> str:
    base = Image.open("template.png").convert("RGBA")
    draw = ImageDraw.Draw(base)
    date_str = datetime.now().strftime("%d.%m.%Y")
    font = ImageFont.truetype("Lovelo_Black.otf", 120)
    x, y = 665, 870
    draw.text((x + 2, y + 2), date_str, font=font, fill=(0, 0, 0, 120))
    draw.text((x, y), date_str, font=font, fill="white")
    output_path = "output.png"
    base.save(output_path)
    return output_path

# ----------------------------
# Command Registrierung
# ----------------------------
async def register_command(command_name: str, description: str, guild_id: int):
    data = load_data()
    if command_name in data["commands"]:
        log.info(f"/{command_name} existiert bereits, überspringe.")
        return
    guild = discord.Object(id=guild_id)
    @bot.tree.command(name=command_name, description=description, guild=guild)
    async def dynamic_command(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            image_path = create_image()
            file = discord.File(image_path)
            await interaction.followup.send(content="📸 Test erfolgreich", file=file)
        except Exception as e:
            log.error(f"Fehler in /{command_name}: {e}")
            await interaction.followup.send(content=f"❌ Fehler: {e}", ephemeral=True)
    try:
        await bot.tree.sync(guild=guild)
        data["commands"].append(command_name)
        save_data(data)
        log.info(f"/{command_name} registriert ✅")
    except Exception as e:
        log.error(f"Fehler beim Registrieren von /{command_name}: {e}")

# ----------------------------
# Alte Threads locken
# ----------------------------
async def lock_old_threads(data: dict):
    for entry in data["daily_posts"]:
        thread_id = entry.get("thread_id") if isinstance(entry, dict) else None
        if not thread_id:
            continue
        try:
            old_thread = await bot.fetch_channel(thread_id)
            if isinstance(old_thread, discord.Thread) and not old_thread.locked:
                await old_thread.edit(locked=True, archived=True)
                log.info(f"Thread '{old_thread.name}' gelockt & archiviert ✅")
        except discord.NotFound:
            log.warning(f"Thread {thread_id} nicht gefunden, überspringe.")
        except Exception as e:
            log.error(f"Fehler beim Locken von Thread {thread_id}: {e}")

# ----------------------------
# Daily Post
# ----------------------------
async def check_and_post():
    data = load_data()
    today_str = datetime.now().strftime("%Y-%m-%d")
    posted_dates = [
        entry["date"] if isinstance(entry, dict) else entry
        for entry in data["daily_posts"]
    ]
    if today_str in posted_dates:
        log.info("Heute bereits gepostet ✅")
        return
    try:
        channel = await bot.fetch_channel(FORUM_CHANNEL_ID)
        if not isinstance(channel, discord.ForumChannel):
            log.error(f"Kanal {FORUM_CHANNEL_ID} ist kein ForumChannel!")
            return
        await lock_old_threads(data)
        image_path = create_image()
        file = discord.File(image_path)
        thread_with_msg = await channel.create_thread(
            name=f"Devlog {datetime.now().strftime('%d.%m.%Y')}",
            content="",
            file=file,
            applied_tags=[]
        )
        thread = thread_with_msg.thread
        try:
            await thread.parent.set_permissions(channel.guild.default_role, send_messages_in_threads=False)
            await thread.parent.set_permissions(channel.guild.me, send_messages_in_threads=True)
        except discord.Forbidden:
            log.warning("Fehlende Rechte für Thread-Permissions, überspringe.")
        data["daily_posts"].append({"date": today_str, "thread_id": thread.id})
        save_data(data)
        log.info(f"Daily Post erstellt: '{thread.name}' (ID: {thread.id}) ✅")
    except discord.Forbidden:
        log.error("Bot hat keine Rechte im ForumChannel!")
    except Exception as e:
        log.error(f"FEHLER Daily Post: {e}", exc_info=True)

# ----------------------------
# Task um 00:01
# ----------------------------
@tasks.loop(minutes=1)
async def midnight_loop():
    now = datetime.now()
    if now.hour == 0 and now.minute == 1:
        await check_and_post()

@midnight_loop.before_loop
async def before_midnight_loop():
    await bot.wait_until_ready()

# ----------------------------
# Bot ready
# ----------------------------
@bot.event
async def on_ready():
    log.info(f"Eingeloggt als {bot.user} (ID: {bot.user.id})")
    await register_command("test", "Testet das Bild", GUILD_ID)
    await check_and_post()
    if not midnight_loop.is_running():
        midnight_loop.start()

bot.run(TOKEN, log_handler=None)