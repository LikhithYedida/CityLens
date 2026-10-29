"""Geography crosswalk: the backbone that lets every source join.

Every source names places differently:
  - Census, BLS, IRS use official codes (5-digit county FIPS, 5-digit CBSA metro codes)
  - Zillow uses its own RegionIDs and short names like "Detroit, MI"

This script builds two tables:
  1. county_to_cbsa:   every U.S. county -> its official metro (CBSA)
  2. zillow_metro_xwalk: every Zillow metro -> official CBSA code, with HOW it matched

Two independent match methods are used and compared. A match-rate report is saved
so you can show exactly how much data joined and why the rest did not.

Run:  python -m pipeline.geo      (run pipeline.zillow first)
"""
import re

import pandas as pd

from pipeline.config import CBSA_DELINEATION_URL, CLEAN_DIR, RAW_DIR, ROOT
from pipeline.utils import SourceError, download, log, record_run

OVERRIDES_PATH = ROOT / "docs" / "crosswalk_overrides.csv"
REPORT_PATH = ROOT / "docs" / "crosswalk_report.md"


# ---------- 1. County -> CBSA from the official Census delineation ----------

def load_delineation() -> pd.DataFrame:
    path = RAW_DIR / "cbsa_delineation_2023.xlsx"
    if not path.exists():
        download(CBSA_DELINEATION_URL, path)
    # The file has two title rows above the real header and footnotes at the bottom.
    raw = pd.read_excel(path, skiprows=2, dtype=str)
    return clean_delineation(raw)


def clean_delineation(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.rename(columns=lambda c: str(c).strip())
    needed = ["CBSA Code", "CBSA Title", "Metropolitan/Micropolitan Statistical Area",
              "County/County Equivalent", "State Name", "FIPS State Code", "FIPS County Code"]
    missing = [c for c in needed if c not in raw.columns]
    if missing:
        raise SourceError(f"Delineation file layout changed; missing columns: {missing}")

    df = raw.dropna(subset=["CBSA Code", "FIPS State Code", "FIPS County Code"]).copy()
    out = pd.DataFrame({
        "county_fips": df["FIPS State Code"].str.zfill(2) + df["FIPS County Code"].str.zfill(3),
        "county_name": df["County/County Equivalent"],
        "state_name": df["State Name"],
        "cbsa_code": df["CBSA Code"].str.strip(),
        "cbsa_title": df["CBSA Title"].str.strip(),
        "cbsa_type": df["Metropolitan/Micropolitan Statistical Area"]
                       .str.replace(" Statistical Area", "", regex=False).str.strip(),
    })
    if "Central/Outlying County" in df.columns:
        out["central_or_outlying"] = df["Central/Outlying County"].values
    return out.drop_duplicates("county_fips").reset_index(drop=True)


# ---------- 2. Zillow metro -> CBSA ----------

def normalize_place(text: str) -> str:
    """Make 'St. Louis' and 'Saint Louis' and 'st louis' compare equal."""
    t = str(text).lower().strip()
    t = re.sub(r"\bsaint\b", "st", t)
    t = re.sub(r"\bste\b", "ste", t)
    t = t.replace(".", "").replace("'", "")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def cbsa_short_key(cbsa_title: str) -> str:
    """'New York-Newark-Jersey City, NY-NJ' -> 'new york|ny' (first city, first state)."""
    if "," not in cbsa_title:
        return normalize_place(cbsa_title)
    cities, states = cbsa_title.rsplit(",", 1)
    first_city = re.split(r"[-/]", cities)[0]
    first_state = states.strip().split("-")[0]
    return f"{normalize_place(first_city)}|{first_state.strip().lower()}"


def zillow_short_key(region_name: str) -> str:
    """'Detroit, MI' -> 'detroit|mi'."""
    return cbsa_short_key(region_name)


def match_by_name(zillow_metros: pd.DataFrame, cbsas: pd.DataFrame) -> pd.DataFrame:
    keys = cbsas.assign(key=cbsas["cbsa_title"].map(cbsa_short_key))
    dup_keys = keys["key"][keys["key"].duplicated(keep=False)]
    keys = keys[~keys["key"].isin(dup_keys)]  # ambiguous keys never auto-match
    z = zillow_metros.assign(key=zillow_metros["region_name"].map(zillow_short_key))
    m = z.merge(keys[["key", "cbsa_code"]], on="key", how="left")
    return m[["zillow_region_id", "cbsa_code"]].rename(columns={"cbsa_code": "cbsa_by_name"})


def match_by_county_vote(zillow_counties: pd.DataFrame, county_to_cbsa: pd.DataFrame,
                         zillow_metros: pd.DataFrame) -> pd.DataFrame:
    """Zillow's county file says which metro each county belongs to. Look up those
    counties' official CBSA and take the majority vote."""
    if "metro_name" not in zillow_counties.columns:
        return pd.DataFrame(columns=["zillow_region_id", "cbsa_by_county", "vote_share"])
    c = (zillow_counties.dropna(subset=["metro_name", "county_fips"])
         .drop_duplicates("county_fips")
         .merge(county_to_cbsa[["county_fips", "cbsa_code"]], on="county_fips", how="inner"))
    votes = c.groupby(["metro_name", "cbsa_code"]).size().rename("n").reset_index()
    votes["vote_share"] = votes["n"] / votes.groupby("metro_name")["n"].transform("sum")
    winners = votes.sort_values("n", ascending=False).drop_duplicates("metro_name")
    m = zillow_metros.merge(winners, left_on="region_name", right_on="metro_name", how="left")
    return m[["zillow_region_id", "cbsa_code", "vote_share"]].rename(
        columns={"cbsa_code": "cbsa_by_county"})


def build_crosswalk(zillow: pd.DataFrame, county_to_cbsa: pd.DataFrame) -> pd.DataFrame:
    metros = (zillow[zillow["geography"] == "metro"]
              [["zillow_region_id", "region_name", "state"]].drop_duplicates("zillow_region_id"))
    counties = zillow[zillow["geography"] == "county"]
    cbsas = county_to_cbsa[["cbsa_code", "cbsa_title", "cbsa_type"]].drop_duplicates("cbsa_code")

    x = (metros.merge(match_by_name(metros, cbsas), on="zillow_region_id", how="left")
               .merge(match_by_county_vote(counties, county_to_cbsa, metros),
                      on="zillow_region_id", how="left"))

    def decide(r):
        a, b = r["cbsa_by_name"], r["cbsa_by_county"]
        if pd.notna(a) and pd.notna(b):
            return (a, "both_agree") if a == b else (b, "conflict_used_county_vote")
        if pd.notna(b):
            return b, "county_vote_only"
        if pd.notna(a):
            return a, "name_only"
        return None, "unmatched"

    x[["cbsa_code", "match_method"]] = x.apply(lambda r: pd.Series(decide(r)), axis=1)

    if OVERRIDES_PATH.exists():  # hand-checked fixes always win
        ov = pd.read_csv(OVERRIDES_PATH, dtype=str, encoding="utf-8")
        if not ov.empty:
            ov["zillow_region_id"] = ov["zillow_region_id"].astype("int64")
            x = x.merge(ov.rename(columns={"cbsa_code": "cbsa_override"}),
                        on="zillow_region_id", how="left")
            has = x["cbsa_override"].notna()
            x.loc[has, "cbsa_code"] = x.loc[has, "cbsa_override"]
            x.loc[has, "match_method"] = "manual_override"
            x = x.drop(columns=["cbsa_override", "note"], errors="ignore")

    return x.merge(cbsas, on="cbsa_code", how="left")


def write_report(x: pd.DataFrame) -> None:
    counts = x["match_method"].value_counts()
    matched = x["cbsa_code"].notna().sum()
    lines = [
        "# Zillow to Census Metro Crosswalk Report", "",
        f"**{matched:,} of {len(x):,} Zillow metros matched ({matched / len(x):.1%}).**", "",
        "| Match method | Metros | Meaning |", "|---|---|---|",
    ]
    meaning = {
        "both_agree": "Name match and county vote point to the same metro",
        "county_vote_only": "Matched through the metro's counties",
        "name_only": "Matched by principal city and state",
        "conflict_used_county_vote": "Methods disagreed; county vote used (review these)",
        "manual_override": "Hand-checked in docs/crosswalk_overrides.csv",
        "unmatched": "No match; excluded from joined analysis",
    }
    for method, n in counts.items():
        lines.append(f"| {method} | {n:,} | {meaning.get(method, '')} |")
    review = x[x["match_method"].isin(["conflict_used_county_vote", "unmatched"])]
    if not review.empty:
        lines += ["", "## Needs review", "",
                  "Add fixes to `docs/crosswalk_overrides.csv` (columns: zillow_region_id, cbsa_code, note).", "",
                  "| Zillow ID | Zillow name | Name match | County vote | Chosen CBSA title |",
                  "|---|---|---|---|---|"]
        def show(v):
            return "" if pd.isna(v) else v
        for _, r in review.iterrows():
            lines.append(f"| {r.zillow_region_id} | {r.region_name} | {show(r.cbsa_by_name)} | "
                         f"{show(r.cbsa_by_county)} | {show(r.cbsa_title)} |")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> pd.DataFrame:
    county_to_cbsa = load_delineation()
    county_to_cbsa.to_parquet(CLEAN_DIR / "county_to_cbsa.parquet", index=False)
    log.info("county_to_cbsa: %s counties in %s metros/micros",
             f"{len(county_to_cbsa):,}", county_to_cbsa["cbsa_code"].nunique())
    record_run("cbsa_delineation", len(county_to_cbsa), "2023-07")

    zpath = CLEAN_DIR / "zillow_housing.parquet"
    if not zpath.exists():
        raise SourceError("Run `python -m pipeline.zillow` first.")
    zillow = pd.read_parquet(zpath)
    if "metro_name" not in zillow.columns:
        log.warning("Zillow table has no metro_name column; re-run pipeline.zillow for the "
                    "county-vote check. Continuing with name matching only.")

    x = build_crosswalk(zillow, county_to_cbsa)
    x.to_parquet(CLEAN_DIR / "zillow_metro_xwalk.parquet", index=False)
    write_report(x)
    rate = x["cbsa_code"].notna().mean()
    log.info("Zillow metro crosswalk: %.1f%% matched. Report: docs/crosswalk_report.md", rate * 100)
    record_run("zillow_metro_xwalk", len(x), "", note=f"match_rate={rate:.3f}")
    return x


if __name__ == "__main__":
    run()
