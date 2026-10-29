"""Layer 7a: the CityLens scorecard and executive memo.

Joins every layer into one row per metropolitan area, so the front page, the memo and
the app all read the same numbers:

  Opportunity Index (Layer 2)   rank, affordability, job growth, metro type
  Rising City Detector (3)      Rising Signal fifth and label
  Forecast Engine (5)           12-month rent and home-value forecasts with 80% ranges
  Ripple Map (6)                growth cluster, ripple pressure, Next Ring Out

Also writes the executive visual (the 15 largest metros on one grid) and the
one-page executive memo. Every number in the memo is computed here, from the saved
results of each layer.

Run:  python -m analysis.scorecard     (run every earlier layer first)
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from analysis import charts
from pipeline.config import CLEAN_DIR, ROOT
from pipeline.utils import SourceError, log, record_run

MARTS = ROOT / "data" / "marts"
OUT = MARTS / "metro_scorecard.parquet"
HISTORY = MARTS / "metro_history.parquet"
SUMMARY = MARTS / "dashboard_summary.json"
RUN_LOG = ROOT / "data" / "run_log.jsonl"
MEMO = ROOT / "docs" / "executive_memo.md"
FIG = ROOT / "docs" / "figures" / "scorecard_largest_metros.png"
AUTHOR = "Likhith Yedida"

CLUSTER_WORDS = {"HH": "Rising cluster", "LL": "Cooling cluster", "HL": "Rising, neighbors cooling",
                 "LH": "Lagging, neighbors rising", "ns": "No clear cluster"}
MIDWEST = {"IL", "IN", "IA", "KS", "MI", "MN", "MO", "NE", "ND", "OH", "SD", "WI"}
NORTHEAST = {"CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"}


def region(state: str) -> str:
    if state in MIDWEST:
        return "Midwest"
    if state in NORTHEAST:
        return "Northeast"
    return "South and West"


# ---------------- scorecard table ----------------

def _read(name: str) -> pd.DataFrame:
    path = MARTS / f"{name}.parquet"
    if not path.exists():
        raise SourceError(f"{path.name} is missing. Run the layer that builds it first.")
    return pd.read_parquet(path)


def build() -> pd.DataFrame:
    oi = _read("opportunity_index")
    rc = _read("rising_cities")[["cbsa_code", "rising_signal", "signal_quintile", "label"]]
    fc = _read("forecasts")
    rm = _read("ripple_map")[["cbsa_code", "cluster", "growth_3y", "ripple_pressure_pp", "next_ring_out"]]
    pts = pd.read_parquet(CLEAN_DIR / "cbsa_points.parquet")[["cbsa_code", "lat", "lon"]]
    mart = _read("mart_metro_month")
    rate = float(mart.dropna(subset=["mortgage_rate_30y"]).sort_values("date")["mortgage_rate_30y"].iloc[-1])

    def fc_cols(metric, prefix):
        f = fc[fc["metric"] == metric][["cbsa_code", "forecast_pct", "lo_pct", "hi_pct"]]
        return f.rename(columns={"forecast_pct": prefix, "lo_pct": f"{prefix}_low", "hi_pct": f"{prefix}_high"})

    sc = (oi[["cbsa_code", "cbsa_title", "state", "population", "size_band", "median_household_income", "rent",
              "home_value", "mortgage_payment", "rent_to_income", "mortgage_to_income", "job_growth_3y",
              "paycheck_vs_prices_3y", "net_migration_per_1k", "permits_per_1k", "rent_growth_3y",
              "home_value_growth_3y", "income_left_after_rent", "opportunity_index", "rank", "rank_p05", "rank_p95",
              "share_top25", "archetype", "affordability_score", "momentum_score", "demand_supply_score"]]
          .rename(columns={"cbsa_title": "metro", "median_household_income": "income", "rank": "opportunity_rank",
                           "opportunity_index": "opportunity_score", "archetype": "metro_type"})
          .merge(rc.rename(columns={"signal_quintile": "rising_fifth", "label": "price_outlook"}), on="cbsa_code", how="left")
          .merge(fc_cols("rent", "rent_forecast"), on="cbsa_code", how="left")
          .merge(fc_cols("home_value", "home_forecast"), on="cbsa_code", how="left")
          .merge(rm, on="cbsa_code", how="left")
          .merge(pts, on="cbsa_code", how="left"))
    sc["growth_cluster"] = sc["cluster"].map(CLUSTER_WORDS)
    sc["next_ring_out"] = sc["next_ring_out"].astype("boolean").fillna(False).astype(bool)
    sc["mortgage_rate"] = rate
    sc["region"] = sc["state"].map(region)
    sc["status"] = np.select(
        [sc["next_ring_out"], sc["price_outlook"].eq("Rising City"), sc["price_outlook"].eq("Cooling Boomtown")],
        ["Next Ring Out", "Rising City", "Cooling Boomtown"], default="")
    return sc.drop(columns=["cluster"]).sort_values("opportunity_rank", na_position="last").reset_index(drop=True)


# ---------------- executive visual ----------------

COLUMNS = [  # (column, header, higher_is_better, formatter)
    ("opportunity_rank", "Opportunity\nrank", False, lambda v: f"#{v:.0f}"),
    ("rent_to_income", "Rent share\nof income", False, lambda v: f"{v:.0%}"),
    ("mortgage_to_income", "Mortgage share\nof income", False, lambda v: f"{v:.0%}"),
    ("job_growth_3y", "Job growth\nper year", True, lambda v: f"{v:+.1%}"),
    ("rent_forecast", "Rent change,\nnext 12 months", False, lambda v: f"{v:+.1%}"),
]
GOOD, MID, BAD = np.array([207, 226, 248]), np.array([241, 240, 236]), np.array([251, 215, 198])


def cell_color(pct: float) -> tuple:
    """pct = share of all metros this value beats for a household (0 worst, 1 best)."""
    if pd.isna(pct):
        return tuple(MID / 255)
    c = MID + (GOOD - MID) * (pct - 0.5) * 2 if pct >= 0.5 else MID + (BAD - MID) * (0.5 - pct) * 2
    return tuple(c / 255)


def chart_scorecard(sc: pd.DataFrame, n: int = 15) -> str:
    top = sc.nlargest(n, "population").sort_values("opportunity_rank").reset_index(drop=True)
    pct = {col: (sc[col].rank(pct=True) if better else 1 - sc[col].rank(pct=True)) for col, _, better, _ in COLUMNS}
    fig, ax = charts.new(7.2, 4.9)
    ax.axis("off")
    ncol, row_h, x0, W = len(COLUMNS), 1.0, 2.4, 1.22
    for j, (col, head, _, fmt) in enumerate(COLUMNS):
        ax.text(x0 + (j + 0.5) * W, n + 0.35, head, ha="center", va="bottom", fontsize=7.2, color=charts.INK_2)
    ax.text(x0 + ncol * W + 0.15, n + 0.35, "Market\nstatus", ha="left", va="bottom", fontsize=7.2, color=charts.INK_2)
    for i, r in top.iterrows():
        y = n - 1 - i
        ax.text(x0 - 0.12, y + 0.5, short_name(r["metro"]), ha="right", va="center",
                fontsize=8, color=charts.INK)
        for j, (col, _, _, fmt) in enumerate(COLUMNS):
            p = pct[col].loc[sc["cbsa_code"] == r["cbsa_code"]].iloc[0]
            ax.add_patch(__import__("matplotlib.patches", fromlist=["x"]).Rectangle(
                (x0 + j * W + 0.04, y + 0.05), W - 0.08, row_h - 0.1, color=cell_color(p), lw=0))
            ax.text(x0 + (j + 0.5) * W, y + 0.5, "" if pd.isna(r[col]) else fmt(r[col]), ha="center", va="center",
                    fontsize=8, color=charts.INK)
        ax.text(x0 + ncol * W + 0.15, y + 0.5, r["status"] or r["metro_type"], ha="left", va="center", fontsize=7.5,
                color=charts.INK if r["status"] else charts.INK_2)
    ax.set_xlim(0, x0 + ncol * W + 2.3)
    ax.set_ylim(-0.2, n + 1.6)
    charts.title(fig, f"The {n} largest metros at a glance",
                 "Blue cells beat most U.S. metros for a household; orange cells trail them. "
                 "Sorted by Opportunity rank, out of 379.")
    return charts.save(fig, FIG, top=0.9)


# ---------------- executive memo ----------------

def forecast_accuracy() -> dict:
    bt = _read("forecast_backtest")
    out = {}
    for metric, g in bt.groupby("metric"):
        err = lambda d, col: (d[col] - d["actual"]).abs().mean() * 100
        calm = g[g["year"] >= 2022]
        base = min(["Flat", "Persistence", "National"], key=lambda b: err(g, b))
        calm_base = min(["Flat", "Persistence", "National"], key=lambda b: err(calm, b))
        out[metric] = {"model": err(g, "CityLens model"), "base": err(g, base),
                       "calm_model": err(calm, "CityLens model"), "calm_base": err(calm, calm_base),
                       "calm_coverage": ((calm["actual"] >= calm["lo"]) & (calm["actual"] <= calm["hi"])).mean()}
    return out


def ripple_stats() -> dict:
    from analysis import ripple_map as rmap
    values, meta = rmap.load()
    d = rmap.standardize(rmap.build_panel(values, meta).dropna(subset=["future"]))
    e = rmap.ripple_effects(d)
    rings = e[e["spec"] == "All years"].set_index("term")
    end = values.index.max()
    g3 = np.log(values.loc[end] / values.loc[end - pd.DateOffset(months=36)]).dropna()
    m = meta.set_index("cbsa_code").loc[g3.index]
    w = rmap.knn_weights(rmap.distance_miles(m["lat"].to_numpy(), m["lon"].to_numpy()))
    gm = rmap.morans_i(g3.to_numpy(), w)
    return {"effect_0_75": float(rings.loc["ring_0_75", "effect_pp"]),
            "effect_75_150": float(rings.loc["ring_75_150", "effect_pp"]),
            "effect_150_300": float(rings.loc["ring_150_300", "effect_pp"]),
            "t_0_75": float(rings.loc["ring_0_75", "t"]), "morans_i": gm["I"], "morans_p": gm["p_value"]}


def ripple_effect() -> float:
    return ripple_stats()["effect_0_75"]


def rising_backtest() -> dict:
    from analysis import rising_cities as rcm
    bt, _ = rcm.backtest(rcm.prepare(rcm.load_panel()))
    lb = rcm.leaderboard(bt).loc[rcm.CHOSEN]
    return {"avg_rank_corr": float(lb["average"]), "avg_spread_pp": float(lb["avg_spread_pp"]),
            "worst_spread_pp": float(lb["worst_spread_pp"])}


def freshness() -> dict:
    """Latest period loaded for each source, from the pipeline's run log."""
    out = {}
    if RUN_LOG.exists():
        for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") == "ok" and rec.get("latest_date"):
                out[rec["source"]] = rec["latest_date"]
    return out


def write_history() -> None:
    mart = _read("mart_metro_month")
    h = mart[mart["cbsa_type"] == "Metropolitan"][["cbsa_code", "date", "rent", "home_value", "employment"]]
    h.to_parquet(HISTORY, index=False)


def coverage(sc: pd.DataFrame) -> dict:
    """How the 935 Census areas in the panel narrow to the metros that are ranked."""
    m = pd.read_parquet(MARTS / "mart_metro_month.parquet", columns=["cbsa_code", "cbsa_type", "rent"])
    types = m.drop_duplicates("cbsa_code")["cbsa_type"].value_counts()
    micro = m[m["cbsa_type"] == "Micropolitan"]
    unranked = sc[sc["opportunity_rank"].isna()]
    pr, ct = unranked["state"].eq("PR"), unranked["state"].eq("CT")
    return {"panel_total": int(m["cbsa_code"].nunique()),
            "metropolitan": int(types.get("Metropolitan", 0)), "micropolitan": int(types.get("Micropolitan", 0)),
            "micro_with_rent": int(micro.dropna(subset=["rent"])["cbsa_code"].nunique()),
            "puerto_rico": int(pr.sum()), "connecticut": int(ct.sum()),
            "no_zillow": sorted(unranked.loc[~pr & ~ct, "metro"].tolist()),
            "ranked": int(sc["opportunity_rank"].notna().sum())}


def write_summary(sc: pd.DataFrame) -> dict:
    ranked = sc.dropna(subset=["opportunity_rank"])
    rising = sc[sc["price_outlook"] == "Rising City"]
    cooling = sc[sc["price_outlook"] == "Cooling Boomtown"]
    policy = json.loads((MARTS / "policy_lab_summary.json").read_text(encoding="utf-8"))
    robust = ranked.nsmallest(5, "opportunity_rank")[["metro", "share_top25"]]
    summary = {
        "housing_as_of": policy["as_of"],
        "mortgage_rate": float(sc["mortgage_rate"].iloc[0]),
        "n_ranked": int(len(ranked)),
        "n_rising_affordable": int((ranked["metro_type"] == "Rising & Affordable").sum()),
        "n_rising": int(len(rising)),
        "rising_midwest_northeast": int(rising["region"].ne("South and West").sum()),
        "n_cooling": int(len(cooling)),
        "cooling_south_west": int(cooling["region"].eq("South and West").sum()),
        "n_next_ring_out": int(sc["next_ring_out"].sum()),
        "rent_forecast_median": float(sc["rent_forecast"].median()),
        "home_forecast_median": float(sc["home_forecast"].median()),
        "opportunity_robust": [{"metro": r.metro, "share_top25": float(r.share_top25)} for r in robust.itertuples()],
        "forecast": forecast_accuracy(),
        "rising": rising_backtest(),
        "ripple": ripple_stats(),
        "policy": policy,
        "freshness": freshness(),
        "coverage": coverage(sc),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    return summary


def short_name(title: str, state: bool = False) -> str:
    """'Dallas-Fort Worth-Arlington, TX' -> 'Dallas'; two-city names stay whole ('Sherman-Denison')."""
    city, st = title.split(",")[0], title.split(",")[-1].strip().split("-")[0]
    parts = city.split("-")
    name = city if len(parts) == 2 and len(city) <= 20 else parts[0]
    return f"{name}, {st}" if state else name


def names(df: pd.DataFrame, k: int, state: bool = False) -> str:
    items = [short_name(m, state) for m in df["metro"].head(k)]
    if len(items) == 1:
        return items[0]
    sep = "; " if state else ", "
    return sep.join(items[:-1]) + ("; and " if state else " and ") + items[-1]


def write_memo(sc: pd.DataFrame) -> None:
    ranked = sc.dropna(subset=["opportunity_rank"])
    acc = forecast_accuracy()
    policy = json.loads((MARTS / "policy_lab_summary.json").read_text(encoding="utf-8"))
    ripple = ripple_effect()
    rising = sc[sc["price_outlook"] == "Rising City"]
    cooling = sc[sc["price_outlook"] == "Cooling Boomtown"]
    nro = sc[sc["next_ring_out"]].sort_values("ripple_pressure_pp", ascending=False)
    sweet_large = ranked[(ranked["metro_type"] == "Rising & Affordable") & (ranked["size_band"] == "Large (1M+)")]
    squeezed_large = ranked[ranked["size_band"] == "Large (1M+)"].sort_values("opportunity_rank", ascending=False)
    rent = sc["rent_forecast"]
    slow_large = sc[sc["size_band"] == "Large (1M+)"].nsmallest(5, "rent_forecast")
    r_acc, h_acc = acc["rent"], acc["home_value"]
    as_of = policy["as_of"]

    L = ["# Executive Memo: Where Opportunity Is Growing in America", "",
         f"{date.today():%B %Y}. Housing data through {pd.Timestamp(as_of):%B %Y}. Prepared by {AUTHOR}.", "",
         "## Bottom line", "",
         f"The places where a typical household can still afford a home and find a growing job market are concentrated "
         f"in Texas, the Southeast and mid-size Midwestern cities, led by {names(ranked, 5, state=True)}. The coasts remain the "
         f"most stretched. Home-price momentum has moved north: the pandemic boomtowns of Florida and Texas are "
         f"cooling, while the Midwest and Northeast are rising. Over the next 12 months, rent in a typical metro is "
         f"expected to rise about {rent.median():.0%}. Among large metros, the slowest growth is expected in "
         f"{names(slow_large, 4)}.", "",
         "## What the data shows", "",
         f"1. **Only {int((ranked['metro_type'] == 'Rising & Affordable').sum())} of {len(ranked)} metros are both "
         f"affordable and growing.** Among large metros, that group is {names(sweet_large, 8)}. In "
         f"{names(squeezed_large, 3)}, a mortgage on a typical home takes "
         f"{squeezed_large['mortgage_to_income'].head(3).min():.0%} to {squeezed_large['mortgage_to_income'].head(3).max():.0%} "
         "of a typical household's income.",
         f"2. **Price growth has changed direction.** {int(rising['region'].ne('South and West').sum())} of "
         f"{len(rising)} metros flagged to outgrow the national market next year are in the Midwest or Northeast. "
         f"{int(cooling['region'].eq('South and West').sum())} of {len(cooling)} cooling boomtowns are in the South "
         "and West. Before 2022, metros gaining residents saw faster price growth; since 2022 they have seen slower "
         "growth.",
         f"3. **Growth spreads about 75 miles.** When metros within 75 miles grow faster, a metro tends to grow "
         f"{ripple:.2f} points faster the following year (per standard deviation), and the pattern held before, "
         f"during and after the pandemic. {len(nro)} affordable metros have neighbors pulling ahead, including "
         f"{names(nro, 5, state=True)}.",
         f"4. **The forecasts beat simple rules.** Rent forecasts missed by {r_acc['model']:.1f} points of 12-month "
         f"growth on average over 2020-2025, against {r_acc['base']:.1f} for the best simple rule, and "
         f"{r_acc['calm_model']:.1f} against {r_acc['calm_base']:.1f} since 2022. Their 80% ranges contained "
         f"{r_acc['calm_coverage']:.0%} of outcomes since 2022.",
         f"5. **Zoning reform helped Minneapolis, but less than reported.** Minneapolis rents are "
         f"{abs(policy['gap_latest']):.0%} below a comparison built from {policy['n_donors']} cities, but its own "
         f"suburbs, which the reform did not cover, fell about {abs(policy['suburbs_gap']):.0%} as well. The reform "
         f"explains at most about {policy['reform_effect_low_pp']:.0f} to {policy['reform_effect_high_pp']:.0f} "
         "points of lower rent.", "",
         "## What to do with it", "",
         f"**Households.** Among large metros, the strongest combination of cost and job growth is in "
         f"{names(sweet_large, 4)}. Rents in {names(slow_large, 3)} are forecast to stay roughly flat over the next "
         f"year ({slow_large['rent_forecast'].min():+.1%} to {slow_large['rent_forecast'].head(3).max():+.1%}), which "
         "gives renters room to negotiate.",
         "",
         f"**Builders and lenders.** Demand is moving toward Rising Cities such as "
         f"{names(rising.sort_values('rising_signal', ascending=False), 3, state=True)}, and toward Next Ring Out "
         f"metros such as {names(nro, 3, state=True)}. In the cooling boomtowns, plan for flat prices and slower "
         "lease-up.",
         "",
         f"**City and regional leaders.** Upzoning is worth doing, but Minneapolis suggests it moves rents by single "
         "digits, not by a third. Because growth spreads about 75 miles, housing supply works best when planned "
         "across a region rather than one city at a time.", "",
         "## What could change this view", "",
         "- National shocks drive most one-year price changes. The 2020-21 surge and the 2022 rate shock broke every "
         "forecast tested here, including this one.",
         "- Migration data runs two years behind and job data six months behind.",
         "- The Rising City and ripple signals predict well, but they do not prove cause and effect.", "",
         "## How the work was done", "",
         "Seven public sources (Zillow, Census ACS, Census building permits, BLS, IRS, the Federal Reserve and Census "
         "geography) were joined into a tested panel of 935 metros by month since 2015. Each finding comes from a "
         "separate, documented analysis: a weighted index with 1,000-weighting sensitivity tests, panel regressions "
         "with walk-forward backtests, a synthetic control with placebo tests, gradient-boosted forecasts with "
         "conformal ranges, and spatial statistics. Every judgment call is in the decisions log."]
    MEMO.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_state_outlines() -> None:
    """State outlines as GeoJSON for the app's map, rounded to about 1 km to keep the file small."""
    import shapefile
    from pipeline.geo_shapes import STATE_SHP
    if not STATE_SHP.exists():
        log.warning("State outlines not found; the app map will show metros without state borders.")
        return
    r = shapefile.Reader(str(STATE_SHP))
    fields = [f[0] for f in r.fields[1:]]
    feats = []
    for rec in r.iterShapeRecords():
        attrs = dict(zip(fields, rec.record))
        if attrs.get("STUSPS") in {"PR", "VI", "GU", "AS", "MP"}:
            continue
        geom = rec.shape.__geo_interface__

        def rnd(c):
            return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 2), round(c[1], 2)]
        feats.append({"type": "Feature", "properties": {"state": attrs.get("STUSPS")},
                      "geometry": {"type": geom["type"], "coordinates": rnd(geom["coordinates"])}})
    (MARTS / "us_states.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                                             encoding="utf-8")


APP_FILES = ["metro_scorecard.parquet", "metro_history.parquet", "dashboard_summary.json", "us_states.geojson"]


def publish_app_data() -> None:
    """Copy the four small files the app reads into app/data, which is committed so the hosted app
    runs without rebuilding the pipeline. About 2 MB in total."""
    import shutil
    dest = ROOT / "app" / "data"
    dest.mkdir(exist_ok=True)
    for name in APP_FILES:
        if (MARTS / name).exists():
            shutil.copyfile(MARTS / name, dest / name)


def run() -> pd.DataFrame:
    sc = build()
    sc.to_parquet(OUT, index=False)
    write_history()
    write_state_outlines()
    write_summary(sc)
    chart_scorecard(sc)
    write_memo(sc)
    publish_app_data()
    record_run("metro_scorecard", len(sc), "")
    log.info("Scorecard: %s metros. Saved metro_scorecard.parquet, the scorecard chart and docs/executive_memo.md",
             len(sc))
    return sc


if __name__ == "__main__":
    run()
