"""Dry-run a source and print rows by (fiscal_year, institution) (dev helper; no DB)."""
import collections, json, sys
from common import DATA
import parsers
key = sys.argv[1]
spec = parsers.SPECS[key]
dkey = spec.get("data_key", key)
m = json.loads((DATA / dkey / "manifest.json").read_text())
c = collections.Counter(); tot = 0
for fname in sorted(m["files"]):
    if spec.get("file_filter") and not spec["file_filter"](fname):
        continue
    for r in spec["parse"](DATA / dkey / fname, fname):
        c[(r["fiscal_year"], r["institution"])] += 1; tot += 1
byfy = collections.defaultdict(list)
for (fy, i), n in sorted(c.items(), key=lambda x: (x[0][0] or 0, str(x[0][1]))):
    byfy[fy].append(f"{i}={n}")
for fy, v in byfy.items():
    print(fy, len(v), sum(int(x.rsplit('=',1)[1]) for x in v), "; ".join(v) if len(sys.argv) > 2 else "")
print("TOTAL", tot, "institutions", len({i for _, i in c}))
