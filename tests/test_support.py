"""Support page payments: only the offered amounts, the right Checkout Session, and webhooks verified."""

import types

import pytest

from app import support


def test_offered_amounts_are_the_owners():
    # Owner's choices (2026-10-19): monthly $5, $7.50, $10, $15, $25; one time $25, $50, $100, $500, $1,000.
    assert [support.dollars(c) for c in support.MONTHLY] == ["$5", "$7.50", "$10", "$15", "$25"]
    assert [support.dollars(c) for c in support.ONCE] == ["$25", "$50", "$100", "$500", "$1,000"]
    assert support.lookup_key("monthly", 500) == "support-monthly-5"          # existing Stripe prices keep their keys
    assert support.lookup_key("monthly", 750) == "support-monthly-750c"


@pytest.mark.parametrize("kind, amount, ok", [
    ("monthly", "500", 500), ("monthly", "750", 750), ("monthly", 2500, 2500), ("monthly", "5000", None),
    ("monthly", "7.50", None), ("once", "100000", 100000), ("once", "3500", None), ("once", "500", None),
    ("yearly", "2500", None), ("once", None, None),
])
def test_only_offered_amounts(kind, amount, ok):
    assert support.valid(kind, amount) == ok


class FakeClient:
    def __init__(self):
        self.created = []
        sessions = types.SimpleNamespace(create=lambda params: self.created.append(params) or
                                         types.SimpleNamespace(url="https://checkout.stripe.com/c/pay/cs_test_x"))
        self.v1 = types.SimpleNamespace(checkout=types.SimpleNamespace(sessions=sessions))


def test_checkout_sessions(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(support, "client", lambda: fake)
    monkeypatch.setattr(support, "price_id", lambda kind, amount: f"price_{kind}_{amount}")
    assert support.checkout_url("monthly", 750).startswith("https://checkout.stripe.com/")
    support.checkout_url("once", 50000)
    monthly, once = fake.created
    assert monthly["mode"] == "subscription" and "submit_type" not in monthly
    assert once["mode"] == "payment" and once["submit_type"] == "donate"
    for p in (monthly, once):
        meta = p["metadata"]
        cents = round(float(meta["amount_dollars"]) * 100)
        assert p["line_items"] == [{"price": f"price_{meta['kind']}_{cents}", "quantity": 1}]
        assert p["managed_payments"] == {"enabled": False} and "payment_method_types" not in p
        assert p["success_url"].endswith("/support/thanks") and p["cancel_url"].endswith("/support?canceled=1")


def test_webhook_needs_a_secret_and_a_valid_signature(monkeypatch):
    monkeypatch.setattr(support, "STRIPE_WEBHOOK_SECRET", "")
    with pytest.raises(support.SupportError):
        support.handle_webhook(b"{}", "t=1,v1=00")
    monkeypatch.setattr(support, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(support, "client", lambda: __import__("stripe").StripeClient("sk_test_x"))
    recorded = []
    monkeypatch.setattr(support, "record", lambda e: recorded.append(e))
    with pytest.raises(Exception) as err:
        support.handle_webhook(b'{"id": "evt_1"}', "t=1,v1=" + "0" * 64)
    assert "Signature" in type(err.value).__name__ and recorded == []


def _page(monkeypatch, enabled: bool) -> str:
    from starlette.testclient import TestClient

    from app import main
    monkeypatch.setattr(support, "enabled", lambda: enabled)
    return TestClient(main.app).get("/support").text      # no `with`: keeps the shared pool open


def test_support_page_shows_every_donation_button(monkeypatch):
    html = _page(monkeypatch, True)
    for label in ("$5 a month", "$7.50 a month", "$10 a month", "$15 a month", "$25 a month"):
        assert f">{label}</button>" in html, label
    for label in ("$25", "$50", "$100", "$500", "$1,000"):
        assert f">{label}</button>" in html, label
    assert html.count('action="/support/checkout"') == 2
    assert "We don't have our nonprofit paperwork yet" in html


def test_support_page_says_so_when_giving_is_off(monkeypatch):
    html = _page(monkeypatch, False)
    assert 'action="/support/checkout"' not in html
    assert "Online giving isn't switched on here yet" in html and "$7.50" in html   # never silently missing
    assert "We don't have our nonprofit paperwork yet" in html


def test_support_page_is_never_pre_rendered():
    # The served page must come from the app (its forms depend on Stripe keys), not a static copy without them.
    src = (__import__("pathlib").Path(__file__).resolve().parent.parent / "scripts" / "render_static.py").read_text()
    pages = src[src.index("PAGES = ["):src.index("]", src.index("PAGES = ["))]
    assert "support.html" not in pages
