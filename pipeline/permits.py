"""Census Building Permits Survey: new homes authorized each year, by county and metro.

Permits are a leading indicator of new housing supply: a permit today becomes a
finished home in roughly 1-2 years. Comparing permits to population and job growth
shows where supply is keeping up with demand and where it is falling behind.

The annual county file has two header rows, then one row per county with
buildings, units, and value for 1-unit, 2-unit, 3-4 unit and 5+ unit structures.
It repeats those columns twice: first the full estimates (with imputation for
offices that didn't report), then reported-only counts. We use the full estimates.

Run:  python -m pipeline.permits     (run pipeline.geo first)
"""
from datetime import date
from io import StringIO

import pandas as pd

from pipeline.config import CLEAN_DIR, PERMITS_COUNTY_URL, PERMITS_START_YEAR, RAW_DIR
from pipeline.utils import SourceError, download, log, record_run

PERMITS_DIR = RAW_DIR / "permits"
UNIT_TYPES = ["units_1", "units_2", "units_3_4", "units_5plus"]

# Sanity range for total U.S. units authorized in one year (actual: roughly 1.1M-1.9M).
NATIONAL_UNITS_RANGE = (700_000, 2_500_000)


def fetch_year(year: int) -> str:
    PERMITS_DIR.mkdir(exist_ok=True)
    path = PERMITS_DIR / f"co{year}a.txt"
    if not path.exists() or year >= date.today().year - 1:  # recent years get revised
        download(PERMITS_COUNTY_URL.format(year=year), path)
    return path.read_text(encoding="latin-1")


def parse_year(text: str, year: int) -> pd.DataFrame:
    """Find the 'Units' columns from the header instead of trusting fixed positions,
    so a small layout change fails loudly instead of reading the wrong column."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        raise SourceError(f"Permits {year} file is too short to be real data.")
    header2 = [h.strip().lower() for h in lines[1].split(",")]
    unit_cols = [i for i, h in enumerate(header2) if h == "units"]
    if len(unit_cols) < 4:
        raise SourceError(f"Permits {year}: expected 4+ 'Units' columns, found {len(unit_cols)}.")

    body = pd.read_csv(StringIO("\n".join(lines[2:])), header=None, dtype=str)
    out = pd.DataFrame({
        "county_fips": body[1].str.strip().str.zfill(2) + body[2].str.strip().str.zfill(3),
        "county_label": body[5].str.strip() if body.shape[1] > 5 else None,
        "year": year,
    })
    for name, col in zip(UNIT_TYPES, unit_cols[:4]):  # first four = full estimates
        out[name] = pd.to_numeric(body[col], errors="coerce").fillna(0)
    out["units_total"] = out[UNIT_TYPES].sum(axis=1)
    out["units_multifamily"] = out[["units_2", "units_3_4", "units_5plus"]].sum(axis=1)
    out = out[out["county_fips"].str.fullmatch(r"\d{5}")]
    return drop_alias_rows(out, year)


def drop_alias_rows(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Census lists a few counties twice under an old and new name (for example
    'Anchorage Borough' and 'Anchorage Municipality') with identical numbers.
    Keep one copy. If a code ever repeats with DIFFERENT numbers, stop: that's
    a real data problem, not a naming alias."""
    dup = df[df["county_fips"].duplicated(keep=False)]
    if dup.empty:
        return df
    conflicting = dup.groupby("county_fips")[UNIT_TYPES].nunique().gt(1).any(axis=1)
    if conflicting.any():
        raise SourceError(f"Permits {year}: county codes repeat with different numbers: "
                          f"{list(conflicting[conflicting].index)}")
    log.info("Permits %s: dropped %s duplicate name rows (%s)", year,
             len(dup) - dup["county_fips"].nunique(), ", ".join(sorted(dup["county_fips"].unique())))
    return df.drop_duplicates("county_fips", keep="first")


def validate(df: pd.DataFrame, year: int) -> None:
    total = df["units_total"].sum()
    low, high = NATIONAL_UNITS_RANGE
    if not low <= total <= high:
        raise SourceError(
            f"Permits {year}: national total {total:,.0f} units is outside the realistic "
            f"range {low:,}-{high:,}. The file layout probably changed; check the header rows.")
    if df["county_fips"].duplicated().any():
        raise SourceError(f"Permits {year}: duplicate county rows.")


def to_metro(county: pd.DataFrame, county_to_cbsa: pd.DataFrame) -> pd.DataFrame:
    m = county.merge(county_to_cbsa[["county_fips", "cbsa_code"]], on="county_fips", how="inner")
    cols = UNIT_TYPES + ["units_total", "units_multifamily"]
    metro = m.groupby(["cbsa_code", "year"])[cols].sum().reset_index()
    metro["multifamily_share"] = metro["units_multifamily"] / metro["units_total"].where(metro["units_total"] > 0)
    return metro


def run() -> pd.DataFrame:
    xpath = CLEAN_DIR / "county_to_cbsa.parquet"
    if not xpath.exists():
        raise SourceError("Run `python -m pipeline.geo` first.")
    county_to_cbsa = pd.read_parquet(xpath)

    frames = []
    for year in range(PERMITS_START_YEAR, date.today().year + 1):
        try:
            df = parse_year(fetch_year(year), year)
            validate(df, year)
        except SourceError as exc:
            if year >= date.today().year - 1:
                log.info("Permits %s not published yet (%s)", year, exc)
                continue
            raise
        log.info("Permits %s: %s counties, %s units authorized nationally",
                 year, f"{len(df):,}", f"{df['units_total'].sum():,.0f}")
        frames.append(df)

    county = pd.concat(frames, ignore_index=True)
    county.to_parquet(CLEAN_DIR / "permits_county.parquet", index=False)
    metro = to_metro(county, county_to_cbsa)
    metro.to_parquet(CLEAN_DIR / "permits_metro.parquet", index=False)

    latest = str(county["year"].max())
    record_run("census_permits", len(county), latest)
    log.info("Saved permits_county and permits_metro (%s metros, %s-%s)",
             metro["cbsa_code"].nunique(), county["year"].min(), latest)
    return metro


if __name__ == "__main__":
    run()
