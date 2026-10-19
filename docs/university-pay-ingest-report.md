# University pay ingest report

Generated 2026-10-18 22:29 (America/Chicago) by `scripts/unipay/report.py`. Staging data only (schema `unipay`); nothing here is on the site.

## Summary

- Sources loaded: **40** (from 26 states/DC)
- Records loaded: **8,565,181** into `unipay.public_payroll_records`
- Institutions (distinct state + institution labels): **562**

| Key | State | Source | Files | Rows | Years | Institutions | Distinct people (inst+name) | Catalog id |
|---|---|---|---|---|---|---|---|---|
| ct | CT | State of Connecticut payroll (higher-ed agencies) | 36 | 979,441 | 2010-2027 | 23 | 91,371 | 30 |
| ma | MA | Massachusetts CTHRU statewide payroll (higher-ed departments) | 18 | 1,198,973 | 2009-2026 | 38 | 185,473 | 76 |
| nyc | NY | NYC Citywide Payroll (CUNY community colleges) | 1 | 262,569 | 2014-2025 | 7 | 48,919 | 125 |
| ga | GA | Open Georgia salaries (USG, TCSG, GMC) | 1 | 1,419,662 | 2015-2025 | 63 | 285,043 | 43 |
| tx | TX | Texas College Salaries (volunteer project, TPIA requests) | 1 | 170,130 | 2025-2026 | 46 | 152,328 | 160 |
| il_iccb | IL | Illinois Community College Board salary & benefits | 11 | 196,985 | 2016-2026 | 67 | 51,661 | 56 |
| oh_osu | OH | The Ohio State University | 5 | 240,592 | 2021-2025 | 1 | 76,282 | 128 |
| oh_ou | OH | Ohio University | 1 | 5,096 | 2025-2025 | 1 | 5,092 | 129 |
| mn | MN | Minnesota MMB state employee salary data (Minnesota State only) | 16 | 313,601 | 2011-2026 | 40 | 66,912 | 89 |
| wa | WA | Washington state salaries 2010-2013 (data.wa.gov y3ds-rkew) | 1 | 374,836 | 2010-2013 | 38 | 133,726 | 174 |
| ne | NE | University of Nebraska budgeted employees | 11 | 149,198 | 2017-2027 | 6 | 28,659 | 109 |
| me | ME | University of Maine System regular employee compensation | 1 | 4,449 | 2026-2026 | 9 | 4,448 | 81 |
| nm | NM | University of New Mexico Sunshine salary book | 1 | 10,676 | 2027-2027 | 1 | 10,667 | 119 |
| dc | DC | DC Government employee salary layer (UDC rows) | 1 | 3,156 | 2027-2027 | 1 | 1,502 | 33 |
| az_asu | AZ | Arizona State University (State Press SalaryList) | 8 | 127,147 | 2018-2025 | 1 | 48,385 | 15 |
| az_ua | AZ | University of Arizona (Flourish embed) | 1 | 107,080 | 2019-2026 | 1 | 25,321 | 16 |
| ks | KS | Kansas state payroll 2021-2025 (Kansas Policy Institute / KansasOpenGo | 1 | 122,263 | 2021-2025 | 7 | 48,815 | 66 |
| nj | NJ | NJ pension membership (active members, higher-ed employers) | 1 | 12,922 | 2026-2026 | 30 | 12,911 | 115 |
| ok | OK | Oklahoma OMES state payroll (higher-ed agencies), FY2026 | 12 | 394,645 | 2026-2026 | 56 | 81,220 | 134 |
| il_graybook | IL | University of Illinois Board of Trustees Gray Book 2026-27 | 4 | 21,515 | 2027-2027 | 4 | 13,755 | 58 |
| sc | SC | SC Dept of Administration state salaries (colleges and universities) | 25 | 20,264 | 2027-2027 | 25 | 20,211 | 147 |
| md | MD | University of Maryland, College Park (Diamondback salary guide API) | 13 | 140,391 | 2013-2025 | 1 | 36,825 | 78 |
| ne_cc | NE | Nebraska community colleges (Flatwater Free Press Nebraska Public Payr | 3 | 3,470 | 2024-2024 | 3 | 3,348 | 110 |
| mo_stl | MO | St. Louis Post-Dispatch Public Pay 2026 (Missouri universities and col | 8 | 22,951 | 2025-2025 | 8 | 22,950 | 93 |
| il_stl | IL | St. Louis Post-Dispatch Public Pay 2026 (SIUE and University of Illino | 5 | 44,841 | 2025-2025 | 5 | 44,744 | 93 |
| mo_um | MO | University of Missouri System annual salary reports (MOspace PDFs) | 8 | 193,293 | 2014-2026 | 7 | 86,248 | 92 |
| mo_msu | MO | Missouri State University FY27 internal operating budget, Detail Full- | 1 | 2,187 | 2027-2027 | 2 | 2,042 | 94 |
| il_isu | IL | Illinois State University salary lists (PDFs, FY2020-FY2026) | 7 | 25,031 | 2020-2026 | 1 | 6,245 | 60 |
| vt_uvm | VT | University of Vermont List of Base Pay (PDF) | 17 | 70,348 | 2010-2026 | 1 | 15,116 | 170 |
| nm_nmhu | NM | New Mexico Highlands University salary reports (PDF) | 4 | 2,873 | 2023-2026 | 1 | 1,707 | 120 |
| tn_apsu | TN | Austin Peay State University employee salary data (PDF) | 1 | 1,158 | 2027-2027 | 1 | 1,156 | 153 |
| tn_etsu | TN | East Tennessee State University active employees (PDF) | 1 | 2,473 | 2024-2024 | 1 | 2,471 | 154 |
| mi_um | MI | University of Michigan Salary Record (PDF) | 1 | 54,659 | 2026-2026 | 3 | 53,241 | 84 |
| me_hist | ME | University of Maine System salaries of regular employees (historical P | 4 | 18,453 | 2020-2022 | 9 | 5,721 | 82 |
| dc_hist | DC | DC DCHR quarterly public body employee listings (UDC rows), Dec 2013 - | 7 | 8,276 | 2014-2022 | 1 | 2,858 | 34 |
| ar_adhe | AR | Arkansas Division of Higher Education Administrator's Compensation Sur | 17 | 15,432 | 2010-2026 | 52 | 5,075 | 10 |
| pa_pitt | PA | University of Pittsburgh 200 highest-paid non-officers (Right-to-Know  | 2 | 400 | 2024-2025 | 1 | 244 | 142 |
| pa_temple | PA | Temple University 200 highest-paid employees other than officers (Righ | 2 | 400 | 2023-2025 | 1 | 246 | 143 |
| in_gateway | IN | Indiana Gateway Form 100R Certified Report of Public Employment and Co | 98 | 1,679,632 | 2012-2025 | 7 | 477,559 | 63 |
| il_ibhe | IL | Illinois Board of Higher Education public university salary search (al | 16 | 143,713 | 2010-2025 | 15 | 47,880 | 57 |

## Skipped or deferred sources

| State | Source | Why |
|---|---|---|
| RI | transparency.ri.gov payroll CSV (A) | robots.txt has `User-agent: * / Disallow: /`; honored, not downloaded. |
| FL | Board of Governors SUS payroll APEX export (A) | robots.txt on prod.flbog.net disallows all agents; export is also session-bound. |
| FL | Florida College System salaries (B) | Export only through a JS search UI with an undocumented API. |
| IA | Iowa Data Hub state salary book (A) | Re-checked Oct 2026: Next.js page with a client-side download button only; no static or GET data URL in the HTML. |
| NV | Transparent Nevada NSHE CSVs (A) | Re-checked Oct 2026: download is a JS button; GET of the CSV name redirects to an HTML page. |
| UT | Transparent Utah compensation downloader (A) | Bulk files come from an undocumented Cloud Run query service used by the JS app; not attempted. |
| TX | Full-name Texas university salaries | texascollegesalaries.com is behind a Cloudflare JS challenge; Texas Tribune explorer (now only the 116 Comptroller agencies, no universities) has no higher-ed rows. No plain-GET full-name source found. |
| OK | Full-name Oklahoma payroll | data.ok.gov payroll files 2010-2026 all publish last name + initials; OpenTheBooks is anti-bot; Oklahoma Watch site no longer resolves. |
| MO | data.mo.gov state payroll (A) | Does not cover colleges or universities. |
| NJ | NJ centralized payroll iqwc-r2w7 (A) | Does not cover institutions. |
| MA | CTHRU quasi-public payroll tc5d-8ckm (A) | Peripheral (quasi-public agencies, not institutions). |
| CT | CT payroll FY2010-2014 ajs4-6pgz (A) | Covered by 9m78-yc88, which starts in FY2010. |
| OH | Ohio State salary snapshots (A) | Downloaded but not loaded: same people as the earnings files; rate, not pay. Kept on disk. |
| PA | PennWatch PASSHE / Thaddeus Stevens salaries (B) | Re-checked Oct 2026: GET with agency/date parameters returns 'No Data Found'; results need a POST with an anti-forgery token. Not submitted. |
| PA | Penn State top-200 PDF (B) | Cloudflare challenge; skipped. |
| IL | University of Illinois FY26 Salary Book PDF (B) | Redundant: Gray Book 2026-27 (loaded) carries present FY2026 salary; UI gross pay comes from il_stl. |
| WA | LEAP / fiscal.wa.gov State Employee Salary Database (B) | Bulk file is sent by email on request (the 'Download Data' link is a mailto to leap@leg.wa.gov). Request drafted in docs/university-pay-requests.md; the main session sends it. data.wa.gov has nothing after 2013. |
| DC | UDC quarterly listings FY2016, FY2019, Dec 2013 (B) | Gap accepted (owner, round 3): no table rules in the FY2016 and FY2019 PDFs (multi-word names cannot be split reliably); Dec 2013 has no agency column. Spreadsheet request to the DCHR FOIA officer drafted for the next round in docs/university-pay-requests.md. |
| IL | Illinois State FY2013-FY2019 PDFs (B) | Supplied by the owner (hand download) but scanned paper lists with an OCR text layer (garbled headers and names, changing column order); not loaded. See Manual download list. |
| ID | Transparent Idaho (B) | JS single-page app; no plain-HTTP data endpoint. |
| MI | Western Michigan employee list PDF (B) | No employee names (position, FTE, salary only); not person-level. |
| CO | University of Colorado personnel roster PDF (B) | No employee names (anonymized roster IDs). |
| MO | UM System salary report 2016-2017 PDF (B) | fonts are embedded as bare glyph ids (/g38/g50...): the PDF has no usable text layer (downloaded, not loaded) |
| MO | UM System salary report 2020-2021 PDF (B) | Qt-rendered PDF: the header row is drawn over each page's first data row (whose salary rate is lost), words of adjacent columns overlap and amounts sit on a different baseline than the text, so rows split or merge (2020-21 test: 759 duplicate and 24 missing Idx numbers, 876 rows without a rate): not reliably extractable (downloaded, not loaded) |
| MO | UM System salary report 2021-2022 PDF (B) | Qt-rendered PDF: the header row is drawn over each page's first data row (whose salary rate is lost), words of adjacent columns overlap and amounts sit on a different baseline than the text, so rows split or merge (2020-21 test: 759 duplicate and 24 missing Idx numbers, 876 rows without a rate): not reliably extractable (downloaded, not loaded) |
| MO | UM System salary report 2023-2024 PDF (B) | Qt-rendered PDF: the header row is drawn over each page's first data row (whose salary rate is lost), words of adjacent columns overlap and amounts sit on a different baseline than the text, so rows split or merge (2020-21 test: 759 duplicate and 24 missing Idx numbers, 876 rows without a rate): not reliably extractable (downloaded, not loaded) |
| MO | UM System salary report 2024-2025 PDF (B) | Qt-rendered PDF: the header row is drawn over each page's first data row (whose salary rate is lost), words of adjacent columns overlap and amounts sit on a different baseline than the text, so rows split or merge (2020-21 test: 759 duplicate and 24 missing Idx numbers, 876 rows without a rate): not reliably extractable (also broken 'ti' ligature glyphs) (downloaded, not loaded) |
| ri | load step | skipped: no downloaded files |

## Coverage notes

- CT: the 12 community colleges merged into Connecticut State Community College in July 2023 and their payroll moved into the 'Connecticut Board of Regents' agency during FY2024, so FY2025+ shows 9 institutions (CT State campus kept in pay_components.campus). FY2010-2014 campuses are recovered from deptid digits (system agencies 'CT Community Colleges' / 'Connecticut State Universities'); Charter Oak's pre-2014 agency 'Board for Academic Awards' was added. FY2027 is a partial year (pay_components.partial_year_through).
- MN: institution is now the Minnesota State campus from the MMB location name (department-number majority when blank); rows with no resolvable location keep 'Minnesota State Colleges and Universities'.
- IL ICCB: from FY2025 the four Illinois Eastern colleges report as one district (Illinois Eastern Community Colleges), so the label count drops from 50 to 46.
- NYC: FY2017 includes about 9,300 'CEASED' employees (about 1,600 in other years) as published, which inflates that year's rows and lowers its median.
- AZ ASU: from 2022 the State Press file includes part-time/student employees (12k -> 20k rows).
- GA: 93,807 exact duplicate rows as published (identical org/name/title/salary/year); kept.
- TX: rows with data_date before Sep 2025 fall into FY2025 (2 institutions); the rest are FY2026 snapshots.
- MD: Diamondback year labels checked against known tenure dates and treated as fiscal years (see parsers.parse_md); the first pass's concern came from settlement payouts to departed coaches.
- il_stl vs il_graybook: same University of Illinois people; il_stl is actual 2025 gross pay, il_graybook is budgeted FY2026/27 salary.
- mo_stl vs mo_um: same University of Missouri people; mo_stl is 2025 gross pay (newsroom), mo_um is the official salary rate + W-2.
- il_ibhe vs il_graybook / il_stl / il_isu: IBHE covers administrators and faculty at all 12 public universities FY2010-2025; the other Illinois sources overlap it for the same people (Gray Book budgeted salary, Post-Dispatch gross pay, ISU list incl. civil service).
- in_gateway: Form 100R lists one row per position line, so people with several positions (overloads, summer, stipends) have several rows; the publisher's stated record count was matched for every unit and year. Owner accepted the IC 5-14-3-3(f) non-commercial-use terms.
- nm_nmhu FY2025: the publisher prints $0.00 for 122 lines; kept as published (base_pay = 0) and flagged pay_components.source_published_zero = true.
- tn_apsu: the list has no date; FY2027 comes from the PDF creation date (2026-09-21), flagged pay_components.year_derived = 'pdf_creation_date' on every row.
- ne_cc: Southeast and Mid-Plains community colleges publish no year; fiscal_year is NULL and pay_components.year_not_published = true.
- dc_hist: DC FY2016 and FY2019 are missing (unruled PDFs); gap accepted, spreadsheet request drafted.
- ar_adhe FY2010-2026: one form per administrator (>= $100k); every year verified and loaded on its own. FY2010-2019 use the older 24-line form (institution and name as printed, typos normalized). A handful of forms per year could not be read (blank or unrecognized layout): FY2010 1, FY2012 1, FY2015 1, FY2020 4, FY2021 2 of the forms counted in the PDF. 'University of Arkansas' (718 rows, mostly FY2011-2014 and FY2016) is the Fayetteville campus, System office or another UA unit where the contents page does not tell them apart; kept as printed.
- mo_um: 8 of 13 MOspace reports loaded (2013-14 to 2015-16, 2017-18 to 2019-20, 2022-23, 2025-26); 2017-18 to 2019-20 print one business unit for Columbia + System office + MU Health Care, labelled University of Missouri.
- il_isu: FY2020-2026 (FY2025 = the 5/19/25 'Update' list, which supersedes the January list); FY2013-2019 OCR scans not loaded.

## Manual download list

Sources a script must not fetch (Cloudflare challenge): someone downloads the files in a browser and drops them on the dev box.

### Illinois State University (il_isu)

- Landing page: https://ir.library.illinoisstate.edu/salaries (Cloudflare-protected; scripts never fetch it)
- Known plain-GET files: https://files.library.illinoisstate.edu/ISUSalaries/fy23_salaries.pdf and https://files.library.illinoisstate.edu/ISUSalaries/fy24_salaries.pdf (both loaded)
- Expected on files.library but unconfirmed: https://files.library.illinoisstate.edu/ISUSalaries/fy25_salaries.pdf and https://files.library.illinoisstate.edu/ISUSalaries/fy26_salaries.pdf (FY2025 and FY2026 were instead supplied by hand, below)
- Where to drop files: `~/unipay-data/il_isu/` (or `~/unipay-data/il_isu/manual/` with a `SHA256SUMS` file); any PDF whose name contains `FY2027` / `fy27_salaries` etc. is picked up, with the fiscal year taken from the name
- Load command (dev box): `cd ~/np-explorer/scripts/unipay && ~/unipay-venv/bin/python pdf_mo_il.py register il_isu && ~/unipay-venv/bin/python pdf_mo_il.py verify il_isu && ./load_keys.sh il_isu` (register adds new PDFs to the manifest with sha256, landing-page URL and file time as retrieved_at; verify prints rows per page, unparsed amounts and a spot check)
- Supplied 2026-10-18: the site owner downloaded FY2013-FY2026 (15 PDFs incl. 'FY2025 Update') by hand into `~/unipay-data/il_isu/manual/` (sha256 in SHA256SUMS, PROVENANCE.txt). Status per file:

| File | Fiscal year | Status | Rows |
|---|---|---|---|
| manual/Illinois State University Salaries FY2013.pdf | 2013 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2014.pdf | 2014 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2015.pdf | 2015 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2016.pdf | 2016 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2017.pdf | 2017 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2018.pdf | 2018 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2019.pdf | 2019 | not loaded: scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column order changes between sections): not reliably extractable |  |
| manual/Illinois State University Salaries FY2020.pdf | 2020 | loaded | 3,641 |
| manual/Illinois State University Salaries FY2021.pdf | 2021 | loaded | 3,515 |
| manual/Illinois State University Salaries FY2022.pdf | 2022 | loaded | 3,450 |
| isu_fy2023.pdf | 2023 | loaded | 3,512 |
| manual/Illinois State University Salaries FY2023.pdf | 2023 | not loaded: same list as isu_fy2023.pdf (files.library copy) plus a cover page; not loaded twice |  |
| isu_fy2024.pdf | 2024 | loaded | 3,681 |
| manual/Illinois State University Salaries FY2024.pdf | 2024 | not loaded: same list as isu_fy2024.pdf (files.library copy) plus a cover page; not loaded twice |  |
| manual/Illinois State University Salaries FY2025 Update.pdf | 2025 | loaded | 3,583 |
| manual/Illinois State University Salaries FY2025.pdf | 2025 | not loaded: superseded by 'FY2025 Update', a complete re-issue of the same list as of 5/19/25 (both employee groups; 3,583 vs 3,605 lines, about 95% of names in common, salaries updated for about a fifth); not loaded twi |  |
| manual/Illinois State University Salaries FY2026.pdf | 2026 | loaded | 3,649 |

## Per-source quality checks

Checks: rows per fiscal year; rows with any pay value; exact duplicates (identical original row within the same file and fiscal year); possible parse errors (empty name, no numeric pay, pay over $10,000,000, negative pay); 20 random sample rows.

### ct: State of Connecticut payroll (higher-ed agencies) (CT)

Notes: SoQL server-side aggregation of paycheck rows per employee record/agency/campus code/payroll FY SoQL server-side aggregation of paycheck rows per employee record/agency/payroll FY

- Rows: 979,441; with a pay value: 979,441 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 2; negative pay: 45

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2010 | 42,008 | 21 | $14,367 | $6,502 |
| 2011 | 52,056 | 21 | $26,277 | $8,520 |
| 2012 | 53,088 | 21 | $27,253 | $8,622 |
| 2013 | 53,715 | 22 | $26,438 | $8,622 |
| 2014 | 53,586 | 22 | $26,537 | $8,702 |
| 2015 | 53,580 | 22 | $28,822 | $9,472 |
| 2016 | 52,285 | 22 | $30,426 | $9,978 |
| 2017 | 59,464 | 22 | $26,777 | $6,137 |
| 2018 | 59,501 | 22 | $26,373 | $6,412 |
| 2019 | 59,289 | 22 | $26,630 | $6,396 |
| 2020 | 57,248 | 22 | $28,221 | $7,304 |
| 2021 | 47,620 | 22 | $34,865 | $11,946 |
| 2022 | 53,675 | 22 | $32,879 | $10,326 |
| 2023 | 57,890 | 22 | $34,012 | $9,029 |
| 2024 | 70,731 | 23 | $27,841 | $7,628 |
| 2025 | 54,904 | 9 | $38,161 | $11,650 |
| 2026 | 54,349 | 9 | $39,404 | $12,619 |
| 2027 | 44,452 | 9 | $17,002 | $6,489 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| UConn Health | Canfield, Jessica L. | UCHC UniversityHealthProf | UCHC | $52,336 | $3,295 | $55,631 | 2025 |
| University of Connecticut | Jacobs, Hayley | Student Services Prog Assist 2 | Students with Disabilities Ctr | $57,058 | $847 | $57,905 | 2025 |
| University of Connecticut | Undisclosed, Undisclosed Undisclose | UCONN GRAD PROF INTERN | Biomedical Engineering | $27,764 | $0 | $27,764 | 2025 |
| University of Connecticut | Undisclosed, Undisclosed Undisclose | GraduateAssistant |  | $9,195 | $0 | $9,195 | 2011 |
| Central Connecticut State University | Schindelman, Sylvia | SULecturer |  | $6,404 | $0 | $6,404 | 2011 |
| University of Connecticut | Undisclosed, Undisclosed Undisclose | UnivStudentWorker |  | $10 | $0 | $10 | 2012 |
| Manchester Community College | Boileau, Mary E | Secretary2 |  | $58,053 | $100 | $58,153 | 2012 |
| UConn Health | Liu, Fudong | UCHC Faculty |  | $64,008 | $0 | $64,008 | 2013 |
| Western Connecticut State University | Undisclosed, Undisclosed Undisclose | UnivStudentWorker |  | $85 | $0 | $85 | 2013 |
| Gateway Community College | Corr, Daniel | CCCPartTimeLecturer |  | $8,622 | $0 | $8,622 | 2013 |
| University of Connecticut | Kask, Virge A | UConnFaculty/Staff |  | $67,979 | $510 | $68,490 | 2014 |
| Gateway Community College | Undisclosed, Undisclosed Undisclose | CCStdntWkr-Disc |  | $4,278 | $0 | $4,278 | 2015 |
| Three Rivers Community College | Sauter, Patricia A. | CCCPartTimeLecturer |  | $9,504 | $0 | $9,504 | 2015 |
| Norwalk Community College | Breen, Christine M | CCCPartTimeLecturer |  | $4,989 | $0 | $4,989 | 2016 |
| Southern Connecticut State University | Undisclosed, Undisclosed Undisclose | SUFedWorkStudy |  | $322 | $0 | $322 | 2016 |
| UConn Health | Cipriano, Ashley | TelecommunicationsOperator |  | $9,934 | $20 | $9,955 | 2016 |
| UConn Health | Isenberg, Jill A. | UCHC UniversityHealthProf |  | $3,056 | $900 | $3,957 | 2016 |
| UConn Health | Gonzalez, Migdalia | UCHC UniversityHealthProf |  | $50,378 | $245 | $50,623 | 2017 |
| University of Connecticut | Undisclosed, Undisclosed Undisclose | Class 4 Default |  | $925 | $9 | $934 | 2017 |
| Gateway Community College | Doolittle, Susan I | CCPTClinicalFaculty |  | $40,286 | $0 | $40,286 | 2018 |

</details>

### ma: Massachusetts CTHRU statewide payroll (higher-ed departments) (MA)

Notes: fiscal_year = calendar year (CTHRU 'year'); UMass campus inferred from department_location_zip_code

- Rows: 1,198,973; with a pay value: 1,198,959 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 14; pay > $10M: 0; negative pay: 350

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2009 | 30,553 | 7 | $22,936 | $15,525 |
| 2010 | 65,374 | 35 | $27,688 | $14,625 |
| 2011 | 84,592 | 37 | $22,669 | $15,189 |
| 2012 | 69,693 | 31 | $28,232 | $13,935 |
| 2013 | 70,839 | 31 | $29,038 | $13,972 |
| 2014 | 70,896 | 31 | $29,911 | $14,403 |
| 2015 | 71,246 | 31 | $31,598 | $15,375 |
| 2016 | 70,666 | 31 | $32,329 | $16,782 |
| 2017 | 70,225 | 31 | $33,095 | $16,519 |
| 2018 | 68,453 | 31 | $34,393 | $17,769 |
| 2019 | 69,921 | 31 | $34,900 | $17,652 |
| 2020 | 63,461 | 31 | $37,670 | $21,422 |
| 2021 | 62,191 | 31 | $38,408 | $21,711 |
| 2022 | 67,851 | 32 | $38,462 | $19,544 |
| 2023 | 64,988 | 31 | $41,208 | $24,149 |
| 2024 | 68,131 | 31 | $41,994 | $23,075 |
| 2025 | 66,715 | 31 | $45,002 | $27,866 |
| 2026 | 63,178 | 31 | $40,426 | $22,656 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Massachusetts College of Art and Design | Flackett, Antony | Contracted Faculty | MASSACHUSETTS COLLEGE OF ART AND DE | $12,212 | $0 | $12,212 | 2012 |
| North Shore Community College | Nigrelli, Eugene | Contracted Faculty | NORTH SHORE COMMUNITY COLLEGE (NSC) | $9,675 | $0 | $9,675 | 2012 |
| Mt Wachusett Community College | Palmieri, Tara | Group Exercise | MT WACHUSETT COMMUNITY COLLEGE (MWC | $1,645 | $0 | $1,645 | 2013 |
| Quinsigamond Community College | D'Argenis, Joan | Cntrct EEs NOtherwise Categor | QUINSIGAMOND COMMUNITY COLLEGE (QCC | $500 | $0 | $500 | 2013 |
| University of Massachusetts Amherst | Thornton, Thomas | Skilled Laborer | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $12,228 | $1,936 | $14,164 | 2013 |
| University of Massachusetts Amherst | Hoel, Christopher | Research Fellow UM | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $18,461 | $0 | $18,461 | 2014 |
| Middlesex Community College | Feeley, David | Contracted Faculty | MIDDLESEX COMMUNITY COLLEGE (MCC) | $8,057 | $0 | $8,057 | 2014 |
| Bristol Community College | Amaral, Juliet | Adjunct Instructor | BRISTOL COMMUNITY COLLEGE (BRC) | $14,292 | $0 | $14,292 | 2015 |
| Springfield Tech Comm College | Statham, Rachel | PT Reference Librarian | SPRINGFIELD TECH COMM COLLEGE (STC) | $25,776 | $0 | $25,776 | 2015 |
| Westfield State University | Oulbeid, Brahim | MSCA Visiting Lecturer | WESTFIELD STATE UNIVERSITY (WSC) | $6,528 | $0 | $6,528 | 2015 |
| Bristol Community College | Martins, Brittany | Kids College TA 453 | BRISTOL COMMUNITY COLLEGE (BRC) | $1,328 | $0 | $1,328 | 2015 |
| University of Massachusetts Boston | Fulton, John | Associate Professor | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $90,866 | $0 | $90,866 | 2015 |
| Bridgewater State University | Davis-Street, Jeanean | Associate Dean | BRIDGEWATER STATE UNIVERSITY (BSC) | $116,126 | $0 | $116,126 | 2015 |
| University of Massachusetts Lowell | Tyndall, Randolph | Instructional Technologist | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $32,651 | $0 | $32,651 | 2015 |
| Bunker Hill Community College | Weinmann, Christopher | Cntrct EEs NOtherwise Categor | BUNKER HILL COMMUNITY COLLEGE (BHC) | $88 | $0 | $88 | 2015 |
| Holyoke Community College | Tynan, Gertrude | Contracted Seasonal Employees | HOLYOKE COMMUNITY COLLEGE (HCC) | $13,860 | $0 | $13,860 | 2016 |
| Massasoit Community College | Janey, Gerald | Adjunct Fac Credit MathSci | MASSASOIT COMMUNITY COLLEGE (MAS) | $5,771 | $0 | $5,771 | 2017 |
| UMass Chan Medical School | Miozzo, Ruben | Asst Professor | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $8,765 | $0 | $8,765 | 2017 |
| Northern Essex Community College | Chory, Susan | Transition to College Faculty | NORTHERN ESSEX COMMUNITY COLLEGE (N | $368 | $0 | $368 | 2017 |
| Westfield State University | Daley, Tara | Contracted Seasonal Employees | WESTFIELD STATE UNIVERSITY (WSC) | $1,325 | $0 | $1,325 | 2017 |

</details>

### nyc: NYC Citywide Payroll (CUNY community colleges) (NY)

Notes: fiscal_year = NYC FY (Jul-Jun)

- Rows: 262,569; with a pay value: 262,569 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 1,961

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2014 | 20,943 | 7 | $23,595 | $10,202 |
| 2015 | 21,393 | 7 | $24,099 | $10,505 |
| 2016 | 22,246 | 7 | $24,233 | $10,523 |
| 2017 | 37,805 | 7 | $18,820 | $2,610 |
| 2018 | 22,517 | 7 | $27,475 | $11,812 |
| 2019 | 22,868 | 7 | $27,554 | $11,732 |
| 2020 | 26,380 | 7 | $24,924 | $8,314 |
| 2021 | 18,964 | 7 | $32,956 | $15,626 |
| 2022 | 17,145 | 7 | $36,626 | $18,125 |
| 2023 | 16,430 | 7 | $38,585 | $20,066 |
| 2024 | 16,015 | 7 | $39,582 | $20,952 |
| 2025 | 19,863 | 7 | $34,963 | $13,751 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Hostos Community College | PERRY, ALISON M | NON-TEACHING ADJUNCT III |  | $6,402 | $0 | $6,402 | 2014 |
| LaGuardia Community College | RIVERA-TORRES, IVAN O | ASSISTANT PROFESSOR |  | $13,630 | $0 | $13,630 | 2014 |
| Borough of Manhattan Community College | COLMANT-DONABED, TANIA | NON-TEACHING ADJUNCT III |  | $13,663 | $0 | $13,663 | 2014 |
| Queensboro Community College | BAM, TEK | COLLEGE ASSISTANT |  | $2,131 | $0 | $2,131 | 2014 |
| Queensboro Community College | CUOMO, MICHELE | ASSOCIATE DEAN |  | $15,098 | $0 | $15,098 | 2014 |
| Bronx Community College | TIMKO, GEORGE | NON-TEACHING ADJUNCT II | BRONX | $445 | $0 | $445 | 2015 |
| Kingsboro Community College | AHRENS, PAULINE M | NON-TEACHING ADJUNCT I | BROOKLYN | $81 | $0 | $81 | 2015 |
| LaGuardia Community College | RIVERA-MAESTRE, REBECCA | NON-TEACHING ADJUNCT III | QUEENS | $3,309 | $0 | $3,309 | 2015 |
| Borough of Manhattan Community College | CORDEIRO, CATHERINE | ADJUNCT LECTURER | MANHATTAN | $9,684 | $0 | $9,684 | 2015 |
| Queensboro Community College | CAMPOS, MANUEL A | CONTINUING EDUCATION TEACHER | QUEENS | $816 | $0 | $816 | 2015 |
| Queensboro Community College | SIMPSON, SAUNDRA | COLLEGE ASSISTANT | QUEENS | $165 | $0 | $165 | 2015 |
| Bronx Community College | PINEIRO-BARCELO, JORGE | ASSOCIATE PROFESSOR | BRONX | $159 | $0 | $159 | 2016 |
| LaGuardia Community College | DRAME, ABDOU K | ASSOCIATE PROFESSOR | QUEENS | $80,235 | $0 | $80,235 | 2016 |
| Borough of Manhattan Community College | EGGERS, JOHN P | ADJUNCT PROFESSOR | MANHATTAN | $9,634 | $0 | $9,634 | 2016 |
| Borough of Manhattan Community College | RAYMOND, MELISSA D | ADJUNCT LECTURER | MANHATTAN | $16,145 | $0 | $16,145 | 2016 |
| Borough of Manhattan Community College | SANTIAGO, MARTIN | MAIL/MESSAGE SERVICES WORKER | MANHATTAN | $22,859 | $939 | $23,797 | 2016 |
| Queensboro Community College | SIMONETTA, MICHAEL | CUSTODIAL ASSISTANT | QUEENS | $30,125 | $793 | $30,918 | 2016 |
| Bronx Community College | LAKE, MAHONEY | CUNY CUSTODIAL ASSISTANT | BRONX | $24,190 | $3,130 | $27,320 | 2017 |
| LaGuardia Community College | BARONE, JEFFREY J | ADJUNCT LECTURER | QUEENS | $7,465 | $0 | $7,465 | 2017 |
| Borough of Manhattan Community College | GENIN, DEMITRY | ADJUNCT SENIOR COLLEGE LAB TECH | MANHATTAN | $8 | $0 | $8 | 2017 |

</details>

### ga: Open Georgia salaries (USG, TCSG, GMC) (GA)

Notes: filtered ORGANIZATION to universities/colleges; salary only (travel kept in pay_components)

- Rows: 1,419,662; with a pay value: 1,419,662 (100.0%)
- Exact duplicate rows (same original row): 93,807
- Empty name: 0; no numeric pay: 0; pay > $10M: 3; negative pay: 1,316

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2015 | 129,383 | 56 | $28,839 | $13,972 |
| 2016 | 129,210 | 54 | $29,991 | $14,792 |
| 2017 | 132,038 | 53 | $30,815 | $14,979 |
| 2018 | 133,116 | 51 | $31,804 | $15,503 |
| 2019 | 135,205 | 51 | $32,048 | $15,558 |
| 2020 | 130,673 | 51 | $34,377 | $18,640 |
| 2021 | 118,390 | 51 | $37,800 | $24,017 |
| 2022 | 124,562 | 51 | $38,192 | $20,500 |
| 2023 | 127,215 | 51 | $39,092 | $21,183 |
| 2024 | 129,329 | 51 | $41,130 | $22,851 |
| 2025 | 130,541 | 51 | $42,932 | $24,786 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Georgia | GODDARD,ELIZABETH A | SERVICE/MAINTENANCE WORKER |  |  |  | $37,910 | 2023 |
| University of Georgia | JEFFERY,SARAH KAY | PUBLIC SERVICE PROFESSIONAL AD |  |  |  | $54,076 | 2023 |
| University of Georgia | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $1,608 | 2023 |
| University of Georgia | DOOMSTORM,DILLON A | TEMPORARY TECHNICAL/PARAPRO |  |  |  | $4,552 | 2023 |
| Georgia College and State University | VALLIANATOS,ELIANNA | STUDENT ASSISTANT PART TIME |  |  |  | $800 | 2025 |
| College of Coastal Georgia | CULWELL,KEVIN MICHAEL | IT SYSTEMS SUPPORT PARA/PRO |  |  |  | $55,338 | 2025 |
| East Georgia State College | STRICKLAND,DAVID L | ASSOCIATE PROFESSOR |  |  |  | $55,446 | 2015 |
| University of Georgia | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $897 | 2025 |
| University of Georgia | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $404 | 2015 |
| University of Georgia | JONES,BARBARA MICHELLE | DEV/FUNDRAISING PROFESSIONAL |  |  |  | $86,727 | 2022 |
| Georgia Gwinnett College | EDGECOMBE,IMANI M | OFFICE/CLERICAL ASSISTANT |  |  |  | $33,512 | 2022 |
| Southern Crescent Technical College | MOBLEY,LARAYSHA YVONNE | CAREER ADVISOR |  |  |  | $42,720 | 2021 |
| University of Georgia | CAMACHO,DARLENE FRANCES | DIRECTOR SUBDIV/UNIT AD |  |  |  | $43,243 | 2021 |
| University of Georgia | BYRNE,KATHRYN R | TEMPORARY HOURLY PROFESSIONAL |  |  |  | $63 | 2021 |
| University of West Georgia | RUDOLPH,EDWIN B | ACADEMIC SERVICES PROFESSIONAL |  |  |  | $51,344 | 2021 |
| University of Georgia | ALVAREZARMENTA,ROSENDO | INFORMATION TECHNOLOGY MANAGER |  |  |  | $83,068 | 2021 |
| Georgia Institute of Technology | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $3,371 | 2022 |
| Georgia Institute of Technology | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $2,121 | 2022 |
| Georgia Institute of Technology | TAYLOR,SHIRLEY S | ACCOUNTING PROFESSIONAL |  |  |  | $65,898 | 2022 |
| Georgia State University | SINGLETON,YORK | FACILITY OPER PROFESSIONAL |  |  |  | $64,771 | 2022 |

</details>

### tx: Texas College Salaries (volunteer project, TPIA requests) (TX)

Notes: Google Drive file 'TCS Export 05_25_2026.csv' in public folder 1RHnj46y3B5X8T4siwudKJOBmuJYDAMRF

- Rows: 170,130; with a pay value: 170,130 (100.0%)
- Exact duplicate rows (same original row): 489
- Empty name: 0; no numeric pay: 0; pay > $10M: 1; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2025 | 2,203 | 2 | $60,492 | $64,184 |
| 2026 | 167,927 | 44 | $86,742 | $68,258 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Austin Community College | Samantha F | Associate, Campus Custodial Operations | Campus Custodial | $49,276 |  |  | 2026 |
| Austin Community College | Vanessa L | Faculty, World Languages | Dean, Lib Arts: Humanities & Comm | $112,623 |  |  | 2026 |
| The University of Texas at Austin | Jon A | Chief Financial Officer | Dell Medical School | $750,000 |  |  | 2026 |
| The University of Texas at Austin | Larry A | Professor Of Practice | Lyndon B Johnson School of Public A | $125,860 |  |  | 2026 |
| The University of Texas at Austin | Keefe B | Assistant Director-Production Services | Moody College of Communication | $118,142 |  |  | 2026 |
| The University of Texas at Austin | Glenn P D | Associate Professor Of Instruction | Department of Computer Science | $112,767 |  |  | 2026 |
| The University of Texas at Austin | Nicholas J H | Associate Professor | Department of Accounting | $295,060 |  |  | 2026 |
| The University of Texas at Austin | Calista J L | Development Specialist | Charles A Dana Center | $62,017 |  |  | 2026 |
| Texas A&M Health Science Center | Christine C | Clinical Assistant Professor | Comprehensive Dentistry | $154,909 |  |  | 2026 |
| Texas A&M Health Science Center | Amy M G | Project Coordinator Ii | Psychiatry Bryan College Station Ca | $48,000 |  |  | 2026 |
| Texas A&M Health Science Center | Maria M A | Administrative Coordinator I | Cop - Office Of The Dean | $54,080 |  |  | 2026 |
| Texas A&M Health Science Center | Lily G | Dean - Faculty | Hsc Senior Vice President | $262,325 |  |  | 2026 |
| Lamar University | Erika P | Distance Learning Adjunct | Educational Leadership | $3,000 |  |  | 2026 |
| Texas A&M Kingsville | Dominique P | Assistant Director P12 | Center for Student Success (Robert  | $68,575 |  |  | 2026 |
| Texas A&M Prairie View | Chrisdolyn D | Executive Director, Student Engagement | Housing Needed For Pct Only | $75,000 |  |  | 2026 |
| University of Houston | Theresa R E | Mgr, Acdmc Prtnrshp & Pblc Eng | Public Art | $80,004 |  |  | 2026 |
| Sam Houston State University | Sylvia V B | Personal Financial Coach | Student Money Management Center | $40,632 |  |  | 2026 |
| Sam Houston State University | Adele R G | Associate Professor 9 Mo | Dept of Management & Marketing | $119,682 |  |  | 2026 |
| Lone Star Community College | Donna L H | Analyst Sr Treasury | Treasury | $95,275 |  |  | 2026 |
| Lone Star Community College | Norma L | Advisor Ii | Advising | $49,796 |  |  | 2026 |

</details>

### il_iccb: Illinois Community College Board salary & benefits (IL)

Notes: total_pay = base + extra duty + enhancements; benefits/annuities kept in pay_components only

- Rows: 196,985; with a pay value: 196,985 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2016 | 20,887 | 50 | $35,116 | $14,759 |
| 2017 | 19,695 | 50 | $36,381 | $15,612 |
| 2018 | 19,029 | 50 | $37,770 | $15,903 |
| 2019 | 18,782 | 50 | $39,007 | $17,105 |
| 2020 | 18,119 | 50 | $40,725 | $18,364 |
| 2021 | 16,374 | 50 | $44,921 | $21,097 |
| 2022 | 17,544 | 50 | $43,878 | $20,653 |
| 2023 | 16,270 | 49 | $46,721 | $22,212 |
| 2024 | 16,405 | 50 | $49,487 | $25,048 |
| 2025 | 16,812 | 46 | $51,823 | $25,064 |
| 2026 | 17,068 | 46 | $53,826 | $26,773 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| College of DuPage | OLIVER, ROBERT EDWARD | PART TIME FACULTY - BASIC | Instructional | $19,800 | $0 | $19,800 | 2016 |
| South Suburban College | MONBROD, DENNIS J | FACULTY, MATH DEVELOPMENTAL CR | Instructional | $84,252 | $0 | $84,252 | 2016 |
| Prairie State College | SPENCER, ELISE C | ASSISTANT PROFESSOR ENGL | Instructional | $49,172 | $6,867 | $56,039 | 2016 |
| Waubonsee Community College | FRIEDLAND, TYLER MITCHELL | ADJUNCT FACULTY | Instructional | $4,500 | $0 | $4,500 | 2016 |
| College of Lake County | WHITE, HIRAM J | PT FACULTY - CREDIT COURSES | Instructional | $5,053 | $343 | $5,396 | 2016 |
| Parkland College | TUCKER, KEVIN | PART-TIME FACULTY | Instructional | $3,399 | $0 | $3,399 | 2017 |
| Illinois Valley Community College | BALZARINI, DOREEN J | PT FAC/SINGLE ACCT # | Instructional | $11,228 | $0 | $11,228 | 2017 |
| Waubonsee Community College | FERNANDEZ, JUAN MANUEL | ADJUNCT FACULTY | Instructional | $9,325 | $0 | $9,325 | 2017 |
| Waubonsee Community College | MAUTHE, JEREMY D | ADJUNCT FACULTY | Instructional | $2,156 | $0 | $2,156 | 2017 |
| Kankakee Community College | BERG, HAROLD EDWIN | ADJUNCT MATH | Instructional | $206 | $0 | $206 | 2017 |
| Southwestern Illinois College | MCCLURE, MICHAEL W | FACULTY | Instructional | $56,809 | $11,306 | $68,115 | 2017 |
| Southwestern Illinois College | SALLIE, ROBERT L | PART TIME FACULTY WELDING | Instructional | $75 | $75 | $150 | 2017 |
| Richland Community College | CREMER, MARCELLA | F/T MATH FACULTY | Instructional | $61,456 | $2,421 | $63,877 | 2017 |
| Illinois Central College | MALMBERG, LAUREN MICHELLE | ADJUNCT FACULTY | Instructional | $4,040 | $0 | $4,040 | 2018 |
| Lincoln Land Community College | STARE, RUSSELL KARL | WEL MOD 1-4 & SUMMER ADJUNCT I | Instructional | $15,070 | $0 | $15,070 | 2018 |
| Mc Henry County College | HOOVER, WILLIAM C | ADJ FAC ECTE | Instructional | $11,149 | $0 | $11,149 | 2018 |
| Harold Washington College | LUCAS, THOMAS R | LECT-CREDIT COURSE III-UNION | Instructional | $7,190 | $0 | $7,190 | 2019 |
| Elgin Community College | HOEKSTRA, KATRINA A | MATHEMATICS UNIT ADJUNCT I FACULTY | Instructional | $5,745 | $0 | $5,745 | 2019 |
| Moraine Valley Community College | KLEDZIK, PHILIP A | HISTORY FACULTY - PT | Instructional | $9,581 | $0 | $9,581 | 2019 |
| Lincoln Land Community College | DEMINK, TARA L | ADULT ED. INSTRUCTOR SURS | Instructional | $17,844 | $0 | $17,844 | 2019 |

</details>

### oh_osu: The Ohio State University (OH)

Notes: calendar-year paid earnings files; salary-snapshot files downloaded but not loaded (same people, rate not pay)

- Rows: 240,592; with a pay value: 240,592 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 2; negative pay: 19

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2021 | 45,415 | 1 | $67,914 | $51,711 |
| 2022 | 46,817 | 1 | $70,233 | $53,275 |
| 2023 | 47,656 | 1 | $73,676 | $56,560 |
| 2024 | 48,896 | 1 | $77,565 | $59,906 |
| 2025 | 51,808 | 1 | $78,972 | $61,415 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| The Ohio State University | Copley, Brenda | Patient Care Associate (HS) | CC99048 University Hospital / 7 Eas | $34,597 | $1,100 | $35,697 | 2021 |
| The Ohio State University | Downs, Keyasia | Social Worker - LSW (HS) | CC99097 Harding / Harding Social Wo | $19,838 | $320 | $20,158 | 2021 |
| The Ohio State University | Robbins, Tina | Program Specialist | CC12101 FAES / Family and Consumer  | $53,108 | $0 | $53,108 | 2021 |
| The Ohio State University | Rub, Guy | Professor (9M) | CC12751 Law / Law Reserve | $166,631 | $13,500 | $180,131 | 2021 |
| The Ohio State University | Westfall, Jae | Program Director | CC11168 EHE / Human Sciences Admini | $97,095 | $0 | $97,095 | 2021 |
| The Ohio State University | York, Kimberly | Talent Acquisition Spec 3 | CC12270 Human Resources / Talent Ac | $73,314 | $0 | $73,314 | 2021 |
| The Ohio State University | Jonas, Daniel | Professor | CC11286 Medicine / IM General Inter | $363,466 | $100,000 | $463,466 | 2022 |
| The Ohio State University | McNally, Kelly | Associate Professor - Clinical | CC12853 Medicine / Pediatrics | $34,637 | $0 | $34,637 | 2022 |
| The Ohio State University | Manculich, Ty | Speech - Language Pathologist - IRP 2 | CC96859 James / Rehabilitation Serv | $8,051 | $0 | $8,051 | 2022 |
| The Ohio State University | Miller, Timothy | Event Services Associate 1 | CC12642 Athletics / General | $520 | $0 | $520 | 2022 |
| The Ohio State University | Boveia, Antonio | Associate Professor (9M) | CC12389 Arts and Sciences / Physics | $110,624 | $24,265 | $134,888 | 2022 |
| The Ohio State University | Bruner, Cameron | Clinical Inst HS | CC13847 Medicine / Eye Physicians a | $62,348 | $2,000 | $64,348 | 2022 |
| The Ohio State University | Vundavalli, Shravani | Assistant Professor - Clinical | CC12853 Medicine / Pediatrics | $43,400 | $8,745 | $52,145 | 2022 |
| The Ohio State University | Cackovic, Barbara | Clinical Research Nurse 2 | CC12858 Medicine / Obstetrics and G | $32,701 | $0 | $32,701 | 2022 |
| The Ohio State University | Davis, Dana | Sterile Supply Technician 2 (HS) | CC99383 University Hospital / Centr | $24,502 | $4,210 | $28,712 | 2022 |
| The Ohio State University | Hill, Kaitlyn | Patient Care Associate/SNA (HS) | CC96711 James / Inpatient Nursing F | $11,602 | $0 | $11,602 | 2022 |
| The Ohio State University | Listermann, Lillie | Staff Nurse-B (HS) | CC96100 James / Medical Intensive C | $37,008 | $1,551 | $38,559 | 2022 |
| The Ohio State University | Jacoby, Robert | Athletic Operations Coordinator 1 | CC12642 Athletics / General | $9,439 | $410 | $9,850 | 2022 |
| The Ohio State University | Young, Sabrina | CT Technologist 2 | CC96011 James / CT Scan | $78,572 | $14,619 | $93,191 | 2023 |
| The Ohio State University | Griffith, Brandy | Associate Professor - Clinical | CC12835 Medicine / Radiology | $401,858 | $85,382 | $487,240 | 2023 |

</details>

### oh_ou: Ohio University (OH)

Notes: base salary as of 12/31/2025 plus 2025 Medicare (W-2) wages as total_pay

- Rows: 5,096; with a pay value: 5,096 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2025 | 5,096 | 1 | $60,905 | $52,343 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Ohio University | Barlag, Rebecca E | Professor of Instruction | CHEMISTRY AND BIOCHEMISTRY | $69,260 | $22,120 | $89,138 | 2025 |
| Ohio University | Cochran, Pamela A | Education Operations Coordinator | CURRICULUM OPERATIONS | $58,372 | $155 | $50,974 | 2025 |
| Ohio University | Cottrill, Josie | Instructor | BACHELOR SCIENCE NURSING | $0 | $7,176 | $7,176 | 2025 |
| Ohio University | Crabtree, Russell L | RELIEF MAINT SPEC | RELIEF MAINTENANCE | $28 | $16,523 | $66,626 | 2025 |
| Ohio University | Crist, Michael W | Certified Flight Instructor 2 | AVN - AVIATION FLIGHT | $30,533 |  | $29,223 | 2025 |
| Ohio University | Decker, Polina K | Graduate Writing Professional Tutor | WRITING COMMONS | $22 |  | $6,222 | 2025 |
| Ohio University | Degitz, Olivia J | Manager of Grants and Outreach | COMMUNITY HEALTH PROGRAMS | $59,792 | $60 | $45,928 | 2025 |
| Ohio University | Dillehay, Stephen N | MAINT REPAIR WORKER 4 | RHE FAC MGT | $27 | $3,305 | $57,848 | 2025 |
| Ohio University | Dodd, Jonathon E | Assistant Director, Operations | EVENT SERVICES | $54,653 | $120 | $46,171 | 2025 |
| Ohio University | Erlewine, Susan A | Instructor | INTERDISCIPLINARY HEALTH STUDIES | $0 | $19,520 | $19,520 | 2025 |
| Ohio University | Faires, Robin L | Instructor | ART + DESIGN | $0 | $21,800 | $21,800 | 2025 |
| Ohio University | Fox, Dennis S | Theater Director | EA DEAN | $19 |  | $78 | 2025 |
| Ohio University | Franz, Berkeley A | Professor | SOCIAL MEDICINE | $138,712 | $95,359 | $227,184 | 2025 |
| Ohio University | Gair, Stuart B | Assistant Professor of Instruction | ART + DESIGN | $54,431 | $3,619 | $56,200 | 2025 |
| Ohio University | Gilmore, Richard S | ACCESS CONTROL TECH 2 | ACCESS MANAGEMENT | $28 | $21,164 | $73,631 | 2025 |
| Ohio University | Hacker, Jneanne K | Executive Director of Housing & Residenc | HRL CENTRAL ADMINISTRATION | $154,790 |  | $146,794 | 2025 |
| Ohio University | Herrold, Heaven L | Learning Services Educational Technology | LIBRARY OPERATIONS | $60,770 | $3,000 | $55,300 | 2025 |
| Ohio University | Jacops, Todd A | Communication & External Relations Manag | DEAN FINE ARTS | $56,328 | $120 | $51,318 | 2025 |
| Ohio University | Jarrahi, Abolfazl | Campus Engagement Specialist II | CAMPUS ENGAGEMENT | $60,047 | $5,537 | $46,944 | 2025 |
| Ohio University | Lachman, Catherine M | Basic Needs Coordinator | DEAN OF STUDENTS | $21 | $1,137 | $21,287 | 2025 |

</details>

### mn: Minnesota MMB state employee salary data (Minnesota State only) (MN)

Notes: agency 'MN St Colleges & Universities'; one row per person per FY (primary record); earnings are all state positions; institution = campus from the MMB location name (department-number majority when the location is blank)

- Rows: 313,601; with a pay value: 313,601 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 1

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2011 | 22,087 | 40 | $41,264 | $38,666 |
| 2012 | 21,803 | 40 | $41,755 | $39,659 |
| 2013 | 21,614 | 40 | $41,687 | $39,552 |
| 2014 | 21,346 | 39 | $42,922 | $41,147 |
| 2015 | 21,049 | 39 | $45,368 | $42,563 |
| 2016 | 20,343 | 39 | $46,389 | $44,388 |
| 2017 | 20,050 | 39 | $47,599 | $45,661 |
| 2018 | 19,789 | 39 | $48,013 | $46,420 |
| 2019 | 19,684 | 39 | $50,829 | $48,215 |
| 2020 | 19,199 | 39 | $51,632 | $50,437 |
| 2021 | 17,979 | 39 | $55,627 | $53,360 |
| 2022 | 18,232 | 40 | $54,880 | $54,087 |
| 2023 | 17,984 | 40 | $59,423 | $57,991 |
| 2024 | 17,680 | 39 | $59,953 | $58,918 |
| 2025 | 17,427 | 39 | $64,197 | $62,787 |
| 2026 | 17,335 | 40 | $65,914 | $64,504 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Saint Paul College | Keller,Isa J | Community College Faculty | MnSCU StPaulTC PT Bi-Wkly Fac | $26,702 | $0 | $26,702 | 2012 |
| Metropolitan State University | Bahn,David L | State University Faculty | MnSCU Metro SU IFO | $108,192 | $4,494 | $112,686 | 2012 |
| Minnesota State Community and Technical  | Heiman,Megan M | Community College Faculty | MnSCU NW Detroit Lk TC Faculty | $48,353 | $0 | $48,353 | 2012 |
| Minnesota State Community and Technical  | Wegscheid,Kelli Jo | Community College Faculty | MnSCU NW Wadena TC Faculty | $19,537 | $0 | $19,537 | 2012 |
| St. Cloud State University | Butenhoff,Linda J | State University Faculty | MnSCU STC Faculty 9/12 A-H | $79,216 | $4,811 | $84,026 | 2013 |
| Inver Hills Community College | Flannigan,Susan K | Customer Svcs Specialist Princ | AFSCME Unltd and Seasl FT | $46,754 | $2,214 | $48,967 | 2013 |
| Saint Paul College | Hugo,Paul T | Food Service Supervisor | MnSCU St Paul TC 216,217,220 | $66,030 | $1,041 | $67,072 | 2013 |
| Minneapolis College | Negia,Mesfin Shumye | Community College Faculty | MnSCU Minneapolis CC Faculty | $56,937 | $0 | $56,937 | 2013 |
| St. Cloud State University | Dick,Marie L | State University Faculty | MnSCU STC Faculty 9/12 A-H | $74,445 | $0 | $74,445 | 2014 |
| Mesabi Range College | Mayer,Jeffrey L | Customized Training Rep | NHED Center Professionals | $50,073 | $5,183 | $55,256 | 2014 |
| Winona State University | Williams,Heather Ann | State University Faculty | MnSCU WIN Unclass Faculty Q-Z | $50,861 | $0 | $50,861 | 2014 |
| Normandale Community College | Johnson,Evan LK | Community College Faculty | MnSCU Normandale Fac UFT A - J | $55,992 | $500 | $56,492 | 2015 |
| Saint Paul College | Setley,Keith R | Tech College Faculty | MnSCU St Paul TC Faculty | $90,984 | $18,473 | $109,457 | 2015 |
| Saint Paul College | Shoebottom,Bonnie Lyn | Office & Admin Specialist Sr | MnSCU St Paul TC AFSCME | $46,296 | $0 | $46,296 | 2015 |
| Minnesota State System Office | Jacobs,Sonya Lee | Information Technology Spec 3 | MnSCU OOC Classified F - K | $73,825 |  | $73,825 | 2016 |
| Inver Hills Community College | Horgen,Jennifer FumikoYamada | MnSCU Academic Professional 1 | MAPE FT NE GT 6 mos sal LT 7 | $8,281 |  | $8,281 | 2016 |
| Rochester Community and Technical Colleg | Staver,Michael L | Tech College Faculty | MnSCU Rochester TC Faculty | $60,026 | $0 | $60,026 | 2017 |
| Minnesota State Community and Technical  | Grommesh,Paul Michael | Tech College Faculty | MnSCU NW Moorhead TC Hr Fac | $1,425 | $0 | $1,425 | 2017 |
| Anoka Technical College | Moeller,Heather Marie | Office & Admin Specialist Int | MnSCU Anoka Henn TC Classified | $38,401 | $0 | $38,401 | 2017 |
| Century College | Conroy,Alexandra L | Community College Faculty | MnSCU Century CTC Faculty/F | $78,274 | $5,281 | $83,555 | 2017 |

</details>

### wa: Washington state salaries 2010-2013 (data.wa.gov y3ds-rkew) (WA)

Notes: wide file unpivoted to one row per person/agency/calendar year with non-zero salary; higher-ed agency codes 352, 360-380, 600-699

- Rows: 374,836; with a pay value: 374,836 (100.0%)
- Exact duplicate rows (same original row): 1
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2010 | 91,323 | 38 | $37,064 | $30,885 |
| 2011 | 92,898 | 38 | $37,025 | $30,553 |
| 2012 | 94,203 | 37 | $37,343 | $30,420 |
| 2013 | 96,412 | 37 | $37,948 | $30,622 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Bellevue Community College | MATTSON, KJELL D | FACULTY |  |  |  | $10,844 | 2012 |
| Cascadia Community College | FAULKNER, DAVID NEIL | INSTRUCTION & CLASSROOM SUPPORT TECH 2 |  |  |  | $27,346 | 2011 |
| Central Washington University | GALINDO, JOANNA | PART TIME TEMPORARY |  |  |  | $665 | 2010 |
| Columbia Basin Community College | BLEAZARD, KERRIN AMY | FACULTY |  |  |  | $49,527 | 2012 |
| Eastern Washington University | HAHN, CHARLOTTE NULL | RPM MENTORTRNR-ICWRTC-501364 |  |  |  | $1,253 | 2013 |
| Green River Community College | DAULTON, RHONDA K | SECRETARY SENIOR |  |  |  | $30,264 | 2010 |
| Green River Community College | JOHANSEN, THOR ERIC | FACULTY |  |  |  | $18,422 | 2011 |
| Green River Community College | SLETTVET, JULIA | FACULTY |  |  |  | $68,383 | 2013 |
| Highline Community College | GARTMAN, MONICA L | FACULTY |  |  |  | $30,398 | 2012 |
| Highline Community College | SUTTON, BILLIE | FACULTY |  |  |  | $1,200 | 2010 |
| Lower Columbia Community College | SCHABOT, DANIEL E | FACULTY |  |  |  | $18,752 | 2012 |
| Bates Technical College | GORACKE, TROY A | FACULTY |  |  |  | $62,344 | 2012 |
| Shoreline Community College | DUKE, STEVEN SEAN | ASST DIR,COMM/MARKETING |  |  |  | $54,817 | 2013 |
| The Evergreen State College | MORISATO, DONALD | FACULTY NATURAL SCIENCE |  |  |  | $76,827 | 2011 |
| University of Washington | AINA, MATTHEW AFOLABI A | TEMPORARY STAFF - HELPER |  |  |  | $410 | 2011 |
| University of Washington | ANDERSON, LAURIE JOY | SENIOR LECTURER-FULL TIME |  |  |  | $29,584 | 2013 |
| University of Washington | BRIDGER, LEAH JACQUELINE | COUNSELOR, SENIOR |  |  |  | $33,135 | 2011 |
| University of Washington | BROOKS, PENNY | PATIENT CARE COORDINATOR |  |  |  | $49,848 | 2010 |
| University of Washington | BUCHANAN, REBECCA A | LECTURER PART-TIME |  |  |  | $9,372 | 2013 |
| University of Washington | COCHRAN, JOSHUA | POST BACCALAUREATE APPOINTMENT |  |  |  | $11,659 | 2013 |

</details>

### ne: University of Nebraska budgeted employees (NE)

Notes: budgeted annual salary as of July 1; fiscal_year = ending year of the FY

- Rows: 149,198; with a pay value: 149,198 (100.0%)
- Exact duplicate rows (same original row): 46
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2017 | 12,740 | 5 | $60,019 | $49,487 |
| 2018 | 13,123 | 5 | $60,972 | $50,247 |
| 2019 | 13,039 | 5 | $62,065 | $51,343 |
| 2020 | 13,332 | 5 | $63,273 | $52,488 |
| 2021 | 13,709 | 5 | $63,290 | $52,363 |
| 2022 | 13,514 | 5 | $64,508 | $53,928 |
| 2023 | 13,699 | 5 | $67,282 | $56,609 |
| 2024 | 13,988 | 5 | $69,447 | $58,356 |
| 2025 | 13,956 | 5 | $71,562 | $60,054 |
| 2026 | 14,154 | 5 | $72,090 | $60,320 |
| 2027 | 13,944 | 5 | $73,978 | $62,232 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Nebraska Medical Center | Borg, Carin | Administrator IV | Surgery | $129,770 |  |  | 2017 |
| University of Nebraska Medical Center | Carson, Steven D | Professor | Pathology/Microbiology | $153,915 |  |  | 2017 |
| University of Nebraska Medical Center | Cline, Melissa R | Tissue Procurement Coordinator | Lions Eye Bank | $40,314 |  |  | 2017 |
| University of Nebraska-Lincoln | Hansen, David J | Professor | Psychology | $152,500 |  |  | 2017 |
| University of Nebraska Omaha | Shuster, Robert D | Chairperson | Geography/Geology | $50,650 |  |  | 2017 |
| University of Nebraska-Lincoln | Cubas, Daniela | Data Collector | NE Ctr Rsrch on Youth,Fam & School | $33,376 |  |  | 2018 |
| University of Nebraska Medical Center | Nowicki, Anthony R | Lead Husbandry Technician | Comparative Medicine | $36,002 |  |  | 2018 |
| University of Nebraska-Lincoln | O'Keefe, Susan K | Accounting Assoc | Greater NE Business Center | $34,664 |  |  | 2018 |
| University of Nebraska-Lincoln | Wilken, Jacqueline K | Secretarial Spec | Athletics | $54,597 |  |  | 2018 |
| University of Nebraska Omaha | Christensen, John | Professor | College of Education | $160,000 |  |  | 2019 |
| University of Nebraska-Lincoln | Pilson, Diana J | Associate Professor | School of Biological Sciences | $26,059 |  |  | 2019 |
| University of Nebraska Medical Center | Stancil, Marvin L | Assoc Professor | Obstetrics/Gynecology | $116,689 |  |  | 2019 |
| University of Nebraska Medical Center | Bottom, Linda A | Administration Associate | Allied Health-Hlth Serv Admin Div | $46,787 |  |  | 2020 |
| University of Nebraska-Lincoln | Bright, Franklin J | Extension Asst | Agronomy & Horticulture | $37,147 |  |  | 2020 |
| University of Nebraska Medical Center | Casale, George P | Assoc Professor | Surgery-General Surgery | $100,387 |  |  | 2020 |
| University of Nebraska-Lincoln | Daly III, Edward J | Professor | Educational Psychology | $115,925 |  |  | 2020 |
| University of Nebraska-Lincoln | Edwards, Jan K | Operations Support Associate | Nebraska Center for Virology | $37,326 |  |  | 2020 |
| University of Nebraska-Lincoln | Flagel, Jill D | Coordinator, Faculty/Staff Disability Sv | Institutional Equity and Compliance | $44,145 |  |  | 2020 |
| University of Nebraska-Lincoln | Liska, Adam J | Assoc Professor | Biological Systems Engineering | $92,433 |  |  | 2020 |
| University of Nebraska Medical Center | MacDonald, Richard G | Chair Medical Students Admissions Cmte | Dean College of Medicine | $6,000 |  |  | 2020 |

</details>

### me: University of Maine System regular employee compensation (ME)

Notes: anonymous SharePoint share link (robots.txt of sharepoint tenant not applicable to share links)

- Rows: 4,449; with a pay value: 4,449 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2026 | 4,449 | 9 | $73,841 | $64,407 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Maine School of Law | Connolly, Amanda | Administrative Coordinator for Student A | PLAW | $53,560 |  |  | 2026 |
| University of Maine System (System Wide  | Andersen, Lesley E. | Software Support Analyst | SITCES | $66,522 |  |  | 2026 |
| University of Maine System (System Wide  | Byard, Renae A. | Procurement Card Administrator | SOSP | $51,501 |  |  | 2026 |
| University of Maine System (System Wide  | Olsen, Jacob A. | Senior Director of Capital Planning and  | SFAC | $135,116 |  |  | 2026 |
| University of Maine System (System Wide  | Salvesen, Michael R. | Business Intelligence (BI) Analyst I | SITCES | $60,000 |  |  | 2026 |
| University of Maine System (System Wide  | Smart, Benjamin M. | Information Technology Project Manager | SITSUPORT | $78,000 |  |  | 2026 |
| University of Maine System (System Wide  | Wandell, Sara | HR Project Asst. (Conf) CL2 | SOHR | $46,280 |  |  | 2026 |
| University of Maine | Bennett, Alyssa | Area Coordinator | OSDEN | $47,674 |  |  | 2026 |
| University of Maine | Boucher, Abigail | Administrative Specialist CL3 | ODSS | $43,867 |  |  | 2026 |
| University of Maine | Carr, Lisa D. | Indigenous Science Program Coordinator | ONAP | $37,492 |  |  | 2026 |
| University of Maine | Coghlan, Stephen M. | Associate Professor of Freshwater Fisher | OW | $105,338 |  |  | 2026 |
| University of Maine | D'Angelo, Susan M. | Senior Fiscal and Administrative Coordin | OVPRP | $60,978 |  |  | 2026 |
| University of Maine | Farooq, Saima | Senior Lecturer in Physics and Astronomy | OPS | $72,269 |  |  | 2026 |
| University of Maine | Faulkner, Mark C. | Associate Director of Facilities Managem | OFM | $106,392 |  |  | 2026 |
| University of Maine | Foltz, Ashley E. | Postdoctoral Research Associate | OPS | $52,000 |  |  | 2026 |
| University of Maine | Freme, Grahm M. | Lecturer in Construction Engineering Tec | OSET | $75,391 |  |  | 2026 |
| University of Maine | Goss, Nicole E. | Assistant Director of Theater Operations | OMCA | $59,370 |  |  | 2026 |
| University of Maine | Groce, Susan H. | Professor of Art | OAT | $134,670 |  |  | 2026 |
| University of Maine | Hall, Brenda L. | Professor of Quaternary Geology | OCLIM | $141,026 |  |  | 2026 |
| University of Maine | Kelley, Joshua B. | Associate Professor of Biochemistry | OBMMB | $92,366 |  |  | 2026 |

</details>

### nm: University of New Mexico Sunshine salary book (NM)

Notes: current snapshot (retrieved Oct 2026 = FY2027); primary position salary only

- Rows: 10,676; with a pay value: 10,676 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 10,676 | 1 | $89,920 | $69,338 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of New Mexico | Painter, Cheyenne | Resident Physician II | Grad Med Education Housestaff | $71,032 |  |  | 2027 |
| University of New Mexico | Cushnyr, Brad W. | Clinician Ed - Professor | Radiology General | $573,987 |  |  | 2027 |
| University of New Mexico | Dominguez, Alicia G. | Sr Institutional Researcher | Provost Office Staff | $77,559 |  |  | 2027 |
| University of New Mexico | Duran, Danielle K. | Data Manager | Project ECHO | $71,984 |  |  | 2027 |
| University of New Mexico | Elizabeth, Marianna | Teacher,Early Childhood | UNM Childrens Campus Administration | $55,550 |  |  | 2027 |
| University of New Mexico | Fisher, Sheri E. | Mgr,Accounting | Project ECHO | $116,997 |  |  | 2027 |
| University of New Mexico | Gaines, Karen H. | Standardized Patient | Assessment &amp; Learning | $9,880 |  |  | 2027 |
| University of New Mexico | Griego, Michael G. | Supv,Parking Services | Parking Transportation Gen Admin | $63,057 |  |  | 2027 |
| University of New Mexico | Garcia, Gena G. | Administrative Coordinator | Ofc of the University Secretary | $52,600 |  |  | 2027 |
| University of New Mexico | Perea, Jon-Michael A. | Technical Analyst 2 | IT Campus Outreach &amp; Engagement | $14,127 |  |  | 2027 |
| University of New Mexico | Humphries, Nicholas A. | Educational Developer/CTL | Center for Teaching and Learning | $69,724 |  |  | 2027 |
| University of New Mexico | Jackson, Amy S. | Associate Dean | CULLS | $135,239 |  |  | 2027 |
| University of New Mexico | Jackson, Polly | Non Credit Teacher | Continuing Education Cont Ed | $0 |  |  | 2027 |
| University of New Mexico | Reitz, Isabella R. | Resident Physician I | Grad Med Education Housestaff | $68,800 |  |  | 2027 |
| University of New Mexico | Rimi, Nayyer S. | Professional Support Intern | Provost Office Staff | $48,990 |  |  | 2027 |
| University of New Mexico | Ringenberg, Lisa | Temp Parttime Faculty | College of Nursing | $17,692 |  |  | 2027 |
| University of New Mexico | Silva, Kailey S. | Admin Assistant 1 | New Mexico Union | $39,499 |  |  | 2027 |
| University of New Mexico | Solano, Alicia T. | Strategic Support Manager | Campus Environments and Services | $131,995 |  |  | 2027 |
| University of New Mexico | Ruff, Preston B. | Programmer Analyst 1 | Pediatrics Center for Development | $56,606 |  |  | 2027 |
| University of New Mexico | Saengngoen, Jet | Educational Developer/CTL | Center for Teaching and Learning | $67,038 |  |  | 2027 |

</details>

### dc: DC Government employee salary layer (UDC rows) (DC)

Notes: point-in-time compensation rate; hourly/per-course rates kept in pay_components only; fiscal_year = DC FY2027 (snapshot Oct 2026)

- Rows: 3,156; with a pay value: 1,269 (40.2%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 1,887; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 3,156 | 1 | $90,579 | $83,291 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of the District of Columbia | Moore, Kyra | Logistics and Research |  | $59,347 |  |  | 2027 |
| University of the District of Columbia | Barry, Carrie | STAFF ASSISTANT |  | $65,035 |  |  | 2027 |
| University of the District of Columbia | Powell, Clarence | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Rich, Jasmine | ASST WOMEN'S BASKETBALL COACH |  | $47,092 |  |  | 2027 |
| University of the District of Columbia | Wellman, Briana | Associate Dean |  | $167,788 |  |  | 2027 |
| University of the District of Columbia | Fraction, Angela | COMMUNICATIONS SPECIALIST |  | $59,244 |  |  | 2027 |
| University of the District of Columbia | Gaskin, Austin | Student Success Advisor |  | $68,140 |  |  | 2027 |
| University of the District of Columbia | Lih, Jean | Student Worker |  |  |  |  | 2027 |
| University of the District of Columbia | Jackson, Campbell | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Baxter, Janel | Student Worker |  |  |  |  | 2027 |
| University of the District of Columbia | Rice, Williams | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Clayton, Okeyia | Student Worker |  |  |  |  | 2027 |
| University of the District of Columbia | Dulce, Maria Theresa | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Hobbs, Reginald | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Davey, Shauna | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Larreategui Plaza, Pablo | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Rocheleau-Lucero, Carolyn | Managing Attorney |  | $91,289 |  |  | 2027 |
| University of the District of Columbia | Campos, Gabriela | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Evans, Emily | LIBRARY TECHNICIAN |  | $65,426 |  |  | 2027 |
| University of the District of Columbia | Morgan, Kiyana | Adjunct Professor-SEIU |  |  |  |  | 2027 |

</details>

### az_asu: Arizona State University (State Press SalaryList) (AZ)

Notes: base salary by calendar year; revised files used where available

- Rows: 127,147; with a pay value: 127,147 (100.0%)
- Exact duplicate rows (same original row): 129
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2018 | 11,774 | 1 | $72,565 | $57,500 |
| 2019 | 12,251 | 1 | $74,193 | $59,025 |
| 2020 | 12,520 | 1 | $75,988 | $60,500 |
| 2021 | 12,311 | 1 | $80,602 | $64,480 |
| 2022 | 20,154 | 1 | $57,717 | $50,050 |
| 2023 | 18,990 | 1 | $66,327 | $57,408 |
| 2024 | 19,523 | 1 | $68,850 | $60,000 |
| 2025 | 19,624 | 1 | $70,120 | $61,500 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Arizona State University | Baker,Olivia | Asst to Director | Shesc | $48,000 |  |  | 2018 |
| Arizona State University | Fox,Aubrey | Academic Success Specialist | CIDSE Software Eng Poly | $45,500 |  |  | 2018 |
| Arizona State University | Griesbeck,Nicholas | Academic Success Specialist | EdPlus Success Coaching Center | $49,044 |  |  | 2018 |
| Arizona State University | Marks,Kathy | Web Application Developer (IT) | DEV Applications and Design | $74,664 |  |  | 2018 |
| Arizona State University | Onakado,Masako | Lecturer | SILC | $50,000 |  |  | 2018 |
| Arizona State University | Poitier,Yasmir | Office Specialist Sr | Univ Registrar Services Dwtn | $33,925 |  |  | 2018 |
| Arizona State University | Sarmiento,Jean | Communications Specialist | Biodesign Communications | $47,424 |  |  | 2018 |
| Arizona State University | Starr,Carolyn | Conference/Events Planner | New Interdisc Arts & Sciences | $54,000 |  |  | 2018 |
| Arizona State University | Sullivan,Frankie | Lecturer | CISA-Sci Math & Soc Sci | $50,000 |  |  | 2018 |
| Arizona State University | Dorney,Jordan | Postdoctoral Scholar | Sch of Civic & Econ Thought | $60,000 |  |  | 2019 |
| Arizona State University | Kullman,Joseph | Science Writer | Engineering Communications | $73,700 |  |  | 2019 |
| Arizona State University | Klemm,Gabriel | Director | Herberger Young Scholars Acad | $78,000 |  |  | 2019 |
| Arizona State University | Lahey,Byron | Clinical Asst Professor | School of Arts Media & Engr | $64,300 |  |  | 2019 |
| Arizona State University | Rawls,Jeffery | Exec Dir & Assoc Professor | Clinical Partnerships | $202,423 |  |  | 2019 |
| Arizona State University | Shin,Seungki | Clinical Asst Professor | Div of Teacher Prep/Tempe | $55,000 |  |  | 2019 |
| Arizona State University | Cwalinski, Pawel | Residency Classification Spec | University Registrar Services | $34,986 |  |  | 2020 |
| Arizona State University | FU, Kai | Asst Research Scientist | Sch Elect Comptr & Energy Engr | $40,000 |  |  | 2020 |
| Arizona State University | Free, Melissa | Asst Professor | English | $82,075 |  |  | 2020 |
| Arizona State University | Gwiszcz, Julianna | Research Professional FSC | LightWorks | $52,000 |  |  | 2020 |
| Arizona State University | Klinkner, Lara | Asst Director | Student Engagement Tempe | $29,273 |  |  | 2020 |

</details>

### az_ua: University of Arizona (Flourish embed) (AZ)

Notes: salary at employment FTE by fiscal year; third-party newsroom

- Rows: 107,080; with a pay value: 107,080 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2019 | 12,890 | 1 | $69,188 | $52,000 |
| 2020 | 13,077 | 1 | $66,053 | $51,162 |
| 2021 | 12,723 | 1 | $62,443 | $49,500 |
| 2022 | 12,543 | 1 | $69,619 | $55,000 |
| 2023 | 12,772 | 1 | $76,457 | $58,548 |
| 2024 | 14,795 | 1 | $80,025 | $63,000 |
| 2025 | 14,218 | 1 | $81,964 | $64,713 |
| 2026 | 14,062 | 1 | $84,133 | $66,500 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Arizona | Gates, Donald Lynn | Assistant Dean, Finance and Administrati | Information Science | $116,500 |  |  | 2026 |
| University of Arizona | Hartzell, Rebecca Ione | Associate Professor of Practice, Disabil | Disability Psychoeduc Studies | $87,744 |  |  | 2026 |
| University of Arizona | Mccann, Keith Shawn | Facilities Management and Services Worke | Parking and Transportation | $38,899 |  |  | 2026 |
| University of Arizona | Rios, Leonardo | Lecturer, English | English | $57,100 |  |  | 2026 |
| University of Arizona | Eismon, Edward A | Police Sergeant | University Police Department | $96,054 |  |  | 2025 |
| University of Arizona | Franco, Marla A | Vice President, Hispanic Serving Institu | Hispanic Serving Institution | $232,212 |  |  | 2025 |
| University of Arizona | Limon, Marco A | Materials Handler | Campus Health and Wellness | $44,157 |  |  | 2025 |
| University of Arizona | Terca, Taylor | Deputy Senior Director, Development - Co | Philanthropy & Alumni Engagmnt | $153,000 |  |  | 2025 |
| University of Arizona | Abel, Murad E | Program Chair - Professor | Forbes School Business & Tech | $105,960 |  |  | 2024 |
| University of Arizona | Ablin, Richard J | Professor, Pathology - (Research Scholar | Pathology | $21,725 |  |  | 2024 |
| University of Arizona | Daines, Michael O | Associate Professor, Pediatrics | Pediatrics | $197,123 |  |  | 2024 |
| University of Arizona | Garcia, Nestor | Technician, Research Engineering | Steward Observatory | $28,592 |  |  | 2024 |
| University of Arizona | Goddard, Stacey | Analyst, Data Solutions | ALVSCE Administration | $87,975 |  |  | 2024 |
| University of Arizona | Mayfield, Jay | Postdoctoral Research Associate I | Mathematics | $55,000 |  |  | 2024 |
| University of Arizona | Rivera, Amorette | Supervisor, Accounts Receivable | Bursar | $63,550 |  |  | 2024 |
| University of Arizona | Zerihun, Dawit | Researcher/Scientist V | Environmental Science-Res | $89,910 |  |  | 2024 |
| University of Arizona | Cowen, Stephen Leigh | Associate Professor, Psychology | Psychology | $108,731 |  |  | 2023 |
| University of Arizona | Danehy, Alexander B | Web Developer/Programmer | Steward Observatory | $61,365 |  |  | 2023 |
| University of Arizona | Herman, Eliot M | Professor, Plant Sciences | School of Plant Sciences-Res | $163,380 |  |  | 2023 |
| University of Arizona | Kaye, Yvonne | Extension Program Assistant | Navajo County Office | $30,838 |  |  | 2023 |

</details>

### ks: Kansas state payroll 2021-2025 (Kansas Policy Institute / KansasOpenGov) (KS)

Notes: fetched with curl (site returned 403 to the python client; robots.txt allows all)

- Rows: 122,263; with a pay value: 122,263 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2021 | 24,153 | 7 | $52,022 | $44,375 |
| 2022 | 23,588 | 7 | $54,749 | $46,920 |
| 2023 | 24,150 | 7 | $57,893 | $50,385 |
| 2024 | 25,049 | 7 | $60,390 | $52,327 |
| 2025 | 25,323 | 7 | $62,905 | $54,751 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Wichita State University | Grover, Travis Richard | Lecturer |  |  |  | $1,200 | 2021 |
| Emporia State University | Bowen, Melodi J | Administrative Specialist |  |  |  | $31,292 | 2021 |
| Emporia State University | Howard, Jody K | Lecturer |  |  |  | $28,257 | 2021 |
| Pittsburg State University | Pross, Christopher L | Assistant Professor |  |  |  | $91,114 | 2021 |
| Wichita State University | Gates, Ryan | Lecturer |  |  |  | $6,830 | 2023 |
| Kansas State University | Tebbutt, Austin H | Landscape Technician I |  |  |  | $19,766 | 2021 |
| Kansas State University | Wilson, Jennifer R | Manager IV, Adm & Managerial |  |  |  | $95,838 | 2021 |
| Kansas State University | Kimbrough, Doreen S | Office Specialist IV |  |  |  | $46,274 | 2021 |
| University of Kansas | Outhier, Sara Diane | Assistant Librarian |  |  |  | $54,894 | 2021 |
| University of Kansas | Tyne, Intisar Ameen | Lecturer |  |  |  | $13,676 | 2021 |
| University of Kansas Medical Center | Herre, Rochelle Menard | Assistant Professor |  |  |  | $57,993 | 2021 |
| University of Kansas Medical Center | Goldsich, Jana Elizabeth | Assistant Professor |  |  |  | $17,654 | 2021 |
| University of Kansas Medical Center | Seymour, Leah | Clinical Research Assistant |  |  |  | $5,656 | 2021 |
| Wichita State University | Gurss, Makenzie Ryan Milner | Lecturer |  |  |  | $7,100 | 2021 |
| Wichita State University | Torrey, Emily Louise | Temporary Worker - UPS |  |  |  | $4,680 | 2021 |
| University of Kansas Medical Center | Dwyer, Timothy | Assistant Professor |  |  |  | $25,820 | 2022 |
| University of Kansas | Moody, Jennifer M | Assistant Researcher Senior |  |  |  | $44,132 | 2022 |
| Fort Hays State University | Schartz, Shane | Associate Professor |  |  |  | $137,415 | 2022 |
| Pittsburg State University | Wehrman, Mary J | Coordinator |  |  |  | $53,076 | 2022 |
| Pittsburg State University | Hartley, Kristine M | Development Specialist |  |  |  | $45,667 | 2022 |

</details>

### nj: NJ pension membership (active members, higher-ed employers) (NJ)

Notes: pension-enrolled employees only (excludes ABP faculty); salary as reported to the pension system as of 2026-06-30; no title

- Rows: 12,922; with a pay value: 12,922 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2026 | 12,922 | 30 | $63,454 | $58,608 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Rowan University | MASTER, KELLY R |  | STATEWIDE | $53,880 |  |  | 2026 |
| Rowan University | VEACOCK, GARY S |  | STATEWIDE | $79,694 |  |  | 2026 |
| Rowan University | WAMPLER, KIMBERLY |  | STATEWIDE | $78,001 |  |  | 2026 |
| New Jersey City University | SINCLAIR, WALTER |  | STATEWIDE | $40,454 |  |  | 2026 |
| Kean University | GALLAGHER, KATHERINE A |  | STATEWIDE | $164,323 |  |  | 2026 |
| Kean University | HOBSON, RICHARD |  | STATEWIDE | $26,100 |  |  | 2026 |
| William Paterson Univ of Nj | KAVAK, GEORGE |  | STATEWIDE | $66,617 |  |  | 2026 |
| William Paterson Univ of Nj | RUSSO, PATRICIA |  | STATEWIDE | $19,657 |  |  | 2026 |
| Montclair State University | FRAGA, JOSE |  | STATEWIDE | $26,100 |  |  | 2026 |
| Montclair State University | TURRIN, JOSEPH E |  | STATEWIDE | $28,275 |  |  | 2026 |
| The College of New Jersey | ANDREWS, MICHELLE M |  | STATEWIDE | $62,510 |  |  | 2026 |
| The College of New Jersey | JASMIN, LANDON E |  | STATEWIDE | $89,857 |  |  | 2026 |
| The College of New Jersey | JONES, CARLA Y |  | STATEWIDE | $56,753 |  |  | 2026 |
| Ramapo College of New Jersey | HERTENSTEIN, CRAIG L |  | STATEWIDE | $63,496 |  |  | 2026 |
| Stockton University | GILRANE, THOMAS C |  | STATEWIDE | $72,095 |  |  | 2026 |
| Stockton University | KLEINSMITH, WARREN |  | STATEWIDE | $190,496 |  |  | 2026 |
| Rutgers University | ALVARADO, JULIO |  | STATEWIDE | $35,818 |  |  | 2026 |
| Rutgers University | BECKLEY, VICTOR |  | STATEWIDE | $41,643 |  |  | 2026 |
| Rutgers University | COLDERO, THOMAS |  | STATEWIDE | $58,574 |  |  | 2026 |
| Rutgers University | DALESSANDRO, ANTHONY |  | STATEWIDE | $41,946 |  |  | 2026 |

</details>

### ok: Oklahoma OMES state payroll (higher-ed agencies), FY2026 (OK)

Notes: monthly payment lines summed per agency + last name + initials per month (FY2026 files 2025-07..2026-06); names are initials only, so persons are ambiguous

- Rows: 394,645; with a pay value: 394,645 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 8

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2026 | 394,645 | 56 | $5,474 | $4,162 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Oklahoma | Osburn, A D |  |  | $0 | $3,300 | $3,300 | 2026 |
| University of Oklahoma | Reynolds, C R |  |  | $0 | $2,574 | $2,574 | 2026 |
| University of Oklahoma | Joseph, S A |  |  | $0 | $3,500 | $3,500 | 2026 |
| University of Oklahoma | Eads, C R |  |  | $0 | $6,826 | $6,826 | 2026 |
| Langston University | Portugal, I R |  |  | $0 | $4,199 | $4,199 | 2026 |
| Univ. of Central Okla. | LIEPINS, S E |  |  | $0 | $240 | $240 | 2026 |
| Univ.of Science & Arts of Ok | Lynn, E G |  |  | $0 | $2,833 | $2,833 | 2026 |
| Northern Oklahoma College | Rogers, D G |  |  | $0 | $2,750 | $2,750 | 2026 |
| Okla. City Community College | Stevenson, M |  |  | $0 | $7,997 | $7,997 | 2026 |
| Northeastern State University | Gerk, M J |  |  | $0 | $4,167 | $4,167 | 2026 |
| Univ. of Okla. Health Sciences Center | Noor, N |  |  | $0 | $9,102 | $9,102 | 2026 |
| Oklahoma State University | Pickle, J D |  |  | $0 | $8,750 | $8,750 | 2026 |
| Tulsa Community College | Tarver, E N |  |  | $0 | $16,703 | $16,703 | 2026 |
| Univ. of Central Okla. | TOOMBS, M L |  |  | $0 | $1,050 | $1,050 | 2026 |
| Oklahoma State University | Dearsmith, D V |  |  | $0 | $2,649 | $2,649 | 2026 |
| University of Oklahoma | McElhaney, G K |  |  | $0 | $772 | $772 | 2026 |
| Rogers State University | Ewing, K L |  |  | $0 | $2,520 | $2,520 | 2026 |
| Univ. of Okla. Health Sciences Center | Ho, W T |  |  | $0 | $7,673 | $7,673 | 2026 |
| Rogers State University | Hocutt, W J |  |  | $0 | $6,083 | $6,083 | 2026 |
| Oklahoma State University | Stanford, J L |  |  | $0 | $3,264 | $3,264 | 2026 |

</details>

### il_graybook: University of Illinois Board of Trustees Gray Book 2026-27 (IL)

Notes: campus-level pages only (unit pages repeat the same rows); one row per job line as published (multi-job employees have several rows); base_pay = proposed FY2027 salary; present FY2026 salary in pay_components

- Rows: 21,515; with a pay value: 21,515 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 21,515 | 4 | $82,551 | $76,512 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Illinois Chicago | Kersten, Sandra K | CLIN ASST PROF | 318 - Biomed & Health Info Sciences | $44,358 |  |  | 2027 |
| University of Illinois Chicago | Abogado, Maitha C | SR ACAD ADVR | 871 - Disability & Human Developmen | $83,801 |  |  | 2027 |
| University of Illinois Chicago | Sufian, Sandra M | PROF | 871 - Disability & Human Developmen | $0 |  |  | 2027 |
| University of Illinois Chicago | Alford, Simon T | PROF (RT) | 387 - Anatomy and Cell Biology | $322,306 |  |  | 2027 |
| University of Illinois Chicago | Kotche, Miiri Ann | CLIN PROF | 857 - Medical Education | $0 |  |  | 2027 |
| University of Illinois Chicago | Aguilar Lugo, Braulio | VST RES SPEC | 386 - Physiology and Biophysics | $44,327 |  |  | 2027 |
| University of Illinois Chicago | Dos Santos Oliveira, Suellen DArc | ASST PROF (RT) | 258 - Anesthesiology | $105,080 |  |  | 2027 |
| University of Illinois Chicago | Danciu, Oana Cristina | PHYSN SURG | 586 - Medicine | $230,968 |  |  | 2027 |
| University of Illinois Chicago | Park, Gye Young | PHYSN SURG | 586 - Medicine | $41,028 |  |  | 2027 |
| University of Illinois Chicago | Alsberg, Eben | PROF | 773 - Orthopaedic Surgery | $0 |  |  | 2027 |
| University of Illinois Chicago | Glassgow, Anne Elizabeth | RES ASSOC PROF | 905 - Pediatrics | $0 |  |  | 2027 |
| University of Illinois Chicago | Twohig, Matthew H | CLIN ASSOC PROF | 397 - Health Sciences Ed - Rockford | $16,640 |  |  | 2027 |
| University of Illinois Chicago | Haley, Colin Michael | CLIN PROF | 338 - Dental Clinics | $0 |  |  | 2027 |
| University of Illinois Chicago | Nouneh, Roger | CLIN ASST PROF | 735 - Periodontics | $7,778 |  |  | 2027 |
| University of Illinois Chicago | Bentel, Michael J | ASST PROF | 737 - Civil, Matls & Env Engineerin | $111,810 |  |  | 2027 |
| University of Illinois Chicago | Gunipe, Prasanth Kumar | POSTDOC RES ASSOC | 323 - Mechanical & Industrial Engr | $63,000 |  |  | 2027 |
| University of Illinois Chicago | Roitman, Mitchell Franklin | PROG DIR, GRAD PROG NEUROSCI | 480 - Graduate Admin | $7,500 |  |  | 2027 |
| University of Illinois Chicago | Blumenthal, Rachel | APRN CNP | 398 - Nursing | $137,280 |  |  | 2027 |
| University of Illinois Chicago | Stanescu, Izabela M | DIR HLTHCARE SUSTAINABLTY OPER | 466 - Support and General Services | $149,379 |  |  | 2027 |
| University of Illinois Chicago | Lubotsky, Darren Howard | ASSOC PROF | 525 - Economics | $218,743 |  |  | 2027 |

</details>

### sc: SC Dept of Administration state salaries (colleges and universities) (SC)

Notes: AIKEN TECHNICAL COLLEGE: 5 pages concatenated CENTRAL CAROLINA TECH COLLEGE: 4 pages concatenated CLEMSON UNIVERSITY: 149 pages concatenated COASTAL CAROLINA UNIVERSITY: 47 pages concatenated DENMARK TECHNICAL COLLEGE: 2 pages concatenated FLO DARLINGTON TECH COLLEGE: 7 pages concatenated FRANCIS MARION UNIVERSITY: 13 pages concatenated GREENVILLE TECHNICAL COLLEGE: 22 pages concatenated HORRY GEORGETOWN TECH COLLEGE: 14 pages concatenated LANDER UNIVERSITY: 13 pages concatenated MEDICAL UNIVERSITY OF SC: 107 pages concatenated MIDLANDS TECHNICAL COLLEGE: 22 pages concatenated NORTHEASTERN TECHNICAL COLLEGE: 3 pages concatenated ORANGEBURG CALHOUN TEC COLLEGE: 5 pages concatenated PIEDMONT TECHNICAL COLLEGE: 9 pages concatenated SPARTANBURG TECHNICAL COLLEGE: 13 pages concatenated TECH COLL OF LOW COUNTRY: 5 pages concatenated THE CITADEL: 22 pages concatenated TRI COUNTY TECHNICAL COLLEGE: 13 pages concatenated TRIDENT TECHNICAL COLLEGE: 23 pages concatenated UNIVERSITY OF CHARLESTON: 49 pages concatenated UNIVERSITY OF SOUTH CAROLINA: 244 pages concatenated WILLIAMSBURG TECHNICAL COLLEGE: 2 pages concatenated WINTHROP UNIVERSITY: 20 pages concatenated YORK TECHNICAL COLLEGE: 9 pages concatenated

- Rows: 20,264; with a pay value: 20,264 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 20,264 | 25 | $92,996 | $77,881 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| The Citadel | NAVARRO, JORDANA | ASSOCIATE PROFESSOR |  |  |  | $98,934 | 2027 |
| The Citadel | WRIGHT, CHRISTOPHER | ASSOCIATE PROFESSOR |  |  |  | $80,121 | 2027 |
| The Citadel | PINNEY, JACKSON | LABORATORY TECHNOLOGIST I |  |  |  | $61,870 | 2027 |
| Clemson University | SUN, YA PING | PROFESSOR |  |  |  | $199,612 | 2027 |
| Clemson University | DUCHOWSKI, ANDREW | PROFESSOR |  |  |  | $171,901 | 2027 |
| Clemson University | DENHAM, BRYAN | NAMED PROFESSOR |  |  |  | $110,691 | 2027 |
| Clemson University | TSAI, KATE | ASSISTANT PROFESSOR |  |  |  | $97,187 | 2027 |
| Clemson University | MASTROIANNI, DOMINIC | ASSOCIATE PROFESSOR |  |  |  | $85,313 | 2027 |
| Clemson University | FISCHER, MATTHEW | EXTENSION ASSOCIATE |  |  |  | $81,541 | 2027 |
| Clemson University | SNIPES, ZACHARY | SENIOR EXTENSION AGENT |  |  |  | $76,012 | 2027 |
| Clemson University | NAVIS, MICHELLE | PROGRAM MANAGER I |  |  |  | $72,828 | 2027 |
| Clemson University | HART, ELIZABETH | PROGRAM COORDINATOR II |  |  |  | $64,314 | 2027 |
| Clemson University | HEAD, SANDRA | ADMINISTRATIVE COORDINATOR I |  |  |  | $60,286 | 2027 |
| Clemson University | DOWELL, JENNIFER | ACCOUNTANT/FISCAL ANALYST II |  |  |  | $58,101 | 2027 |
| University of Charleston | DE BURON, ISAURE | PROFESSOR |  |  |  | $114,150 | 2027 |
| University of Charleston | BLOUIN, CHRISTOPHER | NETWORK ADMINISTRATOR |  |  |  | $64,015 | 2027 |
| Coastal Carolina University | THOMPSON, AMBERLY | APPLICATION DEVELOPER III |  |  |  | $96,031 | 2027 |
| Coastal Carolina University | TERRANOVA, ANDREW | ASSOCIATE PROFESSOR |  |  |  | $95,780 | 2027 |
| Coastal Carolina University | FIELDING, RUSSELL | ASSOCIATE PROFESSOR |  |  |  | $88,649 | 2027 |
| Coastal Carolina University | JAIN, DIPALI | ATHLETICS ADMINISTRATOR |  |  |  | $82,000 | 2027 |

</details>

### md: University of Maryland, College Park (Diamondback salary guide API) (MD)

Notes: API count=10097; fetched 10097 rows over 1010 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10213; fetched 10213 rows over 1022 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10253; fetched 10253 rows over 1026 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10286; fetched 10286 rows over 1029 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10425; fetched 10425 rows over 1043 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10478; fetched 10478 rows over 1048 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10568; fetched 10568 rows over 1057 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10604; fetched 10604 rows over 1061 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10683; fetched 10683 rows over 1069 pages (10/page); api.dbknews.com has no robots.txt (404) API count=10963; fetched 10963 rows over 1097 pages (10/page); api.dbknews.com has no robots.txt (404) API count=11229; fetched 11229 rows over 1123 pages (10/page); api.dbknews.com has no robots.txt (404) API count=12091; fetched 12091 rows over 1210 pages (10/page); api.dbknews.com has no robots.txt (404) API count=12501; fetched 12501 rows over 1251 pages (10/page); api.dbknews.com has no robots.txt (404)

- Rows: 140,391; with a pay value: 140,386 (100.0%)
- Exact duplicate rows (same original row): 23
- Empty name: 5; no numeric pay: 5; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2013 | 12,091 | 1 | $53,842 | $47,886 |
| 2014 | 12,501 | 1 | $56,131 | $49,842 |
| 2015 | 10,213 | 1 | $72,227 | $61,132 |
| 2016 | 10,097 | 1 | $72,370 | $60,948 |
| 2017 | 10,286 | 1 | $74,345 | $62,644 |
| 2018 | 10,425 | 1 | $74,475 | $63,000 |
| 2019 | 10,604 | 1 | $76,098 | $64,566 |
| 2020 | 10,683 | 1 | $79,793 | $67,902 |
| 2021 | 10,253 | 1 | $83,164 | $70,457 |
| 2022 | 10,478 | 1 | $90,904 | $76,508 |
| 2023 | 10,568 | 1 | $94,936 | $79,950 |
| 2024 | 11,229 | 1 | $98,205 | $82,669 |
| 2025 | 10,963 | 1 | $107,778 | $92,067 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Maryland, College Park | Diaz, Miriam R. | Housekeeper | VPAF-FM-B&LM-Building & Landscape M | $31,193 |  |  | 2015 |
| University of Maryland, College Park | Inoue, Makiko | Senior Lecturer | ARHU-School of Languages, Literatur | $40,108 |  |  | 2015 |
| University of Maryland, College Park | O'Connell, Kenneth J. | Lecturer | ENGR-Civil & Enviromental Engr | $15,052 |  |  | 2015 |
| University of Maryland, College Park | Song, Wenxia | Assoc Prof | CMNS-Cell Biology & Molecular Genet | $101,937 |  |  | 2015 |
| University of Maryland, College Park | Zeeger, Tracy Marie | Lecturer | SPHL-Behavioral & Community Health | $53,069 |  |  | 2015 |
| University of Maryland, College Park | Carocci, Patricia E. | Asst Dean | VPUR-Development | $208,285 |  |  | 2016 |
| University of Maryland, College Park | Feijo, Jose A. | Prof | CMNS-Cell Biology & Molecular Genet | $211,801 |  |  | 2016 |
| University of Maryland, College Park | Laskowski, Michael C. | Prof | CMNS-Mathematics | $131,385 |  |  | 2016 |
| University of Maryland, College Park | Quinlan, Elizabeth M. | Prof | CMNS-Biology | $120,000 |  |  | 2016 |
| University of Maryland, College Park | Waks, Edo | Assoc Prof | ENGR-Electrical & Computer Engineer | $57,863 |  |  | 2016 |
| University of Maryland, College Park | Wright, Julie | Head Coach | PRES-Intercollegiate Athletics | $96,900 |  |  | 2016 |
| University of Maryland, College Park | Ferrara, Elizabeth C | Res Assoc | CMNS-Astronomy | $119,340 |  |  | 2013 |
| University of Maryland, College Park | Gonzalez, Fidel Enrique | IT Support Spec | VPSA-Dining Services | $46,023 |  |  | 2013 |
| University of Maryland, College Park | Stevens, L Luminita | Lecturer | BSOS-Economics | $119,340 |  |  | 2013 |
| University of Maryland, College Park | Brown, Janie L. | Res Coor | CMNS-Biology | $61,876 |  |  | 2014 |
| University of Maryland, College Park | Preece, Jennifer J. | Prof And Dean | INFO-College of Information Studies | $231,060 |  |  | 2014 |
| University of Maryland, College Park | Vinson, Mark Douglas | Fac Res Asst | VPR-VP Research | $55,450 |  |  | 2014 |
| University of Maryland, College Park | Chicas, Hector A. | Auto Serv Mech | VPAF- Business Services | $45,821 |  |  | 2017 |
| University of Maryland, College Park | Dwyer, Daniel J | Asst Prof | CMNS-Cell Biology & Molecular Genet | $60,943 |  |  | 2017 |
| University of Maryland, College Park | Farquhar, James | Prof | CMNS-Earth System Science Interdisc | $77,763 |  |  | 2017 |

</details>

### ne_cc: Nebraska community colleges (Flatwater Free Press Nebraska Public Payrolls) (NE)

Notes: Metropolitan Community College: X-WP-Total=2380; fetched 2380 Mid-Plains Community College: X-WP-Total=376; fetched 376 Southeast Community College: X-WP-Total=714; fetched 714

- Rows: 3,470; with a pay value: 3,470 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 47; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2024 | 2,380 | 1 | $35,587 | $16,508 |
| None | 1,090 | 2 | $56,652 | $61,694 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Southeast Community College | Hansen, Shannon | Instructor Welding Technology |  |  |  | $95,259 | None |
| Southeast Community College | Iacono, Leo | Instructor Humanities |  |  |  | $74,047 | None |
| Southeast Community College | Isemann, Elizabeth | Instructor Social Science |  |  |  | $85,667 | None |
| Southeast Community College | Klinginsmith, Shane | Instructor Energy Generation Operations |  |  |  | $63,597 | None |
| Southeast Community College | Luebbe, Christopher | Instructor Welding Technology |  |  |  | $70,140 | None |
| Southeast Community College | Pallas-Duncan, Susan | Instructor Business |  |  |  | $92,051 | None |
| Southeast Community College | Putnam, Andrew | Instructor Electrical & Electromechanica |  |  |  | $60,000 | None |
| Southeast Community College | Stark, Kyla | Instructor Food Service Hospitality |  |  |  | $65,034 | None |
| Southeast Community College | Varley, Trevor | College Advisor/Athletic Coach (Baseball |  |  |  | $52,730 | None |
| Southeast Community College | McCown, Isaac | Custodian I |  |  |  | $34,590 | None |
| Southeast Community College | Johnson, John | Campus Store Customer Services Associate |  |  |  | $42,557 | None |
| Southeast Community College | Ernst, Aaron | Public Safety Officer |  |  |  | $45,760 | None |
| Southeast Community College | Yeager, Seanna | Library Resource Center Specialist |  |  |  | $55,910 | None |
| Mid-Plains Community College | Abbott, Brian | Maintenance Technician | Physical Resources |  |  | $44,642 | None |
| Mid-Plains Community College | Case, Grant Allen | MCC Golf Head Coach | Athletics |  |  | $18,396 | None |
| Mid-Plains Community College | Erickson, Kade Montgomery | Asst Director of Residence Life | Student Services |  |  | $52,529 | None |
| Mid-Plains Community College | Strong, Pam | Outreach Administrative Assistant | Outreach |  |  | $40,301 | None |
| Metropolitan Community College | Foster, Deborah | Continuing Education Instructor | Community & Workforce Education-JM |  |  | $210 | 2024 |
| Metropolitan Community College | Bauermeister, Hannah | Arts Model | Art Labratories -JM |  |  | $240 | 2024 |
| Metropolitan Community College | Freemont, Korina | Re-entry Peer Mentor | Re-entry Services-JM |  |  | $259 | 2024 |

</details>

### mo_stl: St. Louis Post-Dispatch Public Pay 2026 (Missouri universities and colleges) (MO)

Notes: Missouri University of Science and Technology: 124 departments, 127 pages concatenated St. Charles Community College: 84 departments, 85 pages concatenated St. Louis Community College: 147 departments, 149 pages concatenated University of Missouri-Columbia: 398 departments, 470 pages concatenated University of Missouri Health Care: 465 departments, 488 pages concatenated University of Missouri-Kansas City: 184 departments, 201 pages concatenated University of Missouri-St. Louis: 111 departments, 114 pages concatenated University of Missouri System: 34 departments, 37 pages concatenated

- Rows: 22,951; with a pay value: 22,951 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2025 | 22,951 | 8 | $86,429 | $65,828 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Missouri Health Care | Kahle, Claire Alexandra | Speech/Lang Pathologist | Peds OP |  |  | $72,186 | 2025 |
| University of Missouri Health Care | Santiago, Thelma V | Supv Housekeeping | Housekeeping |  |  | $52,690 | 2025 |
| University of Missouri Health Care | Atteberry, Kelsey Ryan | Emrg Med Techn | Ambulance Service |  |  | $23,806 | 2025 |
| University of Missouri Health Care | Rodgers, Elton Reid | Emrg Med Techn-Param, Amb Ser | Ambulance Service |  |  | $61,475 | 2025 |
| University of Missouri Health Care | Meiners, Elizabeth Anna | Nurse, Or/Recovery | Post Anesthesia Care Unit |  |  | $78,096 | 2025 |
| University of Missouri Health Care | Crane, Michelle Lisa | Reimbursement Ast | Financial Clearance Hospital |  |  | $59,577 | 2025 |
| University of Missouri Health Care | Orscheln, Andrew | Med Lab Sci Cert, Sr, Crmc (L) | Lab JC |  |  | $83,762 | 2025 |
| University of Missouri Health Care | Rieves, Devyn Ann | Nurse, Staff II Inpatient, UH | Maternal Newborn Unit |  |  | $108,134 | 2025 |
| University of Missouri Health Care | Moshy, Hyasintha James | Care Team Assoc - Clin, Crmc | Progressive Care Unit JC |  |  | $48,371 | 2025 |
| University of Missouri Health Care | Slavens, Andrea Nicole | Nurse, Clinic Triage | Battle Ave Med Building Clinics |  |  | $75,718 | 2025 |
| University of Missouri Health Care | Redington, Angela Lynn | Nurse, Clinic | OBGYN Clinic |  |  | $86,346 | 2025 |
| University of Missouri Health Care | Gardner, Mary Elizabeth | Mgr, Environmental Svcs | Housekeeping JC |  |  | $84,056 | 2025 |
| University of Missouri Health Care | Allen, Julie M | Occl Therapist | Physical Therapy JC |  |  | $111,981 | 2025 |
| University of Missouri Health Care | Hinton, Celia Marie | Nutrition Associate | DNS JC |  |  | $43,218 | 2025 |
| University of Missouri Health Care | Shaw, Joshua A | Supv Skilled Trades-H | Engineering Admin & Support |  |  | $74,679 | 2025 |
| University of Missouri Health Care | Stansbeary, Sarah L | Chargemaster Spclst | Revenue Integrity Chargemaster |  |  | $72,007 | 2025 |
| University of Missouri Health Care | Armstrong, David Andrew | Certified Med Assistant | Woodrail Int Med Clinic |  |  | $48,421 | 2025 |
| University of Missouri System Office | White, Melissa B | Network Engineer-Princpl | MOREnet |  |  | $101,189 | 2025 |
| University of Missouri System Office | Pico-Vazquez, Sergio Miguel | Business Tech Analyst-Speclst | VP Information Systems |  |  | $60,618 | 2025 |
| University of Missouri System Office | Wiggins, Kathryn Elizabeth | Human Resources Consultnt Sr | Compensation & Classification |  |  | $64,406 | 2025 |

</details>

### il_stl: St. Louis Post-Dispatch Public Pay 2026 (SIUE and University of Illinois) (IL)

Notes: Southern Illinois University Edwardsville: 119 departments, 130 pages concatenated University of Illinois Administration: 50 departments, 60 pages concatenated University of Illinois-Chicago: 333 departments, 625 pages concatenated University of Illinois-Springfield: 88 departments, 89 pages concatenated University of Illinois-Urbana-Champaign: 295 departments, 606 pages concatenated

- Rows: 44,841; with a pay value: 44,841 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2025 | 44,841 | 5 | $84,157 | $64,602 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Illinois System Offices | Myers, Heather | Sr Proj Coord | Admin Info Technology Services |  |  | $101,125 | 2025 |
| University of Illinois System Offices | Peters, Howard A | Sr Expert Advisor Ihh | Office Medicaid Innovation |  |  | $113,761 | 2025 |
| University of Illinois Chicago | Barranco, Lara | Staff Nrs 1 (Lch) | Nursing |  |  | $90,130 | 2025 |
| University of Illinois Chicago | Santos, Ivy Ethel Lara | Adminv Nrs 1 (Lch) | Nursing |  |  | $173,540 | 2025 |
| University of Illinois Chicago | Stephen, Rangitha | Ecg Techn/Telemetry Techn(Lch) | Nursing |  |  | $76,809 | 2025 |
| University of Illinois Chicago | Goldenberg, Sarah E | Phys Therapy Spec (Lch) | Ancillary Services |  |  | $109,956 | 2025 |
| University of Illinois Chicago | Lukas, Pamela V | Xh Staff Nrs (Lch) | Ancillary Services |  |  | $57,944 | 2025 |
| University of Illinois Chicago | Bhagavan, Monica | Resident | Graduate Medical Education |  |  | $37,760 | 2025 |
| University of Illinois Chicago | Qazi, Aisha | Res Spec | Medicine |  |  | $57,190 | 2025 |
| University of Illinois Chicago | Raj, Usha | Prof (RT) | Pediatrics |  |  | $367,650 | 2025 |
| University of Illinois Chicago | Parde, Natalie | Assoc Prof | Computer Science |  |  | $223,295 | 2025 |
| University of Illinois Chicago | Bao, Qing | Postdoc Res Assoc | Pharmaceutical Sciences |  |  | $53,213 | 2025 |
| University of Illinois Chicago | Tran, Sharon | Grad Tch Assistant | Biological Sciences |  |  | $22,806 | 2025 |
| University of Illinois Chicago | Sandoval, Alex | Pharm Techn 3 (LC) | Ambulatory Pharmacy Services |  |  | $40,440 | 2025 |
| University of Illinois Chicago | Evans, Kathryn Elizabeth | Grad Tch Assistant | History |  |  | $29,200 | 2025 |
| University of Illinois Chicago | Delgado, Christina | Fieldwork Instr | Educational Psychology |  |  | $85,156 | 2025 |
| University of Illinois Chicago | Bibo, Courtney Garland | Res Assoc II | Practice, Policy & Partnerships |  |  | $43,430 | 2025 |
| University of Illinois Chicago | Martinson, Katherine A | Sr Res Spec | Practice, Policy & Partnerships |  |  | $101,207 | 2025 |
| University of Illinois Chicago | Partyka, Keith J | Acad Advr | School of Public Health Admin |  |  | $58,113 | 2025 |
| University of Illinois Chicago | Maza, Ramona R | Dir Donor Acquis & Engagmt | Office Institutional Advancement |  |  | $126,739 | 2025 |

</details>

### mo_um: University of Missouri System annual salary reports (MOspace PDFs) (MO)

Notes: MOspace item 18938a72-809a-4e64-8ddf-b3f7c096965f (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item 1e9381e2-0452-4deb-b54c-ff632df930c0 (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item 37ebbe39-1e09-44d7-91a2-7b5802c98e0a (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item 4d5f1951-e124-4d21-9258-529bd2a1ede5 (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item 5ce773f4-d4c4-421e-8056-7d07478632b3 (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item 7907c966-09ee-4fec-981e-6b8310172ffc (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item 97069164-c1cb-40f5-8d8d-2db4c1a78a9b (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated MOspace item cf80f345-4957-48a1-a734-8cdc9b442653 (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated

- Rows: 193,293; with a pay value: 133,764 (69.2%)
- Exact duplicate rows (same original row): 7
- Empty name: 0; no numeric pay: 59,529; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2014 | 24,798 | 4 | $68,464 | $56,541 |
| 2015 | 23,725 | 7 | $70,665 | $58,000 |
| 2016 | 23,691 | 6 | $71,158 | $58,385 |
| 2018 | 23,748 | 4 | $49,797 | $40,118 |
| 2019 | 23,676 | 4 | $79,511 | $64,107 |
| 2020 | 23,882 | 4 | $80,309 | $64,674 |
| 2023 | 24,085 | 6 | $62,907 | $50,000 |
| 2026 | 25,688 | 6 | $74,967 | $60,088 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Missouri | Banning,Adam D | SYST ADMINR-EXPRT | Ag Econ - CARES | $56,000 |  |  | 2014 |
| University of Missouri | Cupp,Kyle Joseph | PATIENT SVC REP | Registration |  |  |  | 2014 |
| University of Missouri | Dunn JR,James E | FOOD SVC WRKR IV | Campus Dining Services |  |  |  | 2014 |
| University of Missouri | Eller,Kristen Marie | NURSE, STAFF NOW III | Staffing Support Services |  |  |  | 2014 |
| University of Missouri | Evans,Debora L | SERVICE REP III | Veterinary Medicine & Surgery |  |  |  | 2014 |
| University of Missouri | Murray,Lindsay Darsnaun Zaire | TEMP ADMIN/PROFL | Student Services |  |  |  | 2014 |
| University of Missouri | Perry,Lana J | EVENTS AST | Intercollegiate Athletics |  |  |  | 2014 |
| University of Missouri | Stoops,Janet L | RESRCH SPCLST | Research Reactor | $38,601 |  |  | 2014 |
| University of Missouri-Kansas City | McGee Jr,Robert Eugene | SECURITY OFFICER | Admin Affairs UMKC Police |  |  |  | 2014 |
| University of Missouri-Kansas City | Schlichting,Frederick W | ASOC HEAD COACH | Intercollegiate Athletics | $47,854 |  |  | 2014 |
| University of Missouri | Crawford,Emily R | PROF, AST | Ed Leadership & Pol Analysis | $68,227 |  |  | 2015 |
| University of Missouri | Melton,Cenitoria Latreice | ACADEMIC ADVISOR | Dean of Graduate School | $34,400 |  |  | 2015 |
| MU Health Care | Jamieson,Bobbi Jo | NURSE, STAFF II | Emergency Services |  |  |  | 2015 |
| University of Missouri-Kansas City | Bowles,Douglas | RESRCH ASOC | Economics | $70,000 |  |  | 2015 |
| Missouri University of Science and Techn | Goad,Jonathan Giles | MEDIA PRODUCER I | Video Communication Center |  |  |  | 2015 |
| Missouri University of Science and Techn | Shaller,David Allyn | EMERITUS | Engineering Education Center | $23,625 |  |  | 2015 |
| University of Missouri | Benson,Heather Renee | ARCHITECTURAL ASSOCIATE | Space Planning | $39,591 |  |  | 2016 |
| University of Missouri | Gates,Justin | EVENT ASSISTANT I | Police |  |  |  | 2016 |
| University of Missouri | Huang,Susan | EVENT ASSISTANT I | Police |  |  |  | 2016 |
| University of Missouri | Lueck,Ronald G | EVENT ASSISTANT I | Intercollegiate Athletics |  |  |  | 2016 |

</details>

### mo_msu: Missouri State University FY27 internal operating budget, Detail Full-Time Salary Budget (MO)

Notes: budgeted (not paid) full-time salary per budget line for FY2027 (year ending 2027-06-30); one row per budget line, so split-funded people have several rows; vacant positions skipped; no job titles (position numbers only); department = organization description

- Rows: 2,187; with a pay value: 2,187 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 2,187 | 2 | $63,327 | $55,178 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Missouri State University | McHenry, Timothy |  | ASSISTIVE TECHNOLOGY CENTER | $57,250 |  |  | 2027 |
| Missouri State University | Jones, Regan |  | ATHLETICS COMMUNICATIONS | $44,488 |  |  | 2027 |
| Missouri State University | Rainwater, Douglas |  | PROVOST OFFICE-OPER | $113,900 |  |  | 2027 |
| Missouri State University | Prock, Casondra |  | HONORS COLLEGE | $35,797 |  |  | 2027 |
| Missouri State University | Brown, Jeffrey |  | ENV HEALTH & SAFETY ADMIN-OPER | $44,335 |  |  | 2027 |
| Missouri State University | Dees, Charles |  | GROUNDS | $49,743 |  |  | 2027 |
| Missouri State University | Grann, Logan |  | GROUNDS | $34,840 |  |  | 2027 |
| Missouri State University | Davidson, Michael |  | FACILITIES & MAINTENANCE | $56,837 |  |  | 2027 |
| Missouri State University | McIver, Joshua |  | FACILITIES & MAINTENANCE | $54,080 |  |  | 2027 |
| Missouri State University | Morris, Benjamin |  | FACILITIES & MAINTENANCE | $49,519 |  |  | 2027 |
| Missouri State University | Liu, Dandan |  | VP COMM & GLOBAL PARTNERSHIPS- | $76,327 |  |  | 2027 |
| Missouri State University | Hammar, Abraham |  | INTERNATIONAL PROGRAMS | $58,984 |  |  | 2027 |
| Missouri State University | Young, Angela |  | REGISTRAR | $93,374 |  |  | 2027 |
| Missouri State University | Weter, Jennifer |  | VP UNIVERSITY ADV ADMIN-OPER | $62,407 |  |  | 2027 |
| Missouri State University | Smith, Stephanie |  | UNIVERSITY ADVANCEMENT | $90,989 |  |  | 2027 |
| Missouri State University | Sabo, Karen |  | THEATRE & DANCE-OPER | $65,490 |  |  | 2027 |
| Missouri State University | Behrend, Bonni |  | MCHHS COUNSELING-OPER | $70,013 |  |  | 2027 |
| Missouri State University | Hornsby-Gutting, Angela |  | HISTORY-OPER | $90,907 |  |  | 2027 |
| Missouri State University | Morgan, Michelle |  | HISTORY-OPER | $76,804 |  |  | 2027 |
| Missouri State University | Schmalzbauer, John |  | RELIGIOUS STUDIES-OPER | $46,779 |  |  | 2027 |

</details>

### il_isu: Illinois State University salary lists (PDFs, FY2020-FY2026) (IL)

Notes: downloaded by hand by the site owner (Cloudflare-protected page); supplied 2026-10-18 PDF tables parsed by column position; salary as published on the list's 'as of' date (Jan of the fiscal year; the FY2025 Update file is as of 5/19/25), monthly amount or hourly rate - units not stated, so base_pay is NULL and the value is kept in pay_components; FY2023/FY2024 from files.library.illinoisstate.edu; FY2020-2022, FY2025, FY2026 downloaded by hand by the site owner from ir.library.illinoisstate.edu (Cloudflare-protected); FY2013-2019 are OCR scans and are not loaded

- Rows: 25,031; with a pay value: 0 (0.0%)
- Exact duplicate rows (same original row): 2
- Empty name: 0; no numeric pay: 25,031; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2020 | 3,641 | 1 |  |  |
| 2021 | 3,515 | 1 |  |  |
| 2022 | 3,450 | 1 |  |  |
| 2023 | 3,512 | 1 |  |  |
| 2024 | 3,681 | 1 |  |  |
| 2025 | 3,583 | 1 |  |  |
| 2026 | 3,649 | 1 |  |  |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Illinois State University | Batson, Marietta | Clinical Asst Professor | School of Teaching and Learnin |  |  |  | 2023 |
| Illinois State University | Carthans, Kimberly | Faculty Associate | Thomas Metcalf School |  |  |  | 2023 |
| Illinois State University | Gardiner-Walsh, Stephanie | Associate Professor | Special Education |  |  |  | 2023 |
| Illinois State University | Hoffman, Carrie | Faculty Associate | University High School |  |  |  | 2023 |
| Illinois State University | Krippel, Jessica | Instructional Asst Professor | School of Biological Sciences |  |  |  | 2023 |
| Illinois State University | Yu, Ui-Jeen | Professor | Family and Consumer Sciences |  |  |  | 2023 |
| Illinois State University | Judson, Robert | Asst Mens Basketball Coach | Intercollegiate Athletics |  |  |  | 2023 |
| Illinois State University | Mortensen, Jennifer | Building Service Worker | Janitorial |  |  |  | 2023 |
| Illinois State University | Blythe, Robert | Pipefitter | Building Maintenance |  |  |  | 2024 |
| Illinois State University | Gibson, Cynthia | Culinary Worker II | Event Management, Dining and H |  |  |  | 2024 |
| Illinois State University | Hobby, Jacob | Carpenter | Building Maintenance |  |  |  | 2024 |
| Illinois State University | Hobson, Joy | Food Service Administrator III | Event Management, Dining and H |  |  |  | 2024 |
| Illinois State University | McGowan, Christina | Building Service Worker | Janitorial |  |  |  | 2024 |
| Illinois State University | Sexton, Andrew | Program Assistant | Illinois Tutoring Initiative |  |  |  | 2024 |
| Illinois State University | Hassani, Sarah | Instructional Asst Professor | Mathematics |  |  |  | 2024 |
| Illinois State University | Reed, Toure | Professor | History |  |  |  | 2024 |
| Illinois State University | Barker, David | Associate Professor |  |  |  |  | 2020 |
| Illinois State University | Hutchison, Michele | Instructional Asst Professor |  |  |  |  | 2020 |
| Illinois State University | Riverstone-Newell, Lori | Associate Professor |  |  |  |  | 2020 |
| Illinois State University | Donnelly, Sheryl | Building Service Foreman |  |  |  |  | 2020 |

</details>

### vt_uvm: University of Vermont List of Base Pay (PDF) (VT)

Notes: base pay (primary job) as published each fall; fiscal_year = FY in which the list was released (srYY = fall YY => FY YY+1; FYnn files as named); non-numeric entries (e.g. 'unpaid leave') kept as pay_text; older files fetched from www.uvm.edu (the Drupal origin host linked on the page is not robots-allowed)

- Rows: 70,348; with a pay value: 70,215 (99.8%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 133; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2010 | 3,786 | 1 | $54,736 | $44,500 |
| 2011 | 3,819 | 1 | $56,055 | $45,386 |
| 2012 | 3,933 | 1 | $55,414 | $44,793 |
| 2013 | 3,894 | 1 | $56,785 | $45,900 |
| 2014 | 3,940 | 1 | $57,939 | $46,745 |
| 2015 | 3,908 | 1 | $59,329 | $48,058 |
| 2016 | 3,985 | 1 | $59,643 | $48,535 |
| 2017 | 4,036 | 1 | $60,862 | $49,462 |
| 2018 | 4,127 | 1 | $60,855 | $49,550 |
| 2019 | 4,186 | 1 | $62,392 | $50,121 |
| 2020 | 4,233 | 1 | $63,738 | $51,405 |
| 2021 | 4,125 | 1 | $62,734 | $50,807 |
| 2022 | 4,192 | 1 | $63,269 | $51,789 |
| 2023 | 4,254 | 1 | $66,728 | $55,632 |
| 2024 | 4,482 | 1 | $68,534 | $57,554 |
| 2025 | 4,711 | 1 | $69,226 | $59,456 |
| 2026 | 4,737 | 1 | $73,488 | $63,179 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Vermont | Collins,Courtney | Lecturer |  | $70,000 |  |  | 2025 |
| University of Vermont | Hooker,Jacqueline | Technical Support Specialist |  | $47,385 |  |  | 2025 |
| University of Vermont | Kolan,Matthew | Senior Lecturer |  | $98,954 |  |  | 2025 |
| University of Vermont | Roberts,Jack | Library Support Senior |  | $45,591 |  |  | 2025 |
| University of Vermont | Strong,Allan | Professor |  | $122,525 |  |  | 2025 |
| University of Vermont | Dixon,Anne | Professor |  | $317,874 |  |  | 2026 |
| University of Vermont | Truax,Sarah | Univ Ops Administration PC1 N |  | $55,029 |  |  | 2026 |
| University of Vermont | Dolan,Kelly K | Outreach Professional Sr |  | $55,332 |  |  | 2022 |
| University of Vermont | Ducis,Katrina | Assistant Professor (COM) |  | $35,000 |  |  | 2022 |
| University of Vermont | Feldman,Jan L. | Professor |  | $82,792 |  |  | 2022 |
| University of Vermont | Reyes,Cynthia C. | Associate Professor |  | $90,542 |  |  | 2022 |
| University of Vermont | Gluchowski,Nina | Assistant Professor (COM) |  | $30,000 |  |  | 2023 |
| University of Vermont | Russell,Sheila Raymond | Researcher/Analyst |  | $90,600 |  |  | 2023 |
| University of Vermont | Dubois,James | Biomed Equipment Tech Sr |  | $82,700 |  |  | 2024 |
| University of Vermont | Fritz,Andrew | Faculty Scientist (COM) |  | $66,950 |  |  | 2024 |
| University of Vermont | Klug,Nicholas | Assistant Professor (COM) |  | $80,842 |  |  | 2024 |
| University of Vermont | Lockwood,Brent | Associate Professor |  | $89,281 |  |  | 2024 |
| University of Vermont | Niemann,Michael | Admin Analyst/Planner |  | $67,980 |  |  | 2024 |
| University of Vermont | Owens,Ryder | Information Tech Professional |  | $68,530 |  |  | 2024 |
| University of Vermont | Alarie,Melody Ann | Business/Acctng Specialst |  | $46,079 |  |  | 2010 |

</details>

### nm_nmhu: New Mexico Highlands University salary reports (PDF) (NM)

Notes: annual salary + FTE per published line (multiple lines per person for overloads/second jobs); fiscal_year from the report (3.1.23 report = FY2023); department text is truncated by the publisher; the FY25 report publishes $0.00 for 122 lines: kept as 0 and flagged pay_components.source_published_zero = true

- Rows: 2,873; with a pay value: 2,873 (100.0%)
- Exact duplicate rows (same original row): 1
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2023 | 711 | 1 | $43,049 | $42,141 |
| 2024 | 950 | 1 | $41,317 | $35,422 |
| 2025 | 671 | 1 | $51,337 | $49,920 |
| 2026 | 541 | 1 | $66,107 | $60,000 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| New Mexico Highlands University | BEINHART, COREY | Data Manager/Analyst | Forest Watershed Restoration I | $74,529 |  |  | 2026 |
| New Mexico Highlands University | COREY-RIVAS, SARAH | Professor of Biology | Biology | $83,968 |  |  | 2026 |
| New Mexico Highlands University | DURAN, LORETTA | Library Associate-Serials Sect | Library | $46,231 |  |  | 2026 |
| New Mexico Highlands University | FREIJE, CHRIS | Head Wrestling Coach | Athletics Mens Wrestling | $52,000 |  |  | 2026 |
| New Mexico Highlands University | HEUSINKVELD, DANA | GIS Specialist | Forest Watershed Restoration I | $84,421 |  |  | 2026 |
| New Mexico Highlands University | HOLLOWAY, JEREMY | Professor In Residence Equity and Justic | SOE Faculty Endowment-Invest I | $78,000 |  |  | 2026 |
| New Mexico Highlands University | MARQUEZ, RALPH | Bus Driver | Motor Pool | $49,920 |  |  | 2026 |
| New Mexico Highlands University | MILCZEWSKI, JOSEPH | Assistant Professor of Supply Chain Mana | Business Administration | $102,803 |  |  | 2026 |
| New Mexico Highlands University | VIGIL, KATHERINE | Accountant | Business Office | $47,331 |  |  | 2026 |
| New Mexico Highlands University | WOODRUFF, JACINDA | Director of Residence Life & Housing Ope | Housing and Student Conduct | $72,810 |  |  | 2026 |
| New Mexico Highlands University | Benavidez, Angel A | Graduate Records & Center Coor | Registrar | $45,141 |  |  | 2023 |
| New Mexico Highlands University | Biggs, James R | Visiting Asst Prof of Forestry | Forestry | $11,338 |  |  | 2023 |
| New Mexico Highlands University | Chavez, Joni F | Senior Admin Asst-Human & FA | College of Arts and Sciences | $45,677 |  |  | 2023 |
| New Mexico Highlands University | Cole, Conrad | Assistant Wrestling Coach | Athletics - Men's Wrestling | $33,421 |  |  | 2023 |
| New Mexico Highlands University | Deleon, Nathan F | Contingent Faculty- Field Practicum Semi | CYFD/SW/FY20/21/22 | $1,000 |  |  | 2023 |
| New Mexico Highlands University | Laumbach, Christian A | Life Drawing Model | Fine Arts | $41,600 |  |  | 2023 |
| New Mexico Highlands University | Linder, Peter S | Associate Dean - CAS/Prof of His & Poli  | College of Arts and Sciences | $79,153 |  |  | 2023 |
| New Mexico Highlands University | Lujan, Darla R | Field Consultant- CRN 4036 4043 Field Pr | CYFD/SW/FY20/21/22 | $750 |  |  | 2023 |
| New Mexico Highlands University | Montoya, Emily R | Director of Financial Aid | Financial Aid | $85,696 |  |  | 2023 |
| New Mexico Highlands University | Moore, Rebecca M | Professor of Social Work | School of Social Work | $83,048 |  |  | 2023 |

</details>

### tn_apsu: Austin Peay State University employee salary data (PDF) (TN)

Notes: current salary list (no date printed; PDF created 2026-09-21 => FY2027, Tennessee FY Jul-Jun); salary under $1,000 is an hourly rate kept in pay_components only; every row carries pay_components.year_derived = 'pdf_creation_date'

- Rows: 1,158; with a pay value: 914 (78.9%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 244; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 1,158 | 1 | $80,807 | $72,000 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Austin Peay State University | Andrew, Jimmy | Shipping & Receiving Delivery Driver | 304001-Central Receiving |  |  |  | 2027 |
| Austin Peay State University | Black, Elizabeth | Advisor | 302000-Human Resources | $50,750 |  |  | 2027 |
| Austin Peay State University | Coleman, Nora | Specialist, Accounts Payable | 301002-Accounting Services |  |  |  | 2027 |
| Austin Peay State University | Conwell, Melissa | Program Director, Tri-County Upward Boun | 405011-Tri-County Upward Bound | $101,035 |  |  | 2027 |
| Austin Peay State University | Corlew, Amy | Assistant Vice President for Enrollment  | 404000-Admissions | $136,959 |  |  | 2027 |
| Austin Peay State University | Derby, Toni-Ann | Senior Associate Director of Athletics,  | 700003-Athletic Administration | $76,250 |  |  | 2027 |
| Austin Peay State University | Dheel, James | Maintenance Technician- HVAC | 304008-Power Plant Maintenance |  |  |  | 2027 |
| Austin Peay State University | Endsley, Jill | Financial Aid Assistant | 404100-Student Financial Aid |  |  |  | 2027 |
| Austin Peay State University | Ferdik, Frank | Associate Professor | 420800-Criminal Justice | $79,251 |  |  | 2027 |
| Austin Peay State University | Gaither, Jamie | Academic Administrative Assistant | 450700-Mathematics and Statistics |  |  |  | 2027 |
| Austin Peay State University | Gupte, Manisha | Associate Professor | 450100-Biology | $77,225 |  |  | 2027 |
| Austin Peay State University | Haley, Parker | Advisor | 302000-Human Resources | $50,750 |  |  | 2027 |
| Austin Peay State University | Harp, Kylie | Specialist, Military-Affiliated Accounti | 601001-Veterans Education Benefits |  |  |  | 2027 |
| Austin Peay State University | Harris, Cameron | Assistant Coach, Softball | 701080-Softball | $45,000 |  |  | 2027 |
| Austin Peay State University | Hemby, Krista | Senior Administrative Assistant | 401200-Distance Education Online Fe |  |  |  | 2027 |
| Austin Peay State University | Hill, Savannah | Instructor in Animation and Visual Effec | 410100-Art and Design | $50,000 |  |  | 2027 |
| Austin Peay State University | Hutchins, Thomas | Executive Director, Physical Plant Depar | 304000-Physical Plant | $150,049 |  |  | 2027 |
| Austin Peay State University | Iyer, Uma | Professor | 420500-Psychological Science and Co | $100,782 |  |  | 2027 |
| Austin Peay State University | Jackson, Jarrod | Library Associate | 406000-Library Office | $53,160 |  |  | 2027 |
| Austin Peay State University | Jaimes, Gricelda | Specialist, Customer Service and Print | 201001-Govs Print |  |  |  | 2027 |

</details>

### tn_etsu: East Tennessee State University active employees (PDF) (TN)

Notes: salary of active employees as of 2024-05-22 => FY2024

- Rows: 2,473; with a pay value: 2,473 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2024 | 2,473 | 1 | $73,284 | $57,540 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| East Tennessee State University | Bah Madison, Isatou | Research Assistant 2 | Internal Medicine | $40,559 |  |  | 2024 |
| East Tennessee State University | Baur, Marten L. | Coordinator | Sport Exercise Recreation Kinesiolo | $45,458 |  |  | 2024 |
| East Tennessee State University | Bennett, Savannah E. | Manager | Reece Museum | $43,901 |  |  | 2024 |
| East Tennessee State University | Beutell, Micah A. | Director | Marketing and Promotion | $56,346 |  |  | 2024 |
| East Tennessee State University | Blevins, Phil E. | Assistant Director | Trio Outreach | $58,964 |  |  | 2024 |
| East Tennessee State University | Cannon, Theresia L. | Coordinator | Office of Sponsored Programs | $50,977 |  |  | 2024 |
| East Tennessee State University | Carter, Vicki W. | Associate Director | Budget and Financial Planning | $68,016 |  |  | 2024 |
| East Tennessee State University | Castle, Brandon M. | Counselor | Arts and Sciences CASE | $46,520 |  |  | 2024 |
| East Tennessee State University | Cyrier, Joanna E. | Advisor | Dean CCRHS | $49,149 |  |  | 2024 |
| East Tennessee State University | Early, Kristen L. | Manager | Finance and Administration | $58,964 |  |  | 2024 |
| East Tennessee State University | France, Kristin G. | Business Manager | Pediatrics | $57,547 |  |  | 2024 |
| East Tennessee State University | Gardner, Kody H. | Engineer | Infor Technology Comp Svcs | $70,642 |  |  | 2024 |
| East Tennessee State University | Gomez, Maggie V. | Advisor | University Advisement | $43,901 |  |  | 2024 |
| East Tennessee State University | Graybeal, Michele L. | Coordinator | Assoc Dean Student Serv | $45,663 |  |  | 2024 |
| East Tennessee State University | Hardin, Cynthia D. | Associate Director | Office of Sponsored Programs | $64,461 |  |  | 2024 |
| East Tennessee State University | Holifield, Margaret S. | Manager | Academic Support Kingsport | $55,578 |  |  | 2024 |
| East Tennessee State University | Lane, Keriann E. | Coordinator | Student Services COM | $41,280 |  |  | 2024 |
| East Tennessee State University | Mayfield, Cynthia J. | Associate Director | Office of Sponsored Programs | $57,400 |  |  | 2024 |
| East Tennessee State University | Muncy, Rebecca H. | Executive Director | University Advancement | $88,825 |  |  | 2024 |
| East Tennessee State University | Musick, Mary E. | Data Analyst | Business and Finance | $63,556 |  |  | 2024 |

</details>

### mi_um: University of Michigan Salary Record (PDF) (MI)

Notes: one row per appointment; base_pay = appointment annual full-time rate (FTR); fraction, FTR basis and amount paid from general fund in pay_components; as of 2025-11-01 => FY2026; Ann Arbor (incl. Michigan Medicine), Dearborn, Flint

- Rows: 54,659; with a pay value: 54,659 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2026 | 54,659 | 3 | $101,474 | $85,546 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Michigan-Ann Arbor | Angelocci,Bradley | Electronic Tech Supervisor | Space Physics Research Lab | $124,007 |  |  | 2026 |
| University of Michigan-Ann Arbor | Bagley-Ayres,Damon | Orthotist and Prosthetist | MM Orthotics&Prosthetics Ctr | $92,585 |  |  | 2026 |
| University of Michigan-Ann Arbor | Bogart,Jessica Ruth | ASST PROFESSOR | School of Music,Theatre&Dance | $103,310 |  |  | 2026 |
| University of Michigan-Ann Arbor | Bracher,Elissa | Sr Bill Clk/Pat Acct Rep Hlth | MM Rev Cycle (PTO) | $50,600 |  |  | 2026 |
| University of Michigan-Ann Arbor | Bratschi,Leo J | SECURITY OFFICER | DPSS Housing Sec & Safety Svcs | $55,640 |  |  | 2026 |
| University of Michigan-Ann Arbor | Butler,Simona Ouzounova | Clinical Pharmacist Specialist | MM CVC Pharmacy Services | $180,430 |  |  | 2026 |
| University of Michigan-Ann Arbor | Caldwell,Laura | PA Medical Specialty | MM CW Midlvl Nephrology | $135,790 |  |  | 2026 |
| University of Michigan-Ann Arbor | Calvin IV,James | Physical Therapist Assistant | MM BCSC CMC Therapy | $72,717 |  |  | 2026 |
| University of Michigan-Ann Arbor | Campbell,Morgan | HOUSE OFFICER III | MM H.O. Neurology | $80,713 |  |  | 2026 |
| University of Michigan-Ann Arbor | Cheng,Jerome | CLINICAL ASSOC PROF | MM Pathology Department | $187,424 |  |  | 2026 |
| University of Michigan-Ann Arbor | Clark,Lina Dilip | EDUC NURSE COORD COMPETENT-NE | MM CW 7E | $139,422 |  |  | 2026 |
| University of Michigan-Ann Arbor | Clark,Steven E | PROFESSOR | LSA Molec./Cell./Develop. Bio | $150,660 |  |  | 2026 |
| University of Michigan-Ann Arbor | Conlon,Anna | HOUSE OFFICER III | MM H.O. Internal Medicine | $80,713 |  |  | 2026 |
| University of Michigan-Ann Arbor | Coughlin,Lara Nicole | ASSOC PROFESSOR | MM Psychiatry Department | $162,130 |  |  | 2026 |
| University of Michigan-Ann Arbor | Couts,Bethany | Recruiting Coord Sr Unit | School of Information | $68,612 |  |  | 2026 |
| University of Michigan-Ann Arbor | Czarny,Allison | Patient Services Associate | Mary Rackham Inst Central Off | $49,234 |  |  | 2026 |
| University of Michigan-Ann Arbor | Dhillon,Baljit Kaur | REGISTERED NURSE - LEVEL C | MM Ambulatory Care Services | $137,488 |  |  | 2026 |
| University of Michigan-Ann Arbor | Dias,Kenadi | Patient Care Technician | MM UH CVC 4B | $44,366 |  |  | 2026 |
| University of Michigan-Ann Arbor | Draelos,Anne | ASST PROFESSOR | MM Comp Med and Bioinformatics | $152,982 |  |  | 2026 |
| University of Michigan-Ann Arbor | Eskesen,Stephen | Business Systems Analyst Sr | MM Pathology Informatics | $98,664 |  |  | 2026 |

</details>

### me_hist: University of Maine System salaries of regular employees (historical PDFs) (ME)

Notes: annual base salary snapshots (Nov 2019, Apr 2020, Nov 2020, Nov 2021) parsed from the PDF text layer; fiscal_year = UMS fiscal year (Jul-Jun) containing the 'As of' date, so FY2020 has two snapshots (pay_components.as_of tells them apart); primary title only; overtime/overload excluded by the publisher

- Rows: 18,453; with a pay value: 18,453 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2020 | 9,335 | 8 | $57,018 | $49,830 |
| 2021 | 4,566 | 8 | $59,269 | $51,755 |
| 2022 | 4,552 | 9 | $62,607 | $53,971 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Maine at Farmington | Davis, Stephen P. | Career Counselor/Outreach Coor | FHUDE | $39,915 |  |  | 2020 |
| University of Maine at Farmington | Meader, Richard H. | Head Men's Basketball Coach | FATHL | $54,528 |  |  | 2020 |
| University of Maine | Bryce, James R. | Program Manager | OADCC | $150,000 |  |  | 2020 |
| University of Maine | Camire, Mary E. | Prof of Food Science & Nutri | OSFA | $119,883 |  |  | 2020 |
| University of Maine | De La Cruz, Gabriel R. | Manager of Computer Services | OHOUS | $48,670 |  |  | 2020 |
| University of Maine | Weiskittel, Aaron R. | Professor | OFORM | $128,414 |  |  | 2020 |
| University of Maine | Williamson, Claudia J. | Parent Educational Professiona | OCES | $45,500 |  |  | 2020 |
| University of Southern Maine | Degifico Jr, Vincent A. | Ice Arena Manager | PATHL | $51,520 |  |  | 2020 |
| University of Southern Maine | Perry, Dana R. | Facilities Maint Worker CL1 | PCUST | $24,024 |  |  | 2020 |
| University of Southern Maine | Robinson, Max H. | Administrative Specialist CL3 | PEDLA | $32,406 |  |  | 2020 |
| University of Southern Maine | Swift, Justin M. | Senior Finance Business Partne | PVADM | $78,458 |  |  | 2020 |
| University of Southern Maine | Timberlake, Sharon E. | Lecturer in Leadership and Org | PACPLA | $55,000 |  |  | 2020 |
| University of Maine at Presque Isle | Rolon, Tyna M. | Talent Sch Coord/Tracking Spec | IUB | $37,954 |  |  | 2020 |
| University of Maine System (System Wide  | Kimball, Karen S. | Deputy V C Acad Affairs | SGCHAN | $189,100 |  |  | 2020 |
| University of Maine at Augusta | Chaples, Sarah J. | Regional Manager/Microenterpri | ACWWC | $49,903 |  |  | 2020 |
| University of Maine | Blackmer, Travis L. | Lecturer of Economics | OSOE | $51,804 |  |  | 2020 |
| University of Maine | Garland, Katherine F. | Horticulture Professional | OCES | $52,653 |  |  | 2020 |
| University of Maine | Marquis, Minnie E. | Child Care Assistant | ODCC | $32,198 |  |  | 2020 |
| University of Maine | Myers Jr, Alvin R. | Facilities Maint Worker CL2 | OHOUS | $33,904 |  |  | 2020 |
| University of Maine | Newell-Caito, Jennifer L. | Lecturer of Molecular and Biom | OBMMB | $46,345 |  |  | 2020 |

</details>

### dc_hist: DC DCHR quarterly public body employee listings (UDC rows), Dec 2013 - Dec 2021 (DC)

Notes: file-name date token '0914' file-name date token '09302017' file-name date token '09302018' file-name date token '200930' file-name date token '210930' file-name date token '211231' file-name date token 'jun15'

- Rows: 8,276; with a pay value: 5,929 (71.6%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 2,347; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2014 | 1,076 | 1 | $68,472 | $63,066 |
| 2015 | 1,094 | 1 | $64,308 | $62,137 |
| 2017 | 1,398 | 1 | $72,409 | $66,671 |
| 2018 | 1,205 | 1 | $67,568 | $64,938 |
| 2020 | 1,262 | 1 | $66,492 | $65,977 |
| 2021 | 1,214 | 1 | $67,266 | $67,813 |
| 2022 | 1,027 | 1 | $76,778 | $72,105 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of the District of Columbia | Bennett‐Roberts, Beverly | ADJUNCT PROFESSOR |  |  |  |  | 2014 |
| University of the District of Columbia | Colbert, Tracey | PROJECT ASST |  | $39,459 |  |  | 2014 |
| University of the District of Columbia | Eagleson, Juanita | ADJUNCT PROFESSOR |  |  |  |  | 2014 |
| University of the District of Columbia | Franklin, Beverly | EXECUTIVE SECRETARY |  | $78,267 |  |  | 2014 |
| University of the District of Columbia | Gay, Troy | Senior Project Specialist (Arc |  | $71,289 |  |  | 2014 |
| University of the District of Columbia | Hamlin, Charlene | ADJUNCT PROFESSOR |  |  |  |  | 2014 |
| University of the District of Columbia | Harrison, Timothy | Admissions Counselor (Transfer |  | $72,327 |  |  | 2014 |
| University of the District of Columbia | Prescott 2nd, Herman | Asst. Provost for Academic Adm |  | $116,848 |  |  | 2014 |
| University of the District of Columbia | Srinivas, Karan | Project Director (WFD Grants) |  | $84,610 |  |  | 2014 |
| University of the District of Columbia | Williams, Adria | Customer Service Representativ |  | $37,178 |  |  | 2014 |
| University of the District of Columbia | Anker, Deborah | Training Instructor |  | $21,532 |  |  | 2015 |
| University of the District of Columbia | Baker, Richard | EDUCATION COUNSELOR |  | $24,496 |  |  | 2015 |
| University of the District of Columbia | Canty, Vivian | Associate Dean, Admissions |  | $92,640 |  |  | 2015 |
| University of the District of Columbia | Cook, Robin | ADJUNCT PROFESSOR |  |  |  |  | 2015 |
| University of the District of Columbia | Flowers, Angelyn | Program Coordinator (Faculty) |  | $1,500 |  |  | 2015 |
| University of the District of Columbia | Hampton-Garland, Pamela | ASST PROFESSOR |  | $65,838 |  |  | 2015 |
| University of the District of Columbia | Harper, Kimberly | ADJUNCT PROFESSOR |  |  |  |  | 2015 |
| University of the District of Columbia | Nelson, William | ASSOC DEAN |  | $116,848 |  |  | 2015 |
| University of the District of Columbia | Pasko, Kaitlyn | Assistant Coach, Women's Lacro |  | $44,252 |  |  | 2015 |
| University of the District of Columbia | Poudel, Naresh | Lab Assistant |  | $14,706 |  |  | 2015 |

</details>

### ar_adhe: Arkansas Division of Higher Education Administrator's Compensation Survey (>= $100k) (AR)

Notes: linked from https://adhe.edu/data-publications/administrator%E2%80%99s-compensation-survey PARTIAL coverage: only administrators with salary >= $100,000 at public institutions; one form page per person parsed by position (pdfplumber words); base_pay = line 12 total base salary (public + private funds), total_pay = line 41 total compensation as published; every line's public/private/total and private-fund source in pay_components ('$ -' accounting dashes are stored as NULL, not 0); fiscal_year = the survey's fiscal year (AR FY Jul-Jun, from the publication; the per-form typed year is kept as fiscal_year_reported_on_form); institution from the table-of-contents section the page falls in

- Rows: 15,432; with a pay value: 15,430 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 2; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2010 | 459 | 35 | $184,934 | $155,862 |
| 2011 | 509 | 36 | $184,593 | $155,310 |
| 2012 | 565 | 35 | $184,876 | $156,231 |
| 2013 | 680 | 34 | $209,073 | $160,874 |
| 2014 | 704 | 35 | $209,840 | $160,675 |
| 2015 | 689 | 39 | $209,484 | $162,928 |
| 2016 | 737 | 41 | $209,782 | $163,859 |
| 2017 | 807 | 40 | $207,467 | $162,396 |
| 2018 | 873 | 40 | $221,000 | $164,831 |
| 2019 | 904 | 40 | $210,326 | $162,148 |
| 2020 | 935 | 37 | $204,716 | $160,962 |
| 2021 | 1,011 | 38 | $205,526 | $162,345 |
| 2022 | 1,079 | 37 | $208,876 | $162,575 |
| 2023 | 1,236 | 31 | $206,714 | $158,563 |
| 2024 | 1,318 | 39 | $195,619 | $157,878 |
| 2025 | 1,379 | 39 | $205,464 | $159,282 |
| 2026 | 1,547 | 39 | $214,517 | $165,333 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Southern Arkansas University Magnolia | Bland, Timothy | Director of Computer Services |  | $108,000 |  | $144,449 | 2026 |
| University of Arkansas System Administra | Evans, Harold | Associate Vice President, Legal & Resear |  | $194,791 |  | $238,339 | 2026 |
| University of Arkansas, Fayetteville | Ussery, Don | Assoc. Director of Univ. Info. Tech. |  | $162,407 |  | $194,827 | 2026 |
| AREON | Johnson, Timothy | AREON Network Engineer |  | $126,901 |  | $159,905 | 2026 |
| University of Arkansas for Medical Scien | Green, Luke | Director of Pharmacy |  | $195,500 |  | $241,997 | 2026 |
| University of Arkansas for Medical Scien | Yelenich, Sarah | Asst. Dir. of Pharmacy |  | $173,300 |  | $211,588 | 2026 |
| Arkansas Tech University | Milligan, Steve | Director of Information Systems |  | $138,074 |  | $170,076 | 2025 |
| UA-Grantham | Shisler, Daniel | Director of University Relations |  | $110,000 |  | $135,639 | 2025 |
| University of Central Arkansas | Whiting, Philip | Head Coach/Athletic Director |  | $175,000 |  | $223,009 | 2025 |
| Arkansas State University | Hicks, Kathy | Executive Assistant |  | $100,000 |  | $131,280 | 2024 |
| Southern Arkansas University Magnolia | Reed, Shawana | Vice President for Finance |  | $145,418 |  | $185,835 | 2024 |
| University of Arkansas, Fayetteville | Balthrop, Andrew | Research Associate - 12 Month |  | $118,450 |  | $171,686 | 2024 |
| University of Arkansas, Fayetteville | Gaddy, Tory | Major Gift Development Officer |  | $113,300 |  | $145,726 | 2024 |
| University of Arkansas, Fayetteville | Martin, Chuck | Asst. Basketball Coach |  | $53,030 |  | $86,308 | 2024 |
| University of Arkansas for Medical Scien | Principe, Philip | Compliance Officer |  | $127,500 |  | $150,046 | 2024 |
| Southern Arkansas University Magnolia | Reed, Shawana | Vice President for Finance |  | $141,871 |  | $185,313 | 2023 |
| University of Arkansas System Administra | Hudson, Angela | Asst. to the President |  | $110,742 |  | $143,943 | 2023 |
| University of Arkansas, Fayetteville | Bayles, Brandon | Director of Institutional Research |  | $160,000 |  | $181,428 | 2023 |
| University of Arkansas Little Rock | Phillips, Carrie | Associate Vice Chancellor |  | $125,000 |  | $152,129 | 2023 |
| University of Arkansas for Medical Scien | Anthony, Carliess | Clinical Services Manager |  | $102,660 |  | $111,542 | 2023 |

</details>

### pa_pitt: University of Pittsburgh 200 highest-paid non-officers (Right-to-Know / 990 disclosure) (PA)

Notes: PARTIAL coverage: only the 200 highest-paid non-officer employees; name + total compensation (no title); compensation is for the calendar year inside the 990 tax year; fiscal_year = 990 tax year end (Jun 30)

- Rows: 400; with a pay value: 400 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2024 | 200 | 1 | $460,555 | $366,463 |
| 2025 | 200 | 1 | $478,217 | $389,608 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Pittsburgh | Capel III, Felton Jeffrey |  |  |  |  | $3,731,055 | 2024 |
| University of Pittsburgh | Bates, Randy Van |  |  |  |  | $906,250 | 2024 |
| University of Pittsburgh | Reis, Steven E. |  |  |  |  | $642,000 | 2024 |
| University of Pittsburgh | Strick, Peter Leonard |  |  |  |  | $610,961 | 2024 |
| University of Pittsburgh | Shroff, Sanjeev Govinddas |  |  |  |  | $503,540 | 2024 |
| University of Pittsburgh | Delitto, Anthony |  |  |  |  | $488,676 | 2024 |
| University of Pittsburgh | Lichtveld, Maureen Y. Tjon |  |  |  |  | $458,874 | 2024 |
| University of Pittsburgh | Childers, Bruce Robert |  |  |  |  | $453,802 | 2024 |
| University of Pittsburgh | Duprex, W. Paul |  |  |  |  | $408,610 | 2024 |
| University of Pittsburgh | Vidovich, Jay |  |  |  |  | $384,390 | 2024 |
| University of Pittsburgh | Badylak, Stephen Francis |  |  |  |  | $377,225 | 2024 |
| University of Pittsburgh | Van Houten, Bennett |  |  |  |  | $366,463 | 2024 |
| University of Pittsburgh | Mirchandani, Prakash |  |  |  |  | $365,459 | 2024 |
| University of Pittsburgh | Ramasubbu, Narayanasamy |  |  |  |  | $354,393 | 2024 |
| University of Pittsburgh | Kemerer, Chris Francis |  |  |  |  | $344,138 | 2024 |
| University of Pittsburgh | Xie, Wen |  |  |  |  | $339,724 | 2024 |
| University of Pittsburgh | Mathis, Chester A. |  |  |  |  | $332,150 | 2024 |
| University of Pittsburgh | Orwig, Kyle E. |  |  |  |  | $330,057 | 2024 |
| University of Pittsburgh | Bernotas, Scott |  |  |  |  | $324,431 | 2024 |
| University of Pittsburgh | Marazita, Mary Louise |  |  |  |  | $318,238 | 2024 |

</details>

### pa_temple: Temple University 200 highest-paid employees other than officers (Right-to-Know) (PA)

Notes: PARTIAL coverage: only the 200 highest-paid non-officer employees; name, position title, total compensation for the calendar year stated in the file; fiscal_year = the 990 fiscal year that calendar year is reported in (calendar year + 1, e.g. calendar 2024 -> FY2024-25)

- Rows: 400; with a pay value: 400 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2023 | 200 | 1 | $571,799 | $509,405 |
| 2025 | 200 | 1 | $598,022 | $546,612 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Temple University | Carey, Roderick | Coach (former) |  |  |  | $1,590,000 | 2025 |
| Temple University | Goldberg, Amy | Dean |  |  |  | $1,223,353 | 2025 |
| Temple University | Criner, Gerard | Professor Tenured |  |  |  | $1,041,739 | 2025 |
| Temple University | Kim, Bong-Soo | Professor Clinician Educator |  |  |  | $949,888 | 2025 |
| Temple University | Eun, Daniel | Professor Clinician Scholar |  |  |  | $949,098 | 2025 |
| Temple University | Kumaran, Maruti | Assoc Prof Clinician Scholar |  |  |  | $922,120 | 2025 |
| Temple University | Khan, Mansoor | Assoc Prof Clinician Educator |  |  |  | $844,095 | 2025 |
| Temple University | Sewards, Joseph | Professor Clinician Educator |  |  |  | $745,101 | 2025 |
| Temple University | Thoder, Joseph | Professor Clinician Scholar |  |  |  | $738,843 | 2025 |
| Temple University | Kasoff, Willard | Assoc Prof Clinician Scholar |  |  |  | $708,246 | 2025 |
| Temple University | Chavin, Kenneth | Professor Clinician Scholar |  |  |  | $669,511 | 2025 |
| Temple University | Deveaux, Eric | Asst Prof Clinician Educator |  |  |  | $635,325 | 2025 |
| Temple University | Pazionis, Theresa | Asst Prof Clinician Scholar |  |  |  | $631,031 | 2025 |
| Temple University | Krauss, Kristin | Professor Clinician Educator |  |  |  | $629,700 | 2025 |
| Temple University | Di Carlo, Antonio | Professor Clinician Scholar |  |  |  | $608,627 | 2025 |
| Temple University | Rae, Lisa | Assoc Prof Clinician Scholar |  |  |  | $592,267 | 2025 |
| Temple University | Goldberg, Marc | Professor Clinician Educator |  |  |  | $588,936 | 2025 |
| Temple University | Cuthbertson, Emily | Professor Clinician Educator |  |  |  | $584,669 | 2025 |
| Temple University | Power, Theresa | Assoc Prof Clinician Educator |  |  |  | $581,273 | 2025 |
| Temple University | Mydlo, Jack | Professor |  |  |  | $576,875 | 2025 |

</details>

### in_gateway: Indiana Gateway Form 100R Certified Report of Public Employment and Compensation (state universities and colleges) (IN)

Notes: Employee Compensation report, year 2012, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,863 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2012, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,901 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2012, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 50,312 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2012, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 12,245 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2012, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 35,303 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2012, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 6,140 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2012, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,765 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 11,018 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,162 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 50,605 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 12,390 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 35,389 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,253 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2013, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,806 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 11,133 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,499 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 51,539 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 12,067 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 35,804 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,585 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2014, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,878 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 11,112 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,738 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 49,486 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 12,072 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 36,653 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,461 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2015, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,930 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,945 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,873 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 49,102 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 11,473 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 37,624 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,342 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2016, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,898 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 11,090 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,852 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 50,384 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,905 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 37,860 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,321 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2017, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,809 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,832 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,745 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 50,941 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,566 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 38,381 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,708 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2018, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,570 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,389 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,382 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 50,525 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 10,446 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 37,390 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 5,158 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2019, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,542 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,908 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,550 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 47,664 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 9,433 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 33,820 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,593 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2020, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,285 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,306 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,354 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 47,881 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,570 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 33,284 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,379 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2021, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,089 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,481 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,237 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 50,422 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,510 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 35,488 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,522 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2022, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,123 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,787 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,030 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 51,816 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,674 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 37,694 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,456 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2023, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,117 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 9,144 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 3,867 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 52,269 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,881 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 39,551 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,844 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2024, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,147 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'Ball State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 8,933 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'Indiana State University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 3,745 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'Indiana University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 51,558 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'Ivy Tech Community College'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 9,104 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'Purdue University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 40,098 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'University of Southern Indiana'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 4,850 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes Employee Compensation report, year 2025, county 'State', unit 'Vincennes University'; SSRS CSV export (ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states 2,006 records. Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees obtained by viewing, printing or downloading will not be used for commercial or political purposes

- Rows: 1,679,632; with a pay value: 1,679,632 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 1; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2012 | 122,529 | 7 | $23,280 | $8,028 |
| 2013 | 122,623 | 7 | $23,701 | $8,044 |
| 2014 | 124,505 | 7 | $23,784 | $7,826 |
| 2015 | 123,452 | 7 | $24,538 | $8,015 |
| 2016 | 123,257 | 7 | $25,456 | $8,555 |
| 2017 | 124,221 | 7 | $26,193 | $8,582 |
| 2018 | 124,743 | 7 | $26,910 | $9,000 |
| 2019 | 121,832 | 7 | $28,144 | $9,823 |
| 2020 | 111,253 | 7 | $31,077 | $13,162 |
| 2021 | 108,863 | 7 | $31,674 | $14,072 |
| 2022 | 113,783 | 7 | $31,590 | $13,010 |
| 2023 | 117,574 | 7 | $32,774 | $13,216 |
| 2024 | 120,703 | 7 | $33,921 | $13,500 |
| 2025 | 120,294 | 7 | $35,329 | $14,097 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Indiana University | LANKFORD, DEBORAH A | HEALTH PLAN SER ASST | UNIVERSITY HUMAN RESOURCE SERV |  |  | $32,761 | 2012 |
| Purdue University | Novakovic, Bozidar | Post Doc Intern Res | WL - Electrical & Compute |  |  | $15,853 | 2012 |
| Indiana University | Fletcher, Kyle D | Student Hourly | ATHLETICS |  |  | $295 | 2013 |
| Indiana University | McCarty, Julia R | Temporary Staff | CANCER CENTER |  |  | $12,444 | 2013 |
| Indiana University | Copeland, Rusty R | AC2 Visiting Fac Summer Only | MATHEMATICS |  |  | $5,833 | 2013 |
| Purdue University | Knust, Kelli L | Student | WL - Women In Engineering |  |  | $334 | 2013 |
| Purdue University | Robinson, Shelly L | Mgmt/Prof | CAL - Career Services |  |  | $77,637 | 2013 |
| Purdue University | Frazier, Kimberly A | Admin/Prof | WL - Field Extension Educ |  |  | $55,821 | 2013 |
| University of Southern Indiana | Knust, Karla N | Student Worker | Academic Skills |  |  | $178 | 2013 |
| Ball State University | Swetlik, Zachary J | Grad Stipend (100100) | Technology |  |  | $5,229 | 2014 |
| Indiana University | Mills, Nancy A | AC2 Adjunct Faculty | MODERN FOREIGN LANGUAGES |  |  | $3,333 | 2014 |
| Indiana University | Zajmi, Agron D | Custodian | RESIDENTIAL PROGRAMS & SERV |  |  | $29,200 | 2014 |
| Ivy Tech Community College | Fry, Randall S | Maint Tech III | Facilities Maintenance |  |  | $33,161 | 2014 |
| Purdue University | Maassen, Jesse | Post Doc Intern Res | WL - Electrical & |  |  | $57,920 | 2014 |
| Indiana State University | James, Haylie M | Graduate Assistant | CD & Coun, School & Ed Psych |  |  | $6,281 | 2015 |
| Indiana University | Regoli, Michael | Dir Elect & Serials Publ | INDIANA UNIVERSITY PRESS |  |  | $62,904 | 2015 |
| Indiana University | Nebesio, Todd D | Clinical Faculty | PED-ENDOCRINOLOGY/DIABETOLOGY |  |  | $64,846 | 2015 |
| Indiana University | Moorthy, Ghurulakshmi | Resident Appointee | ENDOCRINOLOGY |  |  | $24,458 | 2015 |
| Indiana University | Rostad, Masumi P | Professor of Practice | JACOBS SCHOOL OF MUSIC |  |  | $123,848 | 2016 |
| Indiana University | Donahue, Lilly | Student Temporary | MIDDLE EASTERN STUDIES |  |  | $3,611 | 2016 |

</details>

### il_ibhe: Illinois Board of Higher Education public university salary search (all 12 public universities) (IL)

Notes: FY2010, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2010_Salaries.xls); HTML table served as application/ms-excel FY2011, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2011_Salaries.xls); HTML table served as application/ms-excel FY2012, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2012_Salaries.xls); HTML table served as application/ms-excel FY2013, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2013_Salaries.xls); HTML table served as application/ms-excel FY2014, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2014_Salaries.xls); HTML table served as application/ms-excel FY2015, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2015_Salaries.xls); HTML table served as application/ms-excel FY2016, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2016_Salaries.xls); HTML table served as application/ms-excel FY2017, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2017_Salaries.xls); HTML table served as application/ms-excel FY2018, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2018_Salaries.xls); HTML table served as application/ms-excel FY2019, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2019_Salaries.xls); HTML table served as application/ms-excel FY2020, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2020_Salaries.xls); HTML table served as application/ms-excel FY2021, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2021_Salaries.xls); HTML table served as application/ms-excel FY2022, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2022_Salaries.xls); HTML table served as application/ms-excel FY2023, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2023_Salaries.xls); HTML table served as application/ms-excel FY2024, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2024_Salaries.xls); HTML table served as application/ms-excel FY2025, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export (attachment; filename=2025_Salaries.xls); HTML table served as application/ms-excel

- Rows: 143,713; with a pay value: 143,713 (100.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 0; pay > $10M: 0; negative pay: 3

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2010 | 9,909 | 15 | $68,286 | $63,384 |
| 2011 | 9,228 | 15 | $66,947 | $62,600 |
| 2012 | 9,183 | 15 | $68,204 | $64,500 |
| 2013 | 8,976 | 15 | $71,404 | $66,105 |
| 2014 | 8,992 | 15 | $74,730 | $69,266 |
| 2015 | 8,996 | 15 | $75,699 | $70,574 |
| 2016 | 8,873 | 15 | $76,312 | $70,754 |
| 2017 | 8,669 | 15 | $78,907 | $72,960 |
| 2018 | 8,617 | 15 | $80,585 | $74,283 |
| 2019 | 8,573 | 15 | $82,193 | $75,312 |
| 2020 | 8,772 | 15 | $84,512 | $77,000 |
| 2021 | 8,660 | 15 | $87,506 | $79,572 |
| 2022 | 8,711 | 15 | $88,905 | $81,600 |
| 2023 | 8,998 | 15 | $92,410 | $84,779 |
| 2024 | 9,248 | 15 | $97,194 | $88,784 |
| 2025 | 9,308 | 15 | $100,553 | $91,779 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| University of Illinois Springfield | William Cowling | ADJ INSTR |  | $5,000 | $0 | $5,000 | 2010 |
| University of Illinois Urbana-Champaign | Eduardo H. Fradkin |  |  | $120,400 | $0 | $120,400 | 2010 |
| Governors State University | Rhonda N. Hudson | Academic Advisor |  | $5,624 | $0 | $5,624 | 2010 |
| Northern Illinois University | Scott F. Peska | Director, Office of Support & Advocacy |  | $71,580 | $1,000 | $72,580 | 2010 |
| Southern Illinois University Edwardsvill | Paul E. Brunkow | Chair |  | $90,659 | $0 | $90,659 | 2011 |
| University of Illinois Chicago | Thomas B. Golemon | RESIDENCY DIR |  | $150,268 | $0 | $150,268 | 2011 |
| Southern Illinois University Edwardsvill | Bradford J. Reed |  |  | $120,054 | $47,519 | $167,572 | 2011 |
| Eastern Illinois University | Sean A. Peebles |  |  | $68,844 | $0 | $68,844 | 2012 |
| University of Illinois Chicago | Andrew Roche | ADJ ASST PROF |  | $8,000 | $0 | $8,000 | 2012 |
| University of Illinois Chicago | Zhibo Yan | POSTDOC RES ASSOC |  | $6,000 | $0 | $6,000 | 2012 |
| University of Illinois Urbana-Champaign | Sanda Monica Dolcos | POSTDOC RES ASSOC |  | $41,679 | $0 | $41,679 | 2013 |
| University of Illinois Chicago | Dragoslav Gvozdjan | ASST PROF OF CLIN PSYCHIAT |  | $52,500 | $0 | $52,500 | 2013 |
| Southern Illinois University School of M | Jon O. Humphrey | Assistant Professor Family and Community |  | $100,008 | $0 | $100,008 | 2013 |
| Eastern Illinois University | Rosemary L. Painter | Continuing Ed Summer School |  | $0 | $2,500 | $2,500 | 2013 |
| University of Illinois Urbana-Champaign | M Taher A. Saif | PROF |  | $145,000 | $7,500 | $152,500 | 2013 |
| Chicago State University | Cathy E. Davis | Director of Financial Aid |  | $80,004 | $0 | $80,004 | 2014 |
| Northern Illinois University | Joanna Kot |  |  | $55,945 | $0 | $55,945 | 2014 |
| University of Illinois Urbana-Champaign | Julie A. Hengst | ASSOC PROF |  | $40,746 | $0 | $40,746 | 2015 |
| University of Illinois Chicago | Allison D. Phillips | DIR OF DEVLP STRATEGY |  | $75,000 | $0 | $75,000 | 2015 |
| Southern Illinois University School of M | Kathryn M. Waldyke | Assistant Professor Family and Community |  | $102,945 | $0 | $102,945 | 2015 |

</details>

## 990 link candidates (sample)

View `unipay.payroll_990_link_candidates` proposes links from payroll rows to `public.people` at 990 filers that are the institution itself (same normalized name and state) or an affiliated foundation (name contains the institution name and 'foundation', same state); see `unipay.payroll_institution_990_orgs`. EXACT = same normalized name; FUZZY = trigram similarity >= 0.9 with the same last-name token. These are unreviewed candidates only.

990 filers matched to **University of Connecticut**: UNIVERSITY OF CONNECTICUT FOUNDATION INCORPORATED (066070722, foundation)

| Match type | Candidate pairs | Distinct payroll names | Distinct 990 people rows |
|---|---|---|---|
| EXACT | 110 | 6 | 26 |

Sample query: `SELECT ... FROM unipay.payroll_990_link_candidates WHERE institution = 'University of Connecticut'` (one row per name and filer, latest year, top 25 by 990 compensation):

| Type | Sim | Payroll name | Payroll title | FY | Payroll pay | 990 name | 990 title | Tax yr | 990 comp (org + related) | 990 filer |
|---|---|---|---|---|---|---|---|---|---|---|
| EXACT | 1.000 | Martin, John | INSTR SPEC | 2019 | $500 | John Martin | Former President & CEO | 2016 | $328,243 | UNIVERSITY OF CONNECTICUT FOUNDATION INC (foundation) |
| EXACT | 1.000 | Edwards, Kevin A | INSTR SPEC | 2023 | $6,000 | Kevin A Edwards | Vice President | 2013 | $230,391 | UNIVERSITY OF CONNECTICUT FOUNDATION INC (foundation) |
| EXACT | 1.000 | Farooqi, Shahid | ADJUNCT FACULTY | 2019 | $6,224 | SHAHID FAROOQI | Director of Investments | 2019 | $156,270 | UNIVERSITY OF CONNECTICUT FOUNDATION INC (foundation) |
| EXACT | 1.000 | Bennett, Alan | UCSpecPayroll | 2017 | $1,500 | Alan Bennett | Dir until 11/14 | 2014 | $0 | UNIVERSITY OF CONNECTICUT FOUNDATION INC (foundation) |
| EXACT | 1.000 | Cantor, Michael A | UCSpecPayroll | 2015 | $500 | Michael A Cantor | Dir to 11/2016 | 2016 | $0 | UNIVERSITY OF CONNECTICUT FOUNDATION INC (foundation) |
| EXACT | 1.000 | Sherman, Robert | ADJUNCT FACULTY | 2027 | $1,916 | ROBERT SHERMAN | DIRECTOR | 2024 | $0 | UNIVERSITY OF CONNECTICUT FOUNDATION INC (foundation) |

Reading this sample: UConn itself does not file a 990 (it is a state institution), so the only matched filer is the UConn Foundation. The EXACT hits above are mostly common names (e.g. a $500 instructional specialist named John Martin vs the foundation's former CEO); candidates need review of title, year and pay before any link is accepted.

## Deliverables

### 15 best sources to integrate next

Ranked by people covered in the latest loaded year x a 1-5 quality grade (official source, full names, actual pay with components, history). Texas and Oklahoma rank high on head count but their names are truncated (first name + last initial; last name + initials), so they are poor for matching to 990s. The ranking is in `scripts/unipay/deliverables.py`.

| # | Source | People (latest yr) | Latest yr | Quality | Rows loaded | Why |
|---|---|---|---|---|---|---|
| 1 | in_gateway | 117,684 | 2025 | 4/5 | 1,679,632 | Official Form 100R; full names, title, department, calendar-year total compensation per position; all 7 IN public institutions; 2012-2025 |
| 2 | ga | 88,787 | 2025 | 4/5 | 1,419,662 | Official; full names, title, salary only (no split); FY2015-2025; foundation pay excluded |
| 3 | tx | 150,346 | 2026 | 2/5 | 170,130 | Volunteer TPIA compile; bulk export has first name + last initial only; base salary snapshot |
| 4 | wa | 87,594 | 2013 | 3/5 | 374,836 | Official; full names, title, annual salary; 2010-2013 only |
| 5 | oh_osu | 50,818 | 2025 | 5/5 | 240,592 | Official; calendar-year earnings with regular/bonus/OT/other/gross; department; 2021-2025 |
| 6 | ma | 48,407 | 2026 | 5/5 | 1,198,973 | Official; full names, title, base/OT/buyout/other/total actual pay; 2009-2026 |
| 7 | mi_um | 53,241 | 2026 | 4/5 | 54,659 | Official PDF; full names, title, annual FT rate, appointment fraction; all 3 campuses; FY2026 |
| 8 | il_stl | 44,744 | 2025 | 3/5 | 44,841 | Newsroom compile; full names, title, department, actual 2025 gross pay; UIUC, UIC, UIS, SIUE |
| 9 | ct | 24,760 | 2027 | 5/5 | 979,441 | Official paycheck-level data aggregated per FY; full names, title, base/OT/other/gross; FY2010-2027 |
| 10 | mo_um | 25,685 | 2026 | 4/5 | 193,293 | Official PDFs; full names, title, salary rate (+ W-2 wages in several years); all UM campuses + MU Health; multi-year |
| 11 | ok | 81,220 | 2026 | 1/5 | 394,645 | Official but names are last name + initials, no title; monthly payment lines |
| 12 | nyc | 15,782 | 2025 | 5/5 | 262,569 | Official; full names, title, regular/OT/other paid; CUNY community colleges only |
| 13 | ks | 25,317 | 2025 | 3/5 | 122,263 | Third-party compile of KORA records; full names, title, total pay; 2021-2025 |
| 14 | mn | 17,334 | 2026 | 4/5 | 313,601 | Official; full names, title, department, FY earnings (all state positions); Minnesota State only |
| 15 | mo_stl | 22,950 | 2025 | 3/5 | 22,951 | Newsroom compile; full names, title, department, actual 2025 gross pay; MU campuses, MU Health, STLCC, SCC |

Not yet loaded but worth doing next (each needs an owner decision): Illinois IBHE salary search (all 12 public universities; ASP.NET postback export), Indiana Gateway (all public institutions; non-commercial-use agreement), Washington LEAP salary file (email request), Arkansas ADHE FY10-FY25 PDFs (same parser as FY26).

### 10 states with the biggest gaps

States with nothing loaded, weakest best-source rating first, then by size of public higher ed (IPEDS full-time instructional staff at public institutions, 2023-24).

| State | Best rating | Public FT instructional staff (IPEDS) | Rows loaded | Gap (Phase 1 notes) |
|---|---|---|---|---|
| California (CA) | C | 46,162 | 0 | No official bulk, person-level file exists for any California higher-ed system. UC names are behind a search form, and CSU and community college names come only from third parties: Transparent California (now behind a fr |
| North Carolina (NC) | C | 17,440 | 0 | No bulk file or API for the UNC System; only the current quarterly snapshot, no history; no pay beyond base salary (no overtime/other/total pay). No published person-level pay for the 58 community colleges (excluded from |
| Virginia (VA) | C | 13,346 | 0 | No official named, person-level pay file for any Virginia public university or VCCS. Data Point drops names. The only named data is the VCIJ/WHRO 2025 search tool (and older Richmond Times-Dispatch and Washington Busines |
| Wisconsin (WI) | C | 9,895 | 0 | No public, official, named person-level pay file for any Universities of Wisconsin campus or WTCS district. The current Redbook and compensation dashboards are internal. Would need Wisconsin public-records requests (UW S |
| Alabama (AL) | C | 8,965 | 0 | No official person-level salary publication found for any Alabama public university or ACCS. open.alabama.gov has spending/contracts but no payroll. Universities are outside state payroll, so data would require Alabama O |
| Louisiana (LA) | C | 6,595 | 0 | No official published person-level pay for any Louisiana public university system or LCTCS. Regents EMPSAL holds the data but does not publish it. Checkbook coverage of higher ed unconfirmed and robots-blocked. |
| Kentucky (KY) | C | 6,094 | 0 | No official bulk or HTML person-level salary publication found for any Kentucky public university or KCTCS. Universities run their own payrolls outside the state Personnel Cabinet. Not checked individually: EKU, Murray S |
| Mississippi (MS) | C | 5,793 | 0 | No official person-level salary publication found for IHL universities or community colleges; no newspaper salary database found. IHL Annual Workforce Report (slds.ms.gov) is aggregate. Data would require Mississippi Pub |
| Oregon (OR) | C | 5,626 | 0 | No official published person-level pay for any Oregon public university or community college. The state DAS salary dataset has no names and excludes higher ed. Getting real data means public records requests to each of t |
| West Virginia (WV) | C | 3,054 | 0 | No confirmed bulk, named, person-level download for any WV public college. WVU and Marshall run their own payroll and publish no salary lists. Would need to check the OpenGov grid in a browser for export, or file WV FOIA |

### Counts

- States researched (Phase 1): 51 (50 states + DC)
- States with payroll records loaded: 26
- Catalog sources by rating: A: 30, B: 27, C: 94, D: 34
- Catalog sources marked loaded: 39
- Records loaded: 8,565,181
- Institutions covered (distinct state + institution labels): 562

- IPEDS institution-average rows: 15,300 for 3,818 institutions (`unipay.ipeds_faculty_salary_averages`; AVERAGES by rank, not individual pay)

### 10 well-known people at one large loaded system (The Ohio State University, calendar 2025 earnings)

Selected by title (president, head coaches, athletic director, provost, medical leadership); pay as published.

| Name (as published) | Title | Cost center | Year | Regular | Bonus + OT + other | Gross | Components |
|---|---|---|---|---|---|---|---|
| Day, Ryan | Head Coach-Major Sports | CC12637 Athletics / Football | 2025 | $2,000,000 | $11,387,554 | $13,387,554 | `{"bonus": 2100000.0, "gross": 13387554.36, "other": 9287554.32, "regular": 2000000.04, "overtime": 0.0, "position_group": "Athletics"}` |
| Diebler, Jacob | Head Coach-Major Sports | CC12633 Athletics / Basketball Men | 2025 | $800,000 | $1,764,400 | $2,564,400 | `{"bonus": 50000.0, "gross": 2564400.06, "other": 1714400.02, "regular": 800000.04, "overtime": 0.0, "position_group": "Athletics"}` |
| Holtmann, Christopher | Head Coach-Major Sports | CC12633 Athletics / Basketball Men | 2025 | $0 | $1,882,000 | $1,882,000 | `{"bonus": 0.0, "gross": 1881999.96, "other": 1881999.96, "regular": 0.0, "overtime": 0.0, "position_group": "Athletics"}` |
| Carter, Walter | President | CC10433 President / Office of the President | 2025 | $1,155,578 | $448,475 | $1,604,053 | `{"bonus": 398475.0, "gross": 1604052.52, "other": 50000.0, "regular": 1155577.52, "overtime": 0.0, "position_group": "University"}` |
| Bellamkonda, Ravi | Exec Vice President & Provost | CC13097 Academic Affairs Administration / Off | 2025 | $807,723 | $389,147 | $1,196,869 | `{"bonus": 338917.81, "gross": 1196869.49, "other": 50228.83, "regular": 807722.85, "overtime": 0.0, "position_group": "University"}` |
| McGuff, Kevin | Head Coach-Major Sports | CC12649 Athletics / Basketball Women | 2025 | $646,388 | $522,286 | $1,168,674 | `{"bonus": 90000.0, "gross": 1168673.61, "other": 432285.63, "regular": 646387.98, "overtime": 0.0, "position_group": "Athletics"}` |
| Rohlik, Steve | Head Coach | CC12648 Athletics / Ice Hockey Men | 2025 | $547,731 | $48,583 | $596,314 | `{"bonus": 44983.0, "gross": 596314.48, "other": 3600.0, "regular": 547731.48, "overtime": 0.0, "position_group": "Athletics"}` |
| Tucker, Ty | Head Coach | CC12643 Athletics / Tennis Men | 2025 | $407,500 | $103,050 | $510,550 | `{"bonus": 99450.0, "gross": 510550.02, "other": 3600.0, "regular": 407500.02, "overtime": 0.0, "position_group": "Athletics"}` |
| Ryan, Thomas | Head Coach | CC12646 Athletics / Wrestling | 2025 | $451,337 | $59,200 | $510,537 | `{"bonus": 0.0, "gross": 510537.16, "other": 59200.0, "regular": 451337.16, "overtime": 0.0, "position_group": "Athletics"}` |
| HAIRE, Justin | Head Coach | CC12651 Athletics / Baseball Men | 2025 | $490,254 | $17,700 | $507,954 | `{"bonus": 0.0, "gross": 507954.2, "other": 17700.0, "regular": 490254.2, "overtime": 0.0, "position_group": "Athletics"}` |

