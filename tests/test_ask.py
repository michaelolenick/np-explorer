"""Ask: how model replies become plans (the API is faked; no network, no database)."""

import pytest

from app import ask


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    ask._cache.clear()
    ask._day.update(date="", n=0)


def fake(monkeypatch, status=200, body=None, calls=None):
    def post(url, json, headers, timeout):
        if calls is not None:
            calls.append(json)
        return Resp(status, body or {"content": [{"type": "tool_use", "name": "organization_people",
                                                  "input": {"organization": "Workforce Incubator Foundation"}}]})
    monkeypatch.setattr(ask.httpx, "post", post)


def test_question_becomes_a_tool_call(monkeypatch):
    calls = []
    fake(monkeypatch, calls=calls)
    plan = ask.interpret("Who is in the Workforce Incubator Foundation?")
    assert plan == {"tool": "organization_people", "args": {"organization": "Workforce Incubator Foundation"}}
    sent = calls[0]
    assert sent["tool_choice"] == {"type": "any"} and {t["name"] for t in sent["tools"]} >= {
        "people_search", "organization_people", "find_organizations", "organization_money", "leaderboard"}


def test_repeat_questions_are_cached(monkeypatch):
    calls = []
    fake(monkeypatch, calls=calls)
    ask.interpret("Who runs REDM?")
    ask.interpret("  who runs   redm? ")
    assert len(calls) == 1


def test_errors_and_budget(monkeypatch, caplog):
    fake(monkeypatch, status=500)
    assert ask.interpret("anything") == {"error": "unavailable"}
    assert "test-key" not in caplog.text
    fake(monkeypatch, body={"content": [{"type": "text", "text": "hmm"}]})
    assert ask.interpret("something else") == {"error": "unclear"}
    ask._day.update(date=__import__("time").strftime("%Y-%m-%d"), n=ask.PER_DAY)
    assert ask.interpret("one more") == {"error": "busy"}


def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert not ask.enabled()


def test_board_tool_lists_only_visible_boards():
    board_tool = next(t for t in ask.TOOLS if t["name"] == "leaderboard")
    slugs = board_tool["input_schema"]["properties"]["board"]["enum"]
    assert "top-paid" in slugs and "revolving-door" not in slugs
