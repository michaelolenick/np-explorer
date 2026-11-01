"""Owner, 2026-11-01: LLM_VIA=openrouter sends the small model calls through OpenRouter."""

from app import ask


class _Sent(Exception):
    pass


def _capture(monkeypatch):
    sent = {}

    def fake(url, **kw):
        sent.update(url=url, **kw)
        raise _Sent
    monkeypatch.setattr(ask.httpx, "post", fake)
    return sent


def test_openrouter_when_switched(monkeypatch):
    monkeypatch.setenv("LLM_VIA", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    sent = _capture(monkeypatch)
    try:
        ask.post({"model": "claude-haiku-5-5", "max_tokens": 5}, 5)
    except _Sent:
        pass
    assert sent["url"] == ask.OPENROUTER_URL
    assert sent["json"]["model"] == "anthropic/claude-haiku-5.5"
    assert sent["headers"]["Authorization"] == "Bearer test-key"
    assert ask.enabled()


def test_anthropic_by_default(monkeypatch):
    monkeypatch.delenv("LLM_VIA", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    sent = _capture(monkeypatch)
    try:
        ask.post({"model": "claude-haiku-5-5", "max_tokens": 5}, 5)
    except _Sent:
        pass
    assert sent["url"] == ask.API_URL
    assert sent["json"]["model"] == "claude-haiku-5-5"
