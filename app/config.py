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
CONTACT_EMAIL = "mfolenick@vstrat.ai"
MIN_FREE_GB = float(os.environ.get("NP_MIN_FREE_GB", "20"))
