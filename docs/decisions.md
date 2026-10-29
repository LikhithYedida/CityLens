# Decisions Log

One line per judgment call, so every number in this project can be explained and defended.

| # | Date | Decision | Why |
|---|------|----------|-----|
| 1 | 2026-10-27 | Main unit of analysis is the U.S. metro area; county is the second level for maps. | Metros match how people choose where to live and how businesses plan markets. |
| 2 | 2026-10-27 | Analysis window starts January 2015. | Zillow's rent index (ZORI) begins around then, so every source lines up. |
| 3 | 2026-10-27 | Use Zillow's mid-tier, smoothed, seasonally adjusted home values (ZHVI). | Mid-tier reflects a typical home, not luxury or starter extremes. |
| 4 | 2026-10-27 | Average the weekly 30-year mortgage rate to one value per month. | Matches Zillow's monthly grain so tables join cleanly. |
| 5 | 2026-10-27 | Pull CPI alongside mortgage rates. | Lets later steps compare prices in inflation-adjusted dollars. |
| 6 | 2026-10-27 | Treat IRS migration data from 2022–2023 onward as a new series. | The IRS changed its return-matching method starting that year. |
| 7 | 2026-10-27 | Downloads fail loudly with a fix message, and every run is logged. | Zillow changes download paths; silent failures would produce stale results. |
| 8 | 2026-10-27 | Use the July 2023 Census metro definitions for every year. | Metro boundaries change over time; one fixed definition keeps the panel consistent. |
| 9 | 2026-10-27 | Match Zillow metros to Census metros two independent ways (name and county vote), and report the match rate. | No single method is reliable alone; agreement between two methods is evidence the join is right. |
| 10 | 2026-10-27 | Hand-checked fixes go in `docs/crosswalk_overrides.csv`, never in code. | Keeps manual judgment visible and reviewable. |
| 11 | 2026-10-27 | Pull Census ACS at county level and roll up to metros, using weighted averages of county medians. | Medians can't be added. Weighted averages are a documented approximation (weights: households for income, renters for rent, owners for home value). |
| 12 | 2026-10-27 | Use ACS 5-year estimates, not 1-year. | 1-year estimates only cover areas with 65,000+ people; 5-year covers every county. Trade-off: 5-year values are smoother and lag real changes. |
| 13 | 2026-10-27 | Pre-2022 Connecticut counties don't map to current metros and are logged, not silently dropped. | Connecticut replaced its counties with planning regions, which the 2023 definitions use. |
| 14 | 2026-10-27 | Use BLS QCEW for jobs and wages. | It covers about 95% of jobs at county level and gives true monthly job counts. Trade-off: about a 5-6 month release lag. |
| 15 | 2026-10-27 | Treat BLS confidential values (shown as 0) as missing, and don't report a metro job total if any of its counties is missing. | A partial total would look like a job loss that never happened. |
| 16 | 2026-10-27 | Compute metro weekly wage from total wages and jobs, not by averaging county wages. | Averaging averages would give a small county the same weight as a big one. |
| 17 | 2026-10-28 | Leave 21 small Zillow metros unmatched; hand-fix 2 renamed metros. | The 2023 Census update dropped many small towns from metro status, so they have no official code. Poughkeepsie and California, MD were renamed, not dropped, so they were verified by their counties and added as overrides. |
| 18 | 2026-10-28 | Use annual county building permits, full estimates (with imputation), not reported-only counts. | Some permit offices don't report every year; imputed totals are the Census Bureau's best complete estimate. |
| 19 | 2026-10-28 | Find the permit file's "Units" columns from its header, and check the national total is realistic (0.7M-2.5M units). | A small layout change would otherwise read the wrong column silently. |
| 20 | 2026-10-28 | Note the Census permits methodology change in 2023 (annually updated survey universe). | Small breaks around 2023 may come from the method, not the market. |
| 21 | 2026-10-28 | Use IRS U.S.-only summary rows for county migration, not the county-to-county rows. | The IRS hides small county-to-county flows for privacy; summary rows include them. |
| 22 | 2026-10-28 | Report only NET migration for metros. | A move between two counties in the same metro cancels out in the net, but would be double counted in gross inflows and outflows. |
| 23 | 2026-10-28 | Validate each IRS year: national U.S. inflows and outflows must match within 5%. | U.S.-only moves are a closed system; a big gap means a parsing error. |
| 24 | 2026-10-28 | Scale migration per 1,000 residents. | Lets a small metro's growth compare fairly with a big metro's. |
| 25 | 2026-10-28 | Drop repeated county rows in the permits file only when their numbers are identical. | Census lists 5 counties twice under old and new names (4 Alaska boroughs, St. Mary's County MD). Counting both would double them; a repeat with different numbers still stops the pipeline. |
| 26 | 2026-10-28 | When two Zillow series map to one metro, keep the series whose name matches the metro and leave out the absorbed area. | The 2023 Census update merged 12 small areas (e.g. Madera into Fresno) into bigger metros; joining both would count those metros twice. |
| 27 | 2026-10-28 | Carry the latest Census ACS year forward to later months, and flag it (`acs_carried_forward`). | ACS publishes about a year late; carrying forward keeps recent months usable, and the flag keeps it honest. |
| 28 | 2026-10-28 | Mortgage payment = principal + interest on a 30-year loan with 20% down; taxes and insurance excluded. | Gives one consistent comparison across metros. It understates true monthly cost, especially in high-tax states. |
| 29 | 2026-10-28 | Build the master table in SQL (DuckDB) as ordered models plus data tests, dbt-style. | Each model does one job and every rule is a test; a broken join fails the build instead of reaching the analysis. |
| 30 | 2026-10-28 | Inflation-adjust prices to the latest month's dollars using CPI. | A $300K home in 2015 and in 2026 are not the same money. |
| 31 | 2026-10-29 | Opportunity Index uses three pillars: Affordability 40%, Momentum 35%, Demand & Supply 25%. | Affordability is the core question, so it gets the most weight; momentum separates 'cheap because it's thriving' from 'cheap because it's declining'. |
| 32 | 2026-10-29 | Convert every indicator to a 0-100 percentile rank before combining. | Indicators are in different units (ratios, growth rates, per-1,000 counts); percentiles stop one extreme value from swamping the rest. |
| 33 | 2026-10-29 | Use 3-year growth, measured in the same calendar month at both ends. | Smooths out one-off swings, and same-month comparison cancels seasonal patterns. |
| 34 | 2026-10-29 | 'Paycheck vs prices' = wage growth minus the average of rent and home-price growth. | Measures whether a typical paycheck is gaining or losing ground against housing costs. |
| 35 | 2026-10-29 | Within a pillar, average whatever indicators exist; a metro missing a whole pillar is not ranked. | Uses all available evidence without inventing values for missing data. |
| 36 | 2026-10-29 | Test the ranking under 1,000 random weightings and by dropping each indicator in turn. | A ranking that only holds under one choice of weights is an opinion, not a finding. |
| 37 | 2026-10-29 | Score only Metropolitan areas (393), not Micropolitan ones. | Micropolitan areas often lack Zillow rents and have noisy job counts; they can be added as a separate ranking later. |
| 38 | 2026-10-29 | Leave Connecticut metros unranked for now and list them in the report. | BLS moved Connecticut from counties to planning regions in 2024, breaking 3-year job comparisons. Fix planned: a county-to-planning-region crosswalk. |
| 39 | 2026-10-29 | Rising City Detector predicts each metro's next-12-month home-value growth relative to that year's national average. | Removes the national market swing (rates, inflation), which no local signal can predict, and focuses on which metros outpace others. |
| 40 | 2026-10-29 | Lag migration two years and permits one year in every model and backtest. | Matches when the IRS and Census actually publish them; using same-year values would let the backtest see the future. |
| 41 | 2026-10-29 | Estimate with year fixed effects, metro-clustered standard errors, plus robustness specs (no 2020-21, metro fixed effects) and year-by-year slopes. | Repeated observations of one metro aren't independent; the year-by-year view shows whether a signal is stable or regime-dependent. |
| 42 | 2026-10-29 | Choose the prediction design by walk-forward backtest, not by in-sample fit. | The pooled regression fit the past well but failed after the 2022 rate shock; out-of-sample performance is what matters for a forecast. |
| 43 | 2026-10-29 | Use an unfitted, equal-weight blend of momentum and affordability as the Rising Signal. | It had the best average rank correlation (0.54) and no bad years; with no fitted weights it can't overfit a past market. |
| 44 | 2026-10-29 | A 'Rising City' must also be adding jobs; high-migration metros now in the bottom two-fifths of the signal are 'Cooling Boomtowns'. | Separates price rises backed by real economic growth from price-only moves, and names the post-pandemic reversal. |
| 45 | 2026-10-29 | Evaluate Minneapolis's 2040 Plan with city-level Zillow data, not metro data. | Minneapolis is about a tenth of its metro; a metro-level test would dilute any effect. |
| 46 | 2026-10-29 | Use demeaned synthetic control (weights >= 0, summing to 1), fit on Jan 2015 to Nov 2018. | Builds a transparent counterfactual from real cities; demeaning matches the shape of rent growth rather than rent levels. |
| 47 | 2026-10-29 | Exclude Minnesota, California and Oregon cities, plus six cities with their own zoning reforms, from the donor pool. | Donors must be untreated and outside Minneapolis's housing market, or the comparison absorbs the effect being measured. |
| 48 | 2026-10-29 | Judge significance by placebo tests in space (every donor 'treated') and time (fake 2017 reform), plus leave-one-out. | Synthetic control has no textbook standard error; placebos show how unusual the result is. |
| 49 | 2026-10-29 | Compare Minneapolis with its own suburbs (not covered by the reform) and report the regional share. | Separates a Twin Cities-wide rent slowdown from the reform itself; studies comparing Minneapolis only with other cities can't. |
| 50 | 2026-10-29 | Use the suburban counties (Anoka, Dakota, Scott, Washington) as the primary suburb definition; show single suburbs as a range. | Complete data from 2015 and over a million residents; single small suburbs are noisy and one has a missing month. |
| 51 | 2026-10-29 | Report the home-value result as not significant (p = 0.21) instead of dropping it. | Leaving out a weaker result would overstate the evidence. |
| 52 | 2026-10-29 | Forecast 12-month change in log rent and home value for every metropolitan area, monthly. | A one-year horizon is what renters, buyers and lenders plan around; log changes make metros of different price levels comparable. |
| 53 | 2026-10-29 | Judge forecasts by rolling-origin backtest (2020-2025), training only on outcomes known by January of each test year, against flat, persistence and national baselines. | A forecast is only useful if it beats simple rules on data it never saw. |
| 54 | 2026-10-29 | Lag inputs to publication: jobs 6 months, income 12, permits 18, migration 24. | Using data before it's published would make the backtest look better than reality. |
| 55 | 2026-10-29 | Use the average of a two-part model (national trend + metro adjustment) and a direct model as the CityLens forecast. | Each failed in a different regime (2021 surge vs. 2022 rate turn); the average was most accurate overall for both rents and home values. Chosen after seeing the backtest, which is disclosed; forecasts from now on are the true test. |
| 56 | 2026-10-29 | Report all designs, including the ones that lost, plus calm-year (2022-25) and all-year results. | Shows how the final design was reached and where it is and isn't better. |
| 57 | 2026-10-29 | 80% ranges from normalized split conformal prediction (24-month calibration, scaled by metro volatility), with coverage checked in the backtest. | Gives every forecast an honest uncertainty band and proves whether it's calibrated: 94-96% in calm years, 72-81% including the pandemic shock. |
| 58 | 2026-10-29 | Charts are small, answer one question each, and label the values that matter, from a shared style module. | A chart that needs a legend hunt or covers a page without adding information slows the reader down. |
