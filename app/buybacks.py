"""Share buybacks next to insider selling (loader/buybacks.py): the buyback timeline on company pages, insider
trades on person and insider pages, and the buybacks question for plain-English search.

Buyback spending is what the company reported in its cash flow statement (XBRL, SEC Financial Statement Data
Sets); quarters are derived from year-to-date figures. Insider sales are open-market sales (Form 4 code S) and
purchases (code P), at the reported price. A sale is flagged when it came within 30 days after an 8-K announcing a
new or larger buyback, or in a quarter of heavy buybacks (at least $25 million and at least the company's average
buyback quarter). A flag is a coincidence in time, not a finding of wrongdoing; many sales are scheduled in
advance under 10b5-1 plans, which are marked.
"""

from __future__ import annotations

import datetime as dt
import logging

from app import db
from app.corporate import PUBLIC

log = logging.getLogger("np.buybacks")
NOTE = ("Buybacks: cash spent repurchasing common stock, from the company's cash flow statement (quarters derived "
        "from year-to-date figures). Insider sales: open-market sales on Form 4. A flagged sale came within 30 days "
        "after a buyback announcement or in a heavy buyback quarter; that is a timing overlap, not evidence of "
        "wrongdoing, and sales marked 10b5-1 were scheduled in advance under a trading plan.")


def _ok(conn) -> bool:
    return bool(conn.execute("SELECT to_regclass('sec_buybacks') IS NOT NULL AS ok").fetchone()["ok"])


def edgar(cik, accession: str) -> str:
    from app.corporate import filing_url
    return filing_url(cik, accession)


def chart(quarters: list[dict], marks: list, w: int = 720, h: int = 170) -> dict | None:
    """Paired bars per quarter (buybacks, insider sales) and dashed lines at buyback announcements."""
    if not quarters:
        return None
    n = len(quarters)
    slot = (w - 16) / n
    top = max([float(q["buybacks"] or 0) for q in quarters] + [float(q["sold"] or 0) for q in quarters] + [1])
    bars, labels = [], []
    for i, q in enumerate(quarters):
        x0 = 8 + i * slot
        for j, key in enumerate(("buybacks", "sold")):
            v = max(float(q[key] or 0), 0)
            bh = (h - 30) * v / top
            bars.append({"x": round(x0 + slot * (0.1 + 0.4 * j), 1), "w": round(slot * 0.38, 1),
                         "y": round(h - 20 - bh, 1), "h": round(bh, 1), "kind": key, "v": v, "q": q["label"]})
        if q["label"].endswith("Q1") and (n <= 24 or int(q["label"][:4]) % 2 == 0):
            labels.append({"x": round(x0 + slot / 2, 1), "text": q["label"][:4]})
    idx = {q["start"]: i for i, q in enumerate(quarters)}
    lines = []
    for m in marks:
        qs = m["filed"].replace(month=(m["filed"].month - 1) // 3 * 3 + 1, day=1)
        if qs in idx:
            frac = (m["filed"] - qs).days / 92
            lines.append({"x": round(8 + (idx[qs] + frac) * slot, 1), "filed": m["filed"]})
    return {"w": w, "h": h, "bars": bars, "labels": labels, "lines": lines, "top": top}


def company(cik: str) -> dict | None:
    """Everything for the buybacks section of a company page. cik: digits, any zero padding."""
    if not PUBLIC:
        return None
    c = cik.lstrip("0")
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '6s'")
            if not _ok(conn):
                return None
            q = conn.execute("""SELECT period_end, buybacks, net_income, derived, adsh FROM sec_buybacks
                                WHERE cik = %s AND qtrs = 1 ORDER BY period_end""", (c,)).fetchall()
            years = conn.execute("""SELECT period_end, buybacks, net_income, adsh FROM sec_buybacks
                                    WHERE cik = %s AND qtrs = 4 ORDER BY period_end DESC""", (c,)).fetchall()
            if not q and not years:
                return None
            d0 = q[-48:][0]["period_end"] - dt.timedelta(days=20) if q else dt.date(2009, 1, 1)
            since = dt.date(d0.year, (d0.month - 1) // 3 * 3 + 1, 1)      # sales from the first quarter shown
            sales = conn.execute("""
                SELECT date_trunc('quarter', trans_date)::date AS qs, sum(value) AS sold, count(*) AS n,
                       sum(value) FILTER (WHERE plan) AS plan_sold
                FROM sec_buyback_sales WHERE issuer_cik = %s GROUP BY 1""", (c,)).fetchall()
            ann = conn.execute("""SELECT accession, filed, items, document FROM sec_buyback_announcements
                                  WHERE cik = %s ORDER BY filed DESC""", (c,)).fetchall()
            auth = conn.execute("""SELECT ddate, authorized, remaining, adsh FROM sec_buyback_auth WHERE cik = %s
                                   ORDER BY ddate DESC LIMIT 40""", (c,)).fetchall()
            months = conn.execute("""SELECT * FROM sec_buyback_months WHERE cik = %s AND NOT is_total
                                     AND period_end IS NOT NULL ORDER BY period_end DESC, row_no LIMIT 60""", (c,)).fetchall()
            flagged = conn.execute("""
                SELECT s.*, (s.ann_accession IS NOT NULL) AS after_ann FROM sec_buyback_sales s
                WHERE s.issuer_cik = %s AND (s.ann_accession IS NOT NULL OR s.heavy) AND s.trans_date >= %s
                ORDER BY s.value DESC LIMIT 50""", (c, since)).fetchall()
            totals = conn.execute("""
                SELECT count(*) AS n, sum(value) AS sold, count(*) FILTER (WHERE ann_accession IS NOT NULL) AS n_ann,
                       sum(value) FILTER (WHERE ann_accession IS NOT NULL) AS sold_ann,
                       count(*) FILTER (WHERE heavy) AS n_heavy, sum(value) FILTER (WHERE heavy) AS sold_heavy,
                       sum(value) FILTER (WHERE plan) AS sold_plan,
                       count(*) FILTER (WHERE quarter_buybacks > 0) AS n_during,
                       sum(value) FILTER (WHERE quarter_buybacks > 0) AS sold_during
                FROM sec_buyback_sales WHERE issuer_cik = %s AND trans_date >= %s""", (c, since)).fetchone()
            links = conn.execute("""
                SELECT l.kind, l.key, l.name,
                       CASE WHEN l.kind = 'lobbying' THEN (SELECT sum(coalesce(f.income, f.expenses)) FROM lda_filings f
                                                         WHERE f.client_id::text = l.key) END AS lobbying
                FROM sec_company_links l WHERE l.cik = %s ORDER BY l.kind, l.name""", (c,)).fetchall()
            name = conn.execute("SELECT name FROM sec_fin_subs WHERE cik = %s ORDER BY filed DESC LIMIT 1",
                                (c,)).fetchone()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        log.exception("buybacks company %s", cik)
        return None
    by_q = {s["qs"]: s for s in sales}
    quarters = []
    for r in q[-48:]:                     # the last 12 years
        pe = r["period_end"]
        d = pe - dt.timedelta(days=20)          # a 52-53 week quarter ending January 2 belongs to Q4
        qs = dt.date(d.year, (d.month - 1) // 3 * 3 + 1, 1)
        s = by_q.get(qs) or {}
        quarters.append({"start": qs, "label": f"{qs.year} Q{(qs.month - 1) // 3 + 1}", "period_end": pe,
                         "buybacks": r["buybacks"], "net_income": r["net_income"], "derived": r["derived"],
                         "sold": s.get("sold"), "n_sales": s.get("n"), "plan_sold": s.get("plan_sold"),
                         "heavy": False, "adsh": r["adsh"]})
    pos = [float(x["buybacks"]) for x in quarters if x["buybacks"] and x["buybacks"] > 0]
    avg = sum(pos) / len(pos) if pos else 0
    for x in quarters:
        x["heavy"] = bool(x["buybacks"] and float(x["buybacks"]) >= max(avg, 25e6))
    first = quarters[0]["start"] if quarters else None
    marks = [a for a in ann if first and a["filed"] >= first]
    return {"cik": c, "name": name["name"] if name else None, "quarters": quarters, "since": since, "years": years,
            "announcements": ann, "auth": auth, "months": months, "flagged": flagged, "totals": totals,
            "links": links, "chart": chart(quarters, marks), "note": NOTE}


def trades(owner_ciks: list[str], limit: int = 300) -> dict | None:
    """Open-market buys and sales (codes P and S) by these SEC filers, newest first, with totals by company."""
    if not PUBLIC or not owner_ciks:
        return None
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '5s'")
            rows = conn.execute("""
                SELECT t.trans_date, t.code, t.shares, t.price, t.shares * t.price AS value, f.accession,
                       f.issuer_cik, f.issuer_name, f.ticker, o.owner_cik,
                       coalesce(p.aff10b5one, false) OR coalesce(p.footnote, false) AS plan,
                       bs.ann_accession, bs.heavy
                FROM sec_insider_owners o JOIN sec_insider_filings f ON f.accession = o.accession
                JOIN sec_insider_trans t ON t.accession = o.accession
                LEFT JOIN sec_insider_plans p ON p.accession = o.accession
                LEFT JOIN sec_buyback_sales bs ON bs.accession = t.accession AND bs.sk = t.sk
                WHERE o.owner_cik = ANY(%s) AND t.code IN ('P', 'S') AND t.shares > 0
                ORDER BY t.trans_date DESC NULLS LAST, f.accession, t.sk LIMIT %s""", (owner_ciks, limit)).fetchall()
            tot = conn.execute("""
                SELECT f.issuer_cik, f.issuer_name, sum(t.shares * t.price) FILTER (WHERE t.code = 'S') AS sold,
                       sum(t.shares * t.price) FILTER (WHERE t.code = 'P') AS bought,
                       min(t.trans_date) AS first, max(t.trans_date) AS last, count(*) AS n
                FROM sec_insider_owners o JOIN sec_insider_filings f ON f.accession = o.accession
                JOIN sec_insider_trans t ON t.accession = o.accession
                WHERE o.owner_cik = ANY(%s) AND t.code IN ('P', 'S') AND t.shares > 0 AND t.price > 0
                GROUP BY 1, 2 ORDER BY coalesce(sum(t.shares * t.price) FILTER (WHERE t.code = 'S'), 0) DESC
                LIMIT 50""", (owner_ciks,)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("insider trades")
        return None
    if not rows:
        return None
    return {"rows": rows, "by_company": tot, "shown": len(rows), "limit": limit}


def person_trades(cluster_id: int) -> dict | None:
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            ciks = [r["key"] for r in conn.execute("""SELECT key FROM sec_person_links WHERE cluster_id = %s
                                                     AND source = 'insider'""", (cluster_id,)).fetchall()]
    except Exception:  # noqa: BLE001
        return None
    return trades(ciks)


def find_company(name: str) -> dict | None:
    """The company a plain-English question names: the biggest buyback spender whose name starts with it, else
    contains it."""
    n = (name or "").strip().lower()
    if len(n) < 2:
        return None
    try:
        with db.conn() as conn:
            for pat in (n + "%", "%" + n + "%"):
                r = conn.execute("""
                    SELECT s.cik, max(s.name) AS name, coalesce(sum(b.buybacks) FILTER (WHERE b.qtrs = 4), 0) AS total
                    FROM (SELECT DISTINCT ON (cik) cik, name FROM sec_fin_subs WHERE lower(name) LIKE %s
                          ORDER BY cik, filed DESC) s
                    LEFT JOIN sec_buybacks b ON b.cik = s.cik GROUP BY s.cik ORDER BY 3 DESC LIMIT 1""",
                                 (pat,)).fetchone()
                if r:
                    return r
    except Exception:  # noqa: BLE001
        log.exception("buybacks find_company")
    return None


def answer(company_name: str, year_from: int | None = None) -> dict:
    """The buybacks question: buybacks by year, insider sales during buyback quarters and after announcements."""
    c = find_company(company_name)
    if not c:
        return {"kind": "buybacks", "company": None, "query": company_name}
    data = company(c["cik"]) or {}
    years = [y for y in data.get("years", []) if not year_from or y["period_end"].year >= year_from]
    return {"kind": "buybacks", "company": c, "data": data, "years": years[:12],
            "url": f"/corporate/company/{c['cik']}#buybacks"}
