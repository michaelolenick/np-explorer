"""Wikipedia and Wikidata: short bios for people and organizations that are also in FURP (owner, 2026-11-14).

Sources (the official dumps only, one download per file, fixed User-Agent, never the live site per page):
  * Wikidata entity dump (latest-all.json.gz; CC0): humans (instance of Q5) and organizations with an English
    Wikipedia article, plus any item with an IRS EIN (P1297). ~/claude_scripts/wikipedia/wd_filter.py makes one pass
    over it and writes /bulk/wikipedia/extract/{people,orgs}.jsonl and labels.tsv.
  * English Wikipedia pages-articles multistream dump (CC BY-SA 4.0): only the short description and the first
    sentence or two of the lead of the pages that matched are kept (max 300 characters), with the article URL.
Schema `wiki` (own schema, nothing else in the database is touched):
  wiki.entity      one row per person / organization (qid, label, title, descriptions, years, website, EIN, CIK...)
  wiki.label       English labels of every item an entity points at (occupation, employer, headquarters ...)
  wiki.person_name / wiki.org_name   normalized name keys used to match
  wiki.link        (kind, key, qid, method, confidence, evidence, show) the matches; `show` only for methods whose
                   sampled precision is high enough (wiki.precision holds the judged samples)
  wiki.precision   method, judged, correct (random samples of at least 50 per method)

Commands (python -m loader.wikipedia ...):
  load [--dir D]       extract files -> wiki.entity / label / name keys (replaces the previous load)
  match                run the matching rules into wiki.link
  lead                 short description + lead sentence(s) from the enwiki dump for matched entities
  sample METHOD [--n]  random sample of a method's links with the evidence (to judge precision)
  judge METHOD N OK    record a judged sample in wiki.precision
  publish              xlinks rows (xlink kind 'wikipedia'), shown links only, and the boards' source table
  status
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import quote, urlparse

from app.names import normalize_name, normalize_org
from loader import db
from loader.recalls import core as org_core

EXTRACT = os.environ.get("WIKI_EXTRACT", "/bulk/wikipedia/extract")
DUMP_DATE = os.environ.get("WIKI_DUMP_DATE", "2026-11-11")
LOG = os.path.expanduser("~/claude_scripts/wikipedia/status.log")

DDL = """
CREATE SCHEMA IF NOT EXISTS wiki;
CREATE TABLE IF NOT EXISTS wiki.entity (
    qid text PRIMARY KEY, kind text NOT NULL, label text, title text, wd_desc text, short_desc text, lead text,
    birth_year integer, death_year integer, inception integer, dissolved integer, website text, domain text,
    ein text, cik text[], fec text[], lei text[], aliases text[], has_article boolean NOT NULL DEFAULT true,
    occ_q text[], emp_q text[], mem_q text[], cit_q text[], pob_q text[], res_q text[], edu_q text[],
    p31_q text[], hq_q text[], loc_q text[], ctry_q text[], par_q text[], board_q text[], ind_q text[],
    lead_fetched timestamptz, dump_date text);
CREATE INDEX IF NOT EXISTS wiki_entity_kind ON wiki.entity (kind);
CREATE INDEX IF NOT EXISTS wiki_entity_ein ON wiki.entity (ein) WHERE ein IS NOT NULL;
CREATE INDEX IF NOT EXISTS wiki_entity_domain ON wiki.entity (domain) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS wiki_entity_title ON wiki.entity (title);
CREATE TABLE IF NOT EXISTS wiki.label (qid text PRIMARY KEY, label text NOT NULL);
CREATE TABLE IF NOT EXISTS wiki.person_name (qid text NOT NULL, name_norm text NOT NULL, fl text NOT NULL, src text);
CREATE INDEX IF NOT EXISTS wiki_person_name_n ON wiki.person_name (name_norm);
CREATE INDEX IF NOT EXISTS wiki_person_name_fl ON wiki.person_name (fl);
CREATE INDEX IF NOT EXISTS wiki_person_name_q ON wiki.person_name (qid);
CREATE TABLE IF NOT EXISTS wiki.org_name (qid text NOT NULL, core text NOT NULL);
CREATE INDEX IF NOT EXISTS wiki_org_name_c ON wiki.org_name (core);
CREATE INDEX IF NOT EXISTS wiki_org_name_q ON wiki.org_name (qid);
CREATE TABLE IF NOT EXISTS wiki.link (
    kind text NOT NULL, key text NOT NULL, qid text NOT NULL, method text NOT NULL, confidence text NOT NULL,
    evidence text, show boolean NOT NULL DEFAULT false, added timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, key, qid));
CREATE INDEX IF NOT EXISTS wiki_link_qid ON wiki.link (qid);
CREATE INDEX IF NOT EXISTS wiki_link_method ON wiki.link (method);
CREATE TABLE IF NOT EXISTS wiki.precision (
    method text PRIMARY KEY, judged integer NOT NULL, correct integer NOT NULL, note text, judged_at timestamptz NOT NULL DEFAULT now());
"""

# Items that are not organizations although they carry a website or an inception date.
NOT_ORG_P31 = {
    "Q6256", "Q3624078", "Q515", "Q5107", "Q35657", "Q486972", "Q15284", "Q1549591", "Q532", "Q3957", "Q123705", "Q1637706",
    "Q11424", "Q5398426", "Q482994", "Q7889", "Q134556", "Q4830453x", "Q41298", "Q1002697", "Q13406463", "Q95074", "Q571",
    "Q18127", "Q1004", "Q7725634", "Q386724", "Q11410", "Q7366", "Q202444", "Q3305213", "Q16521", "Q8142", "Q8054",
}


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def ensure_schema(conn) -> None:
    ok = conn.execute("SELECT to_regclass('wiki.precision') IS NOT NULL").fetchone()[0]
    if not ok:
        conn.execute(DDL)
        conn.commit()


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    if "//" not in u:
        u = "//" + u
    host = (urlparse(u).hostname or "").lower()
    host = re.sub(r"^(www\d?|m)\.", "", host)
    return host if "." in host else None


def person_keys(label, title, aliases) -> list[tuple[str, str, str]]:
    """(name_norm, first+last key, source) for the label, the article title and the English aliases."""
    out, seen = [], set()
    for src, nm in [("label", label), ("title", title)] + [("alias", a) for a in (aliases or [])]:
        if not nm:
            continue
        n = normalize_name(nm)
        toks = n.split()
        if len(toks) < 2 or n in seen:
            continue
        seen.add(n)
        core = [t for t in toks if t not in ("jr", "sr", "ii", "iii", "iv", "v")]
        fl = f"{core[0]} {core[-1]}" if len(core) >= 2 else n
        out.append((n, fl, src))
    return out


def _iter(paths):
    for path in ([paths] if isinstance(paths, str) else paths):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def _files(dir_: str, stem: str, ext: str) -> list[str]:
    import glob
    return sorted(glob.glob(f"{dir_}/{stem}.{ext}") + glob.glob(f"{dir_}/{stem}.[0-9]*.{ext}"))


def load(dir_: str = EXTRACT) -> None:
    """Extract files -> wiki tables. Replaces entities, labels and name keys."""
    t0 = time.time()
    people_f, orgs_f, labels_f = _files(dir_, "people", "jsonl"), _files(dir_, "orgs", "jsonl"), _files(dir_, "labels", "tsv")
    refs: set[int] = set()

    def addrefs(*lists):
        for l in lists:
            for q in l or ():
                refs.add(int(q[1:]))

    n_p = n_o = 0
    for r in _iter(people_f):
        addrefs(r["occ"], r["emp"], r["mem"], r["cit"], r["pob"], r["res"], r["edu"])
        n_p += 1
    for r in _iter(orgs_f):
        addrefs(r["p31"], r["hq"], r["loc"], r["ctry"], r["par"], r["board"], r["ind"])
        n_o += 1
    log(f"load: read {n_p:,} people and {n_o:,} organization items, {len(refs):,} referenced items")
    labels: dict[int, str] = {}
    own: dict[str, str] = {}
    for lf in labels_f:
        with open(lf, "rb") as f:
            for line in f:
                q, _, lab = line.rstrip(b"\n").partition(b"\t")
                if len(q) < 2:
                    continue
                qi = int(q[1:])
                if qi in refs:
                    labels[qi] = lab.decode()
    log(f"load: {len(labels):,} labels resolved ({time.time() - t0:.0f}s)")
    with db.connect() as conn:
        conn.execute("SET lock_timeout = '20s'")
        ensure_schema(conn)
        for t in ("entity", "label", "person_name", "org_name"):
            conn.execute(f"TRUNCATE wiki.{t}")
        conn.commit()
        cols = ["qid", "kind", "label", "title", "wd_desc", "birth_year", "death_year", "inception", "dissolved", "website", "domain",
                "ein", "cik", "fec", "lei", "aliases", "has_article", "occ_q", "emp_q", "mem_q", "cit_q", "pob_q", "res_q", "edu_q",
                "p31_q", "hq_q", "loc_q", "ctry_q", "par_q", "board_q", "ind_q", "dump_date"]
        conn2 = db.connect()
        with conn.cursor() as cur, conn2.cursor() as cur2:
            with cur.copy(f"COPY wiki.entity ({', '.join(cols)}) FROM STDIN") as cp, \
                    cur2.copy("COPY wiki.person_name (qid, name_norm, fl, src) FROM STDIN") as cpn:
                for r in _iter(people_f):
                    cp.write_row((r["q"], "person", r["l"], r["t"], r["d"], r["by"], r["dy"], None, None,
                                  (r["web"] or [None])[0], domain_of((r["web"] or [None])[0]), None, r["cik"] or None, r["fec"] or None,
                                  None, r["al"] or None, True, r["occ"], r["emp"], r["mem"], r["cit"], r["pob"], r["res"], r["edu"],
                                  None, None, None, None, None, None, None, DUMP_DATE))
                    for n, fl, src in person_keys(r["l"], r["t"], r["al"]):
                        cpn.write_row((r["q"], n, fl, src))
            with cur.copy(f"COPY wiki.entity ({', '.join(cols)}) FROM STDIN") as cp, \
                    cur2.copy("COPY wiki.org_name (qid, core) FROM STDIN") as cpo:
                for r in _iter(orgs_f):
                    if NOT_ORG_P31 & set(r["p31"]) and not r["ein"]:
                        continue
                    eins = [re.sub(r"\D", "", e) for e in r["ein"]]
                    eins = [e for e in eins if len(e) == 9]
                    cp.write_row((r["q"], "org", r["l"], r["t"], r["d"], None, None, r["inc"], r["dis"], (r["web"] or [None])[0],
                                  domain_of((r["web"] or [None])[0]), eins[0] if eins else None, r["cik"] or None, r["fec"] or None,
                                  r["lei"] or None, r["al"] or None, bool(r["t"]), None, None, None, None, None, None, None,
                                  r["p31"], r["hq"], r["loc"], r["ctry"], r["par"], r["board"], r["ind"], DUMP_DATE))
                    seen = set()
                    for nm in [r["l"], r["t"]] + list(r["al"] or []):
                        c = org_core(nm) if nm else ""
                        if len(c) >= 4 and c not in seen:
                            seen.add(c)
                            cpo.write_row((r["q"], c))
            with cur.copy("COPY wiki.label (qid, label) FROM STDIN") as cpl:
                for qi, lab in labels.items():
                    cpl.write_row((f"Q{qi}", lab))
        conn2.commit()
        conn2.close()
        conn.commit()
        conn.execute("ANALYZE wiki.entity")
        conn.execute("ANALYZE wiki.person_name")
        conn.commit()
        n = conn.execute("SELECT kind, count(*) FROM wiki.entity GROUP BY 1").fetchall()
    log(f"load: done in {time.time() - t0:.0f}s: {n}")


# --- matching ------------------------------------------------------------------------------------------------

SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}
RARE = 0.03      # a full name whose first and last name together would occur this often by chance is "rare"
UNCOMMON = 0.3   # ... "uncommon"; above that the name alone says little


def middles_ok(a: str, b: str) -> bool:
    """Two normalized names with the same first and last token: the middle names must not conflict (one side with no
    middle, or the same name or the same initial); a different suffix (jr/sr/iii) is a different person."""
    ta, tb = a.split(), b.split()
    sa = ta[-1] if ta and ta[-1] in SUFFIX and len(ta) > 2 else None
    sb = tb[-1] if tb and tb[-1] in SUFFIX and len(tb) > 2 else None
    if sa != sb:                 # "john smith jr" is not "john smith": both carry the same suffix or neither does
        return False
    ta = ta[:-1] if sa else ta
    tb = tb[:-1] if sb else tb
    if len(ta) < 2 or len(tb) < 2 or ta[0] != tb[0] or ta[-1] != tb[-1]:
        return False
    ma, mb = ta[1:-1], tb[1:-1]
    if not ma or not mb:
        return True
    x, y = ma[0], mb[0]
    return x == y or (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y))


def _insert_links(conn, rows) -> int:
    """rows: (kind, key, qid, method, confidence, evidence). Existing links keep their (stronger, earlier) method."""
    if not rows:
        return 0
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS wl_batch (kind text, key text, qid text, method text, confidence text, evidence text) ON COMMIT DROP")
    conn.execute("TRUNCATE wl_batch")
    with conn.cursor() as cur:
        db.copy_rows(cur, "wl_batch", ["kind", "key", "qid", "method", "confidence", "evidence"], rows)
    return conn.execute("""INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
                           SELECT DISTINCT ON (kind, key, qid) kind, key, qid, method, confidence, evidence FROM wl_batch
                           ORDER BY kind, key, qid, (confidence = 'high') DESC
                           ON CONFLICT DO NOTHING""").rowcount


US_STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
             "DE": "Delaware", "DC": "(District of Columbia|Washington,? D\\.?C)", "FL": "Florida", "GA": "Georgia", "HI": "Hawai.i", "ID": "Idaho",
             "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
             "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
             "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
             "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
             "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
             "VA": "(?<!West )Virginia", "WA": "Washington(?!,? D\\.?C)", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}

PLACE_RE = (r"(city|town|village|municipality|census-designated|unincorporated|county|borough|township|hamlet|locality|"
            r"neighbou?rhood|country|sovereign state|province|island|river|lake|mountain|street|road|bridge|human settlement|"
            r"ghost town|urban area|state of the united states)")


def _prep_tables(conn) -> None:
    """Temp tables shared by the organization and people rules: Wikipedia items that are places (never an organization match),
    FURP nonprofits whose name core also names a Wikipedia organization, and how many nonprofits share each core."""
    if conn.execute("SELECT to_regclass('pg_temp.wiki_fcn') IS NOT NULL").fetchone()[0]:
        return
    conn.execute("DROP TABLE IF EXISTS wiki_st")
    conn.execute("CREATE TEMP TABLE wiki_st (abbr text, rx text)")
    with conn.cursor() as cur:
        db.copy_rows(cur, "wiki_st", ["abbr", "rx"], [(a, r"\m" + n + r"\M") for a, n in US_STATES.items()])
    conn.execute("DROP TABLE IF EXISTS wiki_place")
    conn.execute(f"""CREATE TEMP TABLE wiki_place AS SELECT e.qid FROM wiki.entity e WHERE e.kind = 'org' AND EXISTS (
                     SELECT 1 FROM unnest(e.p31_q) t JOIN wiki.label l ON l.qid = t WHERE l.label ~* '{PLACE_RE}')""")
    conn.execute("CREATE INDEX ON wiki_place (qid)")
    conn.execute("DROP TABLE IF EXISTS wiki_fc")
    conn.execute("""CREATE TEMP TABLE wiki_fc AS
        SELECT n.core, n.key AS ein, n.city, n.state FROM xref_names n JOIN (SELECT DISTINCT core FROM wiki.org_name) w ON w.core = n.core
        WHERE n.kind = 'org'""")
    conn.execute("CREATE INDEX ON wiki_fc (core)")
    conn.execute("ANALYZE wiki_fc")
    conn.execute("DROP TABLE IF EXISTS wiki_fcn")
    conn.execute("CREATE TEMP TABLE wiki_fcn AS SELECT core, count(*) AS n FROM wiki_fc GROUP BY core")
    conn.execute("CREATE INDEX ON wiki_fcn (core)")
    conn.commit()


NOT_PLACE = "AND NOT EXISTS (SELECT 1 FROM wiki_place pl WHERE pl.qid = e.qid)"


def match_orgs(conn) -> dict:
    out = {}
    _prep_tables(conn)

    def run(name, sql):
        t0 = time.time()
        conn.execute("SET statement_timeout = 0")
        n = conn.execute(sql.replace("@@NP@@", NOT_PLACE)).rowcount
        conn.commit()
        out[name] = n
        log(f"match orgs: {name}: {n:,} links ({time.time() - t0:.0f}s)")

    # EXACT identifiers
    run("org ein", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'org', o.ein, e.qid, 'org_ein', 'high', 'Wikidata IRS EIN ' || e.ein FROM wiki.entity e JOIN organizations o ON o.ein = e.ein
        WHERE e.kind = 'org' AND e.has_article ON CONFLICT DO NOTHING""")
    run("college ein", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'college', c.unitid::text, e.qid, 'college_ein', 'high', 'Wikidata IRS EIN ' || e.ein FROM wiki.entity e JOIN colleges c ON c.ein = e.ein
        WHERE e.kind = 'org' AND e.has_article AND NOT coalesce(c.international, false) ON CONFLICT DO NOTHING""")
    run("sec cik", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT DISTINCT 'sec', n.key, e.qid, 'sec_cik', 'high', 'Wikidata SEC Central Index Key ' || c
        FROM wiki.entity e CROSS JOIN LATERAL unnest(e.cik) c JOIN xref_names n ON n.kind = 'sec' AND n.key = ltrim(c, '0')
        WHERE e.kind = 'org' AND e.has_article ON CONFLICT DO NOTHING""")
    # FURP organization domains
    conn.execute("DROP TABLE IF EXISTS wiki_fd")
    conn.execute("""CREATE TEMP TABLE wiki_fd AS
        SELECT ein, name, city, state, lower(regexp_replace(regexp_replace(website, '^\\s*(https?://)?(www\\d?\\.)?', '', 'i'), '[/:?#\\s].*$', '')) AS domain
        FROM organizations WHERE website IS NOT NULL AND website ~ '\\.'""")
    conn.execute("CREATE INDEX ON wiki_fd (domain)")
    conn.execute("ANALYZE wiki_fd")
    conn.execute("DROP TABLE IF EXISTS wiki_fdu")
    conn.execute("CREATE TEMP TABLE wiki_fdu AS SELECT domain FROM wiki_fd GROUP BY domain HAVING count(*) = 1")
    conn.execute("CREATE INDEX ON wiki_fdu (domain)")
    conn.execute("DROP TABLE IF EXISTS wiki_wdu")
    conn.execute("CREATE TEMP TABLE wiki_wdu AS SELECT domain FROM wiki.entity WHERE kind = 'org' AND domain IS NOT NULL GROUP BY domain HAVING count(*) = 1")
    conn.execute("CREATE INDEX ON wiki_wdu (domain)")
    run("website", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'org', f.ein, e.qid, 'org_website', 'medium', 'the same website ' || f.domain || ' (Wikidata official website; the website on the IRS filing)'
        FROM wiki.entity e JOIN wiki_wdu w ON w.domain = e.domain JOIN wiki_fdu u ON u.domain = e.domain JOIN wiki_fd f ON f.domain = e.domain
        WHERE e.kind = 'org' AND e.has_article @@NP@@ ON CONFLICT DO NOTHING""")
    # name core + headquarters city (labels), the core unique among FURP nonprofits
    conn.execute("DROP TABLE IF EXISTS wiki_hq")
    conn.execute("""CREATE TEMP TABLE wiki_hq AS
        SELECT DISTINCT e.qid, census_city_norm(l.label) AS city, l.label FROM wiki.entity e
        CROSS JOIN LATERAL unnest(coalesce(e.hq_q, '{}') || coalesce(e.loc_q, '{}')) r(q) JOIN wiki.label l ON l.qid = r.q
        WHERE e.kind = 'org' AND e.has_article""")
    conn.execute("CREATE INDEX ON wiki_hq (qid)")
    run("name_city", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT DISTINCT 'org', f.ein, e.qid, 'org_name_city', 'medium',
               'the same name and the headquarters city ' || h.label || ' (Wikidata) is the filing city'
        FROM wiki.entity e JOIN wiki.org_name n ON n.qid = e.qid JOIN wiki_fc f ON f.core = n.core
        JOIN wiki_fcn c ON c.core = n.core AND c.n <= 4
        JOIN wiki_hq h ON h.qid = e.qid AND h.city = census_city_norm(f.city)
        WHERE e.kind = 'org' AND e.has_article @@NP@@ ON CONFLICT DO NOTHING""")
    # name only: unique name core among Wikipedia organizations and among FURP nonprofits, at least two words
    conn.execute("DROP TABLE IF EXISTS wiki_wcn")
    conn.execute("""CREATE TEMP TABLE wiki_wcn AS SELECT n.core, min(n.qid) AS qid FROM wiki.org_name n JOIN wiki.entity e ON e.qid = n.qid
                    WHERE e.kind = 'org' AND e.has_article """ + NOT_PLACE + """ GROUP BY n.core HAVING count(DISTINCT n.qid) = 1""")
    org_cls = (r"(organi[sz]ation|nonprofit|non-profit|foundation|university|college|school|hospital|church|congregation|association|society|"
               r"club|museum|institution|institute|company|charity|council|chamber|league|union|seminary|library|center|centre|agency|"
               r"fund|trust|corporation|academy|synagogue|temple|mosque|zoo|orchestra|theat|ministry|network|alliance|coalition|team)")
    run("name_citydesc", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'org', f.ein, w.qid, 'org_name_citydesc', 'medium', 'the same name; the only organization with it on Wikipedia and in FURP; Wikidata describes it in the filing city and state'
        FROM wiki_wcn w JOIN wiki.entity e ON e.qid = w.qid JOIN wiki_fc f ON f.core = w.core JOIN wiki_fcn c ON c.core = w.core AND c.n = 1
        JOIN wiki_st s ON s.abbr = f.state AND e.wd_desc ~* s.rx
        WHERE array_length(string_to_array(w.core, ' '), 1) >= 2 AND length(f.city) >= 4 AND position(lower(f.city) in lower(e.wd_desc)) > 0
        ON CONFLICT DO NOTHING""")
    run("name_state", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'org', f.ein, w.qid, 'org_name_state', 'medium', 'the same name; the only organization with it on Wikipedia and in FURP; Wikidata describes it in the same state'
        FROM wiki_wcn w JOIN wiki.entity e ON e.qid = w.qid JOIN wiki_fc f ON f.core = w.core JOIN wiki_fcn c ON c.core = w.core AND c.n = 1
        JOIN wiki_st s ON s.abbr = f.state AND e.wd_desc ~* s.rx
        WHERE array_length(string_to_array(w.core, ' '), 1) >= 2 ON CONFLICT DO NOTHING""")
    run("name_us", f"""INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'org', f.ein, w.qid, 'org_name_us', 'medium', 'the same name; the only organization with it on Wikipedia and in FURP; Wikidata puts it in the United States'
        FROM wiki_wcn w JOIN wiki.entity e ON e.qid = w.qid JOIN wiki_fc f ON f.core = w.core JOIN wiki_fcn c ON c.core = w.core AND c.n = 1
        WHERE array_length(string_to_array(w.core, ' '), 1) >= 2 AND 'Q30' = ANY(coalesce(e.ctry_q, '{{}}'))
          AND NOT EXISTS (SELECT 1 FROM wiki_st s2 WHERE e.wd_desc ~* s2.rx)
          AND EXISTS (SELECT 1 FROM unnest(e.p31_q) t JOIN wiki.label l ON l.qid = t WHERE l.label ~* '{org_cls}')
        ON CONFLICT DO NOTHING""")
    run("name_only", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'org', f.ein, w.qid, 'org_name_only', 'low', 'the same name; the only organization with it on Wikipedia and in FURP (no other signal)'
        FROM wiki_wcn w JOIN wiki_fc f ON f.core = w.core JOIN wiki_fcn c ON c.core = w.core AND c.n = 1
        WHERE array_length(string_to_array(w.core, ' '), 1) >= 2 ON CONFLICT DO NOTHING""")
    # colleges: website, name
    run("college website", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'college', c.unitid::text, e.qid, 'college_website', 'medium', 'the same website ' || e.domain
        FROM wiki.entity e JOIN wiki_wdu w ON w.domain = e.domain
        JOIN colleges c ON lower(regexp_replace(regexp_replace(c.website, '^\\s*(https?://)?(www\\d?\\.)?', '', 'i'), '[/:?#\\s].*$', '')) = e.domain
        WHERE e.kind = 'org' AND e.has_article AND NOT coalesce(c.international, false) @@NP@@ ON CONFLICT DO NOTHING""")
    run("college name", """INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT 'college', c.unitid::text, e.qid, 'college_name', 'medium', 'the same name; a university, college or school on Wikipedia'
        FROM colleges c JOIN wiki.org_name n ON n.core = c.core_norm JOIN wiki.entity e ON e.qid = n.qid
        WHERE e.kind = 'org' AND e.has_article AND NOT coalesce(c.international, false) AND length(c.core_norm) >= 6
          AND EXISTS (SELECT 1 FROM unnest(e.p31_q) t JOIN wiki.label l ON l.qid = t WHERE l.label ~* '(universit|college|school|institute|academy)')
          AND (SELECT count(*) FROM colleges c2 WHERE c2.core_norm = c.core_norm) = 1
          AND (SELECT count(DISTINCT n2.qid) FROM wiki.org_name n2 WHERE n2.core = n.core) = 1 @@NP@@
        ON CONFLICT DO NOTHING""")
    return out



SUPPORT = {"society", "historical", "retiree", "welfare", "benefit", "plan", "foundation", "fund", "alumni", "alumnae", "friends", "charities", "charity", "trust", "endowment", "auxiliary", "guild",
           "scholarship", "boosters", "booster", "club", "pac", "political", "action", "committee", "ministries", "ministry", "alliance"}


def _words(name: str | None) -> frozenset:
    return frozenset(w for w in org_core(name or "").split() if w not in ("of", "the", "and", "for", "inc"))


def names_agree(furp: str | None, wiki_names: list) -> bool:
    """One name's words contain the other's, and what is left over is not a supporting-organization word
    (a college foundation or alumni association is not the college)."""
    a = _words(furp)
    if not a:
        return False
    for n in wiki_names:
        b = _words(n)
        if not b:
            continue
        if a <= b or b <= a:
            if not ((a ^ b) & SUPPORT):
                return True
    return False


def refine_website(conn) -> dict:
    """A shared website alone also joins a supporting foundation or a station to the thing it supports: keep the website
    links whose names also agree under the method `*_website_name`; the rest stay `*_website` (not shown)."""
    out = {}
    for kind, method, new in (("org", "org_website", "org_website_name"), ("college", "college_website", "college_website_name")):
        if kind == "org":
            rows = conn.execute("""SELECT l.key, l.qid, o.name, e.label, e.title, e.aliases FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid
                                   JOIN organizations o ON o.ein = l.key WHERE l.kind = 'org' AND l.method = %s""", (method,)).fetchall()
        else:
            rows = conn.execute("""SELECT l.key, l.qid, c.name, e.label, e.title, e.aliases FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid
                                   JOIN colleges c ON c.unitid = l.key::int WHERE l.kind = 'college' AND l.method = %s""", (method,)).fetchall()
        ok = [(k, q) for k, q, name, lab, title, al in rows if names_agree(name, [lab, title] + list(al or []))]
        n = 0
        for i in range(0, len(ok), 5000):
            chunk = ok[i:i + 5000]
            n += conn.execute("""UPDATE wiki.link l SET method = %s, confidence = 'high',
                                    evidence = l.evidence || '; the names agree'
                                 FROM unnest(%s::text[], %s::text[]) v(k, q) WHERE l.kind = %s AND l.key = v.k AND l.qid = v.q""",
                              (new, [x[0] for x in chunk], [x[1] for x in chunk], kind)).rowcount
        conn.commit()
        out[new] = n
        log(f"refine: {new}: {n:,} of {len(rows):,} website links also agree on the name")
    return out


def match_people(conn) -> dict:
    out = {}
    t0 = time.time()
    conn.execute("SET statement_timeout = 0")
    # 1. SEC insiders: the CIK on Wikidata is the insider's own CIK (EXACT).
    n = conn.execute("""INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT DISTINCT 'sec_insider', ltrim(o.owner_cik, '0'), e.qid, 'person_cik', 'high', 'Wikidata SEC Central Index Key ' || c
        FROM wiki.entity e CROSS JOIN LATERAL unnest(e.cik) c JOIN sec_insider_owners o ON o.owner_cik = lpad(c, 10, '0')
        WHERE e.kind = 'person' ON CONFLICT DO NOTHING""").rowcount
    conn.commit()
    out["cik insider"] = n
    n = conn.execute("""INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence)
        SELECT DISTINCT 'person', s.cluster_id::text, e.qid, 'person_cik', 'high', 'Wikidata SEC Central Index Key ' || c || ' (the person page is linked to that insider by the SEC loader)'
        FROM wiki.entity e CROSS JOIN LATERAL unnest(e.cik) c JOIN sec_person_links s ON s.source = 'insider' AND s.key = lpad(c, 10, '0')
        WHERE e.kind = 'person' ON CONFLICT DO NOTHING""").rowcount
    conn.commit()
    out["cik person"] = n
    log(f"match people: CIK: {out['cik insider']:,} insiders, {out['cik person']:,} person pages ({time.time() - t0:.0f}s)")

    # 2. Employer / member-of / board of an organization the person is on in FURP, plus the same name.
    t0 = time.time()
    for t in ("wiki_pe", "wiki_fcore"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    _prep_tables(conn)
    conn.execute("""CREATE TEMP TABLE wiki_fcore AS SELECT f.core, f.ein FROM wiki_fc f JOIN wiki_fcn c ON c.core = f.core AND c.n <= 3""")
    conn.execute("CREATE INDEX ON wiki_fcore (core)")
    conn.execute("""CREATE TEMP TABLE wiki_pe AS
        SELECT DISTINCT qid, ein, via FROM (
          SELECT p.qid, o.ein, 'employer_ein' AS via FROM wiki.entity p
            CROSS JOIN LATERAL unnest(coalesce(p.emp_q, '{}') || coalesce(p.mem_q, '{}')) r(q)
            JOIN wiki.entity o ON o.qid = r.q AND o.ein IS NOT NULL WHERE p.kind = 'person'
          UNION ALL
          SELECT b.q, o.ein, 'board_ein' FROM wiki.entity o CROSS JOIN LATERAL unnest(o.board_q) b(q)
            WHERE o.ein IS NOT NULL AND o.board_q IS NOT NULL
          UNION ALL
          SELECT p.qid, f.ein, 'employer_name' FROM wiki.entity p
            CROSS JOIN LATERAL unnest(coalesce(p.emp_q, '{}') || coalesce(p.mem_q, '{}')) r(q)
            JOIN wiki.org_name n ON n.qid = r.q JOIN wiki_fcore f ON f.core = n.core WHERE p.kind = 'person'
          UNION ALL
          SELECT b.q, f.ein, 'employer_name' FROM wiki.entity o CROSS JOIN LATERAL unnest(o.board_q) b(q)
            JOIN wiki.org_name n ON n.qid = o.qid JOIN wiki_fcore f ON f.core = n.core WHERE o.board_q IS NOT NULL
        ) z WHERE qid IN (SELECT qid FROM wiki.entity WHERE kind = 'person')""")
    conn.execute("CREATE INDEX ON wiki_pe (qid)")
    conn.execute("ANALYZE wiki_pe")
    npe = conn.execute("SELECT count(*), count(DISTINCT qid), count(DISTINCT ein) FROM wiki_pe").fetchone()
    log(f"match people: {npe[0]:,} person-organization pairs from Wikidata ({npe[1]:,} people, {npe[2]:,} EINs) ({time.time() - t0:.0f}s)")
    rows = conn.execute("""
        SELECT pe.qid, m.cluster_id, p.name_norm, pn.name_norm AS wname, pe.via, p.ein, min(p.title) AS title
        FROM wiki_pe pe JOIN wiki.person_name pn ON pn.qid = pe.qid
        JOIN people p ON p.ein = pe.ein AND (p.name_norm = pn.name_norm
             OR (np_first_name(p.name_norm) = split_part(pn.fl, ' ', 1) AND np_last_name(p.name_norm) = split_part(pn.fl, ' ', 2)))
        JOIN person_cluster_members m ON m.person_id = p.id
        GROUP BY pe.qid, m.cluster_id, p.name_norm, pn.name_norm, pe.via, p.ein""").fetchall()
    log(f"match people: {len(rows):,} candidate rows at the same organizations ({time.time() - t0:.0f}s)")
    best: dict[tuple[str, int], dict] = {}
    for qid, cid, fname, wname, via, ein, title in rows:
        if not (fname == wname or middles_ok(fname, wname)):
            continue
        k = (qid, cid)
        b = best.setdefault(k, {"eins": {}, "via": set(), "exact": False, "titles": set()})
        b["eins"][ein] = via
        b["via"].add(via)
        b["exact"] |= fname == wname
        if title:
            b["titles"].add(title[:40])
    names = {r[0]: r[1] for r in conn.execute("SELECT ein, name FROM organizations WHERE ein = ANY(%s)", ([e for b in best.values() for e in b["eins"]][:200000],)).fetchall()}
    by_cluster: dict[int, set] = {}
    for (qid, cid) in best:
        by_cluster.setdefault(cid, set()).add(qid)
    ins = []
    amb = 0
    for (qid, cid), b in best.items():
        if len(by_cluster[cid]) > 1:
            amb += 1
            continue
        ein_route = bool(b["via"] & {"employer_ein", "board_ein"})
        e0 = next(iter(b["eins"]))
        org = names.get(e0, e0)
        how = "Wikidata lists an organization (" + ("EIN match" if ein_route else "name match") + ") where the filings name this person"
        ev = f"{how}: {org} (EIN {e0}); {'the same name' if b['exact'] else 'the same first and last name, compatible middle name'}" \
             + (f"; the filing title: {sorted(b['titles'])[0]}" if b["titles"] else "")
        method = ("person_org_ein" if ein_route else "person_org_name") + ("" if b["exact"] else "_fl")
        ins.append(("person", str(cid), qid, method, "high" if ein_route and b["exact"] else "medium", ev))
    n = 0
    for i in range(0, len(ins), 20000):
        n += _insert_links(conn, ins[i:i + 20000])
        conn.commit()
    out["org route"] = n
    log(f"match people: employer/board route: {n:,} links ({amb:,} dropped: two Wikipedia people for one page) ({time.time() - t0:.0f}s)")
    # 3. SEC insiders at a company Wikidata gives as the person's employer, member-of or board (the company's CIK is the issuer).
    t0 = time.time()
    conn.execute("DROP TABLE IF EXISTS wiki_ic")
    conn.execute("""CREATE TEMP TABLE wiki_ic AS
        SELECT DISTINCT qid, lpad(c, 10, '0') AS cik FROM (
          SELECT p.qid, c FROM wiki.entity p CROSS JOIN LATERAL unnest(coalesce(p.emp_q, '{}') || coalesce(p.mem_q, '{}')) r(q)
            JOIN wiki.entity o ON o.qid = r.q AND o.cik IS NOT NULL CROSS JOIN LATERAL unnest(o.cik) c WHERE p.kind = 'person'
          UNION ALL
          SELECT b.q, c FROM wiki.entity o CROSS JOIN LATERAL unnest(o.board_q) b(q) CROSS JOIN LATERAL unnest(o.cik) c
            WHERE o.cik IS NOT NULL AND o.board_q IS NOT NULL) z
        WHERE qid IN (SELECT qid FROM wiki.entity WHERE kind = 'person')""")
    conn.execute("CREATE INDEX ON wiki_ic (cik)")
    conn.execute("ANALYZE wiki_ic")
    rows = conn.execute("""
        SELECT ic.qid, ow.owner_cik, ow.name_norm, pn.name_norm AS wname, min(f.issuer_name) AS issuer, min(ow.title) AS title, min(ow.relationship) AS rel
        FROM wiki_ic ic JOIN sec_insider_filings f ON f.issuer_cik = ic.cik
        JOIN sec_insider_owners ow ON ow.accession = f.accession
        JOIN wiki.person_name pn ON pn.qid = ic.qid
        WHERE ow.name_norm = pn.name_norm
           OR (np_first_name(ow.name_norm) = split_part(pn.fl, ' ', 1) AND np_last_name(ow.name_norm) = split_part(pn.fl, ' ', 2))
        GROUP BY ic.qid, ow.owner_cik, ow.name_norm, pn.name_norm""").fetchall()
    log(f"match people: {len(rows):,} insider candidates at Wikidata employers with a CIK ({time.time() - t0:.0f}s)")
    bestc: dict[tuple[str, str], tuple] = {}
    for qid, ocik, oname, wname, issuer, title, rel in rows:
        if not (oname == wname or middles_ok(oname, wname)):
            continue
        k = (qid, ocik)
        if k not in bestc or oname == wname:
            bestc[k] = (oname == wname, issuer, title or rel)
    by_ins: dict[str, set] = {}
    for (qid, ocik) in bestc:
        by_ins.setdefault(ocik, set()).add(qid)
    ins, ins_p = [], []
    for (qid, ocik), (exact, issuer, role) in bestc.items():
        if len(by_ins[ocik]) > 1:
            continue
        ev = (f"Wikidata lists {issuer} (SEC CIK) as an employer, membership or board of this person; the insider filings name "
              f"{'the same name' if exact else 'the same first and last name'} there" + (f" ({role})" if role else ""))
        method = "insider_issuer" if exact else "insider_issuer_fl"
        ins.append(("sec_insider", ocik.lstrip("0"), qid, method, "high" if exact else "medium", ev))
        ins_p.append(("person", ocik, qid, method, "high" if exact else "medium", ev))
    n = _insert_links(conn, ins)
    sp = {r[0]: r[1] for r in conn.execute("SELECT key, cluster_id FROM sec_person_links WHERE source = 'insider' AND key = ANY(%s)", ([x[1] for x in ins_p],)).fetchall()}
    n2 = _insert_links(conn, [("person", str(sp[k]), q, m, c, e) for (_, k, q, m, c, e) in ins_p if k in sp])
    conn.commit()
    out["insider route"] = n
    log(f"match people: SEC insider route: {n:,} insider pages, {n2:,} person pages ({time.time() - t0:.0f}s)")
    # 4. Name only (lower confidence, flagged): the full name is unique among Wikipedia people and among FURP person pages,
    # the Wikipedia person is a US citizen (Wikidata), and the page is not a bank or other institution.
    t0 = time.time()
    conn.execute("DROP TABLE IF EXISTS wiki_wn")
    conn.execute("""CREATE TEMP TABLE wiki_wn AS
        SELECT pn.name_norm, min(pn.qid) AS qid FROM wiki.person_name pn JOIN wiki.entity e ON e.qid = pn.qid
        WHERE array_length(string_to_array(pn.name_norm, ' '), 1) >= 2 AND 'Q30' = ANY(coalesce(e.cit_q, '{}'))
        GROUP BY pn.name_norm HAVING count(DISTINCT pn.qid) = 1""")
    conn.execute("CREATE INDEX ON wiki_wn (name_norm)")
    conn.execute("""DELETE FROM wiki_wn WHERE name_norm IN (SELECT name_norm FROM wiki.person_name GROUP BY name_norm HAVING count(DISTINCT qid) > 1)""")
    conn.execute("DROP TABLE IF EXISTS wiki_tokfirst")
    conn.execute("CREATE TEMP TABLE wiki_tokfirst AS SELECT first_name AS t, count(*) AS n FROM person_clusters WHERE first_name IN "
                 "(SELECT split_part(name_norm, ' ', 1) FROM wiki_wn) GROUP BY 1")
    conn.execute("DROP TABLE IF EXISTS wiki_toklast")
    conn.execute("CREATE TEMP TABLE wiki_toklast AS SELECT last_name AS t, count(*) AS n FROM person_clusters WHERE last_name IN "
                 "(SELECT split_part(regexp_replace(name_norm, ' (jr|sr|ii|iii|iv)$', ''), ' ', array_length(string_to_array(regexp_replace(name_norm, ' (jr|sr|ii|iii|iv)$', ''), ' '), 1)) FROM wiki_wn) GROUP BY 1")
    conn.execute("CREATE INDEX ON wiki_tokfirst (t)")
    conn.execute("CREATE INDEX ON wiki_toklast (t)")
    total = conn.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'person_clusters'").fetchone()[0] or 15_000_000
    rows = conn.execute("""
        SELECT c.id, w.qid, c.display_name, c.latest_title, c.states[1:2], (coalesce(f.n, 1)::float8 * coalesce(l.n, 1) / %s) AS expected
        FROM wiki_wn w JOIN person_clusters c ON c.name_norm = w.name_norm
        JOIN wiki.entity e ON e.qid = w.qid
        LEFT JOIN wiki_tokfirst f ON f.t = c.first_name LEFT JOIN wiki_toklast l ON l.t = c.last_name
        WHERE NOT coalesce(c.is_institution, false) AND c.n_filings >= 1
          AND (e.death_year IS NULL OR e.death_year >= c.first_year - 1)
          AND (e.birth_year IS NULL OR e.birth_year BETWEEN 1915 AND 2006)
          AND NOT EXISTS (SELECT 1 FROM person_clusters c2 WHERE c2.name_norm = c.name_norm AND c2.id <> c.id)""", (total,)).fetchall()
    ins = [("person", str(cid), qid, "person_name_rare" if exp < RARE else "person_name_uncommon" if exp < UNCOMMON else "person_name_only", "low",
            f"the same full name ({name}); the only person with it on Wikipedia and in the filings; no other signal (the filings: {title or 'no title'}, {', '.join(states or [])}); "
            f"expected number of unrelated people with this name in FURP {exp:.3f}")
           for cid, qid, name, title, states, exp in rows]
    n = 0
    for i in range(0, len(ins), 20000):
        n += _insert_links(conn, ins[i:i + 20000])
        conn.commit()
    out["name only"] = n
    log(f"match people: name only: {n:,} links ({time.time() - t0:.0f}s)")
    return out


# --- leads from the enwiki dump -------------------------------------------------------------------------------

LEAD_MAX = 300
_ABBR = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|Mt|Inc|Co|Corp|Ltd|vs|No|Prof|Gen|Gov|Sen|Rep|Rev|Lt|Col|Capt|Sgt|Hon|Fr|Ft|est|approx|ca|c|b|d|Ph|M|Bros|Assn|Univ|Dept|Mfg|Intl)|\b[A-Z]|\b[A-Z]\.[A-Z])\.$")
_SENT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z\"'(])")


_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_DATE_T = {"birth date and age", "birth date", "death date and age", "death date", "birth-date", "death-date", "bda", "dob",
           "birth date and age2", "death-date and age", "start date", "end date", "start date and age", "dda", "bd"}
_TEXT_T = {"nowrap", "nobr", "small", "smallcaps", "small caps", "lang", "transliteration", "translit", "tlit", "abbr", "linktext", "lc",
           "uc", "lower", "upper", "sort", "nobold", "noitalic", "em", "strong", "mono", "code", "angle", "'"}
_DASH_T = {"spaced ndash", "snd", "spnd", "spaced en dash", "spaced en dash space"}


def _template_text(t) -> str | None:
    """Plain text for the few templates whose output belongs in a lead sentence (dates, dashes, wrappers); None = drop."""
    name = str(t.name).strip().lower()
    pos = [str(p.value).strip() for p in t.params if not p.showkey]
    if name in _DASH_T:
        return " \u2013 "
    if name in ("ndash", "en dash"):
        return "\u2013"
    if name in ("mdash", "em dash"):
        return "\u2014"
    if name in ("nbsp", "spaces", "space"):
        return " "
    if name in _DATE_T:
        try:
            y, m, d = int(pos[0]), int(pos[1]), int(pos[2])
            return f"{_MONTHS[m - 1]} {d}, {y}"
        except (IndexError, ValueError):
            try:
                y, m = int(pos[0]), int(pos[1])
                return f"{_MONTHS[m - 1]} {y}"
            except (IndexError, ValueError):
                return pos[0] if pos and pos[0].isdigit() else None
    if name in ("circa", "c.", "circa2") or name == "c":
        return "c. " + (pos[0] if pos else "")
    if name in _TEXT_T or name.startswith("lang-"):
        v = pos[-1] if name in ("lang", "transliteration", "translit", "tlit") and pos else (pos[0] if pos else "")
        if name.startswith("lang-") and pos:
            v = pos[0]
        return v or None
    if name == "convert" and len(pos) >= 2:
        return f"{pos[0]} {pos[1]}"
    return None


def _flatten_templates(code) -> None:
    for _ in range(6):
        changed = False
        for t in list(code.filter_templates(recursive=True)):
            if any(t is not u and str(u) in str(t) and u in t.params for u in ()):
                continue
            txt = _template_text(t)
            try:
                code.replace(t, txt if txt is not None else "")
                changed = True
            except ValueError:
                pass
        if not changed or not code.filter_templates():
            break


def _skip_leading_blocks(txt: str) -> str:
    """Drop the templates (infoboxes, hatnotes, maintenance banners), files and magic words that open an article, counting
    braces, so that only the prose is parsed."""
    i, n = 0, len(txt)
    while True:
        while i < n and txt[i] in " \t\r\n":
            i += 1
        if txt.startswith("{{", i):
            open_, close_ = "{{", "}}"
        elif re.match(r"\[\[\s*(?:file|image):", txt[i:i + 12], re.I):
            open_, close_ = "[[", "]]"
        elif txt.startswith("__", i):
            j = txt.find("__", i + 2)
            if j < 0:
                break
            i = j + 2
            continue
        else:
            break
        depth, j = 0, i
        while j < n:
            if txt.startswith(open_, j):
                depth += 1
                j += 2
            elif txt.startswith(close_, j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        i = j
    return txt[i:]


def _strip_markup(wikitext: str):
    """(short description or None, plain lead paragraph or None) from an article's wikitext."""
    import mwparserfromhell as mw
    m0 = re.search(r"(?m)^==", wikitext)
    txt = wikitext[:m0.start()] if m0 else wikitext
    txt = txt[:30000]                       # only the lead is parsed: parsing a whole article costs 20 times more
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    txt = re.sub(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", "", txt, flags=re.S | re.I)
    txt = re.sub(r"<(gallery|math|timeline|imagemap|noinclude)[^>]*>.*?</\1>", "", txt, flags=re.S | re.I)
    sm = re.search(r"\{\{\s*(?:short description|shortdesc|short desc)\s*\|\s*([^{}|]*?)\s*(?:\||\}\})", txt, re.I)
    short = mw.parse(sm.group(1)).strip_code().strip() if sm else None
    lead = _skip_leading_blocks(txt)
    lc = mw.parse(lead)
    for l in list(lc.filter_wikilinks()):
        if re.match(r"\s*(file|image|category|media):", str(l.title), re.I):
            try:
                lc.remove(l)
            except ValueError:
                pass
    for t in list(lc.filter_templates(recursive=False)):
        nm = str(t.name).strip().lower()
        if nm.startswith(("infobox", "use ", "good article", "featured article", "pp", "about", "redirect", "for ", "distinguish",
                          "other uses", "see also", "main", "hatnote", "efn", "sfn", "cite", "multiple issues", "refimprove",
                          "bLP", "authority control", "short description", "coord", "taxobox", "speciesbox", "automatic taxobox")):
            try:
                lc.remove(t)
            except ValueError:
                pass
    _flatten_templates(lc)
    plain = lc.strip_code(normalize=True, collapse=True)
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", plain)]
    for p in paras:
        if len(p) < 40 or p[0] in ":*#|{}!" or p.startswith(("thumb", "File:", "Image:")):
            continue
        p = re.sub(r"\(\s*(?:[;,:]\s*)*\)", "", p)
        p = re.sub(r"\(\s*(?:[;,]\s*)+", "(", p)
        p = re.sub(r"\s+([,.;:)])", r"\1", p).replace("( ", "(")
        p = re.sub(r"\s{2,}", " ", p).strip()
        return short, p
    return short, None


def lead_sentences(p: str | None, limit: int = LEAD_MAX) -> str | None:
    """The first sentence, and the second when both fit in `limit` characters (cut at a word with an ellipsis when the
    first alone is longer)."""
    if not p:
        return None
    parts, cur = [], ""
    for piece in _SENT.split(p):
        cur = f"{cur} {piece}".strip() if cur else piece
        if _ABBR.search(cur.rstrip()) and not cur.rstrip().endswith(("..", "?")):
            continue
        parts.append(cur)
        cur = ""
    if cur:
        parts.append(cur)
    out = ""
    for s in parts[:2]:
        cand = f"{out} {s}".strip()
        if len(cand) > limit and out:
            break
        out = cand
        if len(out) >= 140:
            break
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return out or None


def _index_offsets(index_path: str, titles: set[str]) -> dict[int, set[str]]:
    import bz2
    want = {t: t for t in titles}
    by_off: dict[int, set[str]] = {}
    with bz2.open(index_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            off, _, rest = line.partition(":")
            _, _, title = rest.partition(":")
            title = title.rstrip("\n")
            if title in want:
                by_off.setdefault(int(off), set()).add(title)
    return by_off


LEAD_PRIORITY = {"person_cik": 0, "org_ein": 0, "sec_cik": 0, "college_ein": 0, "person_org_ein": 1, "insider_issuer": 1,
                 "college_website_name": 2, "org_website_name": 2, "org_name_city": 2, "org_name_citydesc": 2, "college_name": 2,
                 "person_org_name": 2, "person_org_ein_fl": 3, "person_org_name_fl": 3, "insider_issuer_fl": 3, "person_name_rare": 4}


def lead(dump: str = "/bulk/wikipedia/enwiki-latest-pages-articles-multistream.xml.bz2",
         index: str = "/bulk/wikipedia/enwiki-latest-pages-articles-multistream-index.txt.bz2", limit: int | None = None) -> None:
    """Short description and lead sentence(s) of every entity that has a shown link, from the multistream dump: only the
    streams that hold those pages are read (and each only up to its last wanted page), the surest links first, so a stopped run
    has done the most important pages. Pages without a lead keep Wikidata's one-line description on the page."""
    import bz2
    import html
    t0 = time.time()
    with db.connect() as conn:
        ensure_schema(conn)
        rows = conn.execute("""SELECT e.qid, e.title, min(CASE l.method WHEN 'person_cik' THEN 0 WHEN 'org_ein' THEN 0 WHEN 'sec_cik' THEN 0
                                   WHEN 'college_ein' THEN 0 WHEN 'person_org_ein' THEN 1 WHEN 'insider_issuer' THEN 1 WHEN 'person_name_rare' THEN 4
                                   WHEN 'person_org_ein_fl' THEN 3 WHEN 'person_org_name_fl' THEN 3 WHEN 'insider_issuer_fl' THEN 3 ELSE 2 END)
                               FROM wiki.entity e JOIN wiki.link l ON l.qid = e.qid
                               WHERE l.show AND e.has_article AND e.title IS NOT NULL AND e.lead_fetched IS NULL GROUP BY e.qid, e.title""").fetchall()
        if limit:
            rows = rows[:limit]
    by_title = {t: (q, p) for q, t, p in rows}
    log(f"lead: {len(by_title):,} articles wanted")
    offsets = _index_offsets(index, set(by_title))
    order = sorted(offsets, key=lambda o: (min(by_title[t][1] for t in offsets[o]), o))
    log(f"lead: {sum(len(v) for v in offsets.values()):,} found in {len(offsets):,} streams of the index ({time.time() - t0:.0f}s)")
    got = 0
    page_re = re.compile(r"<page>(.*?)</page>", re.S)
    title_re = re.compile(r"<title>(.*?)</title>")
    text_re = re.compile(r"<text[^>]*>(.*?)</text>", re.S)
    with db.connect() as conn, open(dump, "rb") as f:
        for n, off in enumerate(order, 1):
            want = set(offsets[off])
            f.seek(off)
            d = bz2.BZ2Decompressor()
            pending = ""
            raw = b""
            while want and not d.eof:
                chunk = f.read(1 << 18)
                if not chunk:
                    break
                while want and (chunk or (d.needs_input is False)):
                    try:
                        piece = d.decompress(chunk, 1 << 18)
                    except Exception:      # noqa: BLE001 - a damaged stream
                        want = set()
                        break
                    chunk = b""
                    raw += piece
                    try:
                        text = raw.decode("utf-8")
                        raw = b""
                    except UnicodeDecodeError as ex:       # a character split across two pieces
                        text, raw = raw[:ex.start].decode("utf-8", "replace"), raw[ex.start:]
                    pending += text
                    while True:
                        e = pending.find("</page>")
                        if e < 0:
                            break
                        body, pending = pending[:e], pending[e + 7:]
                        tm = title_re.search(body)
                        if not tm:
                            continue
                        title = html.unescape(tm.group(1))
                        if title not in want:
                            continue
                        want.discard(title)
                        xm = text_re.search(body)
                        wt = html.unescape(xm.group(1)) if xm else ""
                        if wt.lstrip().lower().startswith("#redirect"):
                            continue
                        try:
                            short, plain = _strip_markup(wt)
                            ld = lead_sentences(plain)
                        except Exception as ex:  # noqa: BLE001 - one odd page
                            log(f"lead: {title}: {type(ex).__name__}")
                            continue
                        conn.execute("UPDATE wiki.entity SET short_desc = %s, lead = %s, lead_fetched = now() WHERE qid = %s",
                                     ((short or None) and short[:200], ld, by_title[title][0]))
                        got += 1
                    if d.eof or d.needs_input:
                        break
            if n % 200 == 0:
                conn.commit()
                log(f"lead: {n:,}/{len(order):,} streams, {got:,} leads ({time.time() - t0:.0f}s)")
        conn.commit()
    log(f"lead: done, {got:,} leads from {len(order):,} streams in {time.time() - t0:.0f}s")


def sample(method: str, n: int = 50, seed: float = 0.5) -> list:
    with db.connect() as conn:
        conn.execute("SELECT setseed(%s)", (seed,))
        rows = conn.execute("""
            SELECT l.kind, l.key, l.qid, l.confidence, l.evidence, e.label, e.title, e.wd_desc, e.birth_year, e.website
            FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid WHERE l.method = %s ORDER BY random() LIMIT %s""", (method, n)).fetchall()
        out = []
        for r in rows:
            if r[0] == "person":
                f = conn.execute("SELECT display_name, states, orgs[1:3], latest_title FROM person_clusters WHERE id = %s", (int(r[1]),)).fetchone()
            elif r[0] == "org":
                f = conn.execute("SELECT name, city, state, website FROM organizations WHERE ein = %s", (r[1],)).fetchone()
            elif r[0] == "college":
                f = conn.execute("SELECT name, city, state, website FROM colleges WHERE unitid = %s", (int(r[1]),)).fetchone()
            elif r[0] == "sec":
                f = conn.execute("SELECT name FROM sec_fin_subs WHERE cik::bigint = %s ORDER BY filed DESC LIMIT 1", (int(r[1]),)).fetchone()
            elif r[0] == "sec_insider":
                f = conn.execute("SELECT owner_name, state, title FROM sec_insider_owners WHERE ltrim(owner_cik, '0') = %s LIMIT 1", (r[1],)).fetchone()
            else:
                f = None
            out.append((r, tuple(f) if f else None))
    for i, (r, f) in enumerate(out, 1):
        print(f"[{i}] {r[0]}:{r[1]} {r[2]} ({r[3]})\n    FURP: {f}\n    WIKI: {r[5]} | {r[6]} | {r[7]} | born {r[8]} | {r[9]}\n    WHY : {(r[4] or '')[:230]}")
    return out


def judge(method: str, judged: int, correct: int, note: str = "") -> None:
    with db.connect() as conn:
        conn.execute("""INSERT INTO wiki.precision (method, judged, correct, note) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (method) DO UPDATE SET judged = EXCLUDED.judged, correct = EXCLUDED.correct,
                        note = EXCLUDED.note, judged_at = now()""", (method, judged, correct, note))
        conn.commit()


def status() -> None:
    with db.connect() as conn:
        ensure_schema(conn)
        for r in conn.execute("SELECT kind, count(*), count(lead) FROM wiki.entity GROUP BY 1").fetchall():
            print("entity", r)
        for r in conn.execute("""SELECT l.kind, l.method, l.confidence, count(*), count(*) FILTER (WHERE l.show), p.judged, p.correct
                                 FROM wiki.link l LEFT JOIN wiki.precision p USING (method) GROUP BY 1, 2, 3, 6, 7 ORDER BY 1, 2""").fetchall():
            print("link", r)


# --- publish: show flags, cross-references, leaderboard tables ------------------------------------------------------

MIN_JUDGED = 50
MIN_PRECISION = 0.90


def publish(xlinks: bool = True) -> None:
    """Show only the methods whose judged precision is high enough; write xlinks rows (both ways, linker 'wikipedia');
    rebuild the leaderboard source tables."""
    from app.wikipedia import METHOD_TEXT
    t0 = time.time()
    with db.connect() as conn:
        ensure_schema(conn)
        conn.execute("SET statement_timeout = 0")
        conn.execute("UPDATE wiki.link SET show = false")
        n = conn.execute("""UPDATE wiki.link l SET show = true FROM wiki.precision p
                            WHERE p.method = l.method AND p.judged >= %s AND p.correct::float / p.judged >= %s""",
                         (MIN_JUDGED, MIN_PRECISION)).rowcount
        # an exact identifier (Wikidata's SEC CIK on a person) has too few links to sample 50: all of them were judged
        n += conn.execute("""UPDATE wiki.link l SET show = true FROM wiki.precision p
                             WHERE p.method = l.method AND l.method = 'person_cik' AND p.judged >= 2 AND p.correct = p.judged""").rowcount
        # one Wikipedia article per page: when two articles claim one page, show the stronger method only
        conn.execute("""UPDATE wiki.link l SET show = false FROM (
                            SELECT kind, key, qid, row_number() OVER (PARTITION BY kind, key ORDER BY
                                   CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, method, qid) AS rn
                            FROM wiki.link WHERE show) r
                        WHERE r.rn > 1 AND l.kind = r.kind AND l.key = r.key AND l.qid = r.qid""")
        conn.commit()
        log(f"publish: {n:,} links shown")
        # cross-references (shared table: written at go-live, after the code that shows them is deployed)
        if xlinks and conn.execute("SELECT to_regclass('xlinks_new') IS NOT NULL").fetchone()[0]:
            log("publish: xlinks is being rebuilt; run publish again later")
            return
        if xlinks:
            conn.execute("DELETE FROM xlinks WHERE linker = 'wikipedia'")
        if xlinks:
            text = " ".join("WHEN '%s' THEN '%s'" % (m, t.replace("'", "''")) for m, t in METHOD_TEXT.items())
            exact = "'person_cik', 'org_ein', 'sec_cik', 'college_ein'"
            names = """CASE l.kind WHEN 'person' THEN (SELECT display_name FROM person_clusters WHERE id = l.key::bigint)
                                  WHEN 'org' THEN (SELECT name FROM organizations WHERE ein = l.key)
                                  WHEN 'college' THEN (SELECT name FROM colleges WHERE unitid = l.key::int)
                                  WHEN 'sec' THEN (SELECT name FROM sec_fin_subs WHERE cik::bigint = l.key::bigint ORDER BY filed DESC LIMIT 1)
                                  WHEN 'sec_insider' THEN (SELECT owner_name FROM sec_insider_owners WHERE ltrim(owner_cik, '0') = l.key LIMIT 1) END"""
            conn.execute(f"""CREATE TEMP TABLE wiki_pub AS SELECT l.kind, l.key, l.qid, l.method, e.title, {names} AS pname,
                                  CASE WHEN l.method IN ({exact}) THEN 'EXACT' ELSE 'FUZZY' END || ': ' ||
                                  CASE l.method {text} ELSE l.method END AS how
                             FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid WHERE l.show AND e.title IS NOT NULL""")
            a = conn.execute("""INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                                SELECT 'wikipedia', qid, title, NULL, kind, key, pname, how, 'wikipedia' FROM wiki_pub
                                ON CONFLICT DO NOTHING""").rowcount
            b = conn.execute("""INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                                SELECT kind, key, pname, NULL, 'wikipedia', qid, title, how, 'wikipedia' FROM wiki_pub
                                ON CONFLICT DO NOTHING""").rowcount
            conn.commit()
            log(f"publish: {a:,} + {b:,} xlinks rows")
        # leaderboard sources
        conn.execute("DROP TABLE IF EXISTS wiki.board_people")
        conn.execute("""CREATE TABLE wiki.board_people AS
            SELECT DISTINCT ON (l.key) l.key::bigint AS cluster_id, l.qid, l.method, c.display_name AS name, e.title AS wiki_title,
                   'https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/' || l.qid AS wiki_url,
                   coalesce(e.short_desc, e.wd_desc) AS wiki_desc,
                   r.ein, coalesce(o.name, f.org_name) AS org_name, f.state, f.form_type, f.tax_year, f.id AS filing_id, p.title,
                   (coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0)) AS total
            FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid JOIN person_clusters c ON c.id = l.key::bigint
            JOIN person_cluster_members m ON m.cluster_id = c.id JOIN people p ON p.id = m.person_id
            JOIN filings f ON f.id = p.filing_id AND NOT f.superseded
            CROSS JOIN LATERAL (SELECT p.ein) r LEFT JOIN organizations o ON o.ein = p.ein
            WHERE l.show AND l.kind = 'person' AND NOT coalesce(c.is_institution, false)
              AND (coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0)) > 0
            ORDER BY l.key, (coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0)) DESC, f.tax_year DESC""")
        conn.execute("DROP TABLE IF EXISTS wiki.board_orgs")
        conn.execute("""CREATE TABLE wiki.board_orgs AS
            SELECT p.ein, count(DISTINCT l.key) AS n_people,
                   left(string_agg(DISTINCT c.display_name, '; ' ORDER BY c.display_name), 300) AS names
            FROM wiki.link l JOIN person_clusters c ON c.id = l.key::bigint
            JOIN person_cluster_members m ON m.cluster_id = c.id JOIN people p ON p.id = m.person_id
            WHERE l.show AND l.kind = 'person' GROUP BY p.ein""")
        conn.execute("DROP TABLE IF EXISTS wiki.board_orgs_wp")
        conn.execute("""CREATE TABLE wiki.board_orgs_wp AS
            SELECT DISTINCT ON (l.key) l.key AS ein, e.title AS wiki_title, coalesce(e.short_desc, e.wd_desc) AS wiki_desc,
                   e.inception AS founded, 'https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/' || l.qid AS wiki_url
            FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid WHERE l.show AND l.kind = 'org'
            ORDER BY l.key, (l.confidence = 'high') DESC, l.qid""")
        conn.commit()
        c = {t: conn.execute(f"SELECT count(*) FROM wiki.{t}").fetchone()[0] for t in ("board_people", "board_orgs", "board_orgs_wp")}
        log(f"publish: board sources {c} ({time.time() - t0:.0f}s); build the boards: scripts/load.py boards --only wikipedia-nonprofit-leaders,wikipedia-notable-boards,wikipedia-big-nonprofits")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="loader.wikipedia")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("load"); s.add_argument("--dir", default=EXTRACT)
    s = sub.add_parser("match"); s.add_argument("--only", choices=["orgs", "people"])
    s = sub.add_parser("sample"); s.add_argument("method"); s.add_argument("--n", type=int, default=50)
    s = sub.add_parser("judge"); s.add_argument("method"); s.add_argument("judged", type=int); s.add_argument("correct", type=int); s.add_argument("--note", default="")
    sub.add_parser("status")
    s = sub.add_parser("publish"); s.add_argument("--no-xlinks", action="store_true")
    sub.add_parser("refine")
    s = sub.add_parser("lead"); s.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "load":
        load(a.dir)
    elif a.cmd == "match":
        with db.connect() as conn:
            ensure_schema(conn)
            if a.only in (None, "orgs"):
                conn.execute("DELETE FROM wiki.link WHERE method NOT LIKE 'manual%' AND kind IN ('org', 'college', 'sec')")
            if a.only in (None, "people"):
                conn.execute("DELETE FROM wiki.link WHERE method NOT LIKE 'manual%' AND kind IN ('person', 'sec_insider')")
            conn.commit()
            if a.only in (None, "orgs"):
                match_orgs(conn)
                refine_website(conn)
            if a.only in (None, "people"):
                match_people(conn)
    elif a.cmd == "sample":
        sample(a.method, a.n)
    elif a.cmd == "judge":
        judge(a.method, a.judged, a.correct, a.note)
    elif a.cmd == "status":
        status()
    elif a.cmd == "refine":
        with db.connect() as conn:
            refine_website(conn)
    elif a.cmd == "publish":
        publish(xlinks=not a.no_xlinks)
    elif a.cmd == "lead":
        lead(limit=a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
