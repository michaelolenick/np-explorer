"""USDA FSIS recalls (loader/fsis_recalls.py): what is read from FSIS's text, the row shape, and the one-request rule."""

from loader import fsis_recalls as F
from loader.recalls import COLS

RECALL = {"field_title": "Fontanini Foods LLC Recalls Pork Sausage Products Due to Possible Foreign Matter Contamination",
          "field_recall_number": " 030-2026", "field_recall_url": "http://www.fsis.usda.gov/recalls-alerts/fontanini",
          "field_establishment": ["Fontanini Foods, LLC"], "field_states": ["Illinois", "Indiana"],
          "field_recall_classification": "Class I", "field_risk_level": "High - Class I", "field_recall_type": "Active Recall",
          "field_recall_reason": ["Product Contamination"], "field_processing": ["Raw - Non Intact"],
          "field_product_items": ["5-lb. boxes of &quot;FONTANINI SAUSAGE&quot;", "10-lb. boxes"],
          "field_recall_date": "2026-09-25", "field_last_modified_date": "2026-09-30", "langcode": "English",
          "field_summary": "<p><strong>WASHINGTON, Sept. 25, 2026</strong> &ndash; Fontanini Foods LLC, a McCook, Ill., "
                           "establishment, is recalling approximately 2,320 pounds of raw, frozen pork sausage.</p>"}
ALERT = {"field_title": "FSIS Issues Public Health Alert for Ineligible Pork Products Imported From Ecuador",
         "field_recall_number": "pha-10012025", "field_recall_url": "http://www.fsis.usda.gov/recalls-alerts/pha-pork",
         "field_establishment": [], "field_states": [], "field_recall_classification": "Public Health Alert",
         "field_recall_type": "Public Health Alert", "field_recall_reason": ["Import Violation"], "field_processing": [],
         "field_product_items": ["Pork products"], "field_recall_date": "2025-10-01", "field_last_modified_date": "2025-10-01",
         "langcode": "English", "field_summary": "<p>WASHINGTON, Oct. 1, 2025 - FSIS is issuing a public health alert.</p>"}


def test_place_firm_quantity_and_reason_from_the_text():
    assert F.place(RECALL["field_summary"]) == ("McCook", "IL", "United States")
    assert F.place("Acme, a Long Island City, N.Y., establishment") == ("Long Island City", "NY", "United States")
    assert F.place("Acme, a Toronto, Ontario establishment") == ("Toronto", None, "Canada")
    assert F.place("nothing here") == (None, None, "United States")
    assert F.firm_name(RECALL) == "Fontanini Foods, LLC"
    assert F.firm_name({**RECALL, "field_establishment": []}) == "Fontanini Foods LLC"          # from the title
    assert F.firm_name({**RECALL, "field_establishment": [], "field_title": "FSIS Issues Public Health Alert"}) \
        == "Fontanini Foods LLC"                                                                  # from the summary
    assert F.firm_name(ALERT) is None
    assert F.quantity(RECALL["field_summary"]) == "2,320 pounds"
    assert F.quantity("is recalling 500 lbs. of beef") == "500 pounds"
    assert F.reason(RECALL) == "Product Contamination: Possible Foreign Matter Contamination"
    assert F.reason(ALERT) == "Import Violation: Ineligible Pork Products Imported From Ecuador"


def test_rows_follow_the_fda_columns():
    r = dict(zip(COLS, F.row(RECALL)))
    assert (r["source"], r["recall_number"], r["event_id"], r["status"], r["classification"]) == \
        ("fsis", "030-2026", "030-2026", "Ongoing", "Class I")
    assert (r["recalling_firm"], r["city"], r["state"], r["country"], r["product_type"]) == \
        ("Fontanini Foods, LLC", "McCook", "IL", "United States", "Meat and poultry")
    assert r["firm_id"] == F.firm_id("Fontanini Foods LLC", "IL")                       # same firm as an FDA report would be
    assert r["product_description"] == '5-lb. boxes of "FONTANINI SAUSAGE"; 10-lb. boxes'
    assert r["distribution_pattern"] == "Illinois, Indiana" and r["product_quantity"] == "2,320 pounds"
    assert str(r["recall_initiation_date"]) == "2026-09-25" and str(r["report_date"]) == "2026-09-30"
    assert r["source_url"] == "https://www.fsis.usda.gov/recalls-alerts/fontanini" and r["data_url"] is None
    a = dict(zip(COLS, F.row(ALERT)))
    assert (a["status"], a["classification"], a["recalling_firm"], a["firm_id"]) == \
        ("Public health alert", None, F.PHA_FIRM, F.PHA_FIRM_ID)
    assert F.row({**RECALL, "langcode": "Spanish"}) is None                              # Spanish copies are skipped
    assert F.row({**RECALL, "field_recall_number": " "}) is None


def test_one_request_a_night_as_agreed_with_fsis():
    import inspect
    src = inspect.getsource(F.fetch)
    assert F.UA == "furp.org research michael@furp.org" and F.API == "https://www.fsis.usda.gov/fsis/api/recall/v/1"
    assert "follow_redirects=False" in src and "retry" not in src.lower()
    assert "fsis-pha" in open("app/recall_boards.py").read()                             # unnamed alerts stay off the boards
