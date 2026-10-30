"""The red "fake VCs" warning box (owner, 2026-10-30) and the /how-to-spot-a-fake page it links to."""

import re

from starlette.testclient import TestClient

from app import main

def _client():
    return TestClient(main.app)          # no `with`: keeps the shared pool open


def test_home_page_has_no_warning_box_and_browse_menu_links_fake_people():
    html = _client().get("/").text
    assert 'class="fake-warning' not in html                     # off the home page (owner, 2026-10-30)
    assert '<a class="nav-fake" href="/how-to-spot-a-fake">Fake People</a>' in html
    assert html.index('<a href="/deep">') < html.index('class="nav-fake"') < html.index('href="/about"')  # Browse Data, under Deep queries


def test_how_to_spot_a_fake_page():
    r = _client().get("/how-to-spot-a-fake")
    assert r.status_code == 200
    html = r.text
    assert "<title>How to spot a fake" in html
    assert re.search(r"<body[^>]*>", html).group(0) == '<body class="wide contained">'
    for line in ["A real venture fund leaves a paper trail. Fakes don't. Check it in a minute.",
                 "No Form D is a red flag. No trace anywhere is the real tell.",
                 "they need a broker-dealer license", "Then check everything else"]:
        assert line in html, line
    # the fake-check search first, the full search (all sources) at the bottom
    assert html.index('action="/how-to-spot-a-fake"') < html.index("The short version") < html.index('action="/search"')


def test_how_to_spot_a_fake_search_renders_with_a_query():
    html = _client().get("/how-to-spot-a-fake", params={"q": "zzqx no such fund"}).text
    assert "Results for" in html and "No Form D" in html and "/search?q=zzqx" in html


def test_footer_links_to_the_guide():
    for path in ["/", "/about"]:
        html = _client().get(path).text
        footer = html[html.rindex("<footer"):]
        assert 'href="/how-to-spot-a-fake"' in footer, path


def test_social_tells_section_sits_between_the_short_version_and_section_1():
    html = _client().get("/how-to-spot-a-fake").text
    tells = html.index("The social tells: they're easy to like")
    assert html.index("The short version") < tells < html.index("1. If they're raising money")
    for line in ["A room vouching for someone isn't a check. Paperwork is.", "Asks you to bring friends.",
                 "Gets irritated or evasive when asked to be checked.",
                 "Charm is free. Filings aren't. Check the paperwork below."]:
        assert line in html, line


def test_madoff_section_and_paperwork_section():
    html = _client().get("/how-to-spot-a-fake").text
    assert "Madoff's victims were smart" not in html
    well = html.index("Well connected and well respected means nothing")
    assert html.index("Charm is free.") < well < html.index("Titles mean nothing") < html.index("1. If they're raising money")
    assert 'href="#citations">*</a>' in html[well:html.index("Titles mean nothing")]   # citations at the bottom
    cites = html.index('id="citations"')
    assert html.index("Search everything FURP has") < cites < html.index("ejewishphilanthropy.com")
    paper = html.index("Paperwork is a start, not proof")
    assert html.index("5. Then check everything else") < paper < html.index("Search everything FURP has")
    assert "most fakes fail it." in html


def test_titles_and_check_more_than_the_sec_sections():
    html = _client().get("/how-to-spot-a-fake").text
    titles = html.index("Titles mean nothing")
    assert html.index("Charm is free.") < titles < html.index("1. If they're raising money")
    assert "until someone checked the paperwork." in html
    more = html.index("Check more than the SEC")
    assert html.index("5. Then check everything else") < more < html.index("Paperwork is a start, not proof")
    assert 'href="https://web.archive.org/"' in html


def test_what_to_look_for_warns_about_linkedin():
    html = _client().get("/how-to-spot-a-fake").text
    li = html.index("LinkedIn is never a source.")
    assert html.index("4. What to look for on the result") < li < html.index("5. Then check everything else")
    assert "one-time seminar" in html


def test_names_and_vouching_with_citations():
    html = _client().get("/how-to-spot-a-fake").text
    four, five = html.index("4. What to look for on the result"), html.index("5. Then check everything else")
    assert four < html.index("LinkedIn is never a source.") < html.index("Names don't matter much.") \
        < html.index("Phyllis Gardner") < html.index("Do the people listed match") < five
    assert "Does the name match" not in html
    assert 'href="#citations">**</a>' in html[four:five]
    assert html.index('id="citations"') < html.index("** Names and vouching")
