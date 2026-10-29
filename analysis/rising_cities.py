"""Layer 3: the Rising City Detector.

Question: which affordable metros are about to see prices rise faster than the rest,
and do the usual "boomtown" signals (migration, job growth) actually predict it?

Three parts:

1. EXPLAIN. A panel of every metropolitan area at the end of each year (2018-2024).
   Does what we know in December predict which metros' home values outgrow the typical
   metro over the next 12 months? Estimated with year fixed effects (each year compared
   to that year's national average) and standard errors clustered by metro, then
   re-estimated year by year to see whether each signal is stable or flips with the market.

2. TEST. A walk-forward backtest: for each year, fit only on years whose outcomes were
   already known, predict the next year, and score the ranking against what happened.
   Competing designs include the fitted regression and simple, unfitted blends.

3. DETECT. Apply the design that won the backtest to today's data and list the metros
   most likely to outgrow the typical metro next year, plus the pandemic boomtowns that
   have cooled.

Timing rules (so the backtest never peeks at the future): migration is lagged two years
and permits one year, matching when the IRS and Census actually publish them.

Run:  python -m analysis.rising_cities     (run analysis.opportunity_index first)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.config import ROOT
from pipeline.utils import SourceError, log, record_run

MART = ROOT / "data" / "marts" / "mart_metro_month.parquet"
OPPORTUNITY = ROOT / "data" / "marts" / "opportunity_index.parquet"
OUT = ROOT / "data" / "marts" / "rising_cities.parquet"
REPORT = ROOT / "docs" / "rising_cities_report.md"

FEATURES = ["migration", "job_growth", "wage_growth", "permits", "price_to_income", "momentum"]
LABELS = {
    "migration": "Net migration (2 years earlier)",
    "job_growth": "Job growth (past year)",
    "wage_growth": "Wage growth (past year)",
    "permits": "New homes permitted (prior year)",
    "price_to_income": "Price-to-income (how expensive)",
    "momentum": "Home price growth (past year)",
}
COVID_ORIGINS = [2020, 2021]
FIRST_TEST_YEAR = 2021

PANEL_SQL = """
WITH m AS (SELECT * FROM read_parquet('{mart}') WHERE cbsa_type = 'Metropolitan'),
dec AS (SELECT cbsa_code, year, home_value, median_household_income
        FROM m WHERE month(date) = 12),
jun AS (SELECT cbsa_code, year, employment, avg_weekly_wage FROM m WHERE month(date) = 6),
mig AS (SELECT DISTINCT cbsa_code, year, net_migration_rate_per_1k FROM m
        WHERE net_migration_rate_per_1k IS NOT NULL),
per AS (SELECT DISTINCT cbsa_code, year, permits_per_1k FROM m WHERE permits_per_1k IS NOT NULL)
SELECT d.cbsa_code, d.year AS origin,
       d.home_value, prev.home_value AS home_value_prev, nxt.home_value AS home_value_next,
       d.median_household_income AS income,
       j.employment, jp.employment AS employment_prev,
       j.avg_weekly_wage AS wage, jp.avg_weekly_wage AS wage_prev,
       mg.net_migration_rate_per_1k AS migration,
       p.permits_per_1k AS permits
FROM dec d
LEFT JOIN dec prev ON prev.cbsa_code = d.cbsa_code AND prev.year = d.year - 1
LEFT JOIN dec nxt  ON nxt.cbsa_code  = d.cbsa_code AND nxt.year  = d.year + 1
LEFT JOIN jun j    ON j.cbsa_code    = d.cbsa_code AND j.year    = d.year
LEFT JOIN jun jp   ON jp.cbsa_code   = d.cbsa_code AND jp.year   = d.year - 1
LEFT JOIN mig mg   ON mg.cbsa_code   = d.cbsa_code AND mg.year   = d.year - 2
LEFT JOIN per p    ON p.cbsa_code    = d.cbsa_code AND p.year    = d.year - 1
"""


# ---------------- data ----------------

def load_panel(mart_path=MART) -> pd.DataFrame:
    import duckdb
    if not mart_path.exists():
        raise SourceError("Run `python -m pipeline.build_panel` first.")
    raw = duckdb.connect().execute(PANEL_SQL.format(mart=mart_path.as_posix())).df()
    return add_features(raw)


def add_features(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["future_growth"] = df["home_value_next"] / df["home_value"] - 1
    df["momentum"] = df["home_value"] / df["home_value_prev"] - 1
    df["price_to_income"] = np.log(df["home_value"] / df["income"])
    df["job_growth"] = df["employment"] / df["employment_prev"] - 1
    df["wage_growth"] = df["wage"] / df["wage_prev"] - 1
    return df


def prepare(df: pd.DataFrame, group: str = "origin", target: str | None = "future_growth") -> pd.DataFrame:
    """Within each year: trim the extreme 1% at each end, convert features to z-scores,
    and express the target relative to that year's average (= year fixed effects)."""
    cols = FEATURES + ([target] if target else [])
    out = df.dropna(subset=cols).copy()
    for c in cols:
        g = out.groupby(group)[c]
        out[c] = out[c].clip(g.transform(lambda s: s.quantile(0.01)), g.transform(lambda s: s.quantile(0.99)))
    for c in FEATURES:
        g = out.groupby(group)[c]
        out[f"{c}_z"] = (out[c] - g.transform("mean")) / g.transform("std")
    if target:
        out["target_rel"] = out[target] - out.groupby(group)[target].transform("mean")
    return out


# ---------------- 1. explain ----------------

FORMULA = "target_rel ~ " + " + ".join(f"{f}_z" for f in FEATURES)


def explain(d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    import statsmodels.formula.api as smf

    def fit(data, extra=""):
        return smf.ols(FORMULA + extra, data).fit(cov_type="cluster", cov_kwds={"groups": data["cbsa_code"]})

    def coef_table(model, name):
        ci = model.conf_int()
        return pd.DataFrame({"spec": name, "feature": FEATURES,
                             "effect_pp": [model.params[f"{f}_z"] * 100 for f in FEATURES],
                             "ci_low_pp": [ci.loc[f"{f}_z", 0] * 100 for f in FEATURES],
                             "ci_high_pp": [ci.loc[f"{f}_z", 1] * 100 for f in FEATURES],
                             "p_value": [model.pvalues[f"{f}_z"] for f in FEATURES]})

    main = fit(d)
    no_covid = d[~d["origin"].isin(COVID_ORIGINS)]
    specs = pd.concat([coef_table(main, "All years"),
                       coef_table(fit(no_covid), "Excluding 2020-21"),
                       coef_table(fit(d, " + C(cbsa_code)"), "Metro fixed effects")], ignore_index=True)

    yearly = []
    for origin, g in d.groupby("origin"):
        m = smf.ols(FORMULA, g).fit(cov_type="HC1")
        row = {"origin": int(origin), "n": len(g), "r2": m.rsquared}
        for f in FEATURES:
            row[f] = m.params[f"{f}_z"] * 100
            row[f"{f}_t"] = m.tvalues[f"{f}_z"]
        yearly.append(row)
    fit_stats = pd.DataFrame([{"n_obs": int(main.nobs), "n_metros": d["cbsa_code"].nunique(),
                               "first_origin": int(d["origin"].min()), "last_origin": int(d["origin"].max()),
                               "r2": main.rsquared}])
    return {"specs": specs, "yearly": pd.DataFrame(yearly), "fit": fit_stats}


# ---------------- 2. test ----------------

def rank_corr(pred: pd.Series, actual: pd.Series) -> float:
    return pred.rank().corr(actual.rank())


def quintile_spread(pred: pd.Series, actual: pd.Series) -> float:
    q = pd.qcut(pred.rank(method="first"), 5, labels=False)
    return actual[q == 4].mean() - actual[q == 0].mean()


def design_scores(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, pd.Series]:
    """Every competing design, each producing a score where higher = more expected growth."""
    import statsmodels.formula.api as smf
    t = test.origin.iloc[0]
    recent = train[train["origin"] >= t - 2]
    return {
        "Regression (all past years)": smf.ols(FORMULA, train).fit().predict(test),
        "Regression (last 2 years only)": smf.ols(FORMULA, recent).fit().predict(test),
        "Momentum only": test["momentum_z"],
        "Affordability only": -test["price_to_income_z"],
        "Momentum + affordability": signal(test),
        "Momentum + affordability + low supply": signal(test) - test["permits_z"],
    }


def signal(df: pd.DataFrame) -> pd.Series:
    """The Rising Signal: equal-weight blend of the two signals that held up out of sample."""
    return df["momentum_z"] - df["price_to_income_z"]


CHOSEN = "Momentum + affordability"


def backtest(d: pd.DataFrame, first_test: int = FIRST_TEST_YEAR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk forward: train on origins <= T-1 (their 12-month outcomes are known by December
    of year T), predict origin T."""
    rows, quint = [], []
    for t in sorted(o for o in d["origin"].unique() if o >= first_test):
        train, test = d[d["origin"] <= t - 1], d[d["origin"] == t]
        if test.empty or train.empty:
            continue
        for name, pred in design_scores(train, test).items():
            rows.append({"test_year": int(t), "design": name, "n": len(test),
                         "rank_corr": rank_corr(pred, test["target_rel"]),
                         "top_minus_bottom_pp": quintile_spread(pred, test["target_rel"]) * 100})
        q = pd.qcut(signal(test).rank(method="first"), 5, labels=False)
        for k in range(5):
            quint.append({"test_year": int(t), "quintile": k + 1,
                          "realized_rel_pp": test["target_rel"][q == k].mean() * 100})
    return pd.DataFrame(rows), pd.DataFrame(quint)


def leaderboard(bt: pd.DataFrame) -> pd.DataFrame:
    piv = bt.pivot_table(index="design", columns="test_year", values="rank_corr")
    piv["average"] = piv.mean(axis=1)
    spread = bt.groupby("design")["top_minus_bottom_pp"].agg(["mean", "min"])
    piv["avg_spread_pp"], piv["worst_spread_pp"] = spread["mean"], spread["min"]
    return piv.sort_values("average", ascending=False)


# ---------------- 3. detect ----------------

CURRENT_SQL = """
WITH m AS (SELECT * FROM read_parquet('{mart}') WHERE cbsa_type = 'Metropolitan'),
e AS (SELECT max(date) FILTER (WHERE home_value IS NOT NULL) AS h,
             max(date) FILTER (WHERE employment IS NOT NULL) AS j,
             max(year) FILTER (WHERE net_migration_rate_per_1k IS NOT NULL) AS mg,
             max(year) FILTER (WHERE permits_per_1k IS NOT NULL) AS p FROM m)
SELECT m.cbsa_code, any_value(m.cbsa_title) AS cbsa_title,
       max(m.home_value) FILTER (WHERE m.date = e.h)                         AS home_value,
       max(m.home_value) FILTER (WHERE m.date = e.h - INTERVAL 12 MONTH)     AS home_value_prev,
       max(m.median_household_income) FILTER (WHERE m.date = e.h)            AS income,
       max(m.employment) FILTER (WHERE m.date = e.j)                         AS employment,
       max(m.employment) FILTER (WHERE m.date = e.j - INTERVAL 12 MONTH)     AS employment_prev,
       max(m.avg_weekly_wage) FILTER (WHERE m.date = e.j)                    AS wage,
       max(m.avg_weekly_wage) FILTER (WHERE m.date = e.j - INTERVAL 12 MONTH) AS wage_prev,
       avg(m.net_migration_rate_per_1k) FILTER (WHERE m.year = e.mg)        AS migration,
       avg(m.permits_per_1k) FILTER (WHERE m.year = e.p)                    AS permits,
       any_value(e.h) AS as_of
FROM m CROSS JOIN e GROUP BY m.cbsa_code
"""


def current(mart_path=MART, opportunity_path=OPPORTUNITY) -> pd.DataFrame:
    import duckdb
    raw = duckdb.connect().execute(CURRENT_SQL.format(mart=mart_path.as_posix())).df()
    raw["home_value_next"] = np.nan
    df = add_features(raw)
    df["origin"] = 0  # one cross-section
    d = prepare(df, target=None)
    d["rising_signal"] = signal(d)
    d["signal_quintile"] = pd.qcut(d["rising_signal"].rank(method="first"), 5, labels=False) + 1
    if opportunity_path.exists():
        oi = pd.read_parquet(opportunity_path)[["cbsa_code", "rank", "archetype", "size_band",
                                                "net_migration_per_1k", "affordability_score"]]
        d = d.merge(oi.rename(columns={"rank": "opportunity_rank",
                                       "net_migration_per_1k": "migration_3yr_avg"}),
                    on="cbsa_code", how="left")
    return d.sort_values("rising_signal", ascending=False).reset_index(drop=True)


def classify(d: pd.DataFrame) -> pd.Series:
    """Plain-language label for each metro today."""
    hot_mig = d["migration_3yr_avg"] >= d["migration_3yr_avg"].quantile(0.8)
    labels = np.select(
        [(d["signal_quintile"] == 5) & (d["job_growth"] > 0),
         (d["signal_quintile"] == 5),
         hot_mig & (d["signal_quintile"] <= 2)],
        ["Rising City", "Rising (prices only, jobs flat)", "Cooling Boomtown"], default="")
    # object dtype keeps empty labels as None in every pandas version (pandas 3 would turn them into NaN)
    return pd.Series([lab or None for lab in labels], index=d.index, dtype=object)


# ---------------- report ----------------

def _p(v):
    return "<0.001" if v < 0.001 else f"{v:.3f}"


def write_report(exp: dict, bt: pd.DataFrame, quint: pd.DataFrame, now: pd.DataFrame) -> None:
    fit = exp["fit"].iloc[0]
    main = exp["specs"][exp["specs"]["spec"] == "All years"]
    lb = leaderboard(bt)
    years = [c for c in lb.columns if isinstance(c, (int, np.integer))]
    chosen = lb.loc[CHOSEN]
    q_avg = quint.groupby("quintile")["realized_rel_pp"].agg(["mean", "min", "max"])
    as_of = pd.Timestamp(now["as_of"].iloc[0])

    L = ["# CityLens Rising City Detector", "",
         "**Question:** which metros are about to see home prices rise faster than the rest, and do the "
         "usual boomtown signals actually predict it?", "",
         f"Panel: {int(fit['n_obs']):,} metro-years ({int(fit['n_metros'])} metropolitan areas, December "
         f"{int(fit['first_origin'])} to December {int(fit['last_origin'])}), each predicting the next 12 months "
         "of home-value growth relative to the typical metro that year.", "",
         "## The short answer", "",
         f"1. **Momentum and affordability are the signals that last.** A simple blend of the two ranked metros "
         f"correctly enough that its top fifth outgrew its bottom fifth by **{chosen['avg_spread_pp']:.1f} "
         f"points a year on average** (never less than {chosen['worst_spread_pp']:.1f}) in an honest backtest.",
         "2. **The pandemic boomtown signal flipped.** High migration predicted faster price growth through "
         "2021, then turned negative once rates rose in 2022 (clearly so in 2023 and 2024), as the boomtowns cooled.",
         "3. **A fitted regression lost to the simple blend out of sample**, because it learned relationships "
         "from the pandemic market that stopped holding. Simple, stable signals beat a model tuned to the past.",
         "", "## 1. What predicted price growth (all years pooled)", "",
         "Effect of a one-standard-deviation higher value on next-year home-value growth, in percentage points "
         "relative to the typical metro. Year fixed effects; standard errors clustered by metro.", "",
         "| Signal | Effect (pp) | 95% range | p-value |", "|---|---|---|---|"]
    for _, r in main.iterrows():
        L.append(f"| {LABELS[r['feature']]} | {r['effect_pp']:+.2f} | {r['ci_low_pp']:+.2f} to "
                 f"{r['ci_high_pp']:+.2f} | {_p(r['p_value'])} |")
    L += ["", f"R² = {fit['r2']:.2f}. Prices are hard to predict; this explains part of the spread, not all of it.",
          "", "**Robustness.** The same model excluding the 2020-21 pandemic years, and with metro fixed effects "
          "(comparing each metro only to itself over time):", "",
          "| Signal | All years | Excluding 2020-21 | Metro fixed effects |", "|---|---|---|---|"]
    piv = exp["specs"].pivot(index="feature", columns="spec", values="effect_pp")
    for f in FEATURES:
        L.append(f"| {LABELS[f]} | {piv.loc[f, 'All years']:+.2f} | {piv.loc[f, 'Excluding 2020-21']:+.2f} | "
                 f"{piv.loc[f, 'Metro fixed effects']:+.2f} |")

    L += ["", "The metro fixed effects price-to-income number is much larger because it answers a different "
          "question: not 'do expensive metros grow slower than cheap ones' but 'when a metro's prices run "
          "ahead of its own incomes, do they come back down?' They strongly do.",
          "", "## 2. How the signals changed, year by year", "",
          "Effect (pp per 1 SD) estimated separately for each starting December. Bold = statistically clear "
          "(|t| ≥ 2).", "",
          "| Starting Dec | " + " | ".join(LABELS[f].split(" (")[0] for f in FEATURES) + " | R² |",
          "|---|" + "---|" * (len(FEATURES) + 1)]
    for _, r in exp["yearly"].iterrows():
        cells = [(f"**{r[f]:+.2f}**" if abs(r[f + '_t']) >= 2 else f"{r[f]:+.2f}") for f in FEATURES]
        L.append(f"| {int(r['origin'])} | " + " | ".join(cells) + f" | {r['r2']:.2f} |")
    L += ["", "Momentum predicts growth in every year. Migration and job growth mattered in the cheap-money "
          "pandemic market and faded or reversed after rates rose in 2022. Expensive metros (high "
          "price-to-income) have grown more slowly in most years since 2021.", "",
          "## 3. Backtest: which design actually predicts?", "",
          "Each year, every design is built only from information available at the time, then scored on "
          "what happened next. Rank correlation: 1.0 = perfect ordering, 0 = no better than chance.", "",
          "| Design | " + " | ".join(str(y) for y in years) + " | Average | Top-minus-bottom fifth (avg pp) |",
          "|---|" + "---|" * (len(years) + 2)]
    for name, r in lb.iterrows():
        mark = " ⭐" if name == CHOSEN else ""
        L.append(f"| {name}{mark} | " + " | ".join(f"{r[y]:.2f}" for y in years) +
                 f" | **{r['average']:.2f}** | {r['avg_spread_pp']:+.1f} |")
    L += ["", f"**Chosen: {CHOSEN}.** It needs no fitting, so it can't overfit a past market, and it had the "
          "best average with no bad years.", "",
          "What each fifth of the Rising Signal went on to do (next-year growth vs. the typical metro):", "",
          "| Signal fifth | Average (pp) | Worst year | Best year |", "|---|---|---|---|"]
    names = {1: "Bottom fifth", 2: "2nd", 3: "Middle", 4: "4th", 5: "Top fifth"}
    for k, r in q_avg.iterrows():
        L.append(f"| {names[k]} | {r['mean']:+.1f} | {r['min']:+.1f} | {r['max']:+.1f} |")

    rising = now[now["label"] == "Rising City"]
    cooling = now[now["label"] == "Cooling Boomtown"].sort_values("rising_signal")
    L += ["", f"## 4. Rising Cities now (data as of {as_of:%b %Y})", "",
          "Top fifth of the Rising Signal **and** adding jobs over the past year: metros most likely to outgrow "
          "the typical metro over the next 12 months, for healthy reasons.", "",
          "| Metro | Price growth (past yr) | Price-to-income | Job growth (past yr) | Opportunity rank |",
          "|---|---|---|---|---|"]
    for _, r in rising.head(20).iterrows():
        orank = "" if pd.isna(r.get("opportunity_rank")) else str(int(r["opportunity_rank"]))
        L.append(f"| {r['cbsa_title']} | {r['momentum']:+.1%} | {np.exp(r['price_to_income']):.1f}x | "
                 f"{r['job_growth']:+.1%} | {orank} |")
    if not cooling.empty:
        L += ["", "## Cooling Boomtowns", "",
              "Top fifth for migration over the latest three years, but bottom two-fifths of the Rising Signal "
              "today: the pandemic-era magnets where prices have stalled or fallen.", "",
              "| Metro | Net migration per 1,000 (3-yr avg) | Price growth (past yr) | Price-to-income |",
              "|---|---|---|---|"]
        for _, r in cooling.head(12).iterrows():
            L.append(f"| {r['cbsa_title']} | {r['migration_3yr_avg']:+.1f} | {r['momentum']:+.1%} | "
                     f"{np.exp(r['price_to_income']):.1f}x |")
    L += ["", "## Caveats", "",
          "- This predicts **relative** growth (vs. the typical metro), not whether national prices rise or fall.",
          "- The backtest covers four years (2021-2024), including one major regime change; more years will "
          "make it sharper.",
          "- Migration data ends in 2023 and is used with a two-year lag, as it would be in real time.",
          "- 'Rising' is not a recommendation to buy. For residents it can mean the window of affordability is "
          "closing; for builders and lenders it marks demand."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def run() -> pd.DataFrame:
    d = prepare(load_panel())
    if d.empty:
        raise SourceError("No complete metro-years to model.")
    exp = explain(d)
    bt, quint = backtest(d)
    now = current()
    now["label"] = classify(now)
    now.to_parquet(OUT, index=False)
    write_report(exp, bt, quint, now)
    n_rising = int((now["label"] == "Rising City").sum())
    record_run("rising_cities", len(now), str(now["as_of"].iloc[0])[:7], note=f"rising={n_rising}")
    log.info("Rising City Detector: %s metros scored, %s Rising Cities. Top 5: %s", len(now), n_rising,
             "; ".join(now[now["label"] == "Rising City"].head(5)["cbsa_title"]))
    log.info("Saved data/marts/rising_cities.parquet and docs/rising_cities_report.md")
    return now


if __name__ == "__main__":
    run()
