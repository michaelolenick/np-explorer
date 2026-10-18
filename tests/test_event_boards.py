"""Fundraising-event boards and the Schedule G Part II parser.

Board SQL runs over hand-made rows in a throwaway schema (same table definitions as the
live database), as in test_boards.py. Needs DATABASE_URL for the board tests.
"""

import os
import uuid

import pytest

from app import boards as B
from app import event_class
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

AMENDED, DOUBLE, MULTI, TINY, SMALL_ORG, DERIVED = (f"20000000{i}" for i in range(1, 7))

FILINGS = [  # id, ein, form, year, revenue, superseded, amended, filed, 8a gross income, 8b direct expenses
    (1, AMENDED, "990", 2022, R, True, False, "2023-05-01", 1_000_000, 900_000),     # original, superseded
    (2, AMENDED, "990", 2022, R, False, True, "2023-09-01", 1_000_000, 1_200_000),   # the amended return
    (3, AMENDED, "990", 2021, R, False, False, "2022-05-01", 600_000, 500_000),
    (4, DOUBLE, "990", 2022, R, False, False, "2023-05-01", 3_000_000, 2_000_000),   # both marked current:
    (5, DOUBLE, "990", 2022, R, False, True, "2023-10-01", 1_000_000, 300_000),      #   the amended one wins
    (6, MULTI, "990", 2022, R, False, False, "2023-05-01", 400_000, 700_000),
    (7, TINY, "990EZ", 2022, R, False, False, "2023-05-01", 70_000, 60_000),
    (8, SMALL_ORG, "990", 2022, 1_000, False, False, "2023-05-01", 10_000, 5_000_000),  # out of scope
    (9, DERIVED, "990", 2022, R, False, False, "2023-05-01", 500_000, None),           # 8b blank, 8c reported
]
NET_8C = {9: 100_000}   # line 8c as reported; every other return leaves it blank


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
        conn.execute("""CREATE TABLE event_classes (filing_id bigint, slot text, category text, related boolean,
                        reason text, gala boolean)""")
        for ein in dict.fromkeys(f[1] for f in FILINGS):                # each organization once
            conn.execute("INSERT INTO organizations (ein, name, name_norm, state) VALUES (%s, %s, %s, 'NY')",
                         (ein, f"ORG {ein}", f"org {ein}"))
        for fid, ein, form, year, rev, sup, amd, filed, gross, direct in FILINGS:
            conn.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, state, total_revenue,
                            total_assets_eoy, superseded, amended, filed_date)
                            VALUES (%s,%s,%s,%s,%s,%s,'NY',%s,0,%s,%s,%s)""",
                         (fid, ein, 800000 + fid, form, year, f"ORG {ein}", rev, sup, amd, filed))
            conn.execute("""INSERT INTO expense_breakdown (filing_id, ein, tax_year, form_type, special_event_gross,
                            special_event_expenses, special_event_net) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                         (fid, ein, year, form, gross, direct, NET_8C.get(fid)))
        for slot, e in events(SCHED_G_2015).items():       # Multi's two named events, the rest, the totals
            cols = ["slot"] + [c for c in e if c != "slot"]
            conn.execute(f"INSERT INTO fundraising_events (filing_id, ein, tax_year, {', '.join(cols)}) "
                         f"VALUES (6, %s, 2022, {', '.join(['%s'] * len(cols))})", [MULTI] + [e[c] for c in cols])
        conn.execute("""INSERT INTO fundraising_events (filing_id, ein, tax_year, slot, gross_receipts, food_beverage)
                        VALUES (7, %s, 2022, 'total', 90000, 1000)""", (TINY,))
        for slot, name in (("event1", "Spring Gala"), ("event2", "Charity Golf Outing")):
            cat, related, reason = event_class.classify(name, f"ORG {MULTI}", "E30")
            conn.execute("INSERT INTO event_classes VALUES (6, %s, %s, %s, %s, %s)",
                         (slot, cat, related, reason, event_class.is_gala(name)))
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def run(db, slug, per_org=False):
    cur = db.cursor(row_factory=__import__("psycopg").rows.dict_row)
    rows = cur.execute(f"SELECT * FROM ({B.BY_SLUG[slug].sql}) q ORDER BY pos").fetchall()
    return sorted((r for r in rows if r["org_pos"]), key=lambda r: r["org_pos"]) if per_org else rows


def test_amended_returns_counted_once(db):
    rows = run(db, "beyond-spending")                                  # no itemized events: still fundraising events
    got = {(r["ein"], r["tax_year"]): (r["value"], r["filing_id"]) for r in rows}
    assert len(rows) == len(got)                                       # no organization-year twice
    assert got[(AMENDED, 2022)] == (1_200_000, 2)                      # the amended return, not the superseded original
    assert got[(DOUBLE, 2022)] == (300_000, 5)                         # latest amended return when both are current
    assert SMALL_ORG not in {r["ein"] for r in rows}                   # out of scope


def test_galas_board_is_a_subset_of_beyond(db):
    galas = {(r["ein"], r["tax_year"]) for r in run(db, "event-spending")}
    beyond = {(r["ein"], r["tax_year"]) for r in run(db, "beyond-spending")}
    assert galas == {(MULTI, 2022)} and galas < beyond                 # only Multi has a gala; B holds all of A


def test_default_view_one_row_per_org(db):
    every = run(db, "beyond-spending")
    per_org = run(db, "beyond-spending", per_org=True)
    assert [(r["ein"], r["tax_year"]) for r in every if r["ein"] == AMENDED] == [(AMENDED, 2022), (AMENDED, 2021)]
    assert len({r["ein"] for r in per_org}) == len(per_org) == 5       # Amended, Double, Multi, Tiny, Derived
    assert [r["ein"] for r in per_org][:3] == [AMENDED, MULTI, DERIVED]   # 1.2M, 700k, 400k
    assert B.per_org_view(B.BY_SLUG["beyond-spending"], {}) and not B.per_org_view(B.BY_SLUG["beyond-spending"], {"all": 1})


def test_cost_per_dollar_floor(db):
    rows = run(db, "beyond-cost-per-dollar")
    assert [(r["ein"], float(r["value"])) for r in rows] == [(MULTI, 0.35)]   # 700k / 2M; Tiny's 90k is under the floor


def test_biggest_events_by_group(db):
    assert [(r["event_name"], r["value"], r["category"]) for r in run(db, "biggest-events")] == [
        ("Spring Gala", 250_000, "gala/party")]                         # galas only
    beyond = run(db, "beyond-biggest")
    assert [(r["event_name"], r["mission"]) for r in beyond] == [("Spring Gala", "not the program"),
                                                                  ("Charity Golf Outing", "not the program")]
    assert beyond[1]["reason"] == "NTEE E30, not a sports organization: fundraising outing"
    assert {r["event_names"] for r in run(db, "event-spending")} == {"Spring Gala; Charity Golf Outing"}


def test_derived_expenses_and_not_reported_net(db):
    rows = {r["ein"]: r for r in run(db, "beyond-spending") if r["tax_year"] == 2022}
    assert (rows[DERIVED]["value"], rows[DERIVED]["direct_source"], rows[DERIVED]["net"]) == (400_000, "derived", 100_000)
    assert rows[AMENDED]["direct_source"] == "reported" and rows[AMENDED]["net"] is None   # a blank 8c stays blank
    assert B.fmt(rows[AMENDED]["net"], "money?") == "Not reported"
    net = run(db, "beyond-net")
    assert [(r["ein"], r["value"]) for r in net] == [(MULTI, -300_000)]   # Schedule G line 11 as reported
    assert not {AMENDED, DOUBLE, TINY} & {r["ein"] for r in net}          # blank nets are not ranked as $0


def test_food_drink_with_unreported_lines(db):
    food = {r["ein"]: r for r in run(db, "beyond-food-drink")}
    assert food[MULTI]["value"] == 120_000 and food[MULTI]["entertainment"] is None
    assert B.fmt(food[MULTI]["entertainment"], "money?") == "Not reported"
    assert B.fmt(0, "money?") == "$0" and B.fmt(None, "money") == "-"
