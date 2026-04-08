"""Attendance analytics — summaries, late/absent detection, reports."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import config
import database_supabase as db
import i18n


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)

def _now() -> datetime:
    return datetime.now(_tz())


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO timestamp string into a timezone-aware datetime."""
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(config.TIMEZONE))
    return dt


def _schedule_times() -> list[time]:
    """Parse SCHEDULE_TIMES config into list of time objects."""
    result = []
    for t_str in config.SCHEDULE_TIMES:
        parts = t_str.split(":")
        result.append(time(int(parts[0]), int(parts[1])))
    return sorted(result)


def get_worker_status(first_checkin_ts: str) -> str:
    """Determine status based on first check-in vs first schedule time."""
    schedule = _schedule_times()
    if not schedule:
        return "✅ Present"

    first_dt = _parse_ts(first_checkin_ts)
    first_time = first_dt.time()
    earliest = schedule[0]
    grace = timedelta(minutes=config.GRACE_PERIOD_MINUTES)
    deadline = (datetime.combine(first_dt.date(), earliest) + grace).time()

    if first_time <= deadline:
        return i18n.STATUS_ON_TIME
    else:
        return i18n.STATUS_LATE


def generate_daily_text_summary(target_date: str) -> str:
    """Generate a formatted text summary for a given date."""
    all_workers = db.get_all_workers()
    summary_rows = db.get_daily_summary(target_date)
    groups = db.get_all_groups()

    if not all_workers:
        return i18n.NO_WORKERS

    present_ids = {row["user_id"] for row in summary_rows}
    absent_workers = [w for w in all_workers if w["user_id"] not in present_ids]

    lines = [i18n.REPORT_TITLE.format(target_date, target_date) + "\n"]

    # ── Group-by-group breakdown ─────────────────────────────────────
    if groups:
        for grp in groups:
            grp_rows = [r for r in summary_rows if r["group_id"] == grp["group_id"]]
            if not grp_rows:
                continue
            lines.append(f"\n📌 *{grp['group_name'] or 'Group ' + str(grp['group_id'])}*")
            for row in grp_rows:
                name = f"{row['first_name']} {row['last_name']}".strip()
                uname = f" (@{row['username']})" if row["username"] else ""
                status = get_worker_status(row["first_checkin"])
                first_t = _parse_ts(row["first_checkin"]).strftime("%H:%M")
                last_t = _parse_ts(row["last_checkin"]).strftime("%H:%M")
                lines.append(
                    f"  {status} {name}{uname} — "
                    f"{row['checkin_count']}x "
                    f"(first: {first_t}, last: {last_t})"
                )

    # ── Stats ────────────────────────────────────────────────────────
    total = len(all_workers)
    present = len(present_ids)
    late = sum(1 for r in summary_rows if "Late" in get_worker_status(r["first_checkin"]))
    absent = len(absent_workers)

    lines.append(i18n.STATS_TITLE)
    lines.append(f"  {i18n.TOTAL_WORKERS}: {total}")
    lines.append(f"  {i18n.PRESENT}: {present}")
    lines.append(f"  {i18n.LATE}: {late}")
    lines.append(f"  {i18n.ABSENT}: {absent}")

    # ── Absent list ──────────────────────────────────────────────────
    if absent_workers:
        lines.append("\n" + i18n.ABSENT_LIST_TITLE)
        for w in absent_workers:
            name = f"{w['first_name']} {w['last_name']}".strip()
            uname = f" (@{w['username']})" if w["username"] else ""
            lines.append(f"  • {name}{uname}")

    return "\n".join(lines)


def generate_weekly_stats(end_date: str) -> str:
    """Generate a weekly attendance overview ending on end_date."""
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")

    all_workers = db.get_all_workers()
    checkins = db.get_checkins_for_range(start_str, end_date)

    if not all_workers:
        return "No workers registered."

    # Build per-worker stats
    worker_days: dict[int, set[str]] = {}
    for c in checkins:
        worker_days.setdefault(c["user_id"], set()).add(c["date"])

    lines = [f"📊 *Weekly Report: {start_str} → {end_date}*\n"]

    for w in all_workers:
        uid = w["user_id"]
        name = f"{w['first_name']} {w['last_name']}".strip()
        uname = f" (@{w['username']})" if w["username"] else ""
        days_present = len(worker_days.get(uid, set()))
        lines.append(f"  • {name}{uname}: {days_present}/7 days")

    return "\n".join(lines)
