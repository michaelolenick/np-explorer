"""Task 1b: write docs/university-pay-catalog.md from the Phase 1 JSON plus loaded record counts."""
import glob
import json
import re

from common import REPO, connect

ORDER = ["TX", "CA", "NY", "FL", "IL", "OH", "PA", "MI", "MN", "IN"]
RANK = {"A": 0, "B": 1, "C": 2, "D": 3}


def md(s):
    if s is None:
        return ""
    if isinstance(s, list):
        s = ", ".join(map(str, s))
    s = re.sub(r"\s+", " ", str(s)).replace("|", "/").strip()
    # Power BI publish-to-web tokens are public but trip secret scanners; shorten them in the doc.
    return re.sub(r"(powerbi\.com/view\?r=)[A-Za-z0-9=_-]{20,}", r"\1<token: see state JSON>", s)


def counts():
    """Records loaded per state and per catalog source id (empty if staging tables do not exist yet)."""
    by_state, by_src = {}, {}
    try:
        conn = connect()
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass('unipay.public_payroll_records')")
            if cur.fetchone()[0]:
                cur.execute("""SELECT id, state, coalesce(rows_loaded,0) FROM unipay.university_pay_sources""")
                for sid, st, n in cur.fetchall():
                    by_src[sid] = n
                    by_state[st] = by_state.get(st, 0) + n
            cur.execute("SELECT id, state, institution, url FROM unipay.university_pay_sources ORDER BY id")
            ids = cur.fetchall()
    except Exception as e:  # noqa: BLE001
        print("db unavailable for counts:", type(e).__name__)
        ids = []
    return by_state, by_src, ids


def main():
    states = {}
    for f in sorted(glob.glob(str(REPO / "data/unipay-states/*.json"))):
        d = json.load(open(f))
        states[d["state"]] = d
    by_state, by_src, ids = counts()
    # catalog ids follow load order: sorted file, then source order
    id_iter = iter([i[0] for i in ids])
    src_ids = {}
    for st in sorted(states):
        for i, _ in enumerate(states[st]["sources"]):
            src_ids[(st, i)] = next(id_iter, None)
    rest = sorted((s for s in states if s not in ORDER), key=lambda s: states[s]["state_name"])
    order = [s for s in ORDER if s in states] + rest

    out = ["# University pay data catalog", "",
           "Phase 1 research of public, person-level pay data for public colleges and universities in all 50 states plus DC. "
           "Each source is also a row in `unipay.university_pay_sources`. Ratings: **A** = clean bulk download/API; "
           "**B** = person-level but needs scraping or PDF/form extraction; **C** = partial (top earners, search-only, request-only); "
           "**D** = nothing usable found.", "",
           "Record counts are rows loaded into `unipay.public_payroll_records` (staging only, not on the site).", "",
           "| State | Systems found | Best rating | Years covered (best source) | Records loaded |",
           "|---|---|---|---|---|"]
    tot = 0
    for st in order:
        d = states[st]
        srcs = sorted(d["sources"], key=lambda s: RANK.get(str(s.get("rating", "D"))[:1], 9))
        best = d.get("best_rating") or (srcs[0].get("rating") if srcs else "D")
        years = md(srcs[0].get("coverage_years"))[:70] if srcs else ""
        n = by_state.get(st, 0)
        tot += n
        out.append(f"| {d['state_name']} ({st}) | {len(d.get('systems_found') or [])}: {md(d.get('systems_found'))[:140]} | {best} | {years} | {n:,} |")
    out += ["", f"Total records loaded: **{tot:,}**", ""]

    for st in order:
        d = states[st]
        out += [f"## {d['state_name']} ({st})", ""]
        out.append(f"Systems: {md(d.get('systems_found'))}  ")
        out.append(f"Best rating: **{d.get('best_rating', '')}**. Records loaded: **{by_state.get(st, 0):,}**.")
        out.append("")
        for i, s in enumerate(d["sources"]):
            sid = src_ids.get((st, i))
            r = str(s.get("rating", ""))[:1]
            out.append(f"### [{r}] {md(s.get('institution'))}" + (f"  (catalog id {sid})" if sid else ""))
            out.append("")
            out.append(f"- System/publisher: {md(s.get('system'))}")
            out.append(f"- URL: {md(s.get('url'))}")
            if s.get("download_url"):
                out.append(f"- Download: {md(s.get('download_url'))}")
            out.append(f"- Format: {md(s.get('format'))}; years: {md(s.get('coverage_years'))}")
            out.append(f"- Coverage: {md(s.get('institutions_covered'))}; employees: {md(s.get('employees'))}")
            out.append(f"- Fields: {md(s.get('fields'))}")
            out.append(f"- Access: login/form required: {s.get('login_or_form')}; terms: {md(s.get('terms'))}; updates: {md(s.get('update_frequency'))}; size: {md(s.get('size'))}")
            if r in ("B", "C") or s.get("blocker"):
                out.append(f"- Blocker: {md(s.get('blocker')) or '(none recorded)'}")
            if s.get("notes"):
                out.append(f"- Notes: {md(s.get('notes'))}")
            if sid and by_src.get(sid):
                out.append(f"- **Loaded: {by_src[sid]:,} records**")
            out.append("")
        for k, label in (("private_extra", "Private institutions / extra"), ("gaps", "Gaps"), ("notes", "State notes")):
            if d.get(k):
                out.append(f"**{label}:** {md(d.get(k))}")
                out.append("")
    (REPO / "docs/university-pay-catalog.md").write_text("\n".join(out) + "\n")
    print("wrote catalog doc;", len(order), "states")


if __name__ == "__main__":
    main()
