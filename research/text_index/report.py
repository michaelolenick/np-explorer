"""Write research/text_index/RESULTS.md: what the index holds, how "space" was decided, and the saved questions with
n, organizations and median revenue (owner, 2026-10-28).

Usage (from the np-explorer checkout, .env loaded):  .venv/bin/python research/text_index/report.py
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loader import db  # noqa: E402

OUT = Path(__file__).resolve().parent / "RESULTS.md"


def _n(x) -> str:
    return "–" if x is None else f"{x:,.0f}"


def _money(x) -> str:
    return "–" if x is None else f"${x:,.0f}"


def _pct(a, b) -> str:
    return "–" if not b else f"{100 * (a or 0) / b:.1f}%"


def senses_section(c, md: list[str]) -> None:
    """The ambiguous terms: phrase counts (no model), sense counts (phrases + Haiku), where the term appears, the
    hand-labeled scores, the men / male / boys false hits, and the original questions asked again with clean terms."""
    md.append("## The questions again, with the cleaned terms (organizations)\n")
    md.append("Mentions women / men means the women or men senses \"issues\" or \"incidental\": a real mention, "
              "not just a name (a women's auxiliary, the YMCA). Domestic violence means the DV sense of any of "
              "domestic, violence, abuse, shelter or survivor. Top comp: the highest total pay on the org's latest "
              "return (orgs that list no one paid count as $0).\n")
    md.append("| Question | Orgs | Median revenue | Median top comp |\n|---|---|---|---|")
    clean = c.execute("SELECT i, question, orgs, median_revenue, median_top_comp FROM research.clean_questions "
                      "ORDER BY i").fetchall()
    by = {i: (q, n) for i, q, n, _, _ in clean}
    for i, q, n, rev, top in clean:
        md.append(f"| {q} | {_n(n)} | {_money(rev)} | {_money(top)} |")
    dv = by.get(7, (None, 0))[1]
    if dv:
        md.append(f"\nOf the {_n(dv)} domestic-violence orgs: {_pct(by.get(8, (0, 0))[1], dv)} mention women, "
                  f"{_pct(by.get(9, (0, 0))[1], dv)} mention men, {_pct(by.get(10, (0, 0))[1], dv)} both, "
                  f"{_pct(by.get(11, (0, 0))[1], dv)} neither.")
    sci = by.get(12, (None, 0))[1]
    if sci:
        md.append(f"Of the {_n(sci)} science / STEM orgs, {_pct(by.get(13, (0, 0))[1], sci)} also mention women "
                  "or girls.\n")

    md.append("## Ambiguous terms\n")
    md.append("Each term two ways, side by side: **exact phrases** (the index, no model) and **senses** (every "
              "mention inside one of the phrases takes its sense; the mentions left over were labeled by Claude "
              "Haiku from the org's name, mission and up to three snippets). An org can have several senses. "
              "Phrases that begin with a small word (\"our mission\") can't be searched in the index, so they "
              "appear only in the senses.\n")
    tests = {r[0]: r[1:] for r in c.execute(
        "SELECT topic, n, exact, lenient, misses FROM research.sense_test_results").fetchall()}
    fields = {r[0]: r[1:] for r in c.execute("SELECT * FROM research.sense_fields").fetchall()}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import senses as S
    for topic, t in list(S.TOPICS.items()) + [("space", {"display": "space / aerospace"})]:
        md.append(f"### {t['display']}\n")
        if topic in fields:
            (orgs, name_only, grant_only, in_m, in_p, in_o, in_g, sent, unl) = fields[topic]
            md.append(f"{_n(orgs)} orgs use it. Only in the org's name: {_n(name_only)} ({_pct(name_only, orgs)}); "
                      f"only in grant purposes: {_n(grant_only)} ({_pct(grant_only, orgs)}). In the mission: "
                      f"{_n(in_m)}; program descriptions: {_n(in_p)}; Schedule O: {_n(in_o)}; grant purposes: "
                      f"{_n(in_g)}. Sent to the model (mentions no phrase settled): {_n(sent)}"
                      + (f"; not labeled: {_n(unl)}" if unl else "") + ".\n")
        if topic in tests:
            n, exact, lenient, _ = tests[topic]
            md.append(f"Hand-labeled tricky cases: Haiku exact {exact}/{n}, the right sense among its answers "
                      f"{lenient}/{n}.\n")
        phr = c.execute("""SELECT codes, label, filings, orgs, median_org_revenue FROM research.sense_phrase_counts
                           WHERE topic = %s ORDER BY i""", (topic,)).fetchall()
        if phr:
            md.append("| Exact phrase | Sense | Filings | Orgs | Median revenue |\n|---|---|---|---|---|")
            for codes, label, f, o, med in phr:
                md.append(f"| {label} | {codes} | {_n(f)} | {_n(o)} | {_money(med)} |")
            md.append("")
        sen = c.execute("""SELECT code, sense, orgs, orgs_by_phrase, orgs_by_model, filings, median_org_revenue
                           FROM research.sense_counts WHERE topic = %s ORDER BY orgs DESC""", (topic,)).fetchall()
        if sen:
            md.append("| Sense | Orgs | by phrase | by model | Filings | Median revenue |\n|---|---|---|---|---|---|")
            for code, sense, o, br, bm, f, med in sen:
                md.append(f"| {code} {sense} | {_n(o)} | {_n(br)} | {_n(bm)} | {_n(f)} | {_money(med)} |")
            md.append("")
        if topic == "women":
            md.append("Women, mission vs grant purposes (orgs whose mention is in that field, by sense):\n")
            md.append("| Sense | In mission | In grant purposes | Mission, not grants | Grants, not mission |"
                      "\n|---|---|---|---|---|")
            for code, sense, m, g, mg, gm in c.execute("SELECT * FROM research.sense_women_fields ORDER BY 1"):
                md.append(f"| {code} {sense} | {_n(m)} | {_n(g)} | {_n(mg)} | {_n(gm)} |")
            md.append("")
        if topic == "men":
            md.append("Whole words vs substrings (a random 1% of orgs; \"men\" as a substring also finds women, "
                      "freshmen, Mennonite, abdomen, management...):\n")
            md.append("| Word | Orgs, substring | Orgs, whole word | False-hit orgs before | After |"
                      "\n|---|---|---|---|---|")
            for w, _, sub, whole, top in c.execute("SELECT word, sample_orgs, substring_orgs, wholeword_orgs, "
                                                   "top_false FROM research.sense_falsehits ORDER BY word"):
                md.append(f"| {w} | {_n(sub)} | {_n(whole)} | {_n(sub - whole)} ({_pct(sub - whole, sub)}) | 0 |")
            ex = c.execute("SELECT word, top_false FROM research.sense_falsehits ORDER BY word").fetchall()
            md.append("\nMost common false hits: " + "; ".join(
                f"{w}: " + ", ".join(f"{x} ({k:,})" for x, k in top[:6]) for w, top in ex) + ".\n")
    md.append("Hand-labeled misses (what Haiku said vs the label): see research.sense_test_results.misses.\n")


def main() -> None:
    md = [f"# Topic index: results\n\nBuilt {dt.date.today():%Y-%m-%d}. How it works and the search syntax: "
          "[README.md](README.md). Revenue is each matching org's total revenue on its latest return; medians only.\n"]
    with db.connect() as c:
        c.execute("SET statement_timeout = '10min'")
        md.append("## What's in the index\n\n| Field | Filing rows | Text |\n|---|---|---|")
        for f, n, size in c.execute("""SELECT field, count(*), pg_size_pretty(sum(length(text))::bigint)
                                       FROM research.filing_text GROUP BY 1 ORDER BY 2 DESC""").fetchall():
            md.append(f"| {f} | {_n(n)} | {size or '–'} |")
        orgs, = c.execute("SELECT count(*) FROM research.org_text").fetchone()
        ft, ot = c.execute("""SELECT pg_size_pretty(pg_total_relation_size('research.filing_text')),
                                     pg_size_pretty(pg_total_relation_size('research.org_text'))""").fetchone()
        md.append(f"\n{_n(orgs)} organizations in `research.org_text`. On disk with indexes: filing_text {ft}, "
                  f"org_text {ot}.\n")

        # The senses of "space"
        md.append("## The senses of \"space\" (organizations)\n")
        n_cand, n_term, n_earthly, n_lab = c.execute("""SELECT count(*), count(*) FILTER (WHERE has_term),
                count(*) FILTER (WHERE earthly_only), count(codes) FROM research.space_senses""").fetchone()
        md.append(f"{_n(n_cand)} organizations say \"space\" or \"aerospace\" somewhere. {_n(n_term)} have an "
                  f"unambiguous outer-space term; {_n(n_lab)} were labeled by the model "
                  f"({_n(n_cand - n_lab)} not labeled: failed calls, rerun classify.py). An org can have several "
                  "senses.\n")
        md.append("| Sense | Orgs | of them, all \"space\" mentions are plainly earthly phrases |\n|---|---|---|")
        for col, label in (("outer_space", "O outer space"), ("for_women", "W a space for women or girls"),
                           ("for_men", "M a space for men or boys"), ("facility", "F facility (office, meeting, "
                           "studio, rental)"), ("parking", "P parking"), ("green_open", "G green / open space"),
                           ("safe_personal", "S safe / quiet / personal space"), ("other", "X other")):
            n, e = c.execute(f"SELECT count(*) FILTER (WHERE {col}), count(*) FILTER (WHERE {col} AND earthly_only) "
                             "FROM research.space_senses").fetchone()
            md.append(f"| {label} | {_n(n)} | {_n(e)} |")
        md.append("\nThe last column is a check: an org labeled outer space whose every mention is \"office "
                  "space\" or the like would be suspect.\n")
        for col, label in (("outer_space AND NOT has_term", "outer space (model, no unambiguous term)"),
                           ("for_women", "a space for women or girls"), ("for_men", "a space for men or boys")):
            ex = c.execute(f"""SELECT o.name, left(regexp_replace(coalesce(o.mission_text, ''), '\\s+', ' ', 'g'), 80)
                               FROM research.space_senses s JOIN research.org_text o USING (ein)
                               WHERE {col} ORDER BY md5(s.ein) LIMIT 8""").fetchall()
            md.append(f"Random **{label}**: " + "; ".join(f"{a} ({b})" if b else (a or "?") for a, b in ex) + "\n")

        # The saved questions
        md.append("## The questions\n\nFilings: returns (superseded ones left out) whose text, in any field, "
                  "matches. Orgs: distinct organizations among them.\n")
        md.append("| Question | Filings | Orgs | Median revenue of the orgs | Seconds |\n|---|---|---|---|---|")
        rows = {}
        for view in ("q_space", "q_space_phrases", "q_space_senses", "q_women_in_space", "q_womens_mens_issues",
                     "q_domestic_violence"):
            t = time.time()
            got = c.execute(f"SELECT * FROM research.{view}").fetchall()
            el = time.time() - t
            for q, f, o, med in got:
                rows[q] = (f, o, med)
                md.append(f"| {q} | {_n(f)} | {_n(o)} | {_money(med)} | {el:.1f} (view) |")
        dv = rows.get("domestic violence")
        if dv and dv[0]:
            md.append("\nOf the domestic-violence filings: "
                      f"{100 * rows['domestic violence + women'][0] / dv[0]:.1f}% mention women "
                      f"(n={_n(rows['domestic violence + women'][0])}), "
                      f"{100 * rows['domestic violence + men'][0] / dv[0]:.1f}% mention men "
                      f"(n={_n(rows['domestic violence + men'][0])}), of n={_n(dv[0])}. "
                      f"Of the orgs: {100 * rows['domestic violence + women'][1] / dv[1]:.1f}% and "
                      f"{100 * rows['domestic violence + men'][1] / dv[1]:.1f}% of {_n(dv[1])}.\n")

        senses_section(c, md)

        md.append("## Term lists (the original, word-only questions above)\n")
        for name, label in (("outer_space", "Outer space (unambiguous)"), ("womens_issues", "Women's issues"),
                            ("mens_issues", "Men's issues"), ("domestic_violence", "Domestic violence"),
                            ("women", "Mentions women (for the DV split)"), ("men", "Mentions men (for the DV split)")):
            t, = c.execute("SELECT research.terms(%s)", (name,)).fetchone()
            md.append(f"- **{label}:** `{t}`")
        md.append("\nTerms are stemmed (women also matches women's; girl matches girls). `<->` is a phrase.\n")

        md.append("## Speed check (the query functions)\n\n| Call | Result | Seconds |\n|---|---|---|")
        for call in ("research.topic_count('\"domestic violence\"')",
                     "research.topic_count('\"domestic violence\"', 'orgs')",
                     "research.topic_count('astronaut', 'orgs', 'mission')",
                     "research.topic_count('women <2> space')",
                     "research.topic_count('food bank', 'orgs')",
                     "research.topic_count('space:outer', 'orgs')",
                     "research.topic_count('abuse:domestic')",
                     "research.topic_count('shelter:animal,homeless', 'orgs')"):
            t = time.time()
            n, n_orgs, med, _ = c.execute(f"SELECT * FROM {call}").fetchone()
            md.append(f"| `{call}` | n={_n(n)}, orgs={_n(n_orgs)}, median revenue {_money(med)} | "
                      f"{time.time() - t:.1f} |")
        md.append("\n## Domestic violence by NTEE sector (filings)\n\n| NTEE | Filings | Orgs | Median revenue |"
                  "\n|---|---|---|---|")
        for _, v, n, o, med in c.execute("""SELECT * FROM research.topic_breakdown(research.terms('domestic_violence'))
                                            WHERE dimension = 'ntee_major' ORDER BY n DESC LIMIT 12""").fetchall():
            md.append(f"| {v} | {_n(n)} | {_n(o)} | {_money(med)} |")
    OUT.write_text("\n".join(md) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
