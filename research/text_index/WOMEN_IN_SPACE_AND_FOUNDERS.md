# Women-in-space nonprofits, and founders with no background in the field

FURP research, 2026-10-28. Data: FURP's text index over e-filed 990s (`research/text_index`) and the new-nonprofit pay
tables (`research.npay_*`). Medians only, with n beside every number. Saved SQL and scripts are in
`research/text_index/` (`women_in_space.sql`, `wis_rows.py`, `founders.sql`, `founders_matched.sql`).

**FUZZY.** The women-in-space cohort rests on an outer-space flag (the outer-space term list OR
`anthropic/claude-haiku-5.5` via OpenRouter, run 2026-10-28). Hand-checked precision is **roughly two-thirds** (66 of
100 flagged orgs were really about outer space; 85 of 100 counting aerospace). Founder links are by name and state.

## Executive summary

**Question 1: women-in-space nonprofits**

- **603 orgs** match at least one women-in-space row (`research.wis_rows2`, used as is). Roughly two-thirds precision
  applies, and a separate Haiku yes/no confirmed 306 of the 603 as being about outer space. 561 are still filing
  (a return for 2023 or later).
- They are mostly mid-sized to large. Median latest revenue is **$1.22M** (n=602). 111 have revenue under $100K,
  177 have $100K to $1M, 147 have $1M to $10M and 167 have over $10M. The big ones (Smithsonian, science museums, Girl
  Scout councils, girls' schools, the SETI Institute) mention women or girls and space in the same text.
- **Who funds them.** 515 of the 603 received at least one grant listed on another filer's Schedule I: 48,718
  grant lines, $14.2B in total. The total is dominated by a few large institutions that mention space only
  incidentally. Mayo Clinic alone accounts for $2.6B, mostly from its own affiliates. The median org received
  **$1.14M** in listed grants over all years (n=515). The most frequent funders are donor-advised fund sponsors:
  - Fidelity Charitable, 309 orgs
  - DAF Charitable Giving, 271
  - National Philanthropic Trust, 180
  - Silicon Valley Community Foundation, 78
- **Pay.** These are the cohort orgs founded 2010-2020 (n=127), against all nonprofits founded 2010-2020
  (n=183,802):

  | | Women in space | All nonprofits |
  |---|---|---|
  | Ever paid anyone | 72% (91 of 127) | 48% |
  | Median years to first pay, among those ever paid | 1 (n=91) | 2 (n=88,685) |
  | Median top comp, year 1 | $1,330 (n=73) | $0 (n=93,697) |
  | Median top comp, year 3 | $13,732 (n=94) | $0 (n=115,754) |
  | Median top comp, year 5 | $0 (n=103) | $0 (n=120,679) |
  | Ever paid two people $50K+ | 22.0% | 7.4% |

  They start paying sooner and pay more people well. The cohort is small and skews toward orgs big enough to file
  long narrative text, so read this as direction, not size.

**Question 2: founders with no visible background in the field (founded 2010-2020)**

- **Founders and link confidence.** A founder (the top officer on the first return) was identified for 159,933 of
  183,802 orgs (87%). 86% of those links are low confidence: the name has no middle initial, or it is shared by
  another person in FURP.
- **Successful orgs, $500K+ peak revenue.** Of 44,026, **14.9%** of founders had a visible prior nonprofit role,
  6.5% one in the same NTEE sector and 7.4% one in the org's field. **84.2% had no visible background at all.**
- **Successful orgs, $1M+.** Of 27,895: 19.0% prior role, 8.8% same sector, 80.2% no visible background.
- **Orgs that never passed $100K.** Of 51,772: 3.6% prior role, 1.0% same sector, 95.4% no visible background.
- **Does the gap survive matching?** Yes, though it narrows. Matched on founding year, number of returns filed and
  years observed:

  | | Successful ($500K+) | Never passed $100K | Gap |
  |---|---|---|---|
  | Unmatched | 14.9% | 3.6% | 4.1x |
  | Matched | 14.9% | 5.4% | 2.8x |

  Same sector, matched: 6.5% vs 1.6%. For $1M+ orgs, matched: 19.0% vs 5.5%. High-confidence links only, matched:
  13.8% vs 3.7%. Visibility explains part of the gap, not all of it.
- **Women-in-space founders** (n=119 with a founder; 20 high confidence):
  - Any prior nonprofit role: 9 (7.6%).
  - A prior role in women's issues, girls' programs, STEM/science or space: 6 (5.0%).
  - No visible background: 110 (92.4%).
  - $500K+ orgs, 7 of 60 had a prior role; orgs that never passed $100K, 2 of 16. That is too few to compare.
- **Limits.** FURP sees only public filings. "No visible background" means no record in our data, not no
  experience. 990 e-file data starts with 2010-2011 returns, so founders of early cohorts have little visible history.
  The other sources are thin for this:
  - Payroll links exist for only 1,331 people.
  - Form D and ADV roles before founding matched 67 orgs.
  - Patents matched 75 orgs.
  - Business registries matched 1,614 orgs.

---

## Full report

### 1. Women-in-space cohort

**Definition** (`research.wis_rows2`). Every row requires the outer-space flag. The text read is mission, program
descriptions and Schedule O.

- r1: the flag plus a mention of women or girls that Haiku labeled an issue or an incidental mention (not a name).
- r3-r7: women or girls in the same sentence as one of the following:
  - aerospace (r3)
  - astronaut (r4)
  - astronomy or astronomer (r5)
  - "girls/women in STEM" plus a space word (r6)
  - rocketry, satellite, astronaut or spacecraft, with girls (r7)

| Disjoint bucket (each org once, most specific first) | Orgs |
|---|---|
| women + astronomy | 16 |
| women + astronaut | 11 |
| women + aerospace | 33 |
| girls/women in STEM + space word | 9 |
| girls + rocketry/satellite/spacecraft | 7 |
| flag + women/girls mention only | 527 |
| **Total (at least one row)** | **603** |

**Fixes made along the way.**

- **Missing text.** Joining the text fields lost orgs with a missing field. Fixed with coalesce.
- **Too-strict phrases.** Exact phrases ("women in astronomy") found 0 orgs. Words-anywhere was mostly incidental:
  2 of 20 sampled aerospace hits were real, 0 of 20 astronomy hits. Same-sentence matching is used instead.
- **Missed outer-space orgs.** Orgs that use outer-space terms but never the word "space" (astronomy, NASA,
  planetarium) were never flag candidates. 899 were added; `questions.sql` now includes them.

**Flag accuracy.** The hand check covered 200 orgs (`space_label_check.csv`).

| | Outer space | Aerospace only | Not space |
|---|---|---|---|
| Flagged, n=100 | 66 | 19 | 15 |
| Not flagged but using a space word, n=100 | 1 | — | 99 |

Recall is about 79%, but with a wide range (roughly 40-99%) because only one miss turned up.

**Revenue and contributions by year** (all cohort orgs filing that year):

| Tax year | Orgs | Total revenue | Contributions | Median revenue | Median officer comp | Median top comp |
|---|---|---|---|---|---|---|
| 2011 | 327 | $25.4B | $5.8B | $3.81M | $258,932 | $127,500 |
| 2014 | 421 | $28.9B | $6.4B | $2.67M | $230,170 | $104,556 |
| 2017 | 452 | $29.9B | $7.4B | $2.39M | $220,000 | $101,769 |
| 2020 | 524 | $38.0B | $10.3B | $1.54M | $205,775 | $96,674 |
| 2022 | 553 | $39.1B | $10.5B | $1.41M | $239,196 | $95,615 |
| 2024 | 540 | $47.8B | $10.9B | $1.78M | $224,677 | $109,654 |

**Per-org detail** (in the repo):

- `wis_profile.csv`: name, EIN, state, ruling year, NTEE and latest revenue.
- `wis_years.csv`: every year from the first e-filed return, with these columns:
  - revenue, contributions and officer comp total
  - the highest-paid person's name, title and comp
  - the count paid $50K or more
- `wis_funders.csv`: every Schedule I grant in, with grantor name and EIN, amount, year and purpose.

Grants listed without the recipient's EIN are not counted.

**Largest funders by dollars.** Mayo Clinic, $1.97B to 12 cohort orgs (its own affiliates). Fidelity Charitable,
$1.01B to 309. Spelman College Special Ventures Fund, $560M to 1. The Atlantic Coast Conference and the Big 12 paid
member universities. Then the Corporation for Public Broadcasting, Silicon Valley Community Foundation and National
Philanthropic Trust.

**Summary against the pay-study baselines** (same definitions as `research/new_nonprofit_pay.md`; cohort orgs founded
2010-2020):

| | Women in space (n=127) | All nonprofits (n=183,802) |
|---|---|---|
| Ever paid anyone | 91 (72%) | 88,685 (48%) |
| Median years until anyone was paid | 1 | 2 |
| Median top comp, year 1 | $1,330 (n=73) | $0 (n=93,697) |
| Median top comp, year 3 | $13,732 (n=94) | $0 (n=115,754) |
| Median top comp, year 5 | $0 (n=103) | $0 (n=120,679) |
| Ever paid two people $50K+ | 22.0% | 7.4% |

Whole cohort: 603 orgs, 561 still filing, median latest revenue $1.22M (n=602).

### 2. Founders

**Method** (`founders.sql`, `founders_matched.sql`).

- **Founder:** the executive director or CEO on the org's first 990 / 990-EZ, else the president, else the chair.
  Vice, past, interim and similar titles are excluded.
- **Prior record:** any of these, dated before the ruling year:
  - a 990 role at another org (by person cluster)
  - Form D or Form ADV
  - public payroll
  - a patent
  - a state business registration
- **Same sector:** a prior 990 org in the same NTEE major group.
- **In field:** same sector, or a prior org sharing one of the new org's text-index senses.
- **Women-in-space background:** a prior org with women's issues, girls' programs, research/education (STEM) or
  outer space.
- **Confidence:** "high" means the name has a middle name or initial and is unique in FURP.

**Unmatched shares** (founder identified):

| Group | n | Any prior nonprofit role | Same sector | In field | No visible background |
|---|---|---|---|---|---|
| All founded 2010-2020 | 159,933 | 7.1% | 2.6% | 3.0% | 91.9% |
| Successful, $500K+ | 44,026 | 14.9% | 6.5% | 7.4% | 84.2% |
| Successful, $1M+ | 27,895 | 19.0% | 8.8% | 9.9% | 80.2% |
| Never passed $100K | 51,772 | 3.6% | 1.0% | 1.1% | 95.4% |
| $500K+, high confidence only | 5,728 | 13.8% | 6.6% | 7.5% | 79.7% |
| Never passed $100K, high confidence only | 7,425 | 2.2% | 0.8% | 0.8% | 90.3% |

**Matched** (small orgs reweighted to the successful orgs' mix of founding year x returns filed x years observed):

| Measure | $500K+ | Never >$100K, raw | Never >$100K, matched |
|---|---|---|---|
| Any prior nonprofit role | 14.9% | 3.6% | 5.4% |
| Same sector | 6.5% | 1.0% | 1.6% |
| In field | 7.4% | 1.1% | 1.8% |
| No visible background | 84.2% | 95.4% | 93.6% |

For $1M+ orgs, matched: 19.0% vs 5.5% any prior role. High confidence only, matched: 13.8% vs 3.7% ($500K+) and
18.0% vs 3.9% ($1M+). **The gap survives matching.** It shrinks from about 4x to about 3x, so how visible an org is
explains part of it, but not most.

**Women-in-space founders** (orgs founded 2010-2020: n=127, 119 with a founder, 20 high confidence):

| | Count |
|---|---|
| Any prior nonprofit role | 9 |
| Prior role in the same sector | 3 |
| Prior role in women's issues, girls, STEM or space | 6 |
| No visible background at all | 110 |
| $500K+ orgs with a prior role | 7 of 60 |
| Never-$100K orgs with a prior role | 2 of 16 |

### Limits

- **Public filings only.** "No visible background" means no record in FURP's data, not no experience. Jobs,
  degrees, volunteering and for-profit careers are invisible here.
- **Early cohorts.** 990 e-file data begins with 2010-2011 returns, so 2010-2012 founders have almost no visible prior
  990 history.
- **Fuzzy person matching.** Links are by name and state (86% low confidence); common names can merge different
  people or split one person.
- **Thin non-990 sources.** Payroll links exist for only 1,331 people. Pre-founding Form D/ADV roles matched 67 orgs;
  patents matched 75; business registries matched 1,614.
- **Women-in-space cohort.** Roughly two-thirds precision, and incidental mentions inflate it with large institutions.
  Medians are more reliable than dollar totals.
- **Spend.** OpenRouter spend for this work was under $0.25.
