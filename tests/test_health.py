"""The nightly site check's repair rules (scripts/health.py; owner, 2026-10-28): a restart only for process failures,
a failed load gets its missing files and one retry, three nights in a row is STUCK, the latest nightly run only."""

import datetime as dt
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("health", ROOT / "scripts/health.py")
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)
Check = health.Check


def test_restart_only_for_process_failures():
    checks = [Check("page /", "Page /", False, "missing x", "restart_app", kind="content"),
              Check("page /slow", "Page /slow", False, "slow: 10.1s", "restart_app", kind="perf"),
              Check("app", "The app", False, "HTTP 502", "restart_app", kind="process"),
              Check("page /b", "Page /b", False, "HTTP 500", "restart_app", kind="process")]
    planned = health.plan(checks)
    assert [c.key for c in planned] == ["app"]                  # one restart, and never for content or speed
    assert "would not fix" in health.describe(Check("p", "P", False, "", None, kind="perf"))


def test_latest_nightly_run_only(tmp_path):
    log = tmp_path / "nightly.log"
    log.write_text("2026-10-25 06:55 uspto PVGPATDIS failed: FileNotFoundError: [Errno 2] No such file or directory: "
                   "'/home/michael/data/uspto/api_calls.log'\nTraceback (most recent call last):\n"
                   "=== nightly run 2026-10-28 05:00 UTC ===\nbuybacks failed\n")
    got = {c.key: c for c in health.check_loads(log)}
    assert got["load uspto"].ok and got["load other"].ok        # last week's errors are not tonight's
    assert not got["load buybacks"].ok and got["load buybacks"].repair == "retry_load"
    assert got["load buybacks"].arg[1][-2:] == ["loader.buybacks", "run"]


def test_failed_load_names_the_missing_file(tmp_path):
    log = tmp_path / "nightly.log"
    log.write_text("=== nightly run 2026-10-28 05:00 UTC ===\n2026-10-28 06:55 uspto ECORSEXC failed: FileNotFoundError: "
                   "[Errno 2] No such file or directory: '/home/michael/data/uspto/api_calls.log'\n")
    c = {c.key: c for c in health.check_loads(log)}["load uspto"]
    assert not c.ok and c.arg[2] == ["/home/michael/data/uspto/api_calls.log"]
    assert health.describe(c).startswith("create /home/michael/data/uspto/api_calls.log, then retry the load once")


def test_retry_success_clears_the_check(tmp_path, monkeypatch):
    log = tmp_path / "nightly.log"
    log.write_text("=== nightly run 2026-10-28 05:00 UTC ===\npensions failed\n")
    monkeypatch.setattr(health, "LOGS", tmp_path)
    ok, msg = health.repair_load("pensions", ["true"], [])
    assert ok and "retried the load: done" in msg
    assert {c.key: c for c in health.check_loads(log)}["load pensions"].ok
    ok, msg = health.repair_load("pensions", ["false"], [])
    assert not ok and "escalated" in msg
    health.RETRIED.clear()


def test_create_paths_only_where_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "CREATABLE", (str(tmp_path) + "/",))
    ok, msg = health.create_paths([str(tmp_path / "a/b"), str(tmp_path / "logs/calls.log"), "/etc/furp-test"])
    assert (tmp_path / "a/b").is_dir() and (tmp_path / "logs/calls.log").is_file()
    assert not ok and "not allowed to create /etc/furp-test" in msg


def test_three_nights_is_stuck():
    c = Check("page /x", "Page /x", False, "missing y", kind="content")
    day = dt.date(2026, 10, 25)
    h = health.update_state({}, [c], day)
    h = health.update_state(h, [c], day + dt.timedelta(days=1))
    h = health.update_state(h, [c], day + dt.timedelta(days=1))         # a second run the same day adds nothing
    h = health.update_state(h, [c], day + dt.timedelta(days=2))
    assert h["page /x"] == {"first": "2026-10-25", "last": "2026-10-27", "nights": 3, "what": "Page /x"}
    subject, text = health.report([c], {}, [c], h)
    assert subject.startswith("1 STUCK since 2026-10-25, Site check, 1 problem")
    assert "STUCK, failing 3 nights in a row since 2026-10-25" in text
    assert health.update_state(h, [], day + dt.timedelta(days=3)) == {}     # fixed: forgotten
    gap = health.update_state(h, [c], day + dt.timedelta(days=5))           # a gap starts over
    assert gap["page /x"]["nights"] == 1


def test_dry_run_report_plans_without_repairing():
    c = Check("page /", "Page /", False, "missing z", None, kind="content")
    subject, text = health.report([c], {}, [c], {}, dry_run=True)
    assert text.startswith("DRY RUN") and "Would repair: none: a content problem" in text
