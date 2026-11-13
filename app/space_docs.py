"""Documents from the FURP space on the site (owner, 2026-11-12): the public ones have a page, show up in search
results, the JSON API and the MCP server; FURP-readable ones are only ever read by deep queries and by the
logged-in person whose folder they are in (or a super admin) through search; private ones are not here at all
(app/space_ingest.py never extracts them).

Pages: /docs (the public documents), /docs/<token> (one public document: its text by page, its tables, the FURP
records it mentions, the original to download). Both carry noindex: the text is somebody's upload, not FURP's
own data, so search engines are not asked to index it (the person and organization pages that link to it are).

Everything shown here is untrusted document text (see space_ingest's docstring); the templates escape it, nothing
in it is followed or executed.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import accounts, db, space_ingest
from app.config import SITE_URL

router = APIRouter()
log = logging.getLogger("np.space_docs")
PAGE_SHOW = 400           # pages of text shown on a document page
TABLE_SHOW = 30           # tables shown, and rows per table
ENTITY_KINDS = [("person", "People"), ("org", "Organizations and companies"), ("party", "Parties"), ("ein", "EINs"),
                ("cik", "SEC CIKs"), ("ticker", "Tickers"), ("case", "Case numbers"), ("address", "Addresses"),
                ("email", "Email addresses"), ("amount", "Dollar amounts"), ("date", "Dates")]


def _render(request: Request, template: str, status_code: int = 200, **ctx) -> HTMLResponse:
    from app.main import render
    user = accounts.current_user(request)
    return render(request, template, status_code=status_code, user=user, **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('space_docs') AS t").fetchone()["t"] is not None


PUBLIC_SQL = """SELECT f.id AS file_id, f.filename, f.public_token, f.public_at, f.uploaded_at, f.visibility AS mark, d.name AS folder,
                       p.name AS owner_name, s.kind, s.pages, s.messages, s.tables, s.entities, s.matched, s.words, s.language, s.note,
                       s.extracted_at, s.status
                FROM space_files f JOIN space_folders d ON d.id = f.folder_id LEFT JOIN space_people p ON p.id = f.owner_id
                JOIN space_docs s ON s.file_id = f.id
                WHERE f.removed_at IS NULL AND f.visibility = 'public' AND f.public_token IS NOT NULL AND d.visibility <> 'private'
                  AND s.status = 'extracted'"""


def public_doc(conn, token: str) -> dict | None:
    if not (10 < len(token) < 64):
        return None
    return conn.execute(PUBLIC_SQL + " AND f.public_token = %s", (token,)).fetchone()


def public_list(conn, limit: int = 200) -> list[dict]:
    return conn.execute(PUBLIC_SQL + " ORDER BY f.public_at DESC NULLS LAST, f.id DESC LIMIT %s", (limit,)).fetchall()


def doc_url(r: dict) -> str:
    return f"/docs/{r['public_token']}"


def download_url(r: dict) -> str:
    return f"/p/{r['public_token']}/{quote(r['filename'])}"


# --- pages ---------------------------------------------------------------------------------------------------------

@router.get("/docs", response_class=HTMLResponse)
def docs_index(request: Request):
    with db.conn() as conn:
        docs = [dict(r, url=doc_url(r), download=download_url(r)) for r in public_list(conn)] if _ok(conn) else []
    return _render(request, "space_docs.html", docs=docs)


@router.get("/docs/{token}", response_class=HTMLResponse)
def doc_page(request: Request, token: str):
    with db.conn() as conn:
        r = public_doc(conn, token) if _ok(conn) else None
        if not r:
            return _render(request, "space_denied.html", status_code=404, person=None, super_=False, csrf="")
        fid = r["file_id"]
        pages = conn.execute("SELECT page, label, text FROM space_doc_pages WHERE doc_id = %s ORDER BY page LIMIT %s", (fid, PAGE_SHOW)).fetchall()
        tables = conn.execute("SELECT page, name, header, rows, n_rows FROM space_doc_tables WHERE doc_id = %s ORDER BY id LIMIT %s", (fid, TABLE_SHOW)).fetchall()
        ents = conn.execute("""SELECT kind, text, count, pages, dst_kind, dst_key, dst_name, how, confidence FROM space_doc_entities
                               WHERE doc_id = %s ORDER BY (dst_kind IS NULL), count DESC, text LIMIT 2000""", (fid,)).fetchall()
        messages = conn.execute("""SELECT seq, folder, date, from_addr, to_addr, subject, n_attachments, left(body, 600) AS body
                                   FROM space_doc_messages WHERE doc_id = %s ORDER BY date NULLS LAST, seq LIMIT 300""", (fid,)).fetchall() \
            if r["kind"] == "pst" else []
        xl = conn.execute("SELECT count(*) AS n FROM xlinks WHERE src_kind = 'space_doc' AND src_key = %s", (token,)).fetchone()["n"] \
            if conn.execute("SELECT to_regclass('xlinks') AS t").fetchone()["t"] else 0
    groups = []
    for kind, label in ENTITY_KINDS:
        rows = [dict(e, url=space_ingest.entity_url(e["dst_kind"], e["dst_key"])) for e in ents if e["kind"] == kind]
        if rows:
            groups.append({"kind": kind, "label": label, "rows": rows[:200], "n": len(rows), "matched": sum(1 for x in rows if x["url"])})
    for t in tables:
        t["rows"] = t["rows"][:TABLE_SHOW]
    return _render(request, "space_doc.html", doc=dict(r, url=doc_url(r), download=download_url(r)), pages=pages, tables=tables,
                   groups=groups, messages=messages, n_links=xl, page_show=PAGE_SHOW, table_show=TABLE_SHOW)


# --- search results, the API and the MCP server ------------------------------------------------------------------

def search_for_request(request: Request, q: str, limit: int = 8) -> dict | None:
    """The documents section of a results page: public documents for everyone, plus the viewer's own FURP-readable
    ones (every furp-marked one for a super admin). None when there is nothing to show."""
    try:
        if not q or len(q) < 2:
            return None
        user = accounts.current_user(request)
        with db.conn() as conn:
            if not _ok(conn):
                return None
            res = space_ingest.search_documents(conn, user, q, limit=limit)
        if not res["hits"]:
            return None
        docs = {d["file_id"]: d for d in res["documents"]}
        rows = []
        for h in res["hits"]:
            d = docs.get(h["file_id"])
            if d:
                rows.append({**h, "filename": d["filename"], "folder": d["folder"], "mark": d["mark"], "kind": d["kind"]})
        return {"rows": rows[:limit], "total": res["total"], "any_private_to_me": any(r["mark"] != "public" for r in rows)}
    except Exception:  # noqa: BLE001 - an extra section; never fail the search
        log.exception("documents in search")
        return None


def api_search(q: str, n: int) -> list[dict]:
    """The Documents dataset for /api/v1/datasets/documents and the MCP search_dataset: public documents only."""
    with db.conn() as conn:
        if not _ok(conn):
            return []
        res = space_ingest.search_documents(conn, None, q, limit=n)
    docs = {d["file_id"]: d for d in res["documents"]}
    out, seen = [], set()
    for h in res["hits"]:
        d = docs.get(h["file_id"])
        if not d or d["mark"] != "public":
            continue
        row = {"title": d["filename"], "where": h["where"], "snippet": h["snippet"], "uploaded_at": d["uploaded_at"],
               "folder": d["folder"], "kind": d["kind"], "pages": d["pages"], "messages": d["messages"],
               "url": SITE_URL + d["url"]}
        out.append(row)
        seen.add(h["file_id"])
        if len(out) >= n:
            break
    return out


# --- deep queries ---------------------------------------------------------------------------------------------------

def deep_rows(conn, text: str, limit: int = 40) -> list[dict]:
    """For app/deep.py's documents recipe: passages from every FURP-readable and public document (the whole space,
    the super-admin view: deep queries are the owner's research tool) that match the words. Each row's text column
    is named so the label travels with the data into the model prompt."""
    from app import space
    user = {"email": next(iter(space.SUPER_ADMINS)), "status": "active", "id": 0}
    res = space_ingest.search_documents(conn, user, text, limit=limit)
    docs = {d["file_id"]: d for d in res["documents"]}
    rows = []
    for h in res["hits"]:
        d = docs.get(h["file_id"])
        if d:
            rows.append({"document": d["filename"], "folder": d["folder"], "mark": d["mark"], "where": h["where"],
                         "untrusted_document_text": h["snippet"]})
    return rows


def deep_count(conn, text: str) -> int:
    from app import space
    user = {"email": next(iter(space.SUPER_ADMINS)), "status": "active", "id": 0}
    return int(space_ingest.search_documents(conn, user, text, limit=1)["total"])
