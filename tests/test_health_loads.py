"""The nightly-load check (scripts/health.py): a loader's count line is not an error (owner, 2026-11-28)."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("health_mod", ROOT / "scripts" / "health.py")
health = importlib.util.module_from_spec(spec)
sys.modules["health_mod"] = health
spec.loader.exec_module(health)


def _other(tmp_path, lines):
    log = tmp_path / "nightly.log"
    log.write_text("\n".join([health.NIGHTLY_MARK + "2026-11-28 07:30 UTC ==="] + lines) + "\n")
    return next(c for c in health.check_loads(log) if c.key == "load other")


def test_count_lines_with_failed_zero_pass(tmp_path):
    c = _other(tmp_path, ['{"companies": 25, "filings": 25, "built": 0, "cached": 25, "failed": 0, "no_filing": 0}',
                          "{'companies': 1058, 'filings': 1126, 'built': 0, 'cached': 1126, 'failed': 0, 'no_filing': 3}"])
    assert c.ok


def test_a_real_error_still_fails(tmp_path):
    assert not _other(tmp_path, ["Traceback (most recent call last):"]).ok
    assert not _other(tmp_path, ["psycopg.errors.DeadlockDetected: deadlock detected", "Error: boom"]).ok
