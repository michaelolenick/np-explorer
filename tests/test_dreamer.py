"""Nonprofit Dreamer (app/dreamer.py; owner, 2026-10-30): wording, the page, and where it is linked from."""

import re

from starlette.testclient import TestClient

from app import dreamer, main

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def _stats(n=1842, alive5=56, two50=5, med_officer=0.0, median5=40000.0):
    years = [{"k": k, "n": n, "p25": 0.0, "median": median5 if k == 5 else 0.0, "p75": 1.0, "paid_pct": 8,
              "med_officer": med_officer, "paid_officer": 48000.0} for k in dreamer.YEARS]
    return {"n": n, "filers": n, "closed": 0, "years": years, "reach": [(t, 1) for t in dreamer.THRESHOLDS],
            "alive5": alive5, "two50": two50, "two50_n": 1}


def test_headline_reads_plainly():
    d = {"shown": _stats(), "small": False, "pay": False, "open_only": False}
    assert dreamer.headline(d) == ("Of 1,842 nonprofits like yours, the median paid its officers $0 in year 1 and "
                                   "took in under $50K in year 5. 56% were still filing in year 5.")


def test_headline_leaves_out_survival_for_a_category():
    # A category can't count closed nonprofits (the IRS drops their NTEE code), so it would show ~99%.
    d = {"shown": _stats(), "small": False, "pay": False, "open_only": True}
    assert "still filing" not in dreamer.headline(d)


def test_small_group_says_it_is_all_nonprofits():
    d = {"shown": _stats(n=530801), "small": True, "pay": True, "open_only": False}
    assert dreamer.headline(d).startswith("Of 530,801 nonprofits founded 2012 to 2018 that paid an officer,")


def test_two_salaries_in_plain_words():
    assert dreamer.two50_words(_stats(two50=5)) == ("Could it support two $50K salaries? Only 5% did at some point in "
                                                    "their first five years (about 1 in 20).")
    assert "None of them" in dreamer.two50_words(_stats(two50=0))


def test_money_and_revenue():
    assert dreamer.money(0) == "$0" and dreamer.money(4659) == "$4,659"
    assert dreamer.money(140013) == "$140K" and dreamer.money(8951529) == "$9M" and dreamer.money(1250000) == "$1.2M"
    assert dreamer.revenue(49999) == "under $50K" and dreamer.revenue(64000) == "$64K"


def test_page_without_a_question_has_the_form_and_beta():
    html = client.get("/dreamer").text
    assert 'name="q"' in html and 'name="kind"' in html and 'name="where"' in html and 'name="pay"' in html
    assert re.search(r'Nonprofit Dreamer <span class="beta-tag">BETA</span>', html)
    assert "990-N postcard" in html


def test_linked_from_menu_more_and_home():
    assert 'href="/dreamer"' in client.get("/more").text
    home = client.get("/").text
    assert 'href="/dreamer"' in home[home.index('class="home-search"'):]      # under the search box too
    base = (main.ROOT / "templates" / "base.html").read_text()
    menu = base[base.index('<a href="/deep">'):base.index('<hr class="nav-drop-rule">')]
    assert '<a href="/dreamer">' in menu       # Research, above the divider
