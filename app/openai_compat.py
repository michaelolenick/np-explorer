"""OpenAI direct (owner, 2026-11-17: a free OpenAI key, good for about two weeks, "put in .env and use though").

The site's small model calls speak Anthropic's Messages format (app/ask.py `post`). This module sends the same payload to
OpenAI's chat completions endpoint with OPENAI_API_KEY and turns the reply back into the Messages shape (content blocks,
tool_use, usage, stop_reason), so every caller keeps working unchanged. LLM_VIA=openai in .env makes it the first stop;
when it fails (the key expires or runs out of credit, a refusal), the caller goes on to Anthropic, never to OpenRouter
(app/openrouter_gate.py). The key is read from the environment and never logged.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

log = logging.getLogger("np.llm")
URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-mini"      # small calls (planner, short answers, explanations); OPENAI_MODEL overrides


def enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def model() -> str:
    return os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL


class Resp:
    """The bit of httpx.Response the callers use: status_code, json(), text."""

    def __init__(self, status: int, body: dict):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def to_openai(payload: dict, use_model: str | None = None) -> dict:
    """An Anthropic Messages payload as an OpenAI chat completions request."""
    msgs = []
    system = _text(payload.get("system"))
    if system:
        msgs.append({"role": "system", "content": system})
    for m in payload.get("messages", []):
        msgs.append({"role": m["role"], "content": _text(m.get("content"))})
    want = int(payload.get("max_tokens") or 1000)
    out = {"model": use_model or model(), "messages": msgs,
           "max_completion_tokens": want + 2000,       # reasoning tokens count against the limit
           "reasoning_effort": "low"}
    tools = payload.get("tools") or []
    if tools:
        out["reasoning_effort"] = "none"          # OpenAI rejects function tools together with reasoning on chat completions
        out["tools"] = [{"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}} for t in tools]
        tc = payload.get("tool_choice") or {}
        kind = tc.get("type", "auto") if isinstance(tc, dict) else "auto"
        if kind == "tool" and tc.get("name"):
            out["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
        elif kind == "any":
            out["tool_choice"] = "required"
        elif kind == "none":
            out["tool_choice"] = "none"
        else:
            out["tool_choice"] = "auto"
    return out


def to_messages(data: dict) -> dict:
    """An OpenAI chat completions reply as an Anthropic Messages reply."""
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        content.append({"type": "tool_use", "id": call.get("id", ""), "name": fn.get("name", ""), "input": args})
    finish = choice.get("finish_reason")
    stop = {"length": "max_tokens", "tool_calls": "tool_use", "content_filter": "refusal"}.get(finish, "end_turn")
    if msg.get("refusal"):
        stop = "refusal"
        content.append({"type": "text", "text": msg["refusal"]})
    u = data.get("usage") or {}
    return {"id": data.get("id", ""), "type": "message", "role": "assistant", "model": data.get("model", ""),
            "content": content, "stop_reason": stop,
            "usage": {"input_tokens": int(u.get("prompt_tokens") or 0), "output_tokens": int(u.get("completion_tokens") or 0)}}


def post(payload: dict, timeout: float, use_model: str | None = None) -> Resp:
    """Send an Anthropic-style payload to OpenAI; a Messages-style Resp comes back. Raises httpx.HTTPError on a
    network failure, like httpx.post does."""
    r = httpx.post(URL, timeout=timeout, headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                                                  "content-type": "application/json"}, json=to_openai(payload, use_model))
    try:
        data = r.json()
    except ValueError:
        return Resp(502, {"error": {"message": "reply was not JSON"}})
    if r.status_code != 200:
        msg = str((data.get("error") or {}).get("message") or "")[:200]
        log.warning("openai: HTTP %s %s", r.status_code, msg)
        return Resp(r.status_code, {"error": {"message": msg}})
    return Resp(200, to_messages(data))
