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
    assert html.count('action="/support/checkout"') == 4        # monthly, one time, and an Other dialog for each
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


@pytest.mark.parametrize("kind, typed, cents", [
    ("monthly", "5", 500), ("monthly", "12.50", 1250), ("once", "$1,000", 100000), ("once", "12.345", 1235),
    ("once", "4.99", None), ("once", "0", None), ("once", "-20", None), ("once", "10000.01", None),
    ("once", "10000", 1000000), ("monthly", "abc", None), ("monthly", "nan", None), ("monthly", "", None),
    ("yearly", "20", None),
])
def test_other_amounts_have_a_floor_and_a_ceiling(kind, typed, cents):
    assert support.OTHER_MIN == 500
    assert support.other_cents(kind, typed) == cents


def test_other_amount_checkout_prices_inline(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(support, "client", lambda: fake)
    monkeypatch.setattr(support, "product_id", lambda: "prod_support")
    support.checkout_url("monthly", 1234, other=True)
    support.checkout_url("once", 777700, other=True)
    monthly, once = fake.created
    assert monthly["mode"] == "subscription" and monthly["line_items"] == [
        {"price_data": {"currency": "usd", "unit_amount": 1234, "product": "prod_support",
                        "recurring": {"interval": "month"}}, "quantity": 1}]
    assert once["mode"] == "payment" and once["submit_type"] == "donate" and once["line_items"] == [
        {"price_data": {"currency": "usd", "unit_amount": 777700, "product": "prod_support"}, "quantity": 1}]
    assert monthly["metadata"]["other"] == "1" and once["metadata"]["amount_dollars"] == "7777.00"


def test_support_page_offers_other_amounts(monkeypatch):
    html = _page(monkeypatch, True)
    assert html.count(">Other amount</button>") == 2
    assert 'id="other-monthly"' in html and 'id="other-once"' in html
    assert html.count('name="amount_dollars"') == 2 and html.count('min="5"') == 2
    assert "/static/support.js" in html
    assert ' open aria-labelledby' not in html              # dialogs closed unless asked for


def _post(monkeypatch, data):
    from starlette.testclient import TestClient

    from app import main
    monkeypatch.setattr(support, "enabled", lambda: True)
    monkeypatch.setattr(support, "checkout_url", lambda kind, amount, other=False: f"https://checkout.stripe.com/{kind}/{amount}/{other}")
    return TestClient(main.app).post("/support/checkout", data=data, follow_redirects=False)


def test_other_amount_posts(monkeypatch):
    r = _post(monkeypatch, {"kind": "once", "amount_dollars": "42.50"})
    assert r.status_code == 303 and r.headers["location"] == "https://checkout.stripe.com/once/4250/True"
    r = _post(monkeypatch, {"kind": "monthly", "amount_dollars": "3"})
    assert r.status_code == 400 and "Please enter an amount from $5 to $10,000." in r.text
    assert 'id="other-monthly" class="other-amount" open' in r.text     # the form comes back open
    r = _post(monkeypatch, {"kind": "monthly", "other": "1"})           # Other button without JavaScript
    assert r.status_code == 303 and r.headers["location"] == "/support?other=monthly#other-monthly"
    r = _post(monkeypatch, {"kind": "monthly", "amount": "500"})        # fixed amounts unchanged
    assert r.headers["location"] == "https://checkout.stripe.com/monthly/500/False"


def test_thanks_page_says_thank_you():
    from starlette.testclient import TestClient

    from app import main
    html = TestClient(main.app).get("/support/thanks").text
    assert "We thank you for your donation. You&#39;ve helped shine sunlight in a corner that&#39;s been too dark for too long." in html \
        or "We thank you for your donation. You've helped shine sunlight in a corner that's been too dark for too long." in html
