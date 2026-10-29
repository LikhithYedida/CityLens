"""CityLens decision app.

  Overview         where prices are heading, the five headline findings and the largest metros
  Where to live    which metros fit a household budget, and what is left each month
  Where to build   ranked markets for builders and lenders, with a robustness check
  Metro profile    one metro against its peers and the nation, with its price history
  Methods          how each model was validated, data freshness and known limits

Reads the files written by `python -m analysis.scorecard`.
Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("CITYLENS_DATA_DIR", ROOT / "data" / "marts"))
REPO = "https://github.com/LikhithYedida/CityLens/blob/main"

NAVY, BLUE, ORANGE, TEAL, GRAY = "#1f3b63", "#2a78d6", "#eb6834", "#1baf7a", "#c3c8d0"
INK, INK_2 = "#1f2a37", "#5b6472"
STATUS_COLORS = {"Rising City": BLUE, "Next Ring Out": TEAL, "Cooling Boomtown": ORANGE, "": GRAY}
SIZE_LABELS = {"Large (1M+)": "Large, over 1 million people",
               "Mid-size (250K-1M)": "Midsize, 250,000 to 1 million people",
               "Small (under 250K)": "Small, under 250,000 people"}
SIZE_SHORT = {"Large (1M+)": "large", "Mid-size (250K-1M)": "midsize", "Small (under 250K)": "small"}
STATUS_TEXT = {
    "Rising City": "Home prices likely to outgrow the national market next year, backed by job growth.",
    "Next Ring Out": "Nearby metros are rising faster, and growth tends to spread within 75 miles.",
    "Cooling Boomtown": "Drew many new residents in recent years, but prices have stalled or fallen.",
}
STATUS_PLURAL = {"Rising City": "Rising Cities", "Next Ring Out": "Next Ring Out",
                 "Cooling Boomtown": "Cooling Boomtowns"}

st.set_page_config(page_title="CityLens", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1320px;}
header[data-testid="stHeader"], [data-testid="stHeaderActionElements"], [data-testid="stToolbar"] {display: none;}
.cl-top {display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e3e7ee;
  padding: 4px 0 12px 0; margin-bottom: 26px;}
.cl-logo {display: flex; align-items: center; font-size: 1.55rem; font-weight: 700; color: #1f3b63;
  letter-spacing: -0.4px;}
.cl-mark {position: relative; width: 22px; height: 22px; border: 4px solid #2a78d6; border-radius: 50%;
  box-sizing: border-box; margin-right: 12px;}
.cl-mark::after {content: ""; position: absolute; width: 9px; height: 4px; background: #2a78d6; border-radius: 2px;
  right: -8px; bottom: -4px; transform: rotate(45deg);}
.cl-tag {text-align: right; color: #5b6472; font-size: 0.85rem; line-height: 1.35;}
.cl-tag b {color: #1f2a37; font-weight: 600;}
.cl-kpi .val.txt {font-size: 1.3rem; padding: 6px 0 2px 0;}
.cl-kpis.slim {margin-top: 6px;}
.cl-table {width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 4px 0 6px 0;}
.cl-table th {text-align: left; color: #5b6472; font-weight: 600; font-size: 0.8rem; padding: 8px 10px;
  border-bottom: 1px solid #d9dee6; background: #f7f8fa;}
.cl-table td {padding: 9px 10px; border-bottom: 1px solid #eef0f3; color: #2c3440; vertical-align: top;
  line-height: 1.45;}
.cl-table td.n, .cl-table th.n {text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap;}
.cl-table td:first-child {font-weight: 600; color: #1f2a37;}
.cl-h3 {font-weight: 600; color: #1f2a37; font-size: 1.02rem; margin: 18px 0 2px 0;}
.cl-h3 + .cl-note {margin-bottom: 6px;}
h2, h3 {color: #1f2a37; letter-spacing: -0.2px;}
[data-testid="stMetric"] {background: #ffffff; border: 1px solid #e3e7ee; border-radius: 10px;
  padding: 14px 18px 12px 18px;}
[data-testid="stMetricLabel"] p {color: #5b6472; font-size: 0.85rem;}
[data-testid="stMetricValue"] {color: #1f2a37;}
.cl-h1 {font-size: 2.35rem; font-weight: 700; color: #1f3b63; line-height: 1.15; margin: 6px 0 10px 0;
  letter-spacing: -0.6px;}
.cl-lede {color: #3c4552; font-size: 1.06rem; line-height: 1.55; max-width: 900px;}
.cl-meta {color: #8a93a1; font-size: 0.82rem; margin: 10px 0 18px 0;}
.cl-kpis {display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px;}
.cl-kpi {border: 1px solid #e3e7ee; border-radius: 10px; padding: 14px 18px; background: #fff;
  border-top: 3px solid var(--accent, #1f3b63);}
.cl-kpi .lab {color: #5b6472; font-size: 0.84rem;}
.cl-kpi .val {color: #1f2a37; font-size: 1.9rem; font-weight: 700; line-height: 1.25; margin-top: 2px;}
.cl-kpi .val small {font-size: 1rem; color: #8a93a1; font-weight: 600;}
.cl-kpi .ctx {color: #6b7280; font-size: 0.82rem; line-height: 1.4; margin-top: 2px;}
.cl-grid {display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;}
.cl-card {border: 1px solid #e3e7ee; border-radius: 10px; padding: 16px 18px; background: #ffffff;
  display: flex; flex-direction: column;}
.cl-card .num {font-size: 1.6rem; font-weight: 700; color: #1f3b63; line-height: 1.2;}
.cl-card .head {font-weight: 600; color: #1f2a37; margin: 6px 0 6px 0; font-size: 0.99rem;}
.cl-card .body {color: #4a5361; font-size: 0.9rem; line-height: 1.5; flex-grow: 1;}
.cl-card a {font-size: 0.82rem; color: #2a78d6; text-decoration: none; margin-top: 10px;}
.cl-watch {border: 1px solid #e3e7ee; border-radius: 10px; padding: 6px 16px 10px 16px; background: #fff;}
.cl-watch .grp {font-weight: 600; color: #1f2a37; font-size: 0.92rem; margin-top: 10px;}
.cl-watch .grp i {display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px;}
.cl-watch .def {color: #6b7280; font-size: 0.8rem; line-height: 1.35; margin: 2px 0 4px 0;}
.cl-watch table {width: 100%; border-collapse: collapse; font-size: 0.86rem;}
.cl-watch td {padding: 3px 0; color: #3c4552; border-bottom: 1px solid #f0f2f5;}
.cl-watch td.n {text-align: right; font-variant-numeric: tabular-nums; color: #1f2a37;}
.cl-watch .hd td {color: #8a93a1; font-size: 0.75rem; border-bottom: none; padding-bottom: 0;}
.cl-note {color: #6b7280; font-size: 0.85rem; line-height: 1.5;}
.cl-key {display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin: 0 6px 0 14px;}
@media (max-width: 900px) {.cl-kpis {grid-template-columns: repeat(2, 1fr);} .cl-grid {grid-template-columns: 1fr;}}
</style>
""", unsafe_allow_html=True)


# ---------------- data ----------------

@st.cache_data
def load_scorecard(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["status"] = df["status"].fillna("")
    df["city"] = df["metro"].map(city_name)
    df["size_label"] = df["size_band"].map(SIZE_LABELS)
    return df


@st.cache_data
def load_history(path: str) -> pd.DataFrame | None:
    return pd.read_parquet(path) if Path(path).exists() else None


@st.cache_data
def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def city_name(title: str) -> str:
    """'Davenport-Moline-Rock Island, IA-IL' becomes 'Davenport, IA'."""
    place, _, states = title.partition(",")
    return f"{place.split('-')[0].strip()}, {states.strip().split('-')[0]}"


def pct(v, digits: int = 1, signed: bool = False) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    return f"{v:+.{digits}%}" if signed else f"{v:.{digits}%}"


def money(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"${v:,.0f}"


def pct_rank(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    r = s.rank(pct=True)
    return (r if higher_is_better else 1 - r).fillna(0.5)


def monthly_payment(principal, annual_rate: float, years: int = 30):
    i = annual_rate / 1200
    return principal * i / (1 - (1 + i) ** (-12 * years))


def series_list(names: list[str]) -> str:
    """'A, B and C'."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def table(df: pd.DataFrame, formats: dict, labels: dict, progress: dict | None = None, full: bool = False):
    """Formatted table: numbers keep their sort order, missing values read 'n/a'.
    full=True sizes the table to show every row without an inner scrollbar."""
    styled = df.style.format(formats, na_rep="n/a")
    config = {c: st.column_config.Column(label) for c, label in labels.items()}
    for c, label in (progress or {}).items():
        config[c] = st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f")
    extra = {"height": 35 * (len(df) + 1) + 3} if full else {}
    st.dataframe(styled, hide_index=True, width="stretch", column_config=config,
                 column_order=list(labels) + [c for c in (progress or {}) if c not in labels], **extra)


def finish(chart, height: int):
    """House style for every chart: quiet axes, light grid, one typeface, no border."""
    font = "Source Sans Pro, Arial, sans-serif"
    return (chart.properties(height=height)
            .configure(font=font)
            .configure_view(stroke=None)
            .configure_axis(labelColor=INK_2, titleColor=INK_2, labelFontSize=12, titleFontSize=12,
                            titleFontWeight="normal", gridColor="#eef0f3", domainColor="#d5d9e0",
                            tickColor="#d5d9e0", labelPadding=6, titlePadding=10, labelLimit=320)
            .configure_legend(labelColor=INK_2, labelFontSize=12, symbolType="square", symbolSize=110))


def html_table(rows: pd.DataFrame, numeric: tuple = ()) -> None:
    """Static table that wraps long text instead of truncating it."""
    head = "".join(f"<th class='{'n' if c in numeric else ''}'>{c}</th>" for c in rows.columns)
    body = "".join("<tr>" + "".join(f"<td class='{'n' if c in numeric else ''}'>{v}</td>" for c, v in row.items())
                   + "</tr>" for _, row in rows.iterrows())
    st.markdown(f"<table class='cl-table'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>",
                unsafe_allow_html=True)


def section(title: str, note: str = "") -> None:
    st.markdown(f"<div class='cl-h3'>{title}</div>" + (f"<div class='cl-note'>{note}</div>" if note else ""),
                unsafe_allow_html=True)


def dodge(values: pd.Series, gap: float) -> pd.Series:
    """Nudge end labels apart so none overlap, keeping their order."""
    out, last = {}, -np.inf
    for i, v in values.sort_values().items():
        last = max(v, last + gap)
        out[i] = last
    return pd.Series(out)


@st.cache_data
def national_index(path: str) -> pd.DataFrame | None:
    """Median metro rent and home value, each metro indexed to its January 2015 level."""
    if not Path(path).exists():
        return None
    h = pd.read_parquet(path).sort_values("date")
    out = []
    for col, name in [("rent", "U.S. rent"), ("home_value", "U.S. home value")]:
        wide = h.pivot_table(index="date", columns="cbsa_code", values=col)
        wide = wide.loc[:, wide.iloc[0].notna()]
        idx = 100 * wide / wide.iloc[0]
        out.append(pd.DataFrame({"date": idx.index, "index": idx.median(axis=1).values, "series": name}))
    return pd.concat(out)


def declutter(cands: pd.DataFrame, max_labels: int = 12) -> pd.DataFrame:
    """Keep labels, in priority order, only where they will not collide with one already placed.
    Labels are wide and short, so the horizontal spacing needed is larger than the vertical."""
    def width(row):          # label width in degrees of longitude, about 0.42 per character at national scale
        return 0.42 * len(str(row["city"]).split(",")[0]) / np.cos(np.radians(row["lat"]))

    kept = []
    for _, row in cands.iterrows():
        clash = any(abs(row["lon"] - k["lon"]) < (width(row) + width(k)) / 2 + 0.4
                    and abs(row["lat"] - k["lat"]) < 1.1 for k in kept)
        if not clash:
            kept.append(row)
        if len(kept) == max_labels:
            break
    return pd.DataFrame(kept)


def market_map(points: pd.DataFrame, tooltip: list, labels: pd.DataFrame | None = None, height: int = 440):
    """U.S. map on an Albers projection with state outlines. Dots sized by population and colored by the
    'color' column, hover details on every dot, and printed labels with a white halo on the leading markets.
    It is a static chart, so the page scrolls normally over it."""
    keep = ["lat", "lon", "population", "color", "city"] + [t.shorthand.split(":")[0] if hasattr(t, "shorthand")
                                                            else t.split(":")[0] for t in tooltip]
    pts = points.dropna(subset=["lat", "lon"])
    pts = pts[~((pts["lat"] < 19) & (pts["lon"] > -68))]     # Puerto Rico is outside the U.S. projection
    pts = pts[[c for c in dict.fromkeys(keep) if c in pts.columns]].copy()
    pts["_back"] = pts["color"] == GRAY
    pts = pts.sort_values(["_back", "population"], ascending=[False, False])   # gray underneath, small on top
    layers = []
    if states:
        layers.append(alt.Chart(alt.InlineData(values=states, format=alt.DataFormat(property="features")))
                      .mark_geoshape(fill="#eef1f5", stroke="#ffffff", strokeWidth=1.2))
    layers.append(alt.Chart(pts).mark_circle(stroke="#ffffff", strokeWidth=0.7).encode(
        longitude="lon:Q", latitude="lat:Q",
        opacity=alt.Opacity("_back:N", scale=alt.Scale(domain=[True, False], range=[0.5, 0.9]), legend=None),
        size=alt.Size("population:Q", scale=alt.Scale(type="sqrt", range=[14, 900]), legend=None),
        color=alt.Color("color:N", scale=None), tooltip=tooltip))
    if labels is not None and not labels.empty:
        lab = labels.dropna(subset=["lat", "lon"])[["lat", "lon", "city"]]
        lab = lab.assign(name=lab["city"].str.split(",").str[0])
        base = alt.Chart(lab).encode(longitude="lon:Q", latitude="lat:Q", text="name:N")
        style = dict(fontSize=12, fontWeight=600, dy=-11, font="Source Sans Pro, Arial, sans-serif")
        layers.append(base.mark_text(**style, stroke="#ffffff", strokeWidth=4, strokeJoin="round", strokeOpacity=0.95))
        layers.append(base.mark_text(**style, color=INK))
    st.altair_chart(finish(alt.layer(*layers).project(type="albersUsa"), height), width="stretch")


def legend(items: dict) -> None:
    keys = "".join(f"<span class='cl-key' style='background:{c}'></span>{name}" for name, c in items.items())
    st.markdown(f"<div class='cl-note' style='margin:-6px 0 0 -14px'>{keys}</div>", unsafe_allow_html=True)


def card_html(number: str, head: str, body: str, link: str | None = None) -> str:
    more = f"<a href='{REPO}/docs/{link}' target='_blank'>Read the analysis</a>" if link else ""
    return (f"<div class='cl-card'><div class='num'>{number}</div><div class='head'>{head}</div>"
            f"<div class='body'>{body}</div>{more}</div>")


def kpi_html(label: str, value: str, context: str, accent: str = NAVY) -> str:
    kind = "val txt" if "class='txt'" in value else "val"
    return (f"<div class='cl-kpi' style='--accent:{accent}'><div class='lab'>{label}</div>"
            f"<div class='{kind}'>{value}</div><div class='ctx'>{context}</div></div>")


scorecard_path = DATA_DIR / "metro_scorecard.parquet"
if not scorecard_path.exists():
    st.error("The scorecard file is missing. Run python -m pipeline.run_all to build it.")
    st.stop()

all_metros = load_scorecard(str(scorecard_path))
df = all_metros[all_metros["opportunity_rank"].notna()].copy()
history = load_history(str(DATA_DIR / "metro_history.parquet"))
summary = load_json(str(DATA_DIR / "dashboard_summary.json"))
states = load_json(str(DATA_DIR / "us_states.geojson")) or None
rate = float(df["mortgage_rate"].iloc[0])
as_of = pd.Timestamp(summary["housing_as_of"]).strftime("%B %Y") if summary.get("housing_as_of") else "latest release"
n_sweet = int((df["metro_type"] == "Rising & Affordable").sum())
leaders = [city_name(x["metro"]).split(",")[0] for x in summary.get("opportunity_robust", [])[:3]]

# ---------------- header ----------------
if summary.get("n_rising"):
    headline = "The next price wave is building in the Midwest and Northeast"
    lede = (f"{summary['rising_midwest_northeast']} of the {summary['n_rising']} metros most likely to outgrow the "
            f"national market next year are there, while {summary['cooling_south_west']} of "
            f"{summary['n_cooling']} cooling boomtowns are in the South and West. Southern metros still lead the "
            f"Opportunity Index, with {series_list(leaders)} at the top.")
else:
    headline = "Where opportunity is growing in America"
    lede = "What a paycheck buys, where prices head next and how confident each call is, metro by metro."
st.markdown(
    f"<div class='cl-top'><div class='cl-logo'><span class='cl-mark'></span>CityLens</div>"
    f"<div class='cl-tag'><b>U.S. Metro Housing Monitor</b><br/>Updated with {as_of} data</div></div>"
    f"<div class='cl-h1'>{headline}</div><div class='cl-lede'>{lede}</div>"
    f"<div class='cl-meta'>{len(df)} metropolitan areas &nbsp;&nbsp;|&nbsp;&nbsp; Housing data through {as_of} "
    f"&nbsp;&nbsp;|&nbsp;&nbsp; 30 year fixed rate {rate:.2f}% &nbsp;&nbsp;|&nbsp;&nbsp; Zillow, Census, BLS, IRS "
    f"and Federal Reserve data</div>", unsafe_allow_html=True)

within_reach = int((df["mortgage_to_income"] <= 0.30).sum())
kpis = [kpi_html("Typical rent change, next 12 months", pct(df["rent_forecast"].median(), signed=True),
                 f"Most likely between {pct(df['rent_forecast_low'].median(), signed=True)} and "
                 f"{pct(df['rent_forecast_high'].median(), signed=True)} in the typical metro", NAVY),
        kpi_html("Rising Cities", f"{summary.get('n_rising', int((df['status'] == 'Rising City').sum()))}",
                 (f"{summary['rising_midwest_northeast']} of them in the Midwest and Northeast"
                  if summary.get("n_rising") else "Likely to outgrow the national market next year"), BLUE),
        kpi_html("Affordable and growing", f"{n_sweet} <small>of {len(df)}</small>",
                 "Metros that rank well on both affordability and job and price momentum", TEAL),
        kpi_html("Homes within reach", f"{within_reach} <small>of {len(df)}</small>",
                 "Metros where a typical home with 20% down costs 30% of income or less", ORANGE)]
st.markdown(f"<div class='cl-kpis'>{''.join(kpis)}</div>", unsafe_allow_html=True)

overview, live, build, profile, methods = st.tabs(
    ["Overview", "Where to live", "Where to build", "Metro profile", "Methods"])

# ---------------- overview ----------------
with overview:
    st.subheader("Where home prices are heading")
    m = all_metros.dropna(subset=["lat", "lon"]).copy()
    m["color"] = m["status"].map(lambda s: STATUS_COLORS.get(s, GRAY))
    m["Signal"] = m["status"].replace("", "No signal")
    m["g3"] = m["growth_3y"]
    m["rank_text"] = m["opportunity_rank"].map(lambda v: "Not ranked" if pd.isna(v) else f"#{int(v)}")
    # label candidates: the largest metro of each signal first, then the second largest, and so on
    cands = pd.concat([m[m["status"] == s].nlargest(5, "population").assign(_k=range(5)) for s in STATUS_TEXT]
                      ).sort_values(["_k", "population"], ascending=[True, False])

    left, right = st.columns([5, 2], gap="medium")
    with left:
        market_map(m, [alt.Tooltip("city:N", title="Metro"), alt.Tooltip("Signal:N"),
                       alt.Tooltip("g3:Q", title="Home values, last 3 years", format="+.1%"),
                       alt.Tooltip("home_forecast:Q", title="Home values, next 12 months", format="+.1%"),
                       alt.Tooltip("rent_forecast:Q", title="Rent, next 12 months", format="+.1%"),
                       alt.Tooltip("rank_text:N", title="Opportunity rank")],
                   labels=declutter(cands, 10), height=480)
        legend({STATUS_PLURAL[s]: STATUS_COLORS[s] for s in STATUS_TEXT} | {"No signal": GRAY})
        st.markdown("<div class='cl-note' style='margin-top:4px'>Dot size shows population. Hover any metro for "
                    "its numbers.</div>", unsafe_allow_html=True)
    with right:
        blocks = []
        for s in STATUS_TEXT:
            top = m[m["status"] == s].nlargest(4, "population")
            rows = "".join(f"<tr><td>{c}</td><td class='n'>{pct(v, signed=True)}</td></tr>"
                           for c, v in zip(top["city"], top["home_forecast"]))
            blocks.append(f"<div class='grp'><i style='background:{STATUS_COLORS[s]}'></i>{STATUS_PLURAL[s]}</div>"
                          f"<div class='def'>{STATUS_TEXT[s]}</div><table><tr class='hd'><td>Largest</td>"
                          f"<td class='n'>Home values, next 12 months</td></tr>{rows}</table>")
        st.markdown(f"<div class='cl-watch'>{''.join(blocks)}</div>", unsafe_allow_html=True)

    st.markdown("&nbsp;")
    st.subheader("Five findings")
    f = summary.get("forecast", {}).get("rent", {})
    pol, rip = summary.get("policy", {}), summary.get("ripple", {})
    sweet = df[(df["metro_type"] == "Rising & Affordable") & (df["size_band"] == "Large (1M+)")]
    sweet_names = [c.split(",")[0] for c in sweet.sort_values("opportunity_rank")["city"].head(6)]
    cards = [card_html(f"{n_sweet} of {len(df)}", "Metros that are affordable and still growing",
                       f"{series_list(sweet_names)} lead the large metros. In San Francisco, Los Angeles and "
                       "Boston, a mortgage on a typical home takes well over a third of a typical income.",
                       "opportunity_index_report.md")]
    if summary:
        robust = summary.get("opportunity_robust", [])[:4]
        cards += [
            card_html(f"{summary['rising_midwest_northeast']} of {summary['n_rising']}",
                      "Rising Cities sit in the Midwest and Northeast",
                      f"{summary['cooling_south_west']} of {summary['n_cooling']} cooling boomtowns are in the South "
                      "and West. Population inflows lifted prices through 2021 and have weighed on them since 2022.",
                      "rising_cities_report.md"),
            card_html("75 miles", "The reach of a neighbor's boom",
                      f"Faster growth among metros within 75 miles adds {rip.get('effect_0_75', 0):.2f} points to a "
                      "metro's growth the following year, beyond its own momentum. Past 150 miles the effect "
                      "disappears.", "ripple_map_report.md"),
            card_html(pct(summary["rent_forecast_median"], signed=True), "Rent in the typical metro, next 12 months",
                      f"In backtests from 2020 to 2025 the model missed by {f.get('model', 0):.1f} points against "
                      f"{f.get('base', 0):.1f} for the best simple rule. Since 2022 the miss is "
                      f"{f.get('calm_model', 0):.1f} points and the 80% ranges held "
                      f"{f.get('calm_coverage', 0):.0%} of outcomes.", "forecast_report.md"),
            card_html(f"{pol.get('reform_effect_low_pp', 0):.0f} to {pol.get('reform_effect_high_pp', 0):.0f} points",
                      "What zoning reform did for Minneapolis rents",
                      f"Rents are {abs(pol.get('gap_latest', 0)):.0%} below a synthetic Minneapolis built from "
                      f"{pol.get('n_donors', 0)} cities (p = {pol.get('p_value', 0):.3f}). Its suburbs, outside "
                      f"the reform, fell {abs(pol.get('suburbs_gap', 0)):.0%} too, so most of the gap is regional.",
                      "policy_lab_report.md"),
            card_html(f"{rip.get('morans_i', 0):.2f}", "Growth moves in regional waves",
                      "Moran's I for three year home value growth, where 0 means no geographic pattern. A rising "
                      "belt runs from Chicago to New York while cooling clusters cover Texas and Florida.",
                      "ripple_map_report.md"),
        ]
    st.markdown(f"<div class='cl-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)

    st.markdown("&nbsp;")
    st.subheader("The 15 largest metros, ranked by opportunity")
    big = df.nlargest(15, "population").sort_values("opportunity_rank").copy()
    big["signal"] = big["status"].replace("", "No signal")
    table(big[["city", "opportunity_rank", "rent_to_income", "mortgage_to_income", "job_growth_3y",
               "rent_forecast", "home_forecast", "signal"]],
          {"opportunity_rank": "#{:.0f}", "rent_to_income": "{:.0%}", "mortgage_to_income": "{:.0%}",
           "job_growth_3y": "{:+.1%}", "rent_forecast": "{:+.1%}", "home_forecast": "{:+.1%}"},
          {"city": "Metro", "opportunity_rank": f"Rank of {len(df)}", "rent_to_income": "Rent share of income",
           "mortgage_to_income": "Mortgage share of income", "job_growth_3y": "Job growth per year",
           "rent_forecast": "Rent, next 12 months", "home_forecast": "Home value, next 12 months",
           "signal": "Market signal"}, full=True)
    st.markdown("<div class='cl-note'>Shares of income use the typical household income and typical rent or home "
                "in each metro. Mortgage is principal and interest with 20% down at today's rate. Job growth is the "
                "average over the last three years.</div>", unsafe_allow_html=True)


# ---------------- where to live ----------------
with live:
    st.subheader("Which metros fit my budget")
    c1, c2, c3, c4 = st.columns(4)
    income = c1.number_input("Household income per year", min_value=20_000, max_value=1_000_000,
                             value=75_000, step=5_000, format="%d")
    housing = c2.radio("Housing", ["Rent", "Buy"], horizontal=True)
    down = c3.slider("Down payment, percent", 3, 50, 20, disabled=housing == "Rent")
    cap = c4.slider("Housing budget, percent of income", 15, 50, 30)
    f1, f2, f3 = st.columns(3)
    regions = f1.multiselect("Region", sorted(df["region"].dropna().unique()), placeholder="All regions")
    sizes = f2.multiselect("Metro size", list(SIZE_LABELS.values()), placeholder="All sizes")
    sort_by = f3.selectbox("Rank by", ["Best overall fit", "Most money left each month", "Strongest job growth",
                                       "Steadiest rent outlook"])

    d = df.copy()
    if housing == "Rent":
        d["monthly_cost"] = d["rent"]
    else:
        d["monthly_cost"] = monthly_payment(d["home_value"] * (1 - down / 100), rate)
    d["share"] = d["monthly_cost"] * 12 / income
    d["left_over"] = income / 12 - d["monthly_cost"]
    d["fit"] = 100 * (0.45 * pct_rank(d["share"], False) + 0.30 * pct_rank(d["job_growth_3y"])
                      + 0.25 * pct_rank(d["rent_forecast"], False))
    if regions:
        d = d[d["region"].isin(regions)]
    if sizes:
        d = d[d["size_label"].isin(sizes)]
    fits = d[d["share"] <= cap / 100]
    order = {"Best overall fit": ("fit", False), "Most money left each month": ("left_over", False),
             "Strongest job growth": ("job_growth_3y", False), "Steadiest rent outlook": ("rent_forecast", True)}
    col, asc = order[sort_by]
    fits = fits.sort_values(col, ascending=asc, na_position="last")

    cost_word = "rent" if housing == "Rent" else "a mortgage payment"
    st.markdown(f"**{len(fits)} of {len(d)} metros** keep {cost_word} at or under {cap}% of "
                f"a ${income:,.0f} household income.")
    if not fits.empty:
        best = fits.sort_values("fit", ascending=False).iloc[0]
        growing = int((fits["job_growth_3y"] > 0).sum())
        st.markdown("<div class='cl-kpis slim'>" + "".join([
            kpi_html("Metros that fit", f"{len(fits)} <small>of {len(d)}</small>",
                     f"At {cap}% of income for {'rent' if housing == 'Rent' else 'principal and interest'}"),
            kpi_html("Typical amount left each month", money(fits["left_over"].median()),
                     "Gross monthly income minus housing, in the median metro that fits", TEAL),
            kpi_html("Best overall fit", f"<span class='txt'>{best['city']}</span>",
                     f"{money(best['monthly_cost'])} a month, jobs {pct(best['job_growth_3y'], signed=True)} a year",
                     BLUE),
            kpi_html("Fits with growing jobs", f"{growing} <small>of {len(fits)}</small>",
                     "Job growth above zero over the last three years", ORANGE)]) + "</div>",
            unsafe_allow_html=True)
    if fits.empty:
        st.info("No metro fits these settings. Try a larger housing budget or a larger down payment.")
    else:
        left, right = st.columns([3, 2])
        with left:
            section(f"Top 15 by {sort_by.lower()}")
            show = fits.head(15).assign(signal=lambda x: x["status"].replace("", "No signal"))
            table(show[["city", "monthly_cost", "share", "left_over", "job_growth_3y", "rent_forecast", "signal"]],
                  {"monthly_cost": "${:,.0f}", "share": "{:.1%}", "left_over": "${:,.0f}",
                   "job_growth_3y": "{:+.1%}", "rent_forecast": "{:+.1%}"},
                  {"city": "Metro", "monthly_cost": "Housing per month", "share": "Share of income",
                   "left_over": "Left each month", "job_growth_3y": "Job growth per year",
                   "rent_forecast": "Rent, next 12 months", "signal": "Market signal"}, full=True)
        with right:
            top = fits.head(25).copy()
            top["color"] = BLUE
            section("Where the top 25 are")
            market_map(top, [alt.Tooltip("city:N", title="Metro"),
                             alt.Tooltip("monthly_cost:Q", title="Housing per month", format="$,.0f"),
                             alt.Tooltip("share:Q", title="Share of income", format=".1%"),
                             alt.Tooltip("left_over:Q", title="Left each month", format="$,.0f")],
                       labels=declutter(top, 8), height=380)

        # how many metros fit across incomes, with this household marked
        incomes = np.arange(30_000, 200_001, 5_000)
        base = d["monthly_cost"].dropna() * 12
        curve = pd.DataFrame({"income": incomes,
                              "metros": [(base / x <= cap / 100).sum() for x in incomes]})
        you = pd.DataFrame({"income": [income], "metros": [len(fits)],
                            "label": [f"Your income: {len(fits)} metros"]})
        area = alt.Chart(curve).mark_area(color=NAVY, opacity=0.07).encode(x="income:Q", y="metros:Q")
        line = alt.Chart(curve).mark_line(color=NAVY, strokeWidth=2.2).encode(
            x=alt.X("income:Q", title="Household income", axis=alt.Axis(format="$,.0f", grid=False),
                  scale=alt.Scale(domain=[30_000, 200_000], nice=False)),
            y=alt.Y("metros:Q", title="Metros that fit", axis=alt.Axis(tickCount=5),
                    scale=alt.Scale(domain=[0, len(d)])))
        dot = alt.Chart(you).mark_point(filled=True, size=90, color=ORANGE).encode(x="income:Q", y="metros:Q")
        txt = alt.Chart(you).mark_text(align="left", dx=10, dy=14, fontSize=12, fontWeight=600, color="#1f2a37").encode(
            x="income:Q", y="metros:Q", text="label:N")
        section("How many metros fit at other incomes",
                f"Same housing choice and {cap}% budget. The marker is the income entered above.")
        st.altair_chart(finish(area + line + dot + txt, 240), width="stretch")
        st.markdown(f"<div class='cl-note'>Housing cost is the typical rent, or principal and interest on a 30 year "
                    f"loan for the typical home at {rate:.2f}%. Taxes, insurance and utilities are not included. "
                    "Best overall fit weighs affordability for this income (45%), job growth (30%) and a steady "
                    "rent outlook (25%).</div>", unsafe_allow_html=True)

# ---------------- where to build ----------------
with build:
    st.subheader("Where demand is likely to grow")
    st.markdown("<div class='cl-note'>Set how much each signal matters. Scores are relative ranks among all "
                "metros, from 0 to 100, not predicted returns.</div>", unsafe_allow_html=True)
    signals = {"Home value outlook": ("home_forecast", True), "Rising Signal": ("rising_signal", True),
               "Neighbors rising": ("ripple_pressure_pp", True), "Job growth": ("job_growth_3y", True),
               "Buyer affordability": ("mortgage_to_income", False)}
    defaults = [8, 6, 5, 6, 5]
    cols = st.columns(5)
    weights = np.array([c.slider(name, 0, 10, dv) for c, name, dv in zip(cols, signals, defaults)], dtype=float)
    g1, g2 = st.columns(2)
    min_pop = g1.number_input("Smallest metro to consider, population", 0, 5_000_000, 250_000, step=50_000,
                              format="%d")
    skip_cooling = g2.checkbox("Leave out cooling boomtowns", value=True)

    b = df[df["population"] >= min_pop].copy()
    if skip_cooling:
        b = b[b["status"] != "Cooling Boomtown"]
    if weights.sum() == 0:
        st.info("Give at least one signal some weight.")
    elif len(b) < 10:
        st.info("Fewer than ten metros meet these filters. Lower the population threshold.")
    else:
        parts = np.vstack([pct_rank(b[c], hib).to_numpy() for c, hib in signals.values()])
        b["score"] = 100 * (weights @ parts) / weights.sum()

        # robustness: vary every weight by up to 50% either way and count top 10 finishes
        rng = np.random.default_rng(7)
        draws = weights * rng.uniform(0.5, 1.5, size=(500, len(weights)))
        sims = (draws @ parts) / draws.sum(axis=1, keepdims=True)
        top10 = (np.argsort(np.argsort(-sims, axis=1), axis=1) < 10).mean(axis=0)
        b["robust"] = top10 * 100

        ranked_b = b.sort_values("score", ascending=False)
        left, right = st.columns([3, 2])
        with left:
            table(ranked_b.head(15)[["city", "score", "robust", "home_forecast", "job_growth_3y",
                                     "mortgage_to_income", "status"]],
                  {"home_forecast": "{:+.1%}", "job_growth_3y": "{:+.1%}", "mortgage_to_income": "{:.0%}",
                   "robust": "{:.0f}%"},
                  {"city": "Metro", "robust": "Top 10 in scenarios", "home_forecast": "Home value, next 12 months",
                   "job_growth_3y": "Job growth per year", "mortgage_to_income": "Mortgage share of income",
                   "status": "Market signal"},
                  progress={"score": "Score"})
            st.markdown("<div class='cl-note'>Top 10 in scenarios: the share of 500 alternative weightings, each "
                        "weight moved up to 50% either way, in which the market still ranks in the top 10. "
                        "High values mean the result does not depend on the exact weights.</div>",
                        unsafe_allow_html=True)
        with right:
            mp = ranked_b.head(15).copy()
            mp["color"] = mp["status"].map(lambda s: STATUS_COLORS[s] if s else NAVY)
            section("Where the top 15 are", "Colored by market signal. Navy means no signal.")
            market_map(mp, [alt.Tooltip("city:N", title="Metro"), alt.Tooltip("score:Q", title="Score", format=".0f"),
                            alt.Tooltip("home_forecast:Q", title="Home value, next 12 months", format="+.1%")],
                       labels=declutter(mp, 8), height=380)

        section("What drives the top five scores",
                "Each bar splits the score into the points contributed by each signal at the current weights.")
        top5 = ranked_b.head(5)
        idx = [b.index.get_loc(i) for i in top5.index]
        contrib = pd.DataFrame([{"Metro": top5.loc[i, "city"], "Signal": name, "k": k,
                                 "Points": 100 * weights[k] * parts[k, j] / weights.sum()}
                                for i, j in zip(top5.index, idx) for k, name in enumerate(signals)])
        totals = contrib.groupby("Metro", sort=False)["Points"].sum().reset_index()
        order_m = list(top5["city"])
        bars = alt.Chart(contrib).mark_bar(height=22).encode(
            y=alt.Y("Metro:N", sort=order_m, title=None),
            x=alt.X("sum(Points):Q", title="Score points", scale=alt.Scale(domain=[0, 100]),
                    axis=alt.Axis(tickCount=5)),
            color=alt.Color("Signal:N", sort=list(signals), legend=alt.Legend(orient="bottom", title=None),
                            scale=alt.Scale(domain=list(signals), range=[NAVY, BLUE, TEAL, "#8fb8e8", ORANGE])),
            order=alt.Order("k:Q"),
            tooltip=["Metro", "Signal", alt.Tooltip("Points:Q", format=".1f")])
        labels_t = alt.Chart(totals).mark_text(align="left", dx=6, fontSize=12, fontWeight=600, color=INK).encode(
            y=alt.Y("Metro:N", sort=order_m), x="Points:Q", text=alt.Text("Points:Q", format=".0f"))
        st.altair_chart(finish(bars + labels_t, 220), width="stretch")

# ---------------- metro profile ----------------
with profile:
    names = df.assign(label=np.where(df["city"].duplicated(keep=False), df["metro"], df["city"]))
    options = names.sort_values("label")["label"].tolist()
    default = options.index(names.sort_values("opportunity_rank")["label"].iloc[0])
    pick_label = st.selectbox("Metro", options, index=default)
    r = names[names["label"] == pick_label].iloc[0]
    pick = r["metro"]
    peers = df[df["size_band"] == r["size_band"]]

    st.markdown(f"### {r['city']}")
    pop = (f"{r['population'] / 1e6:.2f} million" if r["population"] >= 1e6 else f"{r['population']:,.0f}")
    st.markdown(f"<div class='cl-note' style='margin-top:-10px'>{SIZE_SHORT[r['size_band']].capitalize()} metro, "
                f"{pop} residents. Opportunity Index group: {r['metro_type']}. Census name: {pick}.</div>",
                unsafe_allow_html=True)
    us = df.median(numeric_only=True)
    rank_ctx = (f"Between #{int(r['rank_p05'])} and #{int(r['rank_p95'])} under 90% of 1,000 alternative weightings"
                if pd.notna(r.get("rank_p05")) else "Opportunity Index")
    nxt = lambda c: (f"{pct(r[c], signed=True)} expected over the next 12 months" if pd.notna(r[c])
                     else "No forecast for this metro")
    vs = lambda c, d=0, sg=False: f"U.S. median metro {pct(us[c], d, sg)}"
    sig = r["status"]
    st.markdown("<div class='cl-kpis'>" + "".join([
        kpi_html("Opportunity rank", f"#{int(r['opportunity_rank'])} <small>of {len(df)}</small>", rank_ctx),
        kpi_html("Typical household income", money(r["income"]),
                 f"Median {SIZE_SHORT[r['size_band']]} metro {money(peers['income'].median())}"),
        kpi_html("Typical rent", money(r["rent"]), nxt("rent_forecast"), BLUE),
        kpi_html("Typical home value", money(r["home_value"]), nxt("home_forecast"), BLUE),
        kpi_html("Rent share of income", pct(r["rent_to_income"], 0), vs("rent_to_income"), TEAL),
        kpi_html("Mortgage share of income", pct(r["mortgage_to_income"], 0),
                 f"20% down. {vs('mortgage_to_income')}", TEAL),
        kpi_html("Job growth per year", pct(r["job_growth_3y"], signed=True),
                 f"Last three years. {vs('job_growth_3y', 1, True)}", TEAL),
        kpi_html("Market signal", f"<span class='txt'>{sig or 'No signal'}</span>",
                 STATUS_TEXT.get(sig, "None of the three price signals applies right now."),
                 STATUS_COLORS[sig] if sig else GRAY)]) + "</div>", unsafe_allow_html=True)

    jg = r["job_growth_3y"]
    sentences = [f"{r['city']} ranks #{int(r['opportunity_rank'])} of {len(df)} on the Opportunity Index."]
    if pd.notna(r["rent_to_income"]):
        sentences.append(f"Rent takes {pct(r['rent_to_income'], 0)} of a typical household's income and a mortgage "
                         f"on a typical home takes {pct(r['mortgage_to_income'], 0)}.")
    sentences.append(f"Jobs have {'grown' if jg >= 0 else 'shrunk'} {abs(jg):.1%} a year over the last three years.")
    if pd.notna(r.get("rent_forecast_low")):
        rf = r["rent_forecast"]
        sentences.append(f"Rent is forecast to {'rise' if rf >= 0 else 'fall'} {abs(rf):.1%} over the next year, "
                         f"most likely between {pct(r['rent_forecast_low'], signed=True)} and "
                         f"{pct(r['rent_forecast_high'], signed=True)}.")
    if r["status"]:
        sentences.append(STATUS_TEXT[r["status"]])
    st.markdown(" ".join(sentences))

    left, right = st.columns([3, 2])
    with left:
        section("Rent and home value since 2015", "Indexed to January 2015 = 100. Dashed lines are the median "
                "U.S. metro on the same basis.")
        if history is not None:
            h = history[history["cbsa_code"] == r["cbsa_code"]].sort_values("date")
            series = []
            for col_, name in [("rent", "Rent"), ("home_value", "Home value")]:
                s = h[["date", col_]].dropna()
                if not s.empty:
                    series.append(pd.DataFrame({"date": s["date"], "index": 100 * s[col_] / s[col_].iloc[0],
                                                "series": name}))
            if series:
                nat = national_index(str(DATA_DIR / "metro_history.parquet"))
                if nat is not None:
                    series.append(nat[nat["date"] >= min(x["date"].min() for x in series)])
                hist = pd.concat(series)
                last = hist.sort_values("date").groupby("series").tail(1).reset_index(drop=True)
                span = hist["index"].max() - hist["index"].min()
                last["y"] = dodge(last["index"], span * 0.065)
                last["label"] = last.apply(lambda x: f"{x['series']} {x['index']:.0f}", axis=1)
                dom = ["Rent", "Home value", "U.S. rent", "U.S. home value"]
                rng = [BLUE, NAVY, "#8fb8e8", "#9aa3af"]
                lines = alt.Chart(hist).mark_line(strokeWidth=2).encode(
                    x=alt.X("date:T", title=None, axis=alt.Axis(
                        format="%Y", grid=False, values=[alt.DateTime(year=y, month=1, date=1)
                                                         for y in range(2016, 2027, 2)])),
                    y=alt.Y("index:Q", title="Index", scale=alt.Scale(zero=False), axis=alt.Axis(tickCount=5)),
                    color=alt.Color("series:N", legend=None, scale=alt.Scale(domain=dom, range=rng)),
                    strokeDash=alt.StrokeDash("series:N", legend=None, scale=alt.Scale(
                        domain=dom, range=[[1, 0], [1, 0], [5, 3], [5, 3]])),
                    tooltip=[alt.Tooltip("date:T", format="%b %Y"), "series:N",
                             alt.Tooltip("index:Q", format=".1f")])
                end = alt.Chart(last).mark_text(align="left", dx=6, fontSize=12, fontWeight=600).encode(
                    x="date:T", y="y:Q", text="label:N",
                    color=alt.Color("series:N", legend=None, scale=alt.Scale(domain=dom, range=rng)))
                st.altair_chart(finish(lines + end, 280), width="stretch")
        else:
            st.markdown("<div class='cl-note'>Price history is not available.</div>", unsafe_allow_html=True)
    with right:
        section("Opportunity Index pillars", "Percentile among ranked metros. Dashed line marks the median.")
        pillars = pd.DataFrame({"Pillar": ["Affordability", "Momentum", "Demand and supply"],
                                "Score": [r["affordability_score"], r["momentum_score"], r["demand_supply_score"]]})
        pillars["side"] = np.where(pillars["Score"] >= 50, "above", "below")
        pb = alt.Chart(pillars).mark_bar(height=24).encode(
            color=alt.Color("side:N", legend=None, scale=alt.Scale(domain=["above", "below"], range=[NAVY, ORANGE])),
            y=alt.Y("Pillar:N", sort=None, title=None),
            x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 100]), title=None,
                    axis=alt.Axis(values=[0, 25, 50, 75, 100])))
        mid = alt.Chart(pd.DataFrame({"x": [50]})).mark_rule(color=GRAY, strokeDash=[4, 3]).encode(x="x:Q")
        pt = alt.Chart(pillars).mark_text(align="left", dx=6, fontSize=12, fontWeight=600, color=INK).encode(
            y=alt.Y("Pillar:N", sort=None), x="Score:Q", text=alt.Text("Score:Q", format=".0f"))
        st.altair_chart(finish(pb + mid + pt, 170), width="stretch")

    section("Against its peers and the nation", f"Peers are the {len(peers)} other {SIZE_SHORT[r['size_band']]} metros.")
    rows = [("Rent share of income", "rent_to_income", "{:.0%}"),
            ("Mortgage share of income", "mortgage_to_income", "{:.0%}"),
            ("Job growth per year", "job_growth_3y", "{:+.1%}"),
            ("Rent growth per year, last 3 years", "rent_growth_3y", "{:+.1%}"),
            ("Rent, next 12 months", "rent_forecast", "{:+.1%}"),
            ("Home value, next 12 months", "home_forecast", "{:+.1%}"),
            ("Net migration per 1,000 residents", "net_migration_per_1k", "{:+.1f}")]
    comp = pd.DataFrame([{"Measure": label, "This metro": fmt.format(r[c]) if pd.notna(r[c]) else "n/a",
                          f"Median {SIZE_SHORT[r['size_band']]} metro": fmt.format(peers[c].median()),
                          "Median U.S. metro": fmt.format(df[c].median())} for label, c, fmt in rows])
    html_table(comp, numeric=tuple(comp.columns[1:]))

    section("Neighbors within 75 miles", "Growth spreads about 75 miles, so these are the markets most likely to "
            "pull this one along.")
    lat1, lon1 = np.radians(r["lat"]), np.radians(r["lon"])
    la, lo = np.radians(all_metros["lat"]), np.radians(all_metros["lon"])
    dist = 3958.8 * 2 * np.arcsin(np.sqrt(np.sin((la - lat1) / 2) ** 2
                                          + np.cos(lat1) * np.cos(la) * np.sin((lo - lon1) / 2) ** 2))
    near = all_metros.assign(miles=dist)
    near = near[(near["miles"] > 0) & (near["miles"] <= 75)].sort_values("miles")
    if near.empty:
        st.markdown("<div class='cl-note'>No other metropolitan area lies within 75 miles.</div>",
                    unsafe_allow_html=True)
    else:
        near["signal"] = near["status"].replace("", "No signal")
        table(near[["city", "miles", "growth_3y", "rent_forecast", "signal"]].head(8),
              {"miles": "{:.0f}", "growth_3y": "{:+.1%}", "rent_forecast": "{:+.1%}"},
              {"city": "Metro", "miles": "Miles away", "growth_3y": "Home values, last 3 years",
               "rent_forecast": "Rent, next 12 months", "signal": "Market signal"}, full=True)

# ---------------- methods ----------------
with methods:
    st.subheader("How the numbers were produced and tested")
    fc, rs, rp, pol = (summary.get(k, {}) for k in ("forecast", "rising", "ripple", "policy"))
    robust = summary.get("opportunity_robust", [])
    if summary:
        val = pd.DataFrame([
            {"Analysis": "Opportunity Index", "Question": "Where does a paycheck go furthest",
             "Method": "Percentile index of affordability, momentum and demand",
             "Validation": "1,000 random weightings and dropping each input",
             "Result": f"Top four stay in the top 25 under {min(x['share_top25'] for x in robust[:4]):.0%} to "
                       f"{max(x['share_top25'] for x in robust[:4]):.0%} of weightings"},
            {"Analysis": "Rising City Detector", "Question": "Which metros will outgrow the market",
             "Method": "Panel regression with year fixed effects, then a two signal rule",
             "Validation": "Walk forward backtest, 2021 to 2024, six designs",
             "Result": f"Top fifth beat bottom fifth by {rs.get('avg_spread_pp', 0):.1f} points a year, "
                       f"never less than {rs.get('worst_spread_pp', 0):.1f}"},
            {"Analysis": "Policy Lab", "Question": "What zoning reform did to Minneapolis rents",
             "Method": f"Synthetic control from {pol.get('n_donors', 0)} cities",
             "Validation": "Placebos in space and time, leave one out, suburb comparison",
             "Result": f"Gap {pct(pol.get('gap_latest'), 0, True)}, p = {pol.get('p_value', 0):.3f}. Reform "
                       f"share {pol.get('reform_effect_low_pp', 0):.0f} to {pol.get('reform_effect_high_pp', 0):.0f} points"},
            {"Analysis": "Forecast Engine", "Question": "Rents and home values a year ahead",
             "Method": "Gradient boosting blended with a national trend model",
             "Validation": "Rolling backtest 2020 to 2025 against three baselines, conformal ranges",
             "Result": f"Rent error {fc.get('rent', {}).get('model', 0):.1f} vs {fc.get('rent', {}).get('base', 0):.1f} "
                       f"points. 80% ranges held {fc.get('rent', {}).get('calm_coverage', 0):.0%} since 2022"},
            {"Analysis": "Ripple Map", "Question": "How far growth spreads",
             "Method": "Moran's I, local clusters and distance ring regression",
             "Validation": "999 permutations, estimates before, during and after COVID",
             "Result": f"Moran's I {rp.get('morans_i', 0):.2f}. Within 75 miles {rp.get('effect_0_75', 0):+.2f} "
                       f"points (t = {rp.get('t_0_75', 0):.1f})"},
        ])
        html_table(val)

    st.markdown("&nbsp;")
    st.subheader("Data and freshness")
    fr = summary.get("freshness", {})
    src = pd.DataFrame([
        ("Zillow home values and rents", "Monthly", fr.get("zillow_metro_home_value", "n/a"), "About 2 weeks"),
        ("BLS jobs and wages (QCEW)", "Monthly, released quarterly", fr.get("bls_qcew", "n/a"), "About 6 months"),
        ("Federal Reserve mortgage rate", "Weekly", fr.get("fred", "n/a"), "About 1 week"),
        ("Census income and renters (ACS 5 year)", "Yearly", fr.get("census_acs5", "n/a"), "About 1 year"),
        ("Census building permits", "Yearly", fr.get("census_permits", "n/a"), "About 5 months"),
        ("IRS migration between counties", "Yearly", fr.get("irs_migration", "n/a"), "About 2 years"),
        ("Census metro definitions and coordinates", "As revised", fr.get("cbsa_delineation", "n/a"), "Not applicable"),
    ], columns=["Source", "Frequency", "Latest period loaded", "Typical publication lag"])
    html_table(src)
    st.markdown("<div class='cl-note'>Every model input is lagged to match when the source is actually published, "
                "so backtests never use information that was not yet available.</div>", unsafe_allow_html=True)

    cov = summary.get("coverage")
    if cov:
        st.markdown("&nbsp;")
        st.subheader("Which areas are ranked")
        steps = pd.DataFrame([
            ("Census core based statistical areas in the data panel", f"{cov['panel_total']:,}"),
            ("Micropolitan areas, urban cores of 10,000 to 50,000 people", f"minus {cov['micropolitan']}"),
            ("Metropolitan areas, urban cores of 50,000 people or more", f"{cov['metropolitan']}"),
            ("Puerto Rico, not covered by Zillow", f"minus {cov['puerto_rico']}"),
            ("Connecticut, job data not comparable after the 2024 change", f"minus {cov['connecticut']}"),
            ("Created in the 2023 Census update, no Zillow series yet: "
             + series_list([city_name(x) for x in cov["no_zillow"]]), f"minus {len(cov['no_zillow'])}"),
            ("Ranked by CityLens", f"{cov['ranked']}"),
        ], columns=["Step", "Areas"])
        html_table(steps, numeric=("Areas",))
        st.markdown(f"<div class='cl-note'>Micropolitan areas stay in the data panel but are not ranked. Zillow "
                    f"publishes rents for only {cov['micro_with_rent']} of the {cov['micropolitan']}, and survey "
                    "and job estimates for areas that small carry wide error margins.</div>", unsafe_allow_html=True)

    st.markdown("&nbsp;")
    st.subheader("Known limits")
    st.markdown("""
- Connecticut metros are not ranked. BLS moved Connecticut from counties to planning regions in 2024, which breaks
  three year job comparisons.
- National shocks drive most one year price changes. The 2020 and 2021 surge and the 2022 rate shock broke every
  forecast tested, including this one.
- The Rising City and ripple signals are predictive. They do not prove that one metro's growth causes another's.
- Figures describe typical households and typical homes in each metro, not any single household.
""")
    st.markdown(f"Full reports: [Opportunity Index]({REPO}/docs/opportunity_index_report.md), "
                f"[Rising City Detector]({REPO}/docs/rising_cities_report.md), "
                f"[Policy Lab]({REPO}/docs/policy_lab_report.md), "
                f"[Forecast Engine]({REPO}/docs/forecast_report.md), [Ripple Map]({REPO}/docs/ripple_map_report.md), "
                f"[Executive memo]({REPO}/docs/executive_memo.md) and the [decisions log]({REPO}/docs/decisions.md).")
