"""Form-submission sources (round 3, owner-authorized): Indiana Gateway Form 100R employee compensation and the IBHE
Illinois public university salary search. Both are ASP.NET WebForms pages; exports come from postbacks.

Fetch:   python forms.py fetch in_gateway|il_ibhe        (network only; files + manifest under ~/unipay-data/<key>/)
Verify:  python forms.py verify in_gateway|il_ibhe       (no DB; per-file counts vs the publisher's stated count, pay parsing, samples)
Loading goes through load.py (SPECS here is merged into parsers.SPECS).

Politeness: one request at a time, >= 3 s between requests, descriptive User-Agent; no login, no CAPTCHA.
"""
import collections
import csv
import datetime as dt
import html
import io
import json
import random
import re
import sys
import time

import httpx

from common import DATA, UA, _robots_ok, sha256_file, to_num
from fetch import manifest, save_manifest

UTC = dt.timezone.utc


def comps(d):
    return {k: v for k, v in d.items() if v is not None}


def hidden(text):
    """All hidden <input> fields of an ASP.NET page (__VIEWSTATE, __EVENTVALIDATION, control client state ...)."""
    out = {}
    for m in re.finditer(r'<input[^>]+type="hidden"[^>]*>', text):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            out[html.unescape(n.group(1))] = html.unescape(v.group(1)) if v else ""
    return out


def options(text, name):
    m = re.search(r'<select[^>]*name="%s"[^>]*>(.*?)</select>' % re.escape(name), text, re.S)
    if not m:
        return []
    return [(a, html.unescape(b).replace("\xa0", " ").strip())
            for a, b in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', m.group(1))]


class Session:
    """One cookie session, one request at a time, fixed minimum delay between requests."""

    def __init__(self, delay=3.0):
        self.c = httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=600)
        self.delay, self.last, self.text, self.url = delay, 0.0, "", None

    def _wait(self):
        w = self.delay - (time.time() - self.last)
        if w > 0:
            time.sleep(w)
        self.last = time.time()

    def _send(self, method, url, keep=True, **kw):
        if not _robots_ok(url):
            raise PermissionError(f"robots.txt disallows {url}")
        for attempt in range(5):
            self._wait()
            try:
                r = self.c.request(method, url, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                r.raise_for_status()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code and code not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise
                print(f"  retry {attempt + 1} ({code or type(e).__name__}) {url}", flush=True)
                time.sleep(30 * 2 ** attempt)
        if keep and "html" in r.headers.get("content-type", ""):
            self.text, self.url = r.text, str(r.url)
        return r

    def get(self, url, **kw):
        return self._send("GET", url, **kw)

    def post(self, url, data, keep=True):
        return self._send("POST", url, keep=keep, data=data)

    def form(self, **extra):
        d = hidden(self.text)
        d.update(extra)
        return d


def save_bytes(key, name, content, url, notes):
    d = DATA / key
    d.mkdir(parents=True, exist_ok=True)
    dest = d / name
    tmp = d / (name + ".part")
    tmp.write_bytes(content)
    tmp.rename(dest)
    m = manifest(key)
    m["files"][name] = {"url": url, "retrieved_at": dt.datetime.now(UTC).isoformat(), "sha256": sha256_file(dest),
                        "bytes": dest.stat().st_size, "notes": notes}
    save_manifest(key, m)


# ---------------------------------------------------------------- Indiana Gateway (Form 100R)
GW = "https://gateway.ifionline.org/report_builder/"
GW_START = GW + "Default2.aspx?rptType=employComp&rptVer=a"
GW_Y, GW_C, GW_U = "ReportViewer1$ctl04$ctl03$ddValue", "ReportViewer1$ctl04$ctl05$ddValue", "ReportViewer1$ctl04$ctl07$ddValue"
# every public higher-education unit listed under the report's 'State' county (the other State units are agencies/boards)
IN_UNITS = ["Ball State University", "Indiana State University", "Indiana University", "Ivy Tech Community College",
            "Purdue University", "University of Southern Indiana", "Vincennes University"]
IN_AGREEMENT = ("Gateway terms (IC 5-14-3-3(f)), accepted by the owner: information including names of government employees "
                "obtained by viewing, printing or downloading will not be used for commercial or political purposes")


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def fetch_in_gateway():
    """Employee Compensation report (SSRS ReportViewer): year -> county 'State' -> unit -> View Report, then the viewer's
    own CSV export URL (the export icon). One CSV per unit per calendar year. No login; the report pages present the
    IC 5-14-3-3(f) non-commercial-use terms as text, which the owner accepted."""
    s = Session(delay=3)
    s.get(GW_START)
    s.post(GW_START, s.form(__EVENTTARGET="ctl00$ContentPlaceHolder1$lknbtnEmployComp", __EVENTARGUMENT=""))
    rurl = s.url
    years = [(v, t) for v, t in options(s.text, GW_Y) if t.isdigit()]
    state = next(v for v, t in options(s.text, GW_C) if t == "State")
    for yv, yt in years:
        todo = [u for u in IN_UNITS if f"in_gw_{yt}_{_slug(u)}.csv" not in manifest("in_gateway")["files"]]
        if not todo:
            print("  have", yt)
            continue
        s.post(rurl, s.form(**{GW_Y: yv, GW_C: "0", GW_U: "0", "__EVENTTARGET": GW_Y, "__EVENTARGUMENT": ""}))
        s.post(rurl, s.form(**{GW_Y: yv, GW_C: state, GW_U: "0", "__EVENTTARGET": GW_C, "__EVENTARGUMENT": ""}))
        units = {t: v for v, t in options(s.text, GW_U)}
        for unit in todo:
            if unit not in units:
                print(f"  !! {yt}: unit {unit} not listed", flush=True)
                continue
            d = s.form(**{GW_Y: yv, GW_C: state, GW_U: units[unit], "ReportViewer1$ctl04$ctl00": "View Report"})
            d.pop("__EVENTTARGET", None)
            s.post(rurl, d)
            eb = re.search(r'ExportUrlBase":"([^"]+)"', s.text)
            if not eb:
                print(f"  !! {yt} {unit}: no export URL", flush=True)
                continue
            r = s.get("https://gateway.ifionline.org" + json.loads('"' + eb.group(1) + '"') + "CSV", keep=False)
            stated = re.search(rb"returned ([\d,]+) records", r.content)
            name = f"in_gw_{yt}_{_slug(unit)}.csv"
            save_bytes("in_gateway", name, r.content, GW_START,
                       notes=f"Employee Compensation report, year {yt}, county 'State', unit '{unit}'; SSRS CSV export "
                             f"(ReportViewer OpType=Export&Format=CSV) after an ASP.NET postback; publisher states "
                             f"{stated.group(1).decode() if stated else '?'} records. {IN_AGREEMENT}")
            print(f"  in_gateway {yt} {unit}: {len(r.content):,} bytes, stated {stated.group(1).decode() if stated else '?'}", flush=True)


def _gw_rows(path):
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    stated = re.search(r"returned ([\d,]+) records", raw)
    rows = list(csv.reader(io.StringIO(raw)))
    hi = next(i for i, r in enumerate(rows) if len(r) >= 6 and r[1] == "first_name")
    return rows[hi], rows[hi + 1:], (int(stated.group(1).replace(",", "")) if stated else None)


def parse_in_gateway(path, fname):
    yr, slug = re.match(r"in_gw_(\d{4})_(.+)\.csv$", fname).groups()
    inst = next(u for u in IN_UNITS if _slug(u) == slug)
    hdr, body, _ = _gw_rows(path)
    for i, r in enumerate(body, 1):
        if not any(c.strip() for c in r):
            continue
        cells = dict(zip(hdr, r))
        name = (cells.get("first_name") or "").strip() or None
        tot = to_num(cells.get("total_compensation"))
        yield dict(institution=inst, person_name=name, title=(cells.get("job_title") or "").strip() or None,
                   department=(cells.get("Department") or "").strip() or None, base_pay=None, other_pay=None, total_pay=tot,
                   pay_components=comps({"total_compensation": tot, "calendar_year": int(yr),
                                         "work_location": (cells.get("Textbox14") or "").strip() or None,
                                         "note": "one row per position line as certified on Form 100R (people with several "
                                                 "positions have several rows)"}),
                   fiscal_year=int(yr), raw={"row": i, "cells": cells})


# ---------------------------------------------------------------- IBHE public university salary search
IBHE = "https://salarysearch.ibhe.org/search.aspx"
IBHE_P = "ctl00$ContentPlaceHolder1$"
IBHE_INST = {  # IBHE label -> label already used by other staged sources (Gray Book, Post-Dispatch, ISU PDFs)
    "University of Illinois Urbana/Champaign": "University of Illinois Urbana-Champaign",
    "University of Illinois Chicago": "University of Illinois Chicago",
    "University of Illinois Springfield": "University of Illinois Springfield",
    "U of I - System Office": "University of Illinois System Offices",
}


def fetch_il_ibhe():
    """One 'Download Data' export per fiscal year with [All Institutions] / [All Positions]: GET the form, then a search
    postback and the export postback (returns an HTML table served as application/ms-excel)."""
    s = Session(delay=4)
    s.get(IBHE)
    years = [v for v, t in options(s.text, IBHE_P + "ddlstYear") if v.isdigit()]
    for y in sorted(years):
        name = f"il_ibhe_fy{y}.xls.html"
        if name in manifest("il_ibhe")["files"]:
            print("  have", name)
            continue
        base = {IBHE_P + "ddlstYear": y, IBHE_P + "lstInstitutions": "000000",
                IBHE_P + "tconSearchParam$tpnlByPos$lstJobPositions": "0"}
        s.get(IBHE)
        s.post(IBHE, s.form(**base, __EVENTTARGET=IBHE_P + "btnSearch", __EVENTARGUMENT=""))
        r = s.post(IBHE, s.form(**base, __EVENTTARGET=IBHE_P + "btnExport", __EVENTARGUMENT=""), keep=False)
        if "excel" not in r.headers.get("content-type", ""):
            print(f"  !! FY{y}: unexpected content type {r.headers.get('content-type')}", flush=True)
            continue
        save_bytes("il_ibhe", name, r.content, IBHE,
                   notes=f"FY{y}, [All Institutions], [All Positions]; 'Download Data' ASP.NET postback export "
                         f"({r.headers.get('content-disposition')}); HTML table served as application/ms-excel")
        print(f"  il_ibhe FY{y}: {len(r.content):,} bytes", flush=True)
        time.sleep(10)  # extra pause between years


_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


def _cell(x):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip()


def parse_il_ibhe(path, fname):
    fy = int(re.search(r"fy(\d{4})", fname).group(1))
    t = path.read_text(encoding="utf-8", errors="replace")
    rows = _TR.findall(t)
    hdr = [_cell(c) for c in _TD.findall(rows[0])]
    want = ["Institution/System Office", "Name", "Position", "Title", "Base Salary", "Additional Compensation"]
    if hdr != want:
        raise ValueError(f"{fname}: unexpected header {hdr}")
    for i, r in enumerate(rows[1:], 1):
        c = [_cell(x) for x in _TD.findall(r)]
        if len(c) != 6:
            raise ValueError(f"{fname}: row {i} has {len(c)} cells")
        inst_pub, name, pos, title, base_t, add_t = c
        base, add = to_num(base_t), to_num(add_t)
        inst = IBHE_INST.get(inst_pub, inst_pub.replace("/", "-"))
        yield dict(institution=inst, person_name=name or None, title=title or None, department=None,
                   base_pay=base, other_pay=add, total_pay=None if base is None else round(base + (add or 0), 2),
                   pay_components=comps({"base_salary": base, "additional_compensation": add, "position_category": pos or None,
                                         "institution_as_published": inst_pub if inst != inst_pub else None,
                                         "total_pay_computed": "base_salary + additional_compensation" if base is not None else None}),
                   fiscal_year=fy, raw={"row": i, "cells": dict(zip(want, c))})


# ---------------------------------------------------------------- specs
SPECS = {
    "in_gateway": dict(state="IN", system="Indiana Gateway Form 100R Certified Report of Public Employment and Compensation (state universities and colleges)",
                       catalog_url_like="%gateway.ifionline.org%", parse=parse_in_gateway,
                       notes="all 7 public higher-education units filing Form 100R under the 'State' county (Ball State, Indiana State, Indiana "
                             "University, Ivy Tech, Purdue, Southern Indiana, Vincennes), every year offered (2012-2025); one row per position line "
                             "as certified (several rows per person when they held several positions); total_pay = total compensation for the "
                             "calendar year as reported by the unit; fiscal_year = that calendar year (Form 100R is calendar-year); campus/work "
                             "city in pay_components.work_location. " + IN_AGREEMENT),
    "il_ibhe": dict(state="IL", system="Illinois Board of Higher Education public university salary search (all 12 public universities)",
                    catalog_url_like="%salarysearch.ibhe.org%", parse=parse_il_ibhe,
                    notes="administrators and faculty (excludes graduate assistants and civil service staff) as submitted by the universities; "
                          "one export per fiscal year FY2010-2025 ([All Institutions]/[All Positions]); base_pay = base salary, other_pay = "
                          "additional compensation, total_pay = their sum (computed); IBHE position category in pay_components; University "
                          "of Illinois labels aligned with the Gray Book source (as-published label kept)"),
}
FETCHERS = {"in_gateway": fetch_in_gateway, "il_ibhe": fetch_il_ibhe}


def verify(key, nsample=15):
    """Per file: parsed rows vs the publisher's stated count (Gateway) / table rows (IBHE), pay parse failures, years, sample."""
    m = manifest(key)
    rnd = random.Random(7)
    tot = 0
    for fname in sorted(m["files"]):
        path = DATA / key / fname
        rows = list(SPECS[key]["parse"](path, fname))
        tot += len(rows)
        stated = _gw_rows(path)[2] if key == "in_gateway" else len(_TR.findall(path.read_text(errors="replace"))) - 1
        nopay = sum(1 for r in rows if r["total_pay"] is None and r["base_pay"] is None)
        bad = [r for r in rows if r["total_pay"] is None and any(re.search(r"\d", v or "") for k, v in r["raw"]["cells"].items()
                                                                  if k in ("total_compensation", "Base Salary"))]
        noname = sum(1 for r in rows if not r["person_name"])
        inst = collections.Counter(r["institution"] for r in rows)
        print(f"== {fname}: rows={len(rows)} stated={stated} {'OK' if stated == len(rows) else 'MISMATCH'} no-pay={nopay} "
              f"pay-parse-failures={len(bad)} no-name={noname} fy={sorted(set(r['fiscal_year'] for r in rows))} inst={len(inst)}", flush=True)
        for r in bad[:3]:
            print("   parse failure:", r["raw"])
        for r in rnd.sample(rows, min(2, len(rows))):
            print("   ", r["institution"], "|", r["person_name"], "|", r["title"], "|", r["department"], "|", r["base_pay"], r["other_pay"],
                  r["total_pay"], "||", json.dumps(r["raw"]["cells"])[:200])
    print("total rows", tot)


if __name__ == "__main__":
    cmd, keys = sys.argv[1], sys.argv[2:]
    for k in keys:
        if cmd == "fetch":
            FETCHERS[k]()
        elif cmd == "verify":
            verify(k)
