"""Columns ordered by the question (owner, 2026-11-06): app/colorder.py."""

from app import ask, boards, colorder

DAF = boards.BY_SLUG["daf-sponsors"]


def test_default_orders_follow_the_site_rule():
    assert [c["key"] for c in colorder.columns({"kind": "daf_orgs"})] == \
        ["value", "contributions", "grants", "count", "ein", "location", "year", "filing"]
    assert [c["key"] for c in colorder.columns({"kind": "board", "board": DAF})][:2] == ["value", "daf_contributions"]
    assert colorder.columns({"kind": "board", "board": DAF})[0]["fmt"] == DAF.value.fmt
    assert [c["key"] for c in colorder.columns({"kind": "top_paid", "board": boards.BY_SLUG["top-paid"], "per_person": True})][:2] == ["value", "n_years"]
    assert colorder.columns({"kind": "timeseries"}) == []


def test_parse_accepts_only_a_permutation():
    cols = colorder.columns({"kind": "vendors"})
    assert colorder.parse("service, paid, year", cols) == ["service", "paid", "year"]
    assert colorder.parse("Paid,\nService,\nYear", cols) == ["paid", "service", "year"]
    assert colorder.parse("paid, service", cols) is None                 # one missing
    assert colorder.parse("paid, service, year, paid", cols) is None     # a duplicate
    assert colorder.parse("paid, service, total", cols) is None          # an invented key
    assert colorder.apply(cols, ["year", "paid"])[0]["key"] == "year" and len(colorder.apply(cols, ["year"])) == 3


def test_order_asks_the_model_once_per_question_and_falls_back(monkeypatch):
    store: dict = {}
    calls = []
    monkeypatch.setattr(ask, "enabled", lambda: True)
    monkeypatch.setattr(ask, "_shared_get", lambda k: store.get(k))
    monkeypatch.setattr(ask, "_shared_put", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(colorder, "_ask_model", lambda q, cols: calls.append(q) or ["contributions", "value", "grants", "count", "year", "ein", "location", "filing"])
    res = {"kind": "daf_orgs"}
    keys = [c["key"] for c in colorder.order("Which DAF sponsors took in the most contributions last year?", res)]
    assert keys[:3] == ["contributions", "value", "grants"] and len(calls) == 1
    colorder.order("Which DAF sponsors took in the most contributions last year?", res)
    assert len(calls) == 1                                               # cached per question
    assert [c["key"] for c in colorder.order("Fidelity Charitable", res)][0] == "value" and len(calls) == 1   # a bare name: no call
    assert colorder.order("", res)[0]["key"] == "value"
    monkeypatch.setattr(colorder, "_ask_model", lambda q, cols: None)   # the model is slow or answers badly
    assert [c["key"] for c in colorder.order("Who holds the most money in donor-advised funds?", res)][0] == "value"
    assert colorder.order("Who pays its vendors the most?", {"kind": "vendors"})[0]["key"] == "paid"   # only three columns: no call


def test_rows_follow_the_first_column(monkeypatch):
    rows = [{"name": "A", "daf_value_eoy": 9, "daf_contributions": 1}, {"name": "B", "daf_value_eoy": 5, "daf_contributions": 7},
            {"name": "C", "daf_value_eoy": 4, "daf_contributions": None}]
    res = {"kind": "daf_orgs", "rows": rows}
    cols = colorder.columns(res)
    assert colorder.resort(res, cols)[0] is res                                   # ranked by the first column already
    by_contrib = colorder.apply(cols, ["contributions"])
    out, note = colorder.resort(res, by_contrib)
    assert [r["name"] for r in out["rows"]] == ["B", "A", "C"] and note.startswith("Sorted by contributions in, highest first")
    assert [r["name"] for r in res["rows"]] == ["A", "B", "C"]                    # the cached result is untouched
    tp = {"kind": "top_paid", "board": boards.BY_SLUG["top-paid"], "per_person": True,
          "rows": [{"list_rank": 1, "value": 9, "n_years": 2}, {"list_rank": 2, "value": 8, "n_years": 5}]}
    out, _ = colorder.resort(tp, colorder.apply(colorder.columns(tp), ["n_years"]))
    assert [(r["list_rank"], r["n_years"]) for r in out["rows"]] == [(1, 5), (2, 2)]
    # A leaderboard result re-reads the board sorted by the column, with the board's own ranks.
    seen = {}
    monkeypatch.setattr(boards, "meta", lambda: {"daf-sponsors": {"n_rows": 1}})
    monkeypatch.setattr(boards, "page", lambda b, f, p, per_page=None: seen.update(f, per_page=per_page) or {"rows": [{"rank": 7}], "total": 1})
    bres = {"kind": "board", "board": DAF, "rows": [{"rank": 1}]}
    out, note = colorder.resort(bres, colorder.apply(colorder.columns(bres), ["daf_grants"]), {"state": "NY", "limit": 10})
    assert out["rows"] == [{"rank": 7}] and seen["sort"] == "daf_grants" and seen["state"] == "NY" and seen["per_page"] == 10
    assert note == "Sorted by grants paid, highest first; the rank is the board's own, by value at year end."
    assert colorder.resort(bres, colorder.apply(colorder.columns(bres), ["tax_year"]))[0] is bres   # not a figure


def test_the_answer_cache_key_carries_the_first_column():
    from app import answer
    cols = colorder.columns({"kind": "daf_orgs"})
    assert answer.key_for("/ask?intent=x", cols) == "/ask?intent=x#first=Value at year end"
    assert answer.key_for("/ask?intent=x", []) == "/ask?intent=x"
    assert "first_column" in answer.SYSTEM
