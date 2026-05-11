# -*- coding: utf-8 -*-
"""
bot.py - Main bot entry point.
"""

import os
import sys
import asyncio
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# Allow imports from src/
sys.path.insert(0, os.path.dirname(__file__))

import database as db
import reminders

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN            = os.getenv("DISCORD_TOKEN", "")
GUILD_ID         = int(os.getenv("GUILD_ID", "0"))
ALERT_CHANNEL_ID = int(os.getenv("FUEL_ALERT_CHANNEL_ID", "0"))
CHECK_CRON       = os.getenv("FUEL_CHECK_CRON", "0 * * * *")   # default: hourly

THRESHOLDS = [
    int(os.getenv("THRESHOLD_CRITICAL", "24")),
    int(os.getenv("THRESHOLD_WARNING",  "72")),
    int(os.getenv("THRESHOLD_NOTICE",   "168")),
]

if not TOKEN:
    sys.exit("❌  DISCORD_TOKEN is not set in .env")

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()


@bot.event
async def on_ready() -> None:
    print(f"✅  Logged in as {bot.user} (ID: {bot.user.id})")

    # Initialise DB
    await db.init_db()
    print("✅  Database ready.")

    # Configure reminder module
    reminders.setup(THRESHOLDS, ALERT_CHANNEL_ID)

    # Sync slash commands to the guild
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"✅  Synced {len(synced)} slash command(s) to guild {GUILD_ID}.")

    # Start the fuel-check scheduler
    minute, hour, day, month, dow = CHECK_CRON.split()
    scheduler.add_job(
        reminders.check_all_structures,
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow),
        args=[bot],
        id="fuel_check",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    print(f"✅  Fuel check scheduler started (cron: {CHECK_CRON}).")


async def load_cogs() -> None:
    await bot.load_extension("cogs.fuel_commands")


async def main() -> None:
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
