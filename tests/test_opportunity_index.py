"""Offline tests for the Opportunity Index using a tiny fake set of metros."""
import numpy as np
import pandas as pd
import pytest

from analysis import opportunity_index as oi


def fake_features():
    """Four metros with clear, known orderings."""
    df = pd.DataFrame({
        "cbsa_code": ["A", "B", "C", "D"],
        "cbsa_title": ["Cheap & Growing", "Pricey & Growing", "Cheap & Stalling", "Pricey & Stalling"],
        "state": ["TX", "CA", "MI", "MA"],
        "population": [2_000_000, 3_000_000, 400_000, 100_000],
        "median_household_income": [80_000, 100_000, 60_000, 70_000],
        "home_value": [300_000, 900_000, 200_000, 500_000],
        "rent": [1_300, 3_000, 1_000, 2_200],
        "mortgage_payment": [1_600, 4_800, 1_100, 2_700],
        "rent_to_income": [0.195, 0.36, 0.20, 0.377],
        "mortgage_to_income": [0.24, 0.576, 0.22, 0.463],
        "home_value_3y_ago": [290_000, 800_000, 200_000, 480_000],
        "rent_3y_ago": [1_250, 2_700, 1_000, 2_000],
        "jobs_now": [1_100, 1_080, 1_000, 990],
        "jobs_3y_ago": [1_000, 1_000, 1_000, 1_000],
        "wage_now": [1_300, 1_600, 1_050, 1_100],
        "wage_3y_ago": [1_100, 1_300, 1_000, 1_100],
        "net_migration_per_1k": [8.0, -2.0, 0.5, -3.0],
        "permits_per_1k": [9.0, 3.0, 1.5, 1.0],
    })
    return oi.add_derived(df)


def test_cagr_handles_missing_and_zero():
    out = oi.cagr(pd.Series([121.0, 50.0, np.nan]), pd.Series([100.0, 0.0, 100.0]), years=2)
    assert out.iloc[0] == pytest.approx(0.10)
    assert np.isnan(out.iloc[1]) and np.isnan(out.iloc[2])


def test_percentile_direction():
    s = pd.Series([0.2, 0.4, 0.3])
    assert oi.percentile(s, -1).idxmax() == 0   # lowest cost ratio is best
    assert oi.percentile(s, +1).idxmax() == 1   # highest growth is best


def test_scoring_orders_metros_sensibly():
    scored = oi.score(fake_features()).set_index("cbsa_code")
    assert scored["rank"].idxmin() == "A"        # cheap and growing wins
    assert scored["rank"].idxmax() == "D"        # pricey and stalling loses
    assert scored["opportunity_index"].between(0, 100).all()


def test_missing_indicator_uses_rest_of_pillar_but_missing_pillar_is_unranked():
    df = fake_features()
    df.loc[df["cbsa_code"] == "C", "rent_to_income"] = np.nan          # one indicator gone
    df.loc[df["cbsa_code"] == "D", ["job_growth_3y", "paycheck_vs_prices_3y"]] = np.nan  # whole pillar gone
    scored = oi.score(df).set_index("cbsa_code")
    assert not np.isnan(scored.loc["C", "opportunity_index"])
    assert np.isnan(scored.loc["D", "opportunity_index"])


def test_custom_weights_change_the_winner():
    df = fake_features()
    growth_only = oi.score(df, weights={"affordability": 0, "momentum": 1, "demand_supply": 0})
    afford_only = oi.score(df, weights={"affordability": 1, "momentum": 0, "demand_supply": 0})
    g = growth_only.set_index("cbsa_code")["opportunity_index"]
    a = afford_only.set_index("cbsa_code")["opportunity_index"]
    assert g["B"] > g["C"] and a["C"] > a["B"]


def test_rank_stability_is_reproducible_and_bounded():
    df = fake_features()
    s1, s2 = oi.rank_stability(df, n=200, top_n=1), oi.rank_stability(df, n=200, top_n=1)
    pd.testing.assert_frame_equal(s1, s2)                        # fixed seed
    assert (s1["rank_p05"] <= s1["rank_median"]).all() and (s1["rank_median"] <= s1["rank_p95"]).all()
    assert s1.set_index("cbsa_code").loc["A", "share_top1"] > 0.5


def test_leave_one_out_covers_every_indicator():
    loo = oi.leave_one_out(fake_features(), top_n=2)
    every = {i for cfg in oi.PILLARS.values() for i in cfg["indicators"]}
    assert set(loo["dropped"]) == every
    assert loo["spearman_vs_baseline"].between(-1, 1).all()


def test_archetypes_and_size_bands():
    scored, _ = oi.build(fake_features())
    arche = scored.set_index("cbsa_code")["archetype"]
    assert arche["A"] == "Rising & Affordable"
    assert arche["D"] == "Squeezed"
    assert oi.size_band(2_000_000) == "Large (1M+)"
    assert oi.size_band(400_000) == "Mid-size (250K-1M)"
    assert oi.size_band(100_000) == "Small (under 250K)"


def test_not_ranked_reasons():
    row = pd.Series({"state": "CT", "home_value": 1.0})
    assert "Connecticut" in oi.not_ranked_reason(row)
    assert "Puerto Rico" in oi.not_ranked_reason(pd.Series({"state": "PR", "home_value": np.nan}))
