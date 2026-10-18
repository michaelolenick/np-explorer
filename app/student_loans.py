"""Student loan asset-backed securities (SLABS): trust, issuer and index pages.

Data: student_loan_trusts, student_loan_trust_months, student_loan_parties and
student_loan_trust_stats, built by loader/student_loans.py from the monthly servicing
reports trusts file with the SEC on Form 10-D. Routes live on `router`, which app/main.py
includes. Facts only: every measure is the issuer's own figure, NULL (shown "Not
reported") where the issuer doesn't report it, and each issuer family's definitions are
shown beside its numbers because families define defaults and delinquency differently.
"""

from __future__ import annotations

import re
import sys
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db
from app.cache import ttl_lru

router = APIRouter()


def last_update() -> dict:
    """{last_ok: when the last successful refresh finished, failed: the latest run if it failed after that,
    data_through: the latest reporting month loaded}. Never raises (pages must render)."""
    from app import db
    out = {"last_ok": None, "failed": None, "data_through": None}
    try:
        with db.conn() as conn:
            r = conn.execute("SELECT max(finished_at) AS t FROM student_loan_runs WHERE ok").fetchone()
            out["last_ok"] = r["t"] if r else None
            f = conn.execute("""SELECT started_at, message FROM student_loan_runs
                                WHERE ok IS false AND started_at > coalesce(%s, '-infinity'::timestamptz)
                                ORDER BY started_at DESC LIMIT 1""", (out["last_ok"],)).fetchone()
            out["failed"] = f
            if not out["last_ok"]:      # before the first scheduled run: when the data was loaded
                r = conn.execute("SELECT max(retrieved_at) AS t FROM student_loan_trust_months").fetchone()
                out["last_ok"] = r["t"] if r else None
            r = conn.execute("SELECT max(period) AS p FROM student_loan_trust_months").fetchone()
            out["data_through"] = r["p"] if r else None
    except Exception:  # noqa: BLE001 - tables missing: say nothing rather than fail the page
        pass
    return out

# Issuer families: one report template, one set of definitions. The loader's parser for
# each family is in loader/sla_parse.py; the words here are what pages show.
FAMILIES: dict[str, dict] = {
    "slm": {
        "name": "SLM / Navient (Sallie Mae)",
        "program": "FFELP and private",
        "delinquency": "Principal of loans in repayment that are 31-60, 61-90, 91-120 and more than 120 days past "
                       "due, as listed in section III of the monthly servicing report (Portfolio Characteristics). "
                       "Private credit trusts add longer buckets.",
        "defaults": "FFELP trusts: Guarantor Principal received in the collection period, the principal the "
                    "guaranty agency paid on defaulted loans (claims paid). Private credit trusts: gross defaults "
                    "as reported.",
        "charge_offs": "FFELP trusts: Non-Reimbursable Losses, the share of claims the guarantor and the federal "
                       "government do not cover (risk sharing, usually 2-3% of a claim). Private trusts: loans "
                       "charged off as reported.",
        "recoveries": "Reported by private credit trusts only. FFELP trusts are paid by the guarantor, so the "
                      "report has no recoveries line.",
        "prepayment": "Since-issued constant prepayment rate (CPR), annualized, as reported.",
    },
    "ncslt": {
        "name": "National Collegiate (First Marblehead)",
        "program": "private",
        "delinquency": "Principal of loans in repayment 31-60, 61-90, 91-120, 121-150, 151-180 and more than 180 days "
                       "past due, from section VI of the Monthly Distribution Report (Portfolio Characteristics by "
                       "Payment Status). 121 days and over are summed into the 120+ column.",
        "defaults": "The month's change in cumulative net claims filed with TERI (The Education Resources "
                    "Institute, the private guarantor), from section VIII. TERI filed for bankruptcy on April 7, "
                    "2008, after which claims went largely unpaid.",
        "charge_offs": "Realized principal losses in the month (section II.B).",
        "recoveries": "The month's change in cumulative liquidation proceeds and recoveries (section VIII.F).",
        "prepayment": "Prepayment rate as reported, updated twice a year (January and July reports).",
    },
}
FAMILIES["nelnet"] = {
    "name": "Nelnet", "program": "FFELP",
    "delinquency": "Principal of loans in repayment 31-60 through more than 300 days past due, from the quarterly "
                   "report's distribution by number of days delinquent. Nelnet calls current loans \"0-30 days "
                   "delinquent\"; they count as current here.",
    "defaults": "Defaults paid this quarter: principal and interest the guarantors paid on defaulted FFELP loans.",
    "charge_offs": "Principal realized losses, claim write-offs: amounts the federal guarantee did not reimburse.",
    "recoveries": "Not reported: FFELP claims are paid by the guarantor.",
    "prepayment": "The latest quarter's constant prepayment rate (CPR), as reported.",
}
FAMILIES["slc"] = {**FAMILIES["slm"], "name": "SLC Student Loan Trusts (Student Loan Corp)", "program": "FFELP",
                   "recoveries": "Not reported: FFELP trusts are paid by the guarantor, so the report has no "
                                 "recoveries line."}
FAMILIES["slm"]["recoveries"] = ("Private credit trusts report recoveries on realized losses. FFELP trusts are paid "
                                 "by the guarantor, so their reports have no recoveries line (Not reported).")
# Families found on EDGAR whose reports aren't parsed yet (names for the coverage table).
UNPARSED = {"keycorp": "KeyCorp Student Loan Trusts", "collegeloan": "College Loan Corp Trusts",
            "goal": "Goal Capital Funding Trusts", "edlinc": "Education Loans Inc (EdLinc, South Dakota)",
            "gco": "GCO Education Loan Funding Trust", "efc": "Education Funding Capital Trusts",
            "cfs": "Collegiate Funding Services Education Loan Trusts", "pheaa": "PHEAA Student Loan Trust I",
            "chase": "Chase Education Loan Trust", "pnc": "PNC Student Loan Trust I", "hef": "Higher Education Funding I",
            "wachovia": "Wachovia Student Loan Trust", "smb": "SMB Private Education Loan Trusts",
            "access": "Access Group", "other": "Other student loan trusts"}
DEFAULT_FAMILY = {"name": "Other", "program": None, "delinquency": "As reported.", "defaults": "As reported.",
                  "charge_offs": "As reported.", "recoveries": "As reported.", "prepayment": "As reported."}

RATE_DEFINITIONS = [
    ("Pool balance", "Principal (plus interest to be capitalized, where the issuer includes it) of the loans the "
                     "trust held at the end of the collection period, as the issuer reports it."),
    ("Delinquency rate", "Every delinquent bucket the issuer reports (usually 31 days past due and over), summed, "
                         "divided by the principal in repayment (current plus delinquent). Loans in school, grace, "
                         "deferment, forbearance and FFELP claims in process are not in repayment. Where an issuer "
                         "doesn't break out loans in repayment the page says so and divides by the pool balance."),
    ("Default rate (12 months)", "Defaults reported over the latest 12 monthly reports, divided by the average pool "
                                 "balance over those months. What counts as a default differs by issuer family "
                                 "(see each family's definitions); FFELP defaults are mostly repaid by the "
                                 "guarantor, so they are not losses to the trust."),
    ("Charge-off rate (12 months)", "Charge-offs over the latest 12 monthly reports, divided by the average pool "
                                    "balance. For FFELP trusts this is the uninsured share of claims."),
    ("12-month change", "The latest delinquency rate minus the rate in the report for the same month a year "
                        "earlier, in percentage points (none when that report is missing)."),
]

FIELDS = [  # (column, label, kind) for the monthly table and CSV
    ("pool_balance", "Pool balance", "money"), ("loan_count", "Loans", "num"),
    ("delinq_rate", "Delinquency rate", "pct"),
    ("delinq_30_59", "30-59 days", "money"), ("delinq_60_89", "60-89 days", "money"),
    ("delinq_90_119", "90-119 days", "money"), ("delinq_120_plus", "120+ days", "money"),
    ("forbearance", "Forbearance", "money"), ("deferment", "Deferment", "money"),
    ("claims_in_process", "Claims in process", "money"),
    ("defaults", "Defaults", "money"), ("charge_offs", "Charge-offs", "money"),
    ("recoveries", "Recoveries", "money"), ("prepayment_rate", "CPR", "pct"),
]


PROGRAMS = {"FFELP": "FFELP (federally guaranteed)", "private": "Private", "refi": "Refinance",
            "mixed": "FFELP and private"}


def program(code: str | None) -> str:
    return PROGRAMS.get(code or "", code or "Not reported")


def family(slug: str | None) -> dict:
    if slug in FAMILIES:
        return FAMILIES[slug]
    return {**DEFAULT_FAMILY, "name": UNPARSED.get(slug or "", slug or "Other"), "unparsed": True}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:80]


def fmt(v, kind: str) -> str:
    """Display a measure. None is always "Not reported": the issuer didn't state it."""
    if v is None:
        return "Not reported"
    if kind == "money":
        v = round(float(v))
        return f"-${-v:,}" if v < 0 else f"${v:,}"
    if kind == "num":
        return f"{int(v):,}"
    if kind == "pct":
        return f"{float(v):.2f}%"
    if kind == "pp":
        return f"{float(v):+.2f} pts"
    return str(v)


def delinq_rate(m: dict) -> tuple[float | None, str | None]:
    """(rate %, basis) for one month: delinquent / in repayment, else delinquent / pool."""
    d = m.get("delinq_total")
    if d is None:
        return None, None
    if m.get("current_balance") is not None:
        rep = float(m["current_balance"]) + float(d)
        return (100.0 * float(d) / rep if rep else None), "repayment"
    if m.get("pool_balance"):
        return 100.0 * float(d) / float(m["pool_balance"]), "pool"
    return None, None


# --- queries --------------------------------------------------------------------------------

def _rows(sql: str, params=()) -> list[dict]:
    with db.conn() as conn:
        return conn.execute(sql, params).fetchall()


@ttl_lru()
def overview() -> dict:
    try:
        fams = _rows("""SELECT t.family, count(*) AS trusts, sum(t.months_parsed) AS months,
                               sum(t.months_failed) AS failed, min(s.first_period) AS first, max(s.last_period) AS last,
                               sum(s.pool_balance) FILTER (WHERE s.last_period >= (SELECT max(last_period) FROM student_loan_trust_stats) - interval '3 months') AS live_balance
                        FROM student_loan_trusts t LEFT JOIN student_loan_trust_stats s USING (cik)
                        GROUP BY t.family ORDER BY count(*) DESC""")
        issuers = _rows("""SELECT p.slug, p.party, p.roles, p.ein, p.match, p.state, p.abs15g, count(DISTINCT t.cik) AS trusts
                           FROM student_loan_parties p
                           LEFT JOIN student_loan_trusts t ON p.party IN (t.sponsor, t.depositor, t.servicer, t.administrator, t.trustee)
                           GROUP BY p.slug, p.party, p.roles, p.ein, p.match, p.state, p.abs15g
                           ORDER BY p.ein IS NULL, count(DISTINCT t.cik) DESC, p.party""")
        trusts = _rows("""SELECT t.cik, t.name, t.family, t.program_type, s.months, s.first_period, s.last_period,
                                 s.pool_balance, s.delinq_rate, s.default_rate_12
                          FROM student_loan_trusts t LEFT JOIN student_loan_trust_stats s USING (cik)
                          ORDER BY t.family, t.name""")
    except Exception:  # noqa: BLE001 - tables not built yet
        return {"families": [], "issuers": [], "trusts": []}
    return {"families": fams, "issuers": issuers, "trusts": trusts}


@ttl_lru()
def trust(cik: int) -> dict | None:
    rows = _rows("SELECT * FROM student_loan_trusts WHERE cik = %s", (cik,))
    if not rows:
        return None
    t = rows[0]
    months = _rows("SELECT * FROM student_loan_trust_months WHERE cik = %s ORDER BY period", (cik,))
    stats = (_rows("SELECT * FROM student_loan_trust_stats WHERE cik = %s", (cik,)) or [None])[0]
    for m in months:
        m["delinq_rate"], m["delinq_basis"] = delinq_rate(m)
    parties = _rows("""SELECT * FROM student_loan_parties WHERE party = ANY(%s) ORDER BY party""",
                    ([x for x in (t["sponsor"], t["depositor"], t["servicer"], t["administrator"], t["trustee"]) if x],))
    return {"trust": t, "months": months, "stats": stats, "gaps": gaps(months), "parties": parties,
            "fam": family(t["family"])}


@ttl_lru()
def issuer(slug: str) -> dict | None:
    rows = _rows("SELECT * FROM student_loan_parties WHERE slug = %s", (slug,))
    if not rows:
        return None
    p = rows[0]
    trusts = _rows("""SELECT t.*, s.pool_balance AS latest_balance, s.last_period, s.first_period, s.months,
                             s.delinq_rate, s.default_rate_12, s.chargeoff_rate_12,
                             array_remove(ARRAY[CASE WHEN t.sponsor = %(p)s THEN 'sponsor' END,
                                                CASE WHEN t.depositor = %(p)s THEN 'depositor' END,
                                                CASE WHEN t.servicer = %(p)s THEN 'servicer' END,
                                                CASE WHEN t.administrator = %(p)s THEN 'administrator' END,
                                                CASE WHEN t.trustee = %(p)s THEN 'trustee' END], NULL) AS roles
                      FROM student_loan_trusts t LEFT JOIN student_loan_trust_stats s USING (cik)
                      WHERE %(p)s IN (t.sponsor, t.depositor, t.servicer, t.administrator, t.trustee)
                      ORDER BY t.closing_date NULLS LAST, t.name""", {"p": p["party"]})
    latest = max((t["last_period"] for t in trusts if t["last_period"]), default=None)
    live = [t for t in trusts if t["last_period"] and latest and (latest - t["last_period"]).days <= 92]
    org = None
    if p["ein"]:
        org = (_rows("SELECT ein, name, city, state, ntee FROM organizations WHERE ein = %s", (p["ein"],)) or [None])[0]
    combined = _rows("""SELECT m.period, sum(m.pool_balance) AS balance, count(*) AS trusts
                        FROM student_loan_trust_months m JOIN student_loan_trusts t USING (cik)
                        WHERE %(p)s IN (t.sponsor, t.depositor, t.servicer, t.administrator, t.trustee)
                        GROUP BY m.period ORDER BY m.period""", {"p": p["party"]})
    return {"party": p, "trusts": trusts, "latest": latest, "live": live, "org": org,
            "combined_balance": sum(float(t["latest_balance"] or 0) for t in live) if live else None,
            "combined": combined}


def gaps(months: list[dict]) -> list[str]:
    """Calendar months between the first and last report that no report covers, as 'YYYY-MM'.
    A quarterly report covers its month and the two before it (period_months)."""
    def back(d: date, k: int) -> date:
        n = d.year * 12 + d.month - 1 - k
        return date(n // 12, n % 12 + 1, 1)
    covered = set()
    for m in months:
        for k in range(int(m.get("period_months") or 1)):
            covered.add(back(m["period"], k))
    if not months:
        return []
    first, last = min(m["period"] for m in months), max(m["period"] for m in months)
    out, d = [], first
    while d < last:
        d = back(d, -1)
        if d not in covered:
            out.append(d.strftime("%Y-%m"))
    return out


# --- charts ---------------------------------------------------------------------------------

def spark(points: list[tuple[date, float | None]], width: int = 640, height: int = 140, pct: bool = False) -> dict | None:
    """An inline SVG line chart's geometry: a polyline per run of reported months (gaps break the line)."""
    pts = [(d, float(v)) for d, v in points if v is not None]
    if len(pts) < 2:
        return None
    x0, x1 = pts[0][0].toordinal(), pts[-1][0].toordinal()
    vmin, hi = min(v for _, v in pts), max(v for _, v in pts)
    lo = min(vmin, 0.0)            # the axis starts at zero
    span_x, span_y = max(1, x1 - x0), (hi - lo) or 1.0
    pad = 8

    def xy(d, v):
        return (pad + (d.toordinal() - x0) / span_x * (width - 2 * pad),
                height - pad - (v - lo) / span_y * (height - 2 * pad))

    runs, cur, prev = [], [], None
    for d, v in points:
        if v is None:
            if cur:
                runs.append(cur)
            cur = []
            continue
        if prev and (d.year * 12 + d.month) - (prev.year * 12 + prev.month) > 1 and cur:
            runs.append(cur)
            cur = []
        x, y = xy(d, float(v))
        cur.append(f"{x:.1f},{y:.1f}")
        prev = d
    if cur:
        runs.append(cur)
    return {"w": width, "h": height, "lines": [" ".join(r) for r in runs if len(r) > 1],
            "dots": [r[0] for r in runs if len(r) == 1],
            "hi": hi, "lo": vmin, "first": pts[0][0], "last": pts[-1][0], "pct": pct}


# --- routes ---------------------------------------------------------------------------------

def _render(request: Request, name: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, name, sl=sys.modules[__name__], **ctx)


@router.get("/student-loans", response_class=HTMLResponse)
def index_page(request: Request):
    return _render(request, "student_loans.html", **overview(), rates=RATE_DEFINITIONS, families_def=FAMILIES)


@router.get("/student-loans/trust/{cik}", response_class=HTMLResponse)
def trust_page(request: Request, cik: int):
    data = trust(cik)
    if not data:
        raise HTTPException(404)
    ms = data["months"]
    charts = {
        "balance": spark([(m["period"], m["pool_balance"]) for m in ms]),
        "delinq": spark([(m["period"], m["delinq_rate"]) for m in ms], pct=True),
        "defaults": spark([(m["period"], (100.0 * float(m["defaults"]) / float(m["pool_balance"]) * 12)
                            if m["defaults"] is not None and m["pool_balance"] else None) for m in ms], pct=True),
    }
    return _render(request, "student_loan_trust.html", charts=charts, fields=FIELDS, **data)


@router.get("/student-loans/issuer/{slug}", response_class=HTMLResponse)
def issuer_page(request: Request, slug: str):
    data = issuer(slug)
    if not data:
        raise HTTPException(404)
    balance_chart = spark([(r["period"], r["balance"]) for r in data["combined"]])
    return _render(request, "student_loan_issuer.html", balance_chart=balance_chart, **data)
