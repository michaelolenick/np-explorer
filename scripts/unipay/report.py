"""Task 2/3/4: write docs/university-pay-ingest-report.md from the loaded staging tables (read-only queries)."""
import datetime as dt
import json
import re

from common import REPO, connect, load_progress
import parsers

SKIPPED = [
    ("RI", "transparency.ri.gov payroll CSV (A)", "robots.txt has `User-agent: * / Disallow: /`; honored, not downloaded."),
    ("FL", "Board of Governors SUS payroll APEX export (A)", "robots.txt on prod.flbog.net disallows all agents; export is also session-bound."),
    ("FL", "Florida College System salaries (B)", "Export only through a JS search UI with an undocumented API."),
    ("IA", "Iowa Data Hub state salary book (A)", "Re-checked Oct 2026: Next.js page with a client-side download button only; no static or GET data URL in the HTML."),
    ("NV", "Transparent Nevada NSHE CSVs (A)", "Re-checked Oct 2026: download is a JS button; GET of the CSV name redirects to an HTML page."),
    ("UT", "Transparent Utah compensation downloader (A)", "Bulk files come from an undocumented Cloud Run query service used by the JS app; not attempted."),
    ("WA", "LEAP / fiscal.wa.gov state employee salaries (B)", "Only newer official WA person-level data. Web view is a Power BI embed (queries are POSTs to Power BI); bulk file needs an email request. Not attempted (no forms/emails). data.wa.gov has nothing after 2013."),
    ("TX", "Full-name Texas university salaries", "texascollegesalaries.com is behind a Cloudflare JS challenge; Texas Tribune explorer (now only the 116 Comptroller agencies, no universities) has no higher-ed rows. No plain-GET full-name source found."),
    ("OK", "Full-name Oklahoma payroll", "data.ok.gov payroll files 2010-2026 all publish last name + initials; OpenTheBooks is anti-bot; Oklahoma Watch site no longer resolves."),
    ("MO", "data.mo.gov state payroll (A)", "Does not cover colleges or universities."),
    ("NJ", "NJ centralized payroll iqwc-r2w7 (A)", "Does not cover institutions."),
    ("MA", "CTHRU quasi-public payroll tc5d-8ckm (A)", "Peripheral (quasi-public agencies, not institutions)."),
    ("CT", "CT payroll FY2010-2014 ajs4-6pgz (A)", "Covered by 9m78-yc88, which starts in FY2010."),
    ("OH", "Ohio State salary snapshots (A)", "Downloaded but not loaded: same people as the earnings files; rate, not pay. Kept on disk."),
    ("PA", "PennWatch PASSHE / Thaddeus Stevens salaries (B)", "Re-checked Oct 2026: GET with agency/date parameters returns 'No Data Found'; results need a POST with an anti-forgery token. Not submitted."),
    ("PA", "Penn State top-200 PDF (B)", "Cloudflare challenge; skipped."),
    ("IL", "IBHE public university salary search (B)", "Excel export is an ASP.NET postback (form submission); not attempted."),
    ("IL", "Illinois State FY2023 / FY2025+ PDFs (B)", "FY2023 layout not reliably extractable; FY2025+ behind a Cloudflare challenge."),
    ("IL", "University of Illinois FY26 Salary Book PDF (B)", "Redundant: Gray Book 2026-27 (loaded) carries present FY2026 salary; UI gross pay comes from il_stl."),
    ("IN", "Indiana Gateway higher-ed salaries (B)", "Per-unit report export after accepting a non-commercial-use agreement; not attempted (agreement needs owner review)."),
    ("ID", "Transparent Idaho (B)", "JS single-page app; no plain-HTTP data endpoint."),
    ("MO", "UM System 2024-25 salary PDF (B)", "Downloaded; ligatures and fused columns make extraction unreliable; 2025-26 loaded instead."),
    ("MI", "Western Michigan employee list PDF (B)", "No employee names (position, FTE, salary only); not person-level."),
    ("CO", "University of Colorado personnel roster PDF (B)", "No employee names (anonymized roster IDs)."),
    ("DC", "UDC quarterly listings FY2016, FY2019, Dec 2013 (B)", "No table rules in those PDFs (multi-word names cannot be split reliably) / no agency column; other years loaded."),
    ("AR", "ADHE administrator compensation FY10-FY25 (B)", "Same layout as FY26 (loaded); not fetched in this pass (about 20 min of PDF parsing per year on the dev box)."),
]

COVERAGE_NOTES = [
    "CT: the 12 community colleges merged into Connecticut State Community College in July 2023 and their payroll moved into the "
    "'Connecticut Board of Regents' agency during FY2024, so FY2025+ shows 9 institutions (CT State campus kept in pay_components.campus). "
    "FY2010-2014 campuses are recovered from deptid digits (system agencies 'CT Community Colleges' / 'Connecticut State Universities'); "
    "Charter Oak's pre-2014 agency 'Board for Academic Awards' was added. FY2027 is a partial year (pay_components.partial_year_through).",
    "MN: institution is now the Minnesota State campus from the MMB location name (department-number majority when blank); "
    "rows with no resolvable location keep 'Minnesota State Colleges and Universities'.",
    "IL ICCB: from FY2025 the four Illinois Eastern colleges report as one district (Illinois Eastern Community Colleges), so the label count drops from 50 to 46.",
    "NYC: FY2017 includes about 9,300 'CEASED' employees (about 1,600 in other years) as published, which inflates that year's rows and lowers its median.",
    "AZ ASU: from 2022 the State Press file includes part-time/student employees (12k -> 20k rows).",
    "GA: 93,807 exact duplicate rows as published (identical org/name/title/salary/year); kept.",
    "TX: rows with data_date before Sep 2025 fall into FY2025 (2 institutions); the rest are FY2026 snapshots.",
    "MD: Diamondback year labels checked against known tenure dates and treated as fiscal years (see parsers.parse_md); the first pass's concern came from settlement payouts to departed coaches.",
    "il_stl vs il_graybook: same University of Illinois people; il_stl is actual 2025 gross pay, il_graybook is budgeted FY2026/27 salary.",
    "mo_stl vs mo_um: same University of Missouri people; mo_stl is 2025 gross pay (newsroom), mo_um is the official FY2026 salary rate + W-2.",
]


def q(cur, sql, args=None):
    cur.execute(sql, args or ())
    return cur.fetchall()


def money(x):
    return "" if x is None else f"${float(x):,.0f}"


def mdcell(s, n=60):
    s = "" if s is None else re.sub(r"\s+", " ", str(s)).replace("|", "/")
    return s[:n]


def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SET statement_timeout='20min'")
    prog = load_progress()
    out = [f"# University pay ingest report", "",
           f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} (America/Chicago) by `scripts/unipay/report.py`. Staging data only "
           "(schema `unipay`); nothing here is on the site.", ""]

    srcs = q(cur, """SELECT s.source_key, min(s.state), min(s.institution_or_system), count(*) AS files, sum(s.bytes),
                     min(s.catalog_source_id), string_agg(DISTINCT s.notes, ' ')
                     FROM unipay.public_payroll_sources s GROUP BY 1 ORDER BY 1""")
    keyinfo = {r[0]: r for r in srcs}
    order = [k for k in parsers.ORDER if k in keyinfo]

    # ---------------------------------------------------------------- overview
    stats = {}
    for k in order:
        r = q(cur, """SELECT count(*), count(DISTINCT r.institution),
              count(*) FILTER (WHERE r.base_pay IS NOT NULL OR r.total_pay IS NOT NULL OR r.other_pay IS NOT NULL),
              count(*) FILTER (WHERE coalesce(btrim(r.person_name),'') = ''),
              count(*) FILTER (WHERE r.base_pay IS NULL AND r.total_pay IS NULL AND r.other_pay IS NULL),
              count(*) FILTER (WHERE greatest(r.base_pay, r.total_pay, r.other_pay) > 10000000),
              count(*) FILTER (WHERE least(r.base_pay, r.total_pay) < 0),
              count(*) - count(DISTINCT md5(r.source_id::text || '|' || coalesce(r.fiscal_year::text,'') || '|' || r.raw::text)),
              min(r.fiscal_year), max(r.fiscal_year),
              count(DISTINCT (r.institution, r.name_norm))
              FROM unipay.public_payroll_records r JOIN unipay.public_payroll_sources s ON s.id=r.source_id
              WHERE s.source_key=%s""", (k,))[0]
        stats[k] = r
    total_rows = sum(s[0] for s in stats.values())
    insts = q(cur, "SELECT count(DISTINCT (state, institution)) FROM unipay.public_payroll_records")[0][0]
    out += ["## Summary", "",
            f"- Sources loaded: **{len(order)}** (from {len(set(keyinfo[k][1] for k in order))} states/DC)",
            f"- Records loaded: **{total_rows:,}** into `unipay.public_payroll_records`",
            f"- Institutions (distinct state + institution labels): **{insts:,}**", "",
            "| Key | State | Source | Files | Rows | Years | Institutions | Distinct people (inst+name) | Catalog id |",
            "|---|---|---|---|---|---|---|---|---|"]
    for k in order:
        ki, s = keyinfo[k], stats[k]
        out.append(f"| {k} | {ki[1]} | {mdcell(ki[2], 70)} | {ki[3]} | {s[0]:,} | {s[8]}-{s[9]} | {s[1]:,} | {s[10]:,} | {ki[5] or ''} |")
    out.append("")

    # ---------------------------------------------------------------- skipped
    out += ["## Skipped or deferred sources", "", "| State | Source | Why |", "|---|---|---|"]
    for st, src, why in SKIPPED:
        out.append(f"| {st} | {src} | {why} |")
    for k, v in sorted(prog.get("sources", {}).items()):
        if v.get("status") not in ("loaded",):
            out.append(f"| {k} | load step | {v.get('status')}: {mdcell(v.get('error') or v.get('reason'), 200)} |")
    out.append("")

    out += ["## Coverage notes", ""] + [f"- {n}" for n in COVERAGE_NOTES] + [""]

    # ---------------------------------------------------------------- per source detail
    out += ["## Per-source quality checks", "",
            "Checks: rows per fiscal year; rows with any pay value; exact duplicates (identical original row within the same file and fiscal year); "
            "possible parse errors (empty name, no numeric pay, pay over $10,000,000, negative pay); 20 random sample rows.", ""]
    for k in order:
        ki, s = keyinfo[k], stats[k]
        out += [f"### {k}: {ki[2]} ({ki[1]})", "", f"Notes: {ki[6] or ''}", "",
                f"- Rows: {s[0]:,}; with a pay value: {s[2]:,} ({(100.0 * s[2] / s[0]) if s[0] else 0:.1f}%)",
                f"- Exact duplicate rows (same original row): {s[7]:,}",
                f"- Empty name: {s[3]:,}; no numeric pay: {s[4]:,}; pay > $10M: {s[5]:,}; negative pay: {s[6]:,}", ""]
        fy = q(cur, """SELECT r.fiscal_year, count(*), count(DISTINCT r.institution), round(avg(coalesce(r.total_pay, r.base_pay))),
                       percentile_disc(0.5) WITHIN GROUP (ORDER BY coalesce(r.total_pay, r.base_pay))
                       FROM unipay.public_payroll_records r JOIN unipay.public_payroll_sources s ON s.id=r.source_id
                       WHERE s.source_key=%s GROUP BY 1 ORDER BY 1""", (k,))
        out += ["| Fiscal year | Rows | Institutions | Mean pay | Median pay |", "|---|---|---|---|---|"]
        out += [f"| {a} | {b:,} | {c} | {money(d)} | {money(e)} |" for a, b, c, d, e in fy]
        out.append("")
        n = s[0] or 1
        samp = q(cur, """SELECT r.institution, r.person_name, r.title, r.department, r.base_pay, r.other_pay, r.total_pay, r.fiscal_year
                         FROM unipay.public_payroll_records r JOIN unipay.public_payroll_sources s ON s.id=r.source_id
                         WHERE s.source_key=%s AND random() < %s LIMIT 20""", (k, min(1.0, 60.0 / n)))
        out += ["<details><summary>20 random rows</summary>", "",
                "| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |", "|---|---|---|---|---|---|---|---|"]
        out += [f"| {mdcell(a,40)} | {mdcell(b,35)} | {mdcell(c,40)} | {mdcell(d,35)} | {money(e)} | {money(f)} | {money(g)} | {h} |"
                for a, b, c, d, e, f, g, h in samp]
        out += ["", "</details>", ""]
    conn.commit()
    (REPO / "docs/university-pay-ingest-report.md").write_text("\n".join(out) + "\n")
    json.dump({"order": order, "total_rows": total_rows, "institutions": insts,
               "stats": {k: list(map(lambda x: x if not hasattr(x, "isoformat") else str(x), v)) for k, v in stats.items()}},
              open(REPO / "data/unipay-report-stats.json", "w"), indent=1, default=str)
    print("report written:", total_rows, "rows")


if __name__ == "__main__":
    main()
