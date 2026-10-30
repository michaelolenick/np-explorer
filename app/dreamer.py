"""Nonprofit Dreamer (owner, 2026-10-30): "Thinking of starting a nonprofit? See what actually happens to ones like
yours." BETA. Free, no login, no language model.

Organizations like yours: nonprofits founded 2012-2018 (the IRS ruling year; estimated for closed ones, loader/dreamer.py) in an NTEE major category, or whose own
words match a description (research.org_text: name, mission and program descriptions; a word with labeled senses,
research.sense_defs, counts only in the meaning chosen: "space" is outer space unless the reader picks another), or
whose name matches it; optionally in a state or within METRO_MILES of a ZIP or "City, ST"; optionally only those that
paid an officer in their first five years ("I plan to pay myself").

Their first five years come from research.dream_orgs (loader/dreamer.py, built from research.npay_years and npay_orgs).
Revenue and officer pay are from 990 and 990-EZ returns; a year with only a 990-N postcard (under $50K) has neither,
so each year's figures are among the organizations that filed a full return that year, with that count shown.
"""

from __future__ import annotations

import logging
import re

from app import db
from app.cache import ttl_lru

log = logging.getLogger("np.dreamer")

FIRST, LAST = 2012, 2018       # founding years (loader/dreamer.py)
MIN_N = 100                     # fewer organizations like yours than this: compared with all nonprofits too
METRO_MILES = 30
YEARS = range(1, 6)
THRESHOLDS = (50_000, 100_000, 250_000, 1_000_000)
LAST_TAX_YEAR = 2025            # the newest tax year in research.npay_years
CLOSED_BY = 3                   # "closed": no return of any kind after year CLOSED_BY
TIMEOUT = "10s"

NTEE = {
    "A": "Arts, culture and humanities", "B": "Education", "C": "Environment", "D": "Animals",
    "E": "Health care", "F": "Mental health and crisis", "G": "Diseases and medical disciplines",
    "H": "Medical research", "I": "Crime and legal", "J": "Employment", "K": "Food, agriculture and nutrition",
    "L": "Housing and shelter", "M": "Public safety and disaster relief", "N": "Recreation and sports",
    "O": "Youth development", "P": "Human services", "Q": "International affairs", "R": "Civil rights and advocacy",
    "S": "Community improvement", "T": "Philanthropy and grantmaking", "U": "Science and technology",
    "V": "Social science", "W": "Public and societal benefit", "X": "Religion", "Y": "Mutual and membership benefit",
    "Z": "Unknown",
}

# The meaning a sense-labeled word gets when the reader hasn't picked one (research.sense_defs codes). Topics not
# listed here aren't narrowed unless the reader picks a meaning.
DEFAULT_SENSE = {"space": "O", "domestic": "D", "science": "E", "women": "I", "men": "I", "shelter": "H",
                 "launch": "S"}
SENSE_WORDS = {"launch": {"launch", "rocket", "rocketri", "orbit", "orbit", "flight"}}   # not "mission": too common

STATE = re.compile(r"^[A-Za-z]{2}$")


@ttl_lru(ttl=600)
def ready() -> bool:
    try:
        with db.conn() as conn:
            return conn.execute("SELECT to_regclass('research.dream_orgs') IS NOT NULL AS ok").fetchone()["ok"]
    except Exception:  # noqa: BLE001
        return False


@ttl_lru(ttl=3600)
def _senses() -> dict:
    """{topic: {"lexemes": set, "codes": [(code, sense, description)]}} from research.sense_defs."""
    out: dict = {}
    with db.conn() as conn:
        if not conn.execute("SELECT to_regclass('research.sense_defs') IS NOT NULL AS ok").fetchone()["ok"]:
            return out
        for r in conn.execute("""SELECT topic, code, sense, description,
                                        tsvector_to_array(to_tsvector('english', replace(tsq, '|', ' '))) AS lex
                                 FROM research.sense_defs ORDER BY topic, code""").fetchall():
            t = out.setdefault(r["topic"], {"lexemes": set(r["lex"]), "codes": []})
            t["codes"].append((r["code"], r["sense"], r["description"]))
    for topic, words in SENSE_WORDS.items():
        if topic in out:
            out[topic]["lexemes"] &= words
    return out


def sense_for(conn, q: str, pick: str | None) -> dict | None:
    """The first sense-labeled word in q: {"topic", "code" (None = any meaning), "word", "codes", "others" (the
    meanings to switch to: (code, name), "any" last)}."""
    if not q:
        return None
    senses = _senses()
    lex = [r["l"] for r in conn.execute("SELECT unnest(tsvector_to_array(to_tsvector('english', %s))) AS l",
                                        (q,)).fetchall()]
    for topic, t in senses.items():
        hit = next((x for x in lex if x in t["lexemes"]), None)
        if not hit:
            continue
        codes = [c for c, _, _ in t["codes"]]
        p_topic, _, p_code = (pick or "").partition(":")
        code = (p_code if p_code in codes else None) if p_topic == topic else DEFAULT_SENSE.get(topic)
        others = [(c, sense.replace("_", " ")) for c, sense, _ in t["codes"] if c != code] + ([("any", "any")] if code else [])
        return {"topic": topic, "code": code, "word": hit, "codes": t["codes"], "others": others}
    return None


def where(conn, *, ntee: str | None, q: str | None, state: str | None, zips: list[str] | None, pay: bool,
          sense: dict | None) -> tuple[str, dict]:
    """The WHERE clause (on research.dream_orgs d) for organizations like yours, and its parameters."""
    w, p = ["true"], {}
    if ntee:
        w.append("d.ntee_major = %(ntee)s")
        p["ntee"] = ntee
    if q:
        p["q"] = q
        text = """d.ein IN (SELECT ein FROM research.org_text t, plainto_tsquery('english', %(q)s) x
                            WHERE t.tsv_name @@ x OR t.tsv_mission @@ x OR t.tsv_program @@ x)"""
        if sense and sense["code"]:
            p["topic"], p["code"] = sense["topic"], f"%{sense['code']}%"
            w.append(text + """ AND EXISTS (SELECT 1 FROM research.org_codes c WHERE c.ein = d.ein
                                            AND c.topic = %(topic)s AND c.codes LIKE %(code)s)""")
        else:
            # Organizations that file only the postcard have no text but a name.
            w.append(f"""({text} OR d.ein IN (SELECT ein FROM organizations o
                                              WHERE o.name_tsv @@ plainto_tsquery('simple', %(q)s)))""")
    if state:
        w.append("d.state = %(state)s")
        p["state"] = state
    if zips is not None:
        w.append("d.zip5 = ANY(%(zips)s)")
        p["zips"] = zips
    if pay:
        w.append("(" + " OR ".join(f"d.o{k} > 0" for k in YEARS) + ")")
    return " AND ".join(w), p


def _stats_sql(cond: str) -> str:
    """Year k counts the organizations still filing something (any return, 990-N included) for year k or later; a
    year without a 990 or 990-EZ counts as revenue under $50K (a postcard year) and no officer pay."""
    cols = []
    for k in YEARS:
        alive = f"FILTER (WHERE d.last_filed >= d.founded + {k})"
        cols += [f"count(*) {alive} AS n{k}",
                 f"percentile_cont(ARRAY[0.25, 0.5, 0.75]) WITHIN GROUP (ORDER BY coalesce(d.r{k}, 0)) {alive} AS rev{k}",
                 f"count(*) FILTER (WHERE d.o{k} > 0) AS paid{k}",
                 f"percentile_cont(0.5) WITHIN GROUP (ORDER BY coalesce(d.o{k}, 0)) {alive} AS med_o{k}",
                 f"percentile_cont(0.5) WITHIN GROUP (ORDER BY d.o{k}) FILTER (WHERE d.o{k} > 0) AS paid_o{k}"]
    cols += [f"count(*) FILTER (WHERE d.peak_revenue >= {t}) AS reach_{t}" for t in THRESHOLDS]
    return f"""SELECT count(*) AS n, count(*) FILTER (WHERE d.returns > 0) AS filers,
                      count(*) FILTER (WHERE d.closed) AS closed,
                      count(*) FILTER (WHERE d.last_filed >= d.founded + 5) AS alive5,
                      count(*) FILTER (WHERE d.two50) AS two50,
                      {', '.join(cols)}
               FROM research.dream_orgs d WHERE {cond}"""


def _shape(r: dict) -> dict:
    n = r["n"] or 0
    pct = (lambda x: round(100.0 * x / n) if n else None)
    years = []
    for k in YEARS:
        nk, rev = r[f"n{k}"], r[f"rev{k}"] or [None, None, None]
        years.append({"k": k, "n": nk, "p25": rev[0], "median": rev[1], "p75": rev[2],
                      "paid_pct": round(100.0 * r[f"paid{k}"] / nk) if nk else None,
                      "med_officer": r[f"med_o{k}"], "paid_officer": r[f"paid_o{k}"]})
    return {"n": n, "filers": r["filers"], "closed": r["closed"], "years": years,
            "reach": [(t, pct(r[f"reach_{t}"])) for t in THRESHOLDS],
            "alive5": pct(r["alive5"]), "two50": pct(r["two50"]), "two50_n": r["two50"]}


EXAMPLES_SQL = """
WITH g AS (SELECT d.*, greatest(d.r1, d.r2, d.r3, d.r4, d.r5) AS best FROM research.dream_orgs d
           WHERE {cond} AND d.returns > 0),
q AS (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY best) AS p50,
             percentile_cont(0.95) WITHIN GROUP (ORDER BY best) AS p95 FROM g WHERE best IS NOT NULL),
c AS (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY best) AS p50 FROM g
      WHERE best IS NOT NULL AND last_filed <= founded + %(closed_by)s AND last_filed <= %(last)s - 3),
-- closed: off the IRS list (else still listed but filing nothing for three years), nearest the median of its kind
pick AS (
    (SELECT 'typical' AS kind, g.ein, g.best FROM g, q WHERE g.best IS NOT NULL AND g.last_filed >= g.founded + 5
     ORDER BY abs(g.best - q.p50), md5(g.ein) LIMIT 1)
    UNION ALL
    (SELECT 'top', g.ein, g.best FROM g, q WHERE g.best >= q.p95 * 0.9 ORDER BY abs(g.best - q.p95), md5(g.ein) LIMIT 1)
    UNION ALL
    (SELECT 'closed', g.ein, g.best FROM g, c WHERE g.best IS NOT NULL AND g.last_filed <= g.founded + %(closed_by)s
       AND g.last_filed <= %(last)s - 3 ORDER BY g.closed DESC, abs(g.best - c.p50), md5(g.ein) LIMIT 1))
SELECT pick.kind, pick.ein, pick.best, o.name, o.city, o.state, g.founded, g.last_filed
FROM pick JOIN g USING (ein) JOIN organizations o USING (ein)"""


def _timeout(conn):
    conn.execute(f"SET LOCAL statement_timeout = '{TIMEOUT}'")


@ttl_lru(ttl=86400)
def overall(pay: bool = False) -> dict:
    with db.conn() as conn:
        _timeout(conn)
        cond, p = where(conn, ntee=None, q=None, state=None, zips=None, pay=pay, sense=None)
        return _shape(conn.execute(_stats_sql(cond), p).fetchone())


@ttl_lru(ttl=3600)
def dream(ntee: str = "", q: str = "", where_: str = "", pay: bool = False, sense: str = "") -> dict:
    """Everything /dreamer shows for one set of choices."""
    ntee = ntee.upper() if ntee.upper() in NTEE else None
    q = " ".join((q or "").split())[:200] or None
    out = {"ntee": ntee, "q": q, "pay": pay, "place": None, "error": None, "sense": None}
    state, zips = None, None
    if where_:
        if STATE.match(where_):
            state = where_.upper()
            out["place"] = state
        else:
            from app import nearby
            center = nearby.place(where_)
            if not center:
                return {**out, "error": "place"}
            with db.conn() as conn:
                zips = nearby._zips_within(conn, center, METRO_MILES)
            out["place"] = f"within {METRO_MILES} miles of {center['label']}"
    with db.conn() as conn:
        _timeout(conn)
        s = sense_for(conn, q, sense or None) if q else None
        out["sense"] = s
        cond, p = where(conn, ntee=ntee, q=q, state=state, zips=zips, pay=pay, sense=s)
        out["group"] = _shape(conn.execute(_stats_sql(cond), p).fetchone())
        out["examples"] = {r["kind"]: r for r in conn.execute(EXAMPLES_SQL.format(cond=cond),
                                                              {**p, "closed_by": CLOSED_BY, "last": LAST_TAX_YEAR})}
    out["small"] = out["group"]["n"] < MIN_N
    out["open_only"] = bool(ntee)      # closed nonprofits have no NTEE code: a category can't count them
    out["all"] = overall(pay)
    out["shown"] = out["all"] if out["small"] else out["group"]
    return out


def money(v) -> str:
    if v is None:
        return "n/a"
    v = float(v)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 10_000:
        return f"${round(v / 1000):,}K"
    return f"${round(v):,}"


def revenue(v) -> str:
    """Revenue for the year table: below $50K is "under $50K" (most of those years are 990-N postcards, no amount)."""
    return "n/a" if v is None else ("under $50K" if v < 50_000 else money(v))


def headline(d: dict) -> str:
    """The result card's sentence: "Of 1,842 nonprofits like yours, the median paid its officers $0 in year 1 ..."."""
    s = d["shown"]
    y1, y5 = s["years"][0], s["years"][4]
    who = f"{s['n']:,} nonprofits like yours" if not d["small"] else f"{s['n']:,} nonprofits founded {FIRST} to {LAST}"
    if d["pay"]:
        who += " that paid an officer"
    text = f"Of {who}, the median paid its officers {money(y1['med_officer'])} in year 1"
    if y5["median"] is not None:
        text += f" and took in {revenue(y5['median'])} in year 5"
    if s["alive5"] is not None and not (d["open_only"] and not d["small"]):
        text += f". {s['alive5']}% were still filing in year 5"
    return text + "."


def two50_words(s: dict) -> str:
    p = s["two50"]
    if p is None:
        return ""
    if p == 0:
        return "Could it support two $50K salaries? None of them did in their first five years."
    return (f"Could it support two $50K salaries? Only {p}% did at some point in their first five years "
            f"(about 1 in {max(1, round(100 / p))}).") if p < 50 else (
            f"Could it support two $50K salaries? {p}% did at some point in their first five years.")
