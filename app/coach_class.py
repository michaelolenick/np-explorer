"""Sports coaches from job titles, deterministically (no AI).

Inputs: a title as published (payroll or Form 990) and, for payroll, the department. Outputs
whether it is a sports coach, the sport, the role (head, assistant, other) and the reason. The
rules are written out in docs/coach-classification.md; keep the two in step.

- A title is a coach title when it has the word "coach" (job codes like "SUCoachPT" are split
  first: "SU Coach PT").
- It is a sports coach unless the title says another kind of coach (success, academic, career,
  health, enrollment, instructional ...) or means a bus ("Coaches/Drivers"). A sport word in the
  title, or a department that says athletics or names a sport, keeps it a sports coach.
- The sport comes from the title first, then the department. No sport word: "Unclear".
  Basketball is split into men's and women's only when the text says which.
- Role: associate or assistant head coach is assistant; head (or co-head) is head; assistant,
  associate and coordinators are assistant; anything else is other.
"""

from __future__ import annotations

import re

UNCLEAR = "Unclear"

# (sport, pattern), first match wins. Patterns run on lowercased text with job codes split.
SPORTS = [
    ("Strength and conditioning", r"\b(strength|conditioning|sports? performance|performance enhancement|s&c)\b"),
    ("Football", r"\b(football|fb|quarterbacks?|qbs?|linebackers?|wide receivers?|running backs?|tight ends?|"
                 r"offensive line|defensive line|special teams|defensive backs|offensive coordinator|defensive coordinator)\b"),
    ("Basketball", r"\b(basketball|mbb|wbb|bball|b-ball)\b"),   # split by gender below
    ("Baseball", r"\b(baseball|coach pitch)\b"),
    ("Softball", r"\bsoftball\b"),
    ("Volleyball", r"\b(volleyball|vball|v-ball)\b"),
    ("Soccer", r"\bsoccer\b"),
    ("Track and field / cross country", r"\b(track|cross[ -]?country|x[ -]?country|xc|t ?& ?f|t&fld|field events|"
                                        r"distance running|sprints|jumps|throws|pole vault)\b"),
    ("Swimming and diving", r"\b(swim(ming)?|diving|dive)\b"),
    ("Wrestling", r"\bwrestl(ing|e)\b"),
    ("Gymnastics", r"\bgymnastics?\b"),
    ("Golf", r"\bgolf\b"),
    ("Tennis", r"\btennis\b"),
    ("Field hockey", r"\bfield hockey\b"),
    ("Ice hockey", r"\b(ice hockey|hockey)\b"),
    ("Lacrosse", r"\b(lacrosse|lax)\b"),
    ("Rowing", r"\b(rowing|crew)\b"),
    ("Water polo", r"\bwater polo\b"),
    ("Beach volleyball", r"\bbeach volleyball\b"),
    ("Cheer and dance", r"\b(cheer(leading)?|spirit squad|dance team|pom)\b"),
    ("Fencing", r"\bfencing\b"),
    ("Rifle", r"\brifle\b"),
    ("Skiing", r"\bski(ing)?\b"),
    ("Equestrian", r"\b(equestrian|riding)\b"),
    ("Bowling", r"\bbowling\b"),
    ("Rugby", r"\brugby\b"),
    ("Sailing", r"\bsailing\b"),
    ("Triathlon", r"\btriathlon\b"),
    ("Esports", r"\be-?sports\b"),
    ("Squash", r"\bsquash\b"),
    ("Rodeo", r"\brodeo\b"),
]
_SPORTS = [(s, re.compile(p)) for s, p in SPORTS]
_BEACH = re.compile(SPORTS[[s for s, _ in SPORTS].index("Beach volleyball")][1])
MEN = re.compile(r"\b(men'?s?|mens|male|boys?|mbb)\b")
WOMEN = re.compile(r"\b(women'?s?|womens|female|ladies|lady|girls?|wbb|w)\b")

COACH = re.compile(r"\bcoach(es|ing)?\b")
# Other kinds of coach, and coaches that are buses.
NOT_SPORT = re.compile(
    r"\b(success|academic|career|life|wellness|well-?being|health|writing|reading|literacy|math|financial|peer|"
    r"executive|nurse|nursing|retention|completion|enrollment|instructional|instruction|learning|leadership|"
    r"transition|recruitment|readiness|mentor|educational|education|teacher|teaching|professional|faculty|"
    r"parent|family|recovery|employment|job|business|technology|data|digital|innovation|lactation|doula|"
    r"housing|navigator|benefits|persistence|strengths|scholars|trio|talent search|college connect|"
    r"non-?credit|early childhood|skills|language|music|vocal|voice|debate|speech|drivers?|driving|bus|"
    r"motor ?coach|transportation|support)\b")
ATHLETIC = re.compile(r"\b(athletic|athletics|sports?|varsity|intercollegiate|team)\b")

HEAD_ASSISTANT = re.compile(r"\b(assoc(iate)?|asst|assistant|ast|assist) ?\.? ?head\b")
HEAD = re.compile(r"\b(co-?)?head\b")
ASSISTANT = re.compile(r"\b(assistant|asst|assist|ast|associate|assoc|coordinator|offensive|defensive|"
                       r"special teams|position|graduate assistant|ga)\b")
COORDINATING = re.compile(r"\b(director of coach|coaching director|coaches? rep|representative|liaison|liason|"
                          r"coaching coord|coaches coord|coach coord|dir of coach|coaching dir|coaches dir)")


def split_codes(text: str | None) -> str:
    """'SUCoachPT' -> 'su coach pt', 'CCAstCoachMa' -> 'cc ast coach ma'; then lowercase."""
    t = text or ""
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    t = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", t)
    t = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", t)
    return re.sub(r"\s+", " ", t.replace("&", " & ").replace("/", " / ")).strip().lower()


def sport_of(text: str) -> str | None:
    if _BEACH.search(text):
        return "Beach volleyball"
    for s, rx in _SPORTS:
        if rx.search(text):
            if s == "Basketball":
                men, women = bool(MEN.search(text)), bool(WOMEN.search(text))
                if men and not women:
                    return "Men's basketball"
                if women and not men:
                    return "Women's basketball"
                return "Basketball (men's or women's not stated)"
            return s
    return None


def role_of(title: str) -> str:
    if HEAD_ASSISTANT.search(title):
        return "assistant"
    if COORDINATING.search(title):
        return "other"
    if HEAD.search(title):
        return "head"
    if ASSISTANT.search(title):
        return "assistant"
    return "other"


def classify(title: str | None, department: str | None = None) -> tuple[bool, str | None, str | None, str]:
    """(is_sports_coach, sport, role, reason). sport is "Unclear" when no sport word appears."""
    t, d = split_codes(title), split_codes(department)
    if not COACH.search(t):
        return False, None, None, "title does not say coach"
    sport_t = sport_of(t)
    sport_d = sport_of(d) if d else None
    athletic_dept = bool(d and (ATHLETIC.search(d) or sport_d))
    other = NOT_SPORT.search(t)
    if other and not sport_t:
        return False, None, None, f"another kind of coach ({other.group(0)})"
    role = role_of(t)
    if sport_t:
        return True, sport_t, role, "sport named in the title"
    if sport_d:
        return True, sport_d, role, "sport named in the department"
    return True, UNCLEAR, role, "coach title with no sport named" + (" (athletics department)" if athletic_dept else "")
