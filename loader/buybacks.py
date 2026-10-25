"""Share buybacks and the insider selling around them. Steps (each one can be run alone; run() does them all):

1. fsds: the SEC's Financial Statement Data Sets (quarterly, 2009 onward): every 10-K, 10-Q, 20-F and 40-F's
   buyback spending (PaymentsForRepurchaseOfCommonStock, else PaymentsForRepurchaseOfEquity), net income
   (NetIncomeLoss, else ProfitLoss) and repurchase authorizations (StockRepurchaseProgramAuthorizedAmount1 and
   ...RemainingAuthorizedRepurchaseAmount1), whole company only (no segments or co-registrants).
2. compute: sec_buybacks, one row per company per quarter (qtrs 1) and fiscal year (qtrs 4). Cash flow figures
   are year-to-date, so a quarter is the year-to-date figure minus the one three months earlier (derived);
   restated figures replace earlier ones (the latest filing wins).
3. plans: 10b5-1 flags on Form 4 filings from the Insider Transactions Data Sets: the filing's 10b5-1 checkbox
   (from April 2023) or a footnote or remark saying the trades were made under a Rule 10b5-1 plan.
4. announcements: 8-K filings announcing a new or larger repurchase authorization (EDGAR full-text search, by
   phrase), per company that reports buybacks.
5. months: the monthly issuer repurchase table (Item 2 of a 10-Q, Item 5 of a 10-K: shares bought, average price,
   shares bought under announced plans, what remains authorized), parsed from the filing's own document, for
   filings of the last three years that report buyback spending.
6. links and sales: companies to lobbying clients and PACs (same normalized name), and sec_buyback_sales: every
   open-market sale (Form 4 code S) by an insider, with the company's buybacks that quarter and the most recent
   buyback announcement in the 30 days before.

Usage: .venv/bin/python -m loader.buybacks [step ...]
"""

from __future__ import annotations

import csv
import datetime as dt
import html as htmllib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from loader import db

FSDS = Path("/bulk/fsds")
FORM345 = Path("/bulk/form345")
FSDS_URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip"
F345_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip"
UA = "furp.org research michael@furp.org"
FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"}
TAGS = {"PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "NetIncomeLoss", "ProfitLoss",
        "StockRepurchaseProgramAuthorizedAmount1", "StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1"}
BUY = ("PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity")
NI = ("NetIncomeLoss", "ProfitLoss")
MONTH_YEARS = 3            # monthly repurchase tables: filings of the last three years (owner, 2026-10-22)
HEAVY_MIN = 25_000_000     # a heavy buyback quarter: at least this much, and at least the company's average quarter
csv.field_size_limit(50_000_000)


def _get(url: str, tries: int = 5) -> bytes | None:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            time.sleep(0.15)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(5 * (attempt + 1))
    return None


def quarters(first: int = 2009) -> list[str]:
    t = dt.date.today()
    return [f"{y}q{q}" for y in range(first, t.year + 1) for q in range(1, 5) if (y, q) <= (t.year, (t.month - 1) // 3 + 1)]


def _date8(v: str | None) -> dt.date | None:
    v = (v or "").strip()
    return dt.date(int(v[:4]), int(v[4:6]), int(v[6:8])) if re.fullmatch(r"\d{8}", v) else None


def _tsv(z: zipfile.ZipFile, name: str):
    info = next((i for i in z.infolist() if i.filename.rsplit("/", 1)[-1].lower() == name.lower()), None)
    if info is None:
        return
    with z.open(info) as raw:
        r = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""), delimiter="\t",
                       quoting=csv.QUOTE_NONE)
        head = next(r)
        for row in r:
            yield dict(zip(head, row))


# --- 1. Financial Statement Data Sets --------------------------------------------------------------------------

def load_fsds_quarter(q: str, status=print) -> int:
    path = FSDS / f"{q}.zip"
    if not path.exists() or path.stat().st_size == 0:
        data = _get(FSDS_URL.format(q=q))
        if not data:
            return 0
        FSDS.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    z = zipfile.ZipFile(path)
    subs = {}
    for s in _tsv(z, "sub.txt"):
        if s.get("form") in FORMS:
            subs[s["adsh"]] = (s["adsh"], s["cik"].lstrip("0"), (s.get("name") or "")[:300], s["form"],
                               _date8(s.get("period")), int(s["fy"]) if (s.get("fy") or "").isdigit() else None,
                               s.get("fp") or None, _date8(s.get("filed")), s.get("instance") or None, q)
    facts = []
    for n in _tsv(z, "num.txt"):
        if n.get("tag") not in TAGS or n.get("adsh") not in subs or n.get("uom") != "USD":
            continue
        if n.get("coreg") or n.get("segments"):
            continue
        d = _date8(n.get("ddate"))
        try:
            v = float(n.get("value") or "")
        except ValueError:
            continue
        if d and (n.get("qtrs") or "").isdigit():
            facts.append((n["adsh"], n["tag"], d, int(n["qtrs"]), v))
    keep = {f[0] for f in facts}
    with db.connect() as conn:
        conn.execute("DELETE FROM sec_fin_facts WHERE adsh IN (SELECT adsh FROM sec_fin_subs WHERE quarter = %s)", (q,))
        conn.execute("DELETE FROM sec_fin_subs WHERE quarter = %s", (q,))
        with conn.cursor() as cur:
            with cur.copy("COPY sec_fin_subs (adsh, cik, name, form, period, fy, fp, filed, instance, quarter) FROM STDIN") as cp:
                for a in keep:
                    cp.write_row(subs[a])
            conn.execute("CREATE TEMP TABLE ff (LIKE sec_fin_facts) ON COMMIT DROP")
            with cur.copy("COPY ff FROM STDIN") as cp:
                for f in facts:
                    cp.write_row(f)
        conn.execute("INSERT INTO sec_fin_facts SELECT DISTINCT ON (adsh, tag, ddate, qtrs) * FROM ff "
                     "ON CONFLICT DO NOTHING")
        conn.execute("""INSERT INTO sec_buyback_runs (file, rows) VALUES (%s, %s)
                        ON CONFLICT (file) DO UPDATE SET loaded = now(), rows = excluded.rows""", (f"fsds {q}", len(facts)))
        conn.commit()
    status(f"buybacks fsds {q}: {len(keep):,} filings, {len(facts):,} values")
    return len(facts)


def fsds(status=print, only_new: bool = True) -> int:
    with db.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT file FROM sec_buyback_runs").fetchall()}
    qs = quarters()
    n = 0
    for q in qs:
        # The newest two quarters are reloaded: the SEC posts a quarter's set in pieces as filings come in.
        if only_new and f"fsds {q}" in done and q not in qs[-2:]:
            continue
        if only_new and q in qs[-2:]:
            (FSDS / f"{q}.zip").unlink(missing_ok=True)
        n += load_fsds_quarter(q, status)
    return n


# --- 2. quarters and years ----------------------------------------------------------------------------------

def _quarterize(vals: dict) -> dict:
    """{(ddate, qtrs): value} year-to-date figures -> {ddate: quarter value}, with a flag for derived ones."""
    out = {}
    for (d, k), v in vals.items():
        if k == 1:
            out[d] = (v, False)
    for (d, k), v in vals.items():
        if k < 2 or k > 4 or d in out:
            continue
        for (d2, k2), v2 in vals.items():
            if k2 == k - 1 and 75 <= (d - d2).days <= 105:
                out[d] = (v - v2, True)
                break
    return out


def compute(status=print) -> int:
    rows, auth = [], []
    with db.connect() as conn:
        cur = conn.execute("""SELECT s.cik, s.name, s.form, s.filed, f.adsh, f.tag, f.ddate, f.qtrs, f.value
                              FROM sec_fin_facts f JOIN sec_fin_subs s USING (adsh)
                              ORDER BY s.cik, s.filed, f.adsh""")
        def flush(cik, facts):
            if not facts:
                return
            name = facts[-1][0]
            latest = {}                   # (tag, ddate, qtrs) -> (value, adsh, filed, form): the latest filing wins
            for nm, form, filed, adsh, tag, d, k, v in facts:
                latest[(tag, d, k)] = (v, adsh, filed, form)
            by_tag = {}
            for (tag, d, k), x in latest.items():
                by_tag.setdefault(tag, {})[(d, k)] = x
            def pick(tags, k_want):
                res = {}
                for tag in reversed(tags):          # the preferred tag goes last and overwrites
                    vals = by_tag.get(tag, {})
                    if k_want == 4:
                        res.update({d: (x[0], False, x) for (d, k), x in vals.items() if k == 4})
                    else:
                        q = _quarterize({dk: x[0] for dk, x in vals.items()})
                        res.update({d: (v, der, vals.get((d, 1)) or next(x for (dd, kk), x in vals.items() if dd == d))
                                    for d, (v, der) in q.items()})
                return res
            for k in (1, 4):
                b, n = pick(BUY, k), pick(NI, k)
                for d in set(b) | set(n):
                    src = (b.get(d) or n.get(d))[2]
                    rows.append((cik, name, d, k, b[d][0] if d in b else None, n[d][0] if d in n else None,
                                 src[1], src[2], src[3], bool((b.get(d) or (0, False))[1])))
            a = by_tag.get("StockRepurchaseProgramAuthorizedAmount1", {})
            r = by_tag.get("StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1", {})
            for d in {d for (d, k) in a if k == 0} | {d for (d, k) in r if k == 0}:
                src = a.get((d, 0)) or r.get((d, 0))
                auth.append((cik, d, (a.get((d, 0)) or (None,))[0], (r.get((d, 0)) or (None,))[0], src[1], src[2]))
        cik, facts = None, []
        for row in cur:
            if row[0] != cik:
                flush(cik, facts)
                cik, facts = row[0], []
            facts.append(row[1:])
        flush(cik, facts)
        conn.execute("CREATE TEMP TABLE bb (LIKE sec_buybacks) ON COMMIT DROP")
        conn.execute("CREATE TEMP TABLE ba (LIKE sec_buyback_auth) ON COMMIT DROP")
        with conn.cursor() as c2:
            with c2.copy("COPY bb (cik, name, period_end, qtrs, buybacks, net_income, adsh, filed, form, derived) FROM STDIN") as cp:
                for r_ in rows:
                    cp.write_row(r_)
            with c2.copy("COPY ba FROM STDIN") as cp:
                for r_ in auth:
                    cp.write_row(r_)
        conn.execute("DELETE FROM sec_buybacks")
        conn.execute("INSERT INTO sec_buybacks SELECT DISTINCT ON (cik, period_end, qtrs) * FROM bb ORDER BY cik, period_end, qtrs, filed DESC")
        conn.execute("DELETE FROM sec_buyback_auth")
        conn.execute("INSERT INTO sec_buyback_auth SELECT DISTINCT ON (cik, ddate) * FROM ba ORDER BY cik, ddate, filed DESC")
        conn.commit()
        conn.execute("ANALYZE sec_buybacks")
        conn.commit()
    status(f"buybacks compute: {len(rows):,} company periods, {len(auth):,} authorization values")
    return len(rows)


# --- 5. monthly repurchase tables ----------------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9
ROLES = [("shares", r"total\s+(?:number\s+of\s+)?shares?\s+(?:of\s+common\s+stock\s+)?(?:re)?purchased|"
                    r"total\s+number\s+of\s+(?:common\s+)?shares|number\s+of\s+shares\s+(?:re)?purchased|"
                    r"shares\s+purchased|total\s+shares"),
         ("avg_price", r"average\s+price"),
         ("plan_shares", r"as\s+part\s+of\s+(?:the\s+|our\s+)?publicly|under\s+(?:the\s+)?(?:publicly\s+)?announced|"
                         r"part\s+of\s+(?:a\s+)?publicly|pursuant\s+to\s+(?:publicly|the)"),
         ("remaining", r"maximum|approximate\s+dollar|remaining|may\s+yet\s+be|that\s+may\s+yet")]
FOOT = re.compile(r"\(\s*(?:\d{1,2}|[a-z]|[ivx]+)\s*\)(?:\s*\(\s*(?:\d{1,2}|[a-z])\s*\))*|\*+")
NUM = re.compile(r"\(?-?\$?\s*\d[\d,]*(?:\.\d+)?\)?")
DATE_RX = re.compile(r"(?P<m>[A-Za-z]{3,9})\.?\s+(?P<d>\d{1,2}),?\s+(?P<y>\d{4})|(?P<mm>\d{1,2})/(?P<dd>\d{1,2})/(?P<yy>\d{2,4})")


def _text(el) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(el.text_content() or "")).strip()


def _dates(label: str, default_year: int | None):
    found = []
    for m in DATE_RX.finditer(label):
        if m.group("m"):
            mo = MONTHS.get(m.group("m").lower()[:4].rstrip(".")) or MONTHS.get(m.group("m").lower()[:3])
            if mo:
                try:
                    found.append(dt.date(int(m.group("y")), mo, int(m.group("d"))))
                except ValueError:
                    pass
        else:
            y = int(m.group("yy"))
            y = y + 2000 if y < 100 else y
            try:
                found.append(dt.date(y, int(m.group("mm")), int(m.group("dd"))))
            except ValueError:
                pass
    if found:
        end = found[-1]
        m = re.match(r"\s*(?:purchased\s+)?([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*(?:[–—-]|to|through)", label, re.I)
        if len(found) == 1 and m and MONTHS.get(m.group(1).lower()[:3]):
            mo = MONTHS[m.group(1).lower()[:3]]
            try:
                return dt.date(end.year - (1 if mo > end.month else 0), mo, int(m.group(2))), end
            except ValueError:
                pass
        return found[0], end
    m = re.search(r"(\d{1,2})/(\d{1,2})\s*(?:[–—-]|to|through)\s*(\d{1,2})/(\d{1,2})\b", label)
    if m and default_year:
        try:
            a, b = dt.date(default_year, int(m.group(1)), int(m.group(2))), dt.date(default_year, int(m.group(3)), int(m.group(4)))
            return (a.replace(year=a.year - 1) if a > b else a), b
        except ValueError:
            pass
    # "July 2024", "July", "July 1 - 31, 2024": a month name, the year from the label or the filing period.
    words = re.findall(r"[a-z]+", label.lower())
    mos = [MONTHS[w] for w in words if w in MONTHS and w != "may" or (w == "may" and len(words) <= 3)]
    ys = [int(y) for y in re.findall(r"\b(20\d\d|19\d\d)\b", label)]
    y = ys[-1] if ys else default_year
    if mos and y:
        import calendar
        start = dt.date(y, mos[0], 1)
        end = dt.date(y, mos[-1], calendar.monthrange(y, mos[-1])[1])
        return start, end
    return None, None


NUMCELL = re.compile(r"\(?\$?\s*-?\d[\d,]*(?:\.\d+)?\s*\)?\s*%?")
DASH = ("—", "-", "–", "N/A", "n/a", "NA", "Not applicable", "None", "none", "nil")


def _isnum(c: str) -> bool:
    return bool(NUMCELL.fullmatch(FOOT.sub("", c).strip()))


def _num(s: str) -> float | None:
    s = re.sub(r"\(\s*\d{1,2}\s*\)|\([a-z]\)|\*", "", s)           # footnote marks: (1), (a), *
    m = NUM.search(s)
    if not m:
        return None
    t = m.group(0)
    neg = t.startswith("(") and t.endswith(")")
    try:
        v = float(re.sub(r"[^\d.]", "", t))
    except ValueError:
        return None
    return -v if neg else v


def parse_tables(doc: bytes, period: dt.date | None) -> list[dict]:
    """The issuer repurchase table(s) in a 10-Q or 10-K document: one dict per row (month or total)."""
    import lxml.html
    try:
        root = lxml.html.fromstring(doc)
    except Exception:  # noqa: BLE001
        return []
    for el in root.iter("br", "div", "p", "span", "td", "th"):
        el.tail = " " + (el.tail or "")
    out = []
    for table in root.iter("table"):
        txt = _text(table).lower()
        if not re.search(r"average\s+price|price\s+paid", txt) or not re.search(r"publicly|announced|program|plan", txt):
            continue
        trs = table.findall(".//tr")
        rows = []
        for tr in trs:
            cells = [_text(td) for td in tr if td.tag in ("td", "th")]
            cells = [c for c in cells if c and c not in ("$", ")", "%") and not FOOT.fullmatch(c)]
            if cells:
                rows.append(cells)
        # Header: the rows before the first row that has a period label and numbers.
        header, hcells, body = [], [], []
        for cells in rows:
            nums = [c for c in cells[1:] if _isnum(c) or c in DASH]
            if not body and (len(nums) < 2 or not (_dates(cells[0], period.year if period else None)[0]
                                                   or "total" in cells[0].lower() or re.search(r"month|period", cells[0].lower()))):
                header.append(" ".join(cells))
                hcells.append(cells)
                continue
            body.append(cells)
        # A header written across rows ("Total Number" / "of Shares" / "Purchased"): read it column by column.
        multi = [c for c in hcells if len(c) >= 3]
        if len(multi) >= 2 and len({len(c) for c in multi}) == 1:
            cols = [" ".join(c[i] for c in multi) for i in range(len(multi[0]))]
            header = [" ".join(c) for c in hcells if len(c) < 3] + cols
        htext = " ".join(header).lower()
        found = []
        for role, rx in ROLES:
            m = re.search(rx, htext)
            if m:
                found.append((m.start(), role))
        found.sort()
        roles = [r for _, r in found]
        # "Total number of shares purchased as part of publicly announced plans" matches shares too: keep order.
        if "avg_price" not in roles:
            continue
        units = {}
        for i, (pos, role) in enumerate(found):
            seg = htext[pos:found[i + 1][0] if i + 1 < len(found) else len(htext)]
            units[role] = 1e9 if re.search(r"in\s+billions|\(billions\)", seg) else \
                1e6 if re.search(r"in\s+millions|\(millions\)|\$\s*millions", seg) else \
                1e3 if re.search(r"in\s+thousands|\(thousands\)|000s|000's", seg) else 1
        first_role = found[0][0] if found else len(htext)
        lead = htext[:first_role]
        whole = re.search(r"in\s+(billions|millions|thousands)[^)]*", lead)
        if whole and not re.search(r"dollars?\s+in|\$\s*in", lead):
            f = {"billions": 1e9, "millions": 1e6, "thousands": 1e3}[whole.group(1)]
            for role in ("shares", "plan_shares"):
                if units.get(role, 1) == 1 and not re.search(r"except\s+(?:for\s+)?(?:the\s+)?(?:number\s+of\s+)?shares?\b(?!\s+data|\s+amounts)|except\s+share\b", whole.group(0)):
                    units[role] = f
        if whole and units.get("remaining", 1) == 1:
            units["remaining"] = {"billions": 1e9, "millions": 1e6, "thousands": 1e3}[whole.group(1)]
        rpos = [i for i, (p, r) in enumerate(found) if r == "remaining"]
        remaining_dollars = bool(rpos) and bool(re.search(r"dollar|\$|value", htext[found[rpos[0] - 1][0] + 30 if rpos[0] else 0:]))
        for i in range(len(body) - 1):
            a, b = body[i][0], body[i + 1][0]
            if re.search(r"(?:[–—-]|\bto|through)\s*$", a) and DATE_RX.search(b) and not re.search(r"[–—-]|\bto\b|through", b):
                body[i][0] = body[i + 1][0] = a + " " + b
        for cells in body:
            label = cells[0]
            vals = []
            for c in cells[1:]:
                if c.strip() in DASH:
                    vals.append(0.0)
                elif _isnum(c):
                    vals.append(_num(c))
            if len(vals) < 2:
                continue
            if len(vals) == len(roles):
                rec = dict(zip(roles, vals))
            elif len(vals) == 4:
                rec = dict(zip(["shares", "avg_price", "plan_shares", "remaining"], vals))
            elif len(vals) == 3 and "remaining" not in roles:
                rec = dict(zip(["shares", "avg_price", "plan_shares"], vals))
            elif len(vals) == len(roles) - 1 and roles[-1] == "remaining":
                rec = dict(zip(roles[:-1], vals))           # a Total row with the last column left blank
            else:
                continue
            for k in list(rec):
                if k in ("shares", "plan_shares") and units.get(k, 1) > 1:
                    rec[k] *= units[k]
                if k == "remaining" and units.get(k, 1) > 1 and remaining_dollars:
                    rec[k] *= units[k]
            if rec.get("avg_price") is not None and not 0 <= rec["avg_price"] < 1e6:
                continue
            start, end = _dates(label, period.year if period else None)
            is_total = "total" in label.lower()
            if not is_total and not start and not re.search(r"month|period", label.lower()):
                continue
            rem = rec.get("remaining")
            if rem and remaining_dollars and units.get("remaining", 1) == 1 and 0 < rem < 100_000 and \
                    (rem != int(rem) or (rec.get("shares") or 0) * (rec.get("avg_price") or 0) > rem * 10):
                spend = (rec.get("shares") or 0) * (rec.get("avg_price") or 0)
                rem *= 1e9 if rem * 1e6 < spend else 1e6   # "$5,904": "(in millions)" stated outside the table
            out.append({"label": label[:200], "start": start, "end": end, "shares": rec.get("shares"),
                        "avg_price": rec.get("avg_price"), "plan_shares": rec.get("plan_shares"),
                        "remaining_value": rem if remaining_dollars else None,
                        "remaining_shares": None if remaining_dollars else rem, "total": is_total})
        if out:
            break
    return out


def months(status=print, years: int = MONTH_YEARS, limit: int | None = None, shard: int = 0, of: int = 1) -> int:
    """Fetch and parse the repurchase table of every 10-Q and 10-K filed in the last `years` years that reports
    buyback spending, skipping filings already tried (sec_buyback_docs)."""
    since = dt.date.today() - dt.timedelta(days=365 * years + 1)
    with db.connect() as conn:
        todo = conn.execute("""
            SELECT s.adsh, s.cik, s.instance, s.period, s.filed FROM sec_fin_subs s
            WHERE s.filed >= %s AND s.form IN ('10-Q', '10-K', '10-KT') AND s.instance LIKE '%%_htm.xml'
              AND EXISTS (SELECT 1 FROM sec_fin_facts f WHERE f.adsh = s.adsh AND f.tag = ANY(%s) AND f.value > 0)
              AND NOT EXISTS (SELECT 1 FROM sec_buyback_docs d WHERE d.adsh = s.adsh)
            ORDER BY s.filed DESC""", (since, list(BUY))).fetchall()
    todo = [t for t in todo if int(t[0][-6:]) % of == shard]      # parallel readers split the filings
    if limit:
        todo = todo[:limit]
    status(f"buybacks months: {len(todo):,} filings to read")
    n = done = 0
    for adsh, cik, inst, period, filed in todo:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{inst[:-len('_htm.xml')]}.htm"
        doc = _get(url, tries=3)
        rows = parse_tables(doc, period) if doc else []
        with db.connect() as conn:
            conn.execute("DELETE FROM sec_buyback_months WHERE adsh = %s", (adsh,))
            for i, r in enumerate(rows):
                conn.execute("""INSERT INTO sec_buyback_months (adsh, row_no, cik, label, period_start, period_end, shares,
                                    avg_price, plan_shares, remaining_value, remaining_shares, is_total, filed, url)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                             (adsh, i, cik, r["label"], r["start"], r["end"], r["shares"], r["avg_price"],
                              r["plan_shares"], r["remaining_value"], r["remaining_shares"], r["total"], filed, url))
            conn.execute("""INSERT INTO sec_buyback_docs (adsh, status, rows) VALUES (%s, %s, %s)
                            ON CONFLICT (adsh) DO UPDATE SET fetched = now(), status = excluded.status, rows = excluded.rows""",
                         (adsh, "ok" if doc else "missing", len(rows)))
            conn.commit()
        done += 1
        n += len(rows)
        if done % 500 == 0:
            status(f"buybacks months: {done:,} of {len(todo):,} filings read, {n:,} rows")
    status(f"buybacks months: {done:,} filings read, {n:,} rows")
    return n


# --- 3. 10b5-1 plans ----------------------------------------------------------------------------------------

PLAN_RX = re.compile(r"10b5-?\s?1", re.I)
NOT_PLAN_RX = re.compile(r"\bnot\b[^.]{0,60}10b5-?\s?1|10b5-?\s?1[^.]{0,40}\b(?:terminated|did not)\b", re.I)


def plans(status=print, only_new: bool = True) -> int:
    with db.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT file FROM sec_buyback_runs WHERE file LIKE 'plans %%'").fetchall()}
    n = 0
    qs = quarters(2006)
    from loader.sec_bulk import form345_files
    listed = form345_files()             # from 2026q2 the data sets moved to another path
    for q in qs:
        if only_new and f"plans {q}" in done and q not in qs[-2:]:
            continue
        path = FORM345 / f"{q}_form345.zip"
        if not path.exists() or q in qs[-2:]:
            data = _get(listed.get(q) or F345_URL.format(q=q))
            if not data:
                continue
            FORM345.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        z = zipfile.ZipFile(path)
        flags: dict[str, list] = {}
        for s in _tsv(z, "SUBMISSION.tsv"):
            box = (s.get("AFF10B5ONE") or "").strip().lower()
            remark = s.get("REMARKS") or ""
            flags[s["ACCESSION_NUMBER"]] = [True if box in ("1", "true") else False if box in ("0", "false") else None,
                                            bool(PLAN_RX.search(remark) and not NOT_PLAN_RX.search(remark))]
        for f in _tsv(z, "FOOTNOTES.tsv"):
            t = f.get("FOOTNOTE_TXT") or ""
            a = f.get("ACCESSION_NUMBER")
            if a in flags and PLAN_RX.search(t) and not NOT_PLAN_RX.search(t):
                flags[a][1] = True
        rows = [(a, v[0], v[1]) for a, v in flags.items() if v[0] is not None or v[1]]
        with db.connect() as conn:
            conn.execute("CREATE TEMP TABLE pl (LIKE sec_insider_plans) ON COMMIT DROP")
            with conn.cursor() as cur, cur.copy("COPY pl FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
            conn.execute("""INSERT INTO sec_insider_plans SELECT DISTINCT ON (accession) * FROM pl
                            ON CONFLICT (accession) DO UPDATE SET aff10b5one = excluded.aff10b5one, footnote = excluded.footnote""")
            conn.execute("""INSERT INTO sec_buyback_runs (file, rows) VALUES (%s, %s)
                            ON CONFLICT (file) DO UPDATE SET loaded = now(), rows = excluded.rows""", (f"plans {q}", len(rows)))
            conn.commit()
        n += len(rows)
        status(f"buybacks plans {q}: {sum(1 for r in rows if r[1] or r[2]):,} filings under a 10b5-1 plan")
    return n


# --- 4. 8-K announcements -----------------------------------------------------------------------------------

ANNOUNCE = ('"authorized an additional" OR "authorized an increase" OR "new share repurchase" OR '
            '"new stock repurchase" OR "new repurchase program" OR "increase in the share repurchase" OR '
            '"increased its share repurchase" OR "approved a new share" OR "approved a new stock" OR '
            '"repurchase authorization of up to" OR "authorized the repurchase of up to" OR '
            '"approved the repurchase of up to" OR "authorized a share repurchase" OR "authorized a stock repurchase"')
EFTS = "https://efts.sec.gov/LATEST/search-index?"


def announcements(status=print, recheck_days: int = 30, shard: int = 0, of: int = 1) -> int:
    """8-Ks announcing a new or larger buyback, for each company that reported buyback spending, from EDGAR
    full-text search (2001 onward). Each company is rechecked once a month for new ones."""
    with db.connect() as conn:
        ciks = [r[0] for r in conn.execute("""
            SELECT b.cik FROM sec_buybacks b LEFT JOIN sec_buyback_ann_runs r ON r.cik = b.cik
            WHERE b.buybacks > 0 AND (r.checked IS NULL OR r.checked < now() - make_interval(days => %s))
            GROUP BY b.cik ORDER BY max(b.buybacks) DESC""", (recheck_days,)).fetchall()]
    ciks = [c for c in ciks if int(c) % of == shard]
    status(f"buybacks announcements: {len(ciks):,} companies to check")
    n = 0
    for i, cik in enumerate(ciks, 1):
        found = []
        for start in (0, 100, 200):
            data = _get(EFTS + urllib.parse.urlencode({"q": ANNOUNCE, "forms": "8-K", "ciks": cik.zfill(10),
                                                      "from": start}), tries=3)
            if not data:
                break
            try:
                hits = json.loads(data)["hits"]
            except (ValueError, KeyError):
                break
            for h in hits.get("hits", []):
                acc, doc = (h["_id"].split(":", 1) + [""])[:2]
                s = h.get("_source", {})
                found.append((acc, cik, s.get("file_date"), ",".join(s.get("items") or []), doc[:200]))
            if len(hits.get("hits", [])) < 100:
                break
        with db.connect() as conn:
            for r in {f[0]: f for f in found}.values():
                if r[2]:
                    conn.execute("""INSERT INTO sec_buyback_announcements (accession, cik, filed, items, document)
                                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", r)
            conn.execute("""INSERT INTO sec_buyback_ann_runs (cik) VALUES (%s)
                            ON CONFLICT (cik) DO UPDATE SET checked = now()""", (cik,))
            conn.commit()
        n += len(found)
        if i % 250 == 0:
            status(f"buybacks announcements: {i:,} of {len(ciks):,} companies, {n:,} 8-Ks")
    status(f"buybacks announcements: {n:,} 8-Ks from {len(ciks):,} companies")
    return n


# --- 6. links and insider sales -----------------------------------------------------------------------------

def links(status=print) -> int:
    """Companies to lobbying clients and to PACs they sponsor, by normalized name (loader.recalls.core)."""
    from loader.recalls import core
    with db.connect() as conn:
        names: dict[str, set] = {}
        for cik, name in conn.execute("""SELECT cik, name FROM (SELECT DISTINCT ON (cik) cik, name FROM sec_fin_subs
                                         ORDER BY cik, filed DESC) x""").fetchall():
            c = core(name)
            if len(c) >= 4:
                names.setdefault(c, set()).add(cik)
        out = set()
        # Only names held by one company (a name shared by several, like old shells, is too weak a link).
        one = {c: next(iter(v)) for c, v in names.items() if len(v) == 1}
        for cid, name in conn.execute("SELECT DISTINCT client_id::text, client_name FROM lda_filings WHERE client_name IS NOT NULL").fetchall():
            if core(name) in one:
                out.add((one[core(name)], "lobbying", cid, name))
        for cmte, org, cname in conn.execute("""SELECT DISTINCT ON (cmte_id) cmte_id, connected_org, name FROM fec_committees
                                                WHERE connected_org IS NOT NULL AND connected_org <> ''
                                                ORDER BY cmte_id, cycle DESC""").fetchall():
            if core(org) in one:
                out.add((one[core(org)], "pac", cmte, cname))
        conn.execute("DELETE FROM sec_company_links")
        with conn.cursor() as cur, cur.copy("COPY sec_company_links FROM STDIN") as cp:
            for r in out:
                cp.write_row(r)
        conn.commit()
    status(f"buybacks links: {sum(1 for r in out if r[1] == 'lobbying'):,} lobbying clients, "
           f"{sum(1 for r in out if r[1] == 'pac'):,} PACs")
    return len(out)


def sales(status=print) -> int:
    """sec_buyback_sales: open-market sales (code S) by insiders of companies that report buybacks, each with the
    company's buyback spending in the calendar quarter of the sale, whether that quarter was heavy (at least
    HEAVY_MIN and at least the company's average buyback quarter), whether the filing says 10b5-1, and the latest
    buyback announcement 0-30 days before the sale."""
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("DELETE FROM sec_buyback_sales")
        conn.execute(f"""
            INSERT INTO sec_buyback_sales (accession, sk, issuer_cik, owner_cik, owner_name, trans_date, shares, price,
                                           value, plan, quarter_end, quarter_buybacks, heavy, ann_accession, ann_filed,
                                           days_after)
            WITH q AS (SELECT cik, date_trunc('quarter', period_end - 20)::date AS qstart, sum(buybacks) AS buybacks
                       FROM sec_buybacks WHERE qtrs = 1 AND buybacks > 0 GROUP BY 1, 2),
                 avgq AS (SELECT cik, avg(buybacks) AS avg_q FROM q GROUP BY 1),
                 s AS (SELECT t.accession, t.sk, ltrim(f.issuer_cik, '0') AS cik, t.trans_date, t.shares, t.price,
                              t.shares * t.price AS value
                       FROM sec_insider_trans t JOIN sec_insider_filings f ON f.accession = t.accession
                       WHERE t.code = 'S' AND t.trans_date >= '2009-01-01' AND t.shares > 0 AND t.price > 0
                         AND t.price < 100000 AND t.shares * t.price < 5e9
                         AND ltrim(f.issuer_cik, '0') IN (SELECT cik FROM avgq)
                         AND (SELECT count(*) FROM sec_insider_owners o WHERE o.accession = t.accession) = 1)
            SELECT s.accession, s.sk, s.cik, o.owner_cik, o.owner_name, s.trans_date, s.shares, s.price, s.value,
                   coalesce(p.aff10b5one, false) OR coalesce(p.footnote, false),
                   (date_trunc('quarter', s.trans_date) + interval '3 months - 1 day')::date, q.buybacks,
                   coalesce(q.buybacks >= {HEAVY_MIN} AND q.buybacks >= a.avg_q, false),
                   an.accession, an.filed, s.trans_date - an.filed
            FROM s JOIN sec_insider_owners o ON o.accession = s.accession
            LEFT JOIN sec_insider_plans p ON p.accession = s.accession
            LEFT JOIN q ON q.cik = s.cik AND q.qstart = date_trunc('quarter', s.trans_date)::date
            LEFT JOIN avgq a ON a.cik = s.cik
            LEFT JOIN LATERAL (SELECT accession, filed FROM sec_buyback_announcements x
                               WHERE x.cik = s.cik AND x.filed <= s.trans_date AND x.filed >= s.trans_date - 30
                               ORDER BY x.filed DESC LIMIT 1) an ON true
            ON CONFLICT DO NOTHING""")
        n = conn.execute("SELECT count(*) FROM sec_buyback_sales").fetchone()[0]
        conn.commit()
        conn.execute("ANALYZE sec_buyback_sales")
        conn.commit()
    status(f"buybacks sales: {n:,} insider sales at companies that buy back stock")
    return n


def run(status=print) -> None:
    """Nightly: new data set quarters, new Form 4 quarters' plan flags, then the derived tables. Monthly tables and
    8-K announcements pick up only what's new."""
    fsds(status)
    compute(status)
    plans(status)
    announcements(status)
    months(status)
    links(status)
    sales(status)


if __name__ == "__main__":
    steps = sys.argv[1:] or ["run"]
    for s in steps:
        if "@" in s:                          # months@0/3: one of three parallel readers
            step, part = s.split("@")
            a, b = part.split("/")
            globals()[step](shard=int(a), of=int(b))
        else:
            globals()[s]()
