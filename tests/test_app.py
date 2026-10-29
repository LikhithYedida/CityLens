"""Runs the Streamlit app headlessly against small fake data and clicks through every tab."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
SIZES = ["Large (1M+)", "Mid-size (250K-1M)", "Small (under 250K)"]


def fake_scorecard(n=40, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "cbsa_code": [f"{i:05d}" for i in range(n)],
        "metro": [f"Metro{i}-Twin{i}, {'TX' if i % 2 else 'OH'}" for i in range(n)],
        "state": ["TX" if i % 2 else "OH" for i in range(n)],
        "region": ["South and West" if i % 2 else "Midwest" for i in range(n)],
        "size_band": [SIZES[0] if i < 10 else SIZES[1] if i < 30 else SIZES[2] for i in range(n)],
        "population": np.linspace(3e6, 1.5e5, n),
        "lat": 38 + rng.normal(0, 0.4, n), "lon": -90 + rng.normal(0, 0.4, n),   # close together: neighbors exist
        "income": rng.uniform(55_000, 110_000, n), "rent": rng.uniform(900, 2_800, n),
        "home_value": rng.uniform(180_000, 800_000, n), "mortgage_rate": 6.3,
        "rent_to_income": rng.uniform(0.15, 0.4, n), "mortgage_to_income": rng.uniform(0.15, 0.6, n),
        "job_growth_3y": rng.normal(0.01, 0.01, n), "rent_growth_3y": rng.normal(0.03, 0.01, n),
        "net_migration_per_1k": rng.normal(1, 3, n),
        "opportunity_rank": np.arange(1, n + 1, dtype=float), "opportunity_score": np.linspace(90, 10, n),
        "rank_p05": np.arange(1, n + 1, dtype=float), "rank_p95": np.arange(1, n + 1, dtype=float) + 10,
        "share_top25": rng.uniform(0, 1, n),
        "affordability_score": rng.uniform(0, 100, n), "momentum_score": rng.uniform(0, 100, n),
        "demand_supply_score": rng.uniform(0, 100, n),
        "metro_type": rng.choice(["Rising & Affordable", "Squeezed"], n),
        "rising_signal": rng.normal(0, 1, n),
        "price_outlook": rng.choice(["Rising City", "Cooling Boomtown", None], n),
        "rent_forecast": rng.normal(0.03, 0.02, n), "rent_forecast_low": -0.01, "rent_forecast_high": 0.07,
        "home_forecast": rng.normal(0.02, 0.02, n), "home_forecast_low": -0.03, "home_forecast_high": 0.08,
        "growth_3y": rng.normal(0.05, 0.04, n), "ripple_pressure_pp": rng.normal(0, 0.5, n),
        "next_ring_out": rng.random(n) < 0.1, "status": rng.choice(["Rising City", "Next Ring Out", ""], n),
    })


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    sc = fake_scorecard()
    sc.to_parquet(tmp_path / "metro_scorecard.parquet", index=False)
    dates = pd.date_range("2015-01-01", "2026-09-01", freq="MS")
    hist = pd.DataFrame([{"cbsa_code": c, "date": d, "rent": 1000 * (1 + 0.003 * i), "home_value": 2e5 * (1 + 0.004 * i),
                          "employment": 1e5} for c in sc["cbsa_code"] for i, d in enumerate(dates)])
    hist.to_parquet(tmp_path / "metro_history.parquet", index=False)
    summary = {"housing_as_of": "2026-09", "n_rising": 24, "rising_midwest_northeast": 19, "n_cooling": 56,
               "cooling_south_west": 55, "rent_forecast_median": 0.031,
               "opportunity_robust": [{"metro": "A", "share_top25": 0.99}] * 5,
               "forecast": {"rent": {"model": 3.1, "base": 3.5, "calm_model": 1.8, "calm_base": 2.7,
                                     "calm_coverage": 0.94}},
               "rising": {"avg_spread_pp": 4.8, "worst_spread_pp": 3.7},
               "ripple": {"effect_0_75": 0.45, "t_0_75": 3.8, "morans_i": 0.69},
               "policy": {"gap_latest": -0.16, "p_value": 0.017, "n_donors": 180, "suburbs_gap": -0.08,
                          "reform_effect_low_pp": 8.4, "reform_effect_high_pp": 10.2},
               "freshness": {"zillow_metro_home_value": "2026-09"}}
    (tmp_path / "dashboard_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    square = {"type": "Polygon", "coordinates": [[[-95, 36], [-85, 36], [-85, 42], [-95, 42], [-95, 36]]]}
    (tmp_path / "us_states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"state": "XX"}, "geometry": square}]}), encoding="utf-8")
    monkeypatch.setenv("CITYLENS_DATA_DIR", str(tmp_path))
    return tmp_path


def run_app():
    return AppTest.from_file(APP, default_timeout=90).run()


def test_app_renders_every_tab(data_dir):
    at = run_app()
    assert not at.exception
    assert any("cl-mark'></span>CityLens" in m.value for m in at.markdown)
    assert [t.label for t in at.tabs] == ["Overview", "Where to live", "Where to build", "Metro profile", "Methods"]
    cards = " ".join(m.value for m in at.markdown)
    assert cards.count("class='cl-kpi'") >= 16   # header, budget and profile cards
    assert len(at.dataframe) >= 4        # overview, live, build, neighbors


def test_household_tool_responds_to_inputs(data_dir):
    at = run_app()
    count = lambda: [m.value for m in at.markdown if "metros**" in m.value][0]
    before = count()
    at.number_input[0].set_value(40_000).run()
    assert not at.exception and count() != before
    at.radio[0].set_value("Buy").run()
    assert not at.exception and "mortgage payment" in count()


def test_profile_uses_plain_city_names_and_builder_handles_zero_weights(data_dir):
    at = run_app()
    picker = [s for s in at.selectbox if s.label == "Metro"][0]
    assert all("-" not in o for o in picker.options)            # 'Metro5, TX', not 'Metro5-Twin5, TX'
    picker.set_value("Metro5, TX").run()
    assert not at.exception
    assert any(m.value.startswith("Metro5, TX ranks") for m in at.markdown)
    for s in at.slider:
        if s.label in {"Home value outlook", "Rising Signal", "Neighbors rising", "Job growth", "Buyer affordability"}:
            s.set_value(0)
    at.run()
    assert not at.exception


def test_app_runs_without_optional_files(data_dir):
    (data_dir / "metro_history.parquet").unlink()
    (data_dir / "dashboard_summary.json").unlink()
    (data_dir / "us_states.geojson").unlink()
    at = run_app()
    assert not at.exception


def test_hosted_app_runs_from_committed_data(monkeypatch):
    """The hosted app reads app/data. Skipped until the scorecard step has published it."""
    committed = Path(APP).parent / "data"
    if not (committed / "metro_scorecard.parquet").exists():
        pytest.skip("app/data not published yet")
    monkeypatch.setenv("CITYLENS_DATA_DIR", str(committed))
    at = run_app()
    assert not at.exception
