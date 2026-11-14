"""Companies House officers and profiles (loader/uk_officers.py, loader/uk_officers_xref.py, app/uk_companies.py; owner, 2026-11-14)."""

import io
import time
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app import uk_companies as app_ukco
from loader import uk_officers as uo

ITEM = {"name": "AITCHISON, Carolyn Jane", "officer_role": "director", "appointed_on": "2022-09-28",
        "country_of_residence": "England", "nationality": "British", "occupation": "Chief Executive",
        "date_of_birth": {"month": 9, "year": 1963, "day": 14},
        "address": {"address_line_1": "21 Palmer Street", "premises": "The Asticus Building", "country": "England", "postal_code": "SW1H 0AD"},
        "links": {"self": "/company/00006400/appointments/uIWKE-2_mahBqQIudbalntCDVuU",
                  "officer": {"appointments": "/officers/TeP5WkFAJ0KnDSJtZWfG8HuQGWo/appointments"}}}


def test_person_name():
    assert uo.person_name("AITCHISON, Carolyn Jane", False) == ("Carolyn Jane Aitchison", "carolyn jane aitchison")
    assert uo.person_name("MCDONALD-SMITH, anna", False)[0] == "anna McDonald-Smith" and uo.person_name("O'BRIEN, Sean", False)[0] == "Sean O'Brien"
    assert uo.person_name("O'BRIEN, Mr Sean", False)[1] == "sean obrien"
    assert uo.person_name("SELDON, Anthony Francis, Sir", False) == ("Sir Anthony Francis Seldon", "anthony francis seldon")
    assert uo.person_name("ENIOLA, Fabiyi, Rev'D Canon", False)[1] == "fabiyi eniola"
    assert uo.person_name("ACME SECRETARIES LIMITED", True) == ("ACME SECRETARIES LIMITED", "acme secretaries limited")


def test_officer_row_keeps_no_day_of_birth_or_street():
    r = dict(zip(uo.OFFICER_COLS, uo.officer_row("00006400", ITEM)))
    assert r["officer_id"] == "TeP5WkFAJ0KnDSJtZWfG8HuQGWo" and r["appt_key"] == "uIWKE-2_mahBqQIudbalntCDVuU"
    assert r["birth_year"] == 1963 and r["birth_month"] == 9 and r["addr_country"] == "England" and r["addr_area"] == "SW"
    flat = " ".join(str(v) for v in r.values())
    assert "Palmer" not in flat and "Asticus" not in flat and "SW1H" not in flat
    assert "birth_day" not in r and 14 not in r.values()
    assert r["corporate"] is False and r["resigned_on"] is None


def test_profile_row():
    js = {"type": "ltd", "jurisdiction": "england-wales", "has_charges": False, "can_file": True,
          "accounts": {"next_due": "2027-05-31", "overdue": False, "last_accounts": {"made_up_to": "2025-08-31"}},
          "confirmation_statement": {"next_due": "2027-02-15"}, "sic_codes": ["85310"],
          "previous_company_names": [{"name": "OLD LTD", "ceased_on": "2003-09-01"}]}
    r = dict(zip(uo.PROFILE_COLS, uo.profile_row("00006400", js, (11, 3, 14))))
    assert r["accounts_next_due"] == "2027-05-31" and r["jurisdiction"] == "england-wales" and r["officers_total"] == 14 and "OLD LTD" in r["previous_names"]


def test_limiter_holds_the_window():
    lim = uo.Limiter(limit=3, window=0.6)
    t0 = time.time()
    for _ in range(3):
        lim.acquire()
    assert time.time() - t0 < 0.3
    lim.acquire()                      # the fourth waits for the first to leave the window
    assert time.time() - t0 >= 0.55
    assert lim.requests == 4


def test_limiter_block_honours_retry_after():
    lim = uo.Limiter(limit=10, window=5)
    lim.block(0.4)
    t0 = time.time()
    lim.acquire()
    assert time.time() - t0 >= 0.35


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_get_429_waits_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "secret-test-key")
    monkeypatch.setattr(uo, "LIM", uo.Limiter(limit=100, window=5))
    monkeypatch.setattr(uo, "WALL_LOG", tmp_path / "walls.log")
    uo.STATS.clear()
    calls = []

    def fake(req, timeout=0):
        calls.append(req)
        assert req.get_header("User-agent") == uo.UA and req.get_header("Authorization").startswith("Basic ")
        assert "secret-test-key" not in req.full_url
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "0.3"}, None)
        return _Resp(b'{"items": []}')

    monkeypatch.setattr(uo.urllib.request, "urlopen", fake)
    code, js = uo.api_get("/company/00006400/officers", {"items_per_page": 100})
    assert code == 200 and js == {"items": []} and len(calls) == 2 and uo.STATS["r429"] == 1
    assert "429" in (tmp_path / "walls.log").read_text()
    uo.STATS.clear()


def test_api_get_404_and_rejected_key(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "secret-test-key")
    monkeypatch.setattr(uo, "LIM", uo.Limiter(limit=100, window=5))
    monkeypatch.setattr(uo, "AUTHFAIL", tmp_path / "AUTH_FAIL")
    codes = iter([404, 401])

    def fake(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, next(codes), "x", {}, None)

    monkeypatch.setattr(uo.urllib.request, "urlopen", fake)
    assert uo.api_get("/company/1/officers") == (404, None)
    with pytest.raises(uo.Fatal):
        uo.api_get("/company/1/officers")
    assert (tmp_path / "AUTH_FAIL").exists()
    uo.STOP.clear()


def test_scrub_hides_the_key(monkeypatch):
    import base64
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "secret-test-key")
    b = base64.b64encode(b"secret-test-key:").decode()
    out = uo.scrub(f"failed with secret-test-key and Basic {b}")
    assert "secret-test-key" not in out and b not in out


def test_queue_priorities_in_the_owners_order():
    assert [p for p, _ in uo.TIERS] == [1, 2, 3, 4, 5, 6]
    assert "charity_number" in uo.TIERS[0][1] and "psc_match" in uo.TIERS[2][1] and ">= 5" in uo.TIERS[3][1]
    assert uo.LIMIT <= 575 and uo.FULL_PRIORITY == 5


def test_xlinks_and_boards_registered():
    from app import boards, xlinks
    assert "uk_officer" in xlinks.SOURCES and xlinks.TARGETS["uk_officer"][1]("abc", None) == "/uk/officer/abc"
    for s in ("uk-officers-most-appointments", "uk-officers-also-trustees", "uk-officers-also-us"):
        assert s in boards.BY_SLUG and boards.BY_SLUG[s].group == "uk-companies"


def _client():
    from app import db
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def test_officer_pages_and_search():
    if not app_ukco.ready():
        return
    from loader import db as ldb
    c = _client()
    assert c.get("/uk/officer/not%20valid").status_code == 404
    assert c.get("/uk/officer/zzzzzzzzzzzz").status_code == 404
    with ldb.connect() as conn:
        conn.execute(uo.DDL)
        conn.execute("DELETE FROM uk_companies.officer WHERE company_number = 'TESTOFF1'")
        conn.execute("""INSERT INTO uk_companies.officer (company_number, appt_key, officer_id, name, name_norm, role, corporate, appointed_on, birth_year, birth_month)
                        VALUES ('TESTOFF1', 'k1', 'testofficer0001', 'Zzqtest Officerx', 'zzqtest officerx', 'director', false, '2020-01-01', 1970, 3)""")
        conn.commit()
    try:
        r = c.get("/uk/officer/testofficer0001")
        assert r.status_code == 200 and "Zzqtest Officerx" in r.text and "March 1970" in r.text and "Open Government Licence" in r.text
        r = c.get("/uk/companies/search?q=zzqtest officerx")
        assert r.status_code == 200 and "/uk/officer/testofficer0001" in r.text
    finally:
        with ldb.connect() as conn:
            conn.execute("DELETE FROM uk_companies.officer WHERE company_number = 'TESTOFF1'")
            conn.commit()


def test_data_page_describes_officers():
    c = _client()
    if not app_ukco.ready():
        return
    t = c.get("/data").text
    assert 'id="uk-companies"' in t and "575" in t and "day of birth" in t
