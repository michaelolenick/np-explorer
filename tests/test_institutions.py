import pytest

from app.institutions import is_institution

GIVEN = {"william", "ben", "gail", "wade", "kim", "john", "james", "dennie"}


@pytest.mark.parametrize("name", [
    "bank of america", "bank of america n a", "wells fargo bank na", "keybank n a", "us bank na",
    "bny mellon n a", "jp morgan chase bank na", "hershey trust company", "reliance trust company",
    "first presbyterian church edgerton", "frost bank trustee", "truist bank", "heritage trust",
    "cape cod foundation", "lynx consulting inc", "fremont unified dist teachers assn",
])
def test_institutions(name):
    assert is_institution(name, GIVEN)


@pytest.mark.parametrize("name", [
    "william church", "ben church", "gail church", "wade alliance", "kim na", "john n a smith",
    "renee mauborgne", "michael olenick", "james banks",
])
def test_people(name):
    assert not is_institution(name, GIVEN)


@pytest.mark.parametrize("name", [
    "noel memorial methodist church", "first hawaiian bank", "first mid illinois bank trust",
    "state st bank trust c", "brown investment advisory and trust", "alta trust",
])
def test_institutions_found_by_refined_rule(name):
    assert is_institution(name, GIVEN | {"noel", "brown"} - {"alta"})


@pytest.mark.parametrize("raw, key", [
    ("bank of america", "bank of america"),
    ("bank of america n a", "bank of america"),
    ("bank of america na", "bank of america"),
    ("bank of america n a trustee", "bank of america"),
    ("the northern trust company", "northern trust"),
    ("wells fargo bank n a ttee", "wells fargo"),
    ("us bank former", "us bank"),
    ("trustee", "trustee"),
])
def test_institution_key(raw, key):
    from app.institutions import institution_key
    assert institution_key(raw) == key


@pytest.mark.parametrize("raw, key", [
    ("jp morgan chase bank na", "jpmorgan chase"),
    ("j p morgan chase bank n a", "jpmorgan chase"),
    ("jpmorgan chase bank na", "jpmorgan chase"),
    ("u s bank n a", "us bank"),
    ("the bank of new york mellon", "bny mellon"),
])
def test_institution_key_spellings(raw, key):
    from app.institutions import institution_key
    assert institution_key(raw) == key


@pytest.mark.parametrize("raw, key", [
    ("wells fargo", "wells fargo"),
    ("wells fargo bank n a", "wells fargo"),
    ("wells fargo bank texas na", "wells fargo"),
    ("wells fargo advisors", "wells fargo"),
    ("wells fargo bank na 94 3080771", "wells fargo"),
    ("pnc bank n a", "pnc bank"),
    ("jp morgan chase bank na", "jpmorgan chase"),
    ("gary worsham wells fargo", "gary worsham wells fargo"),   # a person c/o the bank: not merged
    ("wellsford trust company", "wellsford trust company"),
])
def test_institution_brands(raw, key):
    from app.institutions import institution_key
    assert institution_key(raw) == key


CARE_GIVEN = GIVEN | {"kristin", "sandra", "juan", "greg", "dominic", "keith", "mike", "robert", "ammon", "denise",
                      "merrill", "dean", "morgan", "chase", "david"}


@pytest.mark.parametrize("raw, person", [
    ("kristin cupillari co wells fargo", "kristin cupillari"),
    ("sandra j cupillari co wells fargo", "sandra j cupillari"),
    ("john k tran wells fargo bank", "john k tran"),
    ("juan austin wells fargo foundation", "juan austin"),
    ("attn greg chapmanwells fargo", "greg chapman"),
    ("wells fargokeith hatcher", "keith hatcher"),
    ("wells fargo bank dominic clemente", "dominic clemente"),
    ("mike king market pres wells fargo", "mike king"),
    ("ammon g dunton co wells fargo jr", "ammon g dunton jr"),
    ("denise wyatt wells fargo", "denise wyatt"),
])
def test_care_of_person(raw, person):
    from app.institutions import care_of_person
    got = care_of_person(raw, CARE_GIVEN)
    assert got and got[0] == person and got[1] == "wells fargo"


@pytest.mark.parametrize("raw", [
    "wells fargo bank n a", "wells fargo bank texas na", "wells fargo bank private bank", "wells fargo co denver",
    "wells fargo trust department", "wells fargo", "bank of america n a", "wells fargo institutional trust",
    "bank of america merrill lynch", "morgan stanley dean witter", "jp morgan chase comp", "jp morgan chase trustee",
    "jp morgan chase bankna", "comerica bank wm charitable dept", "morgan keeganregions bank",
])
def test_not_care_of(raw):
    from app.institutions import care_of_person
    assert care_of_person(raw, CARE_GIVEN) is None


def test_care_of_cleanup():
    from app.institutions import care_of_person
    assert care_of_person("bank of america tr david yarter", CARE_GIVEN)[0] == "david yarter"
    assert care_of_person("james c rootes 1100 jp morgan cha", CARE_GIVEN | {"james"})[0] == "james c rootes"


@pytest.mark.parametrize("raw", ["wells fargo bank montana n a", "wells fargo bank na see stmt",
                                 "wells fargo bank see schedule o", "wells fargo mac n9310 060"])
def test_care_of_not_people(raw):
    from app.institutions import care_of_person
    assert care_of_person(raw, CARE_GIVEN | {"montana", "see", "mac"}) is None


def test_care_of_glued_co():
    from app.institutions import care_of_person
    assert care_of_person("robert schoolfieldco wells fargo bk", CARE_GIVEN)[0] == "robert schoolfield"
    assert care_of_person("william allenco wells fargo", CARE_GIVEN | {"william"})[0] == "william allen"
