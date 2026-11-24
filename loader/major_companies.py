"""Major companies: an approximate Fortune 1000 plus the S&P 500, and their filings read ahead of time (owner, 2026-11-24).

    python -m loader.major_companies list        build the list (table major_companies)
    python -m loader.major_companies preload     read the latest 10-K/20-F and any S-1/F-1 of the last 3 years of every company
                                                 not yet read, through the strategic-profile parser (app/s1profile.py)
    python -m loader.major_companies refresh     list (weekly) + preload: run nightly; new filings are the only work
    python -m loader.major_companies status      counts

The list is not official. Revenue ranking: SEC XBRL frames (us-gaap Revenues, RevenueFromContractWithCustomer..., SalesRevenueNet)
for the latest calendar year, US filers with a ticker, top ~1000; merged by CIK with the S&P 500 constituents on Wikipedia.
Each company carries aliases (legal name, common name, ticker, suffixes such as Inc, Corp, Co, The, & and punctuation dropped)
that app/company_route.py reads to recognize it in a search. Source: SEC EDGAR (polite fetcher in loader/s1_terms.py), Wikipedia.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import time

log = logging.getLogger("np.major")
TOP_N = 1000
CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet", "SalesRevenueGoodsNet")


def _db():
    from app import db
    try:
        db.pool.open()
    except Exception:  # noqa: BLE001
        pass
    return db


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS major_companies (
        cik text PRIMARY KEY, name text NOT NULL, legal_name text, ticker text, revenue numeric, rev_rank int,
        sp500 boolean NOT NULL DEFAULT false, f1000 boolean NOT NULL DEFAULT false, aliases text[] NOT NULL DEFAULT '{}',
        updated timestamptz NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS major_filings (
        accession text PRIMARY KEY, cik text NOT NULL, form text, filed date, status text NOT NULL, error text,
        built timestamptz NOT NULL DEFAULT now())""")
    conn.execute("CREATE INDEX IF NOT EXISTS major_filings_cik ON major_filings (cik)")


def _tickers() -> dict[str, dict]:
    from loader import s1_terms as T
    body = T._get("https://www.sec.gov/files/company_tickers.json", 8 << 20)
    out: dict[str, dict] = {}
    for v in (json.loads(body) if body else {}).values():
        out.setdefault(str(int(v["cik_str"])), {"ticker": v["ticker"], "title": v["title"]})   # market-value order: first wins
    return out


def _revenues(year: int) -> dict[str, tuple[float, str]]:
    from loader import s1_terms as T
    best: dict[str, tuple[float, str]] = {}
    for c in CONCEPTS:
        body = T._get(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{c}/USD/CY{year}.json", 96 << 20)
        for r in (json.loads(body) if body else {}).get("data", []):
            if not str(r.get("loc") or "").startswith("US"):
                continue
            k = str(int(r["cik"]))
            if r["val"] > best.get(k, (0, ""))[0]:
                best[k] = (float(r["val"]), r.get("entityName") or "")
    return best


def _sp500() -> dict[str, dict]:
    """{cik: {symbol, name}} from Wikipedia's constituents table."""
    from loader import s1_terms as T
    import lxml.html
    body = T._get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 8 << 20)
    out: dict[str, dict] = {}
    if not body:
        return out
    root = lxml.html.fromstring(body)
    tbl = root.xpath("//table[@id='constituents']")
    if not tbl:
        return out
    rows = tbl[0].xpath(".//tr")
    head = [" ".join(h.text_content().split()).lower() for h in rows[0].xpath("./th")]
    ci = head.index("cik") if "cik" in head else None
    si = head.index("symbol") if "symbol" in head else 0
    ni = head.index("security") if "security" in head else 1
    for tr in rows[1:]:
        td = [" ".join(x.text_content().split()) for x in tr.xpath("./td")]
        if ci is None or len(td) <= max(ci, si, ni) or not td[ci].strip().isdigit():
            continue
        out[str(int(td[ci]))] = {"symbol": td[si].replace(".", "-"), "name": td[ni]}
    return out


def _aliases(legal: str, common: str, ticker: str) -> list[str]:
    from app.company_route import key
    out = []
    for n in (legal, common):
        for v in (n, re.sub(r"\b(?:holdings?|group|international|technologies|enterprises|companies|stores|brands)\b", " ", n or "", flags=re.I)):
            k = key(v)
            if len(k) >= 3 and k not in out:
                out.append(k)
    return out


def build_list(top: int = TOP_N) -> dict:
    db = _db()
    from app.company_route import key
    tick = _tickers()
    year = dt.date.today().year - 1
    rev = _revenues(year)
    if len(rev) < 500:                         # the year's frame is thin early on: fall back one year
        rev = {**_revenues(year - 1), **rev}
    sp = _sp500()
    ranked = sorted(((v[0], k) for k, v in rev.items() if k in tick), reverse=True)[:top]
    f1000 = {k: (i + 1, v) for i, (v, k) in enumerate(ranked)}
    ciks = set(f1000) | set(sp)
    n = 0
    with db.pool.connection() as conn:
        ensure_tables(conn)
        for cik in ciks:
            t = tick.get(cik)
            if not t:
                continue
            w = sp.get(cik)
            legal = t["title"]
            common = (w or {}).get("name") or legal.title()
            ticker = (w or {}).get("symbol") or t["ticker"]
            rk, rv = f1000.get(cik, (None, rev.get(cik, (None,))[0]))
            conn.execute("""INSERT INTO major_companies (cik, name, legal_name, ticker, revenue, rev_rank, sp500, f1000, aliases, updated)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                            ON CONFLICT (cik) DO UPDATE SET name = EXCLUDED.name, legal_name = EXCLUDED.legal_name,
                              ticker = EXCLUDED.ticker, revenue = EXCLUDED.revenue, rev_rank = EXCLUDED.rev_rank,
                              sp500 = EXCLUDED.sp500, f1000 = EXCLUDED.f1000, aliases = EXCLUDED.aliases, updated = now()""",
                         (cik, common, legal, ticker, rv, rk, bool(w), cik in f1000, _aliases(legal, common, ticker)))
            n += 1
    return {"companies": n, "sp500": len(sp), "f1000": len(f1000), "revenue_year": year}


def targets(cik: str) -> list[dict]:
    """The filings to read: the newest 10-K or 20-F, and S-1/F-1 family filings of the last 3 years (newest three)."""
    from app import s1profile as S
    fl = S.all_filings(cik)
    ann = [f for f in fl if f["form"] in S.ANNUAL][:1]
    cut = dt.date.today() - dt.timedelta(days=3 * 365)
    reg = [f for f in fl if f["form"] not in S.ANNUAL and f["filed"] >= cut][:3]
    return ann + reg


def preload(limit: int | None = None, only: list[str] | None = None, budget_s: float | None = None) -> dict:
    db = _db()
    from app import s1profile as S
    with db.pool.connection() as conn:
        ensure_tables(conn)
        rows = conn.execute("SELECT cik, name FROM major_companies ORDER BY rev_rank NULLS LAST, cik").fetchall()
    if only:
        rows = [r for r in rows if r["cik"] in only]
    t0 = time.time()
    c = {"companies": 0, "filings": 0, "built": 0, "cached": 0, "failed": 0, "no_filing": 0}
    for r in rows[:limit] if limit else rows:
        if budget_s and time.time() - t0 > budget_s:
            break
        c["companies"] += 1
        try:
            tg = targets(r["cik"])
        except Exception as e:  # noqa: BLE001
            log.exception("filings of %s", r["cik"])
            c["failed"] += 1
            _mark(db, r["cik"], f"list-{r['cik']}", None, None, "failed", f"filing list: {e}"[:300])
            continue
        if not tg:
            c["no_filing"] += 1
        for f in tg:
            c["filings"] += 1
            if S.stored(f["accession"]) is not None:
                c["cached"] += 1
                _mark(db, r["cik"], f["accession"], f["form"], f["filed"], "ok", None)
                continue
            try:
                d = S.build(r["cik"], f["accession"], summaries=False)
                if d.get("error"):
                    c["failed"] += 1
                    _mark(db, r["cik"], f["accession"], f["form"], f["filed"], "failed", d["error"][:300])
                else:
                    c["built"] += 1
                    _mark(db, r["cik"], f["accession"], f["form"], f["filed"], "ok" if not d.get("partial") else "partial", None)
            except Exception as e:  # noqa: BLE001
                log.exception("build %s %s", r["cik"], f["accession"])
                c["failed"] += 1
                _mark(db, r["cik"], f["accession"], f["form"], f["filed"], "failed", str(e)[:300])
        if c["companies"] % 25 == 0:
            print(json.dumps(c), flush=True)
    return c


def _mark(db, cik, acc, form, filed, status, err) -> None:
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO major_filings (accession, cik, form, filed, status, error) VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (accession) DO UPDATE SET status = EXCLUDED.status, error = EXCLUDED.error, built = now()""",
                     (acc, cik, form, filed, status, err))


def status() -> dict:
    db = _db()
    with db.pool.connection() as conn:
        ensure_tables(conn)
        a = conn.execute("SELECT count(*) n, count(*) FILTER (WHERE sp500) sp, count(*) FILTER (WHERE f1000) f FROM major_companies").fetchone()
        b = conn.execute("SELECT status, count(*) n FROM major_filings GROUP BY status").fetchall()
        c = conn.execute("SELECT count(DISTINCT cik) n FROM major_filings WHERE status IN ('ok','partial')").fetchone()
    return {"companies": a["n"], "sp500": a["sp"], "f1000": a["f"], "filings_by_status": {r["status"]: r["n"] for r in b},
            "companies_with_a_profile": c["n"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "preload", "refresh", "status"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--budget", type=float, help="seconds")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if a.cmd == "list":
        print(build_list())
    elif a.cmd == "preload":
        print(preload(a.limit, a.only, a.budget))
    elif a.cmd == "refresh":
        db = _db()
        with db.pool.connection() as conn:
            ensure_tables(conn)
            r = conn.execute("SELECT max(updated) u FROM major_companies").fetchone()
        if not r["u"] or (dt.datetime.now(dt.timezone.utc) - r["u"]).days >= 7:
            print(build_list())
        print(preload(budget_s=a.budget or 3 * 3600))
    else:
        print(json.dumps(status(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
