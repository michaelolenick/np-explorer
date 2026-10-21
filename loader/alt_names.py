"""Alternate names for every organization (org_alt_names): short names, acronyms and doing-business-as names, so a
search for "ULI" finds the Urban Land Institute. Sources, each recorded on the row:

  dba      "Doing business as" names from the 990 header (and the organization's latest DBA), split where a filer
           packed several into one line ("ULI - THE URBAN LAND INSTITUTE" gives "ULI" and "Urban Land Institute").
           Care-of lines ("C/O Smith LLP") are skipped.
  website  The stem of the website on its returns (uli.org gives "ULI"), skipping hosting services and
           generic stems.
  acronym  The initials of the legal name's significant words (Urban Land Institute gives "ULI"), for names of
           three or more significant words; "of", "the", "and", "inc", "foundation" and the like are skipped.
  llm      For the largest organizations, short names and acronyms a language model suggests, kept only when
           the name, DBA or website supports them (see verified()).

The IRS Business Master File's sort-name field is not used: it is not a reliable short name (loader/bmf.py).
The curated aliases in org_aliases (one meaning per alias, reviewed) still take precedence in search.

build() rebuilds the dba, website and acronym rows; llm_suggest() adds model rows for organizations that don't
have them yet (largest first), so the nightly run picks up new filers.
"""

from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import urlsplit

from loader import db

STOP = {"of", "the", "and", "for", "in", "on", "at", "to", "a", "an", "inc", "incorporated", "co", "corp",
        "corporation", "company", "llc", "ltd", "foundation", "fund", "trust", "association", "assn", "society",
        "nonprofit", "non", "profit", "org", "organization", "chapter", "dba", "aka"}
HOSTS = {"facebook", "google", "sites", "wix", "wixsite", "squarespace", "weebly", "godaddysites", "wordpress",
         "blogspot", "yolasite", "webs", "tripod", "angelfire", "geocities", "linkedin", "instagram", "twitter",
         "youtube", "gmail", "yahoo", "hotmail", "aol", "comcast", "none", "na", "n", "nonprofit", "org", "home",
         "info", "web", "website", "my", "mysite", "site", "online", "http", "https", "www", "charity", "givelively",
         "networkforgood", "paypal", "gofundme", "eventbrite", "churchcenter", "ecwid", "jimdo", "strikingly"}
GENERIC = STOP | {"health", "welfare", "insurance", "plan", "pension", "benefit", "benefits", "united", "states",
                  "national", "american", "center", "services", "service", "group", "return", "affiliates", "and",
                  "local", "union", "council", "district", "county", "city", "state", "school", "schools"}
SPLIT = re.compile(r"\s+-\s+|\s*/\s*|\s*\|\s*|\s*;\s*|\s+aka\s+|\s+a/k/a\s+|\s+dba\s+|\s+d/b/a\s+", re.I)


def norm(s: str) -> str:
    from app.aliases import alias_norm
    return alias_norm(s)


def acronym_letters(name: str) -> str:
    """Initials of every word of the name except articles and legal forms (lower case): "Young Mens Christian
    Association of Greater Seattle" gives "ymcags"."""
    return "".join(w[0] for w in re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split()
                   if w not in ("the", "of", "and", "for", "a", "an", "inc", "incorporated", "co", "corp", "llc"))


def acronym(name: str) -> str | None:
    words = [w for w in re.sub(r"[^A-Za-z0-9 ]+", " ", name or "").split() if w.lower() not in STOP]
    if len(words) < 3 or any(w.isdigit() for w in words):
        return None
    a = "".join(w[0] for w in words).upper()
    return a if 3 <= len(a) <= 8 else None


def website_stem(url: str) -> str | None:
    u = (url or "").strip().lower()
    if not u or "@" in u:
        return None
    if "://" not in u:
        u = "http://" + u
    try:
        host = (urlsplit(u).hostname or "").removeprefix("www.")
    except ValueError:              # malformed entries on some returns ("[www...")
        return None
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return None
    stem = parts[-2] if parts[-2] not in ("org", "com", "net", "edu", "co", "gov") or len(parts) < 3 else parts[-3]
    if stem in HOSTS or not re.fullmatch(r"[a-z0-9-]{2,30}", stem) or stem.isdigit():
        return None
    return stem


def dba_parts(dba: str) -> list[str]:
    from app.address import is_care_of
    if not dba or is_care_of(dba):
        return []
    return [p.strip(" .,") for p in SPLIT.split(dba) if p and len(p.strip(" .,")) >= 2]


def build(status=print) -> dict:
    """Rebuild the dba, website, acronym and former-name rows (the llm rows are kept). Former names are the
    names on an organization's earlier returns ("Humane Society of the United States" is now "Humane World for
    Animals"); shortened or cut-off spellings of the current name are left out."""
    t0 = time.time()
    rows: dict[tuple, str] = {}
    with db.connect() as conn:
        cur = conn.cursor(name="alt_names_orgs")
        cur.itersize = 50_000
        cur.execute("""SELECT o.ein, o.name, o.name_norm, o.dba, o.website,
                              (SELECT array_agg(DISTINCT f.dba) FROM filings f WHERE f.ein = o.ein AND f.dba IS NOT NULL) AS dbas,
                              (SELECT array_agg(DISTINCT f.website) FROM filings f WHERE f.ein = o.ein AND f.website IS NOT NULL) AS sites,
                              (SELECT array_agg(DISTINCT f.org_name) FROM filings f WHERE f.ein = o.ein AND f.org_name IS NOT NULL) AS names
                       FROM organizations o WHERE o.name IS NOT NULL""")
        counts = {"dba": 0, "website": 0, "acronym": 0, "former": 0}
        for ein, name, name_norm, dba, website, dbas, sites, names in cur:
            own = norm(name)
            name_words = set(re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split())
            for d in {dba, *(dbas or [])} - {None}:
                for part in dba_parts(d):
                    n = norm(part)
                    words = set(re.sub(r"[^a-z0-9 ]+", " ", part.lower()).split())
                    # Filers often spill the rest of the legal name into the DBA line ("... of the United States"):
                    # a piece made only of the name's own words, or only of generic words, is not a short name.
                    if not words or words <= name_words or words <= GENERIC:
                        continue
                    if n and n != own and (n, ein, "dba") not in rows:
                        rows[(n, ein, "dba")] = part.upper() if len(part) <= 6 and part.isupper() else part.title()
                        counts["dba"] += 1
            for w in {website, *(sites or [])} - {None}:
                stem = website_stem(w)
                if stem and norm(stem) != own and (norm(stem), ein, "website") not in rows:
                    rows[(norm(stem), ein, "website")] = stem.upper() if len(stem) <= 6 else stem
                    counts["website"] += 1
            for old in names or []:
                n = norm(old)
                if n and n != own and not own.startswith(n) and not n.startswith(own) and (n, ein, "former") not in rows:
                    rows[(n, ein, "former")] = old.title() if old.isupper() else old
                    counts["former"] += 1
            a = acronym(name)
            if a and (norm(a), ein, "acronym") not in rows:
                rows[(norm(a), ein, "acronym")] = a
                counts["acronym"] += 1
        cur.close()
        conn.execute("DELETE FROM org_alt_names WHERE source IN ('dba', 'website', 'acronym', 'former')")
        with conn.cursor() as c, c.copy("COPY org_alt_names (alias_norm, ein, source, alias) FROM STDIN") as cp:
            for (n, ein, src), alias in rows.items():
                if n:
                    cp.write_row((n, ein, src, alias[:120]))
        conn.commit()
        conn.execute("ANALYZE org_alt_names")
        conn.commit()
    status(f"alt names: {counts} in {time.time() - t0:.0f}s")
    return counts


# --- model suggestions for the largest organizations -----------------------------------------------

SYSTEM = """For each US nonprofit listed, give the short names and acronyms people commonly use for it (for example \
"Urban Land Institute" is "ULI"; "American Society for the Prevention of Cruelty to Animals" is "ASPCA"). Only \
names you are confident are in common use for that exact organization; none is a fine answer. Reply with JSON: \
{"results": [{"ein": "...", "names": ["..."]}]}."""


def verified(alias: str, name: str, dba: str | None, website: str | None) -> bool:
    """A suggestion is kept when the organization's own data supports it: it is an acronym of the name's words (in
    order, allowing skipped small words), appears in the DBA, matches the website stem, or is made of the name's
    words."""
    a = re.sub(r"[^a-z0-9 ]", "", alias.lower()).strip()
    if not a or len(a) > 60:
        return False
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split()
    letters = a.replace(" ", "")
    if " " not in a and 2 <= len(letters) <= 10:
        it = iter(w[0] for w in words)
        if all(ch in it for ch in letters) and letters[0] == words[0][0] if words else False:
            return True
    if dba and a in re.sub(r"[^a-z0-9 ]", "", dba.lower()):
        return True
    stem = website_stem(website or "")
    if stem and (stem == letters or stem.replace("-", "") == letters):
        return True
    return all(w in words for w in a.split()) and len(a.split()) >= 2


def llm_suggest(limit: int = 50_000, batch: int = 100, status=print, max_minutes: float | None = None) -> int:
    """Model suggestions, verified, for the `limit` largest organizations (by latest revenue) not yet asked."""
    import httpx
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return 0
    stop = time.time() + max_minutes * 60 if max_minutes else None
    kept = 0
    with db.connect() as conn:
        todo = conn.execute("""
            SELECT o.ein, o.name, o.city, o.state, o.dba, o.website FROM organizations o
            WHERE o.latest_total_revenue IS NOT NULL
              AND o.ein NOT IN (SELECT ein FROM org_alt_names_asked)
            ORDER BY o.latest_total_revenue DESC LIMIT %s""", (limit,)).fetchall()
    for i in range(0, len(todo), batch):
        if stop and time.time() > stop:
            break
        chunk = todo[i:i + batch]
        listing = "\n".join(f"{e} | {n} | {c or ''}, {s or ''} | {w or ''}" for e, n, c, s, d, w in chunk)
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
                "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": os.environ.get("ALIAS_MODEL", "claude-haiku-5-5"), "max_tokens": 8000,
                      "system": SYSTEM, "messages": [{"role": "user", "content": "EIN | name | place | website\n" + listing}]})
            text = "".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text")
            text = text[text.find("{"):text.rfind("}") + 1]
            results = {x.get("ein"): x.get("names") or [] for x in json.loads(text).get("results", [])}
        except Exception as e:  # noqa: BLE001 - skip this batch, try it again next run
            status(f"alt names llm: batch {i // batch} failed ({type(e).__name__})")
            continue
        rows = []
        for ein, name, city, state, dba, website in chunk:
            for alias in results.get(ein, [])[:6]:
                if isinstance(alias, str) and norm(alias) and norm(alias) != norm(name) and verified(alias, name, dba, website):
                    rows.append((norm(alias), ein, "llm", alias.strip()[:120]))
        with db.connect() as conn:
            with conn.cursor() as c:
                c.executemany("""INSERT INTO org_alt_names (alias_norm, ein, source, alias) VALUES (%s, %s, %s, %s)
                                 ON CONFLICT DO NOTHING""", rows)
                c.executemany("INSERT INTO org_alt_names_asked (ein) VALUES (%s) ON CONFLICT DO NOTHING",
                              [(x[0],) for x in chunk])
            conn.commit()
        kept += len(rows)
        if (i // batch) % 20 == 0:
            status(f"alt names llm: {i + len(chunk):,} organizations asked, {kept:,} names kept")
    status(f"alt names llm: {kept:,} names kept")
    return kept
