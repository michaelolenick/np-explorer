"""UK charities cross-referenced to the rest of FURP, and the UK to the US (owner, 2026-11-14).

python -m loader.uk_xref match      compute uk.us_match, uk.us_grant, uk.person_match, uk.trustee_person (schema uk only: invisible to prod)
python -m loader.uk_xref publish    copy the matches into xlinks (linker 'uk:<method>') and xref_counts / xref_state; run it after prod has the code
python -m loader.uk_xref sample METHOD [--n 50]    a random sample of one method's matches, to judge precision
python -m loader.uk_xref status

Methods (each match says how it was made; `confidence` is high or medium):
  domain             the charity's website and a US nonprofit's website have the same domain (not a social/hosting domain, at most
                     three charities and three nonprofits on it)                                                    high
  american_friends   a US nonprofit called "American Friends of X" (or "Friends of X USA") and a charity called X       high
  name               the same name core (loader.recalls.core: no Inc/Ltd/Limited/The) of two or more words with a distinctive word,
                     held by at most two registered charities and at most two records of the US kind                   medium
  affix              the same name once USA/US/America/International/Global (US) or UK/United Kingdom/Britain/International (UK)
                     is taken off, with a distinctive base                                                              medium
  fara_principal     a charity's name is a foreign principal of a FARA registrant, country United Kingdom/Great Britain/England/Scotland
                                                                                                                       medium
  grant              a US foundation's Form 990 grant to a recipient the filing places in the UK (state UK, GB, England, ...) whose name
                     equals the charity's (relation 'grantor': not the same organization, a funding link)
  shared_trustee     a UK trustee whose name equals a person on the matched US nonprofit's 990 (relation 'trustee'); it also lifts the
                     organization match to high confidence
Registered charities only (removed ones are old names and mergers). Nothing is deleted from the shared tables here.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from loader import db
from loader.recalls import core
from loader import uk_charities as uk

KINDS = ("org", "fed", "lda_client", "college")
UK_GRANT_STATES = ("UK", "GB", "ENGLAND", "WALES", "GREAT BRITAIN", "GREAT BRITAN", "UNITED KINGDOM", "ENG", "SCOTLAND", "U.K.",
                   "NORTHERN IRELAND", "ENGLAND, UK", "UNITED KINGDO", "G.B.", "U K", "UNITED KINGD", "GBR", "ENGLAND UK", "BRITAIN")
DOMAIN_BLOCK = ("facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com", "youtube.com", "google.com", "sites.google.com",
                "wordpress.com", "blogspot.com", "wixsite.com", "weebly.com", "squarespace.com", "godaddysites.com", "yahoo.com",
                "gmail.com", "hotmail.com", "aol.com", "outlook.com", "gov.uk", "nhs.uk", "org.uk", "co.uk", "com", "org", "edu",
                "network", "n.a", "na.com", "none.com", "tbd.com", "eventbrite.com", "justgiving.com", "mydonate.bt.com", "paypal.com")
SUFFIX_US = "usa|us|u s|america|americas|united states|north america"
SUFFIX_UK = "uk|u k|united kingdom|britain|great britain|gb|england"

DDL = """
CREATE TABLE IF NOT EXISTS uk.us_match (
    uk_reg bigint NOT NULL, us_kind text NOT NULL, us_key text NOT NULL, us_name text, us_state text,
    method text NOT NULL, relation text NOT NULL DEFAULT 'same', confidence text NOT NULL, evidence text,
    PRIMARY KEY (uk_reg, us_kind, us_key, method));
CREATE INDEX IF NOT EXISTS uk_us_match_us ON uk.us_match (us_kind, us_key);
CREATE TABLE IF NOT EXISTS uk.us_grant (
    uk_reg bigint NOT NULL, grantor_ein text NOT NULL, grants integer, total numeric, first_year integer, last_year integer,
    recipient_name text, PRIMARY KEY (uk_reg, grantor_ein));
CREATE INDEX IF NOT EXISTS uk_us_grant_ein ON uk.us_grant (grantor_ein);
CREATE TABLE IF NOT EXISTS uk.person_match (
    trustee_id bigint NOT NULL, cluster_id bigint NOT NULL, uk_reg bigint, ein text, name text, uk_name text,
    PRIMARY KEY (trustee_id, cluster_id));
CREATE INDEX IF NOT EXISTS uk_person_match_cluster ON uk.person_match (cluster_id);
"""


def _log(msg: str) -> None:
    uk._log("xref: " + msg)


def build_keys(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS uk_keys")
    conn.execute("DROP TABLE IF EXISTS uk_words")
    conn.execute("""CREATE TEMP TABLE uk_words AS
                    SELECT w, count(*) n FROM (SELECT unnest(string_to_array(name_core, ' ')) w FROM uk.charity_main
                                               WHERE status = 'Registered') q GROUP BY w""")
    conn.execute("CREATE INDEX ON uk_words (w)")
    conn.execute("""CREATE TEMP TABLE uk_keys AS
                    SELECT c.reg_number, c.name_core AS core, c.name, c.income, c.web_domain,
                           array_length(string_to_array(c.name_core, ' '), 1) AS nw,
                           count(*) OVER (PARTITION BY c.name_core) AS cnt
                    FROM uk.charity_main c WHERE c.status = 'Registered' AND c.name_core IS NOT NULL AND length(c.name_core) >= 4""")
    conn.execute("CREATE INDEX ON uk_keys (core)")
    conn.execute("ANALYZE uk_keys")
    conn.execute("ANALYZE uk_words")
    # a US signal on the UK side: the charity works in the United States or its own description says USA / America
    conn.execute("DROP TABLE IF EXISTS uk_sig")
    conn.execute(r"""CREATE TEMP TABLE uk_sig AS
                     SELECT DISTINCT reg_number FROM uk.charity WHERE linked_number = 0 AND status = 'Registered'
                            AND activities ~* '\m(usa|united states|america|american|u\.s\.a?)\M'
                     UNION SELECT reg_number FROM uk.area WHERE area IN ('United States', 'United States Of America')""")
    conn.execute("CREATE INDEX ON uk_sig (reg_number)")
    conn.execute("ANALYZE uk_sig")


def distinctive_sql(col: str) -> str:
    """a word of at least 4 letters that fewer than 150 registered charities use (so "church", "trust", "community" don't count)"""
    return f"""EXISTS (SELECT 1 FROM unnest(string_to_array({col}, ' ')) w LEFT JOIN uk_words f ON f.w = w.w
                    WHERE length(w.w) >= 4 AND coalesce(f.n, 0) <= 150)"""


def ins(conn, method: str, confidence: str | None, select: str, relation: str = "same") -> int:
    """confidence None: the select supplies a `confidence` column (the name rules: medium with a US signal, else low)."""
    col = "%s" if confidence else "confidence"
    args = (method, relation, confidence) if confidence else (method, relation)
    return conn.execute(f"""INSERT INTO uk.us_match (uk_reg, us_kind, us_key, us_name, us_state, method, relation, confidence, evidence)
                            SELECT uk_reg, us_kind, us_key, us_name, us_state, %s, %s, {col}, evidence FROM ({select}) q
                            ON CONFLICT DO NOTHING""", args).rowcount


def match() -> None:
    t0 = time.time()
    with db.connect() as conn:
        uk.ensure_schema(conn)
        conn.execute(DDL)
        conn.commit()
        conn.execute("SET work_mem = '256MB'")
        build_keys(conn)
        for t in ("us_match", "us_grant", "person_match"):
            conn.execute(f"TRUNCATE uk.{t}")
        counts = {}
        # 1. website domain
        conn.execute("DROP TABLE IF EXISTS us_dom")
        conn.execute(f"""CREATE TEMP TABLE us_dom AS
                         SELECT ein, name, state, uk.web_domain(website) AS dom FROM organizations WHERE website IS NOT NULL AND website ~ '\\.'""")
        conn.execute("DELETE FROM us_dom WHERE dom IS NULL OR dom = ANY(%s) OR length(dom) < 5", (list(DOMAIN_BLOCK),))
        conn.execute("CREATE INDEX ON us_dom (dom)")
        conn.execute("DROP TABLE IF EXISTS uk_dom")
        conn.execute("""CREATE TEMP TABLE uk_dom AS SELECT reg_number, name, web_domain AS dom FROM uk.charity_main
                        WHERE status = 'Registered' AND web_domain IS NOT NULL""")
        conn.execute("DELETE FROM uk_dom WHERE dom = ANY(%s) OR length(dom) < 5", (list(DOMAIN_BLOCK),))
        conn.execute("CREATE INDEX ON uk_dom (dom)")
        counts["domain"] = ins(conn, "domain", "high", """
            SELECT u.reg_number AS uk_reg, 'org' AS us_kind, d.ein AS us_key, d.name AS us_name, d.state AS us_state,
                   'both use the website ' || u.dom AS evidence
            FROM uk_dom u JOIN us_dom d ON d.dom = u.dom
            WHERE (SELECT count(*) FROM uk_dom x WHERE x.dom = u.dom) <= 3 AND (SELECT count(*) FROM us_dom y WHERE y.dom = u.dom) <= 3""")
        conn.commit()
        # 2. exact name
        kinds = list(KINDS)
        conn.execute("DROP TABLE IF EXISTS us_keys")
        conn.execute("""CREATE TEMP TABLE us_keys AS
                        SELECT kind, key, name, state, core, count(*) OVER (PARTITION BY kind, core) AS cnt
                        FROM xref_names WHERE kind = ANY(%s) AND core IN (SELECT core FROM uk_keys)""", (kinds,))
        conn.execute("CREATE INDEX ON us_keys (core)")
        counts["name"] = ins(conn, "name", None, f"""
            SELECT u.reg_number AS uk_reg, s.kind AS us_kind, s.key AS us_key, s.name AS us_name, s.state AS us_state,
                   'the same name "' || u.core || '"' || CASE WHEN g.reg_number IS NULL THEN ' and nothing else (may be a different organization)'
                        ELSE '; the UK charity works in or mentions the US' END AS evidence,
                   CASE WHEN g.reg_number IS NULL THEN 'low' ELSE 'medium' END AS confidence
            FROM uk_keys u JOIN us_keys s ON s.core = u.core LEFT JOIN uk_sig g ON g.reg_number = u.reg_number
            WHERE u.cnt <= 2 AND s.cnt <= 2 AND u.nw >= 2 AND {distinctive_sql('u.core')}""")
        conn.commit()
        # 3. American Friends of X
        conn.execute("DROP TABLE IF EXISTS us_af")
        conn.execute("""CREATE TEMP TABLE us_af AS
                        SELECT key, name, state, trim(regexp_replace(regexp_replace(core,
                               '^(american|us|usa|u s|united states) friends (of|for) (the )?', ''),
                               ' (usa|us|u s|america|inc|incorporated|foundation|fund)$', '')) AS base
                        FROM xref_names WHERE kind = 'org' AND core ~ '^(american|us|usa|u s|united states) friends (of|for) '
                        UNION ALL
                        SELECT key, name, state, trim(regexp_replace(regexp_replace(core, '^friends (of|for) (the )?', ''),
                               ' (usa|us|u s|america|american)$', ''))
                        FROM xref_names WHERE kind = 'org' AND core ~ '^friends (of|for) .* (usa|us|u s|america)$'""")
        conn.execute("CREATE INDEX ON us_af (base)")
        counts["american_friends"] = ins(conn, "american_friends", "high", """
            SELECT u.reg_number AS uk_reg, 'org' AS us_kind, a.key AS us_key, a.name AS us_name, a.state AS us_state,
                   'US "' || a.name || '" is the American friends of "' || u.name || '"' AS evidence
            FROM uk_keys u JOIN us_af a ON a.base = u.core WHERE u.cnt <= 2 AND length(a.base) >= 5
              AND (SELECT count(*) FROM us_af b WHERE b.base = u.core) <= 3""")
        conn.commit()
        # 4. suffix pairs: "X USA" / "X America" / "X International" against "X", "X UK" against "X"
        conn.execute("DROP TABLE IF EXISTS us_base")
        conn.execute(f"""CREATE TEMP TABLE us_base AS
                         SELECT key, name, state, core, regexp_replace(core, ' ({SUFFIX_US})$', '') AS base
                         FROM xref_names WHERE kind = 'org' AND core ~ ' ({SUFFIX_US})$'
                           AND regexp_replace(core, ' ({SUFFIX_US})$', '') IN (SELECT core FROM uk_keys
                                UNION SELECT regexp_replace(core, ' ({SUFFIX_UK})$', '') FROM uk_keys)""")
        conn.execute("CREATE INDEX ON us_base (base)")
        counts["affix"] = ins(conn, "affix", "medium", f"""
            SELECT u.reg_number AS uk_reg, 'org' AS us_kind, b.key AS us_key, b.name AS us_name, b.state AS us_state,
                   'the US name "' || b.core || '" is the UK name "' || u.core || '" plus a US word' AS evidence
            FROM uk_keys u JOIN us_base b ON b.base = u.core
            WHERE u.cnt <= 2 AND (SELECT count(*) FROM us_base z WHERE z.base = b.base) <= 3 AND {distinctive_sql('b.base')}
              AND NOT EXISTS (SELECT 1 FROM xref_names n WHERE n.kind = 'org' AND n.core = b.base AND n.key <> b.key)""")
        counts["affix"] += ins(conn, "affix", None, f"""
            SELECT u.reg_number AS uk_reg, 'org' AS us_kind, n.key AS us_key, n.name AS us_name, n.state AS us_state,
                   'the UK name "' || u.core || '" is the US name "' || n.core || '" plus a UK word' AS evidence,
                   CASE WHEN g.reg_number IS NULL THEN 'low' ELSE 'medium' END AS confidence
            FROM uk_keys u LEFT JOIN uk_sig g ON g.reg_number = u.reg_number JOIN xref_names n ON n.kind = 'org' AND n.core = regexp_replace(u.core, ' ({SUFFIX_UK})$', '')
            WHERE u.core ~ ' ({SUFFIX_UK})$' AND u.cnt <= 2 AND {distinctive_sql('n.core')} AND length(n.core) >= 5
              AND (SELECT count(*) FROM xref_names n2 WHERE n2.kind = 'org' AND n2.core = n.core) <= 2""")
        conn.commit()
        # 5. FARA foreign principals in the UK
        conn.execute("""CREATE TEMP TABLE IF NOT EXISTS fara_uk AS SELECT 1 WHERE false""")
        rows = conn.execute("""SELECT id, principal, country FROM fara_principals WHERE country IN ('ENGLAND', 'GREAT BRITAIN', 'SCOTLAND', 'UNITED KINGDOM')
                               AND principal IS NOT NULL""").fetchall() if conn.execute("SELECT to_regclass('fara_principals')").fetchone()[0] else []
        by_core = {}
        for r in conn.execute("SELECT reg_number, core, name, nw, cnt FROM uk_keys WHERE cnt <= 2 AND nw >= 2").fetchall():
            by_core.setdefault(r[1], []).append(r)
        n5 = 0
        for pid, principal, country in rows:
            for r in by_core.get(core(principal), []):
                ok = conn.execute(f"SELECT {distinctive_sql('%s')}", (r[1],)).fetchone()[0]
                if ok:
                    n5 += conn.execute("""INSERT INTO uk.us_match (uk_reg, us_kind, us_key, us_name, us_state, method, relation, confidence, evidence)
                                          VALUES (%s, 'fara_principal', %s, %s, NULL, 'fara_principal', 'same', 'medium', %s) ON CONFLICT DO NOTHING""",
                                       (r[0], str(pid), principal, f"FARA foreign principal in {country.title()} with the same name")).rowcount
        counts["fara_principal"] = n5
        conn.commit()
        # 6. grants from US foundations to recipients the filing places in the UK
        conn.execute("DROP TABLE IF EXISTS uk_grants")
        conn.execute("""CREATE TEMP TABLE uk_grants AS
                        SELECT ein, tax_year, recipient_name, recipient_name_norm, coalesce(cash_amount, 0) + coalesce(noncash_amount, 0) AS amt
                        FROM grants WHERE upper(state) = ANY(%s) AND recipient_name IS NOT NULL AND NOT coalesce(recipient_is_person, false)""",
                     (list(UK_GRANT_STATES),))
        agg = {}
        for ein, yr, nm, amt in conn.execute("SELECT ein, tax_year, recipient_name, amt FROM uk_grants").fetchall():
            c = core(nm)
            if c not in by_core:
                continue
            a = agg.setdefault((c, ein), [0, 0, yr, yr, nm])
            a[0] += 1
            a[1] += float(amt or 0)
            a[2], a[3] = min(a[2] or yr, yr), max(a[3] or yr, yr)
        n6 = 0
        for (c, ein), (n, tot, y0, y1, nm) in agg.items():
            for r in by_core[c]:
                if r[4] > 1 or not conn.execute(f"SELECT {distinctive_sql('%s')}", (c,)).fetchone()[0]:
                    continue
                n6 += conn.execute("""INSERT INTO uk.us_grant (uk_reg, grantor_ein, grants, total, first_year, last_year, recipient_name)
                                      VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", (r[0], ein, n, tot, y0, y1, nm)).rowcount
        counts["grant"] = n6
        conn.commit()
        # 7. shared trustees: a UK trustee's name on the matched US nonprofit's 990
        conn.execute("DROP TABLE IF EXISTS st")
        conn.execute("""CREATE TEMP TABLE st AS
                        SELECT DISTINCT m.uk_reg, m.us_key AS ein, t.trustee_id, t.name AS uk_name, p.name_raw AS us_name, pcm.cluster_id
                        FROM uk.us_match m
                        JOIN uk.trustee t ON t.reg_number = m.uk_reg AND t.kind = 'P' AND t.linked_number = 0 AND t.name_norm IS NOT NULL
                                         AND array_length(string_to_array(t.name_norm, ' '), 1) >= 2
                        JOIN people p ON p.ein = m.us_key AND p.name_norm = t.name_norm
                        LEFT JOIN person_cluster_members pcm ON pcm.person_id = p.id
                        WHERE m.us_kind = 'org' AND m.relation = 'same'""")
        conn.execute("""INSERT INTO uk.person_match (trustee_id, cluster_id, uk_reg, ein, name, uk_name)
                        SELECT DISTINCT ON (trustee_id, cluster_id) trustee_id, cluster_id, uk_reg, ein, us_name, uk_name FROM st
                        WHERE cluster_id IS NOT NULL ON CONFLICT DO NOTHING""")
        counts["shared_trustee"] = conn.execute("SELECT count(*) FROM uk.person_match").fetchone()[0]
        conn.execute("""UPDATE uk.us_match m SET confidence = 'high',
                               evidence = m.evidence || '; and ' || s.n || ' name' || CASE WHEN s.n = 1 THEN '' ELSE 's' END
                                          || ' in common between the UK trustees and the US filing'
                        FROM (SELECT uk_reg, ein, count(DISTINCT trustee_id) n FROM st GROUP BY 1, 2) s
                        WHERE m.uk_reg = s.uk_reg AND m.us_kind = 'org' AND m.us_key = s.ein AND m.relation = 'same'""")
        conn.execute("""INSERT INTO uk.us_match (uk_reg, us_kind, us_key, us_name, us_state, method, relation, confidence, evidence)
                        SELECT DISTINCT ON (s.uk_reg, s.ein) s.uk_reg, 'org', s.ein, o.name, o.state, 'shared_trustee', 'same', 'high',
                               count(*) OVER (PARTITION BY s.uk_reg, s.ein) || ' trustee name(s) on both the UK register and the US filing'
                        FROM st s JOIN organizations o ON o.ein = s.ein ON CONFLICT DO NOTHING""")
        conn.commit()
        conn.execute("ANALYZE uk.us_match")
        conn.execute("ANALYZE uk.person_match")
        conn.commit()
        tot = {r[0]: r[1] for r in conn.execute("SELECT method, count(*) FROM uk.us_match GROUP BY 1").fetchall()}
    _log(f"match: {counts} -> uk.us_match by method {tot}; {time.time() - t0:.0f}s")


# --- publish -----------------------------------------------------------------------------------------------------

def publish() -> None:
    """The matches into xlinks (both directions, linker 'uk:<method>') and the engine's counters. Run once the pages exist on prod."""
    from loader import xref
    t0 = time.time()
    with db.connect() as conn:
        xref.ensure_schema(conn)
        if xref._rebuilding(conn):
            _log("publish: xlinks is being rebuilt, try again later")
            return
        conn.execute("DELETE FROM xlinks WHERE linker LIKE 'uk:%'")
        n = 0
        for conf_word, conf in (("EXACT", "high"), ("FUZZY", "medium")):
            # same-entity matches
            n += conn.execute("""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT 'uk_charity', m.uk_reg::text, c.name, NULL, m.us_kind, m.us_key, m.us_name,
                       CASE m.method WHEN 'domain' THEN 'the same website domain' WHEN 'american_friends' THEN 'an "American Friends of" name'
                            WHEN 'name' THEN 'the same name, in the UK and the US' WHEN 'affix' THEN 'the same name apart from a country word'
                            WHEN 'fara_principal' THEN 'a UK foreign principal of the same name'
                            ELSE 'trustees in common' END || ' (' || %s || ')', 'uk:' || m.method
                FROM uk.us_match m JOIN uk.charity_main c ON c.reg_number = m.uk_reg
                WHERE m.relation = 'same' AND m.confidence = %s AND m.method <> 'shared_trustee' ON CONFLICT DO NOTHING""", (conf_word, conf)).rowcount
            n += conn.execute("""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT m.us_kind, m.us_key, m.us_name, m.us_state, 'uk_charity', m.uk_reg::text, c.name,
                       CASE m.method WHEN 'domain' THEN 'the same website domain' WHEN 'american_friends' THEN 'an "American Friends of" name'
                            WHEN 'name' THEN 'the same name, in the UK and the US' WHEN 'affix' THEN 'the same name apart from a country word'
                            WHEN 'fara_principal' THEN 'a UK foreign principal of the same name'
                            ELSE 'trustees in common' END || ' (' || %s || ')', 'uk:' || m.method
                FROM uk.us_match m JOIN uk.charity_main c ON c.reg_number = m.uk_reg
                WHERE m.relation = 'same' AND m.confidence = %s AND m.method <> 'shared_trustee' ON CONFLICT DO NOTHING""", (conf_word, conf)).rowcount
        # pairs matched only by shared trustees
        for a, b in (("'uk_charity', m.uk_reg::text, c.name, NULL", "'org', m.us_key, m.us_name, m.us_state"),
                     ("'org', m.us_key, m.us_name, m.us_state", "'uk_charity', m.uk_reg::text, c.name, NULL")):
            n += conn.execute(f"""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT {a.split(',')[0]}, {a.split(',')[1]}, {a.split(',')[2]}, {a.split(',')[3]},
                       {b.split(',')[0]}, {b.split(',')[1]}, {b.split(',')[2]}, 'trustees in common (EXACT)', 'uk:shared_trustee'
                FROM uk.us_match m JOIN uk.charity_main c ON c.reg_number = m.uk_reg
                WHERE m.method = 'shared_trustee' ON CONFLICT DO NOTHING""").rowcount
        # US foundation grants to the charity
        for direction in (0, 1):
            if direction == 0:
                sel = """'org', g.grantor_ein, o.name, o.state, 'uk_charity', g.uk_reg::text, c.name"""
            else:
                sel = """'uk_charity', g.uk_reg::text, c.name, NULL, 'org', g.grantor_ein, o.name"""
            n += conn.execute(f"""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT {sel}, 'US grants to this UK charity: ' || g.grants || ' grant' || CASE WHEN g.grants = 1 THEN '' ELSE 's' END
                       || ' totalling $' || to_char(g.total, 'FM999,999,999,999') || ', ' || g.first_year || '-' || g.last_year || ' (FUZZY)', 'uk:grant'
                FROM uk.us_grant g JOIN uk.charity_main c ON c.reg_number = g.uk_reg JOIN organizations o ON o.ein = g.grantor_ein
                ON CONFLICT DO NOTHING""").rowcount
        # UK trustees to US person pages (the engine's key for a trustee is the Commission's trustee id)
        for direction in (0, 1):
            if direction == 0:
                sel = "'uk_trustee', pm.trustee_id::text, pm.uk_name, NULL, 'person', pm.cluster_id::text, p.display_name"
            else:
                sel = "'person', pm.cluster_id::text, p.display_name, NULL, 'uk_trustee', pm.trustee_id::text, pm.uk_name"
            n += conn.execute(f"""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT {sel}, 'the same name as an officer or director of ' || coalesce(o.name, pm.ein) || ' (matched to UK ' || c.name
                       || ') (EXACT)', 'uk:shared_trustee'
                FROM uk.person_match pm JOIN person_clusters p ON p.id = pm.cluster_id JOIN uk.charity_main c ON c.reg_number = pm.uk_reg
                LEFT JOIN organizations o ON o.ein = pm.ein ON CONFLICT DO NOTHING""").rowcount
        conn.commit()
        # engine counters (what /data and /admin show)
        conn.execute("DELETE FROM xref_counts WHERE linker LIKE 'uk:%'")
        conn.execute("""INSERT INTO xref_counts (src_kind, dst_kind, linker, rule, n, sources, built)
                        SELECT src_kind, dst_kind, linker, 'UK charities against the US records: ' || replace(linker, 'uk:', ''), count(*),
                               count(DISTINCT src_key), now() FROM xlinks WHERE linker LIKE 'uk:%' GROUP BY src_kind, dst_kind, linker""")
        for method, rule in (("domain", "the charity's website and a US nonprofit's website have the same domain"),
                             ("american_friends", "a US 'American Friends of X' nonprofit and a UK charity X"),
                             ("name", "the same name core of two or more words, distinctive, at most two holders each side"),
                             ("affix", "the same name apart from a country word (USA, America, International, UK...)"),
                             ("fara_principal", "a UK foreign principal under FARA with a charity's name"),
                             ("grant", "US 990 grants to a recipient placed in the UK with a charity's name"),
                             ("shared_trustee", "a UK trustee's name on the matched US nonprofit's 990")):
            xref.set_state(conn, "uk:" + method, src_kind="uk_charity", dst_kinds="org, person, fara_principal, fed, lda_client, college",
                           rule=rule, cursor="done", added=0, seconds=time.time() - t0, full=True)
        conn.execute("""INSERT INTO uk.meta (key, rows, loaded, checked, note) VALUES ('xlinks', %s, now(), now(), 'published to xlinks')
                        ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""", (n,))
        conn.commit()
    _log(f"publish: {n:,} xlinks rows in {time.time() - t0:.0f}s")


def sample(method: str, n: int = 50) -> None:
    method, _, conf = method.partition(":")        # name:low samples only the low-confidence name matches
    with db.connect() as conn:
        rows = conn.execute("""SELECT m.uk_reg, c.name, c.region, c.income, m.us_kind, m.us_key, m.us_name, m.us_state, m.confidence, m.evidence
                               FROM uk.us_match m JOIN uk.charity_main c ON c.reg_number = m.uk_reg
                               WHERE m.method = %s AND (%s = '' OR m.confidence = %s) ORDER BY random() LIMIT %s""", (method, conf, conf, n)).fetchall()
        for r in rows:
            print(f"{r[0]} | UK: {r[1]} ({r[2]}, income {r[3]}) | US {r[4]} {r[5]}: {r[6]} {r[7] or ''} | {r[8]} | {r[9]}")


def status() -> None:
    with db.connect() as conn:
        if conn.execute("SELECT to_regclass('uk.us_match') IS NULL").fetchone()[0]:
            print("uk xref: not run")
            return
        for m, rel, conf, n in conn.execute("SELECT method, relation, confidence, count(*) FROM uk.us_match GROUP BY 1, 2, 3 ORDER BY 1").fetchall():
            print(f"uk xref: {m} {rel} {conf}: {n:,}")
        print("uk xref: grants:", conn.execute("SELECT count(*) FROM uk.us_grant").fetchone()[0],
              "person matches:", conn.execute("SELECT count(*) FROM uk.person_match").fetchone()[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["match", "publish", "sample", "status"])
    ap.add_argument("method", nargs="?")
    ap.add_argument("--n", type=int, default=50)
    a = ap.parse_args(argv)
    if a.cmd == "match":
        match()
    elif a.cmd == "publish":
        publish()
    elif a.cmd == "sample":
        sample(a.method, a.n)
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
