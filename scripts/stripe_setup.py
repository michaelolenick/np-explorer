#!/usr/bin/env python3
"""Set up Stripe for the Support page. Idempotent: run it again any time, on each box.

Creates (or finds) the "Support Strategy Studio" product, one price per amount (lookup keys
support-monthly-<dollars> and support-once-<dollars>), the webhook endpoint at
<SITE_URL>/stripe/webhook, and a customer portal with a login link for managing monthly
support. The webhook signing secret and the portal link are written to .env; nothing secret
is printed. Uses the keys in .env, so test keys set up test mode and live keys live mode.

Usage: .venv/bin/python scripts/stripe_setup.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import support  # noqa: E402
from app.config import SITE_URL, STRIPE_SECRET_KEY  # noqa: E402

ENV = ROOT / ".env"


def set_env(key: str, value: str) -> None:
    text = ENV.read_text()
    line = f"{key}={value}"
    text = re.sub(rf"^{key}=.*$", line, text, flags=re.M) if re.search(rf"^{key}=", text, re.M) else \
        text.rstrip("\n") + f"\n{line}\n"
    ENV.write_text(text)


def main() -> int:
    if not STRIPE_SECRET_KEY:
        print("STRIPE_SECRET_KEY is not set in .env", file=sys.stderr)
        return 1
    mode = "live" if STRIPE_SECRET_KEY.startswith(("sk_live", "rk_live")) else "test"
    c = support.client().v1

    found = [p for p in c.products.list(params={"limit": 100, "active": True}).data
             if (p.metadata or {}).get("app") == support.PRODUCT_TAG]
    product = found[0] if found else c.products.create(params={
        "name": support.PRODUCT_NAME, "metadata": {"app": support.PRODUCT_TAG},
        "description": "Keeps strategystudio.org free, open source and ad-free."})
    print(f"[{mode}] product: {'found' if found else 'created'} {product.id}")

    for kind, amounts in (("monthly", support.MONTHLY), ("once", support.ONCE)):
        for amount in amounts:
            key = support.lookup_key(kind, amount)
            if c.prices.list(params={"lookup_keys": [key], "active": True, "limit": 1}).data:
                print(f"[{mode}] price {key}: found")
                continue
            params = {"product": product.id, "currency": "usd", "unit_amount": amount * 100, "lookup_key": key,
                      "nickname": f"${amount} a month" if kind == "monthly" else f"${amount} one time"}
            if kind == "monthly":
                params["recurring"] = {"interval": "month"}
            c.prices.create(params=params)
            print(f"[{mode}] price {key}: created")

    url = f"{SITE_URL}/stripe/webhook"
    hooks = [w for w in c.webhook_endpoints.list(params={"limit": 100}).data if w.url == url]
    if hooks:
        c.webhook_endpoints.update(hooks[0].id, params={"enabled_events": support.EVENTS})
        print(f"[{mode}] webhook {url}: found, events updated (signing secret unchanged)")
    else:
        hook = c.webhook_endpoints.create(params={"url": url, "enabled_events": support.EVENTS,
                                                  "description": "strategystudio.org Support page"})
        set_env("STRIPE_WEBHOOK_SECRET", hook.secret)
        print(f"[{mode}] webhook {url}: created; signing secret written to .env")

    configs = [p for p in c.billing_portal.configurations.list(params={"limit": 100}).data
               if (p.metadata or {}).get("app") == support.PRODUCT_TAG]
    portal = configs[0] if configs else c.billing_portal.configurations.create(params={
        "metadata": {"app": support.PRODUCT_TAG},
        "business_profile": {"headline": "Manage your support for Strategy Studio",
                             "privacy_policy_url": f"{SITE_URL}/privacy"},
        "features": {"subscription_cancel": {"enabled": True, "mode": "immediately"},
                     "payment_method_update": {"enabled": True},
                     "invoice_history": {"enabled": True},
                     "customer_update": {"enabled": True, "allowed_updates": ["email"]}},
        "login_page": {"enabled": True}})
    if portal.login_page and portal.login_page.url:
        set_env("STRIPE_PORTAL_URL", portal.login_page.url)
    print(f"[{mode}] customer portal: {'found' if configs else 'created'}; login link written to .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
