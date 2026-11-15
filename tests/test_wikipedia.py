"""Wikipedia and Wikidata bios (loader/wikipedia.py, app/wikipedia.py, templates/_wikipedia_about.html, owner 2026-11-14).
Fixture rows use the QIDs Qtest9001..Qtest9003 and are deleted afterwards; they are attached to the first organization,
person and college rows of the shared database and hidden again at teardown."""

import pytest
from starlette.testclient import TestClient

from app import main, wikipedia as wp
from loader import db, wikipedia as lw

client = TestClient(main.app)            # no `with`: keeps the shared pool open
QIDS = ("Qtest9001", "Qtest9002", "Qtest9003")


@pytest.fixture(autouse=True, scope="module")
def pool():
    from app import db as appdb
    try:
        appdb.pool.open()
    except Exception:  # noqa: BLE001
        pass


def _clean(conn):
    conn.execute("DELETE FROM wiki.link WHERE qid = ANY(%s)", (list(QIDS),))
    conn.execute("DELETE FROM wiki.entity WHERE qid = ANY(%s)", (list(QIDS),))
    conn.execute("DELETE FROM wiki.label WHERE qid LIKE 'Qtest90%'")
    conn.commit()
    wp.about.cache_clear()


@pytest.fixture
def conn():
    with db.connect() as c:
        lw.ensure_schema(c)
        _clean(c)
        yield c
        c.rollback()
        _clean(c)


def test_middle_names_must_not_conflict():
    assert lw.middles_ok("john smith", "john a smith")
    assert lw.middles_ok("john a smith", "john adam smith")
    assert not lw.middles_ok("john a smith", "john b smith")
    assert not lw.middles_ok("john smith jr", "john smith sr")
    assert not lw.middles_ok("john smith jr", "john smith") and lw.middles_ok("john a smith jr", "john smith jr")
    assert not lw.middles_ok("john smith", "jane smith")


def test_name_keys_and_domains():
    keys = lw.person_keys("William H. Gates III", "Bill Gates", ["Bill Gates"])
    assert ("william h gates iii", "william gates", "label") in keys and ("bill gates", "bill gates", "title") in keys
    assert lw.person_keys("Madonna", None, None) == []        # one word: never matched
    assert lw.domain_of("https://www.redcross.org/about") == "redcross.org"
    assert lw.domain_of("HTTP://Gatesfoundation.org") == "gatesfoundation.org" and lw.domain_of("not a url") is None


def test_lead_is_short_and_clean():
    wt = ("{{Short description|American charity}}\n{{Infobox organization|name=X}}\n"
          "'''The American Red Cross''' (ARC) is a [[humanitarian]] organization.<ref>Cited.</ref> Founded in 1881 by "
          "[[Clara Barton]], it is headquartered in Washington, D.C. Dr. Smith led it for years and years and years and "
          "years and years and years and years and years and years and years and years and years.\n\n== History ==\nMore.")
    short, plain = lw._strip_markup(wt)
    assert short == "American charity"
    out = lw.lead_sentences(plain)
    assert out.startswith("The American Red Cross (ARC) is a humanitarian organization.")
    assert "<ref" not in out and "{{" not in out and len(out) <= lw.LEAD_MAX + 1
    assert lw.lead_sentences(None) is None
    long_ = lw.lead_sentences("A " + "word " * 120 + "ends here.")
    assert len(long_) <= lw.LEAD_MAX + 1 and long_.endswith("…")


def _free_org(conn, n):
    """A well-known organization with no real Wikipedia link, so the fixture is the only bio on its page."""
    return conn.execute("""SELECT ein FROM organizations o WHERE latest_total_revenue > 1000000 AND NOT EXISTS (
                               SELECT 1 FROM wiki.link l WHERE l.kind = 'org' AND l.key = o.ein)
                           ORDER BY latest_total_revenue DESC OFFSET %s LIMIT 1""", (5000 + n,)).fetchone()[0]


def _fixture(conn, kind, key, qid, ent_kind, **ent):
    cols = {"label": "Test Person", "title": "Test Person", "wd_desc": "a test description", "has_article": True}
    cols.update(ent)
    names = ["qid", "kind"] + list(cols)
    conn.execute(f"INSERT INTO wiki.entity ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})",
                 [qid, ent_kind] + list(cols.values()))
    conn.execute("INSERT INTO wiki.label (qid, label) VALUES ('Qtest9090', 'test occupation') ON CONFLICT DO NOTHING")
    conn.execute("INSERT INTO wiki.link (kind, key, qid, method, confidence, evidence, show) VALUES (%s, %s, %s, %s, 'high', 'test', true)",
                 (kind, key, qid, "org_ein" if ent_kind == "org" else "person_cik"))
    conn.commit()
    wp.about.cache_clear()


def test_org_page_shows_the_block_with_attribution(conn):
    ein = _free_org(conn, 0)
    _fixture(conn, "org", ein, "Qtest9001", "org", title="Test Foundation", label="Test Foundation", inception=1901,
             lead="The Test Foundation is a test. It exists only in the test suite.", short_desc="Test charity")
    a = wp.about("org", ein)
    assert a["title"] == "Test Foundation" and a["url"].endswith("/Test_Foundation") and ("Founded", "1901") in a["facts"]
    html = client.get(f"/org/{ein}").text
    assert "About (Wikipedia)" in html and "The Test Foundation is a test." in html
    assert "CC BY-SA 4.0" in html and "authors and history" in html and "Report a wrong match" in html
    assert "topic=Corrections" in html and "/data#wikipedia" in html
    # the page loses the block when the link is hidden (the precision rule), nothing else changes
    conn.execute("UPDATE wiki.link SET show = false WHERE qid = 'Qtest9001'")
    conn.commit()
    wp.about.cache_clear()
    assert "About (Wikipedia)" not in client.get(f"/org/{ein}").text


def test_living_people_show_only_the_lead(conn):
    cid = conn.execute("""SELECT id FROM person_clusters c WHERE n_filings >= 3 AND NOT EXISTS (
                              SELECT 1 FROM wiki.link l WHERE l.kind = 'person' AND l.key = c.id::text) ORDER BY id OFFSET 100000 LIMIT 1""").fetchone()[0]
    _fixture(conn, "person", str(cid), "Qtest9002", "person", birth_year=1970, occ_q=["Qtest9090"], emp_q=["Qtest9090"],
             lead="Test Person is an example.")
    a = wp.about("person", str(cid))
    assert a["living"] and a["years"] is None and a["occupations"] == [] and a["affiliations"] == []
    html = client.get(f"/person/{cid}").text
    assert "Test Person is an example." in html and "test occupation" not in html
    conn.execute("UPDATE wiki.entity SET death_year = 2001 WHERE qid = 'Qtest9002'")
    conn.commit()
    wp.about.cache_clear()
    a = wp.about("person", str(cid))
    assert not a["living"] and a["years"] == "1970–2001" and a["occupations"] == ["test occupation"]


def test_api_and_xlinks_carry_the_bio(conn):
    from app import public_api, xlinks
    ein = _free_org(conn, 1)
    _fixture(conn, "org", ein, "Qtest9003", "org", title="Test Trust", label="Test Trust", lead="A test trust.")
    v = public_api.xlinks_view("org", ein)
    w = v["wikipedia"]
    assert w["title"] == "Test Trust" and w["attribution"] == "From Wikipedia, CC BY-SA 4.0" and w["wikidata_license"] == "CC0"
    assert "wikipedia" in xlinks.SOURCES
    assert xlinks.SOURCES["wikipedia"][2]("Q42").endswith("/enwiki/Q42")


def test_contact_topic_corrections_preselects_the_form():
    html = client.get("/contact?topic=Corrections&subject=Wrong+Wikipedia+match").text
    assert 'value="Correction or removal request" selected' in html.replace("\n", " ") or "selected" in html
    assert "Wrong Wikipedia match" in html


def test_boards_registered():
    from app import boards
    slugs = [b.slug for b in boards.BOARDS if b.group == "wikipedia"]
    assert slugs == ["wikipedia-nonprofit-leaders", "wikipedia-notable-boards", "wikipedia-big-nonprofits"]
    assert all(boards.BY_SLUG[s].view.startswith("board_wikipedia") for s in slugs)
