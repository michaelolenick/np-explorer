"""Where the data lives, and downloading it.

IRS (2017 onward):  https://www.irs.gov/charities-non-profits/form-990-series-downloads
    lists yearly index_YYYY.csv files and the monthly/batched XML zips.
GivingTuesday mirror of the original AWS release (2011-2016 processing years):
    https://gt990datalake-rawdata.s3.amazonaws.com/  (EfileData/XmlFiles/{object_id}_public.xml
    plus an all-years index under Indices/990xmls/).
IRS Exempt Organizations Business Master File:
    https://www.irs.gov/pub/irs-soi/eo1.csv .. eo4.csv (plus eo_pr.csv, eo_xx.csv).
"""

from __future__ import annotations

import csv
import io
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from app.config import MIN_FREE_GB, RAW_DIR
from loader.status import disk_free_gb

IRS_PAGE = "https://www.irs.gov/charities-non-profits/form-990-series-downloads"
IRS_BASE = "https://apps.irs.gov/pub/epostcard/990/xml"
GT_BUCKET = "https://gt990datalake-rawdata.s3.amazonaws.com"
BMF_FILES = ["eo1", "eo2", "eo3", "eo4", "eo_pr", "eo_xx"]
BMF_URL = "https://www.irs.gov/pub/irs-soi/{name}.csv"
FIRST_IRS_YEAR = 2017       # earliest year the IRS itself still hosts
FIRST_YEAR = 2011           # earliest e-file XML year anywhere
UA = "np-explorer/1.0 (+https://strategystudio.org; nonprofit people search)"
FORMS = {"990", "990EZ", "990PF"}


class DiskFull(RuntimeError):
    pass


def _open(url: str, method: str = "GET", timeout: int = 60):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)


def check_disk() -> None:
    free = disk_free_gb()
    if free < MIN_FREE_GB:
        raise DiskFull(f"STOPPED: only {free:.1f} GB free on {RAW_DIR} (minimum {MIN_FREE_GB:.0f} GB). "
                       f"Free up space or attach a disk, then rerun; loading resumes where it stopped.")


def discover() -> dict[int, dict]:
    """Scrape the IRS downloads page: {year: {"index": url, "zips": [url, ...]}}."""
    with _open(IRS_PAGE) as r:
        html = r.read().decode("utf-8", "replace")
    years: dict[int, dict] = {}
    for url in sorted(set(re.findall(r'href="(https://apps\.irs\.gov/pub/epostcard/990/xml/[^"]+)"', html))):
        m = re.search(r"/xml/(\d{4})/([^/]+)$", url)
        if not m:
            continue
        year, name = int(m.group(1)), m.group(2)
        y = years.setdefault(year, {"index": None, "zips": []})
        if name.lower().endswith(".csv") and name.startswith("index_"):
            y["index"] = url
        elif name.lower().endswith(".zip"):
            y["zips"].append(url)
    for year, y in years.items():
        if not y["index"]:
            y["index"] = f"{IRS_BASE}/{year}/index_{year}.csv"
    return years


def remote_size(url: str) -> int | None:
    try:
        with _open(url, method="HEAD") as r:
            n = r.headers.get("Content-Length")
            return int(n) if n else None
    except Exception:
        return None


def download(url: str, dest: Path, retries: int = 4) -> Path:
    """Download url to dest unless a complete copy is already there."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = remote_size(url)
    if dest.exists() and (size is None or dest.stat().st_size == size):
        return dest
    check_disk()
    if size and disk_free_gb() - size / 2**30 < MIN_FREE_GB:
        raise DiskFull(f"STOPPED: downloading {dest.name} ({size / 2**30:.1f} GB) would leave less than "
                       f"{MIN_FREE_GB:.0f} GB free. Free up space, then rerun.")
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            with _open(url, timeout=120) as r, open(part, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if size and part.stat().st_size != size:
                raise IOError(f"short download {part.stat().st_size} of {size}")
            part.rename(dest)
            return dest
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))
    return dest


def fetch_bytes(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries):
        try:
            with _open(url, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    raise AssertionError("unreachable")


def year_dir(year: int) -> Path:
    return RAW_DIR / str(year)


def index_path(year: int) -> Path:
    return year_dir(year) / f"index_{year}.csv"


def index_counts(year: int) -> int:
    """How many 990/990-EZ/990-PF returns the year's index lists."""
    p = index_path(year)
    if not p.exists():
        return 0
    n = 0
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if (row.get("RETURN_TYPE") or row.get("FormType") or "").strip() in FORMS:
                n += 1
    return n


def index_object_ids(year: int) -> set[str]:
    """Object ids of the 990/990-EZ/990-PF returns a year's index lists."""
    p = index_path(year)
    if not p.exists():
        return set()
    out = set()
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if (row.get("RETURN_TYPE") or "").strip() in FORMS and (row.get("OBJECT_ID") or "").strip():
                out.add(row["OBJECT_ID"].strip())
    return out


# --- GivingTuesday mirror (2011-2016) -----------------------------------------

def gt_latest_index_url() -> str:
    keys = []
    token = None
    while True:
        q = "list-type=2&prefix=Indices/990xmls/index_all_years_efiledata_xmls_created_on_"
        if token:
            q += "&continuation-token=" + urllib.parse.quote(token)
        body = fetch_bytes(f"{GT_BUCKET}/?{q}").decode()
        keys += [k for k in re.findall(r"<Key>([^<]+\.csv)</Key>", body)]
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", body)
        if not m:
            break
        token = m.group(1)
    return f"{GT_BUCKET}/{sorted(keys)[-1]}"


def build_gt_indexes(years=range(FIRST_YEAR, FIRST_IRS_YEAR)) -> dict[int, int]:
    """Stream the GivingTuesday all-years index once; write index_YYYY.csv for pre-2017 years.

    Rows are bucketed by the object_id's leading year (the IRS processing year),
    which is how the original AWS release was organized.
    """
    years = set(years)
    if all(index_path(y).exists() for y in years):
        return {y: sum(1 for _ in open(index_path(y))) - 1 for y in years}
    check_disk()
    url = gt_latest_index_url()
    writers, files, counts = {}, {}, {}
    for y in years:
        year_dir(y).mkdir(parents=True, exist_ok=True)
        files[y] = open(index_path(y).with_suffix(".csv.part"), "w", newline="")
        writers[y] = csv.writer(files[y])
        writers[y].writerow(["OBJECT_ID", "EIN", "RETURN_TYPE", "TAX_PERIOD", "URL"])
        counts[y] = 0
    seen = set()
    with _open(url, timeout=600) as r:
        reader = csv.DictReader(io.TextIOWrapper(r, encoding="utf-8", errors="replace", newline=""))
        for row in reader:
            oid = (row.get("ObjectId") or "").strip()
            if len(oid) < 4 or not oid[:4].isdigit():
                continue
            y = int(oid[:4])
            if y not in years or row.get("FormType") not in FORMS or oid in seen:
                continue
            seen.add(oid)
            writers[y].writerow([oid, row.get("EIN"), row.get("FormType"), row.get("TaxPeriod"),
                                 row.get("URL") or f"{GT_BUCKET}/EfileData/XmlFiles/{oid}_public.xml"])
            counts[y] += 1
    for y in years:
        files[y].close()
        index_path(y).with_suffix(".csv.part").rename(index_path(y))
    return counts


def gt_index_rows(year: int) -> list[dict]:
    with open(index_path(year), newline="") as f:
        return list(csv.DictReader(f))

