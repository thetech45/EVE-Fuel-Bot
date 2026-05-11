# -*- coding: utf-8 -*-
"""
fuel_utils.py - Fuel prediction helpers and ESI fetch utilities.
"""

import time
import math
import aiohttp
from datetime import datetime, timezone


# ── Burn rates (fuel blocks/hour) for common structure types ─────────────────
BURN_RATES: dict[str, float] = {
    "Astrahus":         3.0,
    "Fortizar":        12.0,
    "Keepstar":        48.0,
    "Raitaru":          3.0,
    "Azbel":           12.0,
    "Sotiyo":          48.0,
    "Athanor":          3.0,
    "Tatara":          12.0,
    "Ansiblex":         5.0,
    "Pharolux":         5.0,
    "Tenebrex":         5.0,
    "Metenox":         10.0,
    "Custom":           1.0,
}


def hours_remaining(fuel_amount: int, burn_rate: float) -> float:
    """Return how many hours of fuel are left (float)."""
    if burn_rate <= 0:
        return float("inf")
    return fuel_amount / burn_rate


def predict_empty_timestamp(fuel_amount: int, burn_rate: float,
                             updated_at: int) -> int:
    """
    Return the Unix timestamp when fuel will hit zero,
    accounting for time already elapsed since last update.
    """
    now = int(time.time())
    elapsed_hours = (now - updated_at) / 3600
    remaining_fuel = max(0, fuel_amount - elapsed_hours * burn_rate)
    hours_left = remaining_fuel / burn_rate if burn_rate > 0 else float("inf")
    return int(now + hours_left * 3600)


def current_fuel_estimate(fuel_amount: int, burn_rate: float,
                           updated_at: int) -> int:
    """Estimate current fuel blocks accounting for burn since last update."""
    now = int(time.time())
    elapsed_hours = (now - updated_at) / 3600
    return max(0, math.floor(fuel_amount - elapsed_hours * burn_rate))


def format_duration(hours: float) -> str:
    """Convert a float of hours into a human-readable string like '3d 14h 22m'."""
    if hours == float("inf"):
        return "inf"
    total_minutes = int(hours * 60)
    days, remainder = divmod(total_minutes, 1440)
    hrs, mins = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hrs:
        parts.append(f"{hrs}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)


def fuel_status_emoji(hours: float) -> str:
    if hours <= 24:
        return "🔴"
    if hours <= 72:
        return "🟠"
    if hours <= 168:
        return "🟡"
    return "🟢"


# ── ESI helpers ───────────────────────────────────────────────────────────────

ESI_BASE = "https://esi.evetech.net/latest"


async def esi_get_structure_fuel(structure_id: str, access_token: str) -> int | None:
    """
    Fetch fuel blocks remaining for a structure via ESI.
    Requires a valid access token with esi-corporations.read_structures.v1 scope.
    Returns the fuel block count or None on failure.
    """
    url = f"{ESI_BASE}/corporations/structures/{structure_id}/"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("fuel", []):
                        # Fuel blocks type ID = 4051
                        if item.get("type_id") == 4051:
                            return item["quantity"]
    except Exception:
        pass
    return None


async def esi_search_structure(name: str) -> dict | None:
    """Search ESI for a structure by name (public structures only)."""
    url = f"{ESI_BASE}/search/"
    params = {"categories": "structure", "search": name, "strict": "false"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None
