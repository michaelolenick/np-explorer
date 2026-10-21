"""Contact form: validation, spam checks, rate limit, and the email it builds."""

import pytest

from app import contact


def good(**kw):
    raw = {"name": "  Ada  Lovelace ", "email": " ada@example.org ", "topic": "Feedback",
           "message": "  Nice site.\r\nThanks.  "}
    raw.update(kw)
    return raw


def test_valid_form_is_trimmed():
    form, errors = contact.validate(good())
    assert errors == []
    assert form == {"name": "Ada Lovelace", "email": "ada@example.org", "topic": "Feedback",
                    "message": "Nice site.\nThanks."}


def test_name_is_optional():
    assert contact.validate(good(name=""))[1] == []


@pytest.mark.parametrize("kw, problem", [
    ({"email": ""}, "email"),
    ({"email": "not-an-email"}, "email"),
    ({"email": "a@b.c\nBcc: x@y.z"}, "email"),
    ({"topic": "Spam"}, "topic"),
    ({"topic": ""}, "topic"),
    ({"message": "   "}, "message"),
    ({"message": "x" * 5001}, "5,000"),
    ({"message": "see http://a.example http://b.example www.c.example"}, "links"),
])
def test_invalid(kw, problem):
    errors = contact.validate(good(**kw))[1]
    assert any(problem in e for e in errors), errors


def test_two_links_are_fine():
    assert contact.validate(good(message="http://a.example and https://b.example"))[1] == []


def test_control_characters_dropped():
    form, _ = contact.validate(good(message="hi\x00there\x1b"))
    assert form["message"] == "hithere"


def test_token_round_trip_and_forgery():
    t = contact.issue_token(now=1000)
    assert contact.token_age(t, now=1010) == 10
    ts, sig = t.split(".")
    assert contact.token_age(f"{int(ts) - 60}.{sig}", now=1010) is None   # tampered timestamp
    assert contact.token_age("", now=1010) is None
    assert contact.token_age("garbage", now=1010) is None


def test_bot_checks():
    t = contact.issue_token(now=1000)
    assert not contact.is_bot({"t": t}, now=1005)
    assert contact.is_bot({"t": t, "website": "http://spam.example"}, now=1005)   # honeypot
    assert contact.is_bot({"t": t}, now=1002)                                    # under 3 seconds
    assert contact.is_bot({"t": t}, now=1000 + 2 * 86400)                        # stale form
    assert contact.is_bot({}, now=1005)                                          # no token


def test_rate_limit_five_per_hour():
    lim = contact.HourlyLimit()
    assert all(lim.allow("1.2.3.4", now=i) for i in range(5))
    assert not lim.allow("1.2.3.4", now=10)
    assert lim.allow("5.6.7.8", now=10)          # other IPs unaffected
    assert lim.allow("1.2.3.4", now=3600)        # first send has aged out


def test_truncate_ip():
    assert contact.truncate_ip("203.0.113.77") == "203.0.113.0/24"
    assert contact.truncate_ip("2001:db8:abcd:12::1") == "2001:db8:abcd::/48"
    assert contact.truncate_ip("nonsense") == "unknown"


def test_subject_and_body():
    form = contact.validate(good(message="Line one\n" + "y" * 100))[0]
    s = contact.subject(form)
    assert s.startswith("[furp.org] Feedback: Line one y")
    assert len(s) == len("[furp.org] Feedback: ") + 60
    body = contact.text_body(form, "2026-10-17T10:00:00+00:00", "203.0.113.77")
    assert "Email: ada@example.org" in body and "203.0.113.0/24" in body and "203.0.113.77" not in body


def test_send_failure_keeps_message(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(contact, "FAILED_LOG", tmp_path / "logs" / "contact-failed.jsonl")
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "")
    form = contact.validate(good(message="secret body text"))[0]
    assert contact.send(form, "203.0.113.77") is False
    saved = (tmp_path / "logs" / "contact-failed.jsonl").read_text()
    assert "secret body text" in saved
    assert oct((tmp_path / "logs" / "contact-failed.jsonl").stat().st_mode)[-3:] == "600"
    assert "secret body text" not in caplog.text


def test_send_posts_to_postmark(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"ErrorCode": 0}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, json=json, headers=headers)
        return Resp()

    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token")
    monkeypatch.setattr(contact.httpx, "post", fake_post)
    form = contact.validate(good())[0]
    assert contact.send(form, "203.0.113.77") is True
    assert sent["url"] == "https://api.postmarkapp.com/email"
    assert sent["headers"]["X-Postmark-Server-Token"] == "test-token"
    j = sent["json"]
    assert (j["From"], j["To"], j["ReplyTo"], j["MessageStream"]) == (
        "info@furp.org", "info@furp.org", "ada@example.org", "outbound")
