import datetime as dt

from loader.formd_order import designation, place, worst_cost, request


def row(n, name, d):
    return {"root_accession": str(n), "issuer_name": name, "first_date": dt.date(2020, 1, d), "is_spv": False}


def test_designation_orders_and_parallel_vehicles():
    assert designation("Capital Factory IV, L.P.")[:3] == ("capital factory", "IV", 4.0)
    fam, label, order, variant = designation("Graceada Partners Fund IV-QP, LP")
    assert (fam, label, order, variant) == ("graceada", "IV-QP", 4.001, "QP")
    assert designation("KING STREET REAL ESTATE FUND (OFFSHORE PF), L.P.")[3] == "Offshore Pf"


def test_parallel_vehicle_sits_under_its_twin():
    res = {x["name"]: x for x in place([row(1, "Acme Fund IV, L.P.", 1), row(2, "Acme Fund IV Offshore, Ltd.", 2)])}
    off = res["Acme Fund IV Offshore, Ltd."]
    assert off["fund_kind"] == "series" and off["parent_root"] == "1" and off["confidence"] == "high"


def test_same_company_filing_again_and_operating_companies_need_no_model():
    same = place([row(1, "First Aid Beverages, Inc.", 1), row(2, "FIRST AID BEVERAGES INC", 5)])
    assert not any(x["confidence"] == "low" for x in same)
    assert all(x["fund_kind"] == "other" for x in same)          # dated in order, never sent to a model
    ops = {x["name"]: x for x in place([row(1, "Kleo, Inc.", 1), row(2, "Kleo Fund I, L.P.", 2)])}
    assert ops["Kleo, Inc."]["fund_kind"] == "other" and ops["Kleo, Inc."]["confidence"] == "high"


def test_unclear_fund_goes_to_the_model_with_names_only():
    res = place([row(1, "Acme Ventures Fund I, L.P.", 1), row(2, "Acme Ventures, L.P.", 2)])
    params, todo, funds = request(res)
    assert [x["name"] for x in todo] == ["Acme Ventures, L.P."]
    assert params["messages"][0]["content"] == "Funds:\nF1 Acme Ventures Fund I, L.P.\nPlace:\n1 Acme Ventures, L.P."
    assert params["thinking"] == {"type": "disabled"} and params["max_tokens"] < 120
    assert worst_cost(params, batch=True) < worst_cost(params, batch=False)
