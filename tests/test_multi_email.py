"""One person, several emails, one folder (owner, 2026-11-14): any address logs in to the same person, folder and history."""
import secrets

import pytest
from starlette.testclient import TestClient

from app import accounts, db, space


@pytest.fixture
def client():
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def test_extra_addresses_reach_the_same_person_and_folder(client, monkeypatch):
    tag = secrets.token_hex(3)
    main, extra = f"multi-a-{tag}@example.com", f"multi-b-{tag}@example.org"
    admin = {"id": 0, "email": "mfolenick@gmail.com", "name": "O", "session_hash": "x"}
    monkeypatch.setattr(accounts, "csrf_ok", lambda u, f: True)
    monkeypatch.setattr(accounts, "csrf", lambda u: "t")
    monkeypatch.setattr(accounts, "current_user", lambda request: admin)
    try:
        r = client.post("/admin/people", data={"csrf": "t", "action": "add", "name": f"Multi {tag}", "email": main, "folder": f"Multi{tag}"}, follow_redirects=False)
        assert r.status_code == 303
        with db.conn() as conn:
            pid = conn.execute("SELECT id FROM space_people WHERE lower(email) = %s", (main,)).fetchone()["id"]
        assert not space.login_allowed(extra)
        client.post("/admin/people", data={"csrf": "t", "action": "email", "person_id": str(pid), "email": extra})
        with db.conn() as conn:
            assert space.login_allowed(extra) and space.login_allowed(main)
            a, b = space.person_for(conn, {"email": main}), space.person_for(conn, {"email": extra.upper()})
            assert a["id"] == b["id"] == pid
            assert [d["name"] for d in space._folders_for(conn, b, False)] == [f"Multi{tag}"]
            assert space.emails_of(conn, a) == [main, extra]
        # an address belongs to one person only
        r = client.post("/admin/people", data={"csrf": "t", "action": "email", "person_id": "1", "email": extra}, follow_redirects=False)
        assert r.headers["location"] == "/admin?msg=emailtaken"
        # remove the main one: the extra becomes the main address; the last one cannot be removed
        client.post("/admin/people", data={"csrf": "t", "action": "dropemail", "person_id": str(pid), "email": main})
        with db.conn() as conn:
            assert not space.login_allowed(main) and space.login_allowed(extra)
            assert space.person_for(conn, {"email": extra})["email"] == extra
        r = client.post("/admin/people", data={"csrf": "t", "action": "dropemail", "person_id": str(pid), "email": extra}, follow_redirects=False)
        assert r.headers["location"] == "/admin?msg=lastemail"
        assert "add an email" in client.get("/admin").text
    finally:
        with db.conn() as conn:
            conn.execute("DELETE FROM space_folders WHERE name = %s", (f"Multi{tag}",))
            conn.execute("DELETE FROM space_people WHERE name = %s", (f"Multi {tag}",))
            conn.execute("DELETE FROM space_log WHERE detail LIKE %s", (f"%Multi {tag}%",))
