"""Source credit for CSV downloads: a footer row and a dated filename.

Every CSV ends with a blank row, then
    Source: Strategy Studio, https://strategystudio.org/<page path>, retrieved YYYY-MM-DD
and downloads as strategystudio-<name>-YYYY-MM-DD.csv. The header row stays first.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

from app.cite import page_url


def source_line(path: str, today: dt.date | None = None) -> str:
    """The credit text for the HTML page a CSV belongs to (canonical path, no query string)."""
    return f"Source: Strategy Studio, {page_url(path)}, retrieved {(today or dt.date.today()).isoformat()}"


def footer(path: str, today: dt.date | None = None) -> str:
    """CSV text to append after the last data row: a blank row, then the source row."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([])
    w.writerow([source_line(path, today)])
    return buf.getvalue()


def filename(name: str, today: dt.date | None = None) -> str:
    """strategystudio-<name>-YYYY-MM-DD.csv, with <name> reduced to safe filename characters."""
    name = re.sub(r"[^A-Za-z0-9]+", "-", name or "data").strip("-").lower() or "data"
    return f"strategystudio-{name}-{(today or dt.date.today()).isoformat()}.csv"


def disposition(name: str, today: dt.date | None = None) -> dict:
    """Content-Disposition header for a CSV download."""
    return {"Content-Disposition": f'attachment; filename="{filename(name, today)}"'}
