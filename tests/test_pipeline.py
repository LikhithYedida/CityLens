"""Offline tests with small fake data, so they run without internet or keys."""
import pandas as pd
import pytest

from pipeline.fred import to_monthly
from pipeline.utils import SourceError
from pipeline.zillow import reshape, validate


def fake_zillow_county():
    return pd.DataFrame({
        "RegionID": [1, 2, 3],
        "SizeRank": [0, 1, 2],
        "RegionName": ["United States", "Oakland County", "Wayne County"],
        "RegionType": ["country", "county", "county"],
        "StateName": [None, "MI", "MI"],
        "State": [None, "MI", "MI"],
        "Metro": [None, "Detroit-Warren-Dearborn, MI", "Detroit-Warren-Dearborn, MI"],
        "StateCodeFIPS": [0, 26, 26],
        "MunicipalCodeFIPS": [0, 125, 163],
        "2014-12-31": [180000, 200000, 90000],
        "2015-01-31": [181000, 201000, None],
        "2015-02-28": [182000, 202000, 91000],
    })


def test_reshape_drops_pre_window_missing_and_country():
    out = reshape(fake_zillow_county(), "home_value", "county")
    assert set(out["region_name"]) == {"Oakland County", "Wayne County"}
    assert out["date"].min() == pd.Timestamp("2015-01-01")
    assert len(out) == 3  # Oakland x2 months + Wayne x1 (one missing)


def test_reshape_builds_5_digit_county_fips():
    out = reshape(fake_zillow_county(), "home_value", "county")
    assert set(out["county_fips"]) == {"26125", "26163"}


def test_validate_catches_duplicates():
    out = reshape(fake_zillow_county(), "home_value", "county")
    with pytest.raises(SourceError):
        validate(pd.concat([out, out.head(1)]), "fake")


def test_fred_weekly_to_monthly_average_and_missing_dot():
    obs = pd.DataFrame({"date": ["2026-01-01", "2026-01-08", "2026-01-15", "2026-02-05"],
                        "value": ["6.0", "7.0", ".", "6.5"]})
    monthly = to_monthly(obs, "mortgage_rate_30y")
    assert monthly.loc["2026-01-01", "mortgage_rate_30y"] == pytest.approx(6.5)
    assert monthly.loc["2026-02-01", "mortgage_rate_30y"] == pytest.approx(6.5)
