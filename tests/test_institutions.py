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
