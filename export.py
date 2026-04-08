"""Excel export — generates .xlsx attendance reports."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import config
import database_supabase as db
from analytics import get_worker_status


# ── Style constants ──────────────────────────────────────────────────────
_HEADER_FONT = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
_HEADER_FILL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_CELL_ALIGN = Alignment(vertical="center", wrap_text=False)
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

_ON_TIME_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
_LATE_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
_ABSENT_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

_LINK_FONT = Font(name="Calibri", color="0563C1", underline="single", size=10)


def _style_header(ws, col_count: int) -> None:
    """Apply styling to the first (header) row."""
    for col in range(1, col_count + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _THIN_BORDER


def _auto_width(ws) -> None:
    """Set column widths based on content."""
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                val = str(cell.value) if cell.value else ""
                max_len = max(max_len, len(val))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)


def _get_photo_url(file_id: str) -> str:
    """Generate a Telegram Bot API file URL.
    Note: actual download requires a getFile call, but we store
    the file_id so the admin can retrieve it via the bot."""
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/getFile?file_id={file_id}"


def _get_maps_url(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps?q={lat},{lon}"


def _status_fill(status: str) -> PatternFill:
    if "On Time" in status:
        return _ON_TIME_FILL
    elif "Late" in status:
        return _LATE_FILL
    else:
        return _ABSENT_FILL


def generate_export(checkins: list[dict], title: str = "attendance") -> str:
    """Create an .xlsx file and return its path.

    Parameters
    ----------
    checkins : list[dict]
        Rows from database.get_checkins_for_*
    title : str
        Used in the filename.

    Returns
    -------
    str  – absolute path to the generated file.
    """
    os.makedirs(config.EXPORTS_DIR, exist_ok=True)
    tz = ZoneInfo(config.TIMEZONE)

    wb = Workbook()

    # ── Sheet 1: Detailed Check-ins ──────────────────────────────────
    ws1 = wb.active
    ws1.title = "Check-ins"

    headers1 = [
        "#", "Date", "Time", "Group", "Username",
        "First Name", "Last Name", "Latitude", "Longitude",
        "Google Maps", "Media Type", "Media Link",
    ]
    ws1.append(headers1)
    _style_header(ws1, len(headers1))

    for idx, c in enumerate(checkins, start=1):
        ts = datetime.fromisoformat(c["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=tz)

        maps_url = ""
        if c.get("latitude") and c.get("longitude"):
            maps_url = _get_maps_url(c["latitude"], c["longitude"])

        media_url = ""
        if c.get("media_file_id"):
            media_url = _get_photo_url(c["media_file_id"])

        row_num = idx + 1  # 1-indexed, skip header
        ws1.append([
            idx,
            ts.strftime("%Y-%m-%d"),
            ts.strftime("%H:%M:%S"),
            c.get("group_name", ""),
            c.get("username", ""),
            c.get("first_name", ""),
            c.get("last_name", ""),
            c.get("latitude", ""),
            c.get("longitude", ""),
            maps_url,
            c.get("media_type", "photo"),
            media_url,
        ])

        # Make links clickable
        if maps_url:
            cell = ws1.cell(row=row_num, column=10)
            cell.hyperlink = maps_url
            cell.font = _LINK_FONT
            cell.value = "📍 Open Map"
        if media_url:
            cell = ws1.cell(row=row_num, column=12)
            cell.hyperlink = media_url
            cell.font = _LINK_FONT
            cell.value = f"🔗 View {c.get('media_type', 'media').capitalize()}"

        # Borders
        for col in range(1, len(headers1) + 1):
            ws1.cell(row=row_num, column=col).border = _THIN_BORDER
            ws1.cell(row=row_num, column=col).alignment = _CELL_ALIGN

    _auto_width(ws1)
    # Freeze header row
    ws1.freeze_panes = "A2"

    # ── Sheet 2: Daily Summary ───────────────────────────────────────
    ws2 = wb.create_sheet("Daily Summary")

    headers2 = [
        "Date", "Username", "Full Name", "Group",
        "Check-in Count", "First Check-in", "Last Check-in", "Status",
    ]
    ws2.append(headers2)
    _style_header(ws2, len(headers2))

    # Group checkins by date to compute summary
    dates = sorted(set(c["date"] for c in checkins)) if checkins else []
    row_idx = 2
    all_workers = db.get_all_workers()

    for d in dates:
        summary = db.get_daily_summary(d)
        present_ids = {r["user_id"] for r in summary}

        for r in summary:
            status = get_worker_status(r["first_checkin"])
            first_t = datetime.fromisoformat(r["first_checkin"])
            last_t = datetime.fromisoformat(r["last_checkin"])
            if first_t.tzinfo is None:
                first_t = first_t.replace(tzinfo=tz)
            if last_t.tzinfo is None:
                last_t = last_t.replace(tzinfo=tz)

            ws2.append([
                d,
                r.get("username", ""),
                f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(),
                r.get("group_name", ""),
                r["checkin_count"],
                first_t.strftime("%H:%M:%S"),
                last_t.strftime("%H:%M:%S"),
                status,
            ])
            # Color the status cell
            status_cell = ws2.cell(row=row_idx, column=8)
            status_cell.fill = _status_fill(status)
            for col in range(1, len(headers2) + 1):
                ws2.cell(row=row_idx, column=col).border = _THIN_BORDER
                ws2.cell(row=row_idx, column=col).alignment = _CELL_ALIGN
            row_idx += 1

        # Absent workers
        for w in all_workers:
            if w["user_id"] not in present_ids:
                ws2.append([
                    d,
                    w.get("username", ""),
                    f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
                    "—",
                    0,
                    "—",
                    "—",
                    "❌ Absent",
                ])
                status_cell = ws2.cell(row=row_idx, column=8)
                status_cell.fill = _ABSENT_FILL
                for col in range(1, len(headers2) + 1):
                    ws2.cell(row=row_idx, column=col).border = _THIN_BORDER
                    ws2.cell(row=row_idx, column=col).alignment = _CELL_ALIGN
                row_idx += 1

    _auto_width(ws2)
    ws2.freeze_panes = "A2"

    # ── Save ─────────────────────────────────────────────────────────
    now_str = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
    filename = f"{title}_{now_str}.xlsx"
    filepath = os.path.join(config.EXPORTS_DIR, filename)
    wb.save(filepath)
    return filepath
