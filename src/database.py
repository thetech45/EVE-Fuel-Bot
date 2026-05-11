# -*- coding: utf-8 -*-
"""
database.py - SQLite helpers for structures, fuel logs, and reminder roles.
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fuel.db")


async def init_db() -> None:
    """Create tables if they don't exist yet."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            -- Structures being tracked
            CREATE TABLE IF NOT EXISTS structures (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                type        TEXT    NOT NULL DEFAULT 'Citadel',
                system      TEXT    NOT NULL DEFAULT 'Unknown',
                -- Current fuel blocks in bay
                fuel_amount INTEGER NOT NULL DEFAULT 0,
                -- Fuel burn rate in blocks/hour (default Fortizar = 12/hr)
                burn_rate   REAL    NOT NULL DEFAULT 12.0,
                -- When fuel_amount was last updated (Unix timestamp)
                updated_at  INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                -- Optional: EVE structure ID for ESI auto-fetch
                esi_id      TEXT
            );

            -- Historical fuel log entries
            CREATE TABLE IF NOT EXISTS fuel_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                structure_id    INTEGER NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
                fuel_amount     INTEGER NOT NULL,
                recorded_at     INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                note            TEXT
            );

            -- Discord roles to ping per structure (many-to-many)
            CREATE TABLE IF NOT EXISTS reminder_roles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                structure_id    INTEGER NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
                role_id         TEXT    NOT NULL,
                UNIQUE(structure_id, role_id)
            );

            -- Track which alerts have already been sent so we don't spam
            CREATE TABLE IF NOT EXISTS sent_alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                structure_id    INTEGER NOT NULL REFERENCES structures(id) ON DELETE CASCADE,
                threshold_hours INTEGER NOT NULL,
                sent_at         INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(structure_id, threshold_hours)
            );
            """
        )
        await db.commit()


# ── Structure CRUD ────────────────────────────────────────────────────────────

async def add_structure(name: str, structure_type: str, system: str,
                        fuel: int, burn_rate: float, esi_id: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO structures (name, type, system, fuel_amount, burn_rate, esi_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, structure_type, system, fuel, burn_rate, esi_id),
        )
        await db.commit()
        return cur.lastrowid


async def remove_structure(structure_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM structures WHERE id = ?", (structure_id,))
        await db.commit()
        return cur.rowcount > 0


async def get_structure(structure_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM structures WHERE id = ?", (structure_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_structure_by_name(name: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM structures WHERE name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_structures() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM structures ORDER BY name") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_fuel(structure_id: int, fuel_amount: int, note: str = "") -> None:
    """Update current fuel and append a log entry."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE structures
               SET fuel_amount = ?, updated_at = strftime('%s','now')
               WHERE id = ?""",
            (fuel_amount, structure_id),
        )
        await db.execute(
            "INSERT INTO fuel_log (structure_id, fuel_amount, note) VALUES (?, ?, ?)",
            (structure_id, fuel_amount, note),
        )
        # Clear sent alerts so reminders fire again after a refuel
        await db.execute(
            "DELETE FROM sent_alerts WHERE structure_id = ?", (structure_id,)
        )
        await db.commit()


async def update_burn_rate(structure_id: int, burn_rate: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE structures SET burn_rate = ? WHERE id = ?",
            (burn_rate, structure_id),
        )
        await db.commit()


# ── Fuel log ──────────────────────────────────────────────────────────────────

async def get_fuel_history(structure_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM fuel_log
               WHERE structure_id = ?
               ORDER BY recorded_at DESC LIMIT ?""",
            (structure_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ── Reminder roles ────────────────────────────────────────────────────────────

async def add_reminder_role(structure_id: int, role_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO reminder_roles (structure_id, role_id) VALUES (?, ?)",
            (structure_id, role_id),
        )
        await db.commit()


async def remove_reminder_role(structure_id: int, role_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM reminder_roles WHERE structure_id = ? AND role_id = ?",
            (structure_id, role_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_reminder_roles(structure_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role_id FROM reminder_roles WHERE structure_id = ?", (structure_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


# ── Sent-alert deduplication ──────────────────────────────────────────────────

async def alert_already_sent(structure_id: int, threshold_hours: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM sent_alerts WHERE structure_id = ? AND threshold_hours = ?",
            (structure_id, threshold_hours),
        ) as cur:
            return await cur.fetchone() is not None


async def mark_alert_sent(structure_id: int, threshold_hours: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO sent_alerts (structure_id, threshold_hours)
               VALUES (?, ?)""",
            (structure_id, threshold_hours),
        )
        await db.commit()
