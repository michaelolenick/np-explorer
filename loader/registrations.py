"""Securities registration: who is registered to sell securities or advise on investments.

Sources (all official bulk files, free to reuse):
- SEC "Company Information About Active Broker-Dealers": a monthly list of every active broker-dealer (CIK, name,
  SEC file number 8-..., address), January 2007 on. bd_monthly keeps every month; bd_firms one row per firm with
  its first and last month on the list (active = on the latest list).
- IAPD compilation reports (adviserinfo.sec.gov/compilation, updated daily): every SEC- and state-registered
  investment adviser firm, and every investment adviser representative (IAR) with their current and past adviser
  registrations, employment history, exams, other names, disclosure flags (regulatory, criminal, civil, customer
  complaint, termination, bankruptcy, bond, judgment, investigation) and whether they also hold an active broker
  (agent) registration. FINRA offers no bulk download of BrokerCheck, and its terms don't allow collecting it, so
  people registered only as brokers (not as advisers) aren't here: pages link to a BrokerCheck search instead.
- Form ADV Schedule D 1.B "other business names" (loader/adv.py's bulk files): trade names advisers use.

Links (registration_links), by name only where nothing else is shared, so all are marked Fuzzy on pages:
- people on the site (person_clusters), Form D related persons, Form ADV owners and campaign donors to IARs: the
  same normalized full name held by exactly one IAR, and a shared state (an ADV owner: the IAR works at that
  adviser, by CRD);
- nonprofits and Form D organizations to broker-dealers and adviser firms: the same business name (legal endings
  ignored) held by exactly one firm.

Usage: .venv/bin/python -m loader.registrations [bd] [iapd] [names] [links]
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from loader import db

UA = "furp.org research michael@furp.org"
BD_PAGE = "https://www.sec.gov/foia/frequently-requested-documents/company-information-about-active-broker-dealers"
IAPD = "https://reports.adviserinfo.sec.gov/reports/CompilationReports/"
BD_DIR, IAPD_DIR, ADV_DIR = Path("/bulk/bd"), Path("/bulk/iapd"), Path("/bulk/adv")
DISCLOSURES = {"hasRegAction": "regulatory action", "hasCriminal": "criminal", "hasCivilJudc": "civil judicial",
               "hasCustComp": "customer complaint", "hasTermination": "termination", "hasBankrupt": "bankruptcy",
               "hasBond": "bond", "hasJudgment": "judgment or lien", "hasInvstgn": "investigation"}


def _get(url: str) -> bytes | None:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=600) as r:
                data = r.read()
            time.sleep(0.2)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (attempt + 1))
    return None


def _core(name):
    from loader.recalls import core
    return core(name)


def _date(v):
    v = (v or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%Y"):
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


# --- broker-dealers ----------------------------------------------------------------------------------------------

def _bd_text(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    return data.decode("latin-1")


def bd(status=print) -> int:
    html = (_get(BD_PAGE) or b"").decode("utf-8", "replace")
    urls = sorted(set(re.findall(r'href="(/files/data/broker-dealers/[^"]+/bd(\d{6})\.txt)"', html)))
    with db.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT file FROM registration_runs").fetchall()}
    n = 0
    BD_DIR.mkdir(parents=True, exist_ok=True)
    for path, mmddyy in urls:
        name = f"bd{mmddyy}.txt"
        if name in done:
            continue
        month = dt.date(2000 + int(mmddyy[4:]), int(mmddyy[:2]), 1)
        f = BD_DIR / name
        if not f.exists():
            data = _get("https://www.sec.gov" + path)
            if not data:
                continue
            f.write_bytes(data)
        rows = {}
        for line in _bd_text(f.read_bytes()).splitlines():
            c = [x.strip() for x in line.split("\t")]
            if len(c) < 3 or not c[0].isdigit():
                continue
            c += [""] * (8 - len(c))
            fn = c[2]
            fn = f"8-{int(fn[3:])}" if re.fullmatch(r"008\d+", fn) else fn
            rows[c[0].lstrip("0")] = (month, c[0].lstrip("0"), c[1][:300], fn, c[3][:200] or None, c[4][:200] or None,
                                      c[5][:100] or None, c[6][:10] or None, c[7][:20] or None)
        with db.connect() as conn:
            conn.execute("DELETE FROM bd_monthly WHERE month = %s", (month,))
            with conn.cursor() as cur, cur.copy("COPY bd_monthly FROM STDIN") as cp:
                for r in rows.values():
                    cp.write_row(r)
            conn.execute("INSERT INTO registration_runs (file, rows) VALUES (%s, %s) ON CONFLICT (file) DO UPDATE "
                         "SET loaded = now(), rows = excluded.rows", (name, len(rows)))
            conn.commit()
        n += len(rows)
    with db.connect() as conn:
        latest = conn.execute("SELECT max(month) FROM bd_monthly").fetchone()[0]
        rows = conn.execute("""SELECT l.cik, l.name, l.file_no, l.street1, l.street2, l.city, l.state, l.zip, a.first,
                                      a.last, a.names
                               FROM (SELECT DISTINCT ON (cik) * FROM bd_monthly ORDER BY cik, month DESC) l
                               JOIN (SELECT cik, min(month) AS first, max(month) AS last, array_agg(DISTINCT name) AS names
                                     FROM bd_monthly GROUP BY cik) a USING (cik)""").fetchall()
        conn.execute("CREATE TEMP TABLE b (LIKE bd_firms)")
        with conn.cursor() as cur, cur.copy("COPY b FROM STDIN") as cp:
            for r in rows:
                cp.write_row((r[0], r[1], _core(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[9] == latest,
                              None, r[10]))
        conn.execute("TRUNCATE bd_firms")
        conn.execute("INSERT INTO bd_firms SELECT * FROM b")
        conn.commit()
    status(f"registrations bd: {len(urls)} monthly lists, {n:,} new rows, {len(rows):,} firms ({latest} latest)")
    return len(rows)


# --- IAPD compilation reports ---------------------------------------------------------------------------------------

def _feeds() -> dict[str, str]:
    m = json.loads(_get(IAPD + "CompilationReports.manifest.json") or b"{}")
    out = {}
    for f in m.get("files", []):
        for kind in ("IA_FIRM_SEC", "IA_FIRM_STATE", "IA_INDVL"):
            if f["name"].startswith(kind + "_Feed"):
                out[kind] = f["name"]
    return out


def _fetch(name: str) -> Path:
    IAPD_DIR.mkdir(parents=True, exist_ok=True)
    p = IAPD_DIR / name
    if not p.exists():
        data = _get(IAPD + name)
        if not data:
            raise RuntimeError(f"IAPD file missing: {name}")
        p.write_bytes(data)
        for old in IAPD_DIR.glob(name.split("_Feed")[0] + "_Feed_*"):
            if old.name != name:
                old.unlink()
    return p


def _xml_streams(p: Path):
    if p.suffix == ".gz":
        yield gzip.open(p)
    else:
        z = zipfile.ZipFile(p)
        for n in sorted(z.namelist()):
            yield z.open(n)


def iapd(status=print) -> dict:
    from app.names import normalize_name
    feeds = _feeds()
    firms = {}
    for kind in ("IA_FIRM_SEC", "IA_FIRM_STATE"):
        p = _fetch(feeds[kind])
        feed_date = dt.datetime.strptime(re.search(r"\d\d_\d\d_\d{4}", p.name).group(0), "%m_%d_%Y").date()
        for s in _xml_streams(p):
            for _, el in ET.iterparse(s, events=("end",)):
                if el.tag != "Firm":
                    continue
                info, addr, rg = el.find("Info"), el.find("MainAddr"), el.find("Rgstn")
                crd = info.get("FirmCrdNb")
                if crd:
                    firms[crd] = (crd, info.get("SECNb"), info.get("LegalNm"), info.get("BusNm"),
                                  _core(info.get("BusNm") or info.get("LegalNm")),
                                  addr.get("Strt1") if addr is not None else None, addr.get("City") if addr is not None else None,
                                  addr.get("State") if addr is not None else None, addr.get("PostlCd") if addr is not None else None,
                                  "SEC" if kind == "IA_FIRM_SEC" else "State",
                                  rg.get("St") if rg is not None else None, _date(rg.get("Dt")) if rg is not None else None,
                                  feed_date, None)
                el.clear()
    people, emps = [], []
    p = _fetch(feeds["IA_INDVL"])
    feed_date = dt.datetime.strptime(re.search(r"\d\d_\d\d_\d{4}", p.name).group(0), "%m_%d_%Y").date()
    for s in _xml_streams(p):
        for _, el in ET.iterparse(s, events=("end",)):
            if el.tag != "Indvl":
                continue
            i = el.find("Info")
            crd = i.get("indvlPK")
            first, mid, last = (i.get("firstNm") or "").strip(), (i.get("midNm") or "").strip(), (i.get("lastNm") or "").strip()
            name = " ".join(x for x in (first, mid, last) if x)
            drps = set()
            for d in el.iter("DRP"):
                drps.update(v for k, v in DISCLOSURES.items() if d.get(k) == "Y")
            states = set()
            for e in el.iter("CrntEmp"):
                states.add(e.get("state"))
                for r in list(e.iter("CrntRgstn")) or [None]:
                    emps.append((crd, e.get("orgPK"), e.get("orgNm"), True, _date(r.get("stDt")) if r is not None else None,
                                 None, r.get("regCat") if r is not None else None, r.get("regAuth") if r is not None else None,
                                 e.get("city"), e.get("state")))
                for b in e.iter("BrnchOfLoc"):
                    states.add(b.get("state"))
            for e in el.iter("PrevRgstn"):
                emps.append((crd, e.get("orgPK"), e.get("orgNm"), False, _date(e.get("regBeginDt")), _date(e.get("regEndDt")),
                             None, None, None, None))
                for b in e.iter("BrnchOfLoc"):
                    states.add(b.get("state"))
            for e in el.iter("EmpHs"):
                states.add(e.get("state"))
            people.append((crd, first or None, mid or None, last or None, name,
                           normalize_name(f"{last}, {first} {mid}".strip()) or None, i.get("actvAGReg") == "Y",
                           sorted({o.get("othrNm", "").strip() or " ".join(filter(None, (o.get("firstNm"), o.get("midNm"), o.get("lastNm"))))
                                   for o in el.iter("OthrNm")} - {""}) or None,
                           sorted({x.get("exmCd") for x in el.iter("Exm") if x.get("exmCd")}) or None,
                           sorted({x.get("dsgntnNm") for x in el.iter("Dsgntn") if x.get("dsgntnNm")}) or None,
                           sorted(drps) or None, sorted(s_ for s_ in states if s_ and len(s_) == 2) or None, feed_date))
            el.clear()
    with db.connect() as conn:
        for table, rows in (("iapd_firms", firms.values()), ("iapd_individuals", people), ("iapd_employments", emps)):
            conn.execute(f"DROP TABLE IF EXISTS {table}_new")
            conn.execute(f"CREATE TABLE {table}_new (LIKE {table} INCLUDING ALL)")
            with conn.cursor() as cur, cur.copy(f"COPY {table}_new FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
            db.swap_table(conn, table)
            conn.commit()
    out = {"firms": len(firms), "individuals": len(people), "employments": len(emps)}
    status(f"registrations iapd: {len(firms):,} adviser firms, {len(people):,} representatives, {len(emps):,} registrations")
    return out


# --- other business names ------------------------------------------------------------------------------------------

def names(status=print) -> int:
    """sec_firm_aliases: Form ADV Schedule D 1.B other business names (each adviser's latest filing), the business
    name where it differs from the legal name (IAPD), and broker-dealers' earlier names on the SEC's monthly list."""
    import csv
    csv.field_size_limit(10_000_000)
    rows = set()
    with db.connect() as conn:
        latest = {r[0]: r[1] for r in conn.execute("""SELECT DISTINCT ON (crd) filing_id, crd FROM adv_filings
                                                      WHERE crd IS NOT NULL ORDER BY crd, submitted DESC NULLS LAST""").fetchall()}
        for zp in sorted(ADV_DIR.glob("*.zip")):
            z = zipfile.ZipFile(zp)
            for n in z.namelist():
                if re.search(r"(IA|ERA)_Schedule_D_1B_.*\.csv$", n):
                    for r in csv.DictReader(io.TextIOWrapper(z.open(n), encoding="latin-1", newline="")):
                        fid = (r.get("FilingID") or "").strip()
                        nm = (r.get("Other Business Name") or "").strip()
                        if fid.isdigit() and int(fid) in latest and nm:
                            rows.add((_core(nm), nm[:300], "ia", latest[int(fid)], "Form ADV Schedule D 1.B"))
        for crd, legal, bus in conn.execute("SELECT crd, legal_name, business_name FROM iapd_firms").fetchall():
            for nm in (legal, bus):
                if nm:
                    rows.add((_core(nm), nm[:300], "ia", crd, "IAPD"))
        for cik, names_ in conn.execute("SELECT cik, names FROM bd_firms").fetchall():
            for nm in names_ or []:
                rows.add((_core(nm), nm[:300], "bd", cik, "SEC broker-dealer list"))
        rows = {r for r in rows if r[0]}
        conn.execute("TRUNCATE sec_firm_aliases")
        conn.execute("CREATE TEMP TABLE a (LIKE sec_firm_aliases)")
        with conn.cursor() as cur, cur.copy("COPY a FROM STDIN") as cp:
            for r in rows:
                cp.write_row(r)
        conn.execute("INSERT INTO sec_firm_aliases SELECT DISTINCT ON (alias_norm, kind, key) * FROM a ON CONFLICT DO NOTHING")
        # Broker-dealers' CRD numbers: the same business name as exactly one adviser firm (dual registrants).
        conn.execute("""UPDATE bd_firms b SET crd = f.crd FROM (
                            SELECT name_core, min(crd) AS crd FROM iapd_firms GROUP BY 1 HAVING count(*) = 1) f
                        WHERE f.name_core = b.name_core AND b.name_core <> ''""")
        conn.commit()
    status(f"registrations names: {len(rows):,} firm names and other business names")
    return len(rows)


# --- links ---------------------------------------------------------------------------------------------------------

def links(status=print) -> dict:
    with db.connect() as conn:
        conn.execute("SET work_mem = '1GB'")
        conn.execute("""CREATE TEMP TABLE ui AS SELECT name_norm, min(crd) AS crd, min(states) AS states FROM iapd_individuals
                        WHERE name_norm IS NOT NULL GROUP BY 1 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON ui (name_norm)")
        conn.execute("""CREATE TEMP TABLE uf AS SELECT core, min(kind) AS kind, min(key) AS key FROM (
                            SELECT name_core AS core, 'ia' AS kind, crd AS key FROM iapd_firms WHERE name_core <> ''
                            UNION SELECT name_core, 'bd', cik FROM bd_firms WHERE name_core <> '') x
                        GROUP BY 1 HAVING count(*) = 1""")
        conn.execute("TRUNCATE registration_links")
        # People on the site: unique name in both, and a shared state.
        conn.execute("""INSERT INTO registration_links SELECT 'person', pc.id::text, 'iar', ui.crd, 'name and state'
                        FROM ui JOIN (SELECT name_norm, min(id) AS id, min(states) AS states FROM person_clusters
                                      WHERE NOT is_institution GROUP BY 1 HAVING count(*) = 1) pc USING (name_norm)
                        WHERE ui.states && pc.states ON CONFLICT DO NOTHING""")
        # Form D related persons (people grouped by name and state).
        conn.execute("""INSERT INTO registration_links SELECT 'formd', p.id::text, 'iar', ui.crd, 'name and state'
                        FROM sec_formd_parties p JOIN ui USING (name_norm)
                        WHERE p.kind = 'person' AND p.state = ANY(ui.states) ON CONFLICT DO NOTHING""")
        # Form ADV owners: the same name working at that adviser.
        conn.execute("""INSERT INTO registration_links SELECT DISTINCT 'adv_owner', o.crd || ':' || o.name_norm, 'iar', i.crd,
                               'name, at the same adviser'
                        FROM adv_owners o JOIN iapd_individuals i ON i.name_norm = o.name_norm
                        JOIN iapd_employments e ON e.crd = i.crd AND e.firm_crd = o.crd
                        WHERE o.entity_kind = 'I' AND o.name_norm IS NOT NULL ON CONFLICT DO NOTHING""")
        # Campaign donors (name and ZIP): unique name and the donor's state.
        if conn.execute("SELECT to_regclass('fec_donor_totals') IS NOT NULL").fetchone()[0]:
            conn.execute("""INSERT INTO registration_links SELECT DISTINCT 'donor', coalesce(d.zip5, '00000') || ':' || d.name_norm, 'iar', ui.crd,
                                   'name and state'
                            FROM (SELECT DISTINCT zip5, name_norm, state FROM fec_donor_totals) d JOIN ui USING (name_norm)
                            WHERE d.state = ANY(ui.states) AND d.name_norm ~ '^\\S+ \\S+ \\S+' ON CONFLICT DO NOTHING""")
        # Firms: nonprofits and Form D organizations with the same business name as exactly one firm.
        from app.funders import normalize_org  # noqa: F401  (organizations.name_norm is normalize_org)
        orgs = conn.execute("SELECT ein, name FROM organizations WHERE latest_filing_year IS NOT NULL").fetchall()
        cores = {}
        for ein, name in orgs:
            cores.setdefault(_core(name), []).append(ein)
        uf = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT core, kind, key FROM uf").fetchall()}
        org_links = [("org", eins[0], *uf[c], "business name") for c, eins in cores.items() if c in uf and len(eins) == 1]
        with conn.cursor() as cur, cur.copy("COPY registration_links FROM STDIN") as cp:
            for r in org_links:
                cp.write_row(r)
        conn.execute("""INSERT INTO registration_links SELECT 'formd_entity', p.id::text, uf.kind, uf.key, 'business name'
                        FROM sec_formd_parties p JOIN uf ON uf.core = p.name_norm WHERE p.kind = 'entity'
                        ON CONFLICT DO NOTHING""")
        conn.commit()
        conn.execute("ANALYZE registration_links")
        conn.commit()
        counts = dict(conn.execute("SELECT kind, count(*) FROM registration_links GROUP BY 1").fetchall())
    status("registrations links: " + ", ".join(f"{k} {v:,}" for k, v in sorted(counts.items())))
    return counts


def run(status=print) -> None:
    bd(status)
    iapd(status)
    names(status)
    links(status)


if __name__ == "__main__":
    for step in sys.argv[1:] or ["run"]:
        globals()[step]()
