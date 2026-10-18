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
SITE_URL = os.environ.get("SITE_URL", "https://strategystudio.org")
GITHUB_URL = "https://github.com/michaelolenick/np-explorer"
# prod only on the production VM: usage stats are collected and the daily report is sent only
# there. Anything else (the dev box, a laptop) collects nothing; scripts/report.py needs --dry-run.
APP_ENV = os.environ.get("APP_ENV", "dev")
# Not counted in usage stats: comma-separated IPs or CIDRs (yours, the servers). Loopback never is.
INTERNAL_IPS = os.environ.get("INTERNAL_IPS", "")
USAGE_RETENTION_DAYS = int(os.environ.get("USAGE_RETENTION_DAYS", "90"))
# The daily report (scripts/report.py).
REPORT_TO = os.environ.get("REPORT_TO", "michael@strategystudio.org")
REPORT_FROM = os.environ.get("REPORT_FROM", "reports@strategystudio.org")
REPORT_SUBJECT = os.environ.get("REPORT_SUBJECT", "Strategy Studio daily: {day}")
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
CORRECTIONS_EMAIL = "corrections@strategystudio.org"
INFO_EMAIL = "info@strategystudio.org"
MIN_FREE_GB = float(os.environ.get("NP_MIN_FREE_GB", "20"))

# Leaderboards (app/boards.py). Launch scope: a filing counts when the organization
# reported at least this much revenue or these assets that year.
BOARD_MIN_REVENUE = int(os.environ.get("NP_BOARD_MIN_REVENUE", "10000000"))
BOARD_MIN_ASSETS = int(os.environ.get("NP_BOARD_MIN_ASSETS", "50000000"))
# Person-level boards (Revolving Door, Family Plan) are built but not shown until this is true.
BOARDS_PERSON_LEVEL = os.environ.get("NP_BOARDS_PERSON_LEVEL", "false").lower() in ("1", "true", "yes")
