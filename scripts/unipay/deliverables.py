"""Task 3 sample + Task 4 deliverables, appended to docs/university-pay-ingest-report.md (read-only queries)."""
import json
import re
import sys

from common import REPO, connect


def money(x):
    return "" if x is None else f"${float(x):,.0f}"


def cell(s, n=60):
    s = "" if s is None else re.sub(r"\s+", " ", str(s)).replace("|", "/")
    return s[:n]


# Quality grades for loaded sources (judgement, documented here): full names, real pay, history, titles.
QUALITY = {
    "ct": (5, "Official paycheck-level data aggregated per FY; full names, title, base/OT/other/gross; FY2010-2027"),
    "ma": (5, "Official; full names, title, base/OT/buyout/other/total actual pay; 2009-2026"),
    "ga": (4, "Official; full names, title, salary only (no split); FY2015-2025; foundation pay excluded"),
    "oh_osu": (5, "Official; calendar-year earnings with regular/bonus/OT/other/gross; department; 2021-2025"),
    "nyc": (5, "Official; full names, title, regular/OT/other paid; CUNY community colleges only"),
    "mn": (4, "Official; full names, title, department, FY earnings (all state positions); Minnesota State only"),
    "wa": (3, "Official; full names, title, annual salary; 2010-2013 only"),
    "il_iccb": (4, "Official; full names, title, base/extra duty/benefits; all 48 IL community colleges FY2016-2026"),
    "ks": (3, "Third-party compile of KORA records; full names, title, total pay; 2021-2025"),
    "az_asu": (3, "Student newspaper (public records); full names, title, department, base salary; 2018-2025"),
    "az_ua": (3, "Newsroom (public records); full names, title, department, salary/FTE; FY2019-2026"),
    "ne": (3, "Official budgeted salary (not paid); full names, title, campus, department; FY2017-2027"),
    "tx": (2, "Volunteer TPIA compile; bulk export has first name + last initial only; base salary snapshot"),
    "ok": (1, "Official but names are last name + initials, no title; monthly payment lines"),
    "nj": (2, "Official pension roll: salary only, no title, excludes ABP faculty; snapshot"),
    "me": (3, "Official base salary snapshot; full names, title; single year"),
    "nm": (3, "Official base salary snapshot; full names, title, department; single year"),
    "dc": (2, "Official rate snapshot (annual or hourly), no history"),
    "oh_ou": (3, "Official; base salary + W-2 wages; single year"),
    "il_graybook": (4, "Official budget book; full names, title, department, present/proposed salary; single year"),
    "sc": (3, "Official; full names, title, total comp (salary or YTD); omits < $50k; current FY only"),
    "md": (3, "Student newspaper (public records); full names, title, department, annual salary; 2013-2025"),
    "ne_cc": (2, "Newsroom compile; full names, title, total pay; 3 community colleges; one year (year often unstated)"),
    "mo_stl": (3, "Newsroom compile; full names, title, department, actual 2025 gross pay; MU campuses, MU Health, STLCC, SCC"),
    "il_stl": (3, "Newsroom compile; full names, title, department, actual 2025 gross pay; UIUC, UIC, UIS, SIUE"),
    "mo_um": (4, "Official PDF; full names, title, salary rate + W-2 wages; all UM campuses + MU Health; FY2026"),
    "mo_msu": (2, "Official budget PDF; budgeted salary per line, no titles; FY2027"),
    "il_isu": (2, "Official PDF; full names, title; pay units unstated (kept in components only); FY2024"),
    "vt_uvm": (4, "Official PDF; full names, title, base pay; FY2010-2026"),
    "nm_nmhu": (3, "Official PDF; full names, title, salary; FY2023-2026"),
    "tn_apsu": (3, "Official PDF; full names, title, salary; single year"),
    "tn_etsu": (3, "Official PDF; full names, title, salary; single year (2024)"),
    "mi_um": (4, "Official PDF; full names, title, annual FT rate, appointment fraction; all 3 campuses; FY2026"),
    "me_hist": (3, "Official PDFs; full names, title, base salary; FY2020-2022 snapshots"),
    "dc_hist": (2, "Official PDFs; UDC rows, rate snapshots; 7 fiscal years"),
    "ar_adhe": (2, "Official PDF; administrators >= $100k only; all AR public institutions; FY2026"),
    "pa_pitt": (1, "Top-200 non-officers only; name + gross, no title"),
    "pa_temple": (1, "Top-200 non-officers only"),
}


def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SET statement_timeout='30min'")
    out = []
    stats = json.load(open(REPO / "data/unipay-report-stats.json"))

    # ---------------------------------------------------------------- matching sample
    inst = sys.argv[1] if len(sys.argv) > 1 else "University of Connecticut"
    out += ["## 990 link candidates (sample)", "",
            "View `unipay.payroll_990_link_candidates` proposes links from payroll rows to `public.people` at 990 filers that are the "
            "institution itself (same normalized name and state) or an affiliated foundation (name contains the institution name and "
            "'foundation', same state); see `unipay.payroll_institution_990_orgs`. EXACT = same normalized name; FUZZY = trigram "
            "similarity >= 0.9 with the same last-name token. These are unreviewed candidates only.", ""]
    cur.execute("SELECT ein, org_name, org_relation FROM unipay.payroll_institution_990_orgs WHERE institution=%s ORDER BY 3,2", (inst,))
    orgs = cur.fetchall()
    out += [f"990 filers matched to **{inst}**: " + "; ".join(f"{n} ({e}, {r})" for e, n, r in orgs), ""]
    cur.execute("""SELECT match_type, count(*), count(DISTINCT name_norm), count(DISTINCT people_id)
                   FROM unipay.payroll_990_link_candidates WHERE institution=%s GROUP BY 1""", (inst,))
    out += ["| Match type | Candidate pairs | Distinct payroll names | Distinct 990 people rows |", "|---|---|---|---|"]
    out += [f"| {a} | {b:,} | {c:,} | {d:,} |" for a, b, c, d in cur.fetchall()]
    out.append("")
    cur.execute("""SELECT DISTINCT ON (name_norm, ein) match_type, round(name_similarity::numeric, 3), person_name, payroll_title, fiscal_year,
                          total_pay, base_pay, people_name, people_title, tax_year, comp_org, comp_related, org_name, org_relation
                   FROM unipay.payroll_990_link_candidates WHERE institution=%s
                   ORDER BY name_norm, ein, fiscal_year DESC, tax_year DESC LIMIT 400""", (inst,))
    rows = cur.fetchall()
    rows.sort(key=lambda r: -(float(r[10] or 0) + float(r[11] or 0)))
    out += [f"Sample query: `SELECT ... FROM unipay.payroll_990_link_candidates WHERE institution = '{inst}'` "
            "(one row per name and filer, latest year, top 25 by 990 compensation):", "",
            "| Type | Sim | Payroll name | Payroll title | FY | Payroll pay | 990 name | 990 title | Tax yr | 990 comp (org + related) | 990 filer |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows[:25]:
        out.append(f"| {r[0]} | {r[1]} | {cell(r[2],30)} | {cell(r[3],30)} | {r[4]} | {money(r[5] if r[5] is not None else r[6])} | "
                   f"{cell(r[7],30)} | {cell(r[8],30)} | {r[9]} | {money((r[10] or 0) + (r[11] or 0))} | {cell(r[12],40)} ({r[13]}) |")
    out += ["", "Reading this sample: UConn itself does not file a 990 (it is a state institution), so the only matched filer is the "
            "UConn Foundation. The EXACT hits above are mostly common names (e.g. a $500 instructional specialist named John Martin "
            "vs the foundation's former CEO); candidates need review of title, year and pay before any link is accepted.", ""]

    # ---------------------------------------------------------------- best sources next
    rank = []
    for k, s in stats["stats"].items():
        people_latest = None
        cur.execute("""SELECT max(r.fiscal_year) FROM unipay.public_payroll_records r JOIN unipay.public_payroll_sources s ON s.id=r.source_id
                       WHERE s.source_key=%s""", (k,))
        ly = cur.fetchone()[0]
        cur.execute("""SELECT count(DISTINCT (r.institution, r.name_norm)) FROM unipay.public_payroll_records r
                       JOIN unipay.public_payroll_sources s ON s.id=r.source_id WHERE s.source_key=%s AND r.fiscal_year=%s""", (k, ly))
        people_latest = cur.fetchone()[0]
        q, why = QUALITY.get(k, (3, ""))
        rank.append((people_latest * q, k, people_latest, ly, q, why, s[0]))
    rank.sort(reverse=True)
    out += ["## Deliverables", "", "### 15 best sources to integrate next", "",
            "Ranked by people covered in the latest loaded year x a 1-5 quality grade (official source, full names, actual pay with "
            "components, history). Texas and Oklahoma rank high on head count but their names are truncated (first name + last "
            "initial; last name + initials), so they are poor for matching to 990s. The ranking is in `scripts/unipay/deliverables.py`.", "",
            "| # | Source | People (latest yr) | Latest yr | Quality | Rows loaded | Why |", "|---|---|---|---|---|---|---|"]
    for i, (_, k, p, ly, q, why, n) in enumerate(rank[:15], 1):
        out.append(f"| {i} | {k} | {p:,} | {ly} | {q}/5 | {n:,} | {why} |")
    out += ["", "Not yet loaded but worth doing next (each needs an owner decision): Illinois IBHE salary search "
            "(all 12 public universities; ASP.NET postback export), Indiana Gateway (all public institutions; non-commercial-use "
            "agreement), Washington LEAP salary file (email request), Arkansas ADHE FY10-FY25 PDFs (same parser as FY26).", ""]

    # ---------------------------------------------------------------- gaps
    cur.execute("""
        WITH pub AS (
          SELECT a.state, sum(a.staff_count) AS ft_faculty
          FROM unipay.ipeds_faculty_salary_averages a WHERE a.arank = 7 AND a.control = 'Public' GROUP BY 1),
        loaded AS (SELECT state, count(*) AS n FROM unipay.public_payroll_records GROUP BY 1),
        best AS (SELECT state, state_name, best_rating, gaps FROM unipay.state_research)
        SELECT b.state, b.state_name, b.best_rating, coalesce(p.ft_faculty, 0), coalesce(l.n, 0), b.gaps
        FROM best b LEFT JOIN pub p USING (state) LEFT JOIN loaded l USING (state)
        ORDER BY (coalesce(l.n,0) = 0) DESC, (b.best_rating IN ('C','D')) DESC, coalesce(p.ft_faculty,0) DESC LIMIT 10""")
    gaps = cur.fetchall()
    out += ["### 10 states with the biggest gaps", "",
            "States with nothing loaded, weakest best-source rating first, then by size of public higher ed "
            "(IPEDS full-time instructional staff at public institutions, 2023-24).", "",
            "| State | Best rating | Public FT instructional staff (IPEDS) | Rows loaded | Gap (Phase 1 notes) |", "|---|---|---|---|---|"]
    for st, nm, br, ft, n, g in gaps:
        out.append(f"| {nm} ({st}) | {br} | {int(ft):,} | {n:,} | {cell(g, 220)} |")
    out.append("")

    # ---------------------------------------------------------------- counts
    cur.execute("SELECT rating, count(*) FROM unipay.university_pay_sources GROUP BY 1 ORDER BY 1")
    by_rating = cur.fetchall()
    cur.execute("SELECT count(*), count(DISTINCT state), count(DISTINCT (state, institution)) FROM unipay.public_payroll_records")
    nrec, nst, ninst = cur.fetchone()
    cur.execute("SELECT count(*) FROM unipay.state_research")
    nresearched = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM unipay.university_pay_sources WHERE loaded")
    nloaded_cat = cur.fetchone()[0]
    out += ["### Counts", "",
            f"- States researched (Phase 1): {nresearched} (50 states + DC)",
            f"- States with payroll records loaded: {nst}",
            f"- Catalog sources by rating: " + ", ".join(f"{r}: {n}" for r, n in by_rating),
            f"- Catalog sources marked loaded: {nloaded_cat}",
            f"- Records loaded: {nrec:,}",
            f"- Institutions covered (distinct state + institution labels): {ninst:,}", ""]
    try:
        cur.execute("SELECT count(*), count(DISTINCT unitid) FROM unipay.ipeds_faculty_salary_averages")
        a, b = cur.fetchone()
        out += [f"- IPEDS institution-average rows: {a:,} for {b:,} institutions (`unipay.ipeds_faculty_salary_averages`; "
                "AVERAGES by rank, not individual pay)", ""]
    except Exception:  # noqa: BLE001
        conn.rollback()

    # ---------------------------------------------------------------- well-known people
    cur.execute("""
        SELECT r.person_name, r.title, r.department, r.fiscal_year, r.base_pay, r.other_pay, r.total_pay, r.pay_components
        FROM unipay.public_payroll_records r JOIN unipay.public_payroll_sources s ON s.id = r.source_id
        WHERE s.source_key = 'oh_osu' AND r.fiscal_year = 2025
          AND (r.title ~* '(^president$|head coach|director of athletics|athletic director|provost|dean,? college of medicine|chief executive officer)')
        ORDER BY r.total_pay DESC NULLS LAST LIMIT 10""")
    ppl = cur.fetchall()
    out += ["### 10 well-known people at one large loaded system (The Ohio State University, calendar 2025 earnings)", "",
            "Selected by title (president, head coaches, athletic director, provost, medical leadership); pay as published.", "",
            "| Name (as published) | Title | Cost center | Year | Regular | Bonus + OT + other | Gross | Components |",
            "|---|---|---|---|---|---|---|---|"]
    for n, t, d, y, b, o, tot, pc in ppl:
        out.append(f"| {cell(n,30)} | {cell(t,40)} | {cell(d,45)} | {y} | {money(b)} | {money(o)} | {money(tot)} | `{cell(json.dumps(pc),160)}` |")
    out.append("")
    with open(REPO / "docs/university-pay-ingest-report.md", "a") as f:
        f.write("\n".join(out) + "\n")
    print("deliverables appended")


if __name__ == "__main__":
    main()
