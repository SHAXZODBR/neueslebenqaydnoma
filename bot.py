"""
Attendance Tracking Bot — Cloud Serverless Version (FastAPI + Supabase).

This version runs on Vercel and uses Webhooks for real-time updates
and Vercel Cron for daily automated reports.
"""

import asyncio
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

    if msg.photo:
        media_type = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.video_note:
        media_type = "video_note"
        file_id = msg.video_note.file_id
    elif msg.video:
        media_type = "video"
        file_id = msg.video.file_id
    elif msg.document:
        media_type = "photo" # Treat as photo for logic
        file_id = msg.document.file_id
    else:
        return

    now = _now()
    checkin_id = db.add_checkin(
        user_id=user.id,
        group_id=chat.id,
        media_file_id=file_id,
        media_type=media_type,
        timestamp=now,
    )
    
    # Store in user_data for location linking
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

    # 1. Fallback: check DB for any record without location in last 5 min (likely just sent a photo)
    db_last = db.get_last_checkin_without_location(user.id, chat.id)
    if db_last:
        ts = datetime.fromisoformat(db_last["timestamp"]).replace(tzinfo=_tz())
        if (now - ts).total_seconds() < 300:
            db.update_checkin_location(db_last["id"], lat, lon)
            await msg.reply_text(i18n.LOCATION_LINKED, quote=True)
            return

    # 2. Prevent duplicate "Location Only" messages and records (e.g. from Live Location updates)
    # Check if we already have a location record in the last 2 minutes
    # If so, just update it quietly instead of spamming "Location Saved"
    all_recent = db.get_checkins_for_date(now.strftime("%Y-%m-%d"))
    recent_loc = [c for c in all_recent if c["user_id"] == user.id and c["group_id"] == chat.id]
    if recent_loc:
        last_rec = recent_loc[-1]
        last_ts = datetime.fromisoformat(last_rec["timestamp"]).replace(tzinfo=_tz())
        if (now - last_ts).total_seconds() < 120: # 2 minutes debounce
            db.update_checkin_location(last_rec["id"], lat, lon)
            # No message sent to avoid spam
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
    await update.message.reply_text(i18n.HELP_TEXT, parse_mode="Markdown")

async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(i18n.MY_ID.format(update.effective_user.id), parse_mode="Markdown")

async def cmd_set_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # Only existing admins can add new ones
    if not await _is_admin(user.id):
        await update.message.reply_text("⛔ Admin only.", parse_mode="Markdown")
        return
        
    if not ctx.args:
        await update.message.reply_text("Usage: `/set_admin <telegram_id>`", parse_mode="Markdown")
        return
        
    try:
        new_admin_id = int(ctx.args[0])
        db.add_admin(new_admin_id)
        await update.message.reply_text(i18n.ADMIN_REGISTERED.format(new_admin_id), parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Please provide a numeric Telegram ID.")

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
    await update.message.reply_text(i18n.GENERATING_FULL_EXPORT)
    checkins = db.get_all_checkins()
    filepath = generate_export(checkins, title="attendance_full_export")
    await update.message.reply_document(document=open(filepath, "rb"), filename="attendance_all.xlsx")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    target_date = ctx.args[0] if ctx.args else _now().strftime("%Y-%m-%d")
    text = generate_daily_text_summary(target_date)
    await send_long_message(ctx.bot, update.effective_chat.id, text, parse_mode="Markdown")

async def cmd_weekly(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _is_admin(update.effective_user.id): return
    text = generate_weekly_stats(_now().strftime("%Y-%m-%d"))
    await send_long_message(ctx.bot, update.effective_chat.id, text, parse_mode="Markdown")

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

async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.message or not update.message.text or not update.effective_user:
            return
            
        text = update.message.text
        user_id = update.effective_user.id
        print(f"💬 Received message: '{text}' from user: {user_id}")
        
        is_admin = await _is_admin(user_id)
        print(f"🛡️ Is Admin? {is_admin} (Admins list: {config.ADMIN_IDS})")
        
        if not is_admin: 
            print(f"🚫 User {user_id} is NOT an admin. Ignoring.")
            return
        
        mapping = {
            i18n.BUTTON_TODAY: cmd_summary,
            i18n.BUTTON_EXCEL: cmd_export,
            i18n.BUTTON_WEEKLY: cmd_weekly,
            i18n.BUTTON_EXPORT_ALL: cmd_export_all,
            i18n.BUTTON_HELP: cmd_help
        }
        
        if text in mapping:
            print(f"🎯 Execution command for: {text}")
            await mapping[text](update, ctx)
        else:
            print(f"❓ Text '{text}' not found in mapping: {list(mapping.keys())}")
    except Exception as e:
        print(f"🔥 Error in message_handler: {e}")
        import traceback
        traceback.print_exc()

async def handle_new_chat_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.new_chat_members: return
    bot_user = await ctx.bot.get_me()
    for member in msg.new_chat_members:
        if member.id == bot_user.id:
            _register_group(update.effective_chat)
            await msg.reply_text(i18n.NEW_GROUP_MEMBER)
            break

async def send_long_message(bot, chat_id, text, **kwargs):
    """Split and send message if it exceeds Telegram's 4096 char limit."""
    if len(text) <= 4000:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    
    parts = []
    tmp_text = text
    while tmp_text:
        if len(tmp_text) <= 4000:
            parts.append(tmp_text)
            break
        # Try to split at a newline
        split_at = tmp_text.rfind('\n', 0, 4000)
        if split_at == -1:
            split_at = 4000
        parts.append(tmp_text[:split_at])
        tmp_text = tmp_text[split_at:].lstrip()
    
    for p in parts:
        await bot.send_message(chat_id=chat_id, text=p, **kwargs)


# ── Scheduled Jobs (Cron) ────────────────────────────────────────────────

async def auto_daily_report(ctx_or_app) -> None:
    """Send daily summary and Excel report."""
    logger.info("Starting auto_daily_report...")
    try:
        today = _now().strftime("%Y-%m-%d")
        text = generate_daily_text_summary(today)
        checkins = db.get_checkins_for_date(today)
        filepath = generate_export(checkins, title=f"daily_{today}") if checkins else None

        # Robust bot retrieval
        if hasattr(ctx_or_app, 'bot'):
            bot = ctx_or_app.bot
        elif hasattr(ctx_or_app, 'application'):
            bot = ctx_or_app.application.bot
        else:
            bot = ctx_or_app
            
        logger.info(f"Report generated. Length: {len(text)}. Target date: {today}")

        # ── 1. Send to Channel ───────────────────────────────────────
        channel_id = db.get_report_channel()
        if channel_id:
            logger.info(f"Sending report to channel {channel_id}...")
            try:
                await send_long_message(bot, chat_id=channel_id, text=text, parse_mode="Markdown")
                if filepath:
                    with open(filepath, "rb") as doc:
                        await bot.send_document(chat_id=channel_id, document=doc, filename=f"report_{today}.xlsx")
            except Exception as e:
                logger.error(f"Channel error: {e}")

        # ── 2. Send to Admins (env + DB) ──────────────────────────────
        all_admins = db.get_all_admin_ids()
        logger.info(f"Sending report to {len(all_admins)} admins...")
        
        doc_data = None
        if filepath:
            with open(filepath, "rb") as f:
                doc_data = f.read()

        async def send_to_admin(admin_id):
            try:
                # Use a timeout for each individual send to prevent one slow admin from hanging everything
                await asyncio.wait_for(send_long_message(bot, chat_id=admin_id, text=text, parse_mode="Markdown"), timeout=30)
                if doc_data:
                    await asyncio.wait_for(bot.send_document(chat_id=admin_id, document=doc_data, filename=f"report_{today}.xlsx"), timeout=30)
            except Exception as e:
                logger.error(f"Failed to send to admin {admin_id}: {e}")

        if all_admins:
            # Send concurrently but with an overall timeout
            await asyncio.wait_for(
                asyncio.gather(*(send_to_admin(aid) for aid in all_admins), return_exceptions=True),
                timeout=60
            )

        logger.info("auto_daily_report finished successfully.")

    except Exception as e:
        logger.error(f"Fatal error in auto_daily_report: {e}")
        import traceback
        traceback.print_exc()

# ── FastAPI Endpoints ────────────────────────────────────────────────────

def _register_handlers(application):
    # Command handlers
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
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("set_admin", cmd_set_admin))
    application.add_handler(CommandHandler("export", cmd_export))
    application.add_handler(CommandHandler("summary", cmd_summary))
    application.add_handler(CommandHandler("refresh_summary", cmd_refresh_summary))
    application.add_handler(CommandHandler("weekly", cmd_weekly))
    application.add_handler(CommandHandler("workers", cmd_workers))
    application.add_handler(CommandHandler("groups", cmd_groups))
    application.add_handler(MessageHandler((filters.PHOTO | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.IMAGE | filters.Document.VIDEO) & filters.ChatType.GROUPS, handle_media))
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
        "version": "1.0.4",
        "last_update": "2026-04-09 17:30"
    }
