"""Offline tests for the Rising City Detector using a small synthetic panel."""
import numpy as np
import pandas as pd
import pytest

from analysis import rising_cities as rc


def synthetic_panel(n_metros=60, years=range(2017, 2025), seed=0):
    """Fake metros where next-year growth truly depends on momentum and affordability."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_metros):
        for y in years:
            momentum = rng.normal(0.05, 0.03)
            pti = rng.normal(1.4, 0.3)
            rows.append({
                "cbsa_code": f"M{c:03d}", "origin": y,
                "home_value": 300_000.0, "home_value_prev": 300_000.0 / (1 + momentum),
                "home_value_next": 300_000.0 * (1 + 0.03 + 0.5 * (momentum - 0.05) - 0.02 * (pti - 1.4)
                                                + rng.normal(0, 0.005)),
                "income": 300_000.0 / np.exp(pti),
                "employment": 1_000 * (1 + rng.normal(0.01, 0.01)), "employment_prev": 1_000.0,
                "wage": 1_000 * (1 + rng.normal(0.03, 0.01)), "wage_prev": 1_000.0,
                "migration": rng.normal(2, 4), "permits": rng.normal(4, 1.5),
            })
    return rc.add_features(pd.DataFrame(rows))


def test_add_features_math():
    raw = pd.DataFrame([{"home_value": 110.0, "home_value_prev": 100.0, "home_value_next": 121.0,
                         "income": 55.0, "employment": 105.0, "employment_prev": 100.0,
                         "wage": 102.0, "wage_prev": 100.0}])
    f = rc.add_features(raw).iloc[0]
    assert f["momentum"] == pytest.approx(0.10)
    assert f["future_growth"] == pytest.approx(0.10)
    assert f["price_to_income"] == pytest.approx(np.log(2))
    assert f["job_growth"] == pytest.approx(0.05)


def test_prepare_zscores_and_relative_target_within_year():
    d = rc.prepare(synthetic_panel())
    by_year = d.groupby("origin")
    assert by_year["momentum_z"].mean().abs().max() < 1e-9
    assert (by_year["momentum_z"].std() - 1).abs().max() < 1e-9
    assert by_year["target_rel"].mean().abs().max() < 1e-12


def test_signal_direction():
    df = pd.DataFrame({"momentum_z": [1.0, -1.0], "price_to_income_z": [-1.0, 1.0]})
    s = rc.signal(df)
    assert s.iloc[0] > s.iloc[1]  # rising and cheap beats falling and pricey


def test_quintile_spread_and_rank_corr_on_perfect_prediction():
    actual = pd.Series(np.arange(50, dtype=float))
    assert rc.rank_corr(actual, actual) == pytest.approx(1.0)
    assert rc.quintile_spread(actual, actual) > 0
    assert rc.quintile_spread(-actual, actual) < 0


def test_backtest_finds_true_signal_and_never_trains_on_test_year():
    d = rc.prepare(synthetic_panel())
    bt, quint = rc.backtest(d, first_test=2021)
    assert set(bt["test_year"]) == {2021, 2022, 2023, 2024}
    chosen = bt[bt["design"] == rc.CHOSEN]
    assert (chosen["rank_corr"] > 0.5).all()
    q = quint.groupby("quintile")["realized_rel_pp"].mean()
    assert q[5] > q[1]


def test_explain_recovers_signs():
    d = rc.prepare(synthetic_panel(n_metros=120))
    exp = rc.explain(d)
    main = exp["specs"][exp["specs"]["spec"] == "All years"].set_index("feature")
    assert main.loc["momentum", "effect_pp"] > 0
    assert main.loc["price_to_income", "effect_pp"] < 0
    assert set(exp["yearly"]["origin"]) == set(d["origin"].unique())


def test_classify_labels():
    d = pd.DataFrame({
        "signal_quintile": [5, 5, 1, 3],
        "job_growth": [0.01, -0.01, 0.0, 0.02],
        "migration_3yr_avg": [0.0, 0.0, 30.0, 1.0],
    })
    labels = rc.classify(d).tolist()
    assert labels[0] == "Rising City"
    assert labels[1] == "Rising (prices only, jobs flat)"
    assert labels[2] == "Cooling Boomtown"
    assert pd.isna(labels[3])  # empty label (None or NaN, depending on pandas version)
