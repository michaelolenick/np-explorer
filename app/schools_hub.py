"""The Schools menu: three plain pages (School 990s, School pay data, Student loan data) plus an overview, each a
list of leaderboard-style suggestions with their top three. Suggestions are either a whole board (payroll and
student loan boards) or the Schools Report Card sorted by one column and shown with only that topic's columns
(/boards/schools?view=990|pay|loans&sort=...). Nothing here has its own data: it reads the boards' views."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app import boards

log = logging.getLogger("np.schools")

REPORT_CARD = "schools"

# Report Card columns shown in each topic view (the board's value column and the school's name, state and year
# are always shown).
VIEWS: dict[str, list[str]] = {
    "990": ["n_orgs", "org_revenue", "org_expenses", "org_net_assets", "org_top_person", "org_top_pay",
            "grants_received", "n_funders", "top_funder", "event_direct", "event_net"],
    "pay": ["control", "enrollment", "payroll_total", "headcount", "top_person", "top_pay", "fac_prof", "fac_assoc",
            "fac_asst", "coach_name", "coach_pay", "coach_sport"],
    "loans": ["control", "sector", "enrollment", "cdr_rate", "cdr_year"],
}


@dataclass
class Suggestion:
    title: str
    definition: str
    board: str                       # board slug
    sort: str | None = None          # Report Card column to sort by (None = the board's own ranking)
    view: str | None = None          # Report Card topic view
    person: str | None = None        # column holding a name to show with the value
    person_label: str | None = None  # what that name is ("top funder"); none when it is the value's own person
    subtitle: str | None = None

    @property
    def href(self) -> str:
        if self.sort or self.view:
            q = "&".join(f"{k}={v}" for k, v in (("view", self.view), ("sort", self.sort)) if v)
            return f"/boards/{self.board}?{q}"
        return f"/boards/{self.board}"


@dataclass
class Section:
    key: str
    title: str
    path: str
    intro: str
    suggestions: list[Suggestion] = field(default_factory=list)
    everything: tuple[str, str] | None = None      # (label, href) for "the whole table"


def _board_suggestion(slug: str) -> Suggestion:
    b = boards.BY_SLUG[slug]
    return Suggestion(title=b.title, subtitle=b.subtitle, definition=b.definition, board=slug)


SECTIONS: dict[str, Section] = {
    "990s": Section(
        "990s", "School 990s", "/schools/990s",
        "Colleges themselves rarely file Form 990, but the nonprofits around them do: foundations, athletic "
        "associations, alumni groups, research corporations. These lists rank schools by what those affiliated "
        "nonprofits report.",
        [
            Suggestion("Richest affiliated nonprofits", "Schools whose affiliated nonprofits report the most revenue "
                       "on their latest Forms 990.", REPORT_CARD, "org_revenue", "990"),
            Suggestion("Most money in the bank", "Largest net assets held by a school's affiliated nonprofits.",
                       REPORT_CARD, "org_net_assets", "990"),
            Suggestion("Top earners at affiliated nonprofits", "The highest-paid person on any of a school's "
                       "affiliated nonprofits' 990s.", REPORT_CARD, "org_top_pay", "990", person="org_top_person"),
            Suggestion("Most grants received", "Grants to a school's affiliated nonprofits, as reported by the "
                       "foundations and charities that made them.", REPORT_CARD, "grants_received", "990",
                       person="top_funder", person_label="top funder"),
            Suggestion("Most spent on fundraising events", "Direct costs of fundraising events (990 line 8b) at a "
                       "school's affiliated nonprofits.", REPORT_CARD, "event_direct", "990"),
            Suggestion("Most affiliated nonprofits", "Schools with the most nonprofits matched to them by exact "
                       "name.", REPORT_CARD, "n_orgs", "990"),
        ],
        ("Every school with its 990 columns (Report Card, 990 view)", "/boards/schools?view=990")),
    "pay": Section(
        "pay", "School pay data", "/schools/pay",
        "Public universities publish their payrolls; we load them person by person. These boards rank the people "
        "and the schools.",
        [_board_suggestion(s) for s in ("uni-top-paid", "uni-athletics", "coaches", "uni-admin-faculty", "uni-pay-jump")]
        + [Suggestion("Biggest payrolls by school", "Total published payroll, school by school, with headcount, top "
                      "pay and IPEDS faculty salary averages.", REPORT_CARD, "payroll_total", "pay",
                      person="top_person", person_label="top paid")],
        ("Every school with its pay columns (Report Card, pay view)", "/boards/schools?view=pay")),
    "student-loans": Section(
        "student-loans", "Student loan data", "/schools/student-loans",
        "Two kinds of student loan data: trusts that hold pools of student loans and report to the SEC every "
        "month, and the Department of Education's default rates for each school's borrowers.",
        [_board_suggestion(s) for s in ("student-loan-largest", "student-loan-delinquency", "student-loan-deterioration",
                                        "student-loan-defaults", "student-loan-chargeoffs")]
        + [Suggestion("Highest federal cohort default rates", "The share of a school's federal student loan "
                      "borrowers who defaulted within three years of entering repayment (Department of Education).",
                      REPORT_CARD, "cdr_rate", "loans")],
        ("Every trust, issuer and month (student loan securitization report)", "/student-loans")),
}


def _empty_filters(sort: str | None = None) -> dict:
    from app.main import BOARD_EXTRA_FILTERS
    return {"year": None, "form": None, "state": None, "all": None, "sort": sort, "dir": None,
            **{k: None for k in BOARD_EXTRA_FILTERS}}


def top3(s: Suggestion) -> list[dict]:
    """[{name, url, value, extra, year}] for a suggestion's top three; [] if its board isn't built."""
    b = boards.BY_SLUG.get(s.board)
    meta = boards.meta()
    if b is None or b.slug not in meta:
        return []
    try:
        if s.sort:
            rows = boards.page(b, _empty_filters(s.sort), 1, per_page=3)["rows"]
            col = next((c for c in b.columns if c.key == s.sort), None)
            fmt, label = (col.fmt, col.label) if col else (b.value.fmt, b.value.label)
            key = s.sort
        else:
            rows = boards.top(b, 3)
            fmt, label, key = b.value.fmt, b.value.label, "value"
    except Exception:  # noqa: BLE001 - a view mid-rebuild: show the suggestion without its top three
        log.exception("schools: top three for %s", s.title)
        return []
    out = []
    for r in rows:
        if r.get(key) is None:
            continue
        name = r.get(s.person) if s.person else None
        out.append({"name": r.get("subject_name"), "url": r.get("subject_url"),
                    "value": boards.fmt(r.get(key), fmt) + unit(fmt, label),
                    "extra": (f"{s.person_label}: {name}" if s.person_label else name) if name else None,
                    "year": r.get("tax_year")})
    return out


def unit(fmt: str, label: str) -> str:
    """Rates and ratios are plain numbers in boards.fmt; their labels say what they are ("Default rate (%)")."""
    if fmt.rstrip("?") != "ratio":
        return ""
    if "(%)" in label:
        return "%"
    if "(points)" in label:
        return " points"
    return "x"


def section_context(key: str) -> dict:
    sec = SECTIONS[key]
    return {"section": sec, "items": [(s, top3(s)) for s in sec.suggestions]}


def overview_context() -> dict:
    """The /schools page: each section with its first three suggestions and their leaders."""
    return {"sections": [(sec, [(s, top3(s)[:1]) for s in sec.suggestions[:3]]) for sec in SECTIONS.values()]}


def view_columns(board: boards.Board, view: str | None):
    """The Report Card's columns for a topic view, or None for every column."""
    if board.slug != REPORT_CARD or view not in VIEWS:
        return None
    keep = VIEWS[view]
    return [c for c in board.columns if c.key in keep]


def crumb(board: boards.Board, view: str | None) -> tuple[str, str] | None:
    """(label, href) of the Schools page a school board belongs to, for its breadcrumb."""
    if board.slug == REPORT_CARD:
        sec = {"990": "990s", "pay": "pay", "loans": "student-loans"}.get(view or "")
        return (SECTIONS[sec].title, SECTIONS[sec].path) if sec else ("Schools", "/schools")
    if board.group == "student-loans":
        return SECTIONS["student-loans"].title, SECTIONS["student-loans"].path
    if board.group == "schools":
        return SECTIONS["pay"].title, SECTIONS["pay"].path
    return None
