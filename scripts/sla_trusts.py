"""Step 2 of discovery: every CIK in index_hits.tsv that filed a 10-D (or monthly 8-Ks),
with its EDGAR submissions history. Writes ~/sla-data/trusts.json.
"""

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loader import sec  # noqa: E402


def filings(cik: int) -> tuple[dict, list[dict]]:
    d = json.loads(sec.fetch(f"{sec.DATA}/submissions/CIK{cik:010d}.json"))
    out = []
    blocks = [d["filings"]["recent"]]
    for f in d["filings"].get("files", []):
        blocks.append(json.loads(sec.fetch(f"{sec.DATA}/submissions/{f['name']}")))
    for b in blocks:
        for i in range(len(b["form"])):
            out.append({k: b[k][i] for k in ("form", "filingDate", "accessionNumber", "primaryDocument",
                                             "reportDate", "items") if k in b})
    return d, out


def main():
    rows = [l.rstrip("\n").split("\t") for l in open(sec.CACHE / "index_hits.tsv")]
    by_cik = collections.defaultdict(lambda: {"names": set(), "forms": collections.Counter()})
    for form, company, cik, date, path in rows:
        by_cik[int(cik)]["names"].add(company)
        by_cik[int(cik)]["forms"][form] += 1
    keep = [c for c, v in by_cik.items() if v["forms"]["10-D"] or v["forms"]["8-K"] >= 6 or v["forms"]["424B5"]
            or v["forms"]["ABS-15G"] or v["forms"]["ABS-EE"]]
    print(len(by_cik), "ciks;", len(keep), "with 10-D / repeated 8-K / 424B5 / ABS-15G", flush=True)
    out = {}
    for i, cik in enumerate(sorted(keep)):
        try:
            d, fl = filings(cik)
        except sec.NotFound:
            continue
        forms = collections.Counter(f["form"] for f in fl)
        tend = [f["filingDate"] for f in fl if f["form"] in ("10-D", "10-D/A")]
        t15 = [f["filingDate"] for f in fl if f["form"].startswith("ABS-15G")]
        out[cik] = {"name": d["name"], "former": [x["name"] for x in d.get("formerNames", [])],
                    "sic": d.get("sic"), "sic_desc": d.get("sicDescription"),
                    "state": d.get("stateOfIncorporation"), "biz_state": (d.get("addresses", {}).get("business") or {}).get("stateOrCountry"),
                    "forms": dict(forms), "first_10d": min(tend) if tend else None,
                    "last_10d": max(tend) if tend else None,
                    "first_15g": min(t15) if t15 else None, "last_15g": max(t15) if t15 else None,
                    "first": min(f["filingDate"] for f in fl) if fl else None,
                    "last": max(f["filingDate"] for f in fl) if fl else None}
        if i % 50 == 0:
            print(i, cik, d["name"], flush=True)
    (sec.CACHE / "trusts.json").write_text(json.dumps(out, indent=1))
    print("done", len(out))


if __name__ == "__main__":
    main()
