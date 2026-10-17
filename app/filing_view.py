"""Render a stored e-file XML return as readable HTML.

Every part and schedule becomes a section; repeating groups become tables; each
value carries its raw IRS element name (shown faintly) so it can be cited.
"""

from __future__ import annotations

import gzip
import re
from collections import Counter

from lxml import etree
from markupsafe import Markup, escape

from app.config import XML_DIR
from app.fmt import humanize, money

SECTION_NAMES = {
    "ReturnHeader": "Return header",
    "IRS990": "Form 990",
    "IRS990EZ": "Form 990-EZ",
    "IRS990PF": "Form 990-PF",
}
_SCHED = re.compile(r"^IRS990(?:EZ|PF)?Schedule([A-Z])$")
_AMOUNT = re.compile(r"(Amt|Amount)$")


def section_name(tag: str) -> str:
    m = _SCHED.match(tag)
    if m:
        return f"Schedule {m.group(1)}"
    return SECTION_NAMES.get(tag, humanize(tag))


def load_xml(rel_path: str) -> bytes:
    path = (XML_DIR / rel_path).resolve()
    if XML_DIR.resolve() not in path.parents:
        raise FileNotFoundError(rel_path)
    with gzip.open(path) as f:
        return f.read()


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _value(tag: str, text: str) -> str:
    if _AMOUNT.search(tag):
        try:
            return money(int(float(text)))
        except ValueError:
            pass
    if text in ("X", "true", "1") and tag.endswith("Ind"):
        return "Yes (" + text + ")"
    return text


def _leaves(el, prefix=""):
    """(relative path, text) of every leaf under el."""
    for ch in el:
        tag = _local(ch.tag)
        if not tag:
            continue
        path = f"{prefix}/{tag}" if prefix else tag
        if len(ch):
            yield from _leaves(ch, path)
        else:
            yield path, (ch.text or "").strip()


_NUMERIC = re.compile(r"(Amt|Amount|Cnt|Count|Rt|Pct|Num)$")


def _num_class(tag: str) -> str:
    """Right-align amounts, counts and rates; leave words left-aligned."""
    return ' class="n"' if _NUMERIC.search(tag) else ' class="text"'


def _field_row(tag: str, path: str, text: str) -> str:
    return (f'<tr><th scope="row">{escape(humanize(tag))}</th>'
            f'<td>{escape(_value(tag, text))}</td>'
            f'<td class="raw-col">{escape(path)}</td></tr>')


def _fields_table(rows: list[str]) -> str:
    return ('<div class="scroll"><table class="fields"><thead><tr><th>Field</th><th>Value</th>'
            '<th class="raw-col">IRS element (for citing)</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def _records(tag: str, items) -> str:
    """A repeating group: one small table per entry, its first value as the title."""
    cards = []
    for i, it in enumerate(items, 1):
        leaves = [(p, t) for p, t in _leaves(it) if t]
        title = leaves[0][1] if leaves else f"Entry {i}"
        rows = "".join(
            f'<tr><th scope="row">{escape(humanize(p.rsplit("/", 1)[-1]))}<span class="raw">{escape(p)}</span></th>'
            f'<td{_num_class(p.rsplit("/", 1)[-1])}>{escape(_value(p.rsplit("/", 1)[-1], t))}</td></tr>' for p, t in leaves)
        cards.append(
            f'<table class="record" data-copy-title-cols=\'["#"]\' data-copy-title=\'["{i}"]\'>'
            f'<thead><tr><th colspan="2"><span class="record-title">{escape(title)}</span>'
            f'<span class="record-meta">{escape(humanize(tag))} {i} of {len(items)}</span></th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')
    return (f'<div class="group"><h4>{escape(humanize(tag))} <span class="raw">{escape(tag)}</span> '
            f'<span class="count">({len(items)} entries)</span></h4>'
            f'<div class="records">{"".join(cards)}</div></div>')


def _node(el, prefix: str = "") -> str:
    """A group: its fields as one table, nested groups and repeating groups after."""
    out, rows = [], []
    children = [c for c in el if _local(c.tag)]
    counts = Counter(_local(c.tag) for c in children)
    done = set()

    def flush():
        if rows:
            out.append(_fields_table(rows))
            rows.clear()

    for ch in children:
        tag = _local(ch.tag)
        path = f"{prefix}/{tag}" if prefix else tag
        if counts[tag] > 1 and len(ch):
            if tag in done:
                continue
            done.add(tag)
            flush()
            out.append(_records(tag, [c for c in children if _local(c.tag) == tag]))
        elif len(ch):
            flush()
            out.append(f'<div class="group"><h4>{escape(humanize(tag))} <span class="raw">{escape(tag)}</span></h4>'
                       f'{_node(ch, path)}</div>')
        else:
            rows.append(_field_row(tag, tag, (ch.text or "").strip()))
    flush()
    return "".join(out)


def render(xml: bytes) -> list[dict]:
    root = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    sections = []
    header = next((c for c in root if _local(c.tag) == "ReturnHeader"), None)
    if header is not None:
        sections.append({"id": "ReturnHeader", "title": "Return header", "html": Markup(_node(header))})
    data = next((c for c in root if _local(c.tag) == "ReturnData"), None)
    if data is not None:
        for ch in data:
            tag = _local(ch.tag)
            if not tag:
                continue
            sections.append({"id": tag, "title": section_name(tag), "html": Markup(_node(ch))})
    return sections
