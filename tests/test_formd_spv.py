"""Form D families: SPVs told apart from main funds, the family stem, and the company an SPV is for."""

from app import corporate as C


def test_spv_classification():
    assert C.is_spv("Geek Ventures Competera SPV, a series of Decile SPV, LLC")
    assert C.is_spv("Acme Deal I, a series of Roll Up Vehicles, LP")
    assert not C.is_spv("Geek Ventures Fund I, LP") and not C.is_spv("Sequoia Capital Fund XVIII")


def test_family_and_company():
    assert C.family_stem("Geek Ventures Fund I, LP") == "geek ventures"
    assert C.family_stem("Geek Ventures Fund II, LP") == "geek ventures"
    by_first = {"geek": ["geek ventures"]}
    assert C.family_and_company("Geek Ventures Competera SPV, a series of Decile SPV, LLC", by_first) == \
        ("geek ventures", "Competera")
    assert C.family_and_company("Geek Ventures ShapesXR Seed SPV, a series of Decile SPV, LLC", by_first) == \
        ("geek ventures", "ShapesXR")
    assert C.family_and_company("Geek Ventures CTR SPV II, a series of Decile SPV, LLC", by_first)[1] == "CTR"


def test_deal_codes_are_not_companies():
    assert C.family_and_company("SU-0709 Fund I, a series of Hustle Fund Angel Squad, LP", {})[1] is None
    assert C.family_and_company("CO-0801 Fund II, a series of Hustle Fund Angel Squad, LP", {})[1] is None
