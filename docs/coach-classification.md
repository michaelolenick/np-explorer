# Coach classification

How the coaches board and the athletics board decide who is a sports coach, which sport, and which
role. The code is `app/coach_class.py`; the results are stored per distinct title in `coach_titles`
(built by `load.py colleges --only coaches`). Keep this file and the code in step.

No AI, and no guessing. The rules read only the words the publisher wrote:

- for payroll rows, the job title and the department, as published by the state or university;
- for Form 990 rows, the title in Part VII or Schedule J.

## Step 1: is it a coach title?

The title must contain the word "coach" ("coaches", "coaching" too). Job codes written without
spaces are split first: "SUCoachPT" becomes "SU Coach PT" and "CCAstCoachMa" becomes "CC Ast Coach Ma".

## Step 2: is it a sports coach?

A coach title is **not** a sports coach when the title names another kind of coach and no sport. These
words mark another kind of coach: success, academic, career, life, wellness, health, writing, reading,
literacy, math, financial, peer, executive, nurse, retention, completion, enrollment, instructional,
learning, leadership, transition, recruitment, readiness, mentor, educational, teacher, professional,
faculty, parent, family, recovery, employment, job, business, technology, data, digital, innovation,
lactation, doula, housing, navigator, benefits, persistence, strengths, scholars, TRIO, talent search,
non-credit, early childhood, skills, language, music, vocal, voice, debate, speech, support. Driver,
driving, bus, motor coach and transportation mark a coach that is a bus ("Coaches/Drivers").

A sport word in the title always keeps the row a sports coach ("Academic Coach" is not a sports coach;
"Head Football Coach" is).

## Step 3: sport

The first matching sport wins. The title is read first, then the department.

| Sport | Words |
|---|---|
| Strength and conditioning | strength, conditioning, sport(s) performance, performance enhancement |
| Football | football; position and staff words used only in football: quarterbacks, linebackers, wide receivers, running backs, tight ends, offensive line, defensive line, special teams, defensive backs, offensive coordinator, defensive coordinator |
| Men's basketball / Women's basketball | basketball (or MBB, WBB) with men's / women's (boys, girls, ladies, lady, W) |
| Basketball (men's or women's not stated) | basketball with neither, or both |
| Baseball | baseball, coach pitch |
| Softball | softball |
| Volleyball / Beach volleyball | volleyball; beach volleyball |
| Soccer | soccer |
| Track and field / cross country | track, cross country, XC, T&F, field events, distance running, sprints, jumps, throws, pole vault |
| Swimming and diving | swim, swimming, diving |
| Wrestling, Gymnastics, Golf, Tennis | the sport's name |
| Field hockey / Ice hockey | field hockey; hockey or ice hockey |
| Lacrosse, Rowing (crew), Water polo, Cheer and dance (cheer, spirit squad, dance team), Fencing, Rifle, Skiing, Equestrian, Bowling, Rugby, Sailing, Triathlon, Esports, Squash, Rodeo | the sport's name |

No sport word in the title or the department: **Unclear**. We don't guess from the employer's name or
from pay. "Pitching coach" and "hitting coach" stay Unclear because they could be baseball or softball.

## Step 4: role

| Role | Rule (first that applies) |
|---|---|
| assistant | associate head coach, assistant head coach |
| other | director of coaching, coaching director or coordinator, coaches' representative, liaison |
| head | head or co-head |
| assistant | assistant, asst, assist, ast, associate, assoc, coordinator, offensive, defensive, special teams, position, graduate assistant |
| other | anything else ("Coach", "SUCoach4", "Volunteer Coach") |

## Counts (built 2026-10-18)

| Source | Distinct titles classified as sports coaches | Of which sport Unclear |
|---|---:|---:|
| Public payroll (title and department pairs) | 2,494 | 496 |
| Form 990 titles | 4,579 | 3,716 |

Most 990 coach titles are youth and club sports officers ("Director of Coaching", "Coaches Rep"), which
name no sport, so Unclear is common there. On the coaches board, see the Sport filter for row counts per
sport and source type.

## Combining pay from two payers

On the coaches board, one person can be paid by a public university (payroll) and by its athletic or
booster foundation (990). The two are combined into one row only when:

1. the payroll person is linked to the person's 990 records with an **EXACT** link (the same normalized
   full name at the same institution or one of its affiliated nonprofits; see `loader/colleges.py`);
2. the 990 row is from the institution itself or one of its affiliated nonprofits (`college_orgs`);
3. the payroll fiscal year equals the 990 tax year.

"From nonprofit (990)" is reportable pay from the organization plus other compensation. Pay from
related organizations on the 990 can include the university's own pay, so it is shown separately and
never added. When a coach appears on more than one 990 for a year, only the filing with the largest
total is used. FUZZY links are never combined: those rows are shown separately with the tag and the
evidence.

## Changing the rules

Edit `app/coach_class.py`, add a case to `tests/test_coach_class.py`, update this file, then run
`load.py colleges --only coaches,schools` and `load.py boards --only uni-athletics,coaches,schools`.
