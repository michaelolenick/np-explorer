"""Vendors that are also filing organizations: vendor_org_links, one row per contractor record matched to an EIN.

990 contractor lists give a vendor's name and address but no EIN. A record links to an organization when
  - the address matches one the organization filed from (its BMF/latest address, or the address on any of its
    returns): same zip5, same street number, street names equal or a typo apart (app/address.same_address), and
  - the names match after normalizing (app/address.name_core): the organization's name, a name it filed under,
    or its DBA,
and exactly one EIN qualifies. Two or more qualifying EINs is ambiguous and links nothing.

A vendor's records with no address link too when every addressed record of that vendor name linked to the same
EIN. Candidates come from SQL (same zip5 and street number); the rest is checked in Python.

build() replaces the table in one transaction; report() returns counts and samples for review.
"""

from __future__ import annotations

import difflib
import random
from collections import defaultdict

from psycopg.rows import dict_row

from app import address as A
from loader import db

ZIP5 = r"left(regexp_replace({z}, '\D', '', 'g'), 5)"
# Street number, or "box N" for a PO box: the SQL side of address.street_parts, used only to find candidates.
NUM = (r"""CASE WHEN {s} ~* '^\s*(p\.?\s*o\.?\s*|post\s+office\s+)?box\s*#?\s*\d'
               THEN 'box ' || substring({s} from '(?i)box\s*#?\s*(\d+)')
               ELSE substring({s} from '^\s*(\d+)') END""")

CANDIDATES = f"""
WITH v AS (
    SELECT id, name_raw, name_norm, street, city, state, zip, {ZIP5.format(z='zip')} AS z5,
           {NUM.format(s='street')} AS num
    FROM contractors WHERE street ~ '\\d' AND zip ~ '\\d{{5}}'),
o AS (
    SELECT DISTINCT ein, name, dba, street, zip FROM (
        SELECT ein, name, dba, street, zip FROM organizations
        UNION ALL
        SELECT ein, org_name, dba, street, zip FROM filings) x
    WHERE street ~ '\\d' AND zip ~ '\\d{{5}}'),
ok AS (SELECT o.*, {ZIP5.format(z='zip')} AS z5, {NUM.format(s='street')} AS num FROM o)
SELECT v.id, v.name_raw, v.name_norm, v.street, v.city, v.state, v.zip,
       ok.ein, ok.name AS org_name, ok.dba, ok.street AS org_street, ok.zip AS org_zip
FROM v JOIN ok ON ok.z5 = v.z5 AND ok.num = v.num
"""


def _score(rows):
    """Per contractor id: confident EINs; near misses of two kinds: same address with a similar but different
    name ("name"), and same name, zip5 and number with street names too far apart ("street")."""
    hits: dict[int, set] = defaultdict(set)
    near: list[dict] = []
    vendor: dict[int, dict] = {}
    for r in rows:
        vk, ok = A.key(r["street"], r["zip"]), A.key(r["org_street"], r["org_zip"])
        v = A.name_core(r["name_raw"])
        # A DBA that is a care-of line names the mail agent (a law firm, a bank), not the organization.
        names = {A.name_core(r["org_name"]), "" if A.is_care_of(r["dba"]) else A.name_core(r["dba"])} - {""}
        if not (v and names and vk and ok):
            continue
        same_name = v in names
        if not A.same_address(vk, ok):
            if same_name:
                near.append({**r, "sim": 1.0, "kind": "street"})
            continue
        vendor[r["id"]] = r
        if same_name:
            hits[r["id"]].add(r["ein"])
        else:
            sim = max(difflib.SequenceMatcher(None, v, n).ratio() for n in names)
            if sim >= 0.6:
                near.append({**r, "sim": round(sim, 2), "kind": "name"})
    return hits, near, vendor


def build(status=print) -> dict:
    with db.connect() as conn:
        cur = conn.cursor(name="vendor_org_candidates", row_factory=dict_row)
        cur.itersize = 50_000
        cur.execute(CANDIDATES)
        hits, near, vendor = _score(cur)
        cur.close()
        linked = {cid: next(iter(e)) for cid, e in hits.items() if len(e) == 1}
        ambiguous = {cid: e for cid, e in hits.items() if len(e) > 1}
        # Unaddressed records of a vendor name whose addressed records all linked to one EIN.
        by_name: dict[str, set] = defaultdict(set)
        for cid, ein in linked.items():
            by_name[vendor[cid]["name_norm"]].add(ein)
        single = {n: next(iter(e)) for n, e in by_name.items() if len(e) == 1}
        extra = {}
        if single:
            rows = conn.execute("""
                SELECT c.id, c.name_norm, c.street ~ '\\d' AND c.zip ~ '\\d{5}' AS addressed
                FROM contractors c WHERE c.name_norm = ANY(%s)""", (list(single),)).fetchall()
            unlinked_addressed = {r[1] for r in rows if r[2] and r[0] not in linked}
            for cid, name, addressed in rows:
                if not addressed and name not in unlinked_addressed:
                    extra[cid] = single[name]
        conn.execute("DELETE FROM vendor_org_links")
        with conn.cursor() as c, c.copy("COPY vendor_org_links (contractor_id, ein, method) FROM STDIN") as cp:
            for cid, ein in linked.items():
                cp.write_row((cid, ein, "address"))
            for cid, ein in extra.items():
                cp.write_row((cid, ein, "no address"))
        conn.commit()
        conn.execute("ANALYZE vendor_org_links")
        conn.commit()
    out = {"linked": len(linked), "no_address": len(extra), "ambiguous": ambiguous, "near": near,
           "vendor": vendor}
    status(f"vendor-orgs: {len(linked):,} records linked by address, {len(extra):,} without an address, "
           f"{len(ambiguous):,} ambiguous, {len(near):,} near misses")
    return out


def report(result: dict, k: int = 25, seed: int = 1) -> str:
    """Counts by distinct vendor name and by EIN, plus random samples of matches and near misses."""
    rnd = random.Random(seed)
    with db.connect() as conn:
        n = conn.execute("""SELECT count(*), count(DISTINCT c.name_norm), count(DISTINCT l.ein)
                            FROM vendor_org_links l JOIN contractors c ON c.id = l.contractor_id""").fetchone()
        total = conn.execute("SELECT count(DISTINCT name_norm) FROM contractors").fetchone()[0]
        sample = conn.execute("""
            SELECT DISTINCT ON (c.name_norm) c.name_raw, c.street, c.zip, o.name, o.street AS o_street,
                   o.zip AS o_zip, l.ein, l.method
            FROM vendor_org_links l JOIN contractors c ON c.id = l.contractor_id
            JOIN organizations o ON o.ein = l.ein ORDER BY c.name_norm, l.method, c.id""").fetchall()
    lines = [f"Linked contractor records: {n[0]:,}; distinct vendor names: {n[1]:,} of {total:,}; "
             f"organizations: {n[2]:,}", "", "Sample matches (vendor as filed -> organization):"]
    for r in rnd.sample(sample, min(k, len(sample))):
        lines.append(f"  {r[0]} | {r[1]} {r[2]}  ->  {r[3]} | {r[4]} {r[5]} (EIN {r[6]}, {r[7]})")
    for kind, title in (("name", "same address, names differ"), ("street", "same name, zip and number; street names too far apart")):
        seen, near = set(), []
        for r in sorted((r for r in result["near"] if r["kind"] == kind), key=lambda r: -r["sim"]):
            if (r["name_norm"], r["ein"]) not in seen:
                seen.add((r["name_norm"], r["ein"]))
                near.append(r)
        lines += ["", f"Near misses, not linked ({title}; {len(near):,} distinct pairs), sample:"]
        for r in rnd.sample(near, min(k, len(near))):
            lines.append(f"  {r['sim']:.2f}  {r['name_raw']} | {r['street']} {r['zip']}  vs  {r['org_name']}"
                         f"{' (dba ' + r['dba'] + ')' if r['dba'] else ''} | {r['org_street']} {r['org_zip']} (EIN {r['ein']})")
    amb = list(result["ambiguous"].items())
    lines += ["", f"Ambiguous, not linked (one record, several organizations qualify; {len(amb):,} records), sample:"]
    for cid, eins in rnd.sample(amb, min(10, len(amb))):
        v = result["vendor"][cid]
        lines.append(f"  {v['name_raw']} | {v['street']} {v['zip']}  ->  EINs {', '.join(sorted(eins))}")
    return "\n".join(lines)
