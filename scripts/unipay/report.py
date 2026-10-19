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
    ("TX", "Full-name Texas university salaries", "texascollegesalaries.com is behind a Cloudflare JS challenge; Texas Tribune explorer (now only the 116 Comptroller agencies, no universities) has no higher-ed rows. No plain-GET full-name source found."),
    ("OK", "Full-name Oklahoma payroll", "data.ok.gov payroll files 2010-2026 all publish last name + initials; OpenTheBooks is anti-bot; Oklahoma Watch site no longer resolves."),
    ("MO", "data.mo.gov state payroll (A)", "Does not cover colleges or universities."),
    ("NJ", "NJ centralized payroll iqwc-r2w7 (A)", "Does not cover institutions."),
    ("MA", "CTHRU quasi-public payroll tc5d-8ckm (A)", "Peripheral (quasi-public agencies, not institutions)."),
    ("CT", "CT payroll FY2010-2014 ajs4-6pgz (A)", "Covered by 9m78-yc88, which starts in FY2010."),
    ("OH", "Ohio State salary snapshots (A)", "Downloaded but not loaded: same people as the earnings files; rate, not pay. Kept on disk."),
    ("PA", "PennWatch PASSHE / Thaddeus Stevens salaries (B)", "Re-checked Oct 2026: GET with agency/date parameters returns 'No Data Found'; results need a POST with an anti-forgery token. Not submitted."),
    ("PA", "Penn State top-200 PDF (B)", "Cloudflare challenge; skipped."),
    ("IL", "University of Illinois FY26 Salary Book PDF (B)", "Redundant: Gray Book 2026-27 (loaded) carries present FY2026 salary; UI gross pay comes from il_stl."),
    ("WA", "LEAP / fiscal.wa.gov State Employee Salary Database (B)", "Bulk file is sent by email on request (the 'Download Data' link is a mailto to leap@leg.wa.gov). Request drafted in docs/university-pay-requests.md; the main session sends it. data.wa.gov has nothing after 2013."),
    ("DC", "UDC quarterly listings FY2016, FY2019, Dec 2013 (B)", "Gap accepted (owner, round 3): no table rules in the FY2016 and FY2019 PDFs (multi-word names cannot be split reliably); Dec 2013 has no agency column. Spreadsheet request to the DCHR FOIA officer drafted for the next round in docs/university-pay-requests.md."),
    ("IL", "Illinois State FY2013-FY2019 PDFs (B)", "Supplied by the owner (hand download) but scanned paper lists with an OCR text layer (garbled headers and names, changing column order); not loaded. See Manual download list."),
    ("ID", "Transparent Idaho (B)", "JS single-page app; no plain-HTTP data endpoint."),
    ("MI", "Western Michigan employee list PDF (B)", "No employee names (position, FTE, salary only); not person-level."),
    ("CO", "University of Colorado personnel roster PDF (B)", "No employee names (anonymized roster IDs)."),
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
    "mo_stl vs mo_um: same University of Missouri people; mo_stl is 2025 gross pay (newsroom), mo_um is the official salary rate + W-2.",
    "il_ibhe vs il_graybook / il_stl / il_isu: IBHE covers administrators and faculty at all 12 public universities FY2010-2025; the other "
    "Illinois sources overlap it for the same people (Gray Book budgeted salary, Post-Dispatch gross pay, ISU list incl. civil service).",
    "in_gateway: Form 100R lists one row per position line, so people with several positions (overloads, summer, stipends) have several rows; "
    "the publisher's stated record count was matched for every unit and year. Owner accepted the IC 5-14-3-3(f) non-commercial-use terms.",
    "nm_nmhu FY2025: the publisher prints $0.00 for 122 lines; kept as published (base_pay = 0) and flagged pay_components.source_published_zero = true.",
    "tn_apsu: the list has no date; FY2027 comes from the PDF creation date (2026-09-21), flagged pay_components.year_derived = 'pdf_creation_date' on every row.",
    "ne_cc: Southeast and Mid-Plains community colleges publish no year; fiscal_year is NULL and pay_components.year_not_published = true.",
    "dc_hist: DC FY2016 and FY2019 are missing (unruled PDFs); gap accepted, spreadsheet request drafted.",
    "ar_adhe FY2010-2026: one form per administrator (>= $100k); every year verified and loaded on its own. FY2010-2019 use the older "
    "24-line form (institution and name as printed, typos normalized). A handful of forms per year could not be read (blank or "
    "unrecognized layout): FY2010 1, FY2012 1, FY2015 1, FY2020 4, FY2021 2 of the forms counted in the PDF. 'University of Arkansas' "
    "(718 rows, mostly FY2011-2014 and FY2016) is the Fayetteville campus, System office or another UA unit where the contents page does "
    "not tell them apart; kept as printed.",
    "mo_um: 8 of 13 MOspace reports loaded (2013-14 to 2015-16, 2017-18 to 2019-20, 2022-23, 2025-26); 2017-18 to 2019-20 print one business "
    "unit for Columbia + System office + MU Health Care, labelled University of Missouri.",
    "il_isu: FY2020-2026 (FY2025 = the 5/19/25 'Update' list, which supersedes the January list); FY2013-2019 OCR scans not loaded.",
]


def manual_downloads(cur):
    """'Manual download list': files a script cannot fetch (Cloudflare) and where to drop them. Per-file status comes from
    the il_isu manifest, pdf_mo_il.ISU_SKIP and the loaded rows."""
    from common import DATA
    import pdf_mo_il
    out = ["## Manual download list", "",
           "Sources a script must not fetch (Cloudflare challenge): someone downloads the files in a browser and drops them on the dev box.", "",
           "### Illinois State University (il_isu)", "",
           f"- Landing page: {pdf_mo_il.ISU_LANDING} (Cloudflare-protected; scripts never fetch it)",
           "- Known plain-GET files: https://files.library.illinoisstate.edu/ISUSalaries/fy23_salaries.pdf and "
           "https://files.library.illinoisstate.edu/ISUSalaries/fy24_salaries.pdf (both loaded)",
           "- Expected on files.library but unconfirmed: https://files.library.illinoisstate.edu/ISUSalaries/fy25_salaries.pdf and "
           "https://files.library.illinoisstate.edu/ISUSalaries/fy26_salaries.pdf (FY2025 and FY2026 were instead supplied by hand, below)",
           "- Where to drop files: `~/unipay-data/il_isu/` (or `~/unipay-data/il_isu/manual/` with a `SHA256SUMS` file); any PDF whose "
           "name contains `FY2027` / `fy27_salaries` etc. is picked up, with the fiscal year taken from the name",
           "- Load command (dev box): `cd ~/np-explorer/scripts/unipay && ~/unipay-venv/bin/python pdf_mo_il.py register il_isu && "
           "~/unipay-venv/bin/python pdf_mo_il.py verify il_isu && ./load_keys.sh il_isu` (register adds new PDFs to the manifest with "
           "sha256, landing-page URL and file time as retrieved_at; verify prints rows per page, unparsed amounts and a spot check)",
           "- Supplied 2026-10-18: the site owner downloaded FY2013-FY2026 (15 PDFs incl. 'FY2025 Update') by hand into "
           "`~/unipay-data/il_isu/manual/` (sha256 in SHA256SUMS, PROVENANCE.txt). Status per file:", "",
           "| File | Fiscal year | Status | Rows |", "|---|---|---|---|"]
    cur.execute("""SELECT s.file_name, count(r.id) FROM unipay.public_payroll_sources s LEFT JOIN unipay.public_payroll_records r ON r.source_id=s.id
                   WHERE s.source_key='il_isu' GROUP BY 1""")
    rows = {f.replace("~/unipay-data/il_isu/", ""): n for f, n in cur.fetchall()}
    try:
        files = json.loads((DATA / "il_isu" / "manifest.json").read_text())["files"]
    except FileNotFoundError:
        files = {}
    for f in sorted(files, key=lambda f: (pdf_mo_il.isu_fy(f), f)):
        if f in rows:
            st, n = "loaded", f"{rows[f]:,}"
        else:
            st, n = "not loaded: " + pdf_mo_il.ISU_SKIP.get(f, "not loaded yet"), ""
        out.append(f"| {f} | {pdf_mo_il.isu_fy(f)} | {mdcell(st, 220)} | {n} |")
    return out + [""]


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
    import pdf_mo_il
    extra = []
    for f, why in sorted(pdf_mo_il.MO_UM_SKIP.items()):
        yrs = "-".join(re.findall(r"\d{4}", f))
        extra.append(("MO", f"UM System salary report {yrs} PDF (B)", why + " (downloaded, not loaded)"))
    for st, src, why in SKIPPED + extra:
        out.append(f"| {st} | {src} | {why} |")
    for k, v in sorted(prog.get("sources", {}).items()):
        if v.get("status") not in ("loaded",):
            out.append(f"| {k} | load step | {v.get('status')}: {mdcell(v.get('error') or v.get('reason'), 200)} |")
    out.append("")

    out += ["## Coverage notes", ""] + [f"- {n}" for n in COVERAGE_NOTES] + [""]
    out += manual_downloads(cur)

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
