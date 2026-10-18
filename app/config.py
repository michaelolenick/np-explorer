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
