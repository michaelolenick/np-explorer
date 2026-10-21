"""The home page has no donation box (owner, 2026-10-21); Support FURP stays in the menu."""

from starlette.testclient import TestClient

from app import main


def test_no_donate_box_on_home():
    html = TestClient(main.app).get("/").text          # no `with`: keeps the shared pool open
    assert "donate-box" not in html and "Help us raise money" not in html and ">DONATE</button>" not in html
    assert ">Support FURP<" in html and 'href="/support"' in html
