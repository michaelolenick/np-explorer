"""The "Explain what I'm seeing" button: a button at the top of data pages. Nothing runs until someone clicks it.

On click, static/site.js asks /explain?u=<the page's path and query>. The server rebuilds that page's underlying
data with the same functions the page uses (rows and fields, never the HTML), compacts it, and asks Claude Sonnet
for one to four plain sentences: the most interesting thing first, who or what this is, how the people and
organizations are tied together, what the key numbers mean and why it matters, using only names and numbers in the
data. Every number in the reply is checked against the data (app/answer.numbers_ok); a reply that fails shows no
explanation rather than a wrong one.

Explanations are cached in nl_explain by page URL and a hash of the data sent, so the next click is instant and the
text regenerates only when the data changes. Clicks are rate-limited per visitor (LIMIT).
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
from urllib.parse import parse_qs, urlsplit

import httpx

from app import ask, db
from app.contact import HourlyLimit

log = logging.getLogger("np.explain")
MODEL = os.environ.get("EXPLAIN_MODEL", "claude-sonnet-5-5")
LIMIT = HourlyLimit(30)
MAX_LIST = 15
MAX_CHARS = 20000
SKIP = {"subject_norm", "name_norm", "name_tsv", "sound_tsv", "xml_path", "evidence", "link_evidence", "source_keys",
        "doc", "copy", "lines", "intents", "categories", "topics", "relation_labels", "ranks", "coverage", "labels"}

# Pages that get the button: path prefixes (templates/_explain.html checks page_path against these).
PREFIXES = ("/search", "/ask", "/person/", "/org/", "/contractor/", "/institution/", "/student-loans/trust/",
            "/boards/", "/politics/donor/", "/politics/committee/", "/corporate/insider/", "/corporate/company/",
            "/corporate/form-d/", "/lobbying/client/", "/lobbying/firm/", "/lobbying/lobbyist/")

SYSTEM = """You explain a page of furp.org, a free public data explorer that cross-references public records \
(nonprofit tax returns, public payrolls, campaign contributions, lobbying, federal grants and contracts, SEC \
filings). You get the page's address, the search typed (if any) and DATA: the structured rows and fields shown on \
the page.

Write 1 to 4 short sentences: one or two for a simple page, up to four for a busy one. Very plain language that \
anyone can follow, no jargon. If a term like "990", "donor-advised fund", "Schedule I" or "delinquency" comes up, \
explain it in a few words (a 990 is the tax return most nonprofits file every year).

Lead with the most interesting or surprising thing in DATA. Then cover, as the data allows: who or what this is, \
how the people and organizations on the page are tied together, what the key numbers mean, and why it matters.

Use only names and numbers that appear in DATA. Nothing from outside knowledge, no guessing; if something is unclear \
from the data, leave it out. Do not calculate new totals or percentages. Round large dollar amounts with one \
decimal ("$4.6 billion"). Neutral wording: no claims of wrongdoing. Plain text, no markdown, and never mention \
"DATA", "rows" or "fields"."""


# --- compacting the data ----------------------------------------------------------------------

def _compact(o, depth: int = 0, n: int = MAX_LIST):
    if depth > 6:
        return None
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()[:10]
    if isinstance(o, str):
        return o if len(o) <= 220 else o[:220] + "…"
    if isinstance(o, (int, float, bool)) or o is None:
        return o
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in SKIP or v is None or v == "" or v == [] or v == {}:
                continue
            c = _compact(v, depth + 1, n)
            if c is not None and c != [] and c != {}:
                out[str(k)] = c
        return out
    if isinstance(o, (list, tuple)):
        items = [c for c in (_compact(x, depth + 1, n) for x in list(o)[:n]) if c not in (None, [], {})]
        if len(o) > n:
            items.append(f"... and {len(o) - n} more")
        return items
    if hasattr(o, "title") and hasattr(o, "definition"):        # a leaderboard
        return {"leaderboard": o.title, "what it ranks": o.definition, "value": o.value.label,
                "rule": o.formula[:600]}
    return None


def compact(data) -> dict:
    """The data, with lists shortened until it fits in MAX_CHARS of JSON."""
    c = None
    for n in (MAX_LIST, 8, 4, 2):
        c = _compact(data, n=n)
        if len(json.dumps(c, default=str)) <= MAX_CHARS:
            break
    return c


# --- rebuilding a page's data from its URL ------------------------------------------------------

def page_data(url: str) -> tuple[dict | None, str]:
    """(the page's data, the search typed or ""), using the same functions as the page itself."""
    from app import main, queries, colleges, student_loans, boards, politics, corporate, lobbying, fedspend
    from starlette.requests import Request
    parts = urlsplit(url)
    path, qs = parts.path, parts.query
    qp = {k: v[0] for k, v in parse_qs(qs).items()}
    req = Request({"type": "http", "path": path, "query_string": qs.encode(), "headers": []})
    q = qp.get("q", "")
    m = re.fullmatch(r"/org/(\d{1,9})", path)
    if m:
        ein = m.group(1).zfill(9)
        d = main.cached_org(ein)
        if not d:
            return None, q
        return {"organization": d, "people_listed": queries.org_people([ein]).get(ein, [])[:25],
                "federal_awards": fedspend.org_awards(ein), "lobbying": lobbying.org_lobbying(ein),
                "political_committees": politics.org_committees(ein), "form_d": corporate.org_formd(ein)}, q
    m = re.fullmatch(r"/person/(\d+)", path)
    if m:
        cid = int(m.group(1))
        d = main.cached_person(cid)
        if not d:
            return None, q
        return {"person": d, "campaign_contributions": politics.person_contributions(cid),
                "federal_award_pay": fedspend.person_pay(cid), "sec_records": corporate.person_sec(cid),
                "lobbying": lobbying.person_lobbying(cid)}, q
    m = re.fullmatch(r"/contractor/(\d+)", path)
    if m:
        return queries.contractor(int(m.group(1))), q
    m = re.fullmatch(r"/institution/(\d+)", path)
    if m:
        return colleges.institution(int(m.group(1))), q
    m = re.fullmatch(r"/student-loans/trust/(\d+)", path)
    if m:
        d = student_loans.trust(int(m.group(1)))
        if d and d.get("months"):
            d = {**d, "months": d["months"][-24:]}      # the latest two years of monthly reports
        return d, q
    m = re.fullmatch(r"/boards/([a-z0-9-]+)", path)
    if m:
        b = boards.get(m.group(1))
        if not b:
            return None, q
        filters = main.board_filters(req)
        spec = boards.sort_spec(b, filters["sort"], filters["dir"])
        filters["sort"], filters["dir"] = (spec if spec else (None, None))
        data = boards.page(b, filters, int(qp.get("page", "1") or 1)) if boards.meta().get(b.slug) else {"rows": []}
        return {"board": b, "filters": {k: v for k, v in filters.items() if v}, "rows": data["rows"][:25],
                "total": data.get("total")}, q
    if path == "/ask" and qp.get("intent"):
        intent = main._intent_from_form(req.query_params)
        return {"search": ask.describe(intent), "result": main._cached_nl_run(main.intent_key({**intent, "page": 1}))}, q
    if path in ("/search", "/ask") and q:
        if path == "/ask":
            p = ask.parse(q, "explain")
            if p.get("intent") not in (None, "unknown", "plain"):
                return {"search": ask.describe(p), "result": main._cached_nl_run(main.intent_key({**p, "page": 1}))}, q
        people, institutions, contractors, orgs = main.run_searches(q, main.search_filters(req), 1)
        return {"people": people.get("results"), "institutions": institutions, "contractors": contractors,
                "organizations": orgs}, q
    m = re.fullmatch(r"/politics/donor/(\d{5})/([a-z0-9-]+)", path)
    if m:
        return politics.donor(m.group(1), m.group(2)), q
    m = re.fullmatch(r"/politics/committee/(C\d{8})", path)
    if m:
        return politics.committee(m.group(1)), q
    m = re.fullmatch(r"/corporate/(insider|company)/(\d+)", path)
    if m:
        return (corporate.insider if m.group(1) == "insider" else corporate.company)(m.group(2).zfill(10)), q
    m = re.fullmatch(r"/corporate/form-d/([\d-]+)", path)
    if m:
        return corporate.formd(m.group(1)), q
    m = re.fullmatch(r"/lobbying/(client|firm|lobbyist)/(\d+)", path)
    if m:
        f = {"client": lobbying.client, "firm": lobbying.registrant, "lobbyist": lobbying.lobbyist}[m.group(1)]
        return f(int(m.group(2))), q
    return None, q


# --- the model call and the cache -----------------------------------------------------------------

def _call(url: str, q: str, data: dict) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(ask.API_URL, timeout=45, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 4000, "thinking": {"type": "adaptive"},
                  "output_config": {"effort": "low"}, "system": SYSTEM,
                  "messages": [{"role": "user", "content": f"Page: {url}\nSearch typed: {q or '(none)'}\n\n"
                                                         f"DATA: {json.dumps(data, default=str)}"}]})
    except httpx.HTTPError as e:
        log.warning("explain: call failed (%s)", type(e).__name__)
        return None
    if r.status_code != 200:
        log.warning("explain: model returned %s", r.status_code)
        return None
    body = r.json()
    u = body.get("usage") or {}
    ask._usage(calls=1, input_tokens=int(u.get("input_tokens") or 0), output_tokens=int(u.get("output_tokens") or 0))
    return "".join(c.get("text", "") for c in body.get("content", []) if c.get("type") == "text").strip() or None


def explain(url: str) -> str:
    """The explanation's HTML for a page URL ("" when there is nothing to explain or no good explanation)."""
    from app import answer
    data, q = page_data(url)
    if not data:
        return ""
    c = compact(data)
    version = hashlib.sha256(json.dumps(c, sort_keys=True, default=str).encode()).hexdigest()[:16]
    key = hashlib.sha256(f"{url}|{version}".encode()).hexdigest()
    try:
        with db.conn() as conn:
            row = conn.execute("SELECT html FROM nl_explain WHERE key = %s", (key,)).fetchone()
        if row:
            return row["html"]
    except Exception:  # noqa: BLE001
        pass
    text = _call(url, q, c)
    out = ""
    if text and answer.numbers_ok(text, c):
        out = "".join(f"<p>{html.escape(s)}</p>" for s in [text])
    try:
        with db.conn() as conn:
            conn.execute("""INSERT INTO nl_explain (key, url, version, html) VALUES (%s, %s, %s, %s)
                            ON CONFLICT (key) DO UPDATE SET html = excluded.html, created = now()""",
                         (key, url[:2000], version, out))
    except Exception:  # noqa: BLE001
        pass
    return out


def cached_only(url: str) -> bool:
    """True when this URL has any cached explanation (used to let a repeat click skip the rate limit)."""
    try:
        with db.conn() as conn:
            return bool(conn.execute("SELECT 1 FROM nl_explain WHERE url = %s AND html <> '' LIMIT 1",
                                     (url[:2000],)).fetchone())
    except Exception:  # noqa: BLE001
        return False
