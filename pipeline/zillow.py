"""Zillow home values (ZHVI) and rents (ZORI): download, reshape, validate.

Zillow ships "wide" files: one row per region, one column per month.
We reshape them to "long" (one row per region per month), which is what
joins, charts, and models all expect.

Run:  python -m pipeline.zillow
"""
import pandas as pd

from pipeline.config import CLEAN_DIR, RAW_DIR, START_DATE, ZILLOW_FILES
from pipeline.utils import SourceError, download, log, record_run

ID_COLS = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName",
           "State", "Metro", "StateCodeFIPS", "MunicipalCodeFIPS"]


def reshape(wide: pd.DataFrame, metric: str, geography: str) -> pd.DataFrame:
    """Turn Zillow's wide monthly file into a tidy long table."""
    id_cols = [c for c in ID_COLS if c in wide.columns]
    date_cols = [c for c in wide.columns if c not in id_cols]
    if not date_cols:
        raise SourceError("No monthly date columns found; Zillow's file layout changed.")

    long = wide.melt(id_vars=id_cols, value_vars=date_cols, var_name="date", value_name="value")
    long["date"] = pd.to_datetime(long["date"], errors="coerce")
    long = long.dropna(subset=["date", "value"])
    long = long[long["date"] >= START_DATE]
    long = long[long["RegionType"].str.lower() != "country"]  # keep the U.S. total out of metro tables

    out = pd.DataFrame({
        "zillow_region_id": long["RegionID"].astype("int64"),
        "region_name": long["RegionName"],
        "state": long.get("StateName", long.get("State")),
        "geography": geography,
        "date": long["date"].dt.to_period("M").dt.to_timestamp(),  # first of month
        "metric": metric,
        "value": long["value"].astype(float),
    })
    if "Metro" in long.columns:
        out["metro_name"] = long["Metro"]  # used later to cross-check the metro crosswalk
    if geography == "county" and {"StateCodeFIPS", "MunicipalCodeFIPS"} <= set(long.columns):
        # 5-digit county FIPS: the key that joins to Census, BLS, and IRS data
        out["county_fips"] = (long["StateCodeFIPS"].astype(int).astype(str).str.zfill(2)
                              + long["MunicipalCodeFIPS"].astype(int).astype(str).str.zfill(3))
    return out


def validate(df: pd.DataFrame, name: str) -> None:
    """Basic checks so bad data never reaches the analysis."""
    problems = []
    if df.empty:
        problems.append("table is empty")
    if (df["value"] <= 0).any():
        problems.append(f"{(df['value'] <= 0).sum()} non-positive values")
    dupes = df.duplicated(["zillow_region_id", "date"]).sum()
    if dupes:
        problems.append(f"{dupes} duplicate region-month rows")
    if problems:
        raise SourceError(f"{name} failed validation: " + "; ".join(problems))


def run() -> pd.DataFrame:
    frames = []
    for name, (url, metric, geography) in ZILLOW_FILES.items():
        try:
            raw_path = download(url, RAW_DIR / f"zillow_{name}.csv")
            df = reshape(pd.read_csv(raw_path), metric, geography)
            validate(df, name)
        except SourceError as exc:
            log.error(str(exc))
            record_run(f"zillow_{name}", 0, "", status="failed", note=str(exc))
            continue
        latest = df["date"].max().strftime("%Y-%m")
        log.info("%s: %s rows, %s regions, latest %s",
                 name, f"{len(df):,}", df["zillow_region_id"].nunique(), latest)
        record_run(f"zillow_{name}", len(df), latest)
        frames.append(df)

    if not frames:
        raise SourceError("All Zillow downloads failed. See messages above.")
    combined = pd.concat(frames, ignore_index=True)
    combined.to_parquet(CLEAN_DIR / "zillow_housing.parquet", index=False)
    log.info("Saved data/clean/zillow_housing.parquet (%s rows)", f"{len(combined):,}")
    return combined


if __name__ == "__main__":
    run()
