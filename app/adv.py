"""SEC Form ADV on the site (loader/adv.py): private funds' yearly size and investors (Schedule D 7.B.1) on fund
pages and Form D pages, advisers' owners and control persons on person pages. ADV reports a fund's gross asset
value once a year; it does not say why the value changed (new money, gains, distributions or write-downs).
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db
from app.corporate import PUBLIC

router = APIRouter()
log = logging.getLogger("np.adv")
IAPD = "https://adviserinfo.sec.gov/firm/summary/{crd}"
NOTE = ("Form ADV reports each private fund's gross asset value and number of beneficial owners once a year. It shows "
        "fund size, not distributions: a drop can be money paid back to investors, a write-down, or both, and a rise "
        "can be new money or gains.")


def iapd(crd) -> str:
    return IAPD.format(crd=crd)


def _years(conn, fund_id: str) -> list[dict]:
    """One row per year: the largest report of the fund that year (a fund can be reported by more than one adviser)."""
    return conn.execute("""SELECT DISTINCT ON (year) year, gav, owners, min_investment, fund_type, fund_name, crd
                           FROM adv_funds WHERE fund_id = %s AND year IS NOT NULL
                           ORDER BY year, gav DESC NULLS LAST""", (fund_id,)).fetchall()


def _raised(conn, roots: list[str]) -> dict[int, float]:
    """Form D amount sold by year (the latest filing in each year, summed over the linked offerings)."""
    if not roots:
        return {}
    rows = conn.execute("""SELECT DISTINCT ON (o.root_accession, extract(year FROM d.filing_date))
                                  extract(year FROM d.filing_date)::int AS year, d.amount_sold
                           FROM sec_formd_offerings o JOIN sec_formd d ON d.cik = o.cik
                           WHERE o.root_accession = ANY(%s) AND d.filing_date >= o.first_date AND d.amount_sold IS NOT NULL
                           ORDER BY o.root_accession, extract(year FROM d.filing_date), d.filing_date DESC""",
                        (roots,)).fetchall()
    out: dict[int, float] = {}
    for r in rows:
        out[r["year"]] = out.get(r["year"], 0) + float(r["amount_sold"])
    return out


def chart(years: list[dict], raised: dict[int, float], w: int = 640, h: int = 150) -> dict | None:
    """Bars for gross asset value and for investors, one per year, with the Form D amount sold (to date) as dots on
    the value chart. Coordinates for templates/_adv_fund.html."""
    if not years:
        return None
    first, last = years[0]["year"], years[-1]["year"]
    if raised:
        first, last = min(first, min(raised)), max(last, max(raised))
    span = list(range(first, last + 1))
    by = {r["year"]: r for r in years}
    slot = (w - 16) / len(span)
    top_v = max([float(r["gav"] or 0) for r in years] + [v for v in raised.values()] + [1])
    top_n = max([int(r["owners"] or 0) for r in years] + [1])

    def bars(get, top):
        out = []
        for i, y in enumerate(span):
            v = get(y)
            if v is None:
                continue
            bh = max((h - 30) * v / top, 1 if v else 0)
            out.append({"x": round(8 + i * slot + slot * 0.15, 1), "w": round(slot * 0.7, 1),
                        "y": round(h - 20 - bh, 1), "h": round(bh, 1), "year": y, "v": v})
        return out
    value = bars(lambda y: float(by[y]["gav"]) if y in by and by[y]["gav"] is not None else None, top_v)
    owners = bars(lambda y: int(by[y]["owners"]) if y in by and by[y]["owners"] is not None else None, top_n)
    dots = [{"cx": round(8 + span.index(y) * slot + slot / 2, 1), "cy": round(h - 20 - (h - 30) * v / top_v, 1),
             "year": y, "v": v} for y, v in sorted(raised.items())]
    labels = [{"x": round(8 + i * slot + slot / 2, 1), "year": y} for i, y in enumerate(span)
              if len(span) <= 14 or i % 2 == 0 or y == last]
    return {"w": w, "h": h, "value": value, "owners": owners, "dots": dots, "labels": labels,
            "top_v": top_v, "top_n": top_n}


def fund(fund_id: str) -> dict | None:
    with db.conn() as conn:
        years = _years(conn, fund_id)
        if not years:
            return None
        latest = years[-1]
        adviser = conn.execute("""SELECT * FROM adv_filings WHERE crd = %s
                                  ORDER BY submitted DESC NULLS LAST LIMIT 1""", (latest["crd"],)).fetchone()
        offerings = conn.execute("""SELECT o.* FROM adv_fund_links l JOIN sec_formd_offerings o USING (root_accession)
                                    WHERE l.fund_id = %s ORDER BY o.first_date""", (fund_id,)).fetchall()
        raised = _raised(conn, [o["root_accession"] for o in offerings])
        people = conn.execute("""SELECT o.name, o.title, o.entity_kind, o.control_person, o.ownership_code, l.cluster_id
                                 FROM adv_owners o LEFT JOIN adv_person_links l ON l.crd = o.crd AND l.name_norm = o.name_norm
                                 WHERE o.crd = %s AND o.year = (SELECT max(year) FROM adv_owners WHERE crd = %s)
                                 ORDER BY o.control_person DESC, o.name LIMIT 60""",
                              (latest["crd"], latest["crd"])).fetchall()
    return {"fund_id": fund_id, "years": years, "latest": latest, "adviser": adviser, "offerings": offerings,
            "people": people, "chart": chart(years, raised), "raised": raised}


def for_formd(cik: str | None) -> list[dict]:
    """ADV funds linked to this issuer's Form D offerings, with their yearly chart (Form D pages)."""
    if not PUBLIC or not cik:
        return []
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '3s'")
            links = conn.execute("""SELECT DISTINCT l.fund_id, o.root_accession FROM sec_formd_offerings o
                                    JOIN adv_fund_links l USING (root_accession) WHERE o.cik = %s""", (cik,)).fetchall()
            out = []
            for fid in sorted({l["fund_id"] for l in links})[:3]:
                years = _years(conn, fid)
                if not years:
                    continue
                raised = _raised(conn, [l["root_accession"] for l in links if l["fund_id"] == fid])
                adviser = conn.execute("""SELECT crd, legal_name, business_name FROM adv_filings WHERE crd = %s
                                          ORDER BY submitted DESC NULLS LAST LIMIT 1""", (years[-1]["crd"],)).fetchone()
                out.append({"fund_id": fid, "years": years, "latest": years[-1], "adviser": adviser,
                            "chart": chart(years, raised), "raised": raised})
            return out
    except Exception:  # noqa: BLE001
        log.exception("adv for_formd %s", cik)
        return []


def person(cluster_id: int) -> list[dict]:
    """Advisers this person is listed on as an owner, officer or control person (linked by name and state)."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '2s'")
            return conn.execute("""
                SELECT l.crd, min(o.year) AS first, max(o.year) AS last, bool_or(o.control_person) AS control,
                       (array_agg(o.title ORDER BY o.year DESC))[1] AS title,
                       (SELECT coalesce(f.business_name, f.legal_name) FROM adv_filings f WHERE f.crd = l.crd
                        ORDER BY f.submitted DESC NULLS LAST LIMIT 1) AS adviser,
                       (SELECT count(DISTINCT a.fund_id) FROM adv_funds a WHERE a.crd = l.crd) AS funds
                FROM adv_person_links l JOIN adv_owners o ON o.crd = l.crd AND o.name_norm = l.name_norm
                WHERE l.cluster_id = %s GROUP BY l.crd ORDER BY max(o.year) DESC LIMIT 30""",
                                (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


@router.get("/corporate/fund/{fund_id}", response_class=HTMLResponse)
def fund_page(request: Request, fund_id: str):
    from app.corporate import _render
    if not PUBLIC or not re.fullmatch(r"805-\d{6,12}", fund_id):
        raise HTTPException(404)
    data = fund(fund_id)
    if not data:
        raise HTTPException(404)
    return _render(request, "adv_fund.html", note=NOTE, iapd=iapd, **data)
