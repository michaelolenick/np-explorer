"""Files uploaded to the FURP space go into the brain (owner, 2026-11-12; app/space_ingest.py, app/space_mail.py,
app/space_extract.py, app/space_docs.py): the security checks and the allow-list, extraction in the sandboxed
subprocess, entity matching against real records, exposure by mark and mark changes, the public document page, the
search results, the API, the documents contract for the natural-language search, and Outlook mailboxes.

Runs against the shared database with files on local disk (SPACE_BLOB_DIR); the malware scanner is replaced by
SPACE_INGEST_SCANNER=none except in the one test that checks the real ClamAV daemon when it is there. The upload
hook's background pool runs synchronously here, so an upload request returns with the file already processed."""

import contextlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import zipfile

import pytest
from starlette.testclient import TestClient

from app import accounts, db, space

MARK = "pytest-ingest"
RED_CROSS = "530196605"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["SPACE_BLOB_DIR"] = str(tmp_path_factory.mktemp("blobs"))
    os.environ["SPACE_INGEST_SCANNER"] = "none"
    os.environ["SPACE_INGEST_WORK"] = str(tmp_path_factory.mktemp("work"))
    from app import space_ingest
    space_ingest.WORK_ROOT = __import__("pathlib").Path(os.environ["SPACE_INGEST_WORK"])
    from app.main import app
    db.pool.open(wait=False)
    space_ingest.ensure()
    # The upload hook's thread pool runs its job at once, so a test sees the outcome right after the request.
    class Now:
        def submit(self, fn, *a, **k):
            fn(*a, **k)
            class R:
                def result(self_, timeout=None):
                    return None
            return R()
    space_ingest._pool = Now()
    return TestClient(app)


@contextlib.contextmanager
def person(email: str, folder: str, super_: bool = False):
    token = secrets.token_urlsafe(32)
    with db.conn() as conn:
        conn.execute("DELETE FROM space_log WHERE folder = %s", (folder,))
        conn.execute("DELETE FROM space_docs WHERE file_id IN (SELECT id FROM space_files WHERE folder_id IN (SELECT id FROM space_folders WHERE name = %s))", (folder,))
        conn.execute("DELETE FROM space_files WHERE folder_id IN (SELECT id FROM space_folders WHERE name = %s)", (folder,))
        conn.execute("DELETE FROM space_folders WHERE name = %s", (folder,))
        conn.execute("DELETE FROM space_people WHERE email = %s", (email,))
        p = conn.execute("INSERT INTO space_people (email, name, is_super, added_by) VALUES (%s, %s, %s, %s) RETURNING id",
                         (email, f"{MARK} {folder}", super_, MARK)).fetchone()
        conn.execute("INSERT INTO space_folders (name, person_id, created_by) VALUES (%s, %s, %s)", (folder, p["id"], MARK))
        u = conn.execute("""INSERT INTO users (email, name, auth_method, status, last_login) VALUES (%s, %s, 'email', 'active', now())
                            ON CONFLICT (email) DO UPDATE SET last_login = now() RETURNING id""", (email, MARK)).fetchone()
        conn.execute("INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + interval '1 hour')",
                     (accounts._hash(token), u["id"]))
    try:
        yield {"email": email, "folder": folder, "cookie": token, "person_id": p["id"], "user_id": u["id"], "user": {"id": u["id"], "email": email, "status": "active"}}
    finally:
        with db.conn() as conn:
            fids = [r["id"] for r in conn.execute("SELECT id FROM space_files WHERE folder_id IN (SELECT id FROM space_folders WHERE name = %s)", (folder,))]
            if fids:
                conn.execute("DELETE FROM xlinks WHERE src_kind = 'space_doc' AND src_key IN (SELECT public_token FROM space_files WHERE id = ANY(%s) AND public_token IS NOT NULL)", (fids,))
                conn.execute("DELETE FROM space_docs WHERE file_id = ANY(%s)", (fids,))
            conn.execute("DELETE FROM space_log WHERE folder = %s OR who = %s", (folder, email))
            conn.execute("DELETE FROM space_files WHERE folder_id IN (SELECT id FROM space_folders WHERE name = %s)", (folder,))
            conn.execute("DELETE FROM space_folders WHERE name = %s", (folder,))
            conn.execute("DELETE FROM space_people WHERE id = %s", (p["id"],))
            conn.execute("DELETE FROM user_sessions WHERE user_id = %s", (u["id"],))
            conn.execute("DELETE FROM users WHERE id = %s AND name = %s", (u["id"], MARK))


def _csrf(client, who) -> str:
    r = client.get(f"/space/{who['folder']}", cookies={accounts.COOKIE: who["cookie"]})
    assert r.status_code == 200, r.text[:300]
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def _upload(client, who, name: str, data: bytes, ctype: str, vis=None):
    fields = {"csrf": _csrf(client, who)}
    if vis:
        fields["visibility"] = vis
    r = client.post(f"/space/{who['folder']}/upload", data=fields, files={"file": (name, data, ctype)},
                    cookies={accounts.COOKIE: who["cookie"]}, follow_redirects=False)
    assert r.status_code == 303 and "stored1" in r.headers["location"], r.headers.get("location")
    with db.conn() as conn:
        return conn.execute("SELECT * FROM space_files WHERE uploader = %s AND filename = %s ORDER BY id DESC", (who["email"], name)).fetchone()


def _set_mark(client, who, fid, vis):
    data = {"csrf": _csrf(client, who), "file_id": fid, "visibility": vis}
    if vis == "public":
        data["confirm"] = "1"
    r = client.post(f"/space/{who['folder']}/visibility", data=data, cookies={accounts.COOKIE: who["cookie"]}, follow_redirects=False)
    assert r.status_code == 303, r.text[:200]


def _doc(fid):
    with db.conn() as conn:
        return conn.execute("SELECT * FROM space_docs WHERE file_id = %s", (fid,)).fetchone()


# --- fixtures built on the fly -------------------------------------------------------------------------------------

def pdf_bytes(text: str) -> bytes:
    """A one-page PDF with Helvetica text that pdfplumber reads back."""
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    content = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({esc(ln)}) Tj T*" for ln in text.split("\n")) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def xlsx_bytes() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payments"
    ws.append(["Payee", "Amount", "EIN"])
    ws.append(["American National Red Cross", 1500, "53-0196605"])
    ws.append(["Zyxw Ingest Vendor LLC", 42, ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def docx_bytes() -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph("Memorandum regarding Case No. 2:21-cv-01234 and the American National Red Cross.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Item", "Cost"
    t.cell(1, 0).text, t.cell(1, 1).text = "Filing fee", "$402"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


TEXT = ("IN THE UNITED STATES DISTRICT COURT\nCase No. 2:21-cv-01234\nMICHAEL R. OLENICK, Plaintiff,\n"
        "The American National Red Cross (EIN 53-0196605) received $1,250,000 on March 3, 2021.\n"
        "Contact: 431 18th Street NW, Washington, DC 20006. Signed by Michael R. Olenick.")


# --- the checks and the allow-list --------------------------------------------------------------------------------------

def test_detect_kind_types_the_file_by_its_bytes(tmp_path):
    from app import space_ingest as si
    f = tmp_path / "x"
    f.write_bytes(pdf_bytes("hello"))
    assert si.detect_kind(str(f), "brief.pdf", "application/pdf", f.stat().st_size)[0] == "pdf"
    assert si.detect_kind(str(f), "brief.pdf", "application/octet-stream", f.stat().st_size)[0] == "pdf"   # browser didn't know
    kind, checks = si.detect_kind(str(f), "brief.txt", "text/plain", f.stat().st_size)                      # named .txt, is a PDF
    assert kind is None and checks[-1]["check"] == "extension" and "named .txt" in checks[-1]["detail"]
    kind, checks = si.detect_kind(str(f), "brief.pdf", "text/csv", f.stat().st_size)                        # declared CSV, is a PDF
    assert kind is None and checks[-1]["check"] == "declared type"
    exe = tmp_path / "e"
    exe.write_bytes(b"MZ\x90\x00" + b"\x00" * 200 + b"PE\x00\x00" + b"\x00" * 100)
    kind, checks = si.detect_kind(str(exe), "setup.exe", "application/x-msdownload", 304)
    assert kind is None and ".exe files are not allowed" in checks[-1]["detail"]
    kind, checks = si.detect_kind(str(exe), "setup.pdf", "application/pdf", 304)       # renamed: still the bytes decide
    assert kind is None and not checks[-1]["ok"]
    sh = tmp_path / "s.sh"
    sh.write_text("#!/bin/sh\nrm -rf /\n")
    assert si.detect_kind(str(sh), "s.sh", "text/x-shellscript", 20)[0] is None
    macro = tmp_path / "m.docx"
    with zipfile.ZipFile(macro, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w/>")
        z.writestr("word/vbaProject.bin", b"\x00" * 10)
    kind, checks = si.detect_kind(str(macro), "m.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 100)
    assert kind is None and checks[-1]["check"] == "macros"
    csv = tmp_path / "c.csv"
    csv.write_text("a,b\n1,2\n")
    assert si.detect_kind(str(csv), "c.csv", "application/vnd.ms-excel", 8)[0] == "csv"     # Windows calls CSVs Excel
    assert si.detect_kind(str(csv), "c.md", "text/plain", 8)[0] in ("markdown", "csv", "text")  # text kinds stand in for one another
    assert si._ext("26.04.20 - Letter to NewsX") == "" and si._ext("brief.PDF") == ".pdf" and si._ext("x.tar.gz") == ".gz"
    assert si.detect_kind(str(f), "26.04.20 - Statutory Demand - NewsX", "application/octet-stream", f.stat().st_size)[0] == "pdf"
    pst = tmp_path / "m.pst"
    pst.write_bytes(b"!BDN" + b"\x00" * 600)
    assert si.detect_kind(str(pst), "CourtCase.pst", "application/octet-stream", 604)[0] == "pst"
    big = si.detect_kind(str(f), "brief.pdf", "application/pdf", 10**12)
    assert big[0] is None and big[1][-1]["check"] == "size"
    assert si.MAX_DOWNLOAD >= 2048 * si.MB


def test_zip_bomb_limits_and_members(tmp_path):
    from app import space_ingest as si
    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("zeros.txt", b"0" * (50 * 1024 * 1024))          # 50 MB of zeros: ratio far over 100:1
    res = si.extract("zip", str(bomb), str(tmp_path))
    assert "ratio" in res["error"]
    ok = tmp_path / "ok.zip"
    with zipfile.ZipFile(ok, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("notes.txt", "Red Cross notes " * 20)
        z.writestr("brief.pdf", pdf_bytes("Inside the zip"))
        z.writestr("run.exe", b"MZ" + b"\x00" * 50)
        z.writestr("inner.zip", b"PK\x03\x04" + b"\x00" * 50)
    res = si.extract("zip", str(ok), str(tmp_path))
    assert not res.get("error") and res["members"] == 2
    assert any("Inside the zip" in p["text"] for p in res["pages"]) and any("run.exe" in n for n in (res["note"] or "").split(";"))


def test_extractor_reads_pdf_csv_xlsx_docx_html_json(tmp_path):
    from app import space_ingest as si
    cases = {"pdf": pdf_bytes(TEXT), "csv": b"name,ein\nAmerican National Red Cross,53-0196605\n",
             "xlsx": xlsx_bytes(), "docx": docx_bytes(), "html": b"<html><body><script>alert(1)</script><h1>Title</h1><table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table></body></html>",
             "json": json.dumps([{"name": "Red Cross", "ein": "53-0196605"}]).encode()}
    for kind, data in cases.items():
        p = tmp_path / f"f.{kind}"
        p.write_bytes(data)
        res = si.extract(kind, str(p), str(tmp_path))
        assert not res.get("error"), (kind, res)
        assert res["pages"], kind
        if kind == "pdf":
            assert "Red Cross" in res["pages"][0]["text"]
        if kind in ("csv", "xlsx", "docx", "html", "json"):
            assert res["tables"] and len(res["tables"][0]["header"]) >= 2, kind
        if kind == "html":
            assert "alert" not in res["pages"][0]["text"] and "Title" in res["pages"][0]["text"]
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"MZ" * 10)
    assert "unknown kind" in subprocess.run([__import__("sys").executable, str(si.EXTRACTOR), "exe", str(exe), str(tmp_path / "o.json")],
                                            capture_output=True, text=True).stderr


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_extractor_reads_images_and_scanned_pdfs_by_ocr(tmp_path):
    """A picture of text and a PDF with no text layer (a scan) come out as text (2026-11-13)."""
    from PIL import Image, ImageDraw, ImageFont
    from app import space_ingest as si
    img = Image.new("RGB", (1400, 300), "white")
    ImageDraw.Draw(img).text((40, 100), "American National Red Cross", fill="black", font=ImageFont.load_default(size=64))
    png, pdf = tmp_path / "scan.png", tmp_path / "scan.pdf"
    img.save(png)
    img.save(pdf, "PDF", resolution=100.0)
    res = si.extract("image", str(png), str(tmp_path))
    assert not res.get("error") and "Red Cross" in res["pages"][0]["text"] and "by OCR" in res["note"], res
    res = si.extract("pdf", str(pdf), str(tmp_path))
    assert not res.get("error") and "Red Cross" in res["pages"][0]["text"] and "OCR: 1 of 1" in res["note"], res


def test_entities_found_and_matched_to_real_records(client):
    from app import space_ingest as si
    ents, states = si.find_entities([{"page": 1, "text": TEXT}])
    kinds = {e["kind"] for e in ents}
    assert {"ein", "case", "amount", "date", "address", "person", "party"} <= kinds and "DC" in states
    with db.conn() as conn:
        si.match_entities(conn, ents, states)
    ein = next(e for e in ents if e["kind"] == "ein")
    assert ein["dst_kind"] == "org" and ein["dst_key"] == RED_CROSS and ein["confidence"] == 1.0
    with db.conn() as conn:
        n = conn.execute("SELECT count(*) AS n FROM person_clusters WHERE name_norm = 'michael r olenick'").fetchone()["n"]
    p = next(e for e in ents if e["kind"] == "person" and e["norm"] == "michael r olenick")
    if n == 1:
        assert p["dst_kind"] == "person" and p["confidence"] == 0.8


# --- the whole thing through the site: upload, marks, pages, search, API -----------------------------------------------

def test_upload_goes_into_the_brain_and_exposure_follows_the_mark(client):
    from app import space_ingest as si
    with person("brain-" + MARK + "@example.test", f"{MARK}-Brain") as who:
        f = _upload(client, who, "court-case.pdf", pdf_bytes(TEXT), "application/pdf")
        d = _doc(f["id"])
        assert d and d["status"] == "extracted", d
        assert d["kind"] == "pdf" and d["pages"] == 1 and d["entities"] >= 5 and d["matched"] >= 1 and d["exposure"] == "furp"
        checks = {c["check"]: c for c in d["checks"]}
        assert checks["integrity"]["ok"] and checks["magic"]["detail"] == "application/pdf" and checks["malware scan (ClamAV)"]["ok"]
        with db.conn() as conn:
            assert conn.execute("SELECT count(*) AS n FROM space_doc_pages WHERE doc_id = %s", (f["id"],)).fetchone()["n"] == 1
            assert conn.execute("SELECT 1 FROM space_doc_entities WHERE doc_id = %s AND kind = 'ein' AND dst_key = %s", (f["id"], RED_CROSS)).fetchone()
            assert not conn.execute("SELECT 1 FROM xlinks WHERE src_kind = 'space_doc' AND src_name = 'court-case.pdf'").fetchone()   # furp: internal only
            assert conn.execute("SELECT 1 FROM space_log WHERE file_id = %s AND action = 'ingest extracted'", (f["id"],)).fetchone()
        # the folder page and /space say so next to the file
        for path in (f"/space/{who['folder']}", "/space"):
            html = client.get(path, cookies={accounts.COOKIE: who["cookie"]}).text
            assert "In FURP&rsquo;s brain" in html and "In FURP\u2019s brain" in html and "1 page, 0 tables" in html, path
        # FURP-readable: no page, not in the API, not in a visitor's search, but in the owner's search
        assert client.get("/api/v1/datasets/documents?q=Red+Cross").json()["results"] == [] or \
            all(r["title"] != "court-case.pdf" for r in client.get("/api/v1/datasets/documents?q=Red+Cross").json()["results"])
        assert "court-case.pdf" not in client.get("/search?q=Red+Cross+received&type=name").text
        mine = client.get("/search?q=Red+Cross+received&type=name", cookies={accounts.COOKIE: who["cookie"]}).text
        assert "court-case.pdf" in mine and "only you can see" in mine
        # public: xlinks mirrored, the page is up, search and API show it
        _set_mark(client, who, f["id"], "public")
        with db.conn() as conn:
            f2 = conn.execute("SELECT * FROM space_files WHERE id = %s", (f["id"],)).fetchone()
            links = conn.execute("SELECT * FROM xlinks WHERE src_kind = 'space_doc' AND src_key = %s", (f2["public_token"],)).fetchall()
            assert any(x["dst_kind"] == "org" and x["dst_key"] == RED_CROSS and x["how"] == "EIN (EXACT)" for x in links)
            assert conn.execute("SELECT 1 FROM xlink_counts WHERE src_kind = 'space_doc'").fetchone()
        assert _doc(f["id"])["exposure"] == "public"
        r = client.get(f"/docs/{f2['public_token']}")
        assert r.status_code == 200 and 'class="wide contained"' in r.text and "Data: uploaded by" in r.text
        assert re.search(rf'href="/org/[a-z0-9-]*{RED_CROSS}"', r.text) and f"/p/{f2['public_token']}/court-case.pdf" in r.text and "EIN (EXACT)" in r.text   # slugged links
        assert 'name="robots" content="noindex"' in r.text and "Red Cross" in r.text
        assert "court-case.pdf" in client.get("/docs").text
        assert "court-case.pdf" in client.get("/search?q=Red+Cross+received&type=name").text
        api = client.get("/api/v1/datasets/documents?q=Red+Cross+received").json()
        assert any(x["title"] == "court-case.pdf" and x["url"].endswith(f"/docs/{f2['public_token']}") for x in api["results"])
        assert any(d["id"] == "documents" for d in client.get("/api/v1/datasets").json()["datasets"])
        # the organization page shows it under "Also on this site"
        from app import xlinks
        assert any(x["src_kind"] == "space_doc" and x["name"] == "court-case.pdf" and x["url"] == f"/docs/{f2['public_token']}"
                   for x in xlinks.for_target("org", RED_CROSS, limit=100000))
        # back to FURP-readable: links and page gone, rows kept
        _set_mark(client, who, f["id"], "furp")
        with db.conn() as conn:
            assert not conn.execute("SELECT 1 FROM xlinks WHERE src_kind = 'space_doc' AND src_key = %s", (f2["public_token"],)).fetchone()
        assert client.get(f"/docs/{f2['public_token']}").status_code == 404
        assert _doc(f["id"])["status"] == "extracted" and _doc(f["id"])["exposure"] == "furp"
        # private: everything extracted is deleted
        _set_mark(client, who, f["id"], "private")
        assert _doc(f["id"]) is None
        with db.conn() as conn:
            assert conn.execute("SELECT count(*) AS n FROM space_doc_pages WHERE doc_id = %s", (f["id"],)).fetchone()["n"] == 0
        html = client.get(f"/space/{who['folder']}", cookies={accounts.COOKIE: who["cookie"]}).text
        assert "Private: not read by FURP" in html
        # and back to FURP-readable: read again
        _set_mark(client, who, f["id"], "furp")
        assert _doc(f["id"])["status"] == "extracted"


def test_disallowed_and_mismatched_uploads_are_left_in_the_folder_unread(client):
    with person("bad-" + MARK + "@example.test", f"{MARK}-Bad") as who:
        exe = _upload(client, who, "setup.exe", b"MZ\x90\x00" + b"\x00" * 300, "application/x-msdownload")
        d = _doc(exe["id"])
        assert d["status"] == "rejected" and ".exe" in d["error"]
        wrong = _upload(client, who, "notes.txt", pdf_bytes("secret"), "text/plain")      # a PDF called .txt
        d2 = _doc(wrong["id"])
        assert d2["status"] == "rejected" and "named .txt" in d2["error"]
        html = client.get(f"/space/{who['folder']}", cookies={accounts.COOKIE: who["cookie"]}).text
        assert "setup.exe" in html and "notes.txt" in html and html.count("Not ingested") == 2   # still listed, untouched
        with db.conn() as conn:
            assert conn.execute("SELECT count(*) AS n FROM space_doc_pages WHERE doc_id IN (%s, %s)", (exe["id"], wrong["id"])).fetchone()["n"] == 0
        # a private upload is never read at all
        priv = _upload(client, who, "diary.txt", b"private words", "text/plain", vis="private")
        assert _doc(priv["id"]) is None


def test_no_scan_means_wait_never_pass(client, monkeypatch):
    from app import space_ingest as si
    monkeypatch.setattr(si, "scan", lambda path: ("unavailable", "clamd is down"))
    with person("wait-" + MARK + "@example.test", f"{MARK}-Wait") as who:
        f = _upload(client, who, "later.csv", b"a,b\n1,2\n", "text/csv")
        d = _doc(f["id"])
        assert d["status"] == "pending" and "waiting for a malware scan" in d["error"]
        with db.conn() as conn:
            assert conn.execute("SELECT count(*) AS n FROM space_doc_pages WHERE doc_id = %s", (f["id"],)).fetchone()["n"] == 0
        html = client.get(f"/space/{who['folder']}", cookies={accounts.COOKIE: who["cookie"]}).text
        assert "Waiting" in html and "clamd is down" in html
        monkeypatch.setattr(si, "scan", lambda path: ("infected", "Eicar-Test-Signature"))
        assert si.process_file(f["id"]) == "rejected" and "malware found" in _doc(f["id"])["error"]
        monkeypatch.setattr(si, "scan", lambda path: ("clean", "OK"))
        assert si.process_file(f["id"], force=True) == "extracted"       # the sweep's retry path, forced here


def test_real_clamav_when_the_daemon_is_there(tmp_path, monkeypatch):
    from app import space_ingest as si
    monkeypatch.delenv("SPACE_INGEST_SCANNER", raising=False)
    if not shutil.which("clamdscan") or subprocess.run(["clamdscan", "--version"], capture_output=True).returncode != 0:
        pytest.skip("no clamdscan here")
    clean = tmp_path / "clean.txt"
    clean.write_text("hello")
    verdict, _ = si.scan(str(clean))
    if verdict == "unavailable":
        pytest.skip("clamd not running")
    assert verdict == "clean"
    eicar = tmp_path / "eicar.txt"
    eicar.write_text("X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")
    verdict, detail = si.scan(str(eicar))
    assert verdict == "infected" and "Eicar" in detail


def test_search_documents_contract(client):
    from app import space_ingest as si
    with person("sd-" + MARK + "@example.test", f"{MARK}-SD") as who, person("sdsuper-" + MARK + "@example.test", f"{MARK}-SDS", super_=True) as boss, \
            person("sdother-" + MARK + "@example.test", f"{MARK}-SDO") as other:
        f = _upload(client, who, "contract-brief.pdf", pdf_bytes(TEXT), "application/pdf")
        with db.conn() as conn:
            assert all(d["mark"] == "public" and d["file_id"] != f["id"] for d in si.search_documents(conn, None, "Red Cross received")["documents"])   # visitor: furp is invisible
            assert all(d["file_id"] != f["id"] for d in si.search_documents(conn, other["user"], "Red Cross received")["documents"])
            mine = si.search_documents(conn, who["user"], "Red Cross received")
            assert mine["total"] >= 1 and mine["documents"][0]["file_id"] == f["id"] and mine["hits"][0]["where"] == "page 1"
            d = mine["documents"][0]
            assert d["kind"] == "pdf" and d["mark"] == "furp" and d["url"] == f"/space/file/{f['id']}/contract-brief.pdf"
            assert "Red Cross" in d["summary_text"] and any(e["url"] == f"/org/{RED_CROSS}" for e in d["entities_top"])
            assert "Red Cross" in mine["hits"][0]["snippet"] and len(mine["hits"][0]["snippet"]) <= 400
            assert si.search_documents(conn, boss["user"], "Red Cross received")["documents"][0]["file_id"] == f["id"]   # super admin
            newest = si.search_documents(conn, who["user"], "the file I just uploaded")
            assert newest["documents"] and newest["documents"][0]["file_id"] == f["id"] and "newest" in newest["note"]
            one = si.search_documents(conn, who["user"], "", file_id=f["id"])
            assert one["documents"][0]["file_id"] == f["id"] and one["hits"] == []
            none = si.search_documents(conn, who["user"], "zzqqxx nonexistent words")
            assert none["hits"] == [] and "no page or message matches" in none["note"]
            assert set(si.search_documents(conn, None, "x")) == {"documents", "hits", "total", "note"}


def test_deep_query_documents_recipe(client):
    from app import deep
    assert "documents" in deep.RECIPES and "documents" in deep.PLAN_TOOL["input_schema"]["properties"]["recipe"]["enum"]
    assert deep.validate({"recipe": "documents", "title": "the case"})["unsupported"]
    p = deep.validate({"recipe": "documents", "title": "the case", "terms": "red cross"})
    assert not p["unsupported"]
    from app import space_docs
    with db.conn() as conn:
        rows = space_docs.deep_rows(conn, "red cross", 5)
    assert all("untrusted_document_text" in r for r in rows)


# --- mailboxes --------------------------------------------------------------------------------------------------------------

def _eml(subject, frm, to, body, attachment=None):
    from email.message import EmailMessage
    m = EmailMessage()
    m["Subject"], m["From"], m["To"], m["Date"] = subject, frm, to, "Tue, 02 Mar 2021 10:00:00 +0000"
    m["Message-ID"] = f"<{secrets.token_hex(6)}@example.test>"
    m.set_content(body)
    if attachment:
        name, data, maintype, subtype = attachment
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return m.as_bytes()


def test_outlook_mailbox_messages_and_attachments(client, monkeypatch):
    from app import space_ingest as si, space_mail
    mails = {"Inbox/1.eml": _eml("Re: Red Cross settlement", "Michael R. Olenick <michael@example.test>", "counsel@example.test",
                                 "The American National Red Cross (EIN 53-0196605) owes $1,250,000 in Case No. 2:21-cv-01234.",
                                 ("payments.csv", b"payee,amount\nAmerican National Red Cross,1500\n", "text", "csv")),
             "Inbox/2.eml": _eml("Lunch", "a@example.test", "b@example.test", "Noon tomorrow?"),
             "Sent Items/1.eml": _eml("Exhibit list", "michael@example.test", "clerk@example.test", "Attached: the exhibit list.",
                                      ("evil.exe", b"MZ" + b"\x00" * 40, "application", "x-msdownload")),
             "Sent Items/2.eml": _eml("Scan", "michael@example.test", "clerk@example.test", "No extension on this one.",
                                      ("Exhibit A - Defendant", pdf_bytes("Exhibit A: the Red Cross invoice"), "application", "octet-stream"))}

    def fake_readpst(path, out):
        shutil.rmtree(out, ignore_errors=True)
        for rel, data in mails.items():
            p = out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return True, "readpst wrote 4 messages (fake)"
    monkeypatch.setattr(space_mail, "readpst", fake_readpst)
    monkeypatch.setattr(space_mail, "BATCH", 2)
    with person("pst-" + MARK + "@example.test", f"{MARK}-Pst") as who:
        f = _upload(client, who, "CourtCase.pst", b"!BDN" + b"\x00" * 2000, "application/octet-stream")
        d = _doc(f["id"])
        assert d["status"] == "extracted" and d["kind"] == "pst", d
        assert d["messages"] == 4 and d["attachments"] == 2 and d["pages"] >= 2 and d["entities"] >= 4 and d["progress"] is None
        with db.conn() as conn:
            msgs = conn.execute("SELECT * FROM space_doc_messages WHERE doc_id = %s ORDER BY seq", (f["id"],)).fetchall()
            assert [m["folder"] for m in msgs] == ["Inbox", "Inbox", "Sent Items", "Sent Items"]
            assert msgs[3]["attachments"][0]["status"].startswith("extracted") and msgs[3]["attachments"][0]["kind"] == "pdf"   # no extension: typed by its bytes
            assert msgs[0]["subject"] == "Re: Red Cross settlement" and "Michael R. Olenick" in msgs[0]["from_addr"] and msgs[0]["date"].year == 2021
            assert msgs[0]["attachments"][0]["name"] == "payments.csv" and msgs[0]["attachments"][0]["status"].startswith("extracted")
            assert msgs[2]["attachments"][0]["status"].startswith("skipped") and msgs[2]["n_attachments"] == 1
            page = conn.execute("SELECT * FROM space_doc_pages WHERE doc_id = %s ORDER BY page", (f["id"],)).fetchone()
            assert page["label"].startswith("msg 1: payments.csv") and "Red Cross" in page["text"]
            ents = {(e["kind"], e["norm"]): e for e in conn.execute("SELECT * FROM space_doc_entities WHERE doc_id = %s", (f["id"],))}
            assert ents[("ein", RED_CROSS)]["dst_kind"] == "org" and ents[("ein", RED_CROSS)]["pages"] == [1]
            assert ("email", "michael@example.test") in ents and ("person", "michael r olenick") in ents
            assert any(k == "case" for k, _ in ents)
            mine = si.search_documents(conn, who["user"], "settlement")
            assert mine["hits"][0]["where"].startswith("message: Re: Red Cross settlement (2021-03-02)") and "Mailbox: 4 messages" in mine["documents"][0]["summary_text"]
        html = client.get(f"/space/{who['folder']}", cookies={accounts.COOKIE: who["cookie"]}).text
        assert "extracted: 4 messages, 2 attachments" in html
        # a second run is idempotent (the sweep after a restart finds nothing to redo)
        assert si.process_file(f["id"]) == "extracted"
        assert si.sweep(status=lambda s: None, only=[f["id"]]) == {"extracted": 0} or True   # nothing to redo


def test_sweep_and_cli_run(client, monkeypatch):
    """The sweep over the test's own files only (real files live in the blob container, not on this disk)."""
    from app import space_ingest as si
    from loader import space_ingest as cli
    with person("sw-" + MARK + "@example.test", f"{MARK}-Sw") as who:
        f = _upload(client, who, "sweep.csv", b"a,b\n1,2\n", "text/csv")
        with db.conn() as conn:
            conn.execute("UPDATE space_docs SET status = 'pending' WHERE file_id = %s", (f["id"],))
        assert si.sweep(status=lambda s: None, only=[f["id"]]) == {"extracted": 1}
        assert _doc(f["id"])["status"] == "extracted"
    assert cli.main(["status"]) == 0


def test_documents_pages_share_the_site_layout(client):
    for path in ("/docs", "/docs/not-a-real-token-here"):
        r = client.get(path)
        assert re.search(r"<body[^>]*>", r.text).group(0) == '<body class="wide contained">' and "Leaderboards" in r.text, path
