import re

from app import suppress


def test_redact_removes_name_and_address(monkeypatch):
    monkeypatch.setattr(suppress, "pattern", lambda: re.compile("JUDGE MARY CHICCHELLY|129 TEAKWOOD LANE NE", re.I))
    out = suppress.redact(b"<PersonNm>Judge Mary Chicchelly</PersonNm><AddressLine1Txt>129 TEAKWOOD LANE NE</AddressLine1Txt><X>Lisa Chicchelly</X>").decode()
    assert "CHICCHELLY" not in out.split("<X>")[0].upper() and "TEAKWOOD" not in out.upper()
    assert "Lisa Chicchelly" in out


def test_redact_without_rules_is_unchanged(monkeypatch):
    monkeypatch.setattr(suppress, "pattern", lambda: None)
    assert suppress.redact(b"abc") == b"abc"
