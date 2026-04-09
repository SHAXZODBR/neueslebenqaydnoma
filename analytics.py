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
    """Parse an ISO timestamp string into a timezone-aware datetime and convert to local."""
    dt = datetime.fromisoformat(ts_str)
    tz = ZoneInfo(config.TIMEZONE)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
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


def _esc(text: str) -> str:
    """Escape core Markdown characters."""
    if not text: return ""
    for char in ['_', '*', '[', ']', '`']:
        text = text.replace(char, f"\\{char}")
    return text


def generate_daily_text_summary(target_date: str) -> str:
    """Generate a formatted text summary for a given date, showing all check-in times."""
    all_workers = db.get_all_workers()
    all_checkins = db.get_checkins_for_date(target_date)
    groups = db.get_all_groups()

    if not all_workers:
        return i18n.NO_WORKERS

    # Group check-ins by (group_id, user_id)
    # Use a dictionary to store worker details and a list of their check-in times
    worker_stats = {}
    present_ids = set()
    
    for c in all_checkins:
        gid = c["group_id"]
        uid = c["user_id"]
        present_ids.add(uid)
        
        # Parse time and format
        t_str = _parse_ts(c["timestamp"]).strftime("%H:%M")
        
        key = (gid, uid)
        if key not in worker_stats:
            worker_stats[key] = {
                "user_id": uid,
                "group_id": gid,
                "first_name": c.get("first_name", ""),
                "last_name": c.get("last_name", ""),
                "username": c.get("username", ""),
                "times": []
            }
        worker_stats[key]["times"].append(t_str)
        # Ensure first_checkin for status check (earliest)
        if "first_checkin" not in worker_stats[key] or c["timestamp"] < worker_stats[key]["first_checkin"]:
            worker_stats[key]["first_checkin"] = c["timestamp"]

    absent_workers = [w for w in all_workers if w["user_id"] not in present_ids]

    lines = [f"━━━━━━━━━━━━━━━━━━"]
    lines.append(i18n.REPORT_TITLE.format(target_date, target_date))
    lines.append(f"━━━━━━━━━━━━━━━━━━\n")

    # ── Group-by-group breakdown ─────────────────────────────────────
    if groups:
        for grp in groups:
            gid = grp["group_id"]
            grp_stats = [s for k, s in worker_stats.items() if k[0] == gid]
            if not grp_stats:
                continue
            
            lines.append(f"📌 *{_esc(grp['group_name'] or 'Group ' + str(gid))}*")
            for stat in grp_stats:
                name = _esc(f"{stat['first_name']} {stat['last_name']}".strip())
                uname = f" (@{_esc(stat['username'])})" if stat["username"] else ""
                status = get_worker_status(stat["first_checkin"])
                times_str = ", ".join([f"`{t}`" for t in sorted(list(set(stat["times"])))])
                lines.append(
                    f"  {status} *{name}*{uname} — {times_str}"
                )

    # ── Stats ────────────────────────────────────────────────────────
    total = len(all_workers)
    present = len(present_ids)
    # Late check logic: use the earliest check-in for each present worker
    late_count = 0
    for stat in worker_stats.values():
        if "Late" in get_worker_status(stat["first_checkin"]):
            late_count += 1
    
    absent = len(absent_workers)

    lines.append(f"\n" + i18n.STATS_TITLE)
    lines.append(f"  {i18n.TOTAL_WORKERS}: *{total}*")
    lines.append(f"  {i18n.PRESENT}: *{present}*")
    lines.append(f"  {i18n.LATE}: *{late_count}*")
    lines.append(f"  {i18n.ABSENT}: *{absent}*")

    # ── Absent list ──────────────────────────────────────────────────
    if absent_workers:
        lines.append("\n" + i18n.ABSENT_LIST_TITLE)
        for w in absent_workers:
            name = _esc(f"{w['first_name']} {w['last_name']}".strip())
            uname = f" (@{_esc(w['username'])})" if w["username"] else ""
            lines.append(f"  • {name}{uname}")
    
    lines.append(f"\n━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

    # ── Absent list ──────────────────────────────────────────────────
    if absent_workers:
        lines.append("\n" + i18n.ABSENT_LIST_TITLE)
        for w in absent_workers:
            name = _esc(f"{w['first_name']} {w['last_name']}".strip())
            uname = f" (@{_esc(w['username'])})" if w["username"] else ""
            lines.append(f"  • {name}{uname}")
    
    lines.append(f"\n━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def generate_weekly_stats(end_date: str) -> str:
    """Generate a weekly attendance overview ending on end_date."""
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")

    all_workers = db.get_all_workers()
    # Optimization: only fetch what we need for the weekly count
    checkins = db.get_checkins_for_range(start_str, end_date, columns="user_id, date")

    if not all_workers:
        return "No workers registered."

    # Build per-worker stats
    worker_days: dict[int, set[str]] = {}
    for c in checkins:
        worker_days.setdefault(c["user_id"], set()).add(c["date"])

    lines = [f"📊 *Weekly Report: {start_str} → {end_date}*\n"]

    for w in all_workers:
        uid = w["user_id"]
        name = _esc(f"{w['first_name']} {w['last_name']}".strip())
        uname = f" (@{_esc(w['username'])})" if w["username"] else ""
        days_present = len(worker_days.get(uid, set()))
        lines.append(f"  • {name}{uname}: {i18n.DAYS_PRESENT.format(days_present)}")

    return "\n".join(lines)
