"""Write data/intl-grants-abroad.csv: Schedule F rows (from the cached return XML) for EINs linked EXACT in
data/international-schools.csv."""
import csv, json, re
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
links = list(csv.DictReader(open(REPO / "data/international-schools.csv")))
eins = {re.sub(r"\D", "", r["ein"]).zfill(9) for r in links if r["match"] == "EXACT"}
cands = json.load(open(Path.home() / "unipay-data/intl/evidence_xml.json"))["cands"]
rows = []
for ein in sorted(eins):
    c = cands.get(ein)
    if not c or not c.get("xml"):
        continue
    f = c.get("filing") or {}
    x = c["xml"]
    for part, key in (("Part I: activities by region", "sched_f_regions"), ("Part II: grants to organizations", "sched_f_part2")):
        for item in x.get(key) or []:
            region, amount, desc = (list(item) + [None, None, None])[:3]
            if region is None and amount in (None, 0) and not desc:
                continue
            rows.append({"ein": ein, "tax_year": f.get("tax_year") or "", "object_id": f.get("object_id") or "",
                         "part": part, "region": region or "", "amount": "" if amount is None else amount,
                         "description": desc or ""})
with open(REPO / "data/intl-grants-abroad.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["ein", "tax_year", "object_id", "part", "region", "amount", "description"])
    w.writeheader(); w.writerows(rows)
print(len(rows), "rows for", len({r["ein"] for r in rows}), "EINs of", len(eins))
