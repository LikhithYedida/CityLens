"""Metro coordinates and state outlines for maps and distance calculations.

  - Census Gazetteer: an interior point (latitude/longitude) for every metro area
  - Census cartographic boundaries: simplified state outlines (1:20 million) for maps

Run:  python -m pipeline.geo_shapes
"""
import io
import zipfile

import pandas as pd

from pipeline.config import CLEAN_DIR, GAZETTEER_CBSA_URL, RAW_DIR, STATE_SHAPES_URL
from pipeline.utils import SourceError, download, log, record_run

GEO_DIR = RAW_DIR / "geo"
STATE_SHP = GEO_DIR / "cb_2023_us_state_20m.shp"


def parse_gazetteer(raw: bytes) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.endswith(".txt"))
    g = pd.read_csv(z.open(name), sep="\t", dtype=str)
    g.columns = [c.strip() for c in g.columns]
    needed = {"GEOID", "NAME", "INTPTLAT", "INTPTLONG"}
    if not needed <= set(g.columns):
        raise SourceError(f"Gazetteer layout changed; missing {needed - set(g.columns)}")
    out = pd.DataFrame({
        "cbsa_code": g["GEOID"].str.strip(),
        "name": g["NAME"].str.strip(),
        "lat": pd.to_numeric(g["INTPTLAT"].str.strip(), errors="coerce"),
        "lon": pd.to_numeric(g["INTPTLONG"].str.strip(), errors="coerce"),
    }).dropna(subset=["lat", "lon"])
    if not (out["lat"].between(17, 72).all() and out["lon"].between(-180, -60).all()):
        raise SourceError("Gazetteer coordinates outside the U.S.; file layout probably changed.")
    return out.drop_duplicates("cbsa_code")


def run() -> pd.DataFrame:
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    gaz = download(GAZETTEER_CBSA_URL, GEO_DIR / "gazetteer_cbsa.zip")
    pts = parse_gazetteer(gaz.read_bytes())
    pts.to_parquet(CLEAN_DIR / "cbsa_points.parquet", index=False)
    record_run("census_gazetteer_cbsa", len(pts), "2024")

    shp_zip = download(STATE_SHAPES_URL, GEO_DIR / "states_20m.zip")
    zipfile.ZipFile(shp_zip).extractall(GEO_DIR)
    if not STATE_SHP.exists():
        raise SourceError("State shapefile missing after unzip.")
    log.info("Saved cbsa_points.parquet (%s metros) and state outlines", len(pts))
    return pts


if __name__ == "__main__":
    run()
