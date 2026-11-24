"""Public-records request creator (owner request 2026-11-23): a federal FOIA (5 U.S.C. 552), a state public-records
request, or an IRS 6104(d) request to a nonprofit, written from FURP's own data and a short form.

Live for everyone (owner, 2026-11-24: FURP features are never dev-only). The pages are noindex.
No account is needed. Nothing the user types is stored. The letters come from code (build_letter), so the live preview
and the tests see the same text; the optional "Expand with AI" button sends only the user's few words and the
organization's name to the small model (app/openai_compat.py, the free OpenAI key) and never their name, email or address.

Data: usa_awards (USAspending, linked to organizations by name and zip: loader/usaspending.py) and the reference
tables in app/foia_data.py, each row with its source. Not legal advice; the page says so.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import threading
import time
from collections import Counter

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import db, foia_data as D

log = logging.getLogger("np.foia")
router = APIRouter()


def public() -> bool:
    return True   # live for everyone (owner, 2026-11-24: FURP features are never dev-only)


def _gate():
    if not public():
        raise HTTPException(404)


# ---- awards -----------------------------------------------------------------------------------------------------------

_ASST = re.compile(r"^(?:ASST|CONT)_(?:NON|AGG|AWD|IDV)_(.+?)_(?:[0-9A-Z]{2,4})$")


def award_number(key: str | None) -> str:
    """The award number inside USAspending's generated key: ASST_NON_15JOVW23GG00550LEGA_015 -> 15JOVW23GG00550LEGA."""
    key = key or ""
    m = _ASST.match(key)
    return m.group(1) if m else key


def route(agency: str | None, sub_agency: str | None, key: str | None) -> str:
    """Which FEDERAL contact handles this award: the DOJ office code in the award number first, then agency words."""
    num = award_number(key).upper()
    for code, k in D.DOJ_OFFICE_CODES.items():
        if num.startswith(code):
            return k
    text = f"{agency or ''} {sub_agency or ''}".lower()
    if "justice" in text:
        return "ojp" if "justice programs" in text else "other"
    for words, k in D.AGENCY_WORDS:
        if words in text:
            return k
    return "other"


def _nice(name: str | None) -> str:
    """IRS names are upper case; a letter reads better in title case (with Inc, LLC and the like kept sensible)."""
    name = (name or "").strip()
    if not name.isupper():
        return name
    out = re.sub(r"\b(Llc|Llp|Lp|Usa|Us)\b", lambda m: m.group(1).upper(), name.title())
    return re.sub(r"(\w)'S\b", lambda m: m.group(1) + "'s", re.sub(r"(?<=\w)'S\b", "'s", out))


def org_context(ein: str) -> dict | None:
    ein = re.sub(r"\D", "", ein or "")
    if len(ein) != 9:
        return None
    with db.conn() as conn:
        o = conn.execute("""SELECT ein, name, street, city, state, zip, website, subsection FROM organizations WHERE ein = %s""",
                         (ein,)).fetchone()
        if not o:
            return None
        try:
            rows = conn.execute("""
                SELECT award_key, kind, min(fiscal_year) AS y0, max(fiscal_year) AS y1, sum(obligation) AS total,
                       max(agency) AS agency, max(sub_agency) AS sub_agency, max(program_code) AS program_code,
                       max(program_title) AS program_title, max(description) AS description, max(permalink) AS permalink,
                       max(recipient_uei) AS uei
                FROM usa_awards WHERE recipient_ein = %s GROUP BY award_key, kind
                ORDER BY max(fiscal_year) DESC, sum(obligation) DESC LIMIT 150""", (ein,)).fetchall()
        except Exception:  # noqa: BLE001 - the award tables are not built
            log.exception("foia: awards for %s", ein)
            rows = []
    awards = []
    for r in rows:
        k = route(r["agency"], r["sub_agency"], r["award_key"])
        awards.append({"key": r["award_key"], "number": award_number(r["award_key"]), "kind": r["kind"],
                       "title": (r["program_title"] or "").title() if (r["program_title"] or "").isupper() else (r["program_title"] or ""),
                       "program_code": r["program_code"], "description": (r["description"] or "")[:200],
                       "y0": r["y0"], "y1": r["y1"], "amount": float(r["total"] or 0), "agency": r["agency"],
                       "sub_agency": r["sub_agency"], "route": k, "office": D.FEDERAL[k]["name"], "url": r["permalink"]})
    uei = Counter(r["uei"] for r in rows if r["uei"]).most_common(1)
    org = dict(o)
    org["name"] = _nice(org["name"])
    org["uei"] = uei[0][0] if uei else None
    return {"org": org, "awards": awards}


# ---- letters ----------------------------------------------------------------------------------------------------------

def _money(n) -> str:
    return "${:,.0f}".format(float(n or 0))


def _years(a: dict) -> str:
    y0, y1 = a.get("y0"), a.get("y1")
    return "" if not y0 else (str(y0) if y0 == y1 else f"{y0}-{y1}")


def _s(v, n=400) -> str:
    return re.sub(r"[ \t]+", " ", str(v or "")).strip()[:n]


FEDERAL_RECORDS = {
    "applications": "Grant or contract applications and any amendments or resubmissions",
    "narratives": "Project narratives and work plans",
    "budgets": "Budgets and budget narratives, including approved budget modifications",
    "progress": "Progress and performance reports, including any demographic breakdowns of the people served (aggregate data only; no personally identifying information about the people served)",
    "monitoring": "Monitoring, site-visit, desk-review and compliance reports",
    "correspondence": "Correspondence between the agency and the organization about the award (letters, emails, and notes of calls or meetings)",
    "closeout": "Closeout reports and closeout correspondence",
    "award_docs": "The award notice, award conditions and any special conditions",
    "audits": "Audit and financial-review findings and the agency's follow-up",
}
STATE_RECORDS = {
    "applications": "Applications or proposals for the subgrant or contract, and any amendments",
    "agreements": "The subgrant agreement or contract, amendments and special conditions",
    "budgets": "Budgets and budget narratives, including approved budget modifications",
    "progress": "Progress and performance reports, including any demographic breakdowns of the people served (aggregate data only; no personally identifying information about the people served)",
    "monitoring": "Monitoring, site-visit, desk-review and compliance reports",
    "correspondence": "Correspondence between the agency and the organization about the award (letters, emails, and notes of calls or meetings)",
    "closeout": "Closeout reports and closeout correspondence",
    "payments": "Reimbursement or payment requests and the records of what was paid",
}
IRS_RECORDS = {
    "returns": "Annual information returns (Form 990, 990-EZ or 990-PF, with all schedules and attachments, excluding the names and addresses of contributors) for the three most recent years",
    "application": "The application for recognition of exemption (Form 1023 or 1024), with all supporting documents and attachments, and any correspondence with the IRS about it",
    "determination": "The IRS determination letter",
    "990t": "Form 990-T, if filed, for the three most recent years",
}
RECORD_SETS = {"federal": FEDERAL_RECORDS, "state": STATE_RECORDS, "irs": IRS_RECORDS}


def _date_range(p) -> str:
    a, b = _s(p.get("date_from"), 20), _s(p.get("date_to"), 20)
    if a and b:
        return f"for the period {a} through {b}"
    if a:
        return f"from {a} to the present"
    if b:
        return f"through {b}"
    return ""


def _me(p) -> dict:
    r = p.get("requester") or {}
    g = lambda k, d: _s(r.get(k), 200) or d  # noqa: E731
    return {"name": g("name", "[YOUR NAME]"), "email": g("email", "[YOUR EMAIL]"), "address": g("address", "[YOUR MAILING ADDRESS]"),
            "org": _s(r.get("org"), 200), "phone": _s(r.get("phone"), 40)}


def _signature(me) -> str:
    lines = ["Sincerely,", "", me["name"]]
    if me["org"]:
        lines.append(me["org"])
    lines += [me["address"], me["email"]]
    if me["phone"]:
        lines.append(me["phone"])
    return "\n".join(lines)


def _record_block(p, kind) -> str:
    items = [RECORD_SETS[kind][k] for k in (p.get("records") or []) if k in RECORD_SETS[kind]]
    out = ["  - " + i for i in items]
    also = _s(p.get("also"), 3000)
    if also:
        out.append("  - Also: " + also.replace("\n", "\n    "))
    return "\n".join(out) if out else "  - [choose the records you want]"


def _fee_text(p, statute_federal: bool) -> list[str]:
    cat = p.get("fee_category") or "other"
    out = []
    if statute_federal:
        if cat == "news":
            out.append("Fee category. I am a representative of the news media under 5 U.S.C. § 552(a)(4)(A)(ii)(II), and I do not seek these records for a commercial use. Under the statute, fees are limited to reasonable standard charges for document duplication.")
        elif cat == "educational":
            out.append("Fee category. I am affiliated with an educational institution under 5 U.S.C. § 552(a)(4)(A)(ii)(I), and I do not seek these records for a commercial use. Under the statute, fees are limited to reasonable standard charges for document duplication.")
        else:
            out.append("Fee category. I am an \"all other\" requester under 5 U.S.C. § 552(a)(4)(A)(ii)(III), and I do not seek these records for a commercial use. I understand that I am entitled to two hours of search time and the first 100 pages of duplication without charge.")
    else:
        if cat == "news":
            out.append("Fee category. I am a representative of the news media, and I do not seek these records for a commercial use. I ask that fees be limited to the lowest rate the law allows.")
        elif cat == "educational":
            out.append("Fee category. I am affiliated with an educational institution, and I do not seek these records for a commercial use. I ask that fees be limited to the lowest rate the law allows.")
        else:
            out.append("I do not seek these records for a commercial use.")
    if p.get("fee_waiver", True):
        purpose = _s(p.get("purpose"), 3000)
        if statute_federal:
            w = ("Fee waiver. I request a waiver or reduction of all fees under 5 U.S.C. § 552(a)(4)(A)(iii), because disclosure is in the public interest: "
                 "it is likely to contribute significantly to public understanding of the operations or activities of the government, and it is not primarily in my commercial interest.")
        else:
            w = "Fee waiver. I request a waiver or reduction of all fees to the full extent the law allows, because disclosure is in the public interest and is not primarily in my commercial interest."
        out.append(w + (" " + purpose if purpose else " The records show how public funds awarded to a nonprofit organization were used, a matter of public concern, and I will make what I learn available to the public."))
    limit = _s(p.get("fee_limit"), 12)
    if limit:
        out.append(f"If you estimate that fees will exceed ${limit.lstrip('$')}, please tell me before you do the work so that I can narrow the request.")
    return out


def _awards_block(p, awards, with_agency=True) -> str:
    lines = []
    for i, a in enumerate(awards, 1):
        bits = [a["number"] or a.get("key", "")]
        if a.get("title"):
            bits.append(a["title"])
        s = f"  {i}. " + " - ".join(b for b in bits if b)
        det = ", ".join(x for x in [a.get("office") if with_agency else "", ("FY " + _years(a)) if _years(a) else "",
                                    (_money(a["amount"]) + " obligated") if a.get("amount") else ""] if x)
        if det:
            s += f" ({det})"
        if a.get("url"):
            s += f"\n     Source: {a['url']}"
        lines.append(s)
    manual = _s(p.get("manual_awards"), 2000)
    if manual:
        lines += ["  - " + m.strip() for m in manual.splitlines() if m.strip()]
    return "\n".join(lines)


def _federal(p, org, awards) -> dict:
    me = _me(p)
    key = p.get("agency") or (awards[0]["route"] if awards else "other")
    ag = D.FEDERAL.get(key, D.FEDERAL["other"])
    warnings = []
    use = [a for a in awards if a["route"] == key]
    other = [a for a in awards if a["route"] != key]
    if other:
        warnings.append(f"{len(other)} selected award(s) belong to other agencies; this letter lists only the ones for {ag['name']}. Write a separate request to each agency.")
    if not awards and not _s(p.get("manual_awards")):
        warnings.append("FURP has no federal award data for this organization. Pick the agency yourself and list the award numbers you know.")
    if not ag["v"]:
        warnings.append("This agency's contact is not confirmed. Look up its FOIA office at " + D.FOIA_GOV_FIND + " before you send.")
    ident = f"{org['name']} (EIN {org['ein'][:2]}-{org['ein'][2:]}" + (f"; UEI {org['uei']}" if org.get("uei") else "") + ")"
    rng = _date_range(p)
    head = ag["name"] + (", " + ag["parent"] if ag.get("parent") and ag["parent"] not in ag["name"] and "Department" in ag["parent"] else "")
    paras = [
        dt.date.today().strftime("%B %-d, %Y"),
        "",
        "FOIA Officer\n" + head + ("\n" + ag["address"] if ag.get("address") else ""),
        ("Via: " + ("; ".join(x for x in [ag.get("email"), ag.get("portal")] if x))) if (ag.get("email") or ag.get("portal")) else "",
        "",
        f"Re: Freedom of Information Act request: federal awards to {org['name']}",
        "",
        "Dear FOIA Officer:",
        "",
        f"Under the Freedom of Information Act, 5 U.S.C. § 552, I request copies of the records described below about the federal award(s) to {ident}:",
        "",
        _awards_block(p, use, with_agency=False) or "  [list the award numbers]",
        "",
        "Records requested" + (" " + rng if rng else "") + ":",
        _record_block(p, "federal"),
        "",
        "Format. I prefer electronic records, searchable where possible, sent by email or through your portal, under 5 U.S.C. § 552(a)(3)(B)." if p.get("electronic", True) else "Format. Paper copies are fine.",
        "Please release records on a rolling basis as you find them.",
        "",
    ]
    paras += [t + "\n" for t in _fee_text(p, True)]
    if p.get("expedite"):
        reason = _s(p.get("expedite_reason"), 3000) or "[explain the urgency to inform the public about the government activity at issue]"
        paras.append("Expedited processing. I request expedited processing under 5 U.S.C. § 552(a)(6)(E). " + reason +
                     " I certify that this statement is true and correct to the best of my knowledge and belief.\n")
    paras += [
        "Exemptions. If you withhold anything, please release every reasonably segregable portion (5 U.S.C. § 552(b)), and for each withholding name the exemption and describe what was withheld, so that I can decide whether to appeal.",
        "",
        "Timing. Please confirm that you received this request and give me a tracking number. The statute requires a determination within 20 working days (5 U.S.C. § 552(a)(6)(A)(i)). I am glad to talk about narrowing the request: write or call me.",
        "",
        _signature(me),
    ]
    send = {"to": head, "email": ag.get("email"), "portal": ag.get("portal"), "address": ag.get("address"), "note": ag.get("note"),
            "source": ag["source"], "verified": ag["v"], "find": D.FOIA_GOV_FIND,
            "subject": f"FOIA request: federal awards to {org['name']}"}
    return {"text": "\n".join(x for x in paras if x is not None).replace("\n\n\n", "\n\n"), "send": send, "warnings": warnings}


def _state(p, org, awards) -> dict:
    me = _me(p)
    code = (p.get("state") or "TX").upper()
    st = D.STATES.get(code, D.STATES["TX"])
    presets = D.STATE_AGENCIES.get(code, [])
    agency = _s(p.get("agency_name"), 200) or (presets[0][1] if presets else "[state agency]")
    program = _s(p.get("program"), 500) or (presets[0][2] if presets else "[the grant program or subgrant]")
    warnings = []
    if st["residents_only"]:
        warnings.append(f"{st['name']} limits this law to {st['who'].lower()}. If you do not qualify, ask someone who does to file it.")
    elif "citizen" in st["who"].lower() or "resident" in st["who"].lower():
        warnings.append(f"Who may ask in {st['name']}: {st['who']}.")
    if not st["v"]:
        warnings.append(f"The {st['name']} send-to details are not confirmed. Find the agency's records officer on its website before you send.")
    if not st["deadline_v"]:
        warnings.append(f"The {st['name']} response deadline in this table is not confirmed against the statute. Check it.")
    ident = f"{org['name']} (EIN {org['ein'][:2]}-{org['ein'][2:]})"
    rng = _date_range(p)
    deadline = f" The {st['statute']} requires a response within {st['deadline']}." if st["deadline_v"] and not st["deadline"].startswith("'") else ""
    tx = ""
    if code == "TX":
        tx = (" If you cannot produce everything within 10 business days, please certify that in writing and give me a date (§ 552.221(d)). If you believe any of the information is excepted from disclosure, please ask the Attorney General for a decision within the "
              "10 business days that Tex. Gov't Code § 552.301 allows, and tell me when you do. Please send me a written cost estimate under § 552.2615 "
              "before you charge more than $40.")
    nums = _awards_block(p, awards, with_agency=False)
    paras = [
        dt.date.today().strftime("%B %-d, %Y"),
        "",
        "Public Information Officer / Custodian of Records\n" + agency,
        ("Via: " + st["send_email"]) if st.get("send_email") else "",
        "",
        f"Re: {st['statute']} request: {org['name']}",
        "",
        "Dear Public Information Officer:",
        "",
        f"Under the {st['statute']}, {st['citation']}, I request copies of the records described below about {program} awarded to {ident}.",
        "",
    ]
    if nums:
        paras += ["Related federal awards recorded in public databases (for identification):", nums, ""]
    paras += [
        "Records requested" + (" " + rng if rng else "") + ":",
        _record_block(p, "state"),
        "",
        "Format. I prefer electronic records sent by email or through your portal." if p.get("electronic", True) else "Format. Paper copies are fine.",
        "",
    ]
    paras += [t + "\n" for t in _fee_text(p, False)]
    paras += [
        "If you withhold anything, please release every reasonably segregable portion and cite the specific exception for each withholding." + tx,
        "",
        "Please confirm that you received this request." + deadline + " I am glad to talk about narrowing it: write or call me.",
        "",
        _signature(me),
    ]
    send = {"to": agency, "email": st.get("send_email"), "portal": st.get("send_url"), "address": st["send"], "note": None,
            "source": st.get("send_url") or st["source"], "verified": st["v"], "find": st["source"],
            "subject": f"Public records request: {program}"}
    return {"text": "\n".join(x for x in paras if x is not None).replace("\n\n\n", "\n\n"), "send": send, "warnings": warnings}


def _irs(p, org, awards) -> dict:
    me = _me(p)
    cap = lambda v: (v or "").title() if (v or "").isupper() else (v or "")  # noqa: E731
    addr = ", ".join(x for x in [cap(org.get("street")), cap(org.get("city")), (org.get("state") or "") + " " + (org.get("zip") or "")] if x and x.strip())
    ident = f"{org['name']} (EIN {org['ein'][:2]}-{org['ein'][2:]})"
    sub = (org.get("subsection") or "").strip()
    paras = [
        dt.date.today().strftime("%B %-d, %Y"),
        "",
        f"Custodian of Records / Executive Director\n{org['name']}\n{addr}".rstrip(),
        "",
        f"Re: Request for public inspection documents under 26 U.S.C. § 6104(d): {org['name']}",
        "",
        "Dear Custodian of Records:",
        "",
        f"Under section 6104(d) of the Internal Revenue Code (26 U.S.C. § 6104(d)) and Treasury Regulation § 301.6104(d), I request copies of the following documents of {ident}:",
        "",
        _record_block(p, "irs"),
        "",
        "Format. I prefer electronic copies sent to my email address. If these documents are on your website, a link to them is enough." if p.get("electronic", True)
        else "Format. Paper copies are fine; please mail them to the address below.",
        "",
        "Timing. A request made in person at your principal office must be filled immediately. A written request must be filled within 30 days. "
        "If you charge for copies, please keep the fee to a reasonable copying and postage charge and tell me the amount before you send them.",
        "",
        "Thank you. Please write to me if you need anything from me to fill this request.",
        "",
        _signature(me),
    ]
    warnings = []
    if sub and sub not in ("03",):
        warnings.append(f"FURP lists this organization's IRS subsection as {sub}. The right to its Form 990s applies to all exempt organizations; the application (Form 1023/1024) right applies to those that applied for recognition.")
    if not addr:
        warnings.append("FURP has no mailing address for this organization. Look it up on its website or IRS filings.")
    send = {"to": org["name"], "email": None, "portal": org.get("website"), "address": addr or None,
            "note": "Mail or hand-deliver to the organization's principal office. In person: immediately. Written: within 30 days.",
            "source": "https://www.law.cornell.edu/uscode/text/26/6104", "verified": True, "find": None,
            "subject": f"Section 6104(d) request: {org['name']}"}
    return {"text": "\n".join(x for x in paras if x is not None).replace("\n\n\n", "\n\n"), "send": send, "warnings": warnings}


def build_letter(p: dict) -> dict:
    """p: {kind: federal|state|irs, ein, agency, state, agency_name, program, awards: [award keys], manual_awards, records,
    also, date_from, date_to, electronic, fee_category, fee_waiver, purpose, expedite, expedite_reason, fee_limit, requester}."""
    ctx = org_context(p.get("ein") or "")
    if not ctx:
        return {"text": "", "send": {}, "warnings": ["Pick an organization first."]}
    org = ctx["org"]
    picked = set(p.get("awards") or [])
    awards = [a for a in ctx["awards"] if a["key"] in picked]
    kind = p.get("kind")
    if kind == "irs":
        return _irs(p, org, awards)
    if kind == "state":
        return _state(p, org, awards)
    return _federal(p, org, awards)


# ---- Expand with AI ---------------------------------------------------------------------------------------------------

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}
_day = {"d": None, "n": 0}
PER_IP_HOUR = 12
PER_DAY = 400
EXPAND_PROMPTS = {
    "also": ("The user is writing a public-records request. Rewrite their notes as a clear, specific list or short paragraph of additional records "
             "to request. Keep to what they said; do not invent facts, names, dates or programs. Do not include any person's name or contact details. Plain text only, no markdown."),
    "purpose": ("The user is writing a public-records request and gives a few words on why the records matter to the public. Rewrite it as 2 to 4 plain, factual "
                "sentences supporting a fee waiver (public interest, not commercial). Keep to what they said; do not invent facts, outlets or credentials. Plain text only, no markdown."),
    "expedite": ("The user gives a few words on why a records request is urgent. Rewrite it as 2 to 3 plain, factual sentences stating the urgency to inform the "
                 "public. Keep to what they said; do not invent facts. Plain text only, no markdown."),
}


def _allow(ip: str) -> str | None:
    now = time.time()
    with _lock:
        today = dt.date.today().isoformat()
        if _day["d"] != today:
            _day.update(d=today, n=0)
        if _day["n"] >= PER_DAY:
            return "The AI helper is out of its daily allowance. Write the text yourself or try tomorrow."
        hits = [t for t in _hits.get(ip, []) if now - t < 3600]
        if len(hits) >= PER_IP_HOUR:
            return "That is the hourly limit for the AI helper. Try again later."
        hits.append(now)
        _hits[ip] = hits
        _day["n"] += 1
    return None


def expand_text(field: str, text: str, ctx: dict) -> dict:
    from app import openai_compat
    text = _s(text, 1500)
    if field not in EXPAND_PROMPTS:
        return {"error": "Nothing to expand here."}
    if len(text) < 4:
        return {"error": "Type a few words first."}
    if not openai_compat.enabled():
        return {"error": "The AI helper is not available right now."}
    org = _s(ctx.get("org"), 200)
    kind = {"federal": "a federal FOIA request", "state": "a state public-records request", "irs": "a request to a nonprofit for its IRS Form 990s and exemption application"}.get(ctx.get("kind"), "a public-records request")
    user = f"This is for {kind}" + (f" about the organization {org}" if org else "") + (f", agency: {_s(ctx.get('agency'), 120)}" if ctx.get("agency") else "") + f".\n\nUser's notes:\n{text}"
    payload = {"max_tokens": 500, "system": EXPAND_PROMPTS[field], "messages": [{"role": "user", "content": user}]}
    try:
        r = openai_compat.post(payload, 25.0)
    except Exception:  # noqa: BLE001
        log.exception("foia expand")
        return {"error": "The AI helper did not answer. Your text is unchanged."}
    if r.status_code != 200:
        return {"error": "The AI helper did not answer. Your text is unchanged."}
    out = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
    out = re.sub(r"[*#`]+", "", out)[:2500]
    return {"text": out} if out else {"error": "The AI helper gave nothing usable. Your text is unchanged."}


# ---- routes -----------------------------------------------------------------------------------------------------------

def _page(request: Request, name: str, **ctx):
    from app.main import render
    ctx.setdefault("robots", "noindex, nofollow")
    return render(request, name, **ctx)


@router.get("/records-request", response_class=HTMLResponse)
def page(request: Request, ein: str = "", award: str = "", kind: str = "federal"):
    _gate()
    ein = re.sub(r"\D", "", ein)[:9]
    ctx = org_context(ein) if ein else None
    return _page(request, "records_request.html", ein=ein if ctx else "", org=ctx["org"] if ctx else None, start_award=award[:120],
                 start_kind=kind if kind in ("federal", "state", "irs") else "federal", federal=D.FEDERAL, states=D.STATES,
                 state_agencies=D.STATE_AGENCIES, fed_records=FEDERAL_RECORDS, state_records=STATE_RECORDS, irs_records=IRS_RECORDS)


@router.get("/records-request/tables", response_class=HTMLResponse)
def tables(request: Request):
    _gate()
    return _page(request, "records_request_tables.html", federal=D.FEDERAL, states=D.STATES)


@router.get("/api/foia/context")
def api_context(ein: str = ""):
    _gate()
    ctx = org_context(ein)
    if not ctx:
        raise HTTPException(404)
    return JSONResponse(ctx)


@router.get("/api/foia/orgs")
def api_orgs(q: str = ""):
    _gate()
    q = re.sub(r"[^A-Za-z0-9 &'.-]", " ", q).strip()[:60]
    if len(q) < 3:
        return JSONResponse([])
    from app.names import normalize_name
    qn = normalize_name(q)
    with db.conn() as conn:
        if qn.isdigit() and len(qn) == 9:
            rows = conn.execute("SELECT ein, name, city, state FROM organizations WHERE ein = %s", (qn,)).fetchall()
        else:
            rows = conn.execute("""SELECT ein, name, city, state FROM organizations WHERE name_norm LIKE %s
                                   ORDER BY latest_total_revenue DESC NULLS LAST LIMIT 10""", (qn + "%",)).fetchall()
    return JSONResponse([dict(r) for r in rows])


@router.post("/api/foia/letter")
async def api_letter(request: Request):
    _gate()
    try:
        p = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400)
    if not isinstance(p, dict):
        raise HTTPException(400)
    return JSONResponse(build_letter(p))


@router.post("/api/foia/expand")
async def api_expand(request: Request):
    _gate()
    try:
        p = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400)
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    why = _allow(ip)
    if why:
        return JSONResponse({"error": why}, status_code=429)
    return JSONResponse(expand_text(p.get("field"), p.get("text"), p.get("context") or {}))
