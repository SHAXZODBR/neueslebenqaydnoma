"""
Attendance Tracking Bot — Cloud Serverless Version (FastAPI + Supabase).

This version runs on Vercel and uses Webhooks for real-time updates
and Vercel Cron for daily automated reports.
"""

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import FastAPI, Request, Response
from telegram import Update, Message, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
import database_supabase as db
import i18n
from analytics import generate_daily_text_summary, generate_weekly_stats
from export import generate_export

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── FastAPI Setup ────────────────────────────────────────────────────────
app = FastAPI()

# Global Application instance (lazy-init)
bot_app = None

async def get_bot_app():
    global bot_app
    if bot_app is None:
        bot_app = Application.builder().token(config.BOT_TOKEN).build()
        _register_handlers(bot_app)
        await bot_app.initialize()
    return bot_app

# ── Helpers ──────────────────────────────────────────────────────────────

def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)

def _now() -> datetime:
    return datetime.now(_tz())

def _register_user(user) -> None:
    db.upsert_worker(
        user_id=user.id,
        username=user.username or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )

def _register_group(chat) -> None:
    if chat.type in ("group", "supergroup"):
        db.upsert_group(group_id=chat.id, group_name=chat.title or "")

async def _is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)

def _admin_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(i18n.BUTTON_TODAY), KeyboardButton(i18n.BUTTON_EXCEL)],
        [KeyboardButton(i18n.BUTTON_WEEKLY), KeyboardButton(i18n.BUTTON_EXPORT_ALL)],
        [KeyboardButton(i18n.BUTTON_HELP)],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ── Check-in Handlers ────────────────────────────────────────────────────

async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or chat.type not in ("group", "supergroup"):
        return

    _register_user(user)
    _register_group(chat)

    media_type = "photo" if msg.photo else "video"
    file_id = msg.photo[-1].file_id if msg.photo else msg.video.file_id
    now = _now()

    checkin_id = db.add_checkin(
        user_id=user.id,
        group_id=chat.id,
        media_file_id=file_id,
        media_type=media_type,
        timestamp=now,
    )
    
    # Store in user_data for location linking (persists across webhook calls if using a persistence layer, 
    # but for serverless we rely on the 5-min window and DB fallback)
    ctx.user_data[f"last_media_{chat.id}"] = {"id": checkin_id, "time": now}
    
    await msg.reply_text(
        i18n.get_media_received(media_type) + "\n" + i18n.SEND_LOCATION,
        quote=True,
    )

async def handle_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not msg.location or not chat or not user or chat.type not in ("group", "supergroup"):
        return

    _register_user(user)
    _register_group(chat)

    now = _now()
    lat, lon = msg.location.latitude, msg.location.longitude

    # Fallback: check DB for any record without location in last 5 min
    db_last = db.get_last_checkin_without_location(user.id, chat.id)
    if db_last:
        ts = datetime.fromisoformat(db_last["timestamp"]).replace(tzinfo=_tz())
        if (now - ts).total_seconds() < 300:
            db.update_checkin_location(db_last["id"], lat, lon)
            await msg.reply_text(i18n.LOCATION_LINKED, quote=True)
            return

    db.add_checkin(user_id=user.id, group_id=chat.id, latitude=lat, longitude=lon, timestamp=now)
    await msg.reply_text(i18n.LOCATION_ONLY, quote=True)

# ── Admin Handlers ───────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat, user = update.effective_chat, update.effective_user
    if chat.type != "private": return
    is_admin = await _is_admin(user.id)
    kb = _admin_keyboard() if is_admin else None
    await update.message.reply_text(
        i18n.START_MESSAGE + "\n\n" +
        (i18n.ADMIN_WELCOME if is_admin else i18n.USER_WELCOME),
        parse_mode="Markdown", reply_markup=kb,
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📋 *Commands*\n\n"
        "*Admin commands (private chat):*\n"
        "  /export `[YYYY-MM-DD]` — Export Excel for a date\n"
        "  /summary `[YYYY-MM-DD]` — Daily attendance summary\n"
        "  /weekly — Weekly attendance stats\n"
        "  /set\\_channel `ID` — Set reporting channel\n"
        "  /refresh\\_summary — Manually send reports\n"
        "  /myid — Get your ID\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Your ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def cmd_set_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.add_admin(user.id)
    await update.message.reply_text(f"✅ Registered as admin! ID: `{user.id}`", parse_mode="Markdown")

async def cmd_export(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not await _is_admin(user.id):
        await update.message.reply_text(f"⛔ Admin only. (ID: `{user.id}`)", parse_mode="Markdown")
        return
    target_date = ctx.args[0] if ctx.args else _now().strftime("%Y-%m-%d")
    await update.message.reply_text(f"⏳ Generating export for {target_date}...")
    checkins = db.get_checkins_for_date(target_date)
    if not checkins:
        await update.message.reply_text("No check-ins found.")
        return
    filepath = generate_export(checkins, title=f"attendance_{target_date}")
    await update.message.reply_document(document=open(filepath, "rb"), filename=f"attendance_{target_date}.xlsx")

async def cmd_export_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not await _is_admin(user.id): return
    await update.message.reply_text("⏳ Generating full export...")
    checkins = db.get_all_checkins()
    filepath = generate_export(checkins, title="attendance_full_export")
    await update.message.reply_document(document=open(filepath, "rb"), filename="attendance_all.xlsx")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    target_date = ctx.args[0] if ctx.args else _now().strftime("%Y-%m-%d")
    text = generate_daily_text_summary(target_date)
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_weekly(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    text = generate_weekly_stats(_now().strftime("%Y-%m-%d"))
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_set_channel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    if not ctx.args:
        curr = db.get_report_channel()
        await update.message.reply_text(f"Current channel: `{curr or 'Not set'}`", parse_mode="Markdown")
        return
    db.set_report_channel(ctx.args[0])
    await update.message.reply_text(f"✅ Channel set: `{ctx.args[0]}`", parse_mode="Markdown")

async def cmd_refresh_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    await update.message.reply_text("⏳ Sending report...")
    await auto_daily_report(ctx)
    await update.message.reply_text("✅ Report sent.")

async def cmd_workers(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    workers = db.get_all_workers()
    lines = [f"👥 *Workers ({len(workers)})*"]
    for i, w in enumerate(workers, 1):
        lines.append(f"{i}. {w['first_name']} {w['last_name']} (@{w['username']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_groups(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    groups = db.get_all_groups()
    lines = [f"📌 *Groups ({len(groups)})*"]
    for i, g in enumerate(groups, 1):
        lines.append(f"{i}. {g['group_name']} (`{g['group_id']}`)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def handle_admin_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if not await _is_admin(update.effective_user.id): return
    mapping = {
        i18n.BUTTON_TODAY: cmd_summary,
        i18n.BUTTON_EXCEL: cmd_export,
        i18n.BUTTON_WEEKLY: cmd_weekly,
        i18n.BUTTON_EXPORT_ALL: cmd_export_all,
        i18n.BUTTON_HELP: cmd_help
    }
    if text in mapping: await mapping[text](update, ctx)

async def handle_new_chat_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.new_chat_members: return
    bot_user = await ctx.bot.get_me()
    for member in msg.new_chat_members:
        if member.id == bot_user.id:
            _register_group(update.effective_chat)
            await msg.reply_text("👋 Hello! Workers can check in here by sending photo/location.")
            break

# ── Scheduled Jobs (Cron) ────────────────────────────────────────────────

async def auto_daily_report(ctx_or_app) -> None:
    """Send daily summary and Excel report."""
    today = _now().strftime("%Y-%m-%d")
    text = generate_daily_text_summary(today)
    checkins = db.get_checkins_for_date(today)
    filepath = generate_export(checkins, title=f"daily_{today}") if checkins else None

    bot = ctx_or_app.bot if hasattr(ctx_or_app, 'bot') else ctx_or_app.bot
    
    # Send to Channel
    channel_id = db.get_report_channel()
    if channel_id:
        try:
            await bot.send_message(chat_id=channel_id, text=text, parse_mode="Markdown")
            if filepath:
                await bot.send_document(chat_id=channel_id, document=open(filepath, "rb"), filename=f"report_{today}.xlsx")
        except Exception as e: logger.error(f"Channel error: {e}")

    # Send to Admins (from env)
    for admin_id in config.ADMIN_IDS:
        try: await bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
        except: pass

# ── FastAPI Endpoints ────────────────────────────────────────────────────

def _register_handlers(application):
    admin_btn_filter = filters.ChatType.PRIVATE & (
        filters.Text("📊 Today's Summary") | filters.Text("📥 Download Excel") |
        filters.Text("📅 Weekly Analytics") | filters.Text("📁 Export All Data") |
        filters.Text("⚙️ Settings / Help")
    )
    application.add_handler(MessageHandler(admin_btn_filter, handle_admin_buttons))
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("set_admin", cmd_set_admin))
    application.add_handler(CommandHandler("export", cmd_export))
    application.add_handler(CommandHandler("summary", cmd_summary))
    application.add_handler(CommandHandler("refresh_summary", cmd_refresh_summary))
    application.add_handler(CommandHandler("weekly", cmd_weekly))
    application.add_handler(CommandHandler("workers", cmd_workers))
    application.add_handler(CommandHandler("groups", cmd_groups))
    application.add_handler(MessageHandler((filters.PHOTO | filters.VIDEO) & filters.ChatType.GROUPS, handle_media))
    application.add_handler(MessageHandler(filters.LOCATION & filters.ChatType.GROUPS, handle_location))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))

@app.post("/api/webhook")
async def webhook_handler(request: Request):
    print("📩 Webhook received!")
    application = await get_bot_app()
    data = await request.json()
    print(f"📦 Payload: {data.get('update_id')}")
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return Response(status_code=200)

@app.get("/api/webhook")
async def webhook_test():
    return {"status": "Webhook endpoint is active. Telegram should use POST."}

@app.get("/api/cron")
async def cron_handler(request: Request):
    # Verify auth token if needed: if request.headers.get("Authorization") != f"Bearer {config.CRON_SECRET}": return Response(status_code=401)
    application = await get_bot_app()
    await auto_daily_report(application)
    return {"status": "success"}

@app.get("/")
async def index():
    return {
        "status": "Attendance Bot Cloud is running",
        "version": "1.0.3",
        "last_update": "2026-04-08 15:10"
    }
