"""S-1 strategic profile (app/s1profile.py): section finding, risk categories, competitors, the diff and the dev-only gate.
Nothing here reaches EDGAR or a model."""
import pytest
from fastapi.testclient import TestClient

from app import s1profile as S

RISK = "".join(f"<p><b>Risk number {i} could hurt our results because of {w}.</b></p><p>{'Detail sentence. ' * 40}</p>"
               for i, w in enumerate(["fierce competition from larger rivals", "new regulation and compliance costs",
                                      "the price of our common stock may be volatile"]))
DOC = f"""<html><body>
<p><b>Table of Contents</b></p><p><b>Risk Factors</b></p><p>12</p>
<p><b>Our Competitive Strengths</b></p>
<p><b>Leading platform.</b> {'We built the best platform. ' * 30}</p>
<p><b>Loyal customers.</b> {'Customers stay. ' * 40}</p>
<p><b>Our Growth Strategy</b></p><p><b>Expand abroad.</b> {'We will expand. ' * 40}</p>
<p><b>Competition</b></p><p>{'We compete with Acme Corp and Globex Inc., among others, in many markets. ' * 8}</p>
<p><b>Intellectual Property</b></p><p>{'We hold patents. ' * 50}</p>
<p><b>Risk Factors</b></p><p><b>Risks Related to Our Business</b></p>{RISK}
<p><b>Use of Proceeds</b></p><p>We will use proceeds.</p>
</body></html>"""


def test_blocks_skip_page_furniture():
    b = S.blocks_of(DOC)
    assert not any(x["t"].lower() == "table of contents" for x in b)
    assert any(x["t"] == "Our Competitive Strengths" and x["bold"] for x in b)


def test_sections_and_items():
    b = S.blocks_of(DOC)
    rng = S.find_section(b, S.STRENGTH_RE, search=True, also_stop=S.GROWTH_RE)
    items = S.items_of(b, *rng)
    assert [i["title"] for i in items] == ["Leading platform", "Loyal customers"]
    rr = S.find_section(b, S.RISK_RE, ("major",), 500, max_chars=4000000)
    risks = S.risk_items(b, *rr)
    assert len(risks) == 3
    assert risks[0]["category"] == "competition" and not risks[0]["boilerplate"]
    assert risks[1]["category"] == "regulatory"
    assert risks[2]["category"] == "stock / offering" and risks[2]["boilerplate"]
    assert risks[0]["group"].startswith("Risks Related")


def test_competitors_without_a_model(monkeypatch):
    from app import openai_compat
    monkeypatch.setattr(openai_compat, "enabled", lambda: False)
    names = S.competitor_names("We compete with Acme Corp and Globex Inc., among others. Such as U.S markets.", "Us Co")
    assert "Acme Corp" in names and "Globex Inc" in " ".join(names) and "U.S" not in names


def test_cite_prefers_anchor_then_text_fragment():
    assert S.cite("https://www.sec.gov/a.htm", {"t": "Our Growth Strategy", "id": "sec12"}).endswith("#sec12")
    assert "#:~:text=Our%20Growth" in S.cite("https://www.sec.gov/a.htm", {"t": "Our Growth Strategy", "id": ""})


def test_diff_finds_added_and_removed():
    old = {"risks": [{"title": "We depend on one supplier for all of our key components."}], "competitors": [{"name": "Acme"}]}
    new = {"risks": [{"title": "We depend on a new cyber insurance carrier that may not cover losses."}], "competitors": [{"name": "Acme"}, {"name": "Globex"}]}
    d = S.diff(old, new)
    assert d["risks"]["added"] and d["risks"]["removed"]
    assert d["competitors"] == {"added": ["Globex"], "removed": []}


def test_routes_are_live():
    from app.main import app
    c = TestClient(app)
    r = c.get("/s1")
    assert r.status_code == 200 and "noindex" in r.text and "S-1 strategic profile" in r.text
    assert c.get("/api/s1/search?q=a").status_code == 200
