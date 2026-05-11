# -*- coding: utf-8 -*-
"""
reminders.py - Scheduled fuel-check task that fires alerts to Discord.
"""

import time
import discord
from discord.ext import tasks
from datetime import datetime, timezone

import database as db
import fuel_utils as fu


# Thresholds in hours that trigger alerts (loaded from config in bot.py)
THRESHOLDS: list[int] = []
ALERT_CHANNEL_ID: int = 0


def setup(thresholds: list[int], channel_id: int) -> None:
    """Called once at startup to configure thresholds and channel."""
    global THRESHOLDS, ALERT_CHANNEL_ID
    THRESHOLDS = sorted(thresholds, reverse=True)   # check largest first
    ALERT_CHANNEL_ID = channel_id


async def check_all_structures(bot: discord.Client) -> None:
    """
    Iterate every tracked structure, compute hours remaining,
    and send alerts for any crossed threshold that hasn't been sent yet.
    """
    channel = bot.get_channel(ALERT_CHANNEL_ID)
    if channel is None:
        print(f"[reminders] Alert channel {ALERT_CHANNEL_ID} not found.")
        return

    structures = await db.list_structures()
    now = int(time.time())

    for s in structures:
        estimated_fuel = fu.current_fuel_estimate(
            s["fuel_amount"], s["burn_rate"], s["updated_at"]
        )
        hours_left = fu.hours_remaining(estimated_fuel, s["burn_rate"])
        empty_ts   = fu.predict_empty_timestamp(
            s["fuel_amount"], s["burn_rate"], s["updated_at"]
        )

        for threshold in THRESHOLDS:
            if hours_left <= threshold:
                already_sent = await db.alert_already_sent(s["id"], threshold)
                if not already_sent:
                    await _send_alert(channel, s, estimated_fuel,
                                      hours_left, empty_ts, threshold)
                    await db.mark_alert_sent(s["id"], threshold)
                break   # only fire the most urgent unsent threshold


async def _send_alert(
    channel: discord.TextChannel,
    structure: dict,
    estimated_fuel: int,
    hours_left: float,
    empty_ts: int,
    threshold: int,
) -> None:
    """Build and send the alert embed with role pings."""

    emoji = fu.fuel_status_emoji(hours_left)
    color = {
        True:  discord.Color.red(),
    }.get(hours_left <= 24, discord.Color.orange() if hours_left <= 72 else discord.Color.yellow())

    embed = discord.Embed(
        title=f"{emoji} Fuel Alert – {structure['name']}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="System",        value=structure["system"],                    inline=True)
    embed.add_field(name="Type",          value=structure["type"],                      inline=True)
    embed.add_field(name="Fuel Remaining",value=f"{estimated_fuel:,} blocks",           inline=True)
    embed.add_field(name="Burn Rate",     value=f"{structure['burn_rate']:.1f} blk/hr", inline=True)
    embed.add_field(name="Time Left",     value=fu.format_duration(hours_left),         inline=True)
    embed.add_field(name="Empty At",      value=f"<t:{empty_ts}:F> (<t:{empty_ts}:R>)", inline=False)
    embed.set_footer(text=f"Threshold: ≤{threshold}h remaining")

    # Collect role mentions
    role_ids = await db.get_reminder_roles(structure["id"])
    mentions = " ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else ""

    await channel.send(content=mentions or None, embed=embed)
