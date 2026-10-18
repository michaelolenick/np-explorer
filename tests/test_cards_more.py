"""Share cards for boards that aren't from 990s (payroll, schools, student loan trusts) name their own source."""

from app import boards as B
from app import sharecard


class FakeDraw:
    def __init__(self):
        self.texts = []

    def line(self, *a, **k):
        pass

    def text(self, xy, t, **k):
        self.texts.append(t)

    def textlength(self, t, font=None):
        return len(t) * 10


def test_non_990_cards_render_with_their_source():
    meta = {"year_min": 2009, "year_max": 2027, "n_rows": 1}
    for slug in ("coaches", "schools", "uni-top-paid"):
        png = sharecard.render(B.BY_SLUG[slug], [], meta)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
    sla = B.BY_SLUG.get("student-loan-largest")
    if sla:
        assert sla.kind == "sla" and "10-D" in sla.source_label and sharecard.render(sla, [], meta)[:4] == b"\x89PNG"
    assert "990" not in B.BY_SLUG["coaches"].source_label.split(" and ")[0]
