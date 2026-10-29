# CityLens

[![tests](https://github.com/LikhithYedida/CityLens/actions/workflows/tests.yml/badge.svg)](https://github.com/LikhithYedida/CityLens/actions/workflows/tests.yml)

I started this project with a simple question: if you earn a typical paycheck in America
today, where does it still go far, and where is that about to change?

The answers are scattered across Zillow, the Census, the Bureau of Labor Statistics, the IRS
and the Federal Reserve, and none of them line up out of the box. CityLens pulls seven public
sources into one tested dataset, ranks 379 U.S. metro areas, flags where prices are likely to
rise or cool next, forecasts rents a year out with honest error ranges, and checks one widely
cited housing policy against the data. Housing data runs through September 2026.

If you only have two minutes, read the [one page executive memo](docs/executive_memo.md).

![The 15 largest metros at a glance](docs/figures/scorecard_largest_metros.png)

## What I found

**Only 62 of 379 metros are both affordable and growing.** Huntsville, Austin, Sherman-Denison,
Raleigh and Sioux Falls top the Opportunity Index, and the top four hold a top 25 spot under
94 to 99 percent of 1,000 alternative weightings, so the ranking isn't an artifact of the
weights I picked. Among large metros the group is Austin, Raleigh, Dallas, San Antonio,
Houston, Oklahoma City, Indianapolis and Columbus. At the other end, a mortgage on a typical
home in Los Angeles, San Jose, San Diego or San Francisco takes 52 to 62 percent of a typical
household's income. [Full analysis](docs/opportunity_index_report.md)

**Price growth has moved north.** Of the 24 metros most likely to outgrow the national market
next year, 19 are in the Midwest or Northeast. Of the 56 cooling boomtowns, 55 are in the
South and West, 17 of them in Florida. The part that surprised me: metros gaining residents
saw faster price growth through 2021 and slower growth from 2022 on. A model trained on the
pandemic years learned the wrong lesson, and a simple two signal rule ranked metros better.
[Full analysis](docs/rising_cities_report.md)

**Growth spreads about 75 miles, then fades.** When neighbors within 75 miles grow faster, a
metro grows 0.45 points faster the following year (per standard deviation), on top of its own
momentum. The effect held before, during and after the pandemic and disappears past 150 miles.
That puts 26 affordable metros next in line, including Eau Claire, Fargo, Fort Wayne and
Davenport. [Full analysis](docs/ripple_map_report.md)

![Where home value growth clusters](docs/figures/ripple_cluster_map.png)

**Rent in a typical metro should rise about 3 percent over the next year.** Austin, Dallas,
San Antonio and Orlando are the large metros where rent is expected to stay roughly flat. I
held the forecasts to a strict test: in rolling backtests over 2020 to 2025 they missed by 3.1
points against 3.5 for the best simple rule, and since 2022 by 1.8 against 2.7. Their 80
percent ranges captured 94 percent of what actually happened. [Full analysis](docs/forecast_report.md)

**Minneapolis zoning reform lowered rents, but by less than the headlines say.** Minneapolis
rents are 16 percent below a synthetic Minneapolis built from 180 other cities (p = 0.017).
But the gap opened in 2020, two years after the vote, and the suburbs the reform never touched
fell about 8 percent too. My estimate is that the reform itself accounts for 8 to 10 points.
[Full analysis](docs/policy_lab_report.md)

## The app

The Streamlit app turns the analysis into three tools:

- **Where to live.** Enter an income, rent or buy, a down payment and a budget, and see which
  metros fit and how much is left each month.
- **Where to build.** Builders and lenders weight the signals they care about and get ranked
  markets, along with a check of how often each market stays in the top 10 when the weights move.
- **Metro profile.** Any metro against its peers and the national median, with its price history
  and the neighbors most likely to pull it along.

```bash
streamlit run app/streamlit_app.py
```

## How it is built

| Stage | What it does | Code |
|---|---|---|
| Ingest | Downloads all seven sources, validates each one and logs every run | `pipeline/` |
| Crosswalk | Matches Zillow's metro names to official Census metros two independent ways (97.7 percent matched), with manual fixes kept in a reviewed file | `pipeline/geo.py` |
| Panel | One SQL table (DuckDB) of every metro by month since 2015, with 8 data tests that stop the build on a bad join | `sql/` |
| Opportunity Index | Percentile index of affordability, momentum and demand, stress tested with 1,000 random weightings and by dropping each input | `analysis/opportunity_index.py` |
| Rising City Detector | Panel regression with year fixed effects and clustered errors, then a walk forward backtest of six designs | `analysis/rising_cities.py` |
| Policy Lab | Synthetic control for the Minneapolis 2040 Plan, with placebo tests in space and time and a suburb comparison | `analysis/policy_lab.py` |
| Forecast Engine | Gradient boosting blended with a national trend model, backtested against three baselines, with conformal 80 percent ranges | `analysis/forecast_engine.py` |
| Ripple Map | Global and local Moran's I, distance ring regressions and a U.S. cluster map | `analysis/ripple_map.py` |
| Scorecard | One row per metro joining every analysis, feeding the memo and the app | `analysis/scorecard.py` |

I kept a [decisions log](docs/decisions.md) as I went. It records 80 judgment calls with the
reason for each, from which Zillow series to trust to why I threw out a model that looked good
on paper.

## Run it yourself

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # add free Census, BLS and FRED API keys
python -m pytest                   # runs offline, no data or keys needed
python -m pipeline.run_all         # downloads every source and rebuilds every analysis
streamlit run app/streamlit_app.py
```

## Data sources

- [Zillow Research](https://www.zillow.com/research/data/): home values (ZHVI) and rents (ZORI) by metro, county and city
- [Census American Community Survey](https://www.census.gov/programs-surveys/acs): income, renters and rent burden
- [Census Building Permits Survey](https://www.census.gov/construction/bps/): new housing units
- [BLS Quarterly Census of Employment and Wages](https://www.bls.gov/cew/): jobs and wages by county
- [IRS migration data](https://www.irs.gov/statistics/soi-tax-stats-migration-data): moves between counties
- [FRED](https://fred.stlouisfed.org/): 30 year mortgage rate and consumer prices
- [Census metro definitions, Gazetteer and boundary files](https://www.census.gov/geographies/reference-files.html): which counties make up each metro, plus coordinates and state outlines

## Limits

- The data covers all 935 Census metro and micropolitan areas, but I only rank the 393
  metropolitan ones. Micropolitan towns are too small for reliable rent, survey and job numbers.
  Of the 393, Puerto Rico (6) has no Zillow data, Connecticut (5) changed how BLS reports jobs
  in 2024, and 3 metros created in the 2023 Census update have no Zillow series yet. That
  leaves 379.
- Migration data runs two years behind and job data about six months behind.
- The Rising City and ripple signals predict well, but they don't prove one metro causes
  another's growth.
- National shocks drive most one year price swings. The 2021 surge and the 2022 rate shock broke
  every forecast I tested, including mine.

Next on my list: a county to region crosswalk so Connecticut can be ranked, a monthly automatic
refresh, and drive time instead of straight line distance in the Ripple Map.

## About Me

I'm Likhith Yedida, a data analyst.
[LinkedIn](https://www.linkedin.com/in/likhithyedida).
