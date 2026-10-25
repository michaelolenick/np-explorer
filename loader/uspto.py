"""USPTO bulk data, shared by loader/patents.py and loader/trademarks.py: the Open Data Portal (ODP) product
listings and file downloads, the API request tally, file readers, date parsers, the run log and the weekly refresh.

- The API key is USPTO_API_KEY (.env), sent as the X-API-KEY header and never logged. The key's quota is 1.2M API
  requests and 5M metadata retrievals in all (owner, 2026-10-24), so FURP only uses bulk files: one request lists a
  product's files, one request downloads a file. Every call is counted in uspto_api_usage (kind 'request', plus
  'metadata' for the file records a listing returns). Never loop per-patent or per-trademark API calls.
- Files go to ~/data/uspto/<PRODUCT>/ (a link to /bulk/uspto on the dev box), downloaded with curl -L, resumable.
- How far back: newest first, at most 20 years (CUTOFF): patents filed in the last 20 years (a utility patent
  expires 20 years after filing), the same window for assignments and security interests, and trademarks filed
  in the last 20 years plus older marks still registered (owner, 2026-10-24).
- The products are yearly (assignments, trademark case files) and quarterly (PatentsView), so the weekly refresh
  asks each listing once (4 requests a week) and reloads only when a product has a newer release.

- Checkpoints (uspto_state): each dataset's part and step, rows, newest and oldest dates reached, and what's next.
  Every step is an upsert, and finished steps are recorded (uspto_runs, part "PART/STEP"), so a restart skips
  what's done and redoes at most the step it stopped in, with nothing duplicated.
- Limits: a 429 or "rate limit exceeded" backs off (1, 2, 4, 8, 16 minutes) and retries; a quota error, or 429s
  that outlast the backoff, stop the load cleanly (QuotaStop), save the checkpoint and add a resume entry to the
  dev box's crontab 7 days out (marked RESUME_TAG). The resume checks the API first: still blocked, it reschedules
  a day later and tries daily; otherwise it continues from the checkpoint and removes its cron entry when done.
- Status: one line in ~/uspto_status.log (STATUS_LOG; and uspto_status) after each step and every 10 minutes while
  loading: patents and trademarks loaded with the dates reached, quota used, what's next. Events lead their line:
  LIMIT HIT, RESUME SCHEDULED, RESUMED, FINISHED, ERROR. No email (owner, 2026-10-24).

Usage: .venv/bin/python -m loader.uspto all | resume | refresh | status | usage | indexes
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from loader import db

API = "https://api.uspto.gov/api/v1/datasets/products"
DATA = Path(os.environ.get("USPTO_DATA", Path.home() / "data" / "uspto"))
QUOTA = {"request": 1_200_000, "metadata": 5_000_000}
YEARS_BACK = 20
CUTOFF = dt.date.today().replace(year=dt.date.today().year - YEARS_BACK)
PRODUCT_NAMES = {"PVGPATDIS": "PatentsView granted patents, disambiguated",
                 "ECORSEXC": "USPTO Patent Assignment Dataset",
                 "TRCFECO2": "USPTO Trademark Case Files Dataset",
                 "TRASECO": "USPTO Trademark Assignment Dataset"}
STATES = {"ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO",
          "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA",
          "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
          "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA",
          "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
          "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
          "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
          "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
          "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
          "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY", "PUERTO RICO": "PR"}
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
csv.field_size_limit(1 << 30)


RESUME_TAG = "# furp-uspto-resume"
STATUS_LOG = Path.home() / "uspto_status.log"
STATUS_EVERY = 600                     # seconds between status lines while loading


class QuotaStop(Exception):
    """The API quota is used up, or rate limiting outlasted the backoff: stop, save state, resume later."""


def log(msg: str) -> None:
    print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} {msg}", flush=True)


# --- dates and names ---------------------------------------------------------------------------------------------

def date_any(v: str | None) -> dt.date | None:
    """2018-06-19 (PatentsView), 22apr1991 (patent assignments), 19550103 (trademarks). Impossible years (PatentsView
    has a few, e.g. 1074 for 1974) give None."""
    v = (v or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d\d-\d\d", v[:10]):
            d = dt.date.fromisoformat(v[:10])
        elif re.fullmatch(r"\d{8}", v):
            d = dt.date(int(v[:4]), int(v[4:6]), int(v[6:]))
        elif re.fullmatch(r"\d{1,2}[a-z]{3}\d{4}", v.lower()):
            m = re.fullmatch(r"(\d{1,2})([a-z]{3})(\d{4})", v.lower())
            d = dt.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        else:
            return None
    except (ValueError, KeyError):
        return None
    return d if 1790 <= d.year <= 2100 else None


def state_code(v: str | None) -> str | None:
    v = (v or "").strip().upper()
    if re.fullmatch(r"[A-Z]{2}", v):
        return v
    return STATES.get(v)


def clean(v: str | None, n: int = 500) -> str | None:
    v = (v or "").strip()
    return v[:n] if v and v.upper() not in ("NULL", "NAN") else None


# --- files -------------------------------------------------------------------------------------------------------

def rows(path: Path, delimiter: str = ",", member: str | None = None):
    """Each row of a zipped CSV or TSV as a dict, streamed with unzip -p (nothing extracted to disk)."""
    p = subprocess.Popen(["unzip", "-p", str(path)] + ([member] if member else []), stdout=subprocess.PIPE)
    try:
        r = csv.DictReader(io.TextIOWrapper(p.stdout, encoding="utf-8", errors="replace", newline=""),
                           delimiter=delimiter)
        yield from r
    finally:
        p.stdout.close()
        p.wait()


def file_date(product: str, name: str) -> dt.date | None:
    """The release date of a downloaded file, from the saved product listing (provenance on every row)."""
    try:
        d = json.loads((DATA / f"product_{product}.json").read_text())
        dates = [f["fileReleaseDate"] for f in d["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"]
                 if f["fileName"] == name]
        return dt.date.fromisoformat(max(dates)[:10]) if dates else None
    except Exception:  # noqa: BLE001
        return None


# --- the API, counted --------------------------------------------------------------------------------------------

def count(kind: str, product: str | None, url: str | None, n: int = 1) -> None:
    try:
        with db.connect() as conn:
            conn.execute("INSERT INTO uspto_api_usage (kind, product, url, n) VALUES (%s, %s, %s, %s)",
                         (kind, product, url, n))
            conn.commit()
    except Exception:  # noqa: BLE001 - the tally also goes to the log file
        pass
    with open(DATA / "api_calls.log", "a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {kind} {n} {url}\n")


def listing(product: str) -> dict:
    """The product's file listing (one API request), saved as product_<ID>.json; 429s back off and retry."""
    url = f"{API}/{product}"
    for attempt in range(6):
        count("request", product, url)
        try:
            req = urllib.request.Request(url, headers={"X-API-KEY": os.environ["USPTO_API_KEY"],
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            files = d["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"]
            count("metadata", product, url, len(files))
            DATA.mkdir(parents=True, exist_ok=True)
            (DATA / f"product_{product}.json").write_text(json.dumps(d, indent=1))
            return d
        except urllib.error.HTTPError as e:
            body = e.read()[:2000].decode("utf-8", "replace").lower()
            if "quota" in body:
                raise QuotaStop(f"listing {product}: quota ({e.code})") from None
            if e.code != 429 and "rate limit" not in body and e.code < 500:
                raise
            time.sleep(60 * 2 ** attempt)               # 1, 2, 4, 8, 16, 32 minutes
    raise QuotaStop(f"listing {product}: still rate-limited after backoff")


def newest(product: str, name: str) -> dict | None:
    d = json.loads((DATA / f"product_{product}.json").read_text())
    fs = [f for f in d["bulkDataProductBag"][0]["productFileBag"]["fileDataBag"] if f["fileName"] == name]
    return max(fs, key=lambda f: f["fileReleaseDate"]) if fs else None


def download(product: str, name: str, force: bool = False) -> Path:
    """One file of a product (one API request per attempt), resumable; checked with unzip -t."""
    f = newest(product, name)
    if not f:
        raise RuntimeError(f"{product} has no file {name}")
    out = DATA / product / name
    out.parent.mkdir(parents=True, exist_ok=True)
    done = out.with_name(name + ".done")
    if done.exists() and not force and done.read_text().strip() == f["fileReleaseDate"]:
        return out
    if force or (done.exists() and done.read_text().strip() != f["fileReleaseDate"]):
        out.unlink(missing_ok=True)
        done.unlink(missing_ok=True)
    last429 = False
    for attempt in range(6):
        count("request", product, f["fileDownloadURI"])
        cfg = f'header = "X-API-KEY: {os.environ["USPTO_API_KEY"]}"\n'
        res = subprocess.run(["curl", "-sS", "-L", "-C", "-", "--fail", "--retry", "3", "-K", "-", "-o", str(out),
                              "-w", "%{http_code}", f["fileDownloadURI"]], input=cfg.encode(), capture_output=True)
        code = res.stdout.decode()[-3:]
        if res.returncode == 0 and subprocess.run(["unzip", "-tq", str(out)], capture_output=True).returncode == 0:
            done.write_text(f["fileReleaseDate"])
            return out
        head = out.read_bytes()[:4000].lower() if out.exists() else b""
        if b"html" in head[:100] or b"quota" in head or b"rate limit" in head:
            out.unlink()                    # an error page, not the file
        if b"quota" in head:
            raise QuotaStop(f"download {product}/{name}: quota")
        last429 = code == "429" or b"rate limit" in head
        time.sleep(60 * 2 ** attempt)
    if last429:
        raise QuotaStop(f"download {product}/{name}: still rate-limited after backoff")
    raise RuntimeError(f"download failed: {product}/{name}")


def usage() -> dict:
    with db.connect() as conn:
        got = dict(conn.execute("SELECT kind, sum(n) FROM uspto_api_usage GROUP BY 1").fetchall())
    out = {k: int(got.get(k) or 0) for k in QUOTA}
    log("USPTO API usage: " + ", ".join(f"{k} {out[k]:,} of {QUOTA[k]:,}" for k in QUOTA))
    return out


def import_log() -> int:
    """Calls made before the table existed (the first downloads), from api_calls.log, counted once."""
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM uspto_api_usage WHERE kind = 'request' AND url = 'imported from api_calls.log'"
                        ).fetchone():
            return 0
        n = sum(1 for line in (DATA / "api_calls.log").read_text().splitlines()
                if "api.uspto.gov" in line and not re.search(r"\s(request|metadata) \d+ ", line))
        conn.execute("INSERT INTO uspto_api_usage (kind, url, n) VALUES ('request', 'imported from api_calls.log', %s)",
                     (n,))
        conn.commit()
    return n


# --- runs and loading --------------------------------------------------------------------------------------------

def record_run(conn, product: str, file: str, rows_: int, part: str = "") -> None:
    conn.execute("""INSERT INTO uspto_runs (product, file, file_date, part, rows) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (product, file, part) DO UPDATE SET file_date = excluded.file_date,
                    rows = excluded.rows, loaded = now()""", (product, file, file_date(product, file), part, rows_))
    conn.commit()


def last_run(product: str, file: str, part: str = "") -> dt.date | None:
    with db.connect() as conn:
        r = conn.execute("SELECT file_date FROM uspto_runs WHERE product = %s AND file = %s AND part = %s",
                         (product, file, part)).fetchone()
    return r[0] if r else None


def bulk(conn, table: str, cols: list[str], batch: list[tuple], conflict: str = "DO NOTHING") -> None:
    """COPY a batch into an unlogged staging table, then insert it into the real one (ON CONFLICT ...)."""
    if not batch:
        return
    stage = f"stage_{table}"
    conn.execute(f"CREATE UNLOGGED TABLE IF NOT EXISTS {stage} (LIKE {table} INCLUDING DEFAULTS)")
    conn.execute(f"TRUNCATE {stage}")
    with conn.cursor() as cur, cur.copy(f"COPY {stage} ({', '.join(cols)}) FROM STDIN") as cp:
        for r in batch:
            cp.write_row(r)
    # An upsert can't touch a row twice in one statement: one staged row per key (the last one read).
    distinct = f"DISTINCT ON ({conflict[1:conflict.index(')')]}) " if conflict.startswith("(") else ""
    conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) SELECT {distinct}{', '.join(cols)} FROM {stage} "
                 f"ON CONFLICT {conflict}")
    conn.commit()
    batch.clear()


def upsert(table: str, key: list[str], cols: list[str]) -> str:
    return f"({', '.join(key)}) DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in cols if c not in key)


def drop_stages(conn) -> None:
    for (t,) in conn.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'stage\\_pat\\_%' "
                             "OR tablename LIKE 'stage\\_tm\\_%'").fetchall():
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()


INDEXES = [
    "pat_patents (granted)", "pat_patents (filed)",
    "pat_assignees (assignee_id)", "pat_inventors (inventor_id)", "pat_inventors (name_norm)",
    "pat_assignment_docs (patent_id)", "pat_assignment_parties (name_core)",
    "pat_assignments (record_date) WHERE is_security",
    "pat_assignee_orgs (name_core text_pattern_ops)", "pat_assignee_orgs (n_patents)",
    "pat_inventor_people (name_norm text_pattern_ops)",
    "tm_marks (registration_no)", "tm_marks (mark_norm text_pattern_ops)", "tm_marks (filing_date)",
    "tm_owners (owner_key)", "tm_owners (name_core)",
    "tm_owner_orgs (name_core text_pattern_ops)", "tm_assignment_docs (serial_no)",
]


def indexes(status=log, only: str | None = None) -> None:
    """Secondary indexes, built after a bulk load (each one CONCURRENTLY, so pages keep reading)."""
    with db.connect(autocommit=True) as conn:
        conn.execute("SET maintenance_work_mem = '256MB'")
        for spec in INDEXES:
            table = spec.split()[0]
            if only and not table.startswith(only):
                continue
            name = re.sub(r"[^a-z0-9]+", "_", spec.lower()).strip("_")[:60]
            conn.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {spec}")
        for t in ("pat_patents", "pat_assignees", "pat_inventors", "pat_cpc", "pat_assignments",
                  "pat_assignment_parties", "pat_assignment_docs", "pat_assignee_orgs", "pat_inventor_people",
                  "tm_marks", "tm_owners", "tm_owner_orgs", "tm_assignments", "tm_assignment_parties",
                  "tm_assignment_docs", "ip_links"):
            if not only or t.startswith(only):
                conn.execute(f"ANALYZE {t}")
    status("uspto: indexes built")


# --- checkpoints, status and resuming ----------------------------------------------------------------------------

def step_done(product: str, file: str, part: str, step: str) -> bool:
    """True when this step of this part already finished with the current release of the file."""
    with db.connect() as conn:
        r = conn.execute("SELECT file_date FROM uspto_runs WHERE product = %s AND file = %s AND part = %s",
                         (product, file, f"{part}/{step}")).fetchone()
    return bool(r) and r[0] == file_date(product, file)


def mark_step(conn, product: str, file: str, part: str, step: str, rows_: int) -> None:
    record_run(conn, product, file, rows_, part=f"{part}/{step}")


def checkpoint(dataset: str, part: str | None = None, step: str | None = None, rows_: int | None = None,
               newest: dt.date | None = None, oldest: dt.date | None = None, status: str = "running",
               next_action: str | None = None, next_at: dt.datetime | None = None) -> None:
    with db.connect() as conn:
        conn.execute("""INSERT INTO uspto_state (dataset, part, step, rows, newest, oldest, status, next_action, next_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (dataset) DO UPDATE SET part = coalesce(excluded.part, uspto_state.part),
                          step = coalesce(excluded.step, uspto_state.step), rows = coalesce(excluded.rows, uspto_state.rows),
                          newest = coalesce(excluded.newest, uspto_state.newest),
                          oldest = coalesce(excluded.oldest, uspto_state.oldest), status = excluded.status,
                          next_action = excluded.next_action, next_at = excluded.next_at, updated = now()""",
                     (dataset, part, step, rows_, newest, oldest, status, next_action, next_at))
        conn.commit()


def _short(n: int, cap: int) -> str:
    return f"{n:,}/{cap / 1e6:g}M"


def status_line(next_what: str = "", event: str | None = None) -> str:
    """One line in STATUS_LOG (owner, 2026-10-24: a log file only, no email): ISO time, patents and trademarks
    loaded with the dates reached, quota used, what's next. Events (LIMIT HIT, RESUME SCHEDULED, RESUMED, FINISHED,
    ERROR) lead the line. Also kept in uspto_status."""
    with db.connect() as conn:
        if not next_what:                   # what the checkpoint says comes next, and when
            st = conn.execute("SELECT status, next_action, next_at FROM uspto_state WHERE dataset = 'load'").fetchone()
            if st and st[2]:
                next_what = f"{st[1]} at {st[2].astimezone():%Y-%m-%d %H:%M}"
            elif st and st[1]:
                next_what = st[1]
            else:
                next_what = _ticking["next"] or "weekly refresh, Sunday night (scripts/nightly.sh)"
        pn, pmax, pmin = conn.execute("SELECT count(*), max(granted), min(granted) FROM pat_patents").fetchone()
        tn, tmax, tmin = conn.execute("SELECT count(*), max(filing_date), min(filing_date) FROM tm_marks").fetchone()
        got = dict(conn.execute("SELECT kind, sum(n) FROM uspto_api_usage GROUP BY 1").fetchall())
        line = (f"{dt.datetime.now():%Y-%m-%dT%H:%M} " + (f"{event} | " if event else "")
                + f"patents {pn:,}" + (f" ({pmax}..{pmin})" if pmax else "")
                + f" | trademarks {tn:,}" + (f" ({tmax}..{tmin})" if tmax else "")
                + f" | quota api {_short(int(got.get('request') or 0), QUOTA['request'])}"
                + f" meta {_short(int(got.get('metadata') or 0), QUOTA['metadata'])}"
                + f" | next: {next_what}")
        conn.execute("INSERT INTO uspto_status (line) VALUES (%s)", (line,))
        conn.commit()
    with open(STATUS_LOG, "a") as f:
        f.write(line + "\n")
    log(line)
    return line


_ticking = {"next": "", "on": False}


def start_ticker(next_what: str = "loading") -> None:
    """A status line every 10 minutes while this process loads (a daemon thread; it ends with the process)."""
    import threading
    _ticking["next"] = next_what
    if _ticking["on"]:
        return
    _ticking["on"] = True

    def tick():
        while True:
            time.sleep(STATUS_EVERY)
            try:
                status_line(_ticking["next"])
            except Exception:  # noqa: BLE001 - a missed line isn't worth stopping the load
                pass
    threading.Thread(target=tick, daemon=True).start()


def next_up(what: str) -> None:
    _ticking["next"] = what


def current() -> str:
    return _ticking["next"] or "the load"


def _crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def schedule_resume(days: int, reason: str) -> dt.datetime:
    """A one-time resume in the user's crontab (the dev box clock is America/Chicago, like the other jobs),
    replacing any earlier one; the resume removes it when the load finishes."""
    when = (dt.datetime.now() + dt.timedelta(days=days)).replace(minute=15, second=0, microsecond=0)
    when = when.replace(hour=2) if days >= 1 else when      # 02:15 local, inside the off-hours window
    root = Path(__file__).resolve().parent.parent
    line = (f"{when.minute} {when.hour} {when.day} {when.month} * cd {root} && set -a && . ./.env && set +a && "
            f"nice -n 10 .venv/bin/python -m loader.uspto resume >> {Path.home()}/uspto-resume.log 2>&1 {RESUME_TAG}")
    lines = [x for x in _crontab() if RESUME_TAG not in x] + [line]
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    checkpoint("load", status="waiting", next_action=f"resume ({reason})", next_at=when.astimezone(dt.timezone.utc))
    status_line(f"resume from the checkpoint ({reason})", event=f"RESUME SCHEDULED for {when:%Y-%m-%d %H:%M}")
    return when


def unschedule_resume() -> None:
    lines = _crontab()
    if any(RESUME_TAG in x for x in lines):
        subprocess.run(["crontab", "-"], input="\n".join(x for x in lines if RESUME_TAG not in x) + "\n", text=True,
                       check=True)


def run_all(status=log) -> None:
    """The whole load, newest first, from the checkpoints: patents part by part (each step skipped when done),
    assignments, summaries, indexes and links; then trademarks the same way; then the boards. A QuotaStop saves
    state and schedules a resume 7 days out."""
    from loader import patents, trademarks
    try:
        checkpoint("load", status="running", next_action="loading")
        start_ticker("patent grants, newest first, ETA about 10 min per grant-year part")
        status_line("patent grants, newest first, ETA about 10 min per grant-year part")
        patents.load_patents(status=status)
        next_up("patent assignments, ETA about 15 min")
        patents.load_assignments(status=status)
        next_up("patent summaries, indexes, links and boards, ETA about 20 min")
        patents.summaries(status=status)
        indexes(status=status, only="pat")
        patents.links(status=status)
        boards(status=status)
        next_up("trademarks, newest first, ETA about 20 min per filing-year part")
        status_line("trademarks, newest first, ETA about 20 min per filing-year part")
        trademarks.load_marks(status=status)
        next_up("trademark assignments, ETA about 10 min")
        trademarks.load_assignments(status=status)
        next_up("trademark summaries, indexes, links and boards, ETA about 20 min")
        trademarks.summaries(status=status)
        indexes(status=status, only="tm")
        trademarks.links(status=status)
        boards(status=status)
        next_up("firms: full pass, ETA about 30 min")
        from loader import ip_firms
        ip_firms.derive("full", status=status)        # the final full pass over both backfills
        ip_firms.haiku_check(status=status)           # person or company, for names the rules can't settle
    except QuotaStop as e:
        status(f"uspto: stopped: {e}")
        checkpoint("load", status="stopped", next_action=str(e))
        status_line(f"stopped: {e}", event="LIMIT HIT")
        schedule_resume(7, str(e))
        return
    except Exception as e:
        checkpoint("load", status="error", next_action=f"{type(e).__name__}: {str(e)[:200]}")
        status_line(f"{type(e).__name__}: {str(e)[:200]}; rerun resumes from the checkpoint", event="ERROR")
        raise
    checkpoint("load", status="done", next_action="weekly refresh (scripts/nightly.sh, Sundays)")
    unschedule_resume()
    status_line("weekly refresh (scripts/nightly.sh, Sunday nights)", event="FINISHED")


def resume(status=log) -> None:
    """The cron resume: if the API still refuses, try again tomorrow; otherwise carry on from the checkpoint."""
    try:
        listing("PVGPATDIS")
    except QuotaStop as e:
        schedule_resume(1, f"still limited: {e}")
        return
    status_line("carrying on from the checkpoint", event="RESUMED")
    run_all(status=status)


# --- the weekly refresh ------------------------------------------------------------------------------------------

def refresh(status=log) -> None:
    """Weekly (scripts/nightly.sh, Sunday night): ask each product's listing once; reload a product only when it
    has a newer release than the one loaded, then rebuild links and the patent and trademark boards."""
    from loader import patents, trademarks
    changed = False
    for product, files, loader_fn in (("PVGPATDIS", patents.PV_FILES, patents.load_patents),
                                      ("ECORSEXC", patents.ASSIGN_FILES, patents.load_assignments),
                                      ("TRCFECO2", trademarks.CASE_FILES, trademarks.load_marks),
                                      ("TRASECO", trademarks.ASSIGN_FILES, trademarks.load_assignments)):
        try:
            listing(product)
            time.sleep(5)                                   # space out calls (the API rate-limits)
            if all(last_run(product, f) == file_date(product, f) for f in files):
                status(f"uspto {product}: no new release")
                continue
            for f in files:
                download(product, f)
            loader_fn(status=status)
            changed = True
        except QuotaStop as e:
            status_line(f"weekly refresh stopped: {e}", event="LIMIT HIT")
            schedule_resume(7, str(e))
            return
        except Exception as e:  # noqa: BLE001 - one product failing doesn't stop the rest
            status(f"uspto {product} failed: {type(e).__name__}: {str(e)[:200]}")
    if changed:
        start_ticker("weekly refresh: summaries, indexes, links, boards")
        patents.summaries(status=status)
        trademarks.summaries(status=status)
        indexes(status=status)
        patents.links(status=status)
        trademarks.links(status=status)
        boards(status=status)
        from loader import ip_firms
        ip_firms.derive("full", status=status)        # weekly full reconciliation of the derived firms
        ip_firms.haiku_check(status=status)           # only names not checked before
    status_line("weekly refresh done" + ("" if changed else ": no new USPTO releases"))


def boards(status=log) -> None:
    from app import boards as B
    from loader import boards as LB
    with db.connect() as conn:
        LB._prepare(conn)
        for b in B.BOARDS:
            if b.group == "patents":
                status(f"board {b.slug}: {LB.refresh_board(conn, b)} rows")
        LB.refresh_entries(conn)


if __name__ == "__main__":
    # Run through the imported module, so loader.patents and loader.trademarks share its status ticker.
    from loader import uspto as U
    {"refresh": U.refresh, "usage": U.usage, "indexes": U.indexes, "import_log": lambda: print(U.import_log()),
     "boards": U.boards, "all": U.run_all, "resume": U.resume, "status": lambda: print(U.status_line())
     }[(sys.argv[1:] or ["usage"])[0]]()
