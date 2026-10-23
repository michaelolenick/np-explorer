"""Securities registration on the site (loader/registrations.py): whether a person or firm is registered to sell
securities or advise on investments, from the SEC's broker-dealer list and the IAPD compilation reports.

What "registered" can mean here, and what it can't:
- investment adviser representatives (IARs) and adviser firms: the whole IAPD file, so "no IAPD record" means no
  adviser registration under that name;
- broker registration: known for IARs (IAPD says whether they also hold an active broker registration) and for
  broker-dealer firms (the SEC's monthly list). People registered only as brokers aren't in any public bulk file,
  so every person gets a BrokerCheck search link rather than a "not a broker".
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from app import db
from app.corporate import PUBLIC

log = logging.getLogger("np.registrations")
BROKERCHECK = "https://brokercheck.finra.org/search/genericsearch/grid?query={q}"
IAPD_SEARCH = "https://adviserinfo.sec.gov/search/genericsearch/grid?query={q}"
IAPD_PERSON = "https://adviserinfo.sec.gov/individual/summary/{crd}"
IAPD_FIRM = "https://adviserinfo.sec.gov/firm/summary/{crd}"
BROKER_EXAMS = {"S7", "S6", "S62", "S79", "S82", "S22", "S37", "S38"}
ROLE_RX = re.compile(r"manag|advis|portfolio|placement|capital rais|promoter|chief investment|investment officer", re.I)
NOT_ROLE_RX = re.compile(r"attorney|counsel|secretary|compliance|accountant|auditor|administrator", re.I)


def search_links(name: str) -> dict:
    q = quote(name or "")
    return {"brokercheck": BROKERCHECK.format(q=q), "iapd": IAPD_SEARCH.format(q=q)}


def individual(conn, crd: str) -> dict | None:
    i = conn.execute("SELECT * FROM iapd_individuals WHERE crd = %s", (crd,)).fetchone()
    if not i:
        return None
    emps = conn.execute("""SELECT firm_crd, firm_name, current, min(begin_date) AS begin_date, max(end_date) AS end_date,
                                  string_agg(DISTINCT reg_authority, ', ') AS where_
                           FROM iapd_employments WHERE crd = %s GROUP BY 1, 2, 3
                           ORDER BY current DESC, min(begin_date) DESC NULLS LAST""", (crd,)).fetchall()
    exams = set(i["exams"] or [])
    current = [e for e in emps if e["current"]]
    return {**i, "employments": emps, "current": current, "url": IAPD_PERSON.format(crd=crd),
            "adviser": bool(current), "broker": bool(i["active_broker"]),
            "broker_exams": sorted(exams & BROKER_EXAMS),
            "since": min((e["begin_date"] for e in current if e["begin_date"]), default=None)}


def firm(conn, kind: str, key: str) -> dict | None:
    if kind == "bd":
        f = conn.execute("SELECT * FROM bd_firms WHERE cik = %s", (key,)).fetchone()
        return {**f, "kind": "Broker-dealer", "url": IAPD_FIRM.format(crd=f["crd"]) if f["crd"] else
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={key}"} if f else None
    f = conn.execute("SELECT * FROM iapd_firms WHERE crd = %s", (key,)).fetchone()
    return {**f, "kind": f"Investment adviser ({f['regulator']}-registered)", "name": f["business_name"] or f["legal_name"],
            "url": IAPD_FIRM.format(crd=key)} if f else None


def _section(conn, kind: str, key: str, name: str, roles: list | None = None) -> dict:
    links = conn.execute("SELECT reg_kind, reg_key, how FROM registration_links WHERE kind = %s AND key = %s",
                         (kind, key)).fetchall()
    people = [x for x in (individual(conn, l["reg_key"]) for l in links if l["reg_kind"] == "iar") if x]
    firms = [x for x in (firm(conn, l["reg_kind"], l["reg_key"]) for l in links if l["reg_kind"] in ("bd", "ia")) if x]
    manager = [r for r in roles or [] if ROLE_RX.search(t := f"{r.get('relationships') or ''} {r.get('clarification') or ''}")
               and not NOT_ROLE_RX.search(t)]
    if manager and not people:
        # A fund whose adviser files Form ADV has a registered (or exempt reporting) firm behind it: no flag.
        advised = conn.execute("""SELECT 1 FROM sec_formd d JOIN sec_formd_offerings o ON o.cik = d.cik
                                  JOIN adv_fund_links l ON l.root_accession = o.root_accession
                                  WHERE d.accession = ANY(%s) LIMIT 1""",
                               ([r["accession"] for r in manager if r.get("accession")],)).fetchone()
        manager = [] if advised else manager
    return {"people": people, "firms": firms, "links": search_links(name), "name": name,
            "unregistered_manager": bool(manager) and not people, "manager_roles": manager[:3]}


def for_person(cluster_id: int, name: str) -> dict | None:
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '3s'")
            roles = []
            if conn.execute("SELECT to_regclass('sec_formd_parties') IS NOT NULL AS ok").fetchone()["ok"]:
                roles = conn.execute("""SELECT p.accession, p.relationships, p.clarification FROM sec_formd_parties pt
                                        JOIN sec_formd_people_party x ON x.party_id = pt.id
                                        JOIN sec_formd_people p ON p.accession = x.accession AND p.seq = x.seq
                                        WHERE pt.cluster_id = %s LIMIT 50""", (cluster_id,)).fetchall()
            return _section(conn, "person", str(cluster_id), name, roles)
    except Exception:  # noqa: BLE001
        log.exception("registration person %s", cluster_id)
        return {"people": [], "firms": [], "links": search_links(name), "name": name}


def for_party(party_id: int, kind: str, name: str, roles: list) -> dict | None:
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            return _section(conn, "formd" if kind == "person" else "formd_entity", str(party_id), name,
                            roles if kind == "person" else None)
    except Exception:  # noqa: BLE001
        log.exception("registration party %s", party_id)
        return None


def for_org(ein: str, name: str) -> dict | None:
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            s = _section(conn, "org", ein, name)
            return s if s["firms"] else None          # nonprofits: shown only when one is a registered firm
    except Exception:  # noqa: BLE001
        return None


def search_people(name: str, state: str | None = None, limit: int = 10) -> list[dict]:
    """IARs by name: the exact normalized name first, else first and last name."""
    from app.names import normalize_name
    n = normalize_name(name or "")
    if not n:
        return []
    parts = n.split()
    with db.conn() as conn:
        rows = conn.execute("SELECT crd FROM iapd_individuals WHERE name_norm = %s LIMIT 50", (n,)).fetchall()
        if not rows and len(parts) >= 2:
            rows = conn.execute("""SELECT crd FROM iapd_individuals WHERE lower(last_name) = %s AND lower(first_name) = %s
                                   LIMIT 50""", (parts[-1], parts[0])).fetchall()
        out = [x for x in (individual(conn, r["crd"]) for r in rows) if x]
    if state:
        out = [x for x in out if state in (x["states"] or [])] or out
    return out[:limit]


def search_firms(q: str, limit: int = 10) -> list[dict]:
    """Registered firms whose name or other business name (DBA) is q."""
    from loader.recalls import core
    c = core(q or "")
    if len(c) < 3:
        return []
    try:
        with db.conn() as conn:
            hits = conn.execute("""SELECT DISTINCT kind, key, alias, source FROM sec_firm_aliases WHERE alias_norm = %s
                                   LIMIT %s""", (c, limit)).fetchall() or \
                conn.execute("""SELECT DISTINCT ON (kind, key) kind, key, alias, source FROM sec_firm_aliases
                                WHERE alias_norm LIKE %s ORDER BY kind, key, length(alias_norm) LIMIT %s""",
                             (c + " %", limit)).fetchall()
            out = []
            for h in hits:
                f = firm(conn, h["kind"], h["key"])
                if f:
                    out.append({**f, "matched": h["alias"], "source": h["source"]})
            return out
    except Exception:  # noqa: BLE001
        return []


def answer(name: str, state: str | None = None) -> dict:
    """The plain-English question: "Is Jake Crowley a registered broker?"."""
    firmish = bool(re.search(r"&|\b(co|inc|llc|lp|corp|company|securities|financial|capital|advisors?|advisers?|"
                             r"partners|group|investments?|wealth|management|bank|trust)\b\.?", name or "", re.I))
    firms = search_firms(name)
    people = [] if firmish and firms else search_people(name, state)
    return {"kind": "registration", "name": name, "people": people, "firms": firms, "links": search_links(name)}
