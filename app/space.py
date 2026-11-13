"""The FURP space: a login (magic link only) and private folders for named people, with an admin page (owner, 2026-11-11).

Who
- Super admins (SPACE_SUPER_ADMINS in .env, default the owner, or space_people.is_super): see the whole tree, upload
  anywhere, add or remove people by email, create folders, change any visibility.
- Named people (space_people): one folder each. They see FURP as usual plus their own folder, nothing of anyone else's.
  Only they (and super admins) upload to it or change what is in it.
- Only emails in space_people (or on the Deep Queries allow-list) get a login link: login_allowed(), used by
  app/accounts.py. Login itself is the existing magic link (Postmark); no passwords.

Visibility, on every file and folder
- private: owner and super admins only; FURP's own analysis does not read it.
- furp (the default): FURP may read it internally (furp_readable()), never exposes, links to or quotes it. To a
  visitor it looks exactly like private.
- public: a stable URL, /p/<token>/<filename>, open to anyone with the link, no login. Setting it asks for an explicit
  confirm on a warning page first; setting it back clears the token, so the URL stops working.
A folder's mark is the default for its new uploads; a public folder also lists its public files at /p/f/<token>.

Storage: the private Azure container (app/blobfiles.py); every download goes through serve() so the rules run on each
request. Nothing is deleted: "remove" sets removed_at and hides the row. space_log records every change.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import re
import secrets
import tempfile
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse

from app import accounts, blobfiles, db

router = APIRouter()
log = logging.getLogger("np.space")

VISIBILITIES = ("private", "furp", "public")
VIS_LABEL = {"private": "Private", "furp": "FURP-readable", "public": "Public"}
SUPER_ADMINS = {e.strip().lower() for e in os.environ.get("SPACE_SUPER_ADMINS", "mfolenick@gmail.com").split(",") if e.strip()}
MAX_UPLOAD = int(os.environ.get("SPACE_MAX_UPLOAD_MB", "2048")) * 1024 * 1024   # 2 GB (owner, 2026-11-12: "we have LOTS of space")
INLINE_PREFIXES = ("application/pdf", "image/", "text/plain", "video/", "audio/")
FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,59}$")


# --- who is who ---------------------------------------------------------------------------------

def person_for(conn, user: dict | None) -> dict | None:
    """The space_people row for a logged-in user (active, with that email), or None."""
    if not user:
        return None
    return conn.execute("SELECT * FROM space_people WHERE lower(email) = lower(%s) AND removed_at IS NULL",
                        (user["email"],)).fetchone()


def is_super(user: dict | None, person: dict | None) -> bool:
    return bool(user) and (user["email"].lower() in SUPER_ADMINS or bool(person and person["is_super"]))


def login_allowed(email: str) -> bool:
    """Only emails the owner added get a login link: a named person, a super admin, or the Deep Queries allow-list."""
    e = (email or "").lower()
    if e in SUPER_ADMINS:
        return True
    from app import deep
    if e in deep.allow_list():
        return True
    try:
        with db.conn() as conn:
            return bool(conn.execute("SELECT 1 FROM space_people WHERE lower(email) = %s AND removed_at IS NULL", (e,)).fetchone())
    except Exception:  # noqa: BLE001 - table not there yet
        log.exception("login_allowed")
        return False


def can_manage(folder: dict, person: dict | None, super_: bool) -> bool:
    """Upload to the folder and change what is in it: the folder's person and super admins."""
    return super_ or bool(person and folder["person_id"] == person["id"])


def can_see_file(f: dict, folder: dict, person: dict | None, super_: bool) -> bool:
    """On the site (logged in). A furp item is as private as a private one to people."""
    return can_manage(folder, person, super_)


def furp_readable(conn) -> list[dict]:
    """The files FURP's own analysis may read: furp-marked files in folders that are not private. Never private ones.
    Read bytes with blobfiles.stream(row["blob_path"]). Nothing from here may be shown, linked or quoted publicly."""
    return conn.execute("""SELECT f.*, d.name AS folder FROM space_files f JOIN space_folders d ON d.id = f.folder_id
                           WHERE f.removed_at IS NULL AND f.visibility IN ('furp', 'public') AND d.visibility <> 'private'
                           ORDER BY d.name, f.filename""").fetchall()


def _log(conn, who: str | None, action: str, folder: str | None = None, file_id: int | None = None, detail: str | None = None) -> None:
    conn.execute("INSERT INTO space_log (who, action, folder, file_id, detail) VALUES (%s, %s, %s, %s, %s)",
                 (who, action, folder, file_id, detail))


# --- helpers -------------------------------------------------------------------------------------

def _render(request: Request, template: str, status_code: int = 200, **ctx) -> HTMLResponse:
    from app.main import render
    resp = render(request, template, status_code=status_code, **ctx)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _ctx(request: Request, conn) -> dict:
    user = accounts.current_user(request)
    person = person_for(conn, user)
    return {"user": user, "person": person, "super_": is_super(user, person), "csrf": accounts.csrf(user),
            "vis_label": VIS_LABEL, "visibilities": VISIBILITIES}


def _folders_for(conn, person: dict | None, super_: bool) -> list[dict]:
    if super_:
        return conn.execute("""SELECT d.*, p.name AS person_name, p.email AS person_email,
                                      (SELECT count(*) FROM space_files f WHERE f.folder_id = d.id AND f.removed_at IS NULL) AS n_files
                               FROM space_folders d LEFT JOIN space_people p ON p.id = d.person_id ORDER BY d.name""").fetchall()
    if not person:
        return []
    return conn.execute("""SELECT d.*, p.name AS person_name, p.email AS person_email,
                                  (SELECT count(*) FROM space_files f WHERE f.folder_id = d.id AND f.removed_at IS NULL) AS n_files
                           FROM space_folders d LEFT JOIN space_people p ON p.id = d.person_id
                           WHERE d.person_id = %s ORDER BY d.name""", (person["id"],)).fetchall()


def _human(n: int | None) -> str:
    n = n or 0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _person_files(conn, person_id: int, limit: int = 200) -> list[dict]:
    """The files in a person's folders, newest first, with the folder name."""
    return conn.execute("""SELECT f.*, d.name AS folder_name, d.visibility AS folder_vis FROM space_files f JOIN space_folders d ON d.id = f.folder_id
                           WHERE d.person_id = %s AND f.removed_at IS NULL ORDER BY f.uploaded_at DESC, f.id DESC LIMIT %s""",
                        (person_id, limit)).fetchall()


def _user_id_for(conn, person: dict | None) -> int | None:
    if not person or not person.get("email"):
        return None
    row = conn.execute("SELECT id FROM users WHERE lower(email) = lower(%s) ORDER BY id LIMIT 1", (person["email"],)).fetchone()
    return row["id"] if row else None


def _deep_queries(conn, user_id: int | None, limit: int = 100) -> list[dict]:
    if not user_id:
        return []
    try:
        return conn.execute("""SELECT id, question, status, created_at, cost_usd FROM deep_queries
                               WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""", (user_id, limit)).fetchall()
    except Exception:  # noqa: BLE001 - deep queries not set up here
        log.exception("space: deep queries")
        return []


# --- query history: every search and question a logged-in person runs (owner, 2026-11-12) ----------------------
# The table is created on first use rather than by a migration: two other loads were adding migrations the same
# day (0077, 0078) and alembic needs one linear chain; a small IF NOT EXISTS keeps this independent of them.
HISTORY_LIMIT = 200
_history_ready = False
HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS user_queries (
    id bigserial PRIMARY KEY, user_id integer NOT NULL, at timestamptz NOT NULL DEFAULT now(),
    kind text NOT NULL, q text NOT NULL, url text NOT NULL, detail text);
CREATE INDEX IF NOT EXISTS user_queries_user_at ON user_queries (user_id, at DESC);
"""


def _ensure_history(conn) -> None:
    global _history_ready
    if not _history_ready:
        conn.execute(HISTORY_SQL)
        _history_ready = True


def record_query(request, q: str, kind: str, detail: str | None = None) -> None:
    """Remember a search or question for the logged-in person's history (nothing for visitors). Never raises."""
    try:
        user = accounts.current_user(request)
        if not user or not q:
            return
        url = str(request.url.path) + ("?" + request.url.query if request.url.query else "")
        with db.conn() as conn:
            _ensure_history(conn)
            conn.execute("INSERT INTO user_queries (user_id, kind, q, url, detail) VALUES (%s, %s, %s, %s, %s)",
                         (user["id"], kind[:40], q[:500], url[:2000], (detail or None) and detail[:200]))
    except Exception:  # noqa: BLE001
        log.exception("space: recording a query")


def _history(conn, user_id: int | None, limit: int = HISTORY_LIMIT) -> list[dict]:
    if not user_id:
        return []
    try:
        _ensure_history(conn)
        return conn.execute("SELECT at, kind, q, url FROM user_queries WHERE user_id = %s ORDER BY at DESC, id DESC LIMIT %s",
                            (user_id, limit)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("space: history")
        return []


def _files(conn, folder_id: int) -> list[dict]:
    return conn.execute("SELECT * FROM space_files WHERE folder_id = %s AND removed_at IS NULL ORDER BY uploaded_at DESC, id DESC",
                        (folder_id,)).fetchall()


def _login_redirect(path: str) -> RedirectResponse:
    return RedirectResponse("/login?" + urlencode({"next": path}), status_code=303)


def clean_filename(name: str) -> str:
    """The name as uploaded, minus path parts and control characters; never empty."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>').strip().strip(".")
    return name[:180] or "file"


def _blob_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:120] or "file"


def _disposition(filename: str, content_type: str) -> str:
    kind = "inline" if content_type.startswith(INLINE_PREFIXES) else "attachment"
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _send(f: dict) -> Response:
    """The file's bytes with safe headers; the same for the public and the logged-in route."""
    ctype = f["content_type"] if f["content_type"].startswith(INLINE_PREFIXES) else "application/octet-stream"
    headers = {"Content-Disposition": _disposition(f["filename"], f["content_type"]),
               "Content-Length": str(f["size"]), "X-Content-Type-Options": "nosniff",
               "Cache-Control": "private, no-store",
               "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; sandbox"}
    return StreamingResponse(blobfiles.stream(f["blob_path"]), media_type=ctype, headers=headers)


def public_url(f: dict) -> str | None:
    from app.config import SITE_URL
    return f"{SITE_URL}/p/{f['public_token']}/{quote(f['filename'])}" if f.get("public_token") else None


def public_folder_url(d: dict) -> str | None:
    from app.config import SITE_URL
    return f"{SITE_URL}/p/f/{d['public_token']}" if d.get("public_token") else None


# --- pages: the person's space and a folder ----------------------------------------------------------

@router.get("/space", response_class=HTMLResponse)
def space_home(request: Request, person: int | None = None):
    """One page per person (owner, 2026-11-12: it was disjointed): the folder link first and big, the files they
    loaded, their deep queries and their query history. A super admin picks whose space to see (?person=<id>, the
    switcher at the top); anyone else sees only their own."""
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"]:
            return _login_redirect("/space")
        viewing, own = c["person"], True
        people = []
        if c["super_"]:
            people = conn.execute("SELECT id, name, email FROM space_people WHERE removed_at IS NULL ORDER BY name").fetchall()
            if person is not None:
                viewing = next((p for p in people if p["id"] == person), None)
                own = bool(viewing and c["person"] and viewing["id"] == c["person"]["id"])
                if not viewing:
                    return _render(request, "space_denied.html", status_code=404, **c)
        elif person is not None and not (c["person"] and person == c["person"]["id"]):
            return _render(request, "space_denied.html", status_code=404, **c)
        folders = _folders_for(conn, viewing, False) if viewing else []
        files = [dict(f, public_url=public_url(f), size_human=_human(f.get("size"))) for f in _person_files(conn, viewing["id"])] \
            if viewing else []
        files = _with_ingest(conn, files)
        uid = c["user"]["id"] if own else _user_id_for(conn, viewing)
        return _render(request, "space_home.html", viewing=viewing, own=own, people=people,
                       folders=[dict(d, public_url=public_folder_url(d)) for d in folders], files=files,
                       deep=_deep_queries(conn, uid), history=_history(conn, uid), history_limit=HISTORY_LIMIT, **c)


@router.get("/space/{folder}", response_class=HTMLResponse)
def space_folder(request: Request, folder: str, msg: str = ""):
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"]:
            return _login_redirect(f"/space/{quote(folder)}")
        d = conn.execute("""SELECT d.*, p.name AS person_name, p.email AS person_email FROM space_folders d
                            LEFT JOIN space_people p ON p.id = d.person_id WHERE d.name = %s""", (folder,)).fetchone()
        if not d or not can_manage(d, c["person"], c["super_"]):
            return _render(request, "space_denied.html", status_code=404, **c)
        files = _with_ingest(conn, [dict(f, public_url=public_url(f), folder_vis=d["visibility"]) for f in _files(conn, d["id"])])
        return _render(request, "space_folder.html", folder=dict(d, public_url=public_folder_url(d)), files=files,
                       msg=msg[:40], max_mb=MAX_UPLOAD // (1024 * 1024), **c)


@router.post("/space/{folder}/upload")
async def space_upload(request: Request, folder: str):
    """One or more files into the folder. Multipart; the whole body is capped by nginx (deploy/nginx/furp.org) and
    each file by MAX_UPLOAD here. Read to a temp file while hashing, then stored under <folder>/<id>-<name>."""
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"]:
            return _login_redirect(f"/space/{quote(folder)}")
        d = conn.execute("SELECT * FROM space_folders WHERE name = %s", (folder,)).fetchone()
        if not d or not can_manage(d, c["person"], c["super_"]):
            return _render(request, "space_denied.html", status_code=404, **c)
    form = await request.form()
    if not accounts.csrf_ok(c["user"], {"csrf": form.get("csrf", "")}):
        return RedirectResponse("/login?" + urlencode({"next": f"/space/{folder}"}), status_code=303)
    vis = form.get("visibility") or d["visibility"]
    vis = vis if vis in ("private", "furp") else d["visibility"] if d["visibility"] != "public" else "furp"   # public only via the confirm page
    uploads = [u for u in form.getlist("file") if getattr(u, "filename", None)]
    if not uploads:
        return RedirectResponse(f"/space/{quote(folder)}?msg=nofile", status_code=303)
    stored = too_big = 0
    for up in uploads:
        name = clean_filename(up.filename)
        ctype = (up.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream").split(";")[0].strip()[:100]
        h, size = hashlib.sha256(), 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
            while chunk := await up.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    too_big += 1
                    break
                h.update(chunk)
                tmp.write(chunk)
            else:
                tmp.seek(0)
                with db.conn() as conn:
                    row = conn.execute("""INSERT INTO space_files (folder_id, owner_id, filename, blob_path, visibility, uploader, size, content_type, sha256)
                                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                                       (d["id"], d["person_id"], name, f"pending-{secrets.token_hex(8)}", vis, c["user"]["email"], size, ctype, h.hexdigest())).fetchone()
                    path = f"{_blob_name(d['name'])}/{row['id']}-{_blob_name(name)}"
                    try:
                        blobfiles.put(path, tmp, ctype, size)
                    except Exception:  # noqa: BLE001
                        log.exception("space: upload to blob failed")
                        conn.execute("UPDATE space_files SET removed_at = now(), removed_by = 'upload failed' WHERE id = %s", (row["id"],))
                        return RedirectResponse(f"/space/{quote(folder)}?msg=storage", status_code=303)
                    conn.execute("UPDATE space_files SET blob_path = %s WHERE id = %s", (path, row["id"]))
                    _log(conn, c["user"]["email"], "upload", d["name"], row["id"], f"{size} bytes {ctype} {vis}")
                    stored += 1
                _ingest(row["id"])            # into the brain, in the background (app/space_ingest.py; owner, 2026-11-12)
        await up.close()
    msg = f"stored{stored}" + (f"big{too_big}" if too_big else "")
    return RedirectResponse(f"/space/{quote(folder)}?msg={msg}", status_code=303)


@router.post("/space/{folder}/visibility", response_class=HTMLResponse)
async def space_visibility(request: Request, folder: str):
    """Change a file's or the folder's mark. Public needs the warning page and an explicit confirm; the warning
    page posts back here with confirm=1."""
    form = await accounts._form(request)
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"] or not accounts.csrf_ok(c["user"], form):
            return _login_redirect(f"/space/{quote(folder)}")
        d = conn.execute("SELECT * FROM space_folders WHERE name = %s", (folder,)).fetchone()
        if not d or not can_manage(d, c["person"], c["super_"]):
            return _render(request, "space_denied.html", status_code=404, **c)
        vis = form.get("visibility", "")
        if vis not in VISIBILITIES:
            return RedirectResponse(f"/space/{quote(folder)}", status_code=303)
        fid = form.get("file_id", "")
        f = None
        if fid:
            if not fid.isdigit():
                return RedirectResponse(f"/space/{quote(folder)}", status_code=303)
            f = conn.execute("SELECT * FROM space_files WHERE id = %s AND folder_id = %s AND removed_at IS NULL", (int(fid), d["id"])).fetchone()
            if not f:
                return RedirectResponse(f"/space/{quote(folder)}?msg=missing", status_code=303)
        if vis == "public" and form.get("confirm") != "1":
            return _render(request, "space_confirm.html", folder=d, file=f, **c)
        who = c["user"]["email"]
        if f:
            token = (f["public_token"] or secrets.token_urlsafe(18)) if vis == "public" else None
            conn.execute("""UPDATE space_files SET visibility = %s, public_token = %s,
                                public_at = CASE WHEN %s = 'public' THEN coalesce(public_at, now()) ELSE NULL END WHERE id = %s""",
                         (vis, token, vis, f["id"]))
            _log(conn, who, "visibility", d["name"], f["id"], f"{f['visibility']} -> {vis}")
            _ingest(f["id"])                  # public: mirror its links and page; furp: internal only; private: delete its rows
        else:
            token = (d["public_token"] or secrets.token_urlsafe(18)) if vis == "public" else None
            conn.execute("""UPDATE space_folders SET visibility = %s, public_token = %s,
                                public_at = CASE WHEN %s = 'public' THEN coalesce(public_at, now()) ELSE NULL END WHERE id = %s""",
                         (vis, token, vis, d["id"]))
            _log(conn, who, "folder visibility", d["name"], None, f"{d['visibility']} -> {vis}")
            _ingest_folder(d["id"])           # a private folder makes every file in it unreadable to FURP
    return RedirectResponse(f"/space/{quote(folder)}?msg=changed", status_code=303)


@router.post("/space/{folder}/remove")
async def space_remove(request: Request, folder: str):
    """Hide a file (its row and blob stay; nothing is deleted). The folder's person and super admins."""
    form = await accounts._form(request)
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"] or not accounts.csrf_ok(c["user"], form):
            return _login_redirect(f"/space/{quote(folder)}")
        d = conn.execute("SELECT * FROM space_folders WHERE name = %s", (folder,)).fetchone()
        fid = form.get("file_id", "")
        if not d or not can_manage(d, c["person"], c["super_"]) or not fid.isdigit():
            return _render(request, "space_denied.html", status_code=404, **c)
        conn.execute("""UPDATE space_files SET removed_at = now(), removed_by = %s, public_token = NULL
                        WHERE id = %s AND folder_id = %s AND removed_at IS NULL""", (c["user"]["email"], int(fid), d["id"]))
        _log(conn, c["user"]["email"], "remove", d["name"], int(fid))
        _ingest(int(fid))                     # removed: its extracted rows and links go
    return RedirectResponse(f"/space/{quote(folder)}?msg=removed", status_code=303)


# --- serving files: logged in, and public ------------------------------------------------------------

@router.get("/space/file/{file_id}/{filename}")
def serve(request: Request, file_id: int, filename: str):
    with db.conn() as conn:
        c = _ctx(request, conn)
        f = conn.execute("SELECT * FROM space_files WHERE id = %s AND removed_at IS NULL", (file_id,)).fetchone()
        if f and f["visibility"] == "public" and f["public_token"]:
            return RedirectResponse(f"/p/{f['public_token']}/{quote(f['filename'])}", status_code=302)
        if not c["user"]:
            return _login_redirect(f"/space/file/{file_id}/{quote(filename)}")
        d = conn.execute("SELECT * FROM space_folders WHERE id = %s", (f["folder_id"],)).fetchone() if f else None
        if not f or not d or not can_see_file(f, d, c["person"], c["super_"]):
            return _render(request, "space_denied.html", status_code=404, **c)
    return _send(f)


@router.get("/p/f/{token}", response_class=HTMLResponse)
def public_folder(request: Request, token: str):
    """A public folder: the list of its public files (its private and furp files stay hidden)."""
    with db.conn() as conn:
        d = conn.execute("SELECT * FROM space_folders WHERE public_token = %s AND visibility = 'public'", (token,)).fetchone() \
            if 10 < len(token) < 64 else None
        if not d:
            return _render(request, "space_denied.html", status_code=404, user=None, person=None, super_=False, csrf="")
        files = [dict(f, public_url=public_url(f)) for f in conn.execute(
            "SELECT * FROM space_files WHERE folder_id = %s AND removed_at IS NULL AND visibility = 'public' AND public_token IS NOT NULL ORDER BY filename",
            (d["id"],)).fetchall()]
    resp = _render(request, "space_public_folder.html", folder=d, files=files, user=None, person=None, super_=False, csrf="")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/p/{token}/{filename}")
def public_file(token: str, filename: str):
    with db.conn() as conn:
        f = conn.execute("SELECT * FROM space_files WHERE public_token = %s AND visibility = 'public' AND removed_at IS NULL", (token,)).fetchone() \
            if 10 < len(token) < 64 else None
    if not f:
        return Response("Not found", status_code=404, media_type="text/plain")
    resp = _send(f)
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


# --- admin -------------------------------------------------------------------------------------------

def _people(conn) -> list[dict]:
    return conn.execute("""SELECT p.*, (SELECT string_agg(d.name, ', ' ORDER BY d.name) FROM space_folders d WHERE d.person_id = p.id) AS folders
                           FROM space_people p ORDER BY p.removed_at IS NOT NULL, p.name""").fetchall()


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, msg: str = ""):
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"]:
            return _login_redirect("/admin")
        if not c["super_"]:
            return _render(request, "space_denied.html", status_code=404, **c)
        folders = [dict(d, public_url=public_folder_url(d)) for d in _folders_for(conn, c["person"], True)]
        recent = conn.execute("SELECT * FROM space_log ORDER BY at DESC LIMIT 30").fetchall()
        from app import llm_fallback
        return _render(request, "space_admin.html", people=_people(conn), folders=folders, recent=recent, msg=msg[:40],
                       llm_attempts=llm_fallback.recent_attempts(), llm_models=llm_fallback.models(), **c)


@router.post("/admin/people")
async def admin_people(request: Request):
    """add (email, name, folder), remove (person_id), restore (person_id), email (person_id, email), folder (name,
    person_id). Nothing is deleted: removing a person hides them and ends their login; their folder and files stay."""
    form = await accounts._form(request)
    with db.conn() as conn:
        c = _ctx(request, conn)
        if not c["user"] or not accounts.csrf_ok(c["user"], form):
            return _login_redirect("/admin")
        if not c["super_"]:
            return _render(request, "space_denied.html", status_code=404, **c)
        who, action = c["user"]["email"], form.get("action", "")
        pid = form.get("person_id", "")
        if action == "add":
            email = accounts.normalize_email(form.get("email"))
            name = re.sub(r"\s+", " ", form.get("name", "")).strip()[:120]
            folder = form.get("folder", "").strip() or (name.split()[-1] if name else "")
            if not name or not FOLDER_RE.match(folder):
                return RedirectResponse("/admin?msg=badinput", status_code=303)
            if form.get("email") and not email:
                return RedirectResponse("/admin?msg=bademail", status_code=303)
            if email and conn.execute("SELECT 1 FROM space_people WHERE lower(email) = %s", (email,)).fetchone():
                conn.execute("UPDATE space_people SET removed_at = NULL, removed_by = NULL, name = %s WHERE lower(email) = %s", (name, email))
                p = conn.execute("SELECT * FROM space_people WHERE lower(email) = %s", (email,)).fetchone()
            else:
                p = conn.execute("INSERT INTO space_people (email, name, added_by) VALUES (%s, %s, %s) RETURNING *", (email, name, who)).fetchone()
            if conn.execute("SELECT 1 FROM space_folders WHERE name = %s", (folder,)).fetchone():
                if not conn.execute("SELECT 1 FROM space_folders WHERE person_id = %s", (p["id"],)).fetchone():
                    return RedirectResponse("/admin?msg=foldertaken", status_code=303)
            else:
                conn.execute("INSERT INTO space_folders (name, person_id, created_by) VALUES (%s, %s, %s)", (folder, p["id"], who))
            _log(conn, who, "add person", folder, None, f"{name} <{email or 'no email yet'}>")
            return RedirectResponse("/admin?msg=added", status_code=303)
        if not pid.isdigit():
            return RedirectResponse("/admin?msg=badinput", status_code=303)
        p = conn.execute("SELECT * FROM space_people WHERE id = %s", (int(pid),)).fetchone()
        if not p:
            return RedirectResponse("/admin?msg=missing", status_code=303)
        if action == "remove":
            if (p["email"] or "").lower() in SUPER_ADMINS:
                return RedirectResponse("/admin?msg=owner", status_code=303)
            conn.execute("UPDATE space_people SET removed_at = now(), removed_by = %s WHERE id = %s", (who, p["id"]))
            if p["email"]:
                conn.execute("DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE lower(email) = lower(%s))", (p["email"],))
            _log(conn, who, "remove person", None, None, f"{p['name']} <{p['email']}>")
            return RedirectResponse("/admin?msg=removed", status_code=303)
        if action == "restore":
            conn.execute("UPDATE space_people SET removed_at = NULL, removed_by = NULL WHERE id = %s", (p["id"],))
            _log(conn, who, "restore person", None, None, f"{p['name']} <{p['email']}>")
            return RedirectResponse("/admin?msg=restored", status_code=303)
        if action == "email":
            email = accounts.normalize_email(form.get("email"))
            if not email:
                return RedirectResponse("/admin?msg=bademail", status_code=303)
            if conn.execute("SELECT 1 FROM space_people WHERE lower(email) = %s AND id <> %s", (email, p["id"])).fetchone():
                return RedirectResponse("/admin?msg=emailtaken", status_code=303)
            conn.execute("UPDATE space_people SET email = %s WHERE id = %s", (email, p["id"]))
            _log(conn, who, "set email", None, None, f"{p['name']}: {p['email']} -> {email}")
            return RedirectResponse("/admin?msg=emailset", status_code=303)
        if action == "super":
            on = form.get("on") == "1"
            if not on and (p["email"] or "").lower() in SUPER_ADMINS:
                return RedirectResponse("/admin?msg=owner", status_code=303)
            conn.execute("UPDATE space_people SET is_super = %s WHERE id = %s", (on, p["id"]))
            _log(conn, who, "super admin " + ("on" if on else "off"), None, None, f"{p['name']} <{p['email']}>")
            return RedirectResponse("/admin?msg=changed", status_code=303)
        if action == "folder":
            folder = form.get("folder", "").strip()
            if not FOLDER_RE.match(folder) or conn.execute("SELECT 1 FROM space_folders WHERE name = %s", (folder,)).fetchone():
                return RedirectResponse("/admin?msg=foldertaken", status_code=303)
            conn.execute("INSERT INTO space_folders (name, person_id, created_by) VALUES (%s, %s, %s)", (folder, p["id"], who))
            _log(conn, who, "create folder", folder, None, f"for {p['name']}")
            return RedirectResponse("/admin?msg=foldermade", status_code=303)
    return RedirectResponse("/admin", status_code=303)


# --- into the brain: app/space_ingest.py (owner, 2026-11-12) ----------------------------------------------------

def _ingest(file_id: int) -> None:
    """Queue the file's ingestion (checks, extraction, cross-reference, exposure by mark) in the background."""
    try:
        from app import space_ingest
        space_ingest.enqueue(file_id)
    except Exception:  # noqa: BLE001 - the sweep (loader/space_ingest.py) picks it up later
        log.exception("space: queueing ingestion of file %s", file_id)


def _ingest_folder(folder_id: int) -> None:
    try:
        from app import space_ingest
        space_ingest.enqueue_folder(folder_id)
    except Exception:  # noqa: BLE001
        log.exception("space: queueing ingestion of folder %s", folder_id)


def _with_ingest(conn, files: list[dict]) -> list[dict]:
    """Each file dict with "ingest": what happened to it in the brain (shown next to the file)."""
    try:
        from app import space_ingest
        st = space_ingest.status_for(conn, files)
    except Exception:  # noqa: BLE001 - never fail the page over the status column
        log.exception("space: ingestion status")
        st = {}
    return [dict(f, ingest=st.get(f["id"])) for f in files]


# --- the bar at the top of every page for a logged-in person (base.html) ------------------------------

def bar(request) -> dict | None:
    """Logged in: email, the person's folder (if any), whether they are a super admin, and a CSRF token for the
    logout button. None when logged out, so pages for visitors are untouched. One pooled query per page view with
    a session cookie; nothing for anyone else."""
    try:
        user = accounts.current_user(request)
        if not user:
            return None
        with db.conn() as conn:
            person = person_for(conn, user)
            folders = _folders_for(conn, person, False) if person else []
        return {"email": user["email"], "folder": folders[0]["name"] if len(folders) == 1 else None,
                "super": is_super(user, person), "csrf": accounts.csrf(user), "named": bool(person)}
    except Exception:  # noqa: BLE001 - never break a page over the bar
        log.exception("space bar")
        return None
