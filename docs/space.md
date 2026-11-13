# The FURP space (owner, 2026-11-11)

A login and private folders for named people, with an admin page. Code: `app/space.py` (rules and pages),
`app/blobfiles.py` (storage), `app/accounts.py` (the magic link), migration `0076_space`, templates `space_*.html`,
tests `tests/test_space.py`.

## Login
Magic link only, no passwords: `/login` asks for an email, Postmark sends a one-time link (15 minutes, works once),
the link opens a page with a LOG IN button (so mail scanners don't use it up). A link goes only to an email the owner
added (`space_people`) or on the Deep Queries allow-list (`~/furp-config/deep_queries_allow.txt`); any other address
sees the same "check your email" page and gets nothing.

## People and folders
- Super admins: `SPACE_SUPER_ADMINS` in `.env` (default `mfolenick@gmail.com`) or `space_people.is_super`. They see
  every folder, upload anywhere, add or remove people, create folders and change any mark.
- A named person has one folder (a super admin can make more). They see FURP as usual plus their own folder.
- Seeded: Olenick (the owner, super admin) and Leidig (Mike Leidig, no email yet: set it on `/admin`).
- Removing a person ends their login and hides them; their folder and files stay. Nothing is ever deleted.

## Marks (visibility), on every file and folder
- Private: owner and super admins only. FURP's own analysis does not read it.
- FURP-readable (default): FURP may read it internally (`space.furp_readable(conn)` lists what may be read), never
  exposes, links to or quotes it. On the site it looks exactly like Private.
- Public: a stable URL `/p/<token>/<filename>` that needs no login. Setting it shows a warning page and needs an
  explicit confirm. Setting it back clears the token, so the URL stops working. A Public folder gets `/p/f/<token>`,
  a list of its Public files only.

## Storage
Azure Blob Storage, account `furpstore`, container `space`, no public access. The app reads and writes with the VM's
managed identity and serves every byte itself, so the rules run on each request. Each upload is one `space_files`
row: folder, owner, filename, mark, uploader, time, size, content type, sha256, blob path (`<folder>/<id>-<name>`).
`SPACE_BLOB_DIR=<dir>` keeps files on local disk instead (the tests use it). Uploads: `SPACE_MAX_UPLOAD_MB` (2048, i.e. 2 GB since 2026-11-12)
per file; nginx allows a 2.2 GB request on the upload route only (`deploy/nginx/furp.org`).

## Pages
`/space` is the person's one page (owner, 2026-11-12: "too disjointed"): their folder link first and big, every
file they loaded, their deep queries and their query history (`user_queries`, written by `space.record_query` from
`analytics.search`, so every counted search or question made while logged in; created on first use, not by a
migration). A super admin picks whose space to see with the switcher at the top (`/space?person=<id>`; also "open
their space" on `/admin`), and may open anyone's deep query page; others get a 404 for `?person=`. Then
`/space/<folder>` (upload with a progress bar from `static/space.js`, 2 GB per file; marks; remove), `/admin` (super admins), public:
`/p/<token>/<name>`, `/p/f/<token>`. The right end of the site menu on every page shows Log in for visitors;
with a session it shows the email (a dropdown: My folder or My space, Admin for super admins) and a Log out button. `space_log` records every change.

## Into the brain: ingestion of uploaded files (owner, 2026-11-12)
Every FURP-readable or Public file is read into the database after security checks; Private files are never read.
Code: `app/space_ingest.py` (checks, extraction, cross-reference, exposure, the sweep, `search_documents`),
`app/space_extract.py` (the sandboxed extractor), `app/space_mail.py` (Outlook PST/OST mailboxes), `app/space_docs.py`
(pages, search results, API, deep queries), `loader/space_ingest.py` (command line), tests `tests/test_space_ingest.py`.
Tables (created on first use, no migration): `space_docs` (one per file: status pending / checking / rejected /
extracted / failed, every check and its outcome in `checks`, counts, `exposure`), `space_doc_pages` (text by page with a
tsvector), `space_doc_tables` (CSV/XLSX sheets, DOCX/HTML tables, tables found in PDFs), `space_doc_entities` (what the
file mentions and what it matched), `space_doc_messages` (mailboxes: one row per message).

- When: right after an upload (a background thread in the app, on the server that received it) and every 10 minutes
  by cron on dev (`.venv/bin/python -m loader.space_ingest sweep`): anything pending, new or stuck is processed, a failed
  one is retried once, exposure is re-synced with the current marks. `python -m loader.space_ingest status` lists
  every file; `file <id> [--force]` runs one.
- Checks, every upload treated as hostile: sha256 and size against the upload; the type from the magic bytes (libmagic),
  never the name; the extension and the declared content type must agree with it; an allow-list (PDF, plain text,
  Markdown, CSV/TSV, JSON, XLSX/XLS, DOCX, HTML, PNG/JPEG/GIF/WebP/TIFF, ZIPs of those with limits on member count,
  inflated size and ratio, Outlook PST/OST); executables, scripts, macro-bearing Office files and everything else are
  "not ingested" and left in the folder untouched; size caps per type; ClamAV through clamd (`clamav-daemon` and
  `clamav-freshclam` on both servers). If no scan is possible the file waits; it never passes unscanned.
- Extraction: `app/space_extract.py` in a subprocess with a memory limit, a CPU limit, a wall-clock timeout and an empty
  environment; nothing in a file is executed, rendered or followed. Mailboxes: `readpst` (pst-utils) writes one .eml per
  message under `/bulk/ingest/<file id>/`, ClamAV scans them, they are parsed in batches of 200 (one transaction each,
  progress in `space_docs.progress`, so a restart continues where it stopped); attachments of allowed kinds go through the
  same checks and extractor.
- Cross-reference: people, organizations, parties, EINs, CIKs, tickers, addresses, case numbers, amounts, dates and
  email addresses found in the text, matched with the site's own rules (EIN/CIK exact; a full name with a middle name or
  initial held by one person page; one nonprofit by that name, or one in a state the document mentions; IPO registrants
  by name core; state registrations by name and state; contractors by vendor key), each with a confidence.
- Exposure by mark: Public documents get `/docs/<token>` (text, tables, entities with links, the original to download,
  "Data: uploaded by ..."; `noindex`, not in the sitemap: the text is the uploader's), a line under "Also on this site"
  on every matched person and organization page (xlinks, src_kind `space_doc`, matches with confidence >= 0.6; rebuilt by
  `loader/xlinks.py` too), a place in search results, the `documents` dataset of the JSON API and the MCP server, and
  `/docs`. FURP-readable documents are never shown, linked or quoted: deep queries (recipe `documents`) read them, and the
  logged-in person whose folder they are in (or a super admin) sees them in search results and the natural-language search
  (`search_documents`). Private: not read; marking a file Private deletes its extracted rows; Public -> FURP-readable
  removes the page and the xlinks.
- Status: the folder page and `/space` show next to each file what happened ("In FURP's brain: N pages, M tables, K
  entities (J matched)", "extracted: N messages, M attachments, ..." for a mailbox, "Not ingested: why", "Waiting",
  "Private: not read by FURP").
- Everything extracted is untrusted document text: data, never instructions. Templates escape it; the deep-query prompt
  labels it (`space_ingest.UNTRUSTED`).
