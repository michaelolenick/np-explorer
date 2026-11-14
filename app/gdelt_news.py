"""News and events from GDELT on the pages (this module: app/gdelt_news.py; app/news.py is the FURP-in-the-news page) (owner, 2026-11-14): the "In the news" block on organization, person and company
pages (the latest articles that name the organization or person, linked out), the /news-index leaderboards (organizations and
nonprofits most in the news, people most in the news), and the counts for the API and MCP (get_links gets a "news" entry).

Data: loader/gdelt.py (schema gdelt): articles (URL, domain, title, date, language, tone, themes: metadata and links only, never
article text), links (entity to article, with how the match was made), entity_news (per-entity counts, refreshed nightly) and
stats (the totals shown here; they update themselves after each nightly load). Pages never scan the links table: the latest
articles come from its primary key (entity, date), the counts from entity_news.

Source: The GDELT Project, https://www.gdeltproject.org/. Free for any use; use and redistribution must cite the GDELT Project
and link to its site: ATTRIBUTION is on every block and on /data#gdelt.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from app import db
from app.cache import ttl_lru

log = logging.getLogger(__name__)
router = APIRouter()
PUBLIC = os.environ.get("NEWS_PUBLIC", "1") == "1"
SOURCE_NAME = "The GDELT Project"
SOURCE_URL = "https://www.gdeltproject.org/"
ATTRIBUTION = "News article metadata and links: The GDELT Project (https://www.gdeltproject.org/)."
SOURCE = ("Article links, titles, dates, languages and tone come from the GDELT Project's Global Knowledge Graph (GKG 2.0), which "
          "reads news in over 100 languages every 15 minutes from February 2015; FURP stores only that metadata and the link, "
          "never the article text, and matches the people and organizations GDELT names to FURP records by the rules on /data#gdelt. "
          "Source: the GDELT Project, https://www.gdeltproject.org/.")
# Record kinds that carry news, and what the block calls them.
KINDS = {"org": "organization", "person": "person", "sec": "company", "college": "college", "ipo_company": "company",
         "lda_client": "organization", "fed": "organization", "contractor": "organization", "formd": "company", "adv": "adviser"}
LATEST = 10
LATEST_EVENTS = 5
# CAMEO event root codes (the first two digits of an event's code): what the event is.
CAMEO = {"01": "Made a public statement", "02": "Made an appeal", "03": "Expressed intent to cooperate", "04": "Consulted",
         "05": "Engaged in diplomatic cooperation", "06": "Engaged in material cooperation", "07": "Provided aid", "08": "Yielded",
         "09": "Investigated", "10": "Made a demand", "11": "Disapproved", "12": "Rejected", "13": "Threatened", "14": "Protested",
         "15": "Exhibited force posture", "16": "Reduced relations", "17": "Coerced", "18": "Assaulted", "19": "Fought",
         "20": "Used unconventional mass violence"}


def cameo(code: str | None) -> str:
    return CAMEO.get((code or "")[:2], "Event")


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('gdelt.entity_news') AS t").fetchone()["t"] is not None


@ttl_lru(ttl=300)
def stats() -> dict | None:
    """Totals for /news-index, /data and the API: they update themselves from gdelt.stats (set by the nightly summarize)."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            if conn.execute("SELECT to_regclass('gdelt.stats') AS t").fetchone()["t"] is None:
                return None
            rows = conn.execute("SELECT k, v, updated FROM gdelt.stats").fetchall()
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return None
    out = {r["k"]: r["v"] for r in rows}
    for k in ("days", "records_scanned", "articles", "links", "entities", "orgs_in_news", "people_in_news", "events_scanned", "events",
              "event_links", "event_days"):
        try:
            out[k] = int(out.get(k) or 0)
        except ValueError:
            out[k] = 0
    out["updated"] = max(r["updated"] for r in rows)
    return out


def count_text() -> str:
    """One line for /data and the home of the leaderboards: "N articles ... from M scanned" (self-updating)."""
    s = stats()
    if not s or not s["articles"]:
        return ""
    ev = f"; {s['events_scanned']:,} events scanned, {s['events']:,} linked to organizations" if s.get("events_scanned") else ""
    return (f"{s['records_scanned']:,} GDELT news records scanned ({s.get('first_day', '')} to {s.get('last_day', '')}), "
            f"{s['articles']:,} articles linked to {s['entities']:,} organizations and people ({s['links']:,} links){ev}")


def _dom(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


@ttl_lru(ttl=600, maxsize=4096)
def entity(ekind: str, ekey: str, limit: int = LATEST) -> dict | None:
    """The in-the-news data for one record: total, first and last month, and the latest `limit` articles. None when no news."""
    if not PUBLIC or ekind not in KINDS or not ekey:
        return None
    head = rows = ev_head = ev_rows = None
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '3s'")
            if not _ok(conn):
                return None
            head = conn.execute("SELECT n, first_seen, last_seen FROM gdelt.entity_news WHERE ekind = %s AND ekey = %s",
                                (ekind, str(ekey))).fetchone()
            rows = conn.execute("""SELECT a.url, a.domain, a.title, a.seen, a.lang, a.tone, l.how FROM gdelt.links l
                JOIN gdelt.articles a ON a.aid = l.aid WHERE l.ekind = %s AND l.ekey = %s ORDER BY l.seen DESC LIMIT %s""",
                                (ekind, str(ekey), limit)).fetchall() if head else []
            try:
                ev_head = conn.execute("SELECT n, first_day, last_day FROM gdelt.entity_events WHERE ekind = %s AND ekey = %s",
                                       (ekind, str(ekey))).fetchone()
                ev_rows = conn.execute("""SELECT e.day, e.actor1, e.actor2, e.code, e.place, e.url, e.tone FROM gdelt.event_links l
                    JOIN gdelt.events e ON e.eid = l.eid WHERE l.ekind = %s AND l.ekey = %s ORDER BY l.day DESC, l.eid DESC LIMIT %s""",
                                       (ekind, str(ekey), LATEST_EVENTS)).fetchall() if ev_head else []
            except Exception:  # noqa: BLE001 - events not loaded yet
                ev_head = ev_rows = None
    except Exception:  # noqa: BLE001 - an extra block; never fail the page
        log.exception("news.entity %s %s", ekind, ekey)
        return None
    if not rows and not ev_rows:
        return None
    arts = [{"url": r["url"], "domain": r["domain"] or _dom(r["url"]), "title": (r["title"] or "").strip() or _dom(r["url"]),
             "date": r["seen"].date() if r["seen"] else None, "lang": r["lang"], "tone": r["tone"]} for r in (rows or [])]
    evs = [{"date": r["day"], "what": cameo(r["code"]), "with": " and ".join(x.title() for x in (r["actor1"], r["actor2"]) if x),
            "place": r["place"], "url": r["url"]} for r in (ev_rows or [])]
    how = rows[0]["how"] if rows else ""
    return {"kind": ekind, "key": str(ekey), "count": int(head["n"]) if head else 0, "first": head["first_seen"] if head else None,
            "last": head["last_seen"] if head else None, "how": how, "articles": arts, "attribution": ATTRIBUTION,
            "source_url": SOURCE_URL, "events": int(ev_head["n"]) if ev_head else 0,
            "events_first": ev_head["first_day"] if ev_head else None, "events_last": ev_head["last_day"] if ev_head else None,
            "latest_events": evs}


def api_block(kind: str, key: str) -> dict | None:
    """The "news" entry the xlinks API and the MCP get_links tool return."""
    e = entity(kind, str(key), LATEST)
    if not e:
        return None
    how = e["how"] or ""
    conf = "organization name match" if not how.startswith(("Unique", "Full")) else (
        "full name only: unique and rare (unverified)" if how.startswith("Unique") else "full name and a shared organization in the article")
    return {"articles": e["count"], "events": e["events"],
            "latest_events": [{"date": str(v["date"]), "what": v["what"], "with": v["with"], "place": v["place"], "url": v["url"]}
                              for v in e["latest_events"]], "confidence": conf, "first_month": str(e["first"]) if e["first"] else None, "last_month": str(e["last"]) if e["last"] else None,
            "matched_by": e["how"],
            "latest": [{"title": a["title"], "url": a["url"], "domain": a["domain"], "date": str(a["date"]) if a["date"] else None,
                        "language": a["lang"], "tone": round(a["tone"], 2) if a["tone"] is not None else None} for a in e["articles"]],
            "attribution": ATTRIBUTION, "source": SOURCE_URL}


# --- leaderboards ---------------------------------------------------------------------------------------

def _url(ekind: str, ekey: str, name: str) -> str:
    from app import xlinks
    t = xlinks.TARGETS.get(ekind)
    try:
        return t[1](ekey, name) if t else ""
    except Exception:  # noqa: BLE001
        return ""


@ttl_lru(ttl=600)
def leaderboards(limit: int = 50) -> dict | None:
    s = stats()
    if not s:
        return None
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '8s'")
            org = conn.execute("""SELECT DISTINCT ON (lower(name)) ekind, ekey, name, n_month, n FROM (
                    SELECT ekind, ekey, name, n_month, n FROM gdelt.entity_news WHERE ekind <> 'person' AND n_month > 0
                    ORDER BY n_month DESC LIMIT %s) t WHERE name IS NOT NULL ORDER BY lower(name), n_month DESC""", (limit * 6,)).fetchall()
            npo = conn.execute("""SELECT ekind, ekey, name, n_month, n FROM gdelt.entity_news WHERE ekind = 'org' AND n_month > 0
                    ORDER BY n_month DESC LIMIT %s""", (limit,)).fetchall()
            ppl = conn.execute("""SELECT ekind, ekey, name, n_month, n FROM gdelt.entity_news WHERE ekind = 'person' AND n_month > 0
                    ORDER BY n_month DESC LIMIT %s""", (limit,)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("news.leaderboards")
        return None

    def fmt(rows, cap):
        out = []
        for r in sorted(rows, key=lambda r: -r["n_month"])[:cap]:
            out.append({"kind": KINDS.get(r["ekind"], r["ekind"]), "name": r["name"], "month": r["n_month"], "total": r["n"],
                        "url": _url(r["ekind"], r["ekey"], r["name"] or "")})
        return out
    return {"orgs": fmt(org, limit), "nonprofits": fmt(npo, limit), "people": fmt(ppl, limit), "month": s.get("month", ""),
            "stats": s}


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, news=sys.modules[__name__], **ctx)


@router.get("/news-index", response_class=HTMLResponse)
def news_index(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    data = leaderboards()
    if data is None:
        raise HTTPException(404)
    return _render(request, "news_index.html", **data)
