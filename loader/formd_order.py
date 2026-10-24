"""Fund ordering for Form D listings (owner, 2026-10-24): every offering gets a family (the sponsor's fund family),
a kind (main_fund, spv, series, other), a series label, a sort order within the family, and, for an SPV or series,
its parent fund. Pages then list each family's main funds in natural order with their SPVs and series under them.

1. Deterministic first. The family is the name with legal endings and the trailing fund designation taken off
   ("Capital Factory Ventures, LP - A1" -> "capital factory ventures"; "Capital Factory IV, L.P." and
   "Capital Factory 5, L.P." -> "capital factory"). The trailing designation sets the order:
   roman numerals (I, II, IV), numbers (Fund 5), years (Partners 2017), letter-number series (A1, B2, C3) and
   "Series II-A" style labels; mixed forms in one family sort together (IV, then 5, then 6). With no designation,
   the first filing date orders it.
   Feeder and parallel vehicles ("Fund IV-QP", "Portfolio 4 Offshore", "Fund (Offshore PF)") sort right after
   the fund they parallel.
2. SPVs ("SPV", "a series of ...", "Co-Invest", or flagged by corporate.is_spv) attach to the main fund their
   "a series of X" names when X is a family, else to the nearest main fund of the sponsor by first filing date
   (the latest one filed on or before the SPV).
3. Also settled without Haiku: a family that is one company filing again under the same name (ordered by date),
   and operating companies (no fund words in the name: kind "other", ordered by date).
4. Only the names still unplaced go to Claude Haiku, as names alone (the family's placed funds listed for
   reference), answered in compact JSON with no explanations and no thinking. Large runs go through the Message
   Batches API (half price) with the fixed instructions prompt-cached; small nightly runs call directly. Results are
   cached (name_hash): only new or changed names are re-run. Each run has a hard spend ceiling (--max-dollars,
   default $5): requests are only sent while their worst-case cost (every input token a cache write, every output
   token used) fits under it, and the actual cost is counted from the usage Haiku reports. Low-confidence
   placements are listed at /admin/fund-order.

Usage: .venv/bin/python -m loader.formd_order [--haiku-families N] [--max-dollars 5]
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
PARALLEL = re.compile(r"[\s,-]*\(?\b(offshore(?: pf)?|onshore|qp|delaware|cayman|parallel|feeder|master|institutional"
                      r"|tax[- ]exempt|erisa|ira)\b\)?\s*$", re.I)
FUNDISH = re.compile(r"\b(?:funds?|partners|capital|ventures|investors|investments?|portfolio|opportunit(?:y|ies)|credit|"
                     r"equity|reit|strateg(?:y|ies)|offshore|master|feeder|l\.?p\.?|series|spv)\b", re.I)
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


def designation(name: str) -> tuple[str, str | None, float | None, str | None]:
    """(family key, series label, order, parallel vehicle) from a fund name; order None when there's no designation."""
    s = re.split(r",?\s+\ba series (?:of )?\b", name, maxsplit=1, flags=re.I)[0]        # "X Fund I, a series of Y"
    s = re.sub(r"[,.]?\s+" + LEGAL + r"\s*$", "", s.strip(), flags=re.I)
    s = re.sub(r"[,.]?\s+" + LEGAL + r"\b", " ", s, flags=re.I)                           # "Ventures, LP - A1"
    s = re.sub(r"\s+", " ", s.replace("–", "-")).strip(" ,-")
    variant = None                                                                         # "Fund IV-QP", "Fund (Offshore)"
    while (pm := PARALLEL.search(s)) and pm.start() > 0:
        v = pm.group(1)
        variant = (v.upper() if len(v) <= 3 else v.title()) + (f" {variant}" if variant else "")
        s = s[:pm.start()].strip(" ,-")
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
    if variant:
        label = f"{label}-{variant}" if label else variant
        order = order + 0.001 if order is not None else None                              # right after the fund it parallels
    fam = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    fam = re.sub(r"\b(?:fund|funds|series|partners fund)\s*$", "", re.sub(r"\s+", " ", fam).strip()).strip()
    return fam or re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()[0], label, order, variant


def base_name(name: str) -> str:
    """The name without its legal ending, for spotting one company filing again ("Kleo, Inc." / "KLEO INC")."""
    s = re.sub(r"[,.]?\s+" + LEGAL + r"\s*$", "", name.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def name_hash(names) -> str:
    return hashlib.sha1("|".join(sorted(names)).encode()).hexdigest()[:16]


def place(rows: list[dict]) -> list[dict]:
    """Deterministic placement for one sponsor's offerings (rows: root_accession, issuer_name, first_date, is_spv)."""
    out = {}
    for r in rows:
        fam, label, order, variant = designation(r["issuer_name"])
        spv = bool(r.get("is_spv")) or bool(SPV_RX.search(r["issuer_name"]))
        kind = "spv" if spv else ("series" if variant or (label and re.match(r"(?i)series|[a-z]\d", label)) else "main_fund")
        out[r["root_accession"]] = {"root_accession": r["root_accession"], "family_key": fam, "fund_kind": kind,
                                    "series_label": label, "sort_order": order, "parent_root": None,
                                    "confidence": "high" if (order is not None or spv) else "medium",
                                    "method": "parser", "first_date": r["first_date"], "name": r["issuer_name"],
                                    "variant": variant}
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
            same = len({base_name(x["name"]) for x in xs}) == 1          # one company filing again: date order is right
            for x in xs:
                if same and x["fund_kind"] == "main_fund" and not FUNDISH.search(x["name"]):
                    x["fund_kind"] = "other"                               # an operating company raising again
                if x["confidence"] == "medium" and x["fund_kind"] != "spv" and not same:
                    if FUNDISH.search(x["name"]):
                        x["confidence"] = "low"
                    else:                                                  # an operating company, not a fund
                        x.update(fund_kind="other", confidence="high")
    # A parallel vehicle sits under the main fund with the same number.
    for x in out.values():
        if x["variant"] and x["fund_kind"] == "series" and x["sort_order"] is not None:
            twin = [p for p in mains if p["family_key"] == x["family_key"] and p["sort_order"] is not None
                    and int(p["sort_order"]) == int(x["sort_order"])]
            if twin:
                x["parent_root"] = twin[0]["root_accession"]
    return list(out.values())


SYSTEM = """You sort private investment offerings filed on SEC Form D into fund families. Each request is one \
sponsor. "Funds" lists the sponsor's offerings that are already placed, labeled F1, F2 and so on. "Place" lists the \
offerings to classify, numbered 1, 2 and so on. You see names only.

For every numbered name, return one item with exactly these keys:
- "i": its number.
- "k": its kind. "m" = a main fund (a pooled fund the sponsor raises in its own right). "s" = an SPV (a vehicle \
for one deal or one company, co-investment, sidecar, "a series of" another entity). "v" = a parallel or feeder \
vehicle of one main fund (offshore, QP, institutional, Cayman, Delaware, master or feeder versions, "Fund II-B"). \
"o" = other: an operating company, management company, general partner, or anything that is not a fund.
- "p": the parent, for "s" and "v" only: the F label (like "F3") or the number (like "2") of the main fund it \
belongs to. null when there is no clear parent, and always null for "m" and "o".
- "c": your confidence in this item: "h" (high), "m" (medium) or "l" (low: the name doesn't settle it).
- "o": the fund's position in the sponsor's numbered series when the name implies one (Fund III = 3, "Third" = 3, \
a vintage year like 2019 = 2019, "Opportunity Fund" with no number = null). null when the name implies none.

Rules: answer from the names only. Do not invent numbers. When unsure of a parent, use null. Return every numbered \
name exactly once. Output only the JSON, no explanations.

Example request:
Funds:
F1 Acme Ventures Fund I, L.P.
F2 Acme Ventures Fund II, L.P.
Place:
1 Acme Ventures Opportunity Fund, L.P.
2 Acme Ventures Fund II Offshore Feeder Ltd.
3 Acme Ventures Management, LLC
4 Acme Ventures - Stripe Co-Invest, LLC
5 Acme Ventures Third Fund, L.P.

Example answer:
{"r":[{"i":1,"k":"m","p":null,"o":null,"c":"h"},{"i":2,"k":"v","p":"F2","o":2,"c":"h"},{"i":3,"k":"o","p":null,"o":null,"c":"h"},\
{"i":4,"k":"s","p":null,"o":null,"c":"h"},{"i":5,"k":"m","p":null,"o":3,"c":"h"}]}

Example request:
Funds:
F1 Northgate Capital Partners 2016, L.P.
F2 Northgate Capital Partners 2019, L.P.
Place:
1 Northgate Capital Partners Annex Fund, L.P.
2 Northgate Capital Partners 2019 Institutional, L.P.
3 Northgate Capital Holdings, Inc.

Example answer:
{"r":[{"i":1,"k":"m","p":null,"o":null,"c":"h"},{"i":2,"k":"v","p":"F2","o":2019,"c":"h"},{"i":3,"k":"o","p":null,"o":null,"c":"h"}]}

Example request:
Funds:
F1 Redwood Credit Fund IV, LP
Place:
1 Redwood Credit Strategies, LP
2 Redwood Credit SPV 2023-1, LLC
3 Redwood Credit Strategies (Cayman), Ltd.

Example answer:
{"r":[{"i":1,"k":"m","p":null,"o":null,"c":"h"},{"i":2,"k":"s","p":"F1","o":null,"c":"h"},{"i":3,"k":"v","p":"1","o":null,"c":"h"}]}"""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"], "properties": {"r": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["i", "k", "p", "o", "c"],
    "properties": {"i": {"type": "integer"}, "k": {"type": "string", "enum": ["m", "s", "v", "o"]},
                   "p": {"type": ["string", "null"]}, "o": {"type": ["number", "null"]},
                   "c": {"type": "string", "enum": ["h", "m", "l"]}}}}}}
KINDS = {"m": "main_fund", "s": "spv", "v": "series", "o": "other"}
# Haiku 5.5, dollars per token. Batches are half price; a 1-hour cache write is 2x input, a cache read 0.1x.
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6
API = "https://api.anthropic.com/v1/messages"
# DeepSeek through OpenRouter (owner, 2026-10-24): used first when --model deepseek, Haiku for whatever it returns
# malformed or low confidence. The worst case uses the priciest OpenRouter endpoint for the model; the actual cost
# is what OpenRouter reports.
OR_MODEL = os.environ.get("FUND_ORDER_OR_MODEL", "deepseek/deepseek-v4.1-flash-1017")
OR_WORST_IN, OR_WORST_OUT = 0.50 / 1e6, 1.20 / 1e6


def headers() -> dict:
    return {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"}


def request(res: list[dict]) -> tuple[dict, list[dict], list[dict]] | None:
    """One family's Haiku request: names only, the unplaced ones numbered, the placed funds listed as F1, F2..."""
    todo = [x for x in res if x["confidence"] == "low"]
    if not todo:
        return None
    funds = sorted((x for x in res if x["confidence"] != "low" and x["fund_kind"] == "main_fund"),
                   key=lambda x: x["sort_order"] or 0.0)[-40:]
    text = ("Funds:\n" + "\n".join(f"F{n} {x['name']}" for n, x in enumerate(funds, 1)) + "\n" if funds else "") + \
           "Place:\n" + "\n".join(f"{n} {x['name']}" for n, x in enumerate(todo, 1))
    params = {"model": MODEL, "max_tokens": 34 * len(todo) + 60, "thinking": {"type": "disabled"},
              "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
              "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
              "messages": [{"role": "user", "content": text}]}
    return params, todo, funds


def worst_cost(params: dict, batch: bool, model: str = "haiku") -> float:
    """An upper bound on a request's cost: every input token billed as a cache write (~3 chars a token), every
    output token used."""
    chars = len(SYSTEM) + len(params["messages"][0]["content"])
    if model == "deepseek":
        return chars / 3 * OR_WORST_IN + params["max_tokens"] * OR_WORST_OUT
    return (0.5 if batch else 1.0) * (chars / 3 * 2 * PRICE_IN + params["max_tokens"] * PRICE_OUT)


def cost(usage: dict, batch: bool) -> float:
    u = usage or {}
    return (0.5 if batch else 1.0) * (u.get("input_tokens", 0) * PRICE_IN + u.get("cache_creation_input_tokens", 0) * 2 * PRICE_IN
                                      + u.get("cache_read_input_tokens", 0) * 0.1 * PRICE_IN + u.get("output_tokens", 0) * PRICE_OUT)


def answer(message: dict) -> list[dict] | None:
    try:
        return json.loads("".join(c.get("text", "") for c in message.get("content", []) if c.get("type") == "text"))["r"]
    except Exception:  # noqa: BLE001 - truncated or empty: the family stays as the parser left it
        return None


def apply(todo: list[dict], funds: list[dict], items: list[dict], method: str = "haiku", final: bool = True) -> None:
    """Writes a model's answers onto the family's unplaced rows. With final False, low-confidence answers are left
    unplaced for the fallback model."""
    for a in items:
        if not isinstance(a.get("i"), int) or not 1 <= a["i"] <= len(todo):
            continue
        if a.get("c") == "l" and not final:
            continue
        x, kind, p = todo[a["i"] - 1], KINDS.get(a.get("k"), "other"), a.get("p")
        parent = None
        if p and p[:1] == "F" and p[1:].isdigit() and 1 <= int(p[1:]) <= len(funds):
            parent = funds[int(p[1:]) - 1]["root_accession"]
        elif p and p.isdigit() and 1 <= int(p) <= len(todo) and int(p) != a["i"]:
            parent = todo[int(p) - 1]["root_accession"]
        if kind == "spv":
            order = float(x["first_date"].toordinal()) if x["first_date"] else 0.0
        elif a.get("o") is not None:
            order = float(a["o"]) + (0.001 if kind == "series" else 0.0)
        else:
            order = x["sort_order"]
        x.update(fund_kind=kind, sort_order=order, parent_root=parent if kind in ("spv", "series") else None,
                 confidence="low" if a.get("c") == "l" else "medium", method=method)


def haiku_one(job) -> tuple[list[dict] | None, float]:
    try:
        r = httpx.post(API, timeout=60, headers=headers(), json=job[0])
        body = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"fund order: haiku failed: {type(e).__name__}")
        return None, 0.0
    return (answer(body) if r.status_code == 200 else None), cost(body.get("usage"), batch=False)


def deepseek_one(job) -> tuple[list[dict] | None, float]:
    """The same request through OpenRouter, JSON schema enforced; cost as OpenRouter reports it."""
    params = job[0]
    try:
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions", timeout=90,
                       headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                       json={"model": OR_MODEL, "max_tokens": params["max_tokens"], "temperature": 0,
                             "reasoning": {"enabled": False}, "provider": {"require_parameters": True},
                             "usage": {"include": True},
                             "response_format": {"type": "json_schema", "json_schema": {"name": "placement", "strict": True, "schema": SCHEMA}},
                             "messages": [{"role": "system", "content": SYSTEM}, params["messages"][0]]})
        body = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"fund order: deepseek failed: {type(e).__name__}")
        return None, 0.0
    spent = float((body.get("usage") or {}).get("cost") or 0.0)
    try:
        return json.loads(body["choices"][0]["message"]["content"])["r"], spent
    except Exception:  # noqa: BLE001 - malformed: Haiku takes it
        return None, spent


def direct(jobs: list, status=print, one=haiku_one, method: str = "haiku", final: bool = True) -> float:
    """Requests sent straight away, 16 at a time, answers applied as they come. Returns dollars spent."""
    from concurrent.futures import ThreadPoolExecutor
    spent = 0.0
    with ThreadPoolExecutor(max_workers=16) as pool:
        for job, (items, c) in zip(jobs, pool.map(one, jobs)):
            spent += c
            if items is not None:
                apply(job[1], job[2], items, method, final)
    return spent


def batch(jobs: list, status=print, chunk: int = 500) -> float:
    """Many requests: Message Batches (half price) of 500 families each, all sent at once; each batch's answers are
    applied and saved as soon as it ends, so a stopped run keeps its work. Returns dollars spent."""
    ids = []
    for start in range(0, len(jobs), chunk):
        reqs = [{"custom_id": f"f{start + n}", "params": job[0]} for n, job in enumerate(jobs[start:start + chunk])]
        r = httpx.post(API + "/batches", timeout=300, headers=headers(), json={"requests": reqs})
        r.raise_for_status()
        ids.append(r.json()["id"])
    status(f"fund order: {len(ids)} batches sent for {len(jobs):,} families: {', '.join(ids)}")
    spent, failed, pending, last = 0.0, 0, list(ids), time.time()
    tokens = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0}
    while pending:
        time.sleep(60)
        for bid in list(pending):
            b = httpx.get(f"{API}/batches/{bid}", timeout=60, headers=headers()).json()
            if b["processing_status"] != "ended":
                continue
            pending.remove(bid)
            done = []
            with httpx.stream("GET", b["results_url"], timeout=600, headers=headers()) as rr:
                for line in rr.iter_lines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    job = jobs[int(row["custom_id"][1:])]
                    res = row["result"]
                    if res["type"] == "succeeded":
                        u = res["message"].get("usage") or {}
                        spent += cost(u, batch=True)
                        for k in tokens:
                            tokens[k] += u.get(k) or 0
                    if res["type"] != "succeeded" or (items := answer(res["message"])) is None:
                        failed += 1
                        continue
                    apply(job[1], job[2], items)
                    done.append(job)
            save([x for job in done for x in job[1]])
            status(f"fund order: batch {bid} ended and saved ({b['request_counts']}); ${spent:.4f} so far")
        if pending and time.time() - last > 600:
            status(f"fund order: {len(pending)} of {len(ids)} batches still running; ${spent:.4f} so far")
            last = time.time()
    status(f"fund order: batches done; {failed} families without a usable answer; tokens {tokens}")
    return spent


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


def build(status=print, haiku_families: int = -1, max_dollars: float = 5.0, model: str = "haiku") -> dict:
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
            prior = [cached.get(x["root_accession"]) for x in res if x["confidence"] == "low"]
            if not all(p and p[1] == h and p[2] in ("haiku", "deepseek") for p in prior):   # not already decided for these names
                todo.append(res)
    todo.sort(key=lambda res: -sum(x["confidence"] == "low" for x in res))   # most unclear funds first, so a ceiling spends where it matters
    todo = todo[:haiku_families] if haiku_families >= 0 else todo
    # Only the unplaced names go to a model. Requests are taken in order while their worst-case cost fits under the
    # ceiling, so the actual spend can't pass it. With DeepSeek first, Haiku gets what it returned malformed or low,
    # under what's left of the same ceiling; a large Haiku run goes as one batch at half price.
    deepseek = model == "deepseek" and bool(os.environ.get("OPENROUTER_API_KEY"))
    def take(families, budget, use_batch, who):
        jobs, worst = [], 0.0
        for res in families:
            job = request(res)
            if not job:
                continue
            w = worst_cost(job[0], use_batch, who)
            if worst + w > budget:
                status(f"fund order: ${max_dollars:.2f} ceiling reached at {len(jobs):,} of {len(families):,} families for {who}; the rest wait for the next run")
                break
            jobs.append(job)
            worst += w
        return jobs, worst
    spent, asked, families = 0.0, 0, todo
    if deepseek and families:
        jobs, worst = take(families, max_dollars, False, "deepseek")
        status(f"fund order: DeepSeek for {len(jobs):,} families ({sum(len(j[1]) for j in jobs):,} names), worst case ${worst:.2f}")
        spent += direct(jobs, status, deepseek_one, "deepseek", final=False)
        asked = len(jobs)
        families = [res for res in todo[:len(jobs)] if any(x["confidence"] == "low" for x in res)]
        status(f"fund order: DeepSeek ${spent:.4f}; {len(families):,} families left malformed or low for Haiku")
    if families and os.environ.get("ANTHROPIC_API_KEY"):
        use_batch = len(families) > 50
        jobs, worst = take(families, max_dollars - spent, use_batch, "haiku")
        if jobs:
            status(f"fund order: Haiku for {len(jobs):,} families ({sum(len(j[1]) for j in jobs):,} names), "
                   f"{'batch' if use_batch else 'direct'}, worst case ${worst:.2f}")
            spent += batch(jobs, status) if use_batch else direct(jobs, status)
            asked = max(asked, len(jobs))
    save(placed)
    with db.connect() as conn:
        conn.execute("DELETE FROM formd_order o WHERE NOT EXISTS (SELECT 1 FROM sec_formd_offerings s WHERE s.root_accession = o.root_accession)")
        conn.commit()
        counts = dict(conn.execute("SELECT confidence, count(*) FROM formd_order GROUP BY 1").fetchall())
    status(f"fund order: {len(placed):,} offerings in {len(groups):,} sponsor groups; Haiku for {asked:,} of {len(todo):,} families, "
           f"${spent:.4f} (${spent / max(asked, 1):.6f} a family); {counts} ({time.time() - t0:.0f}s)")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--haiku-families", type=int, default=-1, help="at most this many families (default: all)")
    ap.add_argument("--model", choices=["haiku", "deepseek"], default="haiku", help="first model for unplaced names")
    ap.add_argument("--max-dollars", type=float, default=5.0, help="hard Haiku spend ceiling for this run")
    a = ap.parse_args()
    build(haiku_families=a.haiku_families, max_dollars=a.max_dollars, model=a.model)
