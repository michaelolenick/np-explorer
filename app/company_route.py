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
PEER_FILLER = set("similar to companies company firms businesses stocks brands banks retailers like comparable peer peers group compare compared "
                  "with vs versus alternative alternatives substitutes substitute for who competes compete rivals rival what are is the".split())
# Comparison phrasings ("similar to X", "companies like X", "X peers", "A vs B", "alternatives to X"): company intent for a listed company.
PEER_RX = re.compile(r"\b(?:similar(?:\s+(?:companies|to|firms|businesses))?|(?:companies|firms|businesses|stocks|brands|banks|retailers)\s+like|like|"
                     r"comparable(?:\s+(?:to|companies))?|peers?|peer\s+group|compare(?:d)?(?:\s+to|\s+with)?|vs\.?|versus|"
                     r"alternatives?(?:\s+to)?|substitutes?\s+for|who\s+competes?\s+with|competes?\s+with|rivals?)\b", re.I)
VS_RX = re.compile(r"^(.+?)\s+(?:vs\.?|versus|compared?\s+(?:to|with))\s+(.+)$", re.I)
TOPIC_RX = {k: re.compile(r"\b(?:" + v + r")\b", re.I) for k, v in TOPICS.items()}
CTX_WORDS = set("store stores grocery retailer retailers company brand stock earnings shares ticker".split())
OTHER_INTENT = re.compile(r"\b(?:buybacks?|repurchas\w*|insiders?|recalls?|registered|licensed|brokers?|salary|salaries|paid|ceo|board|"
                          r"directors?|sold|sell|selling)\b", re.I)
FILLER = set("""who whom what which are is was were the of to for and with does do did has have a an their its main major biggest top key
 primary list show me about tell on in vs versus compete competes competing company companys analysis profile""".split())
NONPROFIT_RX = re.compile(r"\b(?:foundations?|nonprofits?|non-profits?|charit(?:y|ies)|990s?|grants?|grantmakers?|funds?|donors?|"
                          r"endowment|donat\w+|trust|board of directors)\b", re.I)
SUFFIX = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "holdings", "holding", "group",
          "the", "sa", "nv", "ag", "lp", "llc", "de", "cl", "class", "adr", "ads", "new", "of", "and"}
# The most common US surnames: a search for one of these is a person search, so a bare one never opens the chooser.
TOP_SURNAMES = set("""smith johnson williams brown jones garcia miller davis rodriguez martinez hernandez lopez gonzalez wilson anderson
 thomas taylor moore jackson martin lee perez thompson white harris sanchez clark ramirez lewis robinson walker young allen king wright
 scott torres nguyen hill flores green adams nelson baker hall rivera campbell mitchell carter roberts gomez phillips evans turner diaz
 parker cruz edwards collins reyes stewart morris morales murphy cook rogers gutierrez ortiz morgan cooper peterson bailey reed kelly
 howard ramos kim cox ward richardson watson brooks chavez wood james bennett gray mendoza ruiz hughes price alvarez castillo sanders
 patel myers long ross foster jimenez powell jenkins perry russell sullivan bell coleman butler henderson barnes gonzales fisher
 vasquez simmons romero jordan patterson alexander hamilton graham reynolds griffin wallace moreno west cole hayes bryant herrera
 gibson ellis tran medina aguilar stevens murray ford castro marshall owens harrison fernandez mcdonald woods washington kennedy
 wells vargas henry chen freeman webb tucker guzman burns crawford olson simpson porter hunter gordon mendez silva shaw snyder
 mason dixon munoz hunt hicks holmes palmer wagner black robertson boyd rose stone salazar fox warren mills meyer rice schmidt
 daniel""".split()) - {"ford"}
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


_major: dict = {"t": 0.0, "rows": [], "alias": {}, "ticker": {}}


def _major_load() -> None:
    """The major companies (loader/major_companies.py), kept ten minutes; empty before the table exists."""
    if time.time() - _major["t"] < 600:
        return
    rows, alias, tick = [], {}, {}
    try:
        with db.pool.connection() as conn:
            for r in conn.execute("SELECT cik, name, ticker, aliases FROM major_companies ORDER BY rev_rank NULLS LAST, cik").fetchall():
                m = {"cik": r["cik"], "name": r["name"], "ticker": r["ticker"] or "", "how": "exact", "major": True,
                     "akeys": [a.split() for a in r["aliases"]]}
                rows.append(m)
                for a in r["aliases"]:
                    alias.setdefault(a, m)
                if r["ticker"]:
                    tick.setdefault(r["ticker"].lower(), m)
    except Exception:  # noqa: BLE001
        log.debug("major_companies not readable yet")
    _major.update(t=time.time(), rows=rows, alias=alias, ticker=tick)


def major_match(name: str, prefix: bool = True) -> dict | None:
    """A major company by name, alias or (typed in capitals) ticker."""
    _major_load()
    k = key(name)
    if not k:
        return None
    m = _major["alias"].get(k)
    if m:
        return m
    nm = (name or "").strip()
    if nm.isupper() and 2 <= len(nm) <= 5 and nm.lower() in _major["ticker"]:
        return _major["ticker"][nm.lower()]
    if prefix and len(k) >= 3:
        qt = k.split()
        for m in _major["rows"]:
            for at in m["akeys"]:
                if at[:len(qt)] == qt and len(at) - len(qt) <= 2:
                    return {**m, "how": "prefix"}
    return None


def find_major_in(tokens: list[str]) -> dict | None:
    """The first major company named inside a sentence: the longest run of words that is a name or alias, or a ticker
    typed in capitals."""
    _major_load()
    n = len(tokens)
    for size in range(min(4, n), 0, -1):
        for i in range(n - size + 1):
            ph = " ".join(tokens[i:i + size])
            if size == 1 and len(ph) < 2:
                continue
            m = major_match(ph, prefix=False)
            if m and not (size == 1 and ph.lower() in FILLER | CTX_WORDS and not ph.isupper()):
                return m
    return None


def match_company(name: str, fuzzy: bool = True) -> dict | None:
    """The public company a name means: the same name, else one whose name starts with it or contains every word of it
    (the list is in market-value order, so the biggest wins), else a close spelling. None when there is none."""
    mj = major_match(name)
    if mj:
        return mj
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
    if fuzzy and len(k) >= 5:
        m = difflib.get_close_matches(k, _idx["keys"], 1, 0.9)
        if m:
            return {**by_key[m[0]][0], "how": "fuzzy"}
    return None


# ---- reading the question ----------------------------------------------------------------------------------------------

def question(q: str) -> dict | None:
    """{topic, entity, tokens} when q asks a company question ("who are competitors to X", "X risks", "nike swot",
    "kroger, the grocery store - tell me competitors"); else None. Company-context words (store, grocery, brand,
    stock, earnings) alone also count, unless the words ask for another kind of answer."""
    s = (q or "").strip().rstrip("?.! ")
    if not s or len(s) > 160 or NONPROFIT_RX.search(s):
        return None
    topic = next((t for t, rx in TOPIC_RX.items() if rx.search(s)), None)
    if topic is None and PEER_RX.search(s):        # "who competes with X" / "rivals of X" already read as the competitors topic
        return _peer_question(s)
    toks = re.findall(r"[A-Za-z0-9&'\u2019]+", s)
    ctx = any(t.lower() in CTX_WORDS for t in toks)
    if not topic and not (ctx and not OTHER_INTENT.search(s)):
        return None
    rest = s
    for rx in TOPIC_RX.values():
        rest = rx.sub(" ", rest)
    words = [w for w in re.findall(r"[A-Za-z0-9&'\u2019.\-]+", rest) if w.lower() not in FILLER and w.lower() not in CTX_WORDS]
    return {"topic": topic or "", "entity": " ".join(words) if 1 <= len(words) <= 5 else "", "tokens": toks}


def _peer_question(s: str) -> dict | None:
    """A comparison phrasing. Company intent only when a listed company is named; otherwise None (the nonprofit path)."""
    toks = re.findall(r"[A-Za-z0-9&'\u2019]+", s)
    vs = VS_RX.match(s)
    if vs:
        a, b = (find_major_in(re.findall(r"[A-Za-z0-9&'\u2019]+", x)) or major_match(x.strip()) for x in (vs.group(1), vs.group(2)))
        if a:
            return {"topic": "peers", "entity": a["name"], "tokens": toks, "major": a, "vs": b}
    rest = PEER_RX.sub(" ", s)
    words = [w for w in re.findall(r"[A-Za-z0-9&'\u2019.\-]+", rest) if w.lower() not in PEER_FILLER and w.lower() not in FILLER]
    ent = " ".join(words)
    m = (find_major_in(words) if words else None) or (major_match(ent) if ent else None)
    if m:
        return {"topic": "peers", "entity": m["name"], "tokens": toks, "major": m, "vs": None}
    return None


def foundation_like(name: str) -> bool:
    return bool(re.search(r"\b(?:foundation|fund|trust|charitable)\b", name or "", re.I))


def nonprofit_options(entity: str, limit: int = 3, strict: bool = False, fetch: int = 40) -> list[dict]:
    """Nonprofits (990 filers) and schools whose name is the entity's, with a foundation first."""
    from app import queries
    k = key(entity)
    toks = k.split()
    out: list[dict] = []
    try:
        for o in queries.search_orgs(entity, limit=fetch):
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
        co = cq.get("major") or find_major_in(cq["tokens"]) or (match_company(cq["entity"]) if cq["entity"] else None)
        if co:
            args = {"topic": cq["topic"], "q": q}
            if cq.get("vs"):
                args["vs"] = cq["vs"]["cik"]
            url = f"/s1/{co['cik']}?" + urllib.parse.urlencode(args)
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
    if co and (co["how"] == "fuzzy" or (len(words) == 1 and co["how"] != "exact" and s.lower() in TOP_SURNAMES)):
        co = None
    if co:
        nps, sch = nonprofit_options(s), school_options(s)
        if nps or sch:
            return {"choose": {"company": co, "nonprofits": nps, "schools": sch}}
        return None
    if len(words) == 1 and s.lower() not in TOP_SURNAMES:   # no company: a foundation and a school of one name ("kellogg")
        nps = nonprofit_options(s)
        if nps and nps[0]["kind"] == "foundation":
            sch = [x for x in school_options(s) if key(x["name"]).split()[:1] == key(s).split()
                   and key(x["name"]) not in {key(o["name"]) for o in nps}]
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
    fa: list[dict] = []
    for q, fetch in ((ck, 80), (ck + " foundation", 40)):        # the bare name first: "x foundation" is slow for a rare x
        fa = [o for o in nonprofit_options(q, 8, strict=True, fetch=fetch) if o["kind"] == "foundation"
              and key(re.sub(r"\b(?:foundation|fund|trust|charitable|inc)\b", " ", o["name"], flags=re.I)) == ck]
        if fa:
            break
    return _alt_nonprofit(fa[0]) if fa else None


def _tier(a, b) -> str:
    if not a or not b:
        return ""
    r = max(a, b) / max(min(a, b), 1)
    return "within 2x" if r <= 2 else "within 5x" if r <= 5 else "within 10x" if r <= 10 else "more than 10x apart"


def peers(cik: str, named: list[str] | None = None, limit: int = 15) -> dict:
    """Company peers: competitors named in its own filing (matched to the major list for ticker, revenue and a profile link),
    then the companies with the same SIC code, nearest in revenue first (within 2x, 5x, 10x)."""
    cik = str(int(cik))
    out = {"me": None, "named": [], "same_sic": [], "sic": None}
    try:
        with db.pool.connection() as conn:
            me = conn.execute("SELECT cik, name, ticker, revenue, sic, sic_desc FROM major_companies WHERE cik = %s", (cik,)).fetchone()
            out["me"] = dict(me) if me else None
            seen = {cik}
            for nm in named or []:
                m = major_match(nm, prefix=False)
                if m and m["cik"] not in seen:
                    r = conn.execute("SELECT cik, name, ticker, revenue, sic_desc FROM major_companies WHERE cik = %s", (m["cik"],)).fetchone()
                    seen.add(m["cik"])
                    out["named"].append({**dict(r), "tier": _tier(me and me["revenue"], r["revenue"]) if r else ""})
                else:
                    out["named"].append({"cik": None, "name": nm, "ticker": "", "revenue": None, "tier": ""})
            if me and me["sic"] and me["sic"] != "none":
                out["sic"] = f"{me['sic']} {me['sic_desc'] or ''}".strip()
                base = float(me["revenue"] or 0)
                rows = conn.execute("SELECT cik, name, ticker, revenue FROM major_companies WHERE sic = %s AND cik <> %s", (me["sic"], cik)).fetchall()
                rows = [dict(r, tier=_tier(base, float(r["revenue"] or 0)) if base and r["revenue"] else "") for r in rows
                        if r["cik"] not in seen]
                rows.sort(key=lambda r: abs(__import__("math").log((float(r["revenue"]) or 1) / base)) if base and r["revenue"] else 99)
                out["same_sic"] = rows[:limit]
    except Exception:  # noqa: BLE001
        log.exception("peers")
    return out


def money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v:,.0f}"
