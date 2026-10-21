"""Source credit: CSV footers and filenames, "Cite this" citations, share-card credit line, license copy.

Pure tests run anywhere; the CSV route tests need DATABASE_URL and skip without a database.
"""

import csv
import datetime as dt
import io

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app import boards as B
from app import cite, csvfoot, sharecard
from app.config import ROOT, SITE_URL

DAY = dt.date(2026, 10, 18)


# --- citations ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,title,path,years,span", [
    ("org", "Example Foundation", "/org/123456789", [2019, None, 2015, 2023], "2015–2023"),
    ("person", "Jane Q. Doe", "/person/42", (2012, 2020), "2012–2020"),
    ("board", "Top paid (The big earners)", "/boards/top-paid", None, ""),
    ("institution", "Example Bank Trust Department", "/institution/7", [2021, 2021], "2021"),
    ("school", "Example University", "/school/99", "2010–2024", "2010–2024"),
    ("trust", "The Example Charitable Trust", "/trust/123456789", [2018, 2022], "2018–2022"),
])
def test_citations_for_each_page_type(kind, title, path, years, span):
    c = cite.citations(title, path, kind, years, today=DAY)
    url = SITE_URL + path
    assert c["url"] == url and c["date"] == "2026-10-18" and c["years"] == span
    formats = dict(c["formats"])
    assert list(formats) == ["Plain text", "APA", "MLA"]
    for text in formats.values():
        assert title in text and "Strategy Studio" in text and url in text
        if span:
            assert f"tax years {span}" in text
        else:
            assert "tax years" not in text
    assert formats["Plain text"].endswith("Retrieved 2026-10-18.")
    assert formats["APA"].startswith("Strategy Studio. (n.d.). " + title + " [" + cite.KINDS[kind])
    assert formats["APA"].endswith(f"Retrieved October 18, 2026, from {url}")
    assert formats["MLA"].startswith("“" + title + ".” Strategy Studio")
    assert formats["MLA"].endswith("Accessed 18 Oct. 2026.")


def test_citation_url_keeps_query_and_defaults_to_today():
    c = cite.citations("X", "/boards/top-paid?state=OH&page=2")
    assert c["url"] == SITE_URL + "/boards/top-paid?state=OH&page=2" and c["date"] == dt.date.today().isoformat()
    assert cite.year_range([None, ""]) == "" and cite.year_range(None) == ""


def _env():
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True, undefined=StrictUndefined)
    cite.install(env)
    return env


def test_cite_partial_renders_with_and_without_context():
    env = _env()
    html = env.from_string('{% with cite_kind="org", cite_years=[2015, 2023] %}{% include "_cite.html" %}{% endwith %}') \
        .render(page_title="Example Foundation", page_path="/org/123456789")
    assert "<details class=\"cite\">" in html and "<summary>Cite this</summary>" in html
    assert html.count('class="copy-cite"') == 3 and "tax years 2015–2023" in html
    assert SITE_URL + "/org/123456789" in html
    bare = env.get_template("_cite.html").render()      # nothing passed: still renders (StrictUndefined)
    assert "Cite this" in bare


def test_license_copy_on_about_data_and_footer():
    from scripts.render_static import CONTEXT
    env = _env()
    for name in ("about.html", "data.html"):
        html = env.get_template(name).render(**CONTEXT)
        assert 'id="license"' in html and "https://creativecommons.org/licenses/by/4.0/" in html
        assert "Data: Strategy Studio (furp.org)" in html and "MIT license" in html
        assert '<a href="/data#license">Data: Strategy Studio, CC BY 4.0.</a>' in html


# --- CSV footer and filename -------------------------------------------------------------

def test_csv_footer_and_filename():
    assert csvfoot.source_line("/boards/top-paid", DAY) == \
        f"Source: Strategy Studio, {SITE_URL}/boards/top-paid, retrieved 2026-10-18"
    rows = list(csv.reader(io.StringIO(csvfoot.footer("/org/123456789/funders", DAY))))
    assert rows == [[], [f"Source: Strategy Studio, {SITE_URL}/org/123456789/funders, retrieved 2026-10-18"]]
    assert csvfoot.filename("top-paid", DAY) == "strategystudio-top-paid-2026-10-18.csv"
    assert csvfoot.filename('org 1/2"x', DAY) == "strategystudio-org-1-2-x-2026-10-18.csv"
    assert csvfoot.disposition("top-paid", DAY)["Content-Disposition"] == \
        'attachment; filename="strategystudio-top-paid-2026-10-18.csv"'


@pytest.fixture(scope="module")
def client():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    row = conn.execute("SELECT ein, tax_year FROM filings WHERE tax_year IS NOT NULL LIMIT 1").fetchone()
    conn.close()
    from starlette.testclient import TestClient

    from app import db
    from app.main import app
    # No `with TestClient(...)`: its lifespan closes the shared pool, and a closed pool can't reopen
    # for the next test module. Open it here (a no-op if already open) and leave it open.
    db.pool.open(wait=False)
    c = TestClient(app)
    c.sample = row
    return c


def _check_csv(r, header_start, page_path, name):
    assert r.status_code == 200
    today = dt.date.today().isoformat()
    assert r.headers["content-disposition"] == f'attachment; filename="strategystudio-{name}-{today}.csv"'
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:len(header_start)] == header_start                     # header row still first
    assert rows[-2] == [] and rows[-1] == [f"Source: Strategy Studio, {SITE_URL}{page_path}, retrieved {today}"]


def test_board_csv_has_header_and_source_footer(client):
    r = client.get("/boards/top-paid.csv?state=OH")
    _check_csv(r, ["rank", "subject_name", "subject_url"], "/boards/top-paid", "top-paid")


def test_org_csvs_have_header_and_source_footer(client):
    if not client.sample:
        pytest.skip("no filings")
    ein, year = client.sample
    r = client.get(f"/org/{ein}/funders.csv")
    _check_csv(r, ["grantor_ein", "grantor_name"], f"/org/{ein}/funders", f"org-{ein}-funders")
    r = client.get(f"/org/{ein}/grants/{year}.csv")
    _check_csv(r, ["tax_year", "kind", "recipient_name"], f"/org/{ein}/grants/{year}", f"org-{ein}-grants-{year}")


# --- share cards -------------------------------------------------------------------------

class _Recorder:
    """Stands in for ImageDraw.Draw: records the text drawn."""

    def __init__(self):
        self.texts = []

    def line(self, *a, **k):
        pass

    def text(self, xy, text, **k):
        self.texts.append(text)

    def textlength(self, text, font=None):
        return len(text) * 12


def test_share_card_credit_line():
    host = SITE_URL.split("://", 1)[-1]
    assert "strategystudio.org" in host
    assert sharecard.credit_line("Top  paid", "/boards/top-paid") == ("Top paid", f"{host}/boards/top-paid")
    d = _Recorder()
    sharecard.draw_footer(d, "Top paid", "/boards/top-paid", "IRS Form 990 filings, 2010 to 2025", None)
    assert d.texts == ["IRS Form 990 filings, 2010 to 2025", f"Top paid | {host}/boards/top-paid"]
    d = _Recorder()
    sharecard.draw_footer(d, "A very long board name " * 10, "/boards/x", "note", None)
    assert d.texts[-1].endswith(f"... | {host}/boards/x")                    # the name gives way, the address never


def test_every_board_card_draws_the_credit(monkeypatch):
    seen = []
    real = sharecard.draw_footer
    monkeypatch.setattr(sharecard, "draw_footer", lambda d, name, path, *a: (seen.append((name, path)), real(d, name, path, *a)))
    for board in B.visible():
        png = sharecard.render(board, [], None)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert seen[-1] == (board.title, f"/boards/{board.slug}")
