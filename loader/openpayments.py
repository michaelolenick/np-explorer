"""CMS Open Payments: payments and transfers of value from drug and device makers (applicable manufacturers and
group purchasing organizations) to physicians, non-physician practitioners and teaching hospitals, from the
program-year detail files CMS publishes (https://openpaymentsdata.cms.gov, dataset catalog
https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items; owner, 2026-11-04). Program years 2019 on
(the current publication; 2013-2018 are CMS's separate archive, not loaded).

Files, in /bulk/openpayments/: OP_DTL_GNRL_PGYR{year}.csv (general payments), OP_DTL_RSRCH_PGYR{year}.csv (research
payments), OP_DTL_OWNRSHP_PGYR{year}.csv (ownership and investment interests), and the covered recipient profile
supplement OP_CVRD_RCPNT_PRFL_SPLMTL.csv (not loaded: the detail rows carry the recipient's name and place).

Tables:
  op_payments     one row per published record (record_id): kind g/r/o, program year, recipient, payer, amount,
                  date, number of payments, form and nature of payment, the first product named (name, type,
                  category), and for research the study name and the first principal investigator (pi_key)
  op_recipients   one row per recipient: physician, non-physician practitioner, teaching hospital or (research)
                  non-covered entity: name, NPI, city, state, specialty, totals and years, key p{profile id},
                  h{teaching hospital id} or n{hash of the entity name}
  op_payers       one row per paying company (CMS's manufacturer or GPO id): name, state, country, totals
  op_person_links recipients -> person pages: the same normalized full name with a middle name or initial, held
                  by exactly one person page, in one of that person's states (the recipient's)
  op_org_links    teaching hospitals and payers -> nonprofits (same name core and state, one on each side) and
                  state business registrations (same)
  op_files        what was loaded from which file

Dropped from the detail files: street address, zip, province and postal code; the second to sixth recipient
types and specialties; license states; the submitting entity's name (the paying entity is kept); city, state and
country of travel; physician ownership, third-party, charity, delay-in-publication, dispute, related-product and
covered/non-covered indicators; the third-party entity name; contextual information; NDC and PDI codes; the second
to fifth products; publication date; change type; and on research rows the second to fifth principal investigators,
the expenditure categories, preclinical indicator, ClinicalTrials.gov id, research link and context of research.

Usage: .venv/bin/python -m loader.openpayments [load [YEAR ...]] [build] [links]
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

from app.names import normalize_name
from loader import db

RAW = Path("/bulk/openpayments")
FIRST_YEAR = 2019
KINDS = {"g": "GNRL", "r": "RSRCH", "o": "OWNRSHP"}
csv.field_size_limit(1 << 24)

DDL = """
CREATE TABLE IF NOT EXISTS op_payments (
    record_id bigint NOT NULL, kind char(1) NOT NULL, program_year smallint NOT NULL, recipient_key text NOT NULL,
    pi_key text, payer_id bigint, amount numeric(14,2), value numeric(14,2), date date, n smallint, form text,
    nature text, product text, product_type text, category text, study text);
CREATE TABLE IF NOT EXISTS op_rcpt_raw (
    key text NOT NULL, kind text, profile_id bigint, npi text, first text, middle text, last text, suffix text,
    name text, city text, state text, country text, specialty text, ccn text, year smallint, file text);
CREATE TABLE IF NOT EXISTS op_payer_raw (id bigint NOT NULL, name text, state text, country text, year smallint, file text);
CREATE TABLE IF NOT EXISTS op_files (file text PRIMARY KEY, kind char(1), year smallint, bytes bigint, rows bigint,
                                     loaded timestamptz);
"""
PAY_COLS = ["record_id", "kind", "program_year", "recipient_key", "pi_key", "payer_id", "amount", "value", "date", "n",
            "form", "nature", "product", "product_type", "category", "study"]
RCPT_COLS = ["key", "kind", "profile_id", "npi", "first", "middle", "last", "suffix", "name", "city", "state", "country",
             "specialty", "ccn", "year", "file"]
PAYER_COLS = ["id", "name", "state", "country", "year", "file"]
RECIPIENT_KINDS = {"Covered Recipient Physician": "Physician",
                   "Covered Recipient Non-Physician Practitioner": "Non-physician practitioner",
                   "Covered Recipient Teaching Hospital": "Teaching hospital",
                   "Non-covered Recipient Entity": "Non-covered entity",
                   "Non-covered Recipient Individual": "Non-covered individual"}


def _s(v, n=200):
    v = (v or "").strip()
    return v[:n] or None


def _num(v):
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return round(float(v), 2)
    except ValueError:
        return None


def _int(v):
    v = re.sub(r"\D", "", v or "")
    return int(v) if v else None


def _date(v):
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", (v or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m[3]), int(m[1]), int(m[2]))
    except ValueError:
        return None


class _SideWriter:
    """csv rows for a later COPY ... (FORMAT csv); None becomes an unquoted empty field, which COPY reads as NULL."""

    def __init__(self, f):
        self.w = csv.writer(f, lineterminator="\n")

    def write_row(self, row):
        self.w.writerow(["" if v is None else v for v in row])


class Cols:
    """Column lookups by header name (the files' column order differs a little by year)."""

    def __init__(self, header):
        self.i = {h.strip(): n for n, h in enumerate(header)}

    def get(self, row, name):
        n = self.i.get(name)
        return row[n] if n is not None and n < len(row) else ""


def _recipient(c, row, prefix="Covered_Recipient_", th=True):
    """(key, raw recipient tuple without year/file) for a covered recipient (or research PI with its prefix)."""
    kind_raw = c.get(row, prefix + "Type") if prefix == "Covered_Recipient_" else c.get(row, prefix + "Covered_Recipient_Type")
    kind = RECIPIENT_KINDS.get(kind_raw.strip(), kind_raw.strip() or None)
    hid = _int(c.get(row, "Teaching_Hospital_ID")) if th else None
    if hid:
        name = _s(c.get(row, "Teaching_Hospital_Name"))
        return f"h{hid}", ("Teaching hospital", None, None, None, None, None, None, name, _s(c.get(row, "Recipient_City"), 100),
                           _s(c.get(row, "Recipient_State"), 2), _s(c.get(row, "Recipient_Country"), 60), None,
                           _s(c.get(row, "Teaching_Hospital_CCN"), 20))
    pid = _int(c.get(row, prefix + "Profile_ID"))
    if prefix == "Covered_Recipient_":
        first, mid, last, suf = (c.get(row, "Covered_Recipient_First_Name"), c.get(row, "Covered_Recipient_Middle_Name"),
                                 c.get(row, "Covered_Recipient_Last_Name"), c.get(row, "Covered_Recipient_Name_Suffix"))
        city, st, ctry = c.get(row, "Recipient_City"), c.get(row, "Recipient_State"), c.get(row, "Recipient_Country")
        spec, npi = c.get(row, "Covered_Recipient_Specialty_1"), c.get(row, "Covered_Recipient_NPI")
    else:
        first, mid, last, suf = (c.get(row, prefix + "First_Name"), c.get(row, prefix + "Middle_Name"),
                                 c.get(row, prefix + "Last_Name"), c.get(row, prefix + "Name_Suffix"))
        city, st, ctry = c.get(row, prefix + "City"), c.get(row, prefix + "State"), c.get(row, prefix + "Country")
        spec, npi = c.get(row, prefix + "Specialty_1"), c.get(row, prefix + "NPI")
    if not pid:
        ent = _s(c.get(row, "Noncovered_Recipient_Entity_Name"))
        if ent:
            return "n" + hashlib.md5(ent.upper().encode()).hexdigest()[:16], ("Non-covered entity", None, None, None, None, None,
                                                                               None, ent, _s(city, 100), _s(st, 2), _s(ctry, 60), None, None)
        return None, None
    first, mid, last, suf = _s(first, 60), _s(mid, 60), _s(last, 80), _s(suf, 20)
    name = " ".join(x for x in (first, mid, last, suf) if x) or None
    return f"p{pid}", (kind or "Physician", pid, _s(npi, 20), first, mid, last, suf, name, _s(city, 100), _s(st, 2),
                       _s(ctry, 60), _s(spec, 200), None)


def _payer(c, row):
    pid = _int(c.get(row, "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_ID"))
    if not pid:
        return None, None
    return pid, (_s(c.get(row, "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name")),
                 _s(c.get(row, "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_State"), 2),
                 _s(c.get(row, "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Country"), 60))


def load_file(conn, kind: str, year: int, status=print) -> int:
    name = f"OP_DTL_{KINDS[kind]}_PGYR{year}.csv"
    path = RAW / name
    if not path.exists() or (path.with_name(name + ".part")).exists():
        return 0
    conn.execute("DELETE FROM op_payments WHERE kind = %s AND program_year = %s", (kind, year))
    conn.execute("DELETE FROM op_rcpt_raw WHERE file = %s", (name,))
    conn.execute("DELETE FROM op_payer_raw WHERE file = %s", (name,))
    conn.commit()
    seen_r, seen_p = set(), set()
    n = 0
    # One COPY at a time per connection: recipients and payers go to side files, copied in after the payments.
    side_r, side_p = RAW / (name + ".rcpt.tmp"), RAW / (name + ".payer.tmp")
    with open(path, encoding="utf-8", errors="replace", newline="") as f, conn.cursor() as cur, \
         open(side_r, "w", newline="") as fr, open(side_p, "w", newline="") as fp:
        reader = csv.reader(f)
        c = Cols(next(reader))
        cr, cpy = _SideWriter(fr), _SideWriter(fp)
        with cur.copy(f"COPY op_payments ({', '.join(PAY_COLS)}) FROM STDIN") as cp:
            for row in reader:
                rid = _int(c.get(row, "Record_ID"))
                if not rid:
                    continue
                py = _int(c.get(row, "Program_Year")) or year
                if kind == "o":
                    pid = _int(c.get(row, "Physician_Profile_ID"))
                    if not pid:
                        continue
                    key = f"p{pid}"
                    first, mid, last, suf = (_s(c.get(row, "Physician_First_Name"), 60), _s(c.get(row, "Physician_Middle_Name"), 60),
                                             _s(c.get(row, "Physician_Last_Name"), 80), _s(c.get(row, "Physician_Name_Suffix"), 20))
                    rraw = ("Physician", pid, _s(c.get(row, "Physician_NPI"), 20), first, mid, last, suf,
                            " ".join(x for x in (first, mid, last, suf) if x) or None, _s(c.get(row, "Recipient_City"), 100),
                            _s(c.get(row, "Recipient_State"), 2), _s(c.get(row, "Recipient_Country"), 60),
                            _s(c.get(row, "Physician_Specialty"), 200), None)
                    pi_key = None
                    amount, value = _num(c.get(row, "Total_Amount_Invested_USDollars")), _num(c.get(row, "Value_of_Interest"))
                    date, num = None, None
                    form = _s(c.get(row, "Interest_Held_by_Physician_or_an_Immediate_Family_Member"), 100)
                    nature, product, ptype, cat, study = "Ownership or investment interest", _s(c.get(row, "Terms_of_Interest"), 300), None, None, None
                else:
                    key, rraw = _recipient(c, row)
                    if not key:
                        continue
                    pi_key = None
                    if kind == "r":
                        pi_key, piraw = _recipient(c, row, "Principal_Investigator_1_", th=False)
                        if pi_key and pi_key not in seen_r:
                            seen_r.add(pi_key)
                            cr.write_row((pi_key, *piraw, py, name))
                    amount, value = _num(c.get(row, "Total_Amount_of_Payment_USDollars")), None
                    date = _date(c.get(row, "Date_of_Payment"))
                    num = _int(c.get(row, "Number_of_Payments_Included_in_Total_Amount")) if kind == "g" else None
                    form = _s(c.get(row, "Form_of_Payment_or_Transfer_of_Value"), 100)
                    nature = _s(c.get(row, "Nature_of_Payment_or_Transfer_of_Value"), 100) if kind == "g" else "Research payment"
                    product = _s(c.get(row, "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_1"), 200)
                    ptype = _s(c.get(row, "Indicate_Drug_or_Biological_or_Device_or_Medical_Supply_1"), 40)
                    cat = _s(c.get(row, "Product_Category_or_Therapeutic_Area_1"), 200)
                    study = _s(c.get(row, "Name_of_Study"), 300) if kind == "r" else None
                if key not in seen_r:
                    seen_r.add(key)
                    cr.write_row((key, *rraw, py, name))
                payer_id, praw = _payer(c, row)
                if payer_id and payer_id not in seen_p:
                    seen_p.add(payer_id)
                    cpy.write_row((payer_id, *praw, py, name))
                cp.write_row((rid, kind, py, key, pi_key, payer_id, amount, value, date, num, form, nature, product, ptype, cat, study))
                n += 1
                if n % 2_000_000 == 0:
                    status(f"openpayments: {name}: {n:,} rows")
    with conn.cursor() as cur:
        for side, table, cols in ((side_r, "op_rcpt_raw", RCPT_COLS), (side_p, "op_payer_raw", PAYER_COLS)):
            with open(side, "rb") as sf, cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN (FORMAT csv)") as cp:
                while chunk := sf.read(1 << 20):
                    cp.write(chunk)
            side.unlink()
    conn.execute("""INSERT INTO op_files (file, kind, year, bytes, rows, loaded) VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (file) DO UPDATE SET bytes = excluded.bytes, rows = excluded.rows, loaded = now()""",
                 (name, kind, year, path.stat().st_size, n))
    conn.commit()
    status(f"openpayments: {name}: {n:,} rows loaded")
    return n


def load(years=None, status=print) -> int:
    total = 0
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("SET statement_timeout = 0")
        conn.commit()
        for year in years or range(FIRST_YEAR, dt.date.today().year + 1):
            for kind in KINDS:
                total += load_file(conn, kind, year, status)
    return total


def build(status=print) -> None:
    """Recipients, payers, indexes and totals from the loaded rows."""
    with db.connect() as conn:
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '1GB'")
        conn.execute("SET maintenance_work_mem = '2GB'")
        status("openpayments: indexes")
        for ddl in ["CREATE INDEX IF NOT EXISTS op_payments_rcpt ON op_payments (recipient_key)",
                    "CREATE INDEX IF NOT EXISTS op_payments_payer ON op_payments (payer_id)",
                    "CREATE INDEX IF NOT EXISTS op_payments_pi ON op_payments (pi_key) WHERE pi_key IS NOT NULL",
                    "CREATE INDEX IF NOT EXISTS op_payments_year ON op_payments (program_year, kind)"]:
            conn.execute(ddl)
            conn.commit()
        if not conn.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'op_payments_record'").fetchone():
            dup = conn.execute("SELECT count(*) - count(DISTINCT record_id) FROM op_payments").fetchone()[0]
            if dup:
                status(f"openpayments: {dup:,} duplicate record ids; keeping the latest program year")
                conn.execute("""DELETE FROM op_payments p USING (SELECT record_id, max(program_year) AS y FROM op_payments
                                GROUP BY 1 HAVING count(*) > 1) d WHERE p.record_id = d.record_id AND p.program_year < d.y""")
                conn.execute("""DELETE FROM op_payments p USING (SELECT record_id, min(ctid) AS c FROM op_payments
                                GROUP BY 1 HAVING count(*) > 1) d WHERE p.record_id = d.record_id AND p.ctid <> d.c""")
            conn.execute("CREATE UNIQUE INDEX op_payments_record ON op_payments (record_id)")
            conn.commit()
        status("openpayments: recipients")
        conn.execute("DROP TABLE IF EXISTS op_recipients_new")
        conn.execute("""
            CREATE TABLE op_recipients_new AS
            WITH latest AS (SELECT DISTINCT ON (key) * FROM op_rcpt_raw ORDER BY key, year DESC),
                 pay AS (SELECT recipient_key AS key, count(*) AS payments,
                                sum(amount) FILTER (WHERE kind = 'g') AS general,
                                sum(amount) FILTER (WHERE kind = 'r') AS research,
                                sum(amount) FILTER (WHERE kind = 'o') AS invested,
                                sum(value) FILTER (WHERE kind = 'o') AS interest_value,
                                min(program_year) AS first_year, max(program_year) AS last_year
                         FROM op_payments GROUP BY 1),
                 pi AS (SELECT pi_key AS key, count(*) AS pi_payments, sum(amount) AS pi_research FROM op_payments
                        WHERE pi_key IS NOT NULL GROUP BY 1)
            SELECT l.key, l.kind, l.profile_id, l.npi, l.first, l.middle, l.last, l.suffix, l.name,
                   CASE WHEN l.profile_id IS NOT NULL THEN nullif(np_norm_name(l.first, l.middle, l.last, l.suffix), '') END AS name_norm,
                   l.city, l.state, l.country, l.specialty, l.ccn,
                   coalesce(p.payments, 0) AS payments, coalesce(p.general, 0) AS general, coalesce(p.research, 0) AS research,
                   coalesce(p.invested, 0) AS invested, coalesce(p.interest_value, 0) AS interest_value,
                   coalesce(p.general, 0) + coalesce(p.research, 0) AS total,
                   coalesce(pi.pi_payments, 0) AS pi_payments, coalesce(pi.pi_research, 0) AS pi_research,
                   least(p.first_year, l.year) AS first_year, greatest(p.last_year, l.year) AS last_year
            FROM latest l LEFT JOIN pay p ON p.key = l.key LEFT JOIN pi ON pi.key = l.key""")
        conn.execute("ALTER TABLE op_recipients_new ADD PRIMARY KEY (key)")
        conn.execute("CREATE INDEX ON op_recipients_new (name_norm)")
        conn.execute("CREATE INDEX ON op_recipients_new (total DESC)")
        conn.execute("CREATE INDEX ON op_recipients_new (npi)")
        if db.has_extension(conn, "pg_trgm"):
            conn.execute("CREATE INDEX ON op_recipients_new USING gin (name_norm gin_trgm_ops)")
        db.swap_table(conn, "op_recipients")
        conn.commit()
        status("openpayments: payers")
        conn.execute("DROP TABLE IF EXISTS op_payers_new")
        conn.execute("""
            CREATE TABLE op_payers_new AS
            WITH latest AS (SELECT DISTINCT ON (id) * FROM op_payer_raw ORDER BY id, year DESC),
                 pay AS (SELECT payer_id AS id, count(*) AS payments, sum(amount) FILTER (WHERE kind = 'g') AS general,
                                sum(amount) FILTER (WHERE kind = 'r') AS research, sum(amount) FILTER (WHERE kind = 'o') AS invested,
                                count(DISTINCT recipient_key) AS recipients, min(program_year) AS first_year,
                                max(program_year) AS last_year
                         FROM op_payments GROUP BY 1)
            SELECT l.id, l.name, l.state, l.country, coalesce(p.payments, 0) AS payments, coalesce(p.general, 0) AS general,
                   coalesce(p.research, 0) AS research, coalesce(p.invested, 0) AS invested,
                   coalesce(p.general, 0) + coalesce(p.research, 0) AS total, coalesce(p.recipients, 0) AS recipients,
                   p.first_year, p.last_year
            FROM latest l LEFT JOIN pay p ON p.id = l.id""")
        conn.execute("ALTER TABLE op_payers_new ADD PRIMARY KEY (id)")
        conn.execute("CREATE INDEX ON op_payers_new (total DESC)")
        conn.execute("CREATE INDEX ON op_payers_new (lower(name))")
        db.swap_table(conn, "op_payers")
        conn.execute("ANALYZE op_payments")
        conn.commit()
        # Summaries the pages read instead of scanning op_payments: by year, by payer and year, by payer and nature,
        # each payer's top recipients and products.
        status("openpayments: summaries")
        conn.execute("DROP TABLE IF EXISTS op_payer_years_new")
        conn.execute("""CREATE TABLE op_payer_years_new AS
                        SELECT payer_id, program_year, kind, count(*) AS n, sum(amount) AS total, count(DISTINCT recipient_key) AS recipients
                        FROM op_payments GROUP BY 1, 2, 3""")
        conn.execute("CREATE INDEX ON op_payer_years_new (payer_id)")
        db.swap_table(conn, "op_payer_years")
        conn.execute("DROP TABLE IF EXISTS op_payer_natures_new")
        conn.execute("""CREATE TABLE op_payer_natures_new AS
                        SELECT payer_id, nature, count(*) AS n, sum(amount) AS total FROM op_payments GROUP BY 1, 2""")
        conn.execute("CREATE INDEX ON op_payer_natures_new (payer_id)")
        db.swap_table(conn, "op_payer_natures")
        conn.execute("DROP TABLE IF EXISTS op_payer_top_new")
        conn.execute("""CREATE TABLE op_payer_top_new AS
                        SELECT * FROM (SELECT payer_id, recipient_key, n, total,
                                              row_number() OVER (PARTITION BY payer_id ORDER BY total DESC NULLS LAST) AS rk
                                       FROM (SELECT payer_id, recipient_key, count(*) AS n, sum(amount) AS total FROM op_payments
                                             GROUP BY 1, 2) x) y WHERE rk <= 100""")
        conn.execute("CREATE INDEX ON op_payer_top_new (payer_id, rk)")
        db.swap_table(conn, "op_payer_top")
        conn.execute("DROP TABLE IF EXISTS op_payer_products_new")
        conn.execute("""CREATE TABLE op_payer_products_new AS
                        SELECT * FROM (SELECT payer_id, product, product_type, category, n, total,
                                              row_number() OVER (PARTITION BY payer_id ORDER BY total DESC NULLS LAST) AS rk
                                       FROM (SELECT payer_id, product, product_type, category, count(*) AS n, sum(amount) AS total
                                             FROM op_payments WHERE product IS NOT NULL GROUP BY 1, 2, 3, 4) x) y WHERE rk <= 40""")
        conn.execute("CREATE INDEX ON op_payer_products_new (payer_id, rk)")
        db.swap_table(conn, "op_payer_products")
        conn.commit()
        n = conn.execute("SELECT (SELECT count(*) FROM op_payments), (SELECT count(*) FROM op_recipients), (SELECT count(*) FROM op_payers)").fetchone()
    status(f"openpayments: {n[0]:,} payments, {n[1]:,} recipients, {n[2]:,} payers")


def ensure_norm_function(conn) -> None:
    """np_norm_name(first, middle, last, suffix): the site's normalize_name, as SQL (letters only, lowercased)."""
    conn.execute(r"""
        CREATE OR REPLACE FUNCTION np_norm_name(f text, m text, l text, s text) RETURNS text AS $$
        SELECT trim(regexp_replace(regexp_replace(lower(concat_ws(' ', nullif(trim(f), ''), nullif(trim(m), ''), nullif(trim(l), ''),
               CASE WHEN lower(trim(s)) IN ('jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv') THEN replace(lower(trim(s)), '.', '') END)),
               '[^a-z ]+', ' ', 'g'), '\s+', ' ', 'g'))
        $$ LANGUAGE sql IMMUTABLE""")


def links(status=print) -> dict:
    """Recipients to person pages; teaching hospitals and payers to nonprofits and business registrations."""
    from loader.recalls import core
    with db.connect() as conn:
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '1GB'")
        conn.execute("""CREATE TABLE IF NOT EXISTS op_person_links (recipient_key text PRIMARY KEY, cluster_id bigint NOT NULL,
                        how text NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS op_person_links_cluster ON op_person_links (cluster_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS op_org_links (key text NOT NULL, kind text NOT NULL, target_kind text NOT NULL,
                        target_key text NOT NULL, how text NOT NULL, PRIMARY KEY (key, kind, target_kind, target_key))""")
        conn.execute("CREATE INDEX IF NOT EXISTS op_org_links_target ON op_org_links (target_kind, target_key)")
        conn.execute("TRUNCATE op_person_links, op_org_links")
        # Recipients' normalized names, by the site's normalizer (a middle name or initial is required).
        rows = conn.execute("""SELECT key, first, middle, last, suffix, state FROM op_recipients
                               WHERE profile_id IS NOT NULL AND middle IS NOT NULL AND state IS NOT NULL""").fetchall()
        conn.execute("CREATE TEMP TABLE op_rn (key text, name_norm text, state text) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy("COPY op_rn FROM STDIN") as cp:
            for key, f, m, l, s, st in rows:
                nn = normalize_name(" ".join(x for x in (f, m, l, s) if x))
                if nn and len(nn.split()) >= 3:
                    cp.write_row((key, nn, st))
        conn.execute("CREATE INDEX ON op_rn (name_norm)")
        n_people = conn.execute("""
            INSERT INTO op_person_links (recipient_key, cluster_id, how)
            SELECT r.key, u.id, 'full name with a middle part, and the recipient''s state'
            FROM op_rn r JOIN (SELECT name_norm, min(id) AS id, min(states) AS states FROM person_clusters
                               WHERE NOT coalesce(is_institution, false) GROUP BY name_norm HAVING count(*) = 1) u
                 ON u.name_norm = r.name_norm
            WHERE r.state = ANY(u.states)""").rowcount
        # Organizations: name core and state, one on each side.
        orgs = conn.execute("SELECT ein, name, state FROM organizations WHERE name IS NOT NULL AND state IS NOT NULL").fetchall()
        conn.execute("CREATE TEMP TABLE op_oc (ein text, core text, state text) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy("COPY op_oc FROM STDIN") as cp:
            for ein, name, st in orgs:
                c = core(name)
                if len(c) >= 4:
                    cp.write_row((ein, c, st))
        conn.execute("CREATE TEMP TABLE op_oc1 AS SELECT core, state, min(ein) AS ein FROM op_oc GROUP BY 1, 2 HAVING count(*) = 1")
        conn.execute("CREATE INDEX ON op_oc1 (core, state)")
        subjects = [("recipient", r[0], r[1], r[2]) for r in conn.execute(
            "SELECT key, name, state FROM op_recipients WHERE kind IN ('Teaching hospital', 'Non-covered entity') AND state IS NOT NULL")]
        subjects += [("payer", str(r[0]), r[1], r[2]) for r in conn.execute(
            "SELECT id, name, state FROM op_payers WHERE name IS NOT NULL AND state IS NOT NULL")]
        conn.execute("CREATE TEMP TABLE op_sc (kind text, key text, core text, state text) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy("COPY op_sc FROM STDIN") as cp:
            for kind, key, name, st in subjects:
                c = core(name or "")
                if len(c) >= 4:
                    cp.write_row((kind, key, c, st))
        n_org = conn.execute("""
            INSERT INTO op_org_links (key, kind, target_kind, target_key, how)
            SELECT s.key, s.kind, 'org', o.ein, 'name and state'
            FROM (SELECT kind, core, state, min(key) AS key FROM op_sc GROUP BY 1, 2, 3 HAVING count(*) = 1) s
            JOIN op_oc1 o ON o.core = s.core AND o.state = s.state""").rowcount
        n_biz = 0
        if conn.execute("SELECT to_regclass('biz_entities') IS NOT NULL").fetchone()[0]:
            n_biz = conn.execute("""
                INSERT INTO op_org_links (key, kind, target_kind, target_key, how)
                SELECT s.key, s.kind, 'biz', e.state || ':' || e.entity_id, 'name and state'
                FROM (SELECT kind, core, state, min(key) AS key FROM op_sc GROUP BY 1, 2, 3 HAVING count(*) = 1) s
                JOIN (SELECT name_core, addr_state, min(state) AS state, min(entity_id) AS entity_id FROM biz_entities
                      WHERE name_core <> '' AND addr_state IS NOT NULL GROUP BY 1, 2 HAVING count(*) = 1) e
                     ON e.name_core = s.core AND e.addr_state = s.state
                ON CONFLICT DO NOTHING""").rowcount
        conn.commit()
    status(f"openpayments links: {n_people:,} people, {n_org:,} nonprofits, {n_biz:,} business registrations")
    return {"people": n_people, "orgs": n_org, "biz": n_biz}


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:]) or ["load", "build", "links"]
    with db.connect() as conn:
        ensure_norm_function(conn)
        conn.commit()
    i = 0
    while i < len(argv):
        cmd = argv[i]
        i += 1
        years = []
        while i < len(argv) and argv[i].isdigit():
            years.append(int(argv[i]))
            i += 1
        if cmd == "load":
            load(years or None)
        elif cmd == "build":
            build()
        elif cmd == "links":
            links()
        else:
            raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
