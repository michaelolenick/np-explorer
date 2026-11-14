"""Companies House REST API: officers and company profiles into schema `uk_companies` (owner, 2026-11-14).

The free REST API key (COMPANIES_HOUSE_API_KEY, in .env on dev and prod, never in code, logs or URLs) is used with HTTP Basic auth, the key as
user name and an empty password. Terms (developer.company-information.service.gov.uk, checked 2026-11-14): 600 requests per rolling five
minutes per application, further requests get HTTP 429 until the window resets; applications that regularly exceed the limit may be banned.
We keep to 575 per rolling 5 minutes with one shared sliding-window limiter and fire the next request the moment a slot opens, around the clock.
Dev and prod share ONE key and one limit, so exactly one fetcher may run anywhere: a Postgres advisory lock (shared database) makes a second
copy exit at once, and `ensure` only starts it on the box that has the marker file ~/claude_scripts/companies_house/RUN_HERE (dev).
Streaming API (stream.companieshouse.gov.uk) needs a separate STREAM key: not used.

Data kept: officers' name, role, appointed/resigned dates, nationality, country of residence, occupation, birth month and year (never the
day of birth), correspondence address only as country (and the UK postcode area). No residential address is stored.
Licence: Open Government Licence v3.0, "Contains public sector information licensed under the Open Government Licence v3.0. Source: Companies House."

python -m loader.uk_officers enqueue      build/extend the priority queue (idempotent)
python -m loader.uk_officers run          the fetcher (one copy; exits at once when another holds the lock)
python -m loader.uk_officers ensure       start `run` detached if it is not running (cron every 3 minutes and nightly.sh; dev only)
python -m loader.uk_officers status       queue, rate and wall-hit numbers
python -m loader.uk_officers summarize    officer_stats (appointment counts per officer) for the boards

Queue priorities: 1 company number on the UK charity register; 2 linked to US entities, SEC or Form D filers; 3 a PSC matched a FURP person;
4 PSC network of 5+ companies; 5 SIC codes of holding, funds, charities, education, health, social care, membership bodies; 6 everything
else, newest incorporations first. Priorities 1-5 get the profile and the officers (2+ requests), priority 6 the officers only.
"""

from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import hashlib
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from loader import db

API = "https://api.company-information.service.gov.uk"
UA = "furp.org data loader (info@furp.org)"
WINDOW = 300.0
LIMIT = int(os.environ.get("CH_REQUESTS_PER_WINDOW", "575"))
WORKERS = 3
LOCK_ID = 778102
HOME = Path(os.environ.get("CH_DIR", str(Path.home() / "claude_scripts" / "companies_house")))
STATUS_LOG = HOME / "status.log"
WALL_LOG = HOME / "walls.log"
RUN_LOG = HOME / "fetcher.log"
MARKER = HOME / "RUN_HERE"
AUTHFAIL = HOME / "AUTH_FAIL"
FULL_PRIORITY = 5          # priorities up to this one also get the profile
PAGE = 100
MAX_PAGES = 20
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Source: Companies House.")

SIC_PATTERN = r"^(642|643|6499|6630|85|86|87|88|9411|9412|9491|9492|9499)"

DDL = """
CREATE SCHEMA IF NOT EXISTS uk_companies;
CREATE TABLE IF NOT EXISTS uk_companies.fetch_queue (
    company_number text PRIMARY KEY, priority smallint NOT NULL, ord integer NOT NULL, state text NOT NULL DEFAULT 'pending',
    attempts smallint NOT NULL DEFAULT 0, retry_after timestamptz, claimed timestamptz, fetched timestamptz, http smallint,
    profile_done boolean NOT NULL DEFAULT false);
CREATE INDEX IF NOT EXISTS fetch_queue_pending ON uk_companies.fetch_queue (priority, ord, company_number) WHERE state = 'pending';
CREATE INDEX IF NOT EXISTS fetch_queue_state ON uk_companies.fetch_queue (state, priority);
CREATE TABLE IF NOT EXISTS uk_companies.officer (
    company_number text NOT NULL, appt_key text NOT NULL, officer_id text, name text, name_norm text, role text, corporate boolean,
    appointed_on date, resigned_on date, nationality text, residence text, occupation text, birth_year smallint, birth_month smallint,
    addr_country text, addr_area text, PRIMARY KEY (company_number, appt_key));
CREATE INDEX IF NOT EXISTS officer_id_idx ON uk_companies.officer (officer_id) WHERE officer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS officer_name_idx ON uk_companies.officer (name_norm text_pattern_ops);
CREATE TABLE IF NOT EXISTS uk_companies.profile (
    company_number text PRIMARY KEY, fetched timestamptz NOT NULL DEFAULT now(), type text, jurisdiction text, status_detail text,
    has_charges boolean, has_insolvency_history boolean, can_file boolean, accounts_last date, accounts_next_due date,
    accounts_overdue boolean, conf_last date, conf_next_due date, conf_overdue boolean, sic text[], previous_names jsonb,
    office_in_dispute boolean, undeliverable boolean, officers_active integer, officers_resigned integer, officers_total integer);
CREATE TABLE IF NOT EXISTS uk_companies.fetch_daily (
    day date PRIMARY KEY, requests integer NOT NULL DEFAULT 0, companies integer NOT NULL DEFAULT 0, officer_rows integer NOT NULL DEFAULT 0,
    r429 integer NOT NULL DEFAULT 0, wall_hits integer NOT NULL DEFAULT 0, window_waits integer NOT NULL DEFAULT 0,
    errors integer NOT NULL DEFAULT 0, wait_seconds real NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS uk_companies.fetch_bucket (bucket timestamptz PRIMARY KEY, n integer NOT NULL);
CREATE TABLE IF NOT EXISTS uk_companies.officer_stats (
    officer_id text PRIMARY KEY, name text, name_norm text, appointments integer, current_appointments integer, companies integer,
    first_appointed date, birth_year smallint, nationality text, example_company text);
"""


def _log(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} uk officers: {msg}"
    print(line, flush=True)


def _key() -> str:
    k = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
    if not k:
        envf = Path.home() / "np-explorer" / ".env"
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.startswith("COMPANIES_HOUSE_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip("'\"")
    return k


def scrub(s: object) -> str:
    s = str(s)
    k = _key()
    if k:
        s = s.replace(k, "***").replace(base64.b64encode((k + ":").encode()).decode(), "***")
    return s


def status_line(msg: str) -> None:
    with STATUS_LOG.open("a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} UK Companies House fetcher: {msg}\n")


def wall_line(msg: str) -> None:
    with WALL_LOG.open("a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}\n")


# --- the shared sliding-window limiter -----------------------------------------------------------

class Limiter:
    """At most LIMIT requests in any rolling WINDOW seconds, shared by all threads. acquire() returns the moment a slot opens."""

    def __init__(self, limit: int = LIMIT, window: float = WINDOW):
        self.limit, self.window = limit, window
        self.times: collections.deque[float] = collections.deque()
        self.lock = threading.Lock()
        self.block_until = 0.0
        self.waits = 0
        self.wait_s = 0.0
        self.requests = 0
        self.buckets: dict[int, int] = collections.defaultdict(int)   # unix 10-second bucket -> requests, flushed to fetch_bucket

    def seed(self, stamps: list[float]) -> None:
        with self.lock:
            self.times.extend(sorted(stamps))

    def block(self, seconds: float) -> None:
        with self.lock:
            self.block_until = max(self.block_until, time.time() + seconds)

    def acquire(self) -> None:
        waited = 0.0
        while True:
            with self.lock:
                now = time.time()
                while self.times and self.times[0] <= now - self.window:
                    self.times.popleft()
                wait = max(self.block_until - now, 0.0)
                if not wait and len(self.times) >= self.limit:
                    wait = self.times[0] + self.window - now + 0.02
                if not wait:
                    self.times.append(now)
                    self.requests += 1
                    self.buckets[int(now // 10) * 10] += 1
                    if waited > 1:
                        self.waits += 1
                    self.wait_s += waited
                    return
            time.sleep(min(wait, 5.0))
            waited += min(wait, 5.0)


LIM = Limiter()
STATS = collections.Counter()
STOP = threading.Event()


class Fatal(Exception):
    pass


def api_get(path: str, params: dict | None = None):
    """GET one API path; returns (http_status, json or None). Handles 429 (Retry-After), 5xx and network errors with backoff."""
    url = API + path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
    auth = "Basic " + base64.b64encode((_key() + ":").encode()).decode()
    tries = 0
    backoff = 5.0
    while not STOP.is_set():
        LIM.acquire()
        req = urllib.request.Request(url, headers={"Authorization": auth, "User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            code = e.code
            if code == 404:
                return 404, None
            if code == 429:
                ra = e.headers.get("Retry-After")
                try:
                    secs = float(ra) if ra else backoff
                except ValueError:
                    secs = backoff
                if not ra:
                    backoff = min(backoff * 2, 120.0)
                LIM.block(secs)
                STATS["r429"] += 1
                STATS["wall_hits"] += 1
                wall_line(f"HTTP 429 (Retry-After {ra or 'absent'}); waiting {secs:.0f}s; requests in window {len(LIM.times)}")
                continue
            if code in (401, 403):
                AUTHFAIL.write_text(dt.datetime.now(dt.timezone.utc).isoformat())
                STOP.set()
                raise Fatal(f"API answered HTTP {code}: the key was rejected or lacks access")
            tries += 1
            if code >= 500 and tries <= 3:
                time.sleep(2 * tries * tries)
                continue
            raise RuntimeError(f"HTTP {code}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            tries += 1
            if tries <= 3:
                time.sleep(2 * tries * tries)
                continue
            raise RuntimeError("network: " + scrub(e)[:120]) from None
    raise Fatal("stopping")


# --- parsing -------------------------------------------------------------------------------------

_PC = re.compile(r"^\s*([A-Za-z]{1,2})\d[A-Za-z\d]?\s*\d[A-Za-z]{2}\s*$")


def _case(s: str) -> str:
    """The register writes surnames in capitals: HAMMERBACHER -> Hammerbacher, MCDONALD -> McDonald, O'BRIEN-SMITH -> O'Brien-Smith."""
    def one(w: str) -> str:
        if not (w.isupper() and len(w) > 1):
            return w
        out = re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), w)
        return "Mc" + out[2:3].upper() + out[3:] if w.startswith("MC") and len(w) > 3 else out
    return " ".join(one(w) for w in s.split(" "))


def person_name(raw: str | None, corporate: bool) -> tuple[str, str]:
    """'SMITH, John Michael' -> ('John Michael Smith', 'john michael smith'); corporate names are kept as they are."""
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    if not corporate and "," in raw:
        # "SURNAME, Forenames" or "SURNAME, Forenames, Title" (Dr, Sir, Lord, Rev'd Canon ...)
        parts = [x.strip() for x in raw.split(",")]
        raw_disp = " ".join(x for x in (" ".join(parts[2:]), _case(parts[1]), _case(parts[0])) if x)
    else:
        raw_disp = raw
    import unicodedata
    a = unicodedata.normalize("NFKD", raw_disp).encode("ascii", "ignore").decode().lower().replace("'", "")
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", a).split()
             if corporate or w not in ("mr", "mrs", "ms", "miss", "dr", "prof", "professor", "sir", "dame", "lord", "lady", "rev", "revd",
                                       "reverend", "cllr", "hon", "mbe", "obe", "cbe", "kc", "qc", "jp", "dl", "canon", "mx", "esq", "baroness", "viscount")]
    return raw_disp, " ".join(words)


def d(v):
    v = v if isinstance(v, str) else ""
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d)", v)
    if not m or m.group(1) in ("0000", "9999"):
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def officer_row(number: str, it: dict) -> tuple:
    role = it.get("officer_role") or ""
    corporate = role.startswith("corporate-") or bool(it.get("identification"))
    disp, norm = person_name(it.get("name"), corporate)
    oid = None
    m = re.search(r"/officers/([^/]+)/appointments", ((it.get("links") or {}).get("officer") or {}).get("appointments") or "")
    if m:
        oid = m.group(1)
    appointed = d(it.get("appointed_on"))
    resigned = d(it.get("resigned_on"))
    dob = it.get("date_of_birth") or {}
    addr = it.get("address") or {}
    pm = _PC.match(addr.get("postal_code") or "")
    ms = re.search(r"/appointments/([^/]+)$", (it.get("links") or {}).get("self") or "")
    key = ms.group(1) if ms else hashlib.md5(f"{oid or norm}|{role}|{appointed}".encode()).hexdigest()[:16]
    # the day of birth and the residential/correspondence street address are never kept
    return (number, key, oid, disp[:200], norm[:200], role, corporate, appointed, resigned, (it.get("nationality") or None),
            (it.get("country_of_residence") or None), (it.get("occupation") or None),
            dob.get("year") if isinstance(dob.get("year"), int) else None, dob.get("month") if isinstance(dob.get("month"), int) else None,
            (addr.get("country") or None), pm.group(1).upper() if pm else None)


OFFICER_COLS = ("company_number", "appt_key", "officer_id", "name", "name_norm", "role", "corporate", "appointed_on", "resigned_on", "nationality",
                "residence", "occupation", "birth_year", "birth_month", "addr_country", "addr_area")


def fetch_officers(number: str):
    rows, start, total, act, res = [], 0, None, None, None
    for _ in range(MAX_PAGES):
        code, js = api_get(f"/company/{number}/officers", {"items_per_page": PAGE, "start_index": start})
        if code == 404 or not js:
            return code, rows, (act, res, total)
        items = js.get("items") or []
        total = js.get("total_results", total)
        act, res = js.get("active_count", act), js.get("resigned_count", res)
        rows += [officer_row(number, it) for it in items]
        start += len(items)
        if not items or (total is not None and start >= total):
            break
    return 200, rows, (act, res, total)


def profile_row(number: str, js: dict, counts) -> tuple:
    acc = js.get("accounts") or {}
    cs = js.get("confirmation_statement") or {}
    prev = [{"name": p.get("name"), "ceased": d(p.get("ceased_on"))} for p in (js.get("previous_company_names") or [])]
    return (number, js.get("type"), js.get("jurisdiction"), js.get("company_status_detail"), js.get("has_charges"), js.get("has_insolvency_history"),
            js.get("can_file"), d((acc.get("last_accounts") or {}).get("made_up_to")), d(acc.get("next_due")), acc.get("overdue"),
            d(cs.get("last_made_up_to")), d(cs.get("next_due")), cs.get("overdue"), js.get("sic_codes") or None, json.dumps(prev) if prev else None,
            js.get("registered_office_is_in_dispute"), js.get("undeliverable_registered_office_address"), *counts)


PROFILE_COLS = ("company_number", "type", "jurisdiction", "status_detail", "has_charges", "has_insolvency_history", "can_file", "accounts_last",
                "accounts_next_due", "accounts_overdue", "conf_last", "conf_next_due", "conf_overdue", "sic", "previous_names", "office_in_dispute",
                "undeliverable", "officers_active", "officers_resigned", "officers_total")


# --- queue ---------------------------------------------------------------------------------------

TIERS = [
    (1, """SELECT DISTINCT company_number FROM uk_companies.xmatch WHERE method = 'charity_number'"""),
    (2, """SELECT DISTINCT company_number FROM uk_companies.xmatch WHERE dst_kind IN ('biz', 'sec', 'formd')
           UNION SELECT DISTINCT src_key FROM xlinks WHERE src_kind = 'uk_company' AND dst_kind NOT IN ('uk_charity', 'uk_company')"""),
    (3, """SELECT DISTINCT company_number FROM uk_companies.psc_match"""),
    (4, """SELECT DISTINCT p.company_number FROM uk_companies.psc_person pp
           JOIN uk_companies.psc p ON p.name_norm = pp.name_norm AND p.birth_year IS NOT DISTINCT FROM pp.birth_year
                AND p.birth_month IS NOT DISTINCT FROM pp.birth_month AND p.kind = 'individual'
           WHERE pp.companies >= 5
           UNION SELECT DISTINCT p.company_number FROM uk_companies.psc p
           JOIN (SELECT reg_number FROM uk_companies.psc WHERE kind LIKE 'corporate%%' AND reg_number IS NOT NULL
                 GROUP BY reg_number HAVING count(DISTINCT company_number) >= 5) g ON g.reg_number = p.reg_number
           WHERE p.kind LIKE 'corporate%%'"""),
    (5, """SELECT company_number FROM uk_companies.company c WHERE sic IS NOT NULL
           AND EXISTS (SELECT 1 FROM unnest(c.sic) s WHERE s ~ %(sic)s)"""),
    (6, """SELECT company_number FROM uk_companies.company"""),
]


def enqueue(conn=None) -> None:
    own = conn is None
    conn = conn or db.connect()
    conn.execute(DDL)
    conn.commit()
    conn.execute("SET statement_timeout = 0")
    for pri, sel in TIERS:
        t0 = time.time()
        if pri == 6:
            # chunked by company-number prefix so no write batch is large
            n = 0
            for pre in [f"{i:02d}" for i in range(0, 100)] + ["OC", "SC", "NI", "LP", "SL", "SO", "NC", "FC", "IP", "RC", "NF", "OE", "CE", "GE", "R0", "NP", "SP", "SE", "SA", "NO", "ZC", "AC", "NL", "IC", "SZ"]:
                n += conn.execute("""
                    INSERT INTO uk_companies.fetch_queue (company_number, priority, ord)
                    SELECT c.company_number, 6, coalesce((current_date - c.incorporated), 999999)
                    FROM uk_companies.company c WHERE c.company_number LIKE %(pre)s
                    ON CONFLICT DO NOTHING""", {"pre": pre + "%"}).rowcount
                conn.commit()
        else:
            n = conn.execute(f"""
                INSERT INTO uk_companies.fetch_queue (company_number, priority, ord)
                SELECT q.company_number, {pri}, coalesce((current_date - c.incorporated), 999999)
                FROM ({sel}) q JOIN uk_companies.company c USING (company_number)
                ON CONFLICT DO NOTHING""", {"sic": SIC_PATTERN}).rowcount
            conn.commit()
        _log(f"enqueue priority {pri}: {n:,} new in {time.time() - t0:.0f}s")
    # a monthly snapshot's new companies are picked up above; priority 1-3 companies are refetched every 45 days
    n = conn.execute("""UPDATE uk_companies.fetch_queue SET state = 'pending', attempts = 0
                        WHERE state = 'done' AND priority <= 3 AND fetched < now() - interval '45 days'""").rowcount
    conn.commit()
    if n:
        _log(f"re-queued {n:,} old priority 1-3 companies")
    if own:
        conn.close()


# --- the fetcher ---------------------------------------------------------------------------------

def _claim(conn, n: int) -> list[tuple[str, int, bool]]:
    rows = conn.execute("""
        UPDATE uk_companies.fetch_queue q SET state = 'working', claimed = now()
        WHERE q.company_number IN (SELECT company_number FROM uk_companies.fetch_queue
                                   WHERE state = 'pending' AND (retry_after IS NULL OR retry_after < now())
                                   ORDER BY priority, ord, company_number LIMIT %s FOR UPDATE SKIP LOCKED)
        RETURNING q.company_number, q.priority, q.profile_done""", (n,)).fetchall()
    conn.commit()
    rows = sorted(rows, key=lambda r: (r[1], r[0]))
    return [(r[0], r[1], r[2]) for r in rows]


def _worker(work: "queue.Queue", out: "queue.Queue") -> None:
    while not STOP.is_set():
        try:
            number, pri, pdone = work.get(timeout=2)
        except queue.Empty:
            continue
        res = {"number": number, "pri": pri, "profile": None, "officers": [], "http": 200, "error": None}
        try:
            code, rows, counts = fetch_officers(number)
            res["officers"], res["http"] = rows, code
            if pri <= FULL_PRIORITY and not pdone and code != 404:
                pc, js = api_get(f"/company/{number}")
                if pc == 200 and js:
                    res["profile"] = profile_row(number, js, counts)
        except Fatal as e:
            res["error"] = "fatal:" + scrub(e)
        except Exception as e:  # noqa: BLE001
            res["error"] = scrub(e)[:200]
        out.put(res)


def _flush(conn, results: list[dict]) -> None:
    for r in results:
        n = r["number"]
        if r["error"]:
            if r["error"].startswith("fatal:"):
                conn.execute("UPDATE uk_companies.fetch_queue SET state = 'pending', claimed = NULL WHERE company_number = %s", (n,))
                continue
            STATS["errors"] += 1
            conn.execute("""UPDATE uk_companies.fetch_queue SET attempts = attempts + 1, claimed = NULL,
                            state = CASE WHEN attempts + 1 >= 5 THEN 'error' ELSE 'pending' END,
                            retry_after = now() + interval '1 hour' WHERE company_number = %s""", (n,))
            continue
        if r["http"] == 404:
            conn.execute("UPDATE uk_companies.fetch_queue SET state = 'notfound', fetched = now(), http = 404, claimed = NULL WHERE company_number = %s", (n,))
            continue
        conn.execute("DELETE FROM uk_companies.officer WHERE company_number = %s", (n,))
        if r["officers"]:
            with conn.cursor() as cur:
                with cur.copy("COPY uk_companies.officer (" + ",".join(OFFICER_COLS) + ") FROM STDIN") as cp:
                    seen = set()
                    for row in r["officers"]:
                        if row[1] in seen:
                            continue
                        seen.add(row[1])
                        cp.write_row(row)
            STATS["officer_rows"] += len(r["officers"])
        if r["profile"]:
            conn.execute("DELETE FROM uk_companies.profile WHERE company_number = %s", (n,))
            conn.execute(f"INSERT INTO uk_companies.profile ({','.join(PROFILE_COLS)}) VALUES ({','.join(['%s'] * len(PROFILE_COLS))})", r["profile"])
        conn.execute("""UPDATE uk_companies.fetch_queue SET state = 'done', fetched = now(), http = 200, claimed = NULL,
                        profile_done = profile_done OR %s WHERE company_number = %s""", (bool(r["profile"]), n))
        STATS["companies"] += 1
    conn.commit()


def _save_counters(conn) -> None:
    snap = dict(STATS)
    STATS.clear()
    req = LIM.requests
    LIM.requests = 0
    waits, wait_s = LIM.waits, LIM.wait_s
    LIM.waits, LIM.wait_s = 0, 0.0
    buckets = dict(LIM.buckets)
    LIM.buckets.clear()
    conn.execute("""INSERT INTO uk_companies.fetch_daily AS f (day, requests, companies, officer_rows, r429, wall_hits, window_waits, errors, wait_seconds)
                    VALUES (current_date, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (day) DO UPDATE SET requests = f.requests + EXCLUDED.requests, companies = f.companies + EXCLUDED.companies,
                      officer_rows = f.officer_rows + EXCLUDED.officer_rows, r429 = f.r429 + EXCLUDED.r429, wall_hits = f.wall_hits + EXCLUDED.wall_hits,
                      window_waits = f.window_waits + EXCLUDED.window_waits, errors = f.errors + EXCLUDED.errors,
                      wait_seconds = f.wait_seconds + EXCLUDED.wait_seconds""",
                 (req, snap.get("companies", 0), snap.get("officer_rows", 0), snap.get("r429", 0), snap.get("wall_hits", 0), waits,
                  snap.get("errors", 0), wait_s))
    for b, n in buckets.items():
        conn.execute("""INSERT INTO uk_companies.fetch_bucket (bucket, n) VALUES (to_timestamp(%s), %s)
                        ON CONFLICT (bucket) DO UPDATE SET n = fetch_bucket.n + EXCLUDED.n""", (b, n))
    conn.execute("DELETE FROM uk_companies.fetch_bucket WHERE bucket < now() - interval '2 days'")
    conn.commit()


def status_text(conn) -> str:
    q = {r[0] + str(r[1]): r[2] for r in conn.execute("SELECT state, priority, count(*) FROM uk_companies.fetch_queue GROUP BY 1, 2").fetchall()}
    st = collections.Counter()
    for k, v in q.items():
        st[k[:-1]] += v
    day = conn.execute("SELECT requests, companies, officer_rows, r429, wall_hits, window_waits, errors FROM uk_companies.fetch_daily WHERE day = current_date").fetchone()
    h = conn.execute("SELECT coalesce(sum(n), 0) FROM uk_companies.fetch_bucket WHERE bucket > now() - interval '30 minutes'").fetchone()[0]
    n30 = conn.execute("SELECT coalesce(sum(n), 0) FROM uk_companies.fetch_bucket WHERE bucket > now() - interval '24 hours'").fetchone()[0]
    rate = int(h) * 48
    pending = st.get("pending", 0) + st.get("working", 0)
    done = st.get("done", 0)
    per_company = 1.0
    prog = conn.execute("""SELECT sum(requests)::float, sum(companies) FROM uk_companies.fetch_daily WHERE day > current_date - 7""").fetchone()
    if prog and prog[1]:
        per_company = prog[0] / prog[1]
    days = pending * per_company / max(rate, 1)
    d = day or (0, 0, 0, 0, 0, 0, 0)
    by_p = " ".join(f"p{p}={q.get('pending' + str(p), 0) + q.get('working' + str(p), 0):,}" for p in range(1, 7))
    return (f"{done:,} companies done, {pending:,} queued ({by_p}), {st.get('notfound', 0):,} not found, {st.get('error', 0):,} failed; "
            f"today {d[0]:,} requests, {d[1]:,} companies, {d[2]:,} officer rows; last 30 min real rate {rate:,} requests/day equivalent "
            f"(last 24h {int(n30):,}); wall hits today {d[4]} (429s {d[3]}, window-full waits {d[5]}), errors {d[6]}; "
            f"about {per_company:.1f} requests/company so about {days:.0f} days for the queue at this rate")


def run() -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    if not _key():
        _log("no COMPANIES_HOUSE_API_KEY in the environment or .env")
        return 2
    lockconn = db.connect(autocommit=True)
    if not lockconn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
        _log("another fetcher holds the lock (one key, one limit, one copy): exiting")
        return 0
    conn = db.connect()
    conn.execute(DDL)
    conn.commit()
    conn.execute("SET statement_timeout = '60s'")
    # a crash left rows 'working'; the limiter window is rebuilt from the saved buckets so a restart never bursts past the limit
    conn.execute("UPDATE uk_companies.fetch_queue SET state = 'pending', claimed = NULL WHERE state = 'working'")
    stamps = []
    for b, n in conn.execute("SELECT extract(epoch FROM bucket), n FROM uk_companies.fetch_bucket WHERE bucket > now() - interval '5 minutes'").fetchall():
        stamps += [float(b) + 9.9] * int(n)      # the end of the bucket: the pessimistic age
    LIM.seed(stamps)
    conn.commit()
    if conn.execute("SELECT count(*) FROM uk_companies.fetch_queue").fetchone()[0] == 0:
        enqueue(conn)
    _log(f"fetcher started; {len(stamps)} requests counted in the last five minutes; limit {LIMIT} per rolling {int(WINDOW)}s")
    status_line("started; " + status_text(conn))
    work: queue.Queue = queue.Queue(maxsize=WORKERS * 4)
    out: queue.Queue = queue.Queue()
    threads = [threading.Thread(target=_worker, args=(work, out), daemon=True) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    last_flush = last_status = last_save = time.time()
    last_enqueue = time.time()
    results: list[dict] = []
    inflight = 0
    fatal = None
    try:
        while not STOP.is_set():
            if work.qsize() < WORKERS * 2:
                for row in _claim(conn, 24):
                    work.put(row)
                    inflight += 1
            try:
                while True:
                    results.append(out.get(timeout=1.0))
                    inflight -= 1
                    if len(results) >= 25:
                        break
            except queue.Empty:
                pass
            now = time.time()
            if results and (len(results) >= 10 or now - last_flush > 15):
                for r in results:
                    if r["error"] and r["error"].startswith("fatal:"):
                        fatal = r["error"]
                _flush(conn, results)
                results = []
                last_flush = now
            if now - last_save > 20:
                _save_counters(conn)
                last_save = now
            if now - last_status > 1800:
                status_line(status_text(conn))
                last_status = now
            if now - last_enqueue > 86400:
                enqueue(conn)
                conn.execute("SET statement_timeout = '60s'")
                last_enqueue = now
            if fatal:
                break
            if inflight == 0 and work.empty() and not conn.execute("SELECT 1 FROM uk_companies.fetch_queue WHERE state = 'pending' LIMIT 1").fetchone():
                _log("queue empty; waiting for new companies")
                time.sleep(300)
    finally:
        STOP.set()
        time.sleep(1)
        while not out.empty():
            results.append(out.get())
        try:
            if results:
                _flush(conn, results)
            conn.execute("UPDATE uk_companies.fetch_queue SET state = 'pending', claimed = NULL WHERE state = 'working'")
            _save_counters(conn)
        except Exception as e:  # noqa: BLE001
            _log("shutdown flush failed: " + scrub(e)[:120])
        conn.close()
    if fatal:
        status_line("STOPPED: " + fatal)
        _log(fatal)
        return 3
    return 0


# --- watchdog ------------------------------------------------------------------------------------

def ensure() -> int:
    """Start the fetcher detached when it is not running; only on the box that has the RUN_HERE marker (dev)."""
    if not MARKER.exists():
        print("uk officers: not the fetcher box (no RUN_HERE marker)")
        return 0
    if AUTHFAIL.exists() and time.time() - AUTHFAIL.stat().st_mtime < 3600:
        print("uk officers: the key was rejected less than an hour ago; not restarting")
        return 0
    lockconn = db.connect(autocommit=True)
    free = lockconn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]
    if free:
        lockconn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    lockconn.close()
    if not free:
        return 0
    if AUTHFAIL.exists():
        AUTHFAIL.unlink()
    with RUN_LOG.open("a") as f:
        subprocess.Popen([sys.executable, "-m", "loader.uk_officers", "run"], cwd=str(Path.home() / "np-explorer"),
                         stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                         env={**os.environ, "PYTHONPATH": str(Path.home() / "np-explorer")})
    status_line(f"restarted by the watchdog on {socket.gethostname()}")
    print("uk officers: started")
    return 0


def summarize() -> None:
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("SET statement_timeout = 0")
        conn.execute("TRUNCATE uk_companies.officer_stats")
        n = conn.execute("""
            INSERT INTO uk_companies.officer_stats
            SELECT officer_id, (array_agg(name ORDER BY appointed_on DESC NULLS LAST))[1], (array_agg(name_norm ORDER BY appointed_on DESC NULLS LAST))[1],
                   count(*), count(*) FILTER (WHERE resigned_on IS NULL), count(DISTINCT company_number), min(appointed_on),
                   max(birth_year), (array_agg(nationality) FILTER (WHERE nationality IS NOT NULL))[1], min(company_number)
            FROM uk_companies.officer WHERE officer_id IS NOT NULL AND NOT corporate GROUP BY officer_id""").rowcount
        conn.commit()
        _log(f"officer_stats: {n:,} officers")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["enqueue", "run", "ensure", "status", "summarize"])
    a = ap.parse_args(argv)
    if a.step == "enqueue":
        enqueue()
    elif a.step == "run":
        return run()
    elif a.step == "ensure":
        return ensure()
    elif a.step == "summarize":
        summarize()
    else:
        with db.connect() as conn:
            conn.execute(DDL)
            conn.commit()
            print(status_text(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
