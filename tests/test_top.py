"""The /top hub of priority pages (owner, 2026-10-30), the footer link to it, and canonical links without ?moved=1."""

import re

from starlette.testclient import TestClient

from app import main, top


def _client():
    return TestClient(main.app)          # no `with`: keeps the shared pool open


def test_pages_split_into_ranges():
    assert top.pages(0) == []
    assert top.pages(1200) == [(1, 1, 500), (2, 501, 1000), (3, 1001, 1200)]


def test_footer_links_top_on_home_and_other_pages():
    for path in ["/", "/about"]:
        assert '<a href="/top">Biggest names</a>' in _client().get(path).text, path


def test_top_hub_renders(monkeypatch):
    monkeypatch.setattr(top, "counts", lambda: {"org": 1200, "funder": 10})
    html = _client().get("/top").text
    assert "<h1>Biggest names on FURP</h1>" in html
    assert '<a href="/top/org/3">1,001&ndash;1,200</a>' in html and '<a href="/top/funder/1">1&ndash;10</a>' in html
    assert re.search(r"<body[^>]*>", html).group(0) == '<body class="wide contained">'


def test_unknown_kind_is_404():
    assert _client().get("/top/nobody/1").status_code == 404


def test_canonical_drops_moved():
    html = _client().get("/about?moved=1").text
    assert '<link rel="canonical" href="' in html
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)
    assert "moved" not in canon and canon.endswith("/about")
    assert "strategystudio.org is now FURP" in html      # the notice still shows
