"""The categorization helper (owner, 2026-11-05): a command-line program that sends nonprofits and Form D issuers to
Anthropic's Message Batches API (Claude Haiku 5.5, half price, the taxonomy in a cached system prompt), validates
the answers against the taxonomies, retries invalid ones once, writes the results, and keeps a spend ledger.
Everything the model does goes through this program with ANTHROPIC_API_KEY from the environment; the key is never
printed, logged or stored.

Kinds:
  nonprofit  organizations with no published NTEE code (loader/ntee.py's prompt, taxonomy and tables): answers go
             to ntee_inferred (ein, ntee_code, confidence, model, batch_id, ...); `loader.ntee build` then rebuilds
             nonprofit_ntee with furp_category/furp_subcategory from the FURP topic index.
  formd      Form D issuers, one per CIK (the latest offering): answers go to form_d_category (cik, accession,
             issuer_name, published_industry, published_fund_type, category, subcategory, fund_type, confidence,
             model, batch_id, ...). The taxonomy is the SEC's own Form D industry list (formd_taxonomy: 12 groups,
             their industries) plus FUND_TYPES; for a pooled investment fund the model says what the fund invests in.

Tables:  category_ledger (one row per batch: kind, requests, items, tokens, dollars, running total, status),
         category_batch_items (what each pending batch request holds, so answers match back and nothing is sent
         twice), formd_taxonomy, form_d_category, category_tests (the hidden-label tests).

Commands:  .venv/bin/python -m loader.categorize estimate                      items per dollar, from the ledger or defaults
           .venv/bin/python -m loader.categorize test nonprofit|formd [N]      N (200) items with published labels, hidden
           .venv/bin/python -m loader.categorize submit nonprofit|formd --wave 25   batches up to about $25 (estimated)
           .venv/bin/python -m loader.categorize collect                       wait for ended batches, write, update the ledger
           .venv/bin/python -m loader.categorize status                        ledger totals, pending batches, coverage
           .venv/bin/python -m loader.categorize build                         nonprofit_ntee + counts (loader.ntee build)
Guards: HARD_STOP dollars in all (ledger plus the estimate for pending batches); no new batches after LAST_SUBMIT
(the credit grant expires 2026-11-14 and a batch may take a day); everything resumable and idempotent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from loader import db, ntee

HARD_STOP = float(os.environ.get("CATEGORIZE_HARD_STOP", "180"))
LAST_SUBMIT = dt.date(2026, 11, 12)
MODEL = ntee.ANTHROPIC_MODEL
BATCH_REQUESTS = 4000
FORMD_PER_REQUEST = 10
BATCH_PRICE = {"input_tokens": 0.05, "output_tokens": 0.25, "cache_creation_input_tokens": 0.0625, "cache_read_input_tokens": 0.005}
DEFAULT_COST = {"nonprofit": 0.00003, "formd": 0.00003}      # dollars per item before a batch has been measured

# --- Form D taxonomy: the SEC's industry groups on Form D, as the filings use them -----------------
FORMD_GROUPS = {
    "Agriculture": ["Agriculture"],
    "Banking & Financial Services": ["Commercial Banking", "Insurance", "Investing", "Investment Banking", "Pooled Investment Fund",
                                     "Other Banking and Financial Services"],
    "Business Services": ["Business Services"],
    "Energy": ["Coal Mining", "Electric Utilities", "Energy Conservation", "Environmental Services", "Oil and Gas", "Other Energy"],
    "Health Care": ["Biotechnology", "Health Insurance", "Hospitals and Physicians", "Pharmaceuticals", "Other Health Care"],
    "Manufacturing": ["Manufacturing"],
    "Real Estate": ["Commercial", "Construction", "REITS and Finance", "Residential", "Other Real Estate"],
    "Retailing": ["Retailing"],
    "Restaurants": ["Restaurants"],
    "Technology": ["Computers", "Telecommunications", "Other Technology"],
    "Travel": ["Airlines and Airports", "Lodging and Conventions", "Tourism and Travel Services", "Other Travel"],
    "Other": ["Other"],
}
FUND_TYPES = {"venture": "venture capital fund", "private_equity": "private equity or buyout fund", "hedge": "hedge fund",
              "real_estate": "real estate fund or property vehicle", "operating_company": "an operating business, not a fund",
              "other": "other pooled vehicle (fund of funds, SPV, credit fund, family office vehicle, trust)"}
FORMD_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"],
                "properties": {"r": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["i", "g", "s", "f", "p"],
                    "properties": {"i": {"type": "integer"}, "g": {"type": "string"}, "s": {"type": "string"},
                                   "f": {"type": "string"}, "p": {"type": "number"}}}}}}


def formd_system() -> str:
    groups = "\n".join(f"{g}: " + "; ".join(inds) for g, inds in FORMD_GROUPS.items())
    funds = "\n".join(f"{k}: {v}" for k, v in FUND_TYPES.items())
    return ("You classify issuers that filed SEC Form D (private securities offerings) from the filing's own fields. For "
            "each issuer give: g, the industry group; s, the industry within that group; f, the fund type; p, your "
            "confidence 0 to 1. Use exactly the names below.\n\nIndustry groups and their industries (group: industries):\n"
            + groups + "\n\nFund types:\n" + funds +
            "\n\nRules: an operating business gets f = operating_company and the industry it operates in. A pooled "
            "investment fund gets the fund type that fits (a venture or seed fund is venture; buyout, growth equity and "
            "secondaries are private_equity; a trading, long/short, quant, macro or credit-trading vehicle is hedge; a "
            "fund, syndication or single-asset vehicle holding property is real_estate; funds of funds, SPVs, co-invest "
            "vehicles, credit or lending funds and family-office vehicles are other) and, for g and s, the sector the "
            "fund invests in when the name or the filing shows it (a biotech venture fund is Health Care / Biotechnology; "
            "a real estate fund is Real Estate and the property type; a tech fund is Technology / Other Technology); when "
            "the fund's sector cannot be told, use Banking & Financial Services / Pooled Investment Fund. The industry "
            "as filed is a hint from the issuer, often just 'Pooled Investment Fund' or 'Other'; improve on it when the "
            "name, the related persons or the sponsor make the sector clear.\n\nAnswer with JSON only: "
            "{\"r\":[{\"i\":<item number>,\"g\":\"<group>\",\"s\":\"<industry>\",\"f\":\"<fund type>\",\"p\":<confidence>}, ...]}, "
            "one item per numbered issuer, in order.")


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v >= 999_999_999_999:
        return "indefinite"
    return f"${v:,.0f}"


def formd_text(r: dict, hide_label: bool = False) -> str:
    lines = [f"Issuer: {r['issuer_name']}"]
    if not hide_label and r.get("industry"):
        lines.append(f"Industry as filed: {r['industry']}" + (f"; fund type as filed: {r['fund_type']}" if r.get("fund_type") else ""))
    place = ", ".join(x for x in (r.get("city"), r.get("state")) if x)
    if place:
        lines.append("Address: " + place)
    if r.get("jurisdiction"):
        lines.append(f"Incorporated in: {r['jurisdiction']}" + (f" ({r['entity_type']})" if r.get("entity_type") else ""))
    off = []
    if r.get("offering_amount") is not None:
        off.append("offering " + _money(r["offering_amount"]))
    if r.get("amount_sold") is not None:
        off.append("sold " + _money(r["amount_sold"]))
    if r.get("investors"):
        off.append(f"{r['investors']} investors")
    if r.get("min_investment"):
        off.append("minimum " + _money(r["min_investment"]))
    if r.get("revenue_range") and r["revenue_range"] not in ("Decline to Disclose", "Not Applicable"):
        off.append("revenue " + r["revenue_range"])
    if r.get("exemptions"):
        off.append("exemption " + str(r["exemptions"])[:40])
    if off:
        lines.append("Offering: " + "; ".join(off))
    if r.get("persons"):
        lines.append("Related persons: " + "; ".join(r["persons"][:8]))
    return "\n".join(lines)


FORMD_CAND_SQL = """
    SELECT o.cik, o.latest_accession AS accession, o.issuer_name, o.industry, o.fund_type, o.entity_type, o.city, o.state,
           d.jurisdiction, d.exemptions, d.revenue_range, o.latest_offering AS offering_amount, o.latest_sold AS amount_sold,
           o.investors, o.min_investment,
           (SELECT array_agg(p.name || ' (' || coalesce(p.relationships, '') || ')' ORDER BY p.seq) FROM sec_formd_people p
             WHERE p.accession = o.latest_accession) AS persons
    FROM (SELECT DISTINCT ON (cik) * FROM sec_formd_offerings ORDER BY cik, latest_date DESC NULLS LAST, latest_accession DESC) o
    LEFT JOIN sec_formd d ON d.accession = o.latest_accession
    WHERE {where}
    ORDER BY {order}"""
FORMD_ORDER = "coalesce(nullif(o.latest_offering, 999999999999), 0) + coalesce(o.latest_sold, 0) DESC, o.cik"


# --- kinds ------------------------------------------------------------------------------------------

class Nonprofit:
    name, key, per_request = "nonprofit", "ein", None
    schema = ntee.SCHEMA

    def system(self, tax):
        return ntee.system_prompt(tax["majors"], tax["codes"])

    def candidates_sql(self, where_extra: str = "") -> str:
        return ntee.CAND_SQL.format(where=ntee._cand_where(False).replace("ntee_batch_eins b", "category_batch_items b")
                                    .replace("b.ein = o.ein", "b.kind = 'nonprofit' AND b.key = o.ein") + where_extra, order=ntee.CAND_ORDER)

    def item(self, row, tax, hide=False):
        text, has = ntee.org_text(row, tax["acts"])
        return text, (ntee.BATCH_TEXT if has else ntee.BATCH_PLAIN)

    def answers(self, rows, parsed, usage, err, tax):
        return ntee.answers(rows, parsed, usage, err, tax)

    def retry(self, rows, out, tax, sysp):
        ntee.retry_invalid(rows, out, tax, sysp)

    def rows_by_key(self, conn, keys):
        return {r["ein"]: dict(r) for r in conn.cursor(row_factory=ntee._dict_row).execute(
            ntee.CAND_SQL.format(where="o.ein = ANY(%s)", order="o.ein"), (keys,)).fetchall()}

    def write(self, conn, recs, meta, batch_id):
        with conn.cursor() as cur:
            for r in recs:
                cur.execute("""INSERT INTO ntee_inferred (ein, ntee_code, confidence, model, prompt_tokens, completion_tokens, cost,
                               attempts, error, raw, filer, batch_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (ein) DO UPDATE SET ntee_code = EXCLUDED.ntee_code, confidence = EXCLUDED.confidence,
                                 model = EXCLUDED.model, prompt_tokens = EXCLUDED.prompt_tokens, completion_tokens = EXCLUDED.completion_tokens,
                                 cost = EXCLUDED.cost, attempts = EXCLUDED.attempts, error = EXCLUDED.error, raw = EXCLUDED.raw,
                                 filer = EXCLUDED.filer, batch_id = EXCLUDED.batch_id, inferred_at = now()""",
                            (r["ein"], r["code"], r["conf"], MODEL, round(r["pt"]), round(r["ct"]), r["cost"], r["attempts"], r["error"],
                             r["raw"], (meta.get(r["ein"]) or {}).get("filer"), batch_id))
        conn.commit()

    def test_rows(self, conn, n):
        half = n // 2
        rows = conn.cursor(row_factory=ntee._dict_row).execute(ntee.CAND_SQL.format(
            where="""o.ein IN ((SELECT ein FROM organizations WHERE ntee IS NOT NULL AND latest_filing_year IS NOT NULL AND length(ntee) >= 3 ORDER BY md5(ein || 'cat') LIMIT %s)
                            UNION ALL (SELECT ein FROM organizations WHERE ntee IS NOT NULL AND latest_filing_year IS NULL AND length(ntee) >= 3 ORDER BY md5(ein || 'cat') LIMIT %s))""",
            order="o.ein"), (half, n - half)).fetchall()
        out = []
        for r in rows:
            r = dict(r); r["label"] = (r.pop("ntee") or "")[:3].upper(); r["ntee"] = None
            out.append(r)
        return out

    def score(self, rec, label):
        c = rec["code"] or ""
        return {"coarse": bool(c) and c[:1] == label[:1], "fine": c == label}


class FormD:
    name, key, per_request = "formd", "cik", FORMD_PER_REQUEST
    schema = FORMD_SCHEMA

    def system(self, tax):
        return formd_system()

    def candidates_sql(self, where_extra: str = "") -> str:
        return FORMD_CAND_SQL.format(where="NOT EXISTS (SELECT 1 FROM form_d_category c WHERE c.cik = o.cik) AND NOT EXISTS "
                                           "(SELECT 1 FROM category_batch_items b WHERE b.kind = 'formd' AND b.key = o.cik)" + where_extra,
                                     order=FORMD_ORDER)

    def item(self, row, tax, hide=False):
        return formd_text(row, hide), FORMD_PER_REQUEST

    def answers(self, rows, parsed, usage, err, tax):
        groups = FORMD_GROUPS
        cost = float(usage.get("cost") or 0.0)
        pt, ct = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        out = {r["cik"]: {"cik": r["cik"], "accession": r["accession"], "issuer_name": r["issuer_name"], "industry": r.get("industry"),
                          "fund_type_filed": r.get("fund_type"), "code": None, "g": None, "s": None, "f": None, "conf": None,
                          "cost": cost / len(rows), "pt": pt / len(rows), "ct": ct / len(rows), "attempts": 1, "error": err, "raw": None}
               for r in rows}
        got = {}
        if parsed and isinstance(parsed.get("r"), list):
            for item in parsed["r"]:
                if isinstance(item, dict) and isinstance(item.get("i"), int):
                    got[item["i"]] = item
        for n, r in enumerate(rows, 1):
            a = got.get(n)
            rec = out[r["cik"]]
            if a is None:
                rec["error"] = rec["error"] or "no answer"
                continue
            g, s, f = str(a.get("g") or "").strip(), str(a.get("s") or "").strip(), str(a.get("f") or "").strip().lower().replace(" ", "_")
            rec["raw"] = f"{g} / {s} / {f}"
            g = _match_name(g, groups.keys())
            s = _match_name(s, groups.get(g, [])) if g else None
            if g and s and f in FUND_TYPES:
                rec.update(g=g, s=s, f=f, code=f"{g}/{s}", conf=ntee._conf(a.get("p")), error=None)
            else:
                rec["error"] = "invalid: " + rec["raw"]
        return out

    def retry(self, rows, out, tax, sysp):
        for r in rows:
            rec = out[r["cik"]]
            if rec["code"] is not None or rec["error"] in ("refusal",):
                continue
            parsed, usage, err = ntee._post_anthropic(sysp, "[1]\n" + formd_text(r) + "\n\nUse the exact group, industry and fund type names from the list.", 80, FORMD_SCHEMA)
            one = self.answers([r], parsed, usage, err, tax)[r["cik"]]
            rec.update(attempts=2, cost=rec["cost"] + one["cost"], pt=rec["pt"] + one["pt"], ct=rec["ct"] + one["ct"],
                       code=one["code"], g=one["g"], s=one["s"], f=one["f"], conf=one["conf"], raw=one["raw"] or rec["raw"],
                       error=None if one["code"] else (err or "invalid after retry: " + str(one["raw"])))

    def rows_by_key(self, conn, keys):
        return {r["cik"]: dict(r) for r in conn.cursor(row_factory=ntee._dict_row).execute(
            FORMD_CAND_SQL.format(where="o.cik = ANY(%s)", order="o.cik"), (keys,)).fetchall()}

    def write(self, conn, recs, meta, batch_id):
        with conn.cursor() as cur:
            for r in recs:
                cur.execute("""INSERT INTO form_d_category (cik, accession, issuer_name, published_industry, published_fund_type, category,
                                 subcategory, fund_type, confidence, model, batch_id, prompt_tokens, completion_tokens, cost, attempts, error, raw)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (cik) DO UPDATE SET accession = EXCLUDED.accession, issuer_name = EXCLUDED.issuer_name,
                                 published_industry = EXCLUDED.published_industry, published_fund_type = EXCLUDED.published_fund_type,
                                 category = EXCLUDED.category, subcategory = EXCLUDED.subcategory, fund_type = EXCLUDED.fund_type,
                                 confidence = EXCLUDED.confidence, model = EXCLUDED.model, batch_id = EXCLUDED.batch_id,
                                 prompt_tokens = EXCLUDED.prompt_tokens, completion_tokens = EXCLUDED.completion_tokens, cost = EXCLUDED.cost,
                                 attempts = EXCLUDED.attempts, error = EXCLUDED.error, raw = EXCLUDED.raw, inferred_at = now()""",
                            (r["cik"], r["accession"], r["issuer_name"], r["industry"], r["fund_type_filed"], r["g"], r["s"], r["f"], r["conf"],
                             MODEL, batch_id, round(r["pt"]), round(r["ct"]), r["cost"], r["attempts"], r["error"], r["raw"]))
        conn.commit()

    def test_rows(self, conn, n):
        rows = conn.cursor(row_factory=ntee._dict_row).execute(FORMD_CAND_SQL.format(
            where="o.industry NOT IN ('Pooled Investment Fund', 'Other') AND o.cik IN (SELECT cik FROM sec_formd_offerings WHERE industry NOT IN ('Pooled Investment Fund', 'Other') ORDER BY md5(cik || 'cat') LIMIT %s)",
            order="o.cik"), (n,)).fetchall()
        out = []
        for r in rows:
            r = dict(r); r["label"] = r["industry"]; r["industry"] = None; r["fund_type"] = None
            out.append(r)
        return out

    def score(self, rec, label):
        group = next((g for g, inds in FORMD_GROUPS.items() if label in inds), None)
        return {"coarse": rec["g"] == group, "fine": rec["s"] == label}


def _match_name(v: str, names) -> str | None:
    low = {n.lower(): n for n in names}
    v = (v or "").strip().lower().replace("&amp;", "&")
    if v in low:
        return low[v]
    v2 = v.replace(" and ", " & ")
    return low.get(v2) or low.get(v.replace(" & ", " and ")) or next((n for k, n in low.items() if k.startswith(v) and v), None)


KINDS = {"nonprofit": Nonprofit(), "formd": FormD()}


# --- tables and the ledger --------------------------------------------------------------------------

def ensure_tables(conn) -> None:
    ntee._ensure_tables(conn)
    conn.execute("ALTER TABLE ntee_inferred ADD COLUMN IF NOT EXISTS batch_id text")
    conn.execute("""CREATE TABLE IF NOT EXISTS category_ledger (
        batch_id text PRIMARY KEY, kind text NOT NULL, submitted timestamptz NOT NULL DEFAULT now(), ended timestamptz,
        status text NOT NULL DEFAULT 'sent', requests integer, items integer, est_dollars double precision,
        input_tokens bigint, cache_write_tokens bigint, cache_read_tokens bigint, output_tokens bigint,
        dollars double precision, running_total double precision, note text)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS category_batch_items (
        kind text NOT NULL, key text NOT NULL, batch_id text NOT NULL, custom_id text NOT NULL, pos smallint NOT NULL, meta jsonb,
        PRIMARY KEY (kind, key))""")
    conn.execute("CREATE INDEX IF NOT EXISTS category_batch_items_batch ON category_batch_items (batch_id, custom_id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS formd_taxonomy (group_name text NOT NULL, industry text NOT NULL, PRIMARY KEY (group_name, industry))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS form_d_category (
        cik text PRIMARY KEY, accession text, issuer_name text, published_industry text, published_fund_type text,
        category text, subcategory text, fund_type text, confidence real, model text, batch_id text,
        inferred_at timestamptz NOT NULL DEFAULT now(), prompt_tokens integer, completion_tokens integer, cost double precision,
        attempts smallint, error text, raw text)""")
    conn.execute("CREATE INDEX IF NOT EXISTS form_d_category_cat ON form_d_category (category, subcategory)")
    conn.execute("CREATE INDEX IF NOT EXISTS form_d_category_fund ON form_d_category (fund_type)")
    conn.execute("""CREATE TABLE IF NOT EXISTS category_tests (
        kind text NOT NULL, key text NOT NULL, label text, answer text, coarse boolean, fine boolean, confidence real,
        batch_id text, tested_at timestamptz NOT NULL DEFAULT now(), error text, PRIMARY KEY (kind, key))""")
    for g, inds in FORMD_GROUPS.items():
        for i in inds:
            conn.execute("INSERT INTO formd_taxonomy VALUES (%s, %s) ON CONFLICT DO NOTHING", (g, i))
    conn.commit()


def spent(conn) -> tuple[float, float]:
    """(dollars on ended batches, estimated dollars of batches still running)."""
    r = conn.execute("""SELECT coalesce(sum(dollars) FILTER (WHERE status = 'done'), 0),
                               coalesce(sum(est_dollars) FILTER (WHERE status = 'sent'), 0) FROM category_ledger""").fetchone()
    return float(r[0]), float(r[1])


def per_item_cost(conn, kind: str) -> float:
    r = conn.execute("""SELECT sum(dollars) / nullif(sum(items), 0) FROM category_ledger
                        WHERE kind = %s AND status = 'done' AND items > 0""", (kind,)).fetchone()
    return float(r[0]) if r and r[0] else DEFAULT_COST[kind]


def estimate() -> None:
    with db.connect() as conn:
        ensure_tables(conn)
        done, pend = spent(conn)
        n_np = conn.execute("SELECT count(*) FROM organizations o WHERE o.ntee IS NULL AND NOT EXISTS (SELECT 1 FROM ntee_inferred i WHERE i.ein = o.ein)").fetchone()[0]
        n_fd = conn.execute("SELECT count(DISTINCT cik) FROM sec_formd_offerings o WHERE NOT EXISTS (SELECT 1 FROM form_d_category c WHERE c.cik = o.cik)").fetchone()[0]
        c_np, c_fd = per_item_cost(conn, "nonprofit"), per_item_cost(conn, "formd")
        print(f"spent ${done:.2f} on ended batches, ${pend:.2f} estimated on running ones; hard stop ${HARD_STOP:.0f}, last submit day {LAST_SUBMIT}")
        print(f"nonprofits left: {n_np:,} at ${c_np * 1000:.4f} per 1,000 ({1 / c_np:,.0f} per dollar): ${n_np * c_np:,.2f}")
        print(f"Form D issuers left: {n_fd:,} at ${c_fd * 1000:.4f} per 1,000 ({1 / c_fd:,.0f} per dollar): ${n_fd * c_fd:,.2f}")
        print(f"batch prices (Claude Haiku 5.5, prompts under 100K tokens): input $0.05, output $0.25, cache write $0.0625, cache read $0.005 per million tokens")


# --- submit -----------------------------------------------------------------------------------------

def _batch_cost(usage: dict) -> float:
    return sum((usage.get(k) or 0) * v / 1e6 for k, v in BATCH_PRICE.items())


def submit(kind_name: str, wave: float, limit: int | None = None, test_rows: list | None = None, force: bool = False) -> list[str]:
    """Batches for one kind until the wave's estimated dollars are used (or the hard stop or the submit deadline is hit).
    With test_rows, those items go instead (labels hidden) and the batch is marked as a test."""
    import httpx
    kind = KINDS[kind_name]
    ids = []
    if dt.date.today() > LAST_SUBMIT and not force:
        print(f"no new batches after {LAST_SUBMIT} (the grant expires 2026-11-14); use --force to override")
        return ids
    with db.connect() as conn:
        ensure_tables(conn)
        tax = ntee.valid_codes(conn)
        sysp = kind.system(tax)
        unit = per_item_cost(conn, kind_name)
        done, pend = spent(conn)
        budget_left = HARD_STOP - done - pend
        wave_left = min(wave, budget_left)
        if wave_left <= 0:
            print(f"nothing submitted: ${done:.2f} spent + ${pend:.2f} running reaches the ${HARD_STOP:.0f} hard stop")
            return ids
        wconn = db.connect()
        try:
            reqs, items, groups = [], [], {}
            est = 0.0

            def flush_group(size):
                batch = groups.get(size)
                if not batch:
                    return
                cid = f"r{len(reqs)}"
                user = "\n\n".join(f"[{n}]\n{kind.item(r, tax, hide=bool(test_rows))[0]}" for n, r in enumerate(batch, 1))
                reqs.append({"custom_id": cid, "params": ntee.anthropic_body(sysp, user, 30 * len(batch) + 40)})
                reqs[-1]["params"]["output_config"] = {"format": {"type": "json_schema", "schema": kind.schema}}
                items.extend((kind_name, r[kind.key], cid, n, json.dumps({"filer": r.get("filer"), "label": r.get("label")})) for n, r in enumerate(batch))
                groups[size] = []

            def send():
                nonlocal est
                if not reqs:
                    return
                e = len(items) * unit
                r = httpx.post(ntee.ANTHROPIC_API + "/batches", timeout=600, headers=ntee.anthropic_headers(), json={"requests": reqs})
                if r.status_code != 200:
                    raise SystemExit(f"batch create failed: HTTP {r.status_code}")
                bid = r.json()["id"]
                with wconn.cursor() as c:
                    c.execute("INSERT INTO category_ledger (batch_id, kind, requests, items, est_dollars, note) VALUES (%s, %s, %s, %s, %s, %s)",
                              (bid, kind_name, len(reqs), len(items), e, "test" if test_rows else None))
                    db.copy_rows(c, "category_batch_items", ["kind", "key", "custom_id", "pos", "meta", "batch_id"], [(*i, bid) for i in items])
                wconn.commit()
                ids.append(bid)
                est += e
                print(f"{kind_name} batch {bid}: {len(reqs):,} requests, {len(items):,} items, about ${e:.2f}")
                reqs.clear(); items.clear()

            if test_rows:
                source = iter(test_rows)
            else:
                cur = conn.cursor(name="cat_cand", row_factory=ntee._dict_row)
                cur.itersize = 2000
                cur.execute(kind.candidates_sql() + (f" LIMIT {int(limit)}" if limit else ""))
                source = (dict(r) for r in cur)
            n_items = 0
            for row in source:
                _, size = kind.item(row, tax)
                groups.setdefault(size, []).append(row)
                n_items += 1
                if len(groups[size]) >= size:
                    flush_group(size)
                if len(reqs) >= BATCH_REQUESTS:
                    send()
                    if est + (BATCH_REQUESTS * 8 * unit) > wave_left:     # the next batch would pass the wave
                        break
            for size in list(groups):
                flush_group(size)
            send()
        finally:
            wconn.close()
    print(f"{kind_name}: {len(ids)} batches submitted, about ${est:.2f}; ${done:.2f} spent before, ${pend:.2f} running")
    return ids


# --- collect ----------------------------------------------------------------------------------------

def collect(workers: int = 8, poll: int = 120, once: bool = False) -> None:
    """Every batch still marked sent: when ended, read its answers, validate, retry invalid items through the Messages
    API, write them, and record tokens and dollars in the ledger."""
    import httpx
    with db.connect() as conn:
        ensure_tables(conn)
        tax = ntee.valid_codes(conn)
        last = time.time()
        while True:
            pending = conn.execute("SELECT batch_id, kind, note FROM category_ledger WHERE status = 'sent' ORDER BY submitted").fetchall()
            if not pending:
                break
            for bid, kind_name, note in pending:
                b = httpx.get(f"{ntee.ANTHROPIC_API}/batches/{bid}", timeout=60, headers=ntee.anthropic_headers()).json()
                if b.get("processing_status") != "ended":
                    continue
                _collect_one(conn, bid, kind_name, note == "test", b, tax, workers)
            if once:
                break
            if time.time() - last > 600:
                n = conn.execute("SELECT count(*) FROM category_ledger WHERE status = 'sent'").fetchone()[0]
                done, pend = spent(conn)
                print(f"collect: {n} batches still running; ${done:.2f} spent, ${pend:.2f} estimated running")
                last = time.time()
            if conn.execute("SELECT count(*) FROM category_ledger WHERE status = 'sent'").fetchone()[0]:
                time.sleep(poll)
        status()


def _collect_one(conn, bid: str, kind_name: str, is_test: bool, b: dict, tax: dict, workers: int) -> None:
    import httpx
    kind = KINDS[kind_name]
    sysp = kind.system(tax)
    members, meta = {}, {}
    for key, cid, pos, m in conn.execute("SELECT key, custom_id, pos, meta FROM category_batch_items WHERE batch_id = %s ORDER BY custom_id, pos", (bid,)).fetchall():
        members.setdefault(cid, []).append(key)
        meta[key] = m or {}
    rows = kind.rows_by_key(conn, list(meta))
    if is_test:
        for key, r in rows.items():
            if kind_name == "nonprofit":
                r["ntee"] = None
            else:
                r["industry"] = None; r["fund_type"] = None
    recs, tokens, dollars, seen = [], {k: 0 for k in BATCH_PRICE}, 0.0, set()
    with httpx.stream("GET", b["results_url"], timeout=900, headers=ntee.anthropic_headers()) as rr:
        for line in rr.iter_lines():
            if not line.strip():
                continue
            row = json.loads(line)
            cid = row.get("custom_id")
            keys = members.get(cid)
            if not keys:
                continue
            seen.add(cid)
            group = [rows[k] for k in keys if k in rows]
            if not group:
                continue
            res = row.get("result") or {}
            if res.get("type") == "succeeded":
                parsed, usage, err = ntee.anthropic_answer(res["message"])
                u = res["message"].get("usage") or {}
                for k in tokens:
                    tokens[k] += u.get(k) or 0
                usage["cost"] = _batch_cost(u)
            else:
                parsed, usage, err = None, {}, f"batch {res.get('type')}"
            out = kind.answers(group, parsed, usage, err, tax)
            dollars += float(usage.get("cost") or 0.0)
            recs.extend(out.values())
    for cid, keys in members.items():
        if cid not in seen:
            group = [rows[k] for k in keys if k in rows]
            if group:
                recs.extend(kind.answers(group, None, {}, "no result", tax).values())
    bad = [r for r in recs if r["code"] is None and r["error"] != "refusal"]
    if bad:
        by_key = {r[kind.key]: r for r in bad}

        def one(key):
            if key in rows:
                kind.retry([rows[key]], {key: by_key[key]}, tax, sysp)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, list(by_key)))
    retry_cost = sum(r["cost"] for r in recs) - dollars       # the retries went through the Messages API at full price
    dollars = sum(r["cost"] for r in recs)
    if is_test:
        with conn.cursor() as c:
            for r in recs:
                label = (meta.get(r[kind.key]) or {}).get("label")
                sc = kind.score(r, label or "")
                c.execute("""INSERT INTO category_tests (kind, key, label, answer, coarse, fine, confidence, batch_id, error)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (kind, key) DO UPDATE SET label = EXCLUDED.label,
                               answer = EXCLUDED.answer, coarse = EXCLUDED.coarse, fine = EXCLUDED.fine, confidence = EXCLUDED.confidence,
                               batch_id = EXCLUDED.batch_id, error = EXCLUDED.error, tested_at = now()""",
                          (kind_name, r[kind.key], label, r["code"], sc["coarse"], sc["fine"], r["conf"], bid, r["error"]))
    else:
        kind.write(conn, recs, meta, bid)
    with conn.cursor() as c:
        c.execute("DELETE FROM category_batch_items WHERE batch_id = %s", (bid,))
        c.execute("""UPDATE category_ledger SET status = 'done', ended = now(), input_tokens = %s, cache_write_tokens = %s, cache_read_tokens = %s,
                     output_tokens = %s, dollars = %s, note = coalesce(note || ' ', '') || %s WHERE batch_id = %s""",
                  (tokens["input_tokens"], tokens["cache_creation_input_tokens"], tokens["cache_read_input_tokens"], tokens["output_tokens"],
                   dollars, json.dumps(b.get("request_counts") or {}), bid))
        c.execute("""UPDATE category_ledger l SET running_total = s.t FROM (SELECT batch_id, sum(dollars) OVER (ORDER BY ended) AS t
                     FROM category_ledger WHERE status = 'done') s WHERE s.batch_id = l.batch_id""")
    conn.commit()
    coded = sum(1 for r in recs if r["code"])
    print(f"{kind_name} batch {bid}{' (test)' if is_test else ''}: {len(recs):,} items, {coded:,} coded, {len(bad):,} retried, "
          f"${dollars:.3f} (retries ${retry_cost:.3f}); tokens in {tokens['input_tokens']:,} cached {tokens['cache_read_input_tokens']:,} "
          f"written {tokens['cache_creation_input_tokens']:,} out {tokens['output_tokens']:,}")
    if is_test:
        report_test(conn, kind_name)


def report_test(conn, kind_name: str) -> None:
    for label, cond in (("all", "true"), ("with 990 text", "key IN (SELECT ein FROM organizations WHERE latest_filing_year IS NOT NULL)") if kind_name == "nonprofit" else ("all", "true"),
                        ("BMF record only", "key IN (SELECT ein FROM organizations WHERE latest_filing_year IS NULL)") if kind_name == "nonprofit" else ("all", "true")):
        r = conn.execute(f"""SELECT count(*), count(answer), count(*) FILTER (WHERE coarse), count(*) FILTER (WHERE fine), avg(confidence)
                             FROM category_tests WHERE kind = %s AND {cond}""", (kind_name,)).fetchone()
        if r[0]:
            print(f"test {kind_name} {label}: {r[0]} items, {r[1]} answered; {'major group' if kind_name == 'nonprofit' else 'industry group'} match "
                  f"{r[2]}/{r[0]} ({r[2] / r[0] * 100:.1f}%), {'3-character code' if kind_name == 'nonprofit' else 'industry'} match {r[3]}/{r[0]} "
                  f"({r[3] / r[0] * 100:.1f}%); mean confidence {r[4] or 0:.2f}")
        if kind_name != "nonprofit":
            break


def test(kind_name: str, n: int) -> None:
    kind = KINDS[kind_name]
    with db.connect() as conn:
        ensure_tables(conn)
        conn.execute("DELETE FROM category_tests WHERE kind = %s", (kind_name,)); conn.commit()
        rows = kind.test_rows(conn, n)
    print(f"test {kind_name}: {len(rows)} items with published labels, hidden; sending as a batch")
    submit(kind_name, wave=1.0, test_rows=rows)


def status() -> None:
    with db.connect() as conn:
        ensure_tables(conn)
        done, pend = spent(conn)
        print(f"ledger: ${done:.2f} spent on ended batches, ${pend:.2f} estimated on running ones, hard stop ${HARD_STOP:.0f}")
        for r in conn.execute("""SELECT kind, status, count(*), coalesce(sum(items), 0), coalesce(sum(dollars), 0), coalesce(sum(est_dollars), 0)
                                 FROM category_ledger GROUP BY 1, 2 ORDER BY 1, 2""").fetchall():
            print(f"  {r[0]:10} {r[1]:5} {r[2]:3} batches {int(r[3]):10,} items ${r[4]:.2f} (est ${r[5]:.2f})")
        np_ = conn.execute("SELECT count(*), count(ntee_code) FROM ntee_inferred").fetchone()
        fd = conn.execute("SELECT count(*), count(category) FROM form_d_category").fetchone()
        left_np = conn.execute("SELECT count(*) FROM organizations o WHERE o.ntee IS NULL AND NOT EXISTS (SELECT 1 FROM ntee_inferred i WHERE i.ein = o.ein)").fetchone()[0]
        left_fd = conn.execute("SELECT count(DISTINCT cik) FROM sec_formd_offerings o WHERE NOT EXISTS (SELECT 1 FROM form_d_category c WHERE c.cik = o.cik)").fetchone()[0]
        print(f"nonprofits: {np_[0]:,} inferred ({np_[1]:,} coded), {left_np:,} left; Form D issuers: {fd[0]:,} categorized ({fd[1]:,} coded), {left_fd:,} left")
        last = conn.execute("SELECT batch_id, kind, status, items, dollars, ended FROM category_ledger ORDER BY submitted DESC LIMIT 5").fetchall()
        for r in last:
            print("  ", r)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["estimate", "test", "submit", "collect", "status", "build"])
    ap.add_argument("kind", nargs="?", choices=list(KINDS))
    ap.add_argument("n", nargs="?", type=int)
    ap.add_argument("--wave", type=float, default=25.0, help="dollars (estimated) per submit run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--once", action="store_true", help="collect: one pass, no waiting")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.command == "estimate":
        estimate()
    elif a.command == "test":
        test(a.kind or "nonprofit", a.n or 200)
    elif a.command == "submit":
        if not a.kind:
            sys.exit("submit needs a kind: nonprofit or formd")
        submit(a.kind, a.wave, a.limit, force=a.force)
    elif a.command == "collect":
        collect(a.workers, once=a.once)
    elif a.command == "status":
        status()
    elif a.command == "build":
        ntee.build()


if __name__ == "__main__":
    main()
