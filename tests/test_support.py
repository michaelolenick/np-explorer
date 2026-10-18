"""Support page payments: only the offered amounts, the right Checkout Session, and webhooks verified."""

import types

import pytest

from app import support


@pytest.mark.parametrize("kind, amount, ok", [
    ("monthly", "5", 5), ("monthly", 50, 50), ("monthly", "7", None), ("monthly", "25.5", None),
    ("once", "1000", 1000), ("once", "35", 35), ("once", "5", None), ("yearly", "25", None), ("once", None, None),
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
    assert support.checkout_url("monthly", 10).startswith("https://checkout.stripe.com/")
    support.checkout_url("once", 500)
    monthly, once = fake.created
    assert monthly["mode"] == "subscription" and "submit_type" not in monthly
    assert once["mode"] == "payment" and once["submit_type"] == "donate"
    for p in (monthly, once):
        meta = p["metadata"]
        assert p["line_items"] == [{"price": f"price_{meta['kind']}_{meta['amount_dollars']}", "quantity": 1}]
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
