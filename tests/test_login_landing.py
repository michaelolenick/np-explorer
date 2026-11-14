"""A login with no destination lands a named person or super admin on /space, others on /deep (owner, 2026-11-14)."""
from app import accounts


def test_safe_next_keeps_empty_and_rejects_offsite():
    assert accounts._safe_next("") == "" and accounts._safe_next(None) == ""
    assert accounts._safe_next("//evil.example") == "" and accounts._safe_next("/deep") == "/deep"


def test_landing_by_role(monkeypatch):
    from app import db
    db.pool.open(wait=False)
    assert accounts.landing("mfolenick@gmail.com") == "/space"
    assert accounts.landing("nobody-listed@example.com") == "/deep"
    assert accounts.landing(None) == "/deep"
