"""Settings, read from the environment (.env in development and under systemd)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5432/nonprofits")
DATA_DIR = Path(os.environ.get("NP_DATA_DIR", "/data"))
RAW_DIR = DATA_DIR / "raw"
XML_DIR = DATA_DIR / "xml"
LOG_DIR = Path(os.environ.get("NP_LOG_DIR", "/var/log/np-explorer"))
SITE_URL = os.environ.get("SITE_URL", "https://furp.org")
GITHUB_URL = "https://github.com/michaelolenick/np-explorer"
# prod only on the production VM: usage stats are collected and the daily report is sent only
# there. Anything else (the dev box, a laptop) collects nothing; scripts/report.py needs --dry-run.
APP_ENV = os.environ.get("APP_ENV", "dev")
# Google Analytics 4 (owner, 2026-10-20). Production only, so dev traffic never reaches the reports; set
# GA_MEASUREMENT_ID in .env to override (empty turns it off).
GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "G-9DBTED3NDF" if APP_ENV == "prod" else "")
# Not counted in usage stats: comma-separated IPs or CIDRs (yours, the servers). Loopback never is.
INTERNAL_IPS = os.environ.get("INTERNAL_IPS", "")
USAGE_RETENTION_DAYS = int(os.environ.get("USAGE_RETENTION_DAYS", "90"))
# The daily report (scripts/report.py).
REPORT_TO = os.environ.get("REPORT_TO", "michael@furp.org")
REPORT_FROM = os.environ.get("REPORT_FROM", "reports@furp.org")       # falls back to the old domain: app/mailer.py
REPORT_SUBJECT = os.environ.get("REPORT_SUBJECT", "FURP Report: {summary} ({day})")
REPORT_FREQUENCY = os.environ.get("REPORT_FREQUENCY", "daily")          # daily | weekly (Mondays)
REPORT_WAIT_MINUTES = int(os.environ.get("REPORT_WAIT_MINUTES", "180"))  # for the nightly loaders to finish
NL_REPORT_MODEL = os.environ.get("NL_REPORT_MODEL", "claude-sonnet-5-5")
# Stripe, for the Support page (app/support.py). Without a secret key the page shows contact only.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PORTAL_URL = os.environ.get("STRIPE_PORTAL_URL", "")
# IndexNow (loader/indexnow.py): unset means the nightly job skips it (the dev box).
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "")
INDEXNOW_MAX = int(os.environ.get("INDEXNOW_MAX", "50000"))
# Corrections, removal requests and data problems; everything else.
CORRECTIONS_EMAIL = "corrections@furp.org"
INFO_EMAIL = "info@furp.org"
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", INFO_EMAIL)
# The BETA tag by the logo and the beta line in the footer (owner, 2026-10-29): set NP_BETA=0 (or flip the default) to
# take both off.
BETA = os.environ.get("NP_BETA", "1").lower() in ("1", "true", "yes")
# Deep Queries (app/deep.py): emails that can run one, one per line in this file. It's read again whenever it
# changes, so adding someone needs no deploy or restart. Without the file, the default list.
DEEP_ALLOWLIST_FILE = os.environ.get("DEEP_ALLOWLIST_FILE", str(Path.home() / "furp-config" / "deep_queries_allow.txt"))
DEEP_ALLOWLIST_DEFAULT = os.environ.get("DEEP_ALLOWLIST", "mfolenick@gmail.com,mfolenick@vstrat.ai")
MIN_FREE_GB = float(os.environ.get("NP_MIN_FREE_GB", "20"))

# Leaderboards (app/boards.py). Launch scope: a filing counts when the organization
# reported at least this much revenue or these assets that year.
BOARD_MIN_REVENUE = int(os.environ.get("NP_BOARD_MIN_REVENUE", "10000000"))
BOARD_MIN_ASSETS = int(os.environ.get("NP_BOARD_MIN_ASSETS", "50000000"))
# Person-level boards (Revolving Door, Family Plan) are built but not shown until this is true.
BOARDS_PERSON_LEVEL = os.environ.get("NP_BOARDS_PERSON_LEVEL", "false").lower() in ("1", "true", "yes")
