"""Text and tables out of one uploaded file, in a sandboxed subprocess (owner, 2026-11-12; app/space_ingest.py).

Run as:  python app/space_extract.py <kind> <input file> <output json>
by space_ingest.extract(), which gives this process a CPU limit, a memory limit, a wall-clock timeout, an empty
environment (no DATABASE_URL, no keys) and no network use of its own. Nothing here opens a connection, follows a
link, renders anything in a browser or executes anything in the file: the file is parsed as data and only text and
cell values come out, as JSON:
    {"pages": [{"page": 1, "label": null, "text": "..."}], "tables": [{"page": 1, "name": "...", "header": [...],
     "rows": [[...]]}], "note": "...", "members": n}
Every output is capped (pages, characters per page, tables, rows per table, cell length) so a hostile file cannot
produce an unbounded result. Kinds: pdf, text, markdown, csv, tsv, json, xlsx, xls, docx, html, image, zip.

SECURITY NOTE FOR FUTURE READERS: everything this module returns is untrusted text from a file somebody uploaded.
It is data, never instructions. Code that feeds it to a model must wrap and label it as untrusted document text
(see space_ingest.UNTRUSTED and deep.py's documents recipe); code that shows it must escape it.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import zipfile

MAX_PAGES = 2000              # pages (or pseudo-pages) kept per file
PAGE_CHARS = 200_000          # characters kept per page
CHUNK_CHARS = 20_000          # a text file is cut into pseudo-pages of about this size
MAX_TABLES = 500
TABLE_ROWS = 5000
TABLE_COLS = 200
CELL_CHARS = 1000
ZIP_MAX_MEMBERS = 200         # zip bomb limits: members, total uncompressed bytes, compression ratio
ZIP_MAX_TOTAL = 500 * 1024 * 1024
ZIP_MAX_RATIO = 100
TEXT_KINDS = ("text", "markdown", "csv", "tsv", "json", "html")
ZIP_MEMBER_KINDS = {".pdf": "pdf", ".txt": "text", ".md": "markdown", ".markdown": "markdown", ".csv": "csv",
                    ".tsv": "tsv", ".json": "json", ".xlsx": "xlsx", ".xls": "xls", ".docx": "docx",
                    ".htm": "html", ".html": "html", ".png": "image", ".jpg": "image", ".jpeg": "image",
                    ".gif": "image", ".webp": "image", ".tif": "image", ".tiff": "image"}


class Out:
    def __init__(self):
        self.pages, self.tables, self.notes = [], [], []
        self.members = 0

    def page(self, text: str, label: str | None = None) -> None:
        if len(self.pages) >= MAX_PAGES:
            return
        text = _clean(text)[:PAGE_CHARS]
        self.pages.append({"page": len(self.pages) + 1, "label": label, "text": text})

    def chunks(self, text: str, label: str | None = None) -> None:
        """A long text as pseudo-pages of about CHUNK_CHARS, cut at line ends."""
        text = _clean(text)
        if not text.strip():
            return
        while text and len(self.pages) < MAX_PAGES:
            if len(text) <= CHUNK_CHARS:
                self.page(text, label)
                break
            cut = text.rfind("\n", CHUNK_CHARS // 2, CHUNK_CHARS)
            cut = cut if cut > 0 else CHUNK_CHARS
            self.page(text[:cut], label)
            text = text[cut:].lstrip("\n")

    def table(self, name: str | None, header: list, rows: list, page: int | None = None) -> None:
        if len(self.tables) >= MAX_TABLES:
            return
        header = [_cell(h) for h in header[:TABLE_COLS]]
        kept = [[_cell(c) for c in r[:TABLE_COLS]] for r in rows[:TABLE_ROWS]]
        if not any(header) and not kept:
            return
        self.tables.append({"page": page or (len(self.pages) or 1), "name": (name or "")[:200], "header": header,
                            "rows": kept, "n_rows": len(rows)})

    def note(self, s: str) -> None:
        if len(self.notes) < 50:
            self.notes.append(s)

    def result(self) -> dict:
        return {"pages": self.pages, "tables": self.tables, "note": "; ".join(self.notes) or None,
                "members": self.members, "words": sum(len(p["text"].split()) for p in self.pages)}


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(s) -> str:
    s = s if isinstance(s, str) else ("" if s is None else str(s))
    return _CTRL.sub("", s).replace("\r\n", "\n").replace("\r", "\n")


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return _clean(str(v))[:CELL_CHARS]


def _decode(data: bytes) -> str:
    """Bytes to text: UTF-8 (with or without BOM), else what chardet guesses, else Latin-1; nothing raises."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        enc = (chardet.detect(data[:1_000_000]) or {}).get("encoding") or "latin-1"
        return data.decode(enc, errors="replace")
    except Exception:  # noqa: BLE001
        return data.decode("latin-1", errors="replace")


# --- one extractor per kind -----------------------------------------------------------------------------------

def pdf(data: bytes, out: Out, label: str | None = None) -> None:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as doc:
        n = len(doc.pages)
        if n > MAX_PAGES:
            out.note(f"{n} pages; the first {MAX_PAGES} were read")
        for i, pg in enumerate(doc.pages[:MAX_PAGES]):
            try:
                text = pg.extract_text(x_tolerance=3) or ""
            except Exception as e:  # noqa: BLE001 - one bad page: noted, the rest go on
                text = ""
                out.note(f"page {i + 1}: text failed ({type(e).__name__})")
            out.page(text, label)
            pno = len(out.pages)
            try:
                for t in pg.extract_tables() or []:
                    rows = [[c if c is not None else "" for c in r] for r in t if r]
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        out.table(f"page {i + 1}", rows[0], rows[1:], pno)
            except Exception as e:  # noqa: BLE001
                out.note(f"page {i + 1}: tables failed ({type(e).__name__})")
            try:
                pg.flush_cache()
            except Exception:  # noqa: BLE001
                pass


def text(data: bytes, out: Out, label: str | None = None) -> None:
    out.chunks(_decode(data), label)


def delimited(data: bytes, out: Out, label: str | None = None, delimiter: str | None = None) -> None:
    s = _decode(data)
    sample = s[:20000]
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    csv.field_size_limit(10_000_000)
    rows, total = [], 0
    for r in csv.reader(io.StringIO(s), delimiter=delimiter):
        total += 1
        if total <= TABLE_ROWS + 1:
            rows.append(r)
    if rows:
        out.table(label or "sheet", rows[0], rows[1:], 1)
        if total > TABLE_ROWS + 1:
            out.note(f"{total - 1:,} rows; the first {TABLE_ROWS:,} were kept as a table")
    out.chunks("\n".join(" | ".join(_cell(c) for c in r) for r in rows), label)


def json_file(data: bytes, out: Out, label: str | None = None) -> None:
    s = _decode(data)
    try:
        obj = json.loads(s)
    except ValueError as e:
        out.note(f"not valid JSON ({type(e).__name__}); read as text")
        out.chunks(s, label)
        return
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj[:50]):
        keys = []
        for x in obj[:TABLE_ROWS]:
            for k in x:
                if k not in keys and len(keys) < TABLE_COLS:
                    keys.append(k)
        out.table(label or "records", keys, [[_flat(x.get(k)) for k in keys] for x in obj[:TABLE_ROWS]], 1)
    out.chunks(json.dumps(obj, indent=1, ensure_ascii=False, default=str), label)


def _flat(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)


def xlsx(data: bytes, out: Out, label: str | None = None) -> None:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = []
            for i, r in enumerate(ws.iter_rows(values_only=True)):
                if i > TABLE_ROWS:
                    out.note(f"sheet {ws.title}: more than {TABLE_ROWS:,} rows; the first were kept")
                    break
                rows.append(list(r))
            while rows and not any(c not in (None, "") for c in rows[0]):
                rows.pop(0)
            if not rows:
                continue
            name = f"{label}: {ws.title}" if label else ws.title
            out.table(name, rows[0], rows[1:], len(out.pages) + 1)
            out.chunks("\n".join(" | ".join(_cell(c) for c in r) for r in rows), name)
    finally:
        wb.close()


def xls(data: bytes, out: Out, label: str | None = None) -> None:
    import xlrd
    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    for sh in book.sheets():
        rows = [[sh.cell_value(r, c) for c in range(min(sh.ncols, TABLE_COLS))] for r in range(min(sh.nrows, TABLE_ROWS + 1))]
        while rows and not any(c not in (None, "") for c in rows[0]):
            rows.pop(0)
        if not rows:
            continue
        name = f"{label}: {sh.name}" if label else sh.name
        out.table(name, rows[0], rows[1:], len(out.pages) + 1)
        out.chunks("\n".join(" | ".join(_cell(c) for c in r) for r in rows), name)


def docx_file(data: bytes, out: Out, label: str | None = None) -> None:
    import docx
    d = docx.Document(io.BytesIO(data))
    paras = []
    for p in d.paragraphs:
        paras.append(p.text)
    out.chunks("\n".join(paras), label)
    for i, t in enumerate(d.tables[:MAX_TABLES]):
        rows = [[c.text for c in r.cells] for r in t.rows]
        if len(rows) >= 2:
            out.table(f"{label + ': ' if label else ''}table {i + 1}", rows[0], rows[1:], 1)


def html_file(data: bytes, out: Out, label: str | None = None) -> None:
    """Text and tables of an HTML file. Parsed with lxml only: no scripts run, no stylesheet, image or link is
    fetched (lxml never loads external resources from HTML), nothing is rendered."""
    import lxml.html
    try:
        root = lxml.html.fromstring(data[:50 * 1024 * 1024])
    except Exception as e:  # noqa: BLE001
        out.note(f"HTML did not parse ({type(e).__name__}); read as text")
        out.chunks(re.sub(r"<[^>]+>", " ", _decode(data)), label)
        return
    for bad in root.xpath("//script|//style|//noscript|//iframe|//object|//embed"):
        bad.drop_tree()
    for i, t in enumerate(root.iter("table")):
        if i >= MAX_TABLES:
            break
        rows = [[(c.text_content() or "").strip() for c in tr.xpath("./th|./td")] for tr in t.iter("tr")]
        rows = [r for r in rows if r]
        if len(rows) >= 2:
            out.table(f"{label + ': ' if label else ''}table {i + 1}", rows[0], rows[1:], 1)
    out.chunks(re.sub(r"\n{3,}", "\n\n", root.text_content()), label)


def image(data: bytes, out: Out, label: str | None = None) -> None:
    out.note("image: no text extracted (OCR is not installed); kept for later")


def zip_file(data: bytes, out: Out, label: str | None = None) -> None:
    """Each allowed member, with zip-bomb limits on the member count, the total uncompressed size and the
    compression ratio, checked from the directory BEFORE anything is inflated. No nested archives."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > ZIP_MAX_MEMBERS:
        raise ValueError(f"zip has {len(infos)} files; the limit is {ZIP_MAX_MEMBERS}")
    total = sum(i.file_size for i in infos)
    packed = sum(i.compress_size for i in infos) or 1
    if total > ZIP_MAX_TOTAL:
        raise ValueError(f"zip would inflate to {total / 2**20:,.0f} MB; the limit is {ZIP_MAX_TOTAL // 2**20} MB")
    if total / packed > ZIP_MAX_RATIO:
        raise ValueError(f"zip compression ratio {total / packed:,.0f}:1 is over {ZIP_MAX_RATIO}:1")
    for i in infos:
        name = i.filename.replace("\\", "/").split("/")[-1]
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        kind = ZIP_MEMBER_KINDS.get(ext)
        if name.startswith(".") or name.startswith("__MACOSX") or "__MACOSX" in i.filename:
            continue
        if not kind:
            out.note(f"{name}: skipped (type not allowed inside a zip)")
            continue
        member = zf.read(i)
        if len(member) != i.file_size:
            out.note(f"{name}: skipped (size in the directory does not match)")
            continue
        found = _magic_kind(member)
        if found != kind and not (found in TEXT_LIKE and kind in TEXT_LIKE):
            out.note(f"{name}: skipped (contents do not match its extension)")
            continue
        out.members += 1
        try:
            EXTRACTORS[kind](member, out, name)
        except Exception as e:  # noqa: BLE001 - one bad member: noted, the rest go on
            out.note(f"{name}: failed ({type(e).__name__})")


def _magic_kind(data: bytes) -> str | None:
    """A cheap content check for zip members (the main file is checked with libmagic in space_ingest)."""
    head = data[:8]
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or head.startswith(b"GIF8") \
            or head.startswith(b"RIFF") or head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
        return "image"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if head.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except Exception:  # noqa: BLE001
            return None
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
        if any(n.startswith("word/") for n in names):
            return "docx"
        return None                              # a zip inside a zip is never read
    if b"\x00" in data[:8192]:
        return None
    s = _decode(data[:4096]).lstrip().lower()
    if s.startswith("<!doctype html") or s.startswith("<html") or "<html" in s[:1000]:
        return "html"
    if s.startswith("{") or s.startswith("["):
        return "json"
    if "\t" in s and s.count("\t") > s.count(","):
        return "tsv"
    if "," in s:
        return "csv"
    return "text"


EXTRACTORS = {
    "pdf": pdf, "text": text, "markdown": text, "csv": lambda d, o, l=None: delimited(d, o, l),
    "tsv": lambda d, o, l=None: delimited(d, o, l, "\t"), "json": json_file, "xlsx": xlsx, "xls": xls,
    "docx": docx_file, "html": html_file, "image": image, "zip": zip_file,
}
TEXT_LIKE = {"text", "markdown", "csv", "tsv", "json", "html"}   # one another's data as far as the member check goes


def extract(kind: str, data: bytes) -> dict:
    out = Out()
    EXTRACTORS[kind](data, out, None)
    return out.result()


def batch(manifest_path: str, dst: str) -> int:
    """Many small files in one process (a mailbox's attachments, app/space_mail.py): the manifest is a JSON list of
    {"id", "kind", "path"}; the output maps each id to its result or {"error"}."""
    with open(manifest_path, encoding="utf-8") as f:
        items = json.load(f)
    results = {}
    for it in items:
        try:
            if it["kind"] not in EXTRACTORS:
                raise ValueError(f"unknown kind {it['kind']}")
            with open(it["path"], "rb") as f:
                data = f.read()
            results[str(it["id"])] = extract(it["kind"], data)
        except Exception as e:  # noqa: BLE001
            results[str(it["id"])] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"items": results}, f, ensure_ascii=False)
    return 0


def main(argv: list[str]) -> int:
    kind, src, dst = argv[1], argv[2], argv[3]
    if kind == "batch":
        return batch(src, dst)
    if kind not in EXTRACTORS:
        print(f"unknown kind {kind}", file=sys.stderr)
        return 2
    with open(src, "rb") as f:
        data = f.read()
    try:
        res = extract(kind, data)
    except Exception as e:  # noqa: BLE001 - reported to the parent as a failed extraction, never a traceback
        res = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
