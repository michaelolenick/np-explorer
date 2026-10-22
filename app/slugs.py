"""Readable entity URLs: a name slug plus the stable ID, /org/urban-land-institute-530159845 and
/person/jane-q-smith-48213. The ID alone still works (old links); pages redirect it (301) to the slug form, and
render() rewrites internal links to the slug form before a page is sent (one batched name lookup per kind), so
visitors and crawlers rarely see a redirect.

KINDS: URL prefix, ID pattern, and a query for {id: name}. canonical(kind, id, name) builds a path; parse() reads
the ID back from either form.
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata

from app import db

# kind: (prefix, id regex, SQL taking a list of ids and returning (id, name), how an id is stored in SQL)
KINDS = {
    "org": ("/org/", r"\d{9}", "SELECT ein, name FROM organizations WHERE ein = ANY(%s)"),
    "person": ("/person/", r"\d+", "SELECT id::text, display_name FROM person_clusters WHERE id = ANY(%s::bigint[])"),
    "contractor": ("/contractor/", r"\d+", "SELECT id::text, name_raw FROM contractors WHERE id = ANY(%s::bigint[])"),
    "institution": ("/institution/", r"\d+", "SELECT unitid::text, name FROM colleges WHERE unitid = ANY(%s::int[])"),
    "trust": ("/student-loans/trust/", r"\d+",
              "SELECT cik::text, name FROM student_loan_trusts WHERE cik = ANY(%s::bigint[])"),
    "committee": ("/politics/committee/", r"C\d{8}",
                  "SELECT DISTINCT ON (cmte_id) cmte_id, name FROM fec_committees WHERE cmte_id = ANY(%s) "
                  "ORDER BY cmte_id, cycle DESC"),
    "client": ("/lobbying/client/", r"\d+",
               "SELECT DISTINCT ON (client_id) client_id::text, client_name FROM lda_filings "
               "WHERE client_id = ANY(%s::int[]) ORDER BY client_id, dt_posted DESC NULLS LAST"),
    "firm": ("/lobbying/firm/", r"\d+",
             "SELECT DISTINCT ON (registrant_id) registrant_id::text, registrant_name FROM lda_filings "
             "WHERE registrant_id = ANY(%s::int[]) ORDER BY registrant_id, dt_posted DESC NULLS LAST"),
    "lobbyist": ("/lobbying/lobbyist/", r"\d+",
                 "SELECT DISTINCT ON (lobbyist_id) lobbyist_id::text, name FROM lda_activity_lobbyists "
                 "WHERE lobbyist_id = ANY(%s::int[]) ORDER BY lobbyist_id"),
    "company": ("/corporate/company/", r"\d+",
                "SELECT DISTINCT ON (issuer_cik) ltrim(issuer_cik, '0'), issuer_name FROM sec_insider_filings "
                "WHERE issuer_cik = ANY(ARRAY(SELECT lpad(x, 10, '0') FROM unnest(%s::text[]) x))"
                " ORDER BY issuer_cik, filing_date DESC"),
    "insider": ("/corporate/insider/", r"\d+",
                "SELECT DISTINCT ON (ltrim(owner_cik, '0')) ltrim(owner_cik, '0'), owner_name FROM sec_insider_owners "
                "WHERE owner_cik = ANY(ARRAY(SELECT lpad(x, 10, '0') FROM unnest(%s::text[]) x))"
                " ORDER BY ltrim(owner_cik, '0')"),
    "recipient": ("/federal-spending/recipient/", r"[A-Z0-9]{12}",
                  "SELECT DISTINCT ON (recipient_uei) recipient_uei, recipient_name FROM usa_awards "
                  "WHERE recipient_uei = ANY(%s) ORDER BY recipient_uei, fiscal_year DESC"),
    "recallfirm": ("/recalls/firm/", r"[0-9a-f]{10}",
                   "SELECT firm_id, name FROM food_recall_firms WHERE firm_id = ANY(%s)"),
    "formd": ("/corporate/form-d/", r"\d{10}-\d{2}-\d{6}",
              "SELECT accession, issuer_name FROM sec_formd WHERE accession = ANY(%s)"),
}
_KEY = {k: re.compile(rf"^(?:[a-z0-9-]*?-)?({v[1]})$") for k, v in KINDS.items()}
_LINK = re.compile(r'href="(' + "|".join(re.escape(v[0]) for v in KINDS.values()) + r')([A-Za-z0-9-]+)(["#?])')
_PREFIX_KIND = {v[0]: k for k, v in KINDS.items()}
_cache: dict = {}
_lock = threading.Lock()
TTL = 3600


def slug(name: str | None) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80].rstrip("-")


def norm_id(kind: str, ident) -> str:
    s = str(ident)
    if kind == "org":
        return re.sub(r"\D", "", s).zfill(9)
    if kind in ("company", "insider"):
        return s.lstrip("0") or "0"
    if kind == "recipient":
        return s.upper()
    return s


def canonical(kind: str, ident, name: str | None) -> str:
    """The page's path: prefix + slug + "-" + id (just the id when there is no usable name)."""
    i, s = norm_id(kind, ident), slug(name)
    return KINDS[kind][0] + (f"{s}-{i}" if s else i)


def parse(kind: str, key: str) -> str | None:
    """The ID in a URL key ("urban-land-institute-530159845" or "530159845"), or None."""
    key = (key or "").strip().lower() if kind != "committee" else (key or "").strip()
    if kind == "committee":
        m = re.search(r"(C\d{8})$", key.upper())
        return m.group(1) if m else None
    if kind == "recipient":
        m = re.search(r"([A-Za-z0-9]{12})$", key)
        return m.group(1).upper() if m else None
    if kind == "org":
        m = re.search(r"(\d{1,9})$", key)
        return m.group(1).zfill(9) if m else None
    m = _KEY[kind].match(key)
    return m.group(1) if m else None


def names(kind: str, ids: list[str]) -> dict[str, str]:
    """{id: name} for these ids (cached for an hour)."""
    now = time.time()
    out, missing = {}, []
    with _lock:
        for i in ids:
            hit = _cache.get((kind, i))
            if hit and now - hit[0] < TTL:
                out[i] = hit[1]
            else:
                missing.append(i)
    if missing:
        try:
            with db.conn() as conn:
                rows = conn.execute(KINDS[kind][2], (missing,)).fetchall()
        except Exception:  # noqa: BLE001 - a table not there yet: leave those links as they are
            rows = []
        with _lock:
            for r in rows:
                vals = list(r.values())
                _cache[(kind, str(vals[0]))] = (now, vals[1])
                out[str(vals[0])] = vals[1]
            if len(_cache) > 300_000:
                _cache.clear()
    return out


def _bare(kind: str, key: str) -> str | None:
    """The ID when a link uses the bare-ID form (no slug yet), else None."""
    i = parse(kind, key)
    if not i:
        return None
    return i if key == i or key.upper() == i or (kind == "org" and key.isdigit()) else None


def rewrite_links(html: str) -> str:
    """Internal entity links in a page, in slug form ("/org/530159845" becomes "/org/urban-land-...-530159845")."""
    found: dict[str, set] = {}
    for m in _LINK.finditer(html):
        kind = _PREFIX_KIND[m.group(1)]
        i = _bare(kind, m.group(2))
        if i:
            found.setdefault(kind, set()).add(norm_id(kind, i))
    if not found:
        return html
    known = {kind: names(kind, sorted(ids)) for kind, ids in found.items()}

    def sub(m):
        kind = _PREFIX_KIND[m.group(1)]
        i = _bare(kind, m.group(2))
        n = known.get(kind, {}).get(norm_id(kind, i)) if i else None
        return f'href="{canonical(kind, i, n)}{m.group(3)}' if n else m.group(0)
    return _LINK.sub(sub, html)


def redirect(request, kind: str, ident, name: str | None):
    """A 301 to the slug form when the request used another form of the URL, else None."""
    from fastapi.responses import RedirectResponse
    want = canonical(kind, ident, name)
    if request.method in ("GET", "HEAD") and request.url.path != want:
        q = request.url.query
        return RedirectResponse(want + (f"?{q}" if q else ""), status_code=301)
    return None
