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
    for line in ["A real venture fund leaves a paper trail. Fakes don't, or leave a very recent or very thin one. So don't ask only whether they've filed something: look at how much they've filed, and since when. Check it in a minute.",
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
    # one merged section 5 (owner, 2026-10-30): everything else, patents/trademarks/state filings and the Wayback Machine
    five = html.index("5. Then check everything else, not just the SEC")
    assert "Check more than the SEC" not in html
    assert five < html.index("patents, trademarks and business filings in several states") \
        < html.index('href="https://web.archive.org/"') < html.index("Paperwork is a start, not proof")


def test_what_to_look_for_warns_about_linkedin():
    html = _client().get("/how-to-spot-a-fake").text
    li = html.index("LinkedIn is never a source.")
    assert html.index("4. What to look for on the result") < li < html.index("5. Then check everything else")
    assert "one-time seminar" in html


def test_names_and_vouching_with_citations():
    html = _client().get("/how-to-spot-a-fake").text
    four, five = html.index("4. What to look for on the result"), html.index("5. Then check everything else")
    # the checklist first, then LinkedIn and schools, names and vouching, then the $1,500 checks (owner, 2026-10-30)
    assert four < html.index("Do the people listed match") < html.index("Is the amount raised") \
        < html.index("does the fund manager have a track record?") < html.index("No fund, or a negligible one") \
        < html.index("LinkedIn is never a source.") < html.index("one-time seminar") < html.index("Names don't matter much.") \
        < html.index("Phyllis Gardner") < html.index("$1,500 checks") < five
    assert "Does the name match" not in html
    assert 'href="#citations">**</a>' in html[four:five]
    assert html.index('id="citations"') < html.index("** Names and vouching")


def test_wikipedia_links_and_sentences():
    html = _client().get("/how-to-spot-a-fake").text
    for page, years in [("Bernie_Madoff", "(150 years in prison)"), ("Anna_Sorokin", "(4 to 12 years in prison)"),
                        ("Elizabeth_Holmes", "(11 years and 3 months in prison)")]:
        assert f'href="https://en.wikipedia.org/wiki/{page}"' in html and years in html


def test_nearby_in_browse_menu_and_under_home_search():
    html = _client().get("/").text
    assert html.index('<a href="/deep">') < html.index('<a href="/nearby">Nearby + Similar</a>') \
        < html.index('class="nav-fake"') < html.index('class="nav-drop-rule"') < html.index("nav-drop-head\">Schools")
    assert html.index("</form>") < html.index('<a href="/nearby">Like searches: nearby and similar</a>') \
        < html.index("home-more")


def test_words_that_sound_like_titles_in_the_social_tells():
    html = _client().get("/how-to-spot-a-fake").text
    words = html.index("Words that sound like titles")
    assert html.index("The social tells") < html.index("Asks you to bring friends.") < words < html.index("Charm is free.")
    assert "nothing to check, by design." in html and "stealth VC fund" in html and "a plan, not an entity." in html


def test_fake_page_says_why_it_exists_in_a_red_box_at_the_top():
    html = _client().get("/how-to-spot-a-fake").text
    box = html.index('<div class="fake-warning">')
    assert html.index("<h1>How to spot a fake</h1>") < box < html.index("FAKE venture funds are a real and recurring problem.") \
        < html.index('action="/how-to-spot-a-fake"')
    assert "plethora" not in html                       # softened: no source backs a count (owner, 2026-10-30)
    assert 'href="#citations">***</a>' in html and html.index('id="citations"') < html.index("*** Fake venture funds")
    assert "sec.gov/news/press-release/2022-217" in html and "litigation-releases/lr-25922" in html
    assert html.count("negligible one") >= 1


def test_negligible_fund_warning():
    html = _client().get("/how-to-spot-a-fake").text
    neg = html.index("No fund, or a negligible one")
    assert html.index("4. What to look for on the result") < neg < html.index("5. Then check everything else")
    assert "$1,500 checks" in html and "no fund behind them, or a negligible one." in html


def test_family_office_specifics_warning():
    html = _client().get("/how-to-spot-a-fake").text
    assert "they don&rsquo;t like people asking for specifics" in html
    assert "who they did it for" in html


def test_manager_track_record_item():
    html = _client().get("/how-to-spot-a-fake").text
    assert "does the fund manager have a track record?" in html
    assert "predates it" not in html


def test_form_d_red_flag_once_after_the_exemption():
    html = _client().get("/how-to-spot-a-fake").text
    assert html.count("No Form D is a red flag") == 1
    assert html.index("Section 4(a)(2)") < html.index("No Form D is a red flag. No trace anywhere is the real tell.") \
        < html.index("2. If they advise funds")


def test_madoff_list_only_names_the_sources_confirm():
    html = _client().get("/how-to-spot-a-fake").text
    assert "Sumitomo" not in html and "Korea Life" not in html
    assert "an insurer (AXA)" in html
    assert "tuftsdaily.com" in html and "jewishjournal.com/uncategorized/67773" in html and "jweekly.com" in html


def test_short_link_preview_and_share():
    r = _client().get("/fake?q=acme", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/how-to-spot-a-fake?q=acme"
    assert _client().get("/fake", follow_redirects=False).headers["location"] == "/how-to-spot-a-fake"
    html = _client().get("/how-to-spot-a-fake").text
    assert re.search(r'<meta property="og:title" content="How to spot a fake VC: check any fund in a minute', html)
    assert '<meta property="og:image" content="' in html and "/static/share/fake-vc.png" in html
    assert (main.ROOT / "static" / "share" / "fake-vc.png").exists()
    for s in ("linkedin.com/sharing/share-offsite/", "twitter.com/intent/tweet", "mailto:?", "Copy link"):
        assert html.count(s) == 2, s                     # at the top and in the cohort box
    box = html.index("Share with your cohort")
    assert box < html.index('id="fake-blurb"') < html.index("Search everything FURP has")
    assert "furp.org/fake" in html[box:]
