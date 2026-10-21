"""A short plain-English answer above each plain-text search result.

After a search runs, its result rows (trimmed to what matters) go to a fast, inexpensive model (ask.MODEL), which
writes two or three sentences that answer the question using only names and numbers from those rows: the direct
answer first, then one thing that stands out. Every number in the answer is checked against the rows; an answer
with a number that isn't there is thrown away (no answer beats a wrong one). Names are linked to their pages.

Answers are cached in nl_answers by the search's static URL, so a repeat visit is instant. The results page shows a
cached answer at once; otherwise static/site.js fetches it from /ask/answer after the page has loaded.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import html
import json
import logging
import os
import re

import httpx

from app import ask, db

log = logging.getLogger("np.answer")
MAX_ROWS = 20
MAX_CHARS = 14000
CACHE_DAYS = 7
SKIP_KEYS = {"subject_norm", "name_norm", "sound_tsv", "name_tsv", "evidence", "link_evidence", "xml_path", "mission",
             "lines", "detail", "copy", "notes"}

SYSTEM = """You write the short answer shown above a table of search results on furp.org, a public data explorer \
(nonprofit tax returns, public payrolls, federal data). You get the question and DATA: the rows of the results.

Rules:
- Two or three sentences, plain text. First sentence: the direct answer to the question. Then one sentence on what \
stands out in the rows (the largest, an outlier, a pattern).
- Rows are in the order the page shows them (usually ranked, largest first). Before writing, check which row \
really has the largest or smallest value you mention; never contradict yourself.
- Use only names and numbers that appear in DATA. Do not add facts, context or explanations from outside DATA, and \
do not guess. Do not calculate new totals, averages or percentages.
- Write names exactly as they appear in DATA (you may fix ALL CAPS to normal capitalization only if you keep every \
word). Write money with a dollar sign; round large amounts to millions or billions with one decimal \
("$4.6 billion").
- Neutral wording: no claims of wrongdoing. No em dashes.
- Never mention "DATA", "rows", "the table" or "the results"; just state the facts ("Chicago has ..."). Do not use \
markdown.
- If DATA has no rows, reply with exactly: EMPTY"""


def _plain(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return v


def _url(r: dict) -> str | None:
    if r.get("subject_url"):
        return r["subject_url"]
    if r.get("cluster_id"):
        return f"/person/{r['cluster_id']}"
    if r.get("ein"):
        return f"/org/{r['ein']}"
    return None


def _row(r: dict) -> dict:
    out = {}
    for k, v in r.items():
        if k in SKIP_KEYS or v is None or v == "" or isinstance(v, (bytes, memoryview)):
            continue
        v = _plain(v)
        if isinstance(v, str) and len(v) > 160:
            v = v[:160]
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and len(v) <= 6 and all(isinstance(x, (str, int, float)) for x in v):
            out[k] = v
    return out


def data_for(result: dict) -> tuple[dict, dict]:
    """(DATA for the model, {name: url} for linking)."""
    links: dict = {}

    def rows(items):
        out = []
        for r in (items or [])[:MAX_ROWS]:
            if not isinstance(r, dict):
                continue
            x = _row(r)
            u = _url(r)
            for nk in ("subject_name", "name", "display_name", "org_name", "grantor_name", "recipient_name",
                       "person_name", "org", "payer"):
                if r.get(nk) and isinstance(r[nk], str):
                    if u and nk in ("subject_name", "name", "display_name", "person_name"):
                        links.setdefault(r[nk], u)
                    elif r.get("ein") and nk in ("org_name", "org"):
                        links.setdefault(r[nk], f"/org/{r['ein']}")
            out.append(x)
        return out

    kind = result.get("kind")
    data: dict = {"kind": kind, "total": result.get("total")}
    if result.get("board") is not None and hasattr(result["board"], "title"):
        b = result["board"]
        data["list"] = {"title": b.title, "value": b.value.label, "rule": b.formula[:400]}
    if isinstance(result.get("rows"), list):
        data["rows"] = rows(result["rows"])
    for k in ("org", "person", "a", "b", "inst"):
        v = result.get(k)
        if isinstance(v, dict) and k != "inst":
            data[k] = _row(v)
            if v.get("name") and v.get("ein"):
                links.setdefault(v["name"], f"/org/{v['ein']}")
            if v.get("display_name") and v.get("id"):
                links.setdefault(v["display_name"], f"/person/{v['id']}")
    if kind == "school" and result.get("inst"):
        d = result["inst"]
        data["school"] = _row(d["college"])
        links.setdefault(d["college"]["name"], f"/institution/{d['college']['unitid']}")
        if d.get("years"):
            data["payroll_years"] = [_row(y) for y in d["years"][:5]]
        if result.get("aff"):
            keep = ("name", "ein", "city", "state", "latest_filing_year", "latest_total_revenue", "latest_total_assets",
                    "latest_total_expenses", "relation")
            data["affiliates_sorted_by_revenue_largest_first"] = rows([
                {**{k: r.get(k) for k in keep}, "top_paid_person": (r.get("top") or {}).get("display_name"),
                 "top_pay": (r.get("top") or {}).get("total")} for r in result["aff"]["rows"]])
            data["affiliate_count_by_ein"] = len(result["aff"]["rows"])
            data["grants_between"] = rows(result["aff"]["grants"])
            data["shared_people"] = rows(result["aff"]["shared"])
        if result.get("topic") == "funders":
            data["funders"] = rows(d.get("funders"))
        if result.get("topic") == "faculty_salaries":
            data["faculty"] = rows(d.get("faculty_latest"))
    if kind == "timeseries" and result.get("data"):
        data["years"] = rows(result["data"].get("rows"))
    if kind == "org_money" and result.get("data"):
        d = result["data"]
        data["filings"] = rows([f for f in d.get("filings") or [] if not f.get("superseded")])
        if d.get("expenses"):
            data["spending"] = _row(d["expenses"][0])
            data["spending_lines"] = rows(d["expenses"][0].get("detail"))
    if kind == "person_orgs":
        data["orgs"] = rows(result.get("orgs"))
    if kind in ("funders",) and result.get("fu"):
        data["funders"] = rows(result["fu"].get("rows") if isinstance(result["fu"], dict) else result["fu"])
    text = json.dumps(data, default=str)
    while len(text) > MAX_CHARS and data.get("rows"):
        data["rows"] = data["rows"][:-3]
        text = json.dumps(data, default=str)
    return data, links


# --- checking numbers ------------------------------------------------------------------------

_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s*(?:billion|million|thousand|%)?", re.I)


def _value(tok: str) -> float | None:
    t = tok.lower().replace("$", "").replace(",", "").strip()
    mult = 1.0
    for w, m in (("billion", 1e9), ("million", 1e6), ("thousand", 1e3)):
        if t.endswith(w):
            mult, t = m, t[: -len(w)].strip()
    t = t.rstrip("%").strip()
    try:
        return float(t) * mult
    except ValueError:
        return None


def _data_numbers(obj, out: list) -> list:
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            v = _value(m)
            if v is not None:
                out.append(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            _data_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _data_numbers(v, out)
    return out


def numbers_ok(answer: str, data: dict) -> bool:
    """Every number in the answer matches one in the data: exactly, or within the rounding the answer shows."""
    nums = _data_numbers(data, [])
    for tok in _NUM.findall(answer):
        v = _value(tok)
        if v is None:
            continue
        rounded = bool(re.search(r"billion|million|thousand", tok, re.I))
        tol = 0.051 * v if rounded else 0.5
        if not any(abs(v - n) <= tol for n in nums):
            log.info("answer: dropped, %r not in the rows", tok)
            return False
    return True


# --- the model call, linking and the cache ------------------------------------------------------

def _call(question: str, data: dict) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(ask.API_URL, timeout=20, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": ask.MODEL, "max_tokens": 4000, "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}, "system": SYSTEM,
                  "messages": [{"role": "user", "content": f"Question: {question}\n\nDATA: {json.dumps(data, default=str)}"}]})
    except httpx.HTTPError as e:
        log.warning("answer: call failed (%s)", type(e).__name__)
        return None
    if r.status_code != 200:
        log.warning("answer: model returned %s", r.status_code)
        return None
    body = r.json()
    u = body.get("usage") or {}
    ask._usage(calls=1, input_tokens=int(u.get("input_tokens") or 0), output_tokens=int(u.get("output_tokens") or 0))
    text = "".join(c.get("text", "") for c in body.get("content", []) if c.get("type") == "text").strip()
    return text or None


def no_em_dash(text: str) -> str:
    """Model text without em dashes (owner, 2026-10-21): a dash between clauses becomes a comma."""
    return re.sub(r"\s*\u2014\s*", ", ", text or "")


def link(text: str, links: dict) -> str:
    """HTML: the answer escaped, each name (as written in the rows, any capitalization) linked once."""
    out = html.escape(no_em_dash(text))
    used: list[tuple[int, int]] = []
    for name in sorted(links, key=len, reverse=True):
        if len(name) < 4:
            continue
        m = None
        for c in re.finditer(re.escape(html.escape(name)), out, re.I):
            # Not inside a longer proper name ("Ohio State University" in "Ohio State University Foundation").
            if re.match(r"\s+[A-Z][A-Za-z]", out[c.end():]) or re.search(r"[A-Za-z]$", out[:c.start()]):
                continue
            if any(a < c.end() and c.start() < b for a, b in used):
                continue
            m = c
            break
        if not m:
            continue
        a = f'<a href="{html.escape(links[name])}">{m.group(0)}</a>'
        out = out[:m.start()] + a + out[m.end():]
        shift = len(a) - (m.end() - m.start())
        used = [(x + shift if x >= m.end() else x, y + shift if y >= m.end() else y) for x, y in used]
        used.append((m.start(), m.start() + len(a)))
    return out


def cache_key(search_url: str) -> str:
    return hashlib.sha256(search_url.encode()).hexdigest()


def cached(search_url: str) -> str | None:
    try:
        with db.conn() as conn:
            r = conn.execute("""SELECT html FROM nl_answers WHERE key = %s
                                AND created > now() - make_interval(days => %s)""",
                             (cache_key(search_url), CACHE_DAYS)).fetchone()
        return r["html"] if r else None
    except Exception:  # noqa: BLE001
        return None


def answer(question: str, search_url: str, result: dict) -> str:
    """The answer's HTML ("" when there isn't a good one), from the cache or a model call."""
    hit = cached(search_url)
    if hit is not None:
        return hit
    data, links = data_for(result)
    has_rows = any(isinstance(v, list) and v for k, v in data.items() if k not in ("list",)) or data.get("school") \
        or data.get("org") or data.get("person")
    text = _call(question, data) if has_rows else None
    out = ""
    if text and text != "EMPTY" and numbers_ok(text, data):
        out = link(text, links)
    try:
        with db.conn() as conn:
            conn.execute("""INSERT INTO nl_answers (key, url, html) VALUES (%s, %s, %s)
                            ON CONFLICT (key) DO UPDATE SET html = excluded.html, created = now()""",
                         (cache_key(search_url), search_url[:2000], out))
    except Exception:  # noqa: BLE001
        pass
    return out
