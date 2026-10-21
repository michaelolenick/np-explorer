"""Google Analytics: the tag on every page in production only, allowed by the CSP, and disclosed on Privacy."""

from pathlib import Path

from starlette.testclient import TestClient

from app import main

ROOT = Path(__file__).resolve().parent.parent


def test_tag_on_pages_when_set(monkeypatch):
    monkeypatch.setitem(main.templates.env.globals, "ga_id", "G-SVNDZGJ06B")
    client = TestClient(main.app)            # no `with`: keeps the shared pool open
    for path in ("/", "/about", "/boards", "/schools", "/search?q=smith", "/privacy"):
        html = client.get(path).text
        assert '<script async src="https://www.googletagmanager.com/gtag/js?id=G-SVNDZGJ06B"></script>' in html, path
        assert 'src="/static/ga.js' in html and 'data-ga-id="G-SVNDZGJ06B"' in html, path


def test_no_tag_when_off(monkeypatch):
    monkeypatch.setitem(main.templates.env.globals, "ga_id", "")
    assert "googletagmanager" not in TestClient(main.app).get("/").text


def test_setup_script_is_the_owners_snippet():
    js = (ROOT / "static" / "ga.js").read_text()
    for line in ("window.dataLayer = window.dataLayer || [];", "function gtag(){dataLayer.push(arguments);}",
                 "gtag('js', new Date());", "gtag('config',"):
        assert line in js


def test_csp_allows_google_tag_and_collection():
    for f in ("furp.org", "dev.strategystudio.org"):
        conf = (ROOT / "deploy" / "nginx" / f).read_text()
        assert "script-src 'self' https://*.googletagmanager.com" in conf, f
        assert "connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com" in conf, f
        assert "'unsafe-inline'" not in conf, f


def test_privacy_page_discloses_it():
    html = TestClient(main.app).get("/privacy").text
    assert "Google Analytics" in html and "_ga_SVNDZGJ06B" in html and "gaoptout" in html
    assert "No third-party analytics" not in html
