"""Offline tests for the Forecast Engine using a small synthetic metro panel."""
import numpy as np
import pandas as pd
import pytest

from analysis import forecast_engine as fe

DATES = pd.date_range("2015-01-01", "2024-12-01", freq="MS")


def synthetic_raw(n=30, seed=0):
    """Metros whose rent growth persists, so a model can learn something real."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n):
        drift = rng.normal(0.003, 0.002)
        rent, home = 1000.0, 250_000.0
        for d in DATES:
            rent *= np.exp(drift + rng.normal(0, 0.002))
            home *= np.exp(drift * 1.1 + rng.normal(0, 0.003))
            rows.append({"cbsa_code": f"{c:05d}", "cbsa_title": f"Metro {c}", "date": d, "rent": rent,
                         "home_value": home, "employment": 100_000 * np.exp(drift * d.year / 10),
                         "median_household_income": 70_000.0, "population": 500_000.0 + c,
                         "mortgage_rate_30y": 4 + d.year - 2015 if d.year < 2023 else 6.5,
                         "permits_per_1k": 4.0, "net_migration_rate_per_1k": 1.0})
    return pd.DataFrame(rows)


def test_features_target_is_12_months_ahead_and_never_uses_future():
    raw = synthetic_raw(n=2)
    feat = fe.build_features(raw, "rent")
    m = feat[feat["cbsa_code"] == "00000"].set_index("date")
    r = raw[raw["cbsa_code"] == "00000"].set_index("date")["rent"]
    d = pd.Timestamp("2018-06-01")
    assert m.loc[d, "target"] == pytest.approx(np.log(r[d + pd.DateOffset(months=12)] / r[d]))
    assert m.loc[d, "growth_12m"] == pytest.approx(np.log(r[d] / r[d - pd.DateOffset(months=12)]))
    assert m["target"].iloc[-12:].isna().all()          # last 12 months have no outcome yet
    assert m["growth_12m"].index.min() == pd.Timestamp("2016-01-01")


def test_relative_target_averages_zero_each_month():
    feat = fe.build_features(synthetic_raw(), "rent")
    by_month = feat.dropna(subset=["target_rel"]).groupby("date")["target_rel"].mean()
    assert by_month.abs().max() < 1e-12


def test_publication_lags_are_applied():
    raw = synthetic_raw(n=1)
    raw["permits_per_1k"] = np.arange(len(raw), dtype=float)
    feat = fe.build_features(raw, "rent").set_index("date")
    d = pd.Timestamp("2020-06-01")
    assert feat.loc[d, "permits_per_1k"] == raw.set_index("date").loc[
        d - pd.DateOffset(months=fe.LAGS["permits"]), "permits_per_1k"]


def test_conformal_quantile_hits_requested_level():
    rng = np.random.default_rng(1)
    cal = pd.DataFrame({"target": rng.normal(0, 1, 2000), "volatility": 1.0})
    q = fe.conformal_quantile(cal, pd.Series(0.0, index=cal.index), floor=0.1, level=0.8)
    assert q == pytest.approx(1.2816, abs=0.08)  # 80% two-sided normal quantile


def test_backtest_only_trains_on_known_outcomes_and_beats_flat():
    feat = fe.build_features(synthetic_raw(), "rent")
    bt = fe.backtest(feat)
    assert set(bt["year"]) <= set(fe.TEST_YEARS)
    sc = fe.score_backtest(bt)
    assert {"All years", "2022-2025"} <= set(sc.index)
    assert sc.loc["All years", fe.MODEL] < sc.loc["All years", "Flat"]
    assert (bt["hi"] >= bt["lo"]).all()


def test_latest_forecast_covers_every_metro_with_ordered_ranges():
    raw = synthetic_raw()
    fc = fe.latest_forecast(fe.build_features(raw, "rent"))
    assert fc["cbsa_code"].nunique() == raw["cbsa_code"].nunique()
    assert (fc["lo"] <= fc["forecast"]).all() and (fc["forecast"] <= fc["hi"]).all()
    assert fc["forecast"].equals((fc["two_part"] + fc["direct"]) / 2)
