"""The single Find a category box (owner, 2026-11-09): app/catbox reads what was typed (a code or name, a
description, or a who-funds-whom question) and the page answers with the right table, never nothing; every query
is logged with its reading, confidence and result count."""
import json
import time

import pytest

from app import catbox, categories, db


@pytest.fixture(scope="module")
def pool():
    try:
        db.pool.open(wait=True)
    except Exception:  # noqa: BLE001 - already open
        pass
    yield db


def _clean(q: str) -> None:
    with db.conn() as conn:
        conn.execute("DELETE FROM category_query_log WHERE q = %s", (q,))
        conn.execute("DELETE FROM category_find_log WHERE q = %s", (q.lower(),))
        conn.execute("DELETE FROM ntee_infer_cache WHERE q = %s", (q.lower(),))


def test_a_bare_code_is_a_lookup_without_asking_the_model(monkeypatch):
    monkeypatch.setattr(catbox, "_ask_model", lambda key: (_ for _ in ()).throw(AssertionError("asked")))
    for q in ("X30", "b82", "K"):
        c = catbox.classify(q)
        assert c["intent"] == "lookup" and c["confidence"] == 1.0 and c["by"] == "rule"


@pytest.mark.parametrize("q, intent, recipient, direction", [
    ("who gives to the Girl Scouts", "grants", "girl scouts", "funders"),
    ("show charities likely to donate to hillel", "grants", "hillel", "funders"),
    ("funders of women in science", "grants", "women in science", "funders"),
    ("who does the Ford Foundation give to", "grants", "ford foundation", "recipients"),
    ("space: for women", "lookup", "", "none"),
    ("jewish organizatinos", "lookup", "", "none"),
    ("campus ministry for college students at universities", "describe", "", "none"),
])
def test_the_guess_from_words_alone_is_uncertain_so_both_readings_run(q, intent, recipient, direction):
    g = catbox.guess(q, "the model is off")
    assert g["intent"] == intent and g["by"] == "guess" and g["confidence"] < catbox.SURE and g["note"] == "the model is off"
    assert g["recipient"].lower() == recipient and g["direction"] == direction


def test_the_model_reading_is_parsed_and_clamped(monkeypatch):
    from app import ask

    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"usage": {"input_tokens": 10, "output_tokens": 5}, "content": [{"type": "text", "text": json.dumps(
                {"intent": "grants", "confidence": 1.7, "recipient": "the Girl Scouts", "topic": "", "place": "", "direction": "none"})}]}
    monkeypatch.setattr(ask, "enabled", lambda: True)
    monkeypatch.setattr(ask, "post", lambda body, timeout: R())
    monkeypatch.setattr(ask, "_usage", lambda **kw: None)
    c = catbox.classify(f"who gives to the Girl Scouts {time.time()}")
    assert c == {"intent": "grants", "confidence": 1.0, "by": "model", "recipient": "the Girl Scouts", "topic": "",
                 "place": "", "direction": "funders", "note": None}


def test_a_failing_model_falls_back_to_the_guess(monkeypatch):
    from app import ask

    class R:
        status_code = 529
        text = "overloaded"
    monkeypatch.setattr(ask, "enabled", lambda: True)
    monkeypatch.setattr(ask, "post", lambda body, timeout: R())
    c = catbox.classify(f"who gives to the Girl Scouts {time.time()}")
    assert c["intent"] == "grants" and c["by"] == "guess" and "HTTP 529" in c["note"]


def test_named_recipients_gather_the_family_and_their_funders(pool):
    cls = catbox._reading("grants", 0.95, "model", recipient="hillel", direction="funders")
    g = catbox.grants_for("show charities likely to donate to hillel", cls, None)
    assert g["kind"] == "named" and g["matched"] > 50 and g["rows"], g
    assert any("hillel" in (e or "").lower() for e in g["examples"])
    top = g["rows"][0]
    assert top["total"] and top["grantor_name"] and top["first_year"] <= top["last_year"]
    assert g["unlinked"]["n"] > 0           # grants naming Hillel whose EIN was not matched are counted, not hidden


def test_recipients_direction_lists_who_a_named_grantor_gave_to(pool):
    cls = catbox._reading("grants", 0.9, "model", recipient="Ford Foundation", direction="recipients")
    g = catbox.grants_for("who does the Ford Foundation give to", cls, None)
    assert g["direction"] == "recipients" and g["rows"] and g["rows"][0]["grantors"] >= 1


def test_described_recipients_use_the_suggested_codes(pool):
    cls = catbox._reading("grants", 0.9, "model", topic="women in science", direction="funders")
    inferred = {"codes": [{"code": "V32", "name": "Women's Studies", "major": "V"}, {"code": "R24", "name": "Women's Rights", "major": "R"}]}
    g = catbox.grants_for("funders of women in science", cls, inferred)
    assert g["kind"] == "topic" and g["codes"] == ["V32", "R24"] and g["rows"] and g["matched"] > 0


def test_run_routes_grants_logs_and_adds_category_suggestions(pool, monkeypatch):
    q = f"who gives to the Girl Scouts {int(time.time())}"
    monkeypatch.setattr(catbox, "classify", lambda s: catbox._reading("grants", 0.92, "model", recipient="Girl Scouts", direction="funders"))
    monkeypatch.setattr(categories, "infer", lambda words: {"codes": [{"code": "O40", "name": "Scouting", "major": "O", "why": "Girl Scouts"}],
                                                            "how": "model", "model": "test", "note": None, "q": words})
    try:
        box = catbox.run(q, "ntee")
        assert box["grants"]["rows"] and box["inferred"]["codes"][0]["code"] == "O40" and box["inferred"]["q"] == "Girl Scouts"
        assert box["results"] == len(box["grants"]["rows"]) + 1 and box["redirect"] is None
        with db.conn() as conn:
            row = conn.execute("SELECT * FROM category_query_log WHERE q = %s", (q,)).fetchone()
        assert row["intent"] == "grants" and float(row["confidence"]) == 0.92 and row["results"] == box["results"] and row["source"] == "model"
        assert set(row) == {"id", "ts", "q", "intent", "confidence", "results", "source"}      # nothing about the visitor
    finally:
        _clean(q)


def test_an_uncertain_reading_runs_both_and_shows_what_came_back(pool, monkeypatch):
    q = f"space exploration {int(time.time())}"
    monkeypatch.setattr(catbox, "classify", lambda s: catbox._reading("describe", 0.4, "guess", topic=s))
    monkeypatch.setattr(categories, "infer", lambda words: {"codes": [{"code": "U31", "name": "Astronomy", "major": "U", "why": "space"}],
                                                            "how": "model", "model": "test", "note": None, "q": words})
    try:
        box = catbox.run(q, "ntee")
        assert not box["sure"] and box["inferred"]["codes"] and box["grants"]["kind"] == "topic" and box["grants"]["rows"]
    finally:
        _clean(q)


def test_a_lookup_that_finds_nothing_falls_through_to_claude(pool, monkeypatch):
    q = f"jewish organizatinos {int(time.time())}"
    monkeypatch.setattr(catbox, "classify", lambda s: catbox._reading("lookup", 0.9, "model"))
    monkeypatch.setattr(categories, "infer", lambda words: {"codes": [{"code": "X30", "name": "Judaism", "major": "X", "why": "Jewish"}],
                                                            "how": "model", "model": "test", "note": None, "q": words})
    try:
        box = catbox.run(q, "ntee")
        assert box["found"] is None and box["inferred"]["codes"][0]["code"] == "X30" and box["grants"] is None
    finally:
        _clean(q)


def test_page_one_box_redirects_a_code_and_shows_the_reading(pool, monkeypatch):
    from starlette.testclient import TestClient
    from app import main
    client = TestClient(main.app)             # no `with`: keeps the shared pool open
    try:
        r = client.get("/categories", params={"q": "X30"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/categories/ntee/X30"
        monkeypatch.setattr(catbox, "classify", lambda s: catbox._reading("lookup", 0.88, "model"))
        html = client.get("/categories", params={"q": "space: for women"}).text
        assert 'type="radio"' not in html and "Code, name, what it does, or who funds whom" in html
        assert "Read as a code or category name by Claude Haiku (confidence 88%)" in html and "for women" in html
        monkeypatch.setattr(catbox, "classify", lambda s: catbox._reading("grants", 0.95, "model", recipient="Girl Scouts", direction="funders"))
        monkeypatch.setattr(categories, "infer", lambda words: {"codes": [{"code": "O40", "name": "Scouting", "major": "O", "why": "Girl Scouts"}],
                                                                "how": "model", "model": "test", "note": None, "q": words})
        q = f"who gives to the Girl Scouts {int(time.time())}"
        html = client.get("/categories", params={"q": q}).text
        assert "Funders of &ldquo;Girl Scouts&rdquo;" in html and "<th>Funder</th>" in html and "Category suggestions for" in html
        assert "Read as a question about who funds whom by Claude Haiku (confidence 95%)" in html
        _clean(q)
        # an old link still forces the description reading
        html = client.get("/categories", params={"q": q, "mode": "infer"}).text
        assert "from the link" in html and "O40" in html
    finally:
        _clean("X30")
        _clean("space: for women")
        _clean(q)
