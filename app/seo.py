"""Titles, meta descriptions and schema.org data for entity pages, written from each page's own data, e.g.
"Jane Q. Smith: board roles at 4 nonprofits, $412,000 in reported pay". Templates use seo.title, seo.description
and seo.jsonld when a route passes them."""

from __future__ import annotations

import re

from app.config import SITE_URL


def money(v) -> str:
    v = float(v or 0)
    if v >= 1e9:
        return f"${v / 1e9:.1f} billion"
    if v >= 1e6:
        return f"${v / 1e6:.1f} million"
    return f"${v:,.0f}"


def _name(s: str | None) -> str:
    s = (s or "").strip()
    return s.title() if s.isupper() else s


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def org(data: dict, everyone: list, extras: dict, path: str) -> dict:
    o, h = data["org"], data.get("headline")
    name = _name(o["name"])
    bits = []
    if h and h.get("total_revenue") is not None:
        bits.append(f"{money(h['total_revenue'])} revenue ({h['tax_year']})")
    paid = [p for p in everyone if p.get("total")]
    if everyone:
        bits.append(f"{len(everyone):,} {'person' if len(everyone) == 1 else 'people'} listed")
    top = max(paid, key=lambda p: p.get("total") or 0, default=None)
    if top:
        bits.append(f"top pay {money(top['total'])}")
    for key, label in (("fed", "federal awards"), ("lobby", "lobbying"), ("committees", "political committees")):
        if extras.get(key):
            bits.append(label)
    title = f"{name}: " + ", ".join(bits[:3]) if bits else name
    where = ", ".join(x for x in ((o.get("city") or "").title(), o.get("state")) if x)
    desc = (f"{name}{' (' + where + ')' if where else ''}, EIN {o['ein'][:2]}-{o['ein'][2:]}: "
            + ("; ".join(bits) if bits else "nonprofit record")
            + ". Officers, pay, grants, vendors and finances from its IRS Form 990 filings, every number linked to "
              "its source.")
    ein = f"{o['ein'][:2]}-{o['ein'][2:]}"
    ld = {"@context": "https://schema.org", "@type": "NGO", "@id": SITE_URL + path, "name": name,
          "url": SITE_URL + path, "taxID": ein, "identifier": _ids(EIN=ein)}
    sub = str(o.get("subsection") or "").lstrip("0")
    if sub.isdigit() and 1 <= int(sub) <= 28:          # schema.org's NonprofitType members Nonprofit501c1..c28
        ld["nonprofitStatus"] = f"https://schema.org/Nonprofit501c{int(sub)}"
    if data.get("mission"):
        ld["description"] = str(data["mission"])[:300]
    if where:
        ld["address"] = _address({"addressLocality": (o.get("city") or "").title() or None,
                                  "addressRegion": o.get("state"), "streetAddress": o.get("street"),
                                  "postalCode": o.get("zip")})
    ld["sameAs"] = [x for x in (_website(o.get("website")),
                                f"https://projects.propublica.org/nonprofits/organizations/{int(o['ein'])}") if x]
    if h and h.get("num_employees"):
        ld["numberOfEmployees"] = {"@type": "QuantitativeValue", "value": h["num_employees"]}
    if top:
        ld["employee"] = {"@type": "Person", "name": _name(top.get("display_name") or top.get("name_raw"))}
    return {"title": title[:110], "description": desc[:300], "jsonld": ld}


def person(data: dict, extras: dict, path: str, org_names: dict | None = None) -> dict:
    c = data["cluster"]
    name = _name(c["display_name"])
    n = c.get("n_orgs") or 0
    total = (data.get("lifetime") or {}).get("total") or 0
    role = "roles" if not c.get("latest_title") else ("board roles" if any(
        w in (c["latest_title"] or "").lower() for w in ("director", "trustee", "board", "chair")) else "roles")
    bits = [f"{role} at {_plural(n, 'nonprofit')}"]
    if total:
        bits.append(f"{money(total)} in reported pay")
    for key, label in (("politics", "political donations"), ("secrec", "corporate filings"),
                       ("lobbying", "registered lobbyist"), ("payroll", "public payroll")):
        if extras.get(key):
            bits.append(label)
    title = f"{name}: " + ", ".join(bits[:3])
    years = f"{c['first_year']}-{c['last_year']}" if c.get("first_year") and c.get("last_year") and \
        c["first_year"] != c["last_year"] else str(c.get("last_year") or "")
    desc = (f"{name}: " + "; ".join(bits)
            + (f", {years}" if years else "") + (f". Latest title: {c['latest_title']}" if c.get("latest_title") else "")
            + ". From nonprofit tax returns and other public records, every number linked to its source.")
    orgs = [o for o in (c.get("orgs") or [])[:5] if o]
    ld = {"@context": "https://schema.org", "@type": "Person", "@id": SITE_URL + path, "name": name,
          "url": SITE_URL + path}
    if c.get("latest_title"):
        ld["jobTitle"] = c["latest_title"]
    eins = []
    for r in data.get("rows") or []:                    # newest first on the page; up to ten organizations
        if r.get("ein") and r["ein"] not in eins:
            eins.append(r["ein"])
    if eins:
        from app import slugs
        names = {**(org_names or {}), **{r["ein"]: r.get("org_name") for r in data.get("rows") or [] if r.get("org_name")}}
        ld["affiliation"] = [{"@type": "Organization", "name": _name(names.get(e) or e),
                              "url": SITE_URL + slugs.canonical("org", e, names.get(e)), "taxID": f"{e[:2]}-{e[2:]}"}
                             for e in eins[:10]]
    elif orgs:
        ld["affiliation"] = [{"@type": "Organization", "name": _name(o)} for o in orgs]
    ciks = ((extras.get("secrec") or {}).get("owner_ciks") or [])[:3]
    if ciks:
        ld["identifier"] = _ids(**{"SEC CIK": [str(x).lstrip("0") for x in ciks]})
        ld["sameAs"] = [_edgar(x) for x in ciks]
    return {"title": title[:110], "description": desc[:300], "jsonld": ld}


def contractor(data: dict, path: str) -> dict:
    c = data["contractor"]
    name = _name(c["name_raw"])
    payers = len({r["ein"] for r in data["rows"]})
    bits = [f"paid {money(data['total'])} by {_plural(payers, 'nonprofit')}" if data["total"] else
            f"vendor to {_plural(payers, 'nonprofit')}"]
    if c.get("service_description"):
        bits.append((c["service_description"] or "").lower()[:60])
    title = f"{name}: " + ", ".join(bits)
    desc = (f"{name}{', ' + (c.get('city') or '').title() + ', ' + c['state'] if c.get('city') and c.get('state') else ''}: "
            + "; ".join(bits) + ". Who paid it, for what and when, from IRS Form 990 contractor lists.")
    ld = {"@context": "https://schema.org", "@type": "Organization", "name": name, "url": SITE_URL + path}
    return {"title": title[:110], "description": desc[:300], "jsonld": ld}


def _ids(**ids) -> list[dict]:
    """schema.org identifiers: PropertyValue per id (a list value gives one each); empty ones left out."""
    out = []
    for k, v in ids.items():
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            if x not in (None, ""):
                out.append({"@type": "PropertyValue", "propertyID": k, "value": str(x)})
    return out


def _address(a: dict | None) -> dict | None:
    a = {k: str(v).strip() for k, v in (a or {}).items() if v is not None and str(v).strip()}
    return {"@type": "PostalAddress", **a} if a else None


def _website(w: str | None) -> str | None:
    w = (w or "").strip()
    if not w or " " in w or "." not in w or w.upper() in ("N/A", "NONE", "NA"):
        return None
    return w if w.lower().startswith("http") else "https://" + w.lower()


def _edgar(cik) -> str:
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={str(cik).lstrip('0').zfill(10)}"


def ld(type_: str, name: str | None, path: str, *, cik=None, accession=None, fund_id=None, ein=None, fec=None,
       uei=None, unitid=None, lda_client=None, lda_registrant=None, lda_lobbyist=None, patent=None, serial=None,
       assignee=None, inventor=None, registry=None, website=None, founding=None, address=None) -> dict:
    """schema.org data for pages whose title and description the template writes (committees, lobbying, SEC...):
    the page's identifiers (EIN, SEC CIK, FEC ID, UEI, IPEDS UNITID, LDA ids, USPTO numbers, a state registry id),
    sameAs links to the same record at its official source, the address and the founding date where known."""
    url = SITE_URL + path
    out = {"@context": "https://schema.org", "@type": type_, "@id": url, "name": _name(name), "url": url}
    ids = _ids(**{"SEC CIK": str(cik).lstrip("0") if cik else None, "SEC accession number": accession,
                  "SEC private fund ID": fund_id, "EIN": f"{str(ein)[:2]}-{str(ein)[2:]}" if ein else None,
                  "FEC committee ID": fec, "UEI": uei, "IPEDS UNITID": unitid, "LDA client ID": lda_client,
                  "LDA registrant ID": lda_registrant, "LDA lobbyist ID": lda_lobbyist, "US patent number": patent,
                  "USPTO serial number": serial, "PatentsView assignee ID": assignee,
                  "PatentsView inventor ID": inventor,
                  f"{registry[0]} business entity ID" if registry else "registry": registry[1] if registry else None})
    if ids:
        out["identifier"] = ids
    if ein and type_ != "Person":
        out["taxID"] = f"{str(ein)[:2]}-{str(ein)[2:]}"
    same = [_edgar(cik) if cik else None,
            f"https://www.fec.gov/data/committee/{fec}/" if fec else None,
            f"https://nces.ed.gov/collegenavigator/?id={unitid}" if unitid else None,
            f"https://patents.google.com/patent/US{patent}" if patent else None,
            f"https://tsdr.uspto.gov/#caseNumber={serial}&caseType=SERIAL_NO&searchType=statusSearch" if serial else None,
            _website(website)]
    if any(same):
        out["sameAs"] = [x for x in same if x]
    if address and _address(address):
        if type_ == "Person":
            out["homeLocation"] = {"@type": "Place", "address": _address(address)}
        elif type_ != "CreativeWork":
            out["address"] = _address(address)
    if founding and type_ not in ("Person", "CreativeWork"):
        out["foundingDate"] = founding.isoformat() if hasattr(founding, "isoformat") else str(founding)
    return out


def website() -> dict:
    """The home page: the site (with a SearchAction that runs a name search) and the FURP Alliance behind it."""
    from app.config import GITHUB_URL
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": SITE_URL + "/#website", "url": SITE_URL + "/", "name": "FURP",
         "alternateName": ["furp.org", "Free, Usable Records for the Public"],
         "description": "A free public-records explorer that cross-references people and organizations across "
                        "nonprofit tax returns, payrolls, campaign contributions, lobbying, federal spending, SEC "
                        "filings, patents, trademarks, state business registries and food recalls.",
         "inLanguage": "en-US", "publisher": {"@id": SITE_URL + "/#organization"},
         "license": "https://creativecommons.org/licenses/by/4.0/",
         "potentialAction": {"@type": "SearchAction",
                             "target": {"@type": "EntryPoint",
                                        "urlTemplate": SITE_URL + "/search?type=name&q={search_term_string}"},
                             "query-input": "required name=search_term_string"}},
        {"@type": "Organization", "@id": SITE_URL + "/#organization", "name": "FURP Alliance", "alternateName": "FURP",
         "url": SITE_URL + "/", "logo": SITE_URL + "/static/furp-logo.png", "email": "info@furp.org",
         "sameAs": ["https://www.linkedin.com/company/furp-data", GITHUB_URL]}]}


STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
               "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
               "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
               "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
               "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
               "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
               "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
               "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
               "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
               "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico"}


def board(b, window: str | None, finding: str | None, filters: dict, csv_url: str, path: str) -> dict:
    """A leaderboard's title (with its filters, so each indexed view is distinct), a description that leads with
    the page's own finding, and schema.org Dataset data (Google Dataset Search)."""
    parts = []
    if filters.get("year"):
        parts.append(str(filters["year"]))
    if filters.get("state"):
        parts.append(STATE_NAMES.get(filters["state"], filters["state"]))
    if filters.get("q"):
        parts.append(f"named {filters['q']}")
    title = f"{b.title} ({b.subtitle})" + (", " + ", ".join(parts) if parts else "")
    lead = (finding.replace("Top row: ", "Top: ", 1) + ". ") if finding else ""
    desc = (lead + b.definition + f" From {b.source_label}" + (f", {window}" if window else "") + ".")[:300]
    years = re.findall(r"(?:19|20)\d\d", window or "")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": title, "description": (b.definition + " "
          + b.formula)[:5000], "url": SITE_URL + path, "isAccessibleForFree": True,
          "license": "https://creativecommons.org/licenses/by/4.0/",
          "creator": {"@type": "Organization", "name": "The FURP Alliance", "url": SITE_URL},
          "keywords": [b.subtitle, b.source_label, "public records", "leaderboard"],
          "variableMeasured": b.value.label,
          "distribution": [
              {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE_URL + csv_url},
              {"@type": "DataDownload", "encodingFormat": "application/geo+json",
               "contentUrl": SITE_URL + csv_url.replace(".csv", "/map", 1)
               + ("&" if "?" in csv_url else "?") + "format=geojson"}]}
    if len(years) >= 2:
        ld["temporalCoverage"] = f"{years[0]}/{years[-1]}"
    return {"title": title[:150], "description": desc, "jsonld": ld}


def item_list(name: str, path: str, items: list[dict]) -> dict:
    """schema.org ItemList for a page that lists links (the day's finds)."""
    return {"@context": "https://schema.org", "@type": "ItemList", "name": name, "url": SITE_URL + path,
            "numberOfItems": len(items),
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": x["question"],
                                 "url": SITE_URL + x["url"]} for i, x in enumerate(items)]}
