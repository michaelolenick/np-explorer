"""Fundraising-event boards and the Schedule G Part II parser.

Board SQL runs over hand-made rows in a throwaway schema (same table definitions as the
live database), as in test_boards.py. Needs DATABASE_URL for the board tests.
"""

import os
import uuid

import pytest

from app import boards as B
from loader import parser

R = B.BOARD_MIN_REVENUE

SCHED_G_2015 = b"""<Return xmlns="http://www.irs.gov/efile" returnVersion="2015v2.1"><ReturnData>
<IRS990ScheduleG><FundraisingEventInformationGrp>
  <Event1Nm>Spring Gala</Event1Nm><GrossReceiptsEvent1Amt>900000</GrossReceiptsEvent1Amt>
  <CharitableContriEvent1Amt>400000</CharitableContriEvent1Amt><GrossRevenueEvent1Amt>500000</GrossRevenueEvent1Amt>
  <RentFacilityCostsEvent1Amt>100000</RentFacilityCostsEvent1Amt><FoodAndBeverageEvent1Amt>80000</FoodAndBeverageEvent1Amt>
  <EntertainmentEvent1Amt>40000</EntertainmentEvent1Amt><OtherDirectExpensesEvent1Amt>30000</OtherDirectExpensesEvent1Amt>
  <Event2Nm>Charity Golf Outing</Event2Nm><GrossReceiptsEvent2Amt>300000</GrossReceiptsEvent2Amt>
  <NonCashPrizesEvent2Amt>50000</NonCashPrizesEvent2Amt><OtherDirectExpensesEvent2Amt>100000</OtherDirectExpensesEvent2Amt>
  <OtherEventsTotalCnt>3</OtherEventsTotalCnt><GrossReceiptsOtherEventsAmt>800000</GrossReceiptsOtherEventsAmt>
  <RentFcltyCostsOtherEventsAmt>300000</RentFcltyCostsOtherEventsAmt>
  <GrossReceiptsTotalAmt>2000000</GrossReceiptsTotalAmt><FoodAndBeverageTotalEventsAmt>120000</FoodAndBeverageTotalEventsAmt>
  <DirectExpenseSummaryEventsAmt>700000</DirectExpenseSummaryEventsAmt><NetIncomeSummaryAmt>-300000</NetIncomeSummaryAmt>
</FundraisingEventInformationGrp></IRS990ScheduleG></ReturnData></Return>"""

SCHED_G_2011 = b"""<Return xmlns="http://www.irs.gov/efile" returnVersion="2011v1.2"><ReturnData>
<IRS990ScheduleG><EventsInformation>
  <NameOfEvent1>NIKE WOMENS MAR</NameOfEvent1><GrossReceiptsEvent1>10133172</GrossReceiptsEvent1>
  <GrossRevenueEvent1>2915069</GrossRevenueEvent1><OtherDirectExpensesEvent1>2915069</OtherDirectExpensesEvent1>
  <TotalNumberOfOtherEvents>1051</TotalNumberOfOtherEvents><GrossReceiptsOtherEvents>177025766</GrossReceiptsOtherEvents>
  <OtherDirectExpensesOtherEvents>31833077</OtherDirectExpensesOtherEvents>
  <GrossReceiptsTotal>194102549</GrossReceiptsTotal><DirectExpenseSummaryEvents>36867938</DirectExpenseSummaryEvents>
</EventsInformation></IRS990ScheduleG></ReturnData></Return>"""


def events(xml):
    return {e["slot"]: e for e in parser._fundraising_events(parser.parse_root(xml))}


def test_schedule_g_multiple_events_2013_tags():
    e = events(SCHED_G_2015)
    assert list(e) == ["event1", "event2", "other", "total"]
    gala, golf = e["event1"], e["event2"]
    assert (gala["name"], gala["keyword"], gala["direct_expenses"], gala["net_income"]) == (
        "Spring Gala", "gala", 250_000, 250_000)                       # 100k + 80k + 40k + 30k; 500k - 250k
    assert (golf["name"], golf["keyword"], golf["direct_expenses"]) == ("Charity Golf Outing", None, 150_000)
    assert golf["food_beverage"] is None and golf["gross_revenue"] is None   # not reported stays None, never 0
    assert (e["other"]["other_count"], e["other"]["name"], e["other"]["rent_facility"]) == (3, None, 300_000)
    assert (e["total"]["gross_receipts"], e["total"]["direct_expenses"], e["total"]["net_income"]) == (
        2_000_000, 700_000, -300_000)


def test_schedule_g_2009_tags_and_no_schedule():
    e = events(SCHED_G_2011)
    assert (e["event1"]["name"], e["event1"]["direct_expenses"], e["other"]["other_count"]) == (
        "NIKE WOMENS MAR", 2_915_069, 1051)
    assert e["total"]["direct_expenses"] == 36_867_938 and "event2" not in e
    assert parser._fundraising_events(parser.parse_root(
        b'<Return xmlns="http://www.irs.gov/efile"><ReturnData><IRS990/></ReturnData></Return>')) == []


@pytest.mark.parametrize("name, word", [("Black & White Ball", "ball"), ("Baseball Classic", None),
                                        ("Annual Benefit Dinner", "benefit"), ("Heart Walk", None),
                                        ("Winter Soiree", "soiree"), ("Wine AUCTION", "auction"), (None, None)])
def test_gala_flag_is_a_word_match(name, word):
    assert parser.gala_word(name) == word


# --- boards -------------------------------------------------------------------------------

AMENDED, DOUBLE, MULTI, TINY, SMALL_ORG = (f"20000000{i}" for i in range(1, 6))

FILINGS = [  # id, ein, form, year, revenue, superseded, amended, filed, 8a gross income, 8b direct expenses
    (1, AMENDED, "990", 2022, R, True, False, "2023-05-01", 1_000_000, 900_000),     # original, superseded
    (2, AMENDED, "990", 2022, R, False, True, "2023-09-01", 1_000_000, 1_200_000),   # the amended return
    (3, AMENDED, "990", 2021, R, False, False, "2022-05-01", 600_000, 500_000),
    (4, DOUBLE, "990", 2022, R, False, False, "2023-05-01", 3_000_000, 2_000_000),   # both marked current:
    (5, DOUBLE, "990", 2022, R, False, True, "2023-10-01", 1_000_000, 300_000),      #   the amended one wins
    (6, MULTI, "990", 2022, R, False, False, "2023-05-01", 400_000, 700_000),
    (7, TINY, "990EZ", 2022, R, False, False, "2023-05-01", 70_000, 60_000),
    (8, SMALL_ORG, "990", 2022, 1_000, False, False, "2023-05-01", 10_000, 5_000_000),  # out of scope
]


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"events_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    try:
        conn.execute(f"SET search_path = {schema}, public")
        for t in ("filings", "organizations", "expense_breakdown", "fundraising_events"):
            conn.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)")
        for ein in dict.fromkeys(f[1] for f in FILINGS):                # each organization once
            conn.execute("INSERT INTO organizations (ein, name, name_norm, state) VALUES (%s, %s, %s, 'NY')",
                         (ein, f"ORG {ein}", f"org {ein}"))
        for fid, ein, form, year, rev, sup, amd, filed, gross, direct in FILINGS:
            conn.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, state, total_revenue,
                            total_assets_eoy, superseded, amended, filed_date)
                            VALUES (%s,%s,%s,%s,%s,%s,'NY',%s,0,%s,%s,%s)""",
                         (fid, ein, 800000 + fid, form, year, f"ORG {ein}", rev, sup, amd, filed))
            conn.execute("""INSERT INTO expense_breakdown (filing_id, ein, tax_year, form_type, special_event_gross,
                            special_event_expenses) VALUES (%s,%s,%s,%s,%s,%s)""", (fid, ein, year, form, gross, direct))
        for slot, e in events(SCHED_G_2015).items():       # Multi's two named events, the rest, the totals
            cols = ["slot"] + [c for c in e if c != "slot"]
            conn.execute(f"INSERT INTO fundraising_events (filing_id, ein, tax_year, {', '.join(cols)}) "
                         f"VALUES (6, %s, 2022, {', '.join(['%s'] * len(cols))})", [MULTI] + [e[c] for c in cols])
        conn.execute("""INSERT INTO fundraising_events (filing_id, ein, tax_year, slot, gross_receipts, food_beverage)
                        VALUES (7, %s, 2022, 'total', 90000, 1000)""", (TINY,))
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def run(db, slug, per_org=False):
    cur = db.cursor(row_factory=__import__("psycopg").rows.dict_row)
    rows = cur.execute(f"SELECT * FROM ({B.BY_SLUG[slug].sql}) q ORDER BY pos").fetchall()
    return sorted((r for r in rows if r["org_pos"]), key=lambda r: r["org_pos"]) if per_org else rows


def test_amended_returns_counted_once(db):
    rows = run(db, "event-spending")
    got = {(r["ein"], r["tax_year"]): (r["value"], r["filing_id"]) for r in rows}
    assert len(rows) == len(got)                                       # no organization-year twice
    assert got[(AMENDED, 2022)] == (1_200_000, 2)                      # the amended return, not the superseded original
    assert got[(DOUBLE, 2022)] == (300_000, 5)                         # latest amended return when both are current
    assert SMALL_ORG not in {r["ein"] for r in rows}                   # out of scope


def test_default_view_one_row_per_org(db):
    every = run(db, "event-spending")
    per_org = run(db, "event-spending", per_org=True)
    assert [(r["ein"], r["tax_year"]) for r in every if r["ein"] == AMENDED] == [(AMENDED, 2022), (AMENDED, 2021)]
    assert len({r["ein"] for r in per_org}) == len(per_org) == 4       # Amended, Double, Multi, Tiny
    assert [r["ein"] for r in per_org][:2] == [AMENDED, MULTI]          # 1.2M, then 700k
    assert B.per_org_view(B.BY_SLUG["event-spending"], {}) and not B.per_org_view(B.BY_SLUG["event-spending"], {"all": 1})


def test_cost_per_dollar_floor(db):
    rows = run(db, "event-cost-per-dollar")
    assert [(r["ein"], float(r["value"])) for r in rows] == [(MULTI, 0.35)]   # 700k / 2M; Tiny's 90k is under the floor


def test_biggest_events_multiple_events(db):
    rows = run(db, "biggest-events")
    assert [(r["event_name"], r["value"], r["keyword"]) for r in rows] == [
        ("Spring Gala", 250_000, "gala"), ("Charity Golf Outing", 150_000, None)]   # "other events" left out
    assert [r["event_name"] for r in run(db, "biggest-events", per_org=True)] == ["Spring Gala"]
    assert {r["event_names"] for r in run(db, "event-spending") if r["ein"] == MULTI} == {
        "Spring Gala; Charity Golf Outing"}


def test_food_drink_and_net_with_unreported_lines(db):
    food = {r["ein"]: r for r in run(db, "event-food-drink")}
    assert food[MULTI]["value"] == 120_000 and food[MULTI]["entertainment"] is None
    assert B.fmt(food[MULTI]["entertainment"], "money?") == "Not reported"
    assert B.fmt(0, "money?") == "$0" and B.fmt(None, "money") == "-"
    net = run(db, "event-net")
    assert [(r["ein"], r["value"]) for r in net][0] == (MULTI, -300_000)    # lowest first
    assert all(r["value"] < 0 for r in net) and AMENDED not in {r["ein"] for r in net if r["tax_year"] == 2021}
