"""GDELT 2.0 Events download-and-filter (owner, 2026-11-14), the events half of "news and events". Standalone like
gdelt_parse.py (python3 -I, no database): per day, the 96 files http://data.gdeltproject.org/gdeltv2/<stamp>.export.CSV.zip are
streamed in memory; events whose Actor1Name or Actor2Name is an organization name FURP knows (same dictionaries as the GKG
filter) are written to /bulk/gdelt/parsed/<day>.e.tsv.gz with an .edone marker. Event metadata only: id, date, actors, CAMEO code,
Goldstein scale, mention and article counts, tone, place, and the source URL. Terms and attribution as gdelt_parse.py.

Usage: python3 -I gdelt_events.py --from 20260101 --to 20260131 [--procs 2] [--order desc]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import os
import sys
import threading
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gdelt_parse as gp  # noqa: E402

BASE_X = gp.BASE


def parse_lines(lines, dic, stats, out) -> None:
    for raw in lines:
        stats["events"] += 1
        f = raw.rstrip("\n").split("\t")
        if len(f) < 61:
            continue
        c1 = gp.core(f[6]) if f[6] else ""
        c2 = gp.core(f[16]) if f[16] else ""
        k1 = " " in c1 and dic.has("orgs", c1)
        k2 = " " in c2 and dic.has("orgs", c2)
        if not (k1 or k2):
            continue
        url = f[60].strip()
        out.write("\t".join([f[0], f[1], c1 if k1 else "", c2 if k2 else "", f[6][:120], f[16][:120], f[26], f[30], f[31], f[33],
                             f[34], f[52][:160], f[53], url]) + "\n")
        stats["kept"] += 1


def do_day(args) -> dict:
    day, dpath, outd = args
    ymd = day.strftime("%Y%m%d")
    done = Path(outd) / f"{ymd}.edone"
    if done.exists():
        return json.loads(done.read_text())
    dic = gp.Dict(Path(dpath))
    stats = dict(day=ymd, events=0, kept=0, files=0, missing=0)
    t0 = time.time()
    tmp = Path(outd) / f"{ymd}.e.tmp"
    stamps = list(gp.day_stamps(day))
    box: dict = {}

    def pre(s):
        try:
            box[s] = gp.fetch(f"{BASE_X}{s}.export.CSV.zip")
        except Exception as e:  # noqa: BLE001
            box[s] = e

    with gzip.open(tmp, "wt", compresslevel=3, encoding="utf-8") as out:
        ths: dict = {}
        for i, s in enumerate(stamps):
            for j in range(i, min(i + 3, len(stamps))):
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
                        parse_lines(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="\n"), dic, stats, out)
    os.replace(tmp, Path(outd) / f"{ymd}.e.tsv.gz")
    stats["seconds"] = round(time.time() - t0, 1)
    done.write_text(json.dumps(stats))
    print(f"{time.strftime('%H:%M:%S')} gdelt events {ymd}: {stats['events']} events, {stats['kept']} kept, {stats['seconds']}s", flush=True)
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
    d0 = max(dt.datetime.strptime(a.d0, "%Y%m%d").date(), gp.FIRST_DAY)
    d1 = min(dt.datetime.strptime(a.d1, "%Y%m%d").date(), dt.date.today() - dt.timedelta(days=1))
    days = [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]
    if a.order == "desc":
        days.reverse()
    jobs = [(d, a.dict, a.out) for d in days if not (Path(a.out) / f"{d:%Y%m%d}.edone").exists()]
    print(f"gdelt events: {len(jobs)} days to do ({d0} to {d1})", flush=True)
    with ProcessPoolExecutor(a.procs) as ex:
        for _ in ex.map(do_day, jobs):
            pass


if __name__ == "__main__":
    main()
