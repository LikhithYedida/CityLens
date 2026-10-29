"""BLS QCEW: monthly jobs and weekly wages for every county, rolled up to metros.

QCEW counts jobs from unemployment-insurance filings, covering about 95% of U.S.
jobs. It's the most complete local jobs data, released about 5-6 months after
each quarter ends. No API key needed.

Each quarterly file has 3 monthly job counts, so we get a true monthly series
that lines up with Zillow.

Run:  python -m pipeline.qcew     (run pipeline.geo first)
"""
from datetime import date

import numpy as np
import pandas as pd

from pipeline.config import CLEAN_DIR, QCEW_START_YEAR, QCEW_URL, RAW_DIR
from pipeline.utils import SourceError, download, log, record_run

COUNTY_TOTAL_AGGLVL = 70  # county, total covered, all industries
ALL_OWNERSHIP = 0
USECOLS = ["area_fips", "own_code", "agglvl_code", "year", "qtr", "disclosure_code",
           "month1_emplvl", "month2_emplvl", "month3_emplvl", "total_qtrly_wages", "avg_wkly_wage"]

QCEW_DIR = RAW_DIR / "qcew"


def fetch_quarter(year: int, qtr: int) -> pd.DataFrame:
    QCEW_DIR.mkdir(exist_ok=True)
    path = QCEW_DIR / f"qcew_{year}_q{qtr}.csv"
    # Older quarters rarely change, so reuse the saved copy. Re-download the last
    # two years each run, since BLS revises recent data.
    if not path.exists() or year >= date.today().year - 1:
        download(QCEW_URL.format(year=year, qtr=qtr), path)
    return pd.read_csv(path, usecols=USECOLS, dtype={"area_fips": str, "disclosure_code": str})


def to_monthly_county(q: pd.DataFrame) -> pd.DataFrame:
    """Keep county totals and reshape 3 month columns into 3 monthly rows."""
    c = q[(q["own_code"] == ALL_OWNERSHIP) & (q["agglvl_code"] == COUNTY_TOTAL_AGGLVL)].copy()
    c = c[c["area_fips"].str.fullmatch(r"\d{5}") & ~c["area_fips"].str.endswith("999")]  # drop "unknown county"
    suppressed = c["disclosure_code"].fillna("").str.strip().eq("N")
    for col in ["month1_emplvl", "month2_emplvl", "month3_emplvl", "total_qtrly_wages", "avg_wkly_wage"]:
        c.loc[suppressed, col] = np.nan  # BLS shows 0 for confidential values; 0 would be wrong

    rows = []
    for m in (1, 2, 3):
        part = c[["area_fips", "year", "qtr", "total_qtrly_wages", "avg_wkly_wage"]].copy()
        part["month"] = (part["qtr"] - 1) * 3 + m
        part["employment"] = c[f"month{m}_emplvl"].values
        rows.append(part)
    out = pd.concat(rows, ignore_index=True)
    out["date"] = pd.to_datetime(dict(year=out["year"], month=out["month"], day=1))
    return out.rename(columns={"area_fips": "county_fips"})[
        ["county_fips", "date", "year", "qtr", "employment", "total_qtrly_wages", "avg_wkly_wage"]]


def to_metro(county: pd.DataFrame, county_to_cbsa: pd.DataFrame) -> pd.DataFrame:
    m = county.merge(county_to_cbsa[["county_fips", "cbsa_code"]], on="county_fips", how="inner")
    jobs = m.groupby(["cbsa_code", "date"]).agg(
        employment=("employment", "sum"),
        n_counties=("county_fips", "nunique"),
        n_missing=("employment", lambda s: s.isna().sum()),
    ).reset_index()
    # Weekly wage from totals: quarterly wages / average quarterly jobs / 13 weeks
    county_q = m.groupby(["cbsa_code", "county_fips", "year", "qtr"]).agg(
        wages=("total_qtrly_wages", "first"), emp=("employment", "mean")).reset_index()
    wages = county_q.groupby(["cbsa_code", "year", "qtr"]).agg(
        wages=("wages", "sum"), emp=("emp", "sum")).reset_index()
    wages["avg_weekly_wage"] = wages["wages"] / wages["emp"] / 13
    jobs["year"], jobs["qtr"] = jobs["date"].dt.year, (jobs["date"].dt.month - 1) // 3 + 1
    out = jobs.merge(wages[["cbsa_code", "year", "qtr", "avg_weekly_wage"]],
                     on=["cbsa_code", "year", "qtr"], how="left")
    out.loc[out["n_missing"] > 0, "employment"] = np.nan  # don't report a partial metro total
    return out.drop(columns=["year", "qtr"])


def run() -> pd.DataFrame:
    xpath = CLEAN_DIR / "county_to_cbsa.parquet"
    if not xpath.exists():
        raise SourceError("Run `python -m pipeline.geo` first.")
    county_to_cbsa = pd.read_parquet(xpath)

    frames = []
    for year in range(QCEW_START_YEAR, date.today().year + 1):
        for qtr in (1, 2, 3, 4):
            try:
                frames.append(to_monthly_county(fetch_quarter(year, qtr)))
            except SourceError:
                log.info("QCEW %s Q%s not published yet; stopping here.", year, qtr)
                break
        else:
            continue
        break
    if not frames:
        raise SourceError("No QCEW quarters downloaded.")

    county = pd.concat(frames, ignore_index=True)
    if county.empty:
        raise SourceError("QCEW files loaded but no county rows matched; BLS codes may have changed.")
    county.to_parquet(CLEAN_DIR / "qcew_county.parquet", index=False)

    metro = to_metro(county, county_to_cbsa)
    metro.to_parquet(CLEAN_DIR / "qcew_metro.parquet", index=False)

    latest = county["date"].max().strftime("%Y-%m")
    record_run("bls_qcew", len(county), latest)
    log.info("QCEW: %s counties, %s metros, %s months, latest %s",
             f"{county['county_fips'].nunique():,}", metro["cbsa_code"].nunique(),
             county["date"].nunique(), latest)
    return metro


if __name__ == "__main__":
    run()
