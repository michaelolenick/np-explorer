"""Support FURP: monthly and one-time contributions through Stripe Checkout (hosted by Stripe).

The buttons appear only when STRIPE_SECRET_KEY is set in .env. Prices are created once by
scripts/stripe_setup.py (Stripe lookup keys support-monthly-<dollars> and support-once-<dollars>),
which also registers the webhook and the customer portal. Card details never touch this server.
Every Stripe event reaches /stripe/webhook, is verified with STRIPE_WEBHOOK_SECRET, and is
recorded in stripe_events (ids and amounts only, no names or emails). A new paid contribution sends the donor a
thank-you and us a short "new donor" note (thank_and_notify); the address is used for those two emails only.
"""

from __future__ import annotations

import functools
import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.config import SITE_URL, STRIPE_PORTAL_URL, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

log = logging.getLogger("np.support")

# Amounts in cents (so $7.50 works). Owner's choices, 2026-10-19.
MONTHLY = [500, 750, 1000, 1500, 2500]
ONCE = [2500, 5000, 10000, 50000, 100000]
# "Other amount" (owner, 2026-10-19): any amount in whole cents between these. Stripe keeps 2.9% + 30 cents of
# each card payment, so below $5 most of a gift would go to fees.
OTHER_MIN = 500
OTHER_MAX = 1_000_000          # $10,000 a payment; larger gifts by arrangement (Contact us)
PRODUCT_NAME = "Support furp.org"
PRODUCT_TAG = "strategystudio-support"       # product metadata, so setup can find it again
INTEGRATION_ID = "strategystudio-support-qkzmvtrd"
PORTAL_URL = STRIPE_PORTAL_URL

# Events the webhook acts on (registered by scripts/stripe_setup.py): payments, the subscription
# lifecycle, and the risk events that can take money back.
EVENTS = ["checkout.session.completed", "checkout.session.async_payment_succeeded",
          "checkout.session.async_payment_failed", "customer.subscription.created",
          "customer.subscription.updated", "customer.subscription.deleted", "invoice.paid",
          "invoice.payment_failed", "charge.refunded", "charge.dispute.created", "radar.early_fraud_warning.created"]


class SupportError(Exception):
    pass


def enabled() -> bool:
    return bool(STRIPE_SECRET_KEY)


def dollars(cents: int) -> str:
    """$5, $7.50, $1,000."""
    return f"${cents // 100:,}" if cents % 100 == 0 else f"${cents / 100:,.2f}"


def lookup_key(kind: str, cents: int) -> str:
    """Stripe lookup key: whole dollars keep the original keys (support-monthly-5); others use cents (…-750c)."""
    return f"support-{kind}-{cents // 100}" if cents % 100 == 0 else f"support-{kind}-{cents}c"


def valid(kind: str, amount) -> int | None:
    """The amount in cents if it is one of the offered choices (the form sends cents), else None."""
    try:
        cents = int(amount)
    except (TypeError, ValueError):
        return None
    return cents if (kind == "monthly" and cents in MONTHLY) or (kind == "once" and cents in ONCE) else None


def other_cents(kind: str, amount_dollars) -> int | None:
    """An 'Other amount' typed in dollars ("12", "12.50", "$1,000") as cents, if allowed; else None."""
    if kind not in ("monthly", "once"):
        return None
    text = str(amount_dollars or "").replace("$", "").replace(",", "").strip()
    try:
        d = Decimal(text)
    except InvalidOperation:
        return None
    if not d.is_finite():
        return None
    cents = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return cents if OTHER_MIN <= cents <= OTHER_MAX else None


@functools.lru_cache(maxsize=1)
def client():
    from stripe import StripeClient
    return StripeClient(STRIPE_SECRET_KEY)


@functools.lru_cache(maxsize=32)
def price_id(kind: str, amount: int) -> str:
    prices = client().v1.prices.list(params={"lookup_keys": [lookup_key(kind, amount)], "active": True, "limit": 1})
    if not prices.data:
        raise SupportError(f"no Stripe price {lookup_key(kind, amount)}; run scripts/stripe_setup.py")
    return prices.data[0].id


@functools.lru_cache(maxsize=1)
def product_id() -> str:
    """The Support product (created by scripts/stripe_setup.py); 'Other' amounts are priced on it inline."""
    for p in client().v1.products.list(params={"limit": 100, "active": True}).data:
        if (p.metadata.to_dict() if p.metadata else {}).get("app") == PRODUCT_TAG:
            return p.id
    raise SupportError("no Stripe Support product; run scripts/stripe_setup.py")


def checkout_url(kind: str, amount: int, other: bool = False) -> str:
    """Create a Checkout Session and return its URL (the browser is redirected there). `other` = a typed amount,
    priced inline on the Support product (monthly ones recur every month like the fixed amounts)."""
    if other:
        price_data = {"currency": "usd", "unit_amount": amount, "product": product_id()}
        if kind == "monthly":
            price_data["recurring"] = {"interval": "month"}
        item = {"price_data": price_data, "quantity": 1}
    else:
        item = {"price": price_id(kind, amount), "quantity": 1}
    params = {
        "mode": "subscription" if kind == "monthly" else "payment",
        "line_items": [item],
        "success_url": f"{SITE_URL}/support/thanks",
        "cancel_url": f"{SITE_URL}/support?canceled=1",
        "integration_identifier": INTEGRATION_ID,
        "metadata": {"kind": kind, "amount_dollars": f"{amount / 100:.2f}", "other": "1" if other else "0"},
        # These are contributions, not sales of digital goods, so Stripe doesn't act as merchant
        # of record (Managed Payments is on by default for this account and needs a product tax code).
        "managed_payments": {"enabled": False},
    }
    if kind == "once":
        params["submit_type"] = "donate"
    session = client().v1.checkout.sessions.create(params=params)
    return session.url


def _amount(obj: dict):
    for k in ("amount_total", "amount_paid", "amount", "amount_refunded"):
        if obj.get(k) is not None:
            return obj[k]
    return None


def record(event) -> bool:
    """Verify-then-record is done by the caller; this stores one event once. Returns False for a repeat."""
    from app.db import pool
    o = event.data.object.to_dict()
    with pool.connection() as conn:
        cur = conn.execute(
            """INSERT INTO stripe_events (event_id, type, created, livemode, object_id, mode, amount, currency, status,
                                          subscription, customer)
               VALUES (%s, %s, to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING""",
            (event.id, event.type, event.created, bool(event.livemode), o.get("id"), o.get("mode"), _amount(o),
             o.get("currency"), o.get("payment_status") or o.get("status"),
             o.get("subscription") if isinstance(o.get("subscription"), str) else None,
             o.get("customer") if isinstance(o.get("customer"), str) else None))
        return cur.rowcount == 1


def thank_and_notify(o: dict) -> None:
    """A new paid contribution: a thank-you to the donor (spread the word, join the FURP Open Data Alliance) and a
    quiet note to us. Sent once per Stripe event (record() drops repeats). The donor's address is used only to
    send these and is not stored."""
    from app import mailer
    from app.config import INFO_EMAIL
    details = o.get("customer_details") or {}
    email, name = details.get("email"), (details.get("name") or "").strip()
    amount = _amount(o)
    how = "a month" if o.get("mode") == "subscription" else "one time"
    gift = f"{dollars(amount)} {how}" if amount else "your contribution"
    if email:
        hello = f"Dear {name.split()[0]}," if name else "Hello,"
        text = (f"{hello}\n\nThank you for supporting furp.org ({gift}). It keeps the public data explorer free, "
                "open source and ad-free, and it pays for the data we're adding next.\n\n"
                "Two ways to help even more:\n"
                "- Spread the word: tell a colleague, a reporter or a researcher about furp.org, and cite us when "
                "you use the data.\n"
                "- Join the FURP Open Data Alliance: reply to this email and we'll add you. Alliance members hear "
                "about new datasets first and help decide what we open up next.\n\n"
                f"Stripe sends your receipt separately. Questions? Just reply.\n\nThe FURP Alliance\n{SITE_URL}\n")
        mailer.send({"From": mailer.address("info", "furp.org"), "To": email, "ReplyTo": INFO_EMAIL,
                     "Subject": "Thank you for supporting furp.org", "TextBody": text, "MessageStream": "outbound"})
    mailer.send({"From": mailer.address("info", "furp.org"), "To": INFO_EMAIL,
                 "Subject": f"New donor: {gift}",
                 "TextBody": f"New contribution: {gift}.\nDonor: {name or '(no name)'} <{email or 'no email'}>\n"
                             f"Stripe: {o.get('id')}{' (test mode)' if not o.get('livemode', True) else ''}\n",
                 "MessageStream": "outbound"})


def handle_webhook(payload: bytes, signature: str | None):
    """Verify the signature (raises ValueError or SignatureVerificationError), then record the event."""
    if not STRIPE_WEBHOOK_SECRET:
        raise SupportError("STRIPE_WEBHOOK_SECRET is not set")
    event = client().construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    new = record(event)
    o = event.data.object.to_dict()     # Stripe objects aren't dicts in this SDK
    if event.type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        log.info("support: %s %s payment_status=%s", event.type, o.get("mode"), o.get("payment_status"))
        if new and o.get("payment_status") == "paid":
            thank_and_notify(o)
    elif event.type in ("invoice.payment_failed", "charge.dispute.created", "radar.early_fraud_warning.created",
                        "charge.refunded", "customer.subscription.deleted"):
        log.warning("support: %s %s", event.type, o.get("id"))
    return event, new
