"""Plain-English search lists page 25 at a time, as far as the results go."""

from starlette.testclient import TestClient

from app import ask, boards, main


def _fake_run(n):
    def run(intent):
        lim = intent["limit"]
        rows = [{"list_rank": i, "subject_name": f"P{i}", "subject_url": f"/person/{i}", "value": 1000 - i,
                 "tax_year": 2022, "org_name": "Org", "state": "OH", "n_years": 1, "also": []}
                for i in range(1, min(n, lim) + 1)]
        return {"kind": "top_paid", "board": boards.get("top-paid"), "rows": rows, "total": len(rows), "per_person": True, "notes": [],
                "url": "/boards/top-paid"}
    return run


def test_run_page_slices_and_keeps_ranks(monkeypatch):
    monkeypatch.setattr(ask, "run", _fake_run(60))
    p1 = ask.run_page({"intent": "top_paid", "limit": 25}, 1)
    assert [r["list_rank"] for r in p1["rows"]] == list(range(1, 26)) and p1["has_next"]
    p2 = ask.run_page({"intent": "top_paid", "limit": 25}, 2)
    assert [r["list_rank"] for r in p2["rows"]] == list(range(26, 51)) and p2["has_next"]   # no stop at 50
    p3 = ask.run_page({"intent": "top_paid", "limit": 25}, 3)
    assert [r["list_rank"] for r in p3["rows"]] == list(range(51, 61)) and not p3["has_next"]


def test_non_lists_are_not_paged(monkeypatch):
    monkeypatch.setattr(ask, "run", lambda intent: {"kind": "school", "inst": {}, "total": 1})
    assert "page" not in ask.run_page({"intent": "school_lookup"}, 3)


def test_page_links_on_the_results_page(monkeypatch):
    monkeypatch.setattr(ask, "run", _fake_run(80))
    main._cached_nl_run.cache_clear() if hasattr(main._cached_nl_run, "cache_clear") else None
    client = TestClient(main.app)          # no `with`: keeps the shared pool open
    url = "/ask?intent=top_paid&scope=state&state=OH&year=2022&ntee=E&q=Highest-paid+hospital+executives+in+Ohio+in+2022"
    html = client.get(url + "&page=2").text
    assert "Page 2: results 26 to 50" in html
    assert "&amp;page=1" in html and "&amp;page=3" in html and "q=Highest-paid+hospital" in html
    assert ">P26<" in html and ">P50<" in html and ">P51<" not in html
