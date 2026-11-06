"""Every email signup and confirmation lands in the owner's daily email (owner, 2026-11-06)."""

from app import mailer, reporters


def test_signup_and_confirm_tell_the_owner(monkeypatch):
    seen = []
    monkeypatch.setattr(mailer, "notify_owner", lambda topic, subject, body, reply_to=None: seen.append((topic, subject, body)))
    reporters._tell_owner("Email signup", "a@b.org signed up from home (awaiting confirmation)")
    reporters._tell_owner("Email signup", "a@b.org confirmed (now active)")
    assert seen == [("Email signups", "Email signup", "a@b.org signed up from home (awaiting confirmation)"),
                    ("Email signups", "Email signup", "a@b.org confirmed (now active)")]
    src = open("app/reporters.py").read()
    assert src.index('_event(conn, "signup", sub_id, src)') < src.index('_tell_owner("Email signup", f"{email} signed up')
    assert '_tell_owner("Email signup", f"{email} confirmed (now active)")' in src


def test_a_failed_notice_never_breaks_the_signup(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(mailer, "notify_owner", boom)
    reporters._tell_owner("Email signup", "x")      # no exception
