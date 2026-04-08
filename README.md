# 🤖 Attendance Tracking Bot

A Telegram bot that tracks worker attendance across multiple groups by capturing **photo + location** check-ins. Exports to Excel with full analytics.

## Features

- 📸📍 **Photo + Location check-ins** — workers send photo and location (in any order, within 5 min)
- 📊 **Excel exports** — detailed check-ins with Google Maps links & photo links + daily summary
- ✅⚠️❌ **Status tracking** — On Time / Late / Absent based on configurable schedule
- 🔔 **Auto daily reports** — sent to admins at end of day
- ⏰ **Check-in reminders** — sent to groups at scheduled times
- 📈 **Weekly stats** — days present per worker
- 💾 **Persistent data** — all data kept from day 1, never deleted

## Quick Start

### 1. Create a Bot
1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token

### 2. Setup
```bash
cd attendancebot

# Create .env from template
cp .env.example .env

# Edit .env — paste your bot token
nano .env

# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

### 3. Configure .env
```env
BOT_TOKEN=123456:ABC-DEF...          # From @BotFather
ADMIN_IDS=123456789                   # Your Telegram user ID (use /myid command)
TIMEZONE=Asia/Tashkent                # Your timezone
SCHEDULE_TIMES=09:00,12:00,15:00,18:00  # Expected check-in times
GRACE_PERIOD_MINUTES=15               # Minutes after schedule to count as "on time"
AUTO_REPORT_HOUR=19                   # Hour to send auto daily summary (24h)
```

### 4. Add to Groups
Add the bot to your worker groups. It will automatically start tracking check-ins.

## Commands

| Command | Where | Description |
|---------|-------|-------------|
| `/start` | Private | Welcome message |
| `/help` | Anywhere | Show all commands |
| `/myid` | Anywhere | Get your Telegram user ID |
| `/set_admin` | Private | Register as admin |
| `/export [date]` | Private | Export Excel for a date (default: today) |
| `/export_range START END` | Private | Export Excel for a date range |
| `/export_all` | Private | Export all historical data |
| `/summary [date]` | Private | Daily text summary |
| `/weekly` | Private | Weekly attendance overview |
| `/workers` | Private | List registered workers |
| `/groups` | Private | List registered groups |

## How Check-ins Work

1. Worker sends a **📸 photo** in the group
2. Bot replies "Photo received, now send location"
3. Worker sends **📍 location** within 5 minutes
4. Bot confirms "✅ Check-in recorded!"

*(Photo and location can be sent in any order)*

## Excel Export Format

**Sheet 1: Check-ins** — Every individual check-in with date, time, group, user info, Google Maps link, photo link

**Sheet 2: Daily Summary** — Per-worker daily overview with check-in count, first/last time, status (✅ On Time / ⚠️ Late / ❌ Absent)
