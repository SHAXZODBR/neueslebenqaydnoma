"""Configuration module — loads settings from .env file."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# ── Admin ────────────────────────────────────────────────────────────────
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [int(x.strip()) for x in _raw_admins.split(",") if x.strip()]

# ── Timezone ─────────────────────────────────────────────────────────────
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Tashkent")

# ── Schedule ─────────────────────────────────────────────────────────────
_raw_schedule = os.getenv("SCHEDULE_TIMES", "09:00,12:00,15:00,18:00")
SCHEDULE_TIMES: list[str] = [t.strip() for t in _raw_schedule.split(",") if t.strip()]

# Grace period (minutes) after scheduled time to still count as "on time"
GRACE_PERIOD_MINUTES: int = int(os.getenv("GRACE_PERIOD_MINUTES", "15"))

# Hour (24h) to auto-send the daily report
AUTO_REPORT_HOUR: int = int(os.getenv("AUTO_REPORT_HOUR", "19"))

# Default channel for daily reports (can be overridden via DB)
REPORT_CHANNEL_ID: str = os.getenv("REPORT_CHANNEL_ID", "")

# ── Cloud / Deployment ───────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

VERCEL_URL: str = os.getenv("VERCEL_URL", "")  # e.g. https://your-app.vercel.app
WEBHOOK_PATH: str = "/api/webhook"
CRON_SECRET: str = os.getenv("CRON_SECRET", "")  # For securing cron endpoint

# ── Filesystem (Vercel uses /tmp) ────────────────────────────────────────
EXPORTS_DIR: str = "/tmp/attendance_exports"
