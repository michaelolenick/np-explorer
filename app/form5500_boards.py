"""Leaderboards for Form 5500 pension and benefit plan filings (app/form5500.py, loader/form5500.py): the sponsors
with the most plans, the nonprofits with the most plans, long-running sponsors whose filings stopped, and sponsors
that also take federal money or lobby (usa_recipient_totals by EIN, xlinks). One row per sponsor EIN
(form5500_sponsors); Year = the latest plan year filed. Shown unless FORM5500_PUBLIC=0 (owner, 2026-11-13)."""

from __future__ import annotations

GROUP_NAME = "benefit-plans"
GROUP = {"title": "Pension and benefit plans", "subtitle": "The Plan Sponsors",
         "definition": "Employers sponsoring the most pension, 401(k) and welfare plans, the nonprofits with the most "
                       "plans, long-running sponsors whose filings stopped, and plan sponsors that are also big "
                       "federal award recipients or lobby Washington. From Department of Labor Form 5500 filings."}
SOURCE = ("From the Form 5500 and 5500-SF annual returns the Department of Labor publishes (plan years 2009 on; "
          "the one-participant 5500-EZ is not published). A sponsor is one employer identification number; plans "
          "are the distinct plan numbers filed under it and filings are every annual return, so a sponsor filing for "
          "one plan every year has one plan and many filings.")


def _sponsors(value: str, where: str, extra: str = "", joins: str = "",
              order: str = "value DESC, filings DESC, subject_key") -> str:
    """One row per sponsor with the standard columns, its plan counts and years, plus extra columns. org_name is
    the nonprofit with the sponsor's EIN, when there is one."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'f5500_sponsor'::text AS subject_kind, s.ein AS subject_key, s.name AS subject_name,
               {norm_sql('s.name')} AS subject_norm, '/form5500/sponsor/' || s.ein AS subject_url, NULL::text AS match,
               s.ein, o.name AS org_name, s.state, '5500'::text AS form_type, s.last_year::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value,
               CASE WHEN o.ein IS NOT NULL THEN '/org/' || o.ein END AS org_url, NULL::text AS source_url,
               s.plans, s.filings, s.first_year::int AS first_year, s.last_year::int AS last_year, s.city,
               s.plan_names[1] AS plan_name{extra}
        FROM form5500_sponsors s LEFT JOIN organizations o ON o.ein = s.ein {joins}
        WHERE s.name IS NOT NULL AND ({where})"""
    return _ranked_by_org(inner, order)


FED = """JOIN (SELECT recipient_ein, sum(total) AS fed_total, sum(n_awards) AS fed_awards,
                     min(fiscal_year) AS fed_first, max(fiscal_year) AS fed_last
              FROM usa_recipient_totals WHERE recipient_ein IS NOT NULL GROUP BY 1) r ON r.recipient_ein = s.ein"""
LDA = """JOIN (SELECT x.src_key AS ein, sum(y.spent) AS lobby_spent, count(DISTINCT y.year) AS lobby_years,
                     min(y.year) AS lobby_first, max(y.year) AS lobby_last
              FROM xlinks x JOIN lda_client_years y ON y.client_id::text = x.dst_key
              WHERE x.src_kind = 'f5500_sponsor' AND x.dst_kind = 'lda_client' GROUP BY 1) lb ON lb.ein = s.ein"""


def form5500_boards() -> list:
    from app.boards import Board, Column
    from app.form5500 import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="f5500", year_label="Latest plan year",
              org_label="Nonprofit", source_label="Department of Labor Form 5500 filings", search=True, unit="sponsor")
    base = [Column("plans", "Plans", "num"), Column("filings", "Filings", "num"), Column("first_year", "First plan year", "year"),
            Column("last_year", "Latest plan year", "year"), Column("city", "City"), Column("plan_name", "A plan")]
    return [
        Board("f5500-most-plans", "Employers sponsoring the most benefit plans", "Plan Factories",
              "Plan sponsors with the most distinct pension, 401(k) and welfare plans on Form 5500 filings, plan years "
              "2009 on.",
              f"Value = distinct plan numbers filed under the sponsor's EIN, all plan years. {SOURCE}",
              _sponsors("s.plans", "s.plans >= 2"), Column("value", "Plans", "num"), base[1:],
              ["Insurance companies and banks top the list: each separate account or collective trust they run for "
               "other employers' plans files as a plan of its own."], **kw),
        Board("f5500-nonprofit-plans", "Nonprofits with the most benefit plans", "Charity Pensions",
              "Organizations that file a Form 990 and sponsor the most pension, 401(k) and welfare plans on Form 5500, "
              "matched by employer identification number.",
              f"Value = distinct plan numbers filed under the nonprofit's EIN, all plan years. The nonprofit is the "
              f"organization with that EIN in the IRS master file. {SOURCE}",
              _sponsors("s.plans", "o.ein IS NOT NULL AND s.plans >= 2",
                        ", o.latest_total_revenue AS revenue, o.latest_num_employees AS employees"),
              Column("value", "Plans", "num"),
              [Column("revenue", "Latest revenue", "money?"), Column("employees", "Employees", "num?"), base[1], base[2],
               base[3], base[5]],
              ["Hospital systems and universities run separate plans for doctors, nurses, faculty and union staff."],
              **{**kw, "unit": "nonprofit"}),
        Board("f5500-gone-quiet", "Long-running plan sponsors whose filings stopped", "Gone Quiet",
              "Sponsors that filed Form 5500 returns for at least ten plan years and then stopped: no filing for the "
              "last three plan years published.",
              f"Value = plan years from the sponsor's first filing to its last, for sponsors with at least ten filings "
              f"whose latest plan year is three or more years before the latest plan year in the data. {SOURCE}",
              _sponsors("s.last_year - s.first_year + 1",
                        "s.filings >= 10 AND s.last_year <= (SELECT max(last_year) FROM form5500_sponsors) - 3"),
              Column("value", "Years of filings", "num"), base,
              ["A merger, a sale, a plan terminated and paid out, a move to a professional employer organization or "
               "a change of EIN all end a sponsor's filings; a plan that stopped filing while still running is the "
               "case to check."], **kw),
        Board("f5500-federal-awards", "Plan sponsors that take the most federal money", "Pensions and Public Money",
              "Employers sponsoring benefit plans that are also federal award recipients in USAspending, matched by "
              "employer identification number, ranked by the federal money obligated to them.",
              f"Value = federal contract and assistance obligations (all fiscal years loaded) to recipients with the "
              f"sponsor's EIN. {SOURCE}",
              _sponsors("r.fed_total", "r.fed_total > 0", ", r.fed_awards, r.fed_first, r.fed_last", FED),
              Column("value", "Federal awards", "money"),
              [Column("fed_awards", "Award records", "num"), Column("fed_first", "First fiscal year", "year"),
               Column("fed_last", "Latest fiscal year", "year"), base[0], base[1], base[3]],
              ["State agencies and universities receive formula grants that dwarf any contractor."], **kw),
        Board("f5500-lobbying", "Plan sponsors that spend the most on lobbying", "Benefits and Lobbyists",
              "Employers sponsoring benefit plans that are also clients on federal Lobbying Disclosure Act reports, "
              "ranked by lobbying spending.",
              f"Value = lobbying spending (income lobbying firms reported from the client plus the client's own reported "
              f"expenses, all years loaded) for the lobbying clients linked to the sponsor by EIN or by name and "
              f"state (loader/xlinks.py). {SOURCE}",
              _sponsors("lb.lobby_spent", "lb.lobby_spent > 0", ", lb.lobby_years, lb.lobby_first, lb.lobby_last", LDA),
              Column("value", "Lobbying", "money"),
              [Column("lobby_years", "Years lobbying", "num"), Column("lobby_first", "First year", "year"),
               Column("lobby_last", "Latest year", "year"), base[0], base[1], base[3]],
              ["Name-and-state matches can join a sponsor to a different company with the same name; the sponsor's "
               "page lists every link."], **kw),
    ]


ALTERNATIVES = {
    "f5500-most-plans": ["Plan Factories", "Benefits by the Hundred", "The Plan Administrators"],
    "f5500-nonprofit-plans": ["Charity Pensions", "Nonprofit Nest Eggs", "Mission and Pension"],
    "f5500-gone-quiet": ["Gone Quiet", "Last Filing", "Where Did the Plan Go"],
    "f5500-federal-awards": ["Pensions and Public Money", "Federal Paychecks", "Washington's Employers"],
    "f5500-lobbying": ["Benefits and Lobbyists", "401(k) Street", "Lobbying on Payroll"],
}
