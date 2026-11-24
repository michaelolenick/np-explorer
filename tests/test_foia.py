"""Public-records request creator (app/foia.py): routing, the reference tables, the letters, the dev-only gate, and the AI button.
No test reaches a real model or needs award data: the organization lookup is replaced."""
import pytest
from fastapi.testclient import TestClient

from app import foia, foia_data as D, openai_compat

ORG = {"ein": "742237306", "name": "Texas Advocacy Project Inc", "street": "3721 EXECUTIVE CENTER DR STE 215", "city": "AUSTIN",
       "state": "TX", "zip": "78731", "website": "www.texasadvocacyproject.org", "subsection": "03", "uei": "ELKAFN491HM8"}
OVW = {"key": "ASST_NON_15JOVW23GG00550LEGA_015", "number": "15JOVW23GG00550LEGA", "kind": "assistance", "title": "Legal Assistance For Victims",
       "y0": 2023, "y1": 2026, "amount": 750000.0, "route": "ovw", "office": D.FEDERAL["ovw"]["name"], "url": "https://www.usaspending.gov/award/x/"}
OVC = dict(OVW, key="ASST_NON_15POVC23GG04078HT_015", number="15POVC23GG04078HT", route="ojp", amount=439618.0)


@pytest.fixture(autouse=True)
def _org(monkeypatch):
    monkeypatch.setattr(foia, "org_context", lambda ein: {"org": dict(ORG), "awards": [OVW, OVC]} if ein == ORG["ein"] else None)


def test_award_number_and_routing():
    assert foia.award_number("ASST_NON_15JOVW23GG00550LEGA_015") == "15JOVW23GG00550LEGA"
    assert foia.route("Department of Justice", "Offices, Boards and Divisions", "ASST_NON_15JOVW23GG00550LEGA_015") == "ovw"
    assert foia.route("Department of Justice", "Office of Justice Programs", "ASST_NON_15POVC23GG04078HT_015") == "ojp"
    assert foia.route("Department of Housing and Urban Development", "", "ASST_NON_X_1") == "hud"
    assert foia.route("Something Else", None, None) == "other"


def test_tables_are_complete_and_sourced():
    assert len(D.STATES) == 51 and "DC" in D.STATES
    for s in D.STATES.values():
        assert s["statute"] and s["citation"] and s["deadline"] and s["fees"] and s["source"].startswith("https://www.rcfp.org/")
    for a in D.FEDERAL.values():
        assert a["name"] and a["source"].startswith("http")
    assert D.STATES["TX"]["send_email"] == "publicrecords@gov.texas.gov"
    assert D.FEDERAL["ovw"]["email"] == "OVW.FOIA@usdoj.gov"


def base(**kw):
    p = {"ein": ORG["ein"], "requester": {"name": "Jo Doe", "email": "jo@example.org", "address": "1 Main St", "org": "Example News"},
         "fee_category": "news", "fee_waiver": True, "records": ["applications", "progress"], "electronic": True}
    p.update(kw)
    return p


def test_federal_letter_prefills_and_limits_to_the_chosen_agency():
    d = foia.build_letter(base(kind="federal", agency="ovw", awards=[OVW["key"], OVC["key"]]))
    t = d["text"]
    assert "5 U.S.C. § 552" in t and "15JOVW23GG00550LEGA" in t and "UEI ELKAFN491HM8" in t and "EIN 74-2237306" in t
    assert "15POVC23GG04078HT" not in t                              # a different agency's award
    assert "representative of the news media" in t and "552(a)(4)(A)(iii)" in t
    assert "aggregate data only" in t
    assert d["send"]["email"] == "OVW.FOIA@usdoj.gov" and d["send"]["verified"]
    assert any("other agencies" in w for w in d["warnings"])
    assert "expedited" not in t.lower()
    assert "expedited processing" in foia.build_letter(base(kind="federal", agency="ovw", expedite=True, expedite_reason="Soon."))["text"].lower()


def test_federal_without_awards_says_so():
    d = foia.build_letter(base(kind="federal", agency="hud", awards=[]))
    assert any("no federal award data" in w for w in d["warnings"])
    assert any("not confirmed" in w for w in foia.build_letter(base(kind="federal", agency="ed", awards=[]))["warnings"])


def test_texas_pia_letter():
    d = foia.build_letter(base(kind="state", state="TX", agency_name="Office of the Governor, Criminal Justice Division", program="VAWA subgrants"))
    t = d["text"]
    assert "Public Information Act" in t and "ch. 552" in t and "552.2615" in t and "552.221(d)" in t
    assert d["send"]["email"] == "publicrecords@gov.texas.gov" and d["send"]["verified"]


def test_residency_warning_for_restricted_states():
    d = foia.build_letter(base(kind="state", state="VA", agency_name="X", program="Y"))
    assert any("limits this law" in w for w in d["warnings"])
    assert not any("limits this law" in w for w in foia.build_letter(base(kind="state", state="TX", agency_name="X", program="Y"))["warnings"])


def test_irs_letter():
    d = foia.build_letter(base(kind="irs", records=["returns", "application"]))
    t = d["text"]
    assert "26 U.S.C. § 6104(d)" in t and "three most recent years" in t and "1023 or 1024" in t
    assert "immediately" in t and "30 days" in t and "Executive Center Dr" in t
    assert d["send"]["address"].startswith("3721 Executive Center Dr")


def test_missing_requester_fields_become_placeholders():
    t = foia.build_letter({"ein": ORG["ein"], "kind": "irs", "records": ["returns"]})["text"]
    assert "[YOUR NAME]" in t and "[YOUR EMAIL]" in t


def test_unknown_org_asks_to_pick_one():
    assert foia.build_letter({"ein": "000000000", "kind": "irs"})["warnings"]


def test_routes_are_live():
    from app.main import app
    c = TestClient(app)
    r = c.get("/records-request")
    assert r.status_code == 200 and "noindex" in r.text and "foia.js" in r.text and "Expand with AI" in r.text
    assert "Texas" in c.get("/records-request/tables").text
    r = c.post("/api/foia/letter", json=base(kind="irs"))
    assert r.status_code == 200 and "6104(d)" in r.json()["text"]


def test_expand_sends_only_the_notes_and_org(monkeypatch):
    seen = {}

    class R:
        status_code = 200
        def json(self): return {"content": [{"type": "text", "text": "**A clear** request."}]}

    def post(payload, timeout, use_model=None):
        seen["p"] = payload
        return R()

    monkeypatch.setattr(openai_compat, "enabled", lambda: True)
    monkeypatch.setattr(openai_compat, "post", post)
    out = foia.expand_text("also", "emails about hotline", {"org": "Texas Advocacy Project Inc", "kind": "federal", "requester": {"name": "Jo Doe"}})
    assert out == {"text": "A clear request."}                        # markdown stripped
    body = str(seen["p"])
    assert "hotline" in body and "Texas Advocacy Project Inc" in body and "Jo Doe" not in body
    assert foia.expand_text("nope", "abcdef", {})["error"]
    assert foia.expand_text("also", "ab", {})["error"]
    monkeypatch.setattr(openai_compat, "enabled", lambda: False)
    assert "not available" in foia.expand_text("also", "abcdef", {})["error"]


def test_expand_rate_limit(monkeypatch):
    monkeypatch.setattr(foia, "_hits", {})
    monkeypatch.setattr(foia, "_day", {"d": None, "n": 0})
    assert all(foia._allow("1.2.3.4") is None for _ in range(foia.PER_IP_HOUR))
    assert foia._allow("1.2.3.4")
    assert foia._allow("5.6.7.8") is None
