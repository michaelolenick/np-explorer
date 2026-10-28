import datetime as dt

from loader import buybacks as lb

TABLE = b"""<html><body><table>
<tr><td>Period</td><td>Total<br>Number of Shares Purchased</td><td>Average Price Paid per Share (1)</td>
<td>Total Number of Shares Purchased as Part of Publicly Announced Plans or Programs</td>
<td>Approximate Dollar Value of Shares that May Yet Be Purchased (in millions)</td></tr>
<tr><td>October 1 - October 31, 2024</td><td>1,000</td><td>$</td><td>50.25</td><td>1,000</td><td>$</td><td>1,234.5</td></tr>
<tr><td>November 1 - 30, 2024</td><td>&#8212;</td><td>$</td><td>&#8212;</td><td>&#8212;</td><td>$</td><td>1,234.5</td></tr>
<tr><td>Total</td><td>1,000</td><td>$</td><td>50.25</td><td>1,000</td><td></td><td></td></tr>
</table></body></html>"""


def test_parse_repurchase_table():
    rows = lb.parse_tables(TABLE, dt.date(2024, 12, 31))
    assert len(rows) == 3
    oct_, nov, total = rows
    assert (oct_["start"], oct_["end"]) == (dt.date(2024, 10, 1), dt.date(2024, 10, 31))
    assert oct_["shares"] == 1000 and oct_["avg_price"] == 50.25 and oct_["plan_shares"] == 1000
    assert oct_["remaining_value"] == 1234.5e6                       # "(in millions)" in that column's header
    assert nov["start"] == dt.date(2024, 11, 1) and nov["shares"] == 0
    assert total["total"]


def test_footnote_marks_are_not_numbers():
    assert lb._isnum("1,234") and lb._isnum("$ 12.50") and not lb._isnum("Average Price Paid per Share 1")
    assert lb._num("5,904 (2)") == 5904


def test_quarters_from_year_to_date():
    d = dt.date
    ytd = {(d(2024, 3, 31), 1): 10.0, (d(2024, 6, 30), 2): 25.0, (d(2024, 9, 30), 3): 45.0, (d(2024, 12, 31), 4): 70.0}
    q = lb._quarterize(ytd)
    assert q[d(2024, 6, 30)] == (15.0, True) and q[d(2024, 12, 31)] == (25.0, True) and q[d(2024, 3, 31)] == (10.0, False)


def test_chart_pairs_bars():
    from app import buybacks
    qs = [{"start": dt.date(2024, 1, 1), "label": "2024 Q1", "buybacks": 100, "sold": 50},
          {"start": dt.date(2024, 4, 1), "label": "2024 Q2", "buybacks": 0, "sold": None}]
    c = buybacks.chart(qs, [{"filed": dt.date(2024, 2, 15)}])
    assert len(c["bars"]) == 4 and len(c["lines"]) == 1 and c["top"] == 100


def test_lobbying_link_sum_uses_the_client_index():
    # 2026-10-28: client_id::text = key scanned all of lda_filings once per link (Boeing: 24 s, past the page's
    # 6 s timeout, so the buybacks section silently disappeared). The id is compared as a number.
    import inspect
    from app import buybacks
    src = inspect.getsource(buybacks.company)
    assert "WHERE f.client_id::text" not in src and "f.client_id = l.key::int" in src
