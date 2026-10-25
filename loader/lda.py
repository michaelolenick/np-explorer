"""Federal lobbying disclosures (Lobbying Disclosure Act): LD-1 registrations and LD-2 quarterly activity reports.

Source: the LDA REST API (https://lda.gov/api/v1/, formerly lda.senate.gov). It pages 25 filings at a time and
allows 15 requests a minute without a key, 120 with one (LDA_API_KEY in .env; free registration at
https://lda.gov/api/register/). crawl() walks filing years newest first, one filing period at a time, keeps
each filing's JSON in lda_filings_raw and remembers which pages are done in lda_crawl, so it can stop and
resume. Once a period is walked, crawl_new() fetches only the filings posted since (new and amended).
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


def _gap() -> float:
    return 0.55 if _key() else 4.1          # 120 or 15 requests a minute


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


def crawl(years: list[int] | None = None, status=print, max_hours: float | None = None) -> int:
    """Fetch every filing for the given years (default: this year back to 1999), skipping finished pages."""
    stop_at = time.time() + max_hours * 3600 if max_hours else None
    years = years or list(range(date.today().year, FIRST_YEAR - 1, -1))
    status(f"lda crawl: {_rate()}")
    n = 0
    with db.connect() as conn:
        for year in years:
            for period in PERIODS:
                done = conn.execute("SELECT pages_done, pages_total FROM lda_crawl WHERE year = %s AND period = %s",
                                    (year, period)).fetchone()
                page = (done[0] + 1) if done else 1
                total = done[1] if done else None
                if total is not None and page > total:
                    continue                      # finished; new and amended filings come from crawl_new()
                while True:
                    if stop_at and time.time() > stop_at:
                        return n
                    t = time.time()
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
                        status(f"lda {year} {period}: page {page} of {pages} ({n:,} filings this run)")
                    if not d.get("next") or page >= pages:
                        break
                    page += 1
                    time.sleep(max(0.0, _gap() - (time.time() - t)))
            status(f"lda {year}: done ({n:,} filings this run)")
    return n


def crawl_new(status=print, max_hours: float | None = None) -> int:
    """Filings posted since the newest one fetched, any filing year: new reports, amendments and terminations,
    via the API's filing_dt_posted_after filter, oldest first, so a run that stops resumes where it left off.
    A day's overlap catches filings posted late; the upsert makes the repeats harmless."""
    from urllib.parse import quote
    stop_at = time.time() + max_hours * 3600 if max_hours else None
    status(f"lda new filings: {_rate()}")
    n = 0
    with db.connect() as conn:
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
            time.sleep(max(0.0, _gap() - (time.time() - t)))
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
