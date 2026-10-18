"""Task 1a: create unipay schema + catalog table and load all Phase 1 sources."""
import glob
import json
import sys

from common import REPO, connect, load_progress, save_progress, wait_for_window

DDL = """
CREATE SCHEMA IF NOT EXISTS unipay;
CREATE TABLE IF NOT EXISTS unipay.university_pay_sources (
  id serial PRIMARY KEY,
  state char(2) NOT NULL,
  state_name text,
  institution text,
  system text,
  url text,
  download_url text,
  coverage_years text,
  institutions_covered text,
  employees text,
  format text,
  fields text[],
  update_frequency text,
  size text,
  login_or_form boolean,
  terms text,
  rating char(1),
  blocker text,
  notes text,
  loaded boolean DEFAULT false,
  rows_loaded integer,
  researched_at timestamptz
);
CREATE TABLE IF NOT EXISTS unipay.state_research (
  state char(2) PRIMARY KEY,
  state_name text,
  systems_found text[],
  best_rating char(1),
  private_extra text,
  gaps text,
  notes text,
  researched_at timestamptz
);
"""


def s(v):
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def main():
    wait_for_window()
    conn = connect()
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("SELECT count(*) FROM unipay.university_pay_sources")
        if cur.fetchone()[0] and "--reload" not in sys.argv:
            print("catalog already loaded")
            return
        cur.execute("TRUNCATE unipay.university_pay_sources RESTART IDENTITY")
        cur.execute("TRUNCATE unipay.state_research")
        n = 0
        for f in sorted(glob.glob(str(REPO / "data/unipay-states/*.json"))):
            d = json.load(open(f))
            cur.execute(
                "INSERT INTO unipay.state_research VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (d["state"], d.get("state_name"), [s(x) for x in d.get("systems_found") or []],
                 (d.get("best_rating") or None) and str(d["best_rating"])[:1], s(d.get("private_extra")),
                 s(d.get("gaps")), s(d.get("notes")), d.get("researched_at")),
            )
            for src in d.get("sources", []):
                fields = src.get("fields")
                if isinstance(fields, str):
                    fields = [x.strip() for x in fields.split(",") if x.strip()]
                lof = src.get("login_or_form")
                if isinstance(lof, str):
                    lof = lof.strip().lower() in ("true", "yes", "y")
                cur.execute(
                    """INSERT INTO unipay.university_pay_sources
                    (state,state_name,institution,system,url,download_url,coverage_years,institutions_covered,
                     employees,format,fields,update_frequency,size,login_or_form,terms,rating,blocker,notes,researched_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (d["state"], d.get("state_name"), s(src.get("institution")), s(src.get("system")),
                     s(src.get("url")), s(src.get("download_url")), s(src.get("coverage_years")),
                     s(src.get("institutions_covered")), s(src.get("employees")), s(src.get("format")),
                     [s(x) for x in fields] if fields else None, s(src.get("update_frequency")), s(src.get("size")),
                     lof, s(src.get("terms")), (s(src.get("rating")) or None) and s(src.get("rating"))[:1],
                     s(src.get("blocker")), s(src.get("notes")), d.get("researched_at")),
                )
                n += 1
        print("loaded", n, "sources")
    p = load_progress()
    p["catalog"] = True
    save_progress(p)


if __name__ == "__main__":
    main()
