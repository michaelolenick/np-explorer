"""Senses of ambiguous terms in the 990 text (owner, 2026-10-28): "space" isn't the only one.

For each term below: the words (whole words only), its senses (one-letter codes), and the phrases that settle a
sense on their own. The same phrase list gives
  - exact phrase counts with no model (research.sense_phrases -> research.q_sense_phrases), and
  - the rule pass: every mention of the term in an org's text is matched against the phrases; a mention inside one
    takes that phrase's sense, and the mentions left over go to Claude Haiku (OpenRouter) with the org's name, the
    first 300 characters of its mission and up to three 200-character snippets around them.
For women, men and girls/boys, a mention in the org's own name that no phrase settles is the name sense (N).
"space" is labeled separately (classify.py: every org that says it) and joins the same tables.

Tables: research.sense_defs (topic, code, sense, description), research.sense_phrases (topic, codes, label, tsq),
research.org_senses (topic, ein, the fields the term appears in, rule_codes, n_ambiguous, snippets, model_codes).

Usage (from the np-explorer checkout, .env loaded):
  .venv/bin/python research/text_index/senses.py sync          definitions -> research.sense_defs / sense_phrases
  .venv/bin/python research/text_index/senses.py rules         the rule pass over research.org_text
  .venv/bin/python research/text_index/senses.py label         Haiku on the leftover mentions (rerun = retry)
  .venv/bin/python research/text_index/senses.py test          the hand-labeled cases in sense_tests.py
  .venv/bin/python research/text_index/senses.py falsehits     men / male / boys: substring vs whole-word hits
"""

from __future__ import annotations

import json
import os
import multiprocessing as mp
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loader import db  # noqa: E402

import classify  # noqa: E402  (the OpenRouter call and the model choice)

MODEL = classify.MODEL
PER_CALL = 10
GAP = {"and", "&", "or", "of", "the", "a", "an", "for", "to", "in", "on", "at", "against", "with", "from", "by",
       "into", "is", "was", "our", "its", "their", "his", "her", "this", "that", "these", "those"}
FIELDS = ("name", "mission", "program", "schedule_o", "grant_purpose", "contractor_service")


# ---------------------------------------------------------------- phrase specs -> regex and tsquery
# A phrase is space-separated slots; a slot is alternatives split by "|"; a trailing "'s" or "'" marks an optional
# possessive; "*" is a prefix. Slots made only of small words (and, &, of, for...) are gaps in the tsquery.

def _slot_re(slot: str) -> str:
    alts, poss = [], False
    for a in slot.split("|"):
        if a.endswith("'s") or a.endswith("'"):
            poss, a = True, a[:-2] if a.endswith("'s") else a[:-1]
        alts.append(re.escape(a).replace(r"\*", r"\w*"))
    return f"(?:{'|'.join(alts)})" + (r"(?:'s|’s|s'|'|s)?" if poss else "")


def phrase_re(p: str) -> str:
    return r"\b" + r"[\s\-]+".join(_slot_re(s) for s in p.split()) + (r"" if p.endswith("*") else r"\b")


def phrase_tsq(p: str) -> str | None:
    """None when the phrase starts with a small word ("our mission"): the index drops those, so the phrase would
    match every "mission". Such phrases work in the rule pass only."""
    if all(a.lower() in GAP for a in p.split()[0].split("|")):
        return None
    tight, loose, gap_t, gap_l, prev_poss = [], [], 0, 0, False
    for slot in p.split():
        alts = [a[:-2] if a.endswith("'s") else a[:-1] if a.endswith("'") else a for a in slot.split("|")]
        if all(a.lower() in GAP for a in alts):
            gap_t += 1
            gap_l += 0 if "&" in alts else 1
            continue
        term = "(" + " | ".join(a.replace("*", ":*") for a in alts) + ")"
        if tight:
            tight.append(f"<{1 + gap_t}>")
            loose.append(f"<{1 + gap_l + (1 if prev_poss else 0)}>")
        tight.append(term)
        loose.append(term)
        gap_t = gap_l = 0
        prev_poss = any(a.endswith("'s") or a.endswith("'") for a in slot.split("|"))
    t, lo = " ".join(tight), " ".join(loose)
    return f"({t})" if t == lo else f"({t}) | ({lo})"


# ---------------------------------------------------------------- the terms
_LAUNCHED = ("program|programs|initiative|initiatives|campaign|campaigns|website|project|projects|pilot|product|"
             "products|app|service|series|fund|podcast|platform|partnership")

# rules: (codes, label, [phrases]); the first rule whose phrase covers a mention decides it (order matters).
TOPICS: dict[str, dict] = {
    "women": {
        "display": "women / woman / female / ladies / girls",
        "words": r"women|woman|womens|female|females|ladies|girls?",
        "tsq": "women | woman | female | ladies | girl",
        "name_code": "N",
        "senses": {"I": ("issues", "women's issues or services for women and girls (health, shelter, rights, "
                                   "programs that serve women)"),
                   "N": ("name", "a name: the org's own name or a group's (women's auxiliary, Ladies of Charity, a "
                                 "church women's group, a women's club)"),
                   "C": ("incidental", "incidental: a woman on the board or staff, 'men and women' meaning everyone, "
                                       "a statistic, a passing mention")},
        "rules": [
            ("N", "women's / ladies' auxiliary, club, guild, league, society, fellowship, ministry, group",
             ["women's|ladies'|womens auxiliary|club|clubs|guild|league|society|fellowship|association|ministry|"
              "ministries|group|circle|council|aid|chorus|board"]),
            ("N", "Ladies of Charity", ["ladies of charity"]),
            ("C", "men and women, male and female (everyone)",
             ["men and|& women", "women and|& men", "man or woman", "male and|or female", "female and|or male",
              "boys and girls", "girls and boys"]),
            ("I", "women's health / shelter / rights / center / services / empowerment",
             ["women's|womens health|shelter|shelters|rights|center|centers|centre|services|empowerment|issues|"
              "leadership|veterans|prison|recovery|resource|crisis"]),
            ("I", "pregnant / homeless / battered / incarcerated women",
             ["pregnant|homeless|battered|abused|incarcerated|low-income|single|older|young|immigrant|refugee "
              "women"]),
            ("I", "women and girls, violence against women",
             ["women and|& girls", "violence against women", "services|housing|support|programs|program|shelter "
              "for women|girls"]),
        ],
    },
    "men": {
        "display": "men / male / boys",
        "words": r"men|mens|male|males|boys?",
        "tsq": "men | male | boy",
        "name_code": "N",
        "senses": {"I": ("issues", "men's issues or services for men and boys (health, recovery, fatherhood, "
                                   "programs that serve men)"),
                   "N": ("name", "a name: the org's own or a group's (Young Men's Christian Association, a Men's "
                                 "Club, Men of Faith, Boys Town, Boys & Girls Clubs)"),
                   "C": ("incidental", "incidental: 'men and women' meaning everyone, a man on the board, a "
                                       "statistic, a passing mention")},
        "rules": [
            ("N", "Young Men's Christian / Hebrew Association", ["young men's christian|hebrew"]),
            ("N", "men's club, fellowship, ministry, group, chorus, shed",
             ["men's|mens club|clubs|fellowship|ministry|ministries|group|groups|chorus|choir|league|association|"
              "breakfast|guild|society|shed|sheds|council|bible", "men of faith"]),
            ("N", "Boys Town, Boys & Girls Clubs", ["boys town", "boys and|& girls club|clubs|clubhouse"]),
            ("C", "men and women, male and female (everyone)",
             ["men and|& women", "women and|& men", "male and|or female", "female and|or male", "boys and girls",
              "girls and boys"]),
            ("I", "men's health / shelter / services / recovery",
             ["men's|mens health|shelter|shelters|services|issues|recovery|support|crisis"]),
            ("I", "homeless / incarcerated / young / Black men; men of color; male survivors",
             ["homeless|incarcerated|young|black|older|at-risk|formerly men|males|boys", "men of color",
              "male survivors", "services|housing|programs|program|shelter|support for men|boys"]),
        ],
    },
    "domestic": {
        "display": "domestic",
        "words": r"domestic",
        "tsq": "domestic",
        "senses": {"D": ("violence", "domestic violence or abuse"),
                   "A": ("animals", "domestic animals or pets"),
                   "W": ("workers", "domestic workers"),
                   "P": ("production", "domestic production, manufacturing, economy, energy, industry"),
                   "T": ("travel", "domestic travel or flights"),
                   "G": ("vs_foreign", "domestic as opposed to foreign or international (domestic grants, "
                                       "organizations, programs)"),
                   "O": ("other", "anything else (domestic partner, domestic relations, domestic policy...)")},
        "rules": [
            ("D", "domestic violence / abuse / assault", ["domestic violence|abuse|assault|abuser|abusers",
                                                          "domestic partner violence|abuse"]),
            ("A", "domestic animals / pets", ["domestic animal|animals|pet|pets|cat|cats|dog|dogs|livestock|fowl"]),
            ("W", "domestic workers", ["domestic worker|workers|employee|employees|help|servant|servants|work"]),
            ("P", "domestic production / economy / industry",
             ["domestic production|manufactur*|economy|energy|oil|industry|industries|market|markets|supply|"
              "product|products|agriculture|food"]),
            ("T", "domestic travel / flights", ["domestic travel|flight|flights|tourism|trip|trips|airline|airlines"]),
            ("G", "domestic vs international; grants to domestic organizations",
             ["domestic and|& international|foreign|overseas", "international|foreign|overseas and|& domestic",
              "domestic grant|grants|grantee|grantees|organization|organizations|charity|charities|recipient|"
              "recipients|nonprofit|nonprofits|government|governments|individual|individuals"]),
            ("O", "domestic partner / relations", ["domestic partner|partners|partnership|relations"]),
        ],
    },
    "violence": {
        "display": "violence / violent",
        "words": r"violence|violent",
        "tsq": "violence | violent",
        "senses": {"D": ("domestic", "domestic, intimate-partner, dating or family violence"),
                   "G": ("gun", "gun or firearm violence"),
                   "C": ("community", "community, street, gang, youth or school violence"),
                   "S": ("sexual", "sexual violence"),
                   "P": ("prevention", "violence prevention in general, not one kind"),
                   "O": ("other", "anything else (violent crime victims, violence in media, war...)")},
        "rules": [
            ("D", "domestic / intimate-partner / dating / family violence",
             ["domestic|dating|family|partner|relationship violence", "intimate partner violence"]),
            ("G", "gun / firearm violence", ["gun|firearm|firearms violence"]),
            ("C", "community / street / gang / youth / school violence",
             ["community|street|gang|youth|neighborhood|urban|school violence"]),
            ("S", "sexual violence", ["sexual violence"]),
            ("P", "violence prevention", ["violence prevention", "prevent|preventing|prevention of violence",
                                          "anti-violence", "non-violence|nonviolence"]),
        ],
    },
    "abuse": {
        "display": "abuse / abused / abusive",
        "words": r"abuse|abused|abuses|abusive",
        "tsq": "abuse | abused | abusive",
        "senses": {"D": ("domestic", "domestic or partner abuse"),
                   "C": ("child", "child abuse"),
                   "E": ("elder", "elder abuse"),
                   "S": ("sexual", "sexual abuse"),
                   "U": ("substance", "substance, drug or alcohol abuse"),
                   "A": ("animal", "animal abuse or cruelty"),
                   "O": ("other", "anything else (abuse of power, financial abuse in general...)")},
        "rules": [
            ("D", "domestic / partner / spousal abuse", ["domestic|partner|spousal|spouse abuse"]),
            ("CS", "child sexual abuse", ["child sexual abuse"]),
            ("C", "child abuse; abused children", ["child|childhood|children abuse", "abuse of|against children",
                                                   "abused and neglected children", "abused children"]),
            ("E", "elder abuse", ["elder|elderly abuse", "abuse of the elderly|elders"]),
            ("S", "sexual abuse", ["sexual abuse", "sexually abused"]),
            ("U", "substance / drug / alcohol abuse",
             ["substance|drug|alcohol|chemical|opioid|narcotic abuse", "alcohol and drug abuse",
              "drug and alcohol abuse", "abuse of drugs|alcohol|substances"]),
            ("A", "animal abuse", ["animal abuse", "abuse of animals", "abused animals|dogs|cats|horses|pets"]),
        ],
    },
    "shelter": {
        "display": "shelter / shelters",
        "words": r"shelter|shelters|sheltered|sheltering",
        "tsq": "shelter",
        "senses": {"H": ("homeless", "a homeless shelter or emergency housing for homeless people"),
                   "D": ("domestic", "a domestic violence shelter"),
                   "A": ("animal", "an animal shelter"),
                   "X": ("disaster", "disaster or evacuation shelter"),
                   "T": ("tax", "a tax shelter"),
                   "O": ("other", "anything else (bus or picnic shelter, shelter in place, food and shelter as "
                                  "basic needs...)")},
        "rules": [
            ("H", "homeless shelter", ["homeless shelter|shelters", "shelter|shelters for the homeless",
                                       "shelter|shelters for homeless", "overnight|warming|winter shelter|shelters"]),
            ("D", "domestic violence / women's shelter",
             ["domestic violence shelter|shelters", "women's|womens shelter|shelters", "battered women's shelter",
              "shelter|shelters for battered|abused women"]),
            ("A", "animal shelter", ["animal|dog|cat|pet|no-kill shelter|shelters", "shelter animals|dogs|cats|pets"]),
            ("X", "disaster / evacuation shelter", ["disaster|evacuation|storm|tornado|hurricane shelter|shelters"]),
            ("T", "tax shelter", ["tax shelter|shelters"]),
            ("O", "bus / picnic shelter, shelter in place", ["bus|picnic|transit shelter|shelters",
                                                             "shelter in place"]),
        ],
    },
    "survivor": {
        "display": "survivor / survivors",
        "words": r"survivor|survivors|survivorship",
        "tsq": "survivor | survivorship",
        "senses": {"D": ("domestic", "domestic violence survivors"),
                   "S": ("sexual", "sexual assault or abuse survivors"),
                   "C": ("cancer", "cancer survivors"),
                   "X": ("disaster", "disaster survivors"),
                   "L": ("suicide", "suicide loss survivors"),
                   "O": ("other", "anything else (Holocaust or trafficking survivors, survivor benefits or "
                                  "pensions...)")},
        "rules": [
            ("C", "cancer survivors", ["cancer survivor|survivors|survivorship", "survivors of cancer"]),
            ("S", "sexual assault / abuse survivors",
             ["sexual assault|violence|abuse survivor|survivors", "rape|incest survivor|survivors",
              "survivors of sexual|rape|incest"]),
            ("D", "domestic violence survivors", ["domestic violence|abuse survivor|survivors",
                                                  "survivors of domestic|intimate"]),
            ("L", "suicide loss survivors", ["suicide loss survivor|survivors", "suicide survivor|survivors",
                                             "survivors of suicide"]),
            ("X", "disaster survivors", ["disaster|hurricane|fire|wildfire|flood|tornado|earthquake survivor|survivors"]),
            ("O", "Holocaust survivors; survivor benefits",
             ["holocaust survivor|survivors", "survivor|survivors benefit|benefits|annuity|pension"]),
        ],
    },
    "science": {
        "display": "science / scientific / STEM",
        "words": r"science|sciences|scientific|scientist|scientists|stem",
        "tsq": "science | scientific | scientist | stem",
        "senses": {"E": ("research_education", "science or STEM education, or scientific or medical research"),
                   "C": ("christian_science", "Christian Science (the church)"),
                   "I": ("incidental", "incidental or other: 'stems from', a plant stem, 'the science of "
                                       "fundraising', a passing mention")},
        "rules": [
            ("C", "Christian Science", ["christian science|scientist|scientists", "church of christ scientist"]),
            ("I", "stems from", ["stem|stems from"]),
            ("E", "science / STEM education, camps, fairs, programs",
             ["science|stem|steam education|educators|program|programs|programming|camp|camps|class|classes|"
              "curriculum|learning|fair|fairs|olympiad|club|clubs|outreach|teacher|teachers|enrichment|activities|"
              "museum|center|centre|careers"]),
            ("E", "scientific / medical research; stem cells",
             ["scientific research|study|studies|discovery", "medical|biomedical|clinical science|sciences",
              "stem cell|cells"]),
        ],
    },
    "launch": {
        "display": "mission / launch / rocket / orbit / flight",
        "words": r"missions?|launch|launched|launches|launching|rockets?|rocketry|orbit|orbital|orbiting|flights?",
        "tsq": "mission | launch | rocket | rocketry | orbit | orbital | flight",
        "senses": {"S": ("space", "space and aerospace: rockets, orbit, space missions or flights"),
                   "R": ("religious", "church or religious missions: mission trips, missionaries, rescue missions"),
                   "M": ("mission_statement", "the organization's mission or mission statement"),
                   "L": ("launch", "launching a program, product, initiative, campaign or website"),
                   "A": ("aviation", "aviation: flights, flight school, medical or Honor Flights"),
                   "F": ("figurative", "figurative or other: launch a career, fight or flight, a flight of stairs, "
                                       "a mission to end hunger")},
        "rules": [
            ("S", "rocket launch, into orbit, space mission / flight",
             ["rocket|satellite launch|launches", "into orbit", "launch|launched into space|orbit",
              "space|shuttle|apollo|lunar mission|missions|flight|flights", "model rocket|rockets", "rocketry",
              "orbital"]),
            ("R", "mission trips, foreign / home missions, rescue missions",
             ["mission trip|trips|team|teams|field|fields|work|outreach|board|committee|offering|offerings|society|"
              "church|churches|hospital", "foreign|home|world|overseas|medical|short-term|rescue mission|missions",
              "missions abroad|overseas"]),
            ("M", "our / its mission, mission statement",
             ["our|its|the mission", "exempt|charitable|primary|organization's|organizational|corporate mission",
              "mission statement|statements", "mission is|was to",
              "furtherance|support|pursuit of its|our|the mission", "mission-related", "mission related",
              "fulfill|achieve|advance|accomplish|further|fulfilling|advancing|achieving its|our|the mission"]),
            ("L", "launched a program / initiative / campaign",
             ["launch|launched|launches|launching a|an|the|our|its|their " + _LAUNCHED,
              "launch|launched|launches|launching new " + _LAUNCHED, "program|product|book|website|campaign launch",
              "launch event|party|celebration"]),
            ("A", "flight school / training, Honor / Angel / medical flights",
             ["flight school|training|instruction|instructor|instructors|museum|crew|nurse|nurses|paramedic|"
              "paramedics|simulator|lessons|hours", "honor|angel|life|medical|charter flight|flights",
              "flight attendant|attendants"]),
            ("F", "fight or flight, flight of stairs", ["fight or flight", "flight|flights of stairs"]),
        ],
    },
    "girls_boys": {
        "display": "girls / boys",
        "words": r"girls?|boys?",
        "tsq": "girl | boy",
        "senses": {"G": ("girls", "programs or services for girls"),
                   "B": ("boys", "programs or services for boys"),
                   "K": ("kids", "children in general ('boys and girls' meaning all kids)"),
                   "S": ("girl_scouts", "Girl Scouts (the name)"),
                   "C": ("boys_girls_clubs", "Boys & Girls Clubs (the name)"),
                   "Y": ("boy_scouts", "Boy Scouts / Scouts BSA (the name)"),
                   "N": ("other_name", "another org or group name (Boys Town, Girls Inc, a girls' school's name...)"),
                   "O": ("other", "anything else: an incidental mention")},
        "name_code": "N",
        "rules": [
            ("S", "Girl Scouts", ["girl scout|scouts"]),
            ("Y", "Boy Scouts", ["boy scout|scouts"]),
            ("C", "Boys & Girls Clubs", ["boys and|& girls club|clubs|clubhouse"]),
            ("N", "Boys Town, Girls Inc", ["boys town", "girls inc|incorporated"]),
            ("K", "boys and girls (kids)", ["boys and|& girls", "girls and|& boys"]),
            ("G", "programs for girls, girls' sports, at-risk girls",
             ["programs|program|services|camp|camps|groups|group|mentoring|empowerment|leadership for girls",
              "girls'|girls empowerment|leadership|program|programs|sports|soccer|basketball|softball|volleyball|"
              "camp|group|groups|lacrosse", "at-risk|young|teen|adolescent girls"]),
            ("B", "programs for boys, boys' sports, at-risk boys",
             ["programs|program|services|camp|camps|groups|group|mentoring|leadership for boys",
              "boys'|boys program|programs|sports|soccer|basketball|baseball|camp|group|groups|lacrosse",
              "at-risk|young|teen|adolescent boys"]),
        ],
    },
}
# "space": labeled by classify.py (every org that says it); here for research.sense_defs and topic_count
SPACE = {"O": ("outer", "outer space"), "W": ("for_women", "a place set aside for women or girls"),
         "M": ("for_men", "a place set aside for men or boys"), "F": ("facility", "office, meeting, studio, rental"),
         "P": ("parking", "parking"), "G": ("green", "green or open land"),
         "S": ("personal", "a safe, quiet or personal space"), "X": ("other", "anything else")}

for _t in TOPICS.values():
    _t["word_re"] = re.compile(r"\b(?:" + _t["words"] + r")\b", re.I)
    _t["compiled"] = [(codes, re.compile("|".join(phrase_re(p) for p in ps), re.I)) for codes, _, ps in _t["rules"]]


def prompt(topic: str) -> str:
    t = TOPICS[topic]
    lines = "\n".join(f"{c} = {d}" for c, (_, d) in t["senses"].items())
    return (f'Each organization below uses "{t["display"]}". For the mentions shown, say which senses they use, '
            f"with these codes:\n{lines}\nJudge by the mentions; the name and mission are context. Give every code "
            f"that applies to the mentions shown, e.g. \"{list(t['senses'])[0]}\" or "
            f"\"{''.join(list(t['senses'])[:2])}\".")


# ---------------------------------------------------------------- sync: definitions into the database
SETUP = """
CREATE TABLE IF NOT EXISTS research.sense_defs (topic text, code text, sense text, description text, tsq text,
                                                PRIMARY KEY (topic, code));
CREATE TABLE IF NOT EXISTS research.sense_phrases (topic text, i int, codes text, label text, tsq text,
                                                   PRIMARY KEY (topic, i));
CREATE TABLE IF NOT EXISTS research.org_senses (
    topic text NOT NULL, ein text NOT NULL,
    in_name boolean, in_mission boolean, in_program boolean, in_schedule_o boolean, in_grant_purpose boolean,
    in_contractor_service boolean, n_mentions int, rule_codes text, n_ambiguous int, snippets jsonb,
    model_codes text, model text, labeled_at timestamptz, PRIMARY KEY (topic, ein));
"""


def sync() -> None:
    with db.connect() as c:
        c.execute(SETUP)
        c.execute("DELETE FROM research.sense_defs")
        c.execute("DELETE FROM research.sense_phrases")
        for topic, t in TOPICS.items():
            for code, (sense, desc) in t["senses"].items():
                c.execute("INSERT INTO research.sense_defs VALUES (%s, %s, %s, %s, %s)",
                          (topic, code, sense, desc, t["tsq"]))
            for i, (codes, label, ps) in enumerate(t["rules"], 1):
                tsqs = [q for q in (phrase_tsq(p) for p in ps) if q]
                c.execute("INSERT INTO research.sense_phrases VALUES (%s, %s, %s, %s, %s)",
                          (topic, i, codes, label, " | ".join(tsqs) or None))
        for code, (sense, desc) in SPACE.items():
            c.execute("INSERT INTO research.sense_defs VALUES ('space', %s, %s, %s, 'space | aerospace')",
                      (code, sense, desc))
        c.commit()
        # every phrase must parse as a tsquery
        for topic, i, tsq in c.execute("SELECT topic, i, tsq FROM research.sense_phrases WHERE tsq IS NOT NULL").fetchall():
            c.execute("SELECT to_tsquery('english', %s)", (tsq,))
    print("sense definitions synced")


# ---------------------------------------------------------------- rules: one pass over research.org_text
def _org(row) -> list[tuple]:
    ein, texts = row[0], dict(zip(FIELDS, row[1:]))
    out = []
    for topic, t in TOPICS.items():
        flags, codes, amb, n = {}, set(), [], 0
        for field in FIELDS:
            text = texts[field] or ""
            hits = list(t["word_re"].finditer(text))
            flags[field] = bool(hits)
            if not hits:
                continue
            n += len(hits)
            spans = [(m.start(), m.end(), i, cs) for i, (cs, rx) in enumerate(t["compiled"]) for m in rx.finditer(text)]
            spans.sort(key=lambda x: x[2])                      # the first rule in the list wins
            for h in hits:
                cs = next((cs for s, e, _, cs in spans if s <= h.start() < e), None)
                if cs is None and field == "name" and t.get("name_code"):
                    cs = t["name_code"]
                if cs is not None:
                    codes.update(cs)
                else:
                    amb.append((FIELDS.index(field), h.start(), field, text))
        if not n:
            continue
        snippets = []
        for _, pos, field, text in sorted(amb, key=lambda x: (x[0] if x[0] else 9, x[1])):
            s = " ".join(text[max(0, pos - 100): pos + 110].split())
            if s not in snippets:
                snippets.append(s)
            if len(snippets) == 3:
                break
        out.append((topic, ein, *(flags[f] for f in FIELDS), n, "".join(sorted(codes)), len(amb),
                    json.dumps(snippets)))
    return out


def rules(workers: int = 2) -> None:
    with db.connect() as c:
        c.execute(SETUP)
        c.commit()
        eins = [r[0] for r in c.execute("SELECT ein FROM research.org_text ORDER BY ein").fetchall()]
    print(f"rule pass over {len(eins)} orgs", flush=True)
    t0, done = time.time(), 0
    with mp.Pool(workers) as pool:
        for i in range(0, len(eins), 5000):
            chunk = eins[i:i + 5000]
            with db.connect() as c:
                rows = c.execute("""SELECT ein, name_text, mission_text, program_text, schedule_o_text,
                                           grant_purpose_text, contractor_service_text
                                    FROM research.org_text WHERE ein = ANY(%s)""", (chunk,)).fetchall()
                out = [r for rs in pool.imap_unordered(_org, rows, chunksize=100) for r in rs]
                with c.cursor() as cur:
                    cur.execute("CREATE TEMP TABLE s (LIKE research.org_senses) ON COMMIT DROP")
                    with cur.copy("COPY s (topic, ein, in_name, in_mission, in_program, in_schedule_o, "
                                  "in_grant_purpose, in_contractor_service, n_mentions, rule_codes, n_ambiguous, "
                                  "snippets) FROM STDIN") as cp:
                        for r in out:
                            cp.write_row(r)
                    # keep the model's labels when the leftover mentions haven't changed
                    cur.execute("""INSERT INTO research.org_senses SELECT * FROM s
                                   ON CONFLICT (topic, ein) DO UPDATE SET
                                     in_name = EXCLUDED.in_name, in_mission = EXCLUDED.in_mission,
                                     in_program = EXCLUDED.in_program, in_schedule_o = EXCLUDED.in_schedule_o,
                                     in_grant_purpose = EXCLUDED.in_grant_purpose,
                                     in_contractor_service = EXCLUDED.in_contractor_service,
                                     n_mentions = EXCLUDED.n_mentions, rule_codes = EXCLUDED.rule_codes,
                                     n_ambiguous = EXCLUDED.n_ambiguous,
                                     model_codes = CASE WHEN research.org_senses.snippets = EXCLUDED.snippets
                                                        THEN research.org_senses.model_codes END,
                                     snippets = EXCLUDED.snippets""")
                c.commit()
            done += len(chunk)
            if done % 100000 < 5000 or done == len(eins):
                el = time.time() - t0
                print(f"{done}/{len(eins)} orgs, {el / 60:.0f} min, ~{el / done * (len(eins) - done) / 60:.0f} min "
                      "left", flush=True)


# ---------------------------------------------------------------- label: Haiku on the leftover mentions
def _ask_raw(topic: str, orgs: list[dict]) -> dict[str, str]:
    """The call itself, keeping only this topic's codes."""
    import os
    import urllib.request
    allowed = "".join(TOPICS[topic]["senses"])
    lines = [f"{i}. Name: {o['name']}\n   Mission: {o['mission'] or '(none)'}\n   Mentions: " + " | ".join(o["snippets"])
             for i, o in enumerate(orgs, 1)]
    text = (f"{prompt(topic)}\n\nReply with JSON only, one entry per numbered organization, like "
            f'{{"1": "{allowed[0]}", "2": "{allowed[:2]}"}}.\n\n' + "\n".join(lines))
    body = {"model": MODEL, "messages": [{"role": "user", "content": text}], "temperature": 0, "max_tokens": 1500}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                                          "Content-Type": "application/json"})
    err, txt = None, ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            txt = d["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", txt, re.S)
            if not m:
                raise ValueError("no JSON in the reply")
            got = json.loads(m.group(0))
            return {orgs[int(k) - 1]["ein"]: "".join(ch for ch in allowed if ch in str(v).upper())
                    for k, v in got.items() if str(k).isdigit() and 1 <= int(k) <= len(orgs)}
        except Exception as ex:  # noqa: BLE001 - retried, then the batch is left for the next pass
            err = ex
            time.sleep(2 * (attempt + 1))
    print(f"{topic}: batch of {len(orgs)} failed: {err}; reply began {txt[:120]!r}", flush=True)
    return {}


BUDGET = float(os.environ.get("SENSE_BUDGET", "12"))   # dollars per label pass; stops (unlabeled orgs stay NULL)


def spent() -> float:
    """OpenRouter's running total for this key, in dollars."""
    req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return float(json.load(r)["data"]["usage"])


def label(workers: int = 24, topics: list[str] | None = None, per_call: int = PER_CALL) -> None:
    """One pass over the orgs not yet labeled. The second pass (smaller batches) retries what the first missed."""
    start = spent()
    for topic in topics or TOPICS:
        with db.connect() as c:
            rows = c.execute("""SELECT s.ein, coalesce(o.name, o.name_text), o.mission_text, s.snippets
                                FROM research.org_senses s JOIN research.org_text o USING (ein)
                                WHERE s.topic = %s AND s.n_ambiguous > 0 AND s.model_codes IS NULL
                                  AND (s.topic <> 'launch'   -- "mission" is in nearly every filing; the model is only
                                       OR s.ein IN (SELECT ein FROM research.space_candidates))  -- needed near 'space'""",
                             (topic,)).fetchall()
        print(f"{topic}: {len(rows)} orgs to label", flush=True)
        orgs = [{"ein": e, "name": (n or "").split("\n")[0][:120],
                 "mission": " ".join((m or "").split("\n")[0].split())[:300], "snippets": s} for e, n, m, s in rows]
        for i in range(0, len(orgs), 2000):
            if (cost := spent() - start) > BUDGET:
                print(f"{topic}: stopping, ${cost:.2f} spent this pass (budget ${BUDGET:.0f})", flush=True)
                return
            part = orgs[i:i + 2000]
            batches = [part[j:j + per_call] for j in range(0, len(part), per_call)]
            with ThreadPoolExecutor(workers) as ex:
                results = list(ex.map(lambda b: _ask_raw(topic, b), batches))
            with db.connect() as c:
                with c.cursor() as cur:
                    cur.executemany("""UPDATE research.org_senses SET model_codes = %s, model = %s, labeled_at = now()
                                       WHERE topic = %s AND ein = %s""",
                                    [(v or "-", MODEL, topic, e) for res in results for e, v in res.items()])
                c.commit()
            if (i // 2000) % 10 == 0 or i + 2000 >= len(orgs):
                print(f"{topic}: {min(i + 2000, len(orgs))}/{len(orgs)}, ${spent() - start:.2f} so far", flush=True)


# ---------------------------------------------------------------- test: hand-labeled cases
def test() -> None:
    from sense_tests import CASES
    rows = []
    for topic, cases in CASES.items():
        orgs = [{"ein": str(i), "name": n, "mission": m, "snippets": [s]} for i, (n, m, s, _) in enumerate(cases)]
        got = {}
        for j in range(0, len(orgs), PER_CALL):
            got.update(_ask_raw(topic, orgs[j:j + PER_CALL]))
        exact = sum(set(got.get(str(i), "")) == set(want) for i, (*_, want) in enumerate(cases))
        lenient = sum(set(want) <= set(got.get(str(i), "")) for i, (*_, want) in enumerate(cases))
        misses = [(n, s, want, got.get(str(i))) for i, (n, m, s, want) in enumerate(cases)
                  if set(got.get(str(i), "")) != set(want)]
        rows.append((topic, len(cases), exact, lenient, json.dumps(misses)))
        print(f"{topic}: exact {exact}/{len(cases)}, right sense among its answers {lenient}/{len(cases)}", flush=True)
        for n, s, want, g in misses:
            print(f"   want {want} got {g}: {n} | {s}", flush=True)
    with db.connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS research.sense_test_results (topic text PRIMARY KEY, n int, exact int,
                     lenient int, misses jsonb, model text, run_at timestamptz DEFAULT now())""")
        for r in rows:
            c.execute("""INSERT INTO research.sense_test_results (topic, n, exact, lenient, misses, model)
                         VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (topic) DO UPDATE SET n = EXCLUDED.n,
                         exact = EXCLUDED.exact, lenient = EXCLUDED.lenient, misses = EXCLUDED.misses,
                         model = EXCLUDED.model, run_at = now()""", (*r, MODEL))
        c.commit()


# ---------------------------------------------------------------- falsehits: men by substring vs by whole word
def falsehits(sample_pct: float = 1.0) -> None:
    # (word, substring searched, the whole word with its plural / possessive)
    words = (("men", "men", r"\bmen(?:'s|s)?\b"), ("male", "male", r"\bmales?\b"), ("boys", "boy", r"\bboys?'?\b"))
    with db.connect() as c:
        c.execute("SET statement_timeout = '30min'")
        rows = c.execute(f"SELECT ein, text FROM research.org_text TABLESAMPLE SYSTEM ({sample_pct}) "
                         "REPEATABLE (7)").fetchall()
        res = []
        for w, frag, whole_re in words:
            sub = [t for _, t in rows if frag in (t or "").lower()]
            whole = [t for t in sub if re.search(whole_re, t, re.I)]
            # what the substring hits really were, when not the whole word
            fakes: dict[str, int] = {}
            for t in sub:
                for m in re.finditer(rf"\w*{frag}\w*", t.lower()):
                    if not re.fullmatch(whole_re.replace("\\b", ""), m.group(0)):
                        fakes[m.group(0)] = fakes.get(m.group(0), 0) + 1
            top = sorted(fakes.items(), key=lambda x: -x[1])[:8]
            res.append((w, len(rows), len(sub), len(whole), json.dumps(top)))
            print(f"{w}: {len(sub)} orgs by substring, {len(whole)} by whole word; false-hit orgs "
                  f"{len(sub) - len(whole)} ({100 * (len(sub) - len(whole)) / max(len(sub), 1):.0f}%); "
                  f"common false hits {top}", flush=True)
        c.execute("""CREATE TABLE IF NOT EXISTS research.sense_falsehits (word text PRIMARY KEY, sample_orgs int,
                     substring_orgs int, wholeword_orgs int, top_false jsonb, run_at timestamptz DEFAULT now())""")
        for r in res:
            c.execute("""INSERT INTO research.sense_falsehits (word, sample_orgs, substring_orgs, wholeword_orgs, top_false)
                         VALUES (%s, %s, %s, %s, %s) ON CONFLICT (word) DO UPDATE SET sample_orgs = EXCLUDED.sample_orgs,
                         substring_orgs = EXCLUDED.substring_orgs, wholeword_orgs = EXCLUDED.wholeword_orgs,
                         top_false = EXCLUDED.top_false, run_at = now()""", r)
        c.commit()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sync":
        sync()
    elif cmd == "rules":
        rules(int(sys.argv[2]) if len(sys.argv) > 2 else 2)
    elif cmd == "label":                       # label [--small] [topic ...]
        small = "--small" in sys.argv
        label(topics=[a for a in sys.argv[2:] if a != "--small"] or None, per_call=3 if small else PER_CALL)
    elif cmd == "test":
        test()
    elif cmd == "falsehits":
        falsehits(float(sys.argv[2]) if len(sys.argv) > 2 else 1.0)
    else:
        print(__doc__)
