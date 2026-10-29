"""Every top-level page (the site menu) uses the same column, so they all have the same side margins."""

import re

import pytest

MENU = ["/boards", "/more", "/about", "/contact", "/deep", "/support"]   # Schools is under Browse; the logo goes home


@pytest.fixture(scope="module")
def bodies():
    from starlette.testclient import TestClient

    from app import main
    client = TestClient(main.app)                 # no `with`: keeps the shared pool open
    out = {}
    for path in MENU:
        r = client.get(path)
        assert r.status_code == 200, path
        out[path] = re.search(r"<body[^>]*>", r.text).group(0)
    return out


def test_menu_pages_share_one_layout(bodies):
    assert set(bodies.values()) == {'<body class="wide contained">'}, bodies


def test_menu_links_are_the_pages_checked():
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent / "templates" / "base.html").read_text()
    menu = re.findall(r'\("(/[a-z]*)", "[^"]+"\)', src[src.index("set nav_items"):].split("\n")[0])
    assert menu == MENU                         # one menu on every page, the home page included (CLAUDE.md)


PAGES = ["/about/news", "/support", "/privacy", "/terms", "/data", "/get-ideas", "/more", "/politics", "/federal-spending",
         "/corporate", "/lobbying", "/schools/pay", "/boards/top-paid", "/org/943242767", "/contractor/62137",
         "/search?q=smith", "/student-loans", "/does-not-exist"]


def test_every_page_has_the_same_margins():
    from starlette.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    for path in PAGES:
        body = re.search(r"<body[^>]*>", client.get(path).text).group(0)
        assert body == '<body class="wide contained">', (path, body)


def test_home_page_has_the_same_menu_and_width():
    from starlette.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    def menu(path):
        html = client.get(path).text
        nav = html[html.index("site-nav"):html.index("</nav>")]
        return re.findall(r"<(?:a|summary)[^>]*>([^<]+)<", nav), re.search(r"<body[^>]*>", html).group(0)
    home, about = menu("/"), menu("/about")
    assert home == about and home[1] == '<body class="wide contained">'
