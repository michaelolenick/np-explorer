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
    out = ideas.propose(["An old question"], 10, "medium", 5)
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
    assert ideas.propose([], 5, "medium", 5) == []


def test_parse_seen():
    assert ideas.parse_seen("3,1,3,x,2") == [3, 1, 2]
    assert len(ideas.parse_seen(",".join(str(i) for i in range(500)))) == ideas.MAX_SEEN


def _fake_pool(monkeypatch):
    pool = {i: f"Idea number {i}" for i in range(1, 21)}
    monkeypatch.setattr(ideas, "maybe_refresh", lambda: None)
    monkeypatch.setattr(ideas, "first_ids", lambda: [1, 2, 3, 4, 5])
    monkeypatch.setattr(ideas, "more_ids", lambda seen, live_ok: [i for i in pool if i not in seen][:5])
    monkeypatch.setattr(ideas, "fetch", lambda ids: [{"id": i, "question": pool[i], "url": f"/ask?intent=x&id={i}"}
                                                     for i in ids if i in pool])


def test_home_shows_five_and_more_adds_five_unseen(monkeypatch):
    _fake_pool(monkeypatch)
    html = client.get("/").text
    assert "Interesting ideas&hellip;" in html and "Or ask:" not in html
    assert html.count('<li><a href="/ask?intent=x&amp;id=') == 5
    assert 'href="/?more=1&amp;seen=1%2C2%2C3%2C4%2C5#ideas" rel="nofollow">More</a>' in html
    html = client.get("/?more=1&seen=1,2,3,4,5").text
    assert html.count('<li><a href="/ask?intent=x&amp;id=') == 10 and "Idea number 10" in html
    assert 'seen=1%2C2%2C3%2C4%2C5%2C6%2C7%2C8%2C9%2C10#ideas' in html
    assert '<link rel="canonical" href="' in html and '/?more' not in html.split('<link rel="canonical" href="')[1][:60]


def test_home_falls_back_to_fixed_examples(monkeypatch):
    monkeypatch.setattr(ideas, "maybe_refresh", lambda: None)
    monkeypatch.setattr(ideas, "first_ids", lambda: [])
    monkeypatch.setattr(ideas, "fetch", lambda ids: [])
    html = client.get("/").text
    assert "Interesting ideas&hellip;" in html and "Who runs the Workforce Incubator Foundation?" in html


def test_robots_keeps_crawlers_off_more():
    assert "Disallow: /?more=" in client.get("/robots.txt").text or \
        "Disallow: /?more=" in (main.ROOT / "static" / "robots.txt").read_text()
