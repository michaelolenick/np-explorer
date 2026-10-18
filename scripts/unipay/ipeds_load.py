"""Optional task: IPEDS average salary by academic rank per institution (INSTITUTION AVERAGES, not individual pay).

Source: NCES IPEDS Data Center complete data files SAL2023_IS (academic year 2023-24, provisional) + HD2023 directory.
"""
import csv
import io
import json
import zipfile

from common import DATA, connect, to_num, wait_for_window

RANKS = {1: "Professor", 2: "Associate professor", 3: "Assistant professor", 4: "Instructor", 5: "Lecturer",
         6: "No academic rank", 7: "All ranks"}
CONTROL = {"1": "Public", "2": "Private nonprofit", "3": "Private for-profit"}

DDL = """
CREATE TABLE IF NOT EXISTS unipay.ipeds_faculty_salary_averages (
  unitid integer NOT NULL,
  institution_name text,
  state char(2),
  control text,
  academic_year text NOT NULL,
  arank smallint NOT NULL,
  rank_label text,
  staff_count integer,
  avg_salary_9mo_equated numeric,
  avg_salary_9mo_equated_men numeric,
  avg_salary_9mo_equated_women numeric,
  salary_outlays_total numeric,
  measure_note text NOT NULL DEFAULT 'INSTITUTION AVERAGE for full-time non-medical instructional staff (IPEDS); not individual pay',
  source_file text,
  file_sha256 text,
  PRIMARY KEY (unitid, academic_year, arank)
);
COMMENT ON TABLE unipay.ipeds_faculty_salary_averages IS
  'IPEDS Salaries survey: institution-level AVERAGE salaries by academic rank. These are averages, not individual pay.';
"""


def rows_from_zip(path):
    z = zipfile.ZipFile(path)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    with z.open(name) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")):
            yield {k.strip().upper(): v for k, v in r.items() if k}


def main():
    m = json.loads((DATA / "ipeds" / "manifest.json").read_text())["files"]
    hd = {r["UNITID"]: r for r in rows_from_zip(DATA / "ipeds" / "HD2023.zip")}
    out = []
    for r in rows_from_zip(DATA / "ipeds" / "SAL2023_IS.zip"):
        r = {k.strip().upper(): v for k, v in r.items()}
        u = hd.get(r["UNITID"], {})
        ar = int(r["ARANK"])
        out.append((int(r["UNITID"]), u.get("INSTNM"), u.get("STABBR"), CONTROL.get(u.get("CONTROL", ""), u.get("CONTROL")),
                    "2023-24", ar, RANKS.get(ar, str(ar)), int(to_num(r.get("SAINSTT")) or 0),
                    to_num(r.get("SAEQ9AT")), to_num(r.get("SAEQ9AM")), to_num(r.get("SAEQ9AW")), to_num(r.get("SAOUTLT")),
                    "~/unipay-data/ipeds/SAL2023_IS.zip", m["SAL2023_IS.zip"]["sha256"]))
    wait_for_window()
    conn = connect()
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("DELETE FROM unipay.ipeds_faculty_salary_averages WHERE academic_year='2023-24'")
        with cur.copy("""COPY unipay.ipeds_faculty_salary_averages (unitid, institution_name, state, control, academic_year, arank,
                 rank_label, staff_count, avg_salary_9mo_equated, avg_salary_9mo_equated_men, avg_salary_9mo_equated_women,
                 salary_outlays_total, source_file, file_sha256) FROM STDIN""") as cp:
            for row in out:
                cp.write_row(row)
    print("ipeds rows:", len(out))


if __name__ == "__main__":
    main()
