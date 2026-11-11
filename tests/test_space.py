"""The FURP space (owner, 2026-11-11): who may log in, who sees what, uploads, visibility and the public URL.

Runs against the shared database (as the other tests do) with files kept on local disk (SPACE_BLOB_DIR), so no Azure
call is made. Test people and files are created and removed by the tests (the rows they add carry the test marker in
their names)."""

import contextlib
import os
import secrets

import pytest
from starlette.testclient import TestClient

from app import accounts, db, space

MARK = "pytest-space"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["SPACE_BLOB_DIR"] = str(tmp_path_factory.mktemp("blobs"))
    from app.main import app
    db.pool.open(wait=False)            # as tests/test_attribution.py: no `with`, its lifespan closes the shared pool
    return TestClient(app)


@contextlib.contextmanager
def person(email: str, folder: str, super_: bool = False):
    """A space person with a folder and a live session cookie; everything is removed afterwards."""
    token = secrets.token_urlsafe(32)
    with db.conn() as conn:
        conn.execute("DELETE FROM space_log WHERE folder = %s", (folder,))
        conn.execute("DELETE FROM space_files WHERE folder_id IN (SELECT id FROM space_folders WHERE name = %s)", (folder,))
        conn.execute("DELETE FROM space_folders WHERE name = %s", (folder,))
        conn.execute("DELETE FROM space_people WHERE email = %s", (email,))
        p = conn.execute("INSERT INTO space_people (email, name, is_super, added_by) VALUES (%s, %s, %s, %s) RETURNING id",
                         (email, f"{MARK} {folder}", super_, MARK)).fetchone()
        conn.execute("INSERT INTO space_folders (name, person_id, created_by) VALUES (%s, %s, %s)", (folder, p["id"], MARK))
        u = conn.execute("""INSERT INTO users (email, name, auth_method, status, last_login) VALUES (%s, %s, 'email', 'active', now())
                            ON CONFLICT (email) DO UPDATE SET last_login = now() RETURNING id""", (email, MARK)).fetchone()
        conn.execute("INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + interval '1 hour')",
                     (accounts._hash(token), u["id"]))
    try:
        yield {"email": email, "folder": folder, "cookie": token, "person_id": p["id"], "user_id": u["id"]}
    finally:
        with db.conn() as conn:
            conn.execute("DELETE FROM space_log WHERE folder = %s OR who = %s", (folder, email))
            conn.execute("DELETE FROM space_files WHERE folder_id IN (SELECT id FROM space_folders WHERE name = %s)", (folder,))
            conn.execute("DELETE FROM space_folders WHERE name = %s", (folder,))
            conn.execute("DELETE FROM space_people WHERE id = %s", (p["id"],))
            conn.execute("DELETE FROM user_sessions WHERE user_id = %s", (u["id"],))
            conn.execute("DELETE FROM users WHERE id = %s AND name = %s", (u["id"], MARK))


def _csrf(client, who) -> str:
    r = client.get(f"/space/{who['folder']}", cookies={accounts.COOKIE: who["cookie"]})
    assert r.status_code == 200, r.text[:300]
    import re
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def _upload(client, who, folder, name=b"hello.txt", data=b"hello space", vis=None):
    csrf = _csrf(client, who)
    fields = {"csrf": csrf}
    if vis:
        fields["visibility"] = vis
    return client.post(f"/space/{folder}/upload", data=fields, files={"file": (name.decode(), data, "text/plain")},
                       cookies={accounts.COOKIE: who["cookie"]}, follow_redirects=False)


def test_login_is_only_for_people_the_owner_added(client, monkeypatch):
    monkeypatch.setattr(space, "SUPER_ADMINS", {"owner@example.test"})
    from app import deep
    monkeypatch.setattr(deep, "DEEP_ALLOWLIST_FILE", "/nonexistent/allow.txt")
    assert space.login_allowed("owner@example.test")
    assert space.login_allowed("mfolenick@gmail.com")              # the Deep Queries default allow-list
    assert not space.login_allowed("stranger@example.test")
    with person("named@example.test", f"{MARK}-named"):
        assert space.login_allowed("Named@Example.test")
    assert not space.login_allowed("named@example.test")           # removed: no link any more


def test_magic_link_is_not_sent_to_strangers(client, monkeypatch):
    sent = []
    from app import mailer
    monkeypatch.setattr(mailer, "send", lambda payload, timeout=20: sent.append(payload) or True)
    from app import contact
    monkeypatch.setattr(contact, "is_bot", lambda form: False)
    r = client.post("/login/email", data={"email": "nobody-" + secrets.token_hex(4) + "@example.test", "next": "/space"}, follow_redirects=False)
    assert r.status_code == 303 and "sent=1" in r.headers["location"]       # the same answer as for a known address
    assert sent == []


def test_logged_out_space_pages_redirect_to_login(client):
    for path in ("/space", "/admin", "/space/Olenick"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login?next="), path
    assert client.get("/p/not-a-real-token-here/x.txt").status_code == 404
    assert client.get("/p/f/not-a-real-token-here").status_code == 404


def test_owner_sees_only_own_folder_and_super_sees_all(client):
    with person("a-" + MARK + "@example.test", f"{MARK}-A") as a, person("b-" + MARK + "@example.test", f"{MARK}-B") as b, \
            person("s-" + MARK + "@example.test", f"{MARK}-S", super_=True) as s:
        ra = client.get(f"/space/{a['folder']}", cookies={accounts.COOKIE: a["cookie"]})
        assert ra.status_code == 200 and ra.headers["cache-control"] == "no-store"
        assert client.get(f"/space/{b['folder']}", cookies={accounts.COOKIE: a["cookie"]}).status_code == 404
        assert client.get("/admin", cookies={accounts.COOKIE: a["cookie"]}).status_code == 404
        home = client.get("/space", cookies={accounts.COOKIE: a["cookie"]}, follow_redirects=False)
        assert home.status_code == 303 and home.headers["location"] == f"/space/{a['folder']}"      # straight to the one folder
        rs = client.get("/space", cookies={accounts.COOKIE: s["cookie"]})
        assert rs.status_code == 200 and a["folder"] in rs.text and b["folder"] in rs.text
        assert client.get("/admin", cookies={accounts.COOKIE: s["cookie"]}).status_code == 200
        assert client.get(f"/space/{b['folder']}", cookies={accounts.COOKIE: s["cookie"]}).status_code == 200


def test_upload_serve_visibility_and_public_url(client):
    with person("u-" + MARK + "@example.test", f"{MARK}-U") as u, person("v-" + MARK + "@example.test", f"{MARK}-V") as v:
        r = _upload(client, u, u["folder"])
        assert r.status_code == 303 and "msg=stored1" in r.headers["location"], r.headers.get("location")
        with db.conn() as conn:
            f = conn.execute("SELECT * FROM space_files WHERE uploader = %s ORDER BY id DESC", (u["email"],)).fetchone()
        assert f["visibility"] == "furp" and f["size"] == 11 and f["content_type"] == "text/plain" and f["filename"] == "hello.txt"
        assert f["sha256"] == __import__("hashlib").sha256(b"hello space").hexdigest()
        assert f["blob_path"].endswith(f"/{f['id']}-hello.txt") and os.path.isfile(os.path.join(os.environ["SPACE_BLOB_DIR"], f["blob_path"]))
        url = f"/space/file/{f['id']}/hello.txt"
        # the owner reads it, a different named person cannot, a visitor is sent to log in
        r = client.get(url, cookies={accounts.COOKIE: u["cookie"]})
        assert r.status_code == 200 and r.content == b"hello space" and r.headers["x-content-type-options"] == "nosniff"
        assert client.get(url, cookies={accounts.COOKIE: v["cookie"]}).status_code == 404
        assert client.get(url, follow_redirects=False).status_code == 303
        # another person cannot upload into this folder or change its marks
        r = _upload(client, v, u["folder"])
        assert r.status_code == 404
        csrf_u = _csrf(client, u)
        # Public needs the confirm page; without confirm nothing changes
        r = client.post(f"/space/{u['folder']}/visibility", data={"csrf": csrf_u, "file_id": f["id"], "visibility": "public"},
                        cookies={accounts.COOKIE: u["cookie"]})
        assert r.status_code == 200 and "anyone with the link" in r.text
        with db.conn() as conn:
            assert conn.execute("SELECT visibility, public_token FROM space_files WHERE id = %s", (f["id"],)).fetchone() == {"visibility": "furp", "public_token": None}
        r = client.post(f"/space/{u['folder']}/visibility", data={"csrf": csrf_u, "file_id": f["id"], "visibility": "public", "confirm": "1"},
                        cookies={accounts.COOKIE: u["cookie"]}, follow_redirects=False)
        assert r.status_code == 303
        with db.conn() as conn:
            f2 = conn.execute("SELECT * FROM space_files WHERE id = %s", (f["id"],)).fetchone()
        assert f2["visibility"] == "public" and f2["public_token"] and f2["public_at"]
        pub = f"/p/{f2['public_token']}/hello.txt"
        r = client.get(pub)                                                       # no login at all
        assert r.status_code == 200 and r.content == b"hello space"
        # back to private: the URL dies and the token is gone
        r = client.post(f"/space/{u['folder']}/visibility", data={"csrf": csrf_u, "file_id": f["id"], "visibility": "private"},
                        cookies={accounts.COOKIE: u["cookie"]}, follow_redirects=False)
        assert r.status_code == 303
        assert client.get(pub).status_code == 404
        with db.conn() as conn:
            f3 = conn.execute("SELECT visibility, public_token, public_at FROM space_files WHERE id = %s", (f["id"],)).fetchone()
            assert f3 == {"visibility": "private", "public_token": None, "public_at": None}
            assert f["id"] not in {x["id"] for x in space.furp_readable(conn)}      # private: FURP's analysis does not read it
        # remove hides the row, deletes nothing
        r = client.post(f"/space/{u['folder']}/remove", data={"csrf": csrf_u, "file_id": f["id"]},
                        cookies={accounts.COOKIE: u["cookie"]}, follow_redirects=False)
        assert r.status_code == 303
        with db.conn() as conn:
            assert conn.execute("SELECT removed_at FROM space_files WHERE id = %s", (f["id"],)).fetchone()["removed_at"]
        assert os.path.isfile(os.path.join(os.environ["SPACE_BLOB_DIR"], f["blob_path"]))
        assert client.get(url, cookies={accounts.COOKIE: u["cookie"]}).status_code == 404


def test_public_folder_lists_only_public_files(client):
    with person("w-" + MARK + "@example.test", f"{MARK}-W") as w:
        _upload(client, w, w["folder"], b"open.txt", b"open")
        _upload(client, w, w["folder"], b"closed.txt", b"closed", vis="private")
        csrf = _csrf(client, w)
        with db.conn() as conn:
            fid = conn.execute("SELECT id FROM space_files WHERE uploader = %s AND filename = 'open.txt'", (w["email"],)).fetchone()["id"]
        client.post(f"/space/{w['folder']}/visibility", data={"csrf": csrf, "file_id": fid, "visibility": "public", "confirm": "1"},
                    cookies={accounts.COOKIE: w["cookie"]}, follow_redirects=False)
        r = client.post(f"/space/{w['folder']}/visibility", data={"csrf": csrf, "visibility": "public", "confirm": "1"},
                        cookies={accounts.COOKIE: w["cookie"]}, follow_redirects=False)
        assert r.status_code == 303
        with db.conn() as conn:
            d = conn.execute("SELECT * FROM space_folders WHERE name = %s", (w["folder"],)).fetchone()
        r = client.get(f"/p/f/{d['public_token']}")
        assert r.status_code == 200 and "open.txt" in r.text and "closed.txt" not in r.text


def test_admin_adds_sets_email_and_removes(client):
    with person("adm-" + MARK + "@example.test", f"{MARK}-ADM", super_=True) as s:
        csrf = _csrf(client, s)
        new_email = "new-" + MARK + "@example.test"
        folder = f"{MARK}-New"
        try:
            r = client.post("/admin/people", data={"csrf": csrf, "action": "add", "name": f"{MARK} New Person", "email": "", "folder": folder},
                            cookies={accounts.COOKIE: s["cookie"]}, follow_redirects=False)
            assert r.headers["location"] == "/admin?msg=added"
            with db.conn() as conn:
                p = conn.execute("SELECT * FROM space_people WHERE name = %s", (f"{MARK} New Person",)).fetchone()
                assert p["email"] is None and conn.execute("SELECT person_id FROM space_folders WHERE name = %s", (folder,)).fetchone()["person_id"] == p["id"]
            assert not space.login_allowed(new_email)
            r = client.post("/admin/people", data={"csrf": csrf, "action": "email", "person_id": p["id"], "email": new_email},
                            cookies={accounts.COOKIE: s["cookie"]}, follow_redirects=False)
            assert r.headers["location"] == "/admin?msg=emailset" and space.login_allowed(new_email)
            r = client.post("/admin/people", data={"csrf": csrf, "action": "remove", "person_id": p["id"]},
                            cookies={accounts.COOKIE: s["cookie"]}, follow_redirects=False)
            assert r.headers["location"] == "/admin?msg=removed" and not space.login_allowed(new_email)
            with db.conn() as conn:          # the folder is kept
                assert conn.execute("SELECT 1 FROM space_folders WHERE name = %s", (folder,)).fetchone()
        finally:
            with db.conn() as conn:
                conn.execute("DELETE FROM space_log WHERE folder = %s OR detail LIKE %s", (folder, f"%{MARK} New Person%"))
                conn.execute("DELETE FROM space_folders WHERE name = %s", (folder,))
                conn.execute("DELETE FROM space_people WHERE name = %s", (f"{MARK} New Person",))


def test_seeded_people_and_folders_exist():
    with db.conn() as conn:
        rows = {r["name"]: r for r in conn.execute("SELECT d.name, p.email, p.is_super FROM space_folders d JOIN space_people p ON p.id = d.person_id WHERE d.name IN ('Olenick', 'Leidig')").fetchall()}
    assert rows["Olenick"]["email"] == "mfolenick@gmail.com" and rows["Olenick"]["is_super"]
    assert "Leidig" in rows


def test_filenames_and_dispositions():
    assert space.clean_filename("../../etc/passwd") == "passwd"
    assert space.clean_filename('C:\\Users\\x\\report "final".pdf') == "report final.pdf"
    assert space.clean_filename("") == "file"
    assert space._disposition("résumé.pdf", "application/pdf").startswith("inline;")
    assert space._disposition("x.exe", "application/x-msdownload").startswith("attachment;")
