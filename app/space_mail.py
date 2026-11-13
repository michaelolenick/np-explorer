"""Outlook mailboxes (PST/OST) uploaded to the FURP space, message by message, into the brain (owner, 2026-11-13: the
first real upload was a 580 MB PST of a court case; "Did you extract the file I just uploaded for search?").

run() is called by app/space_ingest.py after the file passed its checks (magic bytes "!BDN", ClamAV on the whole
file). Then:
1. readpst (pst-utils, libpst) in a subprocess with memory, CPU and wall-clock limits and an empty environment
   writes one .eml file per message (folders as directories, deleted items included) under /bulk/ingest/<file id>/.
2. ClamAV scans everything readpst wrote (clamdscan, recursive); an infected message (its attachments are inside
   its .eml) is skipped and counted, the rest go on. No scan possible: the run waits (status pending) and resumes.
3. Messages are parsed with the standard library's email package in a fixed order (order.json), in batches of
   BATCH, each batch one transaction: folder path, message id, date, from, to, cc, bcc, subject, body (plain text,
   or HTML stripped to text with lxml: nothing is fetched or rendered) and the attachment list (name, type, size,
   sha256, what happened to it) into space_doc_messages. Each attachment of an allowed kind goes through the same
   detect_kind checks and app/space_extract.py (batch mode, same limits) and its text and tables land in
   space_doc_pages and space_doc_tables labelled "msg <seq>: <name>"; zips inside attachments get the zip limits,
   a zip inside a zip is never opened, and the mailbox as a whole has caps on attachment count and bytes.
4. Progress (space_docs.progress: stage, done, total) is committed with each batch, so a restart (deploy, crash)
   continues from the last committed message: the download, readpst's output and the entity tally all stay in the
   scratch directory until the mailbox is done.
5. Entities (people, organizations, EINs, case numbers, amounts, dates, addresses, email addresses, the names in
   From/To/Cc) are tallied across every message and attachment (found.json) and matched once at the end with
   space_ingest.match_entities; for a mailbox, an entity's pages[] holds message sequence numbers.

SECURITY: every header, body and attachment is untrusted data from somebody's mailbox; it is parsed, never acted
on. Nothing follows a link, loads a remote image, runs a macro or opens an attachment with anything but a parser.
Text that reaches a model prompt must be wrapped and labelled (space_ingest.UNTRUSTED).
"""

from __future__ import annotations

import datetime as dt
import email
import email.policy
import email.utils
import hashlib
import json
import logging
import os
import re
import resource
import shutil
import subprocess
from pathlib import Path

from app import db, space_ingest as si
from app.names import normalize_name

log = logging.getLogger("np.space_mail")
BATCH = 200                       # messages per transaction
MAX_MESSAGES = 300_000
MAX_ATTACHMENTS = 20_000          # per mailbox, extracted ones
MAX_ATTACH_BYTES = 2 * 1024**3    # per mailbox, bytes of attachments written out for extraction
ATTACH_CAP = 100 * si.MB          # one attachment, whatever its kind's own cap says
BODY_CHARS = 200_000
HEADER_CHARS = 2000
READPST_MEM_MB = int(os.environ.get("SPACE_MAIL_MEM_MB", "3072"))
READPST_SECONDS = int(os.environ.get("SPACE_MAIL_WALL_S", str(6 * 3600)))
SKIP_EXT = {".pst", ".ost", ".msg", ".eml"}   # mailboxes inside mailboxes are not opened


# --- readpst in a sandbox --------------------------------------------------------------------------------------

def _limits() -> None:
    lim = READPST_MEM_MB * si.MB
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
    resource.setrlimit(resource.RLIMIT_CPU, (READPST_SECONDS, READPST_SECONDS))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ValueError, OSError):
        pass


def readpst(path: Path, out: Path) -> tuple[bool, str]:
    """One .eml per message under out/ (folders as directories, deleted items too, UTF-8 bodies, no RTF copies)."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(out.parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": str(out.parent)}
    try:
        p = subprocess.run(["readpst", "-e", "-D", "-b", "-8", "-q", "-o", str(out), "--", str(path)], env=env, cwd=str(out),
                           capture_output=True, text=True, timeout=READPST_SECONDS, preexec_fn=_limits, start_new_session=True)
    except FileNotFoundError:
        return False, "readpst (pst-utils) is not installed"
    except subprocess.TimeoutExpired:
        return False, f"readpst did not finish in {READPST_SECONDS // 3600} hours"
    n = sum(1 for _ in out.rglob("*.eml"))
    if p.returncode != 0 and n == 0:
        tail = (p.stderr or "").strip().splitlines()[-1:] or [f"exit {p.returncode}"]
        return False, f"readpst failed: {tail[0][:200]}"
    return True, f"readpst wrote {n:,} messages" + (f" (exit {p.returncode}; some items may be missing)" if p.returncode else "")


def scan_dir(out: Path) -> tuple[str, set[str], str]:
    """ClamAV over everything readpst wrote: ("clean" | "infected" | "unavailable", infected paths, detail)."""
    if os.environ.get("SPACE_INGEST_SCANNER") == "none":
        return "clean", set(), "scanner disabled by SPACE_INGEST_SCANNER=none"
    try:
        p = subprocess.run(["clamdscan", "--fdpass", "--multiscan", "--infected", "--no-summary", "-r", "--", str(out)],
                           capture_output=True, text=True, timeout=6 * 3600)
    except FileNotFoundError:
        return "unavailable", set(), "clamdscan is not installed"
    except subprocess.TimeoutExpired:
        return "unavailable", set(), "the scan timed out"
    if p.returncode == 0:
        return "clean", set(), "no malware in the messages"
    if p.returncode == 1:
        bad = {ln.split(": ", 1)[0] for ln in (p.stdout or "").splitlines() if ln.endswith("FOUND")}
        return "infected", bad, f"{len(bad)} message(s) with malware skipped"
    return "unavailable", set(), ((p.stderr or p.stdout or "").strip()[-200:] or f"clamdscan exit {p.returncode}")


# --- one message -----------------------------------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    try:
        import lxml.html
        root = lxml.html.fromstring(html[:4_000_000])
        for bad in root.xpath("//script|//style|//head"):
            bad.drop_tree()
        return re.sub(r"\n{3,}", "\n\n", root.text_content())
    except Exception:  # noqa: BLE001
        return re.sub(r"<[^>]+>", " ", html)


def _hdr(msg, name: str) -> str:
    try:
        v = msg.get(name)
        return re.sub(r"\s+", " ", str(v)).strip()[:HEADER_CHARS] if v else ""
    except Exception:  # noqa: BLE001 - a malformed header is just empty
        return ""


def _date(msg) -> dt.datetime | None:
    try:
        d = email.utils.parsedate_to_datetime(_hdr(msg, "Date"))
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d if d and 1970 <= d.year <= 2100 else None
    except Exception:  # noqa: BLE001
        return None


def _body(msg) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            text = part.get_content()
            if isinstance(text, bytes):
                text = text.decode("utf-8", "replace")
            if part.get_content_subtype() == "html":
                text = _strip_html(text)
            return text[:BODY_CHARS]
    except Exception:  # noqa: BLE001
        pass
    pieces = []
    try:
        for part in msg.walk():
            if part.get_content_maintype() == "text" and not part.is_attachment():
                raw = part.get_payload(decode=True) or b""
                t = raw.decode(part.get_content_charset() or "utf-8", "replace")
                pieces.append(_strip_html(t) if part.get_content_subtype() == "html" else t)
                if sum(len(x) for x in pieces) > BODY_CHARS:
                    break
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(pieces)[:BODY_CHARS]


def parse_eml(data: bytes) -> dict:
    """Headers, body text and the attachments (bytes kept in memory only until this message is done)."""
    msg = email.message_from_bytes(data, policy=email.policy.default)
    atts = []
    try:
        for part in msg.iter_attachments():
            try:
                payload = part.get_payload(decode=True) or b""
            except Exception:  # noqa: BLE001
                payload = b""
            name = (part.get_filename() or "").replace("\\", "/").split("/")[-1][:200]
            atts.append({"name": name, "type": (part.get_content_type() or "")[:100], "size": len(payload),
                         "sha256": hashlib.sha256(payload).hexdigest(), "_bytes": payload})
    except Exception:  # noqa: BLE001
        pass
    return {"message_id": _hdr(msg, "Message-ID")[:500], "date": _date(msg), "from_addr": _hdr(msg, "From"),
            "to_addr": _hdr(msg, "To"), "cc": _hdr(msg, "Cc"), "bcc": _hdr(msg, "Bcc"), "subject": _hdr(msg, "Subject")[:500],
            "body": _body(msg), "attachments": atts}


def _addresses(*headers: str) -> list[tuple[str, str]]:
    try:
        return [(n.strip(), a.strip().lower()) for n, a in email.utils.getaddresses([h for h in headers if h]) if a]
    except Exception:  # noqa: BLE001
        return []


# --- the run -----------------------------------------------------------------------------------------------------

def _order(out: Path, work: Path) -> list[str]:
    """The messages in a fixed order (folder path, then message number), written once so a resumed run sees the
    same sequence numbers."""
    f = work / "order.json"
    if f.exists():
        return json.loads(f.read_text())
    paths = []
    for root, dirs, files in os.walk(out):
        dirs.sort()
        rel = os.path.relpath(root, out)
        for name in sorted(files, key=lambda s: (len(s), s)):
            if name.lower().endswith(".eml"):
                paths.append(os.path.join(rel, name) if rel != "." else name)
    paths = paths[:MAX_MESSAGES]
    f.write_text(json.dumps(paths))
    return paths


def _found_load(work: Path) -> si._Found:
    found = si._Found()
    f = work / "found.json"
    if f.exists():
        for it in json.loads(f.read_text()):
            found.items[(it["kind"], it["norm"])] = it
    return found


def _found_save(work: Path, found: si._Found) -> None:
    (work / "found.json").write_text(json.dumps(list(found.items.values()), ensure_ascii=False))


def _merge(found: si._Found, ents: list[dict]) -> None:
    for e in ents:
        key = (e["kind"], e["norm"])
        if key in found.items:
            it = found.items[key]
            it["count"] += e["count"]
            for p in e["pages"]:
                if p not in it["pages"] and len(it["pages"]) < 20:
                    it["pages"].append(p)
        elif len(found.items) < si.MAX_ENTITIES:
            found.items[key] = e


def run(conn, f: dict, path: Path, work: Path, say) -> str:
    """The mailbox at `path` into the tables, resumably. Returns extracted, failed, pending (scan unavailable: the
    sweep tries again) or checking (not used: a run always finishes or fails within this call)."""
    out, done_marker = work / "mail", work / "readpst.done"
    doc = conn.execute("SELECT * FROM space_docs WHERE file_id = %s", (f["id"],)).fetchone()
    progress = (doc["progress"] if doc and doc["progress"] else {}) or {}
    if not done_marker.exists():
        si._set(conn, f["id"], progress={"stage": "reading the mailbox with readpst"})
        say(f"file {f['id']}: readpst")
        ok, detail = readpst(path, out)
        if not ok:
            si._set(conn, f["id"], status="failed", error=f"extraction failed: {detail}", progress=None)
            si._log(conn, "ingest failed", f, detail)
            return "failed"
        done_marker.write_text(detail)
        for stale in ("order.json", "found.json", "infected.json"):
            (work / stale).unlink(missing_ok=True)
        progress = {}
    infected_file = work / "infected.json"
    if not infected_file.exists():
        si._set(conn, f["id"], progress={"stage": "malware scan of the messages"})
        verdict, bad, detail = scan_dir(out)
        if verdict == "unavailable":
            si._set(conn, f["id"], status="pending", error=f"waiting for a malware scan of the messages ({detail})")
            return "pending"
        infected_file.write_text(json.dumps({"detail": detail, "paths": sorted(bad)}))
    inf = json.loads(infected_file.read_text())
    infected = set(inf["paths"])
    order = _order(out, work)
    total = len(order)
    done = conn.execute("SELECT coalesce(max(seq), 0) AS n FROM space_doc_messages WHERE doc_id = %s", (f["id"],)).fetchone()["n"]
    if done == 0 or progress.get("stage") != "messages":
        with conn.transaction():
            for t in ("space_doc_messages", "space_doc_pages", "space_doc_tables", "space_doc_entities"):
                conn.execute(f"DELETE FROM {t} WHERE doc_id = %s", (f["id"],))
        done, progress = 0, {"stage": "messages", "done": 0, "total": total, "pages": 0, "attachments": 0, "att_bytes": 0, "skipped": 0}
    next_page = int(progress.get("pages", 0)) + 1
    n_att, att_bytes, skipped = int(progress.get("attachments", 0)), int(progress.get("att_bytes", 0)), int(progress.get("skipped", 0))
    found = _found_load(work)
    say(f"file {f['id']}: {total:,} messages, {done:,} already in")
    att_dir = work / "att"
    while done < total:
        batch = order[done:done + BATCH]
        rows, manifest, pending_pages, pending_tables, pseudo = [], [], [], [], []
        shutil.rmtree(att_dir, ignore_errors=True)
        att_dir.mkdir()
        for i, rel in enumerate(batch):
            seq = done + i + 1
            full = out / rel
            folder = os.path.dirname(rel).replace(os.sep, "/") or "(root)"
            if str(full) in infected:
                skipped += 1
                rows.append((f["id"], seq, folder, None, None, None, None, None, None, "(skipped: malware found by ClamAV)", None, json.dumps([]), 0))
                continue
            try:
                m = parse_eml(full.read_bytes())
            except Exception as e:  # noqa: BLE001 - one unreadable message: recorded, the rest go on
                rows.append((f["id"], seq, folder, None, None, None, None, None, None, f"(unreadable message: {type(e).__name__})", None, json.dumps([]), 0))
                continue
            atts = []
            for k, a in enumerate(m["attachments"]):
                data = a.pop("_bytes")
                a["status"] = "listed"
                ext = si._ext(a["name"])
                if not a["name"] or not data:
                    a["status"] = "skipped: empty"
                elif ext in SKIP_EXT:
                    a["status"] = "skipped: mailboxes and messages inside a mailbox are not opened"
                elif ext and ext not in si.EXT_KIND:
                    a["status"] = "skipped: type not allowed"           # no extension at all: the bytes decide, below
                elif a["size"] > ATTACH_CAP:
                    a["status"] = f"skipped: over {ATTACH_CAP // si.MB} MB"
                elif n_att >= MAX_ATTACHMENTS or att_bytes + a["size"] > MAX_ATTACH_BYTES:
                    a["status"] = "skipped: the mailbox's attachment limit was reached"
                else:
                    p = att_dir / f"{seq}_{k}.bin"
                    p.write_bytes(data)
                    kind, checks = si.detect_kind(str(p), a["name"], a["type"], a["size"])
                    if kind is None:
                        a["status"] = "skipped: " + checks[-1]["detail"]
                        p.unlink(missing_ok=True)
                    else:
                        a["kind"] = kind
                        n_att += 1
                        att_bytes += a["size"]
                        manifest.append({"id": f"{seq}:{k}", "kind": kind, "path": str(p), "seq": seq, "k": k, "name": a["name"]})
                atts.append(a)
            rows.append((f["id"], seq, folder, m["message_id"] or None, m["date"], m["from_addr"] or None, m["to_addr"] or None,
                         m["cc"] or None, m["bcc"] or None, m["subject"] or None, m["body"] or None, json.dumps(atts, ensure_ascii=False), len(atts)))
            head = " ".join(x for x in (m["subject"], m["from_addr"], m["to_addr"], m["cc"]) if x)
            pseudo.append({"page": seq, "text": head + "\n" + (m["body"] or "")})
            for name, addr in _addresses(m["from_addr"], m["to_addr"], m["cc"], m["bcc"]):
                found.add("email", addr, addr, seq)
                if name and len(name.split()) >= 2 and not any(ch.isdigit() for ch in name):
                    found.add("person", name, normalize_name(name), seq)
        results = si.extract_batch(manifest, str(att_dir)) if manifest else {}
        att_status = {}
        for it in manifest:
            r = results.get(it["id"]) or {"error": "no result"}
            if r.get("error"):
                att_status[it["id"]] = "extraction failed: " + r["error"][:120]
                continue
            label = f"msg {it['seq']}: {it['name']}"
            for p in r["pages"]:
                pending_pages.append((f["id"], next_page + p["page"] - 1, label + (f" ({p['label']})" if p.get("label") else ""), p["text"]))
                pseudo.append({"page": it["seq"], "text": p["text"]})
            for t in r["tables"]:
                pending_tables.append((f["id"], next_page + (t.get("page") or 1) - 1, f"{label}: {t.get('name') or ''}"[:200],
                                       json.dumps(t["header"], ensure_ascii=False), json.dumps(t["rows"], ensure_ascii=False), t.get("n_rows", len(t["rows"]))))
            next_page += len(r["pages"])
            att_status[it["id"]] = f"extracted: {len(r['pages'])} pages, {len(r['tables'])} tables"
        if att_status:                              # write the outcome into each message's attachment list
            fixed = []
            for row in rows:
                atts = json.loads(row[11])
                for k, a in enumerate(atts):
                    s = att_status.get(f"{row[1]}:{k}")
                    if s:
                        a["status"] = s
                fixed.append(row[:11] + (json.dumps(atts, ensure_ascii=False), row[12]))
            rows = fixed
        ents, _states = si.find_entities(pseudo)
        _merge(found, ents)
        done += len(batch)
        progress = {"stage": "messages", "done": done, "total": total, "pages": next_page - 1, "attachments": n_att,
                    "att_bytes": att_bytes, "skipped": skipped}
        with conn.transaction():
            with conn.cursor() as cur:
                with cur.copy("COPY space_doc_messages (doc_id, seq, folder, message_id, date, from_addr, to_addr, cc, bcc, subject, body, attachments, n_attachments) FROM STDIN") as cp:
                    for row in rows:
                        cp.write_row(row)
                if pending_pages:
                    with cur.copy("COPY space_doc_pages (doc_id, page, label, text) FROM STDIN") as cp:
                        for row in pending_pages:
                            cp.write_row(row)
                if pending_tables:
                    with cur.copy("COPY space_doc_tables (doc_id, page, name, header, rows, n_rows) FROM STDIN") as cp:
                        for row in pending_tables:
                            cp.write_row(row)
            si._set(conn, f["id"], progress=json.dumps(progress), messages=done, attachments=n_att, pages=next_page - 1)
        _found_save(work, found)
        say(f"file {f['id']}: {done:,}/{total:,} messages, {n_att:,} attachments")
    shutil.rmtree(att_dir, ignore_errors=True)
    # Entities, matched once over the whole mailbox.
    ents = list(found.items.values())
    _states = set()
    for e in ents:
        if e["kind"] == "address":
            m = si.STATE_ZIP_RE.search(e["text"])
            if m and m.group(1) in si.STATE_CODES:
                _states.add(m.group(1))
    si._set(conn, f["id"], progress=json.dumps({**progress, "stage": "matching entities"}))
    si.safe_match(conn, f["id"], ents, _states)
    matched = sum(1 for e in ents if e["dst_kind"])
    with conn.transaction():
        conn.execute("DELETE FROM space_doc_entities WHERE doc_id = %s", (f["id"],))
        with conn.cursor() as cur:
            with cur.copy("COPY space_doc_entities (doc_id, kind, text, norm, count, pages, dst_kind, dst_key, dst_name, how, confidence) FROM STDIN") as cp:
                for e in ents:
                    cp.write_row((f["id"], e["kind"], e["text"][:300], e["norm"][:300], e["count"], e["pages"], e["dst_kind"],
                                  e["dst_key"], e["dst_name"], e["how"], e["confidence"]))
        n_tables = conn.execute("SELECT count(*) AS n FROM space_doc_tables WHERE doc_id = %s", (f["id"],)).fetchone()["n"]
        note = done_marker.read_text()[:150] + f"; {inf['detail']}" + (f"; {skipped} message(s) skipped" if skipped else "")
        si._set(conn, f["id"], status="extracted", error=None, messages=total, attachments=n_att, pages=next_page - 1, tables=n_tables,
                entities=len(ents), matched=matched, words=None, language="en", note=note,
                extracted_at=dt.datetime.now(dt.timezone.utc), progress=None)
        si._log(conn, "ingest extracted", f, f"mailbox: {total:,} messages, {n_att:,} attachments, {len(ents):,} entities, {matched:,} matched")
    return "extracted"
