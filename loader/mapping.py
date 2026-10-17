"""Mapping table from logical fields to IRS e-file XML element paths.

The IRS renamed nearly every element when the 2013v3.0 schemas shipped
(e.g. ``TotalRevenueCurrentYear`` became ``CYTotalRevenueAmt``). Rather than
hardcode paths in the parser, every field lists candidate paths per schema era;
the parser tries them in order and takes the first that is present.

Paths are relative to the ``Return`` root with the default IRS namespace
stripped (see parser.strip_namespace). Every candidate path here was checked
against real filings from the IRS and GivingTuesday mirrors.

Eras:
  v2009  returnVersion 2009v1.0 .. 2012v4.x  (the original AWS-era schemas)
  v2013  returnVersion 2013v3.0 and later
"""

from __future__ import annotations

import re

# Every returnVersion seen in the IRS releases. Anything else is logged as
# unknown and parsed with both eras' candidates.
KNOWN_VERSIONS = {
    "2009v1.0", "2009v1.1", "2009v1.2", "2009v1.3", "2009v1.4", "2009v1.7",
    "2010v3.2", "2010v3.3", "2010v3.4", "2010v3.6", "2010v3.7",
    "2011v1.2", "2011v1.3", "2011v1.4", "2011v1.5",
    "2012v2.0", "2012v2.1", "2012v2.2", "2012v2.3", "2012v3.0",
    "2013v3.0", "2013v3.1", "2013v4.0",
    "2014v5.0", "2014v6.0",
    "2015v2.0", "2015v2.1", "2015v3.0",
    "2016v3.0", "2016v3.1",
    "2017v2.0", "2017v2.1", "2017v2.2", "2017v2.3",
    "2018v3.0", "2018v3.1", "2018v3.2", "2018v3.3",
    "2019v5.0", "2019v5.1", "2019v5.2",
    "2020v1.0", "2020v1.1", "2020v1.2", "2020v1.3", "2020v2.0", "2020v3.0", "2020v4.0", "2020v4.1", "2020v4.2",
    "2021v4.0", "2021v4.1", "2021v4.2", "2021v4.3",
    "2022v4.0", "2022v4.1", "2022v5.0",
    "2023v1.0", "2023v2.0", "2023v3.0", "2023v4.0", "2023v5.0", "2023v6.0",
    "2024v1.0", "2024v2.0", "2024v3.0", "2024v4.0", "2024v4.1", "2024v4.2", "2023v5.1", "2024v5.0", "2024v5.1", "2024v5.2",
    "2025v1.0", "2025v2.0", "2025v3.0", "2025v4.0",
}

FORMS = ("990", "990EZ", "990PF")

_VERSION_RE = re.compile(r"^(\d{4})v(\d+)\.(\d+)$")


def era_for(version: str | None) -> tuple[str, bool]:
    """Return (era, known) for a returnVersion string."""
    known = version in KNOWN_VERSIONS
    m = _VERSION_RE.match(version or "")
    if not m:
        return "unknown", False
    year, major = int(m.group(1)), int(m.group(2))
    if year < 2013 or (year == 2013 and major < 3):
        return "v2009", known
    return "v2013", known


# --- Scalar fields -----------------------------------------------------------
# field -> era -> candidate paths

HEADER = {
    "return_type": {
        "v2009": ["ReturnHeader/ReturnType"],
        "v2013": ["ReturnHeader/ReturnTypeCd"],
    },
    "ein": {
        "v2009": ["ReturnHeader/Filer/EIN"],
        "v2013": ["ReturnHeader/Filer/EIN"],
    },
    "name": {
        "v2009": ["ReturnHeader/Filer/Name/BusinessNameLine1"],
        "v2013": ["ReturnHeader/Filer/BusinessName/BusinessNameLine1Txt",
                  "ReturnHeader/Filer/BusinessName/BusinessNameLine1"],
    },
    "name2": {
        "v2009": ["ReturnHeader/Filer/Name/BusinessNameLine2"],
        "v2013": ["ReturnHeader/Filer/BusinessName/BusinessNameLine2Txt",
                  "ReturnHeader/Filer/BusinessName/BusinessNameLine2"],
    },
    "street": {
        "v2009": ["ReturnHeader/Filer/USAddress/AddressLine1",
                  "ReturnHeader/Filer/ForeignAddress/AddressLine1"],
        "v2013": ["ReturnHeader/Filer/USAddress/AddressLine1Txt",
                  "ReturnHeader/Filer/USAddress/AddressLine1",
                  "ReturnHeader/Filer/ForeignAddress/AddressLine1Txt"],
    },
    "city": {
        "v2009": ["ReturnHeader/Filer/USAddress/City",
                  "ReturnHeader/Filer/ForeignAddress/City"],
        "v2013": ["ReturnHeader/Filer/USAddress/CityNm",
                  "ReturnHeader/Filer/USAddress/City",
                  "ReturnHeader/Filer/ForeignAddress/CityNm"],
    },
    "state": {
        "v2009": ["ReturnHeader/Filer/USAddress/State",
                  "ReturnHeader/Filer/ForeignAddress/ProvinceOrState"],
        "v2013": ["ReturnHeader/Filer/USAddress/StateAbbreviationCd",
                  "ReturnHeader/Filer/USAddress/State",
                  "ReturnHeader/Filer/ForeignAddress/ProvinceOrStateNm"],
    },
    "zip": {
        "v2009": ["ReturnHeader/Filer/USAddress/ZIPCode",
                  "ReturnHeader/Filer/ForeignAddress/PostalCode"],
        "v2013": ["ReturnHeader/Filer/USAddress/ZIPCd",
                  "ReturnHeader/Filer/USAddress/ZIPCode",
                  "ReturnHeader/Filer/ForeignAddress/ForeignPostalCd"],
    },
    "tax_year": {
        "v2009": ["ReturnHeader/TaxYear"],
        "v2013": ["ReturnHeader/TaxYr"],
    },
    "tax_period_begin": {
        "v2009": ["ReturnHeader/TaxPeriodBeginDate"],
        "v2013": ["ReturnHeader/TaxPeriodBeginDt"],
    },
    "tax_period_end": {
        "v2009": ["ReturnHeader/TaxPeriodEndDate"],
        "v2013": ["ReturnHeader/TaxPeriodEndDt"],
    },
    "filed_ts": {
        "v2009": ["ReturnHeader/Timestamp"],
        "v2013": ["ReturnHeader/ReturnTs"],
    },
    "amended": {
        "v2009": ["ReturnData/IRS990/AmendedReturn", "ReturnData/IRS990EZ/AmendedReturn",
                  "ReturnData/IRS990PF/AmendedReturn"],
        "v2013": ["ReturnData/IRS990/AmendedReturnInd", "ReturnData/IRS990EZ/AmendedReturnInd",
                  "ReturnData/IRS990PF/AmendedReturnInd"],
    },
}

# Per-form financial and descriptive fields.
FORM_FIELDS = {
    "990": {
        "dba": {
            "v2009": ["ReturnData/IRS990/DoingBusinessAsName/BusinessNameLine1"],
            "v2013": ["ReturnData/IRS990/DoingBusinessAsName/BusinessNameLine1Txt"],
        },
        "website": {
            "v2009": ["ReturnData/IRS990/WebSite"],
            "v2013": ["ReturnData/IRS990/WebsiteAddressTxt"],
        },
        "mission": {
            "v2009": ["ReturnData/IRS990/MissionDescription",
                      "ReturnData/IRS990/ActivityOrMissionDescription"],
            "v2013": ["ReturnData/IRS990/MissionDesc", "ReturnData/IRS990/ActivityOrMissionDesc"],
        },
        "total_revenue": {
            "v2009": ["ReturnData/IRS990/TotalRevenueCurrentYear",
                      "ReturnData/IRS990/TotalRevenue/TotalRevenueColumn"],
            "v2013": ["ReturnData/IRS990/CYTotalRevenueAmt",
                      "ReturnData/IRS990/TotalRevenueGrp/TotalRevenueColumnAmt"],
        },
        "total_expenses": {
            "v2009": ["ReturnData/IRS990/TotalExpensesCurrentYear"],
            "v2013": ["ReturnData/IRS990/CYTotalExpensesAmt",
                      "ReturnData/IRS990/TotalFunctionalExpensesGrp/TotalAmt"],
        },
        "total_assets_eoy": {
            "v2009": ["ReturnData/IRS990/TotalAssetsEOY", "ReturnData/IRS990/TotalAssets/EOY"],
            "v2013": ["ReturnData/IRS990/TotalAssetsEOYAmt", "ReturnData/IRS990/TotalAssetsGrp/EOYAmt"],
        },
        "total_liabilities_eoy": {
            "v2009": ["ReturnData/IRS990/TotalLiabilitiesEOY", "ReturnData/IRS990/TotalLiabilities/EOY"],
            "v2013": ["ReturnData/IRS990/TotalLiabilitiesEOYAmt",
                      "ReturnData/IRS990/TotalLiabilitiesGrp/EOYAmt"],
        },
        "net_assets_eoy": {
            "v2009": ["ReturnData/IRS990/NetAssetsOrFundBalancesEOY"],
            "v2013": ["ReturnData/IRS990/NetAssetsOrFundBalancesEOYAmt",
                      "ReturnData/IRS990/TotalNetAssetsFundBalanceGrp/EOYAmt"],
        },
        "contributions": {
            "v2009": ["ReturnData/IRS990/ContributionsGrantsCurrentYear"],
            "v2013": ["ReturnData/IRS990/CYContributionsGrantsAmt", "ReturnData/IRS990/TotalContributionsAmt"],
        },
        "program_service_revenue": {
            "v2009": ["ReturnData/IRS990/ProgramServiceRevenueCY"],
            "v2013": ["ReturnData/IRS990/CYProgramServiceRevenueAmt",
                      "ReturnData/IRS990/TotalProgramServiceRevenueAmt"],
        },
        "fundraising_expenses": {
            "v2009": ["ReturnData/IRS990/TotalFundrsngExpCurrentYear",
                      "ReturnData/IRS990/TotalFunctionalExpenses/Fundraising"],
            "v2013": ["ReturnData/IRS990/CYTotalFundraisingExpenseAmt",
                      "ReturnData/IRS990/TotalFunctionalExpensesGrp/FundraisingAmt"],
        },
        "officer_comp_total": {
            "v2009": ["ReturnData/IRS990/CompCurrentOfficersDirectors/Total",
                      "ReturnData/IRS990/TotalReportableCompFromOrg"],
            "v2013": ["ReturnData/IRS990/CompCurrentOfcrDirectorsGrp/TotalAmt",
                      "ReturnData/IRS990/TotalReportableCompFromOrgAmt"],
        },
        "num_employees": {
            "v2009": ["ReturnData/IRS990/TotalNbrEmployees"],
            "v2013": ["ReturnData/IRS990/TotalEmployeeCnt"],
        },
        "num_volunteers": {
            "v2009": ["ReturnData/IRS990/TotalNbrVolunteers"],
            "v2013": ["ReturnData/IRS990/TotalVolunteersCnt"],
        },
    },
    "990EZ": {
        "website": {
            "v2009": ["ReturnData/IRS990EZ/WebSite"],
            "v2013": ["ReturnData/IRS990EZ/WebsiteAddressTxt"],
        },
        "mission": {
            "v2009": ["ReturnData/IRS990EZ/PrimaryExemptPurpose"],
            "v2013": ["ReturnData/IRS990EZ/PrimaryExemptPurposeTxt"],
        },
        "total_revenue": {
            "v2009": ["ReturnData/IRS990EZ/TotalRevenue"],
            "v2013": ["ReturnData/IRS990EZ/TotalRevenueAmt"],
        },
        "total_expenses": {
            "v2009": ["ReturnData/IRS990EZ/TotalExpenses"],
            "v2013": ["ReturnData/IRS990EZ/TotalExpensesAmt"],
        },
        "total_assets_eoy": {
            "v2009": ["ReturnData/IRS990EZ/TotalAssets/EOY"],
            "v2013": ["ReturnData/IRS990EZ/Form990TotalAssetsGrp/EOYAmt"],
        },
        "total_liabilities_eoy": {
            "v2009": ["ReturnData/IRS990EZ/SumOfTotalLiabilities/EOY"],
            "v2013": ["ReturnData/IRS990EZ/SumOfTotalLiabilitiesGrp/EOYAmt"],
        },
        "net_assets_eoy": {
            "v2009": ["ReturnData/IRS990EZ/NetAssetsOrFundBalancesEOY",
                      "ReturnData/IRS990EZ/NetAssetsOrFundBalances/EOY"],
            "v2013": ["ReturnData/IRS990EZ/NetAssetsOrFundBalancesEOYAmt",
                      "ReturnData/IRS990EZ/NetAssetsOrFundBalancesGrp/EOYAmt"],
        },
        "contributions": {
            "v2009": ["ReturnData/IRS990EZ/ContributionsGiftsGrantsEtc"],
            "v2013": ["ReturnData/IRS990EZ/ContributionsGiftsGrantsEtcAmt"],
        },
        "program_service_revenue": {
            "v2009": ["ReturnData/IRS990EZ/ProgramServiceRevenue"],
            "v2013": ["ReturnData/IRS990EZ/ProgramServiceRevenueAmt"],
        },
    },
    "990PF": {
        "website": {
            "v2009": ["ReturnData/IRS990PF/StatementsRegardingActivities/WebsiteAddress"],
            "v2013": ["ReturnData/IRS990PF/StatementsRegardingActyGrp/WebsiteAddressTxt"],
        },
        "total_revenue": {
            "v2009": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/TotalRevenueAndExpenses"],
            "v2013": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/TotalRevAndExpnssAmt"],
        },
        "total_expenses": {
            "v2009": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/TotalExpensesRevAndExpnss"],
            "v2013": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/TotalExpensesRevAndExpnssAmt"],
        },
        "total_assets_eoy": {
            "v2009": ["ReturnData/IRS990PF/BalanceSheets/TotalAssetsEOY"],
            "v2013": ["ReturnData/IRS990PF/Form990PFBalanceSheetsGrp/TotalAssetsEOYAmt"],
        },
        "total_liabilities_eoy": {
            "v2009": ["ReturnData/IRS990PF/BalanceSheets/TotalLiabilitiesEOY"],
            "v2013": ["ReturnData/IRS990PF/Form990PFBalanceSheetsGrp/TotalLiabilitiesEOYAmt"],
        },
        "net_assets_eoy": {
            "v2009": ["ReturnData/IRS990PF/BalanceSheets/TotalNetAssetsEOY",
                      "ReturnData/IRS990PF/ChangesInNetAssetsFundBalances/TotalNetAssetsFundBalancesEOY"],
            "v2013": ["ReturnData/IRS990PF/Form990PFBalanceSheetsGrp/TotNetAstOrFundBalancesEOYAmt",
                      "ReturnData/IRS990PF/ChgInNetAssetsFundBalancesGrp/TotNetAstOrFundBalancesEOYAmt"],
        },
        "contributions": {
            "v2009": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/ContriRcvdRevAndExpnss",
                      "ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/ContributionsRcvdRevAndExpnss"],
            "v2013": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/ContriRcvdRevAndExpnssAmt"],
        },
        "officer_comp_total": {
            "v2009": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/CompOfcrDirTrstRevAndExpnss"],
            "v2013": ["ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/CompOfcrDirTrstRevAndExpnssAmt"],
        },
    },
}


# --- Repeating groups --------------------------------------------------------
# Each group spec: era -> {"paths": [group element paths], "fields": {field: [relative paths]}}
# Relative paths are tried in order; "flags" fields are X/true/1 indicators.

_PERSON_NAME_V2009 = ["NamePerson", "PersonName", "Name", "NameBusiness/BusinessNameLine1",
                      "BusinessName/BusinessNameLine1"]
_PERSON_NAME_V2013 = ["PersonNm", "BusinessName/BusinessNameLine1Txt", "BusinessName/BusinessNameLine1"]

_ADDR_V2009 = {
    "street": ["USAddress/AddressLine1", "AddressUS/AddressLine1", "ForeignAddress/AddressLine1",
               "AddressForeign/AddressLine1"],
    "city": ["USAddress/City", "AddressUS/City", "ForeignAddress/City", "AddressForeign/City"],
    "state": ["USAddress/State", "AddressUS/State", "ForeignAddress/ProvinceOrState"],
    "zip": ["USAddress/ZIPCode", "AddressUS/ZIPCode", "ForeignAddress/PostalCode"],
}
_ADDR_V2013 = {
    "street": ["USAddress/AddressLine1Txt", "ForeignAddress/AddressLine1Txt", "USAddress/AddressLine1"],
    "city": ["USAddress/CityNm", "ForeignAddress/CityNm", "USAddress/City"],
    "state": ["USAddress/StateAbbreviationCd", "ForeignAddress/ProvinceOrStateNm"],
    "zip": ["USAddress/ZIPCd", "ForeignAddress/ForeignPostalCd"],
}

PEOPLE_GROUPS = {
    # Form 990 Part VII Section A
    "990": [{
        "source": "990-VIIA",
        "v2009": {
            "paths": ["ReturnData/IRS990/Form990PartVIISectionA"],
            "fields": {
                "name": _PERSON_NAME_V2009,
                "title": ["Title"],
                "avg_hours": ["AverageHoursPerWeek"],
                "avg_hours_related": ["AverageHoursPerWeekRelated"],
                "is_director": ["IndividualTrusteeOrDirector"],
                "is_trustee": ["InstitutionalTrustee"],
                "is_officer": ["Officer"],
                "is_key_employee": ["KeyEmployee"],
                "is_highest_comp": ["HighestCompensatedEmployee"],
                "is_former": ["Former"],
                "comp_org": ["ReportableCompFromOrganization"],
                "comp_related": ["ReportableCompFromRelatedOrgs"],
                "other_comp": ["OtherCompensation"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990/Form990PartVIISectionAGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013,
                "title": ["TitleTxt"],
                "avg_hours": ["AverageHoursPerWeekRt"],
                "avg_hours_related": ["AverageHoursPerWeekRltdOrgRt"],
                "is_director": ["IndividualTrusteeOrDirectorInd"],
                "is_trustee": ["InstitutionalTrusteeInd"],
                "is_officer": ["OfficerInd"],
                "is_key_employee": ["KeyEmployeeInd"],
                "is_highest_comp": ["HighestCompensatedEmployeeInd"],
                "is_former": ["FormerOfcrDirectorTrusteeInd"],
                "comp_org": ["ReportableCompFromOrgAmt"],
                "comp_related": ["ReportableCompFromRltdOrgAmt"],
                "other_comp": ["OtherCompensationAmt"],
            },
        },
    }],
    # Form 990-EZ Part IV (officers) and Part VI highest-paid employees
    "990EZ": [{
        "source": "990EZ-IV",
        "v2009": {
            "paths": ["ReturnData/IRS990EZ/OfficerDirectorTrusteeKeyEmpl"],
            "fields": {
                "name": _PERSON_NAME_V2009,
                "title": ["Title"],
                "avg_hours": ["AvgHoursPerWkDevotedToPosition", "AverageHoursPerWeek"],
                "comp_org": ["Compensation"],
                "benefits": ["ContriToEmplBenefitPlansEtc"],
                "expense_acct": ["ExpenseAccountOtherAllowances"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990EZ/OfficerDirectorTrusteeEmplGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013,
                "title": ["TitleTxt"],
                "avg_hours": ["AverageHrsPerWkDevotedToPosRt"],
                "comp_org": ["CompensationAmt"],
                "benefits": ["EmployeeBenefitProgramAmt"],
                "expense_acct": ["ExpenseAccountOtherAllwncAmt"],
            },
        },
    }, {
        "source": "990EZ-HCE",
        "highest_comp": True,
        "v2009": {
            "paths": ["ReturnData/IRS990EZ/CompensationOfHighestPaidEmpl"],
            "fields": {
                "name": _PERSON_NAME_V2009,
                "title": ["Title"],
                "avg_hours": ["AverageHoursPerWeek"],
                "comp_org": ["Compensation"],
                "benefits": ["ContriToEmplBenefitPlansEtc", "EmployeeBenefits"],
                "expense_acct": ["ExpenseAccount", "ExpenseAccountOtherAllowances"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990EZ/CompensationHighestPaidEmplGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013,
                "title": ["TitleTxt"],
                "avg_hours": ["AverageHoursPerWeekRt"],
                "comp_org": ["CompensationAmt"],
                "benefits": ["EmployeeBenefitsAmt"],
                "expense_acct": ["ExpenseAccountAmt"],
            },
        },
    }],
    # Form 990-PF Part VIII
    "990PF": [{
        "source": "990PF-VIII",
        "v2009": {
            "paths": ["ReturnData/IRS990PF/OfcrDirTrusteesKeyEmployeeInfo/OfcrDirTrusteesOrKeyEmployee"],
            "fields": {
                "name": _PERSON_NAME_V2009,
                "title": ["Title"],
                "avg_hours": ["AvgHoursPerWkDevotedToPosition"],
                "comp_org": ["Compensation"],
                "benefits": ["ContriToEmplBenefitPlansEtc"],
                "expense_acct": ["ExpenseAccountOtherAllowances"],
                **_ADDR_V2009,
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990PF/OfficerDirTrstKeyEmplInfoGrp/OfficerDirTrstKeyEmplGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013,
                "title": ["TitleTxt"],
                "avg_hours": ["AverageHrsPerWkDevotedToPosRt"],
                "comp_org": ["CompensationAmt"],
                "benefits": ["EmployeeBenefitProgramAmt"],
                "expense_acct": ["ExpenseAccountOtherAllwncAmt"],
                **_ADDR_V2013,
            },
        },
    }, {
        "source": "990PF-HCE",
        "highest_comp": True,
        "v2009": {
            "paths": ["ReturnData/IRS990PF/OfcrDirTrusteesKeyEmployeeInfo/CompensationOfHighestPaidEmpl"],
            "fields": {
                "name": _PERSON_NAME_V2009,
                "title": ["Title"],
                "avg_hours": ["AverageHoursPerWeek"],
                "comp_org": ["Compensation"],
                "benefits": ["ContriToEmplBenefitPlansEtc", "EmployeeBenefits"],
                "expense_acct": ["ExpenseAccount"],
                **_ADDR_V2009,
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990PF/OfficerDirTrstKeyEmplInfoGrp/CompensationHighestPaidEmplGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013,
                "title": ["TitleTxt"],
                "avg_hours": ["AverageHrsPerWkDevotedToPosRt"],
                "comp_org": ["CompensationAmt"],
                "benefits": ["EmployeeBenefitsAmt"],
                "expense_acct": ["ExpenseAccountAmt"],
                **_ADDR_V2013,
            },
        },
    }],
}

CONTRACTOR_GROUPS = {
    "990": [{
        "source": "990-VIIB",
        "v2009": {
            "paths": ["ReturnData/IRS990/ContractorCompensation"],
            "fields": {
                "name": ["NameOfContractor/NamePerson", "NameOfContractor/NameBusiness/BusinessNameLine1"],
                "street": ["AddressOfContractor/AddressUS/AddressLine1",
                           "AddressOfContractor/AddressForeign/AddressLine1"],
                "city": ["AddressOfContractor/AddressUS/City", "AddressOfContractor/AddressForeign/City"],
                "state": ["AddressOfContractor/AddressUS/State",
                          "AddressOfContractor/AddressForeign/ProvinceOrState"],
                "zip": ["AddressOfContractor/AddressUS/ZIPCode",
                        "AddressOfContractor/AddressForeign/PostalCode"],
                "service_description": ["DescriptionOfServices"],
                "compensation": ["Compensation"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990/ContractorCompensationGrp"],
            "fields": {
                "name": ["ContractorName/PersonNm", "ContractorName/BusinessName/BusinessNameLine1Txt",
                         "ContractorName/BusinessName/BusinessNameLine1"],
                "street": ["ContractorAddress/USAddress/AddressLine1Txt",
                           "ContractorAddress/ForeignAddress/AddressLine1Txt"],
                "city": ["ContractorAddress/USAddress/CityNm", "ContractorAddress/ForeignAddress/CityNm"],
                "state": ["ContractorAddress/USAddress/StateAbbreviationCd",
                          "ContractorAddress/ForeignAddress/ProvinceOrStateNm"],
                "zip": ["ContractorAddress/USAddress/ZIPCd", "ContractorAddress/ForeignAddress/ForeignPostalCd"],
                "service_description": ["ServicesDesc"],
                "compensation": ["CompensationAmt"],
            },
        },
    }],
    "990EZ": [{
        "source": "990EZ-VI",
        "v2009": {
            "paths": ["ReturnData/IRS990EZ/CompensationOfHighestPaidCntrct"],
            "fields": {
                "name": _PERSON_NAME_V2009, **_ADDR_V2009,
                "service_description": ["TypeOfService", "ServiceType"],
                "compensation": ["Compensation"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990EZ/CompensationOfHghstPdCntrctGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013, **_ADDR_V2013,
                "service_description": ["ServiceTypeTxt"],
                "compensation": ["CompensationAmt"],
            },
        },
    }],
    "990PF": [{
        "source": "990PF-VIII",
        "v2009": {
            "paths": ["ReturnData/IRS990PF/OfcrDirTrusteesKeyEmployeeInfo/CompensationOfHighestPaidCntrct",
                      "ReturnData/IRS990PF/OfcrDirTrusteesKeyEmployeeInfo/CompOfHighestPaidCntrctProfSer"],
            "fields": {
                "name": _PERSON_NAME_V2009, **_ADDR_V2009,
                "service_description": ["TypeOfService", "ServiceType"],
                "compensation": ["Compensation"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990PF/OfficerDirTrstKeyEmplInfoGrp/CompensationOfHghstPdCntrctGrp"],
            "fields": {
                "name": _PERSON_NAME_V2013, **_ADDR_V2013,
                "service_description": ["ServiceTypeTxt"],
                "compensation": ["CompensationAmt"],
            },
        },
    }],
}

SCHEDULE_J = {
    "v2009": {
        "paths": ["ReturnData/IRS990ScheduleJ/Form990ScheduleJPartII"],
        "fields": {
            "name": _PERSON_NAME_V2009,
            "title": ["Title"],
            "base_org": ["BaseCompensationFilingOrg"],
            "base_related": ["CompBasedOnRelatedOrgs"],
            "bonus_org": ["BonusFilingOrg"],
            "bonus_related": ["BonusRelatedOrgs"],
            "other_org": ["OtherCompensationFilingOrg"],
            "other_related": ["OtherCompensationRelatedOrgs"],
            "deferred_org": ["DeferredCompFilingOrg"],
            "deferred_related": ["DeferredCompRelatedOrgs"],
            "nontaxable_org": ["NontaxableBenefitsFilingOrg"],
            "nontaxable_related": ["NontaxableBenefitsRelatedOrgs"],
            "total_org": ["TotalCompensationFilingOrg"],
            "total_related": ["TotalCompensationRelatedOrgs"],
        },
    },
    "v2013": {
        "paths": ["ReturnData/IRS990ScheduleJ/RltdOrgOfficerTrstKeyEmplGrp"],
        "fields": {
            "name": _PERSON_NAME_V2013,
            "title": ["TitleTxt"],
            "base_org": ["BaseCompensationFilingOrgAmt"],
            "base_related": ["CompensationBasedOnRltdOrgsAmt"],
            "bonus_org": ["BonusFilingOrganizationAmount", "BonusFilingOrgAmt"],
            "bonus_related": ["BonusRelatedOrganizationsAmt"],
            "other_org": ["OtherCompensationFilingOrgAmt"],
            "other_related": ["OtherCompensationRltdOrgsAmt"],
            "deferred_org": ["DeferredCompensationFlngOrgAmt"],
            "deferred_related": ["DeferredCompRltdOrgsAmt"],
            "nontaxable_org": ["NontaxableBenefitsFilingOrgAmt"],
            "nontaxable_related": ["NontaxableBenefitsRltdOrgsAmt"],
            "total_org": ["TotalCompensationFilingOrgAmt"],
            "total_related": ["TotalCompensationRltdOrgsAmt"],
        },
    },
}

# Schedule R related organizations (used as clustering evidence).
SCHEDULE_R = {
    "v2009": {
        "paths": ["ReturnData/IRS990ScheduleR/IdDisregardedEntities",
                  "ReturnData/IRS990ScheduleR/IdRelatedTaxExemptOrg",
                  "ReturnData/IRS990ScheduleR/IdRelatedOrgTaxablePartnership",
                  "ReturnData/IRS990ScheduleR/IdRelatedOrgTaxableCorpTrust"],
        "fields": {
            "ein": ["EIN"],
            "name": ["NameOfDisregardedEntity/BusinessNameLine1", "NameOfRelatedOrganization/BusinessNameLine1",
                     "NameOfRelatedOrg/BusinessNameLine1"],
        },
    },
    "v2013": {
        "paths": ["ReturnData/IRS990ScheduleR/IdDisregardedEntitiesGrp",
                  "ReturnData/IRS990ScheduleR/IdRelatedTaxExemptOrgGrp",
                  "ReturnData/IRS990ScheduleR/IdRelatedOrgTxblPartnershipGrp",
                  "ReturnData/IRS990ScheduleR/IdRelatedOrgTxblCorpTrGrp"],
        "fields": {
            "ein": ["EIN"],
            "name": ["DisregardedEntityName/BusinessNameLine1Txt", "RelatedOrganizationName/BusinessNameLine1Txt",
                     "DisregardedEntityName/BusinessNameLine1", "RelatedOrganizationName/BusinessNameLine1"],
        },
    },
}


# --- Grants, donor-advised funds, foundation payout, insider loans --------------

# Grants to organizations (Schedule I Part II) and grants paid by private foundations
# (990-PF Part XV line 3a). Grants to individuals are counted but their names are not kept.
GRANT_GROUPS = {
    "990": [{
        "source": "990-I",
        "v2009": {
            "paths": ["ReturnData/IRS990ScheduleI/RecipientTable"],
            "fields": {
                "name": ["RecipientNameBusiness/BusinessNameLine1"],
                "name2": ["RecipientNameBusiness/BusinessNameLine2"],
                "ein": ["EINOfRecipient"],
                "city": ["AddressUS/City", "AddressForeign/City"],
                "state": ["AddressUS/State", "AddressForeign/ProvinceOrState", "AddressForeign/Country"],
                "cash": ["AmountOfCashGrant"],
                "noncash": ["AmountOfNonCashAssistance"],
                "purpose": ["PurposeOfGrant"],
                "irc_section": ["IRCSection"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990ScheduleI/RecipientTable"],
            "fields": {
                "name": ["RecipientBusinessName/BusinessNameLine1Txt", "RecipientBusinessName/BusinessNameLine1"],
                "name2": ["RecipientBusinessName/BusinessNameLine2Txt", "RecipientBusinessName/BusinessNameLine2"],
                "ein": ["RecipientEIN"],
                "city": ["USAddress/CityNm", "USAddress/City", "ForeignAddress/CityNm"],
                "state": ["USAddress/StateAbbreviationCd", "USAddress/State", "ForeignAddress/ProvinceOrStateNm",
                          "ForeignAddress/CountryCd"],
                "cash": ["CashGrantAmt"],
                "noncash": ["NonCashAssistanceAmt"],
                "purpose": ["PurposeOfGrantTxt"],
                "irc_section": ["IRCSectionDesc"],
            },
        },
    }],
    "990PF": [{
        "source": "990PF-XV",
        "v2009": {
            "paths": ["ReturnData/IRS990PF/SupplementaryInformation/GrantOrContriPaidDuringYear"],
            "fields": {
                "name": ["RecipientBusinessName/BusinessNameLine1"],
                "name2": ["RecipientBusinessName/BusinessNameLine2"],
                "person": ["RecipientPersonName"],
                "city": ["RecipientUSAddress/City", "RecipientForeignAddress/City"],
                "state": ["RecipientUSAddress/State", "RecipientForeignAddress/ProvinceOrState",
                          "RecipientForeignAddress/Country"],
                "cash": ["Amount"],
                "street": ["RecipientUSAddress/AddressLine1", "RecipientForeignAddress/AddressLine1"],
                "purpose": ["PurposeOfGrantOrContribution"],
                "foundation_status": ["RecipientFoundationStatus"],
                "relationship": ["RecipientRelationship"],
            },
        },
        "v2013": {
            "paths": ["ReturnData/IRS990PF/SupplementaryInformationGrp/GrantOrContributionPdDurYrGrp"],
            "fields": {
                "name": ["RecipientBusinessName/BusinessNameLine1Txt", "RecipientBusinessName/BusinessNameLine1"],
                "name2": ["RecipientBusinessName/BusinessNameLine2Txt", "RecipientBusinessName/BusinessNameLine2"],
                "person": ["RecipientPersonNm"],
                "city": ["RecipientUSAddress/CityNm", "RecipientUSAddress/City", "RecipientForeignAddress/CityNm"],
                "state": ["RecipientUSAddress/StateAbbreviationCd", "RecipientUSAddress/State",
                          "RecipientForeignAddress/ProvinceOrStateNm", "RecipientForeignAddress/CountryCd"],
                "cash": ["Amt"],
                "street": ["RecipientUSAddress/AddressLine1Txt", "RecipientUSAddress/AddressLine1",
                           "RecipientForeignAddress/AddressLine1Txt"],
                "purpose": ["GrantOrContributionPurposeTxt"],
                "foundation_status": ["RecipientFoundationStatusTxt"],
                "relationship": ["RecipientRelationshipTxt"],
            },
        },
    }],
}

# Donor-advised funds: the Part IV yes/no (990 line 6; 990-EZ) and Schedule D Part I.
# The 2009-era schema has only column (a), donor-advised funds.
_SCHED_D = "ReturnData/IRS990ScheduleD/"
DAF_FIELDS = {
    "maintains_dafs": {
        "v2009": ["ReturnData/IRS990/DonorAdvisedFunds", "ReturnData/IRS990EZ/MaintainAnyDonorAdvisedFunds"],
        "v2013": ["ReturnData/IRS990/DonorAdvisedFundInd", "ReturnData/IRS990EZ/DonorAdvisedFndsInd"],
    },
    "daf_count": {"v2009": [_SCHED_D + "NumberDAFsHeld"], "v2013": [_SCHED_D + "DonorAdvisedFundsHeldCnt"]},
    "daf_contributions": {"v2009": [_SCHED_D + "DonorAdvisedContributions"],
                          "v2013": [_SCHED_D + "DonorAdvisedFundsContriAmt"]},
    "daf_grants": {"v2009": [_SCHED_D + "GrantsPaidFromDonorFunds"], "v2013": [_SCHED_D + "DonorAdvisedFundsGrantsAmt"]},
    "daf_value_eoy": {"v2009": [_SCHED_D + "AggregateDAFValue"], "v2013": [_SCHED_D + "DonorAdvisedFundsVlEOYAmt"]},
    "other_count": {"v2013": [_SCHED_D + "FundsAndOtherAccountsHeldCnt"]},
    "other_contributions": {"v2013": [_SCHED_D + "FundsAndOtherAccountsContriAmt"]},
    "other_grants": {"v2013": [_SCHED_D + "FundsAndOtherAccountsGrantsAmt"]},
    "other_value_eoy": {"v2013": [_SCHED_D + "FundsAndOtherAccountsVlEOYAmt"]},
}

# Private foundation payout: Part X (minimum investment return), XI, XII.
PF_PAYOUT_FIELDS = {
    "noncharitable_assets": {"v2009": ["ReturnData/IRS990PF/MinimumInvestmentReturn/NetNoncharitableAssets"],
                             "v2013": ["ReturnData/IRS990PF/MinimumInvestmentReturnGrp/NetVlNoncharitableAssetsAmt"]},
    "min_investment_return": {
        "v2009": ["ReturnData/IRS990PF/MinimumInvestmentReturn/MinimumInvestmentReturn",
                  "ReturnData/IRS990PF/DistributableAmount/MinimumInvestmentReturn"],
        "v2013": ["ReturnData/IRS990PF/MinimumInvestmentReturnGrp/MinimumInvestmentReturnAmt",
                  "ReturnData/IRS990PF/DistributableAmountGrp/MinimumInvestmentReturnAmt"]},
    "distributable_amount": {"v2009": ["ReturnData/IRS990PF/DistributableAmount/DistributableAmountAsAdjusted"],
                             "v2013": ["ReturnData/IRS990PF/DistributableAmountGrp/DistributableAsAdjustedAmt"]},
    "qualifying_distributions": {
        "v2009": ["ReturnData/IRS990PF/QualifyingDistributions/QualifyingDistributions"],
        "v2013": ["ReturnData/IRS990PF/QualifyingDistriPartXIIGrp/QualifyingDistributionsAmt",
                  "ReturnData/IRS990PF/PFQualifyingDistributionsGrp/QualifyingDistributionsAmt"]},
}

# Schedule L Part II: loans to and from interested persons.
LOAN_GROUPS = {
    "v2009": {
        "paths": ["ReturnData/IRS990ScheduleL/LoanTable"],
        "fields": {
            "name": ["NamePerson", "NameBusiness/BusinessNameLine1"],
            "relationship": ["RelationshipWithOrganization"],
            "purpose": ["PurposeOfLoan"],
            "to_org": ["LoanToOrganization"],
            "from_org": ["LoanFromOrganization"],
            "original_principal": ["OriginalPrincipalAmount"],
            "balance_due": ["BalanceDue"],
            "in_default": ["Default"],
            "board_approved": ["ApprovedByBoard"],
            "written_agreement": ["WrittenAgreement"],
        },
    },
    "v2013": {
        "paths": ["ReturnData/IRS990ScheduleL/LoansBtwnOrgInterestedPrsnGrp"],
        "fields": {
            "name": ["PersonNm", "BusinessName/BusinessNameLine1Txt", "BusinessName/BusinessNameLine1"],
            "relationship": ["RelationshipWithOrgTxt"],
            "purpose": ["LoanPurposeTxt"],
            "to_org": ["LoanToOrganizationInd"],
            "from_org": ["LoanFromOrganizationInd"],
            "original_principal": ["OriginalPrincipalAmt"],
            "balance_due": ["BalanceDueAmt"],
            "in_default": ["DefaultInd"],
            "board_approved": ["BoardOrCommitteeApprovalInd"],
            "written_agreement": ["WrittenAgreementInd"],
        },
    },
}


# --- Where the money went ----------------------------------------------------------
# Form 990 Part IX (statement of functional expenses): one group per line, with total,
# program, management and fundraising columns. (key, label, 2009-era tag, 2013-era tag)
EXPENSE_LINES_990 = [
    ("grants_us_orgs", "Grants to US organizations and governments", "GrantsToDomesticOrgs", "GrantsToDomesticOrgsGrp"),
    ("grants_us_people", "Grants to US individuals", "GrantsToDomesticIndividuals", "GrantsToDomesticIndividualsGrp"),
    ("grants_foreign", "Grants outside the US", "ForeignGrants", "ForeignGrantsGrp"),
    ("member_benefits", "Benefits paid to members", "BenefitsToMembers", "BenefitsToMembersGrp"),
    ("pay_officers", "Pay: officers, directors, trustees, key employees", "CompCurrentOfficersDirectors",
     "CompCurrentOfcrDirectorsGrp"),
    ("pay_disqualified", "Pay: disqualified persons", "CompDisqualPersons", "CompDisqualPersonsGrp"),
    ("pay_other", "Other salaries and wages", "OtherSalariesAndWages", "OtherSalariesAndWagesGrp"),
    ("pension", "Pension plan contributions", "PensionPlanContributions", "PensionPlanContributionsGrp"),
    ("benefits", "Other employee benefits", "OtherEmployeeBenefits", "OtherEmployeeBenefitsGrp"),
    ("payroll_taxes", "Payroll taxes", "PayrollTaxes", "PayrollTaxesGrp"),
    ("fees_management", "Fees: management", "FeesForServicesManagement", "FeesForServicesManagementGrp"),
    ("fees_legal", "Fees: legal", "FeesForServicesLegal", "FeesForServicesLegalGrp"),
    ("fees_accounting", "Fees: accounting", "FeesForServicesAccounting", "FeesForServicesAccountingGrp"),
    ("fees_lobbying", "Fees: lobbying", "FeesForServicesLobbying", "FeesForServicesLobbyingGrp"),
    ("fees_fundraising", "Fees: professional fundraisers", "FeesForServicesProfFundraising",
     "FeesForServicesProfFundraising"),
    ("fees_investment", "Fees: investment management", "FeesForServicesInvstMgmntFees", "FeesForSrvcInvstMgmntFeesGrp"),
    ("fees_other", "Fees: other services", "FeesForServicesOther", "FeesForServicesOtherGrp"),
    ("advertising", "Advertising and promotion", "Advertising", "AdvertisingGrp"),
    ("office", "Office expenses", "OfficeExpenses", "OfficeExpensesGrp"),
    ("it", "Information technology", "InformationTechnology", "InformationTechnologyGrp"),
    ("royalties", "Royalties", "Royalties", "RoyaltiesGrp"),
    ("occupancy", "Occupancy", "Occupancy", "OccupancyGrp"),
    ("travel", "Travel", "Travel", "TravelGrp"),
    ("travel_officials", "Travel or entertainment for public officials", "TravelEntrtnmntPublicOfficials",
     "PymtTravelEntrtnmntPubOfclGrp"),
    ("conferences", "Conferences, conventions and meetings", "ConferencesMeetings", "ConferencesMeetingsGrp"),
    ("interest", "Interest", "Interest", "InterestGrp"),
    ("affiliates", "Payments to affiliates", "PaymentsToAffiliates", "PaymentsToAffiliatesGrp"),
    ("depreciation", "Depreciation and depletion", "DepreciationDepletion", "DepreciationDepletionGrp"),
    ("insurance", "Insurance", "Insurance", "InsuranceGrp"),
    ("other", "Other (as described)", "OtherExpenses", "OtherExpensesGrp"),
    ("all_other", "All other expenses", "AllOtherExpenses", "AllOtherExpensesGrp"),
    ("total", "Total", "TotalFunctionalExpenses", "TotalFunctionalExpensesGrp"),
]
EXPENSE_COLS_990 = {
    "v2009": {"total": "Total", "program": "ProgramServices", "management": "ManagementAndGeneral",
              "fundraising": "Fundraising", "desc": "Description"},
    "v2013": {"total": "TotalAmt", "program": "ProgramServicesAmt", "management": "ManagementAndGeneralAmt",
              "fundraising": "FundraisingAmt", "desc": "Desc"},
}
# Part VIII line 8: fundraising events (gross income, direct expenses).
EVENTS_990 = {
    "special_event_gross": {"v2009": ["ReturnData/IRS990/FundraisingGrossIncome"],
                            "v2013": ["ReturnData/IRS990/FundraisingGrossIncomeAmt"]},
    "special_event_expenses": {"v2009": ["ReturnData/IRS990/FundraisingDirectExpenses"],
                               "v2013": ["ReturnData/IRS990/FundraisingDirectExpensesAmt"]},
}

# 990-EZ Part I lines 10-17 and line 6c; 990-PF Part I column (a). 2013-era tags add "Amt".
EXPENSE_LINES_EZ = [
    ("grants", "Grants and similar amounts paid", "GrantsAndSimilarAmountsPaid", "GrantsAndSimilarAmountsPaidAmt"),
    ("member_benefits", "Benefits paid to members", "BenefitsPaidToOrForMembers", "BenefitsPaidToOrForMembersAmt"),
    ("pay", "Salaries, other pay and benefits", "SalariesOtherCompEmplBenefits", "SalariesOtherCompEmplBnftAmt"),
    ("fees_contractors", "Fees to independent contractors", "FeesAndOthPymtToIndContractors",
     "FeesAndOtherPymtToIndCntrctAmt"),
    ("occupancy", "Occupancy, rent, utilities, maintenance", "OccupancyRentUtilitiesAndMaint",
     "OccupancyRentUtltsAndMaintAmt"),
    ("printing", "Printing, publications, postage", "PrintingPublicationsPostage", "PrintingPublicationsPostageAmt"),
    ("other", "Other expenses (detail on Schedule O)", "OtherExpensesTotal", "OtherExpensesTotalAmt"),
    ("total", "Total", "TotalExpenses", "TotalExpensesAmt"),
]
EVENTS_EZ = {
    "special_event_gross": {"v2009": ["ReturnData/IRS990EZ/SpecialEventsGrossRevenue"],
                            "v2013": ["ReturnData/IRS990EZ/SpecialEventsGrossRevenueAmt"]},
    "special_event_expenses": {"v2009": ["ReturnData/IRS990EZ/SpecialEventsDirectExpenses"],
                               "v2013": ["ReturnData/IRS990EZ/SpecialEventsDirectExpensesAmt"]},
}
EXPENSE_LINES_PF = [
    ("pay_officers", "Pay: officers, directors, trustees", "CompOfcrDirTrstRevAndExpnss", "CompOfcrDirTrstRevAndExpnssAmt"),
    ("pay_other", "Other salaries and wages", "OthEmplSlrsWgsRevAndExpnss", "OthEmplSlrsWgsRevAndExpnssAmt"),
    ("pension", "Pension plans and employee benefits", "PensionEmplBnftRevAndExpnss", "PensionEmplBnftRevAndExpnssAmt"),
    ("fees_legal", "Fees: legal", "LegalFeesRevAndExpnss", "LegalFeesRevAndExpnssAmt"),
    ("fees_accounting", "Fees: accounting", "AccountingFeesRevAndExpnss", "AccountingFeesRevAndExpnssAmt"),
    ("fees_other", "Fees: other professional", "OtherProfFeesRevAndExpnss", "OtherProfFeesRevAndExpnssAmt"),
    ("interest", "Interest", "InterestRevAndExpnss", "InterestRevAndExpnssAmt"),
    ("taxes", "Taxes", "TaxesRevAndExpnss", "TaxesRevAndExpnssAmt"),
    ("depreciation", "Depreciation and depletion", "DeprecAndDepletionRevAndExpnss", "DeprecAndDpltnRevAndExpnssAmt"),
    ("occupancy", "Occupancy", "OccupancyRevAndExpnss", "OccupancyRevAndExpnssAmt"),
    ("travel_conferences", "Travel, conferences and meetings", "TravConfMeetingRevAndExpnss",
     "TravConfMeetingRevAndExpnssAmt"),
    ("printing", "Printing and publications", "PrintingAndPubRevAndExpnss", "PrintingAndPubRevAndExpnssAmt"),
    ("other", "Other expenses", "OtherExpensesRevAndExpnss", "OtherExpensesRevAndExpnssAmt"),
    ("grants", "Contributions, gifts, grants paid", "ContriGiftsPaidRevAndExpnss", "ContriPaidRevAndExpnssAmt"),
    ("total", "Total", "TotalExpensesRevAndExpnss", "TotalExpensesRevAndExpnssAmt"),
]
EXPENSE_ROOTS = {"990EZ": "ReturnData/IRS990EZ/", "990PF": "ReturnData/IRS990PF/AnalysisOfRevenueAndExpenses/"}
PAY_KEYS = {"pay_officers", "pay_disqualified", "pay_other", "pension", "benefits", "payroll_taxes", "pay"}
GRANT_KEYS = {"grants_us_orgs", "grants_us_people", "grants_foreign", "grants"}


# Schedule B Part I contributors and Part II noncash property (990-PF only; public charities'
# Schedule B names are not public). City and state only: street addresses are not read.
DONOR_GROUPS = {
    "v2009": {
        "paths": ["ReturnData/IRS990ScheduleB/ContributorInfo"],
        "fields": {
            "num": ["ContributorNumber"],
            "person": ["ContributorNameIndividual"],
            "business": ["ContributorNameBusiness/BusinessNameLine1", "ContributorNameBusiness"],
            "city": ["ContributorAddressUS/City", "ContributorAddressForeign/City"],
            "state": ["ContributorAddressUS/State", "ContributorAddressForeign/ProvinceOrState",
                      "ContributorAddressForeign/Country"],
            "total": ["AggregateContributions"],
            "is_person": ["PersonContributionType"],
        },
    },
    "v2013": {
        "paths": ["ReturnData/IRS990ScheduleB/ContributorInformationGrp"],
        "fields": {
            "num": ["ContributorNum"],
            "person": ["ContributorPersonNm"],
            "business": ["ContributorBusinessName/BusinessNameLine1Txt", "ContributorBusinessName/BusinessNameLine1"],
            "city": ["ContributorUSAddress/CityNm", "ContributorForeignAddress/CityNm"],
            "state": ["ContributorUSAddress/StateAbbreviationCd", "ContributorForeignAddress/ProvinceOrStateNm",
                      "ContributorForeignAddress/CountryCd"],
            "total": ["TotalContributionsAmt"],
            "is_person": ["PersonContributionInd"],
        },
    },
}
DONOR_NONCASH = {
    "v2009": {"paths": ["ReturnData/IRS990ScheduleB/NonCashPropertyContribution", "ReturnData/IRS990ScheduleB/NoncashProperty"],
              "fields": {"num": ["ContributorNumber"], "fmv": ["FairMarketValue", "FMVOfNoncashProperty"]}},
    "v2013": {"paths": ["ReturnData/IRS990ScheduleB/NonCashPropertyContributionGrp"],
              "fields": {"num": ["ContributorNum"], "fmv": ["FairMarketValueAmt"]}},
}
