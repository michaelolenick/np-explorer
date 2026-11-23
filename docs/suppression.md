# Suppression list

People kept off furp.org permanently (owner, 2026-11-23). Data in `suppressed_people` (name, name_norm, person_id, eins,
row_ids, added_at, reason, active); filtered events in `suppression_hits`; removed rows archived in `privacy_removed`.
None of these are touched by any rebuild. Code: `loader/suppression.py`, `app/suppress.py`.

Add: `.venv/bin/python -m loader.suppression add --name "First Last" --person-id N --ein E --reason "..."`
(then it sweeps). `list`, `sweep [--dry-run]`, `deactivate ID`.

Layers: insert trigger on `people`; `sweep` in scripts/nightly.sh (before the loads, after IRS and registry loads, at the
end) over every other person table; 410 + noindex at /person/*, /api/person/* and the public API; sitemap leaves them out;
filing pages and XML redact the name (privacy_suppressions). The nightly report lists suppressed names filtered from new data.
Matching is by normalized name; a different person with the same name is suppressed too.
