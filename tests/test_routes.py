"""Each page route goes to its own handler (Home, About, Data and Privacy once rendered Support)."""

from app.main import STATIC_PAGES, app


def handler(path: str, method: str = "GET") -> str:
    return next(r.endpoint.__name__ for r in app.routes if getattr(r, "path", None) == path
                and method in getattr(r, "methods", set()))


def test_static_pages_render_their_own_templates():
    for path in ("/", "/about", "/data", "/privacy"):
        assert handler(path) == "static_page", path
        assert STATIC_PAGES[path] == {"/": "index.html"}.get(path, path.strip("/") + ".html")


def test_support_routes():
    assert handler("/support") == "support_page"
    assert handler("/support/checkout", "POST") == "support_checkout"
