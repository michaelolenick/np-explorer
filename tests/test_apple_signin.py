"""Sign in with Apple for the iOS app (owner, 2026-10-30): token verification against Apple's keys, the login
route, and the apple-app-site-association file for universal links. No network: Apple's keys are faked."""

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from starlette.testclient import TestClient

from app import accounts, main


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def apple():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": "test-kid", "use": "sig", "alg": "RS256",
           "n": _b64(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")), "e": _b64(pub.e.to_bytes(3, "big"))}

    def token(claims: dict, kid: str = "test-kid", alg: str = "RS256", signer=key) -> str:
        head = _b64(json.dumps({"alg": alg, "kid": kid}).encode())
        body = _b64(json.dumps(claims).encode())
        sig = signer.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{head}.{body}.{_b64(sig)}"

    return {"key": key, "jwk": jwk, "token": token}


@pytest.fixture(autouse=True)
def fake_apple_keys(monkeypatch, apple):
    monkeypatch.setattr(accounts, "apple_keys", lambda force=False: [apple["jwk"]])


def _claims(**over):
    c = {"iss": "https://appleid.apple.com", "aud": "org.furp.app", "sub": "001234.abcdef", "exp": time.time() + 600,
         "email": "Someone@PrivateRelay.AppleID.com", "email_verified": "true"}
    c.update(over)
    return c


def test_valid_token_is_accepted(apple):
    claims = accounts.verify_apple_token(apple["token"](_claims()))
    assert claims and claims["sub"] == "001234.abcdef" and claims["email"].startswith("Someone@")


def test_bad_tokens_are_rejected(apple):
    t = apple["token"]
    assert accounts.verify_apple_token("") is None
    assert accounts.verify_apple_token("not.a.token") is None
    assert accounts.verify_apple_token(t(_claims(aud="com.someone.else"))) is None        # another app's token
    assert accounts.verify_apple_token(t(_claims(iss="https://accounts.google.com"))) is None
    assert accounts.verify_apple_token(t(_claims(exp=time.time() - 5))) is None             # expired
    assert accounts.verify_apple_token(t(_claims(), kid="unknown-kid")) is None             # no such key
    assert accounts.verify_apple_token(t(_claims(), alg="none")) is None
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert accounts.verify_apple_token(t(_claims(), signer=other)) is None                # right kid, wrong key
    head, body, sig = t(_claims()).split(".")
    tampered = _b64(json.dumps(_claims(email="attacker@example.com")).encode())
    assert accounts.verify_apple_token(f"{head}.{tampered}.{sig}") is None


def test_login_route_rejects_garbage_without_touching_the_database():
    client = TestClient(main.app)          # no `with`: keeps the shared pool open
    r = client.post("/auth/apple", data={"identityToken": "garbage", "next": "/deep"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?error=apple"
    r = client.post("/auth/apple", data={}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?error=apple"


def test_login_route_logs_in_a_verified_apple_user(apple, monkeypatch):
    seen = {}

    def fake_login(conn, email, method, name, request, next_url):
        from fastapi.responses import RedirectResponse
        seen.update(email=email, method=method, name=name, next=next_url)
        return RedirectResponse(next_url, status_code=303)

    class FakeConn:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(accounts, "_login", fake_login)
    monkeypatch.setattr(accounts.db, "conn", lambda: FakeConn())
    client = TestClient(main.app)
    r = client.post("/auth/apple", data={"identityToken": apple["token"](_claims()), "givenName": "Ada", "familyName": "Lovelace",
                                         "next": "/deep"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/deep"
    assert seen == {"email": "someone@privaterelay.appleid.com", "method": "apple", "name": "Ada Lovelace", "next": "/deep"}
    # an unverified email never logs in
    r = client.post("/auth/apple", data={"identityToken": apple["token"](_claims(email_verified="false"))}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=apple"


def test_apple_app_site_association():
    r = TestClient(main.app).get("/.well-known/apple-app-site-association")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    body = r.json()
    app_id = body["applinks"]["details"][0]["appIDs"][0]
    assert app_id.endswith(".org.furp.app") and body["webcredentials"]["apps"] == [app_id]
    assert {"/": "*"} in body["applinks"]["details"][0]["components"]
