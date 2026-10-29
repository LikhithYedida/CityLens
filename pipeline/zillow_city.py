"""Zillow city-level rents (ZORI) and home values (ZHVI) for the Policy Lab.

Policies like zoning reform happen at the city level, so evaluating them needs
city data, not metro data. Keeps the ~1,000 largest cities plus every Minnesota city
(so Minneapolis's suburbs are available for the same-market check).

Run:  python -m pipeline.zillow_city
"""
import pandas as pd

from pipeline.config import CLEAN_DIR, RAW_DIR, START_DATE, ZILLOW_CITY_FILES
from pipeline.utils import SourceError, download, log, record_run

KEEP_MAX_SIZE_RANK = 1000
ALWAYS_KEEP_STATES = {"MN"}
ID_COLS = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName", "State", "Metro", "CountyName"]


def reshape(wide: pd.DataFrame, metric: str) -> pd.DataFrame:
    if "SizeRank" not in wide.columns or "RegionName" not in wide.columns:
        raise SourceError("Zillow city file layout changed: missing SizeRank or RegionName.")
    keep = (wide["SizeRank"] <= KEEP_MAX_SIZE_RANK) | wide["State"].isin(ALWAYS_KEEP_STATES)
    wide = wide[keep]
    id_cols = [c for c in ID_COLS if c in wide.columns]
    long = wide.melt(id_vars=id_cols, var_name="date", value_name="value")
    long["date"] = pd.to_datetime(long["date"], errors="coerce")
    long = long.dropna(subset=["date", "value"])
    long = long[long["date"] >= START_DATE]
    return pd.DataFrame({
        "city_key": long["RegionName"] + ", " + long["State"],
        "zillow_region_id": long["RegionID"].astype("int64"),
        "city": long["RegionName"],
        "state": long["State"],
        "metro": long.get("Metro"),
        "size_rank": long["SizeRank"].astype("int64"),
        "date": long["date"].dt.to_period("M").dt.to_timestamp(),
        "metric": metric,
        "value": long["value"].astype(float),
    })


def validate(df: pd.DataFrame, metric: str) -> None:
    if df.empty or (df["value"] <= 0).any():
        raise SourceError(f"Zillow city {metric}: empty table or non-positive values.")
    dupes = df.duplicated(["zillow_region_id", "date"]).sum()
    if dupes:
        raise SourceError(f"Zillow city {metric}: {dupes} duplicate city-month rows.")
    if "Minneapolis, MN" not in set(df["city_key"]):
        raise SourceError(f"Zillow city {metric}: Minneapolis is missing.")


def run() -> pd.DataFrame:
    frames = []
    for metric, url in ZILLOW_CITY_FILES.items():
        path = download(url, RAW_DIR / f"zillow_city_{metric}.csv", timeout=300)
        df = reshape(pd.read_csv(path), metric)
        validate(df, metric)
        latest = df["date"].max().strftime("%Y-%m")
        log.info("Zillow city %s: %s cities, latest %s", metric, df["city_key"].nunique(), latest)
        record_run(f"zillow_city_{metric}", len(df), latest)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(CLEAN_DIR / "zillow_city.parquet", index=False)
    log.info("Saved data/clean/zillow_city.parquet (%s rows)", f"{len(out):,}")
    return out


if __name__ == "__main__":
    run()
