"""Supabase (PostgreSQL) database layer for cloud attendance tracking."""

import config
from supabase import create_client, Client
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict

# Initialize Supabase client
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

_PAGE_SIZE = 1000  # Supabase default row limit

def _fetch_all(query) -> List[Dict]:
    """Paginate through a Supabase query to fetch ALL rows.
    
    Supabase returns at most 1000 rows per request by default.
    This helper fetches page by page until all data is retrieved.
    """
    all_data = []
    offset = 0
    while True:
        page = query.range(offset, offset + _PAGE_SIZE - 1).execute()
        if not page.data:
            break
        all_data.extend(page.data)
        if len(page.data) < _PAGE_SIZE:
            break  # Last page
        offset += _PAGE_SIZE
    return all_data

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
    # NB: maybe_single() returns None (not an empty response) when no row matches.
    try:
        res = supabase.table("settings").select("value").eq("key", key).maybe_single().execute()
        return res.data["value"] if res and res.data else default
    except Exception as e:
        print(f"⚠️ get_setting({key}) failed: {e}")
        return default

def set_setting(key: str, value: str) -> None:
    supabase.table("settings").upsert({"key": key, "value": value}).execute()

def get_report_channel() -> str:
    return get_setting("report_channel_id", config.REPORT_CHANNEL_ID)

def set_report_channel(channel_id: str) -> None:
    set_setting("report_channel_id", channel_id)

# ── Webhook update de-duplication ────────────────────────────────────────
# Telegram retries an update if the webhook doesn't answer 200 quickly. On
# serverless, each retry can hit a FRESH instance, so an in-memory set is not
# enough — we record processed update_ids in the settings table (key is the
# PRIMARY KEY, so a plain INSERT is an atomic "first writer wins" check).

def try_mark_update_processed(update_id: int) -> bool:
    """Record a Telegram update_id. Returns False if it was already processed
    (by any instance). Fail-open: on unexpected DB errors returns True so real
    updates are never silently dropped."""
    try:
        supabase.table("settings").insert({
            "key": f"upd_{update_id}",
            "value": _now().isoformat(),
        }).execute()
        return True
    except Exception as e:
        msg = str(e)
        # 23505 = Postgres unique violation; PostgREST surfaces it as a 409.
        if "23505" in msg or "409" in msg or "duplicate" in msg.lower():
            return False
        print(f"⚠️ try_mark_update_processed failed (processing anyway): {e}")
        return True

def is_update_processed(update_id: int) -> bool:
    """Read-only check: was this update already fully processed?
    Used for group check-in updates, which are marked AFTER processing so a
    killed invocation gets retried by Telegram instead of losing the check-in."""
    try:
        res = supabase.table("settings").select("key") \
            .eq("key", f"upd_{update_id}").maybe_single().execute()
        return res is not None and res.data is not None
    except Exception as e:
        print(f"⚠️ is_update_processed failed (treating as new): {e}")
        return False

def cleanup_processed_updates(older_than_hours: int = 48) -> None:
    """Delete old upd_* rows so the settings table stays small.
    Telegram never retries an update after 24h, so 48h is safely past that."""
    cutoff = (_now() - timedelta(hours=older_than_hours)).isoformat()
    try:
        # returning="minimal": don't ship every deleted row back over HTTP.
        supabase.table("settings").delete(returning="minimal") \
            .like("key", "upd_%") \
            .lt("value", cutoff) \
            .execute()
    except Exception as e:
        print(f"⚠️ cleanup_processed_updates failed: {e}")

# ── Cross-instance locks ─────────────────────────────────────────────────

def acquire_lock(name: str, ttl_seconds: int = 180) -> Optional[str]:
    """Atomically acquire a named lock via INSERT on the settings PK.

    Returns an ownership token (store it and pass to release_lock), or None if
    another holder has a fresh lock. A stale lock (older than ttl_seconds —
    e.g. its holder was killed) is broken and re-acquired. Fail-open: on
    unexpected DB errors a token is returned so features keep working.
    """
    key = f"lock_{name}"
    token = _now().isoformat()

    def _try_insert() -> bool:
        try:
            supabase.table("settings").insert({"key": key, "value": token}).execute()
            return True
        except Exception as e:
            msg = str(e)
            if "23505" in msg or "409" in msg or "duplicate" in msg.lower():
                return False
            print(f"⚠️ acquire_lock({name}) failed (proceeding unlocked): {e}")
            return True  # fail-open

    if _try_insert():
        return token

    # Lock row exists — is it stale?
    holder = get_setting(key, "")
    try:
        if holder and (_now() - datetime.fromisoformat(holder)).total_seconds() < ttl_seconds:
            return None  # fresh lock, someone else is running
    except ValueError:
        pass  # unparseable value — treat as stale
    # Break the stale lock (only if it still holds the value we saw) and retry once.
    try:
        supabase.table("settings").delete(returning="minimal") \
            .eq("key", key).eq("value", holder).execute()
    except Exception as e:
        print(f"⚠️ acquire_lock({name}) stale-break failed: {e}")
    return token if _try_insert() else None

def release_lock(name: str, token: str) -> None:
    """Release a lock, but only if we still own it (value matches our token)."""
    try:
        supabase.table("settings").delete(returning="minimal") \
            .eq("key", f"lock_{name}").eq("value", token).execute()
    except Exception as e:
        print(f"⚠️ release_lock({name}) failed: {e}")

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
    try:
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
        return res.data if res and res.data else None
    except Exception as e:
        print(f"⚠️ get_last_checkin_without_location failed: {e}")
        return None

# ── Queries ──────────────────────────────────────────────────────────────

def get_checkins_for_date(target_date: str, columns: str = "*, workers(*), groups(*)") -> List[Dict]:
    query = supabase.table("checkins") \
        .select(columns) \
        .eq("date", target_date) \
        .order("timestamp")
    data = _fetch_all(query)
    
    # Flatten the result if using joined fetch
    if columns == "*, workers(*), groups(*)":
        return _flatten_checkins(data)
    return data

def get_checkins_for_range(start_date: str, end_date: str, columns: str = "*, workers(*), groups(*)") -> List[Dict]:
    query = supabase.table("checkins") \
        .select(columns) \
        .gte("date", start_date) \
        .lte("date", end_date) \
        .order("date") \
        .order("timestamp")
    data = _fetch_all(query)
    
    if columns == "*, workers(*), groups(*)":
        return _flatten_checkins(data)
    return data

def get_all_checkins(columns: str = "*, workers(*), groups(*)") -> List[Dict]:
    query = supabase.table("checkins") \
        .select(columns) \
        .order("date") \
        .order("timestamp")
    data = _fetch_all(query)
    if columns == "*, workers(*), groups(*)":
        return _flatten_checkins(data)
    return data

def _flatten_checkins(data: List[Dict]) -> List[Dict]:
    if not data: return []
    flattened = []
    for item in data:
        worker = item.get("workers") or {}
        group = item.get("groups") or {}
        item["username"] = worker.get("username", "")
        item["first_name"] = worker.get("first_name", "")
        item["last_name"] = worker.get("last_name", "")
        item["group_name"] = group.get("group_name", "")
        # Drop check-ins from excluded users / groups entirely.
        if item.get("group_id") in config.EXCLUDED_GROUP_IDS:
            continue
        if _is_excluded_username(item["username"]):
            continue
        flattened.append(item)
    return flattened

def _is_excluded_username(username: str) -> bool:
    return (username or "").lstrip("@").lower() in config.EXCLUDED_USERNAMES

def get_all_workers() -> List[Dict]:
    res = supabase.table("workers").select("*").order("first_name").execute()
    workers = res.data or []
    return [w for w in workers if not _is_excluded_username(w.get("username"))]

def get_all_groups() -> List[Dict]:
    res = supabase.table("groups").select("*").order("group_name").execute()
    groups = res.data or []
    return [g for g in groups if g.get("group_id") not in config.EXCLUDED_GROUP_IDS]

def get_worker_checkin_count(user_id: int, target_date: str) -> int:
    res = supabase.table("checkins") \
        .select("id", count="exact") \
        .eq("user_id", user_id) \
        .eq("date", target_date) \
        .execute()
    return res.count if res.count is not None else 0

def get_daily_summary(target_date: str) -> List[Dict]:
    """Get per-worker summary for a date: count, first/last check-in."""
    # Fetch all checkins for the date with related data — only file submissions
    all_checkins = get_checkins_for_date(target_date)
    checkins = [c for c in all_checkins if c.get("media_file_id")]
    
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

def _last_group_id_map() -> Dict[int, int]:
    """user_id -> group_id of their most recent check-in (excluded groups skipped).

    Scans check-ins newest-first and STOPS as soon as every known worker is
    covered — active rosters are all present within the first few pages, so
    this is typically 2-4 requests instead of paging the whole table.
    """
    worker_ids = {w["user_id"] for w in get_all_workers()}
    mapping: Dict[int, int] = {}
    offset = 0
    while True:
        page = supabase.table("checkins") \
            .select("user_id, group_id") \
            .order("timestamp", desc=True) \
            .range(offset, offset + _PAGE_SIZE - 1) \
            .execute()
        if not page.data:
            break
        for item in page.data:
            uid = item["user_id"]
            if uid not in mapping and item["group_id"] not in config.EXCLUDED_GROUP_IDS:
                mapping[uid] = item["group_id"]
        if worker_ids and worker_ids.issubset(mapping.keys()):
            break  # every known worker mapped — no need to scan older history
        if len(page.data) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return mapping

def get_workers_last_groups() -> Dict[int, str]:
    """Get a mapping of user_id -> last group name they checked into."""
    groups_by_id = {g["group_id"]: (g.get("group_name") or "Unknown Group")
                    for g in get_all_groups()}
    return {uid: groups_by_id.get(gid, "Unknown Group")
            for uid, gid in _last_group_id_map().items()}

def get_workers_last_group_ids() -> Dict[int, int]:
    """Get a mapping of user_id -> last group_id they checked into.

    Used by /sync to know which group to verify each worker's membership in.
    """
    return _last_group_id_map()

def get_excluded_worker_ids() -> set:
    """user_ids of accounts excluded via EXCLUDED_USERNAMES (raw workers scan)."""
    try:
        res = supabase.table("workers").select("user_id, username").execute()
        return {w["user_id"] for w in (res.data or [])
                if _is_excluded_username(w.get("username"))}
    except Exception as e:
        print(f"⚠️ get_excluded_worker_ids failed: {e}")
        return set()

# ── Group membership ─────────────────────────────────────────────────────

def set_member_active(group_id: int, user_id: int) -> None:
    """Mark a (group, user) as an active member (idempotent upsert)."""
    try:
        supabase.table("group_members").upsert({
            "group_id": group_id,
            "user_id": user_id,
            "is_active": True,
            "left_at": None,
        }, on_conflict="group_id,user_id").execute()
    except Exception as e:
        print(f"⚠️ set_member_active failed: {e}")

def set_member_left(group_id: int, user_id: int) -> None:
    """Mark a (group, user) as having left/been removed from the group."""
    try:
        supabase.table("group_members").upsert({
            "group_id": group_id,
            "user_id": user_id,
            "is_active": False,
            "left_at": _now().isoformat(),
        }, on_conflict="group_id,user_id").execute()
    except Exception as e:
        print(f"⚠️ set_member_left failed: {e}")

def set_members_bulk(active: list, left: list) -> None:
    """Upsert many memberships in one request. ``active``/``left`` are lists of
    (group_id, user_id) tuples. Much faster than one call per worker."""
    now = _now().isoformat()
    rows = [{"group_id": g, "user_id": u, "is_active": True, "left_at": None} for g, u in active]
    rows += [{"group_id": g, "user_id": u, "is_active": False, "left_at": now} for g, u in left]
    if not rows:
        return
    try:
        supabase.table("group_members").upsert(rows, on_conflict="group_id,user_id").execute()
    except Exception as e:
        print(f"⚠️ set_members_bulk failed: {e}")

def get_inactive_worker_ids() -> set:
    """User IDs known to have left every group they belonged to.

    A user counts as inactive ONLY if they have membership rows AND none of
    them is active. Users with no membership rows are treated as active
    (fail-open) so reports never hide people we haven't explicitly removed.
    Returns an empty set if the membership table is missing/unreachable.
    """
    try:
        query = supabase.table("group_members").select("user_id, is_active")
        rows = _fetch_all(query)
    except Exception as e:
        print(f"⚠️ get_inactive_worker_ids failed (treating all as active): {e}")
        return set()

    any_active: Dict[int, bool] = {}
    for r in rows:
        uid = r["user_id"]
        any_active[uid] = any_active.get(uid, False) or bool(r["is_active"])
    return {uid for uid, active in any_active.items() if not active}

def get_active_workers() -> List[Dict]:
    """All workers except those explicitly known to have left their group(s)."""
    workers = get_all_workers()
    inactive = get_inactive_worker_ids()
    if not inactive:
        return workers
    return [w for w in workers if w["user_id"] not in inactive]

# ── Admin management ─────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    try:
        res = supabase.table("admins").select("user_id").eq("user_id", user_id).maybe_single().execute()
        return res is not None and res.data is not None
    except Exception as e:
        print(f"⚠️ is_admin({user_id}) failed: {e}")
        return False

def add_admin(user_id: int) -> None:
    supabase.table("admins").upsert({"user_id": user_id}).execute()

def get_all_admin_ids() -> List[int]:
    """Get all admin IDs from both .env and DB."""
    ids = set(config.ADMIN_IDS)
    res = supabase.table("admins").select("user_id").execute()
    for row in res.data:
        ids.add(row["user_id"])
    return list(ids)
