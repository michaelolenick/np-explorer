"""Explain what I'm seeing: 3 a day per visitor (cookie), then a pointer to Support FURP (owner, 2026-10-21)."""

from starlette.testclient import TestClient

from app import explain, main


def test_three_explanations_a_day_then_support(monkeypatch):
    monkeypatch.setattr(explain, "explain", lambda u: "<p>Explained.</p>")
    monkeypatch.setattr(explain, "cached_only", lambda u: True)
    client = TestClient(main.app, base_url="https://testserver")
    u = next(p for p in explain.PREFIXES if p.startswith("/org/")) + "530159845"
    for _ in range(3):
        r = client.get("/explain", params={"u": u})
        assert r.status_code == 200 and "Explained." in r.text
    r = client.get("/explain", params={"u": u})
    assert "3 free explanations" in r.text and 'href="/support"' in r.text
    assert "Explained." not in r.text
