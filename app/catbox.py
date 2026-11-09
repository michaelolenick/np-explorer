"""One "Find a category" box on /categories (owner, 2026-11-09): the visitor types anything and a small, fast model
(Claude Haiku) says what was meant, then the page answers accordingly:
- lookup: an NTEE code or a category name ("X30", "judaism", "space: for women"): the exact or near match;
- describe: what an organization does ("campus ministry for college students"): Claude Sonnet's ranked codes
  (app/categories.infer);
- grants: who funds, gives to or receives from whom ("show charities likely to donate to hillel"): the grants data
  (org_funders and grant_links, built by loader/funders.py from Schedule I, 990-PF Part XV and DAF sponsor filings),
  with the category suggestions underneath.
An uncertain reading runs describe and grants both and shows whatever came back; a lookup that finds nothing falls
through to describe, so the result is never empty. Every query goes to category_query_log with the reading, its
confidence and the result count, and nothing else (no visitor, address or agent)."""

from __future__ import annotations

import logging
import os
import re

from app import db
from app.cache import ttl_lru
from app.names import normalize_org

log = logging.getLogger(__name__)
ROUTE_MODEL = os.environ.get("CATEGORY_ROUTE_MODEL", "claude-haiku-5-5")
ROUTE_TIMEOUT = float(os.environ.get("CATEGORY_ROUTE_TIMEOUT", "15"))
SURE = 0.7               # a reading below this confidence is uncertain: describe and grants both run
FUNDERS_SHOWN = 50
NAMED_MAX = 300          # organizations resolved for one named recipient family ("hillel": the chapters too)
GRANTORS_MAX = 50        # ... and for one named grantor when the question is who it gives to
CODES_USED = 3           # Sonnet's top codes that stand for a described kind of organization
INTENTS = ("lookup", "describe", "grants")
ROUTE_SCHEMA = {"type": "object", "additionalProperties": False,
                "required": ["intent", "confidence", "recipient", "topic", "place", "direction"],
                "properties": {"intent": {"type": "string", "enum": list(INTENTS)},
                               "confidence": {"type": "number"},
                               "recipient": {"type": "string"}, "topic": {"type": "string"}, "place": {"type": "string"},
                               "direction": {"type": "string", "enum": ["funders", "recipients", "none"]}}}
ROUTE_RULES = (
    "A visitor typed something into the \"Find a category\" box on furp.org, a site about US nonprofits and their IRS "
    "filings. Say what they meant.\n"
    "intent:\n"
    "- lookup: an NTEE code (a letter and two characters, such as X30 or B82) or the name of a category of nonprofit: "
    "a short noun phrase such as \"judaism\", \"private foundations\", \"food banks\", \"jewish organizations\", "
    "\"space: for women\" (a FURP topic and its sense). Typos are fine.\n"
    "- describe: a description of what an organization does, usually a longer phrase or a sentence: \"campus ministry "
    "for college students\", \"feeds families after hurricanes\", \"hospitals that do research\", \"food banks in "
    "Bloomington\".\n"
    "- grants: a question about money between organizations: who funds, gives to, donates to, supports or makes grants "
    "to someone, or who receives grants from someone: \"show charities likely to donate to hillel\", \"funders of "
    "women in science\", \"who gives to the Girl Scouts\", \"who does the Ford Foundation fund\".\n"
    "confidence: 0 to 1, how sure you are of the intent.\n"
    "recipient: for grants, the organization or family of organizations named (\"hillel\", \"Girl Scouts\", \"Ford "
    "Foundation\"), as the visitor wrote it but without a leading \"the\"; empty when none is named.\n"
    "topic: for grants, when the organizations are described rather than named (\"women in science\", \"food banks\"), "
    "that description; for describe, the description itself without the place; for lookup, empty.\n"
    "place: a city, state or region named, otherwise empty.\n"
    "direction: for grants, \"funders\" when they ask who gives to the recipient (the usual case), \"recipients\" when "
    "they ask who the named organization gives to; otherwise \"none\".")
_CODE = re.compile(r"^[A-Za-z][0-9A-Za-z]{0,2}$")
_GRANTS = re.compile(r"\b(who (gives?|donates?|grants?|funds?|supports?)|funders?|funding|donors?|donat(?:e|es|ed|ing|ion|ions)|"
                     r"gives? to|grants? to|funded by|supported by|receives? (?:grants?|money) from|recipients?|grantees?|"
                     r"likely to (?:give|donate|fund))\b", re.I)
_RECIP_DIR = re.compile(r"\b(does|do|did)\b.*\b(give|fund|donate|support|grant)", re.I)
_FILLER = re.compile(r"\b(the|to|of|from|by|show|me|list|find|charities|charity|organizations|organisations|nonprofits|"
                     r"foundations|likely|who|which|what|that|are|is|does|do|did|give|gives|giving|fund|funds|funded|"
                     r"funding|funder|funders|donate|donates|donating|donor|donors|donation|donations|support|supports|"
                     r"grant|grants|grantee|grantees|recipient|recipients|money|receive|receives|received|get|gets|all)\b", re.I)


class _NoAnswer(Exception):
    pass


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())[:300]


def _reading(intent: str, confidence: float, by: str, recipient: str = "", topic: str = "", place: str = "",
             direction: str = "none", note: str | None = None) -> dict:
    return {"intent": intent, "confidence": round(float(confidence), 3), "by": by, "recipient": recipient.strip(),
            "topic": topic.strip(), "place": place.strip(), "direction": direction, "note": note}


def classify(q: str) -> dict:
    """What the visitor meant: {intent, confidence, by (rule | model | guess), recipient, topic, place, direction,
    note}. A bare code is a lookup without asking; otherwise Claude Haiku reads it; when the model is off or fails, a
    guess from the words, marked uncertain so that both readings run."""
    q = q.strip()
    if _CODE.match(q):
        return _reading("lookup", 1.0, "rule")
    try:
        return _ask_model(_norm(q))
    except _NoAnswer as e:
        return guess(q, str(e) or None)


@ttl_lru(ttl=3600)
def _ask_model(key: str) -> dict:
    """Haiku's reading of one query, kept an hour; raises _NoAnswer when there is none (so failures are not kept)."""
    from app import ask
    import httpx
    if not ask.enabled():
        raise _NoAnswer("the model is off (no API key)")
    body = {"model": ROUTE_MODEL, "max_tokens": 300, "thinking": {"type": "adaptive"},
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": ROUTE_SCHEMA}},
            "system": ROUTE_RULES, "messages": [{"role": "user", "content": "Typed: " + key}]}
    try:
        r = ask.post(body, timeout=ROUTE_TIMEOUT)
    except httpx.HTTPError as e:
        log.warning("categories box: routing call failed (%s)", type(e).__name__)
        raise _NoAnswer(f"routing call failed ({type(e).__name__})") from None
    if r.status_code != 200:
        log.warning("categories box: routing model returned %s", r.status_code)
        raise _NoAnswer(f"routing model returned HTTP {r.status_code}")
    data = r.json()
    usage = data.get("usage") or {}
    ask._usage(calls=1, input_tokens=int(usage.get("input_tokens") or 0), output_tokens=int(usage.get("output_tokens") or 0))
    text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text").strip()
    try:
        import json
        ans = json.loads(text)
    except ValueError:
        raise _NoAnswer("routing model gave no JSON") from None
    intent = str(ans.get("intent") or "")
    if intent not in INTENTS:
        raise _NoAnswer("routing model named no intent")
    conf = ans.get("confidence")
    conf = min(1.0, max(0.0, float(conf))) if isinstance(conf, (int, float)) else 0.5
    direction = ans.get("direction") if ans.get("direction") in ("funders", "recipients", "none") else "none"
    if intent == "grants" and direction == "none":
        direction = "funders"
    return _reading(intent, conf, "model", str(ans.get("recipient") or ""), str(ans.get("topic") or ""),
                    str(ans.get("place") or ""), direction)


def guess(q: str, note: str | None = None) -> dict:
    """A reading from the words alone, for when the model cannot answer: grant words make it a grants question, a
    colon or up to three words a lookup, anything longer a description. Always below SURE, so both readings run."""
    words = re.findall(r"[A-Za-z0-9']+", q)
    if _GRANTS.search(q):
        rest = re.sub(r"\s+", " ", _FILLER.sub(" ", q)).strip(" ,.?!")
        direction = "recipients" if _RECIP_DIR.search(q) else "funders"
        return _reading("grants", 0.6, "guess", recipient=rest, topic=rest, direction=direction, note=note)
    if ":" in q or len(words) <= 3:
        return _reading("lookup", 0.6, "guess", note=note)
    return _reading("describe", 0.6, "guess", topic=q, note=note)


# --- the grants reading --------------------------------------------------------------------------

def _available(conn) -> bool:
    return conn.execute("SELECT to_regclass('org_funders') IS NOT NULL AND to_regclass('grant_links') IS NOT NULL "
                        "AS ok").fetchone()["ok"]


def resolve_named(conn, name: str, limit: int) -> list[dict]:
    """Organizations named like the text (largest first): a substring of the normalized name, else the closest
    spellings (trigram), so "hillel" gathers Hillel International and the campus chapters and "girl scotus" still
    finds the Girl Scouts."""
    norm = normalize_org(name)
    if len(norm) < 3:
        return []
    rows = conn.execute("""SELECT ein, name FROM organizations WHERE name_norm ILIKE %s
                           ORDER BY latest_total_revenue DESC NULLS LAST, ein LIMIT %s""",
                        ("%" + norm + "%", limit)).fetchall()
    if rows:
        return rows
    if db.has_trgm():
        rows = conn.execute("""SELECT ein, name FROM organizations WHERE %(norm)s <%% name_norm
                               ORDER BY word_similarity(%(norm)s, name_norm) DESC, latest_total_revenue DESC NULLS LAST, ein
                               LIMIT %(limit)s""", {"norm": norm, "limit": min(limit, 25)}).fetchall()
    return rows


_FUNDERS_SQL = """SELECT f.grantor_ein, max(f.grantor_name) AS grantor_name, max(f.grantor_kind) AS grantor_kind,
                         sum(f.total) AS total, sum(f.n_grants) AS n_grants, count(*) AS recipients,
                         min(f.first_year) AS first_year, max(f.last_year) AS last_year
                  FROM org_funders f {join} WHERE {where}
                  GROUP BY f.grantor_ein ORDER BY total DESC NULLS LAST, f.grantor_ein LIMIT %(lim)s"""


def grants_for(q: str, cls: dict, inferred: dict | None) -> dict | None:
    """Funders of (or recipients of grants from) what the question names or describes. {text, kind (named | topic),
    direction, matched, examples, codes, fields, rows, unlinked}; None when the grants tables are not built."""
    text = (cls.get("recipient") or cls.get("topic") or q).strip()
    direction = "recipients" if cls.get("direction") == "recipients" else "funders"
    out = {"text": text, "kind": "named", "direction": direction, "matched": 0, "examples": [], "codes": [],
           "fields": [], "rows": [], "unlinked": None}
    with db.conn() as conn:
        if not _available(conn):
            return None
        orgs = resolve_named(conn, cls.get("recipient") or text, GRANTORS_MAX if direction == "recipients" else NAMED_MAX) \
            if (cls.get("recipient") or not cls.get("topic")) else []
        if orgs:
            eins = [o["ein"] for o in orgs]
            out.update(matched=len(orgs), examples=[o["name"] for o in orgs[:3]])
            if direction == "recipients":
                out["rows"] = conn.execute("""
                    SELECT l.recipient_ein AS ein, max(o.name) AS name, sum(l.amount) AS total, count(*) AS n_grants,
                           count(DISTINCT l.grantor_ein) AS grantors, min(l.tax_year) AS first_year, max(l.tax_year) AS last_year
                    FROM grant_links l JOIN organizations o ON o.ein = l.recipient_ein WHERE l.grantor_ein = ANY(%(eins)s)
                    GROUP BY l.recipient_ein ORDER BY total DESC NULLS LAST, l.recipient_ein LIMIT %(lim)s""",
                                           {"eins": eins, "lim": FUNDERS_SHOWN}).fetchall()
            else:
                out["rows"] = conn.execute(_FUNDERS_SQL.format(join="", where="f.recipient_ein = ANY(%(eins)s)"),
                                           {"eins": eins, "lim": FUNDERS_SHOWN}).fetchall()
                for r in out["rows"]:
                    r["self"] = r["grantor_ein"] in set(eins)
                norm = normalize_org(cls.get("recipient") or text)
                if len(norm) >= 3:
                    out["unlinked"] = conn.execute("""SELECT count(*) AS n, coalesce(sum(cash_amount), 0) AS total FROM grants
                                                      WHERE recipient_ein IS NULL AND recipient_name_norm ILIKE %s""",
                                                   ("%" + norm + "%",)).fetchone()
            return out
        # Described, not named (or the name matched nothing): the organizations in the categories Sonnet picked for
        # the words, and in any FURP topic the words name.
        out["kind"] = "topic"
        codes = [c["code"] for c in (inferred or {}).get("codes") or [] if len(c["code"]) == 3][:CODES_USED]
        fields = []
        if conn.execute("SELECT to_regclass('research.org_fields') AS t").fetchone()["t"] is not None:
            from app import categories
            fields = [n["code"] for n in categories.search_nodes(text, "furp")["furp"][:CODES_USED]]
        out.update(codes=codes, fields=fields)
        if not codes and not fields:
            return out
        parts = []
        if codes:
            parts.append("SELECT ein FROM nonprofit_ntee WHERE ntee_code = ANY(%(codes)s)")
        if fields:
            parts.append("SELECT ein FROM research.org_fields WHERE field = ANY(%(fields)s)")
        sql = "WITH r AS (" + " UNION ".join(parts) + ") " + _FUNDERS_SQL.format(join="JOIN r ON r.ein = f.recipient_ein", where="true")
        out["rows"] = conn.execute(sql, {"codes": codes, "fields": fields, "lim": FUNDERS_SHOWN}).fetchall()
        out["matched"] = conn.execute("WITH r AS (" + " UNION ".join(parts) + ") SELECT count(*) AS n FROM r",
                                      {"codes": codes, "fields": fields}).fetchone()["n"]
    return out


# --- the box ---------------------------------------------------------------------------------------

def run(q: str, view: str, forced: str = "") -> dict:
    """Everything the page shows for one query: {cls, found, inferred, grants, redirect, results}. forced names an
    intent from an old link (?mode=search or ?mode=infer); otherwise classify() reads the words."""
    from app import categories
    q = q.strip()
    cls = _reading(forced, 1.0, "link") if forced in INTENTS else classify(q)
    intent, sure = cls["intent"], cls["confidence"] >= SURE
    found = inferred = grants = redirect = None
    if intent == "lookup" or not sure:
        found = categories.search_nodes(q, view)
        if intent == "lookup" and sure and _CODE.match(q):
            exact = [n for n in found["ntee"] if n["code"] == q.upper()]
            if len(exact) == 1:
                redirect = categories.node_url("ntee", exact[0]["level"], exact[0]["code"])
        if not any(found.values()):
            found = None
    if intent == "describe" or intent == "grants" or not sure or (intent == "lookup" and found is None):
        words = (cls["topic"] or cls["recipient"] or q) if intent == "grants" else (cls["topic"] or q)
        inferred = categories.infer(words)
    if intent == "grants" or not sure:
        try:
            grants = grants_for(q, cls, inferred)
        except Exception:  # noqa: BLE001 - a grants failure must not hide the other readings
            log.exception("categories box: grants lookup failed")
            grants = None
        if not sure and grants is not None and not grants["rows"]:
            grants = None          # an uncertain reading shows only what came back
    results = sum(len(v) for v in (found or {}).values()) + len((inferred or {}).get("codes") or []) \
        + len((grants or {}).get("rows") or [])
    _log(q, cls, results)
    return {"q": q, "cls": cls, "sure": sure, "found": found, "inferred": inferred, "grants": grants,
            "redirect": redirect, "results": results}


def _log(q: str, cls: dict, results: int) -> None:
    try:
        with db.conn() as conn:
            conn.execute("INSERT INTO category_query_log (q, intent, confidence, results, source) VALUES (%s, %s, %s, %s, %s)",
                         (q[:300], cls["intent"], cls["confidence"], results, cls["by"]))
    except Exception:  # noqa: BLE001 - the log must never break the page
        log.warning("categories box: log write failed")
