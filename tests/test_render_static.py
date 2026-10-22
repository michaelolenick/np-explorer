"""The pre-rendered fallback pages (scripts/render_static.py) render with the current templates: every global a
template uses must be set there too (2026-10-22: a missing one stopped a deploy halfway and caused 500s)."""

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_static_renders_every_page(tmp_path):
    mod = runpy.run_path(str(ROOT / "scripts" / "render_static.py"), run_name="render_static_test")
    g = mod["main"].__globals__                         # runpy returns a copy: patch the function's own globals
    g["ROOT"], g["PUBLIC"] = tmp_path, tmp_path / "public"
    mod["main"]()
    for name in mod["PAGES"]:
        assert (tmp_path / "public" / name).stat().st_size > 0, name
    assert 'class="ideas-signup"' in (tmp_path / "public" / "index.html").read_text()
