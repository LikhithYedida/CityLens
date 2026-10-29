"""FRED: 30-year mortgage rate and CPI, rolled up to monthly.

The mortgage rate is weekly, so we average it to one value per month to
match Zillow's monthly data.

Run:  python -m pipeline.fred
"""
import pandas as pd
import requests

from pipeline.config import CLEAN_DIR, FRED_API_KEY, FRED_SERIES, START_DATE
from pipeline.utils import HEADERS, SourceError, log, record_run

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id: str) -> pd.DataFrame:
    if not FRED_API_KEY:
        raise SourceError("FRED_API_KEY is missing. Add it to your .env file.")
    params = {"series_id": series_id, "api_key": FRED_API_KEY,
              "file_type": "json", "observation_start": START_DATE}
    resp = requests.get(FRED_URL, params=params, headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        raise SourceError(f"FRED {series_id} returned HTTP {resp.status_code}: {resp.text[:200]}")
    obs = pd.DataFrame(resp.json().get("observations", []))
    if obs.empty:
        raise SourceError(f"FRED {series_id} returned no observations.")
    return obs


def to_monthly(obs: pd.DataFrame, column: str) -> pd.DataFrame:
    obs = obs.copy()
    obs["date"] = pd.to_datetime(obs["date"])
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")  # FRED uses "." for missing
    monthly = (obs.dropna(subset=["value"])
                  .set_index("date")["value"]
                  .resample("MS").mean()
                  .rename(column))
    return monthly.to_frame()


def run() -> pd.DataFrame:
    parts = []
    for series_id, column in FRED_SERIES.items():
        try:
            parts.append(to_monthly(fetch_series(series_id), column))
        except SourceError as exc:
            log.error(str(exc))
            record_run(f"fred_{series_id}", 0, "", status="failed", note=str(exc))
    if not parts:
        raise SourceError("All FRED series failed. See messages above.")

    df = pd.concat(parts, axis=1).reset_index()
    latest = df["date"].max().strftime("%Y-%m")
    record_run("fred", len(df), latest)
    df.to_parquet(CLEAN_DIR / "fred_macro.parquet", index=False)
    log.info("Saved data/clean/fred_macro.parquet (%s months, latest %s)", len(df), latest)
    return df


if __name__ == "__main__":
    run()
