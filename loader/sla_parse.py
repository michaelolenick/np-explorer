"""Parsers for student loan ABS monthly servicing reports (Form 10-D exhibits).

Each issuer family publishes the same report template month after month, so there is
one parser per family. A parser takes the report's text (HTML flattened to one line of
words by flatten()) and returns a dict of the student_loan_trust_months measures it
found. Anything the report doesn't state stays out of the dict (stored NULL, shown
"Not reported", never 0). parse_notes explains what was mapped and how.
"""

from __future__ import annotations

import html
import re
from datetime import date

NUM = r"\(?-?\$?\s?[\d,]+(?:\.\d+)?\s?\)?"
DASH = r"(?:-|—|–)"


def flatten(raw: bytes | str) -> str:
    """HTML (or text) to one line of words: tags out, entities decoded, whitespace collapsed."""
    s = raw.decode("latin-1") if isinstance(raw, bytes) else raw
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ").replace("​", " ")
    return re.sub(r"\s+", " ", s)


def money(s: str | None) -> float | None:
    """'$ 1,234.56' -> 1234.56; '(317.63 )' -> -317.63; '-' (a dash for none) -> 0.0."""
    if s is None:
        return None
    s = s.strip()
    if re.fullmatch(DASH, s):
        return 0.0
    neg = s.startswith("(") or s.startswith("-")
    if "." not in s and re.search(r"\d,\d{2}\s*\)?$", s):
        s = s[:s.rindex(",")] + "." + s[s.rindex(",") + 1:]     # a typo'd decimal comma: "1,904,607,71"
    digits = re.sub(r"[^\d.]", "", s)
    if not digits or digits == ".":
        return None
    v = float(digits)
    return -v if neg else v


def to_date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if not m:
        return None
    mo, d, y = (int(x) for x in m.groups())
    y += 2000 if y < 100 else 0
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def period_of(d: date | None) -> date | None:
    return date(d.year, d.month, 1) if d else None


AMT = r"(\$?\s?[\d,]+\.\d{2}|-)"          # an amount as these reports print it, or a dash for none
CNT = r"([\d,]+)"
PCT = r"(-?[\d.]+)\s?%"


# --- generic helpers ------------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(\$\s*)?(\(?-?[\d,]*\.?\d+\s?\)?\s?%?|[-—–](?=\s|$))")


def tokens_after(text: str, label: str, n: int, start: int = 0, window: int = 400):
    """Up to n numbers printed right after label, as (value, is_percent) pairs. Dollar signs are
    skipped, '(x)' is negative and a lone dash is 0. None if the label isn't there or no number follows."""
    m = re.compile(label, re.I).search(text, start)
    if not m:
        return None
    rest, out, pos = text[m.end():m.end() + window], [], 0
    while len(out) < n:
        t = _TOKEN.match(rest, pos)
        if not t or not t.group(2).strip():
            break
        tok = t.group(2).strip()
        pct = tok.endswith("%")
        out.append((money(tok.rstrip("%").strip()) if tok not in "-—–" else 0.0, pct))
        pos = t.end()
    return out or None


def numbers_after(text: str, label: str, n: int, start: int = 0, window: int = 400) -> list[float | None] | None:
    """The first n numbers after the first occurrence of label that has n numbers right after it
    (so a label also used in running text, like "pool balance" in a glossary, is skipped), or None."""
    for m in re.compile(label, re.I).finditer(text, start):
        t = tokens_after(text, re.escape(m.group(0)), n, m.start(), window)
        if t and len(t) == n:
            return [v for v, _ in t]
    return None


def _cnt(v):
    return int(v) if v is not None else None


def _first(pattern: str, text: str, flags=re.I) -> re.Match | None:
    return re.search(pattern, text, flags)


# --- SLM / Navient (FFELP and private credit) ---------------------------------------------
# One template family, three layouts of the loan status table ("Portfolio Characteristics"):
#   2006-2009: two periods side by side, prior first: WAC WAC | loans loans | % % | $ $ | % %
#   2010-2013: current period only:                  WAC | loans | % | $ | %
#   2014-:     current period first, then prior:     WAC | loans | $ | %   (WAC | loans | $ | %)
# The layout is read from where the percent signs fall.

_SFX = r"(?:\s+Current)?(?:\s*\(\d\))?"
SLM_STATUS = [  # (column, pattern for the status label)
    ("school", r"(?:INTERIM:\s*)?IN SCHOOL" + _SFX),
    ("grace", r"(?<!AGED )\bGRACE" + _SFX),
    ("deferment", r"(?:INTERIM:\s*)?DEFERMENT" + _SFX),
    ("current_balance", r"(?:REPAYMENT:?\s*CURRENT|ACTIVE CURRENT)" + r"(?:\s*\(\d\))?"),
    ("d_31_60", r"31-60 DAYS DELINQUENT"), ("d_61_90", r"61-90 DAYS DELINQUENT"),
    ("d_91_120", r"91-120 DAYS DELINQUENT"), ("d_121_150", r"121-150 DAYS DELINQUENT"),
    ("d_151_180", r"151-180 DAYS DELINQUENT"), ("d_181_210", r"181-210 DAYS DELINQUENT"),
    ("d_211_240", r"211-240 DAYS DELINQUENT"), ("d_241_270", r"241-270 DAYS DELINQUENT"),
    ("d_271_300", r"271-300 DAYS DELINQUENT"),
    ("d_gt_120", r"> ?120 DAYS DELINQUENT"), ("d_gt_180", r"> ?180 DAYS DELINQUENT"),
    ("d_gt_270", r"> ?270 DAYS DELINQUENT"), ("d_gt_300", r"> ?300 DAYS DELINQUENT"),
    ("forbearance", r"FORBEARANCE" + _SFX),
    ("claims_in_process", r"CLAIMS IN PROCESS" + r"(?:\s*\(\d\))?"),
]
SLM_BUCKET_LABELS = {"d_31_60": "31-60 days", "d_61_90": "61-90 days", "d_91_120": "91-120 days",
                     "d_121_150": "121-150 days", "d_151_180": "151-180 days", "d_181_210": "181-210 days",
                     "d_211_240": "211-240 days", "d_241_270": "241-270 days", "d_271_300": "271-300 days",
                     "d_gt_120": "> 120 days", "d_gt_180": "> 180 days", "d_gt_270": "> 270 days",
                     "d_gt_300": "> 300 days"}
OVER_120 = ("d_121_150", "d_151_180", "d_181_210", "d_211_240", "d_241_270", "d_271_300",
            "d_gt_120", "d_gt_180", "d_gt_270", "d_gt_300")


def _row(t) -> tuple[int | None, float | None] | None:
    """(loans, principal) for the current period from a status row's tokens."""
    if not t or len(t) < 4 or not t[0][1]:
        return None
    if t[1][1]:                                   # WAC WAC loans loans % % $ $
        return (_cnt(t[3][0]), t[7][0]) if len(t) >= 8 else None
    if t[2][1]:                                   # WAC loans % $ %
        return _cnt(t[1][0]), t[3][0]
    return _cnt(t[1][0]), t[2][0]                 # WAC loans $ %


def _slm_table(text: str) -> tuple[int, int] | None:
    """(start, end) of the loan status table: the Portfolio Characteristics section holding DAYS DELINQUENT."""
    d = re.search(r"DAYS DELINQUENT", text, re.I)
    if not d:
        return None
    heads = [m.end() for m in re.finditer(r"Portfolio Characteristics", text[:d.start()], re.I)]
    start = heads[-1] if heads else max(0, d.start() - 3000)
    end = re.search(r"GRAND TOTAL|\bTOTAL\s+[\d,]+\s+\$", text[start:start + 12000], re.I)
    return start, (start + end.end() + 300 if end else start + 8000)


ROLE_WORDS = {"Depositor": "depositor", "Master Servicer and Administrator": "servicer+administrator",
              "Servicer and Administrator": "servicer+administrator", "Master Servicer": "servicer",
              "Servicer": "servicer", "Administrator": "administrator", "Indenture Trustee": "trustee",
              "Eligible Lender Trustee": "eligible_lender_trustee", "Trustee": "trustee"}
_ROLE = re.compile(r"\s[-–—]\s(" + "|".join(sorted(map(re.escape, ROLE_WORDS), key=len, reverse=True)) + r")\b")


def report_parties(text: str) -> dict:
    """Parties named in the report header ("Navient Funding, LLC - Depositor ..."), as {role: name}."""
    head = text[:2500]
    m = re.search(r"Collection Period:?\s+\d{1,2}/\d{1,2}/\d{2,4}\s*[-–—]\s*\d{1,2}/\d{1,2}/\d{2,4}", head)
    if not m:
        return {}
    out, pos = {}, m.end()
    for r in _ROLE.finditer(head, pos):
        name = head[pos:r.start()].strip(" ,;")
        pos = r.end()
        if not (2 < len(name) < 120) or re.search(r"Page \d|Monthly|Quarterly|Report", name):
            break
        for role in ROLE_WORDS[r.group(1)].split("+"):
            out.setdefault(role, name)
    return out


def parse_slm(text: str) -> dict:
    out: dict = {"parties": report_parties(text)}
    notes = []
    m = _first(r"Distribution Date:?\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    out["distribution_date"] = to_date(m.group(1)) if m else None
    m = _first(r"(?:Collection Period|Transactions from):?\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|—|–|to|through:?)\s*"
               r"(\d{1,2}/\d{1,2}/\d{2,4})", text)
    if m:
        out["collection_start"], out["collection_end"] = to_date(m.group(1)), to_date(m.group(2))
    m = _first(r"Student Loan Portfolio Characteristics\s+(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}/\d{1,2}/\d{4}\s+"
               r"\d{1,2}/\d{1,2}/\d{4}\s+Principal Balance", text)
    if m:                                     # first column is the pool at closing
        v = numbers_after(text, r"\bPool Balance", 3, start=m.end())
        out["closing_date"], out["original_balance"] = to_date(m.group(1)), (v[0] if v else None)
    else:
        m = _first(r"Inputs From Initial Period\s+(\d{1,2}/\d{1,2}/\d{2,4}).{0,300}?Total Pool\s+\$?\s?([\d,]+\.\d{2})", text)
        if m:
            out["closing_date"], out["original_balance"] = to_date(m.group(1)), money(m.group(2))
    span = _slm_table(text)
    if not span:
        return {"error": "no loan status table (no DAYS DELINQUENT rows)", **out}
    table = text[span[0]:span[1]]
    rows = {}
    for col, label in SLM_STATUS:
        r = _row(tokens_after(table, label, 10, window=300))
        if r:
            rows[col] = r
    if not any(c in rows for c in SLM_BUCKET_LABELS):
        return {"error": "loan status table not read", **out}
    get = lambda c: rows.get(c, (None, None))[1]  # noqa: E731
    buckets = [{"label": SLM_BUCKET_LABELS[c], "balance": rows[c][1], "count": rows[c][0]}
               for c in SLM_BUCKET_LABELS if c in rows]
    out["delinquency"] = buckets
    out["delinq_total"] = sum(b["balance"] or 0 for b in buckets)
    out["delinq_30_59"], out["delinq_60_89"], out["delinq_90_119"] = get("d_31_60"), get("d_61_90"), get("d_91_120")
    over = [c for c in OVER_120 if c in rows]
    out["delinq_120_plus"] = sum(get(c) or 0 for c in over) if over else None
    notes.append("Delinquency buckets as labeled (31-60, 61-90, 91-120 days and over) are stored in the 30-59, "
                 "60-89, 90-119 and 120+ columns; the 120+ column sums every longer bucket.")
    out["forbearance"], out["deferment"] = get("forbearance"), get("deferment")
    sg = [get(c) for c in ("school", "grace") if c in rows]
    out["school_grace"] = sum(x or 0 for x in sg) if sg else None
    out["claims_in_process"] = get("claims_in_process")
    out["current_balance"] = get("current_balance")
    if out["current_balance"] is not None:
        out["repayment_balance"] = out["current_balance"] + out["delinq_total"]
    tot = _row(tokens_after(table, r"GRAND TOTAL", 10, window=300))
    if not tot:
        t = tokens_after(table, r"\bTOTAL(?! INTERIM| REPAYMENT)", 2, window=200)
        tot = (_cnt(t[0][0]), t[1][0]) if t and not t[0][1] else None
    # Pool balance, current period: section IV (cont'd) line; the reconciliation's "(=) TOTAL POOL";
    # section I "Total Pool $ prior $ current"; else the status table's total principal.
    m = _first(r"\(cont.d\)\s+\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}/\d{1,2}/\d{2,4}\s+Pool Balance\s+" + AMT, text)
    pool = money(m.group(1)) if m else None
    if pool is None:
        v = numbers_after(text, r"\(=\)\s*TOTAL POOL", 1)
        pool = v[0] if v else None
    if pool is None:
        v = numbers_after(text, r"\bTotal Pool\b", 2)
        pool = v[1] if v else None
    if pool is None and tot:
        pool = tot[1]
        notes.append("Pool balance = total principal in the status table (no pool balance line).")
    out["pool_balance"] = pool
    v = numbers_after(text, r"Total # Loans", 1)
    out["loan_count"] = _cnt(v[0]) if v else (tot[0] if tot else None)
    v = numbers_after(text, r"Total # Borrowers", 1)
    if v:
        out["borrower_count"] = _cnt(v[0])
    v = numbers_after(text, r"Weighted Average Coupon(?! \(WAC\))", 1)
    if v:
        out["wa_interest_rate"] = v[0]
    # CPR, current period: section IV "(CPR)" line; else the last row of the payment history table.
    v = numbers_after(text, r"Constant Prepayment Rate \(CPR\)", 1)
    if v:
        out["prepayment_rate"] = v[0]
    else:
        h = re.search(r"Payment History and CPRs", text, re.I)
        if h:
            rowsh = re.findall(r"[A-Z][a-z]{2}-\d{2}\s+\$\s?[\d,]+(?:\.\d+)?\s+(\(?-?[\d.]+\)?)\s?%",
                               text[h.end():h.end() + 20000])
            if rowsh:
                out["prepayment_rate"] = money(rowsh[-1])
    if "prepayment_rate" in out:
        notes.append("CPR is the since-issued constant prepayment rate as reported (it can be negative).")
    # FFELP: claims paid by guarantors arrive as principal from the guarantor; the uninsured share
    # is "Non-Reimbursable Losses".
    v = numbers_after(text, r"(?:Guarantor Principal|Principal Collections from Guarantor)", 1)
    if v:
        out["defaults"] = v[0]
        notes.append("Defaults = principal received from guarantors this period (FFELP claims paid).")
    v = numbers_after(text, r"Non-Reimbursable Losses During Collection Period", 1)
    if v:
        out["charge_offs"] = v[0]
        notes.append("Charge-offs = Non-Reimbursable Losses (the uninsured share of FFELP claims).")
    v = numbers_after(text, r"Cumulative Non-Reimbursable Losses(?: to Date)?", 1)
    if v:
        out["cum_defaults"] = v[0]
    # Private credit: gross defaults, realized losses and recoveries, current period first.
    v = numbers_after(text, r"Change in Gross Defaults", 1)
    if v and "defaults" not in out:
        out["defaults"] = v[0]
        notes.append("Defaults = change in cumulative gross defaults this period (private loans).")
    v = numbers_after(text, r"Cumulative Gross Defaults", 1)
    if v and "cum_defaults" not in out:
        out["cum_defaults"] = v[0]
    v = numbers_after(text, r"Gross Principal Realized Loss - Periodic", 1)
    if v and "charge_offs" not in out:
        out["charge_offs"] = v[0]
        notes.append("Charge-offs = gross principal realized losses this period.")
    v = numbers_after(text, r"Non-Cash Principal Activity i Realized Losses/Loans Charged Off", 1)
    if v and "charge_offs" not in out:
        out["charge_offs"] = v[0]
        notes.append("Charge-offs = principal realized losses / loans charged off this period.")
    v = numbers_after(text, r"Recoveries on Realized Losses - Periodic", 1) or \
        numbers_after(text, r"Recoveries on Realized Losses", 1)
    if v:
        out["recoveries"] = v[0]
    m = _first(r"Cumulative (?:Gross )?Default Rate[^%\d]{0,60}" + PCT, text)
    if m:
        out["cum_default_pct"] = float(m.group(1))
    out["parse_notes"] = " ".join(notes)
    return out


# --- National Collegiate Student Loan Trusts (First Marblehead) --------------------------------
# "Monthly Distribution Report": status table with prior and current columns side by side
# (WAC, WAC, loans, loans, %, %, $, $, %, %); TERI guaranty claims are cumulative, so the
# month's figure is current minus prior.

NCSLT_STATUS = [("school", r"In School"), ("grace", r"\bGrace"), ("deferment", r"\bDeferment"),
                ("current_balance", r"Active Current|Repayment Current|\bCurrent(?= \d)"),
                ("d_31_60", r"31-60 Days Delinquent"), ("d_61_90", r"61-90 Days Delinquent"),
                ("d_91_120", r"91-120 Days Delinquent"), ("d_121_150", r"121-150 Days Delinquent"),
                ("d_151_180", r"151-180 Days Delinquent"), ("d_gt_180", r"> ?180 Days Delinquent"),
                ("forbearance", r"\bForbearance")]
NCSLT_LABELS = {"d_31_60": "31-60 days", "d_61_90": "61-90 days", "d_91_120": "91-120 days",
                "d_121_150": "121-150 days", "d_151_180": "151-180 days", "d_gt_180": "> 180 days"}


def parse_ncslt(text: str) -> dict:
    out: dict = {}
    notes = []
    m = _first(r"Collection Period\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+(?:to|-)\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    out["collection_end"] = to_date(m.group(2)) if m else None
    m = _first(r"Distribution Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    out["distribution_date"] = to_date(m.group(1)) if m else None
    m = _first(r"Closing Date:\s+([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if m:
        try:
            from datetime import datetime as _dt
            out["closing_date"] = _dt.strptime(m.group(1), "%B %d, %Y").date()
        except ValueError:
            pass
    m = _first(r"Financed Student Loans as of Closing Date\s*[-–—]\s*\$\s?([\d,]+\.\d{2})", text)
    if m:
        out["original_balance"] = money(m.group(1))
    # Each summary line reads prior | change | current. Older text reports break the line after
    # the change, so current = prior + change there.
    def cur(label):
        t = tokens_after(text, label, 3)
        if not t or len(t) < 2:
            return None
        return t[2][0] if len(t) == 3 else (t[0][0] + t[1][0] if None not in (t[0][0], t[1][0]) else None)
    out["pool_balance"] = cur(r"\d Pool Balance")
    if out["pool_balance"] is None:
        return {"error": "no Pool Balance line", **out}
    out["loan_count"] = _cnt(cur(r"Number of Loans"))
    out["borrower_count"] = _cnt(cur(r"Number of Borrowers"))
    v = numbers_after(text, r"Weighted Average Coupon \(WAC\)", 3)
    out["wa_interest_rate"] = v[2] if v else None
    st = re.search(r"Portfolio Characteristics by Payment Status", text, re.I)
    rows = {}
    if st:
        for col, label in NCSLT_STATUS:
            v = numbers_after(text, label, 8, start=st.end(), window=300)
            if v:
                rows[col] = (_cnt(v[3]), v[7])          # current loans, current principal
    if not rows:
        return {"error": "no payment status table", **out}
    buckets = [{"label": NCSLT_LABELS[c], "balance": rows[c][1], "count": rows[c][0]} for c in NCSLT_LABELS if c in rows]
    out["delinquency"] = buckets
    out["delinq_total"] = sum(b["balance"] or 0 for b in buckets) if buckets else None
    g = lambda c: rows.get(c, (None, None))[1]  # noqa: E731
    out["delinq_30_59"], out["delinq_60_89"], out["delinq_90_119"] = g("d_31_60"), g("d_61_90"), g("d_91_120")
    over = [c for c in ("d_121_150", "d_151_180", "d_gt_180") if c in rows]
    out["delinq_120_plus"] = sum(g(c) or 0 for c in over) if over else None
    out["current_balance"] = g("current_balance")
    out["forbearance"], out["deferment"] = g("forbearance"), g("deferment")
    sg = [g(c) for c in ("school", "grace") if c in rows]
    out["school_grace"] = sum(x or 0 for x in sg) if sg else None
    if out["current_balance"] is not None:
        out["repayment_balance"] = out["current_balance"] + (out["delinq_total"] or 0)
    notes.append("Delinquency buckets 31-60, 61-90, 91-120 (stored as 30-59, 60-89, 90-119) and 121-150, "
                 "151-180, over 180 days (summed as 120+).")
    v = numbers_after(text, r"Cumulative (?:Net )?Claims Filed to TERI(?: \(\d\))?", 2)
    if v:
        out["cum_defaults"], out["defaults"] = v[1], (v[1] - v[0] if v[0] is not None and v[1] is not None else None)
        notes.append("Defaults = change in cumulative net claims filed to TERI (the private guarantor) this month.")
    v = numbers_after(text, r"Cumulative Liquidation Proceeds and Recoveries", 2)
    if v:
        out["recoveries"] = v[1] - v[0]
    v = numbers_after(text, r"Student Loan Non-Cash Principal Activity 1 Capitalized Interest \$?\s?[\d,.()-]+ 2 Realized Losses", 1)
    if v:
        out["charge_offs"] = abs(v[0])
        notes.append("Charge-offs = realized principal losses this month.")
    m = _first(r"Cumulative Default Rate as a percentage of (?:Financed Student Loans|Initial)[^%]*?\)\s+" + PCT + r"\s+" + PCT, text)
    if m:
        out["cum_default_pct"] = float(m.group(2))
    m = _first(r"Prepayment Rate(?: \(\d\))?\s+" + PCT, text)
    if m:
        out["prepayment_rate"] = float(m.group(1))
        notes.append("Prepayment rate as reported, updated twice a year.")
    out["parse_notes"] = " ".join(notes)
    return out


# --- Nelnet Student Loan Trusts -------------------------------------------------------------
# Quarterly reports, 2006-2009. The status table shows prior and current quarter side by side
# (WAC WAC | loans loans | remaining term term | $ $ | % %); "Repayment Active 0-30 Days Delinquent"
# is the current bucket. "Defaults Paid this Quarter" is guarantor claims paid; "Principal Realized
# Losses - Claim Write-Offs" is the uninsured share.

NELNET_STATUS = [("school", r"In School"), ("grace", r"\bGrace"), ("deferment", r"\bDeferment"),
                 ("current_balance", r"0-30 Days Delinquent"),
                 ("d_31_60", r"31-60 Days Delinquent"), ("d_61_90", r"61-90 Days Delinquent"),
                 ("d_91_120", r"91-120 Days Delinquent"), ("d_121_150", r"121-150 Days Delinquent"),
                 ("d_151_180", r"151-180 Days Delinquent"), ("d_181_210", r"181-210 Days Delinquent"),
                 ("d_211_240", r"211-240 Days Delinquent"), ("d_241_270", r"241-270 Days Delinquent"),
                 ("d_271_300", r"271-300 Days Delinquent"), ("d_gt_300", r"> ?300 Days Delinquent"),
                 ("forbearance", r"\bForbearance"), ("claims_in_process", r"Claims? (?:Filed|in Process)")]


def parse_nelnet(text: str) -> dict:
    out: dict = {}
    notes = []
    m = _first(r"Distribution Date:?\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    out["distribution_date"] = to_date(m.group(1)) if m else None
    m = _first(r"First Date in Collection Period\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    if m:
        out["collection_start"] = to_date(m.group(1))
    m = _first(r"Collection Period Ending:?\s+(\d{1,2}/\d{1,2}/\d{2,4})", text) or \
        _first(r"Last Date in Collection Period\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    out["collection_end"] = to_date(m.group(1)) if m else None
    v = numbers_after(text, r"(?<!Adjusted )Pool Balance(?: \([^)]*\))?", 2)
    if not v:
        return {"error": "no Pool Balance line", **out}
    out["pool_balance"] = v[1]
    v = numbers_after(text, r"Number of Loans", 2)
    out["loan_count"] = _cnt(v[1]) if v else None
    v = numbers_after(text, r"Number of Borrowers", 2)
    out["borrower_count"] = _cnt(v[1]) if v else None
    st = re.search(r"Days Delinquent\s+[\d.]+\s?%", text, re.I)      # the table, not the contents page
    if not st:
        return {"error": "no loan status table", **out}
    start = max(0, st.start() - 1500)
    def cur(t):
        return (_cnt(t[3][0]), t[7][0]) if t and len(t) >= 8 and t[0][1] and t[1][1] else None

    rows = {}
    for col, label in NELNET_STATUS:
        m = re.compile(label, re.I).search(text, start)
        if not m:
            continue
        r = cur(tokens_after(text, re.escape(m.group(0)), 10, start=m.start(), window=300))
        if not r:   # a group split into subsidized and unsubsidized rows: add the two
            sub = cur(tokens_after(text[m.end():m.end() + 400], r"(?<!Un)Subsidized Loans", 10))
            uns = cur(tokens_after(text[m.end():m.end() + 800], r"Unsubsidized Loans", 10))
            parts = [x for x in (sub, uns) if x]
            if parts:
                r = (sum(x[0] or 0 for x in parts), sum(x[1] or 0 for x in parts))
        if r:
            rows[col] = r
    if not any(c in rows for c in SLM_BUCKET_LABELS):
        return {"error": "loan status table not read", **out}
    g = lambda c: rows.get(c, (None, None))[1]  # noqa: E731
    buckets = [{"label": SLM_BUCKET_LABELS[c], "balance": rows[c][1], "count": rows[c][0]}
               for c in SLM_BUCKET_LABELS if c in rows]
    out["delinquency"] = buckets
    out["delinq_total"] = sum(b["balance"] or 0 for b in buckets)
    out["delinq_30_59"], out["delinq_60_89"], out["delinq_90_119"] = g("d_31_60"), g("d_61_90"), g("d_91_120")
    over = [c for c in OVER_120 if c in rows]
    out["delinq_120_plus"] = sum(g(c) or 0 for c in over) if over else None
    out["current_balance"] = g("current_balance")
    if out["current_balance"] is not None:
        out["repayment_balance"] = out["current_balance"] + out["delinq_total"]
    out["forbearance"], out["deferment"] = g("forbearance"), g("deferment")
    out["claims_in_process"] = g("claims_in_process")
    sg = [g(c) for c in ("school", "grace") if c in rows]
    out["school_grace"] = sum(x or 0 for x in sg) if sg else None
    notes.append("Current = repayment, 0-30 days delinquent (Nelnet's label). Buckets 31-60, 61-90, 91-120 stored "
                 "as 30-59, 60-89, 90-119; every longer bucket summed as 120+.")
    v = numbers_after(text, r"Defaults Paid this Quarter(?: \([^)]*\))?", 1)
    if v:
        out["defaults"] = v[0]
        notes.append("Defaults = defaults paid by guarantors this quarter (FFELP claims).")
    v = numbers_after(text, r"Principal Realized Losses\s*[-—–]\s*Claim Write-Offs", 1)
    if v:
        out["charge_offs"] = v[0]
        notes.append("Charge-offs = principal claim write-offs (not reimbursed by the federal guarantee).")
    v = numbers_after(text, r"Cumulative Defaults Paid to Date", 1)
    if v:
        out["cum_defaults"] = v[0]
    h = re.search(r"Payment History and CPRs", text, re.I)
    if h:
        rowsh = re.findall(r"\d{1,2}/\d{1,2}/\d{4}\s+\$\s?[\d,]+\.\d{2}\s+(-?[\d.]+)\s?%", text[h.end():h.end() + 8000])
        if rowsh:
            out["prepayment_rate"] = float(rowsh[-1])
            notes.append("CPR = the latest quarter's CPR as reported.")
    out["parse_notes"] = " ".join(notes)
    return out


COVER_ROLES = ["Depositor and Sponsor", "Sponsor, Servicer and Administrator", "Sponsor, Master Servicer and "
               "Administrator", "Sponsor and Servicer", "Sponsor and Administrator", "Servicer and Administrator",
               "Master Servicer and Administrator", "Sponsor", "Depositor", "Servicer", "Administrator"]
_COVER = re.compile(r"(.{3,90}?)\s+(" + "|".join(map(re.escape, COVER_ROLES)) + r")\b")


def prospectus_parties(text: str) -> dict:
    """{role: name} from a prospectus supplement's cover: 'X Issuing Entity  Y Depositor and Sponsor  Z Servicer'."""
    m = re.search(r"Issuing Entity", text[:6000])
    if not m:
        return {}
    out, pos = {}, m.end()
    for _ in range(4):
        c = _COVER.match(text, pos)
        if not c:
            break
        name = re.sub(r"^(?:and|,|\s)+", "", c.group(1)).strip(" ,;")
        if re.search(r"\$|Notes|Securities|Page|offered", name, re.I):
            break
        if len(name.split()) < 2:            # "Seller": a pointer to another party, not a name
            pos = c.end()
            continue
        for role in ("sponsor", "depositor", "servicer", "administrator"):
            if role in c.group(2).lower():
                out.setdefault(role, name)
        pos = c.end()
    return out


def looks_like_report(text: str) -> bool:
    """An 8-K that carries a monthly or quarterly servicing / distribution report (before Form 10-D)."""
    return bool(re.search(r"(monthly|quarterly)\s+(distribution|servicing)\s+report|servicer.s\s+(monthly\s+)?report|"
                          r"collection period", text[:6000], re.I))


PARSERS = {"slm": parse_slm, "ncslt": parse_ncslt, "nelnet": parse_nelnet}
ALIASES = {"smb": "slm", "slc": "slm"}   # SMB and SLC (Student Loan Corp) trusts use the Sallie Mae / Navient template
EARLY_8K = {"slm", "smb", "ncslt", "slc"}           # families whose pre-2006 monthly reports came on 8-K and parse the same way
