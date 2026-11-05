"""The categorization helper (owner, 2026-11-05): a command-line program that sends nonprofits and Form D issuers to
Anthropic's Message Batches API (Claude Haiku 5.5, half price, the taxonomy in a cached system prompt), validates
the answers against the taxonomies, retries invalid ones once, writes the results, and keeps a spend ledger.
Everything the model does goes through this program with CATEGORIZE_API_KEY from the environment (the key the owner
set aside for this work on 2026-11-05; ANTHROPIC_API_KEY is the fallback); the key is never printed, logged or stored.

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
           .venv/bin/python -m loader.categorize threshold nonprofit|formd     pass 2: the confidence distribution and cutoffs
           .venv/bin/python -m loader.categorize submit nonprofit --pass 2 --threshold 0.5 --wave 25   the Sonnet pass
           .venv/bin/python -m loader.categorize pass2-report                  re-guessed, changed, gained, flagged
Passes (owner's addendum, 2026-11-05): every pass is a row in category_history (kind, key, pass_number, model, code,
confidence, batch id); the main tables keep the current best (a later pass replaces the code only with higher
confidence; passes and flagged say how many passes an item had and whether they disagreed). Pass 2 sends items below
a confidence cutoff to MODEL2 (the Sonnet tier) with fuller context: the longer program text, Schedule O, officers,
grantees (nonprofits), more related persons and sibling offerings (Form D), and the first pass's guess.
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

import psycopg
from concurrent.futures import ThreadPoolExecutor

from loader import db, ntee

HARD_STOP = float(os.environ.get("CATEGORIZE_HARD_STOP", "180"))
LAST_SUBMIT = dt.date(2026, 11, 12)
MODEL = ntee.ANTHROPIC_MODEL                                  # pass 1: Claude Haiku 5.5
MODEL2 = os.environ.get("CATEGORIZE_MODEL2", "claude-sonnet-5-5")   # pass 2 (owner's addendum): the Sonnet tier
PASS_MODEL = {1: MODEL, 2: MODEL2}
BATCH_REQUESTS = 4000
FORMD_PER_REQUEST = 10
PASS2_SIZES = {"text": 3, "plain": 10, "formd": 8}           # items per request in pass 2 (fuller context per item)
PASS2_PROGRAM_CHARS, PASS2_SCHED_O_CHARS = 2500, 600
# Owner, 2026-11-05: the stronger model may say a record is too sparse to code at all (a stub filing, a bare name); such
# items keep their first-pass code, are marked sparse, and are left out of any later pass.
PASS2_NOTE = ("\n\nSecond pass: these items were coded by a smaller model with low confidence, and you see more of the record. "
              "If the record is too sparse to code at all (a stub filing, a name with nothing else, no activity visible), "
              "answer SPARSE in place of the code (the group field for Form D) with confidence 0, and it will be left alone.")
DEFAULT_COST = {"nonprofit": 0.00003, "formd": 0.00003}      # dollars per item before a batch has been measured
DEFAULT_COST2 = {"nonprofit": 0.0012, "formd": 0.0008}       # pass 2 (Sonnet 5.5 batch: $1 in, $5 out, $0.05 cache read per M)


def batch_prices(model: str) -> dict:
    """Batch prices (half of list) per million tokens for a model."""
    return {k: v / 2 for k, v in ntee.PRICES[model].items()}


BATCH_PRICE = batch_prices(MODEL)

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
    tokens_per_item = 30          # {"i":1,"c":"B82","p":0.8} is about 20 tokens

    def system(self, tax):
        return ntee.system_prompt(tax["majors"], tax["codes"])

    def candidates_sql(self, where_extra: str = "") -> str:
        return ntee.CAND_SQL.format(where=ntee._cand_where(False).replace("ntee_batch_eins b", "category_batch_items b")
                                    .replace("b.ein = o.ein", "b.kind = 'nonprofit' AND b.key = o.ein") + where_extra, order=ntee.CAND_ORDER)

    def item(self, row, tax, hide=False, pass_number=1):
        text, has = ntee.org_text(row, tax["acts"])
        if pass_number == 1:
            return text, (ntee.BATCH_TEXT if has else ntee.BATCH_PLAIN)
        return self.extra(row, text), (PASS2_SIZES["text"] if has else PASS2_SIZES["plain"])

    def extra(self, row, text):
        """Pass 2: what the first pass did not see: the fuller program text, Schedule O, officers, grantees, and the
        first pass's own guess."""
        lines = [text]
        prog = (row.get("program_text") or "").strip()
        if prog and len(prog) > ntee.PROGRAM_CHARS:
            lines.append("Program services, fuller: " + ntee._clip(prog, PASS2_PROGRAM_CHARS))
        so = (row.get("schedule_o_text") or "").strip()
        if so:
            lines.append("Schedule O: " + ntee._clip(so, PASS2_SCHED_O_CHARS))
        if row.get("officers"):
            lines.append("Officers and directors: " + "; ".join(row["officers"][:8]))
        if row.get("grantees"):
            lines.append("Grants made to: " + "; ".join(row["grantees"][:6]))
        if row.get("prior_code"):
            lines.append(f"A first pass by a smaller model guessed {row['prior_code']} ({ntee.valid_codes.__globals__['_tax_cache'].get('codes', {}).get(row['prior_code'], '')}) "
                         f"with confidence {row['prior_conf'] if row.get('prior_conf') is not None else 'unknown'}; judge for yourself.")
        return "\n".join(lines)

    def pass2_sql(self, threshold: float) -> str:
        return ntee.CAND_SQL.format(
            where=f"""o.ein IN (SELECT i.ein FROM ntee_inferred i WHERE i.pass_number = 1 AND NOT i.sparse AND (i.confidence < {float(threshold)} OR i.ntee_code IS NULL)
                      AND NOT EXISTS (SELECT 1 FROM category_history h WHERE h.kind = 'nonprofit' AND h.key = i.ein AND h.pass_number = 2))
                      AND NOT EXISTS (SELECT 1 FROM category_batch_items b WHERE b.kind = 'nonprofit' AND b.key = o.ein)""",
            order=ntee.CAND_ORDER)

    def enrich(self, conn, rows):
        """Officers, grantees and the first-pass guess for pass-2 rows."""
        eins = [r["ein"] for r in rows]
        off, gr, prior = {}, {}, {}
        for ein, names in conn.execute("""SELECT ein, array_agg(name_raw || ' (' || coalesce(title, '') || ')' ORDER BY comp_org DESC NULLS LAST)
                                           FROM (SELECT DISTINCT ON (ein, name_norm) ein, name_raw, title, comp_org FROM people
                                                 WHERE ein = ANY(%s) AND NOT is_duplicate ORDER BY ein, name_norm, tax_year DESC) x GROUP BY ein""", (eins,)).fetchall():
            off[ein] = names
        for ein, names in conn.execute("""SELECT ein, array_agg(recipient_name || coalesce(': ' || left(purpose, 60), '') ORDER BY cash_amount DESC NULLS LAST)
                                           FROM (SELECT DISTINCT ON (ein, recipient_name_norm) ein, recipient_name, purpose, cash_amount FROM grants
                                                 WHERE ein = ANY(%s) AND NOT recipient_is_person ORDER BY ein, recipient_name_norm, cash_amount DESC NULLS LAST) x GROUP BY ein""", (eins,)).fetchall():
            gr[ein] = names
        for ein, code, conf in conn.execute("SELECT ein, ntee_code, confidence FROM ntee_inferred WHERE ein = ANY(%s)", (eins,)).fetchall():
            prior[ein] = (code, conf)
        for r in rows:
            r["officers"], r["grantees"] = off.get(r["ein"]), gr.get(r["ein"])
            r["prior_code"], r["prior_conf"] = prior.get(r["ein"], (None, None))

    def answers(self, rows, parsed, usage, err, tax):
        out = ntee.answers(rows, parsed, usage, err, tax)
        for rec in out.values():
            rec["sparse"] = (rec.get("raw") or "").upper() == "SPARSE"
            if rec["sparse"]:
                rec["error"] = "sparse"
        return out

    def retry(self, rows, out, tax, sysp, model=None):
        ntee.retry_invalid([r for r in rows if not out[r["ein"]].get("sparse")], out, tax, sysp, model)

    def rows_by_key(self, conn, keys, pass_number=1):
        rows = {r["ein"]: dict(r) for r in conn.cursor(row_factory=ntee._dict_row).execute(
            ntee.CAND_SQL.format(where="o.ein = ANY(%s)", order="o.ein"), (keys,)).fetchall()}
        if pass_number == 2:
            self.enrich(conn, list(rows.values()))
        return rows

    def write(self, conn, recs, meta, batch_id, pass_number=1):
        model = PASS_MODEL[pass_number]
        with conn.cursor() as cur:
            for r in recs:
                cur.execute("""INSERT INTO category_history (kind, key, pass_number, model, code, confidence, batch_id, error)
                               VALUES ('nonprofit', %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (kind, key, pass_number) DO UPDATE SET
                                 model = EXCLUDED.model, code = EXCLUDED.code, confidence = EXCLUDED.confidence, batch_id = EXCLUDED.batch_id,
                                 error = EXCLUDED.error, created = now()""", (r["ein"], pass_number, model, r["code"], r["conf"], batch_id, r["error"]))
                # The main row: pass 1 writes it; pass 2 replaces the code only with higher confidence, and flags a disagreement.
                cur.execute("""INSERT INTO ntee_inferred (ein, ntee_code, confidence, model, prompt_tokens, completion_tokens, cost,
                               attempts, error, raw, filer, batch_id, pass_number, passes, flagged, sparse)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s)
                               ON CONFLICT (ein) DO UPDATE SET
                                 sparse = ntee_inferred.sparse OR EXCLUDED.sparse,
                                 ntee_code = CASE WHEN %(better)s THEN EXCLUDED.ntee_code ELSE ntee_inferred.ntee_code END,
                                 confidence = CASE WHEN %(better)s THEN EXCLUDED.confidence ELSE ntee_inferred.confidence END,
                                 model = CASE WHEN %(better)s THEN EXCLUDED.model ELSE ntee_inferred.model END,
                                 batch_id = CASE WHEN %(better)s THEN EXCLUDED.batch_id ELSE ntee_inferred.batch_id END,
                                 pass_number = CASE WHEN %(better)s THEN EXCLUDED.pass_number ELSE ntee_inferred.pass_number END,
                                 inferred_at = CASE WHEN %(better)s THEN now() ELSE ntee_inferred.inferred_at END,
                                 raw = CASE WHEN %(better)s THEN EXCLUDED.raw ELSE ntee_inferred.raw END,
                                 error = CASE WHEN %(better)s THEN EXCLUDED.error ELSE ntee_inferred.error END,
                                 cost = coalesce(ntee_inferred.cost, 0) + coalesce(EXCLUDED.cost, 0),
                                 prompt_tokens = coalesce(ntee_inferred.prompt_tokens, 0) + coalesce(EXCLUDED.prompt_tokens, 0),
                                 completion_tokens = coalesce(ntee_inferred.completion_tokens, 0) + coalesce(EXCLUDED.completion_tokens, 0),
                                 passes = greatest(coalesce(ntee_inferred.passes, 1), EXCLUDED.passes),
                                 flagged = ntee_inferred.flagged OR (EXCLUDED.ntee_code IS NOT NULL AND ntee_inferred.ntee_code IS NOT NULL
                                                                     AND EXCLUDED.ntee_code <> ntee_inferred.ntee_code)""".replace(
                                "%(better)s", "(EXCLUDED.ntee_code IS NOT NULL AND (ntee_inferred.ntee_code IS NULL OR coalesce(EXCLUDED.confidence, 0) > coalesce(ntee_inferred.confidence, 0)))"),
                            (r["ein"], r["code"], r["conf"], model, round(r["pt"]), round(r["ct"]), r["cost"], r["attempts"], r["error"],
                             r["raw"], (meta.get(r["ein"]) or {}).get("filer"), batch_id, pass_number, pass_number, bool(r.get("sparse"))))
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
    tokens_per_item = 60          # the group, industry and fund type names run to 35 tokens an item

    def system(self, tax):
        return formd_system()

    def candidates_sql(self, where_extra: str = "") -> str:
        return FORMD_CAND_SQL.format(where="NOT EXISTS (SELECT 1 FROM form_d_category c WHERE c.cik = o.cik) AND NOT EXISTS "
                                           "(SELECT 1 FROM category_batch_items b WHERE b.kind = 'formd' AND b.key = o.cik)" + where_extra,
                                     order=FORMD_ORDER)

    def item(self, row, tax, hide=False, pass_number=1):
        text = formd_text(row, hide)
        if pass_number == 2:
            if row.get("persons") and len(row["persons"]) > 8:
                text += "\nMore related persons: " + "; ".join(row["persons"][8:20])
            if row.get("siblings"):
                text += "\nOther offerings by the same issuer: " + "; ".join(row["siblings"][:6])
            if row.get("prior"):
                text += f"\nA first pass by a smaller model guessed {row['prior']}; judge for yourself."
            return text, PASS2_SIZES["formd"]
        return text, FORMD_PER_REQUEST

    def pass2_sql(self, threshold: float) -> str:
        return FORMD_CAND_SQL.format(
            where=f"""o.cik IN (SELECT c.cik FROM form_d_category c WHERE c.pass_number = 1 AND NOT c.sparse AND (c.confidence < {float(threshold)} OR c.category IS NULL)
                      AND NOT EXISTS (SELECT 1 FROM category_history h WHERE h.kind = 'formd' AND h.key = c.cik AND h.pass_number = 2))
                      AND NOT EXISTS (SELECT 1 FROM category_batch_items b WHERE b.kind = 'formd' AND b.key = o.cik)""",
            order=FORMD_ORDER)

    def enrich(self, conn, rows):
        ciks = [r["cik"] for r in rows]
        sib, prior = {}, {}
        for cik, names in conn.execute("""SELECT cik, array_agg(DISTINCT issuer_name) FROM sec_formd WHERE cik = ANY(%s) GROUP BY cik""", (ciks,)).fetchall():
            sib[cik] = names
        for cik, g, sc, f, conf in conn.execute("SELECT cik, category, subcategory, fund_type, confidence FROM form_d_category WHERE cik = ANY(%s)", (ciks,)).fetchall():
            prior[cik] = f"{g} / {sc} / {f} with confidence {conf}" if g else None
        for r in rows:
            r["siblings"] = [n for n in (sib.get(r["cik"]) or []) if n != r["issuer_name"]]
            r["prior"] = prior.get(r["cik"])

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
            if g.upper() == "SPARSE":
                rec["sparse"], rec["error"] = True, "sparse"
                continue
            g = _match_name(g, groups.keys())
            s = _match_name(s, groups.get(g, [])) if g else None
            if g and s and f in FUND_TYPES:
                rec.update(g=g, s=s, f=f, code=f"{g}/{s}", conf=ntee._conf(a.get("p")), error=None)
            else:
                rec["error"] = "invalid: " + rec["raw"]
        return out

    def retry(self, rows, out, tax, sysp, model=None):
        for r in rows:
            rec = out[r["cik"]]
            if rec["code"] is not None or rec["error"] in ntee.NO_RETRY:
                continue
            parsed, usage, err = ntee._post_anthropic(sysp, "[1]\n" + formd_text(r) + "\n\nUse the exact group, industry and fund type names from the list.", 80, FORMD_SCHEMA, model)
            one = self.answers([r], parsed, usage, err, tax)[r["cik"]]
            rec.update(attempts=2, cost=rec["cost"] + one["cost"], pt=rec["pt"] + one["pt"], ct=rec["ct"] + one["ct"],
                       code=one["code"], g=one["g"], s=one["s"], f=one["f"], conf=one["conf"], raw=one["raw"] or rec["raw"],
                       error=None if one["code"] else (err or "invalid after retry: " + str(one["raw"])))

    def rows_by_key(self, conn, keys, pass_number=1):
        rows = {r["cik"]: dict(r) for r in conn.cursor(row_factory=ntee._dict_row).execute(
            FORMD_CAND_SQL.format(where="o.cik = ANY(%s)", order="o.cik"), (keys,)).fetchall()}
        if pass_number == 2:
            self.enrich(conn, list(rows.values()))
        return rows

    def write(self, conn, recs, meta, batch_id, pass_number=1):
        model = PASS_MODEL[pass_number]
        better = "(EXCLUDED.category IS NOT NULL AND (form_d_category.category IS NULL OR coalesce(EXCLUDED.confidence, 0) > coalesce(form_d_category.confidence, 0)))"
        with conn.cursor() as cur:
            for r in recs:
                cur.execute("""INSERT INTO category_history (kind, key, pass_number, model, code, category, subcategory, fund_type, confidence, batch_id, error)
                               VALUES ('formd', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (kind, key, pass_number) DO UPDATE SET
                                 model = EXCLUDED.model, code = EXCLUDED.code, category = EXCLUDED.category, subcategory = EXCLUDED.subcategory,
                                 fund_type = EXCLUDED.fund_type, confidence = EXCLUDED.confidence, batch_id = EXCLUDED.batch_id, error = EXCLUDED.error, created = now()""",
                            (r["cik"], pass_number, model, r["code"], r["g"], r["s"], r["f"], r["conf"], batch_id, r["error"]))
                cur.execute(f"""INSERT INTO form_d_category (cik, accession, issuer_name, published_industry, published_fund_type, category,
                                 subcategory, fund_type, confidence, model, batch_id, prompt_tokens, completion_tokens, cost, attempts, error, raw,
                                 pass_number, passes, flagged, sparse)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s)
                               ON CONFLICT (cik) DO UPDATE SET accession = EXCLUDED.accession, issuer_name = EXCLUDED.issuer_name,
                                 sparse = form_d_category.sparse OR EXCLUDED.sparse,
                                 published_industry = EXCLUDED.published_industry, published_fund_type = EXCLUDED.published_fund_type,
                                 category = CASE WHEN {better} THEN EXCLUDED.category ELSE form_d_category.category END,
                                 subcategory = CASE WHEN {better} THEN EXCLUDED.subcategory ELSE form_d_category.subcategory END,
                                 fund_type = CASE WHEN {better} THEN EXCLUDED.fund_type ELSE form_d_category.fund_type END,
                                 confidence = CASE WHEN {better} THEN EXCLUDED.confidence ELSE form_d_category.confidence END,
                                 model = CASE WHEN {better} THEN EXCLUDED.model ELSE form_d_category.model END,
                                 batch_id = CASE WHEN {better} THEN EXCLUDED.batch_id ELSE form_d_category.batch_id END,
                                 pass_number = CASE WHEN {better} THEN EXCLUDED.pass_number ELSE form_d_category.pass_number END,
                                 inferred_at = CASE WHEN {better} THEN now() ELSE form_d_category.inferred_at END,
                                 raw = CASE WHEN {better} THEN EXCLUDED.raw ELSE form_d_category.raw END,
                                 error = CASE WHEN {better} THEN EXCLUDED.error ELSE form_d_category.error END,
                                 cost = coalesce(form_d_category.cost, 0) + coalesce(EXCLUDED.cost, 0),
                                 prompt_tokens = coalesce(form_d_category.prompt_tokens, 0) + coalesce(EXCLUDED.prompt_tokens, 0),
                                 completion_tokens = coalesce(form_d_category.completion_tokens, 0) + coalesce(EXCLUDED.completion_tokens, 0),
                                 attempts = EXCLUDED.attempts, passes = greatest(coalesce(form_d_category.passes, 1), EXCLUDED.passes),
                                 flagged = form_d_category.flagged OR (EXCLUDED.category IS NOT NULL AND form_d_category.category IS NOT NULL
                                           AND (EXCLUDED.category <> form_d_category.category OR EXCLUDED.subcategory <> form_d_category.subcategory
                                                OR EXCLUDED.fund_type <> form_d_category.fund_type))""",
                            (r["cik"], r["accession"], r["issuer_name"], r["industry"], r["fund_type_filed"], r["g"], r["s"], r["f"], r["conf"],
                             model, batch_id, round(r["pt"]), round(r["ct"]), r["cost"], r["attempts"], r["error"], r["raw"], pass_number, pass_number,
                             bool(r.get("sparse"))))
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

def _add_column(conn, table: str, ddl: str) -> None:
    """ALTER TABLE ... ADD COLUMN IF NOT EXISTS takes an exclusive lock even when the column exists; on 2026-11-05 a
    status check doing that deadlocked the collector mid-write, so add a column only when it is really missing."""
    col = ddl.split()[0]
    if not conn.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, col)).fetchone():
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {ddl}")


def ensure_tables(conn) -> None:
    ntee._ensure_tables(conn)
    _add_column(conn, "ntee_inferred", "batch_id text")
    _add_column(conn, "ntee_inferred", "pass_number smallint NOT NULL DEFAULT 1")
    _add_column(conn, "ntee_inferred", "passes smallint NOT NULL DEFAULT 1")
    _add_column(conn, "ntee_inferred", "flagged boolean NOT NULL DEFAULT false")
    _add_column(conn, "ntee_inferred", "sparse boolean NOT NULL DEFAULT false")
    conn.execute("""CREATE TABLE IF NOT EXISTS category_history (
        kind text NOT NULL, key text NOT NULL, pass_number smallint NOT NULL, model text, code text, category text, subcategory text,
        fund_type text, confidence real, batch_id text, error text, created timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (kind, key, pass_number))""")
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
        attempts smallint, error text, raw text, pass_number smallint NOT NULL DEFAULT 1, passes smallint NOT NULL DEFAULT 1,
        flagged boolean NOT NULL DEFAULT false)""")
    _add_column(conn, "form_d_category", "pass_number smallint NOT NULL DEFAULT 1")
    _add_column(conn, "form_d_category", "passes smallint NOT NULL DEFAULT 1")
    _add_column(conn, "form_d_category", "flagged boolean NOT NULL DEFAULT false")
    _add_column(conn, "form_d_category", "sparse boolean NOT NULL DEFAULT false")
    _add_column(conn, "category_ledger", "pass_number smallint NOT NULL DEFAULT 1")
    _add_column(conn, "category_ledger", "model text")
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


def per_item_cost(conn, kind: str, pass_number: int = 1) -> float:
    r = conn.execute("""SELECT sum(dollars) / nullif(sum(items), 0) FROM category_ledger
                        WHERE kind = %s AND pass_number = %s AND status = 'done' AND items > 0 AND coalesce(note, '') NOT LIKE 'test%%'""",
                     (kind, pass_number)).fetchone()
    return float(r[0]) if r and r[0] else (DEFAULT_COST if pass_number == 1 else DEFAULT_COST2)[kind]


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


def submit(kind_name: str, wave: float, limit: int | None = None, test_rows: list | None = None, force: bool = False,
           pass_number: int = 1, threshold: float | None = None) -> list[str]:
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
        sysp = kind.system(tax) + (PASS2_NOTE if pass_number == 2 else "")
        model = PASS_MODEL[pass_number]
        unit = per_item_cost(conn, kind_name, pass_number)
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
                user = "\n\n".join(f"[{n}]\n{kind.item(r, tax, hide=bool(test_rows), pass_number=pass_number)[0]}" for n, r in enumerate(batch, 1))
                reqs.append({"custom_id": cid, "params": ntee.anthropic_body(sysp, user, kind.tokens_per_item * len(batch) + 60, None, model)})
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
                    c.execute("INSERT INTO category_ledger (batch_id, kind, requests, items, est_dollars, note, pass_number, model) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                              (bid, kind_name, len(reqs), len(items), e, "test" if test_rows else None, pass_number, model))
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
                sql = kind.candidates_sql() if pass_number == 1 else kind.pass2_sql(threshold if threshold is not None else 0.5)
                cur.execute(sql + (f" LIMIT {int(limit)}" if limit else ""))
                source = (dict(r) for r in cur)
            if pass_number == 2 and not test_rows:
                source = _enriched(conn, kind, source)
            n_items = 0
            for row in source:
                _, size = kind.item(row, tax, pass_number=pass_number)
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
    print(f"{kind_name} pass {pass_number} ({model}): {len(ids)} batches submitted, about ${est:.2f}; ${done:.2f} spent before, ${pend:.2f} running")
    return ids


def _enriched(conn, kind, source, chunk: int = 500):
    """Pass-2 rows in chunks with their extra context (officers, grantees, prior guess) filled in."""
    buf = []
    for row in source:
        buf.append(row)
        if len(buf) >= chunk:
            kind.enrich(conn, buf)
            yield from buf
            buf = []
    if buf:
        kind.enrich(conn, buf)
        yield from buf


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
            pending = conn.execute("SELECT batch_id, kind, note, pass_number FROM category_ledger WHERE status = 'sent' ORDER BY submitted").fetchall()
            if not pending:
                break
            for bid, kind_name, note, pass_number in pending:
                b = httpx.get(f"{ntee.ANTHROPIC_API}/batches/{bid}", timeout=60, headers=ntee.anthropic_headers()).json()
                if b.get("processing_status") != "ended":
                    continue
                try:
                    _collect_one(conn, bid, kind_name, note == "test", b, tax, workers, pass_number or 1)
                except psycopg.errors.DeadlockDetected as e:        # another session took a lock on our tables
                    conn.rollback()
                    print(f"collect: {bid} hit a deadlock ({str(e).splitlines()[0]}); retrying it in 60s")
                    time.sleep(60)
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


def _collect_one(conn, bid: str, kind_name: str, is_test: bool, b: dict, tax: dict, workers: int, pass_number: int = 1) -> None:
    import httpx
    kind = KINDS[kind_name]
    sysp = kind.system(tax) + (PASS2_NOTE if pass_number == 2 else "")
    model = PASS_MODEL[pass_number]
    prices = batch_prices(model)
    members, meta = {}, {}
    for key, cid, pos, m in conn.execute("SELECT key, custom_id, pos, meta FROM category_batch_items WHERE batch_id = %s ORDER BY custom_id, pos", (bid,)).fetchall():
        members.setdefault(cid, []).append(key)
        meta[key] = m or {}
    rows = kind.rows_by_key(conn, list(meta), pass_number)
    if is_test:
        for key, r in rows.items():
            if kind_name == "nonprofit":
                r["ntee"] = None
            else:
                r["industry"] = None; r["fund_type"] = None
    recs, tokens, dollars, seen = [], {k: 0 for k in prices}, 0.0, set()
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
                usage["cost"] = sum((u.get(k) or 0) * v / 1e6 for k, v in prices.items())
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
    bad = [r for r in recs if r["code"] is None and r["error"] not in ("refusal", "sparse")]
    if bad:
        by_key = {r[kind.key]: r for r in bad}

        def one(key):
            if key in rows:
                kind.retry([rows[key]], {key: by_key[key]}, tax, sysp, model)
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
        kind.write(conn, recs, meta, bid, pass_number)
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
    print(f"{kind_name} pass {pass_number} batch {bid}{' (test)' if is_test else ''}: {len(recs):,} items, {coded:,} coded, {len(bad):,} retried, "
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


def threshold_report(kind_name: str) -> None:
    """The first-pass confidence distribution, the hidden-label test's match rate by confidence, and what each cutoff
    would send to pass 2 (the owner picks the cutoff; roughly the bottom 10 to 20 percent)."""
    table, col = ("ntee_inferred", "ntee_code") if kind_name == "nonprofit" else ("form_d_category", "category")
    with db.connect() as conn:
        conn.execute("SET statement_timeout = '600s'")
        n, null = conn.execute(f"SELECT count(*), count(*) FILTER (WHERE {col} IS NULL) FROM {table} WHERE pass_number = 1").fetchone()
        print(f"{kind_name}: {n:,} first-pass items, {null:,} with no code (always sent to pass 2)")
        print("confidence  items  share  cumulative")
        cum = 0
        for lo, cnt in conn.execute(f"""SELECT floor(coalesce(confidence, 0) * 10) / 10 AS b, count(*) FROM {table} WHERE pass_number = 1 AND {col} IS NOT NULL
                                        GROUP BY 1 ORDER BY 1""").fetchall():
            cum += cnt
            print(f"  < {float(lo) + 0.1:.1f}    {cnt:9,}  {cnt / n * 100:5.1f}%  {cum / n * 100:5.1f}%")
        rows = conn.execute("""SELECT floor(coalesce(confidence, 0) * 10) / 10 AS b, count(*), count(*) FILTER (WHERE coarse), count(*) FILTER (WHERE fine)
                               FROM category_tests WHERE kind = %s GROUP BY 1 ORDER BY 1""", (kind_name,)).fetchall()
        if rows:
            print("hidden-label test by confidence: bucket, items, coarse match, fine match")
            for b, c, co, fi in rows:
                print(f"  < {float(b) + 0.1:.1f}    {c:5}  {co / c * 100:5.1f}%  {fi / c * 100:5.1f}%")
        unit = per_item_cost(conn, kind_name, 2)
        for cut in (0.4, 0.5, 0.6, 0.7):
            k = conn.execute(f"SELECT count(*) FROM {table} WHERE pass_number = 1 AND ({col} IS NULL OR confidence < %s)", (cut,)).fetchone()[0]
            print(f"cutoff {cut}: {k:,} items ({k / n * 100:.1f}%), about ${k * unit:,.2f} with {MODEL2} ({1 / unit:,.0f} per dollar)")


def pass2_report() -> None:
    with db.connect() as conn:
        for kind_name, table, col in (("nonprofit", "ntee_inferred", "ntee_code"), ("formd", "form_d_category", "category")):
            r = conn.execute(f"""SELECT count(*) FILTER (WHERE h.pass_number = 2) AS reguessed,
                                        count(*) FILTER (WHERE h.pass_number = 2 AND h.code IS NOT NULL AND p1.code IS NOT NULL AND h.code <> p1.code) AS changed,
                                        count(*) FILTER (WHERE h.pass_number = 2 AND coalesce(h.confidence, 0) > coalesce(p1.confidence, 0)) AS gained,
                                        count(*) FILTER (WHERE h.pass_number = 2 AND m.pass_number = 2) AS replaced,
                                        count(*) FILTER (WHERE h.pass_number = 2 AND m.flagged) AS flagged,
                                        count(*) FILTER (WHERE h.pass_number = 2 AND m.sparse) AS sparse
                                 FROM category_history h JOIN category_history p1 ON p1.kind = h.kind AND p1.key = h.key AND p1.pass_number = 1
                                 JOIN {table} m ON m.{'ein' if kind_name == 'nonprofit' else 'cik'} = h.key WHERE h.kind = %s""", (kind_name,)).fetchone()
            print(f"{kind_name} pass 2: {r[0]:,} re-guessed, {r[1]:,} changed category, {r[2]:,} gained confidence, {r[3]:,} replaced the first pass, "
                  f"{r[4]:,} flagged as disagreements, {r[5]:,} marked too sparse to code (left out of later passes)")


def status() -> None:
    with db.connect() as conn:
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
    ap.add_argument("command", choices=["estimate", "test", "submit", "collect", "status", "build", "threshold", "pass2-report"])
    ap.add_argument("kind", nargs="?", choices=list(KINDS))
    ap.add_argument("n", nargs="?", type=int)
    ap.add_argument("--wave", type=float, default=25.0, help="dollars (estimated) per submit run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--once", action="store_true", help="collect: one pass, no waiting")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--pass", dest="pass_number", type=int, default=1, choices=(1, 2))
    ap.add_argument("--threshold", type=float, default=None, help="pass 2: send first-pass items below this confidence")
    a = ap.parse_args(argv)
    if a.command == "estimate":
        estimate()
    elif a.command == "test":
        test(a.kind or "nonprofit", a.n or 200)
    elif a.command == "submit":
        if not a.kind:
            sys.exit("submit needs a kind: nonprofit or formd")
        if a.pass_number == 2 and a.threshold is None:
            sys.exit("pass 2 needs --threshold (see the threshold command)")
        submit(a.kind, a.wave, a.limit, force=a.force, pass_number=a.pass_number, threshold=a.threshold)
    elif a.command == "collect":
        collect(a.workers, once=a.once)
    elif a.command == "status":
        status()
    elif a.command == "build":
        ntee.build()
    elif a.command == "threshold":
        threshold_report(a.kind or "nonprofit")
    elif a.command == "pass2-report":
        pass2_report()


if __name__ == "__main__":
    main()
