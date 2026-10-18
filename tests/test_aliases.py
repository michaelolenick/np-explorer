"""Common-name aliases (org_aliases): "INSEAD" means INSEAD's own filer, not its smaller US affiliate."""

import contextlib
import os
import uuid

import pytest

from app import aliases, ask, timeseries

INSEAD_PRIMARY, INSEAD_NA = "311551644", "311734079"


def _db_or_skip():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        psycopg.connect(DATABASE_URL, connect_timeout=5).close()
    except Exception:  # noqa: BLE001
        pytest.skip("no database")


@pytest.fixture(scope="module")
def pool():
    _db_or_skip()
    from app import db
    try:
        db.pool.open()
    except Exception:  # noqa: BLE001 - already open
        pass
    return db


def test_insead_alias_names_the_primary(pool):
    al = aliases.lookup("INSEAD")
    assert al and al["primary"]["ein"] == INSEAD_PRIMARY
    assert [a["ein"] for a in al["affiliates"]] == [INSEAD_NA]
    assert al["primary"]["latest_total_revenue"] > 10 * (al["affiliates"][0]["latest_total_revenue"] or 1)
    org, choices = timeseries.resolve("INSEAD")
    assert choices == [] and org["ein"] == INSEAD_PRIMARY and org["match"] == "EXACT"
    assert org["evidence"] == "Common name for INSTITUT EUPROPEEN D ADMINISTRATION DES AFFAIRES INSEAD."
    assert [a["ein"] for a in org["affiliates"]] == [INSEAD_NA]


def test_nl_question_uses_the_primary(pool, monkeypatch):
    """The model's reply is stubbed: it only names "INSEAD" and the condition; the site picks the organization."""
    import httpx

    class Reply:
        status_code = 200

        def json(self):
            return {"usage": {}, "content": [{"type": "tool_use", "name": "org_timeseries", "input": {
                "org": "INSEAD", "metrics": ["revenue", "assets"], "condition": "a_up_b_down",
                "metric_a": "assets", "metric_b": "revenue"}}]}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Reply())
    monkeypatch.setattr(ask, "_shared_get", lambda key: None)
    monkeypatch.setattr(ask, "_shared_put", lambda key, intent: None)
    monkeypatch.setattr(ask, "_usage", lambda **k: None)
    monkeypatch.setattr(ask, "_calls_today", lambda: 0)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    ask._cache.clear()
    p = ask.parse("give years INSEAD revenue fell but assets rose", "10.0.0.1")
    assert p["intent"] == "org_timeseries" and p["condition"] == "a_up_b_down"
    r = ask.run({k: v for k, v in p.items() if k not in ("how", "parse_ms")})
    assert r["kind"] == "timeseries" and r["org"]["ein"] == INSEAD_PRIMARY
    assert r["org"]["evidence"].startswith("Common name for ")
    assert all(row["assets_yoy"] > 0 and row["revenue_yoy"] < 0 for row in r["data"]["rows"])


def test_proposed_aliases_are_not_used(pool, monkeypatch):
    import psycopg
    from psycopg.rows import dict_row

    from app.config import DATABASE_URL
    schema = f"alias_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"CREATE TABLE {schema}.org_aliases (LIKE public.org_aliases INCLUDING ALL)")
        c.execute(f"""INSERT INTO {schema}.org_aliases (alias_norm, alias, ein, role, status, note)
                      VALUES ('zzqx', 'ZZQX', %s, 'primary', 'proposed', 'test')""", (INSEAD_NA,))

    @contextlib.contextmanager
    def fake():
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        conn.execute(f"SET search_path = {schema}, public")
        try:
            yield conn
        finally:
            conn.close()
    try:
        monkeypatch.setattr("app.db.conn", fake)
        assert aliases.lookup("ZZQX") is None                     # proposed: waits for review
        with psycopg.connect(DATABASE_URL, autocommit=True) as c:
            c.execute(f"UPDATE {schema}.org_aliases SET status = 'live'")
        assert aliases.lookup("zzqx")["primary"]["ein"] == INSEAD_NA
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as c:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


def test_custom_search_skips_aliases():
    from app import funders
    one = [{"ein": "1", "name_norm": "insead"}]
    assert funders.resolve_org("INSEAD", search=lambda q, limit, state: one)[0]["ein"] == "1"
