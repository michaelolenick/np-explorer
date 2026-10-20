"""Home page "Interesting ideas…": questions a language model proposes from what the site can answer, each checked
before it is shown.

- A pool of checked ideas is rebuilt once a day: the first home-page view after the pool is a day old starts a
  background call (Claude Fable 5.1, falling back to Claude Opus 5.5) for about 40 ideas. Each idea is a plain-English
  question plus the structured search behind it (the same tools as the search box, app/ask.py TOOLS). Every one is
  validated (ask.validate) and run (ask.run_page); only ideas that return real results are kept (home_ideas).
- The first five rotate daily (a stable order per day). "More" shows five unseen ideas from the pool; once a visitor
  has seen the whole pool, it asks the model live for new ones, sending every question already shown so nothing
  repeats, checks them the same way, stores them and shows them. The ideas shown are in the URL (?seen=ids), so a
  link reproduces the list.
- A click runs the stored structured search directly: no model call per click, and the result is what was checked.
- A visitor's list (at most 20) is remembered for the browser session in a cookie (COOKIE), so going back to the
  home page shows the same ideas.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import httpx
import psycopg

from app import ask, db
from app.config import DATABASE_URL

log = logging.getLogger("np.ideas")

PER_PAGE = 5
COOKIE = "ss_ideas"          # session cookie: the ids of the ideas this visitor has on their list
MAX_TOTAL = 20               # ideas on the page at most (owner, 2026-10-20)
MAX_SEEN = 200                # ids carried in the URL
REFRESH_HOURS = 24
KEEP_DAYS = 7                 # older ideas are dropped
DAILY_ASK = 40                # ideas requested for the daily pool
LIVE_ASK = 10                 # ideas requested for one "More" press (five shown)
MIN_ROWS = 3                  # a ranked list must return at least this many rows to be shown
LOCK_KEY = 811_204_457        # pg advisory lock: one daily generator across workers and servers
# Claude Opus 5.5 (owner, 2026-10-20: "it's creative enough"). Effort is set explicitly (its default is medium).
# IDEAS_MODELS (comma-separated) overrides; each is tried in turn if one declines.
MODELS = [m for m in os.environ.get("IDEAS_MODELS", "claude-opus-5-5").split(",") if m]
DAILY_EFFORT, LIVE_EFFORT = "high", "medium"
DAILY_TIMEOUT, LIVE_TIMEOUT = 300.0, 60.0

_running = threading.Lock()
_checked = [0.0]              # last time this process looked at the pool's age

# Structured output (output_config.format): these models reject forced tool_choice, and a JSON schema guarantees the
# shape. Strict schemas allow no free-form objects, so each idea's search arguments come back as a JSON string.
IDEAS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ideas"],
    "properties": {"ideas": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["question", "tool", "args_json"],
        "properties": {
            "question": {"type": "string"},
            "tool": {"type": "string", "enum": [t["name"] for t in ask.TOOLS if t["name"] != "unknown"]},
            "args_json": {"type": "string"}}}}},
}

SYSTEM = """You suggest interesting things to look up on Strategy Studio (strategystudio.org), a free public data \
explorer. It has: IRS Form 990 filings of US nonprofits (who runs them, what they pay their executives, board \
members, vendors, grants made and received, donor-advised funds, finances by year, fundraising events and galas); \
public university payrolls (person by person, about 25 states), coaches' pay, school pages, and the site's \
leaderboards.

Each idea is a question (under 80 characters, as a curious person would type it) plus the exact search that \
answers it: "tool" is one of the tools below and "args_json" is that tool's arguments as a JSON object, written as \
a string, following its schema exactly. Tools (name, description, arguments):
{catalog}

Rules:
- Make them genuinely interesting: surprising pay, big money, famous institutions, sports, hospitals, universities, \
foundations, comparisons, changes over time. Mix the tools.
- Use well-known, real US organizations, universities and states; tax years 2015-2024.
- Name a person only if they are a well-known public figure in that role (a university president, a head coach, a \
large nonprofit's CEO). Never private individuals.
- The question must say exactly what the search does: same organization, state, year and topic as the arguments.
- Neutral wording: no accusations or claims about wrongdoing.
- Nothing that repeats or closely rephrases these questions already shown: {shown}"""


def _catalog() -> str:
    return json.dumps([{"name": t["name"], "description": t["description"],
                        "args": t["input_schema"].get("properties", {})}
                       for t in ask.TOOLS if t["name"] != "unknown"], separators=(",", ":"))


def propose(shown: list[str], count: int, effort: str, timeout: float) -> list[dict]:
    """One model call: [{question, tool, args}] (not yet checked). Tries each model in MODELS until one answers."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return []
    payload = {"max_tokens": 16000, "fallbacks": "default",
               "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": IDEAS_SCHEMA}},
               "system": SYSTEM.format(catalog=_catalog(), shown="; ".join(shown[-MAX_SEEN:]) or "none"),
               "messages": [{"role": "user",
                             "content": f"Propose {count} ideas. Today is {dt.date.today():%B %d, %Y}."}]}
    for model in MODELS:
        try:
            r = httpx.post(ask.API_URL, timeout=timeout, headers={
                "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
                "anthropic-beta": "server-side-fallback-2026-07-01"}, json={"model": model, **payload})
        except httpx.HTTPError as e:
            log.warning("ideas: %s call failed (%s)", model, type(e).__name__)
            continue
        if r.status_code != 200:
            log.warning("ideas: %s returned %s", model, r.status_code)      # status only, never the key or body
            continue
        body = r.json()
        u = body.get("usage") or {}
        ask._usage(calls=1, input_tokens=int(u.get("input_tokens") or 0), output_tokens=int(u.get("output_tokens") or 0))
        if body.get("stop_reason") in ("refusal", "max_tokens"):
            log.warning("ideas: %s stopped (%s)", model, body.get("stop_reason"))
            continue
        text = "".join(c.get("text", "") for c in body.get("content", []) if c.get("type") == "text")
        try:
            ideas = json.loads(text).get("ideas") or []
        except (ValueError, AttributeError):
            log.warning("ideas: %s reply was not the expected JSON", model)
            continue
        out = []
        for i in ideas:
            try:
                out.append({"question": i.get("question"), "tool": i.get("tool"),
                            "args": json.loads(i.get("args_json") or "{}")})
            except (ValueError, TypeError, AttributeError):
                continue
        log.info("ideas: %s proposed %d ideas", model, len(out))
        return out
    return []


def works(intent: dict) -> bool:
    """True when the search runs and returns something worth clicking."""
    if intent.get("intent") in (None, "unknown", "plain"):
        return False
    try:
        res = ask.run_page(intent, 1)
    except Exception:  # noqa: BLE001 - a search that errors is simply not shown
        log.info("ideas: %s failed to run", intent.get("intent"))
        return False
    if res.get("kind") in (None, "none", "unsupported", "school_choices"):
        return False
    rows = res.get("rows")
    if isinstance(rows, list):
        return len(rows) >= (MIN_ROWS if "page" in res else 1)
    return True


def _norm(q: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (q or "").lower()).strip()


def check_and_store(proposed: list[dict], shown: list[str], want: int | None = None) -> list[int]:
    """Validate and run proposed ideas (in parallel), store the ones that work, return their ids in proposal order."""
    seen = {_norm(q) for q in shown}
    cands = []
    for idea in proposed:
        q = re.sub(r"\s+", " ", str(idea.get("question") or "")).strip()[:120]
        if not q or _norm(q) in seen:
            continue
        seen.add(_norm(q))
        cands.append((q, ask.validate(str(idea.get("tool") or ""), idea.get("args"))))
    with ThreadPoolExecutor(max_workers=4) as ex:
        ok = list(ex.map(lambda c: works(c[1]), cands))
    keep = [c for c, good in zip(cands, ok) if good][:want or None]
    ids = []
    if keep:
        with db.conn() as conn:
            with conn.transaction():
                for q, intent in keep:
                    ids.append(conn.execute("INSERT INTO home_ideas (question, intent) VALUES (%s, %s) RETURNING id",
                                            (q, json.dumps(intent))).fetchone()["id"])
                conn.execute("DELETE FROM home_ideas WHERE created < now() - make_interval(days => %s)", (KEEP_DAYS,))
    return ids


def refresh(status=log.info) -> int:
    """The daily pool. Returns how many ideas were stored (0 if another worker is already doing it)."""
    with psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), autocommit=True,
                         application_name="np-ideas") as lock_conn:
        if not lock_conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
            return 0
        try:
            with db.conn() as conn:
                recent = [r["question"] for r in conn.execute(
                    "SELECT question FROM home_ideas ORDER BY created DESC LIMIT 100").fetchall()]
            ids = check_and_store(propose(recent, DAILY_ASK, DAILY_EFFORT, DAILY_TIMEOUT), recent)
            status(f"ideas: stored {len(ids)} checked ideas")
            return len(ids)
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def _stale() -> bool:
    try:
        with db.conn() as conn:
            row = conn.execute("SELECT max(created) AS t FROM home_ideas").fetchone()
    except Exception:  # noqa: BLE001 - no table yet
        return False
    return not row or row["t"] is None or row["t"] < dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=REFRESH_HOURS)


def maybe_refresh() -> None:
    """Start a background refresh when the pool is a day old (looked at most every 10 minutes per process)."""
    now = time.time()
    if now - _checked[0] < 600 or not os.environ.get("ANTHROPIC_API_KEY"):
        return
    _checked[0] = now
    if not _stale() or not _running.acquire(blocking=False):
        return

    def run():
        try:
            refresh()
        except Exception:  # noqa: BLE001
            log.exception("ideas: refresh failed")
        finally:
            _running.release()
    threading.Thread(target=run, name="ideas-refresh", daemon=True).start()


def _pool_ids(exclude: list[int], k: int) -> list[int]:
    """The next k ideas in today's order (stable all day), skipping those already shown."""
    try:
        with db.conn() as conn:
            rows = conn.execute("""SELECT id FROM home_ideas
                                   WHERE created > now() - make_interval(days => %s) AND id <> ALL(%s)
                                   ORDER BY md5(id::text || current_date::text) LIMIT %s""",
                                (KEEP_DAYS, exclude, k)).fetchall()
    except Exception:  # noqa: BLE001 - no table yet
        return []
    return [r["id"] for r in rows]


def first_ids() -> list[int]:
    return _pool_ids([], PER_PAGE)


def more_ids(seen: list[int], live_ok: bool) -> list[int]:
    """Five more for a visitor who has seen `seen`: unseen pool ideas first; then, if live_ok, new ones from the
    model, given every question already shown so it doesn't repeat them."""
    want = min(PER_PAGE, MAX_TOTAL - len(seen))
    if want <= 0:
        return []
    ids = _pool_ids(seen, want)
    if len(ids) < want and live_ok:
        shown = [i["question"] for i in fetch(seen + ids)]
        try:
            ids += check_and_store(propose(shown, LIVE_ASK, LIVE_EFFORT, LIVE_TIMEOUT), shown, want - len(ids))
        except Exception:  # noqa: BLE001 - a failed live call just shows what the pool has
            log.exception("ideas: live generation failed")
    return ids


def fetch(ids: list[int]) -> list[dict]:
    """[{id, question, url}] for these ids, in the same order."""
    if not ids:
        return []
    try:
        with db.conn() as conn:
            rows = {r["id"]: r for r in conn.execute("SELECT id, question, intent FROM home_ideas WHERE id = ANY(%s)",
                                                     (ids,)).fetchall()}
    except Exception:  # noqa: BLE001
        return []
    return [{"id": i, "question": rows[i]["question"],
             "url": ask.edit_url(rows[i]["intent"]) + "&" + urlencode({"q": rows[i]["question"]})}
            for i in ids if i in rows]


def parse_seen(v: str | None) -> list[int]:
    out = []
    for p in re.split(r"[,.]", v or ""):        # "," in URLs; "." in the cookie (commas get escaped there)
        if p.strip().isdigit() and int(p) not in out:
            out.append(int(p))
    return out[:MAX_SEEN]


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["refresh"]:
        print(f"stored {refresh(print)}")
