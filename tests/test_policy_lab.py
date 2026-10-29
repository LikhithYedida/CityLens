"""Offline tests for the Policy Lab's synthetic control, using made-up cities."""
import numpy as np
import pandas as pd
import pytest

from analysis import policy_lab as pl
from pipeline import zillow_city

DATES = pd.date_range("2015-01-01", "2024-12-01", freq="MS")
TREAT = pd.Timestamp("2019-01-01")


def fake_donors(n=12, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(len(DATES))
    cols = {}
    for j in range(n):
        trend = rng.uniform(0.001, 0.006)
        wiggle = 0.02 * np.sin(t / rng.uniform(4, 12) + rng.uniform(0, 6))
        cols[f"City{j}, XX"] = np.log(1000) + trend * t + wiggle
    return pd.DataFrame(cols, index=DATES)


def test_synth_recovers_known_blend_and_zero_effect():
    Y = fake_donors()
    y = 0.6 * Y["City0, XX"] + 0.4 * Y["City3, XX"] + 0.25  # level shift shouldn't matter (demeaned)
    r = pl.synth(y, Y, TREAT)
    assert r.weights.sum() == pytest.approx(1.0)
    assert (r.weights >= 0).all()
    assert r.weights["City0, XX"] == pytest.approx(0.6, abs=0.05)
    assert r.pre_rmspe < 1e-3
    assert abs(r.effect_pct("2024-12-01")) < 0.01


def test_synth_detects_an_injected_effect_and_placebo_flags_it():
    Y = fake_donors(n=20)
    y = 0.5 * Y["City1, XX"] + 0.5 * Y["City2, XX"]
    y = y + np.where(DATES >= TREAT, np.log(0.85), 0.0)  # 15% drop after treatment
    r = pl.synth(y, Y, TREAT)
    assert r.effect_pct("2024-12-01") == pytest.approx(-0.15, abs=0.02)
    pv = pl.placebo_space(Y, TREAT, r)
    assert pv.attrs["rank"] == 1
    assert pv.attrs["p_value"] == pytest.approx(1 / 21)


def test_synth_respects_start_and_end_window():
    Y = fake_donors()
    r = pl.synth(Y["City0, XX"], Y.drop(columns="City0, XX"), TREAT, start="2016-01-01", end="2018-12-01")
    assert r.actual.index[0] == pd.Timestamp("2016-01-01")
    assert r.actual.index[-1] == pd.Timestamp("2018-12-01")


def test_suburb_city_fills_one_missing_month_only():
    panel = pd.DataFrame({"A, MN": np.log(np.linspace(1000, 1200, len(DATES)))}, index=DATES)
    panel.loc["2017-01-01", "A, MN"] = np.nan
    assert pl.suburb_city(panel, "A, MN").notna().all()
    panel.loc["2018-01-01":"2018-03-01", "A, MN"] = np.nan
    assert pl.suburb_city(panel, "A, MN") is None


def test_donor_pool_excludes_reform_cities_states_and_incomplete():
    meta = pd.DataFrame({
        "city_key": ["Minneapolis, MN", "Saint Paul, MN", "Austin, TX", "Fresno, CA", "Omaha, NE",
                     "Tulsa, OK", "Gap, OK"],
        "state": ["MN", "MN", "TX", "CA", "NE", "OK", "OK"],
        "metro": [""] * 7, "size_rank": [50, 80, 10, 30, 40, 45, 400],
    })
    panel = pd.DataFrame({k: 1.0 for k in meta["city_key"]}, index=DATES)
    panel.loc["2016-01-01", "Tulsa, OK"] = np.nan
    assert pl.donor_pool(meta, panel) == ["Omaha, NE"]


def test_zillow_city_reshape_keeps_large_and_minnesota_cities():
    wide = pd.DataFrame({
        "RegionID": [1, 2, 3], "SizeRank": [53, 5000, 6000],
        "RegionName": ["Minneapolis", "Tiny Town", "Edina"], "RegionType": ["city"] * 3,
        "StateName": ["MN", "TX", "MN"], "State": ["MN", "TX", "MN"],
        "Metro": ["Minneapolis-St. Paul-Bloomington, MN-WI", "", "Minneapolis-St. Paul-Bloomington, MN-WI"],
        "CountyName": ["Hennepin County", "X", "Hennepin County"],
        "2014-12-31": [1, 1, 1], "2015-01-31": [1200.0, 900.0, 1500.0], "2015-02-28": [1210.0, None, 1510.0],
    })
    out = zillow_city.reshape(wide, "rent")
    assert set(out["city_key"]) == {"Minneapolis, MN", "Edina, MN"}
    assert out["date"].min() == pd.Timestamp("2015-01-01")
    zillow_city.validate(out, "rent")
