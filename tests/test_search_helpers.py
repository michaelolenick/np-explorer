"""Search helpers that need no database."""

from app.main import _EIN, _ORG_SUFFIX
from app.queries import sound_query


def test_sound_query_skips_numbers():
    # An EIN or number has no sound code; an empty term made an invalid tsquery (a 500).
    assert sound_query(["86", "1821217"]) == ""
    assert sound_query(["redm", "1821217"]) == "r350"


def test_ein_pattern():
    assert _EIN.match("86-1821217") and _EIN.match(" 861821217 ")
    assert not _EIN.match("8618212") and not _EIN.match("redm")


def test_org_suffix():
    assert _ORG_SUFFIX.sub("", "redm inc") == "redm"
    assert _ORG_SUFFIX.sub("", "ford foundation") == "ford"
