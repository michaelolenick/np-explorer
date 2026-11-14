"""Build the GDELT name dictionaries (see loader/gdelt_parse.py) from the database: python -m loader.gdelt dict."""
from __future__ import annotations

import array
import mmap
import os
import sys
from pathlib import Path

from loader import db
from loader.gdelt_parse import BITS, MASK, h64, pnorm

ORG_KINDS = ("org", "sec", "college", "ipo_company", "formd", "adv", "fed", "contractor", "lda_client", "lda_registrant",
             "fec_committee", "op_recipient", "op_payer", "fara_principal", "fara_registrant", "recallfirm",
             "f5500_sponsor", "pat_assignee")
GENERIC = {"first baptist church", "united states", "america", "government", "university", "college", "church",
           "school", "company", "foundation", "association", "police", "city", "county", "state", "board"}


def build(dest: str = "/bulk/gdelt/dict") -> dict:
    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    sets = {"orgs": array.array("Q"), "pers_u": array.array("Q"), "pers_c": array.array("Q")}
    with conn.cursor(name="o") as cur:
        cur.itersize = 50000
        # an organization name worth looking for: two words or more, or one distinctive word that names one record
        cur.execute("""SELECT core FROM (SELECT core, count(*) n, max(length(core)) l FROM xref_names
                       WHERE kind = ANY(%s) AND length(core) >= 5 AND core !~ '^[0-9 ]+$' GROUP BY core) t
                       WHERE core LIKE '%% %%' OR (n = 1 AND l >= 6)""", (list(ORG_KINDS),))
        for (c,) in cur:
            if c not in GENERIC:
                sets["orgs"].append(h64(c))
    with conn.cursor(name="p") as cur:
        cur.itersize = 50000
        cur.execute("""SELECT name_norm, count(*) FROM person_clusters WHERE NOT coalesce(is_institution, false)
                       AND name_norm LIKE '%% %%' AND length(name_norm) >= 7 GROUP BY name_norm""")
        for n, c in cur:
            sets["pers_u" if c == 1 else "pers_c"].append(h64(n))
    bm = bytearray(1 << (BITS - 3))
    for k, arr in sets.items():
        a = sorted(set(arr))
        sets[k] = array.array("Q", a)
        for v in a:
            i = v & MASK
            bm[i >> 3] |= 1 << (i & 7)
        with open(d / f"{k}.u64.tmp", "wb") as f:
            sets[k].tofile(f)
        os.replace(d / f"{k}.u64.tmp", d / f"{k}.u64")
    with open(d / "bitmap.bin.tmp", "wb") as f:
        f.write(bm)
    os.replace(d / "bitmap.bin.tmp", d / "bitmap.bin")
    out = {k: len(v) for k, v in sets.items()}
    print("gdelt dict:", out, flush=True)
    return out
