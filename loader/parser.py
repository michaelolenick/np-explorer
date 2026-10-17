"""Parse one IRS e-file XML return into rows, driven by loader.mapping."""

from __future__ import annotations

import re
from datetime import date

from lxml import etree

from app.names import normalize_name, normalize_org
from loader import mapping

_NS_RE = re.compile(rb'\sxmlns="http://www\.irs\.gov/efile"')
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, remove_comments=True)
_TRUE = {"x", "true", "1", "yes"}


def strip_namespace(xml: bytes) -> bytes:
    """Drop the default IRS namespace so mapping paths can be plain element names."""
    return _NS_RE.sub(b"", xml, count=1)


def parse_root(xml: bytes) -> etree._Element:
    return etree.fromstring(strip_namespace(xml), _PARSER)


class Result(dict):
    """Parsed filing: keys filing, people, contractors, schedule_j, related, grants, daf, pf_payout,
    loans, warnings."""


def _first(el, paths):
    for p in paths:
        found = el.find(p)
        if found is not None:
            text = (found.text or "").strip()
            if text:
                return text
            if len(found) == 0:
                # Present but empty (e.g. <OfficerInd/>); treat as present.
                return ""
    return None


def _text(el, paths):
    v = _first(el, paths)
    return v or None


def _int(el, paths):
    v = _first(el, paths)
    if not v:
        return None
    try:
        return int(round(float(v)))
    except ValueError:
        return None


def _num(el, paths):
    v = _first(el, paths)
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _flag(el, paths):
    v = _first(el, paths)
    if v is None:
        return False
    return v.lower() in _TRUE or v == ""


def _yesno(el, paths):
    """True or False when the form answers the question, None when it's left out."""
    v = _first(el, paths)
    if v is None:
        return None
    return v.strip().lower() in _TRUE


def _date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def _candidates(spec_by_era, era):
    if era == "unknown":
        return spec_by_era.get("v2013", []) + spec_by_era.get("v2009", [])
    return spec_by_era.get(era, [])


def _groups(root, spec, era):
    """Yield (element, fields) for every element of a repeating group spec."""
    eras = ["v2013", "v2009"] if era == "unknown" else [era]
    for e in eras:
        s = spec.get(e)
        if not s:
            continue
        for path in s["paths"]:
            for el in root.iterfind(path):
                yield el, s["fields"]


def parse(xml: bytes, object_id: str | int | None = None) -> Result | None:
    """Parse a return. Returns None for forms we don't load (990-T etc.)."""
    root = parse_root(xml)
    version = root.get("returnVersion")
    era, known = mapping.era_for(version)
    warnings = []
    if not known:
        warnings.append(f"unknown returnVersion {version!r}")

    def h(field):
        return _text(root, _candidates(mapping.HEADER[field], era))

    form = h("return_type")
    if form not in mapping.FORMS:
        return None

    ff = mapping.FORM_FIELDS[form]

    def f(field, conv=_int):
        spec = ff.get(field)
        return conv(root, _candidates(spec, era)) if spec else None

    ein = (h("ein") or "").strip()
    tax_year = h("tax_year")
    name = h("name")
    name2 = h("name2")
    dba = f("dba", _text) or name2

    filing = {
        "object_id": int(object_id) if object_id else None,
        "ein": ein,
        "form_type": form,
        "return_version": version,
        "tax_year": int(tax_year) if tax_year and tax_year.isdigit() else None,
        "tax_period_begin": _date(h("tax_period_begin")),
        "tax_period_end": _date(h("tax_period_end")),
        "filed_date": _date(h("filed_ts")),
        "org_name": name,
        "dba": dba,
        "street": h("street"),
        "city": h("city"),
        "state": h("state"),
        "zip": h("zip"),
        "website": clean_website(f("website", _text)),
        "mission": _mission(root, _candidates(ff["mission"], era)) if "mission" in ff else None,
        "total_revenue": f("total_revenue"),
        "total_expenses": f("total_expenses"),
        "total_assets_eoy": f("total_assets_eoy"),
        "total_liabilities_eoy": f("total_liabilities_eoy"),
        "net_assets_eoy": f("net_assets_eoy"),
        "contributions": f("contributions"),
        "program_service_revenue": f("program_service_revenue"),
        "fundraising_expenses": f("fundraising_expenses"),
        "officer_comp_total": f("officer_comp_total"),
        "num_employees": f("num_employees"),
        "num_volunteers": f("num_volunteers"),
        "amended": _flag(root, _candidates(mapping.HEADER["amended"], era)),
    }
    if filing["tax_year"] is None and filing["tax_period_end"]:
        filing["tax_year"] = filing["tax_period_end"].year

    people = []
    for spec in mapping.PEOPLE_GROUPS.get(form, []):
        for el, fields in _groups(root, spec, era):
            raw = _text(el, fields["name"])
            if not raw:
                continue
            g = lambda k, conv=_int: conv(el, fields[k]) if k in fields else None  # noqa: E731
            benefits = g("benefits")
            expense = g("expense_acct")
            other = g("other_comp")
            if other is None and (benefits is not None or expense is not None):
                other = (benefits or 0) + (expense or 0)
            title = g("title", _text)
            is_flag = lambda k: _flag(el, fields[k]) if k in fields else False  # noqa: E731
            row = {
                "source": spec["source"],
                "name_raw": raw,
                "name_norm": normalize_name(raw),
                "title": title,
                "avg_hours": g("avg_hours", _num),
                "avg_hours_related": g("avg_hours_related", _num),
                "is_officer": is_flag("is_officer"),
                "is_director": is_flag("is_director"),
                "is_trustee": is_flag("is_trustee"),
                "is_key_employee": is_flag("is_key_employee"),
                "is_highest_comp": is_flag("is_highest_comp") or bool(spec.get("highest_comp")),
                "is_former": is_flag("is_former"),
                "comp_org": g("comp_org"),
                "comp_related": g("comp_related"),
                "other_comp": other,
                "street": g("street", _text),
                "city": g("city", _text),
                "state": g("state", _text),
                "zip": g("zip", _text),
            }
            # 990-EZ and 990-PF have no role checkboxes: infer from the title.
            if form != "990" and not spec.get("highest_comp"):
                _roles_from_title(row)
            if row["name_norm"]:
                people.append(row)

    contractors = []
    for spec in mapping.CONTRACTOR_GROUPS.get(form, []):
        for el, fields in _groups(root, spec, era):
            raw = _text(el, fields["name"])
            if not raw:
                continue
            if not normalize_org(raw):
                continue
            contractors.append({
                "source": spec["source"],
                "name_raw": raw,
                "name_norm": normalize_org(raw),
                "street": _text(el, fields["street"]),
                "city": _text(el, fields["city"]),
                "state": _text(el, fields["state"]),
                "zip": _text(el, fields["zip"]),
                "service_description": _text(el, fields["service_description"]),
                "compensation": _int(el, fields["compensation"]),
            })

    schedule_j = []
    for el, fields in _groups(root, mapping.SCHEDULE_J, era):
        raw = _text(el, fields["name"])
        if not raw:
            continue
        norm = normalize_name(raw)
        if not norm:            # e.g. a lone apostrophe: nothing to match on
            continue
        row = {"name_raw": raw, "name_norm": norm, "title": _text(el, fields["title"])}
        for k in fields:
            if k not in ("name", "title"):
                row[k] = _int(el, fields[k])
        schedule_j.append(row)

    related = []
    seen = set()
    for el, fields in _groups(root, mapping.SCHEDULE_R, era):
        rein = (_text(el, fields["ein"]) or "").strip()
        if rein and rein.isdigit() and len(set(rein)) > 1 and rein != ein and rein not in seen:
            seen.add(rein)
            related.append({"related_ein": rein, "related_name": _text(el, fields["name"])})

    grants = []
    for spec in mapping.GRANT_GROUPS.get(form, []):
        for el, fields in _groups(root, spec, era):
            g = lambda k, conv=_text: conv(el, fields[k]) if k in fields else None  # noqa: E731
            name = " ".join(x for x in (g("name"), g("name2")) if x) or None
            person = g("person")
            if not name and not person:
                continue
            # A line standing for a list kept in a separate attachment ("Education ... See Statement 26"):
            # a program total, not a grant, and not a person.
            summary = any(SUMMARY_LINE.search(x or "") for x in (name, person, g("purpose"), g("street")))
            if summary and not name:
                name, person = person, None
            rein = re.sub(r"\D", "", g("ein") or "")
            grants.append({
                "source": spec["source"],
                # Grants to individuals: the amount counts, the person's name is not kept.
                "recipient_name": None if person and not name else name,
                "recipient_name_norm": normalize_org(name) if name else None,
                "recipient_ein": rein.zfill(9) if len(rein) in (8, 9) and len(set(rein)) > 1 else None,
                "recipient_is_person": bool(person and not name),
                "is_summary": summary,
                "city": g("city"),
                "state": g("state"),
                "cash_amount": g("cash", _int),
                "noncash_amount": g("noncash", _int),
                "purpose": g("purpose"),
                "irc_section": g("irc_section"),
                "foundation_status": g("foundation_status"),
                "relationship": g("relationship"),
            })

    daf = None
    if form in ("990", "990EZ"):
        vals = {k: (_yesno if k == "maintains_dafs" else _int)(root, _candidates(spec, era))
                for k, spec in mapping.DAF_FIELDS.items()}
        if any(v is not None for v in vals.values()):
            daf = vals

    pf_payout = None
    if form == "990PF":
        vals = {k: _int(root, _candidates(spec, era)) for k, spec in mapping.PF_PAYOUT_FIELDS.items()}
        if any(v is not None for v in vals.values()):
            pf_payout = vals

    loans = []
    if form == "990":
        for el, fields in _groups(root, mapping.LOAN_GROUPS, era):
            raw = _text(el, fields["name"])
            if not raw:
                continue
            row = {"name_raw": raw, "name_norm": normalize_name(raw) or normalize_org(raw)}
            for k in ("relationship", "purpose"):
                row[k] = _text(el, fields[k])
            for k in ("original_principal", "balance_due"):
                row[k] = _int(el, fields[k])
            for k in ("to_org", "from_org", "in_default", "board_approved", "written_agreement"):
                row[k] = _yesno(el, fields[k])
            loans.append(row)

    donors = _donors(root, era) if form == "990PF" else []

    return Result(filing=filing, people=people, contractors=contractors, schedule_j=schedule_j,
                  related=related, grants=grants, daf=daf, pf_payout=pf_payout, loans=loans,
                  expenses=_expenses(root, form, era), donors=donors, warnings=warnings)


SUMMARY_LINE = re.compile(r"\b(see (the )?(attached|statement|stmt|schedule|list|supporting)|statement \d+|"
                          r"attached (list|statement|schedule)|per (attached|schedule|statement)|"
                          r"address for e-?filing|various (recipients|grantees|organizations)|multiple recipients)\b",
                          re.I)


def _donors(root, era: str) -> list[dict]:
    """Schedule B Part I contributors, with Part II noncash values added up per contributor number."""
    noncash: dict[str, int] = {}
    for el, fields in _groups(root, mapping.DONOR_NONCASH, era):
        num = (_text(el, fields["num"]) or "").strip()
        fmv = _int(el, fields["fmv"])
        if num and fmv:
            noncash[num] = noncash.get(num, 0) + fmv
    out = []
    for el, fields in _groups(root, mapping.DONOR_GROUPS, era):
        person, business = _text(el, fields["person"]), _text(el, fields["business"])
        name = person or business
        if not name:
            continue
        num = (_text(el, fields["num"]) or "").strip()
        out.append({
            "contributor_num": int(num) if num.isdigit() else None,
            "name": name,
            "name_norm": normalize_name(name) if person else normalize_org(name),
            # Which name field the filer used. (Schedule B's "Person" box is a contribution type that
            # also covers organizations, so it can't tell people from organizations.)
            "is_person": bool(person),
            "city": _text(el, fields["city"]),
            "state": _text(el, fields["state"]),
            "total_amount": _int(el, fields["total"]),
            "noncash_amount": noncash.get(num),
        })
    return out


# Expense lines the filer itself describes as events (Part IX line 24 descriptions).
EVENT_WORDS = re.compile(r"\b(events?|special events?|galas?|banquets?|dinners?|luncheons?|golf|tournaments?|"
                         r"auctions?|festivals?|concerts?|fundraisers?|receptions?|parties|party|"
                         r"conventions?|retreats?|ceremon(y|ies)|celebrations?|programs? events?)\b", re.I)


def _expenses(root, form: str, era: str) -> dict | None:
    """Where the money went: every expense line on the form, with event spending pulled out."""
    eras = ["v2013", "v2009"] if era == "unknown" else [era]
    lines = []
    if form == "990":
        for e in eras:
            cols = mapping.EXPENSE_COLS_990[e]
            for key, label, t2009, t2013 in mapping.EXPENSE_LINES_990:
                tag = t2013 if e == "v2013" else t2009
                for el in root.iterfind(f"ReturnData/IRS990/{tag}"):
                    vals = [_int(el, [cols[c]]) for c in ("total", "program", "management", "fundraising")]
                    if not any(vals):
                        continue
                    desc = _text(el, [cols["desc"]]) if key == "other" else None
                    lines.append([key, label, desc] + vals)
            if lines:
                break
        events = {k: _int(root, _candidates(spec, era)) for k, spec in mapping.EVENTS_990.items()}
    elif form in mapping.EXPENSE_ROOTS:
        base = mapping.EXPENSE_ROOTS[form]
        spec = mapping.EXPENSE_LINES_EZ if form == "990EZ" else mapping.EXPENSE_LINES_PF
        for e in eras:
            for key, label, t2009, t2013 in spec:
                v = _int(root, [base + (t2013 if e == "v2013" else t2009)])
                if v:
                    lines.append([key, label, None, v, None, None, None])
            if lines:
                break
        events = ({k: _int(root, _candidates(sp, era)) for k, sp in mapping.EVENTS_EZ.items()}
                  if form == "990EZ" else {"special_event_gross": None, "special_event_expenses": None})
    else:
        return None
    if not lines and not any(events.values()):
        return None
    detail = [ln for ln in lines if ln[0] != "total"]
    total = next((ln[3] for ln in lines if ln[0] == "total"), None)
    for ln in lines:
        ln.append(bool(ln[0] == "other" and ln[2] and EVENT_WORDS.search(ln[2])))
    return {
        "total_expenses": total,
        # Zero, not blank, when the form has expense lines but none of this kind: "paid nobody" is a fact.
        "pay_total": sum(ln[3] or 0 for ln in detail if ln[0] in mapping.PAY_KEYS) if lines else None,
        "grants_total": sum(ln[3] or 0 for ln in detail if ln[0] in mapping.GRANT_KEYS) if lines else None,
        "event_lines_total": sum(ln[3] or 0 for ln in detail if ln[-1]) if lines else None,
        "conferences_total": sum(ln[3] or 0 for ln in detail if ln[0] in ("conferences", "travel_conferences"))
        if lines else None,
        "special_event_expenses": events.get("special_event_expenses"),
        "special_event_gross": events.get("special_event_gross"),
        "lines": lines,
    }


_SEE_SCHEDULE = re.compile(r"^\W*(see|refer to)\b.{0,40}\bsch(edule)?\b", re.I)


def _mission(root, paths):
    """First mission text that isn't just a pointer to Schedule O."""
    fallback = None
    for p in paths:
        v = _text(root, [p])
        if not v:
            continue
        if _SEE_SCHEDULE.match(v) and len(v) < 80:
            fallback = fallback or v
            continue
        return v
    return fallback


_NO_SITE = {"n/a", "na", "none", "n a", "no", "0", "-", "not applicable", "no website", "www", "null"}


def clean_website(v):
    if not v:
        return None
    v = v.strip().strip("/")
    if v.lower() in _NO_SITE or "." not in v or " " in v:
        return None
    return v


_TITLE_ROLES = [
    ("is_officer", re.compile(r"\b(pres|president|ceo|chief|cfo|coo|treas|treasurer|secy|secretary|"
                              r"sec|chair|chairman|chairperson|chairwoman|vp|vice|officer|exec|executive|"
                              r"director of|executive director|ed)\b")),
    ("is_director", re.compile(r"\b(dir|director|board|member|bd|governor)\b")),
    ("is_trustee", re.compile(r"\b(trustee|trust)\b")),
]


def _roles_from_title(row):
    t = (row.get("title") or "").lower()
    for key, rx in _TITLE_ROLES:
        if rx.search(t):
            row[key] = True
