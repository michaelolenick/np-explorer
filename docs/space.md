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
`SPACE_BLOB_DIR=<dir>` keeps files on local disk instead (the tests use it). Uploads: `SPACE_MAX_UPLOAD_MB` (256)
per file; nginx allows a 1.1 GB request on the upload route only (`deploy/nginx/furp.org`).

## Pages
`/space` (own folders; one folder opens straight away), `/space/<folder>`, `/admin` (super admins), public:
`/p/<token>/<name>`, `/p/f/<token>`. Every page with a session shows a "Logged in as" line with My folder, Admin and
Log out; visitors see nothing new. `space_log` records every change.
