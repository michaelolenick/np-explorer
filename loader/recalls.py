"""Food recalls: FDA food enforcement reports (openFDA bulk download, every report since 2012), loaded whole each
night (about 30,000 rows), then the recalling firms and their links to the rest of the site.

Firms: one per normalized name and state (core(): lower case, punctuation and legal endings like Inc and LLC
dropped). firm_id is a hash of that key, so a firm's URL survives reloads.

Links (food_recall_links), by the same normalized name, and the state where both sides have one:
  org        a nonprofit filer (organizations)
  lobbying   a lobbying client (lda_filings)
  sec        an SEC issuer (sec_insider_filings; no state there)
  fed        a federal award recipient (usa_awards, through its recipient_name index)
  pac        a political committee the firm sponsors (fec_committees.connected_org)
The match counts print at the end, and the totals that feed the boards (federal contracts, contracts from the
Department of Agriculture and the Defense Logistics Agency, lobbying spending, a sponsored PAC) are kept on the
firm row.

USDA FSIS meat, poultry and egg recalls: not loaded. FSIS's site refuses scripted requests (403 to every
non-browser client), and we don't disguise ours; see FSIS_NOTE.

Usage: .venv/bin/python -m loader.recalls
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import time
import zipfile

import httpx

from loader import db

LISTING = "https://api.fda.gov/download.json"
UA = "furp.org research michael@furp.org"
EVENT_URL = "https://www.accessdata.fda.gov/scripts/ires/index.cfm?Event={}"
DATA_URL = 'https://api.fda.gov/food/enforcement.json?search=recall_number:"{}"'
FSIS_NOTE = "USDA FSIS recalls are not included yet: FSIS's website refuses automated requests."
LEGAL = {"inc", "incorporated", "llc", "l", "c", "co", "corp", "corporation", "company", "ltd", "limited", "lp",
         "llp", "plc", "pllc", "the"}
FOOD_AGENCIES = ("Department of Agriculture", "Defense Logistics Agency")
COLS = ["source", "recall_number", "event_id", "status", "classification", "product_type", "recalling_firm",
        "firm_id", "address", "city", "state", "country", "postal_code", "product_description", "product_quantity",
        "reason_for_recall", "distribution_pattern", "voluntary_mandated", "initial_firm_notification", "code_info",
        "recall_initiation_date", "center_classification_date", "report_date", "termination_date", "source_url",
        "data_url"]


def core(name: str | None) -> str:
    """A firm name for matching: "WinCo Foods, LLC" and "Winco Foods LLC" are "winco foods"."""
    s = (name or "").lower().replace("&", " and ")
    s = re.split(r"\b(?:d/?b/?a|doing business as|a/?k/?a)\b", s)[0]
    words = re.sub(r"[^a-z0-9]+", " ", s).split()
    while words and words[-1] in LEGAL:
        words.pop()
    while words and words[0] == "the":
        words.pop(0)
    return " ".join(words)


def firm_id(name: str, state: str | None) -> str:
    return hashlib.sha1(f"{core(name)}|{(state or '').upper()}".encode()).hexdigest()[:10]


def _date(v: str | None) -> dt.date | None:
    v = (v or "").strip()
    return dt.date(int(v[:4]), int(v[4:6]), int(v[6:8])) if re.fullmatch(r"\d{8}", v) else None


def _clean(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return None if v in ("", "N/A") else v


def fetch_fda(status=print) -> list[dict]:
    with httpx.Client(timeout=300, headers={"User-Agent": UA}, follow_redirects=True) as c:
        parts = c.get(LISTING).json()["results"]["food"]["enforcement"]["partitions"]
        rows = []
        for p in parts:
            z = zipfile.ZipFile(io.BytesIO(c.get(p["file"]).content))
            for n in z.namelist():
                rows += json.loads(z.read(n))["results"]
    status(f"recalls: {len(rows):,} FDA food enforcement reports downloaded")
    return rows


def _row(r: dict) -> tuple:
    firm = (r.get("recalling_firm") or "").strip()
    state = _clean(r.get("state"))
    addr = ", ".join(x for x in (_clean(r.get("address_1")), _clean(r.get("address_2"))) if x) or None
    return ("fda", r["recall_number"], _clean(r.get("event_id")), _clean(r.get("status")),
            _clean(r.get("classification")), _clean(r.get("product_type")), firm, firm_id(firm, state), addr,
            _clean(r.get("city")), state, _clean(r.get("country")), _clean(r.get("postal_code")),
            _clean(r.get("product_description")), _clean(r.get("product_quantity")),
            _clean(r.get("reason_for_recall")), _clean(r.get("distribution_pattern")),
            _clean(r.get("voluntary_mandated")), _clean(r.get("initial_firm_notification")), _clean(r.get("code_info")),
            _date(r.get("recall_initiation_date")), _date(r.get("center_classification_date")),
            _date(r.get("report_date")), _date(r.get("termination_date")),
            EVENT_URL.format(r["event_id"]) if r.get("event_id") else None, DATA_URL.format(r["recall_number"]))


def load(status=print) -> int:
    rows = [_row(r) for r in fetch_fda(status) if r.get("recall_number") and r.get("recalling_firm")]
    with db.connect() as conn:
        conn.execute("DELETE FROM food_recalls WHERE source = 'fda'")
        with conn.cursor() as cur, cur.copy(f"COPY food_recalls ({', '.join(COLS)}) FROM STDIN") as cp:
            for r in rows:
                cp.write_row(r)
        conn.commit()
        conn.execute("ANALYZE food_recalls")
        conn.commit()
    status(f"recalls: {len(rows):,} FDA rows loaded")
    return len(rows)


def build_firms(status=print) -> dict:
    """food_recall_firms and food_recall_links from food_recalls; returns the match counts by kind."""
    t0 = time.time()
    with db.connect() as conn:
        firms = conn.execute("""
            SELECT firm_id, (array_agg(recalling_firm ORDER BY recall_initiation_date DESC NULLS LAST))[1] AS name,
                   (array_agg(city ORDER BY recall_initiation_date DESC NULLS LAST))[1] AS city,
                   (array_agg(state ORDER BY recall_initiation_date DESC NULLS LAST))[1] AS state,
                   count(*) AS recalls, count(DISTINCT event_id) AS events,
                   count(*) FILTER (WHERE classification = 'Class I') AS c1,
                   count(*) FILTER (WHERE classification = 'Class II') AS c2,
                   count(*) FILTER (WHERE classification = 'Class III') AS c3,
                   min(recall_initiation_date) AS first, max(recall_initiation_date) AS last
            FROM food_recalls GROUP BY firm_id""").fetchall()
        by_core: dict[str, list] = {}
        for f in firms:
            by_core.setdefault(core(f[1]), []).append(f)

        def matches(name, state):
            """Firms with this normalized name, in this state when both have one."""
            return [f for f in by_core.get(core(name), []) if not state or not f[3] or f[3] == state]

        links: set = set()
        # Nonprofits: organizations.name_norm is lower case with punctuation removed, legal endings kept, so ask
        # for each firm's name with the common endings and check the core afterward.
        forms = set()
        for c in by_core:
            forms.update({c, f"{c} inc", f"{c} llc", f"{c} co", f"{c} corp", f"{c} corporation", f"{c} company",
                          f"the {c}", f"{c} incorporated", f"{c} ltd"})
        for ein, name, state in conn.execute("SELECT ein, name, state FROM organizations WHERE name_norm = ANY(%s)",
                                             (sorted(forms),)).fetchall():
            for f in matches(name, state):
                links.add((f[0], "org", ein, name))
        for cid, name, state in conn.execute("""SELECT DISTINCT ON (client_id) client_id::text, client_name, client_state
                                                FROM lda_filings ORDER BY client_id, dt_posted DESC NULLS LAST""").fetchall():
            for f in matches(name, state):
                links.add((f[0], "lobbying", cid, name))
        for cik, name in conn.execute("""SELECT DISTINCT ON (issuer_cik) issuer_cik, issuer_name FROM sec_insider_filings
                                         WHERE issuer_cik IS NOT NULL ORDER BY issuer_cik, filing_date DESC""").fetchall():
            for f in matches(name, None):
                links.add((f[0], "sec", cik.lstrip("0") or "0", name))
        for cid, name, state in conn.execute("""SELECT DISTINCT ON (cmte_id) cmte_id, connected_org, state FROM fec_committees
                                                WHERE connected_org IS NOT NULL AND connected_org NOT IN ('NONE', 'N/A')
                                                ORDER BY cmte_id, cycle DESC""").fetchall():
            # A one-word sponsor name ("SESSIONS") is too common to trust without the same state.
            for f in matches(name, state if " " not in core(name) else None):
                links.add((f[0], "pac", cid, name))
        # Federal award recipients: USAspending names are upper case, as filed; try the usual spellings.
        names = set()
        for f in firms:
            n = re.sub(r"\s+", " ", f[1].upper().strip())
            bare = re.sub(r"[.,]", "", n)
            c = core(f[1]).upper()
            names.update({n, bare, c, f"{c} INC", f"{c}, INC.", f"{c} INC.", f"{c} LLC", f"{c}, LLC", f"{c} CO",
                          f"{c} CORP", f"{c} CORPORATION", f"{c} COMPANY", f"{c} LTD"})
        conn.execute("SET statement_timeout = '10min'")
        fed = conn.execute("""
            SELECT recipient_name, state, recipient_uei, sum(obligation) FILTER (WHERE kind = 'contract') AS contracts,
                   sum(obligation) FILTER (WHERE kind = 'contract' AND (agency = ANY(%s) OR sub_agency = ANY(%s))) AS food
            FROM usa_awards WHERE recipient_name = ANY(%s) GROUP BY 1, 2, 3""",
                           (list(FOOD_AGENCIES), list(FOOD_AGENCIES), sorted(names))).fetchall()
        fed_tot: dict[str, list] = {}
        for name, state, uei, contracts, food in fed:
            for f in matches(name, state):
                links.add((f[0], "fed", uei or name, name))
                t = fed_tot.setdefault(f[0], [0, 0])
                t[0] += float(contracts or 0)
                t[1] += float(food or 0)
        lobby = {r[0]: float(r[1] or 0) for r in conn.execute("""
            SELECT l.firm_id, sum(coalesce(f.income, 0) + coalesce(f.expenses, 0))
            FROM (SELECT DISTINCT firm_id, key::int AS client_id FROM unnest(%s::text[], %s::text[]) AS l(firm_id, key)) l
            JOIN lda_filings f ON f.client_id = l.client_id GROUP BY 1""",
            ([x[0] for x in links if x[1] == "lobbying"], [x[2] for x in links if x[1] == "lobbying"])).fetchall()}
        pacs = {x[0] for x in links if x[1] == "pac"}
        conn.execute("TRUNCATE food_recall_firms, food_recall_links")
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO food_recall_firms (firm_id, firm_key, name, city, state, recalls, events, class1,
                               class2, class3, first_recall, last_recall, fed_contracts, fed_food_contracts, lobby_spent,
                               has_pac) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            [(f[0], f"{core(f[1])}|{f[3] or ''}", f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9],
                              f[10], (fed_tot.get(f[0]) or [None, None])[0], (fed_tot.get(f[0]) or [None, None])[1],
                              lobby.get(f[0]), f[0] in pacs) for f in firms])
            cur.executemany("INSERT INTO food_recall_links (firm_id, kind, key, name) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT DO NOTHING", sorted(links))
        conn.commit()
    counts = {k: len({x[0] for x in links if x[1] == k}) for k in ("org", "lobbying", "sec", "fed", "pac")}
    status(f"recalls: {len(firms):,} firms; matched to nonprofits {counts['org']:,}, lobbying clients "
           f"{counts['lobbying']:,}, SEC issuers {counts['sec']:,}, federal award recipients {counts['fed']:,}, "
           f"political committees {counts['pac']:,} ({time.time() - t0:.0f}s)")
    return {"firms": len(firms), **counts}


def run(status=print) -> dict:
    load(status)
    return build_firms(status)


if __name__ == "__main__":
    run()
