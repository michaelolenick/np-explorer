"""Search test set: run every query in tests/search_cases.yml through the site (in-process, real database and
model) and report the pass rate. A case passes when an expected organization is among the first organizations the
results page links to. Run before each deploy (scripts/deploy.sh); the result is logged to logs/search-eval.log and
shown in the nightly report.

    .venv/bin/python scripts/search_eval.py [--only uli] [--json out.json] [--quiet]

The per-visitor question limit and search analytics are switched off for these requests, so a run neither hits
the limit nor counts as visitor searches."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = ROOT / "tests" / "search_cases.yml"
LOG = ROOT / "logs" / "search-eval.log"
_ANCHOR = re.compile(r'<a\b[^>]*?\bhref="/org/(?:[a-z0-9-]*-)?(\d{9})[#"?][^>]*>(.*?)</a>', re.S)


def load_cases() -> list[dict]:
    import yaml
    return yaml.safe_load(CASES.read_text())


def orgs_on(html: str, final_path: str) -> list[tuple[str, str]]:
    """(ein, link text) for the organizations a results page links to, in order, first time each."""
    seen, out = set(), []
    m = re.match(r"/org/(?:[a-z0-9-]*-)?(\d{9})$", final_path)
    if m:                                  # the search went straight to one organization's page
        t = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        out.append((m.group(1), re.sub(r"<[^>]+>", "", t.group(1)) if t else ""))
        seen.add(m.group(1))
    body = html.split("<main", 1)[-1]
    for ein, text in _ANCHOR.findall(body):
        if ein not in seen:
            seen.add(ein)
            out.append((ein, re.sub(r"<[^>]+>", "", text).strip()))
    return out


def grade(case: dict, found: list[tuple[str, str]]) -> bool:
    top = found[:case.get("top", 5)]
    if case.get("ein"):
        want = {str(e).zfill(9) for e in case["ein"]}
        if any(e in want for e, _ in top):
            return True
    if case.get("name"):
        return any(re.search(case["name"], t, re.I) for _, t in top)
    return False


def run(cases: list[dict], quiet: bool = False) -> dict:
    from fastapi.testclient import TestClient

    from app import analytics, ask, main
    ask.limit.allow = lambda ip: True              # noqa: E731 - the per-visitor limit is for visitors
    analytics.search = lambda *a, **k: None        # noqa: E731 - test runs are not visitor searches

    async def passthrough(request, call_next):
        return await call_next(request)
    analytics.middleware = passthrough             # nor page views
    client = TestClient(main.app, base_url="https://furp.org")
    results = []
    for c in cases:
        t0 = time.monotonic()
        r = client.get("/search", params={"q": c["q"]}, follow_redirects=True)
        ms = (time.monotonic() - t0) * 1000
        found = orgs_on(r.text, r.url.path) if r.status_code == 200 else []
        note = re.search(r'<p class="search-note"[^>]*>(.*?)</p>', r.text, re.S)
        ok = r.status_code == 200 and grade(c, found)
        results.append({"q": c["q"], "kind": c.get("kind"), "ok": ok, "status": r.status_code, "ms": round(ms),
                        "top": [f"{t} ({e})" for e, t in found[:3]],
                        "note": re.sub(r"<[^>]+>", "", note.group(1)).strip() if note else None})
        if not quiet:
            print(f"{'PASS' if ok else 'FAIL'} {ms:6.0f} ms  {c['q']!r:45} -> {'; '.join(results[-1]['top'][:2]) or '(none)'}")
    passed = sum(r["ok"] for r in results)
    by_kind: dict = {}
    for r in results:
        k = by_kind.setdefault(r["kind"], [0, 0])
        k[0] += r["ok"]
        k[1] += 1
    return {"passed": passed, "total": len(results), "rate": round(100 * passed / max(1, len(results)), 1),
            "by_kind": by_kind, "results": results}


def main_() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="only cases whose query contains this")
    ap.add_argument("--json", help="write the full results here")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--log", help="the log to append the result to (default logs/search-eval.log here)")
    args = ap.parse_args()
    from app import db
    db.pool.open()
    cases = [c for c in load_cases() if not args.only or args.only in c["q"]]
    out = run(cases, quiet=args.quiet)
    kinds = ", ".join(f"{k} {p}/{n}" for k, (p, n) in out["by_kind"].items())
    print(f"search test set: {out['passed']}/{out['total']} passed ({out['rate']}%): {kinds}")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(out, indent=1))
    if not args.only:
        log = pathlib.Path(args.log) if args.log else LOG
        log.parent.mkdir(exist_ok=True)
        with open(log, "a") as f:
            f.write(json.dumps({"at": int(time.time()), "passed": out["passed"], "total": out["total"],
                                "rate": out["rate"], "by_kind": out["by_kind"],
                                "failed": [r["q"] for r in out["results"] if not r["ok"]]}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main_())
