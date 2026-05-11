# EVE Online Fuel Bot 🛢️

A Discord bot that tracks structure fuel levels, predicts when fuel runs out, and auto-pings specific roles with alerts.

---

## Features

| Feature | Details |
|---|---|
| Track structures | Add any Citadel/Engineering Complex/Upwell structure |
| Fuel prediction | Estimates current fuel and exact empty timestamp accounting for burn since last update |
| Auto-reminders | Pings assigned roles at configurable thresholds (default: 7d / 3d / 1d) |
| Per-structure roles | Different roles can be assigned to different structures |
| Fuel history log | Every update is logged with timestamp and optional note |
| Manual check | `/fuel_check_now` triggers an immediate alert sweep |
| ESI-ready | Stub for auto-fetching fuel via EVE ESI (requires OAuth token) |

---

## Setup

### Prerequisites

- A Discord bot application ([Discord Developer Portal](https://discord.com/developers/applications))
  - Enable **applications.commands** scope
  - Enable **bot** scope with **Send Messages** + **Embed Links** + **Mention Everyone** permissions

### Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your bot token |
| `GUILD_ID` | Your Discord server ID |
| `FUEL_ALERT_CHANNEL_ID` | Channel where alerts are posted |
| `THRESHOLD_CRITICAL` | Hours remaining for 🔴 alert (default 24) |
| `THRESHOLD_WARNING` | Hours remaining for 🟠 alert (default 72) |
| `THRESHOLD_NOTICE` | Hours remaining for 🟡 alert (default 168) |
| `FUEL_CHECK_CRON` | Cron schedule for checks (default `0 * * * *` = hourly) |

---

## Running with Docker (recommended)

### Requirements
- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)

### Start

```bash
docker compose up -d
```

That's it. The bot builds, starts, and restarts automatically on reboot.

### Useful commands

```bash
# View live logs
docker compose logs -f

# Stop the bot
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Open a shell inside the container
docker compose exec eve-fuel-bot bash

# Backup the database
docker cp eve-fuel-bot:/app/data/fuel.db ./fuel.db.backup
```

The SQLite database is stored in a named Docker volume (`fuel-data`) so it survives container rebuilds and restarts.

---

## Running without Docker

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python src/bot.py
```

---

## Slash Commands

All commands use Discord slash commands (`/`).

### Structure Management *(requires Manage Server)*

| Command | Description |
|---|---|
| `/fuel_add` | Add a new structure to track |
| `/fuel_remove` | Stop tracking a structure |
| `/fuel_update` | Update fuel level (after a refuel) |
| `/fuel_burnrate` | Change the burn rate for a structure |

### Viewing Status *(any member)*

| Command | Description |
|---|---|
| `/fuel_status` | Detailed status for one or all structures |
| `/fuel_list` | Compact list of all structures |
| `/fuel_history` | Recent fuel log entries for a structure |

### Roles & Alerts *(requires Manage Server)*

| Command | Description |
|---|---|
| `/fuel_role_add` | Assign a role to receive alerts for a structure |
| `/fuel_role_remove` | Remove a role from a structure's alerts |
| `/fuel_check_now` | Manually trigger an immediate fuel check |

---

## Default Burn Rates

| Structure | Blocks/hr |
|---|---|
| Astrahus / Raitaru / Athanor | 3 |
| Fortizar / Azbel / Tatara | 12 |
| Keepstar / Sotiyo | 48 |
| Ansiblex / Pharolux / Tenebrex | 5 |
| Metenox | 10 |

You can override any burn rate with `/fuel_burnrate`.

---

## Alert Colors

| Color | Meaning |
|---|---|
| 🟢 Green | > 7 days remaining |
| 🟡 Yellow | ≤ 7 days remaining |
| 🟠 Orange | ≤ 3 days remaining |
| 🔴 Red | ≤ 1 day remaining |

Alerts are deduplicated — once an alert fires for a threshold, it won't fire again until the structure is refueled.

---

## Project Structure

```
EVE Fuel Bot/
├── src/
│   ├── bot.py              # Entry point, scheduler setup
│   ├── database.py         # SQLite async helpers
│   ├── fuel_utils.py       # Prediction math + ESI helpers
│   ├── reminders.py        # Scheduled alert logic
│   └── cogs/
│       └── fuel_commands.py  # All slash commands
├── data/
│   └── fuel.db             # Auto-created SQLite database (Docker volume)
├── Dockerfile              # Multi-stage build (python:3.12-slim)
├── docker-compose.yml      # One-command deploy
├── .dockerignore
├── .env                    # Your config (not committed)
├── .env.example            # Template
├── requirements.txt
└── README.md
```
