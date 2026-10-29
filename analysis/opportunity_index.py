"""Layer 2: the CityLens Opportunity Index.

Question: where does a typical paycheck go furthest today, in a place that is still growing?

Three pillars, six indicators, scored for every U.S. metropolitan area:

  Affordability (40%)    rent / income, mortgage payment / income        lower is better
  Momentum (35%)         3-year job growth, paycheck growth vs. prices   higher is better
  Demand & Supply (25%)  net migration per 1,000, new homes permitted    higher is better
                         per 1,000 residents

Each indicator becomes a percentile rank (0-100) so a big number in one indicator
can't swamp the others. Pillars average their indicators; the index is the weighted
sum of pillars.

A ranking is only useful if it doesn't fall apart when someone questions the weights,
so this script also:
  1. re-scores every metro under 1,000 random weightings (rank stability)
  2. drops each indicator one at a time (does any single input drive the result?)

Run:  python -m analysis.opportunity_index     (run pipeline.build_panel first)
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from pipeline.config import ROOT
from pipeline.utils import SourceError, log, record_run

MART = ROOT / "data" / "marts" / "mart_metro_month.parquet"
OUT = ROOT / "data" / "marts" / "opportunity_index.parquet"
REPORT = ROOT / "docs" / "opportunity_index_report.md"

# direction: -1 = lower is better, +1 = higher is better
PILLARS = {
    "affordability": {"weight": 0.40, "indicators": {"rent_to_income": -1, "mortgage_to_income": -1}},
    "momentum": {"weight": 0.35, "indicators": {"job_growth_3y": +1, "paycheck_vs_prices_3y": +1}},
    "demand_supply": {"weight": 0.25, "indicators": {"net_migration_per_1k": +1, "permits_per_1k": +1}},
}
INDICATOR_LABELS = {
    "rent_to_income": "Rent / income", "mortgage_to_income": "Mortgage / income",
    "job_growth_3y": "Job growth (3-yr, yearly)", "paycheck_vs_prices_3y": "Paycheck growth minus price growth",
    "net_migration_per_1k": "Net migration per 1,000", "permits_per_1k": "New homes permitted per 1,000",
}
PILLAR_LABELS = {"affordability": "Affordability", "momentum": "Momentum", "demand_supply": "Demand & Supply"}
N_SIMULATIONS = 1000
SEED = 42
SIZE_BANDS = [(1_000_000, "Large (1M+)"), (250_000, "Mid-size (250K-1M)"), (0, "Small (under 250K)")]

FEATURES_SQL = """
WITH metro AS (
    SELECT * FROM read_parquet('{mart}') WHERE cbsa_type = 'Metropolitan'
),
ends AS (
    SELECT max(date) FILTER (WHERE home_value IS NOT NULL) AS housing_end,
           max(date) FILTER (WHERE employment IS NOT NULL) AS jobs_end,
           max(year) FILTER (WHERE net_migration_rate_per_1k IS NOT NULL) AS migration_end,
           max(year) FILTER (WHERE permits_units IS NOT NULL) AS permits_end
    FROM metro
)
SELECT
    m.cbsa_code,
    any_value(m.cbsa_title)                                                   AS cbsa_title,
    any_value(m.principal_state)                                              AS state,
    -- snapshot at the latest housing month
    max(m.population)              FILTER (WHERE m.date = e.housing_end)      AS population,
    max(m.median_household_income) FILTER (WHERE m.date = e.housing_end)      AS median_household_income,
    max(m.home_value)              FILTER (WHERE m.date = e.housing_end)      AS home_value,
    max(m.rent)                    FILTER (WHERE m.date = e.housing_end)      AS rent,
    max(m.mortgage_payment)        FILTER (WHERE m.date = e.housing_end)      AS mortgage_payment,
    max(m.rent_to_income)          FILTER (WHERE m.date = e.housing_end)      AS rent_to_income,
    max(m.mortgage_to_income)      FILTER (WHERE m.date = e.housing_end)      AS mortgage_to_income,
    -- 3-year changes (same calendar month at both ends, so seasonality cancels)
    max(m.home_value)      FILTER (WHERE m.date = e.housing_end - INTERVAL 36 MONTH) AS home_value_3y_ago,
    max(m.rent)            FILTER (WHERE m.date = e.housing_end - INTERVAL 36 MONTH) AS rent_3y_ago,
    max(m.employment)      FILTER (WHERE m.date = e.jobs_end)                        AS jobs_now,
    max(m.employment)      FILTER (WHERE m.date = e.jobs_end - INTERVAL 36 MONTH)    AS jobs_3y_ago,
    max(m.avg_weekly_wage) FILTER (WHERE m.date = e.jobs_end)                        AS wage_now,
    max(m.avg_weekly_wage) FILTER (WHERE m.date = e.jobs_end - INTERVAL 36 MONTH)    AS wage_3y_ago,
    -- 3 most recent years of yearly sources (each year repeats monthly, so avg = equal-weight years)
    avg(m.net_migration_rate_per_1k) FILTER (WHERE m.year BETWEEN e.migration_end - 2 AND e.migration_end)
                                                                              AS net_migration_per_1k,
    avg(m.permits_per_1k) FILTER (WHERE m.year BETWEEN e.permits_end - 2 AND e.permits_end)
                                                                              AS permits_per_1k,
    any_value(e.housing_end) AS housing_end, any_value(e.jobs_end) AS jobs_end,
    any_value(e.migration_end) AS migration_end, any_value(e.permits_end) AS permits_end
FROM metro m CROSS JOIN ends e
GROUP BY m.cbsa_code
"""


def cagr(now: pd.Series, before: pd.Series, years: float = 3.0) -> pd.Series:
    """Compound yearly growth rate; missing if either end is missing or not positive."""
    ok = (now > 0) & (before > 0)
    return ((now / before) ** (1 / years) - 1).where(ok)


def load_features(mart_path=MART) -> pd.DataFrame:
    if not mart_path.exists():
        raise SourceError("Run `python -m pipeline.build_panel` first.")
    con = duckdb.connect()
    df = con.execute(FEATURES_SQL.format(mart=mart_path.as_posix())).df()
    return add_derived(df)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["job_growth_3y"] = cagr(df["jobs_now"], df["jobs_3y_ago"])
    df["wage_growth_3y"] = cagr(df["wage_now"], df["wage_3y_ago"])
    df["home_value_growth_3y"] = cagr(df["home_value"], df["home_value_3y_ago"])
    df["rent_growth_3y"] = cagr(df["rent"], df["rent_3y_ago"])
    # Cost growth = average of rent and home price growth (whichever exist)
    df["cost_growth_3y"] = df[["rent_growth_3y", "home_value_growth_3y"]].mean(axis=1, skipna=True)
    df["paycheck_vs_prices_3y"] = df["wage_growth_3y"] - df["cost_growth_3y"]
    # What a typical household keeps each year after housing
    df["income_left_after_rent"] = df["median_household_income"] - 12 * df["rent"]
    df["income_left_after_mortgage"] = df["median_household_income"] - 12 * df["mortgage_payment"]
    return df


def percentile(series: pd.Series, direction: int) -> pd.Series:
    """0-100 percentile rank; 100 = best. Missing stays missing."""
    return (series * direction).rank(pct=True, method="average") * 100


def score(df: pd.DataFrame, weights: dict[str, float] | None = None,
          drop: str | None = None) -> pd.DataFrame:
    """Score every metro. `weights` overrides pillar weights; `drop` removes one indicator."""
    weights = weights or {p: cfg["weight"] for p, cfg in PILLARS.items()}
    out = df[["cbsa_code"]].copy()
    for pillar, cfg in PILLARS.items():
        cols = [i for i in cfg["indicators"] if i != drop]
        pct = pd.concat({i: percentile(df[i], cfg["indicators"][i]) for i in cols}, axis=1)
        out[f"{pillar}_score"] = pct.mean(axis=1, skipna=True)  # average whatever is available
        for i in cols:
            out[f"{i}_pct"] = pct[i]
    pillar_cols = [f"{p}_score" for p in PILLARS]
    eligible = out[pillar_cols].notna().all(axis=1)
    total_w = sum(weights.values())
    out["opportunity_index"] = sum(out[f"{p}_score"] * w for p, w in weights.items()) / total_w
    out.loc[~eligible, "opportunity_index"] = np.nan
    out["rank"] = out["opportunity_index"].rank(ascending=False, method="min")
    return out


def archetype(row: pd.Series, aff_median: float, mom_median: float) -> str | None:
    if pd.isna(row["affordability_score"]) or pd.isna(row["momentum_score"]):
        return None
    affordable = row["affordability_score"] >= aff_median
    rising = row["momentum_score"] >= mom_median
    return {(True, True): "Rising & Affordable", (False, True): "Rising but Pricey",
            (True, False): "Affordable but Slowing", (False, False): "Squeezed"}[(affordable, rising)]


def size_band(pop: float) -> str | None:
    if pd.isna(pop):
        return None
    return next(label for floor, label in SIZE_BANDS if pop >= floor)


def rank_stability(df: pd.DataFrame, n: int = N_SIMULATIONS, seed: int = SEED,
                   top_n: int = 25) -> pd.DataFrame:
    """Re-rank under n random pillar weightings drawn evenly from every possible mix
    (Dirichlet(1,1,1)). A metro that stays near the top under most weightings is a
    robust finding, not an artifact of the chosen weights."""
    rng = np.random.default_rng(seed)
    pillars = list(PILLARS)
    base = score(df)
    eligible = base["opportunity_index"].notna()
    pillar_matrix = base.loc[eligible, [f"{p}_score" for p in pillars]].to_numpy()
    w = rng.dirichlet(np.ones(len(pillars)), size=n)               # n x 3
    sims = pillar_matrix @ w.T                                       # metros x n
    ranks = pd.DataFrame(sims).rank(ascending=False, method="min").to_numpy()
    return pd.DataFrame({
        "cbsa_code": base.loc[eligible, "cbsa_code"].to_numpy(),
        "rank_median": np.median(ranks, axis=1),
        "rank_p05": np.percentile(ranks, 5, axis=1),
        "rank_p95": np.percentile(ranks, 95, axis=1),
        f"share_top{top_n}": (ranks <= top_n).mean(axis=1),
    })


def leave_one_out(df: pd.DataFrame, top_n: int = 25) -> pd.DataFrame:
    """Drop each indicator in turn. High rank correlation and top-N overlap mean no single
    input is driving the ranking."""
    base = score(df).dropna(subset=["opportunity_index"])
    base_top = set(base.nsmallest(top_n, "rank")["cbsa_code"])
    rows = []
    for cfg in PILLARS.values():
        for ind in cfg["indicators"]:
            alt = score(df, drop=ind).dropna(subset=["opportunity_index"])
            joined = base[["cbsa_code", "opportunity_index"]].merge(
                alt[["cbsa_code", "opportunity_index"]], on="cbsa_code", suffixes=("", "_alt"))
            rho = joined["opportunity_index"].rank().corr(joined["opportunity_index_alt"].rank())
            alt_top = set(alt.nsmallest(top_n, "rank")["cbsa_code"])
            rows.append({"dropped": ind, "spearman_vs_baseline": rho,
                         f"top{top_n}_overlap": len(base_top & alt_top) / top_n})
    return pd.DataFrame(rows)


def build(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    scored = df.merge(score(df), on="cbsa_code")
    stab = rank_stability(df)
    scored = scored.merge(stab, on="cbsa_code", how="left")
    ranked = scored.dropna(subset=["opportunity_index"])
    aff_med, mom_med = ranked["affordability_score"].median(), ranked["momentum_score"].median()
    scored["archetype"] = scored.apply(archetype, axis=1, args=(aff_med, mom_med))
    scored["size_band"] = scored["population"].map(size_band)
    scored = scored.sort_values("rank", na_position="last").reset_index(drop=True)
    return scored, leave_one_out(df)


# ---------------- report ----------------

def _pct(v, signed=False):
    return "" if pd.isna(v) else (f"{v:+.1%}" if signed else f"{v:.0%}")


def _money(v):
    return "" if pd.isna(v) else f"${v:,.0f}"


def _table(rows: pd.DataFrame) -> list[str]:
    lines = ["| Rank | Metro | Score | Rent / income | Mortgage / income | Job growth / yr | "
             "Paycheck vs prices / yr | Rank range (90%) |",
             "|---|---|---|---|---|---|---|---|"]
    for _, r in rows.iterrows():
        lines.append(
            f"| {int(r['rank'])} | {r['cbsa_title']} | {r['opportunity_index']:.0f} | "
            f"{_pct(r['rent_to_income'])} | {_pct(r['mortgage_to_income'])} | "
            f"{_pct(r['job_growth_3y'], True)} | {_pct(r['paycheck_vs_prices_3y'], True)} | "
            f"{int(r['rank_p05'])}-{int(r['rank_p95'])} |")
    return lines


def not_ranked_reason(r: pd.Series) -> str:
    if r["state"] == "PR":
        return "Puerto Rico: Zillow and IRS migration data don't cover it"
    if r["state"] == "CT":
        return ("Connecticut: BLS switched from counties to planning regions in 2024, "
                "so 3-year job and wage growth can't be compared yet")
    if pd.isna(r["home_value"]):
        return "No Zillow series (Zillow folds this area into a neighboring metro)"
    return "Missing a full pillar of data"


def _not_ranked(scored: pd.DataFrame) -> list[str]:
    missing = scored[scored["opportunity_index"].isna()].copy()
    if missing.empty:
        return []
    missing["reason"] = missing.apply(not_ranked_reason, axis=1)
    lines = ["", f"## Not ranked ({len(missing)} metros)", "", "| Reason | Metros |", "|---|---|"]
    for reason, g in missing.groupby("reason"):
        lines.append(f"| {reason} | {', '.join(g['cbsa_title'])} |")
    return lines


def write_report(scored: pd.DataFrame, loo: pd.DataFrame) -> None:
    ranked = scored.dropna(subset=["opportunity_index"])
    meta = scored.iloc[0]
    n, n_all = len(ranked), len(scored)
    robust = ranked[ranked["share_top25"] >= 0.8]
    lines = [
        "# CityLens Opportunity Index", "",
        f"**{n} of {n_all} U.S. metropolitan areas scored.** Housing as of "
        f"{meta['housing_end']:%b %Y}; jobs and wages as of {meta['jobs_end']:%b %Y}; "
        f"migration {int(meta['migration_end']) - 2}-{int(meta['migration_end'])}; "
        f"permits {int(meta['permits_end']) - 2}-{int(meta['permits_end'])}.", "",
        "**Question:** where does a typical paycheck go furthest today, in a place that is still growing?", "",
        "## How it's scored", "",
        "| Pillar | Weight | Indicators |", "|---|---|---|",
    ]
    for p, cfg in PILLARS.items():
        inds = ", ".join(INDICATOR_LABELS[i] for i in cfg["indicators"])
        lines.append(f"| {PILLAR_LABELS[p]} | {cfg['weight']:.0%} | {inds} |")
    lines += ["", "Each indicator is converted to a 0-100 percentile rank (100 = best), pillars average "
              "their indicators, and the index is the weighted sum. Metros missing an entire pillar are "
              "not ranked.", "", "## Top 20 overall", ""]
    lines += _table(ranked.head(20))

    for _, label in SIZE_BANDS:
        band = ranked[ranked["size_band"] == label]
        if not band.empty:
            lines += ["", f"## Top 10: {label} metros", ""] + _table(band.head(10))

    lines += ["", "## Bottom 10 overall", ""] + _table(ranked.tail(10))
    lines += _not_ranked(scored)

    counts = ranked["archetype"].value_counts()
    lines += ["", "## Four kinds of metros", "",
              "Split at the median affordability and momentum scores:", "",
              "| Archetype | Metros | Meaning |", "|---|---|---|"]
    meaning = {"Rising & Affordable": "Growing and still within reach: the sweet spot",
               "Rising but Pricey": "Strong growth, but costs already high",
               "Affordable but Slowing": "Within reach, but growth is lagging",
               "Squeezed": "Expensive and slowing"}
    for a in meaning:
        lines.append(f"| {a} | {counts.get(a, 0)} | {meaning[a]} |")
    big_sweet = ranked[(ranked["archetype"] == "Rising & Affordable") & (ranked["size_band"] == "Large (1M+)")]
    if not big_sweet.empty:
        lines += ["", "**Large metros in the sweet spot:** " + ", ".join(big_sweet["cbsa_title"].head(12)) + "."]

    lines += ["", "## Does the ranking hold up?", "",
              f"**Random weights.** Every metro was re-ranked under {N_SIMULATIONS:,} random pillar "
              "weightings, drawn evenly from every possible mix. "
              f"**{len(robust)} metros stay in the top 25 in at least 80% of them**, so they rank "
              "highly no matter how you weight the pillars:", ""]
    for _, r in robust.head(15).iterrows():
        lines.append(f"- {r['cbsa_title']}: top 25 in {r['share_top25']:.0%} of weightings "
                     f"(median rank {int(r['rank_median'])})")
    lines += ["", "**Drop one indicator.** Re-scoring without each indicator in turn:", "",
              "| Indicator removed | Rank correlation with baseline | Top-25 overlap |", "|---|---|---|"]
    for _, r in loo.iterrows():
        lines.append(f"| {INDICATOR_LABELS[r['dropped']]} | {r['spearman_vs_baseline']:.2f} | {r['top25_overlap']:.0%} |")
    lines += ["", "A rank correlation near 1.0 means removing that input barely changes the ordering.", "",
              "## Caveats", "",
              "- Rent and mortgage ratios use the area's median household income, not any one person's.",
              "- Mortgage payment is principal and interest only (20% down, 30-year fixed); taxes and insurance are excluded.",
              "- Migration data ends in " + str(int(meta["migration_end"])) + " (the IRS publishes about two years late), "
              "and the latest year uses the IRS's new matching method.",
              "- Ranks within a few places of each other are effectively ties; see the 90% rank range."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> pd.DataFrame:
    df = load_features()
    scored, loo = build(df)
    scored.to_parquet(OUT, index=False)
    write_report(scored, loo)
    n = scored["opportunity_index"].notna().sum()
    record_run("opportunity_index", int(n), str(scored["housing_end"].iloc[0])[:7])
    log.info("Opportunity Index: %s metros ranked. Top 5: %s", n,
             "; ".join(scored.head(5)["cbsa_title"]))
    log.info("Saved data/marts/opportunity_index.parquet and docs/opportunity_index_report.md")
    return scored


if __name__ == "__main__":
    run()
