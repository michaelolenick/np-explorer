"""Highest-paid contractors in plain-English results: newest year first, highest paid within each year."""

from app import ask


def _years_then_pay(rows):
    keys = [(-(r["tax_year"] or 0), -float(r["value"] or 0)) for r in rows]
    return keys == sorted(keys)


def test_one_organization():
    res = ask.run_page(ask.validate("vendors", {"org": "Harvard University"}), 1)
    assert res["kind"] == "vendors" and res["rows"], res.get("kind")
    assert _years_then_pay(res["rows"])


def test_all_organizations():
    res = ask.run_page(ask.validate("vendors", {}), 1)
    assert res["kind"] == "board" and res["rows"]
    assert _years_then_pay(res["rows"])
