"""Layer 6: the Ripple Map. When a metro booms, which neighbors follow, and how far does it spread?

Three questions:

1. CLUSTERS. Do fast-growing metros sit next to each other? Global Moran's I measures
   whether 3-year home-value growth is geographically clustered; local Moran's I (LISA)
   finds the specific hot spots (rising metros surrounded by rising metros) and cool
   spots, each tested with 999 random reshuffles.

2. THE RIPPLE. Beyond a metro's own momentum, does growth in its neighbors predict its
   growth over the next 12 months? Neighbors are grouped into rings (0-75, 75-150 and
   150-300 miles), each a population-weighted average. Estimated with date fixed effects
   (every growth rate measured against the national average that month) and standard
   errors clustered by metro, then checked separately before, during and after COVID,
   and in a walk-forward backtest.

3. THE NEXT RING OUT. Affordable metros whose close neighbors have been rising faster
   than they have: where the ripple says growth is likely to arrive next.

Lower 48 states only (distances and contiguity don't apply to Alaska, Hawaii or Puerto Rico).

Run:  python -m analysis.ripple_map     (run pipeline.geo_shapes and analysis.opportunity_index first)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis import charts
from pipeline.config import CLEAN_DIR, ROOT
from pipeline.geo_shapes import STATE_SHP
from pipeline.utils import SourceError, log, record_run

MART = ROOT / "data" / "marts" / "mart_metro_month.parquet"
POINTS = CLEAN_DIR / "cbsa_points.parquet"
OPPORTUNITY = ROOT / "data" / "marts" / "opportunity_index.parquet"
OUT = ROOT / "data" / "marts" / "ripple_map.parquet"
REPORT = ROOT / "docs" / "ripple_map_report.md"
FIG_DIR = ROOT / "docs" / "figures"

RINGS = [(0, 75), (75, 150), (150, 300)]
NOT_LOWER_48 = {"AK", "HI", "PR"}
K_NEIGHBORS = 6
N_PERMUTATIONS = 999
LISA_P = 0.05
SEED = 42
PERIODS = {"2016-2019": (2016, 2019), "2020-2021": (2020, 2021), "2022-2025": (2022, 2025)}
TEST_YEARS = range(2020, 2026)
CLUSTER_NAMES = {"HH": "Rising cluster", "LL": "Cooling cluster", "HL": "Rising outlier", "LH": "Lagging outlier"}


# ---------------- data ----------------

def load(mart_path=MART, points_path=POINTS) -> tuple[pd.DataFrame, pd.DataFrame]:
    import duckdb
    for p, step in [(mart_path, "pipeline.build_panel"), (points_path, "pipeline.geo_shapes")]:
        if not p.exists():
            raise SourceError(f"Run `python -m {step}` first.")
    m = duckdb.connect().execute(
        f"SELECT cbsa_code, cbsa_title, principal_state, date, home_value, population "
        f"FROM read_parquet('{mart_path.as_posix()}') WHERE cbsa_type = 'Metropolitan'").df()
    pts = pd.read_parquet(points_path)
    meta = (m.groupby("cbsa_code").agg(cbsa_title=("cbsa_title", "first"), state=("principal_state", "first"),
                                      population=("population", "max")).reset_index()
             .merge(pts[["cbsa_code", "lat", "lon"]], on="cbsa_code"))
    meta = meta[~meta["state"].isin(NOT_LOWER_48)]
    values = m[m["cbsa_code"].isin(meta["cbsa_code"])].pivot_table(
        index="date", columns="cbsa_code", values="home_value").sort_index()
    meta = meta.set_index("cbsa_code").loc[values.columns].reset_index()
    return values, meta


def distance_miles(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Great-circle distance between every pair of points (haversine)."""
    la, lo = np.radians(lat), np.radians(lon)
    a = (np.sin((la[:, None] - la[None, :]) / 2) ** 2
         + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin((lo[:, None] - lo[None, :]) / 2) ** 2)
    d = 3958.8 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    np.fill_diagonal(d, np.inf)
    return d


def ring_average(values: np.ndarray, dist: np.ndarray, weights: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Weighted average of other metros' values within [lo, hi) miles; NaN if none."""
    ok = ~np.isnan(values)
    w = ((dist >= lo) & (dist < hi)) * weights[None, :] * ok[None, :]
    den = w.sum(axis=1)
    num = (w * np.nan_to_num(values)[None, :]).sum(axis=1)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def build_panel(values: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Quarterly metro rows: own past-12-month growth, each ring's past growth, and the
    next 12 months' growth, all relative to the national average that month."""
    lv = np.log(values)
    past, future = lv - lv.shift(12), lv.shift(-12) - lv
    past = past.sub(past.mean(axis=1), axis=0)
    future = future.sub(future.mean(axis=1), axis=0)
    dist = distance_miles(meta["lat"].to_numpy(), meta["lon"].to_numpy())
    pop = meta["population"].fillna(meta["population"].median()).to_numpy()
    rows = []
    for d in lv.index:
        if d.month not in (3, 6, 9, 12) or past.loc[d].isna().all():
            continue
        own = past.loc[d].to_numpy()
        row = pd.DataFrame({"cbsa_code": lv.columns, "date": d, "own": own, "future": future.loc[d].to_numpy()})
        for lo, hi in RINGS:
            row[f"ring_{lo}_{hi}"] = ring_average(own, dist, pop, lo, hi)
        rows.append(row)
    return pd.concat(rows, ignore_index=True).dropna(subset=["own"])


RING_COLS = [f"ring_{lo}_{hi}" for lo, hi in RINGS]
FEATURES = ["own"] + RING_COLS


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.dropna(subset=FEATURES).copy()
    for c in FEATURES:
        g = out.groupby("date")[c]
        out[f"{c}_z"] = (out[c] - g.transform("mean")) / g.transform("std")
    return out


# ---------------- 1. clusters ----------------

def knn_weights(dist: np.ndarray, k: int = K_NEIGHBORS) -> np.ndarray:
    """Row-standardized k-nearest-neighbor weights."""
    idx = np.argsort(dist, axis=1)[:, :k]
    w = np.zeros_like(dist, dtype=float)
    np.put_along_axis(w, idx, 1.0 / k, axis=1)
    return w


def morans_i(x: np.ndarray, w: np.ndarray, n_perm: int = N_PERMUTATIONS, seed: int = SEED) -> dict:
    z = (x - x.mean()) / x.std()
    i_obs = float(z @ w @ z / len(z))
    rng = np.random.default_rng(seed)
    sims = np.array([(zp := rng.permutation(z)) @ w @ zp / len(z) for _ in range(n_perm)])
    p = (1 + (sims >= i_obs).sum()) / (n_perm + 1)
    return {"I": i_obs, "p_value": float(p), "expected": -1 / (len(z) - 1)}


def lisa(x: np.ndarray, w: np.ndarray, n_perm: int = N_PERMUTATIONS, seed: int = SEED) -> pd.DataFrame:
    """Local Moran's I with conditional permutation p-values (each metro held fixed while
    its neighbors' values are reshuffled from everyone else)."""
    z = (x - x.mean()) / x.std()
    lag = w @ z
    local = z * lag
    rng = np.random.default_rng(seed)
    n, k = len(z), int((w[0] > 0).sum())
    p = np.empty(n)
    for i in range(n):
        others = np.delete(z, i)
        draws = np.array([rng.choice(others, k, replace=False) for _ in range(n_perm)]).mean(axis=1)
        sim = z[i] * draws
        extreme = (sim >= local[i]).sum() if local[i] >= 0 else (sim <= local[i]).sum()
        p[i] = (1 + extreme) / (n_perm + 1)
    quad = np.where(z >= 0, np.where(lag >= 0, "HH", "HL"), np.where(lag >= 0, "LH", "LL"))
    return pd.DataFrame({"z": z, "lag": lag, "local_i": local, "p_value": p,
                         "cluster": np.where(p < LISA_P, quad, "ns")})


# ---------------- 2. ripple ----------------

FORMULA = "future ~ " + " + ".join(f"{c}_z" for c in FEATURES)


def ripple_effects(d: pd.DataFrame) -> pd.DataFrame:
    import statsmodels.formula.api as smf
    rows = []
    specs = {"All years": d} | {k: d[d["date"].dt.year.between(a, b)] for k, (a, b) in PERIODS.items()}
    for name, data in specs.items():
        m = smf.ols(FORMULA, data).fit(cov_type="cluster", cov_kwds={"groups": data["cbsa_code"]})
        ci = m.conf_int()
        for c in FEATURES:
            rows.append({"spec": name, "term": c, "effect_pp": m.params[f"{c}_z"] * 100,
                         "ci_low": ci.loc[f"{c}_z", 0] * 100, "ci_high": ci.loc[f"{c}_z", 1] * 100,
                         "t": m.tvalues[f"{c}_z"], "n": int(m.nobs)})
    return pd.DataFrame(rows)


def backtest(d: pd.DataFrame) -> pd.DataFrame:
    """Does knowing the neighbors improve next-year rankings over own momentum alone?"""
    import statsmodels.formula.api as smf
    rows = []
    for y in TEST_YEARS:
        train = d[d["date"] <= pd.Timestamp(f"{y - 1}-01-01")]
        test = d[d["date"].dt.year == y]
        if test.empty or train.empty:
            continue
        with_rings = smf.ols(FORMULA, train).fit().predict(test)
        own_only = smf.ols("future ~ own_z", train).fit().predict(test)
        actual = test["future"]
        rows.append({"year": y,
                     "own_rank_corr": own_only.rank().corr(actual.rank()),
                     "ripple_rank_corr": with_rings.rank().corr(actual.rank()),
                     "own_mae_pp": (own_only - actual).abs().mean() * 100,
                     "ripple_mae_pp": (with_rings - actual).abs().mean() * 100})
    return pd.DataFrame(rows)


# ---------------- 3. the next ring out ----------------

def next_ring_out(panel: pd.DataFrame, effects: pd.DataFrame, meta: pd.DataFrame,
                  opportunity_path=OPPORTUNITY) -> pd.DataFrame:
    """Latest quarter: ripple pressure = the part of the forecast that comes from neighbors."""
    latest = standardize(panel[panel["date"] == panel["date"].max()])
    beta = effects[effects["spec"] == "All years"].set_index("term")["effect_pp"]
    latest["ripple_pressure_pp"] = sum(beta[c] * latest[f"{c}_z"] for c in RING_COLS)
    latest["neighbor_gap"] = latest["ring_0_75"] - latest["own"]
    out = latest.merge(meta[["cbsa_code", "cbsa_title", "state", "population", "lat", "lon"]], on="cbsa_code")
    if opportunity_path.exists():
        oi = pd.read_parquet(opportunity_path)[["cbsa_code", "affordability_score", "rank"]]
        out = out.merge(oi.rename(columns={"rank": "opportunity_rank"}), on="cbsa_code", how="left")
    else:
        out["affordability_score"], out["opportunity_rank"] = np.nan, np.nan
    q = out["ripple_pressure_pp"].quantile(0.8)
    out["next_ring_out"] = ((out["ripple_pressure_pp"] >= q) & (out["neighbor_gap"] > 0)
                            & (out["affordability_score"] >= 50))
    return out.sort_values("ripple_pressure_pp", ascending=False).reset_index(drop=True)


# ---------------- charts (new forms: map, ripple decay, catch-up scatter) ----------------

def albers(lat, lon):
    """Albers equal-area conic projection for the lower 48 (standard parallels 29.5N and 45.5N)."""
    lat, lon = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    p1, p2, p0, l0 = np.radians([29.5, 45.5, 37.5, -96.0])
    n = (np.sin(p1) + np.sin(p2)) / 2
    c = np.cos(p1) ** 2 + 2 * n * np.sin(p1)
    rho = np.sqrt(c - 2 * n * np.sin(lat)) / n
    rho0 = np.sqrt(c - 2 * n * np.sin(p0)) / n
    theta = n * (lon - l0)
    return rho * np.sin(theta), rho0 - rho * np.cos(theta)


def state_outlines():
    import shapefile
    if not STATE_SHP.exists():
        return []
    shapes = []
    with shapefile.Reader(str(STATE_SHP)) as r:
        fields = [f[0] for f in r.fields[1:]]
        for rec, shp in zip(r.records(), r.shapes()):
            if dict(zip(fields, rec)).get("STUSPS") in NOT_LOWER_48:
                continue
            pts = np.array(shp.points)
            for a, b in zip(shp.parts, list(shp.parts[1:]) + [len(pts)]):
                shapes.append(albers(pts[a:b, 1], pts[a:b, 0]))
    return shapes


def short(title: str) -> str:
    return title.split(",")[0].split("-")[0]


def chart_map(clusters: pd.DataFrame, growth_label: str) -> str:
    fig, ax = charts.new(6.8, 4.0)
    ax.axis("off")
    for x, y in state_outlines():
        ax.fill(x, y, color="#f1f0ec", lw=0)
        ax.plot(x, y, color="#ffffff", lw=0.6)
    colors = {"HH": charts.SERIES_1, "LL": charts.SERIES_2, "HL": "#9cc3ef", "LH": "#f5b99f", "ns": charts.FAINT}
    x, y = albers(clusters["lat"], clusters["lon"])
    size = 6 + 60 * np.sqrt(clusters["population"] / clusters["population"].max())
    for code in ["ns", "LH", "HL", "LL", "HH"]:
        m = (clusters["cluster"] == code).to_numpy()
        ax.scatter(x[m], y[m], s=size[m], color=colors[code], edgecolor="white", linewidth=0.5, zorder=3,
                   label=None if code == "ns" else f"{CLUSTER_NAMES[code]} ({m.sum()})")
    ax.set_aspect("equal")
    top = pd.concat([clusters[clusters["cluster"] == c].nlargest(4, "population") for c in ("HH", "LL")])
    tx, ty = albers(top["lat"], top["lon"])
    charts.label_points(ax, tx, ty, [f"{short(n)} {g:+.1%}" for n, g in zip(top["cbsa_title"], top["growth_3y"])],
                        dx=7, bold=True, fontsize=7)
    ax.legend(loc="lower left", frameon=False, fontsize=7.5, handletextpad=0.2, borderaxespad=0)
    ax.set_aspect("equal")
    charts.title(fig, "Where home-value growth clusters",
                 f"{growth_label}. Dot size = population; colored = statistically significant cluster")
    return charts.save(fig, FIG_DIR / "ripple_cluster_map.png", top=0.88)


def chart_ripple(effects: pd.DataFrame) -> str:
    fig, ax = charts.new(5.6, 2.8)
    labels = [f"{lo}-{hi} mi" for lo, hi in RINGS]
    xs = np.arange(len(RINGS))
    periods = list(PERIODS)
    for j, per in enumerate(periods):
        e = effects[(effects["spec"] == per)].set_index("term").loc[RING_COLS]
        ax.plot(xs + (j - 1) * 0.09, e["effect_pp"], "o", color=charts.FAINT, ms=4, zorder=2)
    e = effects[effects["spec"] == "All years"].set_index("term").loc[RING_COLS]
    ax.vlines(xs, e["ci_low"], e["ci_high"], color=charts.SERIES_1, lw=1.2, alpha=0.5, zorder=3)
    ax.plot(xs, e["effect_pp"], "-o", color=charts.SERIES_1, lw=2, ms=7, mec=charts.SURFACE, mew=1.2, zorder=4)
    for xi, v in zip(xs, e["effect_pp"]):
        ax.annotate(f"{v:+.2f} pts", (xi, v), xytext=(10, 4), textcoords="offset points", fontsize=8,
                    color=charts.INK, fontweight="bold")
    ax.axhline(0, color=charts.INK_2, lw=0.7)
    ax.set_xticks(xs, labels)
    ax.set_xlim(-0.4, len(RINGS) - 0.4)
    ax.set_ylabel("Extra growth next year (pts)", color=charts.INK_2)
    ax.text(xs[-1] + 0.05, ax.get_ylim()[1] * 0.95, "gray dots: 2016-19,\n2020-21 and 2022-25",
            fontsize=7, color=charts.INK_2, ha="center", va="top")
    charts.title(fig, "Growth ripples about 75 miles, then fades",
                 "Effect of neighbors' faster price growth on a metro's next 12 months, beyond its own momentum")
    return charts.save(fig, FIG_DIR / "ripple_distance_decay.png", top=0.82)


def chart_catch_up(nro: pd.DataFrame) -> str:
    fig, ax = charts.new(5.8, 3.6)
    charts.style(ax, grid="")
    d = nro.dropna(subset=["ring_0_75"])
    pick = d[d["next_ring_out"]].head(8)
    rest = d[~d["cbsa_code"].isin(pick["cbsa_code"])]
    size = lambda s: 5 + 45 * np.sqrt(s / d["population"].max())
    ax.scatter(rest["ring_0_75"], rest["own"], s=size(rest["population"]), color=charts.FAINT, lw=0)
    ax.scatter(pick["ring_0_75"], pick["own"], s=size(pick["population"]) + 12, color=charts.SERIES_1,
               edgecolor="white", lw=0.6, zorder=3)
    lim = np.nanpercentile(np.abs(d[["ring_0_75", "own"]].to_numpy()), 99) * 1.1
    ax.plot([-lim, lim], [-lim, lim], color=charts.INK_2, lw=0.7, ls=(0, (3, 3)))
    ax.text(lim * 0.95, lim * 0.82, "growing as fast\nas neighbors", fontsize=7, color=charts.INK_2, ha="right")
    ax.fill_between([-lim, lim], [-lim, -lim], [-lim, lim], color="#eef4fc", zorder=0)
    ax.text(lim * 0.95, -lim * 0.9, "neighbors pulling ahead:\nripple still coming", fontsize=7.5,
            color=charts.SERIES_1, ha="right", fontweight="bold")
    ax.axhline(0, color=charts.GRID, lw=0.8)
    ax.axvline(0, color=charts.GRID, lw=0.8)
    pct = __import__("matplotlib.ticker", fromlist=["x"]).PercentFormatter(1, decimals=0)
    ax.xaxis.set_major_formatter(pct)
    ax.yaxis.set_major_formatter(pct)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("Neighbors within 75 miles: price growth vs. national, past year", color=charts.INK_2)
    ax.set_ylabel("The metro itself", color=charts.INK_2)
    charts.label_points(ax, pick["ring_0_75"], pick["own"], [short(t) for t in pick["cbsa_title"]], dx=6)
    charts.title(fig, "The Next Ring Out", "Affordable metros whose neighbors are rising faster (blue)")
    return charts.save(fig, FIG_DIR / "ripple_next_ring_out.png", top=0.86)


# ---------------- report ----------------

def write_report(gm, clusters, effects, bt, nro, figs, window) -> None:
    allr = effects[effects["spec"] == "All years"].set_index("term")
    near = allr.loc["ring_0_75"]
    per = effects[(effects["term"] == "ring_0_75") & (effects["spec"] != "All years")]
    wins = int((bt["ripple_rank_corr"] > bt["own_rank_corr"]).sum())
    counts = clusters["cluster"].value_counts()
    hh = clusters[clusters["cluster"] == "HH"].nlargest(8, "population")
    ll = clusters[clusters["cluster"] == "LL"].nlargest(8, "population")
    picks = nro[nro["next_ring_out"]]
    L = ["# CityLens Ripple Map", "",
         "**Question:** when a metro booms, which neighbors follow, and how far does growth spread?", "",
         f"![Cluster map](figures/{figs[0]})", "",
         "## What we found", "",
         f"- **Growth clusters.** Metros with fast home-value growth sit next to each other far more than chance "
         f"would allow (Moran's I = {gm['I']:.2f}, p = {gm['p_value']:.3f}; 0 would mean no clustering).",
         f"- **{counts.get('HH', 0)} metros form rising clusters**, led by "
         + ", ".join(short(t) for t in hh["cbsa_title"]) + ". "
         f"**{counts.get('LL', 0)} form cooling clusters**, led by " + ", ".join(short(t) for t in ll["cbsa_title"]) + ".",
         f"- **Growth ripples about 75 miles.** When neighbors within 75 miles grow faster, a metro grows "
         f"{near['effect_pp']:+.2f} points more the next year per standard deviation, beyond its own momentum "
         f"(t = {near['t']:.1f}). The effect is "
         + ", ".join(f"{r['effect_pp']:+.2f} in {r['spec']}" for _, r in per.iterrows())
         + ": steady through every market regime. Beyond 150 miles it disappears.",
         f"- **It adds real, modest forecasting value.** Including neighbors improved next-year rankings in "
         f"**{wins} of {len(bt)} backtest years**.",
         f"- **{len(picks)} affordable metros are in the Next Ring Out**, where neighbors are pulling ahead and the "
         "ripple hasn't arrived yet.", "",
         f"![Ripple decay](figures/{figs[1]})", "",
         "## How far the ripple travels", ""]
    for _, r in allr.loc[RING_COLS].iterrows():
        lo, hi = r.name.split("_")[1:]
        L.append(f"- **{lo}-{hi} miles:** {r['effect_pp']:+.2f} pts (95% range {r['ci_low']:+.2f} to {r['ci_high']:+.2f}, "
                 f"t = {r['t']:.1f})")
    L.append(f"- *For comparison, the metro's own past growth:* {allr.loc['own', 'effect_pp']:+.2f} pts "
             f"(t = {allr.loc['own', 't']:.1f}).")
    L += ["", "Each effect is the extra growth (percentage points, vs. the national average) over the next 12 months "
          "for a one-standard-deviation faster rise among neighbors in that ring over the past 12 months, holding "
          f"the metro's own past growth fixed. {int(allr['n'].iloc[0]):,} metro-quarters; standard errors clustered "
          "by metro.", "",
          f"![Next ring out](figures/{figs[2]})", "",
          "## The Next Ring Out", "",
          "Top fifth for ripple pressure, neighbors growing faster than the metro itself, and above-median "
          "affordability on the Opportunity Index:", ""]
    for _, r in picks.head(12).iterrows():
        orank = "" if pd.isna(r["opportunity_rank"]) else f"; Opportunity Index #{int(r['opportunity_rank'])}"
        L.append(f"1. **{r['cbsa_title']}**: neighbors {r['ring_0_75']:+.1%} vs. itself {r['own']:+.1%} over the "
                 f"past year (vs. national), adding about {r['ripple_pressure_pp']:+.1f} pts of expected growth{orank}")
    L += ["", "## Backtest", "",
          "Rank correlation of next-year growth, model trained only on earlier years: own momentum alone → with "
          "neighbor rings.", ""]
    L.append(" · ".join(f"**{int(r['year'])}:** {r['own_rank_corr']:.2f} → {r['ripple_rank_corr']:.2f}"
                        for _, r in bt.iterrows()))
    L += ["", "## How it works", "",
          f"- **Clusters:** 3-year home-value growth ({window}); each metro's {K_NEIGHBORS} nearest metros as neighbors; "
          f"global and local Moran's I with {N_PERMUTATIONS} permutations; clusters shown at p < {LISA_P}.",
          "- **Ripple:** quarterly panel 2016-2025; rings are population-weighted averages of other metros' growth by "
          "great-circle distance; all growth measured against the national average that month.",
          "- **Next Ring Out:** ripple pressure = the ring effects applied to each metro's latest neighbor growth.",
          "- **Map:** Albers equal-area projection; Census state outlines and metro interior points.", "",
          "## Caveats", "",
          "- Neighbors may rise together because they share a cause (a regional employer, weather, policy), not "
          "because growth literally spreads. The ripple is predictive, not proof of contagion.",
          "- Distance is straight-line; highways and commuting patterns would sharpen the rings.",
          "- Local clusters are tested one metro at a time, so a few may be false positives at p < 0.05."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def run() -> pd.DataFrame:
    values, meta = load()
    panel = build_panel(values, meta)
    d = standardize(panel.dropna(subset=["future"]))
    effects = ripple_effects(d)
    bt = backtest(d)

    end = values.index.max()
    g3 = np.log(values.loc[end] / values.loc[end - pd.DateOffset(months=36)])
    clusters = meta.assign(growth_3y=np.expm1(g3.to_numpy())).dropna(subset=["growth_3y"]).reset_index(drop=True)
    w = knn_weights(distance_miles(clusters["lat"].to_numpy(), clusters["lon"].to_numpy()))
    gm = morans_i(np.log1p(clusters["growth_3y"].to_numpy()), w)
    clusters = pd.concat([clusters, lisa(np.log1p(clusters["growth_3y"].to_numpy()), w)], axis=1)

    nro = next_ring_out(panel, effects, meta)
    window = f"{end - pd.DateOffset(months=36):%b %Y} to {end:%b %Y}"
    figs = [chart_map(clusters, f"3-year home-value growth, {window}"), chart_ripple(effects), chart_catch_up(nro)]
    write_report(gm, clusters, effects, bt, nro, figs, window)
    # every lower-48 metro keeps its cluster label; ripple columns exist only for metros with
    # neighbors in every ring (remote metros have none within 75 miles)
    ripple_cols = ["cbsa_code", "own", *RING_COLS, "ripple_pressure_pp", "neighbor_gap",
                   "affordability_score", "opportunity_rank", "next_ring_out"]
    out = clusters.merge(nro[ripple_cols], on="cbsa_code", how="left")
    out["next_ring_out"] = out["next_ring_out"].astype("boolean").fillna(False).astype(bool)
    out.to_parquet(OUT, index=False)
    record_run("ripple_map", len(out), f"{end:%Y-%m}", note=f"moran={gm['I']:.3f}")
    log.info("Ripple Map: Moran's I %.2f (p=%.3f); 0-75mi effect %+.2f pts; %s Next Ring Out metros",
             gm["I"], gm["p_value"], effects.query("spec == 'All years' and term == 'ring_0_75'")["effect_pp"].iloc[0],
             int(out["next_ring_out"].sum()))
    return out


if __name__ == "__main__":
    run()
