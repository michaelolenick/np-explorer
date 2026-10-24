#!/usr/bin/env python3
"""Daily usage report for furp.org: compute, write (Claude, checked), save, email.

Production only (APP_ENV=prod). Cron: /etc/cron.d/np-report at 07:00 server time
(America/Chicago). Waits for the nightly loaders (their lock) up to REPORT_WAIT_MINUTES.
REPORT_FREQUENCY=weekly sends on Mondays only, covering the previous seven days.

Usage:
    .venv/bin/python scripts/report.py                     # yesterday, email it (production)
    .venv/bin/python scripts/report.py --dry-run           # write reports/<day>.dry-run.txt only
    .venv/bin/python scripts/report.py --date 2026-10-16 --dry-run --no-llm
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import report  # noqa: E402
from app.config import APP_ENV, RAW_DIR, REPORT_FREQUENCY, REPORT_SUBJECT, REPORT_WAIT_MINUTES, USAGE_RETENTION_DAYS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("np.report")


def loaders_running() -> bool:
    lock = RAW_DIR / ".loader.lock"
    if not lock.exists():
        return False
    with open(lock) as f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=date.fromisoformat, help="last day of the window (default: yesterday)")
    ap.add_argument("--dry-run", action="store_true", help="write the report to a file; no email, no database writes")
    ap.add_argument("--no-llm", action="store_true", help="numbers only, no narrative")
    args = ap.parse_args()

    if APP_ENV != "prod" and not args.dry_run:
        print(f"APP_ENV={APP_ENV}: reports are sent from production only. Use --dry-run here.", file=sys.stderr)
        return 2
    now = datetime.now(report.CHICAGO)
    weekly = REPORT_FREQUENCY == "weekly"
    if weekly and not args.date and not args.dry_run and now.weekday() != 0:
        log.info("REPORT_FREQUENCY=weekly and today isn't Monday: nothing to send")
        return 0
    days = 7 if weekly else 1
    day = args.date or (now.date() - timedelta(days=1))

    notes = []
    if not args.dry_run:
        waited = 0
        while loaders_running() and waited < REPORT_WAIT_MINUTES:
            time.sleep(60)
            waited += 1
        if loaders_running():
            notes.append(f"Note: the nightly loaders were still running after a {REPORT_WAIT_MINUTES}-minute wait; "
                         "the data section may be incomplete.")

    with report.connect() as conn:
        m = report.compute(conn, day, days)
        comp = report.comparisons(conn, day, days)
        prev = report.previous_report(conn, day)
        facts = {"metrics": m, "comparisons": comp, "constants": report.CONSTANTS,
                 "previous_report": prev, "commits_since_previous_report":
                     report.commits_since(prev["created_at"] if prev else None)}
        facts = json.loads(json.dumps(facts, default=str))
        text, status = (None, "--no-llm") if args.no_llm else report.narrative(facts)
        body = report.render(m, comp, text, status, notes)
        html_body = report.to_html(body)

        report.REPORTS.mkdir(exist_ok=True)
        stem = day.isoformat() + (".dry-run" if args.dry_run else "")
        (report.REPORTS / f"{stem}.txt").write_text(body)
        (report.REPORTS / f"{stem}.html").write_text(html_body)
        log.info("report written: %s (%s)", report.REPORTS / f"{stem}.txt", status)
        if args.dry_run:
            print(report.REPORTS / f"{stem}.txt")
            return 0

        metrics_json = json.dumps(m, default=str)
        conn.execute("""INSERT INTO daily_stats (day, metrics) VALUES (%s, %s)
                        ON CONFLICT (day) DO UPDATE SET metrics = excluded.metrics, computed_at = now()""",
                     (day, json.dumps({"core": m["core"], "full": json.loads(metrics_json)})))
        c = m.get("core") or {}

        def n(k):
            return f"{c[k]:,}" if isinstance(c.get(k), (int, float)) else "no"
        summary = (f"{n('human_visitors')} visitors, {n('searches')} searches, {n('server_5xx')} server errors"
                   if c.get("human_visitors") is not None else "daily report")
        subject = REPORT_SUBJECT.format(day=day.isoformat(), summary=summary)
        from app import mailer
        queued = mailer.notify_owner("Daily report", subject.replace("FURP Report: ", ""), body)
        ok, info = (mailer.send_digest(log.info), "sent in the daily batch") if queued else report.send(subject, body, html_body)
        log.info("report email: %s", info) if ok else log.error("report email failed (report kept on disk): %s", info)
        conn.execute("""INSERT INTO report_history (day, status, metrics, recommendations, narrative)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (day) DO UPDATE SET status = excluded.status, metrics = excluded.metrics,
                            recommendations = excluded.recommendations, narrative = excluded.narrative,
                            created_at = now()""",
                     (day, ("sent" if ok else "send_failed") + ("" if text else "_numbers_only"), metrics_json,
                      report.section(text, "THREE RECOMMENDATIONS") if text else None, text))
        for table in ("events", "searches"):
            conn.execute(f"DELETE FROM {table} WHERE ts < now() - make_interval(days => %s)", (USAGE_RETENTION_DAYS,))
        conn.execute("DELETE FROM visitors WHERE last_seen < now() - interval '1 year'")   # the cookie's lifetime
        conn.commit()
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
