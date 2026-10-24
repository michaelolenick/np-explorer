"""Leaderboards for USPTO patents (app/patents.py, loader/patents.py): universities' patents against their federal
research grants, the companies with the most patents and no Form D on file, and the most security interests
recorded against a holder's patents. Built from pat_uni_stats and pat_assignee_orgs (loader/patents.summaries,
links and uni_stats), refreshed after each load (loader/uspto.boards)."""

from __future__ import annotations

GROUP_NAME = "patents"
GROUP = {"title": "Patents", "subtitle": "Patent Pending",
         "definition": "Who holds the most US patents: universities against their federal research grants, "
                       "companies that hold many patents but have filed no Form D, and patent holders with the "
                       "most security interests (loans backed by patents) recorded. From USPTO bulk data."}
SOURCE = ("From USPTO bulk data: PatentsView granted patents, disambiguated (PVGPATDIS, patents filed in the last "
          "20 years) and the USPTO Patent Assignment Dataset (ECORSEXC). A holder is a PatentsView assignee, its name "
          "variants grouped by PatentsView. Links to other records are by name and state (EXACT: identical full "
          "name; FUZZY: legal endings aside).")


def _std(kind: str, key: str, name: str, url: str, match: str, ein: str, org_name: str, state: str, year: str,
         value: str) -> str:
    from app.boards import norm_sql
    return (f"'{kind}'::text AS subject_kind, ({key})::text AS subject_key, {name} AS subject_name, "
            f"{norm_sql(name)} AS subject_norm, {url} AS subject_url, {match}::text AS match, ({ein})::text AS ein, "
            f"{org_name} AS org_name, {state}::text AS state, 'USPTO'::text AS form_type, ({year})::int AS tax_year, "
            f"NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value")


def _universities() -> str:
    from app.boards import _ranked
    inner = f"""
        SELECT {_std('institution', 'u.unitid', 'u.name', "'/institution/' || u.unitid", "NULL", 'u.ein',
                     "(SELECT o.name FROM organizations o WHERE o.ein = u.ein)", 'u.state', "split_part(u.years, '-', 2)",
                     'u.patents')},
               CASE WHEN u.ein IS NOT NULL THEN '/org/' || u.ein END AS org_url,
               u.research_grants,
               CASE WHEN u.research_grants > 0 THEN round(u.patents * 10000000.0 / u.research_grants, 2) END AS per_10m,
               '/institution/' || u.unitid || '#patents' AS source_url
        FROM pat_uni_stats u WHERE u.patents > 0"""
    return _ranked(inner, "value DESC, subject_key")


def _assignees(where: str, value: str) -> str:
    from app.boards import _ranked
    inner = f"""
        SELECT {_std('assignee', 'a.assignee_id', 'a.name', "'/patents/assignee/' || a.assignee_id", "NULL", 'NULL',
                     "concat_ws(', ', a.city, coalesce(a.state, a.country))", 'a.state', 'extract(year FROM a.last_grant)',
                     value)},
               NULL::text AS org_url, a.n_patents, a.n_security, a.first_grant, a.last_grant,
               CASE WHEN EXISTS (SELECT 1 FROM ip_links l WHERE l.src_kind = 'assignee' AND l.src_key = a.assignee_id
                                 AND l.target_kind = 'sec') THEN 'Yes' ELSE '' END AS sec_filer,
               '/patents/assignee/' || a.assignee_id AS source_url
        FROM pat_assignee_orgs a WHERE {where}"""
    return _ranked(inner, "value DESC, subject_key")


def patent_boards() -> list:
    from app.boards import Board, Column
    kw = dict(forms=(), group=GROUP_NAME, kind="patents", year_label="Latest grant", source_label="USPTO bulk data",
              org_label="Place", search=True, unit="holder")
    no_formd = ("NOT a.is_person AND a.assignee_type = 2 AND NOT EXISTS (SELECT 1 FROM ip_links l "
                "WHERE l.src_kind = 'assignee' AND l.src_key = a.assignee_id AND l.target_kind IN ('formd', 'org', 'college'))")
    return [
        Board("patents-universities", "Universities by patents against research grants", "Lab to Patent Office",
              "Colleges and universities ranked by US patents granted to them, next to the federal research grants "
              "they received over the same years, and patents per $10 million of those grants.",
              "Value = patents granted 2021 to 2025 to PatentsView assignees linked to the college (name and state, "
              "governing-board words such as \"Regents of\" set aside). Federal research grants = USAspending "
              "assistance obligations to the college's EIN in fiscal 2021 to 2025 from the National Science "
              "Foundation or the National Institutes of Health, or under a program whose title names research. "
              "Form 990s have no research-spending line, so this is the closest measure FURP has; colleges with no "
              f"EIN on file show Not reported. {SOURCE}",
              _universities(), Column("value", "Patents 2021-2025", "num"),
              [Column("research_grants", "Federal research grants", "money?"),
               Column("per_10m", "Patents per $10M of grants", "ratio")],
              ["A university system's campuses often patent under one name (\"The Regents of the University of "
               "California\"), so the whole system can land on one campus.",
               "Research money also reaches universities through contracts, industry and foundations, none of it "
               "counted here."],
              **{**kw, "org_label": "Nonprofit", "year_label": "Through", "unit": "college"}),
        Board("patents-no-formd", "Companies with the most patents and no Form D", "Patents, No Paperwork",
              "US companies holding the most US patents that have no Form D private-offering filing on record under "
              "their name.",
              "Value = patents granted to the PatentsView assignee (US company or organization), filed in the last 20 "
              "years. Left out: holders linked by name to any Form D issuer, nonprofit or college. Public companies "
              "(SEC filers) sell stock without Form D and are marked. No Form D found by name doesn't mean none was "
              f"filed under another name. {SOURCE}",
              _assignees(no_formd, "a.n_patents"), Column("value", "Patents", "num"),
              [Column("n_security", "Security interests", "num"), Column("sec_filer", "SEC filer", "text")],
              ["Subsidiaries often hold a group's patents under their own names."], **kw),
        Board("patents-security-interests", "Most security interests recorded against patents", "Patents in Hock",
              "Patent holders with the most security interests (patents pledged as loan collateral) recorded "
              "against their patents at the USPTO.",
              "Value = distinct security-interest documents recorded at the USPTO that list at least one patent "
              f"this PatentsView assignee holds. Releases are recorded separately and not subtracted. {SOURCE}",
              _assignees("a.n_security > 0", "a.n_security"), Column("value", "Security interests", "num"),
              [Column("n_patents", "Patents held", "num"), Column("sec_filer", "SEC filer", "text")],
              ["One loan can be recorded more than once (amendments, new lenders joining), and a refinancing "
               "records a new interest."], **kw),
    ]


ALTERNATIVES = {
    "patents-universities": ["Lab to Patent Office", "Ivory Tower Inventions", "Grants to Patents"],
    "patents-no-formd": ["Patents, No Paperwork", "Inventors Without Offerings", "Quiet Patent Holders"],
    "patents-security-interests": ["Patents in Hock", "Pledged Inventions", "Collateral Patents"],
}
