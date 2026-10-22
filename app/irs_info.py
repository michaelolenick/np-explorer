"""IRS exempt-status facts for an organization page (tables from loader/irs_status.py): exempt type, ruling date,
whether donations are deductible (Pub 78), status (exempt, revoked, reinstated) and the principal officer from
its Form 990-N e-postcards. Every organization in the IRS lists has these, with or without a full Form 990."""

from __future__ import annotations

import datetime as dt

from app import db

BMF_URL = "https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf"
TEOS_URL = "https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads"
SUBSECTION = {
    "01": "501(c)(1): corporation organized under an act of Congress", "02": "501(c)(2): title-holding corporation",
    "03": "501(c)(3): charitable, religious, educational, scientific or literary", "04": "501(c)(4): social welfare",
    "05": "501(c)(5): labor, agricultural or horticultural", "06": "501(c)(6): business league or chamber of commerce",
    "07": "501(c)(7): social or recreational club", "08": "501(c)(8): fraternal beneficiary society",
    "09": "501(c)(9): voluntary employees' beneficiary association", "10": "501(c)(10): domestic fraternal society",
    "11": "501(c)(11): teachers' retirement fund", "12": "501(c)(12): benevolent life insurance or mutual company",
    "13": "501(c)(13): cemetery company", "14": "501(c)(14): credit union", "15": "501(c)(15): mutual insurance company",
    "16": "501(c)(16): crop financing", "17": "501(c)(17): supplemental unemployment benefit trust",
    "18": "501(c)(18): employee-funded pension trust", "19": "501(c)(19): veterans organization",
    "21": "501(c)(21): black lung trust", "22": "501(c)(22): multiemployer pension plan",
    "23": "501(c)(23): veterans association founded before 1880", "25": "501(c)(25): title-holding company",
    "26": "501(c)(26): state high-risk health coverage", "27": "501(c)(27): state workers' compensation reinsurance",
    "29": "501(c)(29): qualified nonprofit health insurance issuer", "40": "501(d): religious and apostolic",
    "50": "501(e): cooperative hospital service", "60": "501(f): cooperative educational service",
    "70": "501(k): child care", "71": "501(n): charitable risk pool", "92": "4947(a)(1): nonexempt charitable trust"}
FOUNDATION = {
    "02": "private operating foundation exempt from excise tax", "03": "private operating foundation",
    "04": "private non-operating foundation", "09": "suspense", "10": "church", "11": "school",
    "12": "hospital or medical research organization", "13": "organization supporting a government college",
    "14": "governmental unit", "15": "public charity supported by the public (170(b)(1)(A)(vi))",
    "16": "public charity, 509(a)(2)", "17": "supporting organization, 509(a)(3)", "18": "public safety testing, 509(a)(4)",
    "21": "supporting organization, Type I", "22": "supporting organization, Type II",
    "23": "supporting organization, Type III functionally integrated",
    "24": "supporting organization, Type III non-functionally integrated"}
STATUS = {"01": "Exempt (unconditional)", "02": "Exempt (conditional)", "12": "Trust described in 4947(a)(2)",
          "25": "Private foundation, terminating"}
ORGANIZATION = {"1": "corporation", "2": "trust", "3": "cooperative", "4": "partnership", "5": "association"}
PUB78 = {"PC": "public charity", "PF": "private foundation", "POF": "private operating foundation",
         "SO": "supporting organization", "SONFI": "supporting organization (Type III non-functionally integrated)",
         "SOUNK": "supporting organization", "GROUP": "covered by a group exemption", "LODGE": "fraternal lodge",
         "EO": "other exempt organization", "FORGN": "foreign organization", "UNKWN": "public charity"}


def _ruling(r: str | None) -> str | None:
    if not r or not r.isdigit() or len(r) != 6 or r == "000000":
        return None
    try:
        return dt.date(int(r[:4]), int(r[4:]) or 1, 1).strftime("%B %Y") if int(r[4:]) else r[:4]
    except ValueError:
        return r[:4]


def for_org(ein: str) -> dict | None:
    """Facts for the page, or None when the IRS lists have nothing on this EIN."""
    try:
        # A reload swaps these tables in with a quick rename; a page never waits on it: it skips the section.
        with db.conn() as conn, conn.transaction():
            conn.execute("SET LOCAL lock_timeout = '150ms'")
            b = conn.execute("SELECT * FROM irs_bmf_detail WHERE ein = %s", (ein,)).fetchone()
            p = conn.execute("SELECT * FROM irs_pub78 WHERE ein = %s", (ein,)).fetchone()
            rev = conn.execute("SELECT * FROM irs_revocations WHERE ein = %s ORDER BY revocation_date DESC",
                               (ein,)).fetchall()
            pc = conn.execute("SELECT * FROM irs_epostcard WHERE ein = %s ORDER BY tax_year DESC", (ein,)).fetchall()
    except Exception:  # noqa: BLE001 - tables not there yet, or locked by a reload: no section this time
        return None
    if not (b or p or rev or pc):
        return None
    sub = (b or {}).get("subsection") or (rev[0]["exemption_type"] if rev else None)
    out = {"exempt_type": SUBSECTION.get((sub or "").zfill(2)) if sub else None,
           "foundation": FOUNDATION.get((b or {}).get("foundation") or ""),
           "organization": ORGANIZATION.get((b or {}).get("organization") or ""),
           "ruling": _ruling((b or {}).get("ruling")),
           "deductible": (f"Yes: listed in IRS Publication 78 ({PUB78.get((p['codes'] or '').split(',')[0].strip(), 'qualifying organization')})"
                          if p else ("Yes, according to the Business Master File" if (b or {}).get("deductibility") in ("1", "4")
                                     else "No" if (b or {}).get("deductibility") == "2" else None)),
           "in_pub78": bool(p), "revocations": rev, "epostcards": pc,
           "officer": next((x["officer_name"] for x in pc if x["officer_name"]), None),
           "officer_year": next((x["tax_year"] for x in pc if x["officer_name"]), None),
           "in_bmf": bool(b), "income_amt": (b or {}).get("income_amt"), "asset_amt": (b or {}).get("asset_amt")}
    last = rev[0] if rev else None
    if last and not last["reinstatement_date"]:
        out["status"] = (f"Exemption revoked {last['revocation_date']:%B %-d, %Y} for not filing a return three years "
                         f"in a row (automatic revocation; posted {last['posting_date']:%B %-d, %Y})"
                         if last["posting_date"] else f"Exemption revoked {last['revocation_date']:%B %-d, %Y}")
    elif last:
        out["status"] = (f"Exempt: reinstated {last['reinstatement_date']:%B %-d, %Y} after an automatic revocation on "
                         f"{last['revocation_date']:%B %-d, %Y}")
    elif b:
        out["status"] = STATUS.get(b.get("status") or "", "Exempt") + " (IRS Business Master File)"
    elif pc and pc[0]["terminated"]:
        out["status"] = f"Terminated (its {pc[0]['tax_year']} Form 990-N says so)"
    else:
        out["status"] = None
    return out
