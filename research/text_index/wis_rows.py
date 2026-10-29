"""Builds research.wis_rows2 (2026-10-28), the women-in-space cohort: the rows rebuilt (rows 3-7: both words in the same sentence of mission, program or Schedule O;
every row gated by the outer-space flag), with overlap against row 1, a disjoint breakdown and the union."""
import re
from loader import db

W = r"\b(women|woman|womens|women's|female|females|girls?|girl's|girls')\b"
ROWS = {
    "r3 women + aerospace": ("(women | woman | female | girl) & aerospace", r"\baerospace\b"),
    "r4 women + astronaut": ("(women | woman | female | girl) & astronaut", r"\bastronauts?\b"),
    "r5 women + astronomy": ("(women | woman | female | girl) & (astronomy | astronomer)", r"\bastronom(y|ers?|ical)\b"),
    "r6 girls/women in STEM + space word": ("((girl | women) <2> stem) & (aerospace | space | astronaut | nasa | rocketry | astronomy | rocket | satellite)",
                                            r"\b(aerospace|space|astronauts?|nasa|rocketry|astronomy|rockets?|satellites?)\b"),
    "r7 girls + rocketry/satellite/astronaut/spacecraft": ("girl & (rocketry | satellite | astronaut | spacecraft)",
                                                           r"\b(rocketry|satellites?|astronauts?|spacecraft)\b"),
}
MPS = "coalesce(tsv_mission, ''::tsvector) || coalesce(tsv_program, ''::tsvector) || coalesce(tsv_schedule_o, ''::tsvector)"
with db.connect() as c:
    lab = {r[0] for r in c.execute("SELECT DISTINCT ein FROM research.org_codes WHERE topic='space' AND codes LIKE '%O%'")}
    r1 = {r[0] for r in c.execute(f"""
        SELECT DISTINCT o.ein FROM research.org_codes w JOIN research.org_text o USING (ein)
        WHERE w.topic = 'women' AND w.codes ~ '[IC]' AND (w.in_mission OR w.in_program OR w.in_schedule_o)
          AND {MPS} @@ to_tsquery('english', 'space | ' || research.terms('outer_space'))""")} & lab
    sets = {"r1 flag + women/girls mention": r1}
    for row, (q, topic_re) in ROWS.items():
        same = set()
        for ein, txt in c.execute(f"""SELECT ein, concat_ws(' || ', mission_text, program_text, schedule_o_text)
                                      FROM research.org_text WHERE {MPS} @@ to_tsquery('english', %s)""", (q,)):
            if ein in lab and any(re.search(W, s, re.I) and re.search(topic_re, s, re.I)
                                  for s in re.split(r"(?<=[.!?;])\s+|\s*\|\|\s*|\n+", txt or "")):
                same.add(ein)
        sets[row] = same
    union = set().union(*sets.values())
    print("MEMBERSHIP (overlapping; do not add)")
    for k, s in sets.items():
        print(f"  {k:52s} {len(s):4d}   also in r1: {len(s & r1):4d}   not in r1: {len(s - r1):3d}")
    print(f"  {'UNION: at least one row':52s} {len(union):4d}")
    print("DISJOINT (each org once, most specific row first; these add to the union)")
    order = ["r5 women + astronomy", "r4 women + astronaut", "r3 women + aerospace",
             "r6 girls/women in STEM + space word", "r7 girls + rocketry/satellite/astronaut/spacecraft"]
    left, tot = set(union), 0
    for k in order:
        b = sets[k] & left; left -= b; tot += len(b)
        print(f"  {k:52s} {len(b):4d}")
    print(f"  {'r1 only (flag + women/girls, no specific wording)':52s} {len(left):4d}")
    print(f"  {'TOTAL':52s} {tot + len(left):4d}")
    c.execute("DROP TABLE IF EXISTS research.wis_rows2")
    c.execute("CREATE TABLE research.wis_rows2 (ein text PRIMARY KEY, r1 bool, r3 bool, r4 bool, r5 bool, r6 bool, r7 bool)")
    keys = ["r1 flag + women/girls mention"] + list(ROWS)
    c.cursor().executemany("INSERT INTO research.wis_rows2 VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           [(e, *[e in sets[k] for k in keys]) for e in sorted(union)])
    c.execute("""COMMENT ON TABLE research.wis_rows2 IS 'FUZZY. Women-in-space rows, 2026-10-28, same-sentence matching for
        rows 3-7; every row gated by the outer-space flag (term list OR anthropic/claude-haiku-5.5 via OpenRouter, run
        2026-10-28; hand-checked precision 66%% strict, n=100, research.space_label_check).'""")
    c.commit()
