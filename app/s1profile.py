"""S-1 strategic profile ("SWOT from the company's own words").

A user enters a company (name or ticker) and sees what the company itself told the SEC in its S-1, S-1/A, F-1 or F-1/A:
strengths ("Our Competitive Strengths"), opportunities ("Our Growth Strategy", "Market Opportunity", "Industry"),
weaknesses and threats (the "Risk Factors", grouped by category and flagged company-specific or boilerplate) and the
competitors named in the "Competition" section. Every item keeps a citation: filing, date, section and a link to the
spot in the filing on EDGAR (a text-fragment link, which jumps to the passage in a browser).

Source: SEC EDGAR only (company tickers JSON, submissions API, filing archives), through the polite fetcher in
loader/s1_terms.py (User-Agent naming us, throttled). The filing list comes from ipo_filings (loader/s1) and, for a
company that table lacks, the submissions API. A filing is read on first view and the result is kept in s1_profile.
Extraction is rule based (headings and bold lead-ins). The only model calls are one short plain-language summary per
quadrant and the list of competitor names in the Competition text; both are optional and the page works without them.

Live for everyone (owner, 2026-11-24: FURP features are never dev-only). Pages are noindex.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import threading
import time
import urllib.parse
from html import unescape

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import db

log = logging.getLogger("np.s1profile")
router = APIRouter()
FORMS = ("S-1", "S-1/A", "F-1", "F-1/A")
ANNUAL = ("10-K", "20-F")      # annual reports: Item 1 Business (Competition) and Item 1A Risk Factors (owner, 2026-11-24)
VERSION = 8      # bump to rebuild cached profiles after the extraction rules change


def public() -> bool:
    return True   # live for everyone (owner, 2026-11-24: FURP features are never dev-only)


def _gate():
    if not public():
        raise HTTPException(404)


_ready = [False]


def ensure_table() -> None:
    if _ready[0]:
        return
    with db.pool.connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS s1_profile (
            accession text PRIMARY KEY, cik text NOT NULL, form text, filed date, doc_url text, version int NOT NULL,
            built timestamptz NOT NULL DEFAULT now(), data jsonb NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS s1_profile_cik ON s1_profile (cik)")
    _ready[0] = True


# ---- finding the company and its filings -------------------------------------------------------------------------------

def _clean_name(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def search(q: str, limit: int = 12) -> list[dict]:
    """Companies by ticker or name: ipo_companies first, then SEC's company_tickers.json for a ticker we do not hold."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    ensure_table()
    out: list[dict] = []
    with db.pool.connection() as conn:
        like = _clean_name(q)
        rows = conn.execute(
            """SELECT cik, name, tickers, offer_ticker, offer_date, offer_proceeds, n_filings, last_filed
               FROM ipo_companies
               WHERE upper(offer_ticker) = upper(%s) OR %s = ANY(string_to_array(upper(coalesce(tickers,'')), ','))
                  OR name_core LIKE %s
               ORDER BY (upper(offer_ticker) = upper(%s)) DESC, offer_proceeds DESC NULLS LAST, last_filed DESC LIMIT %s""",
            (q, q.upper(), like + "%", q, limit)).fetchall()
        for r in rows:
            r = dict(r)
            out.append({"cik": r["cik"], "name": r["name"], "ticker": r["offer_ticker"] or (r["tickers"] or "").split(",")[0],
                        "offered": r["offer_date"].isoformat() if r["offer_date"] else None,
                        "proceeds": float(r["offer_proceeds"]) if r["offer_proceeds"] is not None else None,
                        "filings": r["n_filings"]})
    if not out:
        try:
            from app import company_route
            if re.fullmatch(r"[A-Za-z.\-]{1,6}", q):
                company_route._load()
                for r in company_route._idx["rows"]:
                    if r["ticker"].upper() == q.upper():
                        out.append({"cik": r["cik"], "name": r["name"], "ticker": r["ticker"], "offered": None, "proceeds": None,
                                    "filings": None})
            if not out:
                m = company_route.match_company(q)
                if m:
                    out.append({"cik": m["cik"], "name": m["name"], "ticker": m["ticker"], "offered": None, "proceeds": None,
                                "filings": None})
        except Exception:  # noqa: BLE001
            log.exception("company list lookup")
    return out


def company(cik: str) -> dict | None:
    cik = str(int(cik))
    with db.pool.connection() as conn:
        r = conn.execute("""SELECT cik, name, tickers, offer_ticker, sic_desc, state_inc, offer_date, offer_proceeds, offer_exchange
                            FROM ipo_companies WHERE cik = %s""", (cik,)).fetchone()
    if r:
        return dict(r)
    return {"cik": cik, "name": None, "tickers": None, "offer_ticker": None, "sic_desc": None, "state_inc": None,
            "offer_date": None, "offer_proceeds": None, "offer_exchange": None}


def filings(cik: str) -> list[dict]:
    """S-1, S-1/A, F-1, F-1/A filings, newest first: ipo_filings, else the submissions API."""
    cik = str(int(cik))
    with db.pool.connection() as conn:
        rows = conn.execute("""SELECT accession, form, filed, url FROM ipo_filings WHERE cik = %s AND form = ANY(%s)
                               ORDER BY filed DESC, accession DESC""", (cik, list(FORMS))).fetchall()
    out = [dict(r) for r in rows]
    if out:
        return out
    try:
        from loader import s1_terms as T
        body = T._get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", 16 << 20)
        rec = (json.loads(body) if body else {}).get("filings", {}).get("recent", {})
        import datetime as dt
        for acc, form, d in zip(rec.get("accessionNumber", []), rec.get("form", []), rec.get("filingDate", [])):
            if form in FORMS:
                out.append({"accession": acc, "form": form, "filed": dt.date.fromisoformat(d),
                            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"})
    except Exception:  # noqa: BLE001
        log.exception("submissions lookup")
    return out


_ann: dict = {}


def annual_filings(cik: str, n: int = 5) -> list[dict]:
    """The company's newest 10-K and 20-F filings from the submissions API (kept six hours)."""
    cik = str(int(cik))
    hit = _ann.get(cik)
    if hit and time.time() - hit[0] < 21600:
        return hit[1]
    out: list[dict] = []
    try:
        import datetime as dt
        from loader import s1_terms as T
        body = T._get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", 16 << 20)
        rec = (json.loads(body) if body else {}).get("filings", {}).get("recent", {})
        for acc, form, d in zip(rec.get("accessionNumber", []), rec.get("form", []), rec.get("filingDate", [])):
            if form in ANNUAL:
                out.append({"accession": acc, "form": form, "filed": dt.date.fromisoformat(d),
                            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"})
        out = out[:n]
    except Exception:  # noqa: BLE001
        log.exception("annual filings lookup")
    _ann[cik] = (time.time(), out)
    return out


def all_filings(cik: str) -> list[dict]:
    """S-1 family plus annual reports, newest first."""
    out = filings(cik) + annual_filings(cik)
    return sorted(out, key=lambda f: (f["filed"], f["accession"]), reverse=True)


def preferred(fl: list[dict]) -> list[dict]:
    """The order to try filings in: the newest S-1/F-1 when it is under a year old and no annual report followed it,
    else the newest annual report, then the rest newest first (owner, 2026-11-24)."""
    import datetime as dt
    ann = [f for f in fl if f["form"] in ANNUAL]
    reg = [f for f in fl if f["form"] not in ANNUAL]
    first: list[dict] = []
    if reg and (dt.date.today() - reg[0]["filed"]).days <= 365 and not (ann and ann[0]["filed"] > reg[0]["filed"]):
        first = reg[:3]
    return first + [f for f in ann + reg if f not in first]


# ---- reading the document ----------------------------------------------------------------------------------------------

def blocks_of(html: str) -> list[dict]:
    """The document as a list of blocks in order: {t: text, bold: whole block bold/italic, lead: leading bold run, id}."""
    import lxml.html
    try:
        root = lxml.html.fromstring(html.encode("utf-8", "replace") if isinstance(html, str) else html)
    except Exception:  # noqa: BLE001
        return []
    for bad in root.xpath("//script|//style|//head|//*[local-name()='header']"):
        bad.getparent().remove(bad)
    body = root.xpath("//body")
    body = body[0] if body else root
    out: list[dict] = []
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "font", "center"}

    def is_bold(el) -> bool:
        st = (el.get("style") or "").lower().replace(" ", "")
        return el.tag in ("b", "strong", "i", "em", "u") or "font-weight:bold" in st or "font-weight:700" in st \
            or "font-style:italic" in st or el.tag in ("h1", "h2", "h3", "h4", "h5", "h6")

    def runs(el, bold=False):
        """Yield (text, bold) runs of an element's inline content."""
        b = bold or is_bold(el)
        if el.text:
            yield el.text, b
        for ch in el:
            if isinstance(ch.tag, str):
                if ch.tag in ("br",):
                    yield " ", b
                else:
                    yield from runs(ch, b)
            if ch.tail:
                yield ch.tail, b

    def has_block_child(el) -> bool:
        return any(isinstance(c.tag, str) and c.tag in ("p", "div", "li", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6")
                   for c in el)

    def walk(el):
        if not isinstance(el.tag, str):
            return
        if el.tag in ("table",):
            # tables: one block per row, not bold
            for tr in el.iter("tr"):
                parts = [" ".join(" ".join(td.itertext()).split()) for td in tr.findall("td")]
                t = " ".join(p for p in parts if p)
                if t:
                    out.append({"t": t, "bold": False, "lead": "", "id": tr.get("id") or ""})
            return
        if el.tag in BLOCK and not has_block_child(el):
            rr = [(unescape(t).replace("\xa0", " "), b) for t, b in runs(el)]
            text = " ".join("".join(t for t, _ in rr).split())
            if text and (text.lower() == "table of contents" or re.fullmatch(r"(?:page )?[0-9ivxl]{1,4}", text.lower())):
                text = ""
            if text:
                rr = [(t, b) for t, b in rr if t.strip()]
                allb = bool(rr) and all(b for _, b in rr)
                lead = ""
                if rr and rr[0][1] and not allb:
                    acc = []
                    for t, b in rr:
                        if not b:
                            break
                        acc.append(t)
                    lead = " ".join(" ".join(acc).split())
                ident = el.get("id") or ""
                if not ident:
                    a = el.find(".//a[@name]") if el.find(".//a[@name]") is not None else el.find(".//a[@id]")
                    if a is not None:
                        ident = a.get("name") or a.get("id") or ""
                out.append({"t": text, "bold": allb, "lead": lead, "id": ident})
            return
        for ch in el:
            walk(ch)

    walk(body)
    return out


MAJOR = re.compile(r"^(?:prospectus summary|the offering|summary (?:consolidated |historical )?(?:financial|risk)|risk factors|"
                   r"special note regarding forward|cautionary (?:note|statement)|use of proceeds|dividend policy|capitalization|"
                   r"dilution|selected (?:consolidated )?financial|management'?s discussion|business|industry overview|"
                   r"our industry|management|executive compensation|certain relationships|principal (?:and selling )?"
                   r"(?:stockholders|shareholders)|description of (?:our )?(?:capital stock|share capital|securities)|"
                   r"shares eligible|material (?:u\.s\. )?(?:federal )?(?:income )?tax|underwriting|legal matters|experts|"
                   r"where you can find|index to (?:consolidated )?financial|market and industry data|"
                   r"corporate information|implications of being|the reorganization|our corporate structure)\b", re.I)
SUB_END = re.compile(r"^(?:competition|our competitive (?:strengths|advantages)|competitive (?:strengths|advantages|landscape)|our strengths|"
                     r"our (?:growth )?strateg(?:y|ies)|growth strateg(?:y|ies)|our market opportunity|market opportunity|"
                     r"intellectual property|employees|human capital|facilities|properties|legal proceedings|government regulation|"
                     r"regulation|sales and marketing|research and development|customers|our customers|suppliers|manufacturing|"
                     r"seasonality|our history|our technology|our platform|our solution|our products|insurance|"
                     r"our (?:approach|culture|business model)|corporate information|key (?:business )?metrics|"
                     r"our growth (?:drivers|opportunities)|competitive advantages)\b", re.I)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", t.lower()).strip()


def _is_heading(b: dict, maxlen: int = 140) -> bool:
    t = b["t"]
    if len(t) > maxlen or len(t) < 3:
        return False
    if b["bold"]:
        return True
    letters = [c for c in t if c.isalpha()]
    return bool(letters) and t.upper() == t and len(letters) >= 4


def find_section(blocks: list[dict], title_re: re.Pattern, stop=("major", "sub"), min_chars: int = 600,
                 max_chars: int = 60000, search: bool = False, also_stop: re.Pattern | None = None) -> tuple[int, int] | None:
    """(start, end) block indexes of the best section whose heading matches title_re: the candidate with the most text
    before the next heading of a stop kind (a table of contents entry has almost none)."""
    best = None
    for i, b in enumerate(blocks):
        hit = title_re.search if search else title_re.match
        if not _is_heading(b, 90 if search else 140) or not hit(_norm(b["t"])):
            continue
        j, n = i + 1, 0
        while j < len(blocks) and n < max_chars:
            bj = blocks[j]
            if _is_heading(bj) and not hit(_norm(bj["t"])):
                nj = _norm(bj["t"])
                if ("major" in stop and MAJOR.match(nj)) or ("sub" in stop and SUB_END.match(nj)) \
                        or (also_stop is not None and also_stop.search(nj)):
                    break
            n += len(bj["t"])
            j += 1
        if n >= min_chars and (best is None or n > best[2]):
            best = (i, j, n)
    return (best[0], best[1]) if best else None


BULLET = re.compile(r"^[●•▪◦■\-–]\s*(.{8,150}?)\s*[.:]\s+(.{20,})$")


def items_of(blocks: list[dict], start: int, end: int, body_chars: int = 900) -> list[dict]:
    """Items inside a section: a bold paragraph (or bold lead-in) is a title, the text after it is the body."""
    items: list[dict] = []
    cur = None
    for k in range(start + 1, end):
        b = blocks[k]
        t = b["t"]
        mb = BULLET.match(t)
        if mb and not b["bold"]:
            if cur:
                items.append(cur)
            cur = {"title": mb.group(1).strip(" .:"), "body": mb.group(2), "id": b["id"], "idx": k}
        elif b["bold"] and 12 <= len(t) <= 400 and not MAJOR.match(_norm(t)):
            if cur:
                items.append(cur)
            cur = {"title": t, "body": "", "id": b["id"], "idx": k}
        elif b["lead"] and 12 <= len(b["lead"]) <= 300:
            if cur:
                items.append(cur)
            rest = t[len(b["lead"]):].strip()
            cur = {"title": b["lead"].rstrip(" .:\u2014-"), "body": rest, "id": b["id"], "idx": k}
        elif cur is not None and len(cur["body"]) < body_chars * 3:
            cur["body"] += (" " if cur["body"] else "") + t
    if cur:
        items.append(cur)
    for it in items:
        it["body"] = it["body"][:body_chars]
    return items


def paragraph_items(blocks: list[dict], start: int, end: int, body_chars: int = 900, limit: int = 14) -> list[dict]:
    """Fallback when a section has no bold titles: each real paragraph, titled by its first sentence."""
    out = []
    for k in range(start + 1, end):
        t = blocks[k]["t"]
        if len(t) < 80:
            continue
        first = re.split(r"(?<=[.!?])\s", t, 1)[0][:220]
        out.append({"title": first, "body": t[:body_chars], "id": blocks[k]["id"], "idx": k})
        if len(out) >= limit:
            break
    return out


# ---- risk categories ---------------------------------------------------------------------------------------------------

CATS = [
    ("competition", r"\bcompet|market share|pricing pressure|new entrants|larger (?:and|or) (?:more|better)"),
    ("regulatory", r"\bregulat|\bcompliance|government|\bFDA\b|\bFCC\b|\bantitrust|sanction|export control|licens|privacy law|GDPR|CCPA|\bpermit|legislation|\btariff"),
    ("financial / liquidity", r"\bnet loss|history of loss|\bprofitab|\bliquidity|\bindebted|indebtedness|credit facility|additional (?:capital|financing|funding)|"
                              r"\bcash flow|\bgoing concern|operating loss|revenue growth|\bfinancial results|fluctuat\w+ in (?:our )?(?:operating|quarterly)|\bdebt\b|"
                              r"impairment|working capital"),
    ("customer concentration", r"concentrat|significant portion of our (?:revenue|sales)|limited number of (?:customers|clients|partners)|"
                               r"loss of (?:a|one or more|any) (?:key |major |significant )?(?:customer|client|partner)|largest customers?|top (?:\w+ )?customers"),
    ("technology / security", r"cyber|security (?:breach|incident)|data breach|\bhack|\bsoftware\b|\bplatform\b|outage|downtime|disruption|"
                              r"artificial intelligence|\bAI\b|open source|information technology|infrastructure|\bdata\b"),
    ("key personnel", r"key (?:personnel|employees|management|executives|members)|senior management|\bfounder|talent|attract and retain|"
                      r"retain (?:our|qualified)|\bemployees?\b|labor|hire|recruit"),
    ("legal / IP", r"litigation|lawsuit|legal proceeding|intellectual property|patent|trademark|infring|class action|\bclaims\b|indemnif|"
                   r"trade secret|copyright|product liability"),
    ("macro / economic", r"macroeconomic|economic (?:conditions|downturn|slowdown)|recession|inflation|interest rates?|pandemic|COVID|geopolitical|"
                         r"\bwar\b|natural disaster|climate|foreign currency|exchange rates?|supply chain|international operations|"
                         r"consumer spending|inflationary"),
    ("stock / offering", r"common stock|class a|ordinary shares|\bADS|price of our|trading price|public market|this offering|dilut|"
                         r"\bdividend|future sales|analysts|anti-takeover|delaware law|forum|controlled company|public company|"
                         r"emerging growth|sarbanes|voting power|lock-up|underwrit|\bIPO\b|initial public offering"),
]
BOILER = re.compile(r"(?:price of our (?:class a )?(?:common stock|ordinary shares|ADSs?|shares)|trading price|no (?:prior )?(?:public )?market|"
                    r"active (?:and liquid )?trading market|anti-takeover|delaware law|charter|bylaws|forum|dividends?\b|future sales|"
                    r"substantial amount of our (?:common stock|shares)|analysts?|emerging growth company|sarbanes|"
                    r"costs of being a public company|public company|dilution|immediate and substantial|lock-up|"
                    r"broad discretion in the use of|proceeds of this offering|ability to pay (?:any )?dividends|"
                    r"tax receivable|controlled company|dual[- ]class|voting power|exclusive forum)", re.I)
CAT_RE = [(n, re.compile(p, re.I)) for n, p in CATS]
GROUP_HEAD = re.compile(r"^risks? (?:related|relating) to|^general risks?|^risks? (?:associated|particular)|^additional risks?", re.I)


def categorize(title: str, body: str, group: str = "") -> tuple[str, bool]:
    """(category, boilerplate) of a risk factor. Title counts triple; the group heading breaks ties."""
    best, score = "other", 0
    gl = group.lower()
    for name, rx in CAT_RE:
        s = 3 * len(rx.findall(title)) + len(rx.findall(body[:400]))
        if name == "stock / offering" and re.search(r"common stock|ordinary shares|this offering|public company|class a", gl):
            s += 2
        if s > score:
            best, score = name, s
    boiler = bool(BOILER.search(title)) or (best == "stock / offering" and score >= 3)
    return best, boiler


PAGE_HEAD = re.compile(r"\(continued\)|^\d{4} form 10-k|form 10-k\s*\d*$|^table of contents$|^\d{1,3}$|^item\s*\d", re.I)


def risk_items(blocks: list[dict], start: int, end: int) -> list[dict]:
    items = _risk_items(blocks, start, end)
    if len(items) < 6 and end - start >= 40:
        # Some annual reports write risks as paragraphs under short headings (Kroger: "COMPETITIVE ENVIRONMENT"): each
        # heading is an item, titled by the heading
        alt: list[dict] = []
        group, cur = "", None
        for k in range(start + 1, end):
            b = blocks[k]
            t = b["t"].replace("\u200b", "").strip()
            if not t or PAGE_HEAD.search(t):
                continue
            if b["bold"] and 6 <= len(t) <= 120 and not MAJOR.match(_norm(t)) and not _norm(t).startswith("summary of risk"):
                if cur:
                    alt.append(cur)
                cur = {"title": t.capitalize() if t.isupper() else t, "body": "", "id": b["id"], "idx": k, "group": group}
            elif cur is not None and len(cur["body"]) < 2500:
                cur["body"] += (" " if cur["body"] else "") + t
        if cur:
            alt.append(cur)
        alt = [i for i in alt if len(i["body"]) > 80]
        if len(alt) > len(items):
            return _finish_risks(alt)
    return items


def _risk_items(blocks: list[dict], start: int, end: int) -> list[dict]:
    items: list[dict] = []
    group = ""
    cur = None
    for k in range(start + 1, end):
        b = blocks[k]
        t = b["t"]
        nt = _norm(t)
        if PAGE_HEAD.search(t) and len(t) < 80:
            continue
        if (b["bold"] or _is_heading(b)) and GROUP_HEAD.match(nt) and len(t) < 160:
            if cur:
                items.append(cur)
                cur = None
            group = t
            continue
        if b["bold"] and 30 <= len(t) <= 450 and not MAJOR.match(nt) and not nt.startswith("summary of risk"):
            if cur:
                items.append(cur)
            cur = {"title": t, "body": "", "id": b["id"], "idx": k, "group": group}
        elif b["lead"] and 30 <= len(b["lead"]) <= 400:
            if cur:
                items.append(cur)
            cur = {"title": b["lead"].rstrip(), "body": t[len(b["lead"]):].strip(), "id": b["id"], "idx": k, "group": group}
        elif cur is not None and len(cur["body"]) < 2500:
            cur["body"] += (" " if cur["body"] else "") + t
    if cur:
        items.append(cur)
    return _finish_risks(items)


def _finish_risks(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        cat, boiler = categorize(it["title"], it["body"], it.get("group", ""))
        # Company-specific: names the company's own numbers, customers, products or a dollar/percentage figure.
        specific = bool(re.search(r"\$\s?\d|\d+(?:\.\d+)?\s?%|\b(?:our|the) (?:largest|top) \w+|\b[A-Z][a-z]+ (?:Inc|Corp|LLC|Ltd)\b", it["body"][:900]))
        out.append({"title": it["title"], "body": it["body"][:900], "id": it["id"], "idx": it["idx"], "group": it.get("group", ""),
                    "category": cat, "boilerplate": boiler, "specific": specific and not boiler,
                    "chars": len(it["body"])})
    return out


# ---- competitors -------------------------------------------------------------------------------------------------------

NAME_RX = re.compile(r"\b([A-Z][A-Za-z0-9&'.\-]+(?: (?:[A-Z][A-Za-z0-9&'.\-]+|of|&|de))*(?: (?:Inc\.?|Corp\.?|Corporation|LLC|Ltd\.?|plc|Co\.?|Group|Holdings|Technologies))?)")
STOP_NAMES = set("""We Our The They It Its This That These Those In On At For And But Or As If When While Because Although Some Many Most Other Such
 Competition Company Companies Customers Customer Market Markets Products Product Services Service Business United States U.S. Internet Our
 Class Common Stock Item Part Risk Factors Act Exchange Commission SEC IPO FDA GAAP EBITDA COVID Inc LLC AI API SaaS B2B B2C Also However In addition
 Additionally Further Moreover Based Certain Several Both Each Any All Within Among Between Including Such""".split())


def competitor_names(text: str, own: str) -> list[str]:
    """Named competitors from the Competition text: a model reads it when available, else a rule over the sentences
    that name competitors ("such as", "including", "compete with")."""
    names: list[str] = []
    asked = False
    try:
        from app import openai_compat
        if openai_compat.enabled() and len(text) > 120:
            payload = {"max_tokens": 700, "system": "You list companies named as competitors in a passage from a company's SEC "
                       "filing. Output only a JSON array of the company names exactly as written (brand or company names only, "
                       "no generic categories, not the filer itself). No prose.",
                       "messages": [{"role": "user", "content": f"Filer: {own}\n\nPassage:\n{text[:9000]}"}]}
            r = openai_compat.post(payload, 40.0)
            if r.status_code == 200:
                o = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
                m = re.search(r"\[.*\]", o, re.S)
                if m:
                    names = [str(x).strip() for x in json.loads(m.group(0)) if str(x).strip()]
                    asked = True
    except Exception:  # noqa: BLE001
        log.exception("competitor names via model")
    if not names and not asked:
        for sent in re.split(r"(?<=[.;])\s+", text):
            if re.search(r"such as|including|compete (?:directly )?with|competitors? (?:include|are)|competing (?:products|with)|e\.g\.", sent, re.I):
                tail = re.split(r"such as|including|competitors? (?:include|are)|compete (?:directly )?with|e\.g\.,?", sent, 1, flags=re.I)[-1]
                for m in NAME_RX.finditer(tail):
                    n = m.group(1).strip(" .,'")
                    if n and n.split()[0] not in STOP_NAMES and len(n) > 2 and not re.search(r"Exhibit|Schedule|Agreement|Annual|Form|January|February|March|April|June|July|August|September|October|November|December|Compete|Covenant|Report", n):
                        names.append(n)
    seen, out = set(), []
    own_n = _clean_name(own)
    for n in names:
        k = _clean_name(re.sub(r"\b(?:inc|corp|corporation|llc|ltd|plc|co)\b\.?", "", n, flags=re.I))
        if k and k not in seen and k not in own_n and len(k) > 2 and k not in ("u s", "us", "united states", "usa"):
            seen.add(k)
            out.append(n)
    return out[:40]


def link_competitor(name: str) -> dict:
    """The FURP / EDGAR links for a named competitor (an IPO company we hold, else an EDGAR filer search)."""
    core = _clean_name(re.sub(r"\b(?:inc|corp|corporation|llc|ltd|plc|co|holdings|group)\b\.?", "", name, flags=re.I))
    out = {"edgar": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=" + urllib.parse.quote(name) + "&type=&owner=include&count=10"}
    if len(core) < 3:
        return out
    try:
        with db.pool.connection() as conn:
            r = conn.execute("SELECT cik, name FROM ipo_companies WHERE name_core = %s ORDER BY n_filings DESC LIMIT 1", (core,)).fetchone()
        if r:
            out["furp"] = f"/s1/{r['cik']}"
            out["furp_name"] = r["name"]
    except Exception:  # noqa: BLE001
        pass
    return out


# ---- citation ----------------------------------------------------------------------------------------------------------

def cite(doc_url: str, block: dict) -> str:
    """A link to the passage on EDGAR: the anchor id when the heading has one, plus a text fragment."""
    words = re.sub(r"\s+", " ", block["t"]).split(" ")
    frag = urllib.parse.quote(" ".join(words[:6]), safe="")
    end = urllib.parse.quote(" ".join(words[-4:]), safe="") if len(words) > 12 else ""
    t = f"{frag},{end}" if end and len(words) > 12 else frag
    base = doc_url.split("#")[0]
    if "/ix?doc=" not in base and block.get("id") and not block["id"].startswith(("_", "tx")):
        return f"{base}#{urllib.parse.quote(block['id'])}"
    return f"{base}#:~:text={t}"


# ---- building a profile ------------------------------------------------------------------------------------------------

STRENGTH_RE = re.compile(r"competitive (?:strengths|advantages)|our (?:key |core )?strengths|investment highlights|our differentiators|what sets us apart")
GROWTH_RE = re.compile(r"growth (?:strateg|story|opportunit|driver|lever|plan)|our strateg(?:y|ies)|market opportunit|our opportunit|business strategy|how we (?:plan to )?grow")
INDUSTRY_RE = re.compile(r"^(?:our )?(?:industry|market|industry overview|market overview|industry background|industry and market|market opportunity)")
COMP_RE = re.compile(r"^(?:our )?(?:competition|competitive landscape|competitors|competitive conditions|competitive environment|competitive position|competitive factors|competitors and competition)$|^competition and|^our competition")
ANNUAL_END = re.compile(r"^(?:unresolved staff comments|cybersecurity|properties|legal proceedings|mine safety|management'?s discussion|"
                       r"quantitative and qualitative|financial statements and supplementary|selected financial data|market for (?:the )?(?:registrant|our))")
ITEM_PREFIX = re.compile(r"^item\s*\d+[a-c]?\s*[.:\-\u2013\u2014]?\s*(?=\S)", re.I)
RISK_RE = re.compile(r"^risk factors$")
COMP_HINT = re.compile(r"(?:competitors?|competing \w+|competitive (?:products|therapies)) (?:include|are|such as)|compete (?:directly |most directly )?with|marketed (?:products|therapies)[^.]{0,60}(?:include|such as)|\bour (?:principal |main |primary )?competitors", re.I)


def _summarize(title: str, items: list[dict], company_name: str) -> str | None:
    try:
        from app import openai_compat
        if not openai_compat.enabled() or not items:
            return None
        listing = "\n".join(f"- {i['title'][:220]}" for i in items[:14])
        payload = {"max_tokens": 220, "system": "You summarize, in plain language for a general reader, what a company said about itself "
                   "in its SEC filing. Two or three short sentences. Use only the listed statements; add no facts, no opinions, "
                   "no praise. Say 'the company says'.",
                   "messages": [{"role": "user", "content": f"Company: {company_name}. Section: {title}.\nStatements:\n{listing}"}]}
        r = openai_compat.post(payload, 30.0)
        if r.status_code == 200:
            return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()[:700] or None
    except Exception:  # noqa: BLE001
        log.exception("s1 summary")
    return None


def build(cik: str, accession: str, summaries: bool = True) -> dict:
    """Read one filing and store its profile. Returns the data dict (also saved in s1_profile)."""
    from loader import s1_terms as T
    ensure_table()
    cik = str(int(cik))
    fl = next((f for f in all_filings(cik) if f["accession"] == accession), None)
    if not fl:
        raise ValueError("filing not found")
    co = company(cik) or {}
    annual = fl["form"] in ANNUAL
    url, text, note = T.primary_document(cik, accession, fl["form"], limit=(120 << 20) if annual else None)
    if not text:
        data = {"error": f"The filing's main document could not be read ({note}).", "doc_url": url}
    else:
        blocks = blocks_of(text)
        if annual:       # "Item 1A. Risk Factors" is headed "Risk Factors" for the matching below
            for b in blocks:
                if len(b["t"]) < 160 and ITEM_PREFIX.match(b["t"]) and ITEM_PREFIX.sub("", b["t"]).strip():
                    b["t"] = ITEM_PREFIX.sub("", b["t"]).strip()
        name = co.get("name") or ""
        data: dict = {"doc_url": url, "blocks": len(blocks), "sections": {}}
        sec = {}

        def sect(key, rx, stop=("major", "sub"), min_chars=500):
            rng = find_section(blocks, rx, stop, min_chars)
            if rng:
                sec[key] = rng
            return rng

        def pack(key, rng, label, fallback=True):
            if not rng:
                return []
            its = items_of(blocks, *rng)
            its = [i for i in its if len(i["title"]) < 400 and (i["body"] or key == "industry")]
            if len(its) < 2 and fallback:
                its = paragraph_items(blocks, *rng)
            out = []
            for i in its[:30]:
                bl = blocks[i["idx"]]
                out.append({"title": i["title"], "body": i["body"], "section": label, "cite": cite(url, bl)})
            return out

        def sect2(key, rx, **kw):
            rng = find_section(blocks, rx, **kw)
            if rng:
                sec[key] = rng
            return rng

        data["strengths"] = pack("strengths", sect2("strengths", STRENGTH_RE, search=True, also_stop=GROWTH_RE, max_chars=30000), "Competitive strengths")[:16]
        growth = pack("growth", sect2("growth", GROWTH_RE, search=True, also_stop=STRENGTH_RE, max_chars=30000), "Growth strategy / market opportunity")[:16]
        ind_rng = sect("industry", INDUSTRY_RE, ("major",), 800)
        ind = pack("industry", ind_rng, "Industry overview", fallback=True)[:8] if ind_rng else []
        data["opportunities"] = growth + ind
        rr = find_section(blocks, RISK_RE, () if annual else ("major",), 5000, max_chars=4000000, also_stop=ANNUAL_END if annual else None)
        risks = risk_items(blocks, *rr) if rr else []
        for r in risks:
            r["cite"] = cite(url, blocks[r.pop("idx")])
            r["section"] = "Risk factors" + (f" ({r['group']})" if r.get("group") else "")
        data["risks"] = risks
        cr = (find_section(blocks, COMP_RE, ("major", "sub"), 300, max_chars=15000, also_stop=re.compile(r"^.{3,70}$")) if annual
              else sect("competition", COMP_RE, ("major", "sub"), 300))
        ctext = " ".join(blocks[k]["t"] for k in range(cr[0] + 1, cr[1])) if cr else ""
        extra = []
        rs, re_ = (rr or (0, 0))
        for k, bk in enumerate(blocks):
            if rs <= k < re_ or (cr and cr[0] <= k < cr[1]) or (annual and rr and k >= re_):
                continue
            if COMP_HINT.search(bk["t"]) and 60 < len(bk["t"]) < 1500:
                extra.append(bk["t"])
                if len(extra) >= 14:
                    break
        names = competitor_names((ctext + " " + " ".join(extra)).strip(), name) if (ctext or extra) else []
        comps = []
        for n in names:
            # the passage that names it, for the citation and the company's own wording
            lo, hi = cr if cr else (0, len(blocks))
            ix = next((k for k in range(lo, hi) if n in blocks[k]["t"]), None)
            if ix is None:
                ix = next((k for k in range(len(blocks)) if n in blocks[k]["t"]), lo)
            sent = next((s for s in re.split(r"(?<=[.;])\s+", blocks[ix]["t"]) if n in s), blocks[ix]["t"])[:400]
            comps.append({"name": n, "quote": sent, "cite": cite(url, blocks[ix]), "links": link_competitor(n),
                          "section": "Business / Competition"})
        data["competitors"] = comps
        data["competition_text"] = ctext[:1800]
        data["competition_cite"] = cite(url, blocks[cr[0]]) if cr else None
        data["found"] = {k: bool(v) for k, v in {"strengths": data["strengths"], "growth": growth, "risk": risks,
                                                 "competition": ctext, "industry": ind}.items()}
        data["partial"] = not data["found"]["risk"] and not data["found"]["strengths"] and not data["found"]["growth"]
        if summaries and not data["partial"]:
            data["summaries"] = {
                "strengths": _summarize("Competitive strengths", data["strengths"], name),
                "opportunities": _summarize("Growth strategy and market opportunity", data["opportunities"], name),
                "weaknesses": _summarize("Risk factors (company-specific)", [r for r in risks if not r["boilerplate"]], name),
                "threats": _summarize("Risk factors (competition, regulation, economy)",
                                      [r for r in risks if r["category"] in ("competition", "regulatory", "macro / economic")], name),
            }
    with db.pool.connection() as conn:
        conn.execute("""INSERT INTO s1_profile (accession, cik, form, filed, doc_url, version, data) VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (accession) DO UPDATE SET version = EXCLUDED.version, doc_url = EXCLUDED.doc_url,
                        data = EXCLUDED.data, built = now()""",
                     (accession, cik, fl["form"], fl["filed"], url, VERSION, json.dumps(data)))
    return data


def stored(accession: str) -> dict | None:
    ensure_table()
    with db.pool.connection() as conn:
        r = conn.execute("SELECT data, version FROM s1_profile WHERE accession = %s", (accession,)).fetchone()
    if r and r["version"] == VERSION:
        return r["data"]
    return None


_jobs: dict[str, dict] = {}
_jlock = threading.Lock()


def start_build(cik: str, accession: str) -> dict:
    with _jlock:
        j = _jobs.get(accession)
        if j and j["state"] == "running":
            return j
        if j and j["state"] == "failed" and time.time() - j["t"] < 120:
            return j
        j = {"state": "running", "t": time.time(), "err": None}
        _jobs[accession] = j

    def run():
        try:
            build(cik, accession)
            j["state"] = "done"
        except Exception as e:  # noqa: BLE001
            log.exception("s1 build %s", accession)
            j["state"], j["err"] = "failed", str(e)[:200]
    threading.Thread(target=run, daemon=True).start()
    return j


def named_by(name: str, cik: str, limit: int = 12) -> list[dict]:
    """Other companies' filings (read so far) that name this company as a competitor, newest filing per company."""
    from app.company_route import key
    k = key(name or "")
    if len(k) < 3:
        return []
    names = {k}
    if len(k.split()) > 1 and len(k.split()[0]) >= 4:
        names.add(k.split()[0])
    rx = r"\m(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\M"
    try:
        with db.pool.connection() as conn:
            rows = conn.execute("""SELECT DISTINCT ON (p.cik) p.cik, p.form, p.filed, c->>'name' AS cname, c->>'quote' AS quote,
                                          c->>'cite' AS cite, coalesce(m.name, i.name, p.cik) AS who
                                   FROM s1_profile p CROSS JOIN LATERAL jsonb_array_elements(p.data->'competitors') c
                                   LEFT JOIN major_companies m ON m.cik = p.cik LEFT JOIN ipo_companies i ON i.cik = p.cik
                                   WHERE p.cik <> %s AND p.version = %s AND lower(c->>'name') ~ %s
                                   ORDER BY p.cik, p.filed DESC LIMIT %s""", (str(int(cik)), VERSION, rx, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        log.exception("named_by")
        return []


# ---- what changed between two filings ----------------------------------------------------------------------------------

def _key(t: str) -> str:
    return " ".join(_norm(t).split()[:16])


def _diff_titles(old: list[str], new: list[str]) -> tuple[list[str], list[str]]:
    ok = {_key(t): t for t in old}
    nk = {_key(t): t for t in new}
    added, removed = [], []
    for k, t in nk.items():
        if k not in ok and not difflib.get_close_matches(k, list(ok), 1, 0.88):
            added.append(t)
    for k, t in ok.items():
        if k not in nk and not difflib.get_close_matches(k, list(nk), 1, 0.88):
            removed.append(t)
    return added, removed


def diff(old: dict, new: dict) -> dict:
    out = {}
    for key, getter in (("risks", lambda d: [r["title"] for r in d.get("risks", [])]),
                        ("competitors", lambda d: [c["name"] for c in d.get("competitors", [])]),
                        ("strengths", lambda d: [s["title"] for s in d.get("strengths", [])]),
                        ("opportunities", lambda d: [s["title"] for s in d.get("opportunities", [])])):
        a, r = _diff_titles(getter(old), getter(new))
        out[key] = {"added": a, "removed": r}
    return out


# ---- routes ------------------------------------------------------------------------------------------------------------

def _page(request: Request, name: str, **ctx):
    from app.main import render
    ctx.setdefault("robots", "noindex, nofollow")
    from app.company_route import money
    ctx.setdefault("money", money)
    return render(request, name, **ctx)


@router.get("/s1", response_class=HTMLResponse)
def s1_home(request: Request, q: str = Query("", max_length=100)):
    _gate()
    res = search(q) if q.strip() else []
    if len(res) == 1:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"/s1/{res[0]['cik']}", 302)
    return _page(request, "s1_home.html", q=q, results=res)


@router.get("/api/s1/search")
def s1_search(q: str = Query("", max_length=100)):
    _gate()
    return JSONResponse(search(q))


@router.get("/s1/{cik}", response_class=HTMLResponse)
def s1_company(request: Request, cik: str, acc: str = Query("", max_length=30), compare: str = Query("", max_length=30),
               topic: str = Query("", max_length=20), q: str = Query("", max_length=120),
               vs: str = Query("", max_length=12)):
    _gate()
    if not re.fullmatch(r"\d{1,10}", cik):
        raise HTTPException(404)
    cik = str(int(cik))
    co = company(cik)
    if not co.get("name"):
        try:
            from app import company_route
            company_route._load()
            co["name"] = next((r["name"] for r in company_route._idx["rows"] if r["cik"] == cik), None)
        except Exception:  # noqa: BLE001
            pass
    fl = all_filings(cik)
    topic = topic if topic in ("competitors", "risks", "strengths", "strategy", "market", "swot", "peers") else ""
    alt = None
    try:
        from app import company_route
        alt = company_route.foundation_alt(co.get("name") or "") if co.get("name") else None
    except Exception:  # noqa: BLE001
        log.exception("foundation alt")
    if not fl:
        return _page(request, "s1_company.html", co=co, fl=[], cur=None, data=None, state="none", diff=None, cmp=None, note=None,
                     risk_cats=[], topic=topic, alt=alt, asked=q, peers=None, vs_co=None)
    note = None
    if acc:
        cur = next((f for f in fl if f["accession"] == acc), fl[0])
        data = stored(cur["accession"])
        cands = [cur]
    else:
        # default: the newest filing, but an amendment that changes only a few pages has no sections to read, so fall back
        # to the newest complete one and say so
        cands = preferred(fl)[:5]
        cur, data = cands[0], None
        for f in cands:
            dd = stored(f["accession"])
            if dd is None:
                cur, data = f, None
                break
            if dd.get("partial") or dd.get("error"):
                continue
            cur, data = f, dd
            break
        else:
            cur, data = fl[0], stored(fl[0]["accession"])
        if cur["accession"] != fl[0]["accession"] and data:
            note = (f"The newest filing ({fl[0]['form']} {fl[0]['filed']}) changes only part of the registration statement, so the newest complete one is shown."
                    if fl[0]["form"] not in ANNUAL and cur["form"] not in ANNUAL else None)
    state, err = "ready", None
    if data is None:
        j = start_build(cik, cur["accession"])
        state, err = j["state"], j.get("err")
        if state == "done":
            data = stored(cur["accession"])
            state = "ready"
    d = None
    cmpf = None
    if data and compare:
        cmpf = next((f for f in fl if f["accession"] == compare), None)
        old = stored(compare) if cmpf else None
        if cmpf and old is None:
            start_build(cik, compare)
            state = "comparing"
        elif old:
            d = diff(old, data)
    cats: list = []
    if data and data.get("risks"):
        by: dict[str, list] = {}
        for r in data["risks"]:
            by.setdefault(r["category"], []).append(r)
        cats = sorted(by.items(), key=lambda kv: -len(kv[1]))
    pr = vs_co = None
    if topic == "peers":
        from app import company_route
        pr = company_route.peers(cik, [c["name"] for c in (data or {}).get("competitors", [])])
        if vs and re.fullmatch(r"\d{1,10}", vs):
            try:
                with db.pool.connection() as conn:
                    r = conn.execute("SELECT cik, name, ticker, revenue, sic, sic_desc FROM major_companies WHERE cik = %s", (str(int(vs)),)).fetchone()
                vs_co = dict(r) if r else None
            except Exception:  # noqa: BLE001
                log.exception("vs company")
    return _page(request, "s1_company.html", co=co, fl=fl, cur=cur, data=data, state=state, err=err, diff=d, cmp=cmpf, note=note, risk_cats=cats, topic=topic, alt=alt, asked=q,
                 named_by=named_by(co.get("name") or "", cik) if data else [], peers=pr, vs_co=vs_co)
