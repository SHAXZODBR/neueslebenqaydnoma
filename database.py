"""SQLite database layer for attendance tracking."""

import os
import sqlite3
from datetime import datetime, date
from typing import Optional

import config


def _ensure_dirs() -> None:
    """Create data directories if they don't exist."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.EXPORTS_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    _ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id    INTEGER PRIMARY KEY,
                group_name  TEXT    NOT NULL DEFAULT '',
                added_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workers (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT    DEFAULT '',
                first_name  TEXT    DEFAULT '',
                last_name   TEXT    DEFAULT '',
                first_seen  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS checkins (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                group_id      INTEGER NOT NULL,
                latitude      REAL,
                longitude     REAL,
                media_file_id TEXT,
                media_type    TEXT,  -- 'photo' or 'video'
                timestamp     TEXT    NOT NULL,
                date          TEXT    NOT NULL,
                FOREIGN KEY (user_id)  REFERENCES workers(user_id),
                FOREIGN KEY (group_id) REFERENCES groups(group_id)
            );

            CREATE INDEX IF NOT EXISTS idx_checkins_date     ON checkins(date);
            CREATE INDEX IF NOT EXISTS idx_checkins_user_date ON checkins(user_id, date);

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS pending_photos (
                user_id       INTEGER NOT NULL,
                group_id      INTEGER NOT NULL,
                photo_file_id TEXT    NOT NULL,
                timestamp     TEXT    NOT NULL,
                PRIMARY KEY (user_id, group_id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ── Settings ─────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_report_channel() -> str:
    return get_setting("report_channel_id", config.REPORT_CHANNEL_ID)


def set_report_channel(channel_id: str) -> None:
    set_setting("report_channel_id", channel_id)


# ── Upsert helpers ───────────────────────────────────────────────────────

def upsert_group(group_id: int, group_name: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO groups (group_id, group_name, added_at) VALUES (?, ?, ?) "
            "ON CONFLICT(group_id) DO UPDATE SET group_name = excluded.group_name",
            (group_id, group_name, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_worker(user_id: int, username: str, first_name: str, last_name: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO workers (user_id, username, first_name, last_name, first_seen) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "username   = excluded.username, "
            "first_name = excluded.first_name, "
            "last_name  = excluded.last_name",
            (user_id, username or "", first_name or "", last_name or "",
             datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


# ── Check-in ─────────────────────────────────────────────────────────────

def add_checkin(
    user_id: int,
    group_id: int,
    media_file_id: Optional[str] = None,
    media_type: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    """Insert a check-in record. Returns the row id."""
    if timestamp is None:
        timestamp = datetime.now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO checkins "
            "(user_id, group_id, latitude, longitude, media_file_id, media_type, timestamp, date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, group_id, latitude, longitude, media_file_id, media_type,
             timestamp.isoformat(), timestamp.strftime("%Y-%m-%d")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_checkin_location(checkin_id: int, latitude: float, longitude: float) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE checkins SET latitude = ?, longitude = ? WHERE id = ?",
            (latitude, longitude, checkin_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_checkin_without_location(user_id: int, group_id: int) -> Optional[dict]:
    """Get the most recent check-in for a user in a group that doesn't have a location yet."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM checkins "
            "WHERE user_id = ? AND group_id = ? AND latitude IS NULL AND longitude IS NULL "
            "ORDER BY timestamp DESC LIMIT 1",
            (user_id, group_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Pending photos (for separate photo+location workflow) ────────────────

def save_pending_photo(user_id: int, group_id: int, photo_file_id: str, timestamp: datetime) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO pending_photos (user_id, group_id, photo_file_id, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (user_id, group_id, photo_file_id, timestamp.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def pop_pending_photo(user_id: int, group_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM pending_photos WHERE user_id = ? AND group_id = ?",
            (user_id, group_id),
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM pending_photos WHERE user_id = ? AND group_id = ?",
                (user_id, group_id),
            )
            conn.commit()
            return dict(row)
        return None
    finally:
        conn.close()


# ── Queries ──────────────────────────────────────────────────────────────

def get_checkins_for_date(target_date: str) -> list[dict]:
    """Return all check-ins for a given date (YYYY-MM-DD)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT c.*, w.username, w.first_name, w.last_name, g.group_name "
            "FROM checkins c "
            "JOIN workers w ON c.user_id = w.user_id "
            "JOIN groups  g ON c.group_id = g.group_id "
            "WHERE c.date = ? ORDER BY c.timestamp",
            (target_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_checkins_for_range(start_date: str, end_date: str) -> list[dict]:
    """Return all check-ins for a date range inclusive."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT c.*, w.username, w.first_name, w.last_name, g.group_name "
            "FROM checkins c "
            "JOIN workers w ON c.user_id = w.user_id "
            "JOIN groups  g ON c.group_id = g.group_id "
            "WHERE c.date BETWEEN ? AND ? ORDER BY c.date, c.timestamp",
            (start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_checkins() -> list[dict]:
    """Return every check-in ever recorded."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT c.*, w.username, w.first_name, w.last_name, g.group_name "
            "FROM checkins c "
            "JOIN workers w ON c.user_id = w.user_id "
            "JOIN groups  g ON c.group_id = g.group_id "
            "ORDER BY c.date, c.timestamp",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_workers() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM workers ORDER BY first_name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_groups() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM groups ORDER BY group_name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_worker_checkin_count(user_id: int, target_date: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM checkins WHERE user_id = ? AND date = ?",
            (user_id, target_date),
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def get_daily_summary(target_date: str) -> list[dict]:
    """Get per-worker summary for a date: count, first/last check-in."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT c.user_id, w.username, w.first_name, w.last_name, "
            "  g.group_name, g.group_id, "
            "  COUNT(*) as checkin_count, "
            "  MIN(c.timestamp) as first_checkin, "
            "  MAX(c.timestamp) as last_checkin "
            "FROM checkins c "
            "JOIN workers w ON c.user_id = w.user_id "
            "JOIN groups  g ON c.group_id = g.group_id "
            "WHERE c.date = ? "
            "GROUP BY c.user_id, c.group_id "
            "ORDER BY g.group_name, w.first_name",
            (target_date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Admin management ─────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    """Check whether user_id is a registered admin (DB or env)."""
    if user_id in config.ADMIN_IDS:
        return True
    conn = get_connection()
    try:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def add_admin(user_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
    finally:
        conn.close()


def get_unique_dates() -> list[str]:
    """Return all unique dates that have at least one check-in."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT date FROM checkins ORDER BY date"
        ).fetchall()
        return [r["date"] for r in rows]
    finally:
        conn.close()
