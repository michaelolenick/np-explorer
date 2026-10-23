"""The day's finds (app/ideas.py): themes, ten on the front page spread over them, /today and its archive, and the
About index of the archive pages."""

from starlette.testclient import TestClient

from app import ideas, main

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def test_themes():
    assert ideas.theme({"intent": "top_paid"}) == "Pay"
    assert ideas.theme({"intent": "coaches"}) == "Schools and loans"
    assert ideas.theme({"intent": "food_recalls"}) == "Companies and recalls"
    assert ideas.theme({"intent": "funders_of"}) == "Money and grants"
    assert ideas.theme({"intent": "leaderboard", "board": "top-paid"}) == "Pay"
    groups = ideas.group([{"theme": "Schools and loans"}, {"theme": "Pay"}, {"theme": "Pay"}])
    assert [t for t, _ in groups] == ["Pay", "Schools and loans"] and len(groups[0][1]) == 2


def test_front_page_five_one_per_theme(monkeypatch):
    rows = [{"id": i, "intent": {"intent": it}} for i, it in enumerate(
        ["top_paid"] * 6 + ["funders_of"] * 6 + ["coaches"] * 6 + ["food_recalls"] * 1)]

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): return type("R", (), {"fetchall": lambda s: rows})()
    monkeypatch.setattr(ideas.db, "conn", lambda: Conn())
    ids = ideas.first_ids()
    themes = [ideas.theme(rows[i]["intent"]) for i in ids]
    assert len(ids) == ideas.FIRST == 5 and len(set(ids)) == 5
    assert themes.count("Companies and recalls") == 1 and all(themes.count(t) <= 2 for t in set(themes))


def test_today_pages_and_index():
    pools = ideas.pools()
    if not pools:
        return
    r = client.get("/today")
    assert r.status_code == 200 and "finds from public records" in r.text and 'class="ideas-signup"' in r.text
    day = pools[-1]["day"].isoformat()
    assert client.get(f"/today/{day}").status_code == 200
    assert client.get("/today/1999-01-01").status_code == 404 and client.get("/today/notadate").status_code == 404
    idx = client.get("/about/daily").text
    assert idx.index(pools[0]["day"].isoformat()) < idx.index(day) or len(pools) == 1
