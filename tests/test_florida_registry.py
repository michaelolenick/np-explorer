from loader import florida_registry as fl

REC = ("L16000216990FLIP THAT REO LLC".ljust(204) + "IFLAL".ljust(16) + "1558 THE 12TH FAIRWAY".ljust(84)
       + "WELLINGTON".ljust(28) + "FL" + "33414".ljust(10) + "US").ljust(472) + "11302016" + "46-1994649".ljust(14)


def test_fields_from_the_layout():
    s = REC.ljust(1440)
    f = fl.fields(s)
    assert f["cor_number"] == "L16000216990" and f["name"] == "FLIP THAT REO LLC" and f["status"] == "I"
    assert f["filing_type"] == "FLAL" and f["city"] == "WELLINGTON" and f["state"] == "FL" and f["zip"] == "33414"
    assert fl.mdy(f["file_date"]).isoformat() == "2016-11-30" and fl.ein(f["fei_number"]) == "461994649"
    assert fl.ein("NOT APPLICABLE") is None


def test_person_names_split_last_first_middle():
    raw = "THOUBBORON".ljust(20) + "GARY".ljust(14) + "S".ljust(8)
    show, norm, company = fl.person_name(raw, "P")
    assert show == "GARY S THOUBBORON" and not company and norm
    show, norm, company = fl.person_name("CT CORPORATION SYSTEM".ljust(42), "C")
    assert show == "CT CORPORATION SYSTEM" and company and norm is None
