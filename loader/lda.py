"""Federal lobbying disclosures (Lobbying Disclosure Act): LD-1 registrations and LD-2 quarterly activity reports.

Source: the LDA REST API (https://lda.gov/api/v1/, formerly lda.senate.gov). It pages 25 filings at a time and
allows 15 requests a minute without a key, 120 with one (LDA_API_KEY in .env; free registration at
https://lda.gov/api/register/). crawl() walks filing years newest first, one filing period at a time, keeps
each filing's JSON in lda_filings_raw and remembers which pages are done in lda_crawl, so it can stop and
resume. SHARDS crawlers walk the backfill at once (crawl --shard i --of N), each at 1/N of the rate, a pg
advisory lock per filing period keeping two off the same one. Once a period is walked, crawl_new() fetches
only the filings posted since (new and amended), one crawler.
parse() turns the raw JSON into lda_filings, lda_activities and lda_activity_lobbyists.

Every filing links to its source: the filing document on lda.gov (filing_document_url).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date

from loader import db

API = "https://lda.gov/api/v1/filings/"
FIRST_YEAR = 1999
PERIODS = ["first_quarter", "second_quarter", "third_quarter", "fourth_quarter", "mid_year", "year_end"]


def _key() -> str | None:
    return os.environ.get("LDA_API_KEY") or None


SHARDS = 4                       # owner, 2026-10-25: 4 backfill crawlers at once share the key's 120/min


def _gap(of: int = 1) -> float:
    """Seconds between one crawler's requests when `of` crawlers run at once: together they stay at the API's
    limit, 120 requests a minute with a key, 15 without (0.5 s or 4.1 s per request, split `of` ways)."""
    return (0.5 if _key() else 4.1) * max(1, of)


CRAWL_LOCK = 7_412_001           # pg advisory lock: crawl_new() and an unsharded crawl(), one at a time
UNIT_LOCK = 7_412                # pg advisory lock (UNIT_LOCK, year*10 + period index): one crawler per filing period


def _locked(conn, status, key: int = CRAWL_LOCK) -> bool:
    """Take a crawl lock for this connection's session (released when it closes); False if another holds it."""
    if conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
        return True
    status(f"lda: another crawl holds lock {key}; skipping")
    return False


def shard_lock(shard: int) -> int:
    return CRAWL_LOCK + 1 + shard


def units(years: list[int], shard: int = 0, of: int = 1) -> list[tuple[int, str]]:
    """Every (year, period) newest first, this shard's own (every of-th, offset shard) first, then the rest, so a
    shard that finishes early helps with what the others have not reached; the period locks keep any two
    crawlers off the same period."""
    allu = [(y, p) for y in years for p in PERIODS]
    mine = [u for i, u in enumerate(allu) if i % of == shard]
    return mine + [u for i, u in enumerate(allu) if i % of != shard]


def _rate() -> str:
    """Logged at the start of every crawl, so a missing key can't go unnoticed (the key is read at run time)."""
    return "120/min with key" if _key() else "15/min, no key (set LDA_API_KEY in .env)"


def _get(url: str, status=print) -> dict:
    headers = {"User-Agent": "furp.org (public data explorer)", "Accept": "application/json"}
    if _key():
        headers["Authorization"] = f"Token {_key()}"
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or 60)
                time.sleep(min(max(wait, 10), 300))
                continue
            if e.code >= 500 and attempt < 7:
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"LDA API kept failing: {url}")


def crawl(years: list[int] | None = None, status=print, max_hours: float | None = None,
          shard: int | None = None, of: int = 1) -> int:
    """Fetch every filing for the given years (default: this year back to 1999), skipping finished pages.
    shard i of N: one of N crawlers running at once (python -m loader.lda crawl --shard i --of N), each at 1/N of
    the API's rate; the period locks and the lda_crawl checkpoint let them share the work and resume."""
    stop_at = time.time() + max_hours * 3600 if max_hours else None
    years = years or list(range(date.today().year, FIRST_YEAR - 1, -1))
    n = 0
    gap = _gap(of)
    last = 0.0                                    # time of this crawler's last request
    with db.connect() as conn:
        if not _locked(conn, status, CRAWL_LOCK if shard is None else shard_lock(shard)):
            return 0
        label = "" if shard is None else f" shard {shard} of {of}"
        status(f"lda crawl{label}: {_rate()}, {gap:.1f} s between this crawler's requests")
        for year, period in units(years, shard or 0, of if shard is not None else 1):
            ukey = year * 10 + PERIODS.index(period)
            if not conn.execute("SELECT pg_try_advisory_lock(%s, %s)", (UNIT_LOCK, ukey)).fetchone()[0]:
                continue                          # another crawler is on this period
            try:
                done = conn.execute("SELECT pages_done, pages_total FROM lda_crawl WHERE year = %s AND period = %s",
                                    (year, period)).fetchone()
                page = (done[0] + 1) if done else 1
                total = done[1] if done else None
                if total is not None and page > total:
                    continue                  # finished; new and amended filings come from crawl_new()
                while True:
                    if stop_at and time.time() > stop_at:
                        return n
                    time.sleep(max(0.0, gap - (time.time() - last)))
                    last = time.time()
                    d = _get(f"{API}?filing_year={year}&filing_period={period}&page={page}&ordering=dt_posted", status)
                    pages = max(1, -(-d["count"] // 25))
                    with conn.cursor() as cur:
                        for f in d["results"]:
                            cur.execute("""INSERT INTO lda_filings_raw (filing_uuid, filing_year, filing_period, doc)
                                           VALUES (%s, %s, %s, %s)
                                           ON CONFLICT (filing_uuid) DO UPDATE SET doc = excluded.doc,
                                               fetched = now(), parsed = false""",
                                        (f["filing_uuid"], year, period, json.dumps(f)))
                    conn.execute("""INSERT INTO lda_crawl (year, period, pages_done, pages_total, updated)
                                    VALUES (%s, %s, %s, %s, now())
                                    ON CONFLICT (year, period) DO UPDATE SET pages_done = excluded.pages_done,
                                        pages_total = excluded.pages_total, updated = now()""",
                                 (year, period, page, pages))
                    conn.commit()
                    n += len(d["results"])
                    if page % 40 == 0:
                        status(f"lda {year} {period}{label}: page {page} of {pages} ({n:,} filings this run)")
                    if not d.get("next") or page >= pages:
                        status(f"lda {year} {period}{label}: done, {pages} pages ({n:,} filings this run)")
                        break
                    page += 1
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s, %s)", (UNIT_LOCK, ukey))
                conn.commit()
        status(f"lda crawl{label}: pass finished ({n:,} filings this run)")
    return n


def crawl_new(status=print, max_hours: float | None = None, of: int = 1) -> int:
    """Filings posted since the newest one fetched, any filing year: new reports, amendments and terminations,
    via the API's filing_dt_posted_after filter, oldest first, so a run that stops resumes where it left off.
    A day's overlap catches filings posted late; the upsert makes the repeats harmless. Always one crawler (the
    original lock); `of` is how many crawlers run at once, so it takes only its share of the rate."""
    from urllib.parse import quote
    stop_at = time.time() + max_hours * 3600 if max_hours else None
    n = 0
    with db.connect() as conn:
        if not _locked(conn, status):
            return 0
        status(f"lda new filings: {_rate()}")
        since = conn.execute("SELECT max((doc->>'dt_posted')::timestamptz) - interval '1 day' FROM lda_filings_raw"
                             ).fetchone()[0]
        if since is None:
            return 0                              # nothing fetched yet: crawl() walks the years first
        page = 1
        while True:
            if stop_at and time.time() > stop_at:
                break
            t = time.time()
            d = _get(f"{API}?filing_dt_posted_after={quote(since.isoformat())}&ordering=dt_posted&page={page}", status)
            with conn.cursor() as cur:
                for f in d["results"]:
                    cur.execute("""INSERT INTO lda_filings_raw (filing_uuid, filing_year, filing_period, doc)
                                   VALUES (%s, %s, %s, %s)
                                   ON CONFLICT (filing_uuid) DO UPDATE SET doc = excluded.doc,
                                       fetched = now(), parsed = false""",
                                (f["filing_uuid"], f["filing_year"], f["filing_period"], json.dumps(f)))
            conn.commit()
            n += len(d["results"])
            if page % 40 == 0:
                status(f"lda new filings since {since:%Y-%m-%d}: page {page} of {-(-d['count'] // 25)}")
            if not d.get("next"):
                break
            page += 1
            time.sleep(max(0.0, _gap(of) - (time.time() - t)))
    status(f"lda: {n:,} filings posted since {since:%Y-%m-%d %H:%M} fetched")
    return n


# --- parse ---------------------------------------------------------------------------------------

def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _lobbyist_name(lb: dict) -> str:
    return " ".join(x for x in (lb.get("first_name"), lb.get("middle_name"), lb.get("last_name"), lb.get("suffix"))
                    if x).strip()


def parse(status=print, batch: int = 2000) -> int:
    """Raw filings not yet parsed -> lda_filings, lda_activities, lda_activity_lobbyists (replaced per filing)."""
    from app.names import normalize_name
    n = 0
    with db.connect() as conn:
        while True:
            rows = conn.execute("""SELECT filing_uuid, doc FROM lda_filings_raw WHERE NOT parsed
                                   ORDER BY filing_uuid LIMIT %s""", (batch,)).fetchall()
            if not rows:
                break
            ids = [r[0] for r in rows]
            for t in ("lda_activity_lobbyists", "lda_activities", "lda_filings"):
                conn.execute(f"DELETE FROM {t} WHERE filing_uuid = ANY(%s)", (ids,))
            fil, act, lob = [], [], []
            for uuid, f in rows:
                reg, cli = f.get("registrant") or {}, f.get("client") or {}
                fil.append((uuid, f.get("filing_type"), f.get("filing_type_display"), f.get("filing_year"),
                            f.get("filing_period"), f.get("filing_document_url"), _num(f.get("income")),
                            _num(f.get("expenses")), f.get("dt_posted"), f.get("termination_date"), reg.get("id"),
                            reg.get("name"), f.get("registrant_state") or reg.get("state"), cli.get("id"),
                            cli.get("name"), cli.get("general_description"), cli.get("state"),
                            bool(cli.get("client_self_select"))))
                for i, a in enumerate(f.get("lobbying_activities") or []):
                    ents = [e.get("name") for e in a.get("government_entities") or [] if e.get("name")]
                    act.append((uuid, i, a.get("general_issue_code"), a.get("general_issue_code_display"),
                                (a.get("description") or "")[:4000], ents))
                    seen = set()
                    for x in a.get("lobbyists") or []:
                        lb = x.get("lobbyist") or {}
                        if not lb.get("id") or lb["id"] in seen:
                            continue
                        seen.add(lb["id"])
                        name = _lobbyist_name(lb)
                        lob.append((uuid, i, lb["id"], name, normalize_name(name), x.get("covered_position"),
                                    x.get("new")))
            with conn.cursor() as cur:
                db.copy_rows(cur, "lda_filings", ["filing_uuid", "filing_type", "filing_type_display", "filing_year",
                                                  "filing_period", "document_url", "income", "expenses", "dt_posted",
                                                  "termination_date", "registrant_id", "registrant_name",
                                                  "registrant_state", "client_id", "client_name",
                                                  "client_description", "client_state", "self_filer"], fil)
                db.copy_rows(cur, "lda_activities", ["filing_uuid", "n", "issue_code", "issue", "description",
                                                     "entities"], act)
                db.copy_rows(cur, "lda_activity_lobbyists", ["filing_uuid", "n", "lobbyist_id", "name", "name_norm",
                                                             "covered_position", "new"], lob)
            conn.execute("UPDATE lda_filings_raw SET parsed = true WHERE filing_uuid = ANY(%s)", (ids,))
            conn.commit()
            n += len(rows)
    status(f"lda: parsed {n:,} filings")
    return n


def link_orgs(status=print) -> None:
    """Clients and registrants that are filing organizations: normalized name (np_name_core) and state equal,
    exactly one organization with that name in that state. Sets client_ein / registrant_ein."""
    from loader.fec_links import ensure_function
    with db.connect() as conn:
        ensure_function(conn)
        conn.execute("""
            CREATE TEMP TABLE org_keys AS
            SELECT np_name_core(name) AS core, state, min(ein) AS ein FROM organizations
            WHERE name IS NOT NULL GROUP BY 1, 2 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON org_keys (core, state)")
        for side in ("client", "registrant"):
            conn.execute(f"""
                UPDATE lda_filings f SET {side}_ein = k.ein
                FROM org_keys k
                WHERE k.core = np_name_core(f.{side}_name) AND k.state = f.{side}_state
                  AND f.{side}_ein IS DISTINCT FROM k.ein""")
        conn.commit()
        r = conn.execute("""SELECT count(DISTINCT client_id) FILTER (WHERE client_ein IS NOT NULL),
                                   count(DISTINCT client_id),
                                   count(DISTINCT registrant_id) FILTER (WHERE registrant_ein IS NOT NULL),
                                   count(DISTINCT registrant_id) FROM lda_filings""").fetchone()
    status(f"lda: clients linked {r[0]:,} of {r[1]:,}; registrants linked {r[2]:,} of {r[3]:,}")


def crawl_all(status=print, max_hours: float | None = None, shard: int | None = None, of: int = 1) -> None:
    """Filings posted since the last run, then the backfill of older years, until caught up (or max_hours).
    With shards, only shard 0 fetches the new filings (one crawler under the original lock), then its share."""
    stop_at = time.time() + max_hours * 3600 if max_hours else None
    if not shard:
        crawl_new(status=status, max_hours=max_hours, of=of if shard is not None else 1)
    crawl(status=status, max_hours=(stop_at - time.time()) / 3600 if stop_at else None, shard=shard,
          of=of if shard is not None else 1)


if __name__ == "__main__":
    # .venv/bin/python -m loader.lda crawl [--shard i --of N] [--max-hours H]
    # (scripts/offhours.py starts SHARDS of these detached; they run any time of day until caught up)
    import argparse
    import datetime as _dt
    import sys

    def _log(msg: str) -> None:
        print(f"{_dt.datetime.now(_dt.timezone.utc):%Y-%m-%d %H:%M} {msg}", flush=True)

    if sys.argv[1:2] == ["crawl"]:
        ap = argparse.ArgumentParser(prog="loader.lda crawl")
        ap.add_argument("--shard", type=int)
        ap.add_argument("--of", type=int, default=SHARDS)
        ap.add_argument("--max-hours", type=float)
        a = ap.parse_args(sys.argv[2:])
        if a.shard is not None and not 0 <= a.shard < a.of:
            ap.error("--shard must be 0 .. --of minus 1")
        crawl_all(status=_log, max_hours=a.max_hours, shard=a.shard, of=a.of)
