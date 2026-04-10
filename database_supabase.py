"""Supabase (PostgreSQL) database layer for cloud attendance tracking."""

import config
from supabase import create_client, Client
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict

# Initialize Supabase client
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

def _now() -> datetime:
    """Return current localized time."""
    return datetime.now(ZoneInfo(config.TIMEZONE))

def init_db() -> None:
    """
    In Supabase, we usually create tables via the Dashboard or SQL Editor.
    This function can be used to verify connection or run health checks.
    """
    # For now, we assume tables are created via SQL Editor (see supabase_schema.sql)
    pass

# ── Settings ─────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    res = supabase.table("settings").select("value").eq("key", key).maybe_single().execute()
    return res.data["value"] if res.data else default

def set_setting(key: str, value: str) -> None:
    supabase.table("settings").upsert({"key": key, "value": value}).execute()

def get_report_channel() -> str:
    return get_setting("report_channel_id", config.REPORT_CHANNEL_ID)

def set_report_channel(channel_id: str) -> None:
    set_setting("report_channel_id", channel_id)

# ── Upsert helpers ───────────────────────────────────────────────────────

def upsert_group(group_id: int, group_name: str) -> None:
    supabase.table("groups").upsert({
        "group_id": group_id,
        "group_name": group_name,
        "added_at": _now().isoformat()
    }).execute()

def upsert_worker(user_id: int, username: str, first_name: str, last_name: str) -> None:
    supabase.table("workers").upsert({
        "user_id": user_id,
        "username": username or "",
        "first_name": first_name or "",
        "last_name": last_name or "",
        # "first_seen" removed so it's only set by DB default on INSERT
    }).execute()

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
        timestamp = _now()
    
    data = {
        "user_id": user_id,
        "group_id": group_id,
        "latitude": latitude,
        "longitude": longitude,
        "media_file_id": media_file_id,
        "media_type": media_type,
        "timestamp": timestamp.isoformat(),
        "date": timestamp.strftime("%Y-%m-%d")
    }
    res = supabase.table("checkins").insert(data).execute()
    return res.data[0]["id"] if res.data else 0

def update_checkin_location(checkin_id: int, latitude: float, longitude: float) -> None:
    supabase.table("checkins").update({
        "latitude": latitude,
        "longitude": longitude
    }).eq("id", checkin_id).execute()

def get_last_checkin_without_location(user_id: int, group_id: int) -> Optional[dict]:
    res = supabase.table("checkins") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("group_id", group_id) \
        .is_("latitude", "NULL") \
        .is_("longitude", "NULL") \
        .order("timestamp", desc=True) \
        .limit(1) \
        .maybe_single() \
        .execute()
    return res.data if res.data else None

# ── Queries ──────────────────────────────────────────────────────────────

def get_checkins_for_date(target_date: str, columns: str = "*, workers(*), groups(*)") -> List[Dict]:
    res = supabase.table("checkins") \
        .select(columns) \
        .eq("date", target_date) \
        .order("timestamp") \
        .execute()
    
    # Flatten the result if usingJoined fetch
    if columns == "*, workers(*), groups(*)":
        return _flatten_checkins(res.data)
    return res.data

def get_checkins_for_range(start_date: str, end_date: str, columns: str = "*, workers(*), groups(*)") -> List[Dict]:
    res = supabase.table("checkins") \
        .select(columns) \
        .gte("date", start_date) \
        .lte("date", end_date) \
        .order("date") \
        .order("timestamp") \
        .execute()
    
    if columns == "*, workers(*), groups(*)":
        return _flatten_checkins(res.data)
    return res.data

def get_all_checkins() -> List[Dict]:
    res = supabase.table("checkins") \
        .select("*, workers(*), groups(*)") \
        .order("date") \
        .order("timestamp") \
        .execute()
    return _flatten_checkins(res.data)

def _flatten_checkins(data: List[Dict]) -> List[Dict]:
    if not data: return []
    flattened = []
    for item in data:
        worker = item.get("workers", {})
        group = item.get("groups", {})
        item["username"] = worker.get("username", "")
        item["first_name"] = worker.get("first_name", "")
        item["last_name"] = worker.get("last_name", "")
        item["group_name"] = group.get("group_name", "")
        flattened.append(item)
    return flattened

def get_all_workers() -> List[Dict]:
    res = supabase.table("workers").select("*").order("first_name").execute()
    return res.data

def get_all_groups() -> List[Dict]:
    res = supabase.table("groups").select("*").order("group_name").execute()
    return res.data

def get_worker_checkin_count(user_id: int, target_date: str) -> int:
    res = supabase.table("checkins") \
        .select("id", count="exact") \
        .eq("user_id", user_id) \
        .eq("date", target_date) \
        .execute()
    return res.count if res.count is not None else 0

def get_daily_summary(target_date: str) -> List[Dict]:
    """Get per-worker summary for a date: count, first/last check-in."""
    # Fetch all checkins for the date with related data
    checkins = get_checkins_for_date(target_date)
    
    if not checkins:
        return []

    # Map to hold aggregated data: (user_id, group_id) -> summary
    summary_map = {}

    for c in checkins:
        key = (c["user_id"], c["group_id"])
        ts = c["timestamp"]
        
        if key not in summary_map:
            summary_map[key] = {
                "user_id": c["user_id"],
                "username": c.get("username", ""),
                "first_name": c.get("first_name", ""),
                "last_name": c.get("last_name", ""),
                "group_name": c.get("group_name", ""),
                "group_id": c["group_id"],
                "checkin_count": 0,
                "first_checkin": ts,
                "last_checkin": ts
            }
        
        s = summary_map[key]
        s["checkin_count"] += 1
        if ts < s["first_checkin"]:
            s["first_checkin"] = ts
        if ts > s["last_checkin"]:
            s["last_checkin"] = ts

    # Convert map back to list and sort
    results = list(summary_map.values())
    results.sort(key=lambda x: (x["group_name"], x["first_name"]))
    return results

def get_unique_dates() -> List[str]:
    res = supabase.table("checkins").select("date").execute()
    if not res.data: return []
    dates = sorted(list(set(item["date"] for item in res.data)))
    return dates

def get_workers_last_groups() -> Dict[int, str]:
    """Get a mapping of user_id -> last group name they checked into."""
    res = supabase.table("checkins") \
        .select("user_id, group_id, groups(group_name)") \
        .order("timestamp", desc=True) \
        .execute()
    
    mapping = {}
    for item in res.data:
        uid = item["user_id"]
        if uid not in mapping:
            grp = item.get("groups", {})
            mapping[uid] = grp.get("group_name", "Unknown Group")
    return mapping

# ── Admin management ─────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    res = supabase.table("admins").select("user_id").eq("user_id", user_id).maybe_single().execute()
    return res.data is not None

def add_admin(user_id: int) -> None:
    supabase.table("admins").upsert({"user_id": user_id}).execute()

def get_all_admin_ids() -> List[int]:
    """Get all admin IDs from both .env and DB."""
    ids = set(config.ADMIN_IDS)
    res = supabase.table("admins").select("user_id").execute()
    for row in res.data:
        ids.add(row["user_id"])
    return list(ids)
