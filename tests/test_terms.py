"""Terms of use: the owner's asks are on the page, and every page links to it."""

from starlette.testclient import TestClient

from app import main


def test_terms_page():
    client = TestClient(main.app)            # no `with`: keeps the shared pool open
    html = client.get("/terms").text
    for text in ("Use Strategy Studio to make the world a better place.", "Cite us if you use us",
                 "Better yet, spread the word.", "WITHOUT WARRANTY OF ANY KIND",
                 "LIMITED TO THE AMOUNT YOU HAVE CONTRIBUTED", "you agree to these terms"):
        assert text in html, text
    assert '<a href="/terms">Terms</a>' in client.get("/about").text
