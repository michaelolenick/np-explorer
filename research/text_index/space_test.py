"""Hand-labeled check of the "space" senses (owner, 2026-10-28). Run from the np-explorer checkout:
.venv/bin/python research/text_index/space_test.py"""
import sys
sys.path.insert(0, "research/text_index")
sys.path.insert(0, ".")
import classify as C  # noqa: E402

CASES = [  # (name, mission, snippet, the codes that must be there)
    ("Hope House", "Shelter for survivors of abuse", "provides a safe space for women and children to heal", "W"),
    ("Quiet Minds", "Mental health support for teens", "a quiet space where students can decompress between classes", "S"),
    ("Room of Her Own Foundation", "Supports women writers", "every woman deserves a space of her own to create", "W"),
    ("Brave Voices", "Youth dialogue program", "we hold brave space for difficult conversations", "S"),
    ("Downtown Arts Collective", "Affordable studios for artists", "leases office space and studio space to local artists", "F"),
    ("Riverside Land Trust", "Preserves farmland", "protected 400 acres of open space and green space", "G"),
    ("Grace Church", "Worship and fellowship", "renting space to community groups for meetings", "F"),
    ("Healing Circle", "Grief support", "creating space to grieve and space to grow", "S"),
    ("Main Street Coworking", "Small business incubator", "shared workspace and meeting space for entrepreneurs", "F"),
    ("Tech For Good", "Social enterprise accelerator", "leader in the social innovation space", "X"),
    ("Parking Authority Friends", "Downtown revitalization", "added 120 parking spaces near the library", "P"),
    ("Machinists Local 44", "Labor union", "International Association of Machinists and Aerospace Workers", "X"),
    ("Men's Shed Association", "Reducing isolation among older men", "a space where men can gather, build and talk", "M"),
    ("Brotherhood Barbershop Talks", "Mental health for Black men", "a safe space for men to talk about mental health", "M"),
    ("Girls Inc of the Valley", "Inspiring girls", "a girls-only space where girls can lead and learn", "W"),
    ("Sky Watchers Club", "Amateur astronomy education", "public nights to view planets and deep space objects", "O"),
    ("Young Rocketeers", "STEM club", "students build model rockets and learn about space exploration", "O"),
    ("Mars Society Chapter", "Advocates human exploration of Mars", "supporting human settlement of space", "O"),
    ("Girls in STEM", "Science camps for girls", "a week at Space Camp and a visit to the Kennedy Space Center", "O"),
    ("Space Coast Heritage", "Preserves launch history", "museum of the Apollo era and the space race", "O"),
    ("Women in Aerospace Foundation", "Advancing women in aerospace", "scholarships for women in aerospace and space careers", "O"),
    ("Science Center", "Hands-on science museum", "new planetarium show on space; office space leased to partner", "OF"),
]
orgs = [{"ein": str(i), "name": n, "mission": m, "snippets": [s]} for i, (n, m, s, _) in enumerate(CASES)]
for model in (C.MODEL, C.REFERENCE):
    got = {}
    for i in range(0, len(orgs), C.PER_CALL):
        got.update(C._ask(model, C.TOPICS["space"]["prompt"], orgs[i:i + C.PER_CALL]))
    # right: every expected code present, and O / W / M only where expected
    ok = [all(c in got.get(str(i), "") for c in want) and
          all((c in got.get(str(i), "")) == (c in want) for c in "OWM") for i, (*_, want) in enumerate(CASES)]
    print(f"{model}: {sum(ok)}/{len(CASES)} right")
    for i, (n, m, s, want) in enumerate(CASES):
        if not ok[i]:
            print(f"   wrong: {n} | {s} | want {want}, said {got.get(str(i))}")
