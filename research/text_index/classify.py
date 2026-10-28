"""Label organizations for a topic that words alone can't settle (owner, 2026-10-28: a cheap model through
OpenRouter, cheaper than Haiku; send only the org's name and, where it helps, a short summary).

"space" is split into its senses (owner: "space where rockets go is one thing; a space for women or a space for men is
another"; "there's also office space, parking space... disambiguate"). Every org whose text says "space" or
"aerospace" gets every code that applies:
    O  outer space: exploration, astronomy, astronauts, rockets, satellites, aerospace, space education
    W  a place on Earth set aside for women or girls ("a safe space for women", "a women's space")
    M  a place on Earth set aside for men or boys
    F  facility space: office, meeting, studio, classroom, storage, rental or leased space, room in a building
    P  parking
    G  green, open or natural land: parks, gardens, conserved open space
    S  a safe, quiet, brave or personal space that is not specifically for women or for men; "space to heal / grow"
    X  anything else: "the X space" meaning a field or sector, a gap, a space of time, typography, aerospace workers'
       unions (Machinists, UAW), aviation alone
The model sees the org's name, the first 300 characters of its mission and up to three 200-character snippets around
the word (mentions near women / men / astronomy words first), ten orgs per request. Labels go to research.topic_labels
(topic, ein, codes, label = outer space, model); labeled orgs are skipped, so a rerun only does new ones and retries
failed batches.

Usage:  .venv/bin/python research/text_index/classify.py space
        .venv/bin/python research/text_index/classify.py space --compare 200 --models mistralai/mistral-small-24b-instruct-2501
            (another model's agreement with Haiku on a sample)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loader import db  # noqa: E402

# Haiku, not Mistral-small: on 200 real orgs they agreed on outer space / for women / for men 199 of 200 each, but
# Mistral's misses were the ones that matter ("a brave space for girls" missed; a survivors' group called a space for
# men). Haiku costs about $1-2 for every "space" org.
MODEL = "anthropic/claude-haiku-5.5"
REFERENCE = "anthropic/claude-haiku-5.5"
PER_CALL = 10
CODES = "OWMFPGSX"

SPACE_PROMPT = """Each organization below uses the word "space" (or "aerospace"). Say which senses of "space" it uses, with these codes:
O = OUTER SPACE: space exploration or science, astronomy, astronauts, rockets, satellites, aerospace, space education.
W = a place on Earth set aside FOR WOMEN OR GIRLS (a safe space for women, a women's space, a space where girls can ...).
M = a place on Earth set aside FOR MEN OR BOYS (a space for men, a men's space, a space where boys can ...).
F = FACILITY space: office, meeting, event, studio, classroom, storage, rental or leased space; room in a building.
P = PARKING space.
G = GREEN, OPEN or natural space: parks, gardens, conserved open land.
S = a safe, quiet, brave, sacred or personal space NOT specifically for women or for men; space to heal, grow or reflect.
X = anything else: "the X space" meaning a field or sector, a gap, a space of time, a labor union of aerospace or auto
    workers (Machinists, UAW), aviation alone.
W and M need "space" itself to mean a place or room for that group. A program, scholarship, career or field for
women or men ("women in aerospace", "space careers for girls") is not W or M: code the sense of "space" it uses.
Give every code that applies, e.g. "F", "OF", "WS", "GP"."""

TOPICS = {
    "space": {
        "prompt": SPACE_PROMPT,
        "word": r"(?:aero)?spac\w*",
        "first": r"\b(wom[ae]n|girls?|female|sisters?|mothers?|m[ae]n|boys?|male|brothers?|fathers?|astro\w*|"
                 r"planet\w*|rockets?|satellites?|nasa|orbit\w*|launch\w*|stars?|galax\w*)\b",
        "candidates": "SELECT ein FROM research.space_candidates",
        "outer_code": "O",
    },
}


def _snippets(text: str, t: dict, n: int = 3, width: int = 100) -> list[str]:
    """Up to n snippets around the word: those near the 'first' words, then the rest, in order."""
    found = []
    for m in re.finditer(r"\b" + t["word"] + r"\b", text or "", re.I):
        s = " ".join(text[max(0, m.start() - width): m.end() + width].split())
        found.append((0 if re.search(t["first"], s, re.I) else 1, len(found), s))
        if len(found) >= 60:
            break
    out = []
    for _, _, s in sorted(found):
        if s not in out:
            out.append(s)
        if len(out) == n:
            break
    return out


def _rows(conn, eins: list[str], t: dict) -> list[dict]:
    rows = conn.execute("""SELECT ein, coalesce(name, name_text) AS name, mission_text, text
                           FROM research.org_text WHERE ein = ANY(%s)""", (eins,)).fetchall()
    return [{"ein": ein, "name": (name or "").split("\n")[0][:120],
             "mission": " ".join((mission or "").split("\n")[0].split())[:300],
             "snippets": _snippets(text, t)} for ein, name, mission, text in rows]


def _codes(v) -> str:
    return "".join(c for c in CODES if c in str(v).upper()) or "X"


def _ask(model: str, prompt_head: str, orgs: list[dict]) -> dict[str, str]:
    lines = [f"{i}. Name: {o['name']}\n   Mission: {o['mission'] or '(none)'}\n   Mentions: " + " | ".join(o["snippets"])
             for i, o in enumerate(orgs, 1)]
    prompt = (f"{prompt_head}\n\nReply with JSON only, one entry per numbered organization, like "
              '{"1": "F", "2": "OW"}.\n\n' + "\n".join(lines))
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 1500}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                          "Content-Type": "application/json"})
    err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            txt = d["choices"][0]["message"]["content"] or ""
            got = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
            return {orgs[int(k) - 1]["ein"]: _codes(v)
                    for k, v in got.items() if str(k).isdigit() and 1 <= int(k) <= len(orgs)}
        except Exception as ex:  # noqa: BLE001 - retried, then the batch is left for the next run
            err = ex
            time.sleep(2 * (attempt + 1))
    print(f"batch failed: {err}", flush=True)
    return {}


SETUP = """CREATE TABLE IF NOT EXISTS research.topic_labels (
               topic text NOT NULL, ein text NOT NULL, label boolean, model text, labeled_at timestamptz DEFAULT now(),
               PRIMARY KEY (topic, ein));
           ALTER TABLE research.topic_labels ADD COLUMN IF NOT EXISTS codes text;"""


def label(topic: str, model: str, workers: int = 12) -> None:
    t = TOPICS[topic]
    with db.connect() as conn:
        conn.execute(SETUP)
        conn.commit()
        eins = [r[0] for r in conn.execute(
            f"SELECT ein FROM ({t['candidates']}) c WHERE ein NOT IN "
            "(SELECT ein FROM research.topic_labels WHERE topic = %s AND codes IS NOT NULL)", (topic,)).fetchall()]
    print(f"{topic}: {len(eins)} orgs to label with {model}", flush=True)
    done = 0
    for i in range(0, len(eins), 400):
        chunk = eins[i:i + 400]
        with db.connect() as conn:
            orgs = _rows(conn, chunk, t)
        batches = [orgs[j:j + PER_CALL] for j in range(0, len(orgs), PER_CALL)]
        with ThreadPoolExecutor(workers) as ex:
            results = list(ex.map(lambda b: _ask(model, t["prompt"], b), batches))
        with db.connect() as conn:
            for res in results:
                for ein, codes in res.items():
                    conn.execute("""INSERT INTO research.topic_labels (topic, ein, codes, label, model)
                                    VALUES (%s, %s, %s, %s, %s)
                                    ON CONFLICT (topic, ein) DO UPDATE SET codes = EXCLUDED.codes,
                                        label = EXCLUDED.label, model = EXCLUDED.model, labeled_at = now()""",
                                 (topic, ein, codes, t["outer_code"] in codes, model))
            conn.commit()
        done += len(chunk)
        if done % 4000 < 400 or done == len(eins):
            print(f"{done}/{len(eins)}", flush=True)


def compare(topic: str, n: int, models: list[str]) -> None:
    t = TOPICS[topic]
    with db.connect() as conn:
        eins = [r[0] for r in conn.execute(f"SELECT ein FROM ({t['candidates']}) c ORDER BY md5(ein) LIMIT %s",
                                           (n,)).fetchall()]
        orgs = _rows(conn, eins, t)
    batches = [orgs[i:i + PER_CALL] for i in range(0, len(orgs), PER_CALL)]
    answers = {}
    for m in [REFERENCE] + models:
        res = {}
        with ThreadPoolExecutor(8) as ex:
            for r in ex.map(lambda b: _ask(m, t["prompt"], b), batches):
                res.update(r)
        answers[m] = res
    ref = answers[REFERENCE]
    for m in [REFERENCE] + models:
        print(f"{m}: {len(answers[m])} labeled; orgs per code "
              f"{ {c: sum(c in v for v in answers[m].values()) for c in CODES} }")
    for m in models:
        both = [e for e in ref if e in answers[m]]
        for c in CODES:
            agree = sum((c in ref[e]) == (c in answers[m][e]) for e in both)
            print(f"   code {c}: agrees with {REFERENCE} on {agree}/{len(both)}")
        for o in orgs:
            e = o["ein"]
            if e in both and ("O" in ref[e]) != ("O" in answers[m][e]) or e in both and \
                    (set(ref[e]) & set("WM")) != (set(answers[m][e]) & set("WM")):
                print(f"   O/W/M differ: ref={ref[e]} got={answers[m][e]} {o['name']} | {o['snippets'][:1]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", choices=list(TOPICS))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--compare", type=int, default=0)
    ap.add_argument("--models", default=MODEL)
    a = ap.parse_args()
    if a.compare:
        compare(a.topic, a.compare, a.models.split(","))
    else:
        label(a.topic, a.model)
