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
    "2024v1.0", "2024v2.0", "2024v3.0", "2024v4.0", "2024v4.1", "2024v4.2", "2024v5.0", "2024v5.1",
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
