"""Column order by question (owner, 2026-11-06): the figure that answers the question is the first column after the
name, the other figures next, descriptive text after them, identifiers and links last.

The site rule gives every table its default order (app/boards.layout and the per-kind lists below). When a visitor
asked a question (not a bare name), Claude Haiku reads the question and the column labels and orders the columns
the most germane way: one small call (a few hundred tokens), cached 30 days per question in nl_cache, never
changing the rows, only their columns. If the model is off, slow or answers badly, the default order stands."""

from __future__ import annotations

import logging
import os
import re

import httpx

from app import ask, boards
from loader import ntee

log = logging.getLogger("furp.colorder")

MODEL = os.environ.get("COLS_MODEL", "claude-haiku-5-5")
TIMEOUT = 3.0

SYSTEM = ("You order the columns of a table of search results on furp.org, a public-records site, so that the "
          "figure that answers the visitor's question is the first column after the name. You get the question and "
          "the columns as key: label lines. Reply with every key, comma-separated, in the order to show them, and "
          "nothing else. Put the figure the question asks about first; then the other figures, the most relevant to "
          "the question first; then descriptive text; and identifiers (EIN, location, state, year, source or filing "
          "links) last.")

# (key, label, numeric) per result kind of templates/search_nl.html; the first entry is the figure the rows are
# ranked by, and the list is the site rule's order. Rank and Name are never part of it.
KINDS: dict[str, list[tuple[str, str, bool]]] = {
    "daf_orgs": [("value", "Value at year end", True), ("contributions", "Contributions in", True),
                 ("grants", "Grants out", True), ("count", "DAFs held", True), ("ein", "EIN", False),
                 ("location", "Location", False), ("year", "Latest tax year", True), ("filing", "Filing", False)],
    "orgs": [("revenue", "Latest revenue", True), ("ein", "EIN", False), ("location", "Location", False),
             ("year", "Latest year", False)],
    "org_people": [("total", "Total pay from here", True), ("latest_pay", "Latest year pay", True),
                   ("title", "Latest title", False), ("years", "Years", False), ("n_orgs", "Organizations", True)],
    "people": [("total_comp", "Total pay", True), ("title", "Latest title", False), ("orgs", "Organizations", False),
               ("n_orgs", "Number", True), ("years", "Years", False), ("states", "States", False)],
    "vendors": [("paid", "Paid", True), ("service", "Service", False), ("year", "Tax year", False)],
    "payroll": [("pay", "Pay", True), ("institution", "Institution", False), ("title", "Title", False),
                ("year", "Fiscal year", False), ("source", "Source", False)],
    "coaches": [("total", "Total pay", True), ("payroll", "From payroll", True), ("nonprofit", "From nonprofit (990)", True),
                ("org", "School or organization", False), ("sport", "Sport", False), ("role", "Role", False),
                ("year", "Year", False), ("source", "Source", False)],
}


def columns(result: dict) -> list[dict]:
    """The reorderable columns of a result, in the site rule's order (each: key, label, numeric, and for a
    leaderboard its cell kind). Empty for results without a ranked table."""
    kind = result.get("kind")
    if kind == "board" and result.get("board"):
        return [{"key": c["key"], "label": c["label"], "numeric": c["numeric"], "kind": c["kind"], "fmt": c["fmt"]}
                for c in boards.layout(result["board"])]
    if kind == "top_paid" and result.get("board"):
        per_person = bool(result.get("per_person"))
        cols = [("value", result["board"].value.label, True)] + ([("n_years", "Years listed", True)] if per_person else []) \
            + [("org", "Organization", False), ("category", "Category", False), ("state", "State", False),
               ("year", "Best year" if per_person else "Tax year", False)]
        return [{"key": k, "label": lb, "numeric": n} for k, lb, n in cols]
    return [{"key": k, "label": lb, "numeric": n} for k, lb, n in KINDS.get(kind or "", [])]


def order(question: str | None, result: dict) -> list[dict]:
    """The columns in the order to show them for this question: the model's order when there is a question and
    the model answers well (cached per question), else the site rule's."""
    cols = columns(result)
    q = (question or "").strip()
    if len(cols) < 3 or not q or ask.is_plain_name(q) or not ask.enabled():
        return cols
    key = "cols:" + ask.normalize(q) + "|" + str(result.get("kind")) + "|" + ",".join(c["key"] for c in cols)
    hit = ask._shared_get(key)
    keys = hit.get("cols") if isinstance(hit, dict) else None
    if not keys:
        keys = _ask_model(q, cols)
        if keys:
            ask._shared_put(key, {"cols": keys})
    return apply(cols, keys) if keys else cols


# The figure each kind's rows come ranked by, and the row field behind each other figure column.
RANKED = {"daf_orgs": "value", "orgs": "revenue", "org_people": "total", "people": "total_comp", "vendors": "paid",
          "payroll": "pay", "coaches": "total", "top_paid": "value", "board": "value"}
FIELDS = {"daf_orgs": {"contributions": "daf_contributions", "grants": "daf_grants", "count": "daf_count", "year": "tax_year"},
          "org_people": {"latest_pay": "latest_pay", "n_orgs": "n_orgs"}, "people": {"n_orgs": "n_orgs"},
          "coaches": {"payroll": "from_payroll", "nonprofit": "from_nonprofit"}, "top_paid": {"n_years": "n_years"}}


def resort(result: dict, cols: list[dict], intent: dict | None = None) -> tuple[dict, str | None]:
    """(result, note): when the first column is a figure other than the one the rows came ranked by, the rows are
    sorted by it, highest first, so the table's sort and its first column match. A leaderboard result re-reads
    the board sorted by that column (the whole board, ranks as on the board page); the other kinds sort the rows
    they have. The cached result is never changed in place."""
    if not cols or not isinstance(result.get("rows"), list) or not result["rows"]:
        return result, None
    kind, first = result.get("kind"), cols[0]
    if first["key"] == RANKED.get(kind) or not first.get("numeric"):
        return result, None
    if kind == "board":
        b = result.get("board")
        spec = boards.sort_spec(b, first["key"], "desc") if b else None
        if not spec or not boards.meta().get(b.slug):
            return result, None
        i = intent or {}
        filters = {"year": i.get("year"), "form": None, "state": i.get("state"), "q": i.get("name"),
                   "sort": first["key"], "dir": "desc"}
        page = boards.page(b, filters, 1, per_page=i.get("limit") or 25)
        return {**result, "rows": page["rows"]}, (f"Sorted by {first['label'].lower()}, highest first; the rank is "
                                                   f"the board's own, by {b.value.label.lower()}.")
    field = FIELDS.get(kind or "", {}).get(first["key"])
    if not field:
        return result, None
    rows = sorted(result["rows"], key=lambda r: (r.get(field) is None, -(r.get(field) or 0)))
    if rows and "list_rank" in rows[0]:
        rows = [{**r, "list_rank": n} for n, r in enumerate(rows, 1)]
    return {**result, "rows": rows}, f"Sorted by {first['label'].lower()}, highest first, among these rows."


def apply(cols: list[dict], keys: list[str]) -> list[dict]:
    by_key = {c["key"]: c for c in cols}
    out = [by_key[k] for k in keys if k in by_key]
    return out + [c for c in cols if c not in out]


def parse(text: str, cols: list[dict]) -> list[str] | None:
    """The model's reply as keys: every key exactly once, else None."""
    keys = [k.strip().lower() for k in re.split(r"[,\n]+", text or "") if k.strip()]
    want = [c["key"] for c in cols]
    return keys if sorted(keys) == sorted(want) else None


def _ask_model(question: str, cols: list[dict]) -> list[str] | None:
    body = {"model": MODEL, "max_tokens": 200, "system": SYSTEM, "thinking": ntee.thinking_off(MODEL),
            "messages": [{"role": "user", "content": f"Question: {question}\nColumns (key: label):\n"
                          + "\n".join(f"{c['key']}: {c['label']}" for c in cols)}]}
    try:
        r = ask.post(body, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        log.warning("colorder: call failed (%s)", type(e).__name__)
        return None
    if r.status_code != 200:
        log.warning("colorder: model returned %s", r.status_code)
        return None
    data = r.json()
    u = data.get("usage") or {}
    ask._usage(input_tokens=int(u.get("input_tokens") or 0), output_tokens=int(u.get("output_tokens") or 0))
    text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
    keys = parse(text, cols)
    if keys is None:
        log.info("colorder: reply was not a permutation of the columns; default order kept")
    return keys
