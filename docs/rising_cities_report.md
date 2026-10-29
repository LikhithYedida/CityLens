# CityLens Rising City Detector

**Question:** which metros are about to see home prices rise faster than the rest, and do the usual boomtown signals actually predict it?

Panel: 2,632 metro-years (376 metropolitan areas, December 2018 to December 2024), each predicting the next 12 months of home-value growth relative to the typical metro that year.

## The short answer

1. **Momentum and affordability are the signals that last.** A simple blend of the two ranked metros correctly enough that its top fifth outgrew its bottom fifth by **4.8 points a year on average** (never less than 3.7) in an honest backtest.
2. **The pandemic boomtown signal flipped.** High migration predicted faster price growth through 2021, then turned negative once rates rose in 2022 (clearly so in 2023 and 2024), as the boomtowns cooled.
3. **A fitted regression lost to the simple blend out of sample**, because it learned relationships from the pandemic market that stopped holding. Simple, stable signals beat a model tuned to the past.

## 1. What predicted price growth (all years pooled)

Effect of a one-standard-deviation higher value on next-year home-value growth, in percentage points relative to the typical metro. Year fixed effects; standard errors clustered by metro.

| Signal | Effect (pp) | 95% range | p-value |
|---|---|---|---|
| Net migration (2 years earlier) | +0.33 | +0.16 to +0.50 | <0.001 |
| Job growth (past year) | +0.27 | +0.10 to +0.44 | 0.002 |
| Wage growth (past year) | +0.08 | -0.07 to +0.22 | 0.308 |
| New homes permitted (prior year) | -0.17 | -0.34 to +0.01 | 0.058 |
| Price-to-income (how expensive) | -0.34 | -0.44 to -0.24 | <0.001 |
| Home price growth (past year) | +1.43 | +1.30 to +1.56 | <0.001 |

R² = 0.18. Prices are hard to predict; this explains part of the spread, not all of it.

**Robustness.** The same model excluding the 2020-21 pandemic years, and with metro fixed effects (comparing each metro only to itself over time):

| Signal | All years | Excluding 2020-21 | Metro fixed effects |
|---|---|---|---|
| Net migration (2 years earlier) | +0.33 | +0.09 | +0.31 |
| Job growth (past year) | +0.27 | +0.22 | +0.17 |
| Wage growth (past year) | +0.08 | -0.02 | +0.14 |
| New homes permitted (prior year) | -0.17 | -0.68 | -0.44 |
| Price-to-income (how expensive) | -0.34 | -0.48 | -8.14 |
| Home price growth (past year) | +1.43 | +1.11 | +1.30 |

The metro fixed effects price-to-income number is much larger because it answers a different question: not 'do expensive metros grow slower than cheap ones' but 'when a metro's prices run ahead of its own incomes, do they come back down?' They strongly do.

## 2. How the signals changed, year by year

Effect (pp per 1 SD) estimated separately for each starting December. Bold = statistically clear (|t| ≥ 2).

| Starting Dec | Net migration | Job growth | Wage growth | New homes permitted | Price-to-income | Home price growth | R² |
|---|---|---|---|---|---|---|---|
| 2018 | +0.21 | +0.15 | -0.10 | -0.26 | **-0.96** | **+1.05** | 0.21 |
| 2019 | **+1.35** | +0.21 | +0.22 | **-0.77** | -0.06 | **+0.48** | 0.23 |
| 2020 | **+1.54** | **+1.42** | +0.35 | **+1.15** | **+1.73** | **+2.03** | 0.65 |
| 2021 | +0.37 | **+0.79** | **+0.70** | +0.56 | **-1.92** | **+1.38** | 0.24 |
| 2022 | -0.25 | +0.08 | -0.22 | **-1.31** | **-0.38** | **+1.33** | 0.32 |
| 2023 | **-0.41** | +0.13 | +0.07 | **-0.51** | **-0.27** | **+1.40** | 0.59 |
| 2024 | **-0.33** | +0.10 | -0.04 | -0.02 | **-0.90** | **+1.65** | 0.57 |

Momentum predicts growth in every year. Migration and job growth mattered in the cheap-money pandemic market and faded or reversed after rates rose in 2022. Expensive metros (high price-to-income) have grown more slowly in most years since 2021.

## 3. Backtest: which design actually predicts?

Each year, every design is built only from information available at the time, then scored on what happened next. Rank correlation: 1.0 = perfect ordering, 0 = no better than chance.

| Design | 2021 | 2022 | 2023 | 2024 | Average | Top-minus-bottom fifth (avg pp) |
|---|---|---|---|---|---|---|
| Momentum + affordability ⭐ | 0.40 | 0.36 | 0.68 | 0.74 | **0.54** | +4.8 |
| Momentum + affordability + low supply | 0.13 | 0.52 | 0.71 | 0.71 | **0.52** | +3.9 |
| Momentum only | 0.26 | 0.28 | 0.68 | 0.68 | **0.47** | +4.1 |
| Regression (last 2 years only) | 0.23 | -0.12 | 0.70 | 0.70 | **0.38** | +3.3 |
| Regression (all past years) | 0.28 | 0.03 | 0.38 | 0.66 | **0.34** | +3.0 |
| Affordability only | 0.07 | 0.33 | 0.39 | 0.50 | **0.33** | +2.9 |

**Chosen: Momentum + affordability.** It needs no fitting, so it can't overfit a past market, and it had the best average with no bad years.

What each fifth of the Rising Signal went on to do (next-year growth vs. the typical metro):

| Signal fifth | Average (pp) | Worst year | Best year |
|---|---|---|---|
| Bottom fifth | -2.8 | -3.4 | -2.2 |
| 2nd | -0.6 | -1.2 | -0.0 |
| Middle | +0.5 | +0.2 | +1.2 |
| 4th | +0.9 | +0.2 | +1.3 |
| Top fifth | +2.0 | +1.1 | +2.8 |

## 4. Rising Cities now (data as of Sep 2026)

Top fifth of the Rising Signal **and** adding jobs over the past year: metros most likely to outgrow the typical metro over the next 12 months, for healthy reasons.

| Metro | Price growth (past yr) | Price-to-income | Job growth (past yr) | Opportunity rank |
|---|---|---|---|---|
| Springfield, IL | +7.4% | 2.7x | +0.9% | 106 |
| Abilene, TX | +7.6% | 3.3x | +2.1% | 212 |
| Binghamton, NY | +6.9% | 3.1x | +0.9% | 305 |
| Saginaw, MI | +5.4% | 2.9x | +1.0% | 185 |
| Lima, OH | +5.1% | 3.0x | +0.2% | 250 |
| Syracuse, NY | +6.6% | 3.6x | +0.8% | 295 |
| South Bend-Mishawaka, IN-MI | +6.3% | 3.5x | +0.7% | 200 |
| Monroe, MI | +6.1% | 3.5x | +1.9% | 86 |
| Grand Forks, ND-MN | +7.3% | 4.1x | +0.2% | 218 |
| Watertown-Fort Drum, NY | +6.0% | 3.5x | +0.2% | 341 |
| St. Joseph, MO-KS | +4.9% | 3.2x | +0.8% | 121 |
| Janesville-Beloit, WI | +6.2% | 3.9x | +0.1% | 181 |
| Amarillo, TX | +4.1% | 3.1x | +0.8% | 29 |
| Flint, MI | +4.1% | 3.1x | +0.9% | 131 |
| Sioux City, IA-NE-SD | +3.4% | 3.0x | +0.9% | 160 |
| Cedar Rapids, IA | +3.9% | 3.2x | +0.6% | 129 |
| Elkhart-Goshen, IN | +5.5% | 3.9x | +1.4% | 327 |
| Battle Creek, MI | +3.2% | 3.0x | +3.5% | 63 |
| Jonesboro, AR | +4.4% | 3.5x | +1.7% | 70 |
| Montgomery, AL | +3.6% | 3.3x | +0.3% | 177 |

## Cooling Boomtowns

Top fifth for migration over the latest three years, but bottom two-fifths of the Rising Signal today: the pandemic-era magnets where prices have stalled or fallen.

| Metro | Net migration per 1,000 (3-yr avg) | Price growth (past yr) | Price-to-income |
|---|---|---|---|
| Asheville, NC | +7.7 | -3.3% | 5.8x |
| Bend, OR | +11.4 | -0.7% | 7.3x |
| Naples-Marco Island, FL | +18.1 | -1.4% | 6.1x |
| St. George, UT | +24.0 | -0.6% | 6.5x |
| Cape Coral-Fort Myers, FL | +20.2 | -3.5% | 4.4x |
| Greeley, CO | +17.4 | -2.0% | 5.0x |
| Austin-Round Rock-San Marcos, TX | +8.5 | -3.7% | 4.1x |
| North Port-Bradenton-Sarasota, FL | +26.4 | -2.0% | 5.0x |
| Punta Gorda, FL | +33.9 | -3.3% | 4.3x |
| Savannah, GA | +8.4 | -2.7% | 4.4x |
| Sherman-Denison, TX | +21.3 | -3.7% | 3.9x |
| Lakeland-Winter Haven, FL | +30.4 | -2.2% | 4.5x |

## Caveats

- This predicts **relative** growth (vs. the typical metro), not whether national prices rise or fall.
- The backtest covers four years (2021-2024), including one major regime change; more years will make it sharper.
- Migration data ends in 2023 and is used with a two-year lag, as it would be in real time.
- 'Rising' is not a recommendation to buy. For residents it can mean the window of affordability is closing; for builders and lenders it marks demand.
