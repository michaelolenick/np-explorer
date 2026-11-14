"""GDELT news (loader/gdelt_parse.py, loader/gdelt.py, app/gdelt_news.py; owner, 2026-11-14): name normalisation, the GKG
line filter (what is kept, what is dropped, no article text), the dictionary lookup, the "In the news" block and /news-index
rendering with the standard menu and width, the API's news entry with GDELT attribution, and the shared-table hygiene (test
rows use a private entity kind and are deleted)."""

import array
import datetime as dt
import io
import re

import pytest

from loader import gdelt_parse as gp

NAMES_O = ["harvard university", "red cross"]
NAMES_U = ["xavier stonebreaker"]
NAMES_C = ["john smith"]


@pytest.fixture()
def dic(tmp_path):
    bm = bytearray(1 << (gp.BITS - 3))
    for k, names in (("orgs", NAMES_O), ("pers_u", NAMES_U), ("pers_c", NAMES_C)):
        a = array.array("Q", sorted(gp.h64(n) for n in names))
        with open(tmp_path / f"{k}.u64", "wb") as f:
            a.tofile(f)
        for v in a:
            i = v & gp.MASK
            bm[i >> 3] |= 1 << (i & 7)
    (tmp_path / "bitmap.bin").write_bytes(bytes(bm))
    return gp.Dict(tmp_path)


def line(url="https://example.com/a", persons="", orgs="", title="A &amp; B", themes="ECON_INFLATION;TAX_FNCACT;WB_1_X", tone="-2.5,1,3,4,5,6,300"):
    f = [""] * 27
    f[0], f[1], f[3], f[4] = "20260601000000-1", "20260601000000", "example.com", url
    f[7], f[12], f[14], f[15] = themes, persons, orgs, tone
    f[26] = f"<PAGE_TITLE>{title}</PAGE_TITLE><PAGE_AUTHORS>x</PAGE_AUTHORS>"
    return "\t".join(f) + "\n"


def run(lines, dic):
    stats = dict(records=0, articles=0, org_mentions=0, person_mentions=0)
    a, m = io.StringIO(), io.StringIO()
    gp.parse_lines(lines, dic, stats, a, m)
    return stats, a.getvalue(), m.getvalue()


def test_core_and_pnorm_match_the_site_forms():
    assert gp.core("WinCo Foods, LLC") == "winco foods" and gp.core("The Red Cross Inc.") == "red cross"
    assert gp.pnorm("Cathryn O'Malley") == "cathryn omalley" and gp.pnorm("José Núñez-Ruiz") == "jose nunez ruiz"


def test_organization_and_unique_person_kept_with_metadata_only(dic):
    st, a, m = run([line(persons="Xavier Stonebreaker,120;Xavier Stonebreaker,400", orgs="Harvard University,55")], dic)
    assert st["articles"] == 1
    row = a.strip().split("\t")
    assert row[2] == "example.com" and row[4] == "A & B" and row[5] == "eng" and row[6] == "-2.5" and row[7] == "ECON_INFLATION"
    assert "o\tharvard university\t55\t1" in m and "p\txavier stonebreaker\t120\t2\tu" in m
    assert len(row) == 8                                    # no text field of any kind


def test_shared_person_name_kept_only_with_an_organization_in_the_article(dic):
    assert run([line(persons="John Smith,10")], dic)[0]["articles"] == 0
    st, _, m = run([line(persons="John Smith,10", orgs="Red Cross,3")], dic)
    assert st["articles"] == 1 and "p\tjohn smith\t10\t1\tc" in m


def test_unknown_names_and_short_lines_are_dropped(dic):
    assert run([line(persons="Nobody Known,1", orgs="Some Other Group,2"), "short\n"], dic)[0]["articles"] == 0


def test_translated_articles_report_their_source_language(dic):
    f = line(orgs="Harvard University,5").rstrip("\n").split("\t")
    f[25] = "srclc:fra;eng:Moses 2.0 Europarl/JRC-Acquis Collection"
    assert "\tfra\t" in run(["\t".join(f) + "\n"], dic)[1]


# --- pages ---------------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _pool():
    from app import db
    db.pool.open(wait=False)


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient

    from app import db, main
    db.pool.open(wait=False)
    return TestClient(main.app)


@pytest.fixture()
def rows():
    """One test entity (kind "org", an EIN no nonprofit has) with two articles; removed afterwards."""
    from app import db
    ein = "999999991"
    with db.conn() as c:
        if c.execute("SELECT to_regclass('gdelt.links') AS t").fetchone()["t"] is None:
            pytest.skip("gdelt tables not loaded")
        c.execute("DELETE FROM gdelt.links WHERE ekey = %s", (ein,))
        c.execute("DELETE FROM gdelt.articles WHERE aid IN (-1, -2)")
        c.execute("DELETE FROM gdelt.entity_news WHERE ekey = %s", (ein,))
        for aid, day in ((-1, 5), (-2, 9)):
            c.execute("INSERT INTO gdelt.articles (aid, seen, domain, url, title, lang, tone) VALUES (%s, %s, 'example.com', %s, %s, 'eng', -1)",
                      (aid, dt.datetime(2026, 11, day, 12), f"https://example.com/story{day}", f"Test story {day}"))
            c.execute("INSERT INTO gdelt.links (ekind, ekey, seen, aid, how) VALUES ('org', %s, %s, %s, 'Exact name match: \"x\"')",
                      (ein, dt.datetime(2026, 11, day, 12), aid))
        c.execute("INSERT INTO gdelt.entity_news (ekind, ekey, name, n, first_seen, last_seen) VALUES ('org', %s, 'TEST ORG', 2, '2026-11-01', '2026-11-01')", (ein,))
    from app import gdelt_news
    gdelt_news.entity.cache_clear()
    yield ein
    with db.conn() as c:
        c.execute("DELETE FROM gdelt.links WHERE ekey = %s", (ein,))
        c.execute("DELETE FROM gdelt.articles WHERE aid IN (-1, -2)")
        c.execute("DELETE FROM gdelt.entity_news WHERE ekey = %s", (ein,))
    gdelt_news.entity.cache_clear()


def test_entity_lists_latest_first_and_the_api_block_carries_attribution(rows):
    from app import gdelt_news
    e = gdelt_news.entity("org", rows)
    assert [a["title"] for a in e["articles"]] == ["Test story 9", "Test story 5"] and e["count"] == 2
    b = gdelt_news.api_block("org", rows)
    assert b["articles"] == 2 and b["latest"][0]["url"].endswith("story9") and "gdeltproject.org" in b["attribution"]


def test_block_renders_links_and_attribution(rows):
    from app import main
    html = main.templates.get_template("_news_block.html").render(gnews=__import__("app.gdelt_news", fromlist=["x"]), nw_kind="org", nw_key=rows,
                                                                  num=lambda v: f"{v:,}")
    assert 'href="https://example.com/story9"' in html and "In the news" in html and "gdeltproject.org" in html


def test_news_index_keeps_the_site_menu_and_width(client):
    r = client.get("/news-index")
    if r.status_code == 404:
        pytest.skip("gdelt summary not built")
    assert r.status_code == 200
    assert re.search(r"<body[^>]*>", r.text).group(0) == '<body class="wide contained">'
    assert "gdeltproject.org" in r.text and 'href="/support"' in r.text


def test_unknown_entity_has_no_block():
    from app import gdelt_news
    assert gdelt_news.entity("org", "000000000") is None and gdelt_news.entity("nope", "1") is None
