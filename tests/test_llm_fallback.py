"""The model fallback (app/llm_fallback.py) and the documents intent (owner, 2026-11-12): a refusal or a failure is
retried through the configured OpenRouter models, the user is told, every attempt is logged, and when every model
fails the last real error is shown. No real model is called: httpx.post is replaced."""
import json
import secrets

import httpx
import pytest
from starlette.testclient import TestClient

from app import ask, db, llm_fallback as fb


@pytest.fixture(scope="module", autouse=True)
def client():
    """The app's test client for every test here, with the shared pool opened as tests/test_space.py does (no
    `with`: the lifespan would close the pool for the test modules that run after this one)."""
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _text(t):
    return {"content": [{"type": "text", "text": t}], "usage": {"input_tokens": 5, "output_tokens": 5}}


def _tool(name, args):
    return {"content": [{"type": "tool_use", "name": name, "input": args}], "usage": {"input_tokens": 5, "output_tokens": 7}}


def _cleanup():
    with db.conn() as conn:
        if conn.execute("SELECT to_regclass('llm_attempts') AS t").fetchone()["t"]:
            conn.execute("DELETE FROM llm_attempts WHERE model LIKE 'test/%' OR model = 'first/model' OR step = 'test-step'")


def test_refusal_and_supported_request_heuristics():
    assert fb.is_refusal_text("I'm sorry, but I can't help with reading uploaded documents.")
    assert fb.is_refusal_text("What we can't do: summarizing court records")
    assert not fb.is_refusal_text("The Gates Foundation reported $8.3 billion in grants.")
    assert fb.supported_request("tell me something about the court case i just uploaded")
    assert fb.supported_request("highest paid hospital executives in Ohio")
    assert not fb.supported_request("what is the weather tomorrow")
    assert fb.looks_refused(_text("I cannot assist with that."), expects_tool=True)
    assert fb.looks_refused(_text("Here is some prose instead of a tool call"), expects_tool=True)
    assert not fb.looks_refused(_tool("documents", {"text": "court case"}), expects_tool=True)


def test_payload_for_strips_anthropic_only_fields_for_other_models():
    p = {"model": "claude-sonnet-5-5", "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"},
         "tool_choice": {"type": "auto", "disable_parallel_tool_use": True}, "tools": [], "messages": []}
    a = fb.payload_for("anthropic/claude-opus-5.5", p)
    assert a["model"] == "anthropic/claude-opus-5.5" and "thinking" not in a and a["tool_choice"] == {"type": "auto"}
    o = fb.payload_for("openai/gpt-5.6-terra", p)
    assert o["model"] == "openai/gpt-5.6-terra" and "thinking" not in o and "output_config" not in o
    assert o["tool_choice"] == {"type": "auto"}


def test_retry_cycles_models_until_one_is_usable_and_logs_each(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "test/one, test/two, test/three")
    seen = []

    def fake_post(url, timeout, headers, json):
        seen.append(json["model"])
        assert "test-key" in headers["Authorization"] and url == fb.OPENROUTER_URL
        if json["model"] == "test/one":
            return _Resp(200, _text("I can't help with that request."))
        if json["model"] == "test/two":
            return _Resp(200, _tool("documents", {"text": "court case"}))
        raise AssertionError("the third model must not be called")
    monkeypatch.setattr(fb.httpx, "post", fake_post)
    try:
        out = fb.retry("test-step", {"model": "first/model", "tools": [{"name": "documents"}], "messages": []}, 10,
                       lambda b: fb.tool_use(b) is not None, "first/model", why="declined")
        assert seen == ["test/one", "test/two"]
        assert out["model"] == "test/two" and out["body"]["content"][0]["name"] == "documents"
        assert out["note"] == "The first model (first/model) declined this request, so we retried with test/two."
        assert [a for a in out["attempts"]] == [("first/model", "declined"), ("test/one", "declined"), ("test/two", "ok")]
        rows = fb.recent_attempts(10)
        got = [(r["model"], r["outcome"]) for r in rows if r["step"] == "test-step"]
        assert ("test/two", "ok") in got and ("test/one", "declined") in got and ("first/model", "declined") in got
    finally:
        _cleanup()


def test_retry_reports_the_last_real_error_when_every_model_fails(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "test/one,test/two")

    def fake_post(url, timeout, headers, json):
        if json["model"] == "test/one":
            return _Resp(429, {"error": {"message": "rate limited"}})
        raise httpx.ConnectError("boom")
    monkeypatch.setattr(fb.httpx, "post", fake_post)
    try:
        out = fb.retry("test-step", {"model": "first/model", "messages": []}, 10, lambda b: True, "first/model")
        assert out["body"] is None and out["model"] is None and out["note"] is None
        assert out["error"] == "test/two: ConnectError"
        assert out["attempts"][1:] == [("test/one", "http 429"), ("test/two", "error")]
    finally:
        _cleanup()


def test_retry_without_a_key_says_which_variable_to_set(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    try:
        out = fb.retry("test-step", {"model": "first/model", "messages": []}, 10, lambda b: True, "first/model")
        assert out["body"] is None and "OPENROUTER_API_KEY" in out["error"]
    finally:
        _cleanup()


def test_documents_intent_is_part_of_the_planner():
    assert {t["name"] for t in ask.TOOLS} >= {"documents", "unknown"}
    assert "court case" in ask.SYSTEM and "documents tool" in ask.SYSTEM
    assert ask.validate("documents", {"text": "the settlement"}) == {"intent": "documents", "text": "the settlement"}
    assert ask.validate("documents", {}) == {"intent": "documents", "text": ""}
    assert "uploaded documents" in ask.describe({"intent": "documents", "text": "x"})
    assert ask.run({"intent": "documents", "text": ""})["kind"] == "documents"


def test_planner_retries_a_refusal_through_the_fallback_and_tells_the_user(monkeypatch):
    monkeypatch.setattr(ask, "MODEL", "test/primary")        # so the attempt rows this test logs are cleaned up
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "test/two")
    question = f"tell me something about the court case i just uploaded {secrets.token_hex(3)}"
    monkeypatch.setattr(ask, "post", lambda timeout, payload: _Resp(200, _tool("unknown", {
        "reason": "x", "understood": "a summary of an uploaded court case",
        "unsupported": "Reading uploaded documents and summarizing court cases or legal records",
        "suggestion": "Gates Foundation"})))
    monkeypatch.setattr(fb.httpx, "post", lambda url, timeout, headers, json: _Resp(200, _tool("documents", {"text": "court case"})))
    try:
        parsed = ask.parse(question, "127.0.0.1", trusted=True)
        assert parsed["intent"] == "documents" and parsed["text"] == "court case"
        assert parsed["model_note"] == "The first model (test/primary) declined this request, so we retried with test/two."
    finally:
        _cleanup()


def test_planner_shows_the_last_real_error_when_every_model_fails(monkeypatch):
    monkeypatch.setattr(ask, "MODEL", "test/primary")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "test/two")
    question = f"tell me something about the court case i just uploaded {secrets.token_hex(3)}"
    monkeypatch.setattr(ask, "post", lambda timeout, payload: _Resp(503, {}))
    monkeypatch.setattr(fb.httpx, "post", lambda url, timeout, headers, json: _Resp(500, {"error": {"message": "upstream down"}}))
    try:
        parsed = ask.parse(question, "127.0.0.1", trusted=True)
        assert parsed["intent"] == "unknown" and parsed["error"] == "test/two: HTTP 500 upstream down"
    finally:
        _cleanup()


def test_ask_page_shows_the_error_box_not_a_suggestion(client, monkeypatch):
    monkeypatch.setattr(ask, "parse", lambda q, ip, trusted=False: {"intent": "unknown", "reason": "HTTP 503", "how": "fallback",
                                                                     "error": "test/two: HTTP 500 upstream down"})
    r = client.get("/ask?q=tell+me+about+the+court+case+i+just+uploaded")
    assert r.status_code == 200 and 'class="wide contained"' in r.text
    assert "could not run this request" in r.text and "test/two: HTTP 500 upstream down" in r.text
    assert "Closest search we can run" not in r.text


def test_ask_page_runs_the_documents_intent_and_shows_the_model_note(client, monkeypatch):
    from app import documents_search
    monkeypatch.setattr(ask, "parse", lambda q, ip, trusted=False: {"intent": "documents", "text": "court case", "how": "model",
                                                                     "model_note": "The first model (m1) declined this request, so we retried with test/two."})
    monkeypatch.setattr(documents_search, "run", lambda user, parsed, limit=20: {
        "kind": "documents", "total": 1, "note": "", "url": "/ask?intent=documents",
        "documents": [{"file_id": 1, "filename": "CourtCase.pst", "folder": "Leidig", "mark": "furp", "kind": "pst",
                       "status": "extracted", "pages": 0, "messages": 12345, "tables": 0, "entities": 40,
                       "uploaded_at": "2026-11-12", "url": "/space/file/1/CourtCase.pst",
                       "summary_text": "Inbox, Sent; 2019-2024; Re: settlement terms",
                       "entities_top": [{"kind": "org", "text": "Acme Foundation", "url": "/org/1", "count": 9}]}],
        "hits": [{"file_id": 1, "where": "message 2021-03-04 Re: settlement terms", "snippet": "the court case was filed", "url": "/space/file/1/CourtCase.pst"}]})
    monkeypatch.setattr(documents_search, "summary", lambda question, result: "A summary built from the rows.")
    r = client.get("/ask?q=tell+me+something+about+the+court+case+i+just+uploaded")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "CourtCase.pst" in r.text and "12,345 messages" in r.text and "Acme Foundation" in r.text
    assert "the court case was filed" in r.text and "A summary built from the rows." in r.text
    assert "so we retried with test/two" in r.text and "What we can't do" not in r.text


def test_documents_search_degrades_cleanly_without_the_pipeline(monkeypatch):
    from app import documents_search
    import sys
    import app as app_pkg
    monkeypatch.delattr(app_pkg, "space_ingest", raising=False)
    monkeypatch.setitem(sys.modules, "app.space_ingest", None)   # import fails -> the "not yet" note
    out = documents_search.run(None, {"intent": "documents", "text": ""})
    assert out["kind"] == "documents" and out["documents"] == [] and "not extracted yet" in out["note"]
    assert documents_search.summary("q", out) is None
