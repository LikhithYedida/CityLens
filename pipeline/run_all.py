"""Run the whole pipeline in the right order.

Run:  python -m pipeline.run_all
"""
from pipeline import build_panel, census_acs, fred, geo, geo_shapes, migration, permits, qcew, zillow, zillow_city
from analysis import forecast_engine, opportunity_index, policy_lab, rising_cities, ripple_map
from pipeline.utils import log

STEPS = [("Zillow", zillow.run), ("FRED", fred.run), ("Crosswalk", geo.run),
         ("Census ACS", census_acs.run), ("BLS QCEW", qcew.run),
         ("Building permits", permits.run), ("IRS migration", migration.run),
         ("Master panel", build_panel.run),
         ("Opportunity Index", opportunity_index.run),
         ("Rising City Detector", rising_cities.run),
         ("Zillow city data", zillow_city.run), ("Policy Lab", policy_lab.run),
         ("Forecast Engine", forecast_engine.run),
         ("Metro coordinates and maps", geo_shapes.run), ("Ripple Map", ripple_map.run)]

if __name__ == "__main__":
    failed = []
    for name, step in STEPS:
        log.info("===== %s =====", name)
        try:
            step()
        except Exception as exc:  # keep going so one source doesn't block the rest
            log.error("%s failed: %s: %s", name, type(exc).__name__, exc)
            failed.append(name)
    log.info("Done. Failed steps: %s", ", ".join(failed) if failed else "none")
