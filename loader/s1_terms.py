"""Offering terms for the IPO registrations (owner, 2026-11-13): the second pass over loader/s1.py's filings.

For each registrant the primary document of its latest registration statement (S-1, S-1/A, F-1, F-1/A) and of its
final prospectus (424B4, 424B1) is fetched from EDGAR, the HTML stripped, and the cover page read with regular
expressions: the proposed price range ("between $56.00 and $60.00 per share"), the shares offered by the company
and by selling holders, the final price ("The initial public offering price is $68.00 per share", or the price
table), the gross proceeds (the price table's total, else price x shares), the exchange and ticker ("approved for
listing on the Nasdaq Global Select Market under the symbol 'ABNB'"), and the underwriters: the names on the
cover (with the Book-Running Manager / Representatives labels when printed) and the underwriting table in the
"Underwriting" section ("Name | Number of Shares"), whose first rows and the "acting as representatives" sentence
name the leads. Underwriter names are normalised (ALIASES: "Goldman Sachs & Co. LLC", "Goldman, Sachs & Co." and
"Goldman Sachs" are one firm) and tied to FURP's registered broker-dealer and adviser records (sec_firm_aliases).

Tables:
  ipo_offerings              one row per document read: the terms found, the underwriters (jsonb), the leads, the
                             document URL and a parse_note (what was found, or why nothing was). Rows are kept for
                             documents that yielded nothing, so a rerun skips them: the loader is resumable.
  ipo_offering_underwriters  one row per underwriter per document (rank, shares allocated, lead or not)
  ipo_underwriters           the roll-up per firm: deals, as lead, proceeds, by year, the broker-dealer CIK
  ipo_companies              headline terms rolled up per registrant (price_low/high, offer_price, offer_shares,
                             offer_proceeds, offer_exchange, offer_ticker, offer_date, lead_underwriters); the
                             roll-up runs again at the end of every loader.s1 load, which truncates the table.

EDGAR: two requests per document (the filing index, then the primary document; old filings have only the full
submission .txt, whose first <DOCUMENT> is read), the SEC's User-Agent rule, a shared limiter of 5 requests a
second across the worker threads (the SEC allows 10), retries on 5xx. Priority: registrants that priced first,
newest first, then the rest by latest filing. Progress goes to the status callback (the log file when run with
nohup) and to loader_progress (s1:terms).

Usage: .venv/bin/python -m loader.s1_terms [--limit N] [--ciks 1559720,1874178] [--workers 3] [--rollup-only]
       [--reparse]  (reparse: read the documents again for the CIKs given, replacing their rows)
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from loader import db
from loader.recalls import core
from loader.s1 import REG_FORMS, UA

FINAL_FORMS = ("424B4", "424B1")
INTERVAL = 0.2                 # seconds between request starts, all threads together: 5 a second
MAX_BYTES = 40 << 20           # a primary document bigger than this is skipped
COVER_CHARS = 90_000           # the cover page is in the first part of the stripped text
STOP_FILE = Path.home() / "claude_scripts" / "s1" / "STOP"

DDL = """
CREATE TABLE IF NOT EXISTS ipo_offerings (
    accession text NOT NULL, cik text NOT NULL, form text NOT NULL, filed date NOT NULL, role text NOT NULL,
    is_ipo boolean, security text, price_low numeric(12,4), price_high numeric(12,4), price numeric(12,4),
    shares_offered bigint, shares_company bigint, shares_selling bigint, shares_sold bigint, proceeds numeric(20,2),
    exchange text, ticker text, underwriters jsonb, lead_underwriters jsonb, n_underwriters integer,
    doc_url text, doc_chars integer, parsed_at timestamptz NOT NULL, parse_note text,
    PRIMARY KEY (accession, cik));
CREATE INDEX IF NOT EXISTS ipo_offerings_cik ON ipo_offerings (cik, role);
CREATE INDEX IF NOT EXISTS ipo_offerings_proceeds ON ipo_offerings (proceeds DESC) WHERE proceeds IS NOT NULL;
CREATE TABLE IF NOT EXISTS ipo_offering_underwriters (
    accession text NOT NULL, cik text NOT NULL, rank integer NOT NULL, name text NOT NULL, name_key text NOT NULL,
    shares bigint, lead boolean NOT NULL DEFAULT false, PRIMARY KEY (accession, cik, rank));
CREATE INDEX IF NOT EXISTS ipo_offering_underwriters_key ON ipo_offering_underwriters (name_key);
CREATE TABLE IF NOT EXISTS ipo_underwriters (
    name_key text PRIMARY KEY, name text NOT NULL, deals integer NOT NULL, lead_deals integer NOT NULL,
    ipos integer NOT NULL, proceeds numeric(20,2), lead_proceeds numeric(20,2), first date, last date,
    filings integer NOT NULL DEFAULT 0, bd_cik text, bd_name text, ia_crd text, by_year jsonb, aliases jsonb,
    updated timestamptz NOT NULL);
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS price_low numeric(12,4);
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS price_high numeric(12,4);
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_price numeric(12,4);
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_shares bigint;
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_proceeds numeric(20,2);
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_exchange text;
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_ticker text;
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_date date;
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS offer_is_ipo boolean;
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS lead_underwriters text;
ALTER TABLE ipo_companies ADD COLUMN IF NOT EXISTS n_underwriters integer;
CREATE INDEX IF NOT EXISTS ipo_companies_offer_proceeds ON ipo_companies (offer_proceeds DESC) WHERE offer_proceeds IS NOT NULL;
"""


# --- fetching -------------------------------------------------------------------------------------------

class Limiter:
    """At most one request start every INTERVAL seconds, across threads."""

    def __init__(self, interval: float = INTERVAL):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            if now < self.next_at:
                time.sleep(self.next_at - now)
                now = time.monotonic()
            self.next_at = now + self.interval


LIMITER = Limiter()


def _get(url: str, limit: int = MAX_BYTES) -> bytes | None:
    """One EDGAR request; None on 404 or when the body is over the limit; retried on other failures."""
    for attempt in range(5):
        LIMITER.wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=120) as r:
                n = r.headers.get("Content-Length")
                if n and int(n) > limit:
                    return None
                data = r.read(limit + 1)
                return None if len(data) > limit else data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"SEC kept failing: {url}")


ROW = re.compile(r'(?is)<tr[^>]*>\s*<td[^>]*>\s*(\d+)\s*</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
                 r'\s*</td>\s*<td[^>]*>(.*?)</td>')
DOC = re.compile(r"(?s)<DOCUMENT>\s*<TYPE>([^\n<]+).*?<TEXT>(.*?)</TEXT>")


def primary_document(cik: str, accession: str, form: str) -> tuple[str | None, str | None, str]:
    """(url, text, note) of the filing's primary document: the first row of the filing index whose type is the
    form (or the first row), or, when the index has no file links (filings before 2001), the first <DOCUMENT> of
    the full submission text."""
    acc_nodash = accession.replace("-", "")
    idx_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{accession}-index.htm"
    idx = _get(idx_url, 4 << 20)
    if idx is None:
        return None, None, "no filing index"
    rows = ROW.findall(idx.decode("utf-8", "replace"))
    want = form.split("/")[0]
    pick = next((r for r in rows if re.sub(r"<[^>]+>", "", r[4]).strip().upper().startswith(want)), rows[0] if rows else None)
    if pick is None:
        return None, None, "no documents in the index"
    href = pick[2]
    if "/ix?doc=" in href:
        href = href.split("/ix?doc=", 1)[1]
    if href.endswith("/") or "." not in href.rsplit("/", 1)[-1]:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.txt"
        full = _get(url)
        if full is None:
            return url, None, "no submission text"
        m = DOC.search(full.decode("latin-1"))
        return url, (m.group(2) if m else full.decode("latin-1")), "from the submission text"
    url = "https://www.sec.gov" + href if href.startswith("/") else href
    body = _get(url)
    if body is None:
        return url, None, "document missing or too big"
    return url, body.decode("utf-8", "replace"), "primary document"


# --- text -----------------------------------------------------------------------------------------------

def strip_html(h: str) -> str:
    """The document as lines: table cells separated by ' | ', block ends as line breaks."""
    if "<" not in h[:5000] and "&" not in h[:5000] and not re.search(r"(?i)<(p|div|td|br|html)\b", h[:20000]):
        return h.replace("\r", "")
    h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>|<hr[^>]*>|</title>", "\n", h)
    h = re.sub(r"(?is)</td>|</th>", " | ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = htmllib.unescape(h).replace("\xa0", " ").replace("​", "")
    h = re.sub(r"[ \t\r\f\v]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n", h)
    return h


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _money(s: str) -> float:
    return float(s.replace(",", ""))


# --- cover page -----------------------------------------------------------------------------------------

PR = r"(?:US)?\$\s?(\d{1,4}(?:\.\d{1,4})?)"
UNIT = r"(?:shares?|ADSs?|American depositary shares?|units?|ordinary shares?|common shares?|depositary shares?|securit(?:y|ies))"
NUM = r"(\d{1,3}(?:,\d{3})+|\d{4,})"
RANGE = re.compile(r"between " + PR + r" and " + PR + r"(?: per " + UNIT + r")?", re.I)
RANGE2 = re.compile(r"(?:range|of|from) " + PR + r" (?:to|and) " + PR + r"(?: per " + UNIT + r")?", re.I)
RANGE_CTX = re.compile(r"(?i)offering price|price range|price per|price of the|priced at|estimated to be|anticipate|currently estimated|expected to be")
PRICE_LABEL = r"(?:(?:initial )?public offering price|IPO price|offering price(?: to (?:the )?public)?|price to (?:the )?public)"
PRICE_SENT = re.compile(r"(?:" + PRICE_LABEL + r"(?: per " + UNIT + r")?(?: of (?:our|the) [\w ]{3,40}?)? (?:is|was|will be|of|at)|"
                        r"(?:has an|at an?|at the) (?:initial public )?offering price of|at a price of) " + PR, re.I)
PRICE_A_SHARE = re.compile(r"price(?: of)? " + PR + r" (?:a|per) " + UNIT, re.I)
PRICE_TABLE = re.compile(PRICE_LABEL + r"(?: per " + UNIT + r")?(?:\s*\(\d\))?[\s|.…:_-]{0,60}(?:US)?\$[\s|]{0,8}(\d{1,4}(?:\.\d{1,4})?)"
                         r"(?:[\s|.…:_-]{0,60}(?:US)?\$[\s|]{0,8}(\d{1,3}(?:,\d{3})+))?", re.I)
PRICE_TO_PUBLIC = re.compile(r"price to (?:the )?public.{0,600}?per " + UNIT + r"[\s|]{0,12}(?:US)?\$[\s|]{0,8}(\d{1,4}(?:\.\d{1,4})?).{0,500}?total(?: ?\(\d\))?[\s|]{0,12}(?:US)?\$[\s|]{0,8}(\d{1,3}(?:,\d{3})+)", re.I)
HEADLINE = re.compile(r"(?<![\d,.$-])(\d{1,3}(?:,\d{3})+|\d{5,}) (?:American Depositary Shares|ADSs|Shares|Ordinary Shares|Common Shares|Units|Depositary Shares|Class [A-C] )", re.I)
OFFER_CO = re.compile(r"\b(?:we|the company|[A-Z][\w.,&'’ -]{1,60}?) (?:is|are) (?:offering|selling)(?: all of the| an aggregate of| a total of| up to)? " + NUM + r" (?:shares|ADSs|American depositary shares|units|ordinary shares|common shares|Class)", re.I)
OFFER_SELL = re.compile(r"selling (?:stock|share|unit|security)holders?[^.]{0,160}? (?:is|are) (?:offering|selling)(?: an aggregate of| an additional| a total of| up to)? " + NUM + r" (?:shares|ADSs|American depositary shares|units|ordinary shares|common shares|Class)", re.I)
OFFER_GEN = re.compile(r"(?:this prospectus relates to|prospectus covers|offering of|offer and sale of|resale of|offering|sale of)(?: up to| an aggregate of| the)? " + NUM + r" (?:shares|ADSs|units|ordinary shares|common shares)", re.I)
TICKER = re.compile(r"\b(?:on|to|for) (?:the )?((?:Nasdaq|NASDAQ|New York Stock Exchange|NYSE|American Stock Exchange|AMEX|Toronto Stock Exchange|TSX|OTC|Cboe|BATS|Pink)[\w .&-]{0,40}?),? (?:\([^)]{0,40}\) )?under the (?:trading |ticker |proposed )*symbols? [“\"'‘]?\s?([A-Z][A-Z0-9.]{0,6})", re.I)
TICKER2 = re.compile(r"under the (?:trading |ticker |proposed )*symbols? [“\"'‘]\s?([A-Z][A-Z0-9.]{0,6})")
EXCHANGES = [("nasdaq", "Nasdaq"), ("new york stock exchange", "NYSE"), ("nyse american", "NYSE American"), ("nyse mkt", "NYSE American"),
             ("nyse arca", "NYSE Arca"), ("american stock exchange", "NYSE American"), ("amex", "NYSE American"), ("nyse", "NYSE"),
             ("toronto", "TSX"), ("tsx", "TSX"), ("otcqx", "OTCQX"), ("otcqb", "OTCQB"), ("otc", "OTC"), ("pink", "OTC"), ("cboe", "Cboe"), ("bats", "Cboe")]


def _exchange(s: str) -> str | None:
    low = s.lower()
    for k, v in EXCHANGES:
        if k in low:
            if v == "NYSE" and ("american" in low or "mkt" in low or "arca" in low):
                continue
            return v
    return None


def _ok_price(p: float) -> bool:
    return 0.01 <= p < 10000


def _context_ok(flat: str, start: int, bad=("assum", "midpoint", "hypothetical", "last reported", "closing price", "exercise price", "ntbv",
                                            "book value", "dilution", "redemption", "scenario", "trust account", "difference between",
                                            "conversion price", "warrant", "discount to")) -> bool:
    before = flat[max(0, start - 70):start].lower()
    return not any(b in before for b in bad)


def parse_cover(text: str, form: str = "424B4") -> dict:
    """The offering terms on the cover page of a prospectus or registration statement (the first part of the
    stripped text). Missing terms are None; `note` says what was read."""
    cover = text[:COVER_CHARS]
    flat = _flat(cover)
    out = {"is_ipo": None, "security": None, "price_low": None, "price_high": None, "price": None, "shares_offered": None,
           "shares_company": None, "shares_selling": None, "proceeds": None, "exchange": None, "ticker": None, "notes": []}
    low = flat.lower()
    ipo = "initial public offering" in low
    resale = bool(re.search(r"this prospectus (?:relates to|covers) the (?:resale|offer and sale|sale)[^.]{0,80} by the selling", low))
    out["is_ipo"] = bool(ipo and not resale and re.search(
        r"no (?:established )?public (?:trading )?market|prior to this offering,? there (?:has been|was|is) no|"
        r"this is (?:our|the|an|a firm[- ]commitment) initial (?:public )?offering|initial public offering price", low))
    if re.search(r"american depositary share|\bADSs?\b", flat):
        out["security"] = "ADS"
    elif re.search(r"\bunits?\b", low[:6000]) and re.search(r"warrant", low[:6000]):
        out["security"] = "units"
    elif "ordinary shares" in low[:6000] and "common stock" not in low[:6000]:
        out["security"] = "ordinary shares"
    elif "common stock" in low[:12000]:
        out["security"] = "common stock"
    # the price range (registration statements)
    for rx in (RANGE, RANGE2):
        for m in rx.finditer(flat):
            lo, hi = float(m.group(1)), float(m.group(2))
            if not RANGE_CTX.search(flat[max(0, m.start() - 220):m.start()]) or not _context_ok(flat, m.start()):
                continue
            if _ok_price(lo) and lo < hi <= lo * 3:
                out["price_low"], out["price_high"] = lo, hi
                out["notes"].append("range")
                break
        if out["price_low"]:
            break
    # the final price: the sentence, the "PRICE $34.00 A SHARE" line, the price table
    for m in PRICE_SENT.finditer(flat):
        if _context_ok(flat, m.start()):
            p = float(m.group(1))
            if _ok_price(p):
                out["price"] = p
                out["notes"].append("price sentence")
                break
    if out["price"] is None:
        m = PRICE_A_SHARE.search(flat)
        if m and _ok_price(float(m.group(1))) and _context_ok(flat, m.start()):
            out["price"] = float(m.group(1))
            out["notes"].append("price line")
    total = None
    for m in PRICE_TABLE.finditer(flat):
        if not _context_ok(flat, m.start()):
            continue
        p = float(m.group(1))
        if not _ok_price(p):
            continue
        if out["price"] is None:
            out["price"] = p
            out["notes"].append("price table")
        if m.group(2) and abs(p - out["price"]) < 0.01:
            total = _money(m.group(2))
        break
    if total is None:
        m = PRICE_TO_PUBLIC.search(flat)
        if m and _ok_price(float(m.group(1))):
            if out["price"] is None:
                out["price"] = float(m.group(1))
                out["notes"].append("price to public")
            if abs(float(m.group(1)) - out["price"]) < 0.01:
                total = _money(m.group(2))
    # shares: the headline on the cover, the sentences
    starts = [m.start() for m in re.finditer(r"(?i)subject to completion|filed pursuant to rule 424|preliminary prospectus|^\s*prospectus\s*$|\bprospectus\b", flat[:60000])]
    cstart = max((x for x in starts if x < 50000), default=0) if starts else 0
    cstart = min((x for x in starts if x >= 0), default=0) if starts else 0
    head = flat[cstart:cstart + 7000]
    headline = None
    for m in HEADLINE.finditer(head):
        if not re.search(r"(?i)additional|includes?|up to|option|aggregate of", head[max(0, m.start() - 40):m.start()]):
            headline = _num(m.group(1))
            break
    sells = [(m.start(), _num(m.group(1))) for m in OFFER_SELL.finditer(flat[:30000])]
    cos = [(m.start(), _num(m.group(1))) for m in OFFER_CO.finditer(flat[:30000])
           if "selling" not in flat[max(0, m.start() - 120):m.start()].lower() and not re.search(r"selling (?:stock|share)holder", m.group(0), re.I)
           and not re.search(r"additional|option|over-allotment", flat[max(0, m.start() - 80):m.start()], re.I)]
    if cos:
        out["shares_company"] = cos[0][1]
    if sells:
        out["shares_selling"] = sells[0][1]
    parts = (out["shares_company"] or 0) + (out["shares_selling"] or 0)
    if headline and headline >= 1000:
        out["shares_offered"] = headline
        out["notes"].append("shares headline")
    elif parts:
        out["shares_offered"] = parts
        out["notes"].append("shares sentence")
    else:
        m = OFFER_GEN.search(flat[:30000])
        if m:
            out["shares_offered"] = _num(m.group(1))
            out["notes"].append("shares general")
    if out["shares_offered"] and out["shares_company"] is None and out["shares_selling"] is None and not resale:
        out["shares_company"] = out["shares_offered"]
    # proceeds: the price table's total, else price x shares
    if total and out["price"] and (not out["shares_offered"] or 0.5 <= total / (out["price"] * out["shares_offered"]) <= 2):
        out["proceeds"] = total
        out["notes"].append("proceeds table")
    elif out["price"] and out["shares_offered"]:
        out["proceeds"] = round(out["price"] * out["shares_offered"], 2)
        out["notes"].append("proceeds computed")
    if out["price"] and out["price_low"] and not (out["price_low"] / 2 <= out["price"] <= out["price_high"] * 2):
        out["price"] = None
        out["notes"].append("price outside the range dropped")
        out["proceeds"] = None
    # exchange and ticker
    m = TICKER.search(flat)
    if m:
        out["exchange"], out["ticker"] = _exchange(m.group(1)), m.group(2).rstrip(".")
    else:
        m = TICKER2.search(flat)
        if m:
            out["ticker"] = m.group(1).rstrip(".")
            ctx = flat[max(0, m.start() - 200):m.start()]
            out["exchange"] = _exchange(ctx)
    return out


# --- underwriters ---------------------------------------------------------------------------------------

SUFFIX = {"inc", "incorporated", "llc", "l", "c", "lp", "p", "ltd", "limited", "corp", "corporation", "co", "company", "plc",
          "usa", "u", "s", "a", "sa", "ag", "nv", "n", "v", "llp", "and", "the", "international", "americas", "america"}
# normalised key -> the firm's one name. Renamed franchises are merged; firms that were bought keep their own name.
ALIASES = {
    "goldman sachs": "Goldman Sachs", "goldman sachs international": "Goldman Sachs", "goldman sachs asia": "Goldman Sachs",
    "goldman sachs and co": "Goldman Sachs", "goldman sachs and company": "Goldman Sachs",
    "morgan stanley": "Morgan Stanley", "morgan stanley dean witter": "Morgan Stanley", "morgan stanley and co": "Morgan Stanley",
    "morgan stanley and co international": "Morgan Stanley", "morgan stanley asia": "Morgan Stanley",
    "j p morgan": "J.P. Morgan", "j p morgan securities": "J.P. Morgan", "jpmorgan": "J.P. Morgan", "jpmorgan securities": "J.P. Morgan",
    "jp morgan": "J.P. Morgan", "jp morgan securities": "J.P. Morgan", "j p morgan and co": "J.P. Morgan", "jpmorgan chase": "J.P. Morgan",
    "chase securities": "J.P. Morgan", "chase h and q": "Hambrecht & Quist", "hambrecht and quist": "Hambrecht & Quist",
    "bofa securities": "BofA Securities", "bofa merrill lynch": "BofA Securities", "banc of america securities": "BofA Securities",
    "banc of america securities llc": "BofA Securities", "bank of america securities": "BofA Securities",
    "merrill lynch": "Merrill Lynch", "merrill lynch pierce fenner and smith": "Merrill Lynch", "merrill lynch and co": "Merrill Lynch",
    "merrill lynch fenner and smith": "Merrill Lynch", "merrill lynch pierce fenner and smith incorporated": "Merrill Lynch",
    "citigroup": "Citigroup", "citigroup global markets": "Citigroup", "citi": "Citigroup", "salomon smith barney": "Citigroup",
    "smith barney": "Citigroup", "salomon brothers": "Citigroup", "smith barney shearson": "Citigroup", "smith barney harris upham": "Citigroup",
    "credit suisse": "Credit Suisse", "credit suisse securities usa": "Credit Suisse", "credit suisse first boston": "Credit Suisse",
    "cs first boston": "Credit Suisse", "first boston": "Credit Suisse", "credit suisse first boston corporation": "Credit Suisse",
    "deutsche bank securities": "Deutsche Bank", "deutsche bank": "Deutsche Bank", "deutsche banc alex brown": "Deutsche Bank",
    "deutsche bank alex brown": "Deutsche Bank", "deutsche morgan grenfell": "Deutsche Bank", "bt alex brown": "BT Alex. Brown",
    "alex brown and sons": "Alex. Brown & Sons", "alex brown": "Alex. Brown & Sons",
    "barclays": "Barclays", "barclays capital": "Barclays", "lehman brothers": "Lehman Brothers", "lehman": "Lehman Brothers",
    "ubs": "UBS", "ubs securities": "UBS", "ubs investment bank": "UBS", "ubs warburg": "UBS", "warburg dillon read": "UBS",
    "paine webber": "PaineWebber", "painewebber": "PaineWebber", "painewebber incorporated": "PaineWebber",
    "bear stearns": "Bear Stearns", "bear stearns and co": "Bear Stearns",
    "wells fargo securities": "Wells Fargo", "wells fargo": "Wells Fargo", "wachovia securities": "Wachovia", "wachovia capital markets": "Wachovia",
    "first union securities": "Wachovia", "first union capital markets": "Wachovia",
    "jefferies": "Jefferies", "jefferies and company": "Jefferies", "jefferies group": "Jefferies",
    "rbc capital markets": "RBC Capital Markets", "rbc dominion securities": "RBC Capital Markets", "rbc dain rauscher": "RBC Capital Markets",
    "dain rauscher wessels": "RBC Capital Markets", "dain rauscher": "RBC Capital Markets",
    "cowen": "Cowen", "cowen and company": "Cowen", "td cowen": "Cowen", "sg cowen": "Cowen", "sg cowen securities": "Cowen", "cowen and co": "Cowen",
    "piper sandler": "Piper Sandler", "piper sandler and co": "Piper Sandler", "piper jaffray": "Piper Sandler", "piper jaffray and co": "Piper Sandler",
    "u s bancorp piper jaffray": "Piper Sandler", "stifel": "Stifel", "stifel nicolaus": "Stifel", "stifel nicolaus and company": "Stifel",
    "stifel nicolaus weisel": "Stifel", "thomas weisel partners": "Thomas Weisel Partners",
    "raymond james": "Raymond James", "raymond james and associates": "Raymond James",
    "baird": "Baird", "robert w baird and co": "Baird", "robert w baird": "Baird",
    "william blair": "William Blair", "william blair and company": "William Blair",
    "needham": "Needham & Company", "needham and company": "Needham & Company",
    "oppenheimer": "Oppenheimer", "oppenheimer and co": "Oppenheimer", "cibc oppenheimer": "Oppenheimer", "cibc world markets": "CIBC World Markets",
    "donaldson lufkin and jenrette": "Donaldson, Lufkin & Jenrette", "donaldson lufkin and jenrette securities": "Donaldson, Lufkin & Jenrette",
    "dlj": "Donaldson, Lufkin & Jenrette", "dljdirect": "Donaldson, Lufkin & Jenrette",
    "montgomery securities": "Montgomery Securities", "nationsbanc montgomery securities": "Montgomery Securities",
    "robertson stephens": "Robertson Stephens", "robertson stephens and company": "Robertson Stephens", "bancboston robertson stephens": "Robertson Stephens",
    "fleetboston robertson stephens": "Robertson Stephens", "prudential securities": "Prudential Securities", "prudential bache securities": "Prudential Securities",
    "wit capital": "Wit Capital", "wit soundview": "Wit Capital", "soundview technology group": "SoundView", "e offering": "E*Offering",
    "dean witter reynolds": "Dean Witter", "dean witter": "Dean Witter", "kidder peabody": "Kidder, Peabody", "kidder peabody and co": "Kidder, Peabody",
    "jmp securities": "JMP Securities", "citizens jmp": "JMP Securities", "citizens jmp securities": "JMP Securities", "citizens capital markets": "Citizens",
    "keybanc capital markets": "KeyBanc Capital Markets", "mckinley capital": "KeyBanc Capital Markets", "mcdonald and company securities": "KeyBanc Capital Markets",
    "canaccord genuity": "Canaccord Genuity", "canaccord adams": "Canaccord Genuity", "canaccord capital": "Canaccord Genuity",
    "mizuho": "Mizuho", "mizuho securities": "Mizuho", "mizuho securities usa": "Mizuho", "mizuho americas": "Mizuho",
    "nomura": "Nomura", "nomura securities international": "Nomura", "nomura securities": "Nomura",
    "bnp paribas": "BNP Paribas", "bnp paribas securities": "BNP Paribas", "bnp paribas securities corp": "BNP Paribas",
    "hsbc": "HSBC", "hsbc securities usa": "HSBC", "hsbc securities": "HSBC", "evercore": "Evercore", "evercore group": "Evercore", "evercore isi": "Evercore",
    "allen and company": "Allen & Company", "allen and co": "Allen & Company", "guggenheim securities": "Guggenheim Securities",
    "cantor": "Cantor Fitzgerald", "cantor fitzgerald": "Cantor Fitzgerald", "cantor fitzgerald and co": "Cantor Fitzgerald",
    "roth capital partners": "Roth Capital Partners", "roth": "Roth Capital Partners", "roth mkm": "Roth Capital Partners",
    "maxim group": "Maxim Group", "aegis capital": "Aegis Capital", "aegis capital corp": "Aegis Capital", "thinkequity": "ThinkEquity",
    "thinkequity partners": "ThinkEquity", "ef hutton": "EF Hutton", "e f hutton": "EF Hutton", "kingswood capital markets": "EF Hutton",
    "boustead securities": "Boustead Securities", "wallachbeth capital": "WallachBeth Capital", "joseph gunnar and co": "Joseph Gunnar",
    "joseph gunnar": "Joseph Gunnar", "alexander capital": "Alexander Capital", "network 1 financial securities": "Network 1 Financial",
    "network 1 financial": "Network 1 Financial", "laidlaw and company uk": "Laidlaw & Company", "laidlaw and company": "Laidlaw & Company",
    "h c wainwright and co": "H.C. Wainwright", "h c wainwright": "H.C. Wainwright", "hc wainwright": "H.C. Wainwright",
    "ladenburg thalmann": "Ladenburg Thalmann", "ladenburg thalmann and co": "Ladenburg Thalmann",
    "b riley securities": "B. Riley Securities", "b riley fbr": "B. Riley Securities", "b riley and co": "B. Riley Securities", "b riley": "B. Riley Securities",
    "fbr capital markets": "FBR", "fbr capital markets and co": "FBR", "friedman billings ramsey": "FBR", "friedman billings ramsey and co": "FBR", "fbr": "FBR",
    "chardan": "Chardan", "chardan capital markets": "Chardan", "benchmark": "The Benchmark Company", "benchmark company": "The Benchmark Company",
    "craig hallum": "Craig-Hallum", "craig hallum capital group": "Craig-Hallum", "lake street capital markets": "Lake Street Capital Markets",
    "northland securities": "Northland Securities", "northland capital markets": "Northland Securities",
    "d a davidson and co": "D.A. Davidson", "d a davidson": "D.A. Davidson", "wedbush securities": "Wedbush Securities", "wedbush": "Wedbush Securities",
    "wedbush morgan securities": "Wedbush Securities", "wedbush pacgrow": "Wedbush Securities",
    "janney montgomery scott": "Janney Montgomery Scott", "leerink partners": "Leerink Partners", "svb leerink": "Leerink Partners",
    "svb securities": "Leerink Partners", "leerink swann": "Leerink Partners", "leerink swann and company": "Leerink Partners",
    "bmo capital markets": "BMO Capital Markets", "bmo capital markets corp": "BMO Capital Markets", "bmo nesbitt burns": "BMO Capital Markets",
    "scotia capital usa": "Scotiabank", "scotiabank": "Scotiabank", "scotia capital": "Scotiabank", "td securities usa": "TD Securities",
    "td securities": "TD Securities", "truist securities": "Truist Securities", "suntrust robinson humphrey": "Truist Securities",
    "suntrust equitable securities": "Truist Securities", "robinson humphrey": "Truist Securities", "robinson humphrey company": "Truist Securities",
    "academy securities": "Academy Securities", "loop capital markets": "Loop Capital Markets", "loop capital": "Loop Capital Markets",
    "ramirez and co": "Ramirez & Co.", "samuel a ramirez and company": "Ramirez & Co.", "samuel a ramirez and co": "Ramirez & Co.",
    "siebert williams shank and co": "Siebert Williams Shank", "siebert williams shank": "Siebert Williams Shank",
    "siebert cisneros shank and co": "Siebert Williams Shank", "williams capital group": "Siebert Williams Shank",
    "telsey advisory group": "Telsey Advisory Group", "tigress financial partners": "Tigress Financial Partners",
    "c l king and associates": "C.L. King & Associates", "cl king and associates": "C.L. King & Associates", "c l king": "C.L. King & Associates",
    "drexel hamilton": "Drexel Hamilton", "blaylock van": "Blaylock Van", "blaylock robert van": "Blaylock Van", "blaylock beal van": "Blaylock Van",
    "castleoak securities": "CastleOak Securities", "mischler financial group": "Mischler Financial Group", "mfr securities": "MFR Securities",
    "guzman and company": "Guzman & Company", "r seelaus and co": "R. Seelaus & Co.", "penserra securities": "Penserra Securities",
    "roberts and ryan": "Roberts & Ryan", "roberts and ryan investments": "Roberts & Ryan", "cabrera capital markets": "Cabrera Capital Markets",
    "great pacific securities": "Great Pacific Securities", "bancroft capital": "Bancroft Capital", "independence point securities": "Independence Point Securities",
    "credit agricole securities usa": "Credit Agricole CIB", "credit agricole cib": "Credit Agricole CIB", "santander": "Santander",
    "santander investment securities": "Santander", "santander us capital markets": "Santander", "smbc nikko": "SMBC Nikko",
    "smbc nikko securities america": "SMBC Nikko", "mufg": "MUFG", "mufg securities americas": "MUFG", "mitsubishi ufj securities usa": "MUFG",
    "natixis": "Natixis", "natixis securities americas": "Natixis", "societe generale": "Societe Generale", "sg americas securities": "Societe Generale",
    "daiwa capital markets america": "Daiwa Capital Markets", "daiwa securities america": "Daiwa Capital Markets", "daiwa capital markets": "Daiwa Capital Markets",
    "intesa sanpaolo": "Intesa Sanpaolo", "imi intesa sanpaolo": "Intesa Sanpaolo", "wolfe": "Wolfe Research", "wolfe capital markets and advisory": "Wolfe Research",
    "wolfe nomura alliance": "Wolfe Research", "rosenblatt": "Rosenblatt Securities", "rosenblatt securities": "Rosenblatt Securities",
    "morgan keegan and company": "Morgan Keegan", "morgan keegan": "Morgan Keegan", "a g edwards and sons": "A.G. Edwards", "a g edwards": "A.G. Edwards",
    "legg mason wood walker": "Legg Mason", "legg mason": "Legg Mason", "adams harkness and hill": "Adams Harkness", "adams harkness": "Adams Harkness",
    "sandler o neill and partners": "Piper Sandler", "sandler o neill": "Piper Sandler", "keefe bruyette and woods": "KBW", "kbw": "KBW",
    "stephens": "Stephens", "stephens inc": "Stephens", "johnson rice and company": "Johnson Rice", "johnson rice": "Johnson Rice",
    "simmons and company international": "Simmons & Company", "simmons and company": "Simmons & Company", "tudor pickering holt and co": "Tudor, Pickering, Holt",
    "tudor pickering holt": "Tudor, Pickering, Holt", "capital one securities": "Capital One Securities", "pareto securities": "Pareto Securities",
    "clarksons platou securities": "Clarksons", "clarksons securities": "Clarksons", "fearnley securities": "Fearnley Securities",
    "dnb markets": "DNB Markets", "dnb nor markets": "DNB Markets", "nordea": "Nordea", "seb": "SEB", "skandinaviska enskilda banken": "SEB",
    "ing": "ING", "ing financial markets": "ING", "abn amro": "ABN AMRO", "abn amro securities": "ABN AMRO", "abn amro rothschild": "ABN AMRO",
    "rabo securities usa": "Rabobank", "rabobank": "Rabobank", "commerzbank": "Commerzbank", "unicredit": "UniCredit", "macquarie capital usa": "Macquarie",
    "macquarie capital": "Macquarie", "macquarie": "Macquarie", "china renaissance": "China Renaissance", "china renaissance securities hong kong": "China Renaissance",
    "cicc": "CICC", "china international capital corporation hong kong securities": "CICC", "china international capital corporation": "CICC",
    "haitong international securities": "Haitong", "haitong international": "Haitong", "futu": "Futu", "futu inc": "Futu", "tiger brokers": "Tiger Brokers",
    "tiger brokers nz": "Tiger Brokers", "us tiger securities": "Tiger Brokers", "aml global": "Tiger Brokers", "valuable capital": "Valuable Capital",
    "prime number capital": "Prime Number Capital", "univest securities": "Univest Securities", "spartan capital securities": "Spartan Capital",
    "spartan capital": "Spartan Capital", "r f lafferty and co": "R.F. Lafferty", "r f lafferty": "R.F. Lafferty", "bancroft": "Bancroft Capital",
    "dawson james securities": "Dawson James", "dawson james": "Dawson James", "revere securities": "Revere Securities", "the benchmark company": "The Benchmark Company",
    "brookline capital markets": "Brookline Capital Markets", "ascendiant capital markets": "Ascendiant Capital Markets", "viewtrade securities": "ViewTrade",
    "viewtrade": "ViewTrade", "pacific century securities": "Pacific Century Securities", "craft capital management": "Craft Capital", "d boral capital": "D. Boral Capital",
    "boral capital": "D. Boral Capital", "cuttone and co": "Cuttone & Co.", "needham and co": "Needham & Company", "lazard": "Lazard", "lazard capital markets": "Lazard",
    "lazard freres and co": "Lazard", "greenhill and co": "Greenhill", "moelis and company": "Moelis", "perella weinberg partners": "Perella Weinberg Partners",
    "pjt partners": "PJT Partners", "houlihan lokey": "Houlihan Lokey", "houlihan lokey capital": "Houlihan Lokey", "imperial capital": "Imperial Capital",
    "jones trading": "JonesTrading", "jonestrading institutional services": "JonesTrading", "jonestrading": "JonesTrading", "bof a securities": "BofA Securities",
    "ubs securities llc": "UBS", "rbc": "RBC Capital Markets", "key banc capital markets": "KeyBanc Capital Markets",
    "credit suisse securities": "Credit Suisse", "mufg securities": "MUFG", "smbc nikko securities": "SMBC Nikko", "natixis securities": "Natixis",
    "credit agricole securities": "Credit Agricole CIB", "samuel a ramirez": "Ramirez & Co.", "ramirez": "Ramirez & Co.",
    "pacific crest securities": "Pacific Crest Securities", "pacific crest": "Pacific Crest Securities", "muriel siebert and co": "Muriel Siebert & Co.",
    "muriel siebert": "Muriel Siebert & Co.", "wr securities": "Wolfe Research", "e trade securities": "E*TRADE Securities", "etrade securities": "E*TRADE Securities",
    "lebenthal and co": "Lebenthal & Co.", "lebenthal": "Lebenthal & Co.", "m r beal and company": "M.R. Beal & Company", "m r beal": "M.R. Beal & Company",
    "itau bba usa securities": "Itau BBA", "itau bba": "Itau BBA", "btig": "BTIG", "tpg capital bd": "TPG Capital BD", "smbc": "SMBC Nikko",
    "boci": "BOCI", "boci asia": "BOCI", "clsa": "CLSA", "dbs bank": "DBS", "dbs": "DBS", "wells fargo securities llc": "Wells Fargo",
    "citigroup global markets inc": "Citigroup", "deutsche bank securities inc": "Deutsche Bank", "barclays capital inc": "Barclays",
    "jefferies llc": "Jefferies", "cowen and company llc": "Cowen", "stifel nicolaus and company incorporated": "Stifel",
    "piper sandler and co": "Piper Sandler", "raymond james and associates inc": "Raymond James", "william blair and company llc": "William Blair",
    "canaccord genuity llc": "Canaccord Genuity", "oppenheimer and co inc": "Oppenheimer", "needham and company llc": "Needham & Company",
    "bofa securities inc": "BofA Securities", "goldman sachs and co llc": "Goldman Sachs", "morgan stanley and co llc": "Morgan Stanley",
    "j p morgan securities llc": "J.P. Morgan", "ubs securities": "UBS", "hsbc securities usa inc": "HSBC", "nomura securities international inc": "Nomura",
    "mizuho securities usa llc": "Mizuho", "bnp paribas securities corp": "BNP Paribas", "rbc capital markets llc": "RBC Capital Markets",
    "evercore group llc": "Evercore", "allen and company llc": "Allen & Company", "guggenheim securities llc": "Guggenheim Securities",
    "cantor fitzgerald and co": "Cantor Fitzgerald", "roth capital partners llc": "Roth Capital Partners", "maxim group llc": "Maxim Group",
    "aegis capital corp": "Aegis Capital", "thinkequity llc": "ThinkEquity", "ef hutton llc": "EF Hutton", "h c wainwright and co llc": "H.C. Wainwright",
    "ladenburg thalmann and co inc": "Ladenburg Thalmann", "b riley securities inc": "B. Riley Securities", "chardan capital markets llc": "Chardan",
    "craig hallum capital group llc": "Craig-Hallum", "lake street capital markets llc": "Lake Street Capital Markets", "northland securities inc": "Northland Securities",
    "d a davidson and co": "D.A. Davidson", "wedbush securities inc": "Wedbush Securities", "janney montgomery scott llc": "Janney Montgomery Scott",
    "leerink partners llc": "Leerink Partners", "bmo capital markets corp": "BMO Capital Markets", "td securities usa llc": "TD Securities",
    "truist securities inc": "Truist Securities", "academy securities inc": "Academy Securities", "loop capital markets llc": "Loop Capital Markets",
    "siebert williams shank and co llc": "Siebert Williams Shank", "telsey advisory group llc": "Telsey Advisory Group",
    "tigress financial partners llc": "Tigress Financial Partners", "c l king and associates inc": "C.L. King & Associates", "drexel hamilton llc": "Drexel Hamilton",
    "blaylock van llc": "Blaylock Van", "castleoak securities l p": "CastleOak Securities", "mischler financial group inc": "Mischler Financial Group",
    "mfr securities inc": "MFR Securities", "guzman and company": "Guzman & Company", "r seelaus and co llc": "R. Seelaus & Co.",
    "penserra securities llc": "Penserra Securities", "roberts and ryan inc": "Roberts & Ryan", "cabrera capital markets llc": "Cabrera Capital Markets",
    "great pacific securities": "Great Pacific Securities", "bancroft capital llc": "Bancroft Capital", "independence point securities llc": "Independence Point Securities",
    "santander us capital markets llc": "Santander", "smbc nikko securities america inc": "SMBC Nikko", "mufg securities americas inc": "MUFG",
    "natixis securities americas llc": "Natixis", "sg americas securities llc": "Societe Generale", "daiwa capital markets america inc": "Daiwa Capital Markets",
    "rosenblatt securities inc": "Rosenblatt Securities", "kbw inc": "KBW", "keefe bruyette and woods inc": "KBW", "stephens inc": "Stephens",
    "johnson rice and company l l c": "Johnson Rice", "capital one securities inc": "Capital One Securities", "pareto securities as": "Pareto Securities",
    "macquarie capital usa inc": "Macquarie", "china renaissance securities hong kong limited": "China Renaissance", "futu inc": "Futu",
    "us tiger securities inc": "Tiger Brokers", "valuable capital limited": "Valuable Capital", "prime number capital llc": "Prime Number Capital",
    "univest securities llc": "Univest Securities", "spartan capital securities llc": "Spartan Capital", "r f lafferty and co inc": "R.F. Lafferty",
    "dawson james securities inc": "Dawson James", "revere securities llc": "Revere Securities", "the benchmark company llc": "The Benchmark Company",
    "brookline capital markets": "Brookline Capital Markets", "ascendiant capital markets llc": "Ascendiant Capital Markets", "viewtrade securities inc": "ViewTrade",
    "pacific century securities llc": "Pacific Century Securities", "craft capital management llc": "Craft Capital", "d boral capital llc": "D. Boral Capital",
    "lazard freres and co llc": "Lazard", "greenhill and co llc": "Greenhill", "moelis and company llc": "Moelis", "houlihan lokey capital inc": "Houlihan Lokey",
    "imperial capital llc": "Imperial Capital", "jonestrading institutional services llc": "JonesTrading", "a g p alliance global partners": "A.G.P./Alliance Global Partners",
    "a g p": "A.G.P./Alliance Global Partners", "agp alliance global partners": "A.G.P./Alliance Global Partners", "alliance global partners": "A.G.P./Alliance Global Partners",
    "titan partners group": "Titan Partners", "titan partners group llc a division of american capital partners llc": "Titan Partners",
    "american capital partners": "American Capital Partners", "bancroft capital": "Bancroft Capital", "kingswood": "EF Hutton", "rodman and renshaw": "Rodman & Renshaw",
    "rodman and renshaw llc": "Rodman & Renshaw", "network 1 financial securities inc": "Network 1 Financial", "joseph stone capital": "Joseph Stone Capital",
    "eddid securities usa": "Eddid Securities", "cathay securities": "Cathay Securities", "dominari securities": "Dominari Securities", "benjamin securities": "Benjamin Securities",
    "wilson davis and co": "Wilson-Davis & Co.", "wilson davis": "Wilson-Davis & Co.", "r f lafferty": "R.F. Lafferty", "bancroft": "Bancroft Capital",
}
ROLE = re.compile(r"^\s*(?:(?:sole|joint|lead|senior|global|co)[- ]?)*(?:book[- ]?running managers?|bookrunners?|book[- ]?runners?|managers?|lead managers?|co-?managers?|"
                  r"global coordinators?|representatives?|co-?lead managers?|placement agents?|underwriters?|dealer managers?|financial advisors?|structuring agent)\s*\|?\s*$", re.I)
LEAD_ROLE = re.compile(r"book|bookrunner|lead manager|global coordinator|representative|sole manager|^\s*managers?", re.I)
CO_ROLE = re.compile(r"co-?manager|co-?lead|senior co|junior co", re.I)
FIRMISH = re.compile(r"\b(?:securities|capital|partners|& co|and co\b|markets|group|advisors|bank|investment|brothers|financial|sachs|stanley|morgan|jefferies|barclays|"
                     r"citi|ubs|hsbc|nomura|mizuho|cowen|stifel|baird|blair|needham|oppenheimer|evercore|lazard|cantor|roth|maxim|aegis|wainwright|ladenburg|"
                     r"craig|lake street|northland|davidson|wedbush|janney|leerink|bmo|scotia|td|truist|suntrust|academy|loop|ramirez|siebert|telsey|tigress|"
                     r"king|drexel|blaylock|castleoak|mischler|guzman|seelaus|penserra|cabrera|credit|santander|smbc|mufg|natixis|societe|daiwa|intesa|wolfe|"
                     r"rosenblatt|keegan|edwards|legg|adams|sandler|keefe|stephens|johnson rice|simmons|tudor|pareto|clarksons|fearnley|dnb|nordea|seb|ing|"
                     r"abn|rabo|commerzbank|unicredit|macquarie|renaissance|cicc|haitong|futu|tiger|valuable|prime number|univest|spartan|lafferty|dawson|"
                     r"revere|benchmark|brookline|ascendiant|viewtrade|pacific century|craft|boral|cuttone|greenhill|moelis|perella|pjt|houlihan|imperial|jones)\b", re.I)
NOT_FIRM = re.compile(r"^(?:new york|delaware|california|texas|nevada|florida|boston|chicago|san francisco|los angeles|united states|"
                      r"total|name|none|n/a|per|represents|price|proceeds|ipo price|per (?:share|unit|ads|ordinary share|common share))\b|"
                      r"\b(?:expenses|discounts?|commissions?|proceeds|allotment|exercised|aggregate|payable|before|to us|"
                      r"stockholders|shareholders|redemptions?|trust)\b|\b(?:prospectus|underwriters? (?:expect|will|may|have|are)|the date|table of contents|neither|common stock|per share|offering|alphabetical|"
                      r"representation|commission|criminal|page|shares|dated|subject to|approved|securities and exchange)\b", re.I)


def _alias_of(name: str) -> tuple[str | None, str]:
    """(the alias table's name or None, the stripped key): the table is tried on the cleaned name and again after
    each legal suffix comes off, so "Samuel A. Ramirez & Company, Inc." finds "samuel a ramirez and company"."""
    s = re.sub(r"\(\s*(?:usa|u\.?s\.?a?\.?|uk|u\.k\.|hong kong|asia|europe|canada)\s*\)", " ", name.lower())
    s = s.replace("&", " and ").replace("’", "'").replace("'", "")
    words = re.sub(r"[^a-z0-9]+", " ", s).split()
    if words and words[0] == "the":
        words.pop(0)
    while True:
        k = " ".join(words)
        if k in ALIASES:
            return ALIASES[k], k
        if words and words[-1] in SUFFIX:
            words.pop()
        else:
            return None, k


def name_key(name: str) -> str:
    """"Goldman, Sachs & Co." and "GOLDMAN SACHS & CO. LLC" are "goldman sachs"."""
    alias, k = _alias_of(name)
    return name_key_raw(alias) if alias else k


def name_key_raw(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", name.lower().replace("&", " and ")).split()
    while s and s[-1] in SUFFIX:
        s.pop()
    return " ".join(s)


def canonical(name: str) -> str:
    """The firm's one display name: the alias table's, else the name as written, cleaned."""
    alias, _ = _alias_of(name)
    if alias:
        return alias
    clean = re.sub(r"\s*\(\d+\)|\s*\*+$|\s*\|", "", name).strip(" ,;.")
    clean = re.sub(r"\s+", " ", clean)
    if clean.isupper() and len(clean) > 4:
        clean = _title(clean)
    return clean[:120]


def _title(s: str) -> str:
    small = {"and", "of", "the", "de", "&"}
    out = []
    for w in s.lower().split():
        if w in small:
            out.append(w)
        elif len(w) <= 3 and w.endswith("."):
            out.append(w.upper())
        else:
            out.append(w[0].upper() + w[1:])
    return " ".join(out)


_alias_rx = None


def alias_regex() -> re.Pattern:
    """Every alias and canonical name, longest first, as a word-bounded alternation over cleaned text."""
    global _alias_rx
    if _alias_rx is None:
        names = set(ALIASES) | {name_key_raw(v) for v in ALIASES.values()}
        parts = sorted((n for n in names if len(n) >= 3), key=len, reverse=True)
        _alias_rx = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(p) for p in parts) + r")(?![a-z0-9])")
    return _alias_rx


def _clean_for_scan(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("&", " and ")).strip()


def known_names_in(segment: str) -> list[str]:
    """The known firms named in a run of text, in order ("Morgan Stanley Goldman Sachs & Co. LLC" is two)."""
    s = _clean_for_scan(segment)
    found, pos = [], 0
    while True:
        m = alias_regex().search(s, pos)
        if not m:
            break
        k = m.group(0)
        name = ALIASES.get(k) or next((v for v in ALIASES.values() if name_key_raw(v) == k), None)
        if name and name not in found:
            found.append(name)
        pos = m.end()
    return found


def _looks_like_firm(seg: str) -> bool:
    s = seg.strip(" ,;*|")
    if not (3 <= len(s) <= 90) or not s[0].isalpha() or NOT_FIRM.search(s) or len(s.split()) > 9:
        return False
    if re.search(r"\d{4}|\$|%", s):
        return False
    small = {"and", "of", "the", "&", "de", "for", "la", "du", "von", "van", "y", "e", "a"}
    if any(w[0].isalpha() and w[0].islower() and w.lower() not in small for w in s.split()):
        return False
    return bool(FIRMISH.search(s)) or (s[0].isupper() and s.replace(".", "").replace(",", "").replace("&", "and").replace(" ", "").isalpha()
                                       and 2 <= len(s.split()) <= 5 and s not in ("Table of Contents",))


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
BLOCK_END = re.compile(r"(?i)prospectus dated|the date of this prospectus|^\s*(?:" + MONTHS + r")\s+\d{1,2},\s+\d{4}\s*\|?\s*$|"
                       r"^\s*\|?\s*table of contents|^\s*prospectus summary|^\s*summary\s*\|?\s*$|about this prospectus|you should rely only",
                       re.M)


GENERIC = {"securities", "corporation", "corp", "brothers", "incorporated", "inc", "llc", "company", "co", "capital", "markets",
           "partners", "group", "international", "and", "of", "the", "usa", "limited", "ltd", "lp", "l.p.", "bank", "investment",
           "advisors", "america", "americas", "global", "services", "financial", "equity", "equities", "plc", "ag", "sa"}


def _generic(seg: str) -> bool:
    words = re.sub(r"[^a-z0-9.]+", " ", seg.lower().replace("&", " and ")).split()
    return not words or all(w in GENERIC for w in words)


def cover_underwriters(text: str) -> tuple[list[str], list[str]]:
    """(underwriters, leads) from the names printed at the foot of the cover page: after the delivery date or the
    'criminal offense' legend, before the prospectus date, with any role labels (Sole Book-Running Manager,
    Co-Managers) read; without labels the first line is the leads when it names at most four firms."""
    cover = text[:COVER_CHARS]
    starts = [m.end() for m in re.finditer(r"(?i)criminal offense\.?|expect to deliver[^.]{0,200}\.|delivery of the (?:shares|ADSs|units)[^.]{0,200}\.|"
                                           r"will be made (?:on or about|against payment)[^.]{0,120}\.", cover)]
    if not starts:
        return [], []
    start = starts[0]
    for s in starts[1:]:
        if s - start < 3000:
            start = s
    block = cover[start:start + 5000]
    m = BLOCK_END.search(block)
    if m:
        block = block[:m.start()]
    names, leads, role_lead = [], [], None
    first_line_names = None
    # names wrap across lines ("Banc\n of America Securities LLC"), so known firms are read from the joined block
    # and the lines only add unknown firms and the role labels
    flat_known = known_names_in(block)
    lines = block.split("\n")
    for i, line in enumerate(lines):
        segs = [s.strip(" ,;*") for s in line.split("|")]
        segs = [s for s in segs if s and s.lower() not in ("(in alphabetical order)", "in alphabetical order", "in alphabetical order*")]
        line_names = []
        for seg in segs:
            if ROLE.match(seg):
                role_lead = bool(LEAD_ROLE.search(seg)) and not CO_ROLE.search(seg)
                continue
            seg = re.sub(r"\s*\(\d+\)|\s*\*+", "", seg).strip()
            known = known_names_in(seg)
            if known:
                line_names.extend(known)
            else:
                joined = known_names_in(seg + " " + lines[i + 1].split("|")[0] if i + 1 < len(lines) else seg)
                if joined or _generic(seg) or not _looks_like_firm(seg):
                    continue        # a wrapped half of a known name, or not a firm
                line_names.append(canonical(seg))
        for n in line_names:
            if n not in names:
                names.append(n)
                if role_lead:
                    leads.append(n)
        if line_names and first_line_names is None:
            first_line_names = [n for n in line_names if n in flat_known]
    for n in flat_known:
        if n not in names:
            names.append(n)
    if not leads and role_lead is None and first_line_names and len(first_line_names) <= 4:
        leads = list(first_line_names)
    return names[:60], leads[:8]


TABLE_HEAD = re.compile(r"(?i)number of (?:firm )?(?:shares|ADSs|units|ordinary shares|common shares|class [a-c]|securities|depositary|american)")
ROW_NUM = re.compile(r"^[\s|]*\$?\s*(\d{1,3}(?:,\d{3})+|\d{4,})[\s|]*$")
ROW_NAME_NUM = re.compile(r"^\s*\|?\s*([A-Za-z][^|]*?[A-Za-z.)'’])\s*[.…_\s|]*\$?\s*(\d{1,3}(?:,\d{3})+|\d{4,})\s*\|?\s*(?:\|\s*)*$")
REPS = re.compile(r"(?i)(?:acting as|act as|as the|are the|is the|be the) (?:sole |joint |lead |co-)?(?:representatives?|book-?running managers?|bookrunners?|managing underwriters?)")


SECTION_HEAD = re.compile(r"(?i)^\s*\|?\s*(?:underwriting|underwriters|plan of distribution|underwriting \(conflicts? of interest\)|"
                          r"underwriting and plan of distribution)\s*\|?\s*$")


def underwriting_table(text: str) -> list[tuple[str, int | None]]:
    """The 'Name | Number of Shares' table in the Underwriting section: (name, shares) rows in order. The section
    is the last 'Underwriting' heading line that is followed by the underwriting agreement's wording; without one,
    any table whose header mentions the underwriters."""
    lines = text.split("\n")
    heads = [i for i, ln in enumerate(lines) if len(ln) < 80 and SECTION_HEAD.match(ln)]
    spans = []
    for h in heads:
        window = "\n".join(lines[h + 1:h + 400]).lower()
        if "severally" in window or "underwriting agreement" in window or "purchase agreement" in window:
            spans.append((h, min(len(lines), h + 400)))
    if not spans:
        spans = [(0, len(lines))]
    best: list[tuple[str, int | None]] = []
    for lo, hi in spans:
        best = max(best, _table_rows(lines, lo, hi, loose=(lo == 0)), key=len)
    seen, out = set(), []
    for n, v in best:
        k = name_key(n)
        if k and k not in seen:
            seen.add(k)
            out.append((canonical(n), v))
    return out[:80]


def _table_rows(lines: list[str], lo: int, hi: int, loose: bool) -> list[tuple[str, int | None]]:
    best: list[tuple[str, int | None]] = []
    for i in range(lo, hi):
        line = lines[i]
        if len(line) > 100 or not TABLE_HEAD.search(line):
            continue
        back = " ".join(lines[max(0, i - 8):i + 1]).lower()
        if "underwriter" not in back and ("name" not in back or loose):
            continue
        rows, pending, blanks, seen_lines = [], "", 0, 0
        for ln in lines[i + 1:i + 2000]:
            s = ln.strip()
            if not s or re.fullmatch(r"[|\s]*", s):
                blanks += 1
                if blanks > 60:
                    break
                continue
            blanks = 0
            seen_lines += 1
            if seen_lines > 300:
                break
            if re.match(r"(?i)^\s*\|?\s*total", s):
                break
            m = ROW_NAME_NUM.match(ln)
            if m:
                rows.append((pending + " " + m.group(1) if pending and len(pending) < 40 else m.group(1), _num(m.group(2))))
                pending = ""
                continue
            m = ROW_NUM.match(ln)
            if m and pending:
                rows.append((pending, _num(m.group(1))))
                pending = ""
                continue
            seg = re.sub(r"\|", " ", s).strip()
            if re.match(r"(?i)^(?:name|underwriters?|name of underwriters?|number of.*)$", seg):
                continue
            if len(seg) > 120 or re.search(r"(?i)\b(?:severally|agreed|pursuant|subject to|the underwriters|following table)\b", seg):
                if rows:
                    break
                continue
            pending = (pending + " " + seg).strip() if pending and len(pending) < 60 else seg
        rows = [(re.sub(r"\s*\(\d+\)|\s*\*+$", "", n).strip(" ,;."), v) for n, v in rows]
        rows = [(n, v) for n, v in rows if n and n[0].isalpha() and 3 <= len(n) <= 110 and not NOT_FIRM.search(n)
                and len(n.split()) <= 9 and not re.search(r"\. [a-z]|\d{4}|\$|%", n)
                and not re.match(r"(?i)^(?:total|name|underwriters?)$", n)]
        if len(rows) > len(best):
            best = rows
    return best


def representatives(text: str, table: list[tuple[str, int | None]]) -> list[str]:
    """The firms the Underwriting section says are acting as representatives or book-running managers."""
    keys = {name_key(n): n for n, _ in table}
    out = []
    for m in REPS.finditer(text):
        before = text[max(0, m.start() - 450):m.start()]
        if re.search(r"(?i)selling (?:stock|share)holder|co-?managers? are", before[-80:]):
            continue
        found = known_names_in(before)
        s = _clean_for_scan(before)
        for k, n in keys.items():
            if k and len(k) >= 4 and re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", s) and n not in found:
                found.append(n)
        for n in found:
            if n not in out:
                out.append(n)
        if out:
            break
    return out[:8]


def parse_underwriters(text: str) -> dict:
    """underwriters (names in cover order, the table's order when there is no cover block), with the shares
    each took from the table, and the leads."""
    cover, cover_leads = cover_underwriters(text)
    table = underwriting_table(text)
    shares = {name_key(n): v for n, v in table}
    names = list(cover)
    for n, _ in table:
        if name_key(n) not in {name_key(x) for x in names}:
            names.append(n)
    leads = representatives(text, table)
    if not leads:
        leads = cover_leads
    if not leads and table:
        top = max((v or 0) for _, v in table)
        if top:
            leads = [n for n, v in table if v and v >= top * 0.5][:6]
    if not leads and names:
        leads = names[:1]
    lead_keys = {name_key(n) for n in leads}
    rows = [{"name": n, "key": name_key(n), "shares": shares.get(name_key(n)), "lead": name_key(n) in lead_keys} for n in names if name_key(n)]
    # leads named only in the representatives sentence still belong in the list
    for n in leads:
        if name_key(n) not in {r["key"] for r in rows}:
            rows.insert(0, {"name": n, "key": name_key(n), "shares": shares.get(name_key(n)), "lead": True})
    return {"underwriters": rows, "leads": [r["name"] for r in rows if r["lead"]], "table_rows": len(table), "cover_names": len(cover)}


# --- the run ---------------------------------------------------------------------------------------------

def parse_document(text: str, form: str) -> dict:
    cover = parse_cover(text, form)
    uw = parse_underwriters(text)
    notes = list(cover.pop("notes"))
    if uw["table_rows"]:
        notes.append(f"underwriting table {uw['table_rows']}")
    if uw["cover_names"]:
        notes.append(f"cover names {uw['cover_names']}")
    useful = bool(any(cover[k] for k in ("price", "price_low", "shares_offered")) or uw["underwriters"])
    return {**cover, "underwriters": uw["underwriters"], "leads": uw["leads"], "note": ", ".join(notes) or "no terms found",
            "useful": useful}


def plan(conn, ciks: list[str] | None = None, limit: int | None = None, reparse: bool = False) -> list[dict]:
    """Jobs: per registrant, its final prospectus (the earliest 424B4/424B1, the next as a fallback) and its latest
    registration statement (older amendments as fallbacks), skipping the roles already parsed. Priced
    registrants first, newest first."""
    where, params = "", []
    if ciks:
        where = "WHERE c.cik = ANY(%s)"
        params.append([str(int(c)) for c in ciks])
    done = set()
    if not reparse:
        done = {(r[0], r[1]) for r in conn.execute("SELECT cik, role FROM ipo_offerings").fetchall()}
    rows = conn.execute(f"""
        SELECT c.cik, c.priced, c.last_filed, f.accession, f.form, f.filed FROM ipo_companies c
        JOIN ipo_filings f ON f.cik = c.cik AND f.form = ANY(%s) {where.replace('WHERE', 'AND') if where else ''}
        ORDER BY c.priced DESC NULLS LAST, c.last_filed DESC, c.cik, f.filed, f.accession""",
        [list(REG_FORMS) + list(FINAL_FORMS)] + params).fetchall()
    jobs, order, priced_by = {}, [], {}
    for cik, priced, last_filed, acc, form, filed in rows:
        priced_by[cik] = priced
        role = "final" if form in FINAL_FORMS else "reg"
        if (cik, role) in done:
            continue
        key = (cik, role)
        if key not in jobs:
            jobs[key] = {"cik": cik, "role": role, "candidates": []}
            order.append(key)
        jobs[key]["candidates"].append((acc, form, filed))
    out = []
    for key in order:
        j = jobs[key]
        if j["role"] == "reg":
            priced = priced_by.get(j["cik"])
            before = [c for c in j["candidates"] if not priced or c[2] <= priced]
            j["candidates"] = (sorted(before or j["candidates"], key=lambda c: (c[2], c[0]), reverse=True))[:3]
        else:
            j["candidates"] = j["candidates"][:2]
        out.append(j)
        if limit and len(out) >= limit:
            break
    return out


def _write(conn, cik: str, acc: str, form: str, filed, role: str, url: str | None, chars: int, r: dict | None, note: str) -> None:
    conn.execute("DELETE FROM ipo_offering_underwriters WHERE accession = %s AND cik = %s", (acc, cik))
    if r is None:
        conn.execute("""INSERT INTO ipo_offerings (accession, cik, form, filed, role, doc_url, doc_chars, parsed_at, parse_note)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s)
                        ON CONFLICT (accession, cik) DO UPDATE SET parsed_at = now(), parse_note = EXCLUDED.parse_note, doc_url = EXCLUDED.doc_url""",
                     (acc, cik, form, filed, role, url, chars, note))
        return
    uws = r["underwriters"]
    conn.execute("""INSERT INTO ipo_offerings (accession, cik, form, filed, role, is_ipo, security, price_low, price_high, price,
                        shares_offered, shares_company, shares_selling, shares_sold, proceeds, exchange, ticker, underwriters,
                        lead_underwriters, n_underwriters, doc_url, doc_chars, parsed_at, parse_note)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
                    ON CONFLICT (accession, cik) DO UPDATE SET is_ipo = EXCLUDED.is_ipo, security = EXCLUDED.security,
                        price_low = EXCLUDED.price_low, price_high = EXCLUDED.price_high, price = EXCLUDED.price,
                        shares_offered = EXCLUDED.shares_offered, shares_company = EXCLUDED.shares_company, shares_selling = EXCLUDED.shares_selling,
                        shares_sold = EXCLUDED.shares_sold, proceeds = EXCLUDED.proceeds, exchange = EXCLUDED.exchange, ticker = EXCLUDED.ticker,
                        underwriters = EXCLUDED.underwriters, lead_underwriters = EXCLUDED.lead_underwriters, n_underwriters = EXCLUDED.n_underwriters,
                        doc_url = EXCLUDED.doc_url, doc_chars = EXCLUDED.doc_chars, parsed_at = now(), parse_note = EXCLUDED.parse_note""",
                 (acc, cik, form, filed, role, r["is_ipo"], r["security"], r["price_low"], r["price_high"], r["price"], r["shares_offered"],
                  r["shares_company"], r["shares_selling"], r["shares_offered"] if role == "final" else None, r["proceeds"], r["exchange"],
                  r["ticker"], json.dumps(uws), json.dumps(r["leads"]), len(uws), url, chars, note))
    with conn.cursor() as cur:
        db.copy_rows(cur, "ipo_offering_underwriters", ["accession", "cik", "rank", "name", "name_key", "shares", "lead"],
                     ((acc, cik, i + 1, u["name"][:200], u["key"][:200], u["shares"], u["lead"]) for i, u in enumerate(uws)))


def process(conn, job: dict, status=print) -> dict:
    """Read the job's candidates until one yields terms; every candidate read gets a row."""
    cik, role = job["cik"], job["role"]
    result = {"cik": cik, "role": role, "hit": False, "price": None, "range": None, "shares": None, "uw": 0}
    for acc, form, filed in job["candidates"]:
        try:
            url, text, note = primary_document(cik, acc, form)
        except RuntimeError as e:
            _write(conn, cik, acc, form, filed, role, None, 0, None, f"fetch failed: {e}"[:300])
            conn.commit()
            status(f"terms: {cik} {acc} fetch failed")
            continue
        if text is None:
            _write(conn, cik, acc, form, filed, role, url, 0, None, note)
            conn.commit()
            continue
        stripped = strip_html(text)
        r = parse_document(stripped, form)
        _write(conn, cik, acc, form, filed, role, url, len(stripped), r, f"{note}; {r['note']}"[:300])
        conn.commit()
        if r["useful"]:
            result.update(hit=True, price=r["price"], range=(r["price_low"], r["price_high"]) if r["price_low"] else None,
                          shares=r["shares_offered"], uw=len(r["underwriters"]))
            break
    return result


def run(ciks: list[str] | None = None, limit: int | None = None, workers: int = 3, status=print, reparse: bool = False) -> dict:
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        jobs = plan(conn, ciks, limit, reparse)
    status(f"terms: {len(jobs):,} documents to read ({sum(1 for j in jobs if j['role'] == 'final'):,} final prospectuses, "
           f"{sum(1 for j in jobs if j['role'] == 'reg'):,} registration statements), {workers} workers")
    q: queue.Queue = queue.Queue()
    for j in jobs:
        q.put(j)
    counts = {"done": 0, "hit": 0, "final": 0, "final_price": 0, "reg": 0, "reg_range": 0, "uw": 0, "errors": 0}
    lock = threading.Lock()
    t0 = time.time()

    def worker():
        conn = db.connect()
        try:
            while not STOP_FILE.exists():
                try:
                    job = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    r = process(conn, job, status)
                except Exception as e:  # noqa: BLE001 - one document must not stop the run
                    conn.rollback()
                    with lock:
                        counts["errors"] += 1
                    status(f"terms: {job['cik']} {job['role']} error {type(e).__name__}: {e}"[:300])
                    continue
                with lock:
                    counts["done"] += 1
                    counts["hit"] += r["hit"]
                    counts[r["role"]] += 1
                    if r["role"] == "final" and r["price"]:
                        counts["final_price"] += 1
                    if r["role"] == "reg" and r["range"]:
                        counts["reg_range"] += 1
                    counts["uw"] += bool(r["uw"])
                    n = counts["done"]
                if n % 100 == 0 or n == len(jobs):
                    el = time.time() - t0
                    status(f"terms: {n:,}/{len(jobs):,} in {el/60:.0f} min; terms found {counts['hit']:,}; final with price "
                           f"{counts['final_price']:,}/{counts['final']:,}; registrations with range {counts['reg_range']:,}/{counts['reg']:,}; "
                           f"underwriters named {counts['uw']:,}; errors {counts['errors']}")
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    last_rollup = 0
    while any(t.is_alive() for t in threads):
        time.sleep(30)
        if counts["done"] - last_rollup >= 1500:         # the pages keep up with the run
            last_rollup = counts["done"]
            try:
                with db.connect() as conn:
                    rollup(conn, status)
            except Exception as e:  # noqa: BLE001
                status(f"terms: interim roll-up failed: {e}")
    for t in threads:
        t.join()
    if STOP_FILE.exists():
        status("terms: stopped by the STOP file")
    with db.connect() as conn:
        conn.execute(DDL)
        out = rollup(conn, status)
        db.progress(conn, "s1:terms", "done", kind="s1", rows=conn.execute("SELECT count(*) FROM ipo_offerings").fetchone()[0])
        conn.commit()
    return {**counts, **out}


# --- roll-ups --------------------------------------------------------------------------------------------

def rollup(conn, status=print) -> dict:
    """ipo_companies' headline terms and ipo_underwriters from ipo_offerings. Idempotent; runs after every
    loader.s1 load too (that load truncates ipo_companies)."""
    conn.execute("SET statement_timeout = 0")
    conn.execute("""UPDATE ipo_companies SET price_low = NULL, price_high = NULL, offer_price = NULL, offer_shares = NULL,
                    offer_proceeds = NULL, offer_exchange = NULL, offer_ticker = NULL, offer_date = NULL, offer_is_ipo = NULL,
                    lead_underwriters = NULL, n_underwriters = NULL
                    WHERE offer_price IS NOT NULL OR price_low IS NOT NULL OR lead_underwriters IS NOT NULL OR offer_shares IS NOT NULL""")
    n = conn.execute("""
        WITH fin AS (SELECT DISTINCT ON (cik) * FROM ipo_offerings WHERE role = 'final'
                     ORDER BY cik, price IS NULL, filed, accession),
             reg AS (SELECT DISTINCT ON (cik) * FROM ipo_offerings WHERE role = 'reg'
                     ORDER BY cik, price_low IS NULL, filed DESC, accession DESC)
        UPDATE ipo_companies c SET
            price_low = reg.price_low, price_high = reg.price_high,
            offer_price = fin.price, offer_shares = coalesce(fin.shares_offered, reg.shares_offered),
            offer_proceeds = fin.proceeds, offer_exchange = coalesce(fin.exchange, reg.exchange),
            offer_ticker = coalesce(fin.ticker, reg.ticker), offer_date = CASE WHEN fin.price IS NOT NULL THEN fin.filed END,
            offer_is_ipo = coalesce(fin.is_ipo, reg.is_ipo),
            lead_underwriters = nullif(array_to_string(ARRAY(SELECT jsonb_array_elements_text(coalesce(
                CASE WHEN jsonb_array_length(coalesce(fin.lead_underwriters, '[]'::jsonb)) > 0 THEN fin.lead_underwriters END,
                reg.lead_underwriters, '[]'::jsonb))), '; '), ''),
            n_underwriters = coalesce(nullif(fin.n_underwriters, 0), reg.n_underwriters)
        FROM (SELECT cik FROM fin UNION SELECT cik FROM reg) k
        LEFT JOIN fin ON fin.cik = k.cik LEFT JOIN reg ON reg.cik = k.cik
        WHERE c.cik = k.cik""").rowcount
    conn.commit()
    # the firms
    conn.execute("DELETE FROM ipo_underwriters")
    m = conn.execute("""
        INSERT INTO ipo_underwriters (name_key, name, deals, lead_deals, ipos, proceeds, lead_proceeds, first, last, filings, by_year, aliases, updated)
        SELECT u.name_key, (array_agg(u.name ORDER BY (u.name = (SELECT min(x.name) FROM ipo_offering_underwriters x WHERE x.name_key = u.name_key)) DESC, o.filed DESC))[1],
               count(*) FILTER (WHERE o.role = 'final'), count(*) FILTER (WHERE o.role = 'final' AND u.lead),
               count(*) FILTER (WHERE o.role = 'final' AND o.is_ipo),
               sum(o.proceeds) FILTER (WHERE o.role = 'final'), sum(o.proceeds) FILTER (WHERE o.role = 'final' AND u.lead),
               min(o.filed) FILTER (WHERE o.role = 'final'), max(o.filed) FILTER (WHERE o.role = 'final'), count(*),
               (SELECT jsonb_object_agg(y.year, jsonb_build_object('deals', y.deals, 'lead', y.lead, 'proceeds', y.proceeds))
                FROM (SELECT extract(year FROM o2.filed)::int AS year, count(*) AS deals, count(*) FILTER (WHERE u2.lead) AS lead,
                             sum(o2.proceeds) AS proceeds
                      FROM ipo_offering_underwriters u2 JOIN ipo_offerings o2 ON o2.accession = u2.accession AND o2.cik = u2.cik
                      WHERE u2.name_key = u.name_key AND o2.role = 'final' GROUP BY 1) y),
               (SELECT jsonb_agg(DISTINCT a.name) FROM (SELECT DISTINCT name FROM ipo_offering_underwriters WHERE name_key = u.name_key LIMIT 12) a),
               now()
        FROM ipo_offering_underwriters u JOIN ipo_offerings o ON o.accession = u.accession AND o.cik = u.cik
        WHERE u.name_key <> '' GROUP BY u.name_key""").rowcount
    # the broker-dealer and adviser records (sec_firm_aliases) with the same normalised name
    if conn.execute("SELECT to_regclass('sec_firm_aliases') IS NOT NULL").fetchone()[0]:
        rows = conn.execute("SELECT name_key, name, aliases FROM ipo_underwriters").fetchall()
        for key, name, aliases in rows:
            cands = []
            for nm in [name] + list(aliases or []):
                c = core(nm)
                if c and c not in cands:
                    cands.append(c)
            if not cands:
                continue
            bd = conn.execute("""SELECT a.key, a.alias FROM sec_firm_aliases a WHERE a.kind = 'bd' AND a.alias_norm = ANY(%s)
                                 ORDER BY array_position(%s, a.alias_norm), a.key LIMIT 1""", (cands, cands)).fetchone()
            ia = conn.execute("""SELECT a.key FROM sec_firm_aliases a WHERE a.kind = 'ia' AND a.alias_norm = ANY(%s)
                                 ORDER BY array_position(%s, a.alias_norm), a.key LIMIT 1""", (cands, cands)).fetchone()
            if bd or ia:
                conn.execute("UPDATE ipo_underwriters SET bd_cik = %s, bd_name = %s, ia_crd = %s WHERE name_key = %s",
                             (bd[0] if bd else None, bd[1] if bd else None, ia[0] if ia else None, key))
    conn.commit()
    status(f"terms: {n:,} registrants with terms, {m:,} underwriters")
    return {"companies_with_terms": n, "underwriters": m}


def rekey(conn, status=print) -> int:
    """Rename every underwriter row by the current alias table (after ALIASES grows), then roll up again."""
    conn.execute("SET statement_timeout = 0")
    rows = conn.execute("SELECT DISTINCT name FROM ipo_offering_underwriters").fetchall()
    n = 0
    for (name,) in rows:
        new_name, new_key = canonical(name), name_key(name)
        if new_key and new_name:
            n += conn.execute("UPDATE ipo_offering_underwriters SET name = %s, name_key = %s WHERE name = %s AND (name_key <> %s OR name <> %s)",
                              (new_name, new_key, name, new_key, new_name)).rowcount
    conn.execute("""UPDATE ipo_offerings o SET underwriters = (SELECT jsonb_agg(jsonb_build_object('name', w.name, 'key', w.name_key, 'shares', w.shares,
                                                                                               'lead', w.lead) ORDER BY w.rank)
                                                           FROM ipo_offering_underwriters w WHERE w.accession = o.accession AND w.cik = o.cik),
                        lead_underwriters = (SELECT coalesce(jsonb_agg(w.name ORDER BY w.rank), '[]'::jsonb)
                                             FROM ipo_offering_underwriters w WHERE w.accession = o.accession AND w.cik = o.cik AND w.lead)
                    WHERE EXISTS (SELECT 1 FROM ipo_offering_underwriters w WHERE w.accession = o.accession AND w.cik = o.cik)""")
    conn.commit()
    status(f"terms: {n:,} underwriter rows renamed")
    rollup(conn, status)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--limit", type=int, help="documents to read this run")
    ap.add_argument("--ciks", help="comma-separated CIKs (default: every registrant not yet read)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rollup-only", action="store_true", help="only recompute ipo_companies' terms and ipo_underwriters")
    ap.add_argument("--reparse", action="store_true", help="read the documents again even when a row exists")
    ap.add_argument("--rekey", action="store_true", help="rename the underwriters by the current alias table, then roll up")
    a = ap.parse_args(argv)
    log = lambda s: print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {s}", flush=True)  # noqa: E731
    if a.rollup_only or a.rekey:
        with db.connect() as conn:
            conn.execute(DDL)
            (rekey if a.rekey else rollup)(conn, log)
            conn.commit()
        return 0
    out = run([c.strip() for c in a.ciks.split(",")] if a.ciks else None, a.limit, a.workers, log, a.reparse)
    log("terms: " + ", ".join(f"{k} {v:,}" for k, v in out.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
