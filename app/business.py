"""State business registries on the site (loader/business_registry.py): entity pages, registry matches in search,
on-demand lookups of the states' own APIs on a cache miss, links to registries FURP can't load, and officers'
business roles on person pages.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
log = logging.getLogger("np.business")
COVERAGE = ("FURP doesn't yet include every registered business. Not finding a company here doesn't mean it "
            "doesn't exist.")
LOADED = {"NY": "New York", "CO": "Colorado", "CT": "Connecticut", "OR": "Oregon", "PA": "Pennsylvania",
          "TX": "Texas (franchise taxpayers)", "FL": "Florida"}
# Official registry searches for states FURP can't load (no free bulk data or API, or a CAPTCHA): the name is
# filled in where the state's search takes it in the address (checked 2026-10-23); otherwise the search page.
SEARCH = {
    "AL": "https://arc-sos.state.al.us/cgi/corpname.mbr/output?search={q}&type=ALL&place=ALL&stat=ALL",
    "AK": "https://www.commerce.alaska.gov/cbp/main/search/entities",
    "AZ": "https://ecorp.azcc.gov/EntitySearch/Index",
    "AR": "https://www.ark.org/corp-search/",
    "CA": "https://bizfileonline.sos.ca.gov/search/business",
    "DE": "https://icis.corp.delaware.gov/ecorp/entitysearch/namesearch.aspx",
    "DC": "https://boss.dc.gov/",
    "GA": "https://ecorp.sos.ga.gov/BusinessSearch",
    "HI": "https://hbe.ehawaii.gov/documents/search.html?query={q}",
    "ID": "https://sosbiz.idaho.gov/search/business",
    "IL": "https://apps.ilsos.gov/businessentitysearch/",
    "IN": "https://bsd.sos.in.gov/publicbusinesssearch",
    "IA": "https://sos.iowa.gov/search/business/search.aspx",
    "KS": "https://www.sos.ks.gov/eforms/BusinessEntity/Search.aspx",
    "KY": "https://sosbes.sos.ky.gov/BusSearchNProfile/search.aspx",
    "LA": "https://coraweb.sos.la.gov/CommercialSearch/CommercialSearch.aspx",
    "ME": "https://apps3.web.maine.gov/nei-sos-icrs/ICRS?MainPage=x",
    "MD": "https://egov.maryland.gov/BusinessExpress/EntitySearch",
    "MA": "https://corp.sec.state.ma.us/corpweb/CorpSearch/CorpSearch.aspx",
    "MI": "https://mibusinessregistry.lara.state.mi.us/search/business",
    "MN": "https://mblsportal.sos.mn.gov/Business/BusinessSearch?BusinessName={q}",
    "MS": "https://corp.sos.ms.gov/corp/portal/c/page/corpBusinessIdSearch/portal.aspx",
    "MO": "https://bsd.sos.mo.gov/BusinessEntity/BESearch.aspx",
    "MT": "https://biz.sosmt.gov/search/business",
    "NE": "https://www.nebraska.gov/sos/corp/corpsearch.cgi",
    "NV": "https://esos.nv.gov/EntitySearch/OnlineEntitySearch",
    "NH": "https://quickstart.sos.nh.gov/online/BusinessInquire/",
    "NJ": "https://www.njportal.com/DOR/BusinessNameSearch/",
    "NM": "https://enterprise.sos.nm.gov/search/business",
    "NC": "https://www.sosnc.gov/online_services/search/by_title/_Business_Registration",
    "ND": "https://firststop.sos.nd.gov/search/business",
    "OH": "https://businesssearch.ohiosos.gov/",
    "OK": "https://www.sos.ok.gov/corp/corpInquiryFind.aspx",
    "RI": "https://business.sos.ri.gov/CorpWeb/CorpSearch/CorpSearch.aspx",
    "SC": "https://businessfilings.sc.gov/BusinessFiling/Entity/Search",
    "SD": "https://sosenterprise.sd.gov/BusinessServices/Business/FilingSearch.aspx",
    "TN": "https://tncab.tnsos.gov/business-entity-search",
    "UT": "https://businessregistration.utah.gov/EntitySearch/OnlineEntitySearch",
    "VT": "https://bizfilings.vermont.gov/online/BusinessInquire/",
    "VA": "https://cis.scc.virginia.gov/EntitySearch/Index",
    "WA": "https://ccfs.sos.wa.gov/#/BusinessSearch",
    "WV": "https://apps.sos.wv.gov/business/corporations/",
    "WI": "https://apps.dfi.wi.gov/apps/corpsearch/search.aspx",
    "WY": "https://wyobiz.wyo.gov/Business/FilingSearch.aspx",
    "TX": "https://comptroller.texas.gov/taxes/franchise/account-status/search",
    "FL": "https://search.sunbiz.org/Inquiry/CorporationSearch/ByName",
}
STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "DE": "Delaware",
               "DC": "District of Columbia", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
               "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
               "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
               "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
               "NJ": "New Jersey", "NM": "New Mexico", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
               "OK": "Oklahoma", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
               "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
               "WI": "Wisconsin", "WY": "Wyoming", "TX": "Texas (Secretary of State)", "FL": "Florida (Sunbiz)"}


def registry_links(name: str) -> list[dict]:
    q = quote(name or "")
    return [{"state": s, "name": STATE_NAMES.get(s, s), "url": u.replace("{q}", q), "prefilled": "{q}" in u}
            for s, u in sorted(SEARCH.items(), key=lambda kv: STATE_NAMES.get(kv[0], kv[0]))]


def search_local(q: str, limit: int = 20) -> list[dict]:
    """Registry entities named q (legal endings ignored), exact first, then other names (DBAs), then names that start
    with it."""
    from loader.recalls import core
    c = core(q or "")
    if len(c) < 3:
        return []
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('biz_entities') IS NOT NULL AS ok").fetchone()["ok"]:
                return []
            conn.execute("SET LOCAL statement_timeout = '3s'")
            rows = conn.execute("""SELECT e.*, NULL AS matched FROM biz_entities e WHERE e.name_core = %s
                                   UNION ALL
                                   SELECT e.*, n.name FROM biz_names n JOIN biz_entities e USING (state, entity_id)
                                   WHERE n.name_core = %s
                                   LIMIT %s""", (c, c, limit)).fetchall()
            if not rows:
                rows = conn.execute("""SELECT e.*, NULL AS matched FROM biz_entities e WHERE e.name_core LIKE %s
                                       ORDER BY length(e.name_core), e.name LIMIT %s""", (c + " %", limit)).fetchall()
            return rows
    except Exception:  # noqa: BLE001
        log.exception("biz search %s", q)
        return []


def entity(state: str, entity_id: str) -> dict | None:
    with db.conn() as conn:
        e = conn.execute("SELECT * FROM biz_entities WHERE state = %s AND entity_id = %s", (state, entity_id)).fetchone()
        if not e:
            return None
        people = conn.execute("""SELECT p.name, p.role, p.is_entity, p.address,
                                        (SELECT l.key FROM biz_links l WHERE l.state = p.state AND l.entity_id = p.entity_id
                                         AND l.kind = 'person' AND l.key IN (SELECT id::text FROM person_clusters
                                                                             WHERE name_norm = p.name_norm) LIMIT 1) AS cluster_id
                                 FROM biz_people p WHERE p.state = %s AND p.entity_id = %s
                                 ORDER BY p.is_entity, p.role, p.name LIMIT 100""", (state, entity_id)).fetchall()
        names = conn.execute("SELECT name, kind FROM biz_names WHERE state = %s AND entity_id = %s ORDER BY kind, name LIMIT 100",
                             (state, entity_id)).fetchall()
        links = conn.execute("SELECT kind, key, how FROM biz_links WHERE state = %s AND entity_id = %s AND kind <> 'person'",
                             (state, entity_id)).fetchall()
        out = []
        for l in links:
            if l["kind"] == "org":
                o = conn.execute("SELECT name FROM organizations WHERE ein = %s", (l["key"],)).fetchone()
                out.append({"label": "Nonprofit", "name": o["name"] if o else l["key"], "url": f"/org/{l['key']}",
                            "tag": "EXACT" if "EXACT" in (l["how"] or "") else "FUZZY", "how": l["how"]})
            elif l["kind"] == "formd":
                o = conn.execute("""SELECT latest_accession, issuer_name FROM sec_formd_offerings WHERE cik = %s
                                    ORDER BY latest_date DESC LIMIT 1""", (l["key"],)).fetchone()
                if o:
                    out.append({"label": "Form D issuer", "name": o["issuer_name"], "url": f"/corporate/form-d/{o['latest_accession']}",
                                "tag": "FUZZY", "how": l["how"]})
            elif l["kind"] == "adv":
                out.append({"label": "Investment adviser (Form ADV)", "name": f"CRD {l['key']}",
                            "url": f"https://adviserinfo.sec.gov/firm/summary/{l['key']}", "external": True, "tag": "FUZZY", "how": l["how"]})
            elif l["kind"] == "sec":
                out.append({"label": "SEC filer", "name": f"CIK {l['key']}", "url": f"/corporate/company/{l['key']}",
                            "tag": "FUZZY", "how": l["how"]})
    return {"e": e, "people": people, "names": names, "links": out, "state_name": LOADED.get(state, state),
            "official": SEARCH.get(state, "").replace("{q}", quote(e["name"]))}


def person_roles(cluster_id: int) -> list[dict]:
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('biz_links') IS NOT NULL AS ok").fetchone()["ok"]:
                return []
            return conn.execute("""SELECT e.state, e.entity_id, e.name, e.entity_type, e.status, e.formed,
                                          (SELECT string_agg(DISTINCT p.role, ', ') FROM biz_people p JOIN person_clusters pc
                                             ON pc.id = %s AND pc.name_norm = p.name_norm
                                           WHERE p.state = e.state AND p.entity_id = e.entity_id) AS role
                                   FROM biz_links l JOIN biz_entities e USING (state, entity_id)
                                   WHERE l.kind = 'person' AND l.key = %s ORDER BY e.formed DESC NULLS LAST LIMIT 50""",
                                (cluster_id, str(cluster_id))).fetchall()
    except Exception:  # noqa: BLE001
        return []


def for_record(kind: str, key: str) -> list[dict]:
    """Registry entities linked to a nonprofit (org), Form D issuer (formd, by CIK) or SEC filer (sec)."""
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('biz_links') IS NOT NULL AS ok").fetchone()["ok"]:
                return []
            return conn.execute("""SELECT e.* FROM biz_links l JOIN biz_entities e USING (state, entity_id)
                                   WHERE l.kind = %s AND l.key = %s LIMIT 10""", (kind, key)).fetchall()
    except Exception:  # noqa: BLE001
        return []


def _render(request, template, **ctx):
    from app.main import render
    return render(request, template, biz=__import__("sys").modules[__name__], **ctx)


@router.get("/business/{state}/{entity_id}", response_class=HTMLResponse)
def entity_page(request: Request, state: str, entity_id: str):
    if not re.fullmatch(r"[A-Z]{2}", state):
        raise HTTPException(404)
    data = entity(state, entity_id)
    if not data:
        raise HTTPException(404)
    return _render(request, "business_entity.html", **data)


@router.get("/business", response_class=HTMLResponse)
def business_search(request: Request, q: str = Query("", max_length=120)):
    """Registry search: the local copy first; on a miss, the states' own APIs (each name at most once a month per
    state, results kept), then links to the registries FURP can't search for you."""
    q = q.strip()
    rows, asked = search_local(q), False
    if q and not rows:
        from loader import business_registry
        try:
            business_registry.lookup(q, status=log.info)
            asked = True
        except Exception:  # noqa: BLE001
            log.exception("biz lookup %s", q)
        rows = search_local(q)
    return _render(request, "business_search.html", q=q, rows=rows, asked=asked, links=registry_links(q),
                   coverage=COVERAGE, loaded=LOADED)
