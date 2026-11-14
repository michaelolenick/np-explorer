"""GDELT news and events for people and organizations (owner, 2026-11-14: "news/event coverage at large scale from GDELT").

Source: the GDELT Project, https://www.gdeltproject.org/ , GKG 2.0 (a record per news article: URL, domain, title,
language, tone, themes, and the people and organizations the article names, with offsets), 15-minute files from
2015-02-18. Terms: free for any use; any use or redistribution must cite the GDELT Project and link to
https://www.gdeltproject.org/ (shown on every block and on /data#gdelt). Metadata and links only: article text is never
fetched or stored.

Pipeline
  loader/gdelt_parse.py   download each day's 96 files in memory, keep articles that name a name FURP knows (dictionaries
                          from `dict`), write /bulk/gdelt/parsed/<day>.a.tsv.gz / .m.tsv.gz / .done (no database; runs on
                          either server). Zips are never kept.
  load                    each parsed day -> schema gdelt, in one transaction per day with a progress line, restartable by
                          day (gdelt.loaded_days): resolves the day's name hits to FURP entities (rules below), keeps
                          only articles that resolved, adds links and per-month counts.
  loader/gdelt_events.py  the same for GDELT Events 2.0 (export files): events whose actor is a known multi-word organization name
                          -> <day>.e.tsv.gz; `load-events` -> gdelt.events and gdelt.event_links (organizations only).
  summarize               gdelt.entity_news (per entity: articles, first/last seen, last 30 days, name), gdelt.stats (the
                          counts the pages show; they update themselves), the /news leaderboards' source.

Rules (precision first; samples judged with `sample`)
  organizations  the GDELT organization's name core (loader.recalls.core) equals the core of exactly one record of a kind
                 (up to 5 for kinds that carry several ids per company); very frequent names (gdelt.famous) link only to
                 SEC filers, colleges, IPO registrants, advisers, lobbying clients and nonprofits of $10M+ revenue.
  people         a name that belongs to exactly one FURP person cluster and is rare in the news links by "unique name"; every
                 other case (a name shared by clusters, or a famous name) links only when an organization of that cluster
                 (its Form 990 organizations) is also named in the same article, and only to the one cluster that fits.

Usage: python -m loader.gdelt dict | maps | famous | load [--from D --to D --max-days N] | load-events | summarize | daily | status
       | sample [--n 50] [--how organization|person]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import sys
import time
from pathlib import Path

from loader import db, offpeak

PARSED = Path(os.environ.get("GDELT_PARSED_DIR", "/bulk/gdelt/parsed"))
DICT = Path(os.environ.get("GDELT_DICT_DIR", "/bulk/gdelt/dict"))
SOURCE_NAME = "The GDELT Project"
SOURCE_URL = "https://www.gdeltproject.org/"
FAMOUS_COUNT = 5          # a name seen this often in the sample of parsed days (~20 articles per sampled day) is "famous"
FAMOUS_REV = 10_000_000   # a famous organization name links to a nonprofit only at this revenue or more
LINK_KINDS = ("org", "sec", "college", "ipo_company", "lda_client", "fed", "contractor", "formd", "adv")
FAMOUS_KINDS = ("sec", "college", "ipo_company", "adv", "lda_client")
MULTI = ("fed", "lda_client", "fec_committee", "fara_registrant", "contractor")      # several ids per company
GROUP_MAX = 5
COMMON_LAST = 300         # a surname shared by this many FURP person clusters is common: name alone never links

DDL = """
CREATE SCHEMA IF NOT EXISTS gdelt;
CREATE TABLE IF NOT EXISTS gdelt.articles (aid bigint PRIMARY KEY, seen timestamp NOT NULL, domain text, url text NOT NULL,
    title text, lang text, tone real, themes text);
CREATE TABLE IF NOT EXISTS gdelt.links (ekind text NOT NULL, ekey text NOT NULL, seen timestamp NOT NULL, aid bigint NOT NULL,
    how text, off integer, n smallint, PRIMARY KEY (ekind, ekey, seen, aid));
CREATE TABLE IF NOT EXISTS gdelt.entity_month (ekind text NOT NULL, ekey text NOT NULL, month date NOT NULL, n integer NOT NULL,
    PRIMARY KEY (ekind, ekey, month));
CREATE TABLE IF NOT EXISTS gdelt.loaded_days (day date PRIMARY KEY, records integer, kept integer, articles integer,
    links integer, org_links integer, person_links integer, seconds real, loaded timestamptz DEFAULT now(), host text);
CREATE TABLE IF NOT EXISTS gdelt.org_map (core text NOT NULL, ekind text NOT NULL, ekey text NOT NULL, ename text,
    PRIMARY KEY (core, ekind, ekey));
CREATE TABLE IF NOT EXISTS gdelt.common_last (last_name text PRIMARY KEY);
CREATE TABLE IF NOT EXISTS gdelt.famous (kind text NOT NULL, name text NOT NULL, n integer, PRIMARY KEY (kind, name));
CREATE TABLE IF NOT EXISTS gdelt.entity_news (ekind text NOT NULL, ekey text NOT NULL, name text, n bigint NOT NULL,
    first_seen date, last_seen date, n_30d integer NOT NULL DEFAULT 0, n_month integer NOT NULL DEFAULT 0,
    PRIMARY KEY (ekind, ekey));
CREATE TABLE IF NOT EXISTS gdelt.events (eid bigint PRIMARY KEY, day date NOT NULL, actor1 text, actor2 text, code text,
    goldstein real, mentions integer, articles integer, tone real, place text, country text, url text);
CREATE TABLE IF NOT EXISTS gdelt.event_links (ekind text NOT NULL, ekey text NOT NULL, day date NOT NULL, eid bigint NOT NULL,
    PRIMARY KEY (ekind, ekey, day, eid));
CREATE TABLE IF NOT EXISTS gdelt.event_days (day date PRIMARY KEY, scanned integer, kept integer, events integer, links integer,
    seconds real, loaded timestamptz DEFAULT now(), host text);
CREATE TABLE IF NOT EXISTS gdelt.entity_events (ekind text NOT NULL, ekey text NOT NULL, n integer NOT NULL, first_day date,
    last_day date, PRIMARY KEY (ekind, ekey));
CREATE TABLE IF NOT EXISTS gdelt.stats (k text PRIMARY KEY, v text, updated timestamptz DEFAULT now());
"""


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} gdelt: {msg}", flush=True)


def ensure_schema(conn) -> None:
    conn.execute(DDL)
    conn.commit()


# --- dictionaries -----------------------------------------------------------------------------------------------------

def build_dict() -> dict:
    from loader import gdelt_dict
    return gdelt_dict.build(str(DICT))


# --- organization map ------------------------------------------------------------------------------------------------------

def build_maps() -> int:
    """gdelt.org_map: name core -> record, for the kinds that have pages. One record per core and kind (up to GROUP_MAX
    for kinds with several ids per company); single-word nonprofit names that an SEC filer, adviser or IPO registrant
    also carries go to the company; famous names keep only the prominent kinds."""
    conn = db.connect()
    ensure_schema(conn)
    conn.execute("SET statement_timeout = 0")
    conn.execute("DROP TABLE IF EXISTS gdelt.org_map_new")
    conn.execute("CREATE TABLE gdelt.org_map_new (LIKE gdelt.org_map)")
    conn.execute("""
        INSERT INTO gdelt.org_map_new (core, ekind, ekey, ename)
        SELECT x.core, x.kind, x.key, x.name FROM xref_names x
        JOIN (SELECT core, kind FROM xref_names WHERE kind = ANY(%(kinds)s) AND length(core) >= 5 GROUP BY core, kind
              HAVING count(*) <= CASE WHEN kind = ANY(%(multi)s) THEN %(gmax)s ELSE 1 END) u
          ON u.core = x.core AND u.kind = x.kind
        WHERE x.kind = ANY(%(kinds)s)""", dict(kinds=list(LINK_KINDS), multi=list(MULTI), gmax=GROUP_MAX))
    conn.execute("CREATE INDEX ON gdelt.org_map_new (core)")
    conn.execute("ANALYZE gdelt.org_map_new")
    conn.execute("""DELETE FROM gdelt.org_map_new m WHERE m.ekind = 'org' AND m.core NOT LIKE '%% %%' AND EXISTS
        (SELECT 1 FROM gdelt.org_map_new s WHERE s.core = m.core AND s.ekind IN ('sec', 'ipo_company', 'formd', 'adv'))""")
    conn.execute("""DELETE FROM gdelt.org_map_new m USING gdelt.famous f WHERE f.kind = 'o' AND f.name = m.core
        AND m.ekind <> ALL(%s) AND NOT (m.ekind = 'org' AND coalesce((SELECT latest_total_revenue FROM organizations o
        WHERE o.ein = m.ekey), 0) >= %s)""", (list(FAMOUS_KINDS) + ["org"], FAMOUS_REV))
    conn.execute("""DELETE FROM gdelt.org_map_new m USING gdelt.famous f WHERE f.kind = 'o' AND f.name = m.core
        AND m.ekind = 'org' AND coalesce((SELECT latest_total_revenue FROM organizations o WHERE o.ein = m.ekey), 0) < %s""",
                 (FAMOUS_REV,))
    conn.execute("""CREATE TABLE IF NOT EXISTS gdelt.common_last (last_name text PRIMARY KEY)""")
    conn.execute("TRUNCATE gdelt.common_last")
    conn.execute("""INSERT INTO gdelt.common_last SELECT last_name FROM person_clusters WHERE last_name IS NOT NULL
        GROUP BY 1 HAVING count(*) >= %s""", (COMMON_LAST,))
    n = conn.execute("SELECT count(*) FROM gdelt.org_map_new").fetchone()[0]
    conn.execute("ALTER TABLE gdelt.org_map_new ADD PRIMARY KEY (core, ekind, ekey)")
    conn.execute("DROP TABLE IF EXISTS gdelt.org_map")
    conn.execute("ALTER TABLE gdelt.org_map_new RENAME TO org_map")
    conn.commit()
    _log(f"org_map: {n} rows")
    return n


def build_famous(max_days: int = 220) -> int:
    """Names that are frequent in the news, from a sample of parsed days (every Nth day, up to max_days)."""
    from collections import Counter
    days = sorted(p for p in PARSED.glob("*.m.tsv.gz"))
    if not days:
        raise SystemExit("no parsed days yet")
    step = max(1, len(days) // max_days)
    cnt: Counter = Counter()
    for p in days[::step]:
        seen = set()
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                a = line.rstrip("\n").split("\t")
                if len(a) >= 3:
                    seen.add((a[1], a[2]))        # kind, name (once per day)
        cnt.update(seen)
    # one count per sampled day would cap at the number of days: use mentions instead (sum of article counts)
    cnt2: Counter = Counter()
    for p in days[::step]:
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                a = line.rstrip("\n").split("\t")
                if len(a) >= 3:
                    cnt2[(a[1], a[2])] += 1
    rows = [(k, nm, c) for (k, nm), c in cnt2.items() if c >= FAMOUS_COUNT * max(1, len(days[::step]) // 20)]
    conn = db.connect()
    ensure_schema(conn)
    conn.execute("TRUNCATE gdelt.famous")
    with conn.cursor() as cur:
        db.copy_rows(cur, "gdelt.famous", ["kind", "name", "n"], rows)
    conn.commit()
    _log(f"famous: {len(rows)} names from {len(days[::step])} sampled days")
    return len(rows)


# --- loading a day ------------------------------------------------------------------------------------------------------

STAGE = """
CREATE TEMP TABLE _a (aid bigint, seen text, domain text, url text, title text, lang text, tone text, themes text) ON COMMIT DROP;
CREATE TEMP TABLE _m (aid bigint, kind text, name text, off integer, n integer, rule text) ON COMMIT DROP;
"""

RESOLVE = """
CREATE TEMP TABLE _hot ON COMMIT DROP AS SELECT name FROM _m WHERE kind = 'p' GROUP BY name HAVING count(DISTINCT aid) >= 6;
ANALYZE _hot;
CREATE TEMP TABLE _l ON COMMIT DROP AS
SELECT om.ekind, om.ekey, m.aid, m.off, m.n::smallint AS n, 'o'::text AS side,
       'Exact name match: "' || m.name || '"' AS how
  FROM _m m JOIN gdelt.org_map om ON om.core = m.name WHERE m.kind = 'o';
INSERT INTO _l
SELECT 'person', c.cid::text, c.aid, c.off, c.n::smallint, 'p', 'Unique full name in FURP, rare surname, rare in the news: "' || c.name || '"'
  FROM (SELECT m.aid, m.name, m.off, m.n, pc.id AS cid, count(*) OVER (PARTITION BY m.aid, m.name) AS k
          FROM _m m JOIN person_clusters pc ON pc.name_norm = m.name
         WHERE m.kind = 'p' AND m.rule = 'u'
           AND pc.last_name NOT IN (SELECT last_name FROM gdelt.common_last)
           AND NOT EXISTS (SELECT 1 FROM gdelt.famous f WHERE f.kind = 'p' AND f.name = m.name)
           AND m.name NOT IN (SELECT name FROM _hot)) c
 WHERE c.k = 1;
CREATE TEMP TABLE _corr ON COMMIT DROP AS
SELECT DISTINCT m.aid, m.name, m.off, m.n, mem.cluster_id AS cid, x.ename AS org_name
  FROM _m m
  JOIN _m o ON o.aid = m.aid AND o.kind = 'o'
  JOIN gdelt.org_map x ON x.ekind = 'org' AND x.core = o.name
  JOIN people p ON p.ein = x.ekey AND p.name_norm = m.name
  JOIN person_cluster_members mem ON mem.person_id = p.id
 WHERE m.kind = 'p' AND (m.rule = 'c' OR m.name IN (SELECT name FROM _hot)
        OR EXISTS (SELECT 1 FROM gdelt.famous f WHERE f.kind = 'p' AND f.name = m.name)
        OR EXISTS (SELECT 1 FROM gdelt.common_last c WHERE c.last_name = substring(m.name from '[^ ]+$')));
INSERT INTO _l
SELECT 'person', cid::text, aid, off, n::smallint, 'p', 'Full name and the same organization in the article: "' || name || '" with ' || org_name
  FROM (SELECT DISTINCT ON (aid, cid) *, count(*) OVER (PARTITION BY aid, name) AS k FROM _corr ORDER BY aid, cid) t WHERE k = 1;
"""


def parsed_days(order: str = "desc") -> list[dt.date]:
    out = []
    for p in PARSED.glob("*.done"):
        try:
            out.append(dt.datetime.strptime(p.stem, "%Y%m%d").date())
        except ValueError:
            pass
    return sorted(out, reverse=(order == "desc"))


def load_day(conn, day: dt.date) -> dict:
    ymd = f"{day:%Y%m%d}"
    meta = json.loads((PARSED / f"{ymd}.done").read_text())
    t0 = time.time()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(778201)") if False else None
        if conn.execute("SELECT 1 FROM gdelt.loaded_days WHERE day = %s", (day,)).fetchone():
            return {}
        conn.execute("SET LOCAL statement_timeout = 0")
        conn.execute(STAGE)
        with conn.cursor() as cur:
            with cur.copy("COPY _a FROM STDIN") as cp, gzip.open(PARSED / f"{ymd}.a.tsv.gz", "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    row = line.rstrip("\n").replace("\x00", "").split("\t")
                    if len(row) == 8:
                        cp.write_row(row)
            with cur.copy("COPY _m FROM STDIN") as cp, gzip.open(PARSED / f"{ymd}.m.tsv.gz", "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    row = line.rstrip("\n").replace("\x00", "").split("\t")
                    if len(row) == 6:
                        cp.write_row(row)
        conn.execute("ANALYZE _a")
        conn.execute("ANALYZE _m")
        t1 = time.time()
        conn.execute(RESOLVE)
        if os.environ.get("GDELT_DEBUG"):
            _log(f"stage {t1 - t0:.1f}s resolve {time.time() - t1:.1f}s")
        r = conn.execute("""INSERT INTO gdelt.articles (aid, seen, domain, url, title, lang, tone, themes)
            SELECT DISTINCT ON (a.aid) a.aid, to_timestamp(a.seen, 'YYYYMMDDHH24MISS')::timestamp, a.domain, a.url,
                   nullif(a.title, ''), a.lang, nullif(a.tone, '')::real, nullif(a.themes, '')
              FROM _a a WHERE a.aid IN (SELECT aid FROM _l) ON CONFLICT DO NOTHING""")
        n_art = r.rowcount
        r = conn.execute("""INSERT INTO gdelt.links (ekind, ekey, seen, aid, how, off, n)
            SELECT DISTINCT ON (l.ekind, l.ekey, a.seen, l.aid) l.ekind, l.ekey, to_timestamp(a.seen, 'YYYYMMDDHH24MISS')::timestamp,
                   l.aid, l.how, l.off, l.n
              FROM _l l JOIN _a a ON a.aid = l.aid ON CONFLICT DO NOTHING""")
        n_link = r.rowcount
        conn.execute("""INSERT INTO gdelt.entity_month (ekind, ekey, month, n)
            SELECT ekind, ekey, date_trunc('month', %s::date)::date, count(DISTINCT aid) FROM _l GROUP BY 1, 2
            ON CONFLICT (ekind, ekey, month) DO UPDATE SET n = gdelt.entity_month.n + EXCLUDED.n""", (day,))
        side = dict(conn.execute("SELECT side, count(*) FROM _l GROUP BY 1").fetchall())
        conn.execute("""INSERT INTO gdelt.loaded_days (day, records, kept, articles, links, org_links, person_links, seconds, host)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                     (day, meta["records"], meta["articles"], n_art, n_link, side.get("o", 0), side.get("p", 0),
                      round(time.time() - t0, 1), os.uname().nodename))
    return dict(day=ymd, records=meta["records"], kept=meta["articles"], articles=n_art, links=n_link,
                org=side.get("o", 0), person=side.get("p", 0), seconds=round(time.time() - t0, 1))


def load(d0=None, d1=None, max_days=None, wait=True) -> int:
    conn = db.connect()
    ensure_schema(conn)
    total = 0
    done_days = {r[0] for r in conn.execute("SELECT day FROM gdelt.loaded_days").fetchall()}
    conn.commit()
    for day in parsed_days():
        if day in done_days or (d0 and day < d0) or (d1 and day > d1):
            continue
        if wait:
            offpeak.wait("gdelt load", status=_log)
        conn.commit()
        r = load_day(conn, day)
        conn.commit()
        if not r:
            continue
        total += 1
        _log(f"loaded {r['day']}: {r['records']} records scanned, {r['articles']} articles stored, {r['links']} links "
             f"({r['org']} organization, {r['person']} person), {r['seconds']}s")
        if max_days and total >= max_days:
            break
    return total


# --- events -------------------------------------------------------------------------------------------------------------

def event_days(order: str = "desc") -> list[dt.date]:
    out = []
    for p in PARSED.glob("*.edone"):
        try:
            out.append(dt.datetime.strptime(p.stem, "%Y%m%d").date())
        except ValueError:
            pass
    return sorted(out, reverse=(order == "desc"))


def load_event_day(conn, day: dt.date) -> dict:
    ymd = f"{day:%Y%m%d}"
    meta = json.loads((PARSED / f"{ymd}.edone").read_text())
    t0 = time.time()
    with conn.transaction():
        if conn.execute("SELECT 1 FROM gdelt.event_days WHERE day = %s", (day,)).fetchone():
            return {}
        conn.execute("SET LOCAL statement_timeout = 0")
        conn.execute("""CREATE TEMP TABLE _e (eid bigint, sqldate text, c1 text, c2 text, a1 text, a2 text, code text,
            goldstein text, mentions text, articles text, tone text, place text, country text, url text) ON COMMIT DROP""")
        with conn.cursor() as cur:
            with cur.copy("COPY _e FROM STDIN") as cp, gzip.open(PARSED / f"{ymd}.e.tsv.gz", "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    row = line.rstrip("\n").replace("\x00", "").split("\t")
                    if len(row) == 14:
                        cp.write_row(row)
        conn.execute("ANALYZE _e")
        conn.execute("""CREATE TEMP TABLE _el ON COMMIT DROP AS
            SELECT DISTINCT om.ekind, om.ekey, e.eid FROM _e e JOIN gdelt.org_map om ON om.core IN (e.c1, e.c2) WHERE e.c1 <> '' OR e.c2 <> ''""")
        n_ev = conn.execute("""INSERT INTO gdelt.events (eid, day, actor1, actor2, code, goldstein, mentions, articles, tone, place, country, url)
            SELECT e.eid, to_date(e.sqldate, 'YYYYMMDD'), nullif(e.a1, ''), nullif(e.a2, ''), e.code, nullif(e.goldstein, '')::real,
                   nullif(e.mentions, '')::int, nullif(e.articles, '')::int, nullif(e.tone, '')::real, nullif(e.place, ''), nullif(e.country, ''), e.url
              FROM _e e WHERE e.eid IN (SELECT eid FROM _el) AND e.sqldate ~ '^[0-9]{8}$' ON CONFLICT DO NOTHING""").rowcount
        n_link = conn.execute("""INSERT INTO gdelt.event_links (ekind, ekey, day, eid)
            SELECT l.ekind, l.ekey, ev.day, l.eid FROM _el l JOIN gdelt.events ev ON ev.eid = l.eid ON CONFLICT DO NOTHING""").rowcount
        conn.execute("""INSERT INTO gdelt.event_days (day, scanned, kept, events, links, seconds, host) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                     (day, meta["events"], meta["kept"], n_ev, n_link, round(time.time() - t0, 1), os.uname().nodename))
    return dict(day=ymd, scanned=meta["events"], events=n_ev, links=n_link, seconds=round(time.time() - t0, 1))


def load_events(d0=None, d1=None, max_days=None, wait=True) -> int:
    conn = db.connect()
    ensure_schema(conn)
    done = {r[0] for r in conn.execute("SELECT day FROM gdelt.event_days").fetchall()}
    conn.commit()
    total = 0
    for day in event_days():
        if day in done or (d0 and day < d0) or (d1 and day > d1):
            continue
        if wait:
            offpeak.wait("gdelt events load", status=_log)
        conn.commit()
        r = load_event_day(conn, day)
        conn.commit()
        if not r:
            continue
        total += 1
        _log(f"events loaded {r['day']}: {r['scanned']} events scanned, {r['events']} stored, {r['links']} links, {r['seconds']}s")
        if max_days and total >= max_days:
            break
    return total


# --- summary ------------------------------------------------------------------------------------------------------

def summarize() -> dict:
    conn = db.connect()
    ensure_schema(conn)
    conn.execute("SET statement_timeout = 0")
    mx = conn.execute("SELECT max(day) FROM gdelt.loaded_days").fetchone()[0]
    conn.commit()
    if not mx:
        return {}
    # "this month" is the latest month with ten or more days loaded
    month = dt.date(mx.year, mx.month, 1)
    if mx.day < 10:
        month = (month - dt.timedelta(days=1)).replace(day=1)
    conn.execute("DROP TABLE IF EXISTS gdelt.entity_news_new")
    conn.execute("CREATE TABLE gdelt.entity_news_new (LIKE gdelt.entity_news INCLUDING DEFAULTS)")
    conn.execute("""
        INSERT INTO gdelt.entity_news_new (ekind, ekey, n, first_seen, last_seen, n_month)
        SELECT ekind, ekey, sum(n), min(month), max(month), coalesce(sum(n) FILTER (WHERE month = %s), 0)
          FROM gdelt.entity_month GROUP BY 1, 2""", (month,))
    conn.execute("""UPDATE gdelt.entity_news_new e SET name = o.name FROM organizations o WHERE e.ekind = 'org' AND o.ein = e.ekey""")
    conn.execute("""UPDATE gdelt.entity_news_new e SET name = m.ename FROM (SELECT DISTINCT ON (ekind, ekey) ekind, ekey, ename
        FROM gdelt.org_map) m WHERE m.ekind = e.ekind AND m.ekey = e.ekey AND e.name IS NULL""")
    conn.execute("""UPDATE gdelt.entity_news_new e SET name = pc.display_name FROM person_clusters pc
        WHERE e.ekind = 'person' AND pc.id::text = e.ekey""")
    conn.execute("ALTER TABLE gdelt.entity_news_new ADD PRIMARY KEY (ekind, ekey)")
    conn.execute("CREATE INDEX entity_news_new_month ON gdelt.entity_news_new (ekind, n_month DESC) WHERE n_month > 0")
    conn.execute("CREATE INDEX entity_news_new_all ON gdelt.entity_news_new (n_month DESC) WHERE n_month > 0")
    conn.execute("DROP TABLE IF EXISTS gdelt.entity_news")
    conn.execute("ALTER TABLE gdelt.entity_news_new RENAME TO entity_news")
    conn.execute("ALTER INDEX gdelt.entity_news_new_pkey RENAME TO entity_news_pkey")
    conn.execute("ALTER INDEX gdelt.entity_news_new_month RENAME TO entity_news_month")
    conn.execute("ALTER INDEX gdelt.entity_news_new_all RENAME TO entity_news_all")
    conn.commit()
    conn.execute("DROP TABLE IF EXISTS gdelt.entity_events_new")
    conn.execute("CREATE TABLE gdelt.entity_events_new (LIKE gdelt.entity_events)")
    conn.execute("""INSERT INTO gdelt.entity_events_new SELECT ekind, ekey, count(*), min(day), max(day) FROM gdelt.event_links GROUP BY 1, 2""")
    conn.execute("ALTER TABLE gdelt.entity_events_new ADD PRIMARY KEY (ekind, ekey)")
    conn.execute("DROP TABLE IF EXISTS gdelt.entity_events")
    conn.execute("ALTER TABLE gdelt.entity_events_new RENAME TO entity_events")
    conn.execute("ALTER INDEX gdelt.entity_events_new_pkey RENAME TO entity_events_pkey")
    conn.commit()
    stats = {}
    ev = conn.execute("SELECT count(*), coalesce(sum(scanned), 0), coalesce(sum(events), 0), coalesce(sum(links), 0) FROM gdelt.event_days").fetchone()
    stats.update(event_days=ev[0], events_scanned=ev[1], events=ev[2], event_links=ev[3])
    row = conn.execute("""SELECT count(*), coalesce(sum(records), 0), coalesce(sum(articles), 0), coalesce(sum(links), 0),
        min(day), max(day) FROM gdelt.loaded_days""").fetchone()
    stats.update(days=row[0], records_scanned=row[1], articles=row[2], links=row[3], first_day=str(row[4]), last_day=str(row[5]))
    stats["entities"] = conn.execute("SELECT count(*) FROM gdelt.entity_news").fetchone()[0]
    stats["orgs_in_news"] = conn.execute("SELECT count(*) FROM gdelt.entity_news WHERE ekind <> 'person'").fetchone()[0]
    stats["people_in_news"] = conn.execute("SELECT count(*) FROM gdelt.entity_news WHERE ekind = 'person'").fetchone()[0]
    stats["month"] = f"{month:%B %Y}"
    stats["size"] = conn.execute("""SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) FROM pg_class c
        WHERE c.relnamespace = 'gdelt'::regnamespace AND c.relkind = 'r'""").fetchone()[0]
    conn.commit()
    with conn.transaction():
        for k, v in stats.items():
            conn.execute("""INSERT INTO gdelt.stats (k, v, updated) VALUES (%s, %s, now())
                ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, updated = now()""", (k, str(v)))
    conn.commit()
    _log(f"summary: {stats}")
    return stats


def sample(n: int = 50, how: str = "") -> None:
    conn = db.connect()
    q = """SELECT l.ekind, l.ekey, coalesce(e.name, ''), a.title, a.url, l.how FROM gdelt.links l
           JOIN gdelt.articles a USING (aid) LEFT JOIN gdelt.entity_news e ON e.ekind = l.ekind AND e.ekey = l.ekey
           TABLESAMPLE_PLACEHOLDER WHERE true """
    if how == "person":
        q += " AND l.ekind = 'person'"
    elif how == "organization":
        q += " AND l.ekind <> 'person'"
    q = q.replace("TABLESAMPLE_PLACEHOLDER", "")
    q = q.replace("FROM gdelt.links l", "FROM gdelt.links l TABLESAMPLE SYSTEM (0.05)")
    for r in conn.execute(q + " ORDER BY random() LIMIT %s", (n,)).fetchall():
        print(" | ".join(str(x) for x in r))


def daily() -> None:
    """Nightly: parse the days since the last parsed day, load them, summarize."""
    import subprocess
    last = max(parsed_days("asc") or [dt.date(2015, 2, 17)])
    d0 = last + dt.timedelta(days=1)
    d1 = dt.date.today() - dt.timedelta(days=1)
    if d0 <= d1:
        subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("gdelt_parse.py")), "--from", f"{d0:%Y%m%d}",
                        "--to", f"{d1:%Y%m%d}", "--procs", "2", "--out", str(PARSED), "--dict", str(DICT)], check=False)
    last_e = max(event_days("asc") or [dt.date(2015, 2, 17)])
    e0 = last_e + dt.timedelta(days=1)
    if e0 <= d1:
        subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("gdelt_events.py")), "--from", f"{e0:%Y%m%d}",
                        "--to", f"{d1:%Y%m%d}", "--procs", "2", "--out", str(PARSED), "--dict", str(DICT)], check=False)
    load(wait=True)
    load_events(wait=True)
    summarize()


def status() -> None:
    conn = db.connect()
    for r in conn.execute("SELECT k, v, updated FROM gdelt.stats ORDER BY k").fetchall():
        print(*r)
    print("parsed days on disk:", len(parsed_days()), " loaded:", conn.execute("SELECT count(*) FROM gdelt.loaded_days").fetchone()[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="loader.gdelt")
    ap.add_argument("cmd", choices=["dict", "maps", "famous", "load", "load-events", "summarize", "daily", "status", "sample", "schema"])
    ap.add_argument("--from", dest="d0")
    ap.add_argument("--to", dest="d1")
    ap.add_argument("--max-days", type=int)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--how", default="")
    a = ap.parse_args(argv)
    p = lambda s: dt.datetime.strptime(s, "%Y%m%d").date() if s else None  # noqa: E731
    if a.cmd == "dict":
        build_dict()
    elif a.cmd == "schema":
        c = db.connect(); ensure_schema(c)
    elif a.cmd == "maps":
        build_maps()
    elif a.cmd == "famous":
        build_famous()
    elif a.cmd == "load":
        load(p(a.d0), p(a.d1), a.max_days)
    elif a.cmd == "load-events":
        load_events(p(a.d0), p(a.d1), a.max_days)
    elif a.cmd == "summarize":
        summarize()
    elif a.cmd == "daily":
        daily()
    elif a.cmd == "status":
        status()
    elif a.cmd == "sample":
        sample(a.n, a.how)
    return 0


if __name__ == "__main__":
    sys.exit(main())
