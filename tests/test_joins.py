"""Offline tests for the crosswalk, Census, and BLS logic using tiny fake data."""
import numpy as np
import pandas as pd
import pytest

from pipeline import census_acs, geo, qcew


# ---------- crosswalk ----------

def fake_delineation_raw():
    return pd.DataFrame({
        "CBSA Code": ["19820", "19820", "41180", "35620", None],
        "CBSA Title": ["Detroit-Warren-Dearborn, MI", "Detroit-Warren-Dearborn, MI",
                       "St. Louis, MO-IL", "New York-Newark-Jersey City, NY-NJ", None],
        "Metropolitan/Micropolitan Statistical Area": ["Metropolitan Statistical Area"] * 4 + [None],
        "County/County Equivalent": ["Oakland County", "Wayne County", "St. Louis city",
                                     "Kings County", None],
        "State Name": ["Michigan", "Michigan", "Missouri", "New York", None],
        "FIPS State Code": ["26", "26", "29", "36", None],
        "FIPS County Code": ["125", "163", "510", "47", None],
    })


def test_clean_delineation_builds_fips_and_drops_footnotes():
    d = geo.clean_delineation(fake_delineation_raw())
    assert len(d) == 4
    assert set(d["county_fips"]) == {"26125", "26163", "29510", "36047"}
    assert set(d["cbsa_type"]) == {"Metropolitan"}


@pytest.mark.parametrize("title,expected", [
    ("New York-Newark-Jersey City, NY-NJ", "new york|ny"),
    ("St. Louis, MO-IL", "st louis|mo"),
    ("Louisville/Jefferson County, KY-IN", "louisville|ky"),
])
def test_cbsa_short_key(title, expected):
    assert geo.cbsa_short_key(title) == expected


def test_saint_and_st_match():
    assert geo.zillow_short_key("Saint Louis, MO") == geo.cbsa_short_key("St. Louis, MO-IL")


def fake_zillow():
    metro = pd.DataFrame({
        "zillow_region_id": [1, 2, 3],
        "region_name": ["Detroit, MI", "St. Louis, MO", "Nowhere, ZZ"],
        "state": ["MI", "MO", "ZZ"],
        "geography": "metro",
    })
    county = pd.DataFrame({
        "zillow_region_id": [10, 11],
        "region_name": ["Oakland County", "Wayne County"],
        "state": ["MI", "MI"],
        "geography": "county",
        "metro_name": ["Detroit, MI", "Detroit, MI"],
        "county_fips": ["26125", "26163"],
    })
    return pd.concat([metro, county], ignore_index=True)


def test_crosswalk_methods():
    x = geo.build_crosswalk(fake_zillow(), geo.clean_delineation(fake_delineation_raw()))
    by_id = x.set_index("zillow_region_id")
    assert by_id.loc[1, "cbsa_code"] == "19820"
    assert by_id.loc[1, "match_method"] == "both_agree"
    assert by_id.loc[2, "match_method"] == "name_only"
    assert by_id.loc[3, "match_method"] == "unmatched"


# ---------- Census ACS ----------

def test_acs_negative_codes_become_missing_and_burden_computed():
    raw = pd.DataFrame([{
        "NAME": "Oakland County, Michigan", "state": "26", "county": "125",
        "B01003_001E": "1000", "B19013_001E": "-666666666", "B25001_001E": "450",
        "B25003_001E": "400", "B25003_003E": "100", "B25064_001E": "1200",
        "B25077_001E": "300000", "B25070_001E": "100", "B25070_007E": "10",
        "B25070_008E": "5", "B25070_009E": "5", "B25070_010E": "20", "B25070_011E": "10",
    }])
    df = census_acs.clean_year(raw, 2023)
    assert np.isnan(df.loc[0, "median_household_income"])
    assert df.loc[0, "rent_burdened_units"] == 40
    assert df.loc[0, "rent_burden_base"] == 90
    assert df.loc[0, "owner_units"] == 300


def test_acs_metro_weighted_median():
    county = pd.DataFrame({
        "county_fips": ["26125", "26163"], "year": [2023, 2023],
        "population": [100, 300], "median_household_income": [100_000, 50_000],
        "housing_units": [50, 150], "occupied_units": [40, 120], "renter_units": [10, 60],
        "owner_units": [30, 60], "median_gross_rent": [1500, 1000],
        "median_home_value": [400_000, 150_000], "rent_burdened_units": [3, 30],
        "rent_burden_base": [10, 60],
    })
    metro, unmapped = census_acs.to_metro(county, geo.clean_delineation(fake_delineation_raw()))
    row = metro.iloc[0]
    assert row["population"] == 400
    assert row["median_household_income"] == pytest.approx((100_000 * 40 + 50_000 * 120) / 160)
    assert row["renter_share"] == pytest.approx(70 / 160)
    assert unmapped.empty


# ---------- BLS QCEW ----------

def fake_qcew_quarter():
    return pd.DataFrame({
        "area_fips": ["26125", "26163", "26999", "C1982", "26000"],
        "own_code": [0, 0, 0, 0, 0],
        "agglvl_code": [70, 70, 70, 40, 50],
        "year": [2025] * 5, "qtr": [2] * 5,
        "disclosure_code": [None, None, None, None, None],
        "month1_emplvl": [100, 200, 5, 300, 999], "month2_emplvl": [110, 200, 5, 310, 999],
        "month3_emplvl": [120, 200, 5, 320, 999],
        "total_qtrly_wages": [130_000, 260_000, 1, 390_000, 1], "avg_wkly_wage": [909, 1000, 1, 970, 1],
    })


def test_qcew_county_monthly_reshape():
    c = qcew.to_monthly_county(fake_qcew_quarter())
    assert set(c["county_fips"]) == {"26125", "26163"}  # drops unknown county and non-county rows
    assert sorted(c["date"].dt.month.unique()) == [4, 5, 6]
    may = c[(c["county_fips"] == "26125") & (c["date"].dt.month == 5)]
    assert may["employment"].iloc[0] == 110


def test_qcew_suppressed_becomes_missing():
    q = fake_qcew_quarter()
    q.loc[0, "disclosure_code"] = "N"
    c = qcew.to_monthly_county(q)
    assert c[c["county_fips"] == "26125"]["employment"].isna().all()


def test_qcew_metro_sum_and_wage():
    c = qcew.to_monthly_county(fake_qcew_quarter())
    m = qcew.to_metro(c, geo.clean_delineation(fake_delineation_raw()))
    april = m[m["date"].dt.month == 4].iloc[0]
    assert april["employment"] == 300
    assert april["avg_weekly_wage"] == pytest.approx((130_000 + 260_000) / (110 + 200) / 13)



def test_crosswalk_report_saves_as_utf8(tmp_path, monkeypatch):
    """Windows' default encoding can't save the arrow in the report title."""
    monkeypatch.setattr(geo, "REPORT_PATH", tmp_path / "report.md")
    x = geo.build_crosswalk(fake_zillow(), geo.clean_delineation(fake_delineation_raw()))
    geo.write_report(x)
    text = (tmp_path / "report.md").read_bytes().decode("utf-8")
    assert "Nowhere, ZZ" in text and text.startswith("# Zillow to Census")    
