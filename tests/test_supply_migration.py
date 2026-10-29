"""Offline tests for building permits and IRS migration, using tiny fake files."""
import pandas as pd
import pytest

from pipeline import geo, migration, permits
from pipeline.utils import SourceError
from tests.test_joins import fake_delineation_raw

COUNTY_TO_CBSA = geo.clean_delineation(fake_delineation_raw())  # Oakland + Wayne -> Detroit 19820


# ---------- building permits ----------

def fake_permits_text(scale=1):
    header1 = "Survey,FIPS,FIPS,Region,Division,County,,1-unit,,,2-units,,,3-4 units,,,5+ units,,,1-unit rep,,,2-units rep,,,3-4 units rep,,,5+ units rep,,"
    header2 = "Date,State,County,Code,Code,Name,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value"
    rows = [
        # county, 1-unit, 2-units, 3-4, 5+ (units are the 2nd of each triple); reported-only after
        f"2024,26,125,2,3,Oakland County,{500*scale},{500*scale},1,10,{20*scale},1,5,{18*scale},1,20,{400*scale},1,1,1,1,1,1,1,1,1,1,1,1,1",
        f"2024,26,163,2,3,Wayne County,{300*scale},{300*scale},1,5,{10*scale},1,0,0,0,10,{200*scale},1,1,1,1,1,1,1,1,1,1,1,1,1",
        f"2024,29,510,2,4,St. Louis city,{100*scale},{100*scale},1,0,0,0,0,0,0,5,{100*scale},1,1,1,1,1,1,1,1,1,1,1,1,1",
    ]
    return "\n".join([header1, header2, ""] + rows) + "\n"


def test_permits_parse_uses_full_estimates_not_reported_only():
    df = permits.parse_year(fake_permits_text(), 2024)
    oak = df[df["county_fips"] == "26125"].iloc[0]
    assert oak["units_1"] == 500 and oak["units_5plus"] == 400
    assert oak["units_total"] == 938
    assert oak["units_multifamily"] == 438


def test_permits_validate_rejects_unrealistic_national_total():
    with pytest.raises(SourceError):
        permits.validate(permits.parse_year(fake_permits_text(), 2024), 2024)
    permits.validate(permits.parse_year(fake_permits_text(scale=600), 2024), 2024)  # ~1.2M units: ok


def test_permits_layout_change_fails_loudly():
    bad = fake_permits_text().replace("Units", "U")
    with pytest.raises(SourceError):
        permits.parse_year(bad, 2024)


def test_permits_metro_rollup():
    metro = permits.to_metro(permits.parse_year(fake_permits_text(), 2024), COUNTY_TO_CBSA)
    detroit = metro[metro["cbsa_code"] == "19820"].iloc[0]
    assert detroit["units_total"] == 938 + 510
    assert detroit["multifamily_share"] == pytest.approx((438 + 210) / (938 + 510))


# ---------- IRS migration ----------

def fake_inflow():
    # y2 = destination county; y1 = where people came from (or summary codes)
    return pd.DataFrame({
        "y2_statefips": ["26", "26", "26", "26", "26"],
        "y2_countyfips": ["125", "125", "125", "163", "163"],
        "y1_statefips": ["96", "97", "26", "97", "26"],
        "y1_countyfips": ["000", "000", "125", "000", "163"],
        "y1_state": ["MI"] * 5,
        "y1_countyname": ["Total US+Foreign", "Total US", "Non-migrants", "Total US", "Non-migrants"],
        "n1": ["600", "500", "40000", "300", "90000"],
        "n2": ["1100", "1000", "80000", "700", "200000"],
        "agi": ["60000", "50000", "9000000", "20000", "8000000"],
    })


def fake_outflow():
    # y1 = origin county; y2 = where people went (or summary codes)
    return pd.DataFrame({
        "y1_statefips": ["26", "26", "26"],
        "y1_countyfips": ["125", "163", "163"],
        "y2_statefips": ["97", "97", "26"],
        "y2_countyfips": ["000", "000", "163"],
        "y2_state": ["MI"] * 3,
        "y2_countyname": ["Total US", "Total US", "Non-migrants"],
        "n1": ["450", "380", "90000"],
        "n2": ["800", "900", "200000"],
        "agi": ["30000", "35000", "8000000"],
    })


def test_period_code():
    assert migration.period_code(2022) == "2223"
    assert migration.period_code(2015) == "1516"


def test_migration_uses_us_only_summary_rows():
    s = migration.summarize(fake_inflow(), "inflow").set_index("county_fips")
    assert s.loc["26125", "inflow_people"] == 1000  # the 97/000 row, not 96/000 or non-movers
    assert s.loc["26163", "inflow_agi_thousands"] == 20000


def test_migration_net_and_metro_cancels_internal_moves(monkeypatch):
    def fake_fetch(kind, y1):
        return fake_inflow() if kind == "inflow" else fake_outflow()
    monkeypatch.setattr(migration, "fetch", fake_fetch)
    county = migration.build_period(2022).set_index("county_fips")
    assert county.loc["26125", "net_people"] == 1000 - 800
    assert county.loc["26163", "net_people"] == 700 - 900
    assert bool(county["new_series"].all())

    metro = migration.to_metro(county.reset_index(), COUNTY_TO_CBSA, acs_county=None)
    assert metro.iloc[0]["net_people"] == (1000 - 800) + (700 - 900)


def test_migration_validate_flags_mismatched_totals():
    df = pd.DataFrame({"inflow_people": [1000.0], "outflow_people": [500.0]})
    with pytest.raises(SourceError):
        migration.validate(df, "test")


def test_permits_drops_alias_rows_with_identical_numbers():
    text = fake_permits_text().replace(
        "2024,26,163,2,3,Wayne County",
        "2024,26,125,2,3,Oakland Cnty Alias,500,500,1,10,20,1,5,18,1,20,400,1,1,1,1,1,1,1,1,1,1,1,1,1\n2024,26,163,2,3,Wayne County")
    df = permits.parse_year(text, 2024)
    assert (df["county_fips"] == "26125").sum() == 1


def test_permits_conflicting_duplicates_fail_loudly():
    text = fake_permits_text().replace(
        "2024,26,163,2,3,Wayne County",
        "2024,26,125,2,3,Oakland Conflict,1,999,1,10,20,1,5,18,1,20,400,1,1,1,1,1,1,1,1,1,1,1,1,1\n2024,26,163,2,3,Wayne County")
    with pytest.raises(SourceError):
        permits.parse_year(text, 2024)
