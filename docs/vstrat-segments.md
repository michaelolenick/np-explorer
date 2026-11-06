# Segments from VSTRAT: the FURP contract

VSTRAT's segment tool sends FURP a customer or market segment; FURP answers with the organizations in it (nonprofits,
private companies, or both), as JSON and as a page VSTRAT opens in its own tab. Built 2026-11-06 (app/segments.py).

## Endpoint

    POST https://furp.org/api/segments        (while testing: https://dev.furp.org/api/segments)
    Content-Type: application/json
    X-FURP-Key: <key>                          only if FURP has SEGMENTS_API_KEY set; not needed today

`GET /api/segments?segment=...&description=...&context=...&kinds=both&limit=25` returns the same JSON (handy in a
browser). A browser `fetch` from any https page on vstrat.ai or a subdomain (app., dev., www.) gets CORS headers,
preflight included; the browser adds the Origin header itself, and FURP needs no key. A server-to-server call
needs nothing. (Extra origins: the SEGMENTS_ORIGINS environment variable on FURP.)

The call VSTRAT makes from its segment page, as agreed 2026-11-06:

    POST https://furp.org/api/segments
    Content-Type: application/json
    {"segment": "...", "description": "...",
     "context": {"offering": "...", "industry": "...", "customer": "..."},
     "kinds": "both" | "nonprofits" | "firms", "limit": 25}

Any keys in `context` are accepted (offering, industry, customer, user...); they are flattened to one line.

## Request

| field | type | required | meaning |
|---|---|---|---|
| `segment` | string, 1-200 chars | yes | the segment's name, e.g. "first-generation college students" |
| `description` | string, up to 1000 | no | the user's description of the segment (may be empty) |
| `context` | string or object, up to 1000 | no | what the strategy project is about: offering, industry, who the user is. An object is flattened to "offering: ...; industry: ...; user: ..." |
| `kinds` | `both` \| `nonprofits` \| `firms` | no | what to return; default `both` |
| `limit` | integer 1-100 | no | rows per kind; default 25 |
| `state` | two-letter US state | no | only organizations in that state |

Example:

    {
      "segment": "regional hospital systems",
      "description": "multi-hospital nonprofit health systems serving a region, not academic medical centers",
      "context": {"offering": "revenue-cycle software", "industry": "health care IT", "user": "a vendor selling to hospitals"},
      "kinds": "both",
      "limit": 10
    }

## Response (200)

    {
      "status": "ok",                       // ok | ask | off
      "segment": "regional hospital systems",
      "kinds": "both", "limit": 10,
      "page_url": "https://furp.org/segments?segment=regional+hospital+systems&description=...&context=...&kinds=both&limit=10",
      "reading": {                          // how FURP read the segment (a small model's guess, cached per input)
        "terms": ["health system", "regional medical center"],
        "ntee": [{"code": "E22", "name": "Hospital"}, {"code": "E21", "name": "Community Health Systems"}],
        "formd": ["Health Care/Hospitals and Physicians"],
        "wants": "customers",               // customers | peers | competitors | funders | unclear
        "confidence": 0.85, "how": "model"  // cache | model | off | failed
      },
      "nonprofits": [
        {"ein": "...", "name": "...", "city": "...", "state": "..", "ntee_code": "E22",
         "latest_total_revenue": 1234567890, "matched": "name and category", "url": "https://furp.org/org/..."}
      ],
      "firms": [
        {"cik": "...", "name": "...", "city": "...", "state": "..", "industry": "...", "category": "Health Care",
         "subcategory": "Hospitals and Physicians", "amount_sold": 25000000, "offering_amount": 50000000,
         "filing_date": "2025-03-04", "matched": "category", "url": "https://furp.org/formd/..."}
      ],
      "question": null
    }

Rows are ranked by relevance: organizations matched both by name and by category first, then by the figure that
fits the segment (latest revenue for nonprofits, amount raised for companies). Every `url` is the organization's
own FURP page.

When nothing matches with confidence (`"status": "ask"`), `nonprofits` and `firms` are empty, no lookalikes are
offered, and `question` holds one short question for the user, for example:

    "question": "What is “northside widget buyers”? Describe the organizations in it, or the kind of nonprofit or company they resemble."

VSTRAT shows that question (or opens `page_url`, which shows it with an answer box), and sends the answer back as
`description` in a second request. `"status": "off"` means the segment reader was unavailable (the `note` field
says so); try again shortly.

Errors: 400 with `{"error": "..."}` for a missing segment or a non-JSON body; 401 when a key is required and wrong.

## Opening the page

`page_url` is a normal FURP page with FURP's menu and look: the segment's reading, the nonprofit and company tables
(each name a link to its page), and the question when there is one. Open it in a new tab:

    window.open(page_url, "_blank", "noopener");

Anyone can open the link; it carries the whole request in its query string, so it can be shared or bookmarked.
The page also has the segment form at the top, so a user can refine the segment there without going back to VSTRAT.

## How FURP recognizes VSTRAT

FURP knows a request came from VSTRAT by its `Origin` (API calls from the browser) or `Referer` (the results page
opened from VSTRAT). Any VSTRAT environment is VSTRAT: `vstrat.ai`, `www.vstrat.ai`, `bench.vstrat.ai`,
`b2.vstrat.ai` and `dev.vstrat.ai` (`app.analytics.VSTRAT_HOSTS`; the same list gives the CORS origins). Such
visits are tagged `source=vstrat` in FURP's usage stats, are always counted as people (never as bots), show a
small "From VSTRAT" line on the results page, and appear as a VSTRAT row in FURP's daily report (visits, segments
sent, results opened). Nothing is needed on VSTRAT's side beyond calling from a VSTRAT page: a browser sends
`Origin` on the fetch and `Referer` on the opened tab by itself. Do not send `rel="noreferrer"` or a `no-referrer`
policy on the link, or the results page cannot tell it came from VSTRAT.

## Notes

- The reading is cached for 30 days per exact segment + description + context, so repeated calls cost nothing and
  give the same answer; a changed description is a new reading.
- Nonprofits come from IRS Form 990 filers and the exempt-organization list, with the NTEE code the IRS published or
  FURP inferred. Companies come from SEC Form D private offerings since 2014, with the category FURP inferred from the
  filing.
- Rate limits are FURP's normal API limits (per client IP).
