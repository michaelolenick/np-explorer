"""Cross-links between every record kind on the site (loader/xlinks.py for the 2026-11-04 datasets, loader/xref.py, the
continuous engine, for everything since 2026-11-13), read both ways: for_target() lists the records matched to a page
(person, organization, business registration, FEC donor, lobbying client, registrant or lobbyist, SEC filer, Form D
issuer, adviser, contractor, college, recall firm, patent assignee, trademark owner...); for_source() lists the pages
a record matches; both() merges the two for the pages' "Also on this site" block; peers() finds the records that share
an interest (NTEE code, FURP topic, lobbying issue, industry); summary() feeds /data, /admin and the daily report;
links() is the API and MCP view."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from app import db

# How each kind is shown on the pages it links to: (dataset label, record label, url builder(key, name)).
# The sources of loader/xlinks.py first (their labels unchanged), then every kind loader/xref.py collects.
SOURCES = {
    "fara_registrant": ("Foreign agents (FARA)", "FARA registrant", lambda k: f"/fara/registrant/{k}"),
    "fara_principal": ("Foreign agents (FARA)", "FARA foreign principal", lambda k: f"/fara/principals?all=1&id={k}"),
    "fara_person": ("Foreign agents (FARA)", "FARA short-form registrant", lambda k: f"/fara/people?all=1&id={k}"),
    "f5500_sponsor": ("Form 5500 (employee benefit plans)", "Plan sponsor", lambda k: f"/form5500/sponsor/{k}"),
    "f5500_person": ("Form 5500 (employee benefit plans)", "Signed or prepared Form 5500 filings", lambda k: "/form5500/name/" + quote(k, safe="")),
    "op_recipient": ("Open Payments (drug and device company payments)", "Payment recipient", lambda k: f"/openpayments/recipient/{k}"),
    "op_payer": ("Open Payments (drug and device company payments)", "Paying company", lambda k: f"/openpayments/company/{k}"),
    "payroll_person": ("State and city payroll", "Public employee", lambda k: "/pay/search?" + _payroll_query(k)),
    "ipo_company": ("IPO registrations (S-1, F-1)", "IPO registrant", lambda k: f"/ipos/{k}"),
    "space_doc": ("Documents (public uploads to the FURP space)", "Public document", lambda k: f"/docs/{k}"),   # app/space_ingest.py
    # loader/xref.py (2026-11-13)
    "org": ("Nonprofits (IRS Form 990)", "Nonprofit", lambda k: f"/org/{k}"),
    "person": ("People (Form 990 officers, directors and employees)", "Person page", lambda k: f"/person/{k}"),
    "biz": ("State business registries", "Business registration", lambda k: "/business/" + k.split(":", 1)[0] + "/" + quote(k.split(":", 1)[1], safe="")),
    "fed": ("Federal spending (USAspending)", "Federal award recipient", lambda k: f"/federal-spending/recipient/{k}"),
    "lda_client": ("Federal lobbying (LDA)", "Lobbying client", lambda k: f"/lobbying/client/{k}"),
    "lda_registrant": ("Federal lobbying (LDA)", "Lobbying registrant", lambda k: f"/lobbying/firm/{k}"),
    "lda_lobbyist": ("Federal lobbying (LDA)", "Registered lobbyist", lambda k: f"/lobbying/lobbyist/{k}"),
    "fec_committee": ("Campaign finance (FEC)", "Political committee", lambda k: f"/politics/committee/{k}"),
    "fec_donor": ("Campaign finance (FEC)", "FEC donor", lambda k: _donor_url(k)),
    "sec": ("SEC filers (EDGAR)", "SEC filer", lambda k: f"/corporate/company/{k}"),
    "sec_insider": ("SEC insider filings (Forms 3, 4, 5)", "SEC insider", lambda k: f"/corporate/insider/{k}"),
    "formd": ("Form D private offerings", "Form D issuer", lambda k: f"/corporate/form-d/cik/{k}"),
    "formd_party": ("Form D private offerings", "Person named on Form D", lambda k: f"/corporate/fund-person/{k}"),
    "formd_offering": ("Form D private offerings", "Form D offering", lambda k: f"/corporate/form-d/{k}"),
    "adv": ("Investment advisers (Form ADV)", "Investment adviser", lambda k: f"https://adviserinfo.sec.gov/firm/summary/{k}"),
    "adv_person": ("Investment advisers (Form ADV)", "Adviser owner or control person", lambda k: f"/corporate/adviser-person/{k}"),
    "adv_fund": ("Investment advisers (Form ADV)", "Private fund", lambda k: f"/corporate/fund/{k}"),
    "contractor": ("Nonprofit contractors (Form 990)", "Contractor", lambda k: f"/contractor/{k}"),
    "college": ("Colleges and universities (IPEDS)", "College", lambda k: f"/institution/{k}"),
    "recallfirm": ("Food recalls (FDA, USDA)", "Recalling firm", lambda k: f"/recalls/firm/{k}"),
    "pat_assignee": ("Patents (USPTO)", "Patent assignee", lambda k: f"/patents/assignee/{k}"),
    "pat_inventor": ("Patents (USPTO)", "Inventor", lambda k: f"/inventor/{k}"),
    "tm_owner": ("Trademarks (USPTO)", "Trademark owner", lambda k: f"/trademarks/owner/{k}"),
    "sl_issuer": ("Student loan securitizations", "Issuer or servicer", lambda k: f"/student-loans/issuer/{k}"),
    "ipo_underwriter": ("IPO registrations (S-1, F-1)", "Underwriter", lambda k: f"/ipos/underwriters/{quote(k, safe='')}"),
    "pension_fund": ("Public pension private equity reports", "Pension fund holding", lambda k: "/boards/pension-funds?" + urlencode({"q": k.partition(':')[2]})),
    "interest": ("Interests", "Interest", lambda k: _interest_url(k)),
}
TARGETS = {
    "person": ("Person page", lambda k, n: f"/person/{k}"),
    "org": ("Nonprofit", lambda k, n: f"/org/{k}"),
    "biz": ("Business registration", lambda k, n: "/business/" + k.split(":", 1)[0] + "/" + quote(k.split(":", 1)[1], safe="")),
    "fec_donor": ("FEC donor", lambda k, n: _donor_url(k)),
    "lda_client": ("Lobbying client", lambda k, n: f"/lobbying/client/{k}"),
    "lda_registrant": ("Lobbying registrant", lambda k, n: f"/lobbying/firm/{k}"),
    "lda_lobbyist": ("Registered lobbyist", lambda k, n: f"/lobbying/lobbyist/{k}"),
    "formd": ("Form D issuer", lambda k, n: f"/corporate/form-d/cik/{k}"),
    "adv": ("Investment adviser (Form ADV)", lambda k, n: f"https://adviserinfo.sec.gov/firm/summary/{k}"),
    "sec": ("SEC filer", lambda k, n: f"/corporate/company/{k}"),
    "fec_committee": ("Political committee (FEC)", lambda k, n: f"/politics/committee/{k}"),
    "fara_registrant": ("Foreign agent registrant (FARA)", lambda k, n: f"/fara/registrant/{k}"),
    "fed": ("Federal award recipient", lambda k, n: f"/federal-spending/recipient/{k}"),
    "f5500": ("Form 5500 plan sponsor", lambda k, n: f"/form5500/sponsor/{k}"),
    "ipo_company": ("IPO registrant", lambda k, n: f"/ipos/{k}"),                  # documents link to these two (2026-11-12)
    "contractor": ("Nonprofit contractor", lambda k, n: f"/contractor/{k}"),
}
# Every xref kind is a target too (the engine writes both directions).
for _k, (_ds, _label, _url) in SOURCES.items():
    TARGETS.setdefault(_k, (_label, (lambda u: (lambda k, n: u(k)))(_url)))

INTEREST_PREFIX = {"ntee": "NTEE code", "field": "FURP topic", "topic": "Topic", "lda": "Lobbying issue",
                   "formd_industry": "Form D industry", "sic": "SIC industry", "cpc": "Patent class (CPC)", "cfda": "Federal program (CFDA)"}


def _interest_url(key: str) -> str:
    kind, _, v = key.partition(":")
    if kind == "ntee":
        return f"/categories/ntee/{quote(v, safe='')}"
    if kind == "field":
        t, _, s = v.partition(":")
        return f"/categories/furp/{quote(t, safe='')}" + (f"/{quote(s, safe='')}" if s else "")
    if kind == "lda":
        return "/lobbying?" + urlencode({"issue": v})
    if kind == "sic":
        return "/ipos/companies?" + urlencode({"sic": v})
    if kind == "formd_industry":
        return "/categories?" + urlencode({"view": "formd", "q": v})
    if kind == "cpc":
        return "/search?" + urlencode({"q": v, "type": "patents"})
    if kind == "cfda":
        return "/federal-spending?" + urlencode({"program": v})
    return "/search?" + urlencode({"q": v})


def _payroll_query(key: str) -> str:
    state, _, rest = key.partition(":")
    label, _, name_norm = rest.partition(":")
    return urlencode({"q": name_norm, "state": state, "employer": label})


def _donor_url(key: str) -> str:
    from app import politics
    zip5, _, name_norm = key.partition(":")
    return politics.donor_url(name_norm, zip5)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('xlinks') AS t").fetchone()["t"] is not None


def _confidence(how: str | None) -> str:
    h = how or ""
    return "EXACT" if "EXACT" in h else "FUZZY" if "FUZZY" in h or "name" in h.lower() else "Fuzzy"


def for_target(kind: str, key: str, limit: int = 100) -> list[dict]:
    """The records matched to an existing page, grouped for display (interest rows are not records: see peers())."""
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            rows = conn.execute("""SELECT src_kind, src_key, src_name, src_state, how FROM xlinks
                                   WHERE dst_kind = %s AND dst_key = %s AND src_kind <> 'interest'
                                   ORDER BY src_kind, src_name LIMIT %s""", (kind, str(key), limit)).fetchall()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        return []
    out = []
    for r in rows:
        dataset, label, url = SOURCES.get(r["src_kind"], ("", r["src_kind"], lambda k: "#"))
        name = r["src_name"]
        out.append({"dataset": dataset, "label": label, "name": name, "state": r["src_state"], "url": url(r["src_key"]),
                    "how": r["how"], "src_kind": r["src_kind"], "src_key": r["src_key"]})
    return out


def for_source(kind: str, key: str, limit: int = 50) -> list[dict]:
    """The existing pages a record matches."""
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            rows = conn.execute("""SELECT dst_kind, dst_key, dst_name, how FROM xlinks WHERE src_kind = %s AND src_key = %s
                                   AND dst_kind <> 'interest' ORDER BY dst_kind, dst_name LIMIT %s""", (kind, str(key), limit)).fetchall()
            out = []
            for r in rows:
                label, url = TARGETS.get(r["dst_kind"], (r["dst_kind"], lambda k, n: "#"))
                u = url(r["dst_key"], r["dst_name"])
                if r["dst_kind"] == "formd":
                    o = conn.execute("""SELECT latest_accession FROM sec_formd_offerings WHERE cik = %s
                                        ORDER BY latest_date DESC LIMIT 1""", (r["dst_key"],)).fetchone()
                    u = f"/corporate/form-d/{o['latest_accession']}" if o else None
                if u:
                    out.append({"label": label, "name": r["dst_name"] or r["dst_key"], "url": u, "how": r["how"],
                                "external": u.startswith("http"), "exact": "EXACT" in (r["how"] or ""),
                                "kind": r["dst_kind"], "key": r["dst_key"]})
    except Exception:  # noqa: BLE001
        return []
    return out


def both(kind: str, key: str) -> list[dict]:
    """Every record linked to a page, either direction, one row per record (the pages' "Also on this site" table)."""
    seen, out = set(), []
    for x in for_target(kind, key):
        seen.add((x["src_kind"], x["src_key"]))
        out.append(x)
    for x in for_source(kind, key):
        if (x["kind"], x["key"]) in seen:
            continue
        dataset, label, _ = SOURCES.get(x["kind"], ("", x["label"], None))
        out.append({"dataset": dataset, "label": label or x["label"], "name": x["name"], "state": None, "url": x["url"],
                    "how": x["how"], "src_kind": x["kind"], "src_key": x["key"]})
    return out


def interests(kind: str, key: str) -> list[dict]:
    """A record's interest keys (NTEE code, topics, lobbying issues, industries)."""
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            rows = conn.execute("""SELECT dst_key, dst_name, how FROM xlinks WHERE src_kind = %s AND src_key = %s AND dst_kind = 'interest'
                                   ORDER BY dst_key LIMIT 40""", (kind, str(key))).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{"key": r["dst_key"], "kind": INTEREST_PREFIX.get(r["dst_key"].partition(":")[0], "Interest"),
             "name": r["dst_name"] or r["dst_key"], "url": _interest_url(r["dst_key"]), "how": r["how"]} for r in rows]


def peers(kind: str, key: str, state: str | None, limit: int = 10) -> dict | None:
    """"Others with the same interests": the most specific interest first (an NTEE code, a FURP topic, a lobbying issue,
    an industry), records in the same state first, then anywhere; and the other datasets' records that share a topic."""
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return None
            mine = conn.execute("""SELECT dst_key, dst_name FROM xlinks WHERE src_kind = %s AND src_key = %s AND dst_kind = 'interest'
                                   ORDER BY CASE split_part(dst_key, ':', 1) WHEN 'ntee' THEN 0 WHEN 'field' THEN 1 WHEN 'lda' THEN 2
                                                 WHEN 'sic' THEN 3 WHEN 'formd_industry' THEN 4 WHEN 'cpc' THEN 5 WHEN 'cfda' THEN 6 ELSE 9 END,
                                            dst_key LIMIT 12""", (kind, str(key))).fetchall()
            if not mine:
                return None
            specific = [m for m in mine if not m["dst_key"].startswith("topic:")]
            topics = [m for m in mine if m["dst_key"].startswith("topic:")]
            out = {"interests": [{"key": m["dst_key"], "name": m["dst_name"] or m["dst_key"], "url": _interest_url(m["dst_key"]),
                                  "kind": INTEREST_PREFIX.get(m["dst_key"].partition(":")[0], "Interest")} for m in mine],
                   "same": [], "same_key": None, "same_name": None, "same_url": None, "others": []}
            for m in specific[:2]:
                rows = conn.execute("""SELECT src_kind, src_key, src_name, src_state FROM xlinks
                                       WHERE dst_kind = 'interest' AND dst_key = %s AND src_kind = %s AND src_key <> %s
                                         AND (%s::text IS NULL OR src_state = %s)
                                       LIMIT %s""", (m["dst_key"], kind, str(key), state, state, limit)).fetchall()
                if len(rows) < limit and state:
                    more = conn.execute("""SELECT src_kind, src_key, src_name, src_state FROM xlinks
                                           WHERE dst_kind = 'interest' AND dst_key = %s AND src_kind = %s AND src_key <> %s
                                             AND src_state IS DISTINCT FROM %s LIMIT %s""",
                                        (m["dst_key"], kind, str(key), state, limit - len(rows))).fetchall()
                    rows = [*rows, *more]
                if rows:
                    out["same"] = [{"name": r["src_name"] or r["src_key"], "state": r["src_state"], "url": SOURCES[kind][2](r["src_key"])}
                                   for r in rows]
                    out["same_key"], out["same_name"], out["same_url"] = m["dst_key"], m["dst_name"] or m["dst_key"], _interest_url(m["dst_key"])
                    break
            for m in topics[:2]:
                rows = conn.execute("""SELECT DISTINCT ON (src_kind) src_kind, src_key, src_name, src_state FROM (
                                           SELECT src_kind, src_key, src_name, src_state FROM xlinks
                                           WHERE dst_kind = 'interest' AND dst_key = %s AND src_kind <> %s AND src_state = %s LIMIT 400) q
                                       ORDER BY src_kind, src_name LIMIT 6""", (m["dst_key"], kind, state or "")).fetchall()
                for r in rows:
                    ds, label, url = SOURCES.get(r["src_kind"], ("", r["src_kind"], lambda k: "#"))
                    out["others"].append({"label": label, "dataset": ds, "name": r["src_name"] or r["src_key"], "state": r["src_state"],
                                          "url": url(r["src_key"]), "topic": m["dst_name"] or m["dst_key"], "topic_url": _interest_url(m["dst_key"])})
                if out["others"]:
                    break
            return out if out["same"] or out["others"] else out
    except Exception:  # noqa: BLE001 - an extra section
        return None


def links(kind: str, key: str) -> dict:
    """The API and MCP view (app/public_api.py, app/mcp.py): every link either way, plus interests."""
    from app.config import SITE_URL
    rows = []
    for x in both(kind, key):
        u = x["url"]
        rows.append({"kind": x["src_kind"], "key": x["src_key"], "record": x["label"], "dataset": x["dataset"], "name": x["name"],
                     "state": x["state"], "how": x["how"], "confidence": _confidence(x["how"]),
                     "url": u if u.startswith("http") else SITE_URL + u})
    return {"kind": kind, "key": str(key), "links": rows, "interests": interests(kind, key), "count": len(rows)}


def counts() -> list[dict]:
    try:
        with db.conn() as conn:
            if conn.execute("SELECT to_regclass('xlink_counts') AS t").fetchone()["t"] is None:
                return []
            return conn.execute("SELECT src_kind, dst_kind, n, sources, built FROM xlink_counts ORDER BY 1, 2").fetchall()
    except Exception:  # noqa: BLE001
        return []


def summary() -> dict | None:
    """The cross-references section of /data and /admin: counts by source and destination kind and rule (xref_counts,
    refreshed after every sweep), and the engine's state table (every linker's last run)."""
    try:
        with db.conn() as conn:
            if conn.execute("SELECT to_regclass('xref_counts') AS t").fetchone()["t"] is None:
                return None
            pairs = conn.execute("""SELECT src_kind, dst_kind, linker, rule, n, sources, built FROM xref_counts
                                    ORDER BY n DESC, src_kind, dst_kind""").fetchall()
            state = conn.execute("""SELECT linker, src_kind, dst_kinds, rule, last_run, last_full, rows_added, total_added, seconds, runs, error
                                    FROM xref_state ORDER BY linker""").fetchall()
            total = sum(p["n"] for p in pairs)
            last = max((s["last_run"] for s in state if s["last_run"]), default=None)
            built = max((p["built"] for p in pairs), default=None)
            rules = {s["linker"]: s["rule"] for s in state}
            kinds = sorted({p["src_kind"] for p in pairs} | {p["dst_kind"] for p in pairs})
            return {"pairs": [dict(p, rule=rules.get(p["linker"]) or ("loader/xlinks.py, nightly" if p["linker"] == "xlinks" else p["rule"]))
                              for p in pairs],
                    "state": state, "total": total, "last_run": last, "counts_built": built, "kinds": kinds,
                    "labels": {k: SOURCES.get(k, ("", k, None))[1] for k in kinds}}
    except Exception:  # noqa: BLE001
        return None


def report_line() -> dict | None:
    """One line for the daily report (app/report.py): links, kinds, the last sweep, linkers with errors."""
    s = summary()
    if not s:
        return None
    errors = [x["linker"] for x in s["state"] if x["error"]]
    added = sum(x["rows_added"] or 0 for x in s["state"])
    return {"links": s["total"], "kinds": len(s["kinds"]), "last_run": s["last_run"].isoformat(timespec="minutes") if s["last_run"] else None,
            "added_last_run": added, "linkers": len(s["state"]), "errors": errors}
