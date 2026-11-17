"""Owner, 2026-11-17: OpenAI direct first (free key, about two weeks), and OpenRouter never without approval."""
from datetime import date

import httpx

from app import ask, llm_fallback as fb, openai_compat, openrouter_gate


def test_gate_needs_a_current_approval_file(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_APPROVAL_DIR", str(tmp_path))
    assert not openrouter_gate.allowed()
    f = tmp_path / "openrouter_ok.txt"
    f.write_text("until 2026-11-17")
    assert openrouter_gate.allowed(date(2026, 11, 17)) and not openrouter_gate.allowed(date(2026, 11, 18))
    f.write_text("yes please")
    assert not openrouter_gate.allowed()


def test_messages_payload_becomes_openai_and_back():
    payload = {"model": "claude-haiku-5-5", "max_tokens": 300, "system": "be brief",
               "messages": [{"role": "user", "content": "hi"}],
               "tools": [{"name": "documents", "description": "d", "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}}}],
               "tool_choice": {"type": "tool", "name": "documents"}}
    o = openai_compat.to_openai(payload, "gpt-x")
    assert o["model"] == "gpt-x" and o["messages"][0] == {"role": "system", "content": "be brief"}
    assert o["tools"][0]["function"]["name"] == "documents"
    assert o["tool_choice"] == {"type": "function", "function": {"name": "documents"}}
    back = openai_compat.to_messages({"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "c1", "function": {"name": "documents", "arguments": "{\"text\": \"court case\"}"}}]}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3}})
    assert back["content"][0] == {"type": "tool_use", "id": "c1", "name": "documents", "input": {"text": "court case"}}
    assert back["stop_reason"] == "tool_use" and back["usage"] == {"input_tokens": 7, "output_tokens": 3}


def test_ask_post_goes_to_openai_then_anthropic_never_openrouter(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_APPROVAL_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_VIA", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    urls = []

    class R:
        def __init__(self, status, body):
            self.status_code, self._b, self.text = status, body, ""

        def json(self):
            return self._b

    def fake(url, **kw):
        urls.append(url)
        if url == openai_compat.URL:
            return R(401, {"error": {"message": "expired"}})
        return R(200, {"content": [{"type": "text", "text": "ok"}], "usage": {}})
    monkeypatch.setattr(ask.httpx, "post", fake)
    monkeypatch.setattr(openai_compat.httpx, "post", fake)
    r = ask.post({"model": "claude-haiku-5-5", "max_tokens": 5, "messages": []}, 5)
    assert r.status_code == 200 and urls == [openai_compat.URL, ask.API_URL]


def test_fallback_skips_openrouter_without_approval_and_uses_openai(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_APPROVAL_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "oa-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "openai:gpt-test,test/or-model")
    asked, called = [], []
    monkeypatch.setattr(openrouter_gate, "ask_owner", lambda what: asked.append(what) or True)
    monkeypatch.setattr(fb, "log_attempt", lambda *a, **k: None)

    def fake_openai(payload, timeout, use_model=None):
        called.append(use_model)
        return openai_compat.Resp(200, {"content": [{"type": "text", "text": "an answer"}], "usage": {}})
    monkeypatch.setattr(openai_compat, "post", fake_openai)
    monkeypatch.setattr(fb.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("OpenRouter was called")))
    out = fb.retry("t", {"model": "m", "messages": []}, 5, lambda b: True, "m")
    assert out["model"] == "openai:gpt-test" and called == ["gpt-test"] and not asked
    # OpenAI fails: the next model is OpenRouter, which is not called; the owner is asked, once
    monkeypatch.setattr(openai_compat, "post", lambda p, t, use_model=None: openai_compat.Resp(401, {"error": {"message": "expired"}}))
    out = fb.retry("t", {"model": "m", "messages": []}, 5, lambda b: True, "m")
    assert out["body"] is None and "needs the owner's approval" in out["error"] and len(asked) == 1
