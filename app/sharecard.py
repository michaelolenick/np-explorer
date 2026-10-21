"""Share cards: a 1200x630 black-and-white PNG of a board's top ten, for link previews."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app import boards as B
from app.config import SITE_URL

W, H = 1200, 630
MARGIN = 48
FONT_DIRS = [Path("/usr/share/fonts/truetype/liberation"), Path("/usr/share/fonts/truetype/freefont")]
REGULAR = ["LiberationMono-Regular.ttf", "FreeMono.ttf"]
BOLD = ["LiberationMono-Bold.ttf", "FreeMonoBold.ttf"]

_cache: dict = {}


def _font(names: list[str], size: int):
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default(size)


def _fit(draw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "...", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "..."


def host() -> str:
    """The site's address as printed on cards, e.g. "furp.org"."""
    return SITE_URL.split("://", 1)[-1].rstrip("/")


def credit_line(name: str, path: str) -> tuple[str, str]:
    """The card's credit: (page or board name, site address with path). Every card type uses it."""
    return " ".join((name or "").split()), f"{host()}{path}"


def draw_footer(d, name: str, path: str, note: str, font) -> None:
    """The same bottom band on every card: a rule, the source note, then "<name> | furp.org/<path>"."""
    y = H - MARGIN - 52
    d.line([MARGIN, y, W - MARGIN, y], fill=0, width=2)
    d.text((MARGIN, y + 12), _fit(d, note, font, W - 2 * MARGIN), font=font, fill=0)
    label, url = credit_line(name, path)
    sep = " | "
    room = W - 2 * MARGIN - d.textlength(sep + url, font=font)
    d.text((MARGIN, y + 36), (_fit(d, label, font, room) + sep if label and room > 80 else "") + url, font=font, fill=0)


def render(board: B.Board, rows: list[dict], meta: dict | None) -> bytes:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    title, sub, body, small = _font(BOLD, 40), _font(REGULAR, 26), _font(REGULAR, 24), _font(REGULAR, 20)
    d.rectangle([12, 12, W - 13, H - 13], outline=0, width=4)
    y = MARGIN - 8
    d.text((MARGIN, y), _fit(d, board.title, title, W - 2 * MARGIN), font=title, fill=0)
    y += 50
    d.text((MARGIN, y), _fit(d, f'"{board.subtitle}"', sub, W - 2 * MARGIN), font=sub, fill=0)
    y += 42
    d.line([MARGIN, y, W - MARGIN, y], fill=0, width=2)
    y += 14
    value_w = 220
    for r in rows[:10]:
        rank = f"{r['rank']:>2}."
        val = B.fmt(r["value"], board.value.fmt)
        year = str(r.get("tax_year") or "")
        d.text((MARGIN, y), rank, font=body, fill=0)
        name_w = W - 2 * MARGIN - 70 - value_w - 90
        d.text((MARGIN + 70, y), _fit(d, r["subject_name"] or "", body, name_w), font=body, fill=0)
        d.text((W - MARGIN - 90 - d.textlength(val, font=body) - 16, y), val, font=body, fill=0)
        d.text((W - MARGIN - d.textlength(year, font=body), y), year, font=body, fill=0)
        y += 34
    if not rows:
        d.text((MARGIN, y), "Being built. Check back soon.", font=body, fill=0)
    if board.kind == "990":
        source = f"{board.source_label}, {B.window(meta)}"
    else:
        span = f", {meta['year_min']} to {meta['year_max']}" if meta and meta.get("year_min") else ""
        source = f"{board.source_label[0].upper()}{board.source_label[1:]}{span}"
    draw_footer(d, board.title, f"/boards/{board.slug}", source, small)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def card(board: B.Board, rows: list[dict], meta: dict | None) -> bytes:
    """Cached per board until the board is refreshed."""
    key = (board.slug, str((meta or {}).get("refreshed_at")))
    if key not in _cache:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = render(board, rows, meta)
    return _cache[key]
