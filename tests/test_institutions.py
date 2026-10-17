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
