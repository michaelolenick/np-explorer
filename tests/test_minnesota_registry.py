from loader import minnesota_registry as mn

# Records as they appear in the state's file (1096_20260930_M_COMPLETE_Job23_RunOn20261001.CSV).
MASTER = ["4534fd21-2c3a-e911-9170-00155d01b315", "01", "46", "1071274100020", "24 Hour Heating Air and Electric LLC",
          "Active", "2/26/2019", "", "12/31/2027", "North Dakota", "322C", "0", "0", "0",
          "24 Hour Heating Air and Electric LLC", "", "", "", "", "", "", "10/01/2026"]
MARK = ["c5c3fa19-db8c-eb11-9184-00155d01c40e", "01", "57", "1225473000024", "Buttered by K-Luxe", "Active", "3/24/2021",
        "", "03/24/2031", "Minnesota", "333", "0", "0", "0", "", "", "Trademark", "07/10/2020", "03",
        'Navy blue background,"by K-LUXE" in gold letters', "", "10/01/2026"]


def test_master_record_fields_from_the_layout():
    e = mn.master(MASTER)
    assert e["entity_id"] == "4534fd21-2c3a-e911-9170-00155d01b315" and e["name"] == "24 Hour Heating Air and Electric LLC"
    assert e["entity_type"] == "Limited liability company (foreign)" and e["status"] == "Active"
    assert e["formed"].isoformat() == "2019-02-26" and e["jurisdiction"] == "ND"
    assert e["extra"]["original_filing_number"] == "1071274100020" and e["extra"]["next_renewal_due"] == "2027-12-31"
    assert e["extra"]["governing_statute"] == "322C" and "llc_nonprofit" not in e["extra"]
    assert e["export_date"].isoformat() == "2026-10-01"


def test_trademark_fields_go_to_extra():
    x = mn.master(MARK)["extra"]
    assert x["mark_type"] == "Trademark" and x["mark_first_use"] == "2020-07-10" and x["mark_class"] == "03"
    assert x["mark_logo"].startswith("Navy blue background")


def test_party_rows_and_cleanup():
    p = mn.party(["81b466b8-223a-e911-9170-00155d01b315", "03", "59", "1071265600028", "1071265600028", "1", "14",
                  "Carlton A Goss", "8105 Cedar St", "", "Rockford,", "MnMN", "55373", "1234", "USA"])
    assert p[2] == "1" and p[3] == "14" and p[4] == "Carlton A Goss" and p[5] == "carlton a goss" and not p[6]
    assert p[8] == "Rockford" and p[9] == "MN" and p[10] == "55373-1234"
    agent = mn.party(["x", "03", "44", "1", "1", "4", "", "Northwest Registered Agent LLC", "", "", "", "", "", "", ""])
    assert agent[6] and agent[5] is None


def test_codes_and_regions():
    assert mn.ROLES["4"] == "Registered agent" and mn.ROLES["14"] == "Chief executive officer"
    assert mn.entity_type("66") == "Business corporation (domestic)" and mn.entity_type("999") == "Business type 999"
    assert mn.region("MNMN") == "MN" and mn.region("Wisconsin") == "WI" and mn.region("") is None
    assert mn.is_org("C T Corporation System") and mn.is_org("Smith Family Trust")
    assert not mn.is_org("Stephanie Jo Menefee")


def test_newest_dated_folder(tmp_path):
    for d, f in (("2026-09-01", "a.zip"), ("2026-10-28", "b.zip"), ("2026-10-28", "b.CSV"), ("notes", "c.zip")):
        (tmp_path / d).mkdir(exist_ok=True)
        (tmp_path / d / f).write_text("x")
    assert mn.newest(tmp_path).name == "b.CSV"


def test_a_record_with_no_name_is_kept():
    f = list(MARK)
    f[4] = ""
    e = mn.master(f)
    assert e["unnamed"] and e["name"].startswith("Trademark with no name: Navy blue") and e["extra"]["no_name"]
