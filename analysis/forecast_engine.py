"""Layer 5: the Forecast Engine. Where will rents and home values be in 12 months?

The forecast has two parts, because they behave differently:

  national trend   the latest 12-month change across all metros (one number per month,
                   moved by shocks no local data can see, like the 2021 rent surge)
  metro adjustment how much each metro will run above or below that trend, learned by one
                   gradient-boosted model across every metropolitan area from what was
                   knowable at the time: each metro's recent price trends, jobs, incomes,
                   mortgage rates, building permits and migration (each lagged to match
                   when it's actually published)

A direct model (predicting total growth in one step from the same inputs) fails in a
different kind of year: the two-part model misses turning points like the 2022 rate
shock, the direct model missed the 2021 rent surge. The CityLens forecast is the average
of the two, the standard way to hedge regime-specific blind spots. All three are
reported in the backtest.

Every forecast is judged the honest way, with a rolling-origin backtest: for each year
2020-2025 the model is trained only on outcomes known by the start of that year, then
forecasts every metro for every month of the year. It must beat three simple baselines:

  Flat          prices don't change
  Persistence   the next 12 months repeat the last 12
  National      every metro follows the latest national trend

Each forecast comes with an 80% range from conformal prediction: the range is set from
the model's own recent errors (scaled up for metros whose prices swing more), and the
backtest checks that about 80% of real outcomes actually land inside it.

Run:  python -m analysis.forecast_engine     (run pipeline.build_panel first)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis import charts
from pipeline.config import ROOT
from pipeline.utils import SourceError, log, record_run

MART = ROOT / "data" / "marts" / "mart_metro_month.parquet"
OUT = ROOT / "data" / "marts" / "forecasts.parquet"
BACKTEST_OUT = ROOT / "data" / "marts" / "forecast_backtest.parquet"
REPORT = ROOT / "docs" / "forecast_report.md"
FIG_DIR = ROOT / "docs" / "figures"

METRICS = {"rent": "Rent", "home_value": "Home value"}
HORIZON = 12
TEST_YEARS = range(2020, 2026)
COVERAGE = 0.80
MODEL = "CityLens model"
TWO_PART = "Two-part model"
DIRECT = "Direct model"
BASELINES = ["Flat", "Persistence", "National"]
DESIGNS = [MODEL, TWO_PART, DIRECT] + BASELINES
CAL_MONTHS = 24
SHOCK_YEARS = [2020, 2021]
LARGE_METROS = 12

# publication lags in months: jobs (BLS QCEW ~6), income (ACS ~12), permits (~18), migration (IRS ~24)
LAGS = {"jobs": 6, "income": 12, "permits": 18, "migration": 24}

PANEL_SQL = """
SELECT cbsa_code, cbsa_title, date, rent, home_value, employment, median_household_income,
       population, mortgage_rate_30y, permits_per_1k, net_migration_rate_per_1k
FROM read_parquet('{mart}')
WHERE cbsa_type = 'Metropolitan'
ORDER BY cbsa_code, date
"""


# ---------------- features ----------------

def load(mart_path=MART) -> pd.DataFrame:
    import duckdb
    if not mart_path.exists():
        raise SourceError("Run `python -m pipeline.build_panel` first.")
    return duckdb.connect().execute(PANEL_SQL.format(mart=mart_path.as_posix())).df()


def build_features(raw: pd.DataFrame, metric: str) -> pd.DataFrame:
    """One row per metro-month: features known at that month, and the 12-month-ahead target."""
    other = "home_value" if metric == "rent" else "rent"
    df = raw.sort_values(["cbsa_code", "date"]).copy()
    g = df.groupby("cbsa_code", group_keys=False)
    lv, lo = np.log(df[metric]), np.log(df[other])

    def change(series, months):
        return series - series.groupby(df["cbsa_code"]).shift(months)

    out = df[["cbsa_code", "cbsa_title", "date"]].copy()
    out["level"] = df[metric]
    out["target"] = lv.groupby(df["cbsa_code"]).shift(-HORIZON) - lv
    # metro-vs-national part of the outcome: what the metro adjustment model learns
    out["target_rel"] = out["target"] - out.groupby(out["date"])["target"].transform("mean")
    for m in (1, 3, 6, 12, 24):
        out[f"growth_{m}m"] = change(lv, m)
    out["other_growth_12m"] = change(lo, 12)
    out["volatility"] = change(lv, 1).groupby(df["cbsa_code"]).transform(
        lambda s: s.rolling(24, min_periods=12).std()) * np.sqrt(12)
    out["national_growth_12m"] = out.groupby("date")["growth_12m"].transform("mean")
    out["vs_national_12m"] = out["growth_12m"] - out["national_growth_12m"]
    emp = np.log(df["employment"])
    out["job_growth_12m"] = (emp.groupby(df["cbsa_code"]).shift(LAGS["jobs"])
                             - emp.groupby(df["cbsa_code"]).shift(LAGS["jobs"] + 12))
    income = df.groupby("cbsa_code")["median_household_income"].shift(LAGS["income"])
    out["price_to_income"] = np.log(df["home_value"] / income)
    out["rent_to_income"] = np.log(df["rent"] * 12 / income)
    out["mortgage_rate"] = df["mortgage_rate_30y"]
    out["mortgage_rate_change_12m"] = df["mortgage_rate_30y"] - g["mortgage_rate_30y"].shift(12)
    out["permits_per_1k"] = g["permits_per_1k"].shift(LAGS["permits"])
    out["migration_per_1k"] = g["net_migration_rate_per_1k"].shift(LAGS["migration"])
    out["log_population"] = np.log(df["population"])
    return out[out["growth_12m"].notna()].reset_index(drop=True)


FEATURES = ["growth_1m", "growth_3m", "growth_6m", "growth_12m", "growth_24m", "other_growth_12m",
            "volatility", "national_growth_12m", "vs_national_12m", "job_growth_12m", "price_to_income",
            "rent_to_income", "mortgage_rate", "mortgage_rate_change_12m", "permits_per_1k",
            "migration_per_1k", "log_population"]
FEATURE_LABELS = {
    "growth_1m": "Price change, last month", "growth_3m": "Price change, last 3 months",
    "growth_6m": "Price change, last 6 months", "growth_12m": "Price change, last 12 months",
    "growth_24m": "Price change, last 24 months", "other_growth_12m": "Other housing cost, last 12 months",
    "volatility": "How much prices swing", "national_growth_12m": "National trend, last 12 months",
    "vs_national_12m": "Metro vs. national trend", "job_growth_12m": "Job growth",
    "price_to_income": "Home price / income", "rent_to_income": "Rent / income",
    "mortgage_rate": "Mortgage rate", "mortgage_rate_change_12m": "Mortgage rate change",
    "permits_per_1k": "New homes permitted", "migration_per_1k": "Net migration",
    "log_population": "Metro size",
}


# ---------------- models ----------------

def new_model():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         min_samples_leaf=50, l2_regularization=1.0, random_state=0)


def fit(train: pd.DataFrame, target: str = "target"):
    model = new_model()
    model.fit(train[FEATURES], train[target])
    return model


def predict_two_part(rel_model, df: pd.DataFrame) -> pd.Series:
    """Latest national trend + the model's metro adjustment."""
    return df["national_growth_12m"] + rel_model.predict(df[FEATURES])


def baselines(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {"Flat": pd.Series(0.0, index=df.index),
            "Persistence": df["growth_12m"],
            "National": df["national_growth_12m"]}


def scale(df: pd.DataFrame, floor: float) -> pd.Series:
    """Per-metro uncertainty scale: recent price volatility, floored so calm metros
    don't get unrealistically narrow ranges."""
    return df["volatility"].fillna(floor).clip(lower=floor)


def conformal_quantile(cal: pd.DataFrame, pred: pd.Series, floor: float, level: float = COVERAGE) -> float:
    """Normalized split conformal: the level-quantile of |error| / scale on a calibration set."""
    scores = (cal["target"] - pred).abs() / scale(cal, floor)
    n = len(scores)
    q = min(1.0, np.ceil((n + 1) * level) / n)
    return float(np.quantile(scores, q))


def forecast_at(known: pd.DataFrame, cutoff: pd.Timestamp, targets: pd.DataFrame) -> pd.DataFrame:
    """Train on origins <= cutoff (their outcomes are known), calibrate the range on the
    final CAL_MONTHS before the cutoff with a model that hadn't seen them, then forecast."""
    floor = float(known["volatility"].quantile(0.10))
    train = known[known["date"] <= cutoff]
    cal_start = cutoff - pd.DateOffset(months=CAL_MONTHS)
    cal = train[train["date"] > cal_start]
    pre_cal = train[train["date"] <= cal_start]
    cal_pred = (predict_two_part(fit(pre_cal, "target_rel"), cal)
                + fit(pre_cal).predict(cal[FEATURES])) / 2
    q = conformal_quantile(cal, cal_pred, floor)
    rel_model = fit(train, "target_rel")
    out = targets[["cbsa_code", "cbsa_title", "date", "level", "growth_12m", "volatility"]].copy()
    out["two_part"] = predict_two_part(rel_model, targets).to_numpy()
    out["direct"] = fit(train).predict(targets[FEATURES])
    out["forecast"] = (out["two_part"] + out["direct"]) / 2
    model = rel_model
    half = q * scale(targets, floor)
    out["lo"], out["hi"] = out["forecast"] - half, out["forecast"] + half
    out.attrs["model"], out.attrs["q"] = model, q
    return out


def backtest(feat: pd.DataFrame) -> pd.DataFrame:
    known = feat[feat["target"].notna()]
    rows = []
    for year in TEST_YEARS:
        start = pd.Timestamp(f"{year}-01-01")
        test = known[(known["date"] >= start) & (known["date"] < start + pd.DateOffset(years=1))]
        if test.empty:
            continue
        cutoff = start - pd.DateOffset(months=HORIZON)  # outcomes known as of January of the test year
        fc = forecast_at(known, cutoff, test)
        res = fc[["cbsa_code", "date", "lo", "hi"]].assign(year=year, actual=test["target"].to_numpy())
        res[MODEL] = fc["forecast"].to_numpy()
        res[TWO_PART] = fc["two_part"].to_numpy()
        res[DIRECT] = fc["direct"].to_numpy()
        for name, pred in baselines(test).items():
            res[name] = pred.to_numpy()
        rows.append(res)
    if not rows:
        raise SourceError("No backtest years with known outcomes.")
    return pd.concat(rows, ignore_index=True)


def score_backtest(bt: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute error in percentage points of 12-month growth, by year and overall."""
    designs = DESIGNS
    per_year = bt.groupby("year").apply(
        lambda g: pd.Series({d: (g[d] - g["actual"]).abs().mean() * 100 for d in designs}
                            | {"coverage": ((g["actual"] >= g["lo"]) & (g["actual"] <= g["hi"])).mean(),
                               "n": len(g)}), include_groups=False)
    overall = {d: (bt[d] - bt["actual"]).abs().mean() * 100 for d in designs}
    overall["coverage"] = ((bt["actual"] >= bt["lo"]) & (bt["actual"] <= bt["hi"])).mean()
    overall["n"] = len(bt)
    per_year.loc["All years"] = pd.Series(overall)
    calm = bt[~bt["year"].isin(SHOCK_YEARS)]
    calm_row = {d: (calm[d] - calm["actual"]).abs().mean() * 100 for d in designs}
    calm_row["coverage"] = ((calm["actual"] >= calm["lo"]) & (calm["actual"] <= calm["hi"])).mean()
    calm_row["n"] = len(calm)
    per_year.loc["2022-2025"] = pd.Series(calm_row)
    return per_year


def importance(feat: pd.DataFrame, year: int) -> pd.Series:
    """Permutation importance on one held-out year: how much worse the metro adjustment
    gets when each input is shuffled."""
    from sklearn.inspection import permutation_importance
    known = feat[feat["target"].notna()]
    start = pd.Timestamp(f"{year}-01-01")
    test = known[(known["date"] >= start) & (known["date"] < start + pd.DateOffset(years=1))]
    model = fit(known[known["date"] <= start - pd.DateOffset(months=HORIZON)], "target_rel")
    r = permutation_importance(model, test[FEATURES], test["target_rel"], scoring="neg_mean_absolute_error",
                               n_repeats=3, random_state=0)
    return pd.Series(r.importances_mean * 100, index=FEATURES).sort_values(ascending=False)


def latest_forecast(feat: pd.DataFrame) -> pd.DataFrame:
    known = feat[feat["target"].notna()]
    as_of = feat["date"].max()
    targets = feat[(feat["date"] == as_of)].dropna(subset=["growth_12m"])
    return forecast_at(known, known["date"].max(), targets)


# ---------------- charts ----------------

def chart_accuracy(scores: dict[str, pd.DataFrame]) -> str:
    fig, axes = charts.new(6.6, 2.5, ncols=len(scores), sharex=True)
    designs = DESIGNS
    for ax, (metric, sc) in zip(axes, scores.items()):
        vals = sc.loc["All years", designs].astype(float)[::-1]
        colors = [charts.SERIES_1 if d == MODEL else charts.FAINT for d in vals.index]
        ax.barh(vals.index, vals.values, color=colors, height=0.6)
        for i, v in enumerate(vals.values):
            ax.text(v + 0.08, i, f"{v:.1f} pts", va="center", fontsize=8,
                    color=charts.INK if vals.index[i] == MODEL else charts.INK_2,
                    fontweight="bold" if vals.index[i] == MODEL else "normal")
        ax.set_title(METRICS[metric], loc="left", fontsize=9, color=charts.INK)
        ax.grid(False)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.set_xlim(0, vals.max() * 1.35)
    axes[-1].tick_params(labelleft=False)
    charts.title(fig, "Average forecast error, 12 months ahead (lower is better)",
                 "Rolling backtest, every metro, every month of 2020-2025")
    return charts.save(fig, FIG_DIR / "forecast_accuracy.png", top=0.84)


def chart_large_metros(fc: pd.DataFrame, raw: pd.DataFrame) -> str:
    pop = raw.groupby("cbsa_code")["population"].max()
    top = fc.assign(pop=fc["cbsa_code"].map(pop)).nlargest(LARGE_METROS, "pop").sort_values("forecast")
    top["name"] = top["cbsa_title"].str.split(",").str[0].str.split("-").str[0]
    fig, ax = charts.new(6.4, 3.4)
    ax.grid(False)
    charts.style(ax, grid="x")
    y = np.arange(len(top))
    g = np.expm1
    ax.hlines(y, g(top["lo"]), g(top["hi"]), color=charts.FAINT, lw=3.5)
    ax.plot(g(top["forecast"]), y, "o", color=charts.SERIES_1, ms=5.5, mec=charts.SURFACE, mew=1)
    for yi, (_, r) in zip(y, top.iterrows()):
        ax.text(g(r["hi"]) + 0.003, yi, f"{g(r['forecast']):+.1%}", va="center", fontsize=8, color=charts.INK)
    ax.axvline(0, color=charts.INK_2, lw=0.8)
    ax.set_yticks(y, top["name"])
    ax.xaxis.set_major_formatter(__import__("matplotlib.ticker", fromlist=["x"]).PercentFormatter(1, decimals=0))
    span = g(top["hi"]).max() - g(top["lo"]).min()
    ax.set_xlim(g(top["lo"]).min() - span * 0.05, g(top["hi"]).max() + span * 0.18)
    as_of = pd.Timestamp(fc["date"].iloc[0])
    charts.title(fig, f"Rent forecast for the {LARGE_METROS} largest metros, next 12 months",
                 f"From {as_of:%b %Y}. Dot = forecast; bar = 80% range")
    return charts.save(fig, FIG_DIR / "forecast_large_metros.png", top=0.86)


# ---------------- report ----------------

def write_report(scores, fcs, imps, figs) -> None:
    rent_sc, rent_fc = scores["rent"], fcs["rent"]
    allr, calm = rent_sc.loc["All years"], rent_sc.loc["2022-2025"]
    best_base = min(BASELINES, key=lambda b: allr[b])
    gain = 1 - allr[MODEL] / allr[best_base]
    calm_base = min(BASELINES, key=lambda b: calm[b])
    calm_gain = 1 - calm[MODEL] / calm[calm_base]
    as_of = pd.Timestamp(rent_fc["date"].iloc[0])
    L = ["# CityLens Forecast Engine", "",
         "**Question:** where will rents and home values be 12 months from now, and how sure can we be?", "",
         "## Short answer", "",
         f"1. **Over 2020-2025 the rent forecast missed by {allr[MODEL]:.1f} points** of 12-month growth on "
         f"average, vs. {allr[best_base]:.1f} for the best simple baseline ({best_base.lower()}): "
         f"{abs(gain):.0%} {'smaller' if gain > 0 else 'larger'} errors. **Since 2022 the gap is "
         f"{calm_gain:.0%}** ({calm[MODEL]:.1f} vs. {calm[calm_base]:.1f}).",
         f"2. **No model saw the pandemic coming.** In 2020-21 every approach missed badly; most of any forecast's "
         "error is the national swing, which local data can't predict. Two designs fail in different years "
         "(one missed the 2021 surge, the other the 2022 turn), so the CityLens forecast averages them.",
         f"3. **The ranges are honest about it.** {calm['coverage']:.0%} of outcomes landed inside the 80% ranges in "
         f"2022-2025, and {allr['coverage']:.0%} across all years including the pandemic shock.",
         f"4. **Forecast from {as_of:%b %Y}:** typical metro rent "
         f"{np.expm1(rent_fc['forecast'].median()):+.1%} over the next 12 months.", "",
         f"![Forecast accuracy](figures/{figs[0]})", "",
         "## Backtest, year by year", "",
         "Average miss in percentage points of 12-month growth. The model is trained only on outcomes known by "
         "January of each test year.", ""]
    for metric, sc in scores.items():
        L += [f"**{METRICS[metric]}**", "",
              "| Test year | CityLens model | Two-part | Direct | Flat | Persistence | National | 80% range coverage |",
              "|---|---|---|---|---|---|---|---|"]
        for yr, r in sc.iterrows():
            best = min(DESIGNS, key=lambda d: r[d])
            cells = [f"**{r[d]:.1f}**" if d == best else f"{r[d]:.1f}" for d in DESIGNS]
            L.append(f"| {yr} | " + " | ".join(cells) + f" | {r['coverage']:.0%} |")
        L.append("")
    L += ["Bold = most accurate that year. Design history, in order: the direct model came first; its 2021 miss and "
          "the finding that most error is the national swing led to the two-part model; that model's 2022 miss led to "
          "averaging the two. Because these choices were made while looking at this backtest, the forecasts made from "
          "here on are the true out-of-sample test.", "",
          f"## Rent forecast for the {LARGE_METROS} largest metros", "",
          f"![Large metro forecast](figures/{figs[1]})", ""]
    top, bottom = rent_fc.nlargest(10, "forecast"), rent_fc.nsmallest(10, "forecast")
    for heading, rows in [("Fastest expected rent growth", top), ("Slowest expected rent growth", bottom)]:
        L += [f"## {heading} (next 12 months)", "",
              "| Metro | Rent now | Last 12 months | Forecast | 80% range |", "|---|---|---|---|---|"]
        for _, r in rows.iterrows():
            L.append(f"| {r['cbsa_title']} | ${r['level']:,.0f} | {np.expm1(r['growth_12m']):+.1%} | "
                     f"**{np.expm1(r['forecast']):+.1%}** | {np.expm1(r['lo']):+.1%} to {np.expm1(r['hi']):+.1%} |")
        L.append("")
    L += ["## What drives the forecast", "",
          f"Permutation importance on the {max(TEST_YEARS)} test year: how much worse the metro adjustment gets "
          "(points of error) when each input is scrambled.", "",
          "| Input | Added error when scrambled |", "|---|---|"]
    for f, v in imps["rent"].head(8).items():
        L.append(f"| {FEATURE_LABELS[f]} | +{max(v, 0):.2f} pts |")
    hv = fcs.get("home_value")
    if hv is not None:
        L += ["", "## Home values", "",
              f"Typical metro home value forecast: {np.expm1(hv['forecast'].median()):+.1%} over the next 12 months. "
              f"Backtest error {scores['home_value'].loc['All years', MODEL]:.1f} pts "
              f"({scores['home_value'].loc['2022-2025', MODEL]:.1f} since 2022) vs. "
              f"{min(scores['home_value'].loc['All years', b] for b in BASELINES):.1f} for the best baseline; "
              f"range coverage {scores['home_value'].loc['All years', 'coverage']:.0%}."]
    L += ["", "## How it works", "",
          "- **Model:** the average of (a) the latest national 12-month trend plus a metro adjustment and (b) a direct "
          "forecast of total growth. Both are gradient-boosted trees (scikit-learn), one model across all metros; the "
          "adjustment model learns each metro's 12-month change relative to the national average that month.",
          "- **Inputs** are lagged to match publication: jobs 6 months, incomes 12, permits 18, migration 24.",
          "- **Backtest:** for each year 2020-2025, train on outcomes known by January, forecast every metro for "
          "every month of that year.",
          "- **80% ranges:** normalized split conformal prediction. A model trained two years earlier is scored on the "
          "24 months before the cutoff; its errors, scaled by each metro's price volatility, set the range width.",
          "", "## Caveats", "",
          "- 2020-2022 were unusually hard to forecast (pandemic boom, then rate shock); errors in calmer years are "
          "much smaller.",
          "- Forecasts assume the next year looks like the recent past. A sudden shock (a recession, a rate cut cycle) "
          "would push outcomes outside the ranges.",
          "- Zillow's rent index covers asking rents on new leases."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def run() -> dict:
    raw = load()
    scores, fcs, imps, bts = {}, {}, {}, []
    for metric in METRICS:
        feat = build_features(raw, metric)
        bt = backtest(feat)
        scores[metric] = score_backtest(bt)
        fcs[metric] = latest_forecast(feat).assign(metric=metric)
        imps[metric] = importance(feat, max(TEST_YEARS))
        bts.append(bt.assign(metric=metric))
        a = scores[metric].loc["All years"]
        c = scores[metric].loc["2022-2025"]
        log.info("%s: model error %.2f pts (2022-25: %.2f) vs best baseline %.2f (%.2f); coverage %.0f%% (%.0f%%)",
                 metric, a[MODEL], c[MODEL], min(a[b] for b in BASELINES), min(c[b] for b in BASELINES),
                 a["coverage"] * 100, c["coverage"] * 100)
    figs = [chart_accuracy(scores), chart_large_metros(fcs["rent"], raw)]
    write_report(scores, fcs, imps, figs)
    out = pd.concat(fcs.values(), ignore_index=True)
    for c in ("forecast", "lo", "hi", "growth_12m"):
        out[c + "_pct"] = np.expm1(out[c])
    out.to_parquet(OUT, index=False)
    pd.concat(bts, ignore_index=True).to_parquet(BACKTEST_OUT, index=False)
    record_run("forecast_engine", len(out), f"{out['date'].max():%Y-%m}")
    log.info("Saved forecasts, backtest, charts and docs/forecast_report.md")
    return scores


if __name__ == "__main__":
    run()
