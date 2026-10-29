"""IRS migration: who moved into and out of every county, and how much income they brought.

The IRS compares each tax return's address to the same filer's address the year
before. Each file is named by its two filing years: "2223" means filed in 2022
and in 2023, so the move happened roughly between those two tax seasons.

Each inflow/outflow file has a few summary rows per county, marked with special
state codes in the "other side" columns:
  96 / 000  total movers, U.S. + foreign
  97 / 000  total movers, U.S. only
  98 / 000  foreign
  same county code on both sides = people who did NOT move
We use the summary rows, which include small flows the IRS hides in the
county-to-county rows for privacy.

Run:  python -m pipeline.migration     (run pipeline.geo first)
"""
from datetime import date

import pandas as pd

from pipeline.config import (CLEAN_DIR, IRS_FIRST_PERIOD, IRS_INFLOW_URL, IRS_NEW_SERIES_FROM,
                             IRS_OUTFLOW_URL, RAW_DIR)
from pipeline.utils import SourceError, download, log, record_run

IRS_DIR = RAW_DIR / "irs"
US_AND_FOREIGN, US_ONLY = ("96", "000"), ("97", "000")


def period_code(y1: int) -> str:
    """2022 -> '2223'"""
    return f"{y1 % 100:02d}{(y1 + 1) % 100:02d}"


def fetch(kind: str, y1: int) -> pd.DataFrame:
    IRS_DIR.mkdir(exist_ok=True)
    code = period_code(y1)
    url = (IRS_INFLOW_URL if kind == "inflow" else IRS_OUTFLOW_URL).format(yy=code)
    path = IRS_DIR / f"county{kind}{code}.csv"
    if not path.exists():
        download(url, path)
    # County names include accented letters; IRS files are not UTF-8.
    return pd.read_csv(path, dtype=str, encoding="latin-1")


def summarize(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """One row per county: U.S. movers in (or out), with returns, people, and income."""
    df = df.rename(columns=str.lower)
    if kind == "inflow":   # the county is y2 (destination); the other side is y1
        home_s, home_c, other_s, other_c = "y2_statefips", "y2_countyfips", "y1_statefips", "y1_countyfips"
    else:                  # the county is y1 (origin); the other side is y2
        home_s, home_c, other_s, other_c = "y1_statefips", "y1_countyfips", "y2_statefips", "y2_countyfips"
    needed = {home_s, home_c, other_s, other_c, "n1", "n2", "agi"}
    if not needed <= set(df.columns):
        raise SourceError(f"IRS {kind} file layout changed; missing {needed - set(df.columns)}")

    for c in (home_s, other_s):
        df[c] = df[c].str.strip().str.zfill(2)
    for c in (home_c, other_c):
        df[c] = df[c].str.strip().str.zfill(3)
    for c in ("n1", "n2", "agi"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c] < 0, c] = pd.NA  # -1 = suppressed for privacy

    us = df[(df[other_s] == US_ONLY[0]) & (df[other_c] == US_ONLY[1])]
    out = pd.DataFrame({
        "county_fips": us[home_s] + us[home_c],
        f"{kind}_returns": us["n1"],
        f"{kind}_people": us["n2"],
        f"{kind}_agi_thousands": us["agi"],
    })
    out = out[out["county_fips"].str.fullmatch(r"\d{5}") & ~out["county_fips"].str.endswith("000")]
    return out.drop_duplicates("county_fips")


def build_period(y1: int) -> pd.DataFrame:
    inflow = summarize(fetch("inflow", y1), "inflow")
    outflow = summarize(fetch("outflow", y1), "outflow")
    df = inflow.merge(outflow, on="county_fips", how="outer")
    df["net_people"] = df["inflow_people"] - df["outflow_people"]
    df["net_agi_thousands"] = df["inflow_agi_thousands"] - df["outflow_agi_thousands"]
    df["period"] = f"{y1}-{y1 + 1}"
    df["period_end_year"] = y1 + 1
    df["new_series"] = y1 >= IRS_NEW_SERIES_FROM
    return df


def validate(df: pd.DataFrame, period: str) -> None:
    """U.S.-only moves are a closed system: every move out of one county is a move
    into another. National inflows and outflows should nearly match."""
    ins, outs = df["inflow_people"].sum(), df["outflow_people"].sum()
    if not ins or abs(ins - outs) / ins > 0.05:
        raise SourceError(f"IRS {period}: inflows {ins:,.0f} vs outflows {outs:,.0f} differ by >5%.")


def to_metro(county: pd.DataFrame, county_to_cbsa: pd.DataFrame, acs_county: pd.DataFrame | None) -> pd.DataFrame:
    """Metro NET migration is the sum of its counties' net migration: a move between two
    counties in the same metro adds +1 to one and -1 to the other, so it cancels out.
    Gross inflows/outflows would double count those moves, so we only report net."""
    m = county.merge(county_to_cbsa[["county_fips", "cbsa_code"]], on="county_fips", how="inner")
    metro = (m.groupby(["cbsa_code", "period", "period_end_year", "new_series"])
               [["net_people", "net_agi_thousands"]].sum(min_count=1).reset_index())
    if acs_county is not None:  # scale by population so big and small metros compare fairly
        pop = (acs_county.merge(county_to_cbsa[["county_fips", "cbsa_code"]], on="county_fips")
                         .groupby(["cbsa_code", "year"])["population"].sum().rename("population")
                         .reset_index())
        metro = metro.merge(pop, left_on=["cbsa_code", "period_end_year"],
                            right_on=["cbsa_code", "year"], how="left").drop(columns="year")
        metro["net_migration_rate_per_1k"] = metro["net_people"] / metro["population"] * 1000
    return metro


def run() -> pd.DataFrame:
    xpath = CLEAN_DIR / "county_to_cbsa.parquet"
    if not xpath.exists():
        raise SourceError("Run `python -m pipeline.geo` first.")
    county_to_cbsa = pd.read_parquet(xpath)
    acs_path = CLEAN_DIR / "acs_county.parquet"
    acs_county = pd.read_parquet(acs_path) if acs_path.exists() else None

    frames = []
    for y1 in range(IRS_FIRST_PERIOD, date.today().year):
        try:
            df = build_period(y1)
            validate(df, df["period"].iloc[0])
        except SourceError as exc:
            if y1 >= date.today().year - 4:  # IRS publishes ~2 years after the moves
                log.info("IRS %s-%s not available yet (%s)", y1, y1 + 1, exc)
                continue
            raise
        label = df["period"].iloc[0] + (" [new IRS series]" if df["new_series"].iloc[0] else "")
        log.info("IRS %s: %s counties, %s people moved between counties",
                 label, f"{len(df):,}", f"{df['inflow_people'].sum():,.0f}")
        frames.append(df)
    if not frames:
        raise SourceError("No IRS migration files downloaded.")

    county = pd.concat(frames, ignore_index=True)
    county.to_parquet(CLEAN_DIR / "migration_county.parquet", index=False)
    metro = to_metro(county, county_to_cbsa, acs_county)
    metro.to_parquet(CLEAN_DIR / "migration_metro.parquet", index=False)

    latest = county["period"].iloc[-1]
    record_run("irs_migration", len(county), latest)
    log.info("Saved migration_county and migration_metro (%s metros, latest %s)",
             metro["cbsa_code"].nunique(), latest)
    return metro


if __name__ == "__main__":
    run()
