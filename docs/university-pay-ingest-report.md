# University pay ingest report

Generated 2026-10-18 16:41 (America/Chicago) by `scripts/unipay/report.py`. Staging data only (schema `unipay`); nothing here is on the site.

## Summary

- Sources loaded: **38** (from 25 states/DC)
- Records loaded: **6,538,996** into `unipay.public_payroll_records`
- Institutions (distinct state + institution labels): **532**

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
| mo_um | MO | University of Missouri System annual salary report (MOspace PDFs) | 1 | 25,688 | 2026-2026 | 6 | 25,685 | 92 |
| mo_msu | MO | Missouri State University FY27 internal operating budget, Detail Full- | 1 | 2,187 | 2027-2027 | 2 | 2,042 | 94 |
| il_isu | IL | Illinois State University salary lists (FY2023, FY2024 PDFs) | 1 | 3,681 | 2024-2024 | 1 | 3,674 | 60 |
| vt_uvm | VT | University of Vermont List of Base Pay (PDF) | 17 | 70,348 | 2010-2026 | 1 | 15,116 | 170 |
| nm_nmhu | NM | New Mexico Highlands University salary reports (PDF) | 4 | 2,873 | 2023-2026 | 1 | 1,707 | 120 |
| tn_apsu | TN | Austin Peay State University employee salary data (PDF) | 1 | 1,158 | 2027-2027 | 1 | 1,156 | 153 |
| tn_etsu | TN | East Tennessee State University active employees (PDF) | 1 | 2,473 | 2024-2024 | 1 | 2,471 | 154 |
| mi_um | MI | University of Michigan Salary Record (PDF) | 1 | 54,659 | 2026-2026 | 3 | 53,241 | 84 |
| me_hist | ME | University of Maine System salaries of regular employees (historical P | 4 | 18,453 | 2020-2022 | 9 | 5,721 | 82 |
| dc_hist | DC | DC DCHR quarterly public body employee listings (UDC rows), Dec 2013 - | 7 | 8,276 | 2014-2022 | 1 | 2,858 | 34 |
| ar_adhe | AR | Arkansas Division of Higher Education Administrator's Compensation Sur | 1 | 1,547 | 2026-2026 | 39 | 1,546 | 10 |
| pa_pitt | PA | University of Pittsburgh 200 highest-paid non-officers (Right-to-Know  | 2 | 400 | 2024-2025 | 1 | 244 | 142 |
| pa_temple | PA | Temple University 200 highest-paid employees other than officers (Righ | 2 | 400 | 2023-2025 | 1 | 246 | 143 |

## Skipped or deferred sources

| State | Source | Why |
|---|---|---|
| RI | transparency.ri.gov payroll CSV (A) | robots.txt has `User-agent: * / Disallow: /`; honored, not downloaded. |
| FL | Board of Governors SUS payroll APEX export (A) | robots.txt on prod.flbog.net disallows all agents; export is also session-bound. |
| FL | Florida College System salaries (B) | Export only through a JS search UI with an undocumented API. |
| IA | Iowa Data Hub state salary book (A) | Re-checked Oct 2026: Next.js page with a client-side download button only; no static or GET data URL in the HTML. |
| NV | Transparent Nevada NSHE CSVs (A) | Re-checked Oct 2026: download is a JS button; GET of the CSV name redirects to an HTML page. |
| UT | Transparent Utah compensation downloader (A) | Bulk files come from an undocumented Cloud Run query service used by the JS app; not attempted. |
| WA | LEAP / fiscal.wa.gov state employee salaries (B) | Only newer official WA person-level data. Web view is a Power BI embed (queries are POSTs to Power BI); bulk file needs an email request. Not attempted (no forms/emails). data.wa.gov has nothing after 2013. |
| TX | Full-name Texas university salaries | texascollegesalaries.com is behind a Cloudflare JS challenge; Texas Tribune explorer (now only the 116 Comptroller agencies, no universities) has no higher-ed rows. No plain-GET full-name source found. |
| OK | Full-name Oklahoma payroll | data.ok.gov payroll files 2010-2026 all publish last name + initials; OpenTheBooks is anti-bot; Oklahoma Watch site no longer resolves. |
| MO | data.mo.gov state payroll (A) | Does not cover colleges or universities. |
| NJ | NJ centralized payroll iqwc-r2w7 (A) | Does not cover institutions. |
| MA | CTHRU quasi-public payroll tc5d-8ckm (A) | Peripheral (quasi-public agencies, not institutions). |
| CT | CT payroll FY2010-2014 ajs4-6pgz (A) | Covered by 9m78-yc88, which starts in FY2010. |
| OH | Ohio State salary snapshots (A) | Downloaded but not loaded: same people as the earnings files; rate, not pay. Kept on disk. |
| PA | PennWatch PASSHE / Thaddeus Stevens salaries (B) | Re-checked Oct 2026: GET with agency/date parameters returns 'No Data Found'; results need a POST with an anti-forgery token. Not submitted. |
| PA | Penn State top-200 PDF (B) | Cloudflare challenge; skipped. |
| IL | IBHE public university salary search (B) | Excel export is an ASP.NET postback (form submission); not attempted. |
| IL | Illinois State FY2023 / FY2025+ PDFs (B) | FY2023 layout not reliably extractable; FY2025+ behind a Cloudflare challenge. |
| IL | University of Illinois FY26 Salary Book PDF (B) | Redundant: Gray Book 2026-27 (loaded) carries present FY2026 salary; UI gross pay comes from il_stl. |
| IN | Indiana Gateway higher-ed salaries (B) | Per-unit report export after accepting a non-commercial-use agreement; not attempted (agreement needs owner review). |
| ID | Transparent Idaho (B) | JS single-page app; no plain-HTTP data endpoint. |
| MO | UM System 2024-25 salary PDF (B) | Downloaded; ligatures and fused columns make extraction unreliable; 2025-26 loaded instead. |
| MI | Western Michigan employee list PDF (B) | No employee names (position, FTE, salary only); not person-level. |
| CO | University of Colorado personnel roster PDF (B) | No employee names (anonymized roster IDs). |
| DC | UDC quarterly listings FY2016, FY2019, Dec 2013 (B) | No table rules in those PDFs (multi-word names cannot be split reliably) / no agency column; other years loaded. |
| AR | ADHE administrator compensation FY10-FY25 (B) | Same layout as FY26 (loaded); not fetched in this pass (about 20 min of PDF parsing per year on the dev box). |
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
- mo_stl vs mo_um: same University of Missouri people; mo_stl is 2025 gross pay (newsroom), mo_um is the official FY2026 salary rate + W-2.

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
| Charter Oak State College | Crooms, Melanie C | COSCAdjunctFaculty | Bd State Acdmc Awds | $2,310 | $0 | $2,310 | 2024 |
| University of Connecticut | Kane, Rowan L. | ADJUNCT FACULTY | Urban Studies Program | $12,372 | $0 | $12,372 | 2025 |
| Capital Community College | Undisclosed, Undisclosed Undisclose | CCStdntWkr-Disc |  | $420 | $0 | $420 | 2011 |
| Charter Oak State College | Undisclosed, Undisclosed Undisclose | BSAAStudntWkr |  | $11,751 | $0 | $5,876 | 2012 |
| Southern Connecticut State University | Undisclosed, Undisclosed Undisclose | GraduateAssistant |  | $12,000 | $0 | $12,000 | 2012 |
| UConn Health | Waller, Nekita | UCHC UniversityHealthProf |  | $44,589 | $0 | $44,589 | 2013 |
| University of Connecticut | Undisclosed, Undisclosed Undisclose | UnivStudentWorker |  | $3,776 | $0 | $3,776 | 2013 |
| Naugatuck Valley Community College | Wright, Susan B. | HumanResourcesAssistant |  | $50,966 | $0 | $50,966 | 2013 |
| Central Connecticut State University | Kapral, Constance J. | SULecturer |  | $11,653 | $0 | $11,653 | 2014 |
| Manchester Community College | Van Rynbach, Iris | CC NCL |  | $900 | $0 | $900 | 2015 |
| University of Connecticut | Quetant, Sabine | UCSpecPayroll |  | $16,016 | $0 | $16,016 | 2015 |
| Gateway Community College | Nigam, Chaitanya | CCCPartTimeLecturer |  | $16,630 | $0 | $16,630 | 2016 |
| University of Connecticut | Rogers, Helen J. | RESEARCH SPEC |  | $5,640 | $0 | $5,640 | 2017 |
| University of Connecticut | Caldera, Yolanda | UCSpecPayroll |  | $5,450 | $0 | $5,450 | 2017 |
| University of Connecticut | Awino, Valerie A | UConnFaculty/Staff |  | $5,815 | $1,209 | $7,024 | 2017 |
| Middlesex Community College | Chapman, Louise | CCCPartTimeLecturer |  | $11,225 | $0 | $11,225 | 2018 |
| Naugatuck Valley Community College | Arzu, Max K. | CCEducAsst9-19 |  | $16,505 | $0 | $16,505 | 2018 |
| Central Connecticut State University | Petkova, Olga S. | SUProfr(10Months) |  | $118,849 | $4,751 | $123,700 | 2019 |
| Eastern Connecticut State University | Vasington, Anik M. | SUAdmin3 |  | $70,724 | $0 | $70,724 | 2019 |
| Western Connecticut State University | Piscopo, Barbara C. | SULecturer |  | $10,170 | $0 | $10,170 | 2019 |

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
| Bristol Community College | Driscoll, Kathleen | Adjunct Instructor | BRISTOL COMMUNITY COLLEGE (BRC) | $28,065 | $0 | $28,065 | 2012 |
| North Shore Community College | Muldoon, Kaitlin | Cntrct EEs NOtherwise Categor | NORTH SHORE COMMUNITY COLLEGE (NSC) | $9,885 | $61 | $9,946 | 2012 |
| University of Massachusetts Amherst | Viteri Mejia, Cesar | Departmental Assistant | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $6,100 | $0 | $6,100 | 2012 |
| University of Massachusetts Lowell | Morris, Mary Ellen | Adjunct Faculty | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $12,588 | $0 | $12,588 | 2012 |
| Bridgewater State University | Mahoney, Penelope | Orff Schulwerk Instructor | BRIDGEWATER STATE UNIVERSITY (BSC) | $3,939 | $0 | $3,939 | 2012 |
| Worcester State University | Sullivan-Jacques, Serenity | LEI - 535400 | WORCESTER STATE UNIVERSITY (WOR) | $2,168 | $0 | $2,168 | 2012 |
| University of Massachusetts Amherst | Jordan, Amina | Departmental Assistant | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $4,240 | $0 | $4,240 | 2012 |
| Cape Cod Community College | Yacek, Chester | Dean | CAPE COD COMMUNITY COLLEGE (CCC) | $109,988 | $0 | $109,988 | 2012 |
| Bridgewater State University | Schleicher, Nicholas | EAS Day Unit Visiting Lecturer | BRIDGEWATER STATE UNIVERSITY (BSC) | $6,008 | $0 | $6,008 | 2012 |
| UMass Chan Medical School | Kachinski, Michelle | Coord, Admin Iii | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $57,268 | $0 | $57,268 | 2013 |
| University of Massachusetts Amherst | Akisik, Orhan | Lecturer U of M | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $66,179 | $25,444 | $91,623 | 2013 |
| Framingham State University | Nicholl, Susan | State Coll Non Unit Visit Lect | FRAMINGHAM STATE UNIVERSITY (FRC) | $1,201 | $0 | $1,201 | 2013 |
| Bristol Community College | Shaw, Paula | Adjunct Instructor | BRISTOL COMMUNITY COLLEGE (BRC) | $5,862 | $0 | $5,862 | 2013 |
| University of Massachusetts Boston | Papargjir, Mimoza | Clerk III | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $5,743 | $0 | $5,743 | 2013 |
| Bristol Community College | Donovan, Amanda | DeveloperEvent Participant | BRISTOL COMMUNITY COLLEGE (BRC) | $1,500 | $0 | $1,500 | 2014 |
| Northern Essex Community College | Romano, Laura | Adjuncts Foundational Studies | NORTHERN ESSEX COMMUNITY COLLEGE (N | $6,488 | $0 | $6,488 | 2014 |
| Roxbury Community College | Nolan, Joyce | Maintainer I | ROXBURY COMMUNITY COLLEGE (RCC) | $21,973 | $567 | $22,540 | 2014 |
| University of Massachusetts Amherst | Bell, Rebecca | Advisor, Career Services | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $45,692 | $0 | $45,692 | 2014 |
| University of Massachusetts Boston | Fu, Harry | Post Doctoral Research Fellow | UNIVERSITY OF MASSACHUSETTS SYSTEM  | $1,929 | $5,884 | $7,813 | 2014 |
| Bunker Hill Community College | Piantedosi, John | Cntrct EEs NOtherwise Categor | BUNKER HILL COMMUNITY COLLEGE (BHC) | $26,540 | $0 | $26,540 | 2014 |

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
| Hostos Community College | CHARDAVOYNE, ESTHER M | SENIOR VICE PRESIDENT |  | $191,610 | $0 | $191,610 | 2014 |
| LaGuardia Community College | NEGOUAI, JEAN JOSEPH T | COLLEGE ASSISTANT |  | $7,794 | $501 | $8,295 | 2014 |
| Queensboro Community College | RIVERA, GISELA | NON-TEACHING ADJUNCT I |  | $1,751 | $0 | $1,751 | 2014 |
| Queensboro Community College | SINGH, MICHELLE H | COLLEGE ASSISTANT |  | $11,449 | $0 | $11,449 | 2014 |
| Guttman Community College | NOVELLO, JOHN C | COLLEGE SECURITY SPECIALIST |  | $14,083 | $7,585 | $21,669 | 2014 |
| Kingsboro Community College | JN PIERRE, MELISA | LECTURER | BROOKLYN | $8,986 | $0 | $8,986 | 2015 |
| LaGuardia Community College | KYRIACOU, JONATHAN P | CONTINUING EDUCATION TEACHER | QUEENS | $796 | $0 | $796 | 2015 |
| Borough of Manhattan Community College | HUANG, JUAN LI | COLLEGE ACCOUNTING ASSISTANT | MANHATTAN | $16,615 | $976 | $17,591 | 2015 |
| Queensboro Community College | OBRIEN, JULIA R | COLLEGE ASSISTANT | QUEENS | $10,886 | $0 | $10,886 | 2015 |
| LaGuardia Community College | DAMATO, BO | ADJUNCT LECTURER | QUEENS | $5,836 | $0 | $5,836 | 2016 |
| LaGuardia Community College | GERTNER, DANIEL M | ADJUNCT ASSISTANT PROFESSOR | QUEENS | $31,177 | $0 | $31,177 | 2016 |
| LaGuardia Community College | HAMED, MUTAZ A | COLLEGE ASSISTANT | QUEENS | $10,299 | $581 | $10,880 | 2016 |
| Borough of Manhattan Community College | GREENE, SHANIQUA | IT SUPPORT ASSISTANT | MANHATTAN | $28,644 | $11 | $28,655 | 2016 |
| Borough of Manhattan Community College | NIXON, COLIN | CAMPUS PUBLIC SAFETY SERGEANT | MANHATTAN | $49,867 | $5,565 | $55,432 | 2016 |
| Borough of Manhattan Community College | RODGERS, KELLY A | NON-TEACHING ADJUNCT III | MANHATTAN | $500 | $0 | $500 | 2016 |
| Queensboro Community College | BALCH, LLOYD M | HIGHER EDUCATION ASSOCIATE | QUEENS | $96,114 | $0 | $96,114 | 2016 |
| Queensboro Community College | CUADROS, DENNIS | ADJUNCT LECTURER | QUEENS | $10,417 | $0 | $10,417 | 2016 |
| Queensboro Community College | MONAHAN, ANTHONY LOUIS | ASSISTANT PROFESSOR | QUEENS | $3,353 | $0 | $3,353 | 2016 |
| Queensboro Community College | MYLES, WILLIAM S | ADJUNCT LECTURER | QUEENS | $13,316 | $0 | $13,316 | 2016 |
| Hostos Community College | BAS, UGURCAN | COLLEGE ASSISTANT | BRONX | $126 | $0 | $126 | 2017 |

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
| University of Georgia | TINCHER,JILL FRAZIER | DIRECTOR DIV/DPT AD |  |  |  | $242,093 | 2023 |
| University of Georgia | CUNNINGHAM,COURTNEY | IT APPLICATION PROFESSIONAL |  |  |  | $37,307 | 2023 |
| Central Georgia Technical College | PERRY,SHAVONDA LAVETTE LASHA | INSTRUCTIONAL AIDE |  |  |  | $10,448 | 2023 |
| Georgia Gwinnett College | THORNTON,CHANDRA V | PART TIME INSTRUCTOR |  |  |  | $23,760 | 2025 |
| Augusta University | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $3,142 | 2025 |
| University of Georgia | PINYAN,HENRY | IT APPLICATION PROFESSIONAL |  |  |  | $43,500 | 2025 |
| University of Georgia | SANDS,AMANDA | BUSINESS OPERATIONS PROFESSIONAL |  |  |  | $12,418 | 2015 |
| Georgia Regents University | KENYON,TINA MARIE | OFFICE / CLERICAL ASSISTANT |  |  |  | $19,120 | 2015 |
| University of Georgia | PRICHARD,PHILIP W | PUBLIC SERVICE PARA/PRO |  |  |  | $7,880 | 2022 |
| University of Georgia | COLBERT,MOZAN RONEL | TEMPORARY PROFESSIONAL |  |  |  | $2,813 | 2022 |
| Atlanta Metropolitan State College | CHAMBERS,TARITA | LIBRARY PROFESSIONAL AD |  |  |  | $53,626 | 2022 |
| South Georgia Technical College | RUSSELL,MICHAEL | ADJUNCT FACULTY (HRLY) |  |  |  | $11,264 | 2021 |
| Georgia State University | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $3,005 | 2019 |
| University of Georgia | LAVENDER,CHERYL ANDERSON | BUSINESS OPER PROFESSIONAL |  |  |  | $72,750 | 2021 |
| University of Georgia | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $2,277 | 2021 |
| University of Georgia | STUDENT EMPLOYEE | GRADUATE ASSISTANT |  |  |  | $21,294 | 2021 |
| Georgia State University | STUDENT EMPLOYEE | GRADUATE RESEARCH ASSISTANT |  |  |  | $7,137 | 2022 |
| Athens Technical College | STATOM,CHASITY A | CASHIER (TCSG) |  |  |  | $20,700 | 2015 |
| Georgia Institute of Technology | MERRITT,MIRANDA | TEMPORARY OFFICE CLERICAL |  |  |  | $4,785 | 2023 |
| Georgia College & State University | STUDENT EMPLOYEE | STUDENT ASSISTANT |  |  |  | $3,437 | 2015 |

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
| Texas Woman's University | Jennifer G | Sta.coord Family Services | University Housing & Dining | $42,000 |  |  | 2026 |
| Texas Woman's University | Damien H | Fac.asst Prof | Department of Language, Culture & G | $65,650 |  |  | 2026 |
| Texas Tech | David L S | Professor | School of Music | $100,078 |  |  | 2026 |
| Austin Community College | Stephanie L | Manager, Technical Support | Information Technology | $127,997 |  |  | 2026 |
| The University of Texas at Austin | Nadia G | Admissions Application Review Specialist | Office of Admissions | $41,600 |  |  | 2026 |
| University of Houston | Annette G G | Dir, Program 1 | Business Operations | $70,000 |  |  | 2026 |
| University of Houston | Barialy R | Skilled Trades Tech 3 | Facilities Operations for SS | $44,865 |  |  | 2026 |
| Lone Star Community College | Troy E H | Professor Arts | Art | $97,327 |  |  | 2026 |
| University of North Texas | Shauna B | Program Director | DSA-Frisco | $90,543 |  |  | 2026 |
| University of North Texas | Miles B | Parking & Transport Attendant | Parking Services | $31,500 |  |  | 2026 |
| Lone Star Community College | Jada R V | Advisor Ii | Advising | $47,807 |  |  | 2026 |
| University of North Texas | Jeff G | Academic Advisor | RCOB-Undergrad Programs | $43,888 |  |  | 2026 |
| University of North Texas | Renee G | Research Scientist I | Educational Psychology | $67,000 |  |  | 2026 |
| The University of Texas at Dallas | Ignacio M | Research Associate | Chemistry | $50,000 |  |  | 2026 |
| The University of Texas at Austin | Diego O | Project Manager | Special Education | $82,000 |  |  | 2026 |
| The University of Texas at Austin | RUBICELIA P G | Building Attendant Ii | University Housing and Dining | $39,657 |  |  | 2026 |
| Texas State University | Faisal H A | Assoc Professor Of Instruction | School of Health Administration | $82,500 |  |  | 2026 |
| Texas State University | Charles A B | Systems Support Spec Ii | Philosophy | $60,071 |  |  | 2026 |
| Texas State University | Kevin A F | Professor | Conslng, Ldrship, Adlt Educ & Schl  | $124,897 |  |  | 2026 |
| Texas State University | Toni D M | Assistant Professor | School of Social Work | $96,375 |  |  | 2026 |

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
| College of DuPage | KRENEK, CRAIG WILLIAM | PART TIME FACULTY - BASIC | Instructional | $21,749 | $0 | $21,749 | 2016 |
| Triton College | HADAC, JAMES | ADULT BASIC EDUCATION ADJUNCT | Instructional | $10,792 | $1,046 | $11,838 | 2016 |
| William Rainey Harper College | LORENZ, BRENNA E | ASSOCIATE PROFESSOR | Instructional | $83,739 | $0 | $83,739 | 2016 |
| William Rainey Harper College | PINTER, KELLY M | ADJUNCT FACULTY | Instructional | $24,672 | $0 | $24,672 | 2016 |
| Southwestern Illinois College | FIRSE, SHIRLEY GRUND | PART TTIME FACULTY RETIREE HRO PROGRAM | Instructional | $648 | $0 | $648 | 2016 |
| Mc Henry County College | JACOBS, JOANN | ADJ FAC MCC 101 & 102 | Instructional | $4,850 | $0 | $4,850 | 2016 |
| College of Lake County | BAGSHAW, MARIANNA DEMEO | PT FACULTY - CREDIT COURSES | Instructional | $2,715 | $0 | $2,715 | 2016 |
| College of Lake County | HIPP, LINDA R | PT FACULTY - CREDIT COURSES | Instructional | $21,714 | $4,009 | $25,723 | 2016 |
| College of DuPage | CROOKER, JAMES WILLIAM | PART TIME FACULTY - BASIC | Instructional | $6,246 | $0 | $6,246 | 2017 |
| College of DuPage | NIGGINS, MELISSA MARIE | PART TIME FACULTY - BASIC | Instructional | $5,693 | $0 | $5,693 | 2017 |
| Triton College | DYER, MARIA-TEREZA LINS | PSYCHOLOGY FACULTY | Instructional | $77,011 | $0 | $77,011 | 2017 |
| Parkland College | WEFEL, KATRINA L | PART-TIME FACULTY | Instructional | $37,007 | $0 | $37,007 | 2017 |
| Highland Community College | VISEL, DOUGLAS | PT INSTRUCTOR | Instructional | $0 | $0 | $0 | 2017 |
| Kankakee Community College | SCHAFER, LOLA M | ADJUNCT RESPIRATORY THERAPY | Instructional | $18,087 | $0 | $18,087 | 2017 |
| Morton College | STANEVICIUS, RAMONA | PT FACULTY, NURSING | Instructional | $1,579 | $0 | $1,579 | 2017 |
| College of Lake County | KEYZER, JOHN M | PT FACULTY - CREDIT COURSES | Instructional | $12,036 | $168 | $12,204 | 2017 |
| Lewis and Clark Community College | HEINEY-YOUNG, RHONDA L | ADJUNCT FACULTY | Instructional | $8,688 | $0 | $8,688 | 2017 |
| Lewis and Clark Community College | WELLHAUSEN, KEVIN M | PROFESSOR | Instructional | $82,892 | $27,628 | $110,520 | 2017 |
| Wilbur Wright College | POROMANSKA, MARGARITA K | LECTURER-CREDIT COURSE I-UNION | Instructional | $0 | $400 | $400 | 2018 |
| Illinois Central College | SHERWOOD, M ANNETTE | ADJUNCT FACULTY | Instructional | $2,514 | $0 | $2,514 | 2018 |

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
| The Ohio State University | Haifley, Kristen | Fiscal Officer | CC11676 Business and Finance / Proc | $55,696 | $500 | $56,196 | 2021 |
| The Ohio State University | Heggestad, Robert | Program Assistant | CC11186 EHE / Teaching and Learning | $7,150 | $0 | $7,150 | 2021 |
| The Ohio State University | Kavanagh, Andrea | Vet Care Tch-Ans, PM & CC | CC10627 Veterinary Medical Center / | $1,708 | $0 | $1,708 | 2021 |
| The Ohio State University | Kazimi, Maher | Clinical Research Coordinator-NE | CC11125 CCC / Clinical Trials Offic | $16,789 | $396 | $17,184 | 2021 |
| The Ohio State University | Nikolaus, Rebecca | Staff Nurse-B (HS) | CC98071 Ross / 4 Ross Cardiovascula | $54,424 | $1,478 | $55,902 | 2021 |
| The Ohio State University | Novotny, Matthew | Laboratory Animal Technician 1 | CC10974 ERIK / University Laborator | $34,771 | $3,695 | $38,467 | 2021 |
| The Ohio State University | Phelps, Tyler | Golf Course Worker 2 | CC12695 Athletics / Golf Course Ope | $19,004 | $943 | $19,947 | 2021 |
| The Ohio State University | Ray, Kamal | Research Associate 1-B/H-NE | CC12291 Arts and Sciences / Chemist | $41,818 | $3,889 | $45,707 | 2021 |
| The Ohio State University | Spisak, Matthew | Project Manager-Fac Ops Dev | CC12574 Administration and Planning | $51,065 | $1,500 | $52,565 | 2021 |
| The Ohio State University | Whiteside, Danny | Auxiliary Ems/Fire Prev Ofcr | CC13029 Administration and Planning | $986 | $0 | $986 | 2021 |
| The Ohio State University | Wolf, Donna | Assistant Director | CC11005 Advancement / Development G | $78,163 | $1,000 | $79,163 | 2021 |
| The Ohio State University | Johnson, Ryan | Research Development Partnerships Analys | CC11299 Medicine / IM Medical Oncol | $77,656 | $500 | $78,156 | 2022 |
| The Ohio State University | Feyes, Emily | Academic Director | CC10589 Veterinary Medicine / Veter | $119,050 | $4,000 | $123,050 | 2022 |
| The Ohio State University | DeAndrea, David | Associate Professor (9M) | CC12404 Arts and Sciences / School  | $104,013 | $11,534 | $115,547 | 2022 |
| The Ohio State University | Stewart, Yolanda | Lecturer (SEM) | CC11171 EHE / Accreditation, Placem | $24,000 | $0 | $24,000 | 2022 |
| The Ohio State University | Rozario, Chantal | Inpatient Registered Nurse 2 | CC97746 East / Nursing Services | $73,231 | $7,900 | $81,130 | 2022 |
| The Ohio State University | Negash, Negash | Reporting and Analytics Analyst 2 | CC13750 ERIK / Office of Strategic  | $75,750 | $0 | $75,750 | 2022 |
| The Ohio State University | Hetrick, Jessica | Occupational Therapist 2 | CC99304 University Hospital / Rehab | $65,855 | $3,200 | $69,055 | 2022 |
| The Ohio State University | Smith, Craig | Event Services Associate 1 | CC12642 Athletics / General | $504 | $0 | $504 | 2022 |
| The Ohio State University | Levering, Melody | Internal Resource Pool Nurse (HS) | CC94115 Ambulatory Services / Perin | $13,712 | $0 | $13,712 | 2022 |

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
| Ohio University | Blazier, Sarah C | Manager, Online Student Success | STUDENT SERVICES AND RETENTION SUPP | $70,000 |  | $55,705 | 2025 |
| Ohio University | Wright, Traver J | Assistant Professor | BIOLOGICAL SCIENCES | $82,500 | $27,500 | $104,397 | 2025 |
| Ohio University | Borror, Matthew J | International Student Advisor | ISSS - INTERNATIONAL STUDENT AND SC | $45,484 |  | $38,070 | 2025 |
| Ohio University | Adler, Scott C | Network Administrator, Senior Specialist | NETWORK OPERATIONS | $38 | $5,312 | $66,622 | 2025 |
| Ohio University | Allanson, Ashley G | Associate Professor of Instruction | RECREATION, SPORT PEDAGOGY & CONSUM | $64,378 | $21,242 | $83,476 | 2025 |
| Ohio University | Anaya, George A | Civil Rights Investigator/SMP Hearing Ch | UNIVERSITY CIVIL RIGHTS COMPLIANCE | $94,432 | $11,446 | $30,542 | 2025 |
| Ohio University | Andre, Laura M | Publicity and Metadata Manager | OU PRESS | $61,492 |  | $49,823 | 2025 |
| Ohio University | Aziz, Omar | Assistant Professor of Instruction | FINANCE | $90,000 |  | $33,675 | 2025 |
| Ohio University | Barresi, Andrea S | Associate Professor of Instruction | BIOMEDICAL SCIENCES | $108,507 |  | $95,236 | 2025 |
| Ohio University | Bender, Andrea L | Director | ATHLETIC TRAINING | $68,569 | $7,044 | $39,940 | 2025 |
| Ohio University | Berkey, Lisa | Assistant Professor of Instruction | MARKETING | $75,000 | $2,995 | $77,341 | 2025 |
| Ohio University | Brewster, Tara R | Executive Assistant | HONORS TUTORIAL COLLEGE | $24 | $833 | $23,693 | 2025 |
| Ohio University | Brown, Jeffrey R | Graphic Designer II | UCM PERSONNEL | $59,236 |  | $54,454 | 2025 |
| Ohio University | Carrillo Bastos, Ramon | Instructor | PHYSICS AND ASTRONOMY | $0 | $13,749 | $13,749 | 2025 |
| Ohio University | Chadwell, Caela W | Success Advisor | CHSP STUDENT SERVICES | $55,389 | $3,690 | $50,350 | 2025 |
| Ohio University | Cheadle, Rexie H | AIRPORT OPERATION SPECIALIST | AIRPORT OPERATIONS | $26 | $11,268 | $58,465 | 2025 |
| Ohio University | Chrisman-Khawam, Leanne | Associate Professor | SOCIAL MEDICINE | $171,832 | $27,254 | $183,778 | 2025 |
| Ohio University | Clifton, Margaret A | Accounting Support Specialist | CH DEAN | $18 | $221 | $33,799 | 2025 |
| Ohio University | Corcoran, Laura L | Instructor | CH EDUCATION | $0 | $8,435 | $8,435 | 2025 |
| Ohio University | Crow, Ashley A | Associate Clinical Professor | PHYSICAL THERAPY | $101,026 | $12,235 | $105,357 | 2025 |

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
| Normandale Community College | Klocek,Yvonne M | Community College Faculty | MnSCU Normandale Fac UFT K - Z | $78,676 | $0 | $78,676 | 2011 |
| North Hennepin Community College | Pins,Cynthia L | Community College Faculty | MnSCU N Hennepin CC Faculty/F | $68,600 | $0 | $68,600 | 2011 |
| Minnesota State University Moorhead | Severn,Elizabeth K | State University Faculty | MnSCU MHD Unclass Faculty M-Z | $50,019 | $0 | $50,019 | 2011 |
| Minnesota West Community and Technical C | Williamson,Justin M | Tech College Faculty | MnSCU MnWest Jackson TC Fac | $62,075 | $0 | $62,075 | 2011 |
| St. Cloud State University | Tuorila,James R | State Univ Adjuct Unit | MnSCU STC Unclass Adjunct Fac | $7,200 | $0 | $7,200 | 2012 |
| Minnesota State System Office | Olson,Gail M | MnSCU Administrator 12 | MnSCU OOC Admin | $159,586 | $0 | $159,586 | 2012 |
| Normandale Community College | Esele,Ignatius I | Community College Faculty | MnSCU Normandale Fac UFT A - J | $78,642 | $0 | $78,642 | 2012 |
| Riverland Community College | Leas,Terrence | MnScCUPresident/Vice Chanc II | MnSCU OOC Presidents | $164,014 | $10,625 | $174,639 | 2012 |
| Hibbing Community College | Turcotte,Chad M | Tech College Faculty | MnSCU Hibbing TC Faculty | $741 | $0 | $741 | 2012 |
| Lake Superior College | Hon,Daniel Robert | Tech College Faculty | MnSCU Lk Sup Duluth UTCE | $1,080 | $0 | $1,080 | 2012 |
| North Hennepin Community College | Basam,Fati Omar | College Laboratory Asst 2 | MnSCU N Hennepin CC AFSCME/A | $5,877 | $167 | $6,044 | 2013 |
| Rochester Community and Technical Colleg | Bedwell,Stanley C | Community College Faculty | MnSCU Rochester CC Faculty | $4,601 | $50 | $4,651 | 2013 |
| Riverland Community College | Enfield,Thomas P | Groundskeeper Inter | MnSCU Rvrld Austin TC Class | $40,851 | $318 | $41,170 | 2013 |
| Century College | Hairston,Ervin | Tech College Faculty | MnSCU Century CTC Faculty/01 | $20,859 | $0 | $20,859 | 2013 |
| Normandale Community College | Kemperman,William E | Community College Faculty | MnSCU Normandale Fac TempFT/PT | $3,640 | $0 | $3,640 | 2013 |
| Normandale Community College | Kothari Arslan,Reena | Community College Faculty | MnSCU Normandale Fac UFT K - Z | $68,586 | $50 | $68,636 | 2013 |
| Inver Hills Community College | Marshall,Maureen K | Community College Faculty | Faculty TPT Adjunct | $74,963 | $2,244 | $77,207 | 2013 |
| Minnesota State University, Mankato | Raps,Bruce E | Accounting Officer | MnSCU MAN Classified O-Z | $49,830 | $0 | $49,830 | 2013 |
| Minnesota State University, Mankato | Van Duynhoven,Mary C | Office & Admin Specialist Int | MnSCU MAN Classified O-Z | $39,210 | $0 | $39,210 | 2013 |
| Lake Superior College | Wilson,David Anthony | Tech College Faculty | MnSCU Lk Sup Duluth NC Faculty | $2,700 | $0 | $2,700 | 2013 |

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
| Big Bend Community College | OLSON, KAREN L | PROGRAM ASSISTANT |  |  |  | $34,192 | 2010 |
| Central Washington University | BENNETT, VIRGINIA A | ASSISTANT PROFESSOR |  |  |  | $62,500 | 2010 |
| Central Washington University | BURCHAM, JANET K | PART TIME TEMPORARY |  |  |  | $1,000 | 2012 |
| Columbia Basin Community College | HANSEN, SHELLY L | FACULTY |  |  |  | $1,749 | 2012 |
| Columbia Basin Community College | VERGARA, ANA G | FACULTY |  |  |  | $5,475 | 2013 |
| Eastern Washington University | ERIKSON, NANCY | QUARTERLY FACULTY |  |  |  | $6,875 | 2010 |
| Eastern Washington University | MCDAVIS, BRUCE H | INSTRUCTOR-SATORI |  |  |  | $400 | 2011 |
| Edmonds Community College | MADISON, RAPHAEL O | MANAGER-SALES & MARKETING |  |  |  | $2,121 | 2011 |
| Edmonds Community College | PEREZ, ASTRID M | FACULTY |  |  |  | $42,488 | 2013 |
| Peninsula Community College | MATTSON, PAUL S | FACULTY |  |  |  | $12,648 | 2013 |
| Seattle Community College | GOFORTH, JANE E | FACULTY |  |  |  | $38,253 | 2011 |
| Seattle Community College | VERHEYDEN, NANCY E | DEAN, VOCATIONAL EDUCATION |  |  |  | $81,589 | 2013 |
| Shoreline Community College | KUO, ANDREA YIH SHIEN | HUMAN RESOURCE CONSULT 2 |  |  |  | $37,295 | 2013 |
| Skagit Valley College | SCHEER, CHARISSE L | SOCIAL WORK ASSISTANT 2 |  |  |  | $19,095 | 2012 |
| South Puget Sound Community College | SMITH, DEBORAH A | FACULTY |  |  |  | $51,960 | 2010 |
| South Puget Sound Community College | SMITH, DEBORAH E | FACULTY |  |  |  | $10,507 | 2012 |
| Spokane Community College | CONNOLLEY, MARK R | MAINTENANCE MECHANIC 2 |  |  |  | $47,484 | 2011 |
| University of Washington | ANGER, MATTHEW W | COACH |  |  |  | $114,453 | 2011 |
| University of Washington | BLAKE, KATHLEEN | PROFESSOR |  |  |  | $52,448 | 2010 |
| University of Washington | BLATTMAN, NEGIN NOBAR | FELLOW |  |  |  | $25,518 | 2010 |

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
| University of Nebraska-Lincoln | Kringen, Alexis J | Senior Development Officer | Athletics | $82,000 |  |  | 2017 |
| University of Nebraska Medical Center | Morales, Ana Laura O | Clinical Study Associate | Int Med DEM | $35,643 |  |  | 2017 |
| University of Nebraska-Lincoln | Riedesel, Charles | Assistant Professor of Practice | Computer Science & Engineering | $77,215 |  |  | 2017 |
| University of Nebraska-Lincoln | Stephenson, Mitchell B | Asst Professor | Panhandle Rsch & Ext Center | $83,846 |  |  | 2017 |
| University of Nebraska Medical Center | Theesen, Kim R | Graphic Designer | COD-Dental Administration | $44,493 |  |  | 2017 |
| University of Nebraska Medical Center | Uggen, Jennifer T | Asst Professor | Anesthesiology | $100,200 |  |  | 2017 |
| University of Nebraska Medical Center | Wiley, Michael R | Research Asst Professor | COPH Environ, Agri & Occ Health | $92,070 |  |  | 2017 |
| University of Nebraska Medical Center | Barnett, Sharon A | Office Associate II | COPH Epidemiology | $37,814 |  |  | 2018 |
| University of Nebraska Omaha | Girten, Kristin Marie | Associate Professor | English | $67,652 |  |  | 2018 |
| University of Nebraska Medical Center | Hansen, Stephanie L | Undergraduate Program Coordinator | Psychiatry | $34,441 |  |  | 2018 |
| University of Nebraska-Lincoln | Hoffer, Schuyler P | Dining Service Associate | Athletics | $20,372 |  |  | 2018 |
| University of Nebraska-Lincoln | Holz, Aaron J | Associate Professor | School of Art, Art History & Design | $75,217 |  |  | 2018 |
| University of Nebraska Omaha | Kalasek, Julie Ann | Assistant Director | Health Services | $64,436 |  |  | 2018 |
| University of Nebraska Medical Center | McVicker, Benita L | Outcomes Research Scientist | Int Med GI | $33,710 |  |  | 2018 |
| University of Nebraska Omaha | Nichol-Caddy, John J | Marketing Consultant | Nebraska Business Development Cente | $48,600 |  |  | 2018 |
| University of Nebraska Omaha | Roland, Thomas A | Professor | Music | $70,560 |  |  | 2018 |
| University of Nebraska-Lincoln | Stone, Julie M | Assoc Professor | Biochemistry | $90,180 |  |  | 2018 |
| University of Nebraska-Lincoln | Taylor, Robert J | Senior Editor | University Press | $68,561 |  |  | 2018 |
| University of Nebraska-Lincoln | Thomas, Christine A | Project Manager | Engineering Computer Science | $73,181 |  |  | 2018 |
| University of Nebraska-Lincoln | Akasheh, Osama Z | Post Doc Rsch Assoc | Water for Food Institute | $54,810 |  |  | 2019 |

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
| University of Maine System (System Wide  | Cyr, Peter P. | IT Specialist CL2 | SITSUPORT | $54,746 |  |  | 2026 |
| University of Maine System (System Wide  | McCann, Brandi D. | Senior Digital Content and Accessibility | SGCHAN | $56,795 |  |  | 2026 |
| University of Maine System (System Wide  | Moran, Eileen | Development & Grant Writing Specialist | SVCAA | $65,421 |  |  | 2026 |
| University of Maine System (System Wide  | Santus, Felicia | Procurement Data Administrator | SOSP | $54,600 |  |  | 2026 |
| University of Maine System (System Wide  | Wells, Ashley | Accountant | SOOT | $73,174 |  |  | 2026 |
| University of Maine System (System Wide  | Whittemore, Jamie B. | Assistant Director of AP4ME and Early Co | SVCAA | $71,042 |  |  | 2026 |
| University of Maine | Bailey, Michael A. | Executive Director of Finance/Extension  | OCES | $100,466 |  |  | 2026 |
| University of Maine | Bartosenski Bowden, Mary | Lecturer III | OEH | $22,459 |  |  | 2026 |
| University of Maine | Biddle, Catharine | Associate Professor | OEDUH | $102,339 |  |  | 2026 |
| University of Maine | Brehme, Christopher E. | Senior NNA Lobster Network GIS, Outreach | ONFDN | $72,657 |  |  | 2026 |
| University of Maine | Bruce, Mitchell R. | Professor of Chemistry | OCH | $135,796 |  |  | 2026 |
| University of Maine | Campbell, Beth | Career Counselor, STEM & Health Professi | OCPP | $51,000 |  |  | 2026 |
| University of Maine | Case, Ashley M. | Lead Grant and Contract Administrator | OSPIRE | $69,966 |  |  | 2026 |
| University of Maine | Desisto, William | Professor of Chemical Engineering | OCHE | $188,790 |  |  | 2026 |
| University of Maine | Drewniany, Paula F. | Principal Lecturer in Mathematics | OMS | $93,906 |  |  | 2026 |
| University of Maine | Finch, Bradly K. | Library Specialist CL3 | OLY | $49,920 |  |  | 2026 |
| University of Maine | Finemore, Christine L. | Community Education Asst CL3 | OCES | $55,952 |  |  | 2026 |
| University of Maine | Friess, Wilhelm A. | Professor of Mechanical Engineering; Dir | OME | $148,477 |  |  | 2026 |
| University of Maine | Gautrau, Margaret | Communications Specialist IV | OADCC | $72,657 |  |  | 2026 |
| University of Maine | Giudice, Nicholas A. | Professor | OCIS | $169,433 |  |  | 2026 |

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
| University of New Mexico | Fawcett, Peter J. | Associate Dean | Arts Sciences Admn Support | $176,992 |  |  | 2027 |
| University of New Mexico | Day, Marie C. | Retail Manager | Bookstore Main Campus | $63,630 |  |  | 2027 |
| University of New Mexico | Driscoll, Jason C. | Coord,Custodial Svcs | UNM Public Events | $48,853 |  |  | 2027 |
| University of New Mexico | Duran, Danielle K. | Data Manager | Project ECHO | $71,984 |  |  | 2027 |
| University of New Mexico | Eiden, Clement T. | Operations Specialist | Recreational Services Administrat | $52,486 |  |  | 2027 |
| University of New Mexico | Elliott, Elizabeth | Program Specialist | CRTC Clinic Rsrch Data Management | $73,626 |  |  | 2027 |
| University of New Mexico | Emerson, Ramona D. | Assistant Professor | Film and Digital Arts | $67,226 |  |  | 2027 |
| University of New Mexico | Griego, Gwendolyn J. | Sr Fiscal Services Tech | COPH Deans Office | $65,130 |  |  | 2027 |
| University of New Mexico | Garrote, Andoni | Temp Parttime Faculty | School of Law | $19,333 |  |  | 2027 |
| University of New Mexico | Helmrich, Emily D. | Clinician Ed-Assist Prof | Pathology | $258,058 |  |  | 2027 |
| University of New Mexico | Holmes, Richard R. | Administrative Officer (Div) | HSC Academic Affairs | $71,427 |  |  | 2027 |
| University of New Mexico | Hernandez, Zulema | Supv,Custodial Services | HSC FM Custodial | $51,512 |  |  | 2027 |
| University of New Mexico | Hilton, Kasey N. | Coord,Academics | Chemistry Department | $47,478 |  |  | 2027 |
| University of New Mexico | Hussein, Omar M. | Clinician Ed-Assoc Prof | Neurology Adult | $218,340 |  |  | 2027 |
| University of New Mexico | James, Carolyn | Bus Driver | Transportation Support | $52,065 |  |  | 2027 |
| University of New Mexico | Papendieck, Adam S. | Assistant Professor | CULLS OILS | $84,032 |  |  | 2027 |
| University of New Mexico | Phillips, Christina E. | Mgr,Clinical Trials Operations | IM Epi | $105,508 |  |  | 2027 |
| University of New Mexico | Price, Jada J. | Child Care Worker | UNM Childrens Campus Administration | $42,536 |  |  | 2027 |
| University of New Mexico | Rodriguez Alvarez, Juan S. | Resident Physician III | Grad Med Education Housestaff | $73,617 |  |  | 2027 |
| University of New Mexico | Simcox, Kristian S. | Associate Professor | Gallup Branch | $81,669 |  |  | 2027 |

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
| University of the District of Columbia | Bowden, Angelita | HRIS Analyst |  | $78,684 |  |  | 2027 |
| University of the District of Columbia | Thompson, Jhinelle | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Detrick, Anne | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Gaffney, Aniyah | WORK STUDY AIDE IV |  |  |  |  | 2027 |
| University of the District of Columbia | Akpan, Betty | ADJUNCT PROFESSOR |  |  |  |  | 2027 |
| University of the District of Columbia | Cooper, Clara | SECRETARY |  | $71,395 |  |  | 2027 |
| University of the District of Columbia | Smith, Kevin | POLICE OFFICER |  | $65,426 |  |  | 2027 |
| University of the District of Columbia | Winters, Benjamin | ADJUNCT PROFESSOR |  |  |  |  | 2027 |
| University of the District of Columbia | Mitchell, Alisha | Acting Assoc Registrar |  | $109,182 |  |  | 2027 |
| University of the District of Columbia | Shy, Denize | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Payton, Randolph | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Celio, Shawn | Vice President, HR |  | $187,223 |  |  | 2027 |
| University of the District of Columbia | Leer-Gray, Raysa | Deputy Chief Operating Officer |  | $167,789 |  |  | 2027 |
| University of the District of Columbia | Forney, Shantell | Special Assistant |  | $102,250 |  |  | 2027 |
| University of the District of Columbia | Kelsey, Serita | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Hixon, Orlando | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | Dorta, Dorven | Adjunct Professor-SEIU |  |  |  |  | 2027 |
| University of the District of Columbia | May, Bridget | Director, Data, Tech.& Innovat |  | $99,395 |  |  | 2027 |
| University of the District of Columbia | Goodman, Crystal | Rehabilitation Counselor |  | $84,353 |  |  | 2027 |
| University of the District of Columbia | Gray, Juanita | DIRECTOR |  | $105,401 |  |  | 2027 |

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
| Arizona State University | Harris,Rebecca | Postdoctoral Research Scholar | Center for Evol, Med & Pub Hlt | $48,000 |  |  | 2018 |
| Arizona State University | Lee,Yann-Hang | Professor | Sch Compt Infor & Dec Sys Engr | $139,637 |  |  | 2018 |
| Arizona State University | Provenzano,Timothy | Project Manager | Collections Care Preservation | $50,000 |  |  | 2018 |
| Arizona State University | Wang,Lu | Accountant | Capital Assets Management | $48,960 |  |  | 2018 |
| Arizona State University | Chiarelli,Dean | Clinical Asst Professor | CONHI MHI | $63,272 |  |  | 2019 |
| Arizona State University | Gant,Mindy | Project Manager | TSGM Exec Ed | $72,000 |  |  | 2019 |
| Arizona State University | Haseley,Hilary | Instructor | School Of Social Work | $45,000 |  |  | 2019 |
| Arizona State University | Keresty,Kathy | Administrative Asst | Barrett Honors College | $36,982 |  |  | 2019 |
| Arizona State University | Markovich,Vesna | Coordinator | SILC | $48,845 |  |  | 2019 |
| Arizona State University | Wargo,Sedona | MultiMedia Technician | WPC Dean Mkt & Comm | $42,000 |  |  | 2019 |
| Arizona State University | Beck, Sabrina | Business Operations Specialist | Sch Elect Comptr & Energy Engr | $47,750 |  |  | 2020 |
| Arizona State University | Dickson, Daniel | Director | Student Creative Services | $91,187 |  |  | 2020 |
| Arizona State University | Hogue, Richard | Grounds Supervisor | FDM FM Grounds Services | $48,000 |  |  | 2020 |
| Arizona State University | Schmidt, Kevin | Professor | Physics Department | $118,400 |  |  | 2020 |
| Arizona State University | Shrestha, Milan | Lecturer Sr | SOS Faculty & Researchers | $61,500 |  |  | 2020 |
| Arizona State University | Wentz, Sarah | Academic Success Advisor | Sch Engr Matter Trnsprt Energy | $43,264 |  |  | 2020 |
| Arizona State University | ZENG, CHAO | Postdoctoral Research Scholar | Sch Sustain Engr & Built Envrn | $52,021 |  |  | 2020 |
| Arizona State University | Christianson, Serena | Academic Success Advs Coord | Sols Undergraduate Programs | $54,500 |  |  | 2021 |
| Arizona State University | Kim, James | EdPlus Success Coach | EdPlus Success Coaching Center | $47,500 |  |  | 2021 |
| Arizona State University | Pittman, Andrea | Assoc Professor | College of Health Solutions SH | $100,980 |  |  | 2021 |

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
| University of Arizona | Goddard, Timothy Arthur | Manager, Archaeological Records Office | Arizona State Museum | $78,566 |  |  | 2026 |
| University of Arizona | Montano, Nieves M | Coordinator, Supplemental Instruction | Think Tank | $49,387 |  |  | 2026 |
| University of Arizona | Sanders, Staci | Veterinary Technician II | University Animal Care | $50,801 |  |  | 2026 |
| University of Arizona | Travan, Stacey Eugene | Dining Services Supervisor | Arizona Student Unions | $48,500 |  |  | 2026 |
| University of Arizona | Brown, Susan A | Department Head, Management Information  | Management Information Systems | $355,276 |  |  | 2025 |
| University of Arizona | Francisco, Michelle Elena | Administrative Assistant | School of Dance | $41,157 |  |  | 2025 |
| University of Arizona | Ojeda, Raquel Malia | Information Technology Support Analyst | Campus IT Services | $39,933 |  |  | 2025 |
| University of Arizona | Yung, Michelle L | Research Software Engineer III | D7: AZ Data Science Initiative | $99,901 |  |  | 2025 |
| University of Arizona | Baker, Christopher A | Deputy Senior Director of Development, E | Philanthropy & Alumni Engagmnt | $120,830 |  |  | 2024 |
| University of Arizona | Brown, Jasmine | Student Accounts Coordinator | Student Financial Advising | $44,644 |  |  | 2024 |
| University of Arizona | Ladner, Thomas | Coordinator, Facilities Planning and Ope | Eller Administration | $60,890 |  |  | 2024 |
| University of Arizona | Lauber, Trevor | Community Outreach Professional I | Cochise County Office | $44,855 |  |  | 2024 |
| University of Arizona | Pearmain, Stephanie R | Associate Professor of Practice | English | $59,781 |  |  | 2024 |
| University of Arizona | Vinogradov, Alex | Security Engineer III | IT Security & Network | $146,362 |  |  | 2024 |
| University of Arizona | Yao, Guang | Associate Professor, Molecular and Cellu | Molecular and Cellular Biology | $115,751 |  |  | 2024 |
| University of Arizona | Armand-Cade, Debra | Senior Academic Advisor I | Chemistry & Biochemistry - Sci | $55,904 |  |  | 2023 |
| University of Arizona | Machado, Dolores M | Associate Director, Orientation and New  | Admissions & New Student Enrol | $63,615 |  |  | 2023 |
| University of Arizona | Cox, Daniel H | Software Engineer | Large Binocular Telescope Obs | $102,558 |  |  | 2022 |
| University of Arizona | Davidowitz, Goggy | Professor, Entomology | Entomology-Res | $106,622 |  |  | 2022 |
| University of Arizona | Otto, Hans W | Adjunct Lecturer, Ecology and Evolutiona | Ecology & Evolutionary Biology | $44,440 |  |  | 2022 |

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
| University of Kansas | Sloan, Bryce A | Custodian |  |  |  | $37,116 | 2023 |
| University of Kansas | Hicks, Cooper C | Temporary Worker-UPS |  |  |  | $428 | 2023 |
| Kansas State University | Avocat, Helene | Visiting Assistant Professor |  |  |  | $28,170 | 2021 |
| University of Kansas | Becchina, Nicole Elise | Administrative Associate |  |  |  | $40,436 | 2021 |
| University of Kansas | Baranski, John A | IT Associate Programmer |  |  |  | $75,966 | 2021 |
| Fort Hays State University | Al-Emran, Md | Instructor - Regular |  |  |  | $2,495 | 2022 |
| University of Kansas | Chen, Andrew | Professor |  |  |  | $168,470 | 2022 |
| Kansas State University | Anno, Rina | Associate Professor |  |  |  | $86,388 | 2023 |
| Kansas State University | Trepinski, Scott P | Instructor |  |  |  | $9,750 | 2023 |
| Kansas State University | Yelich Biniecki, Susan M | Associate Professor |  |  |  | $79,941 | 2021 |
| Kansas State University | Smallwood, Cierra L | Nutrition Educator |  |  |  | $24,139 | 2021 |
| Fort Hays State University | Meier, Mary J | Executive Administrative Specialist |  |  |  | $27,244 | 2021 |
| University of Kansas | Turenne, Michael James | Police Instructor Senior |  |  |  | $76,307 | 2021 |
| University of Kansas | Myers, Austin MacKenzie | Research Aide |  |  |  | $11,154 | 2021 |
| University of Kansas Medical Center | Boggs, Kacee Lynn | Senior Regulatory Coordinator Non-Exempt |  |  |  | $55,723 | 2021 |
| University of Kansas | Thornton, Allayne E | Administrative Associate |  |  |  | $41,292 | 2022 |
| University of Kansas | Hutchison, Justin M | Assistant Professor |  |  |  | $121,770 | 2022 |
| Kansas State University | Trewyn, Ronald W | Assistant To The President |  |  |  | $445,596 | 2022 |
| University of Kansas | Ackley, Brian D | Associate Professor |  |  |  | $92,613 | 2022 |
| Wichita State University | Shorte', Torisha Helene | Career Coach |  |  |  | $40,229 | 2022 |

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
| Rowan University | FALCONI, MARK G |  | STATEWIDE | $97,135 |  |  | 2026 |
| Rowan University | KING, JANINE C |  | STATEWIDE | $104,095 |  |  | 2026 |
| New Jersey City University | MURPHY, DANIELLE |  | STATEWIDE | $69,606 |  |  | 2026 |
| Kean University | CZERWONKA, MALGORZATA |  | STATEWIDE | $91,580 |  |  | 2026 |
| Kean University | SEXTON, BRIAN P |  | STATEWIDE | $26,100 |  |  | 2026 |
| William Paterson Univ of Nj | MUSTAFOSKI, SAFET |  | STATEWIDE | $54,389 |  |  | 2026 |
| Montclair State University | NORDMANN, HEINZ |  | STATEWIDE | $77,364 |  |  | 2026 |
| Montclair State University | PANKIEWICZ, GARY V |  | STATEWIDE | $26,100 |  |  | 2026 |
| Montclair State University | SAMMY, SOOKRANEE C |  | STATEWIDE | $48,575 |  |  | 2026 |
| The College of New Jersey | MBACHU, MITCHELL |  | STATEWIDE | $130,964 |  |  | 2026 |
| Ramapo College of New Jersey | PEREZ-STRUMOLO, LYSANDIA M |  | STATEWIDE | $137,091 |  |  | 2026 |
| Stockton University | BLACK, ALLISON |  | STATEWIDE | $54,800 |  |  | 2026 |
| Stockton University | GREEN, DENISE S |  | STATEWIDE | $107,126 |  |  | 2026 |
| Stockton University | LONGO, JUDY K |  | STATEWIDE | $77,061 |  |  | 2026 |
| Stockton University | MANUOLA, SHAWN J |  | STATEWIDE | $96,788 |  |  | 2026 |
| Stockton University | PEREZ, MADELINE |  | STATEWIDE | $88,577 |  |  | 2026 |
| Stockton University | PEREZ, NOEMI |  | STATEWIDE | $44,793 |  |  | 2026 |
| Thomas Edison State University | BOYD-THOMPSON, LORRAINE V |  | STATEWIDE | $81,182 |  |  | 2026 |
| Rutgers University | ANDINO, ROBERT |  | STATEWIDE | $63,185 |  |  | 2026 |
| Rutgers University | ARMSBY, DOREEN N |  | STATEWIDE | $23,634 |  |  | 2026 |

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
| Univ. of Okla. Health Sciences Center | Boylan, P M |  |  | $0 | $9,856 | $9,856 | 2026 |
| Univ. of Okla. Health Sciences Center | Zimmerman, C N |  |  | $0 | $17,412 | $17,412 | 2026 |
| Tulsa Community College | Pomeroy, C F |  |  | $0 | $3,626 | $3,626 | 2026 |
| University of Oklahoma | King-Kelly, C K |  |  | $0 | $8,462 | $8,462 | 2026 |
| University of Oklahoma | Solomon, M M |  |  | $0 | $2,560 | $2,560 | 2026 |
| Univ. of Central Okla. | RHOADS, J D |  |  | $0 | $5,433 | $5,433 | 2026 |
| Oklahoma State University | Wehrenberg, N T |  |  | $0 | $3,360 | $3,360 | 2026 |
| Rogers State University | Crow, B D |  |  | $0 | $876 | $876 | 2026 |
| Univ. of Okla. Health Sciences Center | Massey, S E |  |  | $0 | $5,332 | $5,332 | 2026 |
| University of Oklahoma | Tennant, T A |  |  | $0 | $3,363 | $3,363 | 2026 |
| Tulsa Community College | Van De Mark, C R |  |  | $0 | $6,767 | $6,767 | 2026 |
| Northeastern State University | Revels, M R |  |  | $0 | $9,027 | $9,027 | 2026 |
| Univ. of Okla. Health Sciences Center | Nelson, B N |  |  | $0 | $4,855 | $4,855 | 2026 |
| Oklahoma State University | Parkison, A D |  |  | $0 | $7,792 | $7,792 | 2026 |
| Oklahoma State University | Zehr, J M |  |  | $0 | $3,653 | $3,653 | 2026 |
| Okla. City Community College | Zachariah, R |  |  | $0 | $1,110 | $1,110 | 2026 |
| Okla. City Community College | French, D R |  |  | $0 | $3,971 | $3,971 | 2026 |
| Univ. of Central Okla. | NGUYEN, H |  |  | $0 | $521 | $521 | 2026 |
| Univ. of Okla. Health Sciences Center | Delaney, D B |  |  | $0 | $7,820 | $7,820 | 2026 |
| Connors State College | Day, T D |  |  | $0 | $3,939 | $3,939 | 2026 |

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
| University of Illinois System Offices | Thompson, Julie S | ASST DIR REAL ESTATE | 832 - Cap Prgm, Real Est, & Util Sv | $97,819 |  |  | 2027 |
| University of Illinois Chicago | Bond, Samantha G | ASSOC PROG DIR | 318 - Biomed & Health Info Sciences | $5,000 |  |  | 2027 |
| University of Illinois Chicago | Sultana, Farheen | ASST PROF OF CLIN ANESTH | 258 - Anesthesiology | $70,380 |  |  | 2027 |
| University of Illinois Chicago | Chau, Felix Yan-Fay | PHYSN SURG | 539 - Ophthalmology & Visual Sci | $135,552 |  |  | 2027 |
| University of Illinois Chicago | Patel, Preyal Ankit | DIR ADMIN OPERS | 219 - Pathology | $185,865 |  |  | 2027 |
| University of Illinois Chicago | Bennett, Peter Sylvester | PROF OF CLIN PSYCHIAT | 722 - Psychiatry | $136,345 |  |  | 2027 |
| University of Illinois Chicago | Pandey, Subhash C | PROF (RT) | 722 - Psychiatry | $232,609 |  |  | 2027 |
| University of Illinois Chicago | Rana, Basabi | PROF (RT) | 271 - Surgery | $85,425 |  |  | 2027 |
| University of Illinois Chicago | Pourarian, Shokouh | CLIN ASST PROF | 323 - Mechanical & Industrial Engr | $114,166 |  |  | 2027 |
| University of Illinois Chicago | Andrews, Amanda J | APRN CNP | 398 - Nursing | $157,773 |  |  | 2027 |
| University of Illinois Chicago | Burns-Howard, Kathryn | ASST DEAN OF STDNT SERV | 310 - Honors College | $91,323 |  |  | 2027 |
| University of Illinois Chicago | Aleksa, Vainis | ASST DIR OF COMPOSITION FOR TH | 492 - English | $83,782 |  |  | 2027 |
| University of Illinois Chicago | Dissanayake Appuhamillage, Thilini | POSTDOC RES ASSOC | 354 - Physics | $61,812 |  |  | 2027 |
| University of Illinois Chicago | Ramanathan, Kumar | BRIDGE 2 FAC POSTDOC RES ASSOC | 734 - Political Science | $82,433 |  |  | 2027 |
| University of Illinois Chicago | Caragher, Kristyn M | REF & LIAISON LIBRN | 280 - University Library | $0 |  |  | 2027 |
| University of Illinois Chicago | Vortman, Rebecca Kathleen | CLIN ASSOC PROF | 662 - Pop Health Nursing Science | $128,329 |  |  | 2027 |
| University of Illinois Chicago | Franzblau, Scott Gary | ALBERT SCHATZ PROF | 440 - Pharmaceutical Sciences | $10,000 |  |  | 2027 |
| University of Illinois Chicago | Albarran, Joseph Gregory | CLIN INSTR | 967 - Pharmacy Practice | $85,677 |  |  | 2027 |
| University of Illinois Chicago | Ardinger, Eric Nicholas | DIR ADVS SYST ASSMT | 683 - Offc for Advising Development | $103,734 |  |  | 2027 |
| University of Illinois Chicago | Hehman, Lisa E | DIR ADVS DEVLP | 683 - Offc for Advising Development | $103,742 |  |  | 2027 |

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
| The Citadel | ROMAN AMARO, LUZ | ADMINISTRATIVE COORDINATOR I |  |  |  | $52,263 | 2027 |
| The Citadel | WIMER, AARON | DEPARTMENT CHAIR/HEAD |  |  |  | $129,944 | 2027 |
| The Citadel | WATSON, MARY | PROFESSOR |  |  |  | $120,917 | 2027 |
| The Citadel | GRENIER, KATHERINE | PROFESSOR |  |  |  | $106,118 | 2027 |
| Clemson University | HALLENBECK, DOUG | VICE PRESIDENT |  |  |  | $351,900 | 2027 |
| Clemson University | HANSSEN, FREDERICK | PROFESSOR |  |  |  | $174,237 | 2027 |
| Clemson University | ZHAO, XIN | ASSOCIATE PROFESSOR |  |  |  | $119,577 | 2027 |
| Clemson University | MITCHELL, KIMBERLY | PROJECT MANAGER II |  |  |  | $117,285 | 2027 |
| Clemson University | CUTLER, KYLE | STUDENT SERVICES MANAGER II |  |  |  | $91,780 | 2027 |
| Clemson University | BALDWIN, WENDY | PROJECT MANAGER I |  |  |  | $88,434 | 2027 |
| Clemson University | GREGGS, EDWARD | INFORMATION SYSTEMS / BUSINESS ANALYST I |  |  |  | $80,884 | 2027 |
| Clemson University | GRANT, PHILLIP | ASSISTANT PROFESSOR |  |  |  | $77,250 | 2027 |
| Clemson University | CALDWELL, WILLIAM | INFORMATION SYSTEMS / BUSINESS ANALYST I |  |  |  | $71,488 | 2027 |
| Clemson University | COOK, GILLIAN | ACCOUNTANT/FISCAL ANALYST III |  |  |  | $64,505 | 2027 |
| Clemson University | TOWE, REBECCA | ADMINISTRATIVE COORDINATOR II |  |  |  | $63,240 | 2027 |
| Clemson University | MCDINE, JONATHAN | NETWORK ADMINISTRATOR |  |  |  | $58,854 | 2027 |
| University of Charleston | ROCKEFELLER, PHILIP | APPLICATION DEVELOPER IV |  |  |  | $108,201 | 2027 |
| University of Charleston | DAVIS, JULIE | ASSOCIATE PROFESSOR |  |  |  | $88,921 | 2027 |
| University of Charleston | VEAL, ERICA | ASSISTANT LIBRARIAN |  |  |  | $72,400 | 2027 |
| Coastal Carolina University | WEINBACH, ANDREW | PROFESSOR |  |  |  | $153,415 | 2027 |

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
| University of Maryland, College Park | Maloney, Kate | Coordinator | VPSA-Campus Recreation Services | $55,472 |  |  | 2015 |
| University of Maryland, College Park | Shaw, Lewis | Lecturer | ARHU-School of Music | $6,120 |  |  | 2015 |
| University of Maryland, College Park | Warnick, Skip | Asst Dir | IT-ESE-Enterprise Software Engineer | $122,493 |  |  | 2015 |
| University of Maryland, College Park | Zhang, Hua Alice | Coordinator | BMGT-IT Smith | $68,347 |  |  | 2015 |
| University of Maryland, College Park | Jewison, Eileen | Accounting Assoc | CMNS-Entomology | $27,336 |  |  | 2016 |
| University of Maryland, College Park | Ofoha, Oluchi R. | Fac Res Asst | CMNS-Inst for Physical Science & Te | $30,298 |  |  | 2016 |
| University of Maryland, College Park | Burczek Dreier, John | Sr Res Anlst | Office of Inst Research, Planning & | $63,664 |  |  | 2013 |
| University of Maryland, College Park | Cronin, Barbara A. | Asst to Dir | PUAF-Center for Public Policy and P | $26 |  |  | 2013 |
| University of Maryland, College Park | Dolet, Nakita Carmen | Admin Asst II | UGST-Undergraduate Studies | $34,502 |  |  | 2013 |
| University of Maryland, College Park | Malm, Stan | Lecturer | BSOS-Criminology & Criminal Justice | $7,140 |  |  | 2013 |
| University of Maryland, College Park | Mollman, Garrett | IT Support Asst | BMGT-IT Smith | $40,035 |  |  | 2013 |
| University of Maryland, College Park | Nandal, Anjali | Fac Res Asst | AGNR-Animal & Avian Sciences | $45,000 |  |  | 2013 |
| University of Maryland, College Park | Pimentel, Carlos L. | Lecturer | ARHU-School of Languages, Literatur | $55,080 |  |  | 2013 |
| University of Maryland, College Park | Rubloff, Gary W. | Prof | ENGR-Institute for Systems Research | $91,615 |  |  | 2013 |
| University of Maryland, College Park | Wheeler, Curtis | Food Serv Aide I | VPSA-Dining Services | $10 |  |  | 2013 |
| University of Maryland, College Park | Goorwah, Fenton | Service Worker | VPSA-Dining Services | $11 |  |  | 2014 |
| University of Maryland, College Park | Johnson, NaKisha N. | Ext Prog Asst | AGNR-UME-1890 | $16,640 |  |  | 2014 |
| University of Maryland, College Park | Manguttathil, Manoj Gopalakrishnan | Res Assoc | CMNS-Earth System Science Interdisc | $46,350 |  |  | 2014 |
| University of Maryland, College Park | Wang, Chenxi | Res Assoc | CMNS-Earth System Science Interdisc | $61,800 |  |  | 2014 |
| University of Maryland, College Park | Caluori, Nava E | Fac Asst | BSOS-Psychology | $32,000 |  |  | 2017 |

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
| Southeast Community College | Butler, Jessica | Instructor Nursing Assistant |  |  |  | $60,000 | None |
| Southeast Community College | Holay, Sandeep | Instructor Mathematics |  |  |  | $103,808 | None |
| Southeast Community College | Masters, Jeannette | Instructor Speech Communication |  |  |  | $92,279 | None |
| Southeast Community College | McConnell, Steven | Instructor Science |  |  |  | $78,748 | None |
| Southeast Community College | Vesely-Robb, Diane | Director Continuing Education |  |  |  | $70,697 | None |
| Southeast Community College | Griggs, Misty | Operations Coordinator Campus & It |  |  |  | $57,618 | None |
| Southeast Community College | Wailes, Mariah | College Advisor |  |  |  | $51,847 | None |
| Southeast Community College | Laursen, Kaila | Assistant Director Child Development Cen |  |  |  | $45,146 | None |
| Southeast Community College | Hoke, Margaret | Administrative Assistant II Student Serv |  |  |  | $43,202 | None |
| Southeast Community College | Meyer, Alyssa | Administrative Assistant II Health Scien |  |  |  | $44,907 | None |
| Southeast Community College | Richards, Dean | Maintenance Worker II |  |  |  | $56,389 | None |
| Southeast Community College | Baccam, Kasey | Web Developer |  |  |  | $69,930 | None |
| Mid-Plains Community College | Blake, Casey Dee | Technology Helpdesk Supervisor | Information Technology |  |  | $60,000 | None |
| Mid-Plains Community College | Brown, Buddy J | Plumbing Maintenance Technician | Physical Resources |  |  | $66,560 | None |
| Mid-Plains Community College | Knott, Gail M | Dean of Outreach and Training | Outreach |  |  | $103,296 | None |
| Mid-Plains Community College | Newland, Matthew Allen | Adjunct Faculty | Faculty |  |  | $6,300 | None |
| Mid-Plains Community College | Tagwerker, Curtis Aron | Coordinator of Residence Life | Student Services |  |  | $46,800 | None |
| Mid-Plains Community College | Wilhelmson, Grace Elizabeth | Child Development Center Staff | Child Development Center |  |  | $5,000 | None |
| Mid-Plains Community College | Name Withheld, Student | Student Ambassador | Student |  |  | $8,000 | None |
| Metropolitan Community College | Barsell, Michaella | Adjunct Faculty - Credit | Academic Affairs -JM |  |  | $36 | 2024 |

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
| University of Missouri Health Care | McDowell, Taylor Donette | Care Team Assoc-Clinical, UH | Emergency Department UH |  |  | $28,082 | 2025 |
| University of Missouri Health Care | Daugherty, Bradley K | Physical Therapist | Therapies |  |  | $109,331 | 2025 |
| University of Missouri Health Care | Trujillo, Gabriella Mia | Care Team Assoc-Clinical, UH | Clinical Operations Float Pool |  |  | $21,307 | 2025 |
| University of Missouri Health Care | Schrader, Kimberly Beth | Med Lab Sci Cert, Sr, Crmc (L) | Lab JC |  |  | $88,271 | 2025 |
| University of Missouri Health Care | Mata, David Zachary | HC Electronic Bld Sys Spc | Plant Engineering |  |  | $79,084 | 2025 |
| University of Missouri Health Care | Anderson, Mykel Haleigh | Nurse, Admiss & Transfer Cntr | Patient Logistics Center |  |  | $66,518 | 2025 |
| University of Missouri Health Care | Patel, Arpan | Resident Physician-4th Yr | Resident Orthopedics |  |  | $68,689 | 2025 |
| University of Missouri Health Care | Hoffman, Linda Carol | Nurse, Staff Inpatient Prn, UH | MOI 3rd Floor Inpatient |  |  | $39,298 | 2025 |
| University of Missouri Health Care | Cooper, Brian L | Pacs Technologist | Radiology - Admin |  |  | $100,313 | 2025 |
| University of Missouri Health Care | Hall, Lynsey Marie | Business Coordinator | Radiology - Admin |  |  | $52,881 | 2025 |
| University of Missouri Health Care | Bax, Kayla Aislyn | Licensed Prac Nurse, Clinic | Surgery Clinic |  |  | $54,483 | 2025 |
| University of Missouri Health Care | Gharabagi, Ariess Paul | Resident Physician-3rd Yr | Resident Ophthalmology |  |  | $61,785 | 2025 |
| University of Missouri Health Care | Heard Jr, James Edward | Sterile Prcsg Tech Cert, UH | MOI Sterile Processing |  |  | $65,394 | 2025 |
| University of Missouri Health Care | Shelabarger, Tracy Shawn | Nurse, Clinic Triage | Neurology Clinic Keene |  |  | $71,384 | 2025 |
| University of Missouri Health Care | Stark, Christen L | Mgr, Health Sys Rel & Market Dev | Strategic Plng & Phys Mrktng |  |  | $125,316 | 2025 |
| University of Missouri Health Care | Bradley, Melissa K | Certified Med Assistant | Occupational Med JC Eastland |  |  | $41,000 | 2025 |
| University of Missouri Health Care | Corum, Audrey Rachel | Business Coordinator | Mizzou Quick Care - Conley |  |  | $55,406 | 2025 |
| University of Missouri System Office | King, Jennifer Dawn | Business Svcs Consultant II | State Historical Society |  |  | $65,248 | 2025 |
| University of Missouri System Office | Dye, Jan Susan | System Administrator-Princpl | IT Systems Support |  |  | $90,873 | 2025 |
| University of Missouri-Columbia | Camarena Martinez, Norma Angelica | Custodian II | Facility Operations |  |  | $38,638 | 2025 |

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
| University of Illinois System Offices | Ross, Kathryn G | Sr Assistant Vpres | System Human Resource Services |  |  | $198,729 | 2025 |
| University of Illinois Chicago | Amarra, Mary Grace | Nursing Techn (Lch) | Nursing |  |  | $85,630 | 2025 |
| University of Illinois Chicago | Coleman, Pamela L. | Health Care Util Rev Coord (Lch) | Nursing |  |  | $170,063 | 2025 |
| University of Illinois Chicago | Nieves, Lyannie | Staff Nrs 1 (Lch) | Nursing |  |  | $53,468 | 2025 |
| University of Illinois Chicago | Sandoval, Kimberly Michelle | Staff Nrs 1 (Lch) | Nursing |  |  | $147,211 | 2025 |
| University of Illinois Chicago | Toda, Herchel J | Staff Nrs 1 (Lch) | Nursing |  |  | $118,977 | 2025 |
| University of Illinois Chicago | McCoy, Caitlin A | Occupat Therapist (Lch) | Ancillary Services |  |  | $81,682 | 2025 |
| University of Illinois Chicago | Montoya, Mario | Radiologic Spec (Lch) | Ancillary Services |  |  | $131,373 | 2025 |
| University of Illinois Chicago | Xavier, Dileep | Hemodialysis Techn (Lch) | Ancillary Services |  |  | $87,337 | 2025 |
| University of Illinois Chicago | Zuniga-Lee, Giovanna | Clin Nursing Consult 2 (Lch) | Ancillary Services |  |  | $110,313 | 2025 |
| University of Illinois Chicago | Fox, Linnie | Building Serv Suprv (LC) | Facilities Management Admin |  |  | $66,583 | 2025 |
| University of Illinois Chicago | Rodriguez, Alejandra Valeria | Vst Res Assoc I | Medicine |  |  | $56,287 | 2025 |
| University of Illinois Chicago | Ahmad, Saba | Extra Service Lump Sum - Peds | Pediatrics |  |  | $85,500 | 2025 |
| University of Illinois Chicago | Ortiz, Kevin | Soc W Aide 3 (Lcdb) | Div of Specializ Care for Chil |  |  | $41,816 | 2025 |
| University of Illinois Chicago | Baig, Afiya | 5020 HR Assoc 1 (LC) | Administration |  |  | $70,283 | 2025 |
| University of Illinois Chicago | Hassan, Chandra | Physn Surg | Surgery |  |  | $456,200 | 2025 |
| University of Illinois Chicago | Taylor, Diandra Myriame Vaval | Postdoc Res Assoc | Pharmaceutical Sciences |  |  | $62,090 | 2025 |
| University of Illinois Chicago | Murphy, Michael Patrick | Police Sgt (LC) | University Police |  |  | $166,528 | 2025 |
| University of Illinois Chicago | Schmidt-McNulty, Tina | INSTR | Kinesiology and Nutrition |  |  | $78,277 | 2025 |
| University of Illinois Chicago | Woolley, Brittany Shannon | Nurs Practr | Internal Medicine |  |  | $160,433 | 2025 |

</details>

### mo_um: University of Missouri System annual salary report (MOspace PDFs) (MO)

Notes: MOspace item 18938a72-809a-4e64-8ddf-b3f7c096965f (collection handle 10355/43681); MOspace rights statement: protected by copyright, all rights reserved unless otherwise indicated

- Rows: 25,688; with a pay value: 25,221 (98.2%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 467; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2026 | 25,688 | 6 | $74,967 | $60,088 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| MU Health Care | Emery,Tyler Robert | RESIDENT PHYSICIAN-2ND YR | Resident Child Health | $68,169 |  | $65,358 | 2026 |
| MU Health Care | Gardner,Maria Alison | NURSE STAFF FT, INPT FLT POOL | Central Staffing Scheduling JC |  |  | $103,188 | 2026 |
| MU Health Care | Harlan,Denise R | NURSE CLINICIAN | Cardiology Clinic |  |  | $19,276 | 2026 |
| MU Health Care | Jones,Erianna | MED CODING SPCLST-CERTIFIED | Coding & Data Management |  |  | $49,233 | 2026 |
| MU Health Care | Jordan,Yolanda D | SCHEDULER, AMBULATORY | EF Patient Access |  |  | $61,970 | 2026 |
| University of Missouri | Balendiran,Vaishnavi | PROF, AST CLINCL DEPT | Ophthalmology | $240,000 |  | $156,296 | 2026 |
| University of Missouri | Blake,Elizabeth Ann | CSM ASSOCIATE I | Intercollegiate Athletics |  |  | $55,589 | 2026 |
| University of Missouri | Burton,Cameron Lynn | BUSINESS OPS ASSOCIATE SR | Thompson Center | $71,400 |  | $63,051 | 2026 |
| University of Missouri | Chaumont,Katie Nicole | CSM OPERATIONS COORDINATOR | Biological Science |  |  | $39,861 | 2026 |
| University of Missouri | Driskill,Karla Kaye | HUMAN RESOURCES SPECIALIST III | Dean of Veterinary Medicine |  |  | $70,963 | 2026 |
| University of Missouri | Goodwin,Whitney Annette | SCIENTIST SR | MRR Research & Education | $83,232 |  | $93,317 | 2026 |
| University of Missouri | Griffith,Samuel Vincent Troy | PROF, ASOC TEACH | School of Music | $73,757 |  | $77,456 | 2026 |
| University of Missouri | Hayes,Melissa D | OFFICE SUPPORT ASSISTANT SR | Facility Operations |  |  | $81,032 | 2026 |
| University of Missouri | Johnson,April Joyce | OPERATIONS SUPPORT TECH SR | Police |  |  | $49,980 | 2026 |
| University of Missouri | Jordan,Connor Patrick | ADVANCEMENT DIR I | Intercollegiate Athletics | $84,500 |  | $90,428 | 2026 |
| University of Missouri | Lang,Yuekun | PROF, AST RESRCH | Lab for Infectious Disease Res | $67,535 |  | $62,611 | 2026 |
| University of Missouri | Mott,Rebecca Louise | PROF, AST | Applied Soc Sci | $96,073 |  | $122,475 | 2026 |
| University of Missouri | Mottola,Megan Elise | PROGRAM/PROJECT SUPPRT COOR I | Student H&WB Admin |  |  | $47,050 | 2026 |
| University of Missouri | Mukarurinda,Dancille N/A | CUSTODIAN II | Facility Operations |  |  | $35,404 | 2026 |
| University of Missouri | Plank,Crystal Leigh | RESEARCH CONSULTANT II | School of Nursing | $76,632 |  | $70,529 | 2026 |

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
| Missouri State University | Letterman, Emily |  | OFFICE OF STRATEGIC | $48,040 |  |  | 2027 |
| Missouri State University | Taylor, Eric |  | FACULTY CTR FOR TEACHING & | $58,715 |  |  | 2027 |
| Missouri State University | Balasundaram, Gautam |  | PROCUREMENT SERVICES | $68,325 |  |  | 2027 |
| Missouri State University | Cramer, Michael |  | CUSTODIAL | $34,681 |  |  | 2027 |
| Missouri State University | Deever, Nakia |  | CUSTODIAL | $35,017 |  |  | 2027 |
| Missouri State University | Fisher, Destiney |  | CUSTODIAL | $34,681 |  |  | 2027 |
| Missouri State University | Bowen, Steven |  | FACILITIES & MAINTENANCE | $44,282 |  |  | 2027 |
| Missouri State University | Walters, Charles |  | BUSINESS SERVICES | $57,899 |  |  | 2027 |
| Missouri State University | Patterson, Ethan |  | COMPUTER SERVICES- OPER | $65,296 |  |  | 2027 |
| Missouri State University | Mings, Deidre |  | HUMAN RESOURCES ADMIN-OPER | $70,954 |  |  | 2027 |
| Missouri State University | Davis, Chelsea |  | DISABILITY RESOURCE CENTER | $46,950 |  |  | 2027 |
| Missouri State University | Childs, Elaina |  | FINANCIAL AID | $36,968 |  |  | 2027 |
| Missouri State University | Wahl, Shawn |  | RCASH ADMINISTRATION-OPER | $190,130 |  |  | 2027 |
| Missouri State University | Allen, Jimmie |  | ART & DESIGN-OPER | $70,333 |  |  | 2027 |
| Missouri State University | Ott, Brian |  | COMMUNICATION-OPER | $121,368 |  |  | 2027 |
| Missouri State University | Kyle, Jerri |  | COMMUNICATION-OPER | $54,994 |  |  | 2027 |
| Missouri State University | Jordan, Linda |  | ENGLISH-OPER | $46,452 |  |  | 2027 |
| Missouri State University | Sabo, Karen |  | THEATRE & DANCE-OPER | $65,490 |  |  | 2027 |
| Missouri State University | Li, Yingying |  | BUSINESS ADMINSTRATION-OPER | $62,400 |  |  | 2027 |
| Missouri State University | Petet, Lucy |  | BUSINESS ADMINSTRATION-OPER | $42,000 |  |  | 2027 |

</details>

### il_isu: Illinois State University salary lists (FY2023, FY2024 PDFs) (IL)

Notes: PDF table parsed by column position; salary as of Jan 2 of the fiscal year, as published (monthly amount or hourly rate; units not stated so base_pay left NULL and the value kept in pay_components); FY2024 file only: the FY2023 PDF uses a different layout that the column detector does not handle (downloaded, not loaded); FY2025+ only behind a Cloudflare challenge

- Rows: 3,681; with a pay value: 0 (0.0%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 3,681; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2024 | 3,681 | 1 |  |  |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Illinois State University | Adams, Elizabeth | Director Senior | Development-Fundraising |  |  |  | 2024 |
| Illinois State University | Alberto, Margarita | Office Administrator | Event Management, Dining and H |  |  |  | 2024 |
| Illinois State University | Atayde, Maritza | Asst Dir Gamma Phi Circus | College Appl Sci & Tech Suppor |  |  |  | 2024 |
| Illinois State University | Bell, Kilee | Program Coordinator | Planning, Research & Policy An |  |  |  | 2024 |
| Illinois State University | Boylan, David | Maintenance Repair Worker | Building Maintenance |  |  |  | 2024 |
| Illinois State University | Caslow, Joseph | Tree Surgeon | Campus Services Division / Gro |  |  |  | 2024 |
| Illinois State University | Curl, Kathryn | Dir Financial Aid | Financial Aid Office |  |  |  | 2024 |
| Illinois State University | Davenport, Deborah | Business Administrative Assoc | Office of Technology Solutions |  |  |  | 2024 |
| Illinois State University | DeJaynes, Debra | Human Resource Associate | Human Resources |  |  |  | 2024 |
| Illinois State University | Gathright, Ryan | Heavy Driver | Building Maintenance |  |  |  | 2024 |
| Illinois State University | Grimes, Jeffrey | Staff Psychologist | Student Counseling Services |  |  |  | 2024 |
| Illinois State University | Grove, Jennah | Office Manager | Clinical Experiences in Teache |  |  |  | 2024 |
| Illinois State University | Hendrix, Benjamin | IT Tech Assoc | Infrastructure Op & Networking |  |  |  | 2024 |
| Illinois State University | Hensleigh, Ani | Vice President and Provost | Vice President & Provost |  |  |  | 2024 |
| Illinois State University | Jackson, Craig | Dir Infrastructr Op Netwrk | Office of Technology Solutions |  |  |  | 2024 |
| Illinois State University | Johnson, Erica | Administrative Aide | Office of Technology Solutions |  |  |  | 2024 |
| Illinois State University | Kapila, Emmanuel | Food Serv Sanitation Laborer | Event Management, Dining and H |  |  |  | 2024 |
| Illinois State University | Kralis, Raymond | Head Mens Golf Coach | Intercollegiate Athletics |  |  |  | 2024 |
| Illinois State University | Legrand, Robert | IT Tech Assoc | College of Arts & Sci-Informat |  |  |  | 2024 |
| Illinois State University | Lowe, Jessica | Program Coordinator | Research Ethics & Compliance |  |  |  | 2024 |

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
| University of Vermont | Moore,Carolyn | Real Estate Admin PC2 X |  | $65,920 |  |  | 2025 |
| University of Vermont | Shah,Dhruv | Assistant Professor (COM) |  | $43,593 |  |  | 2025 |
| University of Vermont | Crain,Karen | Research Compliance PC3 X |  | $72,940 |  |  | 2026 |
| University of Vermont | Ebratt,Ernesto | Senior Lecturer |  | $66,692 |  |  | 2026 |
| University of Vermont | Esfandiari,Navid | Professor (COM) |  | $30,000 |  |  | 2026 |
| University of Vermont | Lester-Coll,Nataniel | Associate Professor (COM) |  | $50,000 |  |  | 2026 |
| University of Vermont | Mei,Linda | Research Compliance PC3 X |  | $65,571 |  |  | 2026 |
| University of Vermont | Stutzman,Kathleen | Research Laboratory PC2 X |  | $65,363 |  |  | 2026 |
| University of Vermont | Johnson Dunston,Megan Marie | Lecturer (Part-Time) |  | $6,243 |  |  | 2022 |
| University of Vermont | Ko,Nga Ling | Assistant Professor (COM) |  | $67,500 |  |  | 2022 |
| University of Vermont | Borst,Matthew A | Custodial Maintenance Spec |  | $34,778 |  |  | 2023 |
| University of Vermont | Fanslow,Yolanda H. Chen | Professor |  | $103,000 |  |  | 2023 |
| University of Vermont | Gramling,Jason T. | Assistant Professor (COM) |  | $21,000 |  |  | 2023 |
| University of Vermont | Higgins,Timothy J. | Associate Professor (COM) |  | $50,000 |  |  | 2023 |
| University of Vermont | Montgomery,Erin J. | Student Srvcs Professional |  | $56,071 |  |  | 2023 |
| University of Vermont | Pecor,Peter M. | Maintenance Worker |  | $39,187 |  |  | 2023 |
| University of Vermont | Porter,Douglas W. | Research Assistant Prof |  | $75,644 |  |  | 2023 |
| University of Vermont | Beaudry,Janine | Outreach Professional Sr |  | $76,915 |  |  | 2024 |
| University of Vermont | Butel,Sylvie | Administrative Professional |  | $69,889 |  |  | 2024 |
| University of Vermont | Helmer,Sarah | Student Services Administrator |  | $101,346 |  |  | 2024 |

</details>

### nm_nmhu: New Mexico Highlands University salary reports (PDF) (NM)

Notes: annual salary + FTE per published line (multiple lines per person for overloads/second jobs); fiscal_year from the report (3.1.23 report = FY2023); department text is truncated by the publisher

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
| New Mexico Highlands University | ANGELL, MARY | Student Support Specialist | Santa Fe Center | $55,355 |  |  | 2026 |
| New Mexico Highlands University | BIEGLER, CHAD | Administrative Analyst | Human Resources Payroll | $69,628 |  |  | 2026 |
| New Mexico Highlands University | CONTRERAS, ADRIANA | Administrative Assistant - Academic Affa | English | $41,829 |  |  | 2026 |
| New Mexico Highlands University | GRIEGO, MIGUEL | Gen. Maint. Super./Carpenter | Facilities Services | $51,251 |  |  | 2026 |
| New Mexico Highlands University | SHARP, REBECCA | Instructor of Media Arts & Technology | Media Arts and Technology | $58,916 |  |  | 2026 |
| New Mexico Highlands University | Amador, Tristen K | Contingent Facutly- CRN 4266 Leader Inno | Business Administration | $3,000 |  |  | 2023 |
| New Mexico Highlands University | Bassett, Shay | Network Manager | Information Technology Services | $75,900 |  |  | 2023 |
| New Mexico Highlands University | Casias, Anthony A | Custodian | Facilities Services | $33,426 |  |  | 2023 |
| New Mexico Highlands University | Gallegos, Juan M | Assoc Prof of English/Chair | English | $68,253 |  |  | 2023 |
| New Mexico Highlands University | Gonzales, Yvette | Financial Aid Technician | Financial Aid | $38,730 |  |  | 2023 |
| New Mexico Highlands University | Gupta, Rahul | On-Call Systems Analyst | Information Technology Services | $19,126 |  |  | 2023 |
| New Mexico Highlands University | Lucero Martinez, Kristina D | Admissions Coordinator | Recruitment & Undergrad Admissions | $47,330 |  |  | 2023 |
| New Mexico Highlands University | Maldonado, Sharen K | Senior Adm Asst II | School of Social Work | $43,202 |  |  | 2023 |
| New Mexico Highlands University | Montano, Lawrence M | Student Support Specialist | CYFD/SW/FY20/21/22 | $48,751 |  |  | 2023 |
| New Mexico Highlands University | Montano, Katherine S | Administrative Assistant | Visual & Performing Arts | $36,858 |  |  | 2023 |
| New Mexico Highlands University | Ortega, Frances T | Instructor of Social Work | School of Social Work | $55,363 |  |  | 2023 |
| New Mexico Highlands University | Peters, Jacqueline | SAR Specialist | Business Office | $41,600 |  |  | 2023 |
| New Mexico Highlands University | Sandoval, Andra | Custodian | Facilities Services | $31,200 |  |  | 2023 |
| New Mexico Highlands University | Valenzuela, Elisabeth | Overload- Instr Math Span/Engl Bil Cls | Teacher Education | $3,000 |  |  | 2023 |
| New Mexico Highlands University | Andrada-ValenciaJulia, A | Administrative Assistant | Education - Field Services | $39,541 |  |  | 2024 |

</details>

### tn_apsu: Austin Peay State University employee salary data (PDF) (TN)

Notes: current salary list (no date printed; PDF created 2026-09-21 => FY2027, Tennessee FY Jul-Jun); salary under $1,000 is an hourly rate kept in pay_components only

- Rows: 1,158; with a pay value: 914 (78.9%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 244; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2027 | 1,158 | 1 | $80,807 | $72,000 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Austin Peay State University | Anderson, Matthew | Associate Professor | 450900-Engineering Technology | $88,589 |  |  | 2027 |
| Austin Peay State University | Atkinson, Robert | Professor & Chair | 410500-Languages and Literature | $80,813 |  |  | 2027 |
| Austin Peay State University | Barquero, Laura | Associate Professor | 440200-Educational Specialties | $64,250 |  |  | 2027 |
| Austin Peay State University | Bolton, Rhonda | Coordinator | 302000-Human Resources | $61,007 |  |  | 2027 |
| Austin Peay State University | Chamness, Laura | Assistant Professor | 450300-Chemistry | $64,750 |  |  | 2027 |
| Austin Peay State University | Crouse, Christopher | Visiting Assistant Professor | 450100-Biology | $51,845 |  |  | 2027 |
| Austin Peay State University | Day, Jesse | Coordinator, Student Success | 402014-Academic Advisement | $52,270 |  |  | 2027 |
| Austin Peay State University | Degraauw, Jill | Director, Boyd Health Services | 802001-Health Services | $89,661 |  |  | 2027 |
| Austin Peay State University | Derby, Toni-Ann | Senior Associate Director of Athletics,  | 700003-Athletic Administration | $76,250 |  |  | 2027 |
| Austin Peay State University | Easter, Katie | Coordinator, Southeastern Grassland Init | 450140-Southeastern Grasslands Init | $61,431 |  |  | 2027 |
| Austin Peay State University | Fields, Fonda | Director, Human Resources | 302000-Human Resources | $100,703 |  |  | 2027 |
| Austin Peay State University | Gomez, Nathaniel | Director, Marketing & Fan Experience | 700009-Ath Marketing | $61,250 |  |  | 2027 |
| Austin Peay State University | Hamilton, Sondra | Associate Vice President for Budget & Fi | 301000-Associate VP Budget and Fina | $190,084 |  |  | 2027 |
| Austin Peay State University | Harmon, Jordan | Athletic Director | 700000-VP Athletics | $250,000 |  |  | 2027 |
| Austin Peay State University | Hubert, Crissa | Assistant Director of Procurement | 301005-Procurement | $57,000 |  |  | 2027 |
| Austin Peay State University | King, Jamalyn | Advisor | 302000-Human Resources | $60,171 |  |  | 2027 |
| Austin Peay State University | Kochanowski, Danika | Advisor | 302000-Human Resources | $50,750 |  |  | 2027 |
| Austin Peay State University | Longan, Jason | Director, Event Services | 803200-University Events & ID Servi | $76,750 |  |  | 2027 |
| Austin Peay State University | Mayo, Daniel | Associate Professor | 450700-Mathematics and Statistics | $77,585 |  |  | 2027 |
| Austin Peay State University | McDaniel, Brianna | Specialist, Admissions | 404000-Admissions |  |  |  | 2027 |

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
| East Tennessee State University | Brewer, McKenzie R. | Research Associate | Internal Medicine | $40,706 |  |  | 2024 |
| East Tennessee State University | Chadwick, Alissa L. | Specialist | Office of Sponsored Programs | $40,560 |  |  | 2024 |
| East Tennessee State University | Cooper, Chassidy L. | Coordinator | Office of Equity and Inclusion | $53,992 |  |  | 2024 |
| East Tennessee State University | Diciuccio, Jessica D. | Coordinator | Res Imp Comm Outreach | $53,060 |  |  | 2024 |
| East Tennessee State University | Gillert, Alexis M. | Nurse | Nursing Graduate Programs | $59,950 |  |  | 2024 |
| East Tennessee State University | Godfrey, Anne W. | Director | University Advancement | $79,305 |  |  | 2024 |
| East Tennessee State University | Gray, Zane W. | Manager | Physical Plant Adm | $60,421 |  |  | 2024 |
| East Tennessee State University | Hicks, Christopher D. | Specialist | Tax and Revenue Services | $47,207 |  |  | 2024 |
| East Tennessee State University | Jones, Kaitlin R. | Nurse | Nursing Graduate Programs | $56,082 |  |  | 2024 |
| East Tennessee State University | Lane, Keriann E. | Coordinator | Student Services COM | $41,280 |  |  | 2024 |
| East Tennessee State University | Montgomery, Robin W. | Director | Finance and Administration | $76,076 |  |  | 2024 |
| East Tennessee State University | Payne, Eric B. | Assistant Director | Campus Recreation | $46,523 |  |  | 2024 |
| East Tennessee State University | Ryans, Cody A. | Manager | Office of University Relations | $56,441 |  |  | 2024 |
| East Tennessee State University | Short, Candace L. | Business Manager | Surgery | $57,540 |  |  | 2024 |
| East Tennessee State University | Smith, Marjorie K. | Writer | Family Medicine | $64,028 |  |  | 2024 |
| East Tennessee State University | Smith, Matthew D. | Manager | Infor Technology Comp Svcs | $108,680 |  |  | 2024 |
| East Tennessee State University | Statzer, Brandy V. | Manager | Academic Support Bristol | $67,490 |  |  | 2024 |
| East Tennessee State University | Williamson, Amy D. | Coordinator | Academic Technology Support | $60,417 |  |  | 2024 |
| East Tennessee State University | Clavier, Cheri W. | Assistant Vice Provost | Institutional Effectiveness Assessm | $111,357 |  |  | 2024 |
| East Tennessee State University | Ritter, Pamela S. | Vice President | Office of VP for Univ Adv | $234,047 |  |  | 2024 |

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
| University of Michigan-Ann Arbor | Abu Sheikh,Nada | Sales Assistant Intermediate | Michigan Language Assessment | $44,124 |  |  | 2026 |
| University of Michigan-Ann Arbor | Adem,Fatima | HOUSE OFFICER II | MM H.O. Emergency Med Core | $77,609 |  |  | 2026 |
| University of Michigan-Ann Arbor | Ali,Zara | Clinical Pharmacist | MM PAV Pharmacy Services | $133,789 |  |  | 2026 |
| University of Michigan-Ann Arbor | Badder,Monica | REGISTERED NURSE - LEVEL C | MM Post Anes Care Unit - UH | $134,805 |  |  | 2026 |
| University of Michigan-Ann Arbor | Bertschy,Scott | Development Director Senior | SEAS Development | $232,805 |  |  | 2026 |
| University of Michigan-Ann Arbor | Burnside,Nichole Ve-Ella | Admin Manager Inter Healthcare | MM Emergency Medicine UM Adult | $124,800 |  |  | 2026 |
| University of Michigan-Ann Arbor | Cacovean,Leeann | Admin Manager Sr Healthcare | MM Quality - CVC | $147,890 |  |  | 2026 |
| University of Michigan-Ann Arbor | Caldwell,Julie Christia | Patient Care Technician | MM CW VVWH | $53,040 |  |  | 2026 |
| University of Michigan-Ann Arbor | Callaghan,Margaret | Phlebotomist Specialist | MM Path O/P Phlebotomy | $47,986 |  |  | 2026 |
| University of Michigan-Ann Arbor | Citalan Madrid,Ali Francisco | RESEARCH INVESTIGATOR | MM Michigan Neuroscience Inst | $75,555 |  |  | 2026 |
| University of Michigan-Ann Arbor | Combs,Kaitlyn | Mammography Technologist | MM Cancer Center RAD | $84,469 |  |  | 2026 |
| University of Michigan-Ann Arbor | Das,Chayanika | RESEARCH FELLOW | Chemical Engineering Dept | $62,232 |  |  | 2026 |
| University of Michigan-Ann Arbor | Davis,Marna | REGISTERED NURSE - LEVEL C | MM Post Anes Care Unit - UH | $134,805 |  |  | 2026 |
| University of Michigan-Ann Arbor | De La Iglesia,Michele | Admin Specialist Inter Health | MM Division of Anatomy | $74,078 |  |  | 2026 |
| University of Michigan-Ann Arbor | Dunn,Michael | REGISTERED NURSE - LEVEL C | MM UH CVC 8B2 | $107,723 |  |  | 2026 |
| University of Michigan-Ann Arbor | Ejemole,Favour | Desktop Support Spec Inter | MM Anesthesiology Department | $61,800 |  |  | 2026 |
| University of Michigan-Ann Arbor | Falcone,Giusy | ASST PROFESSOR | Aerospace Engineering | $114,575 |  |  | 2026 |
| University of Michigan-Ann Arbor | Faught,Julie A | REGISTERED NURSE - LEVEL D | MM Cardiovascular Medicine at | $142,126 |  |  | 2026 |
| University of Michigan-Ann Arbor | Francisco,Kaitlyn | Admin Manager Assoc Healthcare | MM Northville Core | $84,977 |  |  | 2026 |
| University of Michigan-Ann Arbor | Friedman,Matt | PROFESSOR | LSA Earth & Environmental Sci. | $146,842 |  |  | 2026 |

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
| University of Maine at Augusta | Sullivan, Con | Assistant Professor of Biology | ASCIE | $53,681 |  |  | 2020 |
| University of Maine at Farmington | Pratt, Cynthia C. | AD Athl, HC Fld Hocky/Instr | FATHL | $49,147 |  |  | 2020 |
| University of Maine at Machias | Ball, Heather L. | Associate Professor - AY | MRMB | $58,116 |  |  | 2020 |
| University of Maine | Bates, Bonnie J. | Administrative Support Supvsr | OHOUS | $43,826 |  |  | 2020 |
| University of Maine | Lamountain, Rosemary A. | Administrative Support Supvsr | OSET | $50,773 |  |  | 2020 |
| University of Maine | Rounsville Jr, Thomas | Molecular Diag Professional | OCES | $56,000 |  |  | 2020 |
| University of Southern Maine | Everson, David W. | Assistant Prof of Sociology | PSOC | $57,081 |  |  | 2020 |
| University of Southern Maine | Staples, Seth A. | Lecturer in Chemistry | PCHEM | $49,591 |  |  | 2020 |
| University of Maine at Augusta | Nardone, Gilda E. | Exec Dir New Ventures Maine | ACWWC | $100,014 |  |  | 2020 |
| University of Maine at Farmington | Milliken, Ronald P. | Director of Financial Aid | FFIAI | $78,903 |  |  | 2020 |
| University of Maine at Fort Kent | Picard, Frances D. | Administrative Specialist CL3 | KNURS | $46,987 |  |  | 2020 |
| University of Maine | Jamison, Jonathan K. | Lead Fac Maint Worker CL2 | OATH | $40,643 |  |  | 2020 |
| University of Maine | Kontur, Patricia A. | Director of Programs | ONFDN | $66,712 |  |  | 2020 |
| University of Maine | Neville, Tyler | Asst Dir of Athletic Comm | OATH | $36,000 |  |  | 2020 |
| University of Southern Maine | Sheats, Bailey K. | Administrative Specialist CL3 | PCOS | $33,446 |  |  | 2020 |
| University of Southern Maine | Soloway, Marshall | E-Learning Technology Dir | PMCCI | $93,909 |  |  | 2020 |
| University of Southern Maine | Walsh, Gwendolyn R. | Administrative Specialist CL2 | PCTEL | $29,744 |  |  | 2020 |
| University of Southern Maine | Williams, Jill K. | Employer Relationship Manager | PCEH | $56,444 |  |  | 2020 |
| University of Maine System (System Wide  | Nalesnik, Robert | Campus Services Tech Lead | SITCSUMFK | $40,685 |  |  | 2020 |
| University of Maine System (System Wide  | Pettorini, Marisa E. | Administrative Specialist CL2 | SITMGTWEST | $33,550 |  |  | 2020 |

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
| University of the District of Columbia | Bachman, Paul | PROFESSOR |  | $99,139 |  |  | 2014 |
| University of the District of Columbia | Bryant, Kevin | ADJUNCT PROFESSOR |  |  |  |  | 2014 |
| University of the District of Columbia | Degraphenreid, Kenneth | AUDITORIUM MANAGEMENT AIDE |  | $10,212 |  |  | 2014 |
| University of the District of Columbia | Dillard, Nicole | ADJUNCT PROFESSOR |  |  |  |  | 2014 |
| University of the District of Columbia | Luis, Rigoberto | ADJUNCT PROFESSOR |  |  |  |  | 2014 |
| University of the District of Columbia | Mathapo, Gail | Associate Director, Law Librar |  | $81,889 |  |  | 2014 |
| University of the District of Columbia | Matthews, Jennifer | Director |  | $92,774 |  |  | 2014 |
| University of the District of Columbia | Bradley, Shaumika | PROGRAM ASSISTANT |  | $37,074 |  |  | 2015 |
| University of the District of Columbia | Cousin, Carolyn | PROFESSOR |  | $103,586 |  |  | 2015 |
| University of the District of Columbia | Dunson, Konyka | Grants Administration Officer |  | $68,964 |  |  | 2015 |
| University of the District of Columbia | Jamison, Denise | LIBRARY TECH |  | $50,646 |  |  | 2015 |
| University of the District of Columbia | Welch, Corrie | STAFF ASSISTANT |  | $59,822 |  |  | 2015 |
| University of the District of Columbia | Zedalis, Eric | Assistant Director of Athletic |  | $60,111 |  |  | 2015 |
| University of the District of Columbia | MCDUFFIE, TIMOTHY B | STUDENT SUCCESS SPEC. |  | $53,748 |  |  | 2017 |
| University of the District of Columbia | Tewolde, Danay | WORK STUDY AIDE III |  |  |  |  | 2017 |
| University of the District of Columbia | Wilson, Jeffrey | ADJUNCT INSTRUCTOR ‐ WDLL |  |  |  |  | 2017 |
| University of the District of Columbia | Calloway, Marcia | ADJUNCT PROFESSOR |  |  |  |  | 2017 |
| University of the District of Columbia | Crane‐Seeber, Jesse | ASSISTANT PROFESSOR |  | $67,536 |  |  | 2018 |
| University of the District of Columbia | Ellis, Alfreda | FINANCIAL AID COUNSELOR |  | $87,123 |  |  | 2018 |
| University of the District of Columbia | Lycorish, Roy | Logistics and Research Associa |  | $73,090 |  |  | 2018 |

</details>

### ar_adhe: Arkansas Division of Higher Education Administrator's Compensation Survey (>= $100k) (AR)

Notes: PARTIAL coverage: only administrators with salary >= $100,000 at public institutions; one form page per person parsed by position (pdfplumber words); base_pay = line 12 total base salary (public + private funds), total_pay = line 41 total compensation as published; every line's public/private/total and private-fund source in pay_components ('$ -' accounting dashes are stored as NULL, not 0); fiscal_year = the survey's fiscal year (AR FY Jul-Jun, from the publication; the per-form typed year is kept as fiscal_year_reported_on_form); institution from the table-of-contents section the page falls in

- Rows: 1,547; with a pay value: 1,546 (99.9%)
- Exact duplicate rows (same original row): 0
- Empty name: 0; no numeric pay: 1; pay > $10M: 0; negative pay: 0

| Fiscal year | Rows | Institutions | Mean pay | Median pay |
|---|---|---|---|---|
| 2026 | 1,547 | 39 | $214,517 | $165,333 |

<details><summary>20 random rows</summary>

| Institution | Name (as published) | Title | Department | Base | Other | Total | FY |
|---|---|---|---|---|---|---|---|
| Arkansas State University | Boothman, Christopher | Executive Project/Program Director |  | $230,850 |  | $276,934 | 2026 |
| Arkansas State University | Broadway, Michael "Shane" | Vice President |  | $217,808 |  | $267,098 | 2026 |
| Arkansas State University | Nelson, Heather | Interim Associate Vice Chancellor (Janua |  | $200,000 |  | $226,433 | 2026 |
| Arkansas State University | Walz, Stacy | Associate Dean of Schools |  | $148,045 |  | $196,957 | 2026 |
| Arkansas State University | Robinson, Malcolm | Assistant Football Coach |  | $120,000 |  | $131,963 | 2026 |
| Arkansas State University | Joblin, Christopher | Assistant Coach |  | $110,000 |  | $143,670 | 2026 |
| Arkansas State University | Patchell, James | Head Coach |  | $109,000 |  | $153,399 | 2026 |
| Arkansas Tech University | McCall, Suzanne | Vice Pres. for Admin & Finance |  | $183,600 |  | $236,899 | 2026 |
| University of Arkansas System Administra | Moore, Michael | Vice-Pres. for Academic Affairs |  | $325,518 |  | $379,544 | 2026 |
| University of Arkansas, Fayetteville | Silverfield, Ryan | Head Football Coach |  | $204,167 |  | $3,908,395 | 2026 |
| University of Arkansas, Fayetteville | Varady, Scott | Vice Chan for Advancement/Development |  | $362,376 |  | $435,511 | 2026 |
| University of Arkansas, Fayetteville | Estes, Shauna | Head Golf Coach |  | $260,000 |  | $413,718 | 2026 |
| University of Arkansas, Fayetteville | Davis, Bob | Dir of Research & Sponsored Programs |  | $325,000 |  | $382,168 | 2026 |
| University of Arkansas, Fayetteville | Serin, Jason | Executive Project/Program Director |  | $179,375 |  | $227,686 | 2026 |
| University of Arkansas, Fayetteville | Calipari, Bradley | Executive Project/Program Director |  | $150,000 |  | $212,561 | 2026 |
| University of Arkansas, Fayetteville | Gearity, Ann | Asst. V-C for Advancement |  | $150,000 |  | $189,081 | 2026 |
| University of Arkansas, Fayetteville | Gasper, Scott | Assoc. Dir. of Athletics |  | $145,833 |  | $174,700 | 2026 |
| University of Arkansas, Fayetteville | Sturgeon, Sandy | Dir. of Financial & Mgt. Analysis |  | $125,625 |  | $160,336 | 2026 |
| University of Arkansas, Fayetteville | Probst, Steven | Librarian |  | $117,547 |  | $151,630 | 2026 |
| University of Arkansas, Fayetteville | Gaddy, Tory | Development/Advancement Manager |  | $116,699 |  | $150,987 | 2026 |

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
| University of Pittsburgh | Fisher, Daniel Thomas |  |  |  |  | $681,114 | 2024 |
| University of Pittsburgh | Reis, Steven E. |  |  |  |  | $642,000 | 2024 |
| University of Pittsburgh | Freeman, Bruce A. |  |  |  |  | $541,732 | 2024 |
| University of Pittsburgh | Wipf, Peter |  |  |  |  | $506,242 | 2024 |
| University of Pittsburgh | McKibben, Leeanna Rebekah |  |  |  |  | $478,800 | 2024 |
| University of Pittsburgh | Berg, Jeremy Mark |  |  |  |  | $469,893 | 2024 |
| University of Pittsburgh | Lichtveld, Maureen Y. Tjon |  |  |  |  | $458,874 | 2024 |
| University of Pittsburgh | Chyu, Minking |  |  |  |  | $448,094 | 2024 |
| University of Pittsburgh | Thompson, Ann Ellen |  |  |  |  | $427,022 | 2024 |
| University of Pittsburgh | Lo, Cecilia Wen Ya |  |  |  |  | $426,088 | 2024 |
| University of Pittsburgh | Vorp, David A. |  |  |  |  | $408,104 | 2024 |
| University of Pittsburgh | Poropatich, Ronald Kurt |  |  |  |  | $399,924 | 2024 |
| University of Pittsburgh | Schatten, Gerald Phillip |  |  |  |  | $391,142 | 2024 |
| University of Pittsburgh | Badylak, Stephen Francis |  |  |  |  | $377,225 | 2024 |
| University of Pittsburgh | Ndoh, Uduak Sunday |  |  |  |  | $376,272 | 2024 |
| University of Pittsburgh | Leana, Carrie R. |  |  |  |  | $371,159 | 2024 |
| University of Pittsburgh | Phillips, Mary Louise |  |  |  |  | $367,834 | 2024 |
| University of Pittsburgh | Leibovich, Adam Keith |  |  |  |  | $367,282 | 2024 |
| University of Pittsburgh | Wisniewski, Stephen R. |  |  |  |  | $365,591 | 2024 |
| University of Pittsburgh | Armony, Ariel Carlos |  |  |  |  | $362,720 | 2024 |

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
| Temple University | Toyoda, Yoshiya | Professor Clinician Scholar |  |  |  | $1,709,115 | 2025 |
| Temple University | Weaver, Michael | Professor Clinician Scholar |  |  |  | $1,030,397 | 2025 |
| Temple University | Khan, Mansoor | Assoc Prof Clinician Educator |  |  |  | $844,095 | 2025 |
| Temple University | Edmundowicz, Daniel | Professor Clinician Scholar |  |  |  | $823,058 | 2025 |
| Temple University | Salamanca-Padilla, Yidy | Assoc Prof Clinician Educator |  |  |  | $764,693 | 2025 |
| Temple University | Henderer, Jeffrey | Professor Clinician Scholar |  |  |  | $714,438 | 2025 |
| Temple University | Hajdinaj, Shqiponja | Asst Prof Clinician Educator |  |  |  | $674,587 | 2025 |
| Temple University | Lorei, Matthew | Assoc Prof Clinician Educator |  |  |  | $666,607 | 2025 |
| Temple University | Alao, Kamardeen | Assoc Prof Clinician Educator |  |  |  | $617,126 | 2025 |
| Temple University | Koenigsberg, Robert | Professor Clinician Scholar |  |  |  | $612,497 | 2025 |
| Temple University | Rae, Lisa | Assoc Prof Clinician Scholar |  |  |  | $592,267 | 2025 |
| Temple University | Baskin, Sean | Asst Prof Clinician Educator |  |  |  | $562,106 | 2025 |
| Temple University | Kumar, Sudhir | Professor |  |  |  | $553,333 | 2025 |
| Temple University | Katz, Paul | Professor Clinician Educator |  |  |  | $547,474 | 2025 |
| Temple University | Bashir, Riyaz | Professor Clinician Scholar |  |  |  | $546,417 | 2025 |
| Temple University | Grenda, Dane | Asst Prof Clinician Educator |  |  |  | $545,509 | 2025 |
| Temple University | Streibert, Claire | Asst Prof Clinician Educator |  |  |  | $535,965 | 2025 |
| Temple University | Kissko, John | Assoc Prof Clinician Educator |  |  |  | $531,011 | 2025 |
| Temple University | Basil, Anuj | Assoc Prof Clinician Scholar |  |  |  | $528,950 | 2025 |
| Temple University | Ma, Grace | Professor Tenured |  |  |  | $526,037 | 2025 |

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
| 1 | ga | 88,787 | 2025 | 4/5 | 1,419,662 | Official; full names, title, salary only (no split); FY2015-2025; foundation pay excluded |
| 2 | tx | 150,346 | 2026 | 2/5 | 170,130 | Volunteer TPIA compile; bulk export has first name + last initial only; base salary snapshot |
| 3 | wa | 87,594 | 2013 | 3/5 | 374,836 | Official; full names, title, annual salary; 2010-2013 only |
| 4 | oh_osu | 50,818 | 2025 | 5/5 | 240,592 | Official; calendar-year earnings with regular/bonus/OT/other/gross; department; 2021-2025 |
| 5 | ma | 48,407 | 2026 | 5/5 | 1,198,973 | Official; full names, title, base/OT/buyout/other/total actual pay; 2009-2026 |
| 6 | mi_um | 53,241 | 2026 | 4/5 | 54,659 | Official PDF; full names, title, annual FT rate, appointment fraction; all 3 campuses; FY2026 |
| 7 | il_stl | 44,744 | 2025 | 3/5 | 44,841 | Newsroom compile; full names, title, department, actual 2025 gross pay; UIUC, UIC, UIS, SIUE |
| 8 | ct | 24,760 | 2027 | 5/5 | 979,441 | Official paycheck-level data aggregated per FY; full names, title, base/OT/other/gross; FY2010-2027 |
| 9 | mo_um | 25,685 | 2026 | 4/5 | 25,688 | Official PDF; full names, title, salary rate + W-2 wages; all UM campuses + MU Health; FY2026 |
| 10 | ok | 81,220 | 2026 | 1/5 | 394,645 | Official but names are last name + initials, no title; monthly payment lines |
| 11 | nyc | 15,782 | 2025 | 5/5 | 262,569 | Official; full names, title, regular/OT/other paid; CUNY community colleges only |
| 12 | ks | 25,317 | 2025 | 3/5 | 122,263 | Third-party compile of KORA records; full names, title, total pay; 2021-2025 |
| 13 | mn | 17,334 | 2026 | 4/5 | 313,601 | Official; full names, title, department, FY earnings (all state positions); Minnesota State only |
| 14 | mo_stl | 22,950 | 2025 | 3/5 | 22,951 | Newsroom compile; full names, title, department, actual 2025 gross pay; MU campuses, MU Health, STLCC, SCC |
| 15 | il_iccb | 17,067 | 2026 | 4/5 | 196,985 | Official; full names, title, base/extra duty/benefits; all 48 IL community colleges FY2016-2026 |

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
- States with payroll records loaded: 25
- Catalog sources by rating: A: 30, B: 27, C: 94, D: 34
- Catalog sources marked loaded: 37
- Records loaded: 6,538,996
- Institutions covered (distinct state + institution labels): 532

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

