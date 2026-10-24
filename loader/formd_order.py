"""Fund ordering for Form D listings (owner, 2026-10-24): every offering gets a family (the sponsor's fund family),
a kind (main_fund, spv, series, other), a series label, a sort order within the family, and, for an SPV or series,
its parent fund. Pages then list each family's main funds in natural order with their SPVs and series under them.

1. Deterministic first. The family is the name with legal endings and the trailing fund designation taken off
   ("Capital Factory Ventures, LP - A1" -> "capital factory ventures"; "Capital Factory IV, L.P." and
   "Capital Factory 5, L.P." -> "capital factory"). The trailing designation sets the order:
   roman numerals (I, II, IV), numbers (Fund 5), years (Partners 2017), letter-number series (A1, B2, C3) and
   "Series II-A" style labels; mixed forms in one family sort together (IV, then 5, then 6). With no designation,
   the first filing date orders it.
2. SPVs ("SPV", "a series of ...", "Co-Invest", or flagged by corporate.is_spv) attach to the main fund their
   "a series of X" names when X is a family, else to the nearest main fund of the sponsor by first filing date
   (the latest one filed on or before the SPV).
3. Names the parser can't confidently place (no designation and no SPV marker, in a family with other funds) go to
   Claude Haiku, one call per family with every name in it (16 at a time, every such family), for kind, parent and order. Results are cached
   (name_hash): only new or changed names are re-run. Each run has a hard spend ceiling (--max-dollars, default $20), counted
   from the token usage Haiku reports, and results are saved every 500 families so a stopped run keeps its work. Low-confidence placements are listed at /admin/fund-order.

Usage: .venv/bin/python -m loader.formd_order [--haiku-families N] [--max-dollars 20]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time

import httpx

from loader import db

ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
LEGAL = r"(?:l\.?\s?p\.?|llc|l\.?l\.?c\.?|inc\.?|ltd\.?|limited|corp\.?|corporation|co\.?|plc|scsp|sarl|s\.?a\.?|lllp|llp)"
SPV_RX = re.compile(r"\bspvs?\b|\ba series of\b|\bco-?invest|\bseries (?:of )?[a-z0-9 ,.&'-]*\bllc\b", re.I)
MODEL = os.environ.get("FUND_ORDER_MODEL", "claude-haiku-5-5")


def roman(s: str) -> int | None:
    s = s.lower()
    if not s or not re.fullmatch(r"[ivxlc]+", s):
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        v = ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total if 0 < total < 400 else None


def designation(name: str) -> tuple[str, str | None, float | None]:
    """(family key, series label, order) from a fund name; order None when there's no designation."""
    s = re.split(r",?\s+\ba series (?:of )?\b", name, maxsplit=1, flags=re.I)[0]        # "X Fund I, a series of Y"
    s = re.sub(r"[,.]?\s+" + LEGAL + r"\s*$", "", s.strip(), flags=re.I)
    s = re.sub(r"[,.]?\s+" + LEGAL + r"\b", " ", s, flags=re.I)                           # "Ventures, LP - A1"
    s = re.sub(r"\s+", " ", s.replace("–", "-")).strip(" ,-")
    label, order = None, None
    m = re.search(r"(?:\bseries\s+)?\b([ivxlc]+|\d{1,4})(?:-([a-z]))?\s*$", s, re.I)
    m2 = re.search(r"\b([a-z])\s?-?(\d{1,3})\s*$", s, re.I)                               # A1, B 2, C-3
    if m2 and not m:
        label = (m2.group(1) + m2.group(2)).upper()
        order = (ord(m2.group(1).upper()) - 64) * 1000 + int(m2.group(2))
        s = s[:m2.start()]
    elif m:
        tok, sub = m.group(1), m.group(2)
        if tok.isdigit():
            n = int(tok)
            order = float(n) if n < 1000 or 1900 <= n <= 2100 else None
        else:
            r = roman(tok)
            order = float(r) if r else None
        if order is not None:
            if sub:
                order += (ord(sub.lower()) - 96) / 100.0
            label = m.group(0).strip()
            s = s[:m.start()]
    fam = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    fam = re.sub(r"\b(?:fund|funds|series|partners fund)\s*$", "", re.sub(r"\s+", " ", fam).strip()).strip()
    return fam or re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()[0], label, order


def name_hash(names) -> str:
    return hashlib.sha1("|".join(sorted(names)).encode()).hexdigest()[:16]


def place(rows: list[dict]) -> list[dict]:
    """Deterministic placement for one sponsor's offerings (rows: root_accession, issuer_name, first_date, is_spv)."""
    out = {}
    for r in rows:
        fam, label, order = designation(r["issuer_name"])
        spv = bool(r.get("is_spv")) or bool(SPV_RX.search(r["issuer_name"]))
        kind = "spv" if spv else ("series" if label and re.match(r"(?i)series|[a-z]\d", label) else "main_fund")
        out[r["root_accession"]] = {"root_accession": r["root_accession"], "family_key": fam, "fund_kind": kind,
                                    "series_label": label, "sort_order": order, "parent_root": None,
                                    "confidence": "high" if (order is not None or spv) else "medium",
                                    "method": "parser", "first_date": r["first_date"], "name": r["issuer_name"]}
    mains = [x for x in out.values() if x["fund_kind"] == "main_fund"]
    fams = {x["family_key"] for x in out.values() if x["fund_kind"] in ("main_fund", "series")}
    for x in out.values():
        if x["fund_kind"] == "spv":
            # SPVs list by date under their parent (their own "Fund I" designations are per deal)
            x["sort_order"] = float(x["first_date"].toordinal()) if x["first_date"] else 0.0
        elif x["sort_order"] is None:
            x["sort_order"] = float(x["first_date"].toordinal()) / 1e6 if x["first_date"] else 0.0   # below numbered funds
        if x["fund_kind"] != "spv":
            continue
        m = re.search(r"\ba series (?:of )?(.+)$", x["name"], re.I)
        parent_fam = designation(m.group(1))[0] if m else None
        pool = [p for p in mains if p["family_key"] == parent_fam] or mains
        before = [p for p in pool if p["first_date"] and x["first_date"] and p["first_date"] <= x["first_date"]]
        best = max(before, key=lambda p: p["first_date"]) if before else (min(pool, key=lambda p: p["first_date"] or x["first_date"]) if pool else None)
        if best:
            x["parent_root"] = best["root_accession"]
            x["confidence"] = "high" if parent_fam in fams else "medium"
            x["method"] = "parser" if parent_fam in fams else "nearest by date"
        else:
            x["confidence"] = "medium"
    # A fund with no designation in a family that has other funds: Haiku decides.
    by_fam = {}
    for x in out.values():
        by_fam.setdefault(x["family_key"], []).append(x)
    for fam, xs in by_fam.items():
        if len(xs) > 1:
            for x in xs:
                if x["confidence"] == "medium" and x["fund_kind"] != "spv":
                    x["confidence"] = "low"
    return list(out.values())


SYSTEM = """You order a private-fund sponsor's Form D offerings. You get every offering name in one family, each with \
an id and first filing date. For each id, return fund_kind (main_fund, spv, series or other), parent_id (the main \
fund an SPV or series belongs to, or null), and sort_order (a number: main funds in their natural order, oldest or \
lowest number first; an SPV or series gets its own order within its parent), and confidence (high, medium, low)."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["id", "fund_kind", "parent_id", "sort_order", "confidence"],
    "properties": {"id": {"type": "string"}, "fund_kind": {"type": "string", "enum": ["main_fund", "spv", "series", "other"]},
                   "parent_id": {"type": ["string", "null"]}, "sort_order": {"type": "number"},
                   "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}}}}}


PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6      # Haiku 5.5, dollars per token


def haiku(family: list[dict]) -> tuple[dict | None, float]:
    """Haiku's placement for one family, and what the call cost in dollars."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, 0.0
    cost = 0.0
    listing = "\n".join(f"{x['root_accession']} | {x['first_date']} | {x['name']}" for x in family)
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 8000, "system": SYSTEM,
                  "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
                  "messages": [{"role": "user", "content": listing}]})
        u = r.json().get("usage", {}) if r.status_code == 200 else {}
        cost = u.get("input_tokens", 0) * PRICE_IN + u.get("output_tokens", 0) * PRICE_OUT
        r.raise_for_status()
        out = json.loads("".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text"))
        return {i["id"]: i for i in out.get("items", [])}, cost
    except Exception as e:  # noqa: BLE001
        print(f"fund order: haiku failed: {type(e).__name__}")
        return None, cost


def sponsor(name: str) -> str:
    """The broad sponsor group families are compared within: the first two words of the name ("capital factory")."""
    m = re.search(r"\ba series (?:of )?(.+)$", name, re.I)          # an SPV belongs to the sponsor it's a series of
    words = re.sub(r"[^a-z0-9 ]+", " ", (m.group(1) if m else name).lower()).split()
    return " ".join(words[:2]) if words else ""


def save(rows: list[dict]) -> None:
    """Upserts placements; a Haiku placement for the same names is never overwritten by a deterministic one."""
    with db.connect() as conn:
        conn.execute("CREATE TEMP TABLE fo (LIKE formd_order INCLUDING DEFAULTS)")
        with conn.cursor() as cur, cur.copy("""COPY fo (root_accession, family_key, fund_kind, series_label, sort_order,
                                               parent_root, confidence, method, name_hash) FROM STDIN""") as cp:
            for x in rows:
                cp.write_row((x["root_accession"], x["family_key"][:200], x["fund_kind"], (x["series_label"] or "")[:40] or None,
                              x["sort_order"], x["parent_root"], x["confidence"], x["method"], x["name_hash"]))
        conn.execute("""INSERT INTO formd_order (root_accession, family_key, fund_kind, series_label, sort_order, parent_root,
                                                 confidence, method, name_hash, updated)
                        SELECT root_accession, family_key, fund_kind, series_label, sort_order, parent_root, confidence, method,
                               name_hash, now() FROM fo
                        ON CONFLICT (root_accession) DO UPDATE SET family_key = excluded.family_key, fund_kind = excluded.fund_kind,
                            series_label = excluded.series_label, sort_order = excluded.sort_order, parent_root = excluded.parent_root,
                            confidence = excluded.confidence, method = excluded.method, name_hash = excluded.name_hash,
                            updated = now()
                        WHERE formd_order.name_hash IS DISTINCT FROM excluded.name_hash OR formd_order.method <> 'haiku'
                              OR excluded.method = 'haiku'""")
        conn.commit()


def build(status=print, haiku_families: int = -1, max_dollars: float = 20.0) -> dict:
    t0 = time.time()
    with db.connect() as conn:
        rows = conn.execute("""SELECT root_accession, issuer_name, first_date, is_spv FROM sec_formd_offerings""").fetchall()
        cached = {r[0]: r for r in conn.execute("SELECT root_accession, name_hash, method FROM formd_order").fetchall()}
    groups: dict[str, list] = {}
    for root, name, first, spv in rows:
        if name:
            groups.setdefault(sponsor(name), []).append({"root_accession": root, "issuer_name": name, "first_date": first, "is_spv": spv})
    placed, todo = [], []
    for g, members in groups.items():
        res = place(members)
        h = name_hash(m["issuer_name"] for m in members)
        for x in res:
            x["name_hash"] = h
        placed += res
        if any(x["confidence"] == "low" for x in res) and 2 <= len(members) <= 200:
            prior = [cached.get(x["root_accession"]) for x in res]
            if not all(p and p[1] == h and p[2] == "haiku" for p in prior):   # not already decided for these names
                todo.append(res)
    todo.sort(key=lambda res: -sum(x["confidence"] == "low" for x in res))   # most unclear funds first, so a ceiling spends where it matters
    todo = todo[:haiku_families] if haiku_families >= 0 else todo
    # Haiku is cheap and each call is small: many families at once, under a hard dollar ceiling. A call starts only
    # while spend plus a worst case for every call in flight stays under the ceiling, so the total never passes it.
    import threading
    from concurrent.futures import ThreadPoolExecutor
    worst = 30_000 * PRICE_IN + 8_000 * PRICE_OUT      # max_tokens 8000; inputs are far under 30k tokens
    lock, spend = threading.Lock(), {"spent": 0.0, "inflight": 0, "stopped": False}
    def ask(res):
        with lock:
            if spend["stopped"] or spend["spent"] + (spend["inflight"] + 1) * worst > max_dollars:
                spend["stopped"] = True
                return res, None
            spend["inflight"] += 1
        ans, cost = haiku(res)
        with lock:
            spend["inflight"] -= 1
            spend["spent"] += cost
        return res, ans
    asked = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        for start in range(0, len(todo), 500):
            batch = todo[start:start + 500]
            for res, ans in pool.map(ask, batch):
                if not ans:
                    continue
                asked += 1
                ids = {y["root_accession"] for y in res}
                for x in res:
                    a = ans.get(x["root_accession"])
                    if a and (x["confidence"] == "low" or (x["fund_kind"] == "spv" and x["method"] == "nearest by date")):
                        x.update(fund_kind=a["fund_kind"], sort_order=float(a["sort_order"]),
                                 parent_root=a["parent_id"] if a["parent_id"] in ids else x["parent_root"],
                                 confidence=a["confidence"], method="haiku")
            save([x for res in batch for x in res])
            status(f"fund order: Haiku placed {asked:,} of {len(todo):,} families, ${spend['spent']:.2f} spent "
                   f"(ceiling ${max_dollars:.2f})")
            if spend["stopped"]:
                status(f"fund order: stopped at the ${max_dollars:.2f} ceiling")
                break
    save(placed)
    with db.connect() as conn:
        conn.execute("DELETE FROM formd_order o WHERE NOT EXISTS (SELECT 1 FROM sec_formd_offerings s WHERE s.root_accession = o.root_accession)")
        conn.commit()
        counts = dict(conn.execute("SELECT confidence, count(*) FROM formd_order GROUP BY 1").fetchall())
    status(f"fund order: {len(placed):,} offerings in {len(groups):,} sponsor groups; Haiku for {asked} of {len(todo)} families, "
           f"${spend['spent']:.2f}; {counts} ({time.time() - t0:.0f}s)")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--haiku-families", type=int, default=-1, help="at most this many families (default: all)")
    ap.add_argument("--max-dollars", type=float, default=20.0, help="hard Haiku spend ceiling for this run")
    a = ap.parse_args()
    build(haiku_families=a.haiku_families, max_dollars=a.max_dollars)
