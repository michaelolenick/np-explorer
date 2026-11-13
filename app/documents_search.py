"""The `documents` search intent: uploaded documents in the FURP space, by their reader (owner, 2026-11-12).

"Tell me something about the court case I just uploaded" is a supported request: the planner (app/ask.py) maps it
to the documents tool, this module runs the site's own SQL over the extracted documents (app/space_ingest.py, with
the reader's marks: public for everyone, FURP-readable for the folder's person and super admins, private never),
and the short answer on top puts the rows into words (app/answer.py). Never through the shared result cache,
because what one reader may see another may not.
"""

from __future__ import annotations

import html
import logging
import time

from app import accounts, analytics, ask, db

log = logging.getLogger("np.documents")

NOT_YET = ("Uploaded documents are not extracted yet: the extraction pipeline is being installed. The files are "
           "stored; their text, tables and the people and organizations they mention will be searchable here.")


def run(user: dict | None, parsed: dict, limit: int = 20) -> dict:
    """The documents the reader may see that match the words, newest first when the words are generic."""
    text = (parsed.get("text") or "").strip()
    out = {"kind": "documents", "documents": [], "hits": [], "total": 0, "note": "", "url": ask.edit_url(parsed)}
    try:
        from app import space_ingest
        search = space_ingest.search_documents
    except (ImportError, AttributeError):
        out["note"] = NOT_YET
        return out
    try:
        with db.conn() as conn:
            found = search(conn, user, text, limit)
    except Exception:  # noqa: BLE001
        log.exception("documents: search")
        out["note"] = "The document index could not be searched just now; please try again in a moment."
        return out
    out.update({k: found.get(k, out[k]) for k in ("documents", "hits", "total", "note")})
    if not user and not out["documents"]:
        out["note"] = (out["note"] + " " if out["note"] else "") + "Log in to search the documents in your own folder."
    return out


def summary(question: str, result: dict) -> str | None:
    """A short written answer from the rows (the documents and the matching passages), with the model fallback."""
    from app import answer as nl_answer
    if not result.get("documents"):
        return None
    data = {"documents": [{k: d.get(k) for k in ("filename", "folder", "mark", "kind", "status", "pages", "messages",
                                                   "tables", "entities", "uploaded_at", "summary_text")}
                          | {"mentions": [e.get("text") for e in (d.get("entities_top") or [])][:20]}
                          for d in result["documents"][:5]],
            "passages": [{"where": h.get("where"), "text": h.get("snippet")} for h in result.get("hits", [])[:15]]}
    text = nl_answer._call(question, data)
    return html.escape(nl_answer.no_em_dash(text)) if text else None


def respond(request, q: str, parsed: dict, t0: float):
    from app.main import NL_EXAMPLES, render
    user = accounts.current_user(request)
    result = run(user, parsed)
    answer_html = summary(q or ask.describe(parsed), result)
    resp = render(request, "search_nl.html", q=q, intent=parsed, result=result, reading=ask.describe(parsed),
                  cols=[], sort_note=None, answer_html=answer_html, answer_src=None, edit_url=ask.edit_url,
                  page_url=lambda p: ask.edit_url(parsed), categories=[("", "Any")], category_label=ask.category_label,
                  topics=[], intents=[t["name"] for t in ask.TOOLS if t["name"] != "unknown"], examples=NL_EXAMPLES)
    resp.headers["Cache-Control"] = "no-store"          # per-reader results: never cached
    ask.record((time.monotonic() - t0) * 1000, parsed)
    analytics.search(request, q or "(documents)", "nl", intent="documents", results=result["total"])
    return resp
