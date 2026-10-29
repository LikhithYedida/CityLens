# CityLens: Seeing Where Opportunity Is Growing in America

CityLens looks at every U.S. metro each month through one lens: where are jobs, people, and
income arriving faster than prices are climbing? It finds the places where opportunity is
growing and life is still within reach, before everyone else notices.

It ranks 935 metros on how far a paycheck goes today, detects which affordable metros are
about to grow, and tests what actually works (like zoning reform) to keep cities open to the
people who want to build a life there. It serves two audiences:

- **People** deciding where to start a career, raise a family, or stretch a salary further
- **Businesses** (builders, lenders, employers, investors) deciding where to grow next

## Roadmap
| Layer | Question it answers | Status |
|---|---|---|
| 1. Data foundation | 7 public sources joined into one tested metro-by-month table | ✅ Done |
| 2. Opportunity Index | Where does a paycheck go furthest today? | Next |
| 3. Rising City Detector | Which affordable metros are about to grow? | Planned |
| 4. Policy Lab | Did Minneapolis's zoning reform slow rent growth? (synthetic control) | Planned |
| 5. Forecast Engine | Where will rents be in 12 months, with honest uncertainty? | Planned |
| 6. Ripple Map | When a metro booms, which neighbors follow? | Planned |
| 7. Decision Tools | Where should a family move, or a builder build? (app + executive memo) | Planned |
| Ops | Monthly automatic refresh with health checks (GitHub Actions) | Planned |

## Data sources
| Source | What it gives | Status |
|---|---|---|
| Zillow Research (ZHVI, ZORI) | Home values and rents by metro and county | ✅ Built |
| FRED | 30-year mortgage rate, CPI | ✅ Built |
| Census metro definitions (2023) | Which counties make up each metro | ✅ Built |
| Census ACS 5-year | Income, renters, rent burden, home values | ✅ Built |
| BLS QCEW | Monthly jobs and weekly wages | ✅ Built |
| Census Building Permits | New housing supply | ✅ Built |
| IRS SOI Migration | Net movers and income by county and metro | ✅ Built |

## Master panel
`pipeline/build_panel.py` runs the SQL models in `sql/` (DuckDB) to build one table:
**every metro × every month since 2015**, with rent, home value, income, jobs, permits,
migration, and mortgage rate side by side, plus affordability ratios. Eight SQL tests in
`sql/tests/` must pass (zero failing rows each). Coverage and a spot check are written to
`docs/panel_report.md`.

## The crosswalk
Every source names places differently. `pipeline/geo.py` matches Zillow's metros to
official Census metro codes two independent ways, then writes a match-rate report to
`docs/crosswalk_report.md`. Hand-checked fixes go in `docs/crosswalk_overrides.csv`.

## Run it
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then paste your free API keys
python -m pytest                  # offline tests, no internet needed
python -m pipeline.run_all        # runs every source in order
```
Or run one source at a time: `python -m pipeline.zillow`, `pipeline.fred`, `pipeline.geo`,
`pipeline.census_acs`, `pipeline.qcew`, `pipeline.permits`, `pipeline.migration`, then `pipeline.build_panel`.

Clean tables land in `data/clean/`. Every run adds a health line to `data/run_log.jsonl`.

## Project structure
```
pipeline/   one script per data source, plus shared config and helpers
tests/      offline tests using small fake data
docs/       decisions log (every judgment call, with the reason)
notebooks/  exploration
app/        Streamlit app (later)
```

## Data notes
- Zillow changes its CSV download paths occasionally. If a download fails, the error
  message explains how to update the link in `pipeline/config.py`.
- See `docs/decisions.md` for every methodology choice.

*Data: Zillow Research, Federal Reserve Bank of St. Louis (FRED), U.S. Census Bureau,
Bureau of Labor Statistics, IRS Statistics of Income.*
