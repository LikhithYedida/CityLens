"""Central settings: paths, API keys, and source URLs.

Zillow changes its CSV download paths from time to time. If a download
fails, open https://www.zillow.com/research/data/, right-click the
matching "Download" link, copy the new URL, and paste it below.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
RAW_DIR.mkdir(parents=True, exist_ok=True)
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")
BLS_API_KEY = os.getenv("BLS_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Analysis window. Zillow's rent index (ZORI) starts in 2015.
START_DATE = "2015-01-01"

_Z = "https://files.zillowstatic.com/research/public_csvs"
ZILLOW_FILES = {
    # name: (url, metric, geography)
    "metro_home_value": (f"{_Z}/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv", "home_value", "metro"),
    "metro_rent":       (f"{_Z}/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv", "rent", "metro"),
    "county_home_value": (f"{_Z}/zhvi/County_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv", "home_value", "county"),
    "county_rent":       (f"{_Z}/zori/County_zori_uc_sfrcondomfr_sm_month.csv", "rent", "county"),
}

# Official metro definitions (July 2023 delineation, the latest Census publishes).
CBSA_DELINEATION_URL = ("https://www2.census.gov/programs-surveys/metro-micro/geographies/"
                        "reference-files/2023/delineation-files/list1_2023.xlsx")

# Census ACS 5-year: years to try. Years not yet published are skipped with a log line.
ACS_YEARS = list(range(2015, 2026))

# BLS QCEW: county and metro jobs/wages. No key needed.
QCEW_URL = "https://data.bls.gov/cew/data/api/{year}/{qtr}/industry/10.csv"  # 10 = all industries
QCEW_START_YEAR = 2015

# FRED series: 30-year fixed mortgage rate (weekly) and CPI (monthly, for
# turning nominal dollars into inflation-adjusted dollars later).
FRED_SERIES = {
    "MORTGAGE30US": "mortgage_rate_30y",
    "CPIAUCSL": "cpi",
}

# Census Building Permits Survey: annual county files (new housing units authorized).
PERMITS_COUNTY_URL = "https://www2.census.gov/econ/bps/County/co{year}a.txt"
PERMITS_START_YEAR = 2015

# IRS migration: county inflow/outflow files, named by the two filing years ("2223").
IRS_INFLOW_URL = "https://www.irs.gov/pub/irs-soi/countyinflow{yy}.csv"
IRS_OUTFLOW_URL = "https://www.irs.gov/pub/irs-soi/countyoutflow{yy}.csv"
IRS_FIRST_PERIOD = 2015   # 2015-2016 file ("1516")
IRS_NEW_SERIES_FROM = 2022  # 2022-2023 file onward uses the IRS's enhanced matching
