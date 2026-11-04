"""Cross-links (loader/xlinks.py) between the Form 5500, FARA, Open Payments and state and city payroll records and
the rest of the site, read both ways: for_target() lists the new records that match an existing page (person,
organization, business registration, FEC donor, lobbying client, registrant or lobbyist, SEC filer, Form D
issuer, adviser); for_source() lists the existing pages a new record matches."""

from __future__ import annotations

from urllib.parse import quote

from app import db

# How each source kind is shown on the pages it links to: (dataset label, record label, url builder).
SOURCES = {
    "fara_registrant": ("Foreign agents (FARA)", "FARA registrant", lambda k: f"/fara/registrant/{k}"),
    "fara_principal": ("Foreign agents (FARA)", "FARA foreign principal", lambda k: f"/fara/principals?all=1&id={k}"),
    "fara_person": ("Foreign agents (FARA)", "FARA short-form registrant", lambda k: f"/fara/people?all=1&id={k}"),
    "f5500_sponsor": ("Form 5500 (employee benefit plans)", "Plan sponsor", lambda k: f"/form5500/sponsor/{k}"),
    "f5500_person": ("Form 5500 (employee benefit plans)", "Signed or prepared Form 5500 filings", lambda k: "/form5500/name/" + quote(k, safe="")),
    "op_recipient": ("Open Payments (drug and device company payments)", "Payment recipient", lambda k: f"/openpayments/recipient/{k}"),
    "op_payer": ("Open Payments (drug and device company payments)", "Paying company", lambda k: f"/openpayments/company/{k}"),
    "payroll_person": ("State and city payroll", "Public employee", lambda k: "/pay/search?" + _payroll_query(k)),
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
}


def _payroll_query(key: str) -> str:
    state, _, rest = key.partition(":")
    label, _, name_norm = rest.partition(":")
    from urllib.parse import urlencode
    return urlencode({"q": name_norm, "state": state, "employer": label})


def _donor_url(key: str) -> str:
    from app import politics
    zip5, _, name_norm = key.partition(":")
    return politics.donor_url(name_norm, zip5)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('xlinks') AS t").fetchone()["t"] is not None


def for_target(kind: str, key: str, limit: int = 100) -> list[dict]:
    """The new-dataset records matched to an existing page, grouped for display."""
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            rows = conn.execute("""SELECT src_kind, src_key, src_name, src_state, how FROM xlinks
                                   WHERE dst_kind = %s AND dst_key = %s ORDER BY src_kind, src_name LIMIT %s""",
                                (kind, str(key), limit)).fetchall()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        return []
    out = []
    for r in rows:
        dataset, label, url = SOURCES.get(r["src_kind"], ("", r["src_kind"], lambda k: "#"))
        name = r["src_name"]
        out.append({"dataset": dataset, "label": label, "name": name, "state": r["src_state"], "url": url(r["src_key"]),
                    "how": r["how"], "src_kind": r["src_kind"], "src_key": r["src_key"]})
    return out


def for_source(kind: str, key: str) -> list[dict]:
    """The existing pages a new record matches."""
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            rows = conn.execute("""SELECT dst_kind, dst_key, dst_name, how FROM xlinks WHERE src_kind = %s AND src_key = %s
                                   ORDER BY dst_kind, dst_name LIMIT 50""", (kind, str(key))).fetchall()
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


def counts() -> list[dict]:
    try:
        with db.conn() as conn:
            if conn.execute("SELECT to_regclass('xlink_counts') AS t").fetchone()["t"] is None:
                return []
            return conn.execute("SELECT src_kind, dst_kind, n, sources, built FROM xlink_counts ORDER BY 1, 2").fetchall()
    except Exception:  # noqa: BLE001
        return []
