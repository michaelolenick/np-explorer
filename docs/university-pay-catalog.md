# University pay data catalog

Phase 1 research of public, person-level pay data for public colleges and universities in all 50 states plus DC. Each source is also a row in `unipay.university_pay_sources`. Ratings: **A** = clean bulk download/API; **B** = person-level but needs scraping or PDF/form extraction; **C** = partial (top earners, search-only, request-only); **D** = nothing usable found.

Record counts are rows loaded into `unipay.public_payroll_records` (staging only, not on the site).

| State | Systems found | Best rating | Years covered (best source) | Records loaded |
|---|---|---|---|---|
| Texas (TX) | 10: University of Texas System, Texas A&M University System, Texas Tech University System, University of Houston System, University of North Tex | A | 2020-2026 (snapshots; latest data dates 2025-01 to 2026-06 depending o | 170,130 |
| California (CA) | 3: University of California (10 campuses, UCOP, ASUCLA, ANR, UC Law SF), California State University (23 campuses + Chancellor's Office), Calif | C | 2010-2025 (calendar years) | 0 |
| New York (NY) | 2: State University of New York (SUNY): state-operated campuses, statutory colleges, 30 locally sponsored community colleges, City University o | A | FY2014-FY2025 | 262,569 |
| Florida (FL) | 2: State University System of Florida (12 universities, Board of Governors), Florida College System (28 state/community colleges) | A | Current snapshot only (labeled 'Spring 2026'); refreshed twice a year, | 0 |
| Illinois (IL) | 4: University of Illinois System, Southern Illinois University System, Regional public universities (ISU, NIU, EIU, WIU, CSU, NEIU, GSU), Illin | A | FY2010-FY2026 in search; XLSX files FY2016-FY2026 | 387,244 |
| Ohio (OH) | 4: Ohio Department of Higher Education / University System of Ohio (14 public universities, each self-governing), The Ohio State University, Oh | A | Salaries as of 9/30 and calendar-year earnings, 2021-2025 as XLSX (sea | 245,688 |
| Pennsylvania (PA) | 4: Pennsylvania State System of Higher Education (PASSHE, 10 universities), State-related universities (Penn State, Pitt, Temple, Lincoln), Tha | B | monthly snapshots 7/15/2012 - 9/15/2026 | 800 |
| Michigan (MI) | 2: 15 constitutionally autonomous public universities (no state system): University of Michigan (Ann Arbor, Dearborn, Flint), Michigan State, W | B | annual PDFs (as of Nov 1) at least 2020-2025; Deep Blue library archiv | 54,659 |
| Minnesota (MN) | 2: Minnesota State (formerly MnSCU: 7 state universities + 26 community and technical colleges), University of Minnesota System (Twin Cities, D | A | FY2011-FY2026 | 313,601 |
| Indiana (IN) | 4: Indiana University System, Purdue University System, Ball State, Indiana State, University of Southern Indiana, Vincennes University, Ivy Te | B | 2012-2025 | 1,679,632 |
| Alabama (AL) | 4: University of Alabama System, Auburn University System, Alabama Community College System (ACCS), Independent publics: Alabama A&M, Alabama S | C | 2016-2025 (filter); site reports ~1.09M salary rows | 0 |
| Alaska (AK) | 1: University of Alaska System (UAF, UAA incl. community campuses such as Prince William Sound College, UAS) | C | on request (current); semi-annual notices 2021-2026 | 0 |
| Arizona (AZ) | 2: Arizona Board of Regents (ASU, University of Arizona, NAU), Arizona community college districts (Maricopa County CCD, Pima CCD, and ~8 other | A | calendar years 2018-2025 (one CSV per year; 2018 also XLSX; '2023 revi | 234,227 |
| Arkansas (AR) | 7: University of Arkansas System, Arkansas State University System, Arkansas Tech University, University of Central Arkansas, Henderson State ( | B | FY2010-FY2026 | 15,432 |
| Colorado (CO) | 4: University of Colorado System, Colorado State University System (Fort Collins, Pueblo, Global), Colorado Community College System (CCCS), In | B | FY2024-25 (snapshot 11/1/2024); earlier years likely under similar /do | 0 |
| Connecticut (CT) | 2: University of Connecticut (incl. UConn Health), Connecticut State Colleges & Universities (CSCU, Board of Regents): Central, Eastern, Southe | A | calendar years 2015-present (min calendar_year value 2010; latest chec | 979,441 |
| Delaware (DE) | 3: University of Delaware (state-assisted, privately governed), Delaware State University, Delaware Technical Community College (4 campuses) | C | 2017-2025 | 0 |
| District of Columbia (DC) | 1: University of the District of Columbia (incl. UDC Community College) | A | current snapshot only (rows with 2025 hire dates present; DCHR page 'L | 11,432 |
| Georgia (GA) | 3: University System of Georgia (Board of Regents, 26 institutions), Technical College System of Georgia (22 colleges), Georgia Military Colleg | A | FY2015-FY2025 downloadable (state fiscal year Jul-Jun); older years in | 1,419,662 |
| Hawaii (HI) | 1: University of Hawaii System (10 campuses: UH Manoa, UH Hilo, UH West Oahu, 7 community colleges) | C | FY2011, 2012, 2013, 2016, 2018, 2020, 2022, 2024, 2026 | 0 |
| Idaho (ID) | 2: Idaho State Board of Education four-year institutions (Boise State, University of Idaho, Idaho State, Lewis-Clark State College), Community  | B | multi-year (reports cited 2015-2024; data said to update daily) | 0 |
| Iowa (IA) | 2: Board of Regents, State of Iowa (University of Iowa, Iowa State University, University of Northern Iowa, plus Iowa School for the Deaf / Iow | A | FY2007-FY2025 (coverage start 2006-07-01); per-year datasets FY2019-FY | 0 |
| Kansas (KS) | 3: Kansas Board of Regents state universities (KU, KU Medical Center, Kansas State, Wichita State, Emporia State, Pittsburg State, Fort Hays St | A | 2020-2025 (CSV covers 2021-2025; 2020 in web table) | 122,263 |
| Kentucky (KY) | 2: Independent public universities coordinated by Council on Postsecondary Education (UK, UofL, WKU, EKU, Murray State, Morehead State, NKU, Ke | C | current (updated monthly on the 24th) | 0 |
| Louisiana (LA) | 5: LSU System, University of Louisiana System (9 universities), Southern University System, Louisiana Community and Technical College System (L | C | 2023-present (launched Sept 2023) | 0 |
| Maine (ME) | 3: University of Maine System (UM, UMA, UMF, UMFK, UMM, UMPI, USM, Maine Law, System-Wide Services), Maine Community College System (7 colleges | A | current snapshot June 2026 on page; earlier editions (Nov 2019, Apr 20 | 22,902 |
| Maryland (MD) | 4: University System of Maryland (12 institutions incl. UMD College Park, UMB, UMBC, Towson, Salisbury, etc.), Morgan State University (indepen | A | 2013-2025 | 140,391 |
| Massachusetts (MA) | 3: University of Massachusetts System (Amherst, Boston, Dartmouth, Lowell, Chan Medical School/Worcester), Massachusetts State Universities (Br | A | 2010-2026 (calendar years; current year updated through latest pay per | 1,198,973 |
| Mississippi (MS) | 2: Mississippi Institutions of Higher Learning (IHL): Univ. of Mississippi (incl. UMMC), Mississippi State, Southern Miss, Jackson State, Alcor | C | 2017-2025 | 0 |
| Missouri (MO) | 3: University of Missouri System (Columbia, Kansas City, Missouri S&T, St. Louis, MU Health Care), Regional public universities (Missouri State | B | 2007-2025 | 263,272 |
| Montana (MT) | 2: Montana University System (University of Montana campuses: Missoula, Montana Tech, UM Western, Helena College; Montana State University camp | C | not stated | 0 |
| Nebraska (NE) | 3: University of Nebraska System (UNL, UNMC, UNO, UNK, IANR/NCTA, System office/ITS), Nebraska State College System (Chadron, Peru, Wayne State | A | XLSX FY2022-23 through FY2026-27; budget-by-department PDF volumes bac | 152,668 |
| Nevada (NV) | 1: Nevada System of Higher Education (NSHE): UNLV, UNR, Nevada State University, Desert Research Institute, College of Southern Nevada, Truckee | A | 2009-2025 (per-campus pages 2009-2021; combined 'NSHE Administration'  | 0 |
| New Hampshire (NH) | 2: University System of New Hampshire (UNH, Plymouth State, Keene State, Granite State College/UNH Manchester), Community College System of New | C | Calendar year 2012-present (per search snippet) | 0 |
| New Jersey (NJ) | 5: Rutgers University (incl. RBHS), NJIT, Rowan University, State colleges/universities: Montclair State, Kean, William Paterson, NJCU, Ramapo, | A | current snapshot (as_of_date 2026-06-30; salary = four most recent rep | 12,922 |
| New Mexico (NM) | 8: University of New Mexico (incl. branch campuses, HSC), New Mexico State University (incl. branches), New Mexico Highlands University, New Me | A | current fiscal year snapshot only (FY July-June; refreshed monthly on  | 13,549 |
| North Carolina (NC) | 2: University of North Carolina System (17 institutions + System Office), North Carolina Community College System (58 colleges) | C | Current quarterly snapshot only (page states data current as of Septem | 0 |
| North Dakota (ND) | 1: North Dakota University System (NDUS: 11 institutions incl. UND, NDSU, and the 2-year colleges BSC, LRSC, WSC, NDSCS, DCB) | C | last ten fiscal years (per help page), monthly detail | 0 |
| Oklahoma (OK) | 6: Oklahoma State System of Higher Education (State Regents), University of Oklahoma (incl. OU Health Sciences Center), Oklahoma State Universi | A | 2010 (Q3) through FY2027 to date (July 2026); calendar-year datasets 2 | 394,645 |
| Oregon (OR) | 2: Seven independent public universities with their own boards (UO, OSU, PSU, OIT, SOU, WOU, EOU), coordinated by the Higher Education Coordina | C | multi-year incl. 2025 (558,282 salary records per search snippet) | 0 |
| Rhode Island (RI) | 1: Rhode Island public higher education (Council on Postsecondary Education / Office of the Postsecondary Commissioner): University of Rhode Is | A | FY2011-FY2026 (FY2026 partial; page says last updated October 9, 2025) | 0 |
| South Carolina (SC) | 2: SC public senior institutions (USC system, Clemson, College of Charleston, MUSC, Winthrop, Coastal Carolina, SC State, The Citadel, Francis  | B | current fiscal year only (page says last updated September 16, 2026) | 20,264 |
| South Dakota (SD) | 2: South Dakota Board of Regents (6 universities: USD, SDSU, SD Mines, NSU, DSU, BHSU, plus 2 special schools), South Dakota Board of Technical | C | current ('constantly updated' from the state payroll system) | 0 |
| Tennessee (TN) | 3: University of Tennessee System (UTK, UTC, UT Martin, UT Southern, UTHSC, UTIA, UT Institute for Public Service), Tennessee Board of Regents  | B | current ('Updated as of 2026'; file last-modified 2026-09-23) | 3,631 |
| Utah (UT) | 1: Utah System of Higher Education (USHE): University of Utah, Utah State University (incl. USU Eastern, Blanding), Weber State, Southern Utah, | A | About FY2010 to FY2025, varies by entity (annual compensation reports  | 0 |
| Vermont (VT) | 2: University of Vermont (UVM), Vermont State Colleges System: Vermont State University and Community College of Vermont | B | FY2009-10 to FY2025-26 (one PDF per year; snapshot as of Nov 1) | 70,348 |
| Virginia (VA) | 3: 15 independent public four-year institutions (UVA, Virginia Tech, VCU, GMU, W&M, JMU, ODU, Radford, VMI, VSU, NSU, CNU, Longwood, UMW, UVA-W | C | FY2017 to about FY2022 in the new portal (the VT library FAQ says Virg | 0 |
| Washington (WA) | 2: Six public four-year institutions (University of Washington, Washington State University, Western Washington, Central Washington, Eastern Wa | A | calendar years 2010-2013 | 374,836 |
| West Virginia (WV) | 2: WV Higher Education Policy Commission (HEPC): WVU (incl. Potomac State, WVU Tech), Marshall, Bluefield State, Concord, Fairmont State, Glenv | C | Report described as of Dec 31, 2021 (calendar 2021); later years not c | 0 |
| Wisconsin (WI) | 2: Universities of Wisconsin (formerly UW System; 13 universities incl. UW-Madison, UW-Milwaukee), Wisconsin Technical College System (WTCS, 16 | C | FY2013+ for expenditures; salary tab years not confirmed | 0 |
| Wyoming (WY) | 2: University of Wyoming, Wyoming Community College Commission (7 colleges: Casper, Central Wyoming, Eastern Wyoming, Laramie County CC, Northe | C | 2017-2025 | 0 |

Total records loaded: **8,565,181**

## Texas (TX)

Systems: University of Texas System, Texas A&M University System, Texas Tech University System, University of Houston System, University of North Texas System, Texas State University System, Texas Woman's University, Stephen F. Austin State University (now in UT System), Texas State Technical College, Texas public community college districts (about 50, each locally governed; no statewide system payroll)  
Best rating: **A**. Records loaded: **170,130**.

### [A] Texas College Salaries (volunteer project, data from Texas Public Information Act requests)  (catalog id 160)

- System/publisher: Multi-system: UT, Texas A&M, Texas Tech, UH, UNT, Texas State, TWU, TSTC, about 25 community college districts
- URL: https://texascollegesalaries.com/historic_data
- Download: https://drive.google.com/drive/folders/1RHnj46y3B5X8T4siwudKJOBmuJYDAMRF
- Format: CSV (Google Drive file 'TCS Export 05_25_2026.csv', plus a Google Doc readme); HTML per-employee pages on the site; years: 2020-2026 (snapshots; latest data dates 2025-01 to 2026-06 depending on institution)
- Coverage: 67 institutions (universities, health science centers, system offices, community colleges), 181,913 employees on file; employees: all (as released by each institution; annual base salary only)
- Fields: institution, department, name, title, annual_base_salary, gender, ethnicity, hire_date/employment dates (varies by institution)
- Access: login/form required: False; terms: Search results say the site is licensed CC BY-SA 4.0; FAQ says data come from TPIA requests and are not sold; updates: 2-3 times per year; size: 22.5 MB CSV (May 2026 export)
- Notes: This is the best single bulk source for Texas public higher ed. It is unofficial and volunteer-run. Fields vary by institution because each school answers the records request differently (FAQ Q03). Base salary only, no overtime or supplemental pay. The download is a Google Drive folder, so you need the file ID or Drive API to fetch it automatically. A 'Data processing statement' page describes how the data were cleaned. I did not download the CSV, so the fields listed are inferred from the FAQ and site pages.
- **Loaded: 170,130 records**

### [D] Texas Tribune Government Salaries Explorer (Texas Comptroller state employee payroll)  (catalog id 161)

- System/publisher: State agencies only
- URL: https://salaries.texastribune.org/
- Download: https://s3.amazonaws.com/raw.texastribune.org/state_of_texas/salaries/02_non_duplicated_employees/2026-07-01.csv
- Format: CSV; years: Snapshot 2026-07-01 (older snapshots probably exist at the same S3 prefix)
- Coverage: 116 state agencies; public universities and colleges are NOT included; employees: all state agency employees (not higher ed)
- Fields: agency, agency_name, last_name, first_name, mi, class_code, class_title, ethnicity, gender, employee_type, hire_date, rate, hours_worked, monthly, annual, statenum, duplicated, multiple_full_time_jobs, summed_annual_salary
- Access: login/form required: False; terms: not stated (Tribune publishes it in the public interest); updates: periodic (several times a year); size: 46.6 MB (Content-Length 46,581,557)
- Blocker: Leaves out institutions of higher education; useful only as a template or for any A&M System service agencies, if they are included
- Notes: Clean A-quality file for state agencies, rated D here because it has no university payroll. The Tribune says it 'no longer publishes salaries for other employees'. Its 2010-2011 higher-ed data (UT, A&M, Tech, UH, UNT) is no longer published. I could not confirm whether A&M System agencies such as AgriLife Extension, Forest Service or TEEX appear in it.

### [D] UT System institutional annual operating budgets  (catalog id 162)

- System/publisher: University of Texas System (also Stephen F. Austin)
- URL: https://www.utsystem.edu/
- Download: https://www.utsystem.edu/sites/default/files/documents/report-state/2026/annual-operating-budgets-stephen-f-austin-state-university/fy-2027-stephen-f-austin-state-university.pdf
- Format: PDF; years: FY2019-FY2027 (older volumes on UNT Portal to Texas History)
- Coverage: UT System institutions; employees: aggregate only
- Fields: department, category (faculty/classified salaries), FTE, salaries_and_wages_total
- Access: login/form required: False; terms: not stated; updates: annual; size: about 5.6 MB per institution PDF
- Blocker: Not person-level: totals by department and salary category only
- Notes: I checked the SFA FY2027 volume (116 pages). It has department totals for FTE and salaries but no names. Recorded so nobody re-checks it.

### [C] OpenPayrolls / GovSalaries / OpenTheBooks (commercial or nonprofit aggregators)  (catalog id 163)

- System/publisher: Multi
- URL: https://openpayrolls.com/
- Format: search-form / HTML; years: varies (about 2018-2025)
- Coverage: many Texas public universities; employees: varies
- Fields: name, title, employer, pay, year
- Access: login/form required: True; terms: not stated (openpayrolls.com returned HTTP 403 to automated fetch); updates: unknown; size: unknown
- Blocker: Search-only third-party sites; openpayrolls blocks automated access (403); no bulk download
- Notes: Secondary sources. Texas College Salaries is better.

**Private institutions / extra:** None found. Rice, SMU, Baylor, TCU and other Texas privates publish only IRS 990 data.

**Gaps:** There is no official statewide or system-level person-level higher-ed payroll file. The Comptroller payroll leaves out universities, and UT, A&M and Tech budgets are aggregate. Universities do not post person-level salaries on their own sites, so Texas depends on the volunteer TPIA-based Texas College Salaries dataset. It covers about 25 of roughly 50 community college districts and base salary only (no total or other pay).

**State notes:** I treated the Tribune/Comptroller file as out of scope for universities (rated D) but recorded it because it is clean and bulk. I checked UT System operating budget PDFs and confirmed they are aggregate. I did not download the Texas College Salaries CSV (22.5 MB), so its fields come from the FAQ and site pages. The best fix for official data would be TPIA requests to each system office.

## California (CA)

Systems: University of California (10 campuses, UCOP, ASUCLA, ANR, UC Law SF), California State University (23 campuses + Chancellor's Office), California Community Colleges (73 districts, 116 colleges; locally governed)  
Best rating: **C**. Records loaded: **0**.

### [C] UC Annual Wage database (UC Office of the President)  (catalog id 21)

- System/publisher: University of California
- URL: https://ucannualwage.ucop.edu/wage/
- Download: https://ucannualwage.ucop.edu/wage/search (undocumented AJAX endpoint used by the search form; params op, page, rows, sidx, sord + form fields year, firstname, lastname, location, title, pay range)
- Format: search-form (HTML results loaded by AJAX); years: 2010-2025 (calendar years)
- Coverage: All UC locations: Berkeley, Davis, Irvine, UCLA, Merced, Riverside, San Diego, San Francisco, Santa Barbara, Santa Cruz, UCOP, ASUCLA, ANR, UC Law SF; employees: all (names redacted as '******' for student-status employees, including medical residents)
- Fields: year, location, first_name, last_name, title, gross_pay, regular_pay, overtime_pay, other_pay
- Access: login/form required: True; terms: UCOP Terms of Use, https://www.ucop.edu/terms/index.html; updates: annual (calendar year data released mid-following year); size: about 300,000-360,000 rows per year (per Transparent California counts for UC)
- Blocker: Search-only form with no bulk export; getting everything means paging the undocumented /wage/search endpoint (a form submission, which I did not try)
- Notes: Official person-level UC source with names and a pay breakdown. The JS (wg.js) shows paged queries with a 'rows' page-size parameter and location 'ALL'. If the owner allows automated form paging, this could be upgraded to B or A. Page also warned 'A search error occurred' at times.

### [C] Transparent California (California Policy Center)  (catalog id 22)

- System/publisher: UC, CSU, community college districts (plus cities, counties, etc.)
- URL: https://transparentcalifornia.com/salaries/university-of-california/
- Download: In-page 'Download CSV' buttons (JS, via https://transparentcalifornia.com/api/v1); filenames like university-of-california-salary-2025.csv. The legacy /export/<year>-<slug>.csv URLs now redirect to the home page.
- Format: CSV (after login); HTML tables rendered client-side; years: UC 2011-2025; CSU and community college districts multi-year (about 2011-2025, varies by agency)
- Coverage: UC (system-wide file), CSU, and most community college districts as separate agencies; employees: all
- Fields: name, job_title, department/employer, base_pay, overtime, other_pay, total_benefits, total_pay, total_pay_and_benefits, year, notes
- Access: login/form required: True; terms: not stated on salary page (Privacy and Disclaimer pages linked); robots.txt allows agency pages, disallows /salaries/all/ and /salaries/search/, crawl-delay 1; updates: annual; size: UC: 361,406 rows (2025), 357,157 (2024), 339,037 (2023), and so on back to 259,043 (2011)
- Blocker: The redesigned site requires a (free) account login before any CSV download; the JS sends anonymous users to /login
- Notes: This would be the best California source (A quality: per-agency, per-year CSVs with names and a full pay breakdown) if the owner creates a free account. It covers CSU and community colleges with names, which official sources do not. Data come from CPRA requests.

### [C] Government Compensation in California (State Controller's Office)  (catalog id 23)

- System/publisher: CSU (mandatory), UC and community college districts (voluntary)
- URL: https://publicpay.ca.gov/ (now redirects to https://gcc.sco.ca.gov/)
- Download: https://gcc.sco.ca.gov/Reports/RawExport.aspx ; files like https://gcc.sco.ca.gov/RawExport/2024_CaliforniaStateUniversity.zip and 2024_UniversityOfCalifornia.zip (pattern inferred; HEAD returned 403 Cloudflare challenge)
- Format: CSV in ZIP (raw export by year and employer type); years: 2009-2025 (2025 CSU data released; 113,967 CSU employees in 2025)
- Coverage: CSU 23 campuses + Chancellor's Office; UC; reporting community college districts; employees: all positions, but NO employee names
- Fields: year, employer_type, employer_name, department_or_subdivision, position, min_position_salary, max_position_salary, reported_base_wage, regular_pay, overtime_pay, lump_sum_pay, other_pay, total_wages, retirement_contributions, health_dental_vision, employer_county
- Access: login/form required: True; terms: not stated (SCO posts data as reported and does not audit it); updates: annual; size: not determined (blocked)
- Blocker: Not person-level (positions only, no names), and Cloudflare 'Just a moment' JS challenge returns 403 to scripted requests
- Notes: Clean official bulk data, and the only official CSU pay source, but it has no names. The field list is from my own knowledge of the GCC raw export because I could not load the page. A human in a browser can probably download the ZIPs.

### [C] Sacramento Bee State Worker Pay database  (catalog id 24)

- System/publisher: California state civil service + CSU
- URL: https://www.sacbee.com/news/databases/state-pay/
- Format: search-form; years: unknown (updates reported through 2022-2023 data)
- Coverage: CSU campuses (plus state departments); employees: all CSU employees, by name
- Fields: name, department, title, regular_pay, overtime, other_pay, total_pay, year
- Access: login/form required: True; terms: not stated (could not load); updates: annual; size: unknown
- Blocker: Search-only news database, sacbee.com refused automated fetch, and it may be paywalled
- Notes: Fields are from secondary descriptions. CSU person-level data is also available from Transparent California.

**Private institutions / extra:** None found. Stanford, USC, Caltech and other privates publish only IRS 990 data. (Stanford posts some aggregate compensation reports but nothing person-level.)

**Gaps:** No official bulk, person-level file exists for any California higher-ed system. UC names are behind a search form, and CSU and community college names come only from third parties: Transparent California (now behind a free login) and the Sacramento Bee (search-only). The official SCO bulk file has no names and is behind Cloudflare. I did not check individual community college district websites; they post salary schedules, not person-level pay.

**State notes:** I followed the rules strictly: login, form and JS-challenge sources are rated C even when the data underneath are A quality. Recommendation: (1) a free Transparent California account gives A-quality CSVs for UC, CSU and community colleges; (2) if form paging is allowed, the UC Annual Wage /wage/search endpoint gives official UC data from 2010 on. data.ca.gov (CKAN) had no relevant salary datasets. GCC field names are from prior knowledge, not confirmed this session.

## New York (NY)

Systems: State University of New York (SUNY): state-operated campuses, statutory colleges, 30 locally sponsored community colleges, City University of New York (CUNY): senior colleges (state-funded) and 7 community colleges (city-funded)  
Best rating: **A**. Records loaded: **262,569**.

### [A] NYC Citywide Payroll Data (Fiscal Year), NYC Office of Payroll Administration  (catalog id 125)

- System/publisher: CUNY community colleges
- URL: https://data.cityofnewyork.us/City-Government/Citywide-Payroll-Data-Fiscal-Year-/k397-673e
- Download: https://data.cityofnewyork.us/api/views/k397-673e/rows.csv?accessType=DOWNLOAD (full CSV); SODA API https://data.cityofnewyork.us/resource/k397-673e.json?$where=agency_name like 'COMMUNITY COLLEGE%'
- Format: API (Socrata SODA) / CSV; years: FY2014-FY2025
- Coverage: Bronx CC, Hostos CC, Kingsborough CC, LaGuardia CC, Borough of Manhattan CC, Queensborough CC, Guttman CC (agency_name values 'COMMUNITY COLLEGE (BRONX)', etc. and 'GUTTMAN COMMUNITY COLLEGE'); employees: all employees on the city payroll at CUNY community colleges (faculty, staff, adjuncts)
- Fields: fiscal_year, payroll_number, agency_name, last_name, first_name, mid_init, agency_start_date, work_location_borough, title_description, leave_status_as_of_june_30, base_salary, pay_basis, regular_hours, regular_gross_paid, ot_hours, total_ot_paid, total_other_pay
- Access: login/form required: False; terms: NYC Open Data Terms of Use (no license field set on the dataset); updates: annual (last rows update 2026-04-16); size: 6,775,830 rows in the whole dataset; about 262,000 CUNY community college rows (15,500-37,000 per year, e.g. FY2025 19,295)
- Notes: Clean and loadable. Filter by agency_name with the SODA API instead of downloading the full 6.8M-row file. Hunter College High School also appears (K-12, not a college). CUNY senior colleges are not in this dataset; they are on the state payroll.
- **Loaded: 262,569 records**

### [C] SeeThroughNY (Empire Center), state payroll from the Office of the State Comptroller  (catalog id 126)

- System/publisher: SUNY state-operated campuses and hospitals, CUNY senior colleges; also county, NYC and school payrolls
- URL: https://www.seethroughny.net/payrolls
- Format: search-form (AJAX results); years: 2008-2026 in the year filter (state payroll data notes say 2008-2023, as of Dec 31 each year)
- Coverage: All SUNY state-operated campuses (in the 'State - Executive' branch); CUNY (state-paid senior college employees); community colleges only where county payroll includes them; employees: all (state payroll)
- Fields: name, employer/agency, subagency/campus, title, rate_of_pay, pay_basis, total_pay, year, branch
- Access: login/form required: True; terms: Terms of Use at https://www.seethroughny.net/terms-use (boilerplate; no explicit scraping ban found); data 'from official government sources', accuracy not guaranteed; robots.txt does not block /payrolls; updates: annual; size: not stated
- Blocker: Search-only form with no bulk download found; getting complete data means paging AJAX searches (a form submission)
- Notes: This is the only public person-level source for SUNY and CUNY senior colleges. Underlying data are OSC payroll files obtained by FOIL. A FOIL request to OSC for the state payroll file filtered to SUNY/CUNY departments would give A-quality data.

### [D] NY Authorities Budget Office (PARIS) salary data on data.ny.gov  (catalog id 127)

- System/publisher: State and local public authorities
- URL: https://data.ny.gov/d/unag-2p27
- Download: https://data.ny.gov/api/views/unag-2p27/rows.csv?accessType=DOWNLOAD ; https://data.ny.gov/api/views/fx93-cifz/rows.csv?accessType=DOWNLOAD
- Format: API (Socrata) / CSV; years: multi-year (fiscal_year_end_date)
- Coverage: No SUNY/CUNY campuses: a query for authority names containing UNIVERS or COLLEGE returned none; employees: authority employees
- Fields: authority_name, fiscal_year_end_date, last_name, middle_initial, first_name, title, group, department, pay_type, base_annualized_salary, actual_salary_paid, overtime_paid, performance_bonus, extra_pay, other_compensation, total_compensation
- Access: login/form required: False; terms: data.ny.gov terms (no license on dataset); updates: annual; size: not checked
- Blocker: No higher-ed institutions in the data
- Notes: Checked and ruled out. The Dormitory Authority (DASNY) is a state authority but not a college.

**Private institutions / extra:** None found. Columbia, NYU, Cornell's endowed colleges and other privates publish only IRS 990 data. (Cornell's statutory colleges are SUNY units and are on the state payroll.)

**Gaps:** There is no official bulk person-level file for SUNY or CUNY senior colleges. OSC does not publish a name-level payroll download, so SeeThroughNY (search-only) is the only option. The 30 SUNY community colleges are paid by their sponsoring counties or the colleges themselves, and coverage depends on county payrolls (SeeThroughNY 'Counties' branch). The SUNY Research Foundation (a private nonprofit) is not covered.

**State notes:** Searched Socrata catalogs for data.ny.gov and data.cityofnewyork.us. I confirmed by SODA queries that CUNY community colleges are in the NYC Citywide Payroll and that the PARIS authority salary data has no colleges. I did not run SeeThroughNY's AJAX search because that counts as a form submission. Its field list comes from the data notes (name, position, rate, total pay).

## Florida (FL)

Systems: State University System of Florida (12 universities, Board of Governors), Florida College System (28 state/community colleges)  
Best rating: **A**. Records loaded: **0**.

### [A] Florida Board of Governors 'Right to Know' SUS payroll (linked from Florida Has a Right to Know)  (catalog id 40)

- System/publisher: State University System of Florida
- URL: https://prod.flbog.net/ords/f?p=140:1::::::
- Download: Oracle APEX report export: 'Download Results' link (#action$download?widgetAction=FLOW_EXCEL_OUTPUT_R161951744643473500_en) on the page above; clear all search criteria to get the full data set. Session-bound, no static URL.
- Format: CSV (APEX classic report download) / HTML table; years: Current snapshot only (labeled 'Spring 2026'); refreshed twice a year, about April and November
- Coverage: All 12 SUS universities (FAMU, FAU, FGCU, FIU, FPU, FSU, New College, UCF, UF, UNF, USF, UWF); employees: all (salaried and OPS, including graduate assistants; grad assistant names appear as 'Graduate Assistant'; confidential/exempt records removed)
- Fields: university, first_name, last_name, employment_type, budget_entity/job_category, class_title, annual_compensation, funding_source, fte
- Access: login/form required: False; terms: not stated; data notes say salaries may come from public and private sources and confidential/exempt records are left out; updates: semi-annual (about April and November); size: not stated (full SUS payroll, probably 100,000+ rows since employees appear once per funding source)
- Notes: Official full-dataset download with no login. The download link depends on an APEX session cookie, so a scraper must GET the page first, then the download URL, in the same cookie session. There is no history: capture each snapshot when it is published. No department field, but funding source and class title are included. One person can have several rows (one per funding source) with fractional FTE. I did not download the full file.

### [B] Florida College System salaries (DMS, Florida Has a Right to Know)  (catalog id 41)

- System/publisher: Florida College System
- URL: https://college-salaries.myflorida.com/
- Download: In-page 'Export Results' button (JS; data from the site's backend API, endpoint not documented)
- Format: search-form with CSV/XLSX export (Next.js app); years: Current snapshot; collected twice a year (March data = prior calendar year; September data = prior fiscal year July-June)
- Coverage: All 28 FCS colleges (Broward, Chipola, Central Florida, Daytona State, Eastern Florida State, Florida Gateway, Florida SouthWestern, FSCJ, Gulf Coast, Hillsborough, Indian River, Lake-Sumter, Miami Dade, North Florida, Northwest Florida State, Palm Beach State, Pasco-Hernando, Pensacola, Polk, Santa Fe, Seminole State, South Florida State, SCF Manatee-Sarasota, St. Johns River, St. Petersburg, Tallahassee State, Florida Keys, Valencia); employees: all (confidential/exempt records removed)
- Fields: employee_name, college, annual_salary, function, position_title, category_title
- Access: login/form required: False; terms: not stated; updates: semi-annual (about March and September); size: not stated
- Blocker: No static bulk file. Export only runs through the JS search UI ('All Colleges' plus 'Export Results'); the backend API is undocumented and needs a browser or reverse-engineering
- Notes: Official and complete for FCS, with no login or CAPTCHA. Exporting with all filters cleared should give every college at once (not tested). Fields come from the filter labels on the page.

### [D] Florida Has a Right to Know: State Personnel System payroll (DMS / People First)  (catalog id 42)

- System/publisher: State agencies (not universities or colleges)
- URL: https://www.floridahasarighttoknow.myflorida.com/search_state_payroll
- Download: http://salaries.myflorida.com/
- Format: search-form with export; years: current, updated weekly
- Coverage: 28 executive-branch State Personnel System entities; no SUS or FCS institutions; employees: state agency employees
- Fields: name, agency, position_title, salary
- Access: login/form required: False; terms: not stated; updates: weekly (Mondays); size: not checked
- Blocker: No higher-ed employees; universities and colleges have their own sources (above)
- Notes: This hub page links to the SUS (BOG) and FCS sources and to an SBA payroll XLSX (https://dms-media.ccplatform.net/content/download/106666/file/As%20of%202026.09.30.xlsx), which is not higher ed.

**Private institutions / extra:** None found. University of Miami and other private Florida schools publish only IRS 990 data.

**Gaps:** Both official sources are current snapshots with no archive, so a time series means capturing every April/November (SUS) and March/September (FCS) release. The SUS data has no department field and lists one row per funding source. I did not look for older data such as news databases or individual university HR pages. UF, FSU and others answer public records requests but post no separate bulk files that I found. Row counts were not stated on either site.

**State notes:** Rated the BOG SUS source A because a full-dataset download is offered with no login (session cookie only). Rated the FCS source B because export runs only through the JS UI. I followed the links from the Florida Has a Right to Know payroll hub page. I did not click any downloads or exports.

## Illinois (IL)

Systems: University of Illinois System, Southern Illinois University System, Regional public universities (ISU, NIU, EIU, WIU, CSU, NEIU, GSU), Illinois Community College System (ICCB, 48 colleges in 39 districts)  
Best rating: **A**. Records loaded: **387,244**.

### [A] All 48 Illinois public community colleges  (catalog id 56)

- System/publisher: Illinois Community College Board (ICCB)
- URL: http://iccbdbsrv.iccb.org/salarysearch/home.cfm
- Download: https://iccbdbsrv.iccb.org/salarysearch/fiscalyr/Fiscal Year 2026 Salary & Benefits of IL CC Admin & Instructors.xlsx (one file per year FY2016-FY2026; same folder, file names vary slightly: 'Instructor' vs 'Instructors', FY2017 has ' 2018-03' suffix)
- Format: XLSX; years: FY2010-FY2026 in search; XLSX files FY2016-FY2026
- Coverage: All public community college districts (portal says 45 colleges in text; ICCB system is 48 colleges); employees: administrators and instructional staff (full- and part-time); no classified/support staff
- Fields: college, name, title, full/part-time, base_pay, extra_duty_pay, other_benefits, vacation_days, sick_days, fiscal_year
- Access: login/form required: False; terms: not stated; updates: annual (report due July 1; FY2026 file posted 2026-09-02); size: ~1.6 MB per XLSX (FY2026 1,630,001 bytes; FY2016 1,870,017 bytes)
- Notes: Required by P.A. 96-0266. Direct static XLSX links on home page; HEAD confirmed 200. Field list from definitions page; verify column headers when loading. Also searchable by college/name/title.
- **Loaded: 196,985 records**

### [B] All 12 public universities (UIUC, UIC, UIS, UI System Admin, SIUC, SIUE, SIU School of Medicine, SIU System, ISU, NIU, EIU, WIU, CSU, NEIU, GSU)  (catalog id 57)

- System/publisher: Illinois Board of Higher Education (IBHE)
- URL: https://salarysearch.ibhe.org/
- Download: https://salarysearch.ibhe.org/search.aspx ('Download Data' button = ASP.NET postback that returns an MS-Excel file of the current search; no static URL)
- Format: search-form with Excel export; years: FY2010-FY2025
- Coverage: all Illinois public universities; employees: president, administrators, faculty, instructors (incl. adjuncts); excludes graduate assistants and civil service/support staff
- Fields: institution, name, position category, job title, full/part-time, base_salary, additional_compensation, benefits (vacation, sick, bonuses, retirement enhancements, other benefits), fiscal_year
- Access: login/form required: True; terms: not stated (data as submitted by universities); updates: annual; size: not stated
- Blocker: No static file: Excel export needs a scripted ASP.NET postback (viewstate) per year with 'All Institutions' selected.
- Notes: No CAPTCHA seen. Default selection is All Institutions / All Positions, so one export per year likely returns everyone. Info log last shown entry is 2023 but year dropdown goes to 2025. Not tested (no form submissions made).
- **Loaded: 143,713 records**

### [B] University of Illinois (Urbana-Champaign, Chicago, Springfield, System Offices)  (catalog id 58)

- System/publisher: University of Illinois System
- URL: https://www.bot.uillinois.edu/gray-book
- Download: https://www.trustees.uillinois.edu/trustees/resources/26-27-Graybook/TOC.html (per-unit HTML pages e.g. .../26-27-Graybook/AM.html); prior years at https://www.trustees.uillinois.edu/trustees/resources/historical-files/html%20versions/25-26-Graybook/
- Format: HTML (also DOCX/PDF per campus in some years); years: 2026-27 current; historical HTML versions for at least 2023-24 and 2025-26 (earlier years likely in historical-files)
- Coverage: UIUC, UIC, UIS, System Offices; employees: academic and administrative staff (faculty, academic professionals); civil service staff not included
- Fields: name, job_title, tenure, employee_class, present_fte, proposed_fte, present_salary, proposed_salary, unit/department, employee total for all jobs
- Access: login/form required: False; terms: not stated; updates: annual (August Board meeting; 2026-27 dated Aug 24, 2026); size: ~130 links in TOC; one HTML table per unit
- Blocker: No CSV; ~130 per-unit HTML pages must be scraped and multi-job rows reconciled.
- Notes: bot.uillinois.edu landing page returned 403 to scripts; trustees.uillinois.edu pages return 200. Clean, consistent table markup. The 25-26 DOCX links found in search now 404 (moved to historical folder).
- **Loaded: 21,515 records**

### [B] University of Illinois (all campuses)  (catalog id 59)

- System/publisher: University of Illinois System - Planning & Budgeting
- URL: https://www.pb.uillinois.edu/
- Download: https://www.pb.uillinois.edu/documents/FY26-Salary-Book.pdf
- Format: PDF; years: FY2026 (budgeted rates as of fall 2025); FY27 file not yet at the analogous URL
- Coverage: UIUC, UIC, UIS, System; employees: unclear - described as salary book of budgeted pay rates; may include civil service
- Fields: name, title, unit, fte, salary (budgeted)
- Access: login/form required: False; terms: not stated; updates: annual; size: 10.3 MB PDF
- Blocker: Large PDF; text extraction not verified (could not render here).
- Notes: Field list assumed from typical salary book layout; verify. Possibly broader than the Gray Book if it includes civil service.

### [B] Illinois State University  (catalog id 60)

- System/publisher: Illinois State University
- URL: https://ir.library.illinoisstate.edu/salaries
- Download: https://files.library.illinoisstate.edu/ISUSalaries/fy24_salaries.pdf (pattern fyNN_salaries.pdf; plus separate update files)
- Format: PDF; years: FY1990s-FY2026 (repository items FY2005-FY2026; guide says back to 1990)
- Coverage: Illinois State University; employees: all (faculty, administrative professional, civil service)
- Fields: name, title, department, salary, fte
- Access: login/form required: False; terms: not stated; updates: annual (plus mid-year update files); size: ~1.6 MB per year PDF
- Blocker: PDF only; requires table extraction per year.
- Notes: Hosted in Milne Library bepress repository. Field list presumed; verify.
- **Loaded: 25,031 records**

### [C] UIUC, SIUE, Missouri S&T and other St. Louis-area public employers  (catalog id 61)

- System/publisher: St. Louis Post-Dispatch Public Pay (news)
- URL: https://graphics.stltoday.com/apps/payrolls/
- Format: HTML; years: multiple annual editions (salaries_2024, salaries_2025)
- Coverage: UIUC (agency 114), SIUE (136), others in Metro East; employees: all on payroll (gross pay)
- Fields: agency, department, name, title, gross_pay, year
- Access: login/form required: False; terms: not stated; robots disallows master search URLs; updates: annual; size: not stated
- Blocker: News site HTML with ads, partial institution coverage; official sources better.
- Notes: Derivative of FOIA'd payrolls; useful only as a cross-check for civil service gross pay.

### [C] Various  (catalog id 62)

- System/publisher: OpenTheBooks / OpenPayrolls (third-party)
- URL: https://www.openthebooks.com/illinois-state-employees/
- Format: search-form; years: varies
- Coverage: varies (OpenPayrolls has SIUC records back to 2012); employees: all
- Fields: name, title, employer, pay, year
- Access: login/form required: True; terms: site terms restrict reuse; updates: irregular; size: not stated
- Blocker: Search-only third-party aggregators, no bulk download.
- Notes: Not inspected in detail.

**Private institutions / extra:** None found. Daily Illini (student paper) publishes a Salary Guide for UI only. No private Illinois school found publishing pay beyond IRS 990.

**Gaps:** Civil service / support staff pay at universities is not in the statewide IBHE or ICCB data (they cover only administrators and faculty). Civil service is covered only where a campus publishes it (ISU PDFs, possibly UI Salary Book). No official CSV for universities. NIU, SIU, EIU, WIU, CSU, NEIU, GSU have no standalone salary pages found beyond the IBHE database. Illinois Comptroller payroll data does not appear to include universities (they run their own payroll); data.illinois.gov has no salary datasets.

**State notes:** Rated IBHE as B rather than A because the Excel export is a postback, not a static file; I did not submit the form. Did not download any bulk files (HEAD only). UI FY26 Salary Book contents not verified because the PDF could not be rendered locally.

## Ohio (OH)

Systems: Ohio Department of Higher Education / University System of Ohio (14 public universities, each self-governing), The Ohio State University, Ohio University, Ohio community colleges (23, each independent; Ohio Association of Community Colleges)  
Best rating: **A**. Records loaded: **245,688**.

### [A] The Ohio State University (University, Athletics, Wexner Medical Center/Health System)  (catalog id 128)

- System/publisher: The Ohio State University
- URL: https://apps.hr.osu.edu/salaries/
- Download: https://apps.hr.osu.edu/public/documents/salaries/2025-Salaries-Combined-v3.xlsx ; https://apps.hr.osu.edu/public/documents/salaries/2025-Earnings-Combined.xlsx (pattern YYYY-Salaries-Combined.xlsx and YYYY-Earnings-Combined.xlsx for 2021-2025)
- Format: XLSX; years: Salaries as of 9/30 and calendar-year earnings, 2021-2025 as XLSX (search tool since 2018, earlier years were in the tool)
- Coverage: Ohio State (all campuses, incl. medical center and athletics); employees: all non-student employees
- Fields: first_name, last_name, job_title, funding_unit/college (CCH6), department, database (University/Athletics/Health System), salary_or_hourly_rate, fte, regular_earnings, overtime, bonus, leave_payout, year
- Access: login/form required: False; terms: not stated; updates: salaries mid-October, earnings early January (data last updated 2/23/2026); size: Salaries 2025: 3.39 MB; Earnings 2025: 4.13 MB; ~45,000+ rows per year
- Notes: Static XLSX links on the search page; HEAD confirmed 200. Field names from page help text; verify headers. Host sets Citrix bot cookies but did not block.
- **Loaded: 240,592 records**

### [A] Ohio University (Athens + regional campuses)  (catalog id 129)

- System/publisher: Ohio University
- URL: https://www.ohio.edu/hr/compensation/salary-database
- Download: https://www.ohio.edu/sites/default/files/2026-03/2025%20Annual%20Salary%20W2%20report.xlsx
- Format: XLSX (plus HTML sortable table); years: base salary as of 12/31/2025 (current file only; prior years not linked)
- Coverage: Ohio University; employees: all non-student employees (adjunct/early-retiree faculty show zero salary)
- Fields: name, department, title, base_pay, W-2 earnings (per file name)
- Access: login/form required: False; terms: not stated; updates: annual (spring; last updated March 12, 2026); size: 552 KB
- Notes: File path changes each year (sites/default/files/YYYY-MM/...), so re-scrape landing page for new link. Spreadsheet 'includes further detail' than HTML table.
- **Loaded: 5,096 records**

### [C] 13 Ohio public universities (BGSU, Central State, Cleveland State, Kent State, Miami, Ohio U, Shawnee State, Ohio State, Akron, Cincinnati, Toledo, Wright State, Youngstown State)  (catalog id 130)

- System/publisher: The Buckeye Institute (think tank) Higher Ed Salary database
- URL: https://www.buckeyeinstitute.org/data/higher_ed_salary
- Format: search-form; years: 2011-2022
- Coverage: 13 public universities (not NEOMED, not community colleges); employees: all employees (gross wages)
- Fields: name, school, department, job_title, gross_salary, year
- Access: login/form required: True; terms: not stated; updates: irregular (latest year 2022); size: not stated
- Blocker: Search form only, no bulk export; data stops at 2022.
- Notes: Data obtained by public records requests to each university. UC lacks department 2019-2022; Shawnee lacks job titles 2019, 2021, 2022. Best multi-institution historical source for Ohio, could be worth a records request to Buckeye for the underlying files.

### [C] Ohio public higher education (scope unclear)  (catalog id 131)

- System/publisher: Ohio Checkbook (Ohio Treasurer / Dept of Administrative Services)
- URL: https://checkbook.ohio.gov/Salaries/HigherEdu.aspx
- Download: https://public.tableau.com/views/SalariesHigherEducation/DashboardHigherEducation (Tableau Public, 'Download CSV' in viewer)
- Format: Tableau dashboard; years: unclear; Tableau workbook metadata lastUpdateDate 2022-11-27
- Coverage: unclear (public universities); employees: unclear
- Fields: institution, name, title, pay, year (presumed)
- Access: login/form required: False; terms: not stated; updates: unclear, appears stale; size: not stated
- Blocker: Tableau Public embed; direct CSV URL is behind an AWS WAF CAPTCHA, and the workbook looks stale (2022).
- Notes: Published by profile 'ohiodas'. Could not confirm person-level detail without interacting with the dashboard. Ohio Checkbook also has a Colleges and Universities spending section (expenditures, not pay).

### [C] Miami University, Wright State, Sinclair CC and other Dayton/Butler-area employers  (catalog id 132)

- System/publisher: Dayton Daily News / Journal-News I-Team Payroll Project (news)
- URL: https://www.daytondailynews.com/
- Format: search-form; years: around 2017-2018 editions found
- Coverage: regional public employers incl. Miami University; employees: all
- Fields: name, employer, title, pay
- Access: login/form required: True; terms: not stated (paywalled news site); updates: irregular; size: not stated
- Blocker: Search-only news database, paywall, old.
- Notes: Not inspected in depth.

### [C] Various Ohio universities  (catalog id 133)

- System/publisher: OpenTheBooks (third-party)
- URL: https://www.openthebooks.com/ohio-state-employees/
- Format: HTML/search-form; years: varies
- Coverage: OSU, UC, Miami, BGSU etc. appear in state employee listing (sourced to Ohio Treasurer); employees: all
- Fields: name, employer, title, annual_wages, year
- Access: login/form required: True; terms: site terms restrict reuse; updates: annual; size: not stated
- Blocker: Third-party, paginated search; no bulk download without account.
- Notes: Suggests the Treasurer/Checkbook has university payroll data that is not exposed as a clean download.

**Private institutions / extra:** None found.

**Gaps:** No official multi-institution bulk file. Only Ohio State and Ohio University publish downloadable files. No published person-level pay found for University of Cincinnati, Miami, Kent State, BGSU, Toledo, Akron, Wright State, Cleveland State, Youngstown State, Shawnee State, Central State, NEOMED, or any of the 23 community colleges (all would need Ohio public records requests). Buckeye Institute covers 13 universities but only through 2022 and only via search form.

**State notes:** Rated Ohio Checkbook Tableau as C because the CSV path hit a CAPTCHA wall and I did not interact further. Did not download bulk files (HEAD only). Searched for UC/Miami/Kent/BGSU/Toledo/Akron official salary pages; none found, only H-1B aggregators.

## Pennsylvania (PA)

Systems: Pennsylvania State System of Higher Education (PASSHE, 10 universities), State-related universities (Penn State, Pitt, Temple, Lincoln), Thaddeus Stevens College of Technology (state-owned), Pennsylvania community colleges (15, locally sponsored)  
Best rating: **B**. Records loaded: **800**.

### [B] PASSHE universities (System of Higher Education, ~10,400 employees) and Thaddeus Stevens College of Technology  (catalog id 140)

- System/publisher: PennWATCH (Commonwealth of Pennsylvania, Office of Administration)
- URL: https://pennwatch.pa.gov/Employees/Salaries
- Download: https://pennwatch.pa.gov/Employees/Salaries?SelectedAgency=<agency>&SelectedAsOfDate=<m/15/yyyy> (GET query form; no bulk file found)
- Format: HTML (search results table, GET parameters); years: monthly snapshots 7/15/2012 - 9/15/2026
- Coverage: all PASSHE universities and system office (one agency, 'System of Higher Education'); Thaddeus Stevens; employees: all salaried and wage employees
- Fields: last_name, first_name, agency, position/job_title, annual_salary_or_hourly_rate, as_of_date
- Access: login/form required: True; terms: see PennWATCH Disclaimers page (not reviewed in detail); updates: monthly (15th); size: ~10,400 PASSHE rows per snapshot
- Blocker: No bulk export found; must page through GET search results per agency per month.
- Notes: Separate 'Employee Compensation' report includes other pay (overtime etc.). Search uses plain GET parameters so scraping is straightforward; I did not run a search. Campus is probably not a field, may need title/department parsing. Historically PDF/spreadsheet available on request.

### [B] Penn State University  (catalog id 141)

- System/publisher: State-related universities (Right-to-Know Law Chapter 15 / Act 29 of 2023 reports)
- URL: https://budgetandfinance.psu.edu/public-reports
- Download: https://budgetandfinance.psu.edu/sites/budgetandfinance/files/right_to_know_2024.pdf
- Format: PDF; years: annual; top 25 until FY2023, top 200 from FY2024
- Coverage: Penn State; employees: officers/directors plus 200 highest-paid employees only
- Fields: name, title, base_salary, 990 compensation for officers
- Access: login/form required: False; terms: not stated; updates: annual (late May); size: 3.0 MB (2024 report)
- Blocker: Only top-200 earners, PDF; landing page is behind a Cloudflare challenge.
- Notes: FY2025 report released May 30, 2026 but not found at the analogous URL (right_to_know_2025.pdf 404).

### [B] University of Pittsburgh  (catalog id 142)

- System/publisher: State-related universities (Right-to-Know Law Chapter 15 reports)
- URL: https://www.financeoperations.pitt.edu/right-know-disclosures
- Download: https://www.financeoperations.pitt.edu/sites/default/files/2026-05/FY25 PITT FORM 990 Public Disclosure Filed Copy.pdf
- Format: PDF; years: FY2012-FY2025 (top 25; top 200 from FY2024)
- Coverage: Pitt; employees: officers plus 200 highest-paid
- Fields: name, title, base_salary
- Access: login/form required: False; terms: not stated; updates: annual (May); size: not stated
- Blocker: Top-200 only, PDF tables.
- Notes: Also posts contracts over $5,000.
- **Loaded: 400 records**

### [B] Temple University (and Lincoln University similarly)  (catalog id 143)

- System/publisher: State-related universities (Right-to-Know Law Chapter 15 reports)
- URL: https://www.temple.edu/about/public-information
- Format: PDF; years: annual
- Coverage: Temple; Lincoln posts similar report (URL not found); employees: officers plus 200 highest-paid
- Fields: name, title, base_salary
- Access: login/form required: False; terms: not stated; updates: annual; size: not stated
- Blocker: Top-200 only, PDF.
- Notes: Temple page exists (200); individual PDF links not extracted.
- **Loaded: 400 records**

### [C] PA state employees incl. PASSHE  (catalog id 144)

- System/publisher: OpenTheBooks / PennLive / PublicSource (third-party)
- URL: https://www.openthebooks.com/pennsylvania-state-employees/
- Format: search-form; years: varies
- Coverage: PASSHE (via PennWATCH data); employees: all
- Fields: name, employer, title, pay, year
- Access: login/form required: True; terms: site terms restrict reuse; updates: annual; size: not stated
- Blocker: Third-party search only; same data as PennWATCH.
- Notes: Not inspected in detail.

**Private institutions / extra:** None found. (Penn State, Pitt, Temple, Lincoln are state-related, legally private nonprofits; they publish Form 990 data plus top-200 salary lists under Act 29 of 2023, already recorded as sources.)

**Gaps:** No bulk download anywhere. State-related universities (by far the largest employers) disclose only officers and top 200 earners; full rosters require RTK requests, which they are largely exempt from. No person-level data found for any of the 15 community colleges. PennWATCH covers PASSHE fully but only via paged search. data.pa.gov has no state payroll dataset.

**State notes:** Rated PennWATCH B (GET-based search with HTML table, scrapable) rather than C because the parameters are simple URL query strings; I did not execute a search. Penn State budgetandfinance site returned Cloudflare 403 to scripts; PDF itself returned 200.

## Michigan (MI)

Systems: 15 constitutionally autonomous public universities (no state system): University of Michigan (Ann Arbor, Dearborn, Flint), Michigan State, Wayne State, Western Michigan, Central Michigan, Eastern Michigan, Grand Valley, Oakland, Ferris, Michigan Tech, Northern Michigan, Saginaw Valley, Lake Superior State, Michigan Technological, Michigan community colleges (28, locally governed; Michigan Community College Association)  
Best rating: **B**. Records loaded: **54,659**.

### [B] University of Michigan (Ann Arbor incl. Michigan Medicine, Dearborn, Flint)  (catalog id 84)

- System/publisher: University of Michigan
- URL: https://hr.umich.edu/ (Faculty and Staff Salary Disclosure / Salary Record)
- Download: https://hr.umich.edu/sites/default/files/salary_record_2025.pdf ; prior: https://obp.umich.edu/wp-content/uploads/pubdata/mandatoryreports/salary_disclosure_2024.pdf , https://hr.umich.edu/sites/default/files/salary-disclosure-2023.pdf , .../um-salary-disclosure-2022.pdf
- Format: PDF; years: annual PDFs (as of Nov 1) at least 2020-2025; Deep Blue library archive of Salary Listings from about 2002 to mid-2010s
- Coverage: all three UM campuses; employees: all faculty and staff with appointments (excludes summer teaching/overload pay)
- Fields: name, appointment_title, appointing_department, campus, appointment_fte, full_time_rate (FTR), FTR_basis, general_fund_amount
- Access: login/form required: False; terms: not stated; updates: annual (early-mid December); size: large PDF (~1,000+ pages; size not obtained)
- Blocker: PDF only and hr.umich.edu / obp.umich.edu / deepblue return Cloudflare 403 to scripted requests; needs a real browser or manual download.
- Notes: Field list from search snippets of the Deep Blue records and report notes. 2025 report dated 12/09/2025.
- **Loaded: 54,659 records**

### [C] University of Michigan (also EMU, WMU, MSU, OSU, Purdue, Iowa, Minnesota sister sites)  (catalog id 85)

- System/publisher: umsalary.info (third-party, built from UM disclosures)
- URL: https://www.umsalary.info/
- Format: search-form (HTML results); years: 2002-03 to 2025-26
- Coverage: University of Michigan; sister sites for EMU and WMU; employees: all in UM salary disclosure
- Fields: name, title, department, campus, fte, full_time_rate, general_fund_amount, year
- Access: login/form required: True; terms: not stated; updates: annual; size: not stated
- Blocker: Search-only (last name required), third-party; no bulk download.
- Notes: Useful as a cleaned historical cross-check; the official PDFs are the primary source.

### [B] Western Michigan University  (catalog id 86)

- System/publisher: Western Michigan University
- URL: https://wmich.edu/
- Download: https://files.wmich.edu/s3fs-public/attachments/u335/2023/EMPLOYEE_LIST_AS_OF_10_6_23.pdf
- Format: PDF; years: as of 10/6/2023 (newer edition not found)
- Coverage: WMU; employees: faculty and staff
- Fields: name, position_title, department, appointment_period, fte, salary
- Access: login/form required: False; terms: not stated; updates: unknown (appears annual, Oct snapshot); size: 456 KB
- Blocker: PDF only; latest found is 2023 and no landing page located.
- Notes: Title 'Salary Detail for Faculty and Staff'. Name presence assumed from report type; verify.

### [C] Michigan State University  (catalog id 87)

- System/publisher: Michigan State University
- URL: https://libguides.lib.msu.edu/facultysalaries
- Format: PDF/online (restricted); years: FY13-FY26 online (MSU users only); print in library; 2012-13 online for all users
- Coverage: MSU; employees: faculty, academic staff, regular nonacademic staff (as of Oct 1)
- Fields: name, title, department, salary
- Access: login/form required: True; terms: use limited to MSU faculty, staff and students; updates: annual; size: not stated
- Blocker: Online editions require MSU NetID login (KC portal needs 2FA); public gets print copy only.
- Notes: Public would need a Michigan FOIA request.

### [C] Michigan public universities (various)  (catalog id 88)

- System/publisher: OpenPayrolls / OpenTheBooks / MLive (third-party)
- URL: https://openpayrolls.com/
- Format: HTML/search-form; years: varies to 2025
- Coverage: MSU, WMU, UM and others; employees: all
- Fields: name, employer, title, pay, year
- Access: login/form required: True; terms: site terms restrict reuse; updates: annual; size: not stated
- Blocker: Third-party per-person pages, no bulk download.
- Notes: MLive/Ann Arbor News has a 2025 UM salary database (search).

**Private institutions / extra:** None found.

**Gaps:** No statewide source; Michigan universities are constitutionally autonomous and not on state payroll (state transparency sites exclude them). Only UM publishes a complete public salary record (PDF). No person-level data found for Wayne State, CMU, EMU (except third-party), GVSU, Oakland, Ferris, Michigan Tech, NMU, SVSU, LSSU, or any community college. State School Aid Act only requires posting the president's salary.

**State notes:** UM sites sit behind Cloudflare and returned 403 even to HEAD; recorded URLs from search results. Did not attempt to bypass. Rated UM B (PDF) despite the bot wall since a browser download works.

## Minnesota (MN)

Systems: Minnesota State (formerly MnSCU: 7 state universities + 26 community and technical colleges), University of Minnesota System (Twin Cities, Duluth, Morris, Crookston, Rochester)  
Best rating: **A**. Records loaded: **313,601**.

### [A] All Minnesota State colleges and universities (plus all other executive/judicial state agencies)  (catalog id 89)

- System/publisher: Minnesota Management and Budget (MMB) state employee payroll data
- URL: https://mn.gov/mmb/transparency-mn/payrolldata.jsp
- Download: https://mn.gov/mmb-stat/transparency/employee-salary-data/fiscal-year-2026.xlsx (pattern fiscal-year-YYYY.xlsx, FY2011-FY2026)
- Format: XLSX (two tables plus metadata sheet, need joining); years: FY2011-FY2026
- Coverage: all 33 Minnesota State institutions and system office; excludes University of Minnesota; employees: all paid during the fiscal year (full-time, part-time, seasonal, student workers on state payroll)
- Fields: record_nbr, employee_name, agency_name, department/campus, job_title, class_code, employment_status, full/part-time, hire_date, regular_wages, overtime_wages, other_wages, total_wages, compensation_rate, rate_unit, location, fiscal_year (48 public data elements in total)
- Access: login/form required: False; terms: not stated (public data under Minnesota Government Data Practices Act); updates: annual (FY2026 file posted 2026-09-09); size: 16.3 MB (FY2026); page says just under 22 MB
- Notes: Field names approximated from the 48-element description; check metadata sheet. Filter agency to Minnesota State. Also an annual Executive Branch Total Compensation Report (calendar year, includes benefits).
- **Loaded: 313,601 records**

### [C] University of Minnesota (all campuses)  (catalog id 90)

- System/publisher: University of Minnesota
- URL: https://askmn.libanswers.com/umtc_faq/faq/341039
- Format: on request (Data Practices request via Libraries or Institutional Data and Research); years: on request
- Coverage: University of Minnesota; employees: all
- Fields: name, title, department, salary
- Access: login/form required: True; terms: Minnesota Government Data Practices Act; updates: on request; size: not stated
- Blocker: No published file; Reporting Center needs UMN login; outsiders must request (Libraries handle up to 3 lookups/day, larger to IDR).
- Notes: Not on state payroll, so absent from MMB files.

### [C] University of Minnesota  (catalog id 91)

- System/publisher: Third-party (umsalary.info 'Minnesota Salary' sister site, OpenPayrolls)
- URL: https://openpayrolls.com/
- Format: search-form; years: around 2020-2025 on OpenPayrolls
- Coverage: University of Minnesota; employees: all
- Fields: name, title, pay, year
- Access: login/form required: True; terms: site terms restrict reuse; updates: annual; size: not stated
- Blocker: Third-party search only.
- Notes: Shows UMN data has been released via data requests; a bulk request to UMN could get the same.

**Private institutions / extra:** None found.

**Gaps:** University of Minnesota (largest public employer in higher ed) has no published person-level salary file; must be requested under the Data Practices Act.

**State notes:** Did not download the MMB XLSX (HEAD only). Considered the MMB source to cover all community/technical colleges and state universities, since Minnesota State is on the state payroll (SEMA4).

## Indiana (IN)

Systems: Indiana University System, Purdue University System, Ball State, Indiana State, University of Southern Indiana, Vincennes University, Ivy Tech Community College (single statewide community college system)  
Best rating: **B**. Records loaded: **1,679,632**.

### [B] State universities (IU, Purdue, Ball State, Indiana State, USI, Vincennes, Ivy Tech) and all local units  (catalog id 63)

- System/publisher: Indiana Gateway for Government Units (DLGF / IU Indiana Business Research Center) - Form 100R Employee Compensation
- URL: https://gateway.ifionline.org/report_builder/Default2.aspx?rptType=employComp&rptVer=a
- Download: Report builder export (CSV/Excel/PDF) per unit and year via ASP.NET report viewer; no bulk file on https://gateway.ifionline.org/public/download.aspx
- Format: search-form with CSV/Excel export; years: 2012-2025
- Coverage: all state universities and colleges filing Form 100R (per Gateway: state government, state universities, state boards and commissions, local units); employees: all employees (Form 100R certified report)
- Fields: unit, employee_last_name, employee_first_name, position/duties, total_compensation, year
- Access: login/form required: True; terms: User must agree per IC 5-14-3-3(f) that names/addresses obtained will not be used for commercial or political purposes; updates: annual (100R filed each January for prior calendar year); size: not stated
- Blocker: No bulk download; per-unit report export via ASP.NET form after accepting a non-commercial-use agreement.
- Notes: Official statewide source covering every public institution. PFW library FAQ confirms Purdue is listed and the export icon gives CSV/Excel. Indiana Transparency Portal points to Gateway for higher-ed salaries. Did not run the report builder. Non-commercial-use clause may restrict how loaded data can be used.
- **Loaded: 1,679,632 records**

### [D] State agencies only (not universities)  (catalog id 64)

- System/publisher: Indiana Transparency Portal (State Comptroller)
- URL: https://www.in.gov/itp/state-employees/employee-salaries/
- Format: search-form; years: current
- Coverage: none of the universities (they are not paid through the State Comptroller); employees: state agency employees
- Fields: agency, name, title, annualized_salary_or_hourly_rate
- Access: login/form required: True; terms: not stated; updates: periodic; size: not stated
- Notes: Recorded to show it excludes higher ed; portal itself redirects users to Gateway for higher education salaries.

### [C] Indiana University, Purdue (and others)  (catalog id 65)

- System/publisher: Third-party (OpenPayrolls, umsalary.info 'Purdue Salary' sister site)
- URL: https://openpayrolls.com/
- Format: search-form; years: varies to 2025
- Coverage: IU, Purdue; employees: all
- Fields: name, employer, title, pay, year
- Access: login/form required: True; terms: site terms restrict reuse; updates: annual; size: not stated
- Blocker: Third-party search only; derived from Gateway 100R data.
- Notes: Not inspected in depth.

**Private institutions / extra:** None found.

**Gaps:** No bulk file; Gateway requires per-unit exports with a non-commercial-use agreement. No university-published salary lists found for IU, Purdue, Ball State, ISU, USI, Vincennes, or Ivy Tech. 100R gives total compensation only, not base vs other pay.

**State notes:** Rated Gateway B (not A) because exports require the report-builder form and a terms acceptance; it is otherwise the single most complete source across my six states. Assumed Ivy Tech and Vincennes file 100R as state educational institutions (not verified).

## Alabama (AL)

Systems: University of Alabama System, Auburn University System, Alabama Community College System (ACCS), Independent publics: Alabama A&M, Alabama State, Athens State, Jacksonville State, Troy, Montevallo, North Alabama, South Alabama, West Alabama  
Best rating: **C**. Records loaded: **0**.

### [C] All Alabama public universities and community colleges (aggregator)  (catalog id 5)

- System/publisher: multiple
- URL: https://www.openthebooks.com/alabama-state-employees/
- Format: search-form / HTML; years: 2016-2025 (filter); site reports ~1.09M salary rows
- Coverage: UA, UAB, UAH, Auburn, South Alabama, Troy, AAMU, ASU, UNA and many ACCS community colleges (Calhoun, Gadsden State, Jefferson State, Snead State, Bevill State, etc.); employees: all (as received by OpenTheBooks via records requests / state comptroller)
- Fields: year, employer, name, title, annual_wages, source
- Access: login/form required: True; terms: Terms & Conditions linked; not reviewed; updates: annual (not stated); size: ~1,089,094 rows reported; only top 10,000 browsable
- Blocker: Search-only, browsing capped at top 10,000 rows; no bulk download without contacting OpenTheBooks
- Notes: Best single coverage found for Alabama. Source column shows the paying entity (university or 'Alabama State Comptroller'), suggesting data obtained from each university plus state payroll. Third-party, not official.

### [C] University of Alabama and others (aggregator)  (catalog id 6)

- System/publisher: University of Alabama System
- URL: https://openpayrolls.com/
- Format: HTML (one page per employee); years: approx. 2010-2025
- Coverage: University of Alabama (per-employee profile pages seen); others likely; employees: all
- Fields: name, title, employer, year, pay
- Access: login/form required: False; terms: not stated; updates: not stated; size: not stated
- Blocker: Third-party per-person profile pages only; no bulk file; provenance unclear
- Notes: Repackaged records; useful only for spot checks.

### [D] Alabama 4-year public universities (13 institutional 'Open Alabama' expenditure sites)  (catalog id 7)

- System/publisher: multiple
- URL: https://www.ache.edu/index.php/4-year-institutions-monthly-expenditures/
- Format: search-form / HTML per institution; years: varies
- Coverage: AAMU, ASU, Athens State, Auburn/AUM, JSU, Troy, Montevallo, UA, UAB, UAH, UNA, South Alabama, UWA; employees: none - vendor expenditures only
- Fields: payee, amount, date, category
- Access: login/form required: True; terms: not stated; updates: monthly; size: not stated
- Blocker: Vendor checkbook registers under Act 2010-?? (Open Alabama); no person-level payroll
- Notes: Checked open.ua.edu (expenditures only) and Alabama State University page (alasu.edu .../payroll.php returns a 155MB HTML page containing a vendor expenditure table, not salaries). Recorded so these are not re-checked.

### [D] Alabama Commission on Higher Education (ACHE) faculty wages  (catalog id 8)

- System/publisher: statewide
- URL: https://www.ache.edu/wp-content/IPEDS/Salaries/Faculty-Wages.pdf
- Download: https://www.ache.edu/wp-content/IPEDS/Salaries/Faculty-Wages.pdf
- Format: PDF; years: 2021-22, 2024-25 editions seen
- Coverage: all public and private institutions; employees: faculty, aggregate averages by rank (not person-level)
- Fields: institution, rank, average_salary
- Access: login/form required: False; terms: not stated; updates: annual; size: small PDF
- Blocker: Aggregate only (IPEDS-derived), no names
- Notes: Not person-level; listed for context only.

### [D] Alabama Community College System  (catalog id 9)

- System/publisher: ACCS
- URL: https://www.accs.edu/about-accs/financial-disclosure/
- Format: unknown; years: unknown
- Coverage: ACCS colleges; employees: unknown
- Fields: 
- Access: login/form required: False; terms: not stated; updates: unknown; size: unknown
- Blocker: Site returned HTTP 403 to automated requests; no person-level pay found via search
- Notes: ACCS publishes salary schedules (pay scales) rather than individual pay. Recheck manually in a browser.

**Private institutions / extra:** None found beyond IRS 990s.

**Gaps:** No official person-level salary publication found for any Alabama public university or ACCS. open.alabama.gov has spending/contracts but no payroll. Universities are outside state payroll, so data would require Alabama Open Records Act requests (or licensing OpenTheBooks data).

**State notes:** Rated OpenTheBooks C because browsing is capped and needs search; it is the only broad coverage found. Did not attempt the Alabama State Comptroller payroll since no public payroll portal was found.

## Alaska (AK)

Systems: University of Alaska System (UAF, UAA incl. community campuses such as Prince William Sound College, UAS)  
Best rating: **C**. Records loaded: **0**.

### [C] University of Alaska System  (catalog id 1)

- System/publisher: University of Alaska
- URL: https://www.alaska.edu/news/system/2026-notice-ua-salaries-public-data.php
- Format: records request (no online file); years: on request (current); semi-annual notices 2021-2026
- Coverage: UAF, UAA, UAS, System Office; employees: all except student employees
- Fields: department, name, ft_pt_status, bargaining_unit, employee_class, job_title, compensation, staff_benefit_rate, previous_positions, employment_dates
- Access: login/form required: True; terms: Alaska Public Records Act (AS 40.25) / AS 39.25.080; Regents' policy; updates: on request; UA notifies employees semi-annually; size: not stated
- Blocker: Not published online; requires a public records request to UA
- Notes: UA confirms the full payroll with names and compensation is public and released routinely to requesters, so a request is likely to yield a clean bulk file. Good candidate for a records request.

### [C] University of Alaska Fairbanks (UAF Sun Star student newspaper database)  (catalog id 2)

- System/publisher: University of Alaska
- URL: https://uaf.edu/news/archives/news-archives-2010-2021/ua-salary-information-released-to-sun-star.php
- Format: search-form / HTML; years: c. 2011-2012
- Coverage: UAF (later UA-wide release); employees: all non-student
- Fields: name, position, department, campus, gross_salary
- Access: login/form required: True; terms: not stated; updates: one-off; size: not stated
- Blocker: Old (2011-12) student-newspaper searchable database at uafsunstar.com; could not confirm it is still online
- Notes: Historic only.

### [C] State of Alaska executive compensation report (AS 37.05.210)  (catalog id 3)

- System/publisher: State of Alaska, Division of Finance
- URL: https://doa.alaska.gov/dof/reports/transparency.html
- Format: PDF (per search snippets); years: annual calendar-year reports (published end of January)
- Coverage: University of Alaska president, vice-president, campus chancellors (plus state executives); employees: UA top executives only (~5-6 people)
- Fields: name, title, compensation, travel
- Access: login/form required: False; terms: not stated; updates: annual; size: small
- Blocker: Covers only a handful of UA executives; doa.alaska.gov returned HTTP 403 to automated fetch so format/years not verified
- Notes: Checkbook Online (doa.alaska.gov/dof/reports/ckbkonline.html) is vendor payments >= $1,000 in Excel/PDF, not payroll; UA is not on the state checkbook payroll.

### [C] University of Alaska (aggregator)  (catalog id 4)

- System/publisher: University of Alaska
- URL: https://openpayrolls.com/
- Format: HTML (one page per employee); years: approx. 2017-2023 seen
- Coverage: UAA, UAF, UAS employees (profile pages seen, e.g. UAA faculty 2023); employees: all (as obtained)
- Fields: name, title, employer, year, pay
- Access: login/form required: False; terms: not stated; updates: not stated; size: not stated
- Blocker: Third-party per-person pages; no bulk download; provenance unclear
- Notes: Suggests UA records-request data has been obtained and republished by third parties.

**Private institutions / extra:** None found (Alaska Pacific University publishes only IRS 990). Ilisagvik College is a tribal college; not researched.

**Gaps:** No online person-level pay publication by University of Alaska; state open-data/checkbook does not include UA payroll. Full data available only via public records request.

**State notes:** Treated Alaska community colleges as part of UA (UAA community campuses). doa.alaska.gov blocked automated fetch (403), so executive compensation report details come from search snippets.

## Arizona (AZ)

Systems: Arizona Board of Regents (ASU, University of Arizona, NAU), Arizona community college districts (Maricopa County CCD, Pima CCD, and ~8 other county districts)  
Best rating: **A**. Records loaded: **234,227**.

### [A] Arizona State University  (catalog id 15)

- System/publisher: Arizona Board of Regents
- URL: https://www.statepress.com/article/2025/11/salary-database-2024
- Download: https://raw.githubusercontent.com/TheStatePress/SalaryList/master/data-csv/2025.csv (also 2018.csv ... 2024 revised.csv; list via https://api.github.com/repos/thestatepress/SalaryList/contents/data-csv)
- Format: CSV; years: calendar years 2018-2025 (one CSV per year; 2018 also XLSX; '2023 revised' and '2024 revised' files)
- Coverage: ASU (all campuses); employees: all (~19,500 in 2024; students likely excluded)
- Fields: calendar_year, full_name, job_description, department_description, salary, fte
- Access: login/form required: False; terms: not stated (student newspaper; public records obtained from ASU); updates: annual (State Press records request each fall); size: 0.9-2.8 MB per year file
- Notes: Public GitHub repo behind the State Press embedded viewer (thestatepress.github.io/SalaryList). Header names vary slightly by year (e.g. 2018 'Jobcode Descr','Fte' as fraction; 2025 salary formatted as '$5,800,000' and FTE as 100). Base salary only, no other/total pay.
- **Loaded: 127,147 records**

### [A] University of Arizona  (catalog id 16)

- System/publisher: Arizona Board of Regents
- URL: https://azluminaria.org/2025/11/21/university-of-arizona-searchable-salary-database-for-2023-2024/
- Download: https://flo.uri.sh/visualisation/16806493/embed (Flourish embed; full dataset is embedded as JSON in the page variable _Flourish_data)
- Format: JSON (embedded in HTML); years: FY2019-FY2026
- Coverage: University of Arizona (all units); employees: all (per UA records-request release)
- Fields: fiscal_year, name, primary_title, department, annual_salary_at_fte, ft_pt, fte, full_fte_salary, hourly_pay_rate, original_hire_date
- Access: login/form required: False; terms: not stated (news organization; data compiled by University of Arizona via public records request); updates: annual (Arizona Luminaria, ~Nov/Dec); size: ~15 MB embed page; 107,080 rows (12.5k-14.8k per year)
- Notes: One HTTP request yields all 8 years as clean JSON rows; verified row counts by year. Third-party (nonprofit newsroom), not official. Daily Wildcat also published earlier UA salary databases (2016-17, 2017-18, 2019-20) and Arizona Daily Star/tucson.com had a 2016 database.
- **Loaded: 107,080 records**

### [C] Arizona public employees incl. ASU, UA, NAU and community colleges (Arizona Republic / AZ Data Central)  (catalog id 17)

- System/publisher: multiple
- URL: http://www.azcentral.com/pages/interactives/news/local/arizona-data/arizona-government-salary-database/
- Format: search-form; years: 2018 free; 2019+ subscriber-only
- Coverage: ASU, UA, NAU, community college districts, state agencies; employees: all
- Fields: name, employer, title, salary, year
- Access: login/form required: True; terms: not stated; updates: annual (historically); size: ~154,000 state employees (per Inside Higher Ed)
- Blocker: Search-only and paywalled (subscriber) for recent years
- Notes: Only known source naming NAU employees beyond aggregators.

### [C] Arizona public employees incl. universities and community colleges (aggregator)  (catalog id 18)

- System/publisher: multiple
- URL: https://www.openthebooks.com/arizona-state-employees/
- Format: search-form / HTML; years: approx. 2017-2024
- Coverage: ASU, UA, NAU, Maricopa CCD, Pima CC and others; employees: all (as obtained)
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: Terms & Conditions linked; not reviewed; updates: annual (not stated); size: 666,236 rows reported; only top 10,000 browsable
- Blocker: Search-only; browsing capped at top 10,000 rows; no bulk download
- Notes: Best available coverage for NAU and community college districts.

### [D] Northern Arizona University  (catalog id 19)

- System/publisher: Arizona Board of Regents
- URL: https://in.nau.edu/budget/reports/
- Format: PDF; years: FY22-FY28 budget documents
- Coverage: NAU; employees: none person-level
- Fields: cost_center, personal_services_total, fte
- Access: login/form required: False; terms: not stated; updates: annual; size: FY26 budget book 7.2 MB / 61 pages; FY24 BUDDIES 1 MB / 190 pages
- Blocker: Budget books are cost-center level only (checked FY26 book and FY24 BUDDIES); no names
- Notes: A 2017 State Press editorial said NAU published all salaries in budget documents; current documents no longer do.

### [D] Arizona Board of Regents personnel report  (catalog id 20)

- System/publisher: Arizona Board of Regents
- URL: https://azregents.edu/sites/default/files/reports/2025-Personnel-Report-r1.pdf
- Download: https://azregents.edu/sites/default/files/reports/2025-Personnel-Report-r1.pdf
- Format: PDF; years: FY2025 (annual)
- Coverage: ASU, UA, NAU; employees: aggregate (turnover, average compensation)
- Fields: institution, employee_group, average_salary, turnover
- Access: login/form required: False; terms: not stated; updates: annual; size: not checked
- Blocker: Aggregate only, no person-level data
- Notes: Context only.

**Private institutions / extra:** None found beyond IRS 990s (Grand Canyon University is for-profit/now nonprofit; no extra pay data seen).

**Gaps:** No official (university-hosted) person-level salary files for ASU, UA or NAU; both A sources are newsroom republications of records-request data. NAU has no free person-level source. Community college districts (Maricopa, Pima, etc.) have no person-level source other than OpenTheBooks/azcentral.

**State notes:** Rated the State Press GitHub CSVs and Arizona Luminaria Flourish JSON as A because each is a clean bulk file reachable without login; flagged as third-party. Peeked only CSV headers (byte range) and counted Flourish rows; no large downloads.

## Arkansas (AR)

Systems: University of Arkansas System, Arkansas State University System, Arkansas Tech University, University of Central Arkansas, Henderson State (now ASU System), Southern Arkansas University System, Arkansas community colleges (independent districts, e.g. NWACC, Pulaski Tech is in UA System)  
Best rating: **B**. Records loaded: **15,432**.

### [B] All Arkansas public universities and colleges - Administrator's Compensation Survey  (catalog id 10)

- System/publisher: Arkansas Division of Higher Education (ADHE)
- URL: https://adhe.edu/data-publications/administrator%E2%80%99s-compensation-survey
- Download: https://adhe.edu/File/Administrator's%20Compensation%20Survey%20FY26v2%28PAGE%20NUMBERS%29.pdf (one PDF per fiscal year, FY10-FY26, same /File/ path)
- Format: PDF (one structured form page per employee); years: FY2010-FY2026
- Coverage: all public universities and two-year colleges (sections: Universities, then colleges); employees: employees earning $100,000 or more (administrators, coaches, faculty)
- Fields: fiscal_year, institution_fice, institution_abbrev, employee_id, first_name, last_name, position_title, salary_within_line_item_max, state_funds_above_lim, uams_professional_income, other_source_salary, total_base_salary_public_private, retirement_match, health_insurance, life_insurance, social_security, car_allowance, housing, deferred_comp, bonuses, other_compensation_1_14, total_compensation
- Access: login/form required: False; terms: not stated; updates: annual; size: FY26: 27.4 MB, 1,600 pages
- Blocker: PDF form-per-person layout; text extracts but field values are separated from labels and need positional parsing; only >= $100k earners
- Notes: Very rich compensation detail (public vs private funds, bonuses, car/housing) for high earners; 17 years of history. Verified FY26 contains names, titles and amounts via pypdf text extraction.
- **Loaded: 15,432 records**

### [D] Arkansas state employees (Transparency Arkansas, DFA)  (catalog id 11)

- System/publisher: State of Arkansas
- URL: https://transparency.arkansas.gov/employee_compensation.php?tab=byagency
- Download: https://transparency.arkansas.gov/ajax.php?do:GetTableData=1&report=employeecompensation&tab=byagency&fiscal_year=<FY> (DataTables JSON); CSV/XLS export links ?do:export_csv&report=employeecompensation&...&type=csv
- Format: JSON (DataTables endpoint) / CSV export; years: FY2016-current
- Coverage: state agencies only incl. Department of Higher Education staff; NO universities or colleges; employees: state agency employees
- Fields: fiscal_year, agency, pay_class, classification, position_number, title, name, hire_date, grade, gender, race, pay
- Access: login/form required: False; terms: not stated; updates: monthly; size: 120 agencies
- Blocker: Does not include higher-education institutions (verified agency list for current FY; only ADHE, Dept of Education, Career Education)
- Notes: Recorded so it isn't re-checked; universities run their own payroll. CSV export returned HTTP 202 with empty body (async) to curl.

### [C] Arkansas public universities and colleges (Arkansas Democrat-Gazette Right2Know)  (catalog id 12)

- System/publisher: multiple
- URL: https://www.arkansasonline.com/right2know/statesalaries2010/
- Format: search-form; years: 2010-2011 (higher ed); 2018 state employee database at https://www.arkansasonline.com/right2know/state/ (above-average earners only)
- Coverage: public universities and colleges (2010-11 FOIA collection); employees: all (2010-11); > $40,530 (2018)
- Fields: name, employer, title, salary
- Access: login/form required: True; terms: not stated; updates: discontinued; size: not stated
- Blocker: Search-only and stale (2010-11); 2018 database unclear whether it includes higher ed
- Notes: Historic only.

### [C] Arkansas public institutions (aggregator)  (catalog id 13)

- System/publisher: multiple
- URL: https://openpayrolls.com/state/arkansas/2026
- Format: HTML; years: 2025-2026 seen
- Coverage: unclear whether universities are included; employees: unknown
- Fields: name, title, employer, pay
- Access: login/form required: False; terms: not stated; updates: not stated; size: not stated
- Blocker: Third-party, per-person pages, provenance and higher-ed coverage unclear
- Notes: Likely republishes the Transparency Arkansas state-agency data.

### [D] Arkansas public institutions expenditure websites (Ark. Code 6-61-137)  (catalog id 14)

- System/publisher: multiple
- URL: https://adhe.edu/data-publications/colleges--universities
- Format: HTML per institution; years: monthly, by fiscal year
- Coverage: all public universities and colleges; employees: none (vendor expenditures)
- Fields: payee, amount, date
- Access: login/form required: False; terms: not stated; updates: monthly; size: not stated
- Blocker: Expenditure checkbooks, not payroll
- Notes: NWACC site (api.nwacc.edu/expenditures) refused connection.

**Private institutions / extra:** Private institutions do not appear in the ADHE compensation survey (public only); none found.

**Gaps:** No all-employee person-level pay file for any Arkansas public university or college; only the ADHE >= $100k survey. State transparency payroll excludes higher ed. Full rosters require Arkansas FOIA requests to each institution.

**State notes:** Downloaded the FY26 ADHE survey PDF temporarily (27 MB) to verify structure, then deleted it. Rated it B rather than A because it's PDF and limited to high earners.

## Colorado (CO)

Systems: University of Colorado System, Colorado State University System (Fort Collins, Pueblo, Global), Colorado Community College System (CCCS), Independent publics: Metropolitan State University of Denver, University of Northern Colorado, Colorado School of Mines, Colorado Mesa, Western Colorado, Fort Lewis, Adams State  
Best rating: **B**. Records loaded: **0**.

### [B] University of Colorado (all campuses) - Personnel roster PDF  (catalog id 25)

- System/publisher: University of Colorado System
- URL: https://www.cu.edu/budgetpolicy/cu-data
- Download: https://www.cu.edu/doc/fy25-personnel-cu-roster-all-campusespdf
- Format: PDF (420 pages, clean tabular text); years: FY2024-25 (snapshot 11/1/2024); earlier years likely under similar /doc/ paths
- Coverage: CU Boulder, CU Denver, CU Anschutz, UCCS, System Administration; employees: all except temporary, student and part-time retiree employees
- Fields: fiscal_year, campus, roster_id, employee_record, department_group, department_group_detail, department_name, job_family, job_title, full_time_pct, line_total_annual_base
- Access: login/form required: False; terms: not stated; updates: annual; size: 8.6 MB; 31,775 rows / 27,704 unique employees
- Blocker: PDF and NO employee names (anonymized roster ID only)
- Notes: Person-level but de-identified; pay is base only (no bonuses/allowances). Text extracts cleanly with pypdf, one row per line. The companion online 'CU Salary Database' (https://www.cu.edu/budget/cu-salary-database, FY2025-26, updated 4/1/2026) is the same data in a JS viewer; no data URL was found in page source.

### [C] Colorado State University (Fort Collins) - Compensation Report  (catalog id 26)

- System/publisher: Colorado State University System
- URL: https://www.ir.colostate.edu/compensation-report/
- Format: unknown (likely dashboard); years: unknown
- Coverage: CSU Fort Collins; employees: unknown (per CSU, online data omits names and gender)
- Fields: 
- Access: login/form required: False; terms: not stated; updates: unknown; size: unknown
- Blocker: Cloudflare returns 403 to scripted requests; page content not visible without JS; CSU says names are excluded online (names only in a printed analysis at Morgan Library)
- Notes: Fort Collins Coloradoan has published a CSU salary database in its Data Central (without names per CSU letter). Recheck in a browser.

### [D] CSU-Pueblo budget documents  (catalog id 27)

- System/publisher: Colorado State University System
- URL: https://www.csupueblo.edu/office-of-financial-management/
- Download: https://www.csupueblo.edu/office-of-financial-management/_doc/egbudgetfy26.pdf
- Format: PDF; years: FY25, FY26
- Coverage: CSU-Pueblo; employees: none person-level
- Fields: department, account, budget
- Access: login/form required: False; terms: not stated; updates: annual; size: 1.3 MB, 71 pages
- Blocker: Account-level budget only, no names
- Notes: Older CSU-Pueblo 'Staffing Pattern' publications (Colorado State Publications Library, spl.cde.state.co.us/artemis/ucspserials/...) listed named employees with base pay (e.g. 2015, 2020) - historic PDFs, possibly B for history.

### [C] Colorado state publications library - historic personnel rosters / staffing patterns  (catalog id 28)

- System/publisher: multiple
- URL: https://spl.cde.state.co.us/artemis/ucspserials/ucsp112internet/ucsp1122020internet.pdf
- Download: https://spl.cde.state.co.us/artemis/ (serial PDFs per institution/year, e.g. ucsp1122015internet.pdf, uccs1102014internet.pdf)
- Format: PDF; years: various, c. 2007-2020
- Coverage: CSU-Pueblo, UCCS, others; employees: all (some editions include names)
- Fields: name (some years), position, department, base_pay
- Access: login/form required: False; terms: not stated; updates: irregular / discontinued; size: not checked
- Blocker: Scattered historic PDFs of varying layout; not verified which include names
- Notes: Identified via Colorado Virtual Library guide; not opened.

### [D] Colorado state employees (Colorado Politics tool / TOP)  (catalog id 29)

- System/publisher: State of Colorado
- URL: https://www.coloradopolitics.com/2018/03/12/colorado-politics-new-tool-allows-users-to-see-how-much-top-earners-in-colorado-government-make
- Format: search-form; years: Nov 2017
- Coverage: state agencies only; universities and colleges excluded (own payroll); employees: state employees > $90k
- Fields: name, department, title, salary
- Access: login/form required: False; terms: not stated; updates: one-off; size: not stated
- Blocker: Excludes higher education
- Notes: data.colorado.gov has no employee salary datasets (searched Socrata catalog for 'salary' and 'employee').

**Private institutions / extra:** None found beyond IRS 990s (University of Denver, Colorado College, Regis).

**Gaps:** No named person-level salary data officially published by any Colorado public institution (CU roster is de-identified; CSU omits names online). Nothing found for CCCS, MSU Denver (personnel budgeting page now 403; archive inaccessible), UNC, Mines, Mesa, Western, Fort Lewis, Adams State. Named data requires CORA requests.

**State notes:** Rated CU roster B despite lacking names because it is all-employee, person-level and cleanly parseable. MSU Denver once had a 'personnel budgeting' page (archived 2021) of unknown content. Shared scratchpad venv was deleted mid-run by another process; used a private folder w_ak8.

## Connecticut (CT)

Systems: University of Connecticut (incl. UConn Health), Connecticut State Colleges & Universities (CSCU, Board of Regents): Central, Eastern, Southern, Western CSU, CT State Community College (12 campuses), Charter Oak State College  
Best rating: **A**. Records loaded: **979,441**.

### [A] State of Connecticut payroll (includes UConn, UConn Health, CSCU)  (catalog id 30)

- System/publisher: CT Office of the State Comptroller (OpenPayroll)
- URL: https://data.ct.gov/Government/State-Employee-Payroll-Data-Calendar-Year-2015-thr/9m78-yc88
- Download: https://data.ct.gov/api/views/9m78-yc88/rows.csv?accessType=DOWNLOAD (SODA API: https://data.ct.gov/resource/9m78-yc88.json)
- Format: API (Socrata SODA) / CSV; years: calendar years 2015-present (min calendar_year value 2010; latest check date 2026-10-16)
- Coverage: University of Connecticut, UConn Health Center, Connecticut Board of Regents (department field splits Central/Eastern/Southern/Western CSU, CSCC campuses Asnuntuck, Capital, Gateway, Housatonic, Manchester, Middlesex, Naugatuck Valley, Northwestern, Norwalk, Quinebaug Valley, Three Rivers, Tunxis, CSCU System Office, Board of State Academic Awards/Charter Oak), Office of Higher Education; employees: all paid employees
- Fields: pyrl_fiscal_yr, calendar_year, deptid, emplid_empl_rcd, first_name, middle_initial, last_name, name_suffix, check, check_dt, chk_option, chk_status, annual_rate, bi_weekly_comp_rate, other, fringe, overtime, salaries_wages, fringe_amt_no_retire, sers_amount, arp_amount, teachers_amount, judges_amount, tot_gross, job_cd_descr, ee_class_descr, job_indicator, full_part, orig_hire, term_date, city, postal, state, union_descr, agency, department
- Access: login/form required: False; terms: Public Domain (dataset license); updates: bi-weekly (each pay period); size: ~29.95 million rows (one row per paycheck); 2025 alone: UConn 343,397, UConn Health 156,755, Board of Regents 304,976 rows
- Notes: Check-level rows; aggregate by emplid_empl_rcd + calendar_year for annual pay. Use SODA $where on agency to pull only higher-ed (avoid full 30M-row CSV). Powers openpayroll.ct.gov. Older catalog id virr-yb6n now returns 'authentication_required' - use 9m78-yc88.
- **Loaded: 979,441 records**

### [A] State of Connecticut payroll FY2010-2014 (includes UConn, CSUs, community colleges)  (catalog id 31)

- System/publisher: CT Office of the State Comptroller
- URL: https://data.ct.gov/d/ajs4-6pgz
- Download: https://data.ct.gov/api/views/ajs4-6pgz/rows.csv?accessType=DOWNLOAD
- Format: API (Socrata) / CSV; years: FY2010-FY2014
- Coverage: all state agencies incl. higher-ed (pre-CSCU-merger agency names); employees: all
- Fields: fiscal_year, agency, agency_description, department, employee_name, job_description, account_description, earnings
- Access: login/form required: False; terms: not stated in metadata checked; updates: static (historic); size: 434,303 rows
- Notes: Historic complement; earnings broken out by account description (pay type).

### [A] Connecticut OpenPayroll web app  (catalog id 32)

- System/publisher: CT Office of the State Comptroller
- URL: https://openpayroll.ct.gov/
- Format: HTML app (Socrata OpenPayroll); years: 2015-present
- Coverage: same as 9m78-yc88; employees: all
- Fields: name, agency, department, job, annual_rate, overtime, fringe, gross
- Access: login/form required: False; terms: not stated; updates: bi-weekly; size: n/a
- Notes: Front end only; use the data.ct.gov dataset. robots.txt allows all.

**Private institutions / extra:** None found beyond IRS 990s (Yale, Wesleyan, etc.).

**Gaps:** None significant. Quasi-public entities are in a separate dataset (82ej-bwva link) - not needed for universities.

**State notes:** Confirmed higher-ed coverage via small SODA aggregate queries (counts by agency/department for 2025). Did not download full files.

## Delaware (DE)

Systems: University of Delaware (state-assisted, privately governed), Delaware State University, Delaware Technical Community College (4 campuses)  
Best rating: **C**. Records loaded: **0**.

### [C] Delaware state employees incl. Delaware Tech and Delaware State University (aggregator)  (catalog id 36)

- System/publisher: multiple
- URL: https://www.openthebooks.com/delaware-state-employees/
- Format: search-form / HTML; years: 2017-2025
- Coverage: Delaware Technical Community College (George, Owens, Stanton, Terry campuses, Office of the President), Delaware State University (incl. Office of Sponsored Programs); University of Delaware not listed; employees: all (as obtained from State of Delaware payroll)
- Fields: year, employer, name, title, annual_wages, source
- Access: login/form required: True; terms: Terms & Conditions linked; not reviewed; updates: annual (not stated); size: 203,688 rows reported; only top 10,000 browsable
- Blocker: Search-only, browsing capped at top 10,000 rows; no bulk download
- Notes: Only source found covering DTCC and DSU by name. Data originates from the State of Delaware payroll (OMB), which can be requested under Delaware FOIA as CSV/Excel (a 2024 MuckRock request asked OMB for all state compensation data; page returned 403 so outcome not verified).

### [C] Delaware state employees (aggregator)  (catalog id 37)

- System/publisher: multiple
- URL: https://openpayrolls.com/
- Format: HTML (per-person pages); years: 2025 seen
- Coverage: State of Delaware payroll (higher-ed coverage unverified); employees: unknown
- Fields: name, title, employer, pay, pay_frequency
- Access: login/form required: False; terms: not stated; updates: not stated; size: not stated
- Blocker: Third-party per-person pages; no bulk file; provenance unclear

### [D] Delaware Department of Human Resources workforce report  (catalog id 38)

- System/publisher: State of Delaware
- URL: https://dhr.delaware.gov/reports/talent-management/2025-de-workforce-rpt.pdf
- Download: https://dhr.delaware.gov/reports/talent-management/2025-de-workforce-rpt.pdf
- Format: PDF; years: FY2025 (annual series)
- Coverage: Executive Branch only; explicitly excludes Higher Education; employees: aggregate
- Fields: average_salary, headcount
- Access: login/form required: False; terms: not stated; updates: annual; size: not checked
- Blocker: Aggregate and excludes higher ed
- Notes: Context only.

### [D] Delaware Open Data (data.delaware.gov)  (catalog id 39)

- System/publisher: State of Delaware
- URL: https://data.delaware.gov/
- Format: Socrata; years: n/a
- Coverage: none; employees: none
- Fields: 
- Access: login/form required: False; terms: not stated; updates: n/a; size: n/a
- Blocker: No employee payroll dataset (searched catalog for salary, payroll, compensation, employee; only educator salary aggregates and credit card transactions)

**Private institutions / extra:** University of Delaware is privately governed but state-assisted; under Delaware FOIA it is only covered for public-funds/board matters and it does not publish employee pay beyond its IRS 990. No private colleges publishing extra data found.

**Gaps:** No official online person-level pay for Delaware State University, Delaware Tech or University of Delaware. State payroll (which includes DTCC and DSU) is not published as open data; obtainable via FOIA to OMB.

**State notes:** Treated University of Delaware as public-ish (listed in systems) but expect no data. News Journal (delawareonline) salary lookups reportedly existed but could not be located.

## District of Columbia (DC)

Systems: University of the District of Columbia (incl. UDC Community College)  
Best rating: **A**. Records loaded: **11,432**.

### [A] University of the District of Columbia (within DC Government employee salary layer)  (catalog id 33)

- System/publisher: DC Department of Human Resources (DCHR) / DC GIS Open Data
- URL: https://opendata.dc.gov/datasets/c9a03cab565b44849bcfc57e63fd3591
- Download: https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/35/query?where=DESCRSHORT%3D%27UDC%27&outFields=*&returnGeometry=false&f=json (ArcGIS REST, maxRecordCount 1000 - page with resultOffset; Hub also offers CSV export)
- Format: API (ArcGIS REST JSON) / CSV via Hub; years: current snapshot only (rows with 2025 hire dates present; DCHR page 'Last Updated 10/01/2026', refreshed quarterly)
- Coverage: UDC (agency code 'UDC'; includes UDC-CC) plus all DC agencies; employees: all incl. adjunct/temporary (adjunct COMPRATE is per-hour/credit rate)
- Fields: first_name, last_name, job_title, agency, grade, comp_rate, hire_date, type_of_appointment
- Access: login/form required: False; terms: Creative Commons Attribution 4.0 International; updates: quarterly; size: 62,201 rows total; 3,156 UDC rows
- Notes: Point-in-time rate (annual or hourly per appointment type), not earnings; no overtime/other pay. No history in the layer - capture quarterly to build history.
- **Loaded: 3,156 records**

### [B] University of the District of Columbia - historic quarterly 'Public Body Employee Information' PDFs  (catalog id 34)

- System/publisher: DC Department of Human Resources
- URL: https://dchr.dc.gov/public-employee-salary-information
- Download: https://dchr.dc.gov/sites/default/files/dc/sites/dchr/publication/attachments/public_body_employee_information_211231.pdf (one PDF per quarter, FY2014 Q1 - FY2022 Q1; links on landing page)
- Format: PDF (tabular text); years: Dec 2013 - Dec 2021 (quarterly)
- Coverage: all DC agencies incl. University of the District of Columbia; employees: all
- Fields: office, appointment_type, last_name, first_name, title, grade, annual_rate, start_date
- Access: login/form required: False; terms: not stated; updates: quarterly (discontinued after Dec 2021 in PDF form); size: Dec 2021: 4.25 MB, 897 pages
- Blocker: PDF text extraction splits some words/columns (e.g. 'Assoc iate'); needs positional parsing
- Notes: Verified UDC rows present (pages ~590+ in Dec 2021 file). Gives ~8 years of quarterly history.
- **Loaded: 8,276 records**

### [C] DCHR Public Body Information Search Tool  (catalog id 35)

- System/publisher: DC Department of Human Resources
- URL: https://dchr.dc.gov/publicbodyinfo
- Download: https://datagate.dc.gov/ess/v1.0/employees (JSON used by page)
- Format: search-form (Vue app over JSON API); years: current
- Coverage: all DC agencies incl. UDC; employees: all
- Fields: first_name, last_name, agency, title, grade, rate, hire_date
- Access: login/form required: True; terms: not stated; updates: quarterly; size: n/a
- Blocker: API is restricted to the dchr.dc.gov origin ('Unauthorized Domain/User'); use the open-data layer instead
- Notes: Did not attempt to work around the origin check.

**Private institutions / extra:** None found beyond IRS 990s (Georgetown, GWU, American, Catholic, Howard - Howard receives a federal appropriation but no person-level pay publication found).

**Gaps:** Only rates (no actual earnings/overtime) and only the current snapshot in open data; 2022-2025 quarterly history appears unavailable except via the live layer at each refresh.

**State notes:** Sampled 3 UDC rows (title/grade/rate only) to confirm content and currency.

## Georgia (GA)

Systems: University System of Georgia (Board of Regents, 26 institutions), Technical College System of Georgia (22 colleges), Georgia Military College  
Best rating: **A**. Records loaded: **1,419,662**.

### [A] All USG institutions, TCSG technical colleges, Georgia Military College, state agencies and local school boards  (catalog id 43)

- System/publisher: Open Georgia (Georgia Department of Audits and Accounts) - Salary & Travel
- URL: https://open.ga.gov/download.html
- Download: https://open.ga.gov/export/SalaryTravelDataExport2025.zip (pattern SalaryTravelDataExport<YYYY>.zip for 2015-2025; all years: https://open.ga.gov/export/SalaryTravelDataExportAllYears.zip)
- Format: CSV (comma-delimited .txt inside ZIP, header row); years: FY2015-FY2025 downloadable (state fiscal year Jul-Jun); older years in search tool / DOAA CD-ROM archive back to ~2003
- Coverage: Every University System of Georgia unit, every TCSG technical college, Georgia Military College (per Open Georgia description page), plus all state agencies and K-12 boards; employees: all (anyone paid in the fiscal year, incl. part-time)
- Fields: name, title, salary (total paid in FY), travel, organization, fiscal_year
- Access: login/form required: False; terms: Files 'made available for download and should be used at your own risk'; no other license stated; updates: annual (2025 file last-modified 2025-12-30); size: 2025 zip ~10 MB (2024 zip 9,197,715 bytes); all-years zip 111,573,331 bytes
- Notes: Verified header via partial range request: NAME,TITLE,SALARY,TRAVEL,ORGANIZATION,FISCAL_YEAR. Numbers wrapped in single quotes (strip on load). No department, no base/other pay split, no FTE/hire date. Names are LAST,FIRST M. Filter ORGANIZATION for university/college names. Per AJC reporting, foundation-paid supplements (e.g. coaches) are not included. robots.txt allows /export/ but disallows the /sta/ search app.
- **Loaded: 1,419,662 records**

### [C] All Georgia public employees incl. USG  (catalog id 44)

- System/publisher: Open Georgia salary & travel search
- URL: https://open.ga.gov/openga/stHome/acceptDisclaimer
- Format: search-form; years: multiple fiscal years
- Coverage: same as bulk files; employees: all
- Fields: name, title, salary, travel, organization, fiscal_year
- Access: login/form required: True; terms: disclaimer acceptance required; updates: annual; size: not stated
- Blocker: Disclaimer click-through and search form; robots.txt disallows /sta/; redundant with bulk ZIPs.
- Notes: Use the bulk download instead.

### [C] Georgia state employees incl. USG institutions  (catalog id 45)

- System/publisher: OpenTheBooks (third party)
- URL: https://www.openthebooks.com/georgia-state-employees/
- Format: HTML/search; years: multiple years (2025 shown)
- Coverage: USG institutions among state agencies; employees: all, but web view limited to top 10,000 of ~1.34M records
- Fields: name, title, employer, pay, year
- Access: login/form required: True; terms: not stated (site terms apply); updates: annual; size: 1,342,198 salary records stated
- Blocker: Paged search view capped at top 10,000; full data needs account/request; derived from Open Georgia anyway.
- Notes: Secondary source; not needed given the official bulk files.

**Private institutions / extra:** None found; private universities (Emory, Mercer, etc.) only via IRS 990.

**Gaps:** No department, FTE, hire date, or base vs. supplemental pay split in Open Georgia. No standalone USG or TCSG salary database found. Foundation and athletic-association pay excluded.

**State notes:** Open Georgia covers USG + TCSG + GMC in one statewide file, so no per-institution pages were pursued. Header verified via a 40 KB range request (no full download). Did not check AJC salary database (no confirmed downloadable data).

## Hawaii (HI)

Systems: University of Hawaii System (10 campuses: UH Manoa, UH Hilo, UH West Oahu, 7 community colleges)  
Best rating: **C**. Records loaded: **0**.

### [C] University of Hawaii System (all campuses) plus 18 other state/county agencies  (catalog id 46)

- System/publisher: Honolulu Civil Beat Hawaii Public Employee Salary Database (news org)
- URL: https://www.civilbeat.org/data/hawaii-state-salaries/
- Format: search-form; years: FY2011, 2012, 2013, 2016, 2018, 2020, 2022, 2024, 2026
- Coverage: UH System (all 10 campuses) among state/county agencies; employees: all (UH graduate assistants included with identities redacted)
- Fields: name, department, sub_department, title, salary_range, fiscal_year, hourly_flag
- Access: login/form required: True; terms: not stated; updates: roughly biennial; last updated 2026-02-04; size: ~100,000 entries (~74,600 state, ~19,300 local)
- Blocker: Search form only, no bulk download found; salaries shown as ranges, not exact amounts.
- Notes: Data obtained by Civil Beat under UIPA (Hawaii public records law). Search by department, name, title, salary range, year. UH supplied ranges or salary points depending on bargaining unit.

### [C] University of Hawaii System faculty  (catalog id 47)

- System/publisher: UHPA (faculty union) Salary Research
- URL: https://www.uhpa.org/salary-research/
- Format: HTML (aggregate tables); years: current (Feb 2024 snapshot shown) plus salary archives
- Coverage: UH campuses incl. community colleges; employees: faculty only (plus separate executive/management page)
- Fields: department/campus/faculty type, min_salary, avg_salary, max_salary
- Access: login/form required: False; terms: not stated; updates: quarterly (stated); size: not stated
- Blocker: Pages viewed show aggregates (min/avg/max by department/campus), not person-level rows; some content may be member-only.
- Notes: Data supplied by UH to the union. Executive-management salaries page at /salary-research/executive-management-salaries/ may be person-level but was not confirmed.

### [C] University of Hawaii System  (catalog id 48)

- System/publisher: UH annual salary report to Legislature (HRS 304A-1004)
- URL: https://hawaii.edu/govrel/docs/reports/2024/hrs304a-1004_2024_salary_annual-report_508.pdf
- Download: https://hawaii.edu/govrel/docs/reports/2024/hrs304a-1004_2024_salary_annual-report_508.pdf
- Format: PDF; years: annual reports (2024 checked)
- Coverage: UH System; employees: executive/managerial and salary actions (not confirmed)
- Fields: not confirmed
- Access: login/form required: False; terms: not stated; updates: annual; size: 3.6 MB PDF
- Blocker: PDF appears to contain scanned 1-bit images (OCR needed); content and employee coverage not confirmed.
- Notes: Could not extract text locally (no PDF tools available); WebFetch saw only embedded scanned images.

**Private institutions / extra:** None found (Chaminade, Hawaii Pacific, BYU-Hawaii: IRS 990 only).

**Gaps:** No official bulk or API person-level pay data for UH. Hawaii open data portal (opendata.hawaii.gov CKAN) has no employee-salary dataset (only budget table J1). Best route for full data is a UIPA public records request to UH.

**State notes:** Searched opendata.hawaii.gov CKAN API for 'salary' (1 hit, budget-level only). Civil Beat rated C because of search-only access and salary ranges. Did not submit any search forms.

## Idaho (ID)

Systems: Idaho State Board of Education four-year institutions (Boise State, University of Idaho, Idaho State, Lewis-Clark State College), Community colleges (College of Western Idaho, College of Southern Idaho, North Idaho College, College of Eastern Idaho) - locally governed  
Best rating: **B**. Records loaded: **0**.

### [B] Boise State, University of Idaho, Idaho State, Lewis-Clark State plus all state agencies  (catalog id 53)

- System/publisher: Transparent Idaho (Idaho State Controller) - Workforce & Salary
- URL: https://transparent.idaho.gov/Workforce&Salary
- Format: HTML (JavaScript single-page app); export option not verified; years: multi-year (reports cited 2015-2024; data said to update daily)
- Coverage: four public universities/colleges on the state payroll (Luma system); NOT community colleges; employees: all (since July 2023 university counts include students regardless of benefits)
- Fields: name, agency, title, pay_rate/salary, pay basis (hourly/annual)
- Access: login/form required: False; terms: not stated; updates: stated as daily; size: not stated
- Blocker: Site is a JS single-page app that returned only a shell to scripted requests (bundle also served HTML); person-level report structure and any Excel/CSV export could not be verified without a browser.
- Notes: Reports include Employee Pay Rates, Highest Paid State Employees, employee counts and pay ranges. Shows pay rates, not total earnings. Coach pay from athletic revenue may be excluded. Contact transparentidaho@sco.idaho.gov. A headless browser could reveal the backing API.

### [C] Boise State, University of Idaho, Idaho State, Lewis-Clark State  (catalog id 54)

- System/publisher: Idaho Statesman public university pay database (news org)
- URL: https://www.aol.com/much-boise-state-football-coach-110000652.html (syndicated article linking to the Statesman database)
- Format: search-form; years: recent single year (2024-2025)
- Coverage: four public four-year institutions; no community colleges; employees: all (~15,000)
- Fields: name, agency, hourly_pay, salary
- Access: login/form required: True; terms: not stated (Statesman site may be paywalled); updates: occasional; size: ~15,000 employees
- Blocker: Search form only, results capped at 200 per search, no download; possibly paywalled.
- Notes: Data likely from Transparent Idaho/public records requests.

### [C] Idaho state employees incl. universities  (catalog id 55)

- System/publisher: OpenTheBooks (third party)
- URL: https://www.openthebooks.com/idaho-state-employees/
- Format: HTML/search; years: multiple years
- Coverage: state agencies incl. universities; employees: all, but web view capped
- Fields: name, title, employer, pay, year
- Access: login/form required: True; terms: site terms; updates: annual; size: not stated
- Blocker: Paged view capped to top records; full data requires account/request.
- Notes: Secondary source.

**Private institutions / extra:** None found (BYU-Idaho, College of Idaho, Northwest Nazarene: IRS 990 only).

**Gaps:** Community colleges (CWI, CSI, NIC, CEI) are not in Transparent Idaho and no published salary lists were found for them. No confirmed bulk CSV/API for university pay. Total compensation (vs pay rate) missing.

**State notes:** Transparent Idaho rated B on the expectation that its official person-level pay-rate reports are scrapable, but this was not verified (JS app blocked plain HTTP fetches; did not use a browser). Idaho Education News 'Big salaries on campus' articles (2024) are analyses, not datasets.

## Iowa (IA)

Systems: Board of Regents, State of Iowa (University of Iowa, Iowa State University, University of Northern Iowa, plus Iowa School for the Deaf / Iowa Braille), Iowa community colleges (15 locally governed districts)  
Best rating: **A**. Records loaded: **0**.

### [A] University of Iowa, Iowa State University, University of Northern Iowa (all Regents institutions) plus all state agencies  (catalog id 49)

- System/publisher: State of Iowa Salary Book - Iowa Data Hub (Dept. of Administrative Services / Dept. of Management)
- URL: https://data.iowa.gov/catalog/dataset/1001
- Download: Download button on the dataset page (JS-generated; no static URL exposed). Old Socrata URL https://data.iowa.gov/api/views/s3p7-wy6w/rows.csv?accessType=DOWNLOAD now returns 404 after the portal migration.
- Format: CSV (download from data hub; underlying table state_salary_book); years: FY2007-FY2025 (coverage start 2006-07-01); per-year datasets FY2019-FY2025 also listed (catalog/dataset/1280-1286)
- Coverage: All Regents universities and all state departments, boards, commissions; excludes community colleges, Community Based Corrections, State Fair Board; employees: all with annual salary >= $1,000
- Fields: record_id, fiscal_year, department_name, sub_organization_name, employee_name, employee_gender, county, employee_position, employee_base_salary, employee_salary (total paid in FY), employee_travel_subsistence
- Access: login/form required: False; terms: CC BY (data hub page); data.gov copy listed as CC0; updates: annually (data last updated 2026-07-23); size: 1,179,610 rows (all years)
- Notes: Portal moved from Socrata to a new Next.js 'Iowa Data Hub' in 2025; the Download button is client-side so a static bulk URL needs to be captured from the browser. 'TERMINATED' appears in base salary column for departed employees; people paid by multiple departments appear multiple times. sub_organization_name may give college/unit for Regents rows. robots.txt allows all generic agents (Content-Signal ai-train=no).

### [C] University of Iowa, ISU, UNI and state employees  (catalog id 50)

- System/publisher: The Gazette (Cedar Rapids) salary databases (news org)
- URL: https://www.thegazette.com/news/records/salaries/data-university-of-iowa-public-employee-salaries-for-fiscal-year-2024/article_e899aa51-a4cd-50b0-ab35-ac91652fa8a7.html
- Format: HTML/search; years: per fiscal year (FY2023, FY2024 seen)
- Coverage: Regents universities, state agencies; employees: all
- Fields: name, title, department, salary, fiscal_year
- Access: login/form required: True; terms: not stated (may be paywalled); updates: annual; size: not stated
- Blocker: Embedded search tables; derived from the official Salary Book, which is better.
- Notes: Redundant with Salary Book.

### [C] Iowa community colleges (administrators)  (catalog id 51)

- System/publisher: Iowa Legislature - Community College Additional Information Report
- URL: https://www.legis.iowa.gov/docs/publications/DF/1448343.pdf
- Download: https://www.legis.iowa.gov/docs/publications/DF/1448343.pdf
- Format: PDF; years: FY2023
- Coverage: 15 community colleges; employees: contracted administrators only
- Fields: college, position, salary, benefits
- Access: login/form required: False; terms: not stated; updates: annual; size: not stated
- Blocker: PDF, administrators only, mostly positions rather than full names.
- Notes: Only state-level source touching community college pay.

### [C] Indian Hills Community College (and local governments)  (catalog id 52)

- System/publisher: Ottumwa Courier 2024 Area Public Salaries database (news org)
- URL: https://www.ottumwacourier.com/news/record/database-2024-area-public-salaries/html_0b74d04e-034e-11f0-9edf-9bf0826cfb1d.html
- Format: HTML/search; years: 2024
- Coverage: Indian Hills Community College only (among higher ed); employees: all
- Fields: name, employer, title, salary
- Access: login/form required: False; terms: not stated; updates: annual; size: not stated
- Blocker: Single college, embedded news table, no download.
- Notes: Local coverage only.

**Private institutions / extra:** None found (Grinnell, Drake, etc.: IRS 990 only).

**Gaps:** Community colleges are excluded from the Salary Book; no statewide person-level community college pay source found (public records requests per college needed). Static bulk-download URL for the new Iowa Data Hub not captured.

**State notes:** data.iowa.gov left Socrata (catalog API says domain not found; /api/views returns 404), so metadata came from the new dataset page's embedded JSON (column list from its transformSql). Did not click Download.

## Kansas (KS)

Systems: Kansas Board of Regents state universities (KU, KU Medical Center, Kansas State, Wichita State, Emporia State, Pittsburg State, Fort Hays State), Washburn University (municipal), 19 locally governed community colleges and 6 technical colleges (coordinated by KBOR)  
Best rating: **A**. Records loaded: **122,263**.

### [A] KU, KUMC, K-State, Wichita State, Emporia State, Pittsburg State, Fort Hays State plus all state agencies  (catalog id 66)

- System/publisher: KansasOpenGov.org (Kansas Policy Institute) - Payroll: All State Employees
- URL: https://kansasopengov.org/databank/payroll-all-state-employees/
- Download: https://kansasopengov.org/wp-content/uploads/2023/07/State-Payroll-2021-to-2025.csv
- Format: CSV; years: 2020-2025 (CSV covers 2021-2025; 2020 in web table)
- Coverage: Regents universities and all state agencies on state payroll; not Washburn or community/technical colleges; employees: all on state payroll (excludes pay from privately raised funds, e.g. coaches' foundation pay)
- Fields: year, first_name (with middle initial), last_name, agency, position, total_pay
- Access: login/form required: False; terms: not stated; updates: annual (file last-modified 2026-06-05); size: 18,660,392 bytes
- Notes: Third-party (think tank) compiled from Kansas Open Records Act requests; verified CSV header via 600-byte range request. No department, no base/other split. robots.txt allows all.
- **Loaded: 122,263 records**

### [C] All state agencies incl. Regents universities  (catalog id 67)

- System/publisher: KanView (Kansas Department of Administration) - Employee Compensation / Data Download Center
- URL: https://kanview.ks.gov/
- Download: https://kanview.ks.gov/DataDownload.aspx (not visited)
- Format: HTML search + downloads (ASP.NET); years: FY2006-present (site states); prior-year employee compensation in Data Download Center
- Coverage: state agencies incl. Regents universities; employees: all (compensation by agency and by job title)
- Fields: agency, job_title, compensation (names not confirmed)
- Access: login/form required: True; terms: informational purposes only disclaimer; updates: annual/periodic; size: not stated
- Blocker: robots.txt disallows all crawling (User-agent: * Disallow: /); ASP.NET forms; person-level names not confirmed.
- Notes: Only the homepage was fetched before reading robots.txt; stopped there. Official source but robots-blocked for automated collection; could request data from Dept. of Administration.

**Private institutions / extra:** None found.

**Gaps:** No source for Washburn University or Kansas community/technical colleges. No department, FTE, or base vs. other pay split. Foundation-funded pay excluded.

**State notes:** Used the KansasOpenGov CSV as best source despite being third-party, because the official KanView forbids crawling. Did not download the full CSV.

## Kentucky (KY)

Systems: Independent public universities coordinated by Council on Postsecondary Education (UK, UofL, WKU, EKU, Murray State, Morehead State, NKU, Kentucky State), Kentucky Community and Technical College System (KCTCS, 16 colleges)  
Best rating: **C**. Records loaded: **0**.

### [C] State agencies; universities and KCTCS referred to their own institutions  (catalog id 68)

- System/publisher: Kentucky Transparency (transparency.ky.gov) Salary Search - Personnel Cabinet data
- URL: https://transparency.ky.gov/search/Pages/SalarySearch.aspx
- Format: search-form; years: current (updated monthly on the 24th)
- Coverage: Executive, Judicial and Legislative branch agencies; page says to contact individual universities and community/technical colleges for their data; employees: all state employees (universities not actually included per page text)
- Fields: name, agency, title, salary
- Access: login/form required: True; terms: informational purposes only; not an official business record; updates: monthly; size: not stated
- Blocker: Search form only; host did not resolve (DNS ENOTFOUND) on 2026-10-18; universities/KCTCS not covered - redirects users to institutions.
- Notes: Described from search-engine snippets because the site was unreachable.

### [C] University of Kentucky  (catalog id 69)

- System/publisher: Lexington Herald-Leader UK salary database (news org)
- URL: https://www.aol.com/much-university-kentucky-employees-2024-162149876.html (syndicated article pointing to Herald-Leader database)
- Format: search-form; years: 2024 (also earlier editions)
- Coverage: University of Kentucky (incl. UK HealthCare); employees: all
- Fields: name, college, department, job_title, annual_salary
- Access: login/form required: True; terms: not stated (likely paywalled); updates: annual; size: not stated
- Blocker: Search-only news app built from an open records request; no download.
- Notes: Shows the data is obtainable from UK via Kentucky Open Records Act request.

### [C] Western Kentucky University  (catalog id 70)

- System/publisher: WKU Budget & Finance - Budgeted Salary Information (budgeted positions report)
- URL: https://www.wku.edu/budget-finance/budget/operating-budgets/2026-2027/
- Download: https://www.wku.edu/budget-finance/secure_docs/fy27-budgeted-positions-report.pdf
- Format: PDF; years: FY2027 (annual)
- Coverage: WKU; employees: budgeted positions (likely all)
- Fields: not confirmed (position, budgeted salary)
- Access: login/form required: True; terms: not stated; updates: annual; size: not stated
- Blocker: HTTP 401 - requires WKU NetID login (Basic auth).
- Notes: Public budget book PDFs on the same page are aggregate only.

### [C] UK, UofL, NKU, KCTCS and other Kentucky public employers  (catalog id 71)

- System/publisher: OpenTheBooks (third party)
- URL: https://www.openthebooks.com/kentucky-state-employees/
- Format: HTML/search; years: 2017-2025
- Coverage: includes UK, UofL, NKU, KCTCS among state employers; employees: all, web view capped at top 10,000 of ~765,000
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: site terms; updates: annual; size: 764,985 salary records stated
- Blocker: Web view capped at top 10,000; full data needs account/request.
- Notes: The only multi-institution compilation found; OpenTheBooks evidently obtained university payrolls via records requests.

**Private institutions / extra:** None found.

**Gaps:** No official bulk or HTML person-level salary publication found for any Kentucky public university or KCTCS. Universities run their own payrolls outside the state Personnel Cabinet. Not checked individually: EKU, Murray State, Morehead State, NKU, Kentucky State, KCTCS websites (budget books typically aggregate). Open records requests to each institution are the likely route.

**State notes:** transparency.ky.gov was unreachable (DNS failure) so its description relies on search snippets. Did not attempt the WKU login.

## Louisiana (LA)

Systems: LSU System, University of Louisiana System (9 universities), Southern University System, Louisiana Community and Technical College System (LCTCS), Louisiana Board of Regents (coordinating board)  
Best rating: **C**. Records loaded: **0**.

### [C] Executive-branch state agencies (higher education inclusion uncertain)  (catalog id 72)

- System/publisher: Louisiana Checkbook (Division of Administration) - State Employees salary database
- URL: https://checkbook.la.gov/stateEmployees/index.cfm
- Format: search-form (ColdFusion); years: 2023-present (launched Sept 2023)
- Coverage: all executive branch agencies; at launch did NOT include salaried higher education employees (Louisiana Illuminator, Sept 2023); current status unverified; employees: all executive-branch (higher ed possibly only wage/classified staff)
- Fields: name, agency, title, salary (unverified)
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Blocker: robots.txt disallows /stateEmployees/ so it was not crawled; higher-ed coverage unconfirmed; search-style app.
- Notes: Created under a 2018 law (Sen. Rick Ward). Worth a manual check or a request to DOA for a bulk extract that includes higher ed.

### [D] All Louisiana public colleges and universities (data collection)  (catalog id 73)

- System/publisher: Louisiana Board of Regents EMPSAL (Employee Salary Data System)
- URL: https://www.laregents.edu/data-publications/empsal/
- Format: internal data collection; only PDF specs public; years: FY2023-FY2026 specifications posted
- Coverage: all public higher education institutions and systems (LSU, ULS, Southern, LCTCS); employees: all compensated personnel at a point in time
- Fields: per spec: employee identifier, institution, position, salary, FTE etc. (not public)
- Access: login/form required: True; terms: not stated; updates: annual; size: not stated
- Notes: Person-level data exists centrally at Regents but is not published; contact Regents Data Services Helpdesk (225-342-4253) or file a public records request - best single target for a records request. Direct curl got 403 (WAF); WebFetch read the page.

### [D] LSU  (catalog id 74)

- System/publisher: LSU Digital Commons - 'Salaries of Louisiana State University Employees' collection
- URL: https://digitalcommons.lsu.edu/employeesalaries/
- Format: repository collection (empty); years: none listed
- Coverage: LSU; employees: unknown
- Fields: 
- Access: login/form required: False; terms: not stated; updates: n/a; size: 0 items visible
- Notes: Collection page exists but lists no items.

### [C] LSU, Southern, ULS universities and other Louisiana public employers  (catalog id 75)

- System/publisher: OpenTheBooks / OpenPayrolls (third party)
- URL: https://www.openthebooks.com/louisiana-state-employees/
- Format: HTML/search; years: 2021-2025
- Coverage: includes LSU and Southern University employees; employees: all, web view capped
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: site terms; updates: annual; size: not stated
- Blocker: Capped paged views (top 10,000) and per-person pages; no bulk download without account/request.
- Notes: OpenPayrolls.com also has per-person LSU 2025 pages (e.g. https://openpayrolls.com/shane-stadler-175837775); provenance unverified.

**Private institutions / extra:** None found (Tulane, Loyola: IRS 990 only).

**Gaps:** No official published person-level pay for any Louisiana public university system or LCTCS. Regents EMPSAL holds the data but does not publish it. Checkbook coverage of higher ed unconfirmed and robots-blocked.

**State notes:** Honored checkbook.la.gov robots.txt (Disallow /stateEmployees/). lailluminator.com returned 403, so Illuminator details come from search snippets. Did not check each ULS campus individually; LSU's own site only publishes aggregate peer-salary PDFs.

## Maine (ME)

Systems: University of Maine System (UM, UMA, UMF, UMFK, UMM, UMPI, USM, Maine Law, System-Wide Services), Maine Community College System (7 colleges), Maine Maritime Academy  
Best rating: **A**. Records loaded: **22,902**.

### [A] University of Maine System (all campuses incl. Maine Law and System-Wide Services)  (catalog id 81)

- System/publisher: UMS Human Resources Reports - Regular Employee Compensation Report ('Salaries of Regular Employees')
- URL: https://www.maine.edu/human-resources/reports/
- Download: https://umainesystem.sharepoint.com/:x:/s/USERVICES-OnlineDocs/IQDqj_BhiQonQYDtctkano9vAR0sfdWOg5CFpMSk7PO7JV4?download=1 (anonymous SharePoint share; resolves to /sites/USERVICES-OnlineDocs/Shared Documents/HR/Public Info Salary Reports/Regular Employee Compensation Report June 2026.xlsx; needs cookie jar to follow redirects)
- Format: XLSX (one sheet; ~30 lines of legend above the header row); years: current snapshot June 2026 on page; earlier editions (Nov 2019, Apr 2020, Nov 2020, Nov 2021, Apr 2023, Nov 2024, Apr 2025) published as PDF/XLSX under maine.edu/human-resources/wp-content/uploads/
- Coverage: all UMS universities and units; employees: all regular full-time and part-time employees (primary title only)
- Fields: campus, formatted_name (Last, First M.), dept_id, title, salbase (annual base salary incl. stipends >= 1 year), job_status (FR/PR), bargaining_unit, faculty_appt (FY/AY/Federal), fte
- Access: login/form required: False; terms: Disclaimer: made available as a public service; reliance at user's own risk; updates: about twice a year (spring and fall snapshots); size: 315,353 bytes; ~4,450 employee rows
- Notes: Verified header and sample rows. Excludes overtime, overload teaching, short-term stipends; base salary only (not actual earnings). Dept ID is a code (e.g. PLAW). Older snapshots are PDFs (rate B) useful for history; only the current file is linked on the page, so archive URLs need collection over time or from search engines.
- **Loaded: 4,449 records**

### [B] University of Maine System (historical)  (catalog id 82)

- System/publisher: UMS 'Public Information Document' PDFs
- URL: https://www.maine.edu/human-resources/wp-content/uploads/sites/7/2021/11/UMS_PUBLICINFO_MAIN_11-22-21-dist-1.pdf
- Download: https://www.maine.edu/human-resources/wp-content/uploads/sites/7/2020/11/Public-Information-Document-11.3.20.pdf ; .../2020/04/Public-Information-Document-4.3.20.pdf ; .../2020/02/Public-Information-Document-11.26.19_accessible.pdf
- Format: PDF; years: Nov 2019 - Nov 2021 snapshots
- Coverage: all UMS campuses; employees: all regular employees
- Fields: campus, name, title, base_salary, job_status, bargaining_unit, fte
- Access: login/form required: False; terms: same disclaimer; updates: semiannual; size: not checked
- Blocker: PDF tables need extraction; no index page linking the archive.
- Notes: Same structure as the current XLSX.
- **Loaded: 18,453 records**

### [C] Maine Community College System  (catalog id 83)

- System/publisher: FOAA response via MuckRock (2023)
- URL: https://www.muckrock.com/foi/maine-13/records-retention-schedules-org-charts-employee-chart-master-list-of-forms-foaa-log-maine-community-college-system-148512/
- Format: spreadsheet attachment (per search snippet); years: 2023
- Coverage: MCCS (at least one college/system office); employees: all (name/title/salary list)
- Fields: name, title, salary
- Access: login/form required: False; terms: not stated; updates: one-off; size: not stated
- Blocker: One-off records-request release; MuckRock returned 403 to automated fetch so attachment availability unconfirmed.
- Notes: Shows MCCS releases name/title/salary lists free of charge on FOAA request.

**Private institutions / extra:** None found (Bowdoin, Bates, Colby: IRS 990 only).

**Gaps:** No published salary data for Maine Community College System or Maine Maritime Academy; both would need FOAA requests. UMS data is base salary only, not total pay; only the current snapshot is linked.

**State notes:** Downloaded the 315 KB UMS xlsx to verify columns (small file), then deleted it. Did not pursue the Maine state payroll (state employees only; UMS/MCCS run separate payrolls).

## Maryland (MD)

Systems: University System of Maryland (12 institutions incl. UMD College Park, UMB, UMBC, Towson, Salisbury, etc.), Morgan State University (independent public), St. Mary's College of Maryland (independent public), Baltimore City Community College (state) and 15 county-governed community colleges  
Best rating: **A**. Records loaded: **140,391**.

### [A] University of Maryland, College Park  (catalog id 78)

- System/publisher: The Diamondback Salary Guide (UMD student newspaper) - JSON API
- URL: https://salaryguide.dbknews.com/
- Download: https://api.dbknews.com/salary/year/<YYYY>?page=<n>&sortby=salary&order=desc&search= (years list: https://api.dbknews.com/salary/years)
- Format: API (JSON); years: 2013-2025
- Coverage: UMD College Park only; employees: all (faculty and staff; 10,963 records for 2025)
- Fields: division, department, title, employee (name), salary (string with $ and commas), employee_type, exempt_status
- Access: login/form required: False; terms: not stated on API; Diamondback historically described the data as freely available to the public; updates: annual; size: 2025: 10,963 rows; paged at 10 rows per page (~1,100 requests per year); page-size parameters ignored
- Notes: Endpoint discovered in the site's JS bundle; verified /years and /year/2025 responses with a few spaced requests. Data comes from UMD via public records. Salary is a budgeted/annual salary, no other pay or FTE. Small page size means a full pull should be slow and polite (no robots.txt on api host - returns HTML error). Fields vary slightly by year (check older years).
- **Loaded: 140,391 records**

### [C] State employees incl. University System of Maryland institutions  (catalog id 79)

- System/publisher: Baltimore Sun Public Salary Records (news org)
- URL: https://salaries.news.baltimoresun.com/salaries/2017+Maryland+state+salaries/9
- Format: HTML/search; years: selected years up to ~2017+ (archive)
- Coverage: state agencies incl. USM (system 'UM') and other public colleges; employees: all
- Fields: name, system, organization, title, pay_type, gross_yearly_earnings, year
- Access: login/form required: False; terms: not stated; updates: irregular / possibly discontinued; size: not stated
- Blocker: Site returned 502 Bad Gateway on 2026-10-18; stale data; HTML-only.
- Notes: Would be B if back online (paged HTML tables).

### [C] Maryland state employees incl. USM  (catalog id 80)

- System/publisher: OpenTheBooks (third party)
- URL: https://www.openthebooks.com/maryland-state-employees/
- Format: HTML/search; years: multiple years
- Coverage: state payroll incl. USM institutions; employees: all, web view capped
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: site terms; updates: annual; size: not stated
- Blocker: Capped paged view (top 10,000); full data requires account/request.
- Notes: Secondary source; not verified in detail.

**Private institutions / extra:** None found (Johns Hopkins, Loyola, etc.: IRS 990 only).

**Gaps:** No official statewide or USM-wide salary publication found; opendata.maryland.gov (Socrata) has no employee salary dataset (only FTE counts, x8qy-486w). Nothing found for UMBC, UMB, Towson, Salisbury, other USM campuses, Morgan State, St. Mary's, or community colleges - Maryland Public Information Act requests needed.

**State notes:** Rated the Diamondback API A because it is clean JSON with names, departments and salaries back to 2013, even though it covers only College Park and is a student-newspaper source. Baltimore Sun salary site was down (502).

## Massachusetts (MA)

Systems: University of Massachusetts System (Amherst, Boston, Dartmouth, Lowell, Chan Medical School/Worcester), Massachusetts State Universities (Bridgewater, Fitchburg, Framingham, Salem, Westfield, Worcester, MassArt, MCLA, Mass Maritime), Massachusetts Community Colleges (15 colleges)  
Best rating: **A**. Records loaded: **1,198,973**.

### [A] All Massachusetts public higher-ed institutions (UMass system, 9 state universities, 15 community colleges) via Commonwealth statewide payroll  (catalog id 76)

- System/publisher: Commonwealth of Massachusetts - Office of the Comptroller CTHRU
- URL: https://cthrupayroll.mass.gov/
- Download: https://cthru.data.socrata.com/api/views/9ttk-7vz6/rows.csv?accessType=DOWNLOAD (SODA API: https://cthru.data.socrata.com/resource/9ttk-7vz6.json)
- Format: CSV / JSON / Socrata API; years: 2010-2026 (calendar years; current year updated through latest pay period)
- Coverage: UMass System (campus in department_location_zip_code e.g. 'U Mass Lowell', 'U Mass Worcester'); Bridgewater, Fitchburg, Framingham, Salem, Westfield, Worcester State; MassArt; MCLA; Mass Maritime; Berkshire, Bristol, Bunker Hill, Cape Cod, Greenfield, Holyoke, Mass Bay, Massasoit, Middlesex, Mt Wachusett, Northern Essex, North Shore, Quinsigamond, Roxbury, Springfield Tech CCs; Dept of Higher Education; employees: all (full-time, part-time, contractors, student employees)
- Fields: year, name_last, name_first, department_division, department_code, position_title, position_type, service_end_date, pay_total_actual, pay_base_actual, pay_buyout_actual, pay_overtime_actual, pay_other_actual, annual_rate, pay_year_to_date, department_location_zip_code (campus for UMass), contract, bargaining_group_no, bargaining_group_title, trans_no
- Access: login/form required: False; terms: not stated (standard Socrata open data); updates: per pay period (biweekly); dataset updated 2026-10-17; size: 2,741,713 rows all agencies 2009-2026; 2025 higher-ed approx 70k rows (UMS 31,890)
- Notes: No academic department field: department_division is the institution; UMass campus only via department_location_zip_code text. Filter by department_code (UMS, BSC, FSC, FRC, SSA, WSC, WOR, MCA, NAC, MMA, and CC codes). Metadata min year shows 2009 though site advertises 2010.
- **Loaded: 1,198,973 records**

### [A] Massachusetts quasi-public agencies  (catalog id 77)

- System/publisher: CTHRU Quasi Government Payroll
- URL: https://cthru.data.socrata.com/
- Download: https://cthru.data.socrata.com/resource/tc5d-8ckm.json
- Format: CSV / JSON / Socrata API; years: multiple calendar years
- Coverage: quasi-government agencies (possibly UMass Building Authority / MA Educational Financing type bodies); not colleges themselves; employees: all employees of quasi agencies
- Fields: quasi_agency_code, quasi_agency_name, calendar_year, payroll_date_as_of, last_name, first_name, middle_name, job_description, job_code, department_code, department_name, pay_year_to_date, annual_rate
- Access: login/form required: False; terms: not stated; updates: periodic (updated 2026-09-18); size: not checked
- Notes: Peripheral; only relevant if higher-ed quasi agencies are of interest. Not verified which agencies are included.

**Private institutions / extra:** None found; MA private universities (Harvard, MIT, BU, Northeastern etc.) publish only IRS 990 compensation.

**Gaps:** No academic department/college-unit field for any institution; UMass campus only via location text. No separate UMass system salary database checked beyond CTHRU (not needed).

**State notes:** Used Socrata catalog API to find current production dataset id 9ttk-7vz6 (old id rxhc-k6iz no longer resolves). Did not download bulk file; HEAD shows CSV export available (streamed, no content-length).

## Mississippi (MS)

Systems: Mississippi Institutions of Higher Learning (IHL): Univ. of Mississippi (incl. UMMC), Mississippi State, Southern Miss, Jackson State, Alcorn State, Delta State, Mississippi University for Women, Mississippi Valley State, Mississippi Community College Board (15 community colleges)  
Best rating: **C**. Records loaded: **0**.

### [C] Mississippi state employees incl. IHL universities (UM, MSU, USM, others) and at least one community college  (catalog id 97)

- System/publisher: OpenTheBooks (private nonprofit aggregator)
- URL: https://www.openthebooks.com/mississippi-state-employees/
- Format: search-form (HTML results, top 10,000 per query); years: 2017-2025
- Coverage: State agencies and IHL universities (Univ. of Mississippi, Mississippi State, Southern Miss seen); Southwest Mississippi CC seen in employer filter; completeness for other CCs unclear; employees: all (as obtained via public records requests)
- Fields: year, employer, name, title, annual_wages, source
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions linked (contents not reviewed); updates: annual; size: 293,793 records (all employers, all years)
- Blocker: Search-only interface capped at 10,000 results per query, no bulk export; third-party data; no department field.
- Notes: Only person-level source found for Mississippi public universities. Bulk data may be obtainable by request from OpenTheBooks.

### [D] Mississippi state agencies  (catalog id 98)

- System/publisher: Transparency Mississippi (Dept. of Finance and Administration)
- URL: https://www.transparency.ms.gov/workforce/workforce.aspx
- Format: HTML reports; years: FY2015-present (pre-FY2015 archive separate)
- Coverage: State agencies on the state MAGIC/SPAHRS payroll; IHL universities and community colleges run their own payroll and do not appear to be included; employees: aggregate only (employee counts, salary & fringe by agency, salary statistics)
- Fields: agency, employee_count, salary_and_fringe_totals
- Access: login/form required: False; terms: not stated; updates: not stated; size: not stated
- Notes: No person-level pay; listed for completeness only.

**Private institutions / extra:** None found (Millsaps, Mississippi College, Belhaven etc. only IRS 990).

**Gaps:** No official person-level salary publication found for IHL universities or community colleges; no newspaper salary database found. IHL Annual Workforce Report (slds.ms.gov) is aggregate. Data would require Mississippi Public Records Act requests to each institution.

**State notes:** Searched IHL, Transparency MS, Clarion Ledger, Mississippi Today, university budget documents. Did not use postback reports on transparency.ms.gov (form submission). H-1B LCA sites (h1bdata, Ellis) exist but cover visa positions only and were excluded.

## Missouri (MO)

Systems: University of Missouri System (Columbia, Kansas City, Missouri S&T, St. Louis, MU Health Care), Regional public universities (Missouri State, UCM, SEMO, Truman, Northwest Missouri State, Missouri Southern, Missouri Western, Lincoln, Harris-Stowe), Missouri community colleges (St. Louis CC, Metropolitan CC, St. Charles CC, Ozarks Tech, etc.) - locally governed  
Best rating: **B**. Records loaded: **263,272**.

### [B] University of Missouri System (all campuses + system office)  (catalog id 92)

- System/publisher: University of Missouri System
- URL: https://mospace.umsystem.edu/xmlui/handle/10355/43681 (Employee Salary Reports for UM and All Campuses)
- Download: https://mospace.umsystem.edu/server/api/core/bitstreams/66043a16-a90f-47d0-911a-7a2f115ada1d/content (annual-salary-report-2025-26.pdf); list items via https://mospace.umsystem.edu/server/api/discover/search/objects?scope=e9ae9f73-aa9b-44e7-aca2-a3bc09223743&dsoType=ITEM
- Format: PDF (text-based tables); years: 2013-14 through 2025-26 (13 annual reports)
- Coverage: MU Columbia (COLUM), UMKC, Missouri S&T, UMSL, UM System office (Business Unit column); employees: all (faculty, staff, residents, postdocs, hourly)
- Fields: name, w2_box5_prior_year_earnings, business_unit (campus), department, job_title, salary_rate (annual or hourly)
- Access: login/form required: False; terms: MOspace: protected by copyright, all rights reserved unless otherwise indicated; updates: annual; size: 2025-26 PDF 8.6 MB, 370 pages (approx 18k rows)
- Blocker: PDF only; requires table extraction (clean single-line rows, text extractable with pypdf).
- Notes: Excellent field set incl. department and both rate and actual W-2 pay. DSpace 7 REST API lists items/bitstreams. UMSL archive at https://irl.umsl.edu/salary has older UMSL-only reports back to 1986 (image/PDF).
- **Loaded: 193,293 records**

### [B] University of Missouri campuses, MU Health Care, St. Louis Community College, St. Charles Community College (plus IL universities and MO/IL state govt)  (catalog id 93)

- System/publisher: St. Louis Post-Dispatch Public Pay database
- URL: https://graphics.stltoday.com/apps/payrolls/salaries_2025/
- Format: HTML (agency -> department -> person tables); years: editions salaries_2017 through salaries_2025 (2025 edition = 2024 pay)
- Coverage: UM System, MU Columbia, UMKC, UMSL, Missouri S&T, MU Health Care, St. Louis CC, St. Charles CC (and State of Missouri agencies); employees: full-time employees
- Fields: name, title, department, gross_pay, hire_date
- Access: login/form required: False; terms: not stated (newspaper site; robots.txt disallows master_search queries, crawl-delay 10 for some bots); updates: annual (July); size: UM System office 505 FT; others not counted
- Blocker: HTML only, needs crawl of agency/department pages (URL pattern salaries_YYYY/<agency>_<dept>/); ad-heavy pages; robots disallows search endpoints.
- Notes: Only source found covering St. Louis-area community colleges. Regional universities (Missouri State, UCM etc.) not included.
- **Loaded: 67,792 records**

### [B] Missouri State University (Springfield and West Plains)  (catalog id 94)

- System/publisher: Missouri State University
- URL: https://www.missouristate.edu/FinancialServices/FY27BoardApprovedBudget.htm
- Download: https://www.missouristate.edu/FinancialServices/_Files/FY27OpeartingBudgetDetail.pdf
- Format: PDF; years: annual budget books; FY07 standalone salary PDF; detailed books FY12-FY27 on site
- Coverage: Missouri State University; employees: budgeted faculty and staff positions
- Fields: name, department (salary budget detail section), budgeted_fte_percent, budgeted_salary
- Access: login/form required: False; terms: not stated; updates: annual (June board approval); size: FY27 detailed budget book 11.5 MB
- Blocker: Budget PDF; salary list (Faculty/Staff Salary Budget Summary, alphabetical) is an appendix in a large budget book; budgeted not actual pay; no title in summary list may require joining with dept detail.
- Notes: Contents of FY27 book not opened; structure per FY23 page description.
- **Loaded: 2,187 records**

### [A] State of Missouri executive agencies (incl. Dept of Higher Education & Workforce Development)  (catalog id 95)

- System/publisher: Missouri Open Data / Missouri Accountability Portal
- URL: https://data.mo.gov/d/przm-8aj2
- Download: https://data.mo.gov/resource/przm-8aj2.json (2025); yearly datasets 2007-2025 e.g. nkgr-ek2r (2024)
- Format: CSV / JSON / Socrata API; years: 2007-2025
- Coverage: State agencies only; universities and community colleges are NOT included (only the MDHEWD agency, 374 employees in 2025); employees: state agency employees
- Fields: calendar_year, agency_name, position_title, employee_name, ytd_gross_pay
- Access: login/form required: False; terms: not stated; updates: annual; size: 2024: 72,868 rows (all agencies)
- Notes: Rated A as a data source, but it does not cover colleges; useful only for state higher-ed agency staff.

### [C] Missouri public employers incl. universities  (catalog id 96)

- System/publisher: OpenTheBooks
- URL: https://www.openthebooks.com/missouri-state-employees/
- Format: search-form; years: not verified
- Coverage: not verified; employees: not verified
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions; updates: annual; size: not checked
- Blocker: Search-only, 10,000-row result cap, no export.
- Notes: Not inspected in detail; listed as fallback for regional universities.

**Private institutions / extra:** None found (Washington University in St. Louis, Saint Louis University: 990 only).

**Gaps:** No person-level data found for UCM, SEMO, Truman, Northwest Missouri, Missouri Southern, Missouri Western, Lincoln, Harris-Stowe, or community colleges outside St. Louis (Metropolitan CC, Ozarks Tech, etc.). No bulk machine-readable source for any university.

**State notes:** Downloaded the 8.6 MB UM 2025-26 PDF once to confirm fields (moderate size). data.mo.gov state pay rated A but flagged as not covering institutions; best_rating reflects higher-ed coverage (B).

## Montana (MT)

Systems: Montana University System (University of Montana campuses: Missoula, Montana Tech, UM Western, Helena College; Montana State University campuses: Bozeman, Billings, Northern, Great Falls College; Office of the Commissioner of Higher Education), Community colleges (Flathead Valley, Miles, Dawson - locally governed, under MUS Board of Regents)  
Best rating: **C**. Records loaded: **0**.

### [C] State of Montana employees (SABHRS payroll)  (catalog id 99)

- System/publisher: Montana Department of Administration - State Employee Data dashboard
- URL: https://employeepay.mt.gov/
- Download: https://tableau-ext.mt.gov/#/site/DOA/views/SABHRSStateEmployeeData/EmployeeDataDashboard
- Format: Tableau dashboard (interactive); years: not stated
- Coverage: State agencies on SABHRS; Montana University System campuses run separate payroll (Banner) and are likely NOT included (unverified; dashboard is JavaScript-only); employees: state agency employees
- Fields: name, agency, job_title, pay (exact fields not verified)
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Blocker: Tableau interactive dashboard requires filter interaction; no bulk download confirmed; likely excludes MUS universities.
- Notes: Tableau crosstab export may be possible but was not attempted (interaction/form).

### [C] Montana State University (and possibly other MUS campuses)  (catalog id 100)

- System/publisher: OpenPayrolls (commercial aggregator)
- URL: https://openpayrolls.com/
- Format: HTML per-person pages; years: 2025 seen in search results
- Coverage: Montana State University (individual pages found); others unverified; employees: unverified
- Fields: name, employer, title, pay, year
- Access: login/form required: False; terms: not reviewed (site returned HTTP 403 to automated fetch); updates: unknown; size: unknown
- Blocker: Site blocks automated access (HTTP 403); third-party, per-person pages only, provenance unclear.
- Notes: Existence of 2025 MSU data suggests MSU released a payroll file under public records law; original could be requested from data@montana.edu.

### [C] Montana public employers  (catalog id 101)

- System/publisher: OpenTheBooks
- URL: https://www.openthebooks.com/montana-state-employees/
- Format: search-form; years: not verified
- Coverage: not verified; employees: not verified
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions; updates: annual; size: not checked
- Blocker: Search-only, 10,000-row cap, no export; MUS coverage unverified.
- Notes: Fallback.

### [D] Montana State University  (catalog id 102)

- System/publisher: MSU University Data & Analytics
- URL: https://www.montana.edu/data/facultystaff/salaryinfo.html
- Format: request (email data@montana.edu); aggregate HTML/NetID-restricted benchmarks; years: n/a
- Coverage: MSU Bozeman; employees: individual data by request only; public page shows aggregates by title/discipline
- Fields: name, position_title, employment_dates, salary (on request)
- Access: login/form required: True; terms: Montana public records law; updates: n/a; size: n/a
- Notes: No published person-level list; MSU library guide explicitly states there is no central posting of MUS salaries.

**Private institutions / extra:** None found (Carroll College, Rocky Mountain College, Univ. of Providence: 990 only).

**Gaps:** No official published person-level pay for any MUS campus or community college. MUS operating budgets (mus.edu/data/operating_budgets) are aggregate only. Would require public records requests to MSU, UM, and community colleges.

**State notes:** Did not interact with Tableau dashboard. OpenPayrolls fetch blocked (403); did not retry.

## Nebraska (NE)

Systems: University of Nebraska System (UNL, UNMC, UNO, UNK, IANR/NCTA, System office/ITS), Nebraska State College System (Chadron, Peru, Wayne State), Nebraska community colleges (Central, Metropolitan, Mid-Plains, Northeast, Southeast, Western Nebraska)  
Best rating: **A**. Records loaded: **152,668**.

### [A] University of Nebraska System (all campuses)  (catalog id 109)

- System/publisher: University of Nebraska - Budget and Planning
- URL: https://nebraska.edu/offices/business-finance/budget-and-planning/budgeted-employees-as-of-july-1
- Download: https://docs.nebraska.edu/unop/docs/Business%20and%20Finance/budget-salary/2026-2027/Budgeted%20Employees%20as%20of%20July%201%202026.xlsx (prior years: https://nebraska.edu/offices/business-finance/budget-and-planning/archive , e.g. .../budget-salary/2025-2026/3%20Budgeted%20Employees%20as%20of%20July%201%202025.xlsx)
- Format: XLSX (plus PDF personnel rosters and budget-by-department volumes); years: XLSX FY2022-23 through FY2026-27; budget-by-department PDF volumes back to 2010-11
- Coverage: UNL (City), IANR/NCTA, UNMC, UNO, UNK, UNOP/ITS; employees: employees holding permanently budgeted salary lines (excludes temporary/hourly/student)
- Fields: employee_name, position_title, campus, department, budgeted_annual_salary, salary_from_state_aided_funds, salary_from_other_funds
- Access: login/form required: False; terms: not stated ('available for any member of the public to inspect'); updates: annual (as of July 1); size: FY2027 XLSX 796 KB, ~13,944 rows
- Notes: Header rows (3) precede column headers in XLSX. Budgeted salary, not actual paid. PDF budget-by-department volumes add FTE and job class for older years (2010-2022) - B quality.
- **Loaded: 149,198 records**

### [B] Metropolitan CC, Mid-Plains CC, Southeast CC (plus State of Nebraska agencies, cities, counties)  (catalog id 110)

- System/publisher: Flatwater Free Press Nebraska Salaries Database
- URL: https://salaries.flatwaterfreepress.org/
- Format: HTML (paginated lists, 25 per page); years: 2023-2025 (varies by employer; calendar or fiscal)
- Coverage: Metropolitan Community College, Mid-Plains Community College, Southeast Community College; state agencies (not University of Nebraska or State Colleges); employees: all employees of covered employers
- Fields: name, title, organization, department, total_pay
- Access: login/form required: False; terms: not stated; updates: annual; size: 43,000+ employees in 58 agencies
- Blocker: HTML-only paginated pages; no bulk download.
- Notes: Only person-level source found for Nebraska community colleges. Nonprofit newsroom.
- **Loaded: 3,470 records**

### [C] Nebraska state employees incl. University of Nebraska and State College System office  (catalog id 111)

- System/publisher: OpenTheBooks
- URL: https://www.openthebooks.com/nebraska-state-employees/
- Format: search-form; years: multiple years (to 2024 seen)
- Coverage: State agencies (State Treasurer data), University of Nebraska (records request), Nebraska State College System office seen; employees: all
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions; updates: annual; size: 278,464 records (all employers/years)
- Blocker: Search-only, 10,000-row cap per query, no export.
- Notes: Possible fallback for Chadron/Peru/Wayne State.

**Private institutions / extra:** None found (Creighton, Nebraska Wesleyan, etc.: 990 only).

**Gaps:** Nebraska State College System (Chadron, Peru, Wayne) has no published person-level salary list found (only via OpenTheBooks, unverified). Community colleges Central, Northeast, Western Nebraska not found. University of Nebraska data is budgeted salary only (no actual pay or temp/hourly staff).

**State notes:** Downloaded the 796 KB NU XLSX once to confirm columns. nebraskaspending.gov did not respond (connection failure). Flatwater state-agency list contains no college/university entities (only Coordinating Commission for Postsecondary Education).

## Nevada (NV)

Systems: Nevada System of Higher Education (NSHE): UNLV, UNR, Nevada State University, Desert Research Institute, College of Southern Nevada, Truckee Meadows CC, Western Nevada College, Great Basin College, System Administration  
Best rating: **A**. Records loaded: **0**.

### [A] Nevada System of Higher Education (all institutions; combined file in recent years)  (catalog id 123)

- System/publisher: Transparent Nevada (Nevada Policy Research Institute)
- URL: https://transparentnevada.com/salaries/2025/nevada-system-higher-education-system-administrati/
- Download: CSV via 'Download CSV' button on each employer-year page (file e.g. nevada-system-higher-education-system-administrati-salary-2025.csv); per-campus pages e.g. https://transparentnevada.com/salaries/2021/university-nevada-las-vegas/
- Format: CSV (download) + HTML tables; years: 2009-2025 (per-campus pages 2009-2021; combined 'NSHE Administration' file 2023-2025, which includes UNLV/UNR/DRI presidents, coaches, medical school staff)
- Coverage: UNLV, UNR, Nevada State, DRI, CSN, TMCC, WNC, GBC, NSHE System Administration; employees: all
- Fields: name, job_title, department_employer, base_pay, overtime, other_pay, total_benefits, total_pay, total_pay_and_benefits, notes, year
- Access: login/form required: False; terms: not stated on page reviewed; updates: annual; size: 2025: 20,534 records
- Notes: Third-party (NPRI) site built on public records requests. CSV link is generated by JavaScript (Next.js app); direct URL not captured. In 2023-2025 the 'Department/Employer' column showed '-' in visible rows, so campus may not be identifiable in combined file - verify. 2022 missing from list.

### [C] Nevada public employers incl. NSHE  (catalog id 124)

- System/publisher: OpenTheBooks
- URL: https://www.openthebooks.com/nevada-state-employees/
- Format: search-form; years: not verified
- Coverage: not verified; employees: not verified
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions; updates: annual; size: not checked
- Blocker: Search-only, 10,000-row cap, no export.
- Notes: Fallback only.

**Private institutions / extra:** None found (Touro University Nevada, Roseman: 990 only).

**Gaps:** No official NSHE-published salary file or state open-data dataset found; State of Nevada payroll on Transparent Nevada/open.nv.gov covers state agencies, not NSHE. Campus identification in 2023-2025 combined NSHE file uncertain; 2022 NSHE file not listed.

**State notes:** Relied on Transparent Nevada as best source despite being third-party, since it offers per-year CSVs. Did not download CSVs.

## New Hampshire (NH)

Systems: University System of New Hampshire (UNH, Plymouth State, Keene State, Granite State College/UNH Manchester), Community College System of New Hampshire (7 colleges: Great Bay, Lakes Region, Manchester, Nashua, NHTI, River Valley, White Mountains)  
Best rating: **C**. Records loaded: **0**.

### [C] State of New Hampshire employees (possibly incl. CCSNH; USNH unlikely)  (catalog id 112)

- System/publisher: TransparentNH - State Employee Pay Search (Dept. of Administrative Services)
- URL: https://www.nh.gov/transparentnh/search/
- Download: Calendar-year .xls/.xlsx downloads linked from the search page (URLs not captured; site returned HTTP 403 to automated requests)
- Format: XLS/XLSX download + search-form; years: Calendar year 2012-present (per search snippet)
- Coverage: State agencies on state payroll; whether CCSNH or USNH are included is unverified (both are separate bodies corporate with own payroll, so likely excluded); employees: state employees
- Fields: agency, employee_name, job_title, pay_type, pay_amount, year
- Access: login/form required: False; terms: not stated (could not load page); updates: annual files; search updated periodically; size: not stated
- Blocker: nh.gov returns HTTP 403 to automated access; higher-ed coverage unverified and probably absent.
- Notes: If CCSNH appears in the agency list it would be A-quality bulk XLSX; recheck with a normal browser.

### [C] University of New Hampshire, Keene State, Plymouth State (USNH) and Community College System of NH  (catalog id 113)

- System/publisher: OpenTheBooks
- URL: https://www.openthebooks.com/new-hampshire-state-employees/
- Format: search-form; years: 2017-2024 for USNH (source: University System of New Hampshire); CCSNH 2021-2022 seen
- Coverage: UNH, Keene State, Plymouth State (USNH); CCSNH; employees: all
- Fields: year, employer, name, title, annual_wages, source
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions; updates: annual; size: not checked
- Blocker: Search-only, 10,000-row cap per query, no export; third-party.
- Notes: Only person-level source found for USNH; implies USNH releases a payroll file on request (Right-to-Know Law).

### [D] USNH 'Salary Book'  (catalog id 114)

- System/publisher: University System of New Hampshire
- URL: https://www.usnh.edu/
- Format: unknown; years: unknown
- Coverage: USNH; employees: unknown
- Fields: 
- Access: login/form required: False; terms: not stated; updates: unknown; size: unknown
- Notes: Many SEO-spam pages reference a 'USNH Salary Book 2023/2024', but no official usnh.edu page was found (probed URLs 404). Historically USNH printed a salary book available in libraries/on request; existence of a current public online copy unconfirmed.

**Private institutions / extra:** None found (Dartmouth, SNHU, Saint Anselm: 990 only).

**Gaps:** No official online person-level pay for USNH or CCSNH found. TransparentNH could not be inspected (403). Would need Right-to-Know requests or manual browser check of TransparentNH agency list.

**State notes:** Did not attempt to bypass nh.gov 403. Rated TransparentNH C because higher-ed coverage is unverified.

## New Jersey (NJ)

Systems: Rutgers University (incl. RBHS), NJIT, Rowan University, State colleges/universities: Montclair State, Kean, William Paterson, NJCU, Ramapo, TCNJ, Stockton, Thomas Edison State, 19 county community colleges (Bergen, Brookdale, Camden, Essex, Hudson, Mercer, Middlesex, Morris, Ocean, Passaic, Raritan Valley, Rowan College at Burlington/Gloucester, Salem, Sussex, Union, Warren, Atlantic Cape, etc.)  
Best rating: **A**. Records loaded: **12,922**.

### [A] All NJ public universities and county colleges (pension-enrolled employees only)  (catalog id 115)

- System/publisher: NJ YourMoney - Active Pension Members (Division of Pensions & Benefits / Treasury)
- URL: https://data.nj.gov/d/44xg-bswk
- Download: https://data.nj.gov/api/views/44xg-bswk/rows.csv?accessType=DOWNLOAD (SODA: https://data.nj.gov/resource/44xg-bswk.json)
- Format: CSV / JSON / Socrata API; years: current snapshot (as_of_date 2026-06-30; salary = four most recent reported quarters); no history in this dataset
- Coverage: Rutgers (5,393), Rowan (1,074), Montclair State (639), Stockton (577), TCNJ (382), NJIT (365), William Paterson (362), Kean (334), NJCU (312), Ramapo (213), Thomas Edison (69), University Hospital (3,149), and all county community colleges (e.g. Bergen 320, Middlesex 331, Essex 296, Hudson 225, Camden 220); employees: members of state pension systems (PERS, TPAF, PFRS etc.) only - excludes Alternate Benefit Program (ABP) members, i.e. most faculty and professional staff
- Fields: as_of_date, member_last_name, member_first_name, member_mi, enrollment_date, employer_name, location_code, location_name, pension_fund_name, pension_group_name, veteran_status, service_years_qty, service_months_qty, current_employer_salary_amt, all_employers_salary_amt, membership_tier
- Access: login/form required: False; terms: not stated (data.nj.gov open data); updates: periodic (updated 2026-09-21); size: 400,716 rows (all public employers statewide)
- Notes: Clean and loadable but partial: no job title or department, and excludes ABP faculty. Filter by employer_name. Retired members in separate dataset nma7-ti96.
- **Loaded: 12,922 records**

### [A] State of New Jersey agencies (Centralized Payroll)  (catalog id 116)

- System/publisher: NJ YourMoney - Agency Payroll
- URL: https://data.nj.gov/d/iqwc-r2w7
- Download: https://data.nj.gov/resource/iqwc-r2w7.json
- Format: CSV / JSON / Socrata API; years: 2010-2026 (quarterly)
- Coverage: State agencies only; colleges/universities are NOT included (only 'Commission on Higher Education' / Office of Secretary of Higher Education staff); employees: state agency employees
- Fields: calendar_year, calendar_quarter, full_name, original_employment_dte, salary_hourly_rate, master_department_agency_desc, master_section_desc, master_title_desc, master_ytd_regular_pay, master_ytd_overtime_payments, master_ytd_all_other_payments, master_ytd_earnings, record_type
- Access: login/form required: False; terms: not stated; updates: quarterly; size: 2,842,265 rows
- Notes: Does not cover institutions; listed for completeness. Authority Payroll (kiki-imre) includes HESAA and Educational Facilities Authority only.

### [C] Rutgers University (and state govt, authorities, local govts)  (catalog id 117)

- System/publisher: Asbury Park Press DataUniverse
- URL: https://www.app.com/data/
- Format: search-form; years: through ~2021+ (Rutgers updated Feb 2022)
- Coverage: Rutgers (full payroll incl. non-pension staff); other universities via pension data; employees: all (Rutgers)
- Fields: name, employer, title, salary, year
- Access: login/form required: True; terms: subscriber-only (site returned HTTP 402 Payment Required); updates: irregular; size: not stated
- Blocker: Paywalled (subscriber-only) search interface; no download.
- Notes: Not inspected beyond paywall.

### [C] NJ public employers incl. Rutgers and state universities  (catalog id 118)

- System/publisher: OpenTheBooks / OpenPayrolls
- URL: https://www.openthebooks.com/new-jersey-state-employees/
- Format: search-form / per-person HTML; years: not verified (OpenPayrolls shows Rowan 2025)
- Coverage: not verified; employees: not verified
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: site terms; updates: annual; size: not checked
- Blocker: Search-only, 10,000-row cap, no export; OpenPayrolls blocks automated access.
- Notes: Fallback for full-payroll (incl. ABP faculty) data.

**Private institutions / extra:** None found (Princeton, Seton Hall, Stevens, FDU: 990 only).

**Gaps:** No official full-payroll (incl. faculty/ABP members, with titles) publication for any NJ public university or county college. Pension dataset lacks titles/departments and historical snapshots. Full data requires OPRA requests.

**State notes:** Found pension dataset via data.nj.gov catalog; it's the only official open source with names + salary for NJ higher-ed, but coverage skews to staff. Rated A on format, flagged partial coverage.

## New Mexico (NM)

Systems: University of New Mexico (incl. branch campuses, HSC), New Mexico State University (incl. branches), New Mexico Highlands University, New Mexico Tech, Eastern New Mexico University, Western New Mexico University, Northern New Mexico College, Community colleges (CNM, San Juan College, Santa Fe CC, Clovis CC, NM Junior College, Luna CC, Mesalands CC, etc.)  
Best rating: **A**. Records loaded: **13,549**.

### [A] University of New Mexico  (catalog id 119)

- System/publisher: UNM Sunshine Transparency Portal - Salary Book
- URL: https://sunshine.unm.edu/salary-book/index.php
- Download: https://sunshine.unm.edu/cache/salary-book.json
- Format: JSON (DataTables ajax feed) + HTML; years: current fiscal year snapshot only (FY July-June; refreshed monthly on the 5th)
- Coverage: UNM (main campus, HSC, branches - primary positions); employees: all employees with a primary position (faculty, staff, residents, temp part-time faculty)
- Fields: name, department, grade, job_title, position_type (Primary), appointment_percent, annual_salary
- Access: login/form required: False; terms: not stated (robots.txt allows); updates: monthly; size: 1.1 MB JSON (Last-Modified 2026-10-06)
- Notes: Array-of-arrays JSON, salary as formatted string ('$68,800'). No history: archive by pulling monthly/annually going forward. Only primary position salary.
- **Loaded: 10,676 records**

### [B] New Mexico Highlands University  (catalog id 120)

- System/publisher: NMHU Salary Report
- URL: https://www.nmhu.edu/aur/salary-report/
- Download: https://www.nmhu.edu/wp-content/uploads/2025/12/FY26-NMHU-Salary-Report.pdf (also FY25: /2024/11/NMHU-Salary-Report-FY25.pdf, FY24: /2023/11/NMHU-Salary-Report-FY24.pdf, FY23: /2023/03/NMHU-Salary-Report-3.1.23-1.pdf)
- Format: PDF (text tables); years: FY2023-FY2026
- Coverage: NMHU; employees: all salaried employees
- Fields: first_name, last_name, fte, position, annual_salary, department (truncated to ~30 chars)
- Access: login/form required: False; terms: not stated; updates: annual; size: FY26 PDF 148 KB, 14 pages
- Blocker: PDF only; small, clean text-extractable table but department text truncated.
- Notes: Page cites NM Senate Bill 195 as the posting requirement - other NM institutions may have similar postings not found in this search.
- **Loaded: 2,873 records**

### [C] New Mexico public employers incl. universities/colleges (sourced from NM ERB/PERA retirement data)  (catalog id 121)

- System/publisher: OpenTheBooks
- URL: https://www.openthebooks.com/new-mexico-state-employees/
- Format: search-form; years: to 2024 seen
- Coverage: NM Tech record seen (source: state retirement system); likely all ERB-covered higher-ed employers; employees: retirement-system members
- Fields: year, employer, name, title, annual_wages, source
- Access: login/form required: True; terms: OpenTheBooks Terms & Conditions; updates: annual; size: not checked
- Blocker: Search-only, 10,000-row cap, no export; third-party.
- Notes: Possible fallback for NMSU, NM Tech, ENMU, WNMU, community colleges.

### [D] State of New Mexico executive agencies (SHARE payroll)  (catalog id 122)

- System/publisher: New Mexico Sunshine Portal (DFA/GSD)
- URL: https://www.sunshineportalnm.com/
- Format: search-form; years: calendar-year gross pay (years not verified)
- Coverage: State agencies in SHARE; universities and colleges run separate payroll and are not included; employees: state agency employees (names of rank-and-file were court-ordered removed in 2012 per Albuquerque Journal; current status unverified)
- Fields: name, position, organization, hire_date, status, salary, gross_pay
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Notes: SSL handshake failure on fetch; no higher-ed coverage. Listed for completeness.

**Private institutions / extra:** None found (St. John's College, Navajo Technical University (tribal), etc.: 990 only).

**Gaps:** No published person-level salary data found for NMSU, NM Tech, ENMU, WNMU, NNMC, or community colleges (CNM, San Juan, Santa Fe CC...). UNM data is current snapshot only with no historical archive. A statewide higher-ed source does not exist; NM ERB data (via OpenTheBooks) is the only cross-institution option.

**State notes:** UNM JSON endpoint discovered in page's DataTables config; HEAD + 600-byte range read only. Downloaded 148 KB NMHU PDF to confirm fields. Another process had deleted a shared venv in the scratchpad; created a separate one (venv_mnm9).

## North Carolina (NC)

Systems: University of North Carolina System (17 institutions + System Office), North Carolina Community College System (58 colleges)  
Best rating: **C**. Records loaded: **0**.

### [C] UNC System Office and all constituent institutions  (catalog id 103)

- System/publisher: University of North Carolina System
- URL: https://uncdm.northcarolina.edu/salaries/index.php
- Format: search-form (HTML results); years: Current quarterly snapshot only (page states data current as of September 30, 2026)
- Coverage: UNC System Office plus the 16 universities and NC School of Science and Math; excludes UNC Health Care and UNC Press; employees: permanent employees (faculty, SHRA and EHRA staff); temporary employees not included
- Fields: name, institution, department, position_title, salary, snapshot_date
- Access: login/form required: True; terms: not stated; page says the data is a point-in-time snapshot and may not reflect all funding sources; updates: quarterly; size: not stated (roughly 50,000+ permanent employees system-wide, estimate)
- Blocker: Gated behind a POSTed 'Click to Access' agreement form, then search-driven results; no published bulk file. Not submitted per instructions.
- Notes: Best and only official system-wide source. The gate is just a click-through (button name=action value=agree, POST to index.php), so if clicking through is acceptable this probably becomes a scrapable B (results tables by campus). The UNC Health Sciences Library FAQ says results for individual departments can be downloaded, which I could not verify without passing the gate. No historical snapshots exposed on the landing page.

### [D] State agencies paid through NC Integrated HR-Payroll System  (catalog id 104)

- System/publisher: State of North Carolina (Office of the State Controller)
- URL: https://ncosc.gov/salary_database
- Format: search-form; years: current monthly snapshot
- Coverage: none of the universities or community colleges (explicitly excluded); employees: state agency employees only
- Fields: name, agency, job_title, position_title, salary
- Access: login/form required: False; terms: see https://www.ncosc.gov/disclaimer-terms-use; updates: monthly (first business day); size: not stated
- Notes: Listed only to record that it does NOT cover higher ed: page says community college employees and university employees are not paid through the system.

### [C] Statewide aggregator (multiple NC public employers)  (catalog id 105)

- System/publisher: OpenTheBooks (nonprofit)
- URL: https://www.openthebooks.com/north-carolina-state-employees/
- Format: search-form; years: unknown (could not load)
- Coverage: unknown; employees: unknown
- Fields: 
- Access: login/form required: True; terms: not stated; updates: unknown; size: unknown
- Blocker: Site returns HTTP 403 with a bot 'Client Challenge' page; search-only, no bulk download.
- Notes: Third-party; not verified.

**Private institutions / extra:** None found. Duke, Wake Forest, Davidson etc. publish only IRS 990 compensation.

**Gaps:** No bulk file or API for the UNC System; only the current quarterly snapshot, no history; no pay beyond base salary (no overtime/other/total pay). No published person-level pay for the 58 community colleges (excluded from the state OSC database; would require public records requests to each college). The News & Observer / Charlotte Observer 'UNC System Workers' salary database is mentioned by a UNC library FAQ but appears paywalled/stale and I could not confirm a current URL.

**State notes:** Did not submit the UNC click-through form, per the no-forms rule, so rated C even though it is probably the best NC source. Did not try individual campus HR sites because all UNC campuses feed the system database. OpenTheBooks blocked by an anti-bot challenge; I recorded it and did not attempt to bypass.

## North Dakota (ND)

Systems: North Dakota University System (NDUS: 11 institutions incl. UND, NDSU, and the 2-year colleges BSC, LRSC, WSC, NDSCS, DCB)  
Best rating: **C**. Records loaded: **0**.

### [C] All state agencies and all NDUS institutions  (catalog id 106)

- System/publisher: State of North Dakota OMB Financial Transparency portal
- URL: https://www.omb.nd.gov/financial-transparency/dashboards/employee-compensation-dashboard
- Download: https://cognospubrep.nd.gov/Analytics/bi/?perspective=dashboard&pathRef=.public_folders%2FPublic+Reporting%2FNew+Transparency+Website%2FEmployee+Compensation&ui_appbar=false&ui_navbar=false&action=view&mode=dashboard
- Format: IBM Cognos Analytics dashboard (JavaScript BI app); years: last ten fiscal years (per help page), monthly detail
- Coverage: All NDUS campuses (universities and 2-year colleges) plus state agencies; excludes Bank of ND, Mill & Elevator, Roughrider Industries, Housing & Finance; employees: all paid through PeopleSoft payroll (full-time, temporary, overtime split by expense type); some names redacted for safety
- Fields: agency_or_university, position_description, payroll_amount, expense_type (full-time salary / temporary salary / overtime), fiscal_year, month, employee_name (uncertain: help page describes the table as 'by agency and position')
- Access: login/form required: False; terms: not stated on dashboard; OMB site has a Disclaimer page; updates: monthly (mid-month; June data at end of July); size: not stated
- Blocker: Data only reachable through an interactive Cognos dashboard (filters limited to first 100 options); no published bulk payroll file or documented API.
- Notes: Official and covers every public college in ND, including 2-year colleges, with total pay by type, which is good content. Cognos loaded anonymously (HTTP 200) but renders client-side; Cognos sometimes allows per-widget CSV export or a REST call underneath, which could be explored with a browser to lift it to B. Could not confirm whether employee names are shown.

### [D] All state agencies and NDUS  (catalog id 107)

- System/publisher: State of North Dakota OMB Mass Download (checkbook)
- URL: https://www.omb.nd.gov/financial-transparency/dashboards/mass-download
- Download: https://www.omb.nd.gov/sites/default/files/documents/financial-transparency/transparency/mass_download_fy26.xlsx
- Format: XLSX; years: FY2010-FY2027
- Coverage: state agencies and NDUS; employees: n/a (vendor payments; payroll inclusion not confirmed)
- Fields: agency, vendor, account_description, amount, date (presumed)
- Access: login/form required: False; terms: not stated; updates: monthly; size: FY2026 39MB; FY2025 22MB; FY2027 to date 6MB
- Notes: Bulk checkbook (expenditure) files, described as 'detailed checkbook data'; almost certainly vendor payments, not person-level payroll. Not downloaded (large). Recorded in case payroll lines turn out to be included; if they are, this would be an A.

### [C] NDUS institutions (aggregated)  (catalog id 108)

- System/publisher: OpenPayrolls (third-party)
- URL: https://openpayrolls.com/state/north-dakota/2025
- Format: HTML; years: 2017-2026 per search results
- Coverage: NDSU, UND, NDUS Core Technology Services, others; employees: all (as republished from state records)
- Fields: name, employer, title, pay, year
- Access: login/form required: True; terms: not stated; updates: unknown; size: unknown
- Blocker: Cloudflare blocks automated requests (HTTP 403 'Sorry, you have been blocked'); third-party, HTML only.
- Notes: Its existence suggests the state data does include names; likely derived from the OMB portal or a records request.

**Private institutions / extra:** None. ND has very few private colleges (University of Mary, University of Jamestown); none found publishing pay beyond IRS 990.

**Gaps:** No clean bulk download of person-level higher-ed payroll. The official Cognos dashboard covers all NDUS institutions, including community colleges, but is interactive only and may not show names. Tribal colleges are not state institutions and are not covered.

**State notes:** Rated the OMB Cognos dashboard C, not B, because it is a JS BI tool rather than scrapable HTML. Did not download the 22-39MB checkbook XLSX files to check for payroll rows, per the no-large-downloads rule. OpenPayrolls was blocked by Cloudflare; not bypassed.

## Oklahoma (OK)

Systems: Oklahoma State System of Higher Education (State Regents), University of Oklahoma (incl. OU Health Sciences Center), Oklahoma State University / OSU A&M system, Regional University System of Oklahoma (RUSO), Oklahoma community colleges (OCCC, TCC, Rose State, etc.), Oklahoma Career and Technology Education  
Best rating: **A**. Records loaded: **394,645**.

### [A] All public colleges and universities that report payroll to OMES, plus state agencies  (catalog id 134)

- System/publisher: State of Oklahoma Payroll (OMES) on data.ok.gov (CKAN)
- URL: https://data.ok.gov/dataset/state-of-oklahoma-payroll-fiscal-year-2026
- Download: Monthly CSVs, e.g. https://data.ok.gov/dataset/ca31c294-6084-4bf2-a466-ab11356bd0dc/resource/55dd61f7-a7d5-4a6b-a3ab-fcfab6110933/download/payroll_public_202607.csv ; API: https://data.ok.gov/api/3/action/datastore_search?resource_id=<id> and datastore_search_sql (both work anonymously); dataset list: https://data.ok.gov/api/3/action/package_search?q=payroll
- Format: CSV (monthly files) + CKAN Datastore API (JSON, SQL); years: 2010 (Q3) through FY2027 to date (July 2026); calendar-year datasets 2010-2020, fiscal-year datasets FY2021-FY2027
- Coverage: Verified in the July 2026 file: University of Oklahoma, OU Health Sciences Center, Oklahoma State University, UCO, NSU, Cameron, East Central, SE and SW Oklahoma State, Northwestern OSU, Panhandle State, Langston, Rogers State, USAO, OCCC, Tulsa CC, Rose State, Seminole State, Carl Albert, Connors, Eastern OSC, Redlands CC, Murray State, NEO A&M, Northern Oklahoma College, Western Oklahoma SC, State Regents, RUSO, OSSM, University Center at Ponca City, CareerTech. 147 agencies in total.; employees: all paid employees (person-level monthly payments)
- Fields: REPORT_DATE, AGENCY_NUMBER, AGENCY_NAME, LAST_NAME, FIRST_INITIAL, MIDDLE_INITIAL, HOURS, AMOUNT, CHECK_DATE, ACCOUNT, ACCOUNT_DESCRIPTION (pay type, e.g. 'Sals-H.Ed Non-Prof. Pay'), UPDATE_DATE
- Access: login/form required: False; terms: Creative Commons Attribution (license on dataset); updates: monthly (after the 15th of the following month); size: about 19-27 MB per monthly CSV; about 174,000 rows in the July 2026 file; FY2026 has 13 monthly files
- Notes: Best source for OK. Caveats: NO job title or department; the name is last name plus initials only; rows are payment lines by account/pay type, so annual pay per person has to be summed and the person reconstructed from agency + last name + initials, which is ambiguous for common names. Amounts include overtime/longevity/terminal pay and exclude employer FICA/retirement. Early years (2010-2020) are quarterly CSVs. One agency is misspelled ('ROSE STATE COLEGE').
- **Loaded: 394,645 records**

### [C] Oklahoma state employees incl. OU, OSU, OUHSC  (catalog id 135)

- System/publisher: OpenTheBooks (third-party)
- URL: https://www.openthebooks.com/oklahoma-state-employees/
- Format: search-form / HTML; years: multiple years (805,265 salary records per search snippet)
- Coverage: state agencies and universities; employees: all
- Fields: year, employer, name, title (often blank), annual_wages, source
- Access: login/form required: True; terms: not stated; updates: unknown; size: 805,265 records (stated)
- Blocker: Anti-bot 'Client Challenge' (HTTP 403) on automated requests; derived from the same OMES data, so it adds little.
- Notes: Not needed given the OMES CKAN source.

### [D] Oklahoma public universities (FY2019)  (catalog id 136)

- System/publisher: Oklahoma Watch university salary database
- URL: https://oklahomawatch.opalstacked.com/university-salaries/about
- Format: search-form; years: FY2019 (July 2018-June 2019)
- Coverage: colleges and universities reporting to OMES; employees: all
- Fields: name, institution, pay
- Access: login/form required: False; terms: not stated; updates: one-time; size: unknown
- Notes: Host no longer resolves (DNS ENOTFOUND). It was built from OMES payroll data. Stale/offline.

**Private institutions / extra:** None found; University of Tulsa, Oklahoma City University, ORU, OBU and others publish only IRS 990 data.

**Gaps:** No job titles or departments in the official payroll data; a title roster would need university HR sources or records requests (OU and OSU do not appear to post salary lists). Branch campuses (OSU-Tulsa, OSU-OKC, OSU-IT Okmulgee, OU-Tulsa) appear to be rolled into parent agency numbers rather than broken out; not verified per campus. Technology center districts (CareerTech local districts) are not in the state payroll.

**State notes:** Verified fields, row count and higher-ed agency list with the CKAN datastore_search and datastore_search_sql APIs (small aggregate queries only, no bulk download). Rated A despite missing titles because it is bulk, official, multi-year and API-accessible.

## Oregon (OR)

Systems: Seven independent public universities with their own boards (UO, OSU, PSU, OIT, SOU, WOU, EOU), coordinated by the Higher Education Coordinating Commission (HECC), 17 independent community college districts (PCC, Lane, Chemeketa, Mt. Hood, etc.)  
Best rating: **C**. Records loaded: **0**.

### [D] Oregon state agencies (not universities or community colleges)  (catalog id 137)

- System/publisher: State of Oregon Transparency / DAS on data.oregon.gov (Socrata)
- URL: https://data.oregon.gov/dataset/4cmg-5yp4
- Download: https://data.oregon.gov/api/views/4cmg-5yp4/rows.csv?accessType=DOWNLOAD ; API https://data.oregon.gov/resource/4cmg-5yp4.json
- Format: CSV / Socrata API; years: multi-year (fiscal years; updated 2026-09-22)
- Coverage: state agencies only; no university or community college agencies matched 'UNIV', 'COLLEGE' or 'HIGHER' (HECC is a state agency and may appear under another name); employees: state agency employees
- Fields: fiscal_year, agency_title, classification, annual_salary, full_part_time, service_type, agency
- Access: login/form required: False; terms: Public Domain U.S. Government (as tagged); updates: annual; size: 496,398 rows
- Notes: Does not help: it has NO employee names and does not cover universities (independent since 2014) or community colleges (local districts). Recorded so it is not re-checked.

### [D] University of Oregon  (catalog id 138)

- System/publisher: UO Office of Public Records request log
- URL: https://publicrecords.uoregon.edu/content/compensation-data-0
- Format: HTML (request log entries only); years: n/a
- Coverage: University of Oregon; employees: n/a
- Fields: 
- Access: login/form required: True; terms: not stated; updates: n/a; size: n/a
- Notes: The public log shows that full payroll files (name, title, department, salary) have been released to requesters (e.g. 2019-269, 2025-519), but the released files are not posted. You would need your own public records request (a form/email, possibly with fees).

### [C] Oregon public universities and state agencies (UO, OSU, PSU, etc.)  (catalog id 139)

- System/publisher: OpenTheBooks (third-party)
- URL: https://www.openthebooks.com/oregon-state-employees/
- Format: search-form / HTML (shows top 10,000 results); years: multi-year incl. 2025 (558,282 salary records per search snippet)
- Coverage: state agencies plus UO, OSU, PSU (some rows from OpenTheBooks' own open-records requests); employees: all
- Fields: year, employer, name, title, annual_wages
- Access: login/form required: True; terms: not stated; updates: unknown; size: 558,282 records (stated)
- Blocker: Anti-bot 'Client Challenge' (HTTP 403) on automated requests; search results capped at 10,000 rows; no bulk download.
- Notes: The only person-level source found that covers Oregon universities; third-party, built from records requests.

**Private institutions / extra:** None found; Reed College, Lewis & Clark, Willamette and University of Portland publish only IRS 990 data.

**Gaps:** No official published person-level pay for any Oregon public university or community college. The state DAS salary dataset has no names and excludes higher ed. Getting real data means public records requests to each of the 7 universities and 17 community colleges (UO's log shows it routinely releases payroll spreadsheets). No news-organization salary database found (Oregonian, Statesman Journal, Salem Reporter).

**State notes:** Did not check each of the 7 universities' and 17 community colleges' HR sites individually: searches turned up no posted salary lists, and UO's public records site shows the data is handled only by request. Rated OpenTheBooks C because it is blocked to automated access.

## Rhode Island (RI)

Systems: Rhode Island public higher education (Council on Postsecondary Education / Office of the Postsecondary Commissioner): University of Rhode Island, Rhode Island College, Community College of Rhode Island  
Best rating: **A**. Records loaded: **0**.

### [A] University of Rhode Island, Rhode Island College, Community College of Rhode Island, Office of Higher Education, plus all state agencies  (catalog id 145)

- System/publisher: State of Rhode Island Transparency Portal - RI State Employee Payroll
- URL: https://transparency.ri.gov/payroll/
- Download: https://transparency.ri.gov/payroll/sendtocsvall.php
- Format: CSV (single 'complete list' export, all years in one file; served as application/vnd.ms-excel with a .csv filename); years: FY2011-FY2026 (FY2026 partial; page says last updated October 9, 2025)
- Coverage: Department values include 'U R I', 'R I COLLEGE', 'COMMUNITY COLLEGE OF R I', 'HIGHER EDUCATION', 'STATE COLLEGES', 'RIHEAA', and all executive, judicial and legislative agencies; employees: all state-paid employees (classified and non-classified), including terminated employees with a termination date
- Fields: fiscal_year, last, first, m (middle initial), department, title, regular, overtime, other, total, annual (annual salary), termination
- Access: login/form required: False; terms: not stated; updates: quarterly in principle; stalled since 2025-10-09 during the state's payroll-system transition (per Rhode Island Current, Sept 2026); size: not stated (streamed, chunked; likely tens of MB covering about 16 fiscal years)
- Notes: Excellent: one GET returns every year, with regular/overtime/other/total split and annual salary. Checked with a HEAD request and by reading the first 1.5KB only. Caveats: many faculty and professional staff carry the generic title 'NON CLASSIFIED' instead of a real job title; there is no department below agency level (e.g. just 'U R I'); the CSV uses comma-plus-space delimiters with a trailing comma. Data is stale after Oct 2025; newer payroll is available only by APRA request. robots.txt names only Googlebot and archive bots, so not restrictive.

### [D] RI state employees (2010-2011)  (catalog id 146)

- System/publisher: RIOpenGov.org (Ocean State Policy Research Institute)
- URL: https://www.golocalprov.com/news/new-riopengov.org-make-ri-state-workers-salaries-public-online
- Format: search-form; years: 2010-2011
- Coverage: state employees incl. higher ed; employees: all
- Fields: name, agency, title, pay
- Access: login/form required: False; terms: not stated; updates: none (historical); size: unknown
- Notes: Historical only and superseded by the official portal. Not checked further.

**Private institutions / extra:** None found; Brown University, Providence College, Bryant, RISD etc. publish only IRS 990 data.

**Gaps:** Official file not refreshed since 2025-10-09 (FY2026 incomplete; nothing for FY2027 yet). Generic 'NON CLASSIFIED' titles for most faculty and non-classified staff. No department/college detail inside each institution.

**State notes:** Only three public institutions, all covered by the one statewide file, so I did not look for separate campus sources.

## South Carolina (SC)

Systems: SC public senior institutions (USC system, Clemson, College of Charleston, MUSC, Winthrop, Coastal Carolina, SC State, The Citadel, Francis Marion, Lander), each with its own board, overseen by the SC Commission on Higher Education, SC Technical College System (16 technical colleges)  
Best rating: **B**. Records loaded: **20,264**.

### [B] All state agencies, colleges and universities under DSHR oversight (USC campuses, Clemson, CofC, MUSC, Winthrop, Coastal, SC State, Citadel, Francis Marion, Lander, all 16 technical colleges)  (catalog id 147)

- System/publisher: SC Department of Administration - State Salaries Query
- URL: https://admin.sc.gov/transparency/state-salaries
- Download: Paged HTML via GET: https://admin.sc.gov/transparency/state-salaries?agency=All&job=All&firstname=&lastname=&page=N (N = 0..1800)
- Format: HTML table (Drupal view, 25 rows per page, about 1,800 pages, so roughly 45,000 rows); years: current fiscal year only (page says last updated September 16, 2026)
- Coverage: all public 4-year institutions and technical colleges (e.g. 'AIKEN TECHNICAL COLLEGE' in the agency list); excludes MUSC Hospital Authority and a list of legislative/judicial bodies; employees: FTE employees earning $50,000 or more (by FOIA rule; lower pay is released only in ranges)
- Fields: last_name, first_name, agency, job_title, total_compensation, bonuses
- Access: login/form required: False; terms: not stated; disclaimer that Admin cannot guarantee accuracy, and that the data 'should not be used for comparison purposes'; updates: periodic (several times a year; last update 2026-09-16); size: about 45,000 rows (estimated from 1,800 pages x 25)
- Blocker: No bulk download; current year only; must page through about 1,800 HTML pages (plain GET, no form POST or CAPTCHA), and employees under $50k are omitted.
- Notes: Clean, consistent HTML table that is easy to scrape politely. For colleges and universities, 'total compensation does not include all types of pay and bonuses'; university staff who are dually employed with other agencies are excluded. No department field. Total compensation = annual salary or year-to-date actual earnings, whichever is greater. Search results mention older cached versions that offered a downloadable file of salaries over $50,000; none is linked now. No history, so snapshots would have to be taken over time.
- **Loaded: 20,264 records**

### [C] SC state employees incl. universities  (catalog id 148)

- System/publisher: The State (Columbia) newspaper salary database
- URL: https://www.thestate.com/ (state salary database article, syndicated via AOL: 'How much do certain SC state employees get paid? Check out our state salary database')
- Format: search-form (embedded); years: current
- Coverage: same as the state data; employees: $50,000+
- Fields: name, agency, title, total_compensation
- Access: login/form required: True; terms: not stated; updates: periodic; size: unknown
- Blocker: Newspaper site blocked to our fetcher and likely paywalled; it republishes the official Admin data.
- Notes: Redundant with the official source.

**Private institutions / extra:** None found; Furman, Wofford, Presbyterian etc. publish only IRS 990 data.

**Gaps:** No bulk file; no history (current snapshot only); employees under $50k listed only as ranges or omitted; college pay excludes some pay types; no department field. MUSC Hospital Authority not included.

**State notes:** Used plain GET pagination of the Drupal view (one test page fetched). This is a URL query, not a form submission, so it is rated B rather than C. Did not look at individual campus sites because the state query covers all of them.

## South Dakota (SD)

Systems: South Dakota Board of Regents (6 universities: USD, SDSU, SD Mines, NSU, DSU, BHSU, plus 2 special schools), South Dakota Board of Technical Education (4 technical colleges: Lake Area, Mitchell, Southeast, Western Dakota)  
Best rating: **C**. Records loaded: **0**.

### [C] State employees (Board of Regents institutions likely included; not verified)  (catalog id 149)

- System/publisher: Open SD (Bureau of Finance and Management) - Payroll > Employee Salaries
- URL: https://open.sd.gov/
- Format: search-form (ASP.NET pages); years: current ('constantly updated' from the state payroll system)
- Coverage: state agencies; whether Board of Regents universities appear could not be verified; technical colleges are probably not included (they are not on state payroll); employees: individual state employees
- Fields: name, agency, title, salary (expected; not verified)
- Access: login/form required: True; terms: see http://sd.gov/disclaim.aspx; robots.txt is 'User-agent: * Disallow: /'; updates: continuous / frequent (per site); size: not stated
- Blocker: robots.txt disallows all crawling of open.sd.gov, and the salaries tool is an interactive ASP.NET search; no bulk file found.
- Notes: The home page says users can review 'salaries of individual state employees'. Because of the robots.txt Disallow-all I did not open the salaries page (only the home page was fetched once, before reading robots). A bulk extract would likely need a records request to BFM. A separate Executive Salaries page (https://open.sd.gov/executive_salaries.aspx, statutory list under SDCL 4-7-10.1, May 18, 2026 snapshot) lists only top executives, e.g. the BOR Executive Director.

### [D] South Dakota Board of Regents  (catalog id 150)

- System/publisher: SDBOR Human Resources
- URL: https://sdbor.edu/departments/human-resources/classification-and-compensation/
- Format: HTML/PDF; years: current
- Coverage: BOR system; employees: n/a (pay grade ranges only)
- Fields: grade, min, max
- Access: login/form required: False; terms: not stated; updates: annual; size: n/a
- Notes: Only salary ranges, no person-level data. The BOR personnel manual says name, title, salary, institution and department number may be released on request.

### [D] SD state budget (aggregate)  (catalog id 151)

- System/publisher: Open Budget (Tyler/Socrata) southdakota.budget.socrata.com
- URL: https://southdakota.budget.socrata.com/
- Format: interactive budget app; years: multi-year
- Coverage: all state budget units incl. BOR; employees: n/a
- Fields: budget, actuals by object
- Access: login/form required: False; terms: not stated; updates: annual; size: n/a
- Notes: Aggregate budget/spending only, not payroll by person.

**Private institutions / extra:** None found; Augustana, University of Sioux Falls, Dakota Wesleyan, Mount Marty publish only IRS 990 data.

**Gaps:** No downloadable or crawlable person-level higher-ed pay. Open SD is the only official listing and it forbids crawling. Technical colleges (governed via local school districts / Board of Technical Education) have no published pay lists. No news-org salary database found (Argus Leader, SD Searchlight).

**State notes:** Honored open.sd.gov robots.txt (Disallow: /) after discovering it, so the Employee Salaries page itself was not inspected; fields and coverage there are inferred, not verified. Would need a human browser check or a records request to confirm whether BOR employees are listed.

## Tennessee (TN)

Systems: University of Tennessee System (UTK, UTC, UT Martin, UT Southern, UTHSC, UTIA, UT Institute for Public Service), Tennessee Board of Regents (13 community colleges + 24 TCATs), Locally governed institutions (LGIs), each with its own board: MTSU, University of Memphis, ETSU, Tennessee State, Tennessee Tech, Austin Peay  
Best rating: **B**. Records loaded: **3,631**.

### [C] Tennessee Board of Regents system office, 13 community colleges, TCATs  (catalog id 152)

- System/publisher: Tennessee Board of Regents
- URL: https://www.tbr.edu/hr/salaries
- Download: Paged HTML: https://www.tbr.edu/hr/salaries?page=N (about 120+ pages per search-engine index)
- Format: HTML table (Drupal, paginated); years: current snapshot
- Coverage: TBR system office, all community colleges, TCAT campuses; employees: all regular employees
- Fields: institution, last_name, first_name, job_title, department, salary (base), fte
- Access: login/form required: False; terms: not stated; base salary excludes longevity, stipends and additional pay for temporary or extra duties; updates: not stated; size: not stated (120+ pages)
- Blocker: robots.txt has 'Disallow: /hr/salaries/' and 'Crawl-delay: 10', so the site owner does not want this crawled; otherwise it would be a clean B (paged HTML).
- Notes: Fields and pagination taken from search-engine snippets; I did not crawl the pages because of robots.txt. Best candidate for a records request asking for the same data as a spreadsheet.

### [B] Austin Peay State University  (catalog id 153)

- System/publisher: LGI (APSU)
- URL: https://www.apsu.edu/human-resources/compensation/salary-database.php
- Download: https://www.apsu.edu/human-resources/documents/employee-salary-data.pdf
- Format: PDF; years: current ('Updated as of 2026'; file last-modified 2026-09-23)
- Coverage: APSU; employees: current employees (some redacted under T.C.A. 10-7-501)
- Fields: name, department, job_title, salary, employment_status
- Access: login/form required: False; terms: not stated; redaction policy on page; updates: annual (approx.); size: 753 KB
- Blocker: PDF only (table extraction needed); current year only, no history.
- Notes: Direct link, no form. Fields per page text (Transparent Tennessee wording); I only sent a HEAD request for the PDF and did not open it.
- **Loaded: 1,158 records**

### [B] East Tennessee State University  (catalog id 154)

- System/publisher: LGI (ETSU)
- URL: https://www.etsu.edu/human-resources/
- Download: https://www.etsu.edu/human-resources/documents/active_employees_as_of_05.22.2024.pdf ; https://www.etsu.edu/human-resources/documents/2022_active_employee_salaries.pdf
- Format: PDF; years: 2022, 2024 (May 22, 2024 snapshot); newer lists not found
- Coverage: ETSU; employees: active employees
- Fields: name, department, title, salary
- Access: login/form required: False; terms: not stated; updates: irregular; size: 2024 PDF 585 KB
- Blocker: PDF tables only; no index page links them (found via search), and the latest is May 2024.
- Notes: Well-structured name/department/title/salary columns (per search snippet). Other years may exist under the same /documents/ path.
- **Loaded: 2,473 records**

### [C] University of Tennessee System (all campuses and institutes)  (catalog id 155)

- System/publisher: University of Tennessee
- URL: https://tennessee.edu/about/facts-figures/data-dashboards/human-resources/salary/
- Download: https://app.powerbi.com/view?r=<token: see state JSON>
- Format: Power BI publish-to-web dashboard; years: current
- Coverage: UTK, UTC, UTM, UT Southern, UTHSC, UTIA, IPS, System Administration; employees: all paid, regular, active employees
- Fields: name, campus, department, title, base_salary (expected; not verified inside Power BI)
- Access: login/form required: False; terms: not stated; updates: not stated; size: not stated (about 15,000+ employees, estimate)
- Blocker: Interactive Power BI embed only; no export or bulk file. Scraping means reverse-engineering the Power BI querydata API.
- Notes: Official and covers the whole UT system. Also mirrored at data.tennessee.edu (returned HTTP 403 to my request).

### [C] University of Memphis (search UI also lists APSU, ETSU, MTSU, TSU, TTU in a commented-out school dropdown)  (catalog id 156)

- System/publisher: LGI (UofM)
- URL: https://umwa.memphis.edu/salary/index.php/main/search
- Format: search-form (POST); years: current
- Coverage: University of Memphis (other LGIs appear only in commented-out options); employees: all (base salaries rounded to the dollar)
- Fields: first_name, last_name, school, department, title, base_salary
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Blocker: Results only via a POST search form (salaryform); not submitted.
- Notes: The department dropdown is fully enumerated in the page, so per-department queries are possible if form submission is ever allowed.

### [C] Middle Tennessee State University  (catalog id 157)

- System/publisher: LGI (MTSU)
- URL: https://w1.mtsu.edu/hrs/salary/employee-salary-database.php
- Format: search-form (GET, DataTables results); years: current
- Coverage: MTSU; employees: all
- Fields: first_name, last_name, department, job_title, salary
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Blocker: Search-only: at least a 2-character search term is required before any rows show; no full list or download.
- Notes: GET params first/last/dept/title; a full harvest would need many queries.

### [C] Tennessee State University  (catalog id 158)

- System/publisher: LGI (TSU)
- URL: https://banner.tnstate.edu/BannerExtensibility/customPage/page/salarySearch
- Format: search-form (Banner Extensibility page); years: current
- Coverage: TSU; employees: all
- Fields: last_name, first_name, department, title, salary
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Blocker: Search by name required (Banner custom page, JS app).
- Notes: Not opened; details from search snippet.

### [D] Tennessee state executive-branch agencies  (catalog id 159)

- System/publisher: Transparent Tennessee - State Employee Salary Search (TN DOHR)
- URL: https://salary.app.tn.gov/public/searchsalary
- Download: JSON endpoints: https://salary.app.tn.gov/salary/api/distinctAgencyNames.json ; POST https://salary.app.tn.gov/salary/search.json
- Format: JSON API behind search page; years: current
- Coverage: 53 agencies; only higher-ed related agency is 'Higher Education Commission' (THEC). No UT, TBR or LGI institutions.; employees: state agency employees
- Fields: agency_name, last_name, first_name, job_title, comp_rate, comp_rate_period, full_part, bonus, as_of
- Access: login/form required: False; terms: see TN.gov web policies; updates: not stated; size: not stated
- Notes: Recorded to show the state portal does not cover colleges (only THEC staff).

**Private institutions / extra:** None found; Vanderbilt, Sewanee, Rhodes, Belmont etc. publish only IRS 990 data.

**Gaps:** No bulk/API source for any TN public college. UT System (largest) is Power BI only; TBR community colleges sit on an HTML list that robots.txt disallows; MTSU, Memphis and TSU are search-only; Tennessee Tech and UT campuses separately publish nothing found beyond the UT dashboard. Only base salary everywhere (no total/other pay). No history except ETSU's scattered PDFs.

**State notes:** Fragmented state: TN higher ed was split in 2017 into UT, TBR and six independent LGIs, and each publishes separately. Honored robots.txt for tbr.edu. Did not submit POST forms (Memphis) or run name searches (MTSU, TSU). A browser-based look at the UT Power BI could raise it to B if it has a table visual with 'export data' enabled.

## Utah (UT)

Systems: Utah System of Higher Education (USHE): University of Utah, Utah State University (incl. USU Eastern, Blanding), Weber State, Southern Utah, Utah Valley, Utah Tech, Snow College, Salt Lake Community College; plus Utah technical colleges  
Best rating: **A**. Records loaded: **0**.

### [A] All USHE institutions and technical colleges (each reports as its own entity)  (catalog id 164)

- System/publisher: Transparent Utah (Office of the State Auditor)
- URL: https://old.transparent.utah.gov/entity_comp.php
- Download: No static file URL. The Compensation Downloader builds a zipped CSV per entity and fiscal year via an undocumented query service at https://tu-query-handler-prod-uewlhjwsua-wm.a.run.app (query name getEntityCompensationZip, used by static/js/alex_queries.js). The page also offers CSV/XLSX/JSON export buttons for the preview table.
- Format: CSV (zipped), XLSX, JSON; years: About FY2010 to FY2025, varies by entity (annual compensation reports are due 90 days after fiscal year end)
- Coverage: All public colleges and universities in Utah, plus all state and local government entities; employees: all (at-risk employees may be redacted on request)
- Fields: entity_name, fiscal_year, employee_name, title, net_amount, description (pay type: wages, benefits, etc.), fund1-4, org1-4, cat1-4
- Access: login/form required: False; terms: Disclaimers page (old.transparent.utah.gov/disclaimers.php); no explicit reuse restriction seen; updates: annual per entity; size: not stated; large entities (University of Utah, USU, SLCC) are zipped and take up to 1 minute to generate
- Notes: robots.txt allows everything. You pick an entity and year in a dropdown: no login, account or CAPTCHA. Rated A because it returns a full bulk CSV per entity-year. Data is long format: one row per employee per pay type (wages, benefits, etc.), so it has to be pivoted. There is no department name, only org codes. The new React site at transparent.utah.gov has the same data. I did not test the endpoint, to avoid form-style calls.

### [C] Same as above  (catalog id 165)

- System/publisher: Transparent Utah - Employee Pay Search / Highest Paid
- URL: https://old.transparent.utah.gov/empdet.php
- Format: search-form; years: same as downloader
- Coverage: all public entities; employees: all
- Fields: name, entity, title, year, pay
- Access: login/form required: True; terms: not stated; updates: annual; size: not stated
- Blocker: Name search only; it duplicates the bulk downloader.
- Notes: Listed for completeness.

### [C] University of Utah, Utah State University, others  (catalog id 166)

- System/publisher: OpenTheBooks (third party)
- URL: https://www.openthebooks.com/utah-state-employees/
- Format: HTML; years: multiple recent years
- Coverage: state employees, including universities; employees: all
- Fields: name, title, employer, pay, year
- Access: login/form required: False; terms: OpenTheBooks site terms; updates: annual; size: about 740k-760k records stated in search snippets
- Blocker: Third-party copy of Transparent Utah data, paginated HTML; the official bulk source is better.
- Notes: Secondary source. Not verified.

**Private institutions / extra:** None found. BYU and Westminster publish no pay data beyond the IRS 990.

**Gaps:** No department names (only org codes). No hire date or FTE. No documented static bulk URLs: each entity-year export is generated on demand.

**State notes:** I rated the Transparent Utah downloader A even though you have to pick an entity and year in the UI. It is public, needs no login or CAPTCHA, and returns full bulk files. I treated login_or_form as false because no form gates access. No single-university salary pages were found: the USU library points users to Transparent Utah.

## Vermont (VT)

Systems: University of Vermont (UVM), Vermont State Colleges System: Vermont State University and Community College of Vermont  
Best rating: **B**. Records loaded: **70,348**.

### [B] University of Vermont  (catalog id 170)

- System/publisher: UVM (independent quasi-public)
- URL: https://www.uvm.edu/oira/faculty-and-staff
- Download: https://www.uvm.edu/d10-files/documents/2025-11/Final-FY26-Base-Pay.pdf (FY26, 1.7 MB); https://www.uvm.edu/d10-files/documents/2024-12/2024-2025-Base-Pay.pdf (FY25, 1.7 MB); https://uvmd10.drup2.uvm.edu/d10-files/documents/2024-07/Final_FY24_Base_Pay.pdf, Final_FY23_Base_Pay.pdf, Final_FY22_Base_Pay.pdf, sr09.pdf through sr20.pdf (FY2009-10 to FY2020-21)
- Format: PDF; years: FY2009-10 to FY2025-26 (one PDF per year; snapshot as of Nov 1)
- Coverage: University of Vermont; employees: all (regular paid positions)
- Fields: name, primary_job_title, base_pay
- Access: login/form required: False; terms: not stated; updates: annual (November); size: about 1.7 MB per PDF, roughly 4,000-5,000 rows
- Blocker: Data is only in PDF (text-based, alphabetical table), so each year needs PDF table extraction. There is no department column.
- Notes: Published by the Office of Institutional Research and Assessment. Base pay only: bonuses and extra pay are excluded. The PDFs look text-based, not scanned.
- **Loaded: 70,348 records**

### [D] State of Vermont executive, judicial and legislative employees (NOT colleges)  (catalog id 171)

- System/publisher: data.vermont.gov (Socrata)
- URL: https://data.vermont.gov/d/jgqy-2smf
- Download: https://data.vermont.gov/api/views/jgqy-2smf/rows.csv?accessType=DOWNLOAD
- Format: CSV/API; years: current snapshot, refreshed monthly
- Coverage: none of the higher-education institutions (UVM and VSCS run their own payroll); employees: state employees only
- Fields: name, job_title, department, job_type, salary, salary_type, data_as_of
- Access: login/form required: False; terms: not stated (no license in metadata); updates: monthly; size: 10,570 rows
- Notes: Checked: no department contains COLLEGE or UNIV. Recorded here so it isn't searched again. Related Socrata datasets (2is8-zt8g, 69uf-6qeu) are also state-only.

### [C] Vermont State University, Community College of Vermont  (catalog id 172)

- System/publisher: Vermont State Colleges System
- URL: https://openpayrolls.com/
- Format: HTML; years: 2013, 2025 seen
- Coverage: Vermont State University; employees: unknown
- Fields: name, title, pay, year
- Access: login/form required: False; terms: OpenPayrolls terms; updates: unknown; size: not stated
- Blocker: Third-party aggregator, one page per person, sourced from public-records requests. No official VSCS publication found.
- Notes: No official VSCS, VTSU or CCV salary list was found online.

**Private institutions / extra:** None found. Middlebury, Norwich, Champlain and Saint Michael's publish only the IRS 990.

**Gaps:** No official person-level pay for Vermont State University or Community College of Vermont (would need a public records request). UVM has base pay only, in PDF, with no department.

**State notes:** Rated the UVM PDFs B, since they are clean text PDFs with long history. The state Socrata salary dataset was checked and has no higher-ed employees, so it is rated D for this purpose. OpenPayrolls VTSU pages are listed as C.

## Virginia (VA)

Systems: 15 independent public four-year institutions (UVA, Virginia Tech, VCU, GMU, W&M, JMU, ODU, Radford, VMI, VSU, NSU, CNU, Longwood, UMW, UVA-Wise), Richard Bland College, Virginia Community College System (VCCS, 23 colleges)  
Best rating: **C**. Records loaded: **0**.

### [C] All state agencies on state payroll, including VCCS colleges and universities (shown by agency)  (catalog id 167)

- System/publisher: Commonwealth Data Point (Auditor of Public Accounts)
- URL: https://datapoint.apa.virginia.gov/salaries.php
- Download: No bulk file. The page queries salaryConnection.php by POST (AngularJS app).
- Format: search-form (HTML/JS); years: FY2017 to about FY2022 in the new portal (the VT library FAQ says Virginia Tech's latest year is 2022); earlier years in the legacy portal
- Coverage: state agencies including higher-ed institutions; employees: all
- Fields: agency, position, employee_id (anonymized unique id, NO NAME), total_salary, state_salary, non_state_salary, special_rate, bonuses, state_begin_date
- Access: login/form required: True; terms: not stated; updates: annual (lagging); size: not stated
- Blocker: No employee names (anonymized IDs only), and access is through an interactive query form with no bulk export.
- Notes: Official, but not person-level by name. Useful only for position-level aggregates.

### [C] UVA (incl. medical center, UVA-Wise), GMU, JMU, ODU, VCU, Radford, Virginia Tech and others, plus all DOA-payroll agencies including VCCS  (catalog id 168)

- System/publisher: Virginia Center for Investigative Journalism at WHRO (news database)
- URL: https://www.whro.org/virginia-center-for-investigative-journalism/2026-07-09/search-our-virginia-salary-database
- Format: search-form; years: calendar/fiscal 2025
- Coverage: about 170,000 state employees including public universities; employees: all (caveats: Radford and JMU base salary only; VCU excludes people earning $10,000 or less)
- Fields: name, agency, position, salary
- Access: login/form required: True; terms: not stated; updates: one-off / annual (2025 data published July 2026); size: about 170,000 rows
- Blocker: Search-only news tool. The article URL returned 404 on 2026-10-17 (it may have moved), and no download link was found.
- Notes: Built from Department of Accounts payroll plus public-records requests to each independent university payroll. VCIJ might share the dataset on request.

### [C] Virginia state employees including universities  (catalog id 169)

- System/publisher: OpenTheBooks (third party)
- URL: https://www.openthebooks.com/
- Format: HTML; years: varies
- Coverage: varies; employees: varies
- Fields: name, title, employer, pay, year
- Access: login/form required: False; terms: OpenTheBooks terms; updates: irregular; size: not stated
- Blocker: Third-party paginated HTML; coverage of Virginia universities not verified.
- Notes: Not verified in detail.

**Private institutions / extra:** None found.

**Gaps:** No official named, person-level pay file for any Virginia public university or VCCS. Data Point drops names. The only named data is the VCIJ/WHRO 2025 search tool (and older Richmond Times-Dispatch and Washington Business Journal databases), all search-only. Would need Virginia FOIA requests to each university, which run their own payroll.

**State notes:** Checked data.virginia.gov (CKAN): only city salary datasets (Norfolk, Virginia Beach). Data Point salaries rated C because it has no names. The VCIJ article is the best named source but has no download. University library FAQs (e.g., Virginia Tech) point to Data Point and say it lacks names and departments.

## Washington (WA)

Systems: Six public four-year institutions (University of Washington, Washington State University, Western Washington, Central Washington, Eastern Washington, The Evergreen State College), State Board for Community and Technical Colleges (SBCTC, 34 colleges)  
Best rating: **A**. Records loaded: **374,836**.

### [B] All public four-year institutions and all community and technical colleges, plus all state agencies  (catalog id 173)

- System/publisher: State Employee Salary Database (OFM data, published by LEAP on fiscal.wa.gov)
- URL: https://fiscal.wa.gov/Staffing/Salaries.aspx
- Download: The full-database download link is sent by email after mailing leap@leg.wa.gov (the 'Download Data' button is a mailto link). The interactive view is an embedded Power BI report.
- Format: Power BI (interactive); bulk file by email request (format not stated, historically CSV/XLSX); years: rolling previous 5 calendar years (about 2020-2024 as of 2026; 2025 data expected in summer 2026)
- Coverage: UW, WSU, WWU, CWU, EWU, Evergreen, all SBCTC colleges, all state agencies; employees: all, except student employees (names withheld for confidentiality and domestic-violence cases)
- Fields: agency/institution, employee_name, job_title, total_annual_earnings by calendar year (base plus overtime and premiums, rounded to $100)
- Access: login/form required: True; terms: Published as a public service, not required by law (FAQ); no reuse terms stated; updates: annual (early summer); size: not stated (several hundred thousand rows for 5 years)
- Blocker: The bulk file needs an email request to LEAP (a manual form-like step); the web view is Power BI only.
- Notes: Official, comprehensive and clean once obtained: one manual email gets the whole 5-year file. Rated B instead of A only because of the email gate. Supporting PDFs: SalaryDataFAQ.pdf, SalaryPersonnelIncluded.pdf, SalarySpecial.pdf. No department field, only agency and job title. I did not send the email.

### [A] All state agencies and higher-ed institutions (agency 360 = UW, 365 = WSU, etc.)  (catalog id 174)

- System/publisher: data.wa.gov (Socrata) - Annual Salary 2010 thru 2013
- URL: https://data.wa.gov/d/y3ds-rkew
- Download: https://data.wa.gov/api/views/y3ds-rkew/rows.csv?accessType=DOWNLOAD
- Format: CSV/API; years: calendar years 2010-2013
- Coverage: all state agencies and higher-ed institutions; employees: all
- Fields: agency (code), agency_title, employee_name, job_title, salary2010, salary2011, salary2012, salary2013
- Access: login/form required: False; terms: not stated; updates: none (historical; last updated 2015-01-22); size: 339,763 rows
- Notes: Historical only, but loads cleanly. UW (360) has about 97k rows and WSU (365) about 33k. Wide format, one column per year.
- **Loaded: 374,836 records**

### [C] Washington State University and others  (catalog id 175)

- System/publisher: News databases (Daily Evergreen, etc.)
- URL: https://dailyevergreen.com/23354/transparency/washington-state-salaries-database
- Format: search-form/HTML; years: varies
- Coverage: varies; employees: varies
- Fields: name, title, salary
- Access: login/form required: False; terms: not stated; updates: irregular; size: not stated
- Blocker: Derived from the same OFM data; search-only, not authoritative.
- Notes: Not needed given the official source.

**Private institutions / extra:** None found.

**Gaps:** Current years (2014+) have no public static bulk URL (email request to LEAP required). No department, FTE or hire date. Earnings are rounded to $100 and are calendar-year totals.

**State notes:** Best rating is A because of the historical 2010-2013 Socrata file. For current data the LEAP database is rated B because of the email gate, which is the recommended route (one manual email). A data.virginia.gov 'Agency Salaries - Washington' mirror turned out to be agency totals only, so it was ignored.

## West Virginia (WV)

Systems: WV Higher Education Policy Commission (HEPC): WVU (incl. Potomac State, WVU Tech), Marshall, Bluefield State, Concord, Fairmont State, Glenville State, Shepherd, West Liberty, WV State University, WV School of Osteopathic Medicine, WV Community and Technical College System (9 colleges)  
Best rating: **C**. Records loaded: **0**.

### [C] All state agencies, including public colleges on wvOASIS payroll, plus WVU and Marshall (supplied by the universities)  (catalog id 180)

- System/publisher: WV State Auditor - WV Checkbook 'State of West Virginia Total Compensation' (OpenGov)
- URL: https://stories.opengov.com/westvirginia/published/dtU9eqSBP
- Download: Embedded OpenGov data grid: https://westvirginia.opengov.com/data/#/42541/query=8303D64F93C47B5D5DAE110DE82470AC (no static file found)
- Format: HTML/JS data grid (OpenGov); years: Report described as of Dec 31, 2021 (calendar 2021); later years not confirmed
- Coverage: state agencies, public higher-ed colleges, WVU, Marshall; employees: all
- Fields: employee name (likely), agency, total compensation, pay types (wvOASIS pay codes)
- Access: login/form required: False; terms: WV Checkbook / OpenGov Terms of Use linked in footer; updates: annual report (irregular); size: not stated
- Blocker: Data is only in a JavaScript OpenGov grid with no documented export. Whether names are shown and which years exist could not be confirmed without a browser.
- Notes: Official source. The OpenGov grid may offer CSV export in a browser, which a human should check: if so, upgrade to B or A. Total compensation for WVU and Marshall came from the universities; the rest came from wvOASIS HRM/Payroll.

### [C] WV state employees including WVU, WVSOM and others  (catalog id 181)

- System/publisher: OpenPayrolls (third party)
- URL: https://openpayrolls.com/state/west-virginia/2025
- Format: HTML; years: 2004-2025 (per year pages)
- Coverage: state agencies and some higher-ed (WVSOM and WVU entries seen); employees: about 33k state records for 2024
- Fields: name, title, agency, pay, year
- Access: login/form required: False; terms: OpenPayrolls terms; updates: annual; size: about 33,239 records for 2024
- Blocker: Third-party aggregator with paginated per-person pages; provenance unverified.
- Notes: Probably mirrors Auditor data; may be missing independent-payroll universities.

### [D] All HEPC/CTCS institutions (classified staff)  (catalog id 182)

- System/publisher: WV HEPC salary schedules
- URL: https://wvhepc.edu/wp-content/uploads/2024/05/2024-WV-Higher-Education-Employee-Salary-Schedule-April-2024.pdf
- Download: https://wvhepc.edu/wp-content/uploads/2024/05/2024-WV-Higher-Education-Employee-Salary-Schedule-April-2024.pdf
- Format: PDF; years: 2024
- Coverage: all public colleges; employees: classified only (pay grades, not persons)
- Fields: pay_grade, rates
- Access: login/form required: False; terms: not stated; updates: periodic; size: small PDF
- Notes: Not person-level: pay schedule only. Recorded so it isn't re-researched.

**Private institutions / extra:** None found.

**Gaps:** No confirmed bulk, named, person-level download for any WV public college. WVU and Marshall run their own payroll and publish no salary lists. Would need to check the OpenGov grid in a browser for export, or file WV FOIA requests.

**State notes:** wvcheckbook.gov is an OpenGov single-page app, so I listed its story pages and found the 'State of West Virginia Total Compensation' story, which embeds an OpenGov data grid. I couldn't confirm an export without a browser, so it is rated C. No news-organization database with downloads was found (searched Gazette-Mail and Mountain State Spotlight).

## Wisconsin (WI)

Systems: Universities of Wisconsin (formerly UW System; 13 universities incl. UW-Madison, UW-Milwaukee), Wisconsin Technical College System (WTCS, 16 locally governed districts)  
Best rating: **C**. Records loaded: **0**.

### [C] State agencies; Universities of Wisconsin planned but limited  (catalog id 176)

- System/publisher: OpenBook Wisconsin (Dept. of Administration)
- URL: https://openbook.wi.gov/
- Format: search-form (ASP.NET/Telerik); years: FY2013+ for expenditures; salary tab years not confirmed
- Coverage: state agencies; UW coverage 'may be limited' per site; employees: state employees (UW status unclear)
- Fields: employee_name, agency, class, gross_pay, ytd_gross_pay
- Access: login/form required: True; terms: not stated; updates: not stated; size: not stated
- Blocker: robots.txt disallows all crawling (User-agent: * Disallow: /). The site is an ASP.NET postback search, and UW payroll coverage is unconfirmed.
- Notes: Has a Salary tab. The homepage text still says UW salary data will be added in the future and may be limited because UW uses separate accounting systems. I did not crawl beyond the homepage, out of respect for robots.txt.

### [C] UW-Madison (data maintained by UW System)  (catalog id 177)

- System/publisher: UW System Compensation Dashboard (internal analytics)
- URL: https://search.data.wisc.edu/specifications/29713
- Format: dashboard (internal); years: current employees (last updated Oct 2025)
- Coverage: UW-Madison; employees: all
- Fields: salary info on current employees
- Access: login/form required: True; terms: Classified 'Employee Record Data Internal'; updates: ongoing; size: not stated
- Blocker: Internal: NetID login required; not public.
- Notes: Listed only to record that it is not publicly available.

### [C] UW-Madison and other UW universities  (catalog id 178)

- System/publisher: OpenPayrolls (third party)
- URL: https://openpayrolls.com/
- Format: HTML; years: 2025 seen
- Coverage: UW-Madison and others; employees: unknown
- Fields: name, title, employer, pay, year
- Access: login/form required: False; terms: OpenPayrolls terms; updates: unknown; size: not stated
- Blocker: Third-party aggregator, one page per person, sourced from public-records requests; unverified.

### [D] Universities of Wisconsin (historical)  (catalog id 179)

- System/publisher: UW System Annual Budget 'Redbook' with salary detail
- URL: http://systemwide.uwsa.edu/budplan/redbook/book1/
- Format: HTML (historical); years: 2009-10, 2010-11 (old links); current Redbook appears only in internal WISER
- Coverage: all UW institutions; employees: budgeted positions (historically names, titles, departments, budgeted salary)
- Fields: name, title, department, budgeted_salary, fte
- Access: login/form required: False; terms: not stated; updates: annual (historical); size: not stated
- Notes: The old public Redbook salary-detail pages (uwsa.edu/budplan) are linked from a UW-Madison stats faculty page but appear defunct. The current Redbook is in WISER (internal). Might be on the Wayback Machine.

**Private institutions / extra:** None found.

**Gaps:** No public, official, named person-level pay file for any Universities of Wisconsin campus or WTCS district. The current Redbook and compensation dashboards are internal. Would need Wisconsin public-records requests (UW System Office of General Counsel), which the press uses.

**State notes:** I respected openbook.wi.gov's robots.txt (Disallow all) and did not crawl its salary search. Search results are full of SEO spam pages about 'UW System Redbook salaries'; I ignored them. WTCS districts are locally governed and no published salary lists were found.

## Wyoming (WY)

Systems: University of Wyoming, Wyoming Community College Commission (7 colleges: Casper, Central Wyoming, Eastern Wyoming, Laramie County CC, Northern Wyoming CC District, Northwest, Western Wyoming)  
Best rating: **C**. Records loaded: **0**.

### [C] University of Wyoming, Casper College, Central Wyoming College, Eastern Wyoming College, Laramie County CC, Northern Wyoming CC District, Northwest College, Community College Commission (plus state agencies)  (catalog id 183)

- System/publisher: OpenTheBooks - Wyoming state employees (third party; sourced from Wyoming State Auditor and Legislative Service Office records requests)
- URL: https://www.openthebooks.com/wyoming-state-employees/
- Format: HTML (paginated, filterable); years: 2017-2025
- Coverage: University of Wyoming and 6 community colleges plus the Commission (Western Wyoming CC not seen in the filter list), plus state agencies; employees: all
- Fields: year, employer, name, title, annual_wages, source
- Access: login/form required: False; terms: OpenTheBooks site terms; updates: annual; size: 185,846 salary records total; only the top 10,000 are browsable
- Blocker: Third-party HTML with no export, and the browse limit is the top 10,000 rows, so the full set can't be reached by scraping.
- Notes: Best available. OpenTheBooks may provide the full dataset on request.

### [C] University of Wyoming and others  (catalog id 184)

- System/publisher: OpenPayrolls (third party)
- URL: https://openpayrolls.com/state/wyoming
- Format: HTML; years: 2017-2025 (year pages)
- Coverage: state employees including University of Wyoming; employees: about 31k records for 2025
- Fields: name, title, employer, pay, year
- Access: login/form required: False; terms: OpenPayrolls terms; updates: annual; size: 31,328 records for 2025 (stated)
- Blocker: Third-party, one page per person; provenance unverified.

### [C] State employees (possibly incl. University of Wyoming)  (catalog id 185)

- System/publisher: MuckRock FOIA requests to Wyoming State Auditor (public request pages with released files)
- URL: https://www.muckrock.com/foi/wyoming-305/wyoming-state-employees-2019-2022-128342/
- Format: spreadsheet attachments (per search snippet); years: 2010-2018 and 2019-2022 (separate requests: .../wyoming-state-employees-2010-2018-129816/)
- Coverage: unclear; State Auditor payroll (UW may run its own payroll); employees: state employees
- Fields: department, title, hire_date, annual_gross_salary, name (likely)
- Access: login/form required: False; terms: MuckRock terms; updates: one-off; size: not stated
- Blocker: MuckRock returned HTTP 403 to automated fetch, so contents and coverage could not be verified. These are one-off FOIA releases.
- Notes: Worth a manual look: released spreadsheets may be downloadable without login.

**Private institutions / extra:** None (no private universities of note in Wyoming).

**Gaps:** No official online person-level pay source for the University of Wyoming or any community college. The State Auditor's transparency site (WyOpen) covers vendor payments and excludes salaries, and wyoopen.gov did not resolve. Data has come only through Public Records Act requests.

**State notes:** Rated OpenTheBooks C, since it's the most complete and covers UW plus the community colleges for 2017-2025 but has no export. wyoopen.gov returned DNS failure (ENOTFOUND). A 2019 news report says WyOpen excludes salaries.

