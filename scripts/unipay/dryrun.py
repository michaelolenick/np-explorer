"""Parse a source without touching the DB; print counts and a few rows (dev helper)."""
import collections, json, sys
from common import DATA, name_norm
import parsers
key = sys.argv[1]; lim = int(sys.argv[2]) if len(sys.argv) > 2 else 0
spec = parsers.SPECS[key]
m = json.loads((DATA / key / "manifest.json").read_text())
tot = 0
for fname in sorted(m["files"]):
    if spec.get("file_filter") and not spec["file_filter"](fname): continue
    c = collections.Counter(); n = 0; first = []
    for r in spec["parse"](DATA / key / fname, fname):
        n += 1; c[(r["fiscal_year"], r["institution"])] += 1
        if len(first) < 2: first.append({k: r[k] for k in r if k != "raw"} | {"nn": name_norm(r["person_name"])})
        if lim and n >= lim: break
    tot += n
    print(fname, n, len(c), c.most_common(3)); [print("   ", json.dumps(x, default=str)[:400]) for x in first]
print("TOTAL", tot)
