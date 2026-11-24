# S-1 strategic profile (dev only)

`/s1` and `/s1/<cik>` show what a company told the SEC in its S-1, S-1/A, F-1 or F-1/A: strengths ("Our Competitive Strengths"),
opportunities ("Growth Strategy", "Market Opportunity", "Industry"), weaknesses and threats (the Risk Factors, grouped into
nine categories and flagged company-specific or boilerplate) and the competitors named in "Competition". Every item keeps the
company's own wording and a link to the passage on EDGAR (the heading's anchor, else a text-fragment link).

- Code: `app/s1profile.py`. Templates `s1_home.html`, `s1_company.html`. Tests `tests/test_s1profile.py`.
- Source: SEC EDGAR through `loader/s1_terms.py` (`primary_document`, throttled, User-Agent naming FURP). Filing list from
  `ipo_filings`, else the submissions API; tickers from `ipo_companies`, else `company_tickers.json`.
- A filing is read on first view (about 10 seconds) and stored in `s1_profile` (created on first use). Bump `VERSION` in
  `app/s1profile.py` after changing the extraction rules; stale rows are rebuilt on the next view.
- Extraction is rules on headings and bold lead-ins. Two optional model calls (`openai_compat`): one plain-language summary per
  quadrant and the competitor names in the Competition text. The page works without them.
- An amendment that changes only a few pages (no sections) is detected (`partial`); the default view falls back to the newest
  complete filing and says so.
- Changes between filings: add `?acc=<accession>&compare=<older accession>`; risks, competitors, strengths and opportunities
  are compared by heading text.
- Release: all routes return 404 unless `S1_PUBLIC=1`. Add it to prod `.env`, merge the branch `s1-profile`, deploy.
- Known gaps: biotech S-1s often have no "Strengths" section; competitor names are missed when the company names none;
  categories are keyword rules, so "other" holds the ones that match nothing.
