"""Address and name normalization for matching vendors to filing organizations (app/address.py)."""

from collections import Counter

from app import address as A


def test_funston_variants_are_one_address():
    keys = [A.key(s, z) for s, z in [("300 FUNSTON AVE", "94118"), ("300 Funston Avenue", "941182116"),
                                     ("300 Funson Avenue", "94118"), ("300 funstun ave", "94118-2116")]]
    assert all(A.same_address(keys[0], k) for k in keys)


def test_different_number_zip_or_street_is_not_the_same():
    a = A.key("300 Funston Ave", "94118")
    assert not A.same_address(a, A.key("301 Funston Ave", "94118"))
    assert not A.same_address(a, A.key("300 Funston Ave", "94119"))
    assert not A.same_address(a, A.key("300 Fulton St", "94118"))
    assert not A.same_address(A.key("10 5th Ave", "10011"), A.key("10 6th Ave", "10011"))


def test_units_directions_and_po_boxes():
    assert A.key("1127 Clements St Suite 4", "94118") == ("94118", "1127", "clements")
    assert A.key("330 W Pender Street", "V6B 1T1") is None            # no US zip
    assert A.key("PO Box 1234", "10001") == ("10001", "box 1234", "po box")
    assert A.key("", "94118") is None and A.key("Funston Ave", "94118") is None


def test_name_core():
    assert A.name_core("The Internet Archive, Inc.") == "internet archive"
    assert A.name_core("Smith & Jones LLC") == "smith and jones"
    assert A.name_core("Internet Archive US") != A.name_core("Internet Archive")


def test_collapse_keeps_the_most_common_spelling_and_every_original():
    rows = [("300 FUNSTON AVENUE", "SAN FRANCISCO", "CA", "94118")] * 5 + \
           [("300 Funston Avenue", "San Francisco", "CA", "941182116")] * 2 + \
           [("300 funstun ave", "SAN FRANCISCO", "CA", "94118"), ("1127 Clements St", "San Francisco", "CA", "94118")]
    counts = Counter(rows)
    groups = A.collapse(list(counts), counts)
    assert len(groups) == 2
    assert groups[0]["shown"] == ("300 FUNSTON AVENUE", "SAN FRANCISCO", "CA", "94118")
    assert len(groups[0]["variants"]) == 3


def test_unit_numbers_and_misspelled_street_types():
    assert A.key("515 Post Oak Blvd 1000", "77027") == A.key("515 POST OAK BLVD STE 1000", "77027-9482")
    assert A.same_address(A.key("50 F Street NW No 1075", "20001"), A.key("50 F STREET NW SUITE 1075", "20001"))
    assert A.key("5700 WAYNE AVENYE", "19144") == A.key("5700 Wayne Ave", "19144")
    assert A.key("350 SO OAK AVE", "95361") == A.key("350 S OAK AVE", "95361")


def test_care_of_lines():
    assert A.is_care_of("CO HARRISON & HELD LLP") and A.is_care_of("% Bank of America") and A.is_care_of("c/o Smith")
    assert not A.is_care_of("Collaborative Inc") and not A.is_care_of("Cooper Union")
