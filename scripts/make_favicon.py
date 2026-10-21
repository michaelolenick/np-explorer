#!/usr/bin/env python3
"""Generate the favicon set: a black square with a white lowercase f (furp.org).

The glyph comes from Nimbus Sans Bold (URW's metric clone of Helvetica Bold;
apt install fonts-urw-base35). The SVG embeds the glyph as a path so it does
not depend on fonts installed on the viewer's machine.

Usage: .venv/bin/python scripts/make_favicon.py
"""

from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf"  # bold sans (Helvetica Bold metrics)
CHAR = "f"  # lowercase f, for furp.org
STATIC = Path(__file__).resolve().parent.parent / "static"
GLYPH_HEIGHT = 0.72  # glyph height as a fraction of the icon size


def png(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), "black")
    draw = ImageDraw.Draw(img)
    # Find the font size that makes the glyph's ink GLYPH_HEIGHT of the icon, then center the ink.
    probe = ImageFont.truetype(FONT, 1000)
    l, t, r, b = probe.getbbox(CHAR)
    font = ImageFont.truetype(FONT, round(1000 * size * GLYPH_HEIGHT / (b - t)))
    l, t, r, b = font.getbbox(CHAR)
    draw.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), CHAR, font=font, fill="white")
    return img


def svg() -> str:
    font = TTFont(FONT)
    glyph_set = font.getGlyphSet()
    glyph = glyph_set[font.getBestCmap()[ord(CHAR)]]
    bounds = BoundsPen(glyph_set)
    glyph.draw(bounds)
    x0, y0, x1, y1 = bounds.bounds
    scale = 100 * GLYPH_HEIGHT / (y1 - y0)
    # Flip y (font units point up) and center the ink in a 100x100 box.
    dx = (100 - (x1 - x0) * scale) / 2 - x0 * scale
    dy = (100 + (y1 - y0) * scale) / 2 + y0 * scale
    path = SVGPathPen(glyph_set, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    glyph.draw(TransformPen(path, (scale, 0, 0, -scale, dx, dy)))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect width="100" height="100" fill="#000"/>'
        f'<path fill="#fff" d="{path.getCommands()}"/>'
        "</svg>\n"
    )


def main() -> None:
    STATIC.mkdir(exist_ok=True)
    png(256).save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    png(180).save(STATIC / "apple-touch-icon.png", optimize=True)
    png(192).save(STATIC / "icon-192.png", optimize=True)
    png(512).save(STATIC / "icon-512.png", optimize=True)
    (STATIC / "favicon.svg").write_text(svg(), encoding="utf-8")
    for name in ["favicon.ico", "favicon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png"]:
        print(f"wrote static/{name}")


if __name__ == "__main__":
    main()
