"""The suppression list (owner, 2026-11-23): 410 for suppressed people, the insert guard, the sweep. Every DB test runs in a
transaction that is rolled back, on a made-up name, so nothing is left in the shared database."""
import pytest

from app import suppress
from loader import suppression
from loader.suppression import add


def test_410_for_suppressed_id_and_slug(monkeypatch):
    monkeypatch.setitem(suppress._list, "at", 10 ** 12)
    monkeypatch.setitem(suppress._list, "ids", {19661518})
    monkeypatch.setitem(suppress._list, "slugs", {"julissa-vogel"})
    assert suppress.is_suppressed_person(19661518)
    assert suppress.is_suppressed_person(5, "julissa-vogel-19661518")
    assert suppress.is_suppressed_person(5, "julissa-vogel-5")           # the name is suppressed, whatever the id
    assert not suppress.is_suppressed_person(5, "alissa-vogel-5")
    r = suppress.gone()
    assert r.status_code == 410 and r.body == b"" and "noindex" in r.headers["x-robots-tag"]


def test_person_page_is_410(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setitem(suppress._list, "at", 10 ** 12)
    monkeypatch.setitem(suppress._list, "ids", {19661518})
    monkeypatch.setitem(suppress._list, "slugs", {"julissa-vogel"})
    c = TestClient(app)
    for u in ("/person/julissa-vogel-19661518", "/person/19661518", "/api/person/19661518"):
        r = c.get(u)
        assert r.status_code == 410 and r.content == b"" and "noindex" in r.headers["x-robots-tag"], u


def test_insert_guard_and_sweep_roll_back():
    from loader import db
    conn = db.connect()
    try:
        suppression.ensure(conn=None)
        conn.execute(suppression.DDL)
        add(conn, "Zzqx Testperson", None, reason="test")
        # new data: the trigger drops the row and logs a hit
        n = conn.execute("""INSERT INTO people (filing_id, ein, name_raw, name_norm)
                            VALUES (-1, '000000000', 'Zzqx Testperson', 'zzqx testperson')""").rowcount
        assert n == 0
        assert conn.execute("SELECT count(*) FROM suppression_hits WHERE name_norm = 'zzqx testperson'").fetchone()[0] == 1
    finally:
        conn.rollback()
        conn.close()


def test_nightly_runs_the_sweep():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "scripts" / "nightly.sh").read_text()
    assert text.count('src "suppression sweep"') >= 3
