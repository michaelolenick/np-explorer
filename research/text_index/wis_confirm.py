"""Final women-in-space cohort (owner, 2026-10-28): one Claude Haiku yes/no on outer space for every org in
research.wis_rows2 (the union of the women-in-space rows). Yes set -> research.wis_cohort. FUZZY."""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from loader import db

sys.path.insert(0, "research/text_index")
from senses import spent  # noqa: E402

MODEL = "anthropic/claude-haiku-5.5"
SPACE = re.compile(r"\b(outer space|space\w*|aerospace|astronaut\w*|cosmonaut\w*|astronom\w*|astrophysic\w*|nasa|"
                   r"planetari\w*|rocket\w*|satellite\w*|orbit\w*|mars|moon|lunar|stars?|telescope\w*|stem)\b", re.I)
WOMEN = re.compile(r"\b(women\w*|woman\w*|female\w*|girl\w*)\b", re.I)
HEAD = """For each organization below, answer whether its work, or a program or grant it describes, is about OUTER SPACE:
space exploration or science, astronomy, astronauts, rockets or spacecraft, space camps, space museums or space
education. Answer "N" when "space" means a room or place (office, meeting, safe, green, maker or art space), a place
name (Space Coast, Space City), or when it is only aviation or aerospace-industry jobs with nothing about space.
Reply with JSON only, one entry per numbered organization, "Y" or "N", like {"1": "Y", "2": "N"}."""


def snippets(txt):
    sents = re.split(r"(?<=[.!?;])\s+|\s*\|\|\s*|\n+", txt or "")
    hit = [s for s in sents if SPACE.search(s)]
    both = [s for s in hit if WOMEN.search(s)]
    out, seen = [], set()
    for s in both + hit:
        s = " ".join(s.split())[:260]
        if s.upper() not in seen:
            seen.add(s.upper()); out.append(s)
        if len(out) == 4:
            break
    return out


def ask(orgs):
    lines = [f"{i}. {o['name']}: " + " | ".join(o["snips"]) for i, o in enumerate(orgs, 1)]
    body = {"model": MODEL, "temperature": 0, "max_tokens": 1500,
            "messages": [{"role": "user", "content": HEAD + "\n\n" + "\n".join(lines)}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                          "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                txt = json.load(r)["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", txt, re.S)
            if not m:
                raise ValueError(f"no JSON in reply: {txt[:80]!r}")
            got = json.loads(m.group(0))
            return {orgs[int(k) - 1]["ein"]: str(v).strip().upper().startswith("Y")
                    for k, v in got.items() if str(k).isdigit() and 1 <= int(k) <= len(orgs)}
        except Exception as ex:  # noqa: BLE001
            err = ex; time.sleep(2 * (attempt + 1))
    print("batch failed:", err, flush=True)
    return {}


with db.connect() as c:
    rows = c.execute("""SELECT r.ein, coalesce(o.name, ''), concat_ws(' || ', o.mission_text, o.program_text, o.schedule_o_text)
                        FROM research.wis_rows2 r JOIN research.org_text o USING (ein)""").fetchall()
orgs = [{"ein": e, "name": n.split("\n")[0][:120], "snips": snippets(t)} for e, n, t in rows]
start = spent()
with db.connect() as c:                                # keep answers from an earlier run; ask only the rest
    res = dict(c.execute("SELECT ein, outer_space FROM research.wis_confirm").fetchall()) \
        if c.execute("SELECT to_regclass('research.wis_confirm')").fetchone()[0] else {}
for per in (10, 3):                                    # second pass, smaller batches, for anything the first missed
    todo = [o for o in orgs if o["ein"] not in res]
    with ThreadPoolExecutor(8) as ex:
        for r in ex.map(ask, [todo[i:i + per] for i in range(0, len(todo), per)]):
            res.update(r)
print(f"{len(orgs)} orgs, {len(res)} answered, {sum(res.values())} yes, ${spent() - start:.3f} spent", flush=True)
with db.connect() as c:
    c.execute("DROP TABLE IF EXISTS research.wis_confirm")
    c.execute("CREATE TABLE research.wis_confirm (ein text PRIMARY KEY, outer_space boolean, model text, labeled_at timestamptz DEFAULT now())")
    c.cursor().executemany("INSERT INTO research.wis_confirm (ein, outer_space, model) VALUES (%s, %s, %s)",
                           [(e, v, MODEL) for e, v in res.items()])
    c.execute("DROP TABLE IF EXISTS research.wis_cohort")
    c.execute("""CREATE TABLE research.wis_cohort AS SELECT r.* FROM research.wis_rows2 r JOIN research.wis_confirm c USING (ein)
                 WHERE c.outer_space""")
    c.execute("ALTER TABLE research.wis_cohort ADD PRIMARY KEY (ein)")
    c.execute("""COMMENT ON TABLE research.wis_cohort IS 'FUZZY. Final women-in-space cohort, 2026-10-28: research.wis_rows2
        orgs that anthropic/claude-haiku-5.5 (OpenRouter, 2026-10-28) confirmed as about outer space. Upstream flag
        precision was roughly two-thirds (hand check n=100).'""")
    c.commit()
    print(c.execute("SELECT count(*) FROM research.wis_cohort").fetchone()[0], "in research.wis_cohort")
