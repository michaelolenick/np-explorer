"""Company or nonprofit? Routes a question about an entity to the right reading (owner, 2026-11-24).

"who are competitors to avery dennison?" means the public company (SEC EDGAR), not its foundation (990s). This module:
  * matches a name against the SEC's company list (company_tickers.json, kept a day) and the IPO registrants we hold;
  * reads the intent: company words (competitors, risks, strengths, strategy, SWOT, threats, market) -> the company's
    strategic profile (/s1/{cik}); nonprofit words (foundation, nonprofit, charity, 990, grants, fund) -> the nonprofit;
  * when the words settle nothing and the name fits both a company and a nonprofit, offers a chooser (a plain inline
    list; the choice lives in the URL as pick=company|org|all, so it is bookmarkable and never asked twice);
  * offers the other reading in one line.
SEC data is read through the polite fetcher in loader/s1_terms.py.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import threading
import time
import urllib.parse

from app import db

log = logging.getLogger("np.company_route")

TOPICS = {
    "competitors": r"competitors?|competition|competes?|competing|competitive|rivals?",
    "risks": r"risks?|risk factors|threats?|weakness(?:es)?",
    "strengths": r"strengths?|advantages?",
    "strategy": r"strateg(?:y|ies)|swot|opportunit(?:y|ies)",
    "market": r"markets?",
}
TOPIC_RX = {k: re.compile(r"\b(?:" + v + r")\b", re.I) for k, v in TOPICS.items()}
FILLER = set("""who whom what which are is was were the of to for and with does do did has have a an their its main major biggest top key
 primary list show me about tell on in vs versus compete competes competing company companys analysis profile""".split())
NONPROFIT_RX = re.compile(r"\b(?:foundations?|nonprofits?|non-profits?|charit(?:y|ies)|990s?|grants?|grantmakers?|funds?|donors?|"
                          r"endowment|donat\w+|trust|board of directors)\b", re.I)
SUFFIX = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "holdings", "holding", "group",
          "the", "sa", "nv", "ag", "lp", "llc", "de", "cl", "class", "adr", "ads", "new", "of", "and"}
ORG_WORDS = {"foundation", "fund", "trust", "charitable", "institute", "university", "college", "school"}


def key(name: str) -> str:
    s = (name or "").lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t not in SUFFIX]
    return " ".join(toks) if toks else s.strip()


# ---- the SEC company list ----------------------------------------------------------------------------------------------

_CACHE = os.environ.get("COMPANY_TICKERS_CACHE", "/tmp/np_company_tickers.json")
_idx: dict = {"t": 0.0, "rows": [], "by_key": {}, "keys": []}
_lock = threading.Lock()


def _load() -> None:
    if _idx["rows"] and time.time() - _idx["t"] < 86400:
        return
    with _lock:
        if _idx["rows"] and time.time() - _idx["t"] < 86400:
            return
        body = None
        try:
            if os.path.exists(_CACHE) and time.time() - os.path.getmtime(_CACHE) < 86400:
                body = open(_CACHE, "rb").read()
        except OSError:
            body = None
        if body is None:
            try:
                from loader import s1_terms as T
                body = T._get("https://www.sec.gov/files/company_tickers.json", 8 << 20)
                if body:
                    try:
                        with open(_CACHE + ".tmp", "wb") as f:
                            f.write(body)
                        os.replace(_CACHE + ".tmp", _CACHE)
                    except OSError:
                        pass
            except Exception:  # noqa: BLE001
                log.exception("company_tickers fetch")
        rows, by_key = [], {}
        for v in (json.loads(body) if body else {}).values():
            r = {"cik": str(int(v["cik_str"])), "name": v["title"], "ticker": v["ticker"], "key": key(v["title"])}
            rows.append(r)
            by_key.setdefault(r["key"], []).append(r)
        if rows:
            _idx.update(t=time.time(), rows=rows, by_key=by_key, keys=list(by_key))


def match_company(name: str, fuzzy: bool = True) -> dict | None:
    """The public company a name means: the same name, else one whose name starts with it or contains every word of it
    (the list is in market-value order, so the biggest wins), else a close spelling. None when there is none."""
    k = key(name)
    if len(k) < 3:
        return None
    # IPO registrants we hold (a company with no ticker yet, or gone)
    try:
        with db.pool.connection() as conn:
            r = conn.execute("SELECT cik, name, offer_ticker FROM ipo_companies WHERE name_core = %s OR name_core = %s "
                             "ORDER BY n_filings DESC LIMIT 1", (k, re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).strip())).fetchone()
        if r:
            return {"cik": str(int(r["cik"])), "name": r["name"], "ticker": r["offer_ticker"] or "", "how": "exact"}
    except Exception:  # noqa: BLE001
        pass
    _load()
    by_key, rows = _idx["by_key"], _idx["rows"]
    if k in by_key:
        return {**by_key[k][0], "how": "exact"}
    qt = k.split()
    best = None
    for r in rows:
        rt = r["key"].split()
        if rt[:len(qt)] == qt and len(rt) - len(qt) <= 2:
            return {**r, "how": "prefix"}
        if best is None and len(qt) >= 2 and set(qt) <= set(rt) and len(rt) - len(qt) <= 1:
            best = {**r, "how": "words"}
    if best:
        return best
    if len(qt) == 1:                       # one word: a company whose name has it in it ("kellogg" -> WK Kellogg Co)
        for r in rows:
            if qt[0] in r["key"].split() and len(r["key"].split()) <= 3:
                return {**r, "how": "word"}
    if fuzzy and len(k) >= 5:
        m = difflib.get_close_matches(k, _idx["keys"], 1, 0.9)
        if m:
            return {**by_key[m[0]][0], "how": "fuzzy"}
    return None


# ---- reading the question ----------------------------------------------------------------------------------------------

def question(q: str) -> dict | None:
    """{topic, entity} when q asks a company question ("who are competitors to X", "X risks", "nike swot"); else None."""
    s = (q or "").strip().rstrip("?.! ")
    if not s or len(s) > 120 or NONPROFIT_RX.search(s):
        return None
    topic = next((t for t, rx in TOPIC_RX.items() if rx.search(s)), None)
    if not topic:
        return None
    rest = TOPIC_RX["competitors"].sub(" ", s)
    for rx in TOPIC_RX.values():
        rest = rx.sub(" ", rest)
    words = [w for w in re.sub(r"[^\w'&.\- ]+", " ", rest).split() if w.lower() not in FILLER]
    if not 1 <= len(words) <= 5:
        return None
    return {"topic": topic, "entity": " ".join(words)}


def foundation_like(name: str) -> bool:
    return bool(re.search(r"\b(?:foundation|fund|trust|charitable)\b", name or "", re.I))


def nonprofit_options(entity: str, limit: int = 3, strict: bool = False) -> list[dict]:
    """Nonprofits (990 filers) and schools whose name is the entity's, with a foundation first."""
    from app import queries
    k = key(entity)
    toks = k.split()
    out: list[dict] = []
    try:
        for o in queries.search_orgs(entity, limit=40):
            nt = key(o["name"] or "").split()
            if not toks or nt[:len(toks)] != toks and (strict or not set(toks) <= set(nt[:4])):
                continue
            if re.search(r"retiree|welfare|benefit|pension|employees", o["name"] or "", re.I):
                continue
            out.append({"kind": "foundation" if foundation_like(o["name"]) else "nonprofit", "name": o["name"], "ein": o["ein"],
                        "state": o["state"], "city": o["city"], "revenue": o["latest_total_revenue"],
                        "year": o["latest_filing_year"]})
    except Exception:  # noqa: BLE001
        log.exception("nonprofit options")
    out.sort(key=lambda o: (o["kind"] != "foundation", -(o["revenue"] or 0)))
    return out[:limit]


def school_options(entity: str, limit: int = 2) -> list[dict]:
    from app import colleges
    toks = key(entity).split()
    try:
        best, others = colleges.resolve(entity)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in ([best] if best else []) + list(others or []):
        nm = r.get("name") or ""
        if toks and set(toks) <= set(key(nm).split()):
            out.append({"kind": "school", "name": nm, "url": f"/institution/{r['unitid']}" if r.get("unitid") else None,
                        "state": r.get("state"), "city": r.get("city")})
    return out[:limit]


def options(entity: str) -> dict:
    """Every plausible reading of an entity name: the public company, nonprofits, schools."""
    co = match_company(entity)
    return {"company": co, "nonprofits": nonprofit_options(entity), "schools": school_options(entity)}


def resolve(q: str) -> dict | None:
    """What to do with a search for q: {"go": url} for a clear intent, {"choose": options} when genuinely ambiguous,
    else {"alt": one-line other reading} or None (carry on as before)."""
    cq = question(q)
    if cq:
        co = match_company(cq["entity"])
        if co:
            url = f"/s1/{co['cik']}?" + urllib.parse.urlencode({"topic": cq["topic"], "q": q})
            return {"go": url, "company": co}
        return None
    s = (q or "").strip()
    if not s or len(s) > 80 or re.search(r"\d", s):
        return None
    if NONPROFIT_RX.search(s):                 # the words say nonprofit: carry on, offer the company in one line
        core = " ".join(re.sub(NONPROFIT_RX, " ", s).split())
        co = match_company(core, fuzzy=False) if len(core) >= 3 else None
        if co and co["how"] in ("exact", "prefix"):
            return {"alt": {"text": f"Did you mean the public company {co['name']}?", "url": f"/s1/{co['cik']}?q={urllib.parse.quote(s)}",
                            "tail": "Competitors, risks, strategy"}}
        return None
    words = s.split()
    if len(words) > 4:
        return None
    co = match_company(s)
    if co and co["how"] == "fuzzy":
        co = None
    if co:
        nps, sch = nonprofit_options(s), school_options(s)
        if nps or sch:
            return {"choose": {"company": co, "nonprofits": nps, "schools": sch}}
        return None
    if len(words) == 1:                         # no company: a foundation and a school of one name ("kellogg")
        nps = nonprofit_options(s)
        if nps and nps[0]["kind"] == "foundation":
            sch = [x for x in school_options(s) if key(x["name"]) not in {key(o["name"]) for o in nps}]
            if sch:
                return {"choose": {"company": None, "nonprofits": nps, "schools": sch}}
    return None


def _alt_nonprofit(o: dict) -> dict:
    return {"text": f"Did you mean the {o['name'].title()}?", "url": f"/org/{o['ein']}", "tail": "Grants, finances, people"}


def company_alt(name: str) -> dict | None:
    """For a nonprofit page: the public company of the same name, as one line."""
    core = re.sub(r"\b(?:foundation|fund|charitable|trust|inc)\b", " ", name or "", flags=re.I)
    core = " ".join(core.split())
    co = match_company(core, fuzzy=False) if len(core) >= 3 else None
    if co and co["how"] in ("exact", "prefix"):
        return {"text": f"Did you mean the public company {co['name']}?", "url": f"/s1/{co['cik']}", "tail": "Competitors, risks, strategy"}
    return None


def foundation_alt(company_name: str) -> dict | None:
    ck = key(company_name)
    fa = [o for o in nonprofit_options(ck + " foundation", 8, strict=True) if o["kind"] == "foundation"
          and key(re.sub(r"\b(?:foundation|fund|trust|charitable|inc)\b", " ", o["name"], flags=re.I)) == ck]
    return _alt_nonprofit(fa[0]) if fa else None


def money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v:,.0f}"
