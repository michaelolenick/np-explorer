"""State business registries: entities, officers and principals, registered agents and other names (DBAs, trade
names), from each state's official free bulk data (owner, 2026-10-23).

Sources (official open-data portals, Socrata SODA API, paged; no login, no CAPTCHA):
  NY  data.ny.gov n9v6-gdp6   active corporations since 1800: entity, agent, chairman (monthly)
  CO  data.colorado.gov 4ykn-tg5h   every entity, all statuses, with agent (daily); u7sb-g482 trade names
  CT  data.ct.gov n7gp-d28j   business master (daily); ka36-64k6 principals; qh2m-n44y registered agents
  OR  data.oregon.gov tckn-sxa6   active entities: principal place, agent, authorized representatives (weekly)
  PA  data.pa.gov xvd7-5r2c   current registrations with their officers and parties (monthly)
  TX  data.texas.gov 9cir-efmm   active franchise taxpayers (the Comptroller's list, with the SOS file number and
      status; the Secretary of State sells its own data); jrea-zgmq sales tax outlets (trade names)
  FL  Sunbiz quarterly corporate file (cordata.zip, fixed width, up to six officers): parsed from
      /bulk/registry/fl/ when the file is there. The state's download server needs a login (published by the state
      for public use), which FURP's automation doesn't enter; the owner places the file.

Each source replaces its own rows: entities it no longer lists are dropped; people and names are reloaded.
lookup() asks the same APIs for a name the local copy doesn't have (a cache miss) and keeps every result.

Usage: .venv/bin/python -m loader.business_registry [source ...] | links | lookup NAME
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from loader import db

UA = "furp.org research michael@furp.org"
PAGE = 50000
FL_DIR = Path("/bulk/registry/fl")


def _date(v):
    v = (v or "").strip()
    if re.match(r"\d{4}-\d\d-\d\d", v):
        try:
            return dt.date.fromisoformat(v[:10])
        except ValueError:
            return None
    if re.fullmatch(r"\d{8}", v):            # Florida: MMDDYYYY
        try:
            return dt.date(int(v[4:]), int(v[:2]), int(v[2:4]))
        except ValueError:
            return None
    return None


def _join(*parts) -> str | None:
    s = " ".join(p.strip() for p in parts if p and str(p).strip())
    return s or None


def _get_json(url: str, tries: int = 5):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"}),
                                        timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise
            time.sleep(10 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"no answer: {url[:120]}")


def socrata(domain: str, dataset: str, where: str | None = None, limit: int | None = None):
    """Every row of a Socrata dataset, paged in :id order (stable while the dataset is being updated)."""
    offset = 0
    while True:
        q = {"$limit": PAGE if not limit else min(PAGE, limit - offset), "$offset": offset, "$order": ":id"}
        if where:
            q["$where"] = where
        rows = _get_json(f"https://{domain}/resource/{dataset}.json?" + urllib.parse.urlencode(q))
        yield from rows
        offset += len(rows)
        if len(rows) < q["$limit"] or (limit and offset >= limit):
            return
        time.sleep(0.5)


# --- per-source row mappers: each returns (entity or None, [people], [names]) --------------------------------------

def _person(name, role, address=None, entity=None):
    return {"name": name, "role": role, "address": address, "is_entity": bool(entity)}


def ny(r):
    e = {"entity_id": r.get("dos_id"), "name": r.get("current_entity_name"), "entity_type": r.get("entity_type"),
         "status": "Active", "formed": _date(r.get("initial_dos_filing_date")),
         "street": _join(r.get("location_address_1"), r.get("location_address_2")) or _join(r.get("dos_process_address_1")),
         "city": r.get("location_city") or r.get("dos_process_city"), "addr_state": r.get("location_state") or r.get("dos_process_state"),
         "zip": r.get("location_zip") or r.get("dos_process_zip"), "agent_name": r.get("registered_agent_name"),
         "agent_address": _join(r.get("registered_agent_address_1"), r.get("registered_agent_city"), r.get("registered_agent_state")),
         "jurisdiction": r.get("jurisdiction")}
    people = [_person(r["chairman_name"], "Chairman or chief executive",
                      _join(r.get("chairman_city"), r.get("chairman_state")))] if r.get("chairman_name") else []
    return e, people, []


def co(r):
    agent = r.get("agentorganizationname") or _join(r.get("agentfirstname"), r.get("agentmiddlename"), r.get("agentlastname"))
    return ({"entity_id": r.get("entityid"), "name": r.get("entityname"), "entity_type": r.get("entitytype"),
             "status": r.get("entitystatus"), "formed": _date(r.get("entityformdate")),
             "street": _join(r.get("principaladdress1"), r.get("principaladdress2")), "city": r.get("principalcity"),
             "addr_state": r.get("principalstate"), "zip": r.get("principalzipcode"), "agent_name": agent,
             "agent_address": _join(r.get("agentprincipaladdress1"), r.get("agentprincipalcity"), r.get("agentprincipalstate")),
             "jurisdiction": r.get("jurisdictonofformation")}, [], [])


def co_names(r):
    return ({"entity_id": r.get("entityid")} if r.get("entityid") else None, [],
            [{"name": r.get("tradenamedescription"), "kind": "Trade name"}] if r.get("tradenamedescription") else [])


def ct(r):
    return ({"entity_id": r.get("id"), "name": r.get("name"), "entity_type": r.get("business_type"),
             "status": _join(r.get("status"), r.get("sub_status") and f"({r['sub_status']})"),
             "formed": _date(r.get("date_registration")), "street": r.get("billingstreet"), "city": r.get("billingcity"),
             "addr_state": r.get("billingstate"), "zip": r.get("billingpostalcode"),
             "jurisdiction": r.get("state_or_territory_formation") or r.get("country_formation")}, [], [])


def ct_principals(r):
    name = r.get("name__c") or _join(r.get("firstname"), r.get("middlename"), r.get("lastname"), r.get("suffix"))
    return ({"entity_id": r.get("business_id")} if r.get("business_id") else None,
            [_person(name, r.get("designation") or "Principal", _join(r.get("business_city"), r.get("business_state")),
                     entity=not r.get("lastname"))] if name else [], [])


def ct_agents(r):
    name = r.get("name__c") or _join(r.get("firstname"), r.get("middlename"), r.get("lastname"))
    return ({"entity_id": r.get("business_id")} if r.get("business_id") else None,
            [_person(name, "Registered agent", _join(r.get("business_city"), r.get("business_state")),
                     entity=not r.get("lastname"))] if name else [], [])


def or_(r):
    kind = r.get("associated_name_type") or ""
    e = {"entity_id": r.get("registry_number"), "name": r.get("business_name"), "entity_type": r.get("entity_type"),
         "status": "Active", "formed": _date(r.get("registry_date")), "jurisdiction": r.get("jurisdiction")}
    if kind == "PRINCIPAL PLACE OF BUSINESS":
        e.update(street=_join(r.get("address"), r.get("address_continued")), city=r.get("city"), addr_state=r.get("state"),
                 zip=r.get("zip"))
    name = r.get("entity_of_record_name") or _join(r.get("first_name"), r.get("middle_name"), r.get("last_name"), r.get("suffix"))
    people = []
    if kind in ("REGISTERED AGENT", "AUTHORIZED REPRESENTATIVE", "PRESIDENT", "SECRETARY", "MEMBER", "MANAGER") and name:
        people.append(_person(name, kind.title(), _join(r.get("city"), r.get("state")), entity=bool(r.get("entity_of_record_name"))))
    return e, people, []


def pa(r):
    name = _join(r.get("first_name"), r.get("middle_name"), r.get("last_name"))
    return ({"entity_id": r.get("filing_number"), "name": r.get("business_name"),
             "entity_type": r.get("typeofbusinessregistration"), "status": "Current", "formed": _date(r.get("creationdate")),
             "street": _join(r.get("address_line1"), r.get("address_line2")), "city": r.get("city"),
             "addr_state": r.get("state"), "zip": r.get("zip")},
            [_person(name, r.get("party_type") or "Party")] if name else [], [])


def tx(r):
    return ({"entity_id": r.get("taxpayer_number"), "name": r.get("taxpayer_name"),
             "entity_type": r.get("taxpayer_organizational_type"),
             "status": _join("Active franchise taxpayer", r.get("sos_status_code") and f"(SOS status {r['sos_status_code']})"),
             "formed": _date(r.get("sos_charter_date")), "street": r.get("taxpayer_address"), "city": r.get("taxpayer_city"),
             "addr_state": r.get("taxpayer_state"), "zip": r.get("taxpayer_zip"),
             "jurisdiction": _join("SOS file", r.get("secretary_of_state_sos_or_coa_file_number"))}, [], [])


def tx_outlets(r):
    on = (r.get("outlet_name") or "").strip()
    return ({"entity_id": r.get("taxpayer_number")} if r.get("taxpayer_number") else None, [],
            [{"name": on, "kind": "Trade name (sales tax outlet)"}] if on and on.upper() != (r.get("taxpayer_name") or "").upper() else [])


# (source, state, domain, dataset, mapper, kind): kind "entities" replaces the state's entities from that source,
# "people" / "names" reload that source's people or names.
SOURCES = [
    ("ny", "NY", "data.ny.gov", "n9v6-gdp6", ny, "entities"),
    ("co", "CO", "data.colorado.gov", "4ykn-tg5h", co, "entities"),
    ("co_names", "CO", "data.colorado.gov", "u7sb-g482", co_names, "names"),
    ("ct", "CT", "data.ct.gov", "n7gp-d28j", ct, "entities"),
    ("ct_principals", "CT", "data.ct.gov", "ka36-64k6", ct_principals, "people"),
    ("ct_agents", "CT", "data.ct.gov", "qh2m-n44y", ct_agents, "people"),
    ("or", "OR", "data.oregon.gov", "tckn-sxa6", or_, "entities"),
    ("pa", "PA", "data.pa.gov", "xvd7-5r2c", pa, "entities"),
    ("tx", "TX", "data.texas.gov", "9cir-efmm", tx, "entities"),
    ("tx_outlets", "TX", "data.texas.gov", "jrea-zgmq", tx_outlets, "names"),
]
NAME_FIELD = {"ny": "current_entity_name", "co": "entityname", "ct": "name", "or": "business_name", "pa": "business_name",
              "tx": "taxpayer_name"}
ECOLS = ["state", "entity_id", "name", "name_core", "entity_type", "status", "formed", "street", "city", "addr_state",
         "zip", "agent_name", "agent_address", "jurisdiction", "source"]


def _flush(conn, state, source, ents, people, names, replace_people=False):
    from app.names import normalize_name
    from loader.recalls import core
    if ents:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS be (LIKE biz_entities INCLUDING DEFAULTS)")
        conn.execute("TRUNCATE be")
        with conn.cursor() as cur, cur.copy(f"COPY be ({', '.join(ECOLS)}) FROM STDIN") as cp:
            for e in ents.values():
                cp.write_row([state, e["entity_id"], (e.get("name") or "")[:500], core(e.get("name"))[:500]] +
                             [(str(e[c])[:500] if e.get(c) is not None and not isinstance(e[c], dt.date) else e.get(c))
                              for c in ECOLS[4:14]] + [source])
        conn.execute(f"""INSERT INTO biz_entities ({', '.join(ECOLS)}, loaded)
                         SELECT {', '.join(ECOLS)}, now() FROM be
                         ON CONFLICT (state, entity_id) DO UPDATE SET
                         {', '.join(f"{c} = coalesce(excluded.{c}, biz_entities.{c})" for c in ECOLS[2:])}, loaded = now()""")
    if people:
        with conn.cursor() as cur, cur.copy("COPY biz_people (state, entity_id, name, name_norm, role, is_entity, address, source) FROM STDIN") as cp:
            for eid, p in people:
                cp.write_row((state, eid, p["name"][:300], None if p["is_entity"] else (normalize_name(p["name"]) or None),
                              (p["role"] or "")[:100], p["is_entity"], (p.get("address") or "")[:300] or None, source))
    if names:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS bn (LIKE biz_names)")
        conn.execute("TRUNCATE bn")
        with conn.cursor() as cur, cur.copy("COPY bn FROM STDIN") as cp:
            for eid, n in names:
                cp.write_row((state, eid, n["name"][:300], core(n["name"])[:300], n["kind"], source))
        conn.execute("INSERT INTO biz_names SELECT * FROM bn ON CONFLICT DO NOTHING")
    conn.commit()


def load(source: str, status=print, limit: int | None = None) -> int:
    src = next(s for s in SOURCES if s[0] == source)
    name, state, domain, dataset, mapper, kind = src
    start = dt.datetime.now(dt.timezone.utc)
    n = 0
    with db.connect() as conn:
        if kind == "people":
            conn.execute("DELETE FROM biz_people WHERE source = %s", (name,))
        if kind == "names":
            conn.execute("DELETE FROM biz_names WHERE source = %s", (name,))
        if kind == "entities":
            conn.execute("DELETE FROM biz_people WHERE source = %s", (name,))
        conn.commit()
        ents, people, names = {}, [], []
        for r in socrata(domain, dataset, limit=limit):
            r = {k: v.strip() if isinstance(v, str) else v for k, v in r.items()}
            e, ps, ns = mapper(r)
            if not e or not e.get("entity_id"):
                continue
            eid = str(e["entity_id"]).strip()
            if kind == "entities" and e.get("name"):
                prev = ents.get(eid)
                ents[eid] = {**(prev or {}), **{k: v for k, v in e.items() if v is not None}}
            people += [(eid, p) for p in ps]
            names += [(eid, x) for x in ns]
            n += 1
            if n % 20000 == 0:
                _flush(conn, state, name, ents, people, names)
                ents, people, names = {}, [], []
            if n % 500000 == 0:
                status(f"business registry {name}: {n:,} rows")
        _flush(conn, state, name, ents, people, names)
        if kind == "entities" and not limit:
            # Entities this source no longer lists (dissolved, or dropped from an active-only list).
            gone = conn.execute("DELETE FROM biz_entities WHERE source = %s AND loaded < %s", (name, start)).rowcount
            status(f"business registry {name}: {gone:,} entities no longer listed, removed")
        conn.execute("""INSERT INTO biz_runs (source, rows) VALUES (%s, %s)
                        ON CONFLICT (source) DO UPDATE SET loaded = now(), rows = excluded.rows""", (name, n))
        conn.commit()
    status(f"business registry {name}: {n:,} rows loaded")
    return n


# --- Florida (a file the owner places) ---------------------------------------------------------------------------

def florida(status=print) -> int:
    """Sunbiz quarterly corporate data (cordata.zip or its cordata*.txt files): 1440-character records."""
    import zipfile
    files = sorted(FL_DIR.glob("cordata*.zip")) + sorted(FL_DIR.glob("cordata*.txt"))
    if not files:
        status("business registry fl: no file in /bulk/registry/fl (place cordata.zip from the Sunbiz quarterly data)")
        return 0
    start = dt.datetime.now(dt.timezone.utc)

    def lines():
        for f in files:
            if f.suffix == ".zip":
                z = zipfile.ZipFile(f)
                for nm in sorted(z.namelist()):
                    with z.open(nm) as fh:
                        for line in fh:
                            yield line.decode("latin-1")
            else:
                with open(f, encoding="latin-1") as fh:
                    yield from fh

    def fld(s, a, n):
        return s[a - 1:a - 1 + n].strip() or None
    n = 0
    with db.connect() as conn:
        conn.execute("DELETE FROM biz_people WHERE source = 'fl'")
        conn.commit()
        ents, people = {}, []
        for s in lines():
            if len(s) < 668:
                continue
            eid = fld(s, 1, 12)
            if not eid:
                continue
            ents[eid] = {"entity_id": eid, "name": fld(s, 13, 192), "status": {"A": "Active", "I": "Inactive"}.get(fld(s, 205, 1) or "", fld(s, 205, 1)),
                         "entity_type": fld(s, 206, 15), "street": _join(fld(s, 221, 42), fld(s, 263, 42)),
                         "city": fld(s, 305, 28), "addr_state": fld(s, 333, 2), "zip": fld(s, 335, 10),
                         "formed": _date(fld(s, 473, 8)), "agent_name": fld(s, 545, 42),
                         "agent_address": _join(fld(s, 588, 42), fld(s, 630, 28), fld(s, 658, 2))}
            for k in range(6):
                o = 669 + 128 * k
                title, kind, oname = fld(s, o, 4), fld(s, o + 4, 1), fld(s, o + 5, 42)
                if oname:
                    people.append((eid, _person(oname, title or "Officer", _join(fld(s, o + 89, 28), fld(s, o + 117, 2)),
                                                entity=(kind == "C"))))
            n += 1
            if n % 20000 == 0:
                _flush(conn, "FL", "fl", ents, people, [])
                ents, people = {}, []
        _flush(conn, "FL", "fl", ents, people, [])
        conn.execute("DELETE FROM biz_entities WHERE source = 'fl' AND loaded < %s", (start,))
        conn.execute("""INSERT INTO biz_runs (source, rows) VALUES ('fl', %s)
                        ON CONFLICT (source) DO UPDATE SET loaded = now(), rows = excluded.rows""", (n,))
        conn.commit()
    status(f"business registry fl: {n:,} entities")
    return n


# --- on-demand lookups -------------------------------------------------------------------------------------------

def lookup(name: str, status=print, timeout: float = 6.0) -> int:
    """Ask each state API, in parallel, for entities whose name starts with `name`: only states not asked about this
    name in the last 30 days (biz_lookups), so each lookup happens on a cache miss. Every result is kept."""
    from concurrent.futures import ThreadPoolExecutor
    from loader.recalls import core
    c = core(name)
    if len(c) < 3:
        return 0
    safe = re.sub(r"[^A-Z0-9 &.,'-]", "", name.upper()).strip().replace("'", "''")
    with db.connect() as conn:
        asked = {r[0] for r in conn.execute("""SELECT state FROM biz_lookups WHERE query_core = %s
                                               AND asked > now() - interval '30 days'""", (c,)).fetchall()}
    todo = [s for s in SOURCES if s[5] == "entities" and s[1] not in asked]

    def ask(src):
        source, state, domain, dataset, mapper, kind = src
        q = {"$limit": 200, "$where": f"upper({NAME_FIELD[source]}) like '{safe}%'"}
        url = f"https://{domain}/resource/{dataset}.json?" + urllib.parse.urlencode(q)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                return src, json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            status(f"lookup {state}: {type(e).__name__}")
            return src, None
    with ThreadPoolExecutor(max_workers=6) as pool:
        answers = list(pool.map(ask, todo))
    found = 0
    with db.connect() as conn:
        for (source, state, domain, dataset, mapper, kind), rows in answers:
            if rows is None:
                continue
            ents, people = {}, []
            for r in rows:
                r = {k: v.strip() if isinstance(v, str) else v for k, v in r.items()}
                e, ps, ns = mapper(r)
                if e and e.get("entity_id") and e.get("name"):
                    eid = str(e["entity_id"]).strip()
                    ents[eid] = {**ents.get(eid, {}), **{k: v for k, v in e.items() if v is not None}}
                    people += [(eid, p) for p in ps]
            _flush(conn, state, source, ents, people, [])
            conn.execute("""INSERT INTO biz_lookups (query_core, state, found) VALUES (%s, %s, %s)
                            ON CONFLICT (query_core, state) DO UPDATE SET asked = now(), found = excluded.found""",
                         (c, state, len(ents)))
            conn.commit()
            found += len(ents)
    return found


# --- links -------------------------------------------------------------------------------------------------------

def links(status=print) -> dict:
    """Entities to nonprofits, Form D issuers, Form ADV advisers, SEC filers and contractors (the same business
    name in the same state, held by one record on each side); officers to people (sec-style: unique full name
    with a middle part, in one of the person's states); other names into the firm alias table."""
    with db.connect() as conn:
        conn.execute("SET work_mem = '1GB'")
        conn.execute("TRUNCATE biz_links")
        conn.execute("""CREATE TEMP TABLE ue AS SELECT name_core, addr_state, min(state) AS state, min(entity_id) AS entity_id
                        FROM biz_entities WHERE name_core <> '' GROUP BY 1, 2 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON ue (name_core, addr_state)")
        n = {}
        from loader.recalls import core
        # Nonprofits (core computed in Python: organizations has no core column).
        orgs = conn.execute("SELECT ein, name, state FROM organizations WHERE name IS NOT NULL").fetchall()
        conn.execute("CREATE TEMP TABLE oc (ein text, core text, state text)")
        with conn.cursor() as cur, cur.copy("COPY oc FROM STDIN") as cp:
            for ein, name, st in orgs:
                cp.write_row((ein, core(name), st))
        for kind, sql in (
            ("org", "SELECT ein AS key, core, state FROM oc"),
            ("formd", "SELECT DISTINCT ON (cik) cik AS key, NULL AS core, state, issuer_name AS name FROM sec_formd_offerings ORDER BY cik, latest_date DESC"),
            ("adv", "SELECT DISTINCT ON (crd) crd AS key, NULL AS core, state, coalesce(business_name, legal_name) AS name FROM adv_filings WHERE crd IS NOT NULL ORDER BY crd, submitted DESC NULLS LAST"),
            ("sec", "SELECT DISTINCT ON (cik) cik AS key, NULL AS core, NULL AS state, name FROM sec_fin_subs ORDER BY cik, filed DESC"),
        ):
            rows = conn.execute(sql).fetchall()
            conn.execute("DROP TABLE IF EXISTS lk")
            conn.execute("CREATE TEMP TABLE lk (key text, core text, state text)")
            with conn.cursor() as cur, cur.copy("COPY lk FROM STDIN") as cp:
                for r in rows:
                    c = r[1] if kind == "org" else core(r[3])
                    if c:
                        cp.write_row((str(r[0]), c, r[2]))
            if kind == "sec":      # SEC filers have no state here: the name must be unique nationally
                cnt = conn.execute("""INSERT INTO biz_links SELECT e.state, e.entity_id, 'sec', lk.key, 'business name'
                                      FROM lk JOIN (SELECT name_core, min(state) AS state, min(entity_id) AS entity_id
                                                    FROM biz_entities GROUP BY 1 HAVING count(*) = 1) e ON e.name_core = lk.core
                                      ON CONFLICT DO NOTHING""").rowcount
            else:
                cnt = conn.execute(f"""INSERT INTO biz_links SELECT ue.state, ue.entity_id, '{kind}', lk.key, 'business name and state'
                                       FROM lk JOIN ue ON ue.name_core = lk.core AND ue.addr_state = lk.state
                                       ON CONFLICT DO NOTHING""").rowcount
            n[kind] = cnt
        n["person"] = conn.execute("""INSERT INTO biz_links SELECT DISTINCT ON (p.state, p.entity_id, u.id) p.state, p.entity_id, 'person', u.id::text, 'officer name and state'
                                      FROM biz_people p JOIN (SELECT name_norm, min(id) AS id, min(states) AS states FROM person_clusters
                                                              WHERE NOT is_institution AND name_norm ~ '^\\S+ \\S+ \\S+'
                                                              GROUP BY 1 HAVING count(*) = 1) u ON u.name_norm = p.name_norm
                                      JOIN biz_entities e ON e.state = p.state AND e.entity_id = p.entity_id
                                      WHERE NOT p.is_entity AND coalesce(e.addr_state, e.state) = ANY(u.states)
                                      ON CONFLICT DO NOTHING""").rowcount
        # Other names into the firm alias table, so a trade-name search finds the registered business.
        conn.execute("DELETE FROM sec_firm_aliases WHERE kind = 'biz'")
        n["aliases"] = conn.execute("""INSERT INTO sec_firm_aliases (alias_norm, alias, kind, key, source)
                                       SELECT DISTINCT ON (name_core, state || ':' || entity_id) name_core, name, 'biz',
                                              state || ':' || entity_id, kind
                                       FROM biz_names WHERE name_core <> '' ON CONFLICT DO NOTHING""").rowcount
        conn.commit()
        for t in ("biz_entities", "biz_people", "biz_names", "biz_links"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
    status("business registry links: " + ", ".join(f"{k} {v:,}" for k, v in n.items()))
    return n


def run(status=print) -> None:
    for s in SOURCES:
        try:
            load(s[0], status)
        except Exception as e:  # noqa: BLE001 - one state failing doesn't stop the rest
            status(f"business registry {s[0]} failed: {type(e).__name__}: {str(e)[:200]}")
    florida(status)
    links(status)


if __name__ == "__main__":
    args = sys.argv[1:] or ["run"]
    if args[0] == "lookup":
        print(lookup(" ".join(args[1:])))
    else:
        for a in args:
            if a in {s[0] for s in SOURCES}:
                load(a)
            else:
                globals()[a]()
