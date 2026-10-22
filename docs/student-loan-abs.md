# Student loan asset-backed securities (SLABS) from SEC EDGAR

What the SEC holds on student loan securitizations, what we load, and what isn't there and
why. Code: `scripts/sla_index.py`, `scripts/sla_trusts.py` (discovery), `loader/sec.py`
(throttled, cached downloads), `loader/sla_parse.py` (one parser per issuer family),
`loader/student_loans.py` (ingest and stats), `loader/sla_link.py` (990 matching),
`loader/cohort_default.py` (federal cohort default rates). Pages: `app/student_loans.py`;
boards: `app/student_loan_boards.py`; tables: migration 0027.

## How we searched

* Every EDGAR quarterly form index, 1994 Q1 to 2026 Q4 (`full-index/YYYY/QTRn/form.gz`),
  filtered to filers whose names look like student loan vehicles or sponsors (student loan,
  education loan, SLM, Navient, Nelnet, SMB, National Collegiate, SoFi, College Ave,
  Brazos, PHEAA, Access Group, Goal Capital and so on) and to the forms that matter
  (10-D, 10-K, 8-K, 424B2/3/5, 424H, FWP, ABS-15G, ABS-EE, SF-1/SF-3, S-3, 15-15D).
  15,882 filings matched.
* The submissions history (`data.sec.gov/submissions/CIK##########.json`) of each of the
  313 filers with a 10-D, at least six 8-Ks, a 424B5 or an ABS-15G.
* Every request sends `User-Agent: furp.org research michael@furp.org`
  and the downloader holds itself to 4 requests a second (the SEC allows 10). Raw files
  are cached gzipped under `~/sla-data/raw` (not in git); re-parsing never re-downloads.

## What exists

| Form | Filings | What it is |
|---|---:|---|
| 8-K | 5,192 | Before Regulation AB (2006), monthly and quarterly reports came on 8-K; later, notices |
| 10-D | 5,039 | The monthly (or quarterly) distribution report, with the servicing report as EX-99.1 |
| 424B3 / 424B5 / 424B2 | 2,244 | Prospectus supplements: parties, initial pool, loan characteristics at closing |
| FWP | 959 | Free-writing prospectuses (term sheets) |
| 10-K | 840 | Annual reports: servicer compliance statements and attestations |
| ABS-15G | 753 | Rule 15Ga-1 reports of repurchase demands, filed yearly by each securitizer |
| 15-15D | 220 | Suspension of reporting |
| ABS-EE | **0** | Asset-level data. No student loan filer has ever filed one |

**Trusts.** 133 trusts kept (a 10-D, or six or more 8-Ks), in these issuer families:

| Family | CIKs | 10-Ds | Reporting on 10-D |
|---|---:|---:|---|
| SLM / Navient (Sallie Mae; Navient after 2014), incl. SLM Private Credit | 137 | 4,839 | 2006 to Oct 2026 |
| SLC Student Loan Trusts (Citibank's Student Loan Corp; Discover; now Navient-administered) | 16 | 70 | 2006 to 2024 |
| National Collegiate Student Loan Trusts (First Marblehead; private, TERI-guaranteed) | 17 | 39 | 2006 to July 2008 |
| College Loan Corp Trusts | 3 | 42 | 2006 to 2008 |
| Nelnet Student Loan Trusts | 20 | 15 | 2006 to 2009 |
| Goal Capital Funding Trusts | 3 | 14 | 2006 to 2008 |
| Chase Education Loan Trust 2007-A | 1 | 3 | 2007 to 2008 |
| KeyCorp, EdLinc (Education Loans Inc, South Dakota), GCO, Education Funding Capital, PHEAA Student Loan Trust I, Collegiate Funding Services, PNC, Higher Education Funding, Wachovia, Signet, SMS, CIT | 29 | 0 | 8-K only, 1996 to 2008 |

Only 35 trusts report continuously: the SLM Student Loan Trusts of 2010 to 2014 and the
Navient Student Loan Trusts of 2014-1 through 2015-3 (all FFELP), monthly from issue to
October 2026, plus a handful of SLC trusts (quarterly). Every other registered trust filed
Form 15-15D after its first fiscal year (allowed once a class has fewer than 300 holders)
and stopped reporting to the SEC: for example SLM Student Loan Trust 2006-1 has three
10-Ds, and each National Collegiate trust has under a year of reports before July 2008.

**Securitizers that file only Form ABS-15G** (their deals are private or municipal): SoFi
Lending, SoFi Bank, College Avenue Student Loans, Earnest Operations, DR Bank (Laurel
Road), SMB Education Funding (Sallie Mae Bank's private trusts), Navient Credit Funding,
Navient Refinance Funding, Navient Education Loan Funding, Nelnet, Bank of America Student
Loan Securitization Corp, Wachovia Education Loan Funding, CIT Strategic Finance, Education
Loan Finance (ELFI), Santiago Student Loan Depositor Trust, and the nonprofit and state
secondary markets: AccessLex Institute (formerly Access Group), Brazos Education Loan
Authority, Brazos Education Funding Corporation, Bosque Higher Education Authority, North
Texas Higher Education Authority, South Texas Higher Education Authority, Montana Higher
Education Student Assistance Corp, South Carolina Student Loan Corp, Student Loan Finance
Corp (South Dakota, EdLinc's parent), PHEAA Student Loan Foundation, Pennsylvania Higher
Education Assistance Agency, Northstar Education Finance, Patriot and Viking Student Loan
Capital, Granite Edvance (New Hampshire), PCG Academic Loan Group, U.S. Education Loan
Trust III and IV, Access to Loans for Learning Student Loan Corp, ECMC Group trusts.

**Formats.** 10-D servicing reports are HTML exhibits (EX-99.1). Pre-2006 8-K reports are
plain text (`.txt`) or early HTML. No XML or XBRL report data, no PDFs among the reports we
read, no ABS-EE.

## Loan-level data: none

Regulation AB II (2014) requires asset-level data on Form ABS-EE (Schedule AL, Item 1125)
only for residential and commercial mortgages, auto loans and leases, debt securities and
resecuritizations. The SEC did not extend it to other asset classes, student loans among
them. The index confirms it: zero ABS-EE filings by any student loan
filer. Every figure here is a pool total from the issuer's monthly report.

## Pool-level fields in the reports

SLM / Navient / SLC template (the same report since 2006, in three table layouts):

* pool balance, principal, interest to be capitalized, number of loans and borrowers,
  weighted average coupon and remaining term, pool factor
* loan status by principal and count: in school, grace, deferment, current, 31-60,
  61-90, 91-120 and over 120 days delinquent (private credit: up to over 180 or 270 days),
  forbearance, claims in process, aged claims rejected
* FFELP: principal from guarantors (claims paid), non-reimbursable losses (the uninsured
  share), cumulative non-reimbursable losses, rejected-claim repurchases
* private credit: gross defaults (period and cumulative), realized losses, recoveries,
  cumulative default and net loss tests
* since-issued constant prepayment rate (CPR); it can be negative and is shown as reported
* loan type (Stafford, PLUS, SLS, consolidation) and **school type** (four-year, two-year,
  technical, other) as percentages of the pool
* notes, reserve account, parity ratio, waterfall, triggers

National Collegiate template: pool balance, loans, borrowers, WAC, status table (in
school, current, 31-60 through over 180 days, forbearance), TERI claims filed / paid / in
process (cumulative), realized losses, recoveries, cumulative default rates (of loans in
repayment and of the pool at closing), a twice-yearly prepayment rate, borrower type
(cosigned / not) and program type (undergraduate, graduate, K-12, medical, continuing
education).

## What we load (student_loan_trust_months)

pool balance, loans, borrowers, the issuer's delinquency buckets (in `delinquency` jsonb,
labels as printed) mapped onto 30-59 / 60-89 / 90-119 / 120+ (the reports use 31-60 /
61-90 / 91-120 / over 120; the 120+ column sums every longer bucket), total delinquent,
current, in repayment, forbearance, deferment, school and grace, claims in process,
defaults, charge-offs, recoveries, cumulative defaults and default percent where printed,
CPR, WAC, the months the report covers (1, or 3 for quarterly trusts), and the filing and
document URLs. Fields an issuer doesn't print are NULL and show "Not reported".

Definitions differ by family and are shown on every trust page (`FAMILIES` in
`app/student_loans.py`):

* **Defaults.** SLM/Navient/SLC FFELP: principal received from guarantors in the period
  (claims paid; the guarantor and the federal government repay 97 to 100%, so these are
  not losses). SLM private credit: the change in cumulative gross defaults. National
  Collegiate: the month's change in cumulative net claims filed with TERI.
* **Charge-offs.** FFELP: non-reimbursable losses. Private: realized principal losses.
* **Recoveries.** Private trusts only; FFELP reports have no recoveries line (Not reported).
* **Rates** (pages and boards) are ours, computed the same way for every trust:
  delinquency = delinquent / in repayment (current plus delinquent), or / pool balance when
  a report doesn't break out the current bucket (flagged); default and charge-off rates =
  sum over the reports in the window / average pool balance, annualized by the months the
  reports cover; 12-month change = this report's delinquency rate minus the rate in the
  report for the same month a year earlier (none if that report is missing).

Parties: depositor, servicer, administrator and indenture trustee from each report's header
(latest report wins); sponsor from the prospectus supplement cover; closing date and initial
pool balance from the reports' first column (SLM/Navient 2014 layout, 2010-2013 "inputs
from initial period", National Collegiate "financed student loans as of closing date").

## Ingest results

Loaded 2026-10-18: **5,021 trust-months from 101 trusts**, November 2004 to August 2026
(10 of them from plain-text 8-Ks, the rest HTML exhibits).

| Family | Trusts | With data | Months parsed | Found, not parsed | Reports |
|---|---:|---:|---:|---:|---|
| SLM / Navient / SLM Private Credit | 80 | 79 | 4,889 | 2 | Mar 2005 to Aug 2026 |
| SLC Student Loan Trusts (quarterly) | 10 | 7 | 68 | 2 | Aug 2006 to Jul 2024 |
| National Collegiate | 10 | 9 | 51 | 14 | Nov 2004 to Jun 2008 |
| Nelnet (quarterly) | 8 | 6 | 13 | 2 | Apr 2006 to Nov 2008 |
| KeyCorp, Collegiate Funding Services, Goal, Education Funding Capital, College Loan Corp, EdLinc, GCO, PHEAA, PNC, Higher Education Funding, Chase, other | 32 | 0 | not parsed | | 1996 to 2008 |

Failures, by trust: National Collegiate 1996-S1 (7: 1996 text 8-Ks with no separate
report document), National Collegiate 2004-2 (3), 2005-1, 2005-3, 2006-1, 2007-4 (1 each:
early text layouts with the table split across lines), SLC 2007-1 (2), Nelnet 2006-2 and
2008-3 (1 each), SLM 2003-5 and 2010-2 (1 each). Each failure's reason is in
`student_loan_trusts.notes`.

Missing months: 12 trusts have calendar months with no report between their first and
last; most are real gaps on EDGAR (SLM Private Credit 2003-A/B/C reported in 2006, stopped,
and filed again in 2015). Quarterly reports cover three months each and are not gaps.

Not reported, by field (rows with NULL of 5,021): recoveries 4,985 (FFELP reports have
no recoveries line), prepayment rate 59, defaults 20, forbearance 12.

Parties: sponsor known for 67 of the 101 trusts (prospectus cover), closing date for 64,
initial pool balance for 65.

One issuer typo is corrected on read: SLM Student Loan Trust 2011-3's April 2012 report
prints "Guarantor Principal 1,904,607,71"; a trailing comma followed by two digits is read
as a decimal point (`money()` in `loader/sla_parse.py`).

## 990 links

63 parties (depositors, servicers, administrators, trustees, sponsors, and securitizers
filing Form ABS-15G). 11 match a 990 filer, all of them securitizers whose deals are
private or municipal (so no pool data):

| Party (EDGAR) | 990 filer | EIN | Tag |
|---|---|---|---|
| Bosque Higher Education Authority, Inc. (TX) | Bosque Higher Education Authority Inc | 74-2534099 | EXACT |
| Brazos Education Funding Corporation, Inc. (TX) | Brazos Education Funding Corporation Inc | 20-3870176 | EXACT |
| Brazos Education Loan Authority, Inc. (TX) | Brazos Education Loan Authority Inc | 20-3868073 | EXACT |
| Education Loan Finance, Inc. (TN) | Education Loan Finance Inc | 62-1586836 | EXACT |
| Granite Edvance Corp (NH) | Granite Edvance Corporation | 02-0368776 | EXACT |
| Montana Higher Education Student Assistance Corp (MT) | same | 81-0393527 | EXACT |
| Northstar Education Finance, Inc. (MN) | same | 41-1961427 | EXACT |
| North Texas Higher Education Authority, Inc. (TX) | same | 23-7133739 | EXACT |
| PHEAA Student Loan Foundation Inc (PA) | same | 51-0423553 | EXACT |
| South Carolina Student Loan Corp (SC) | South Carolina Student Loan Corporation | 57-0602805 | EXACT |
| AccessLex Institute (EDGAR address DE) | AccessLex Institute (PA) | 23-2719985 | FUZZY (same name, different state) |

The Pennsylvania Higher Education Assistance Agency is labeled a state agency (no 990).
Not matched: Student Loan Finance Corp (SD), South Texas Higher Education Authority,
Access to Loans for Learning Student Loan Corp, PCG Academic Loan Group, Education Loans
Inc (EdLinc): no 990 filer with the same or a similar name in the same state. No trust is
linked to a school.

## What is not available, and why

* **Loan-level data**: not required for student loan ABS (above).
* **School-level data**: no issuer reports loans by school, only by school *type*. Trusts
  are not linked to schools. The separate `cohort_default_rates` table holds the
  Department of Education's official federal cohort default rates by school (OPE school
  code), which describe all federal loans at a school, not securitized pools.
* **Most of the market since 2008**: private and refinance deals (SoFi, College Ave,
  Earnest, Laurel Road, CommonBond, SMB, Navient private and refi trusts since 2014,
  Nelnet) are sold under Rule 144A and file no reports; their monthly reports go to
  investors privately. Their sponsors file only Form ABS-15G.
* **Municipal and nonprofit issuers** (Brazos, North Texas, PHEAA, AccessLex/Access Group,
  EdLinc after 2008, state agencies) issue tax-exempt or taxable municipal bonds;
  their disclosure goes to the MSRB's EMMA system, not EDGAR.
* **Suspended trusts**: about 100 registered trusts (SLM 1996-2009, SLC, Nelnet,
  National Collegiate, Goal, College Loan Corp) filed 15-15D; their later reports were
  posted on sponsor or trustee web sites (Navient's investor site, U.S. Bank for National
  Collegiate) and are not on EDGAR. National Collegiate's 2008-onward history (the TERI
  bankruptcy, the later litigation) is therefore not here.
* **Pre-2006 8-K reports** of SLM trusts were mostly filed in combined filings by SLM
  Funding (one filing, many trusts), and KeyCorp, EdLinc, SLC and others used varied text
  layouts; parsers for them are listed under What's left.
* **Borrower characteristics** (income, FICO, repayment plan detail) appear only in
  prospectus tables at closing, not monthly.

## What's left

* Parsers for the 8-K-era families (KeyCorp 1999-2006, EdLinc 1997-2008, GCO, Education
  Funding Capital, Collegiate Funding Services, College Loan Corp, Goal Capital, PHEAA
  Student Loan Trust I, PNC, Chase): about 400 reports, varied text layouts.
* SLM trusts' pre-2006 reports filed in combined SLM Funding 8-Ks (one filing, many trusts).
* The few early National Collegiate and Nelnet text reports listed under failures.
* School-type mix (four-year / two-year / technical) is in every SLM report and could be
  stored per month; it isn't yet.
* Pairing: `cohort_default_rates` holds FSA's FY2021-2023 official rates (4,579 schools,
  13,737 school-years, keyed by 6-digit OPE school code). The `colleges` table has no
  OPEID column, so joining to UNITID needs the IPEDS HD OPEID crosswalk added there.
  Rates for the 2021-2023 cohorts are near zero because federal loan payments were paused.
