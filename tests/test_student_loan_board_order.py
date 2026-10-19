"""Student loan boards: the owner's order, and every board shows pool balance and delinquency rate."""

from app import boards, schools_hub

ORDER = ["student-loan-largest", "student-loan-delinquency", "student-loan-deterioration", "student-loan-defaults",
         "student-loan-chargeoffs"]


def test_order_everywhere():
    assert [b.slug for b in boards.group_members("student-loans")] == ORDER
    assert [s.board for s in schools_hub.SECTIONS["student-loans"].suggestions if s.board != "schools"] == ORDER


def test_every_board_shows_pool_and_delinquency():
    for slug in ORDER:
        b = boards.BY_SLUG[slug]
        shown = {b.value.label} | {c.label for c in b.columns}
        assert any("Pool balance" in x for x in shown), slug
        assert any(x.startswith(("Delinquency rate", "Rate now")) for x in shown), slug
        for c in b.columns:                     # each shown column is selected by the board's SQL
            assert c.key in b.sql, (slug, c.key)
