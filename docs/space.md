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
