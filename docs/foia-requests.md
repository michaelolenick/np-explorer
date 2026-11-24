# Public-records request creator (owner request 2026-11-23)

Live on dev and production; no flag. The pages are noindex.

- Page: `/records-request?ein=...&award=...` (five steps with Back/Next: type, organization, records, you and fees, review and send). Tables: `/records-request/tables`.
- Buttons: "Request records" on org pages and on each federal award row (shown only when the flag is on).
- API: `GET /api/foia/context?ein=`, `GET /api/foia/orgs?q=`, `POST /api/foia/letter`, `POST /api/foia/expand` (AI, 12 per IP per hour, 400 a day).
- Letters come from `app/foia.py:build_letter`; reference tables with sources are in `app/foia_data.py`.
- Awards: `usa_awards` linked to organizations by name and zip (3% of award rows, 178,583 organizations). Award office comes from the DOJ code in the award number (15JOVW = OVW), else from the agency name.
- Federal contacts: read on each agency's own FOIA page (`v` True = read 2026-11-23). foia.gov's list needs an API key (api.foia.gov, X-API-Key); load it into `FEDERAL` when one is available.
- State table: Reporters Committee Open Government Guide; `deadline_v` False means filled from the statute, not confirmed on that page. Only Texas has a confirmed send-to address.
- Expand with AI: `openai_compat` (free key) only; sends the user's few words and the organization's name, never the requester's details. Never OpenRouter.
- Released 2026-11-24.
