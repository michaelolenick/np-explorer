"""GDELT 2.0 GKG download-and-filter (owner, 2026-11-14: news and events for people and organizations).

No database here, so it runs on either server (python3 -I, no imports from the app). For each day it fetches the 96
fifteen-minute GKG files (http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip), streams them in memory (the
zips are never kept: 170-400 GB a year), keeps only articles that name something FURP knows, and writes per day
  /bulk/gdelt/parsed/YYYYMMDD.a.tsv.gz   one row per kept article: aid, date, domain, url, title, lang, tone, themes
  /bulk/gdelt/parsed/YYYYMMDD.m.tsv.gz   one row per kept mention: aid, kind (o/p), name, offset, times, rule
  /bulk/gdelt/parsed/YYYYMMDD.done       JSON counts; its presence means the day is complete (restartable by day)
Metadata and links only: never article text.

A name is "known" when its normalised form is in the dictionaries built from the database by loader/gdelt.py (dict):
  orgs.u64      sorted 64-bit hashes of organization name cores (the xref engine's loader.recalls.core)
  pers_u.u64    person names that belong to exactly one FURP person cluster (full names, two or more words)
  pers_c.u64    person names shared by several clusters: kept only when the article also names a known organization
                (the corroboration the later match step needs; it checks the shared organization exactly)
  bitmap.bin    2^30-bit prefilter over all three, so most names cost one byte lookup

GDELT terms (https://www.gdeltproject.org/about.html#termsofuse): free for any use; any use or redistribution must
include a citation to the GDELT Project and a link to https://www.gdeltproject.org/. The pages say so.

Usage: python3 -I gdelt_parse.py --dict /bulk/gdelt/dict --out /bulk/gdelt/parsed --from 20260101 --to 20260131
       [--procs 3] [--order desc]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import gzip
import hashlib
import html
import io
import json
import mmap
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BASE = "http://data.gdeltproject.org/gdeltv2/"
UA = "furp.org data loader (info@furp.org)"
FIRST_DAY = dt.date(2015, 2, 18)
BITS = 30
MASK = (1 << BITS) - 1
LEGAL = {"inc", "incorporated", "llc", "l", "c", "co", "corp", "corporation", "company", "ltd", "limited", "lp",
         "llp", "plc", "pllc", "the"}
NOISE_THEMES = ("TAX_", "WB_", "EPU_", "UNGP_", "CRISISLEX_", "USPEC_", "SOC_POINTSOFINTEREST", "GENERAL_GOVERNMENT",
                "MEDIA_", "SOC_GENERALCRIME", "SELF_IDENTIFIED", "LEADER", "WB")
_nonalnum = re.compile(r"[^a-z0-9]+")
_title = re.compile(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", re.S)
_lang = re.compile(r"srclc:([a-z]{3})")


def h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def core(name: str) -> str:
    """loader.recalls.core, copied: "WinCo Foods, LLC" -> "winco foods"."""
    s = _strip(name).replace("&", " and ")
    s = re.split(r"\b(?:d/?b/?a|doing business as|a/?k/?a)\b", s)[0]
    words = _nonalnum.sub(" ", s).split()
    while words and words[-1] in LEGAL:
        words.pop()
    while words and words[0] == "the":
        words.pop(0)
    return " ".join(words)


def pnorm(name: str) -> str:
    """The person_clusters.name_norm form: lower case, apostrophes dropped, other punctuation a space."""
    s = _strip(name).replace("'", "").replace("’", "")
    return " ".join(_nonalnum.sub(" ", s).split())


class Dict:
    def __init__(self, d: Path):
        self.f = open(d / "bitmap.bin", "rb")
        self.bm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        self.arr = {}
        self.keep = []
        for k in ("orgs", "pers_u", "pers_c"):
            f = open(d / f"{k}.u64", "rb")
            m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            self.arr[k] = memoryview(m).cast("Q")

    def has(self, kind: str, s: str) -> bool:
        v = h64(s)
        i = v & MASK
        if not (self.bm[i >> 3] >> (i & 7)) & 1:
            return False
        a = self.arr[kind]
        j = bisect.bisect_left(a, v)
        return j < len(a) and a[j] == v


def _pairs(field: str):
    """V2Persons / V2Organizations: "Name,offset;Name,offset" -> {name: [offsets]} in first-seen order."""
    out: dict[str, list[int]] = {}
    for part in field.split(";"):
        if not part:
            continue
        name, _, off = part.rpartition(",")
        if not name:
            name, off = part, "0"
        try:
            o = int(off)
        except ValueError:
            o = 0
        out.setdefault(name, []).append(o)
    return out


def parse_lines(lines, dic: Dict, stats: dict, a_out, m_out) -> None:
    for raw in lines:
        stats["records"] += 1
        f = raw.rstrip("\n").split("\t")
        if len(f) < 16:
            continue
        orgs = {}
        for name, offs in _pairs(f[14]).items():
            c = core(name)
            if len(c) >= 3 and dic.has("orgs", c):
                orgs.setdefault(c, []).extend(offs)
        pers = {}
        for name, offs in _pairs(f[12]).items():
            n = pnorm(name)
            if n.count(" ") < 1:
                continue
            if dic.has("pers_u", n):
                pers.setdefault(n, [[], "u"])[0].extend(offs)
            elif orgs and dic.has("pers_c", n):
                pers.setdefault(n, [[], "c"])[0].extend(offs)
        if not orgs and not pers:
            continue
        url = f[4].strip()
        if not url:
            continue
        aid = h64(url) & 0x7FFFFFFFFFFFFFFF
        extras = f[26] if len(f) > 26 else ""
        m = _title.search(extras)
        title = html.unescape(m.group(1)).strip().replace("\t", " ").replace("\n", " ")[:300] if m else ""
        lm = _lang.search(f[25]) if len(f) > 25 else None
        lang = lm.group(1) if lm else "eng"
        tone = f[15].split(",", 1)[0]
        themes = []
        for t in f[7].split(";"):
            if t and not t.startswith(NOISE_THEMES) and t not in themes:
                themes.append(t)
                if len(themes) >= 8:
                    break
        a_out.write(f"{aid}\t{f[1]}\t{f[3]}\t{url}\t{title}\t{lang}\t{tone}\t{' '.join(themes)}\n")
        for c, offs in orgs.items():
            m_out.write(f"{aid}\to\t{c}\t{min(offs)}\t{len(offs)}\t\n")
        for n, (offs, rule) in pers.items():
            m_out.write(f"{aid}\tp\t{n}\t{min(offs)}\t{len(offs)}\t{rule}\n")
        stats["articles"] += 1
        stats["org_mentions"] += len(orgs)
        stats["person_mentions"] += len(pers)


def fetch(url: str, tries: int = 4) -> bytes | None:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 * (k + 1))
    raise RuntimeError("download failed: " + url)


def day_stamps(day: dt.date):
    for i in range(96):
        t = dt.datetime(day.year, day.month, day.day) + dt.timedelta(minutes=15 * i)
        yield t.strftime("%Y%m%d%H%M%S")


def do_day(args) -> dict:
    day, dpath, out = args
    ymd = day.strftime("%Y%m%d")
    done = Path(out) / f"{ymd}.done"
    if done.exists():
        return json.loads(done.read_text())
    dic = Dict(Path(dpath))
    stats = dict(day=ymd, records=0, articles=0, org_mentions=0, person_mentions=0, files=0, missing=0)
    t0 = time.time()
    tmp_a, tmp_m = Path(out) / f"{ymd}.a.tmp", Path(out) / f"{ymd}.m.tmp"
    stamps = list(day_stamps(day))
    box: dict[str, bytes | None] = {}

    def pre(s):  # prefetch thread
        try:
            box[s] = fetch(f"{BASE}{s}.gkg.csv.zip")
        except Exception as e:  # noqa: BLE001
            box[s] = e  # type: ignore[assignment]

    with gzip.open(tmp_a, "wt", compresslevel=3, encoding="utf-8") as a_out, \
            gzip.open(tmp_m, "wt", compresslevel=3, encoding="utf-8") as m_out:
        ths: dict[str, threading.Thread] = {}
        ahead = 3
        for i, s in enumerate(stamps):
            for j in range(i, min(i + ahead, len(stamps))):
                if stamps[j] not in ths:
                    th = threading.Thread(target=pre, args=(stamps[j],))
                    th.start()
                    ths[stamps[j]] = th
            ths[s].join()
            data = box.pop(s)
            if isinstance(data, Exception):
                raise data
            if data is None:
                stats["missing"] += 1
                continue
            stats["files"] += 1
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for nm in z.namelist():
                    with z.open(nm) as fh:
                        parse_lines(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="\n"), dic,
                                    stats, a_out, m_out)
    os.replace(tmp_a, Path(out) / f"{ymd}.a.tsv.gz")
    os.replace(tmp_m, Path(out) / f"{ymd}.m.tsv.gz")
    stats["seconds"] = round(time.time() - t0, 1)
    done.write_text(json.dumps(stats))
    print(f"{time.strftime('%H:%M:%S')} gdelt parse {ymd}: {stats['records']} records, {stats['articles']} kept, "
          f"{stats['org_mentions']} org and {stats['person_mentions']} person mentions, {stats['seconds']}s", flush=True)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default="/bulk/gdelt/dict")
    ap.add_argument("--out", default="/bulk/gdelt/parsed")
    ap.add_argument("--from", dest="d0", required=True)
    ap.add_argument("--to", dest="d1", required=True)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--order", default="desc")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    d0 = max(dt.datetime.strptime(a.d0, "%Y%m%d").date(), FIRST_DAY)
    d1 = min(dt.datetime.strptime(a.d1, "%Y%m%d").date(), dt.date.today() - dt.timedelta(days=1))
    days = [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]
    if a.order == "desc":
        days.reverse()
    jobs = [(d, a.dict, a.out) for d in days if not (Path(a.out) / f"{d:%Y%m%d}.done").exists()]
    print(f"gdelt parse: {len(jobs)} days to do ({d0} to {d1})", flush=True)
    with ProcessPoolExecutor(a.procs) as ex:
        for _ in ex.map(do_day, jobs):
            pass


if __name__ == "__main__":
    main()
