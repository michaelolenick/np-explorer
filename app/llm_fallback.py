"""Retry a model step through other models when the first one declines (owner, 2026-11-12).

FURP's AI steps (the search planner in app/ask.py, deep-query planning and answers in app/deep.py, the short answer
in app/answer.py, page explanations in app/explain.py and app/autoexplain.py) only turn a question into one of the
site's own SQL searches and then put the rows into words. A model that answers "I can't", "I'm unable" or plans
nothing for a request the site supports (an uploaded document, a known table) is a model problem, not a scope
problem. So: detect the refusal, retry the same step through OpenRouter with the models in LLM_FALLBACK_MODELS
(in order, comma-separated in .env; the default list is below), tell the user which model answered in the end, and
log every attempt in llm_attempts (what the /admin page lists) so the owner can see which models refuse. When every
model fails, the caller shows the last real error, not a rewritten suggestion.

Needs OPENROUTER_API_KEY in .env (already there on both boxes). Model ids are OpenRouter ids (provider/model).
"""

from __future__ import annotations

import logging
import os
import re
import time

import httpx

from app import db

log = logging.getLogger("np.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/messages"
DEFAULT_MODELS = "anthropic/claude-opus-5.5,openai/gpt-5.6-terra,google/gemini-4-carbon,x-ai/grok-4.7"


def models() -> list[str]:
    """The fallback models, in order: LLM_FALLBACK_MODELS in .env (comma-separated OpenRouter ids); the default
    list when the variable is not set; none at all when it is set but empty (the tests set it empty so no test
    ever reaches a real model)."""
    raw = os.environ.get("LLM_FALLBACK_MODELS")
    if raw is None:
        raw = DEFAULT_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


def enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY")) and bool(models())


# What a refusal looks like in a model's text (the text is the model's own words, so these phrases are its).
REFUSAL_RE = re.compile(
    r"\b(I can(?:no|')?t (?:help|assist|do|provide|access|read|summari[sz]e|comply|answer)|I(?:'m| am) unable|"
    r"unable to (?:help|assist|comply|provide|access|read)|cannot assist|can'?t assist|I won'?t be able|"
    r"not able to (?:help|assist|access|read)|as an AI\b|outside (?:of )?(?:my|the|its) (?:scope|capabilit)|"
    r"beyond (?:my|the) (?:scope|capabilit)|I (?:must|have to) (?:decline|refuse)|I'?m not able to|"
    r"What we can'?t do|don'?t have (?:access|the ability) to)", re.I)

# Requests the site does support, even when the planner says otherwise: uploaded documents and the known tables.
SUPPORTED_RE = re.compile(
    r"\b(upload(?:ed|s)?|document|file|court case|lawsuit|case file|complaint|deposition|mailbox|email|pst|"
    r"attachment|pdf|spreadsheet|nonprofit|charit|990|salary|salaries|pay|compensation|grant|donor|lobby|"
    r"contract|campaign|fec|sec|insider|form d|patent|trademark|recall|payroll|census|ipo|s-1|board|trustee|"
    r"officer|director|executive|revenue|assets|contractor|vendor|college|university|school|hospital)\b", re.I)


def is_refusal_text(text: str | None) -> bool:
    return bool(text) and bool(REFUSAL_RE.search(text))


def supported_request(question: str | None) -> bool:
    return bool(question) and bool(SUPPORTED_RE.search(question))


def text_of(body: dict | None) -> str:
    if not body:
        return ""
    return "".join(c.get("text", "") for c in body.get("content", []) if c.get("type") == "text").strip()


def tool_use(body: dict | None) -> dict | None:
    if not body:
        return None
    return next((c for c in body.get("content", []) if c.get("type") == "tool_use"), None)


def looks_refused(body: dict | None, expects_tool: bool = False) -> bool:
    """A reply that declined: refusal words in its text, a refusal stop, or (when a tool call was expected) no
    tool call and only prose."""
    if not body:
        return False
    if body.get("stop_reason") == "refusal":
        return True
    text = text_of(body)
    if is_refusal_text(text):
        return True
    return expects_tool and tool_use(body) is None and bool(text)


def payload_for(model: str, payload: dict) -> dict:
    """The same request for another model: Anthropic-only fields (thinking, output_config) only go to Anthropic
    models; everyone gets the system prompt, the tools and the messages unchanged."""
    out = {**payload, "model": model}
    if not model.startswith("anthropic/"):
        out.pop("thinking", None)
        out.pop("output_config", None)
        if isinstance(out.get("tool_choice"), dict):
            out["tool_choice"] = {"type": out["tool_choice"].get("type", "auto")}
    return out


# --- the attempt log ---------------------------------------------------------------------------------------------
# Created on first use, not by a migration (two other loads were adding migrations the day this was written).
_ready = False
ATTEMPTS_SQL = """
CREATE TABLE IF NOT EXISTS llm_attempts (
    id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), step text NOT NULL, model text NOT NULL,
    outcome text NOT NULL, ms integer, detail text);
CREATE INDEX IF NOT EXISTS llm_attempts_at ON llm_attempts (at DESC);
"""


def log_attempt(step: str, model: str, outcome: str, ms: float | None = None, detail: str | None = None) -> None:
    """One line in the log and one row in llm_attempts: step, model, outcome (declined / ok / http 429 / error)."""
    global _ready
    log.info("llm %s: %s -> %s%s", step, model, outcome, f" ({detail[:120]})" if detail else "")
    try:
        with db.conn() as conn:
            if not _ready:
                conn.execute(ATTEMPTS_SQL)
                _ready = True
            conn.execute("INSERT INTO llm_attempts (step, model, outcome, ms, detail) VALUES (%s, %s, %s, %s, %s)",
                         (step[:40], model[:80], outcome[:60], None if ms is None else int(ms), (detail or None) and detail[:300]))
    except Exception:  # noqa: BLE001 - the log never breaks a step
        log.exception("llm: attempt log")


def recent_attempts(limit: int = 50) -> list[dict]:
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('llm_attempts') AS t").fetchone()["t"]:
                return []
            return conn.execute("SELECT at, step, model, outcome, ms, detail FROM llm_attempts ORDER BY at DESC, id DESC LIMIT %s",
                                (limit,)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("llm: reading attempts")
        return []


# --- the retry -----------------------------------------------------------------------------------------------------

def note_for(model: str | None, first: str) -> str | None:
    """The one line shown to the user when another model had to answer."""
    return f"The first model ({first}) declined this request, so we retried with {model}." if model else None


def retry(step: str, payload: dict, timeout: float, usable, first_model: str, why: str = "declined") -> dict:
    """Run the step again through each fallback model until `usable(body)` is true.

    Returns {"body": reply or None, "model": the model that answered or None, "note": the user-facing line or None,
    "error": the last real error when every model failed, "attempts": [(model, outcome), ...]}.
    `usable(body) -> bool` is the step's own test (a validated plan, a non-refusal summary, parseable JSON)."""
    out = {"body": None, "model": None, "note": None, "error": None, "attempts": [(first_model, why)]}
    if not enabled():
        # Nothing to retry with: the first model's failure is in the app log already; no attempt rows.
        out["error"] = ("No fallback models: set OPENROUTER_API_KEY (and optionally LLM_FALLBACK_MODELS) in .env."
                        if not os.environ.get("OPENROUTER_API_KEY") else "LLM_FALLBACK_MODELS is empty: no fallback models.")
        return out
    log_attempt(step, first_model, why)
    for model in models():
        t0 = time.monotonic()
        try:
            r = httpx.post(OPENROUTER_URL, timeout=timeout, headers={
                "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "anthropic-version": "2023-06-01",
                "content-type": "application/json", "HTTP-Referer": "https://furp.org", "X-Title": "FURP"},
                json=payload_for(model, payload))
        except httpx.HTTPError as ex:
            ms = (time.monotonic() - t0) * 1000
            out["error"] = f"{model}: {type(ex).__name__}"
            log_attempt(step, model, "error", ms, type(ex).__name__)
            out["attempts"].append((model, "error"))
            continue
        ms = (time.monotonic() - t0) * 1000
        if r.status_code != 200:
            detail = ""
            try:
                detail = str((r.json().get("error") or {}).get("message") or "")[:200]
            except Exception:  # noqa: BLE001
                detail = ""
            out["error"] = f"{model}: HTTP {r.status_code}{' ' + detail if detail else ''}"
            log_attempt(step, model, f"http {r.status_code}", ms, detail)
            out["attempts"].append((model, f"http {r.status_code}"))
            continue
        try:
            body = r.json()
        except ValueError:
            out["error"] = f"{model}: reply was not JSON"
            log_attempt(step, model, "bad reply", ms)
            out["attempts"].append((model, "bad reply"))
            continue
        try:
            ok = bool(usable(body))
        except Exception as ex:  # noqa: BLE001
            ok = False
            log.exception("llm: usable() failed")
            out["error"] = f"{model}: {type(ex).__name__}"
        if ok:
            log_attempt(step, model, "ok", ms)
            out.update(body=body, model=model, note=note_for(model, first_model))
            out["attempts"].append((model, "ok"))
            return out
        declined = looks_refused(body, expects_tool="tools" in payload)
        out["error"] = f"{model}: {'declined' if declined else 'no usable answer'}"
        if not declined:
            t = text_of(body)
            if t:
                out["error"] += ": " + t[:200]
        log_attempt(step, model, "declined" if declined else "unusable", ms, text_of(body)[:200])
        out["attempts"].append((model, "declined" if declined else "unusable"))
    return out
