# Minnesota business bulk order file (MBLS)

Source: Office of the Minnesota Secretary of State, Business Services, "Business Bulk Data Implementation Guide"
(Rev08012025; a copy is at /bulk/registry/mn/business-bulk-order-implementation-guide-and-record-layout.pdf on the
dev server). How to load it: loader/minnesota_registry.py (`.venv/bin/python -m loader.minnesota_registry`,
`--limit N` for a test run, `--if-new` as the nightly run calls it).

## Getting a new file (re-request)

There is no fixed download URL: each order is a one-time file. Free for the news media, journalists, researchers and
non-commercial use.

1. Fill in the request form for non-paying users: https://www.sos.mn.gov, Business & Liens, the Business & Liens Data
   section, the Business Data Available page.
2. Email it to business.services@state.mn.us (phone 651-296-2803 or 1-877-551-6767 with questions).
3. The order is filled within 10 days. Sign in to the MBLS Portal (https://mblsportal.sos.mn.gov), open
   Transaction History, and download the zip.
4. Put the zip (as downloaded) in `/bulk/registry/mn/YYYY-MM-DD/`, the date being the download date, with a
   PROVENANCE.txt (the download link and time) beside it if you have them. On the production server
   (20.168.8.141) the nightly run (scripts/nightly.sh) loads it that night: it loads only when the newest dated
   folder holds a file that isn't the one last loaded there (recorded in `/bulk/registry/mn/.loaded`).
5. Or load it at once from either server (they share the database), e.g. on dev, where the 2026-10-28 file is:
   `cd ~/np-explorer && set -a && . ./.env && set +a && .venv/bin/python -m loader.minnesota_registry`
   (about an hour; `--limit 5000` for a test run).

The state creates the data at the start of each month; the file name carries the dates
(`1096_20260930_M_COMPLETE_Job23_RunOn20261001.CSV`: data through 2026-09-30, exported 2026-10-01).

## The file

- One CSV in a zip (3.49 GB unzipped, 26,239,159 lines in the 2026-10-01 export), no header, Windows-1252, every
  field in double quotes (a quote inside a field is doubled). Grouped by record type: all 01, then all 02, then all 03.
- Active and inactive records. Master ID (a GUID) ties the three record types together; it is never reused.

### 01 Business master (2,565,924 records): one per business

Master ID, Record Type ("01"), Business Type Code, Original Filing Number, Minnesota Business Name (or the trademark
word or phrase), Business Filing Status (Active, Inactive), Filing Date, Expiration Date, Next Renewal Due Date, Home
Jurisdiction (state, country or tribe name), Governing Statute (302A, 322C, 317A, 333...), Is LLC Non Profit (0/1),
Is LLLP (0/1), Is Professional (0/1), Home Business Name (a foreign business's name at home), Number of Shares, then
trademarks only: Business Mark Type (Trademark, Service Mark, Certification Mark, Collective Mark), Mark First Use
Date, Mark Classification Number, Mark Logo (a description); a blank column; Export Date. Dates M/D/YYYY.

### 02 Filing history (16,254,825 records)

Master ID, Record Type ("02"), Business Type Code, Original Filing Number, Filing Number, Filing Action (Original
Filing, Annual Renewal, Amendment, Administrative Dissolution, Registered Office and/or Agent...), Filing Rank (P
primary, S secondary within the same filing), Filing Date, Effective Date.

### 03 Names and addresses (7,418,410 records): only those current when the file was made

Master ID, Record Type ("03"), Business Type Code, Original Filing Number, Filing Number, Name Type Number, Address
Type Number, Party Name, Street Address Line 1, Street Address Line 2, City Name, Region Code, Postal Code, Postal
Code Extension, Country Name. A record is a name, an address, or a name with its address (a party's primary
address). The registered agent's name has no address of its own: it is at the registered office (address type 3) or
the registered agent address (21). Some region codes are doubled ("MNMN").

### Codes (Appendix II)

Business types: 38 Cooperative Association, 39 Cooperative (Foreign), 41 Nonprofit Corporation (Domestic), 42
Nonprofit Corporation (Foreign), 43 Business Corporation (Foreign), 44 Limited Liability Company (Domestic), 46
Limited Liability Company (Foreign), 48 Limited Partnership (Domestic), 49 Limited Partnership (Foreign), 50 Limited
Liability Partnership (Domestic), 52 Limited Liability Partnership (Foreign), 57 Trademark, 59 Assumed Name, 60 Name
Reservation, 66 Business Corporation (Domestic), 104 Cooperative (Domestic), 161 Housing Cooperative.

Name types: 1 Applicant, 2 Markholder, 4 Registered Agent, 7 Organizer, 8 Incorporator, 11 Filing Contact, 12
President, 13 Manager, 14 Chief Executive Officer, 19 Individual Contact for Agent.

Address types: 2 Principal Place of Business, 3 Registered Office, 4 Home Office, 5 Principal Office, 6 Chief
Executive Office, 7 Office, 8 Designated Office, 9 Service Address (withdrawals), 11 Business Mailing, 14 Party
Primary, 16 Principal Office Mailing, 17 Principal Executive Office, 18 Designated Office Mailing, 19 Registered Agent
Mailing, 21 Registered Agent, 204 Individual Contact for Agent Mailing, 9999 Mailing.

## How FURP stores it

- biz_entities (state MN, entity_id = Master ID, source mn): name, type spelled out, status, formed (filing date),
  the business's address (the first present of principal place of business, principal executive office, principal
  office, chief executive office, home office, office, designated office, registered office, then mailing addresses;
  which one is in extra.address_type), registered agent and the agent's address (registered agent address, else
  registered office), home jurisdiction as a state code. Everything else Minnesota publishes goes in extra: original
  filing number, business type code, expiration date, next renewal due, governing statute, LLC nonprofit, LLLP,
  professional, home business name, number of shares, the trademark fields, and for inactive businesses the date and
  action of the latest filing that ended it (dissolution, termination, revocation, cancellation, withdrawal,
  expiration) as dissolved and dissolved_by.
- biz_people: every named party with its role spelled out, city and state only (the registered agent's from the
  registered office); is_entity when the name has a legal ending or an organization word (the file doesn't say).
- biz_filings: every filing history record.
- Duplicate Master IDs in one file keep the last record.
