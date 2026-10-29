"""Census American Community Survey (5-year): income, renters, rent burden, housing.

Pulled at county level for every year, then rolled up to CURRENT (2023) metro
definitions. Metro boundaries change over time; using one fixed definition keeps
the panel consistent so "Austin grew X%" means the same Austin every year.

Run:  python -m pipeline.census_acs     (run pipeline.geo first)
"""
import numpy as np
import pandas as pd
import requests

from pipeline.config import ACS_YEARS, CENSUS_API_KEY, CLEAN_DIR
from pipeline.utils import HEADERS, SourceError, log, record_run

ACS_URL = "https://api.census.gov/data/{year}/acs/acs5"

VARIABLES = {
    "B01003_001E": "population",
    "B19013_001E": "median_household_income",
    "B25001_001E": "housing_units",
    "B25003_001E": "occupied_units",
    "B25003_003E": "renter_units",
    "B25064_001E": "median_gross_rent",
    "B25077_001E": "median_home_value",
    "B25070_001E": "renters_total",
    "B25070_007E": "rent_30_35pct",
    "B25070_008E": "rent_35_40pct",
    "B25070_009E": "rent_40_50pct",
    "B25070_010E": "rent_50plus_pct",
    "B25070_011E": "rent_not_computed",
}


def fetch_year(year: int) -> pd.DataFrame:
    params = {"get": "NAME," + ",".join(VARIABLES), "for": "county:*", "in": "state:*"}
    if CENSUS_API_KEY:
        params["key"] = CENSUS_API_KEY
    resp = requests.get(ACS_URL.format(year=year), params=params, headers=HEADERS, timeout=120)
    if resp.status_code == 404:
        raise SourceError(f"ACS {year} 5-year not published yet")
    if resp.status_code != 200 or not resp.text.startswith("["):
        raise SourceError(f"ACS {year} returned HTTP {resp.status_code}: {resp.text[:200]}")
    rows = resp.json()
    return clean_year(pd.DataFrame(rows[1:], columns=rows[0]), year)


def clean_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    df = df.rename(columns=VARIABLES)
    for col in VARIABLES.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # Census uses large negative codes (-666666666 etc.) for "not available"
        df.loc[df[col] < 0, col] = np.nan
    df["county_fips"] = df["state"].str.zfill(2) + df["county"].str.zfill(3)
    df["year"] = year
    burdened = df[["rent_30_35pct", "rent_35_40pct", "rent_40_50pct", "rent_50plus_pct"]].sum(axis=1)
    df["rent_burdened_units"] = burdened
    df["rent_burden_base"] = df["renters_total"] - df["rent_not_computed"].fillna(0)
    df["owner_units"] = df["occupied_units"] - df["renter_units"]
    keep = ["county_fips", "NAME", "year", "population", "median_household_income",
            "housing_units", "occupied_units", "renter_units", "owner_units",
            "median_gross_rent", "median_home_value", "rent_burdened_units", "rent_burden_base"]
    return df[keep].rename(columns={"NAME": "county_label"})


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    ok = values.notna() & weights.notna() & (weights > 0)
    return float(np.average(values[ok], weights=weights[ok])) if ok.any() else np.nan


def to_metro(county: pd.DataFrame, county_to_cbsa: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Roll counties up to metros. Counts are summed. Medians can't be summed, so we
    use a weighted average of county medians (an approximation, documented)."""
    m = county.merge(county_to_cbsa[["county_fips", "cbsa_code"]], on="county_fips", how="left")
    unmapped = m[m["cbsa_code"].isna()]
    m = m.dropna(subset=["cbsa_code"])

    def agg(g):
        return pd.Series({
            "population": g["population"].sum(),
            "housing_units": g["housing_units"].sum(),
            "occupied_units": g["occupied_units"].sum(),
            "renter_units": g["renter_units"].sum(),
            "median_household_income": weighted_mean(g["median_household_income"], g["occupied_units"]),
            "median_gross_rent": weighted_mean(g["median_gross_rent"], g["renter_units"]),
            "median_home_value": weighted_mean(g["median_home_value"], g["owner_units"]),
            "rent_burdened_units": g["rent_burdened_units"].sum(),
            "rent_burden_base": g["rent_burden_base"].sum(),
            "n_counties": len(g),
        })

    metro = m.groupby(["cbsa_code", "year"]).apply(agg, include_groups=False).reset_index()
    metro["renter_share"] = metro["renter_units"] / metro["occupied_units"]
    metro["rent_burden_rate"] = metro["rent_burdened_units"] / metro["rent_burden_base"]
    return metro, unmapped


def run() -> pd.DataFrame:
    xpath = CLEAN_DIR / "county_to_cbsa.parquet"
    if not xpath.exists():
        raise SourceError("Run `python -m pipeline.geo` first.")
    county_to_cbsa = pd.read_parquet(xpath)

    frames = []
    for year in ACS_YEARS:
        try:
            df = fetch_year(year)
        except SourceError as exc:
            log.info("Skipping: %s", exc)
            continue
        log.info("ACS %s: %s counties", year, f"{len(df):,}")
        frames.append(df)
    if not frames:
        raise SourceError("No ACS years downloaded. Check your CENSUS_API_KEY and that it is activated.")

    county = pd.concat(frames, ignore_index=True)
    county.to_parquet(CLEAN_DIR / "acs_county.parquet", index=False)

    metro, unmapped = to_metro(county, county_to_cbsa)
    metro.to_parquet(CLEAN_DIR / "acs_metro.parquet", index=False)

    # Rural counties outside any metro are expected. Old Connecticut counties (09001-09015)
    # are also expected: Connecticut switched to planning regions, which the 2023 metro
    # definitions use. Log it instead of hiding it.
    pop_share = unmapped.groupby("year")["population"].sum() / county.groupby("year")["population"].sum()
    for yr, share in pop_share.items():
        log.info("ACS %s: %.1f%% of U.S. population is outside any metro/micro (expected ~6%%)", yr, share * 100)
    ct_old = unmapped["county_fips"].str.match(r"^090(0[1-9]|1[0-5])$").sum()
    if ct_old:
        log.info("%s rows are pre-2022 Connecticut counties not in current metro definitions "
                 "(see docs/decisions.md)", ct_old)

    latest = str(county["year"].max())
    record_run("census_acs5", len(county), latest)
    log.info("Saved acs_county.parquet and acs_metro.parquet (%s metros, years %s-%s)",
             metro["cbsa_code"].nunique(), county["year"].min(), latest)
    return metro


if __name__ == "__main__":
    run()
