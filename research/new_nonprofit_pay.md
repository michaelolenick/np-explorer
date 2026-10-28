# How long until a new nonprofit pays anyone, and how much?

FURP 990 data, built 2026-10-27. The rerunnable SQL is `research/new_nonprofit_pay.sql` in np-explorer: `psql "$DATABASE_URL" -f research/new_nonprofit_pay.sql`. It builds `research.npay_years` (1,237,859 org-years) and `research.npay_orgs` (484,146 orgs) once, and every number below comes from those two tables.

- **Medians only.** Zeros are kept everywhere, and **n** is shown next to every number.
- **Scope:**
  - Forms: 990 and 990-EZ e-filed returns. 990-N has no pay fields, so it's used only to flag switching. 990-PF is excluded.
  - Cohorts: founding years 2010–2020.
  - No sampling was needed (cohorts have 27k–72k orgs).
  - Each query has a time limit (15 min for the build, 5 min for the stats). The whole build took about 2 minutes.

## Definitions

- **Founding year:** the IRS ruling year. The IRS publishes no founding date. See data quality item 1.
- **Year k:** tax year minus founding year.
- **Officer comp:** total pay to officers, directors and key employees (990 Part I line 5; 990-EZ Part IV).
- **Salaries:**
  - 990: Part IX lines 5–7 (officer pay plus all other salaries and wages).
  - 990-EZ: line 12, which also includes benefits because the EZ doesn't split them out.
- **Top comp:** the highest single compensation paid by the org (990 Part VII-A, 990-EZ Part IV and the EZ's list of highest-paid employees).
- **Paid:** any of the three is above $0.
- **Filers:** cohort orgs with at least one 990 or 990-EZ return.

## Bottom line

- **About half of the filers ever pay anyone.**
  - 48.3% of filers ever pay (n=183,802).
  - Counting orgs that only ever filed a 990-N, or no return at all, the share is 18.3% (n=484,146).
- **Orgs that do start paying usually start early.** The median first paid year is year 2 after founding (n=88,685).
- **The typical new nonprofit pays nobody.**
  - The median officer comp, salaries and top comp across all filers is **$0** in years 1, 3, 5 and 10, in every cohort.
  - The only exception is orgs whose revenue ever reaches $500K or more.
- **Among orgs that are paying by year 5:**
  - median salaries: $72,559 (n=60,107)
  - median officer comp: $21,500 (n=60,387)
  - median top individual comp: $14,000 (n=60,387)

  In most paying orgs, the money goes to staff rather than to one well-paid executive.
- **Two or more people at $50K or more is rare.**
  - 7.4% of filers ever get there (n=183,802).
  - The median time to get there is 4 years.
  - Above $1M in peak revenue, the share is 35.9%.

## 1. Ever paid, and years to first pay, by cohort

Cohorts from 2010 on appear to pay sooner, but most of that is a data artifact, not a real trend:

- **Ever paid:** later cohorts have had fewer years in which to start paying.
- **Paid by year 3 and year 5:** older cohorts are missing early returns, because small orgs could paper-file before about 2020 (data quality item 3).

| Cohort | Cohort orgs | Filers | % of filers ever paid | % of all ever paid | n paid | Median years to first pay | % of filers paid by yr 3 | % of filers paid by yr 5 |
|---|---|---|---|---|---|---|---|---|
| 2010 | 27,805 | 11,907 | 52.1 | 22.3 | 6,200 | 3 | 26.7 | 33.7 |
| 2011 | 28,198 | 11,894 | 52.3 | 22.1 | 6,225 | 3 | 28.4 | 35.0 |
| 2012 | 26,855 | 11,454 | 50.3 | 21.5 | 5,761 | 3 | 28.8 | 34.7 |
| 2013 | 34,608 | 11,108 | 50.8 | 16.3 | 5,640 | 2 | 30.1 | 36.0 |
| 2014 | 71,604 | 27,704 | 47.3 | 18.3 | 13,110 | 2 | 28.4 | 34.3 |
| 2015 | 47,587 | 18,782 | 49.7 | 19.6 | 9,328 | 2 | 30.1 | 38.8 |
| 2016 | 46,909 | 18,078 | 47.8 | 18.4 | 8,639 | 2 | 30.6 | 40.0 |
| 2017 | 45,925 | 16,829 | 47.3 | 17.3 | 7,967 | 2 | 33.2 | 41.7 |
| 2018 | 46,833 | 16,558 | 45.9 | 16.2 | 7,595 | 2 | 35.2 | 42.4 |
| 2019 | 58,293 | 21,482 | 46.1 | 17.0 | 9,895 | 1 | 38.6 | 45.0 |
| 2020 | 49,529 | 18,006 | 46.2 | 16.8 | 8,325 | 1 | 41.5 | 46.2 |
| **All** | **484,146** | **183,802** | **48.3** | **18.3** | **88,685** | **2** | **32.3** | **39.3** |

**Sensitivity check.** Some returns report pay of $1–$9. If "paid" means at least $1,000 in a year, 47.4% of filers ever paid (n=87,213 of 183,802), with the same median of 2 years. Every cohort moves by less than 1.2 points.

## 2. Pay at years 1, 3, 5 and 10 (all cohorts pooled)

**All filers that year, zeros included:** the median officer comp, salaries and top comp are **$0** at every year, both pooled and in every single cohort. Here is how many filers that covers at each year:

| Year | Filers that year |
|---|---|
| 1 | 93,697 |
| 3 | 115,754 |
| 5 | 120,679 |
| 10 | 64,215 |

**Orgs already paying by that year.** These orgs had their first paid year at or before year k. Their medians still include $0 for years in which they paid nobody.

| Year | n paying | Median officer comp | n with a salary line | Median salaries | Median top comp |
|---|---|---|---|---|---|
| 1 | 38,467 | $20,000 | 38,361 | $66,009 | $14,475 |
| 3 | 54,329 | $21,560 | 54,129 | $70,417 | $15,000 |
| 5 | 60,387 | $21,500 | 60,107 | $72,559 | $14,000 |
| 10 | 34,390 | $23,045 | 34,172 | $79,827 | $13,929 |

Year 10 exists only for the 2010–2015 cohorts. For the 2015 cohort, year 10 is tax year 2025, which is still only partly filed. The tables per cohort are in the appendix.

## 3. By size bucket (peak revenue across all of the org's returns)

Excluded here: 895 filers whose returns report no revenue figure.

**Ever paid**

| Peak revenue | Filers | n paid | % ever paid | Median years to first pay |
|---|---|---|---|---|
| Under $100K | 60,887 | 11,907 | 19.6 | 3 |
| $100K–$500K | 72,900 | 37,521 | 51.5 | 3 |
| $500K–$1M | 18,253 | 13,571 | 74.3 | 1 |
| Over $1M | 30,867 | 25,669 | 83.2 | 1 |

By cohort, the share that ever paid is flat within each bucket:

| Peak revenue | % ever paid, range across cohorts |
|---|---|
| Under $100K | 19–21% |
| $100K–$500K | 50–53% |
| $500K–$1M | 72–76% |
| Over $1M | 78–87% |

The median years to first pay falls for later cohorts, which is the same artifact explained in section 1. The full breakdown by cohort is in the SQL output.

**Medians, all filers in the bucket, zeros included**

| Peak revenue | Year | n | Officer comp | n salaries | Salaries | Top comp |
|---|---|---|---|---|---|---|
| Under $100K | 1 / 3 / 5 / 10 | 24,492 / 28,630 / 29,527 / 14,835 | $0 | 22,730 / 26,647 / 27,592 / 14,029 | $0 | $0 |
| $100K–$500K | 1 / 3 / 5 / 10 | 35,681 / 47,041 / 50,891 / 27,595 | $0 | 35,249 / 46,667 / 50,510 / 27,373 | $0 | $0 |
| $500K–$1M | 1 | 11,175 | $0 | 11,066 | $10,958 | $0 |
| $500K–$1M | 3 | 14,025 | $0 | 13,942 | $35,241 | $0 |
| $500K–$1M | 5 | 14,407 | $0 | 14,317 | $51,447 | $0 |
| $500K–$1M | 10 | 7,779 | $0 | 7,733 | $69,432 | $0 |
| Over $1M | 1 | 22,096 | $6,038 | 21,785 | $108,000 | $0 |
| Over $1M | 3 | 25,795 | $34,000 | 25,627 | $180,569 | $22,795 |
| Over $1M | 5 | 25,613 | $51,320 | 25,435 | $247,769 | $39,000 |
| Over $1M | 10 | 13,926 | $77,743 | 13,833 | $380,269 | $63,970 |

**Medians, orgs already paying by that year**

| Peak revenue | Year | n paying | Officer comp | n salaries | Salaries | Top comp |
|---|---|---|---|---|---|---|
| Under $100K | 1 | 3,092 | $465 | 3,053 | $7,167 | $9 |
| Under $100K | 3 | 4,598 | $0 | 4,506 | $5,963 | $0 |
| Under $100K | 5 | 5,429 | $0 | 5,316 | $5,435 | $0 |
| Under $100K | 10 | 3,030 | $0 | 2,950 | $3,702 | $0 |
| $100K–$500K | 1 | 13,346 | $8,344 | 13,319 | $32,400 | $5,400 |
| $100K–$500K | 3 | 20,696 | $7,800 | 20,632 | $35,789 | $4,651 |
| $100K–$500K | 5 | 24,282 | $7,079 | 24,199 | $36,763 | $3,016 |
| $100K–$500K | 10 | 13,892 | $3,552 | 13,810 | $36,943 | $0 |
| $500K–$1M | 1 | 6,478 | $23,521 | 6,467 | $75,224 | $16,000 |
| $500K–$1M | 3 | 9,247 | $30,000 | 9,233 | $95,000 | $20,000 |
| $500K–$1M | 5 | 10,117 | $35,525 | 10,091 | $108,934 | $23,077 |
| $500K–$1M | 10 | 5,714 | $40,078 | 5,697 | $132,214 | $25,121 |
| Over $1M | 1 | 15,547 | $65,546 | 15,522 | $260,623 | $51,680 |
| Over $1M | 3 | 19,781 | $76,500 | 19,758 | $331,110 | $62,000 |
| Over $1M | 5 | 20,553 | $85,100 | 20,501 | $393,212 | $70,000 |
| Over $1M | 10 | 11,753 | $101,923 | 11,715 | $522,983 | $85,000 |

**Under $100K.** The small paying orgs mostly pay a little staff time, and many stop paying again: median salaries are $5–7K, and the median top comp is $0 from year 3 on.

**Officer comp vs top comp.** A median officer comp above the median top comp is not a contradiction. Officer comp sums everyone listed, while top comp is the single highest amount.

## 4. Two or more people paid at least $50K each on the same return

| Group | Filers | n reached | % reached | Median years to get there |
|---|---|---|---|---|
| Cohort 2010 | 11,907 | 1,182 | 9.9 | 7 |
| Cohort 2011 | 11,894 | 1,114 | 9.4 | 6 |
| Cohort 2012 | 11,454 | 957 | 8.4 | 6 |
| Cohort 2013 | 11,108 | 988 | 8.9 | 5 |
| Cohort 2014 | 27,704 | 2,093 | 7.6 | 4 |
| Cohort 2015 | 18,782 | 1,497 | 8.0 | 4 |
| Cohort 2016 | 18,078 | 1,289 | 7.1 | 4 |
| Cohort 2017 | 16,829 | 1,103 | 6.6 | 3 |
| Cohort 2018 | 16,558 | 1,013 | 6.1 | 3 |
| Cohort 2019 | 21,482 | 1,319 | 6.1 | 2 |
| Cohort 2020 | 18,006 | 1,136 | 6.3 | 2 |
| Under $100K | 60,887 | 24 | 0.04 | 4.5 |
| $100K–$500K | 72,900 | 953 | 1.3 | 5 |
| $500K–$1M | 18,253 | 1,624 | 8.9 | 5 |
| Over $1M | 30,867 | 11,087 | 35.9 | 3 |
| **All** | **183,802** | **13,691** | **7.4** | **4** |

These counts are lower bounds:

- The 990 lists an employee who isn't an officer, director or key employee only when they earn over $100K.
- The 990-EZ lists employees only when they earn over $50K.

So two staff members paid $60K each at a 990 filer usually don't appear. The falling median years for later cohorts is the same artifact explained in section 1.

## Data quality flags

1. **Survivorship bias (the biggest issue).**
   - The ruling year comes from the IRS's current Business Master File.
   - The 1,392,339 orgs that have left it (revoked, terminated or merged) have no ruling year, so they are in no cohort.
   - So every cohort contains only orgs that still exist in 2026. This most likely overstates how many orgs ever pay.
   - Another 11,554 orgs that are in the BMF have no ruling year either.
2. **Ruling year is not founding year.**
   - 30,868 cohort orgs filed a return before their ruling year (the IRS rules retroactively, and many orgs operate before they apply).
   - For 11,052 orgs, the first paid year comes before the ruling year, giving negative "years to first pay". These are kept, not clamped.
3. **E-file coverage favors later years.**
   - Before mid-2021, small orgs could paper-file the 990-EZ, and paper returns aren't in the e-file data.
   - The share of each cohort's eventual filers that have a year-1 return rises from 37% (2010) to 70% (2020).
   - This is why paid-by-year-3 rises from 26.7% to 41.5% across cohorts, and why first-pay years for the older cohorts are pushed later.
   - 31,643 orgs have gaps between their first and last return.
4. **990-N switching.**
   - 232,633 cohort orgs (48%) only ever filed a 990-N. 67,711 (14%) filed no return we hold at all.
   - 96,429 orgs filed both a 990-N and a 990 or 990-EZ, and 7,866 switched back and forth at least twice.
   - Years filed on a 990-N count as missing, not as $0. They're almost certainly unpaid (revenue at or under $50K), so the "all filers" medians would stay at $0 either way.
5. **Salaries are not like for like.** The 990-EZ salary line includes employee benefits, while the 990 figure excludes them.
6. **Missing salary lines.**
   - 31,672 returns (2.6%) have no parsed expense lines, so salaries are left blank and those returns are left out of the n for salaries.
   - 23,333 returns report officer pay but $0 on the salary lines. That's a filer inconsistency, kept as filed.
7. **Odd values.**
   - 164 returns show top comp more than 5 times revenue (and above $250K), and 4,542 returns show negative revenue. Both are kept as filed.
   - Some returns report $1–$9 of pay. See the $1,000 sensitivity check under section 1.
8. **2014 cohort.** It's 1.5–2.5 times the size of the cohorts around it, because the IRS introduced Form 1023-EZ in July 2014. Most of the extra orgs are tiny.
9. **Tax year 2025 is partial.** That year mostly affects the 2015 cohort at year 10 and the 2020 cohort at year 5, both of which have fewer filers.
10. **Amended returns.** Each org-year keeps one return: the original unless it was superseded, otherwise the latest filed.
11. **Dollars are nominal**, not adjusted for inflation.

## Appendix: by cohort, orgs already paying by that year

| Cohort | Year | n paying | Officer comp | Salaries (n) | Top comp |
|---|---|---|---|---|---|
| 2010 | 1 / 3 / 5 / 10 | 1,832 / 2,833 / 3,482 / 4,853 | $26,225 / $24,982 / $25,358 / $26,882 | $72,300 / $71,358 / $77,930 / $88,513 (1,829 / 2,830 / 3,473 / 4,831) | $21,679 / $19,500 / $19,462 / $17,738 |
| 2011 | 1 / 3 / 5 / 10 | 2,042 / 3,003 / 3,635 / 5,182 | $25,000 / $22,398 / $24,000 / $27,374 | $71,895 / $74,006 / $77,186 / $84,285 (2,040 / 2,998 / 3,624 / 5,158) | $19,340 / $18,000 / $17,600 / $19,290 |
| 2012 | 1 / 3 / 5 / 10 | 2,109 / 2,967 / 3,496 / 4,926 | $18,188 / $19,173 / $21,147 / $24,730 | $64,593 / $69,805 / $68,136 / $81,048 (2,102 / 2,959 / 3,486 / 4,889) | $12,500 / $14,318 / $14,606 / $15,235 |
| 2013 | 1 / 3 / 5 / 10 | 2,234 / 2,990 / 3,532 / 4,872 | $21,221 / $22,287 / $23,411 / $25,228 | $71,023 / $75,950 / $80,364 / $91,000 (2,230 / 2,985 / 3,518 / 4,841) | $15,575 / $15,000 / $15,168 / $15,000 |
| 2014 | 1 / 3 / 5 / 10 | 5,369 / 7,068 / 8,433 / 11,267 | $18,100 / $18,042 / $17,854 / $19,665 | $65,942 / $66,896 / $70,090 / $78,121 (5,361 / 7,042 / 8,399 / 11,189) | $12,480 / $12,000 / $11,630 / $10,800 |
| 2015 | 1 / 3 / 5 / 10* | 3,730 / 5,084 / 6,660 / 3,290 | $20,363 / $21,769 / $21,163 / $16,569 | $68,569 / $70,500 / $70,170 / $54,585 (3,722 / 5,070 / 6,633 / 3,264) | $14,540 / $14,975 / $14,000 / $7,710 |
| 2016 | 1 / 3 / 5 | 3,547 / 5,022 / 6,710 | $21,000 / $20,340 / $22,914 | $68,413 / $69,744 / $72,641 (3,540 / 5,007 / 6,684) | $15,240 / $13,148 / $14,819 |
| 2017 | 1 / 3 / 5 | 3,457 / 5,227 / 6,524 | $18,050 / $20,400 / $22,136 | $64,961 / $66,627 / $76,000 (3,450 / 5,209 / 6,494) | $13,846 / $14,750 / $14,185 |
| 2018 | 1 / 3 / 5 | 3,488 / 5,504 / 6,408 | $19,200 / $21,267 / $21,969 | $62,287 / $66,000 / $73,337 (3,472 / 5,472 / 6,368) | $14,500 / $15,000 / $14,264 |
| 2019 | 1 / 3 / 5 | 5,528 / 7,766 / 8,503 | $19,938 / $22,126 / $22,948 | $64,500 / $72,665 / $78,078 (5,505 / 7,730 / 8,441) | $12,530 / $14,400 / $13,300 |
| 2020 | 1 / 3 / 5* | 5,131 / 6,865 / 3,004 | $21,109 / $24,632 / $14,343 | $64,500 / $75,804 / $50,351 (5,110 / 6,827 / 2,987) | $14,166 / $16,000 / $9,048 |

\* = tax year 2025, still being filed, so the numbers are partial and skew toward early filers.

Filers per cohort that year, all with medians of $0 for all three measures:

| Cohort | Year 1 | Year 3 | Year 5 | Year 10 |
|---|---|---|---|---|
| 2010 | 4,363 | 5,877 | 6,780 | 8,623 |
| 2011 | 4,711 | 6,173 | 6,903 | 9,350 |
| 2012 | 4,942 | 6,205 | 6,831 | 9,062 |
| 2013 | 5,195 | 6,168 | 6,811 | 8,879 |
| 2014 | 13,265 | 15,577 | 17,332 | 21,598 |
| 2015 | 8,862 | 10,712 | 12,868 | 6,703 |
| 2016 | 8,891 | 10,774 | 13,662 | – |
| 2017 | 8,640 | 11,091 | 13,121 | – |
| 2018 | 8,815 | 12,130 | 12,908 | – |
| 2019 | 13,341 | 16,752 | 16,834 | – |
| 2020 | 12,672 | 14,295 | 6,629 | – |
