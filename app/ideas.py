"""Home page "Interesting ideas…": suggested lookups from a nightly pool, each checked before it is shown.

- Every night at midnight US Eastern (cron, deploy/cron/np-ideas) refresh() builds a new pool of POOL_SIZE ideas.
  The model (Claude Opus 5.5) gets an overview of every dataset on the site, built from the live database schema
  that night (schema_overview(): tables, approximate row counts, columns, plus the leaderboards), so new datasets
  are included as they are added. It is asked for interesting ideas, varied across datasets, a few of them spicy.
  Each idea is a plain-English question plus the structured search behind it (the same tools as the search box,
  app/ask.py TOOLS). Every one is validated (ask.validate) and run (ask.run_page); ideas that return no results
  are dropped. Rounds repeat until the pool is full (at most MAX_ROUNDS).
- A visitor sees five ideas picked at random from the latest pool. "More" adds five they haven't seen, up to
  MAX_TOTAL; then the More link goes away. No model call ever happens on a page view.
- The ideas shown are in the URL (?seen=ids), so a link reproduces the list; a visitor's list is remembered for
  the browser session in a cookie (COOKIE), so going back to the home page shows the same ideas.
- A click runs the stored structured search directly: no model call per click, and the result is what was checked.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import httpx
import psycopg

from app import ask, db
from app.config import DATABASE_URL

log = logging.getLogger("np.ideas")

PER_PAGE = 5
COOKIE = "ss_ideas"          # session cookie: the ids of the ideas this visitor has on their list
MAX_TOTAL = 25               # ideas on the page at most; then More goes away (owner, 2026-10-21)
MAX_SEEN = 200                # ids carried in the URL
POOL_SIZE = 120               # ideas in each night's pool (owner, 2026-10-21)
ASK_PER_CALL = 50             # ideas requested per model call; calls run in parallel, CALLS_PER_ROUND at a time
CALLS_PER_ROUND = 3
MAX_ROUNDS = 4
KEEP_DAYS = 14                # older ideas are dropped
MIN_ROWS = 3                  # a ranked list must return at least this many rows to be shown
LOCK_KEY = 811_204_457        # pg advisory lock: one daily generator across workers and servers
# Claude Opus 5.5 (owner, 2026-10-20: "it's creative enough"). Effort is set explicitly (its default is medium).
# IDEAS_MODELS (comma-separated) overrides; each is tried in turn if one declines.
MODELS = [m for m in os.environ.get("IDEAS_MODELS", "claude-opus-5-5").split(",") if m]
EFFORT, TIMEOUT = "high", 600.0

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

SYSTEM = """You suggest interesting things to look up on furp.org, a free public data \
explorer. Here is everything it holds tonight, from the live database (table, approximate rows, columns), and its \
leaderboards:
{overview}

Each idea is a question (under 80 characters, as a curious person would type it) plus the exact search that \
answers it: "tool" is one of the tools below and "args_json" is that tool's arguments as a JSON object, written as \
a string, following its schema exactly. Only these searches can be run, so every idea must be answerable by one of \
them (a leaderboard counts). Tools (name, description, arguments):
{catalog}

Rules:
- Make them genuinely interesting and varied: spread them across the datasets above (nonprofit pay and finances, \
grants and funders, vendors, galas, university payrolls and coaches, schools, student loans, campaign \
contributions, and anything newer), and across the tools and leaderboards. Surprising pay, big money, famous \
institutions, sports, hospitals, universities, foundations, comparisons, changes over time.
- Make a few of them spicy: provocative, eyebrow-raising questions a reporter would want to click. Spicy means \
pointed, not accusatory: still neutral and factual, no claims of wrongdoing.
- Use well-known, real US organizations, universities and states; recent years the data covers.
- Name a person only if they are a well-known public figure in that role (a university president, a head coach, a \
large nonprofit's CEO). Never private individuals.
- The question must say exactly what the search does: same organization, state, year and topic as the arguments.
- Nothing that repeats or closely rephrases these questions already in tonight's pool: {shown}"""

# Tables left out of the overview: internal bookkeeping, staging and per-visitor state.
SKIP_TABLES = re.compile(r"(^board_|_new$|_raw$|_runs?$|_crawl$|^loader_|^nl_|^home_ideas$|^alembic|^analytics|"
                         r"_progress$|^filing_year_counts$|_keys$|^usage|^sessions?$|^contact|^support_|^stripe|"
                         r"^stage_|^events$|^searches$|^daily_stats$|^report_history$|^loaded_objects$|^given_names$|"
                         r"^person_big_summary$|^person_search$)")


def schema_overview() -> str:
    """Tables in the public schema with approximate row counts and columns, from the live catalog, then the
    leaderboards. Rebuilt every night, so a new dataset shows up as soon as its tables exist."""
    from app import boards
    with db.conn() as conn:
        rows = conn.execute("""
            SELECT c.relname AS t, greatest(c.reltuples, 0)::bigint AS n,
                   string_agg(a.attname, ', ' ORDER BY a.attnum) AS cols
            FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE ns.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
            GROUP BY 1, 2 ORDER BY 1""").fetchall()
        parts = {r["p"]: r["n"] for r in conn.execute("""
            SELECT p.relname AS p, sum(greatest(c.reltuples, 0))::bigint AS n FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid JOIN pg_class p ON p.oid = i.inhparent GROUP BY 1""").fetchall()}
    lines = [f"- {r['t']} (~{parts.get(r['t'], r['n']):,} rows): {r['cols']}" for r in rows
             if not SKIP_TABLES.search(r["t"]) and parts.get(r["t"], r["n"]) > 0]     # empty tables aren't data yet
    lines.append("Leaderboards (tool \"leaderboard\", argument board):")
    lines += [f"- {b.slug}: {b.title}. {b.definition}" for b in boards.visible()]
    return "\n".join(lines)


def _catalog() -> str:
    return json.dumps([{"name": t["name"], "description": t["description"],
                        "args": t["input_schema"].get("properties", {})}
                       for t in ask.TOOLS if t["name"] != "unknown"], separators=(",", ":"))


def propose(shown: list[str], count: int, effort: str = EFFORT, timeout: float = TIMEOUT,
            overview: str | None = None, focus: str = "") -> list[dict]:
    """One model call: [{question, tool, args}] (not yet checked). Tries each model in MODELS until one answers."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return []
    payload = {"max_tokens": 32000, "fallbacks": "default",
               "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": IDEAS_SCHEMA}},
               "system": SYSTEM.format(overview=overview if overview is not None else schema_overview(),
                                       catalog=_catalog(), shown="; ".join(shown[-MAX_SEEN:]) or "none"),
               "messages": [{"role": "user",
                             "content": f"Propose {count} ideas. Today is {dt.date.today():%B %d, %Y}.{focus}"}]}
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


def reject(pool, question: str, reason: str, parsed: dict | None = None) -> None:
    """Log a suggestion the checker dropped (idea_rejects), so the owner sees what the query mode can't handle."""
    log.info("ideas: rejected %r: %s", question, reason)
    try:
        with db.conn() as conn:
            conn.execute("INSERT INTO idea_rejects (pool, question, reason, parsed) VALUES (%s, %s, %s, %s)",
                         (pool, question, reason, json.dumps(parsed, default=str) if parsed else None))
    except Exception:  # noqa: BLE001 - logging must not stop the check
        pass


def typed_intent(question: str) -> tuple[dict | None, str | None]:
    """The search a visitor typing this question gets (the plain-text parse). (intent, None) when it becomes a
    real search; (None, reason) when it falls back to a name search."""
    p = ask.parse(question, "ideas-check", trusted=True)
    if p.get("intent") in (None, "unknown", "plain"):
        return None, f"couldn't turn the question into a search ({p.get('intent')}: {p.get('reason') or p.get('how')})"
    return {k: v for k, v in p.items() if k not in ("how", "parse_ms")}, None


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


def _search_key(intent: dict) -> str:
    return json.dumps({k: v for k, v in intent.items() if v not in (None, "", [], False)}, sort_keys=True)


def check_and_store(proposed: list[dict], shown: list[str], want: int | None = None,
                    pool: dt.date | None = None, searches: set[str] | None = None) -> list[int]:
    """Validate and run proposed ideas (in parallel), store the ones that work (in `pool`, tonight's pool date),
    return their ids in proposal order. `searches` (search keys already in the pool) is updated in place."""
    seen = {_norm(q) for q in shown}
    same = searches if searches is not None else set()
    cands = []
    for idea in proposed:
        q = re.sub(r"\s+", " ", str(idea.get("question") or "")).strip()[:120]
        if not q or _norm(q) in seen:
            continue
        intent = ask.validate(str(idea.get("tool") or ""), idea.get("args"))
        k = _search_key(intent)
        if k in same:                    # the same search worded differently: one is enough
            continue
        seen.add(_norm(q))
        same.add(k)
        cands.append((q, intent))
    def check(c):
        # The question as typed must parse into a search (no name-search fallback), and that search must return
        # results; the parsed search is what gets stored, so typing the question and clicking it agree.
        q, _ = c
        typed, why = typed_intent(q)
        if not typed:
            reject(pool, q, why)
            return None
        if not works(typed):
            reject(pool, q, "the search returned no results", typed)
            return None
        return (q, typed)
    with ThreadPoolExecutor(max_workers=4) as ex:
        checked = list(ex.map(check, cands))
    keep = [c for c in checked if c][:want or None]
    ids = []
    if keep:
        with db.conn() as conn:
            with conn.transaction():
                for q, intent in keep:
                    ids.append(conn.execute("""INSERT INTO home_ideas (question, intent, pool) VALUES (%s, %s, %s)
                                               RETURNING id""", (q, json.dumps(intent), pool)).fetchone()["id"])
                conn.execute("DELETE FROM home_ideas WHERE created < now() - make_interval(days => %s)", (KEEP_DAYS,))
    return ids


FOCUS = [" Lean toward nonprofits, foundations, grants, vendors and galas.",
         " Lean toward universities, schools, coaches, payrolls and student loans.",
         " Lean toward campaign contributions, leaderboards and anything newer in the overview."]


def pool_date() -> dt.date:
    """Tonight's pool date: the date in US Eastern time (the job runs at midnight Eastern)."""
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/New_York")).date()


def refresh(status=log.info, size: int = POOL_SIZE) -> int:
    """Build tonight's pool: rounds of parallel model calls until `size` checked ideas are stored. Returns how many
    were stored (0 if another worker is already doing it)."""
    with psycopg.connect(DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"), autocommit=True,
                         application_name="np-ideas") as lock_conn:
        if not lock_conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
            return 0
        try:
            pool = pool_date()
            overview = schema_overview()
            status(f"ideas: overview of {overview.count(chr(10)) + 1} lines")
            with db.conn() as conn:
                conn.execute("DELETE FROM home_ideas WHERE pool = %s", (pool,))       # a rerun replaces the night
            shown: list[str] = []
            searches: set[str] = set()
            stored = 0
            for rnd in range(MAX_ROUNDS):
                need = size - stored
                if need <= 0:
                    break
                calls = CALLS_PER_ROUND if rnd == 0 else 1
                with ThreadPoolExecutor(max_workers=calls) as ex:
                    batches = list(ex.map(lambda k: propose(shown, ASK_PER_CALL if rnd == 0 else min(ASK_PER_CALL, need * 2),
                                                            overview=overview, focus=FOCUS[k % len(FOCUS)]),
                                          range(calls)))
                proposed = [i for b in batches for i in b]
                ids = check_and_store(proposed, shown, need, pool, searches)
                stored += len(ids)
                shown += [i["question"] for i in fetch(ids)]
                status(f"ideas: round {rnd + 1}: {len(proposed)} proposed, {len(ids)} kept, {stored} in the pool")
            return stored
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def _latest_pool() -> str:
    """SQL for the ideas a visitor can see: the latest pool; before the first nightly pool, recent ideas."""
    return """(pool = (SELECT max(pool) FROM home_ideas)
               OR (NOT EXISTS (SELECT 1 FROM home_ideas WHERE pool IS NOT NULL)
                   AND created > now() - make_interval(days => 7)))"""


def _pool_ids(exclude: list[int], k: int) -> list[int]:
    """k ideas at random from the latest pool, skipping those already shown."""
    try:
        with db.conn() as conn:
            rows = conn.execute(f"""SELECT id FROM home_ideas WHERE {_latest_pool()} AND id <> ALL(%s)
                                    ORDER BY random() LIMIT %s""", (exclude, k)).fetchall()
    except Exception:  # noqa: BLE001 - no table yet
        return []
    return [r["id"] for r in rows]


def first_ids() -> list[int]:
    return _pool_ids([], PER_PAGE)


def more_ids(seen: list[int]) -> list[int]:
    """Five more for a visitor who has seen `seen`, never repeating, up to MAX_TOTAL in all."""
    want = min(PER_PAGE, MAX_TOTAL - len(seen))
    return _pool_ids(seen, want) if want > 0 else []


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
    db.pool.open(wait=True)
    if sys.argv[1:] == ["refresh"]:
        print(f"stored {refresh(print)}", flush=True)
    elif sys.argv[1:] == ["overview"]:
        print(schema_overview())
