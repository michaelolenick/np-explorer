"""Organization pages list officers and directors who reported no compensation in their own section."""

import re

import pytest

AOGF, DUCKS = "810739440", "135643799"     # American Online Giving Foundation (all $0); Ducks Unlimited (paid staff)


@pytest.fixture(scope="module")
def client():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        psycopg.connect(DATABASE_URL, connect_timeout=5).close()
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    from starlette.testclient import TestClient

    from app import db
    from app.main import app
    try:
        db.pool.open(wait=False)      # no `with`: the lifespan would close the shared pool
    except Exception:  # noqa: BLE001 - already open
        pass
    return TestClient(app)


def _section(html: str, heading: str) -> str:
    i = html.find(heading)
    if i < 0:
        return ""
    ends = [j for j in (html.find("<h2", i + len(heading)), html.find("<h3", i + len(heading))) if j > 0]
    return html[i:min(ends)] if ends else html[i:]


def test_all_zero_org_lists_its_officers(client):
    html = client.get(f"/org/{AOGF}").text
    assert "No one listed on these returns was paid" not in html
    assert "reported compensation from the organization" in html            # the replacement line, with the count
    sec = _section(html, "Officers and directors, no compensation reported")
    m = re.search(r"(\d+) people", sec)                                 # everyone across its returns (grows with new filings)
    assert m and sec.count("/person/") == int(m.group(1)) == sec.count("$0 reported") >= 8
    assert "BRYAN DE LOTTINVILLE".title() in sec.title() or "Lottinville" in sec


def test_org_with_paid_staff_keeps_both_sections(client):
    html = client.get(f"/org/{DUCKS}").text
    paid = _section(html, "People paid by the organization")
    unpaid = _section(html, "Officers and directors, no compensation reported")
    assert re.search(r"\d+ (person|people) paid across every filing", paid)
    assert paid.count("/person/") > 5 and unpaid.count("$0 reported") >= 1
    assert "None of the" not in paid                                           # only when nobody was paid
