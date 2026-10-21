"""A query that hits the statement timeout shows a "try again" page (503), never a 500."""

import psycopg
from starlette.testclient import TestClient

from app import main

client = TestClient(main.app, raise_server_exceptions=False)


def test_statement_timeout_is_a_503_not_a_500(monkeypatch):
    def slow(*a, **k):
        raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    monkeypatch.setattr(main, "cached_org", slow)
    r = client.get("/org/999999998")
    assert r.status_code == 503 and r.headers["retry-after"] == "10" and "took too long" in r.text
