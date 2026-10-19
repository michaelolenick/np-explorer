"""Shared and cited addresses keep the query, so a recipient doesn't have to repeat the search."""

import re

from starlette.testclient import TestClient

from app import cite, main

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def _meta(html, prop):
    m = re.search(rf'<meta property="{prop}" content="([^"]+)"', html)
    return m and m.group(1).replace("&amp;", "&")


def _canonical(html):
    return re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1).replace("&amp;", "&")


def test_search_links_keep_the_query():
    html = client.get("/search?q=smith&utm_source=x&fbclid=abc").text
    assert _canonical(html).endswith("/search?q=smith")
    assert _meta(html, "og:url").endswith("/search?q=smith")         # tracking parameters dropped


def test_board_links_keep_sort_for_sharing_not_for_canonical():
    html = client.get("/boards/schools?view=990&sort=org_revenue&page=2").text
    assert _meta(html, "og:url").endswith("/boards/schools?view=990&sort=org_revenue&page=2")
    assert _canonical(html).endswith("/boards/schools?page=2")
    assert "/boards/schools?view=990&amp;sort=org_revenue&amp;page=2" in html or \
           "/boards/schools?view=990&sort=org_revenue&page=2" in html   # Cite this


def test_plain_pages_unchanged_and_notices_dropped():
    html = client.get("/support?canceled=1").text
    assert _canonical(html).endswith("/support") and _meta(html, "og:url").endswith("/support")
    assert _canonical(client.get("/about").text).endswith("/about")


def test_page_queries_and_cite_url():
    from starlette.requests import Request
    req = Request({"type": "http", "method": "GET", "path": "/search", "headers": [],
                   "query_string": b"q=a+b&sort=x&utm_medium=y&type="})
    assert main.page_queries(req) == ("q=a+b&sort=x", "q=a+b")
    assert cite.page_url("/search?q=a#top").endswith("/search?q=a")
