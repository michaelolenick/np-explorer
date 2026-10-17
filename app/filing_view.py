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


def _table(tag: str, items) -> str:
    rows = [dict(_leaves(it)) for it in items]
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    head = "".join(f'<th>{escape(humanize(c.rsplit("/", 1)[-1]))}<span class="raw">{escape(c)}</span></th>'
                   for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{escape(_value(c.rsplit('/', 1)[-1], r.get(c, '')))}</td>" for c in cols)
                   + "</tr>" for r in rows)
    return (f'<div class="group"><h4>{escape(humanize(tag))} <span class="raw">{escape(tag)}</span> '
            f'<span class="count">({len(rows)} rows)</span></h4>'
            f'<div class="scroll"><table class="xml"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>')


def _node(el) -> str:
    out = []
    children = [c for c in el if _local(c.tag)]
    counts = Counter(_local(c.tag) for c in children)
    done = set()
    for ch in children:
        tag = _local(ch.tag)
        if counts[tag] > 1 and len(ch):
            if tag in done:
                continue
            done.add(tag)
            out.append(_table(tag, [c for c in children if _local(c.tag) == tag]))
        elif len(ch):
            out.append(f'<div class="group"><h4>{escape(humanize(tag))} <span class="raw">{escape(tag)}</span></h4>'
                       f'{_node(ch)}</div>')
        else:
            text = (ch.text or "").strip()
            out.append(f'<div class="f"><span class="k">{escape(humanize(tag))}</span> '
                       f'<span class="v">{escape(_value(tag, text))}</span> <span class="raw">{escape(tag)}</span></div>')
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
