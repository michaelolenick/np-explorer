"""NTEE codes for every nonprofit (owner, 2026-11-05): the published code from the IRS Business Master File, an
inferred code from a small model for the rest, the NCCS taxonomy, FURP's own topic index, and the counts behind
/categories.

Tables (all rebuilt with swap_table except ntee_inferred, which accumulates):
  ntee_taxonomy        code, level (broad, major, code), parent, name, description, naics, effective_date.
                       The 3-character codes and the 26 major groups come from NCCS's lookup files; the 10 broad
                       categories (I to X) and the common codes from NCCS's NTEE history page (BROAD, COMMON below).
  ntee_activity_codes  the IRS's pre-1995 activity codes (BMF ACTIVITY field) with names and the NTEE codes NCCS
                       maps them to; an input to the model for organizations with no 990 text.
  ntee_inferred        one row per organization the model has seen: ein, ntee_code (NULL when it never gave a valid
                       code), confidence, model, inferred_at, tokens, cost, attempts, error. Resumable: a rerun
                       skips every ein here.
  ntee_test            the method test: organizations with a published code, the code hidden from the model.
  nonprofit_ntee       ein, ntee_code, ntee_source (published | inferred), confidence (NULL when published),
                       inferred_model, inferred_at, furp_category, furp_subcategory, ntee_raw (the BMF value).
                       furp_* come from research.org_fields (the 990 text index's topic:sense tags, built
                       2026-10-28/29); an organization with several tags gets its rarest (most specific) one.
  ntee_counts          view (ntee | furp), level, code, parent, name, orgs, published, inferred: the tree and the
                       per-category figures on /categories and in search.
  ntee_infer_cache     the Categories page's "describe it" lookups (app/categories.py), keyed by the words typed.

Commands:  .venv/bin/python -m loader.ntee taxonomy            download (if missing) and load the taxonomy
           .venv/bin/python -m loader.ntee test [N]            the method on N (500) organizations with published codes
           .venv/bin/python -m loader.ntee infer [--via anthropic|batch|openrouter] [--budget $] [--limit N] [--workers W]
           .venv/bin/python -m loader.ntee submit | collect   the Batches route in two steps (infer --via batch does both)
           .venv/bin/python -m loader.ntee build               nonprofit_ntee + ntee_counts (nightly, after the BMF)
           .venv/bin/python -m loader.ntee all                 taxonomy, build
The model: Claude Haiku 5.5 through Anthropic's Messages API (ANTHROPIC_API_KEY) or Message Batches API (half price), or
the same model through OpenRouter (OPENROUTER_API_KEY); no key is ever printed. Orgs go to
the model several per request (BATCH_TEXT for ones with 990 text, BATCH_PLAIN for BMF-only ones); a reply that is
not a valid 3-character code is retried once, alone, with that major group's code list; else the code is NULL and
the error logged. Spend is what OpenRouter reports per request (usage.cost), kept per organization.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from loader import db

RAW = Path(os.environ.get("NTEE_RAW", "/bulk/ntee"))
CODE_URL = "https://nccsdata.s3.amazonaws.com/lookups/bmf/latest/ntee_code.csv"
MAJOR_URL = "https://nccsdata.s3.amazonaws.com/lookups/bmf/latest/ntee_code_major_group.csv"
ACTIVITY_URL = "https://raw.githubusercontent.com/Nonprofit-Open-Data-Collective/irs-exempt-org-business-master-file/master/README.md"
TAXONOMY_SOURCE = ("NCCS (Urban Institute) NTEE code lookup, nccs.urban.org/nccs/datasets/ntee/, checked against the IRS list "
                   "each January; broad categories and common codes from urbaninstitute.github.io/nccs-legacy/ntee/ntee-history.html.")
# The ten broad categories and their major groups, as the NCCS NTEE history page lists them.
BROAD = [("I", "Arts, Culture, and Humanities", "A"), ("II", "Education", "B"), ("III", "Environment and Animals", "CD"),
         ("IV", "Health", "EFGH"), ("V", "Human Services", "IJKLMNOP"), ("VI", "International, Foreign Affairs", "Q"),
         ("VII", "Public, Societal Benefit", "RSTUVW"), ("VIII", "Religion Related", "X"),
         ("IX", "Mutual/Membership Benefit", "Y"), ("X", "Unknown, Unclassified", "Z")]
# Common codes: the same meaning in every major group (x01 is advocacy for that group's field, and so on).
COMMON = {"01": "Alliance/Advocacy Organizations", "02": "Management and Technical Assistance",
          "03": "Professional Societies/Associations", "05": "Research Institutes and/or Public Policy Analysis",
          "11": "Monetary Support - Single Organization", "12": "Monetary Support - Multiple Organizations",
          "19": "Nonmonetary Support Not Elsewhere Classified (N.E.C.)"}

# Where the model calls go (owner, 2026-11-05): "anthropic" (the Messages API, one request at a time), "batch" (the
# Message Batches API, half price, answers within a day) or "openrouter" (the first run went this way). The model is
# Haiku 5.5 either way; prices are Anthropic's list prices per million tokens, used to cost each organization.
VIA = os.environ.get("NTEE_VIA", "anthropic")
ANTHROPIC_MODEL = os.environ.get("NTEE_ANTHROPIC_MODEL", "claude-haiku-5-5")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
PRICES = {   # dollars per million tokens, Anthropic list prices (platform.claude.com/docs/en/about-claude/pricing, 2026-11-05)
    "claude-haiku-5-5": {"input_tokens": 0.10, "output_tokens": 0.50, "cache_creation_input_tokens": 0.125, "cache_read_input_tokens": 0.01},
    "claude-sonnet-5-5": {"input_tokens": 2.00, "output_tokens": 10.00, "cache_creation_input_tokens": 2.50, "cache_read_input_tokens": 0.10},
}
PRICE = PRICES["claude-haiku-5-5"]
BATCH_REQUESTS = 4000                    # requests per Message Batch (each carries the 23 KB system prompt; 256 MB cap)
MODEL = os.environ.get("NTEE_MODEL", "anthropic/claude-haiku-5.5")    # OpenRouter's cheapest Haiku, 2026-11-05: $0.10/M in, $0.50/M out
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
FULL_LIST = os.environ.get("NTEE_FULL_LIST", "1") == "1"   # send every code (cached) rather than the major groups alone
BATCH_TEXT, BATCH_PLAIN = 5, 20          # organizations per request: with 990 text / BMF record only
MISSION_CHARS, PROGRAM_CHARS, SCHED_O_CHARS = 400, 700, 300
CODE_RE = re.compile(r"^[A-Z][0-9A-Z]{2}$")

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"],
          "properties": {"r": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["i", "c", "p"],
              "properties": {"i": {"type": "integer"}, "c": {"type": "string"}, "p": {"type": "number"}}}}}}


# --- taxonomy --------------------------------------------------------------------------------------

def _download(url: str, dest: Path, refresh: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not refresh:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "furp.org loader (contact@furp.org)"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def _activity_rows(readme: Path):
    """The README's activity-code table: '001\t|\tChurch,synagogue, etc\t|\tX20 - X70'."""
    for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and re.fullmatch(r"[0-9]{3}", parts[0]) and parts[1]:
            yield parts[0], re.sub(r"\s+", " ", parts[1]), (parts[2] if len(parts) > 2 and parts[2] else None)


def taxonomy(refresh: bool = False) -> None:
    codes = _download(CODE_URL, RAW / "ntee_code.csv", refresh)
    majors = _download(MAJOR_URL, RAW / "ntee_code_major_group.csv", refresh)
    readme = _download(ACTIVITY_URL, RAW / "activity_codes_readme.md", refresh)
    rows = []
    for roman, name, letters in BROAD:
        rows.append((roman, "broad", None, name, f"Major groups {', '.join(letters)}", None, None))
    letter_broad = {ch: roman for roman, _, letters in BROAD for ch in letters}
    with open(majors, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ch = r["ntee_code_first_character"].strip().upper()
            rows.append((ch, "major", letter_broad.get(ch), r["ntee_code_major_group"].strip(), None, None,
                         _date(r.get("effective_date"))))
    n_codes = 0
    with open(codes, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = r["ntee_code"].strip().upper()
            if not CODE_RE.match(code):
                continue
            rows.append((code, "code", code[0], r["ntee_code_definition"].strip(),
                         (r.get("ntee_code_description") or "").strip() or None,
                         (r.get("naics_code") or "").strip() or None, _date(r.get("effective_date"))))
            n_codes += 1
    acts = list(_activity_rows(readme))
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS ntee_taxonomy_new")
        cur.execute("""CREATE TABLE ntee_taxonomy_new (code text NOT NULL, level text NOT NULL, parent text, name text NOT NULL,
                       description text, naics text, effective_date date, PRIMARY KEY (level, code))""")
        db.copy_rows(cur, "ntee_taxonomy_new", ["code", "level", "parent", "name", "description", "naics", "effective_date"], rows)
        cur.execute("CREATE INDEX ON ntee_taxonomy_new (parent)")
        db.swap_table(conn, "ntee_taxonomy")
        cur.execute("DROP TABLE IF EXISTS ntee_activity_codes_new")
        cur.execute("CREATE TABLE ntee_activity_codes_new (code text PRIMARY KEY, name text NOT NULL, ntee_hint text)")
        db.copy_rows(cur, "ntee_activity_codes_new", ["code", "name", "ntee_hint"], acts)
        db.swap_table(conn, "ntee_activity_codes")
        conn.commit()
    print(f"ntee taxonomy: {len(BROAD)} broad categories, {sum(1 for r in rows if r[1] == 'major')} major groups, "
          f"{n_codes:,} codes; {len(acts)} IRS activity codes")


def _date(s):
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"[0-9]{8}", s) else None


# --- the model --------------------------------------------------------------------------------------

_tax_cache: dict = {}


def valid_codes(conn) -> dict:
    """{'codes': {code: name}, 'majors': {letter: name}} from ntee_taxonomy (cached per process)."""
    if not _tax_cache:
        _tax_cache["codes"] = dict(conn.execute("SELECT code, name FROM ntee_taxonomy WHERE level = 'code'").fetchall())
        _tax_cache["majors"] = dict(conn.execute("SELECT code, name FROM ntee_taxonomy WHERE level = 'major' ORDER BY code").fetchall())
        _tax_cache["acts"] = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT code, name, ntee_hint FROM ntee_activity_codes").fetchall()}
    return _tax_cache


def system_prompt(majors: dict, codes: dict | None = None) -> str:
    """The instructions, the 26 major groups and (FULL_LIST) every code with its name, grouped by letter. The full list
    is about 8,000 tokens; OpenRouter caches it for Anthropic models (cache_control below), so a request pays a tenth
    of the price for it."""
    common = "; ".join(f"{k} {v}" for k, v in COMMON.items())
    if codes and FULL_LIST:
        by_letter: dict = {}
        for c, nm in sorted(codes.items()):
            by_letter.setdefault(c[0], []).append(f"{c} {nm}")
        groups = "\n".join(f"{k} {v}\n" + "\n".join(by_letter.get(k, [])) for k, v in majors.items())
        listing = "Every valid code, by major group:\n" + groups
    else:
        listing = "Major groups:\n" + "\n".join(f"{k} {v}" for k, v in majors.items())
    return ("You assign NTEE-CC codes (the National Taxonomy of Exempt Entities, NCCS core codes) to US tax-exempt "
            "organizations from their IRS records. A code is one major-group letter and two more characters, such as "
            "B82 (Scholarships) or P20 (Human Service Organizations). Pick the single most specific code that fits each "
            "organization's main purpose and activity, the way the IRS and NCCS code it: a church is X20 (X30 synagogue, "
            "X40 mosque, X50 Buddhist temple), a Lions or Rotary club S80, a fraternal lodge Y40 or Y42, a sports club or "
            "league N6x, a scholarship fund B82, a PTA or booster club B94, a volunteer fire company M24, a cemetery Y50, "
            "an employee benefit trust Y43, a homeowners association S20 or S22. If only the field is clear, use that "
            "group's general code (letter + 20). Reserve Z99 for records with nothing to go on.\n\n" + listing +
            "\n\nCommon codes (two-digit part, same meaning in every group; use them for support, advocacy, research "
            "and professional bodies within a field): " + common +
            "\n\nAnswer with JSON only: {\"r\":[{\"i\":<item number>,\"c\":\"<code>\",\"p\":<confidence 0 to 1>}, ...]}, "
            "one item per numbered organization, in order.")


def org_text(o: dict, acts: dict) -> tuple[str, bool]:
    """One organization's lines for the prompt, and whether it has 990 text."""
    lines = [f"Name: {o['name']}"]
    place = ", ".join(x for x in (o.get("city"), o.get("state")) if x)
    if place:
        lines.append(f"Place: {place}")
    sub = (o.get("subsection") or "").lstrip("0")
    if sub:
        lines.append(f"IRS subsection: 501(c)({sub})")
    if o.get("ruling_year"):
        lines.append(f"IRS ruling year: {o['ruling_year']}")
    a = o.get("activity") or ""
    labels = []
    for i in range(0, min(len(a), 9), 3):
        c = a[i:i + 3]
        if c and c != "000" and c in acts:
            name, hint = acts[c]
            labels.append(f"{name}" + (f" (NTEE {hint})" if hint else ""))
    if labels:
        lines.append("IRS activity codes (pre-1995 application): " + "; ".join(labels))
    has_text = False
    mission = (o.get("mission") or o.get("mission_text") or "").strip()
    if mission:
        lines.append("Mission (Form 990): " + _clip(mission, MISSION_CHARS)); has_text = True
    prog = (o.get("program_text") or "").strip()
    if prog:
        lines.append("Program services (Form 990 Part III): " + _clip(prog, PROGRAM_CHARS)); has_text = True
    so = (o.get("schedule_o_text") or "").strip()
    if so and not prog:                      # Schedule O is mostly expense lists; only worth sending without Part III text
        lines.append("Schedule O: " + _clip(so, SCHED_O_CHARS)); has_text = True
    return "\n".join(lines), has_text


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s)
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


def model_name() -> str:
    return MODEL if VIA == "openrouter" else ANTHROPIC_MODEL


def _price(usage: dict, batch: bool = False, model: str | None = None) -> float:
    """Dollars for one Anthropic usage block at list prices (half for a batch)."""
    prices = PRICES.get(model or ANTHROPIC_MODEL, PRICE)
    d = sum((usage.get(k) or 0) * v / 1e6 for k, v in prices.items())
    return d / 2 if batch else d


def _parse_text(content: str):
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", (content or "").strip())
    try:
        return json.loads(content)
    except ValueError:
        m = re.search(r"\{.*\}", content, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    return None


def anthropic_body(system: str, user: str, max_tokens: int, schema: dict | None = None, model: str | None = None) -> dict:
    """One Messages API request: the system prompt cached, thinking off (a lookup, not a puzzle), JSON by schema."""
    return {"model": model or ANTHROPIC_MODEL, "max_tokens": max_tokens, "thinking": {"type": "disabled"},
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "output_config": {"format": {"type": "json_schema", "schema": schema or SCHEMA}},
            "messages": [{"role": "user", "content": user}]}


def anthropic_headers() -> dict:
    """The categorization key (owner, 2026-11-05: CATEGORIZE_API_KEY in .env, for this work and nothing else), else the
    site's ANTHROPIC_API_KEY. Never printed or logged."""
    key = os.environ.get("CATEGORIZE_API_KEY") or os.environ["ANTHROPIC_API_KEY"]
    return {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def anthropic_answer(message: dict) -> tuple[dict | None, dict, str | None]:
    """(parsed JSON, usage with cost, error) from one Messages API response body."""
    usage = dict(message.get("usage") or {})
    usage["cost"] = _price(usage, model=message.get("model"))
    usage["cached"] = usage.get("cache_read_input_tokens") or 0
    usage["prompt_tokens"] = (usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) + usage["cached"]
    usage["completion_tokens"] = usage.get("output_tokens") or 0
    if message.get("stop_reason") == "refusal":
        return None, usage, "refusal"
    text = "".join(b.get("text") or "" for b in (message.get("content") or []) if b.get("type") == "text")
    if not text:
        return None, usage, "empty content (" + str(message.get("stop_reason")) + ")"
    parsed = _parse_text(text)
    return parsed, usage, None if parsed is not None else "not JSON"


def _post_anthropic(system: str, user: str, max_tokens: int, schema: dict | None = None, model: str | None = None) -> tuple[dict | None, dict, str | None]:
    import httpx
    body = anthropic_body(system, user, max_tokens, schema, model)
    for attempt in range(4):
        try:
            r = httpx.post(ANTHROPIC_API, timeout=120, headers=anthropic_headers(), json=body)
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                return None, {}, f"request failed: {type(e).__name__}"
            time.sleep(2 + 3 * attempt)
            continue
        if r.status_code in (408, 409, 429, 500, 502, 503, 529):
            time.sleep(float(r.headers.get("retry-after") or 3 + 5 * attempt))
            continue
        if r.status_code != 200:
            return None, {}, f"HTTP {r.status_code}"     # status only: never the body
        return anthropic_answer(r.json())
    return None, {}, "rate limited"


def _post(system: str, user: str, max_tokens: int) -> tuple[dict | None, dict, str | None]:
    """One model request by VIA: (parsed JSON or None, usage with cost, error). Never prints a key or a body."""
    return _post_openrouter(system, user, max_tokens) if VIA == "openrouter" else _post_anthropic(system, user, max_tokens)


def _post_openrouter(system: str, user: str, max_tokens: int) -> tuple[dict | None, dict, str | None]:
    """One OpenRouter request: (parsed JSON or None, usage, error). Never prints the key or the body on failure."""
    import httpx
    body = {"model": MODEL, "temperature": 0, "max_tokens": max_tokens, "usage": {"include": True},
            "reasoning": {"enabled": False},        # Haiku 5.5 otherwise spends the whole output on hidden reasoning
            "response_format": {"type": "json_schema", "json_schema": {"name": "ntee", "strict": True, "schema": SCHEMA}},
            "messages": [{"role": "system", "content": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]},
                         {"role": "user", "content": user}]}
    for attempt in range(3):
        try:
            r = httpx.post(OR_URL, timeout=120, headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                                       "HTTP-Referer": "https://furp.org", "X-Title": "furp.org NTEE"}, json=body)
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return None, {}, f"request failed: {type(e).__name__}"
            time.sleep(2 + 3 * attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(3 + 5 * attempt)
            continue
        if r.status_code != 200:
            return None, {}, f"HTTP {r.status_code}"
        data = r.json()
        usage = data.get("usage") or {}
        usage["cached"] = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None, usage, "no content"
        if not content:
            return None, usage, "empty content (" + str(data["choices"][0].get("finish_reason")) + ")"
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            return json.loads(content), usage, None
        except ValueError:
            m = re.search(r"\{.*\}", content, re.S)
            if m:
                try:
                    return json.loads(m.group(0)), usage, None
                except ValueError:
                    pass
            return None, usage, "not JSON"
    return None, {}, "rate limited"


def classify(orgs: list[dict], tax: dict) -> list[dict]:
    """One batch: returns per org {ein, code, conf, cost, prompt_tokens, completion_tokens, attempts, error}."""
    sysp = system_prompt(tax["majors"], tax["codes"])
    user = "\n\n".join(f"[{n}]\n{org_text(o, tax['acts'])[0]}" for n, o in enumerate(orgs, 1))
    parsed, usage, err = _post(sysp, user, 24 * len(orgs) + 40)
    out = answers(orgs, parsed, usage, err, tax)
    retry_invalid(orgs, out, tax, sysp)
    return list(out.values())


def answers(orgs: list[dict], parsed, usage: dict, err: str | None, tax: dict) -> dict:
    """The model's reply for a batch of organizations, validated against the taxonomy: {ein: record}."""
    codes = tax["codes"]
    cost = float(usage.get("cost") or 0.0)
    pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    out = {o["ein"]: {"ein": o["ein"], "code": None, "conf": None, "cost": cost / len(orgs), "pt": pt / len(orgs),
                      "ct": ct / len(orgs), "cached": int(usage.get("cached") or 0) / len(orgs), "attempts": 1, "error": err, "raw": None}
           for o in orgs}
    got = {}
    if parsed and isinstance(parsed.get("r"), list):
        for item in parsed["r"]:
            if isinstance(item, dict) and isinstance(item.get("i"), int):
                got[item["i"]] = item
    for n, o in enumerate(orgs, 1):
        a = got.get(n)
        rec = out[o["ein"]]
        if a is None:
            rec["error"] = rec["error"] or "no answer"
        else:
            code = str(a.get("c") or "").strip().upper()
            rec["raw"] = code
            if code in codes:
                rec["code"], rec["conf"], rec["error"] = code, _conf(a.get("p")), None
            else:
                rec["error"] = f"invalid code {code or '(empty)'}"
    return out


def retry_invalid(orgs: list[dict], out: dict, tax: dict, sysp: str, model: str | None = None) -> None:
    """Retry the invalid or missing ones once, alone, with the code list for the letter the model chose."""
    codes, majors, acts = tax["codes"], tax["majors"], tax["acts"]
    for o in orgs:
        rec = out[o["ein"]]
        if rec["code"] is not None or rec["error"] in ("HTTP 401", "HTTP 402", "rate limited", "refusal"):
            continue
        letter = (rec["raw"] or "")[:1]
        subset = {c: nm for c, nm in codes.items() if c[0] == letter} if letter in majors else codes
        listing = "\n".join(f"{c} {nm}" for c, nm in sorted(subset.items()))
        user1 = (f"[1]\n{org_text(o, acts)[0]}\n\nValid codes" + (f" in group {letter} ({majors[letter]})" if letter in majors else "")
                 + " (answer with one of these exactly):\n" + listing)
        parsed, usage, err = _post(sysp, user1, 60) if not model else _post_anthropic(sysp, user1, 60, None, model)
        rec["attempts"] = 2
        rec["cost"] += float(usage.get("cost") or 0.0)
        rec["pt"] += int(usage.get("prompt_tokens") or 0)
        rec["ct"] += int(usage.get("completion_tokens") or 0)
        a = (parsed or {}).get("r", [{}])[0] if parsed and isinstance(parsed.get("r"), list) and parsed["r"] else {}
        code = str((a or {}).get("c") or "").strip().upper()
        if code in codes:
            rec["code"], rec["conf"], rec["error"] = code, _conf((a or {}).get("p")), None
        else:
            rec["error"] = err or f"invalid code after retry: {code or '(empty)'}"


def _conf(p):
    try:
        return max(0.0, min(1.0, round(float(p), 3)))
    except (TypeError, ValueError):
        return None


# --- candidates and the runs ----------------------------------------------------------------------

CAND_SQL = """
    SELECT o.ein, o.name, o.city, o.state, o.subsection, o.ruling_year, d.activity, p.mission, t.mission_text,
           t.program_text, t.schedule_o_text, (o.latest_filing_year IS NOT NULL) AS filer, o.ntee
    FROM organizations o
    LEFT JOIN irs_bmf_detail d ON d.ein = o.ein
    LEFT JOIN org_profile p ON p.ein = o.ein
    LEFT JOIN research.org_text t ON t.ein = o.ein
    WHERE {where}
    ORDER BY {order}"""


def _ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS ntee_inferred (
        ein text PRIMARY KEY, ntee_code text, confidence real, model text, inferred_at timestamptz NOT NULL DEFAULT now(),
        prompt_tokens integer, completion_tokens integer, cost double precision, attempts smallint, error text, raw text, filer boolean)""")
    conn.execute("CREATE INDEX IF NOT EXISTS ntee_inferred_code ON ntee_inferred (ntee_code)")
    conn.execute("""CREATE TABLE IF NOT EXISTS ntee_test (
        ein text PRIMARY KEY, published text, ntee_code text, confidence real, model text, tested_at timestamptz NOT NULL DEFAULT now(),
        prompt_tokens integer, completion_tokens integer, cost double precision, attempts smallint, error text, raw text, filer boolean)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ntee_batches (
        id text PRIMARY KEY, created timestamptz NOT NULL DEFAULT now(), status text NOT NULL DEFAULT 'sent', requests integer,
        orgs integer, ended timestamptz, cost double precision, note text)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ntee_batch_eins (
        ein text PRIMARY KEY, batch_id text NOT NULL, custom_id text NOT NULL, pos smallint NOT NULL, filer boolean)""")
    conn.execute("CREATE INDEX IF NOT EXISTS ntee_batch_eins_batch ON ntee_batch_eins (batch_id, custom_id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS ntee_infer_cache (
        q text PRIMARY KEY, result jsonb NOT NULL, model text, cost double precision, created timestamptz NOT NULL DEFAULT now())""")
    conn.commit()


def _write(conn, table: str, recs: list[dict], extra: dict) -> None:
    with conn.cursor() as cur:
        for r in recs:
            cur.execute(f"""INSERT INTO {table} (ein, {'published, ' if table == 'ntee_test' else ''}ntee_code, confidence, model,
                            prompt_tokens, completion_tokens, cost, attempts, error, raw, filer)
                            VALUES (%s, {'%s, ' if table == 'ntee_test' else ''}%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ein) DO UPDATE SET ntee_code = EXCLUDED.ntee_code, confidence = EXCLUDED.confidence,
                              model = EXCLUDED.model, prompt_tokens = EXCLUDED.prompt_tokens, completion_tokens = EXCLUDED.completion_tokens,
                              cost = EXCLUDED.cost, attempts = EXCLUDED.attempts, error = EXCLUDED.error, raw = EXCLUDED.raw, filer = EXCLUDED.filer""",
                        (r["ein"], *([extra[r["ein"]]["published"]] if table == "ntee_test" else []), r["code"], r["conf"], model_name(),
                         round(r["pt"]), round(r["ct"]), r["cost"], r["attempts"], r["error"], r["raw"], extra[r["ein"]]["filer"]))
    conn.commit()


class Runner:
    """Streams candidates in batches to the model with W threads, writing each batch's answers as they come."""

    def __init__(self, table: str, workers: int, budget: float | None, status=print):
        self.table, self.workers, self.budget, self.status = table, workers, budget, status
        self.lock = threading.Lock()
        self.done = self.ok = self.retried = 0
        self.spent = 0.0
        self.pt = self.ct = self.cached = 0
        self.t0 = time.monotonic()
        self.stop = False

    def run(self, where: str, order: str, limit: int | None) -> None:
        with db.connect() as conn:
            _ensure_tables(conn)
            tax = valid_codes(conn)
            wconn = db.connect()
            try:
                with ThreadPoolExecutor(max_workers=self.workers) as pool, \
                        conn.cursor(name="ntee_cand", row_factory=_dict_row) as cur:
                    cur.itersize = 2000
                    cur.execute(CAND_SQL.format(where=where, order=order) + (f" LIMIT {int(limit)}" if limit else ""))
                    pending = set()
                    text_batch, plain_batch = [], []
                    last_report = time.monotonic()

                    def flush(batch):
                        if batch:
                            pending.add(pool.submit(classify, list(batch), tax))
                            batch.clear()

                    def drain(block_until: int):
                        nonlocal last_report
                        while len(pending) > block_until:
                            done_now = [f for f in pending if f.done()]
                            if not done_now:
                                time.sleep(0.2)
                                continue
                            for f in done_now:
                                pending.discard(f)
                                recs = f.result()
                                _write(wconn, self.table, recs, self.meta)
                                with self.lock:
                                    self.done += len(recs)
                                    self.ok += sum(1 for r in recs if r["code"])
                                    self.retried += sum(1 for r in recs if r["attempts"] > 1)
                                    self.spent += sum(r["cost"] for r in recs)
                                    self.pt += sum(r["pt"] for r in recs); self.ct += sum(r["ct"] for r in recs)
                                    self.cached += sum(r.get("cached", 0) for r in recs)
                            if time.monotonic() - last_report > 60:
                                self.report(); last_report = time.monotonic()
                            if self.budget is not None and self.spent >= self.budget:
                                self.stop = True

                    self.meta = {}
                    for row in cur:
                        if self.stop:
                            break
                        self.meta[row["ein"]] = {"filer": row["filer"], "published": (row.get("ntee") or "")[:3].upper() or None}
                        row = dict(row)
                        if self.table == "ntee_test":
                            row["ntee"] = None
                        _, has_text = org_text(row, tax["acts"])
                        (text_batch if has_text else plain_batch).append(row)
                        if len(text_batch) >= BATCH_TEXT:
                            flush(text_batch)
                        if len(plain_batch) >= BATCH_PLAIN:
                            flush(plain_batch)
                        drain(self.workers * 2)
                    if not self.stop:
                        flush(text_batch); flush(plain_batch)
                    drain(0)
            finally:
                wconn.close()
        self.report(final=True)

    def report(self, final: bool = False) -> None:
        el = time.monotonic() - self.t0
        rate = self.done / el * 3600 if el else 0
        self.status(f"ntee {self.table}: {self.done:,} orgs ({self.ok:,} coded, {self.retried:,} retried), "
                    f"${self.spent:.2f} spent (${self.spent / self.done * 1000 if self.done else 0:.3f} per 1,000 orgs), "
                    f"{self.pt:,.0f} in ({self.cached:,.0f} cached) / {self.ct:,.0f} out tokens, {rate:,.0f} orgs/hour"
                    + (", stopped at the budget" if self.stop else "") + (" [done]" if final else ""))


def _dict_row(cursor):
    cols = [c.name for c in cursor.description]
    return lambda values: dict(zip(cols, values))


def test(n: int, workers: int) -> None:
    """The method on n organizations with a published code (half with 990 text, half BMF-only), the code hidden."""
    half = n // 2
    with db.connect() as conn:
        _ensure_tables(conn)
        conn.execute("DELETE FROM ntee_test")
        conn.commit()
        conn.execute("SET statement_timeout = '600s'")
        eins = [r[0] for r in conn.execute("""(SELECT ein FROM organizations WHERE ntee IS NOT NULL AND latest_filing_year IS NOT NULL
                                               AND length(ntee) >= 3 ORDER BY md5(ein) LIMIT %s)
                                              UNION ALL
                                              (SELECT ein FROM organizations WHERE ntee IS NOT NULL AND latest_filing_year IS NULL
                                               AND length(ntee) >= 3 ORDER BY md5(ein) LIMIT %s)""", (half, n - half)).fetchall()]
    where = "o.ein = ANY(ARRAY[" + ",".join(f"'{e}'" for e in eins) + "])"
    Runner("ntee_test", workers, None).run(where, "o.ein", None)
    with db.connect() as conn:
        for label, cond in (("all", "true"), ("with 990 text", "filer"), ("BMF record only", "NOT filer")):
            r = conn.execute(f"""SELECT count(*), count(ntee_code), count(*) FILTER (WHERE left(published, 1) = left(ntee_code, 1)),
                                        count(*) FILTER (WHERE published = ntee_code), avg(confidence), sum(cost)
                                 FROM ntee_test WHERE {cond}""").fetchone()
            tot, coded, letter, full, conf, cost = r
            print(f"test {label}: {tot} orgs, {coded} coded; letter match {letter}/{tot} ({letter / tot * 100 if tot else 0:.1f}%), "
                  f"3-character match {full}/{tot} ({full / tot * 100 if tot else 0:.1f}%); mean confidence {conf or 0:.2f}; ${cost or 0:.3f}")
        print("test: published codes not in the taxonomy:",
              conn.execute("SELECT count(*) FROM ntee_test t WHERE NOT EXISTS (SELECT 1 FROM ntee_taxonomy x WHERE x.level = 'code' AND x.code = t.published)").fetchone()[0])
        print("test: errors:", conn.execute("SELECT error, count(*) FROM ntee_test WHERE error IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall())


CAND_ORDER = "(o.latest_filing_year IS NOT NULL) DESC, o.latest_total_revenue DESC NULLS LAST, o.ein"


def _cand_where(retry_null: bool) -> str:
    return ("o.ntee IS NULL AND NOT EXISTS (SELECT 1 FROM ntee_inferred i WHERE i.ein = o.ein"
            + (" AND i.ntee_code IS NOT NULL" if retry_null else "") + ")"
            " AND NOT EXISTS (SELECT 1 FROM ntee_batch_eins b WHERE b.ein = o.ein)")


def infer(budget: float | None, limit: int | None, workers: int, retry_null: bool = False) -> None:
    if VIA == "batch":
        submit(limit, retry_null)
        collect(workers)
        return
    Runner("ntee_inferred", workers, budget).run(_cand_where(retry_null), CAND_ORDER, limit)


# --- the Message Batches API --------------------------------------------------------------------

def _batch_rows(cur):
    for row in cur:
        yield dict(row)


def submit(limit: int | None, retry_null: bool = False, per_batch: int = BATCH_REQUESTS) -> list[str]:
    """Send every remaining organization to the Message Batches API, BATCH_REQUESTS requests per batch (each request
    BATCH_TEXT or BATCH_PLAIN organizations). Each organization is recorded in ntee_batch_eins with its batch and
    request, so collect() can match answers back and a rerun never sends it twice."""
    import httpx
    ids = []
    with db.connect() as conn:
        _ensure_tables(conn)
        tax = valid_codes(conn)
        sysp = system_prompt(tax["majors"], tax["codes"])
        wconn = db.connect()
        try:
            with conn.cursor(name="ntee_batch_cand", row_factory=_dict_row) as cur:
                cur.itersize = 2000
                cur.execute(CAND_SQL.format(where=_cand_where(retry_null), order=CAND_ORDER) + (f" LIMIT {int(limit)}" if limit else ""))
                text_batch, plain_batch, reqs, eins = [], [], [], []

                def add(batch):
                    cid = f"r{len(reqs)}"
                    user = "\n\n".join(f"[{n}]\n{org_text(o, tax['acts'])[0]}" for n, o in enumerate(batch, 1))
                    reqs.append({"custom_id": cid, "params": anthropic_body(sysp, user, 24 * len(batch) + 40)})
                    eins.extend((o["ein"], cid, n, o["filer"]) for n, o in enumerate(batch))
                    batch.clear()

                def send():
                    if not reqs:
                        return
                    r = httpx.post(ANTHROPIC_API + "/batches", timeout=600, headers=anthropic_headers(), json={"requests": reqs})
                    if r.status_code != 200:
                        raise SystemExit(f"batch create failed: HTTP {r.status_code}")
                    bid = r.json()["id"]
                    with wconn.cursor() as c:
                        c.execute("INSERT INTO ntee_batches (id, requests, orgs) VALUES (%s, %s, %s)", (bid, len(reqs), len(eins)))
                        db.copy_rows(c, "ntee_batch_eins", ["ein", "custom_id", "pos", "filer", "batch_id"], [(*e, bid) for e in eins])
                    wconn.commit()
                    ids.append(bid)
                    print(f"ntee batch {bid}: {len(reqs):,} requests, {len(eins):,} orgs sent")
                    reqs.clear(); eins.clear()

                for row in _batch_rows(cur):
                    (text_batch if org_text(row, tax["acts"])[1] else plain_batch).append(row)
                    if len(text_batch) >= BATCH_TEXT:
                        add(text_batch)
                    if len(plain_batch) >= BATCH_PLAIN:
                        add(plain_batch)
                    if len(reqs) >= per_batch:
                        send()
                add(text_batch); add(plain_batch)
                send()
        finally:
            wconn.close()
    print(f"ntee: {len(ids)} batches submitted")
    return ids


def collect(workers: int = 8, poll: int = 120) -> None:
    """Wait for every unfinished batch, write its answers to ntee_inferred (invalid codes retried one at a time
    through the Messages API), and report spend. Safe to rerun: finished batches are marked in ntee_batches."""
    import httpx
    with db.connect() as conn:
        _ensure_tables(conn)
        tax = valid_codes(conn)
        sysp = system_prompt(tax["majors"], tax["codes"])
        total_cost = 0.0
        last = time.time()
        while True:
            pending = [r[0] for r in conn.execute("SELECT id FROM ntee_batches WHERE status = 'sent' ORDER BY created").fetchall()]
            if not pending:
                break
            for bid in pending:
                b = httpx.get(f"{ANTHROPIC_API}/batches/{bid}", timeout=60, headers=anthropic_headers()).json()
                if b.get("processing_status") != "ended":
                    continue
                cost = _collect_one(conn, bid, b, tax, sysp, workers)
                total_cost += cost
            if time.time() - last > 600:
                n = conn.execute("SELECT count(*) FROM ntee_batches WHERE status = 'sent'").fetchone()[0]
                print(f"ntee collect: {n} batches still running; ${total_cost:.2f} collected so far")
                last = time.time()
            if conn.execute("SELECT count(*) FROM ntee_batches WHERE status = 'sent'").fetchone()[0]:
                time.sleep(poll)
        tot = conn.execute("SELECT count(*), count(ntee_code), round(sum(cost)::numeric, 2) FROM ntee_inferred").fetchone()
        print(f"ntee collect: done; ntee_inferred has {tot[0]:,} orgs ({tot[1]:,} coded), ${tot[2]} spent in all")


def _collect_one(conn, bid: str, b: dict, tax: dict, sysp: str, workers: int) -> float:
    """One ended batch: answers matched to organizations by custom_id, validated, retried, written."""
    import httpx
    members = {}
    for ein, cid, pos, filer in conn.execute("SELECT ein, custom_id, pos, filer FROM ntee_batch_eins WHERE batch_id = %s ORDER BY custom_id, pos", (bid,)).fetchall():
        members.setdefault(cid, []).append({"ein": ein, "filer": filer})
    recs, cost, seen = [], 0.0, set()
    with httpx.stream("GET", b["results_url"], timeout=900, headers=anthropic_headers()) as rr:
        for line in rr.iter_lines():
            if not line.strip():
                continue
            row = json.loads(line)
            orgs = members.get(row.get("custom_id"))
            if not orgs:
                continue
            seen.add(row["custom_id"])
            res = row.get("result") or {}
            if res.get("type") == "succeeded":
                parsed, usage, err = anthropic_answer(res["message"])
                usage["cost"] = _price(res["message"].get("usage") or {}, batch=True)
            else:
                parsed, usage, err = None, {}, f"batch {res.get('type')}"
            out = answers(orgs, parsed, usage, err, tax)
            cost += float(usage.get("cost") or 0.0)
            recs.extend(out.values())
    for cid, orgs in members.items():          # requests with no result line at all
        if cid not in seen:
            recs.extend(answers(orgs, None, {}, "no result", tax).values())
    # The invalid ones: fetch their records and retry through the Messages API, a few at a time.
    bad = [r for r in recs if r["code"] is None and r["error"] not in ("refusal",)]
    if bad:
        eins = [r["ein"] for r in bad]
        rows = {row["ein"]: dict(row) for row in conn.cursor(row_factory=_dict_row).execute(
            CAND_SQL.format(where="o.ein = ANY(%s)", order="o.ein"), (eins,)).fetchall()}
        by_ein = {r["ein"]: r for r in bad}

        def one(ein):
            if ein in rows:
                retry_invalid([rows[ein]], {ein: by_ein[ein]}, tax, sysp)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, eins))
        cost += sum(r["cost"] for r in bad)
    meta = {o["ein"]: {"filer": o["filer"], "published": None} for orgs in members.values() for o in orgs}
    _write(conn, "ntee_inferred", recs, meta)
    with conn.cursor() as c:
        c.execute("DELETE FROM ntee_batch_eins WHERE batch_id = %s", (bid,))
        c.execute("UPDATE ntee_batches SET status = 'done', ended = now(), cost = %s, note = %s WHERE id = %s",
                  (cost, json.dumps(b.get("request_counts") or {}), bid))
    conn.commit()
    coded = sum(1 for r in recs if r["code"])
    print(f"ntee batch {bid}: {len(recs):,} orgs, {coded:,} coded, {len(bad):,} retried, ${cost:.2f} ({b.get('request_counts')})")
    return cost


# --- nonprofit_ntee and the counts ------------------------------------------------------------------

def build() -> None:
    with db.connect() as conn, conn.cursor() as cur:
        _ensure_tables(conn)
        cur.execute("SET statement_timeout = '3600s'")
        cur.execute("DROP TABLE IF EXISTS nonprofit_ntee_new")
        cur.execute("""CREATE TABLE nonprofit_ntee_new AS
            WITH furp AS (
                SELECT DISTINCT ON (f.ein) f.ein, split_part(f.field, ':', 1) AS furp_category,
                       nullif(split_part(f.field, ':', 2), '') AS furp_subcategory
                FROM research.org_fields f JOIN (SELECT field, count(*) AS n FROM research.org_fields GROUP BY 1) c USING (field)
                ORDER BY f.ein, c.n, f.field),
            pub AS (
                SELECT o.ein, upper(left(o.ntee, 3)) AS ntee_code, o.ntee AS ntee_raw FROM organizations o
                WHERE o.ntee IS NOT NULL AND length(o.ntee) >= 3),
            inf AS (
                SELECT i.ein, i.ntee_code, i.confidence, i.model, i.inferred_at FROM ntee_inferred i
                WHERE i.ntee_code IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pub WHERE pub.ein = i.ein))
            SELECT x.ein, x.ntee_code, x.ntee_source, x.confidence, x.inferred_model, x.inferred_at,
                   f.furp_category, f.furp_subcategory, x.ntee_raw
            FROM (SELECT ein, ntee_code, 'published' AS ntee_source, NULL::real AS confidence, NULL::text AS inferred_model,
                         NULL::timestamptz AS inferred_at, ntee_raw FROM pub
                  UNION ALL
                  SELECT ein, ntee_code, 'inferred', confidence, model, inferred_at, NULL FROM inf) x
            LEFT JOIN furp f USING (ein)""")
        cur.execute("ALTER TABLE nonprofit_ntee_new ADD PRIMARY KEY (ein)")
        cur.execute("CREATE INDEX ON nonprofit_ntee_new (ntee_code)")
        cur.execute("CREATE INDEX ON nonprofit_ntee_new (left(ntee_code, 1))")
        cur.execute("CREATE INDEX ON nonprofit_ntee_new (furp_category, furp_subcategory)")
        db.swap_table(conn, "nonprofit_ntee")
        conn.commit()
        n, pub, inf = cur.execute("SELECT count(*), count(*) FILTER (WHERE ntee_source = 'published'), count(*) FILTER (WHERE ntee_source = 'inferred') FROM nonprofit_ntee").fetchone()
        print(f"nonprofit_ntee: {n:,} organizations ({pub:,} published, {inf:,} inferred)")
    counts()


def counts() -> None:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = '3600s'")
        cur.execute("DROP TABLE IF EXISTS ntee_counts_new")
        cur.execute("""CREATE TABLE ntee_counts_new AS
            WITH per_code AS (
                SELECT ntee_code AS code, count(*) AS orgs, count(*) FILTER (WHERE ntee_source = 'published') AS published,
                       count(*) FILTER (WHERE ntee_source = 'inferred') AS inferred FROM nonprofit_ntee GROUP BY 1),
            per_major AS (SELECT left(code, 1) AS code, sum(orgs) AS orgs, sum(published) AS published, sum(inferred) AS inferred FROM per_code GROUP BY 1)
            SELECT 'ntee' AS view, t.level, t.code, t.parent, t.name,
                   coalesce(CASE t.level WHEN 'code' THEN c.orgs WHEN 'major' THEN m.orgs
                            WHEN 'broad' THEN (SELECT sum(orgs) FROM per_major pm JOIN ntee_taxonomy x ON x.level = 'major' AND x.code = pm.code WHERE x.parent = t.code) END, 0)::bigint AS orgs,
                   coalesce(CASE t.level WHEN 'code' THEN c.published WHEN 'major' THEN m.published
                            WHEN 'broad' THEN (SELECT sum(published) FROM per_major pm JOIN ntee_taxonomy x ON x.level = 'major' AND x.code = pm.code WHERE x.parent = t.code) END, 0)::bigint AS published,
                   coalesce(CASE t.level WHEN 'code' THEN c.inferred WHEN 'major' THEN m.inferred
                            WHEN 'broad' THEN (SELECT sum(inferred) FROM per_major pm JOIN ntee_taxonomy x ON x.level = 'major' AND x.code = pm.code WHERE x.parent = t.code) END, 0)::bigint AS inferred
            FROM ntee_taxonomy t LEFT JOIN per_code c ON t.level = 'code' AND c.code = t.code
            LEFT JOIN per_major m ON t.level = 'major' AND m.code = t.code
            UNION ALL
            SELECT 'furp', 'topic', split_part(field, ':', 1), NULL, split_part(field, ':', 1), count(DISTINCT f.ein),
                   count(DISTINCT f.ein) FILTER (WHERE n.ntee_source = 'published'), count(DISTINCT f.ein) FILTER (WHERE n.ntee_source = 'inferred')
            FROM research.org_fields f LEFT JOIN nonprofit_ntee n ON n.ein = f.ein GROUP BY 3
            UNION ALL
            SELECT 'furp', 'sense', field, split_part(field, ':', 1), nullif(split_part(field, ':', 2), ''), count(DISTINCT f.ein),
                   count(DISTINCT f.ein) FILTER (WHERE n.ntee_source = 'published'), count(DISTINCT f.ein) FILTER (WHERE n.ntee_source = 'inferred')
            FROM research.org_fields f LEFT JOIN nonprofit_ntee n ON n.ein = f.ein WHERE f.field LIKE '%:%' GROUP BY 3, 4, 5""")
        cur.execute("ALTER TABLE ntee_counts_new ADD PRIMARY KEY (view, level, code)")
        db.swap_table(conn, "ntee_counts")
        conn.commit()
        print("ntee_counts:", cur.execute("SELECT view, level, count(*), sum(orgs) FROM ntee_counts GROUP BY 1, 2 ORDER BY 1, 2").fetchall())
        print("published codes not in the taxonomy:",
              cur.execute("""SELECT count(*), count(DISTINCT ntee_code) FROM nonprofit_ntee n WHERE ntee_source = 'published'
                             AND NOT EXISTS (SELECT 1 FROM ntee_taxonomy t WHERE t.level = 'code' AND t.code = n.ntee_code)""").fetchone())


def main(argv=None) -> None:
    global VIA
    ap = argparse.ArgumentParser()
    ap.add_argument("commands", nargs="+")
    ap.add_argument("--budget", type=float, default=None, help="stop the inference run at this many dollars (OpenRouter's reported cost)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--retry-null", action="store_true", help="also redo organizations the model never coded")
    ap.add_argument("--via", choices=("anthropic", "batch", "openrouter"), default=None, help=f"where the calls go (default {VIA})")
    a = ap.parse_args(argv)
    if a.via:
        VIA = a.via
    cmds = list(a.commands)
    i = 0
    while i < len(cmds):
        c = cmds[i]
        if c == "taxonomy":
            taxonomy(a.refresh)
        elif c == "test":
            n = int(cmds[i + 1]) if i + 1 < len(cmds) and cmds[i + 1].isdigit() else 500
            i += 1 if i + 1 < len(cmds) and cmds[i + 1].isdigit() else 0
            test(n, a.workers)
        elif c == "infer":
            infer(a.budget, a.limit, a.workers, a.retry_null)
        elif c == "submit":
            VIA = "batch"; submit(a.limit, a.retry_null)
        elif c == "collect":
            VIA = "batch"; collect(a.workers)
        elif c == "build":
            build()
        elif c == "counts":
            counts()
        elif c == "all":
            taxonomy(a.refresh); build()
        else:
            sys.exit(f"unknown command {c}")
        i += 1


if __name__ == "__main__":
    main()
