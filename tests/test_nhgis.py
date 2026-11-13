"""loader/nhgis.py: the codebook and column handling that the NHGIS load relies on (no network, no database)."""
from loader import nhgis

CODEBOOK = """
Data Dictionary
--------------------------------------------------------------------------------

Context Fields
        GISJOIN:     GIS Join Match Code
        YEAR:        Data File Year
        STUSAB:      State/US Abbreviation
        STATEA:      State Code
        NAME_E:      Area Name

Data Type (E):
    Estimates

Table 1:     Sex by Age
Universe:    Total population
Source code: B01001
NHGIS code:  ASNQ
        ASNQE001:    Total
        ASNQE002:    Male

Table 2:     Median Age by Sex
Universe:    Total population
Source code: B01002
NHGIS code:  ASNR
        ASNRE001:    Median age --!! Total

Data Type (M):
    Margins of error

        NAME_M:      Area Name

    Table 1:     Sex by Age
    Universe:    Total population
    Source code: B01001
    NHGIS code:  ASNQ
        ASNQM001:    Total
        ASNQM002:    Male
"""


def test_codebook_tables_and_variables():
    tables, variables = nhgis.parse_codebook(CODEBOOK)
    assert tables["ASNQ"] == {"source_code": "B01001", "description": "Sex by Age", "universe": "Total population"}
    assert tables["ASNR"]["source_code"] == "B01002"
    assert variables["ASNQE002"] == {"nhgis_code": "ASNQ", "description": "Male"}
    assert variables["ASNQM001"]["nhgis_code"] == "ASNQ" and variables["ASNRE001"]["description"].startswith("Median age")
    assert variables["GISJOIN"]["nhgis_code"] is None and variables["NAME_M"]["nhgis_code"] is None


def test_columns_split_by_table_longest_code_first():
    header = ["GISJOIN", "YEAR", "STUSAB", "STATEA", "NAME_E", "ASNQE001", "ASNQE002", "ASNRE001", "NAME_M",
              "ASNQM001", "ASNQM002", "U7H001"]
    context, groups = nhgis.group_columns(header, ["ASNQ", "ASNR", "U7H"])
    assert context == ["GISJOIN", "YEAR", "STUSAB", "STATEA", "NAME_E", "NAME_M"]
    assert groups == {"ASNQ": ["ASNQE001", "ASNQE002", "ASNQM001", "ASNQM002"], "ASNRE001"[:4]: ["ASNRE001"],
                      "U7H": ["U7H001"]}
    assert nhgis.infer_codes(header) == ["ASNQ", "ASNR", "U7H"]
    assert nhgis._data_type("ASNQM001", "ASNQ") == "M" and nhgis._data_type("U7H001", "U7H") is None


def test_table_names_and_extract_definition():
    assert nhgis.pg_table("2020_2024_ACS5a", "B01001") == "d_2020_2024_acs5a_b01001"
    meta = {"name": "2020_DHCa", "geogLevels": [{"name": "state"}, {"name": "county"}, {"name": "blck_grp"}],
            "dataTables": [{"name": "P1"}, {"name": "P2"}]}
    d = nhgis.extract_definition(meta, nhgis.GEOG_LEVELS)
    assert d["datasets"] == {"2020_DHCa": {"dataTables": ["P1", "P2"], "geogLevels": ["state", "county"]}}
    assert d["dataFormat"] == "csv_no_header" and d["breakdownAndDataTypeLayout"] == "single_file"
