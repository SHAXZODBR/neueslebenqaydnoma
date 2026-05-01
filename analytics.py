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
    """Generate a formatted text summary for a given date, showing optimized check-in times."""
    all_workers = db.get_all_workers()
    all_checkins_raw = db.get_checkins_for_date(target_date)
    # ONLY file submissions — exclude location-only, text, chat join entries
    all_checkins = [c for c in all_checkins_raw if c.get("media_file_id")]
    groups = db.get_all_groups()

    if not all_workers:
        return i18n.NO_WORKERS

    # Group check-ins by (group_id, user_id)
    worker_stats = {}
    present_ids = set()
    
    for c in all_checkins:
        gid = c["group_id"]
        uid = c["user_id"]
        present_ids.add(uid)
        
        t_dt = _parse_ts(c["timestamp"])
        t_str = t_dt.strftime("%H:%M")
        
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
        if "first_checkin" not in worker_stats[key] or c["timestamp"] < worker_stats[key]["first_checkin"]:
            worker_stats[key]["first_checkin"] = c["timestamp"]

    # Deduplicate timestamps in the same minute for a cleaner report
    def format_times(times: list[str]) -> str:
        s_times = sorted(list(set(times)))  # Deduplicate: each unique minute once
        return ", ".join([f"`{t}`" for t in s_times])

    lines = [i18n.REPORT_TITLE.format(target_date, target_date)]
    lines.append(f"━━━━━━━━━━━━━━━━━━\n")

    # ── Group-by-group breakdown ─────────────────────────────────────
    if groups:
        for grp in groups:
            gid = grp["group_id"]
            grp_stats = [s for k, s in worker_stats.items() if k[0] == gid]
            if not grp_stats:
                continue
            
            lines.append(f"🏘 *{_esc(grp['group_name'] or 'Группа')}*")
            for stat in grp_stats:
                name = _esc(f"{stat['first_name']} {stat['last_name']}".strip())
                uname = f" (@{_esc(stat['username'])})" if stat["username"] else ""
                status = get_worker_status(stat["first_checkin"])
                times_str = format_times(stat["times"])
                lines.append(f"  {status} *{name}*{uname}\n     └─ {times_str}")
            lines.append("")

    # ── Stats Summary ───────────────────────────────────────────────
    total = len(all_workers)
    present = len(present_ids)
    late_count = sum(1 for s in worker_stats.values() if i18n.STATUS_LATE in get_worker_status(s["first_checkin"]))
    absent_count = total - present

    lines.append(f"{i18n.STATS_TITLE}")
    lines.append(f"  {i18n.TOTAL_WORKERS}: `{total}`")
    lines.append(f"  {i18n.PRESENT}: `{present}`")
    lines.append(f"  {i18n.LATE}: `{late_count}`")
    lines.append(f"  {i18n.ABSENT}: `{absent_count}`\n")

    # ── Detailed Absent List ─────────────────────────────────────────
    absent_workers = [w for w in all_workers if w["user_id"] not in present_ids]
    if absent_workers:
        lines.append(f"{i18n.ABSENT_LIST_TITLE}")
        
        # Group absents by last known group
        last_groups = db.get_workers_last_groups()
        absents_by_group = {}
        for w in absent_workers:
            grp_name = last_groups.get(w["user_id"], "Новички / Новые")
            absents_by_group.setdefault(grp_name, []).append(w)
            
        for grp_name, workers in sorted(absents_by_group.items()):
            lines.append(f"  📍 *{_esc(grp_name)}*")
            for w in workers:
                name = _esc(f"{w['first_name']} {w['last_name']}".strip())
                uname = f" (@{_esc(w['username'])})" if w["username"] else ""
                lines.append(f"    • {name}{uname}")
    
    lines.append(f"\n━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def generate_weekly_stats(end_date: str) -> str:
    """Generate a weekly attendance overview ending on end_date.

    Shows, for each worker, the per-day status across the 7-day window,
    including which group they checked in to on each present day.
    """
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")

    all_workers = db.get_all_workers()
    # Pull full info so we can show group + date breakdown (file submissions only)
    checkins_raw = db.get_checkins_for_range(start_str, end_date)
    checkins = [c for c in checkins_raw if c.get("media_file_id")]

    if not all_workers:
        return i18n.NO_WORKERS

    # All 7 dates in the window (chronological)
    week_dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    # Per-worker map: date -> set of group names checked in to that day
    worker_day_groups: dict[int, dict[str, set[str]]] = {}
    for c in checkins:
        uid = c["user_id"]
        d = c["date"]
        gname = c.get("group_name") or "—"
        worker_day_groups.setdefault(uid, {}).setdefault(d, set()).add(gname)

    # Group workers by last known group, like the daily report
    last_groups = db.get_workers_last_groups()
    workers_by_group: dict[str, list[dict]] = {}
    for w in all_workers:
        grp_name = last_groups.get(w["user_id"], "Новички / Новые")
        workers_by_group.setdefault(grp_name, []).append(w)

    lines = [f"📊 *Weekly Report: {start_str} → {end_date}*"]
    lines.append("━━━━━━━━━━━━━━━━━━\n")

    for grp_name in sorted(workers_by_group.keys()):
        lines.append(f"🏘 *{_esc(grp_name)}*")
        for w in sorted(workers_by_group[grp_name], key=lambda x: (x.get("first_name") or "", x.get("last_name") or "")):
            uid = w["user_id"]
            name = _esc(f"{w['first_name']} {w['last_name']}".strip())
            uname = f" (@{_esc(w['username'])})" if w["username"] else ""
            day_map = worker_day_groups.get(uid, {})
            days_present = len(day_map)

            lines.append(f"  • *{name}*{uname} — {i18n.DAYS_PRESENT.format(days_present)}")
            for d in week_dates:
                short = datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m %a")
                if d in day_map:
                    grps = ", ".join(_esc(g) for g in sorted(day_map[d]))
                    lines.append(f"     ✅ `{short}` — {grps}")
                else:
                    lines.append(f"     ❌ `{short}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
