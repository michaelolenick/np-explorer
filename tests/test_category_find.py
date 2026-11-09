"""Find a category, Describe what it does (owner, 2026-11-08): Claude Sonnet with the cached code list, ranked codes
with reasons, typo-tolerant fallbacks (never empty), the lookup log."""
import json
import time

import pytest

from app import categories


@pytest.fixture(scope="module")
def db():
    from app import db as adb
    try:
        adb.pool.open(wait=True)        # no close: the shared pool (as tests/test_alt_names.py)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    if not categories.code_list():
        pytest.skip("no taxonomy")
    return adb


def test_code_list_and_cached_prompt(db):
    by = {c["code"]: c for c in categories.code_list()}
    assert by["X30"]["name"] == "Judaism" and "Jewish" in by["X30"]["description"]
    block = categories.find_system()
    assert block[0]["cache_control"] == {"type": "ephemeral"} and "K31 Food Banks, Pantries:" in block[0]["text"]
    assert all(len(c["description"]) <= categories.DESC_CHARS + 3 for c in by.values())


@pytest.mark.parametrize("q, code", [("jewish organizatinos", "X30"), ("food banks", "K31"), ("Food Bank", "K31"),
                                     ("synagogues", None), ("zzqx", None)])
def test_fallback_reads_typos_and_plurals_and_is_never_empty(db, q, code):
    codes, how = categories.fallback(q)
    assert codes, "never empty"
    if code:
        assert codes[0]["code"] == code and how in ("keywords", "fuzzy") and codes[0]["why"].startswith("Matched ")
    else:
        assert how in ("keywords", "fuzzy", "majors")


def test_parse_keeps_valid_codes_with_reasons(db):
    raw = json.dumps({"r": [{"c": "x30", "why": "Jewish"}, {"c": "ZZZ", "why": "bad"}, {"c": "X30", "why": "dup"},
                            {"c": "K31", "why": "food"}]})
    out = categories._parse(raw)
    assert [c["code"] for c in out] == ["X30", "K31"] and out[0]["why"] == "Jewish" and out[0]["name"] == "Judaism"
    assert categories._parse("not json") == [] and categories._parse(json.dumps({"r": []})) == []
    padded = json.dumps({"r": [{"c": "X30", "why": "Jewish organizations"}, {"c": "X20", "why": "Not a fit; skip"},
                               {"c": "X99", "why": "Weaker fit than X30"}]})
    assert [c["code"] for c in categories._parse(padded)] == ["X30"]


def test_cost_prices_cached_prompt_tokens_at_a_tenth():
    from app import autoexplain
    full = autoexplain.cost_of("claude-sonnet-5-5", {"input_tokens": 41521, "output_tokens": 100})
    cached = autoexplain.cost_of("claude-sonnet-5-5", {"input_tokens": 12, "cache_read_input_tokens": 41509, "output_tokens": 100})
    assert 0.083 < full < 0.085 and 0.009 < cached < 0.0095


def _clean(db, q):
    with db.conn() as conn:
        conn.execute("DELETE FROM ntee_infer_cache WHERE q = %s", (categories._norm_q(q),))
        conn.execute("DELETE FROM category_find_log WHERE q = %s", (categories._norm_q(q),))


def test_infer_uses_the_model_then_the_cache_and_logs_both(db, monkeypatch):
    q = f"test synagogue lookup {time.time()}"
    monkeypatch.setattr(categories, "_resting", lambda: None)
    monkeypatch.setattr(categories, "_call_model", lambda q: (json.dumps({"r": [{"c": "X30", "why": "synagogue"}]}),
                                                               {"input_tokens": 10, "output_tokens": 5}, None))
    try:
        out = categories.infer(q)
        assert out["how"] == "model" and out["codes"][0]["code"] == "X30" and out["codes"][0]["why"] == "synagogue"
        again = categories.infer(q)
        assert again["how"] == "cache" and again["codes"][0]["code"] == "X30"
        with db.conn() as conn:
            rows = conn.execute("SELECT method, model, raw, codes FROM category_find_log WHERE q = %s ORDER BY id",
                                (categories._norm_q(q),)).fetchall()
        assert [r["method"] for r in rows] == ["model", "cache"] and "X30" in rows[0]["raw"] and rows[0]["codes"] == ["X30"]
        assert rows[0]["model"] == categories.FIND_MODEL
    finally:
        _clean(db, q)


def test_infer_falls_back_when_the_model_fails_and_says_why(db, monkeypatch):
    q = f"food banks {int(time.time())}"
    monkeypatch.setattr(categories, "_resting", lambda: None)
    monkeypatch.setattr(categories, "_call_model", lambda q: (None, {}, "call failed (ConnectError)"))
    try:
        out = categories.infer(q)
        assert out["how"] == "keywords" and out["codes"][0]["code"] == "K31" and "call failed" in out["note"]
        with db.conn() as conn:
            row = conn.execute("SELECT method, error, raw FROM category_find_log WHERE q = %s", (categories._norm_q(q),)).fetchone()
        assert row["method"] == "keywords" and "call failed" in row["error"] and row["raw"] is None
    finally:
        _clean(db, q)


def test_page_shows_ranked_codes_with_reasons_and_the_method(db, monkeypatch):
    from starlette.testclient import TestClient
    from app import main
    q = f"jewish organizatinos {int(time.time())}"
    monkeypatch.setattr(categories, "_resting", lambda: None)
    monkeypatch.setattr(categories, "_call_model", lambda q: (json.dumps({"r": [{"c": "X30", "why": "Jewish organizations"}]}),
                                                               {"input_tokens": 10, "output_tokens": 5}, None))
    client = TestClient(main.app)         # no `with`: keeps the shared pool open
    try:
        html = client.get("/categories", params={"q": q, "mode": "infer"}).text
        assert "<th>Why</th>" in html and "X30" in html and "Jewish organizations" in html
        assert "Ranked by Claude (" in html and "Code, name, what it does, or who funds whom" in html
        monkeypatch.setattr(categories, "_call_model", lambda q: (None, {}, "model returned HTTP 529"))
        html = client.get("/categories", params={"q": q + " x", "mode": "infer"}).text
        assert "X30" in html and "The model gave no answer (model returned HTTP 529)" in html
    finally:
        _clean(db, q)
        _clean(db, q + " x")
