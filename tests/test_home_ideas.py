"""Home page "Interesting ideas…": the model call's shape and parsing, the More link, and the fallback."""

import json
import types

from starlette.testclient import TestClient

from app import ideas, main

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def _resp(status, body):
    return types.SimpleNamespace(status_code=status, json=lambda: body)


def _reply(ideas_list, stop="end_turn"):
    return {"stop_reason": stop, "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "text", "text": json.dumps({"ideas": ideas_list})}]}


def test_propose_parses_and_falls_back_between_models(monkeypatch):
    calls = []
    monkeypatch.setattr(ideas, "MODELS", ["first-model", "second-model"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ideas.ask, "_usage", lambda **k: None)

    def post(url, timeout, headers, json):   # noqa: A002
        calls.append(json)
        if json["model"] == ideas.MODELS[0]:
            return _resp(400, {})                 # e.g. a retention setting declines the first model
        return _resp(200, _reply([{"question": "Highest-paid coaches in Texas", "tool": "coaches",
                                   "args_json": "{\"state\": \"TX\"}"},
                                  {"question": "Broken args", "tool": "coaches", "args_json": "{not json"}]))
    monkeypatch.setattr(ideas.httpx, "post", post)
    out = ideas.propose(["An old question"], 10, "medium", 5, overview="- orgs (~1 rows): ein")
    assert [c["model"] for c in calls] == ideas.MODELS[:2]
    assert out == [{"question": "Highest-paid coaches in Texas", "tool": "coaches", "args": {"state": "TX"}}]
    body = calls[-1]
    assert body["output_config"]["format"]["type"] == "json_schema" and body["output_config"]["effort"] == "medium"
    assert "tool_choice" not in body and body["fallbacks"] == "default"
    assert "An old question" in body["system"]                 # what was already shown is sent, so it isn't repeated


def test_refusal_is_not_used(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(ideas.ask, "_usage", lambda **k: None)
    monkeypatch.setattr(ideas, "MODELS", ["m1"])
    monkeypatch.setattr(ideas.httpx, "post", lambda *a, **k: _resp(200, _reply([{"question": "x", "tool": "coaches",
                                                                                "args_json": "{}"}], "refusal")))
    assert ideas.propose([], 5, "medium", 5, overview="") == []


def test_parse_seen():
    assert ideas.parse_seen("3,1,3,x,2") == [3, 1, 2]
    assert len(ideas.parse_seen(",".join(str(i) for i in range(500)))) == ideas.MAX_SEEN


def _fake_pool(monkeypatch):
    pool = {i: f"Idea number {i}" for i in range(1, 121)}
    monkeypatch.setattr(ideas, "first_ids", lambda: [1, 2, 3, 4, 5])
    monkeypatch.setattr(ideas, "_pool_ids", lambda seen, k: [i for i in pool if i not in seen][:k])
    monkeypatch.setattr(ideas, "fetch", lambda ids: [{"id": i, "question": pool[i], "url": f"/ask?intent=x&id={i}"}
                                                     for i in ids if i in pool])


def test_home_shows_five_and_more_adds_five_unseen(monkeypatch):
    _fake_pool(monkeypatch)
    html = client.get("/").text
    assert "Interesting ideas&hellip;" in html and "Or ask:" not in html
    assert html.count('<li><a href="/ask?intent=x&amp;id=') == 5
    assert ('href="/?more=1&amp;seen=1%2C2%2C3%2C4%2C5#ideas" rel="nofollow" '
            'data-busy="Finding more suggested searches&hellip;">Show more suggested searches</a>') in html
    html = client.get("/?more=1&seen=1,2,3,4,5").text
    assert html.count('<li><a href="/ask?intent=x&amp;id=') == 10 and "Idea number 10" in html
    assert 'seen=1%2C2%2C3%2C4%2C5%2C6%2C7%2C8%2C9%2C10#ideas' in html
    assert '<link rel="canonical" href="' in html and '/?more' not in html.split('<link rel="canonical" href="')[1][:60]


def test_home_falls_back_to_fixed_examples(monkeypatch):
    monkeypatch.setattr(ideas, "first_ids", lambda: [])
    monkeypatch.setattr(ideas, "fetch", lambda ids: [])
    html = client.get("/").text
    assert "Interesting ideas&hellip;" in html and "Who runs the Workforce Incubator Foundation?" in html


def test_robots_keeps_crawlers_off_more():
    assert "Disallow: /?more=" in client.get("/robots.txt").text or \
        "Disallow: /?more=" in (main.ROOT / "static" / "robots.txt").read_text()


def test_busy_bar_for_links_that_name_their_wait():
    js = (main.ROOT / "static" / "site.js").read_text()
    assert 'a.hasAttribute("data-busy")' in js and 'showBusy(a.getAttribute("data-busy"))' in js


def test_list_is_remembered_for_the_session(monkeypatch):
    _fake_pool(monkeypatch)
    c = TestClient(main.app, base_url="https://testserver")    # the cookie is Secure on https sites
    r = c.get("/?more=1&seen=1,2,3,4,5")
    cookie = r.cookies.get(ideas.COOKIE) or c.cookies.get(ideas.COOKIE)
    assert cookie and cookie.split(".") == [str(i) for i in range(1, 11)]
    assert "Max-Age" not in r.headers.get("set-cookie", "") and "expires" not in r.headers.get("set-cookie", "").lower()
    html = c.get("/").text                                     # back to Home: the same ten
    i = html.index('id="ideas"')
    assert html[i:html.index("</ul>", i)].count("<li>") == 10 and "Idea number 10" in html


def test_remembered_list_never_over_the_maximum(monkeypatch):
    _fake_pool(monkeypatch)
    top = ideas.MAX_TOTAL                                      # 40 (owner, 2026-10-22)
    c = TestClient(main.app, base_url="https://testserver")    # the cookie is Secure on https sites
    c.cookies.set(ideas.COOKIE, ".".join(str(i) for i in range(1, top + 6)))
    html = c.get("/").text
    assert html.count('<li><a href="/ask?intent=x&amp;id=') == top and "Show more suggested searches" not in html


def test_model_is_opus():
    assert ideas.MODELS[0] == "claude-opus-5-5"


def test_more_stops_at_the_maximum_and_never_repeats(monkeypatch):
    _fake_pool(monkeypatch)
    top = ideas.MAX_TOTAL
    seen = ",".join(str(i) for i in range(1, top - 4))
    html = client.get(f"/?more=1&seen={seen}").text
    assert html.count('<li><a href="/ask?intent=x&amp;id=') == top and f"Idea number {top}" in html
    assert "Show more suggested searches" not in html                        # the maximum shown: More is gone
    assert ideas.more_ids(list(range(1, top + 1))) == []


def test_schema_overview_lists_live_tables_and_boards():
    from app import db
    db.pool.open(wait=True)
    text = ideas.schema_overview()
    assert "- organizations (~" in text and "ein" in text
    assert "Leaderboards" in text and "top-paid" in text
    assert "home_ideas" not in text and "board_top_paid" not in text      # bookkeeping and board views left out
