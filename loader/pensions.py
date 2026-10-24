"""Public pension funds' private equity commitments, fund by fund (owner, 2026-10-23).

- CalPERS: the Private Equity Program Fund Performance Review page (fund, vintage year, capital committed, cash in,
  cash out, cash out plus remaining value, net IRR, investment multiple, "As of" date). It's an HTML table, updated
  quarterly. History: every earlier version the Internet Archive kept of the page (2014 on), each with its as-of
  date. CalPERS's board investment committee packets carry only totals by vintage, not funds, so they add nothing
  fund by fund.
- CalSTRS: the Private Equity Portfolio Performance PDF (yearly, as of June 30; earlier March 31 or September 30):
  fund, vintage, committed, contributed, distributed, market value, since-inception IRR. Its multiple isn't printed:
  (distributed + market value) / contributed. History: the PDFs linked from the page now and in archived copies.

pension_commitments keeps every as-of date. match() links each fund to Form D offerings and Form ADV private funds
by name (legal endings ignored) and vintage year, with a confidence:
  high    the same name and the vintage within a year of the Form D's first filing (or the fund's first ADV year)
  medium  the same name, vintage not confirmed
  low     a near-identical name (trigram similarity 0.85 or more) and the vintage confirmed
Refreshed by the nightly job on the first of each month (both funds publish quarterly or yearly).

Usage: .venv/bin/python -m loader.pensions [calpers] [calstrs] [match]
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from loader import db

UA = "Mozilla/5.0 (furp.org research michael@furp.org)"
CALPERS_URLS = ["https://www.calpers.ca.gov/investments/about-investment-office/investment-organization/pep-fund-performance",
                "https://www.calpers.ca.gov/page/investments/about-investment-office/investment-organization/pep-fund-performance",
                "https://www.calpers.ca.gov/page/investments/asset-classes/private-equity/pep-fund-performance"]
CALSTRS_PAGE = "https://www.calstrs.com/private-equity-portfolio-performance"
CALSTRS_HISTORY = [
    "https://calstrs.com/files/5c3703f7c/CalSTRSPrivateEquityPerformanceReportFYE2024.pdf",
    "https://www.calstrs.com/files/428a22ee6/PrivateEquityPerformance-06302023.pdf",
    "https://www.calstrs.com/files/dde3f45f7/PrivateEquityPerformance-06302022.pdf",
]


def _get(url: str, tries: int = 3, timeout: int = 120) -> bytes | None:
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            time.sleep(5 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (attempt + 1))
    return None


def _num(v):
    v = (v or "").strip().replace("$", "").replace(",", "").replace("%", "").replace("x", "")
    if v in ("", "-", "N/M", "NM", "N/A", "n/a"):
        return None
    neg = v.startswith("(") and v.endswith(")")
    try:
        n = float(v.strip("()"))
    except ValueError:
        return None
    return -n if neg else n


def _asof(text: str) -> dt.date | None:
    m = re.search(r"[Aa]s of ([A-Z][a-z]+) (\d{1,2}), ?(\d{4})", text)
    if not m:
        return None
    try:
        d = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
    except ValueError:
        return None
    if d.day == 1 and d.month == 12:          # CalPERS once printed "December 1, 2018" for December 31
        d = d.replace(day=31)
    return d


def _store(pension: str, as_of: dt.date, rows: list[dict], url: str) -> int:
    from loader.recalls import core
    with db.connect() as conn:
        conn.execute("DELETE FROM pension_commitments WHERE pension = %s AND as_of = %s", (pension, as_of))
        seen = set()
        with conn.cursor() as cur, cur.copy("""COPY pension_commitments (pension, fund_name, fund_core, vintage, committed,
                                               cash_in, cash_out, total_value, net_irr, multiple, as_of, source_url) FROM STDIN""") as cp:
            for r in rows:
                if r["fund_name"] in seen:
                    continue
                seen.add(r["fund_name"])
                cp.write_row((pension, r["fund_name"][:300], core(r["fund_name"])[:300], r.get("vintage"), r.get("committed"),
                              r.get("cash_in"), r.get("cash_out"), r.get("total_value"), r.get("net_irr"), r.get("multiple"),
                              as_of, url[:500]))
        conn.execute("""INSERT INTO pension_sources (url, pension, as_of, rows) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (url) DO UPDATE SET as_of = excluded.as_of, rows = excluded.rows, loaded = now()""",
                     (url[:500], pension, as_of, len(seen)))
        conn.commit()
    return len(seen)


# --- CalPERS -----------------------------------------------------------------------------------------------------

def parse_calpers(page: str) -> tuple[dt.date | None, list[dict]]:
    tables = re.findall(r"<table.*?</table>", page, flags=re.S)
    if not tables:
        return None, []
    big = max(tables, key=len)

    def cells(r):
        return [re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<sup.*?</sup>|<[^>]+>", "", c))).strip()
                for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, flags=re.S)]
    out = []
    for r in re.findall(r"<tr.*?</tr>", big, flags=re.S):
        c = cells(r)
        if len(c) != 8 or c[0] in ("Fund", "") or not re.fullmatch(r"(19|20)\d\d", c[1]):
            continue
        out.append({"fund_name": c[0], "vintage": int(c[1]), "committed": _num(c[2]), "cash_in": _num(c[3]),
                    "cash_out": _num(c[4]), "total_value": _num(c[5]), "net_irr": _num(c[6]), "multiple": _num(c[7])})
    return _asof(re.sub(r"<[^>]+>", " ", page)), out


def calpers(status=print) -> int:
    """The live page when it answers, then every month's capture in the Internet Archive."""
    with db.connect() as conn:
        have = {r[0] for r in conn.execute("SELECT DISTINCT as_of FROM pension_commitments WHERE pension = 'CalPERS'").fetchall()}
        tried = {r[0] for r in conn.execute("SELECT url FROM pension_sources WHERE pension = 'CalPERS'").fetchall()}
    n = 0
    pages = []
    live = _get(CALPERS_URLS[0])
    if live:
        pages.append((CALPERS_URLS[0], live.decode("utf-8", "replace")))
    for url in CALPERS_URLS:
        cdx = _get("https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(
            {"url": url, "output": "json", "filter": "statuscode:200", "collapse": "timestamp:6"}), timeout=180)
        try:
            caps = json.loads(cdx or b"[]")[1:]
        except ValueError:
            caps = []
        for cap in caps:
            arch = f"https://web.archive.org/web/{cap[1]}id_/{cap[2]}"
            if arch in tried:
                continue
            data = _get(arch, timeout=180)
            time.sleep(1)
            if data:
                pages.append((arch, data.decode("utf-8", "replace")))
    for url, page in pages:
        as_of, rows = parse_calpers(page)
        if not as_of or len(rows) < 50:
            if url.startswith("https://web.archive.org"):
                with db.connect() as conn:       # remember empty captures so they aren't fetched again
                    conn.execute("INSERT INTO pension_sources (url, pension, rows) VALUES (%s, 'CalPERS', 0) ON CONFLICT DO NOTHING", (url,))
                    conn.commit()
            continue
        if as_of in have and not url.startswith("https://www.calpers"):
            with db.connect() as conn:
                conn.execute("INSERT INTO pension_sources (url, pension, as_of, rows) VALUES (%s, 'CalPERS', %s, %s) ON CONFLICT DO NOTHING",
                             (url, as_of, len(rows)))
                conn.commit()
            continue
        k = _store("CalPERS", as_of, rows, url)
        have.add(as_of)
        n += k
        status(f"pensions calpers: {as_of} {k} funds")
    status(f"pensions calpers: {len(have)} as-of dates")
    return n


# --- CalSTRS -----------------------------------------------------------------------------------------------------

_NUM = r"(-|\(?[\d,]+(?:\.\d+)?\)?|N/?M|NM)"
_ROW = re.compile(r"^(?P<name>.+?) ?(?P<vy>(?:19|20)\d\d) (?P<c>" + _NUM + r") (?P<p>" + _NUM + r") (?P<d>" + _NUM + r") (?P<mv>"
                  + _NUM + r") (?P<irr>" + _NUM + r")$")
_ROW4 = re.compile(r"^(?P<name>.+?) ?(?P<vy>(?:19|20)\d\d) (?P<c>" + _NUM + r") (?P<p>" + _NUM + r") (?P<d>" + _NUM + r") (?P<irr>"
                   + _NUM + r")$")


def parse_calstrs(pdf_bytes: bytes) -> tuple[dt.date | None, list[dict]]:
    import pdfplumber
    rows, text_all = [], []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text(x_tolerance=3) or ""
            text_all.append(t)
            for ln in t.splitlines():
                ln = re.sub(r"(?<=\s)(\d) (?=\d{1,2},\d{3})", r"\1", ln.strip())   # a lone digit split off: "7 0,000,000"
                m = _ROW.match(ln)
                if m:
                    g = m.groupdict()
                    mv = _num(g["mv"])
                elif (m := _ROW4.match(ln)):                                       # market value cell missing
                    g = m.groupdict()
                    mv = None
                else:
                    continue
                name = g["name"].strip()
                if not name or name.lower().startswith(("total", "description")):
                    continue
                paid, dist = _num(g["p"]), _num(g["d"])
                rows.append({"fund_name": name, "vintage": int(g["vy"]), "committed": _num(g["c"]), "cash_in": paid,
                             "cash_out": dist, "total_value": (dist or 0) + (mv or 0) if (dist or mv) else None,
                             "net_irr": _num(g["irr"]),
                             "multiple": round(((dist or 0) + (mv or 0)) / paid, 2) if paid else None})
    text = "\n".join(text_all)
    m = re.search(r"(?:as of|ended|ending)\s+([A-Z][a-z]+ \d{1,2}, ?\d{4}|\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    as_of = None
    if m:
        v = m.group(1)
        for fmt in ("%B %d, %Y", "%B %d,%Y", "%m/%d/%Y"):
            try:
                as_of = dt.datetime.strptime(v, fmt).date()
                break
            except ValueError:
                pass
    return as_of, rows


def _asof_from_url(url: str) -> dt.date | None:
    m = re.search(r"FYE(\d{4})", url)
    if m:
        return dt.date(int(m.group(1)), 6, 30)
    m = re.search(r"(\d{2})(\d{2})(\d{4})\.pdf", url)
    if m:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def calstrs(status=print) -> int:
    page = (_get(CALSTRS_PAGE) or b"").decode("utf-8", "replace")
    urls = [urllib.parse.urljoin(CALSTRS_PAGE, u) for u in re.findall(r'href="([^"]+\.pdf)"', page)
            if re.search(r"private.?equity", u, re.I)]
    with db.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT url FROM pension_sources WHERE pension = 'CalSTRS' AND rows > 0").fetchall()}
    n = 0
    for url in dict.fromkeys(urls + CALSTRS_HISTORY):
        if url in done:
            continue
        data = _get(url) or _get(f"https://web.archive.org/web/2026id_/{url}")
        if not data or not data.startswith(b"%PDF"):
            continue
        as_of, rows = parse_calstrs(data)
        as_of = as_of or _asof_from_url(url)
        if not as_of or len(rows) < 50:
            status(f"pensions calstrs: {url} parsed {len(rows)} rows, as of {as_of}: skipped")
            continue
        k = _store("CalSTRS", as_of, rows, url)
        n += k
        status(f"pensions calstrs: {as_of} {k} funds")
    return n


# --- matches -----------------------------------------------------------------------------------------------------

def match(status=print) -> int:
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("TRUNCATE pension_fund_matches")
        conn.execute("""CREATE TEMP TABLE pf AS SELECT DISTINCT ON (pension, fund_name) pension, fund_name, fund_core, vintage
                        FROM pension_commitments WHERE fund_core <> '' ORDER BY pension, fund_name, as_of DESC""")
        # Form D offerings (main offerings): core names, computed here, with the first filing's year.
        from loader.recalls import core
        offs = conn.execute("SELECT root_accession, issuer_name, extract(year FROM first_date)::int FROM sec_formd_offerings").fetchall()
        conn.execute("CREATE TEMP TABLE fo (key text, core text, year int)")
        with conn.cursor() as cur, cur.copy("COPY fo FROM STDIN") as cp:
            for k, nm, y in offs:
                c = core(nm)
                if c:
                    cp.write_row((k, c, y))
        funds = conn.execute("SELECT fund_id, min(fund_name), min(year) FROM adv_funds WHERE fund_id IS NOT NULL GROUP BY fund_id").fetchall()
        conn.execute("CREATE TEMP TABLE fa (key text, core text, year int)")
        with conn.cursor() as cur, cur.copy("COPY fa FROM STDIN") as cp:
            for k, nm, y in funds:
                c = core(nm)
                if c:
                    cp.write_row((k, c, y))
        for t in ("fo", "fa"):
            conn.execute(f"CREATE INDEX ON {t} (core)")
            conn.execute(f"CREATE INDEX ON {t} USING gin (core gin_trgm_ops)")
        n = 0
        for kind, t, slack in (("formd", "fo", 1), ("adv", "fa", 2)):
            # Exact names: high when the vintage fits, else medium.
            n += conn.execute(f"""INSERT INTO pension_fund_matches
                                  SELECT pf.pension, pf.fund_name, '{kind}', x.key,
                                         CASE WHEN pf.vintage IS NOT NULL AND x.year IS NOT NULL
                                                   AND x.year BETWEEN pf.vintage - {slack} AND pf.vintage + {slack}
                                              THEN 'high' ELSE 'medium' END, 1
                                  FROM pf JOIN {t} x ON x.core = pf.fund_core ON CONFLICT DO NOTHING""").rowcount
            # Near-identical names, only with a fitting vintage.
            n += conn.execute(f"""INSERT INTO pension_fund_matches
                                  SELECT pf.pension, pf.fund_name, '{kind}', x.key, 'low', round(similarity(x.core, pf.fund_core)::numeric, 2)
                                  FROM pf JOIN {t} x ON x.core % pf.fund_core AND x.core <> pf.fund_core
                                  WHERE similarity(x.core, pf.fund_core) >= 0.85 AND pf.vintage IS NOT NULL
                                    AND x.year BETWEEN pf.vintage - {slack} AND pf.vintage + {slack}
                                  ON CONFLICT DO NOTHING""").rowcount
        # "Fund IV" and "Fund V" are near-identical strings but different funds: a close match must have the same
        # numbers and roman numerals.
        mark = re.compile(r"\b(?:[ivxl]+|\d+)\b")
        names = {("fo", r[0]): r[1] for r in conn.execute("SELECT key, core FROM fo").fetchall()}
        names.update({("fa", r[0]): r[1] for r in conn.execute("SELECT key, core FROM fa").fetchall()})
        drop = []
        for pension, fund, kind, key, core_ in conn.execute("""SELECT m.pension, m.fund_name, m.kind, m.key, pf.fund_core
                                                              FROM pension_fund_matches m JOIN pf USING (pension, fund_name)
                                                              WHERE m.confidence = 'low'""").fetchall():
            other = names.get(("fo" if kind == "formd" else "fa", key), "")
            if set(mark.findall(core_)) != set(mark.findall(other)):
                drop.append((pension, fund, kind, key))
        for d in drop:
            conn.execute("DELETE FROM pension_fund_matches WHERE pension = %s AND fund_name = %s AND kind = %s AND key = %s", d)
        conn.commit()
        counts = conn.execute("SELECT kind, confidence, count(*) FROM pension_fund_matches GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    status("pensions match: " + ", ".join(f"{k} {c} {m:,}" for k, c, m in counts))
    return n


def run(status=print) -> None:
    for step in (calpers, calstrs):
        try:
            step(status)
        except Exception as e:  # noqa: BLE001
            status(f"pensions {step.__name__} failed: {type(e).__name__}: {e}")
    match(status)


if __name__ == "__main__":
    for s in sys.argv[1:] or ["run"]:
        globals()[s]()
