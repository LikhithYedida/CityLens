-- THE MASTER TABLE: one row per metro per month, every source side by side.
CREATE OR REPLACE TABLE mart_metro_month AS
WITH acs AS (
    SELECT * FROM read_parquet('{clean}/acs_metro.parquet')
),
base AS (
    SELECT
        s.cbsa_code, s.date, s.year,
        d.cbsa_title, d.cbsa_type, d.principal_state,
        z.zillow_region_name,
        -- Housing (Zillow, monthly)
        z.home_value, z.rent,
        z.home_value / lag(z.home_value, 12) OVER w - 1 AS home_value_growth_yoy,
        z.rent / lag(z.rent, 12) OVER w - 1             AS rent_growth_yoy,
        -- Rates and prices (FRED, monthly)
        f.mortgage_rate_30y, f.cpi,
        -- Jobs (BLS, monthly)
        j.employment, j.avg_weekly_wage, j.job_growth_yoy, j.wage_growth_yoy,
        -- People and income (Census ACS, yearly; latest year carried forward)
        a.year AS acs_year,
        a.population, a.median_household_income, a.renter_share, a.rent_burden_rate,
        a.housing_units,
        -- Supply (Census permits, yearly)
        p.units_total AS permits_units, p.multifamily_share AS permits_multifamily_share,
        -- Migration (IRS, yearly; period ending in this year)
        mg.net_people AS net_migration, mg.net_migration_rate_per_1k, mg.net_agi_thousands AS net_migration_agi_thousands,
        mg.new_series AS migration_new_series
    FROM spine s
    JOIN dim_metro d USING (cbsa_code)
    LEFT JOIN stg_zillow_metro z ON z.cbsa_code = s.cbsa_code AND z.date = s.date
    LEFT JOIN read_parquet('{clean}/fred_macro.parquet') f ON f.date::DATE = s.date
    LEFT JOIN stg_jobs j ON j.cbsa_code = s.cbsa_code AND j.date = s.date
    ASOF LEFT JOIN acs a ON a.cbsa_code = s.cbsa_code AND s.year >= a.year
    LEFT JOIN read_parquet('{clean}/permits_metro.parquet') p ON p.cbsa_code = s.cbsa_code AND p.year = s.year
    LEFT JOIN read_parquet('{clean}/migration_metro.parquet') mg ON mg.cbsa_code = s.cbsa_code AND mg.period_end_year = s.year
    WINDOW w AS (PARTITION BY s.cbsa_code ORDER BY s.date)
),
latest_cpi AS (
    SELECT cpi AS cpi_base FROM read_parquet('{clean}/fred_macro.parquet')
    WHERE cpi IS NOT NULL AND date::DATE <= (SELECT max(date) FROM spine)
    ORDER BY date DESC LIMIT 1
)
SELECT
    b.*,
    b.acs_year < b.year AS acs_carried_forward,
    -- Affordability
    b.rent * 12 / b.median_household_income       AS rent_to_income,
    b.home_value / b.median_household_income      AS price_to_income,
    -- Monthly principal + interest on a 30-year loan with 20% down (taxes/insurance excluded)
    (0.8 * b.home_value) * (b.mortgage_rate_30y / 1200)
        / (1 - power(1 + b.mortgage_rate_30y / 1200, -360))          AS mortgage_payment,
    (0.8 * b.home_value) * (b.mortgage_rate_30y / 1200)
        / (1 - power(1 + b.mortgage_rate_30y / 1200, -360)) * 12
        / b.median_household_income                                   AS mortgage_to_income,
    -- Supply vs. population
    b.permits_units / b.population * 1000         AS permits_per_1k,
    -- Inflation-adjusted (today's dollars)
    b.home_value * (c.cpi_base / b.cpi)           AS home_value_real,
    b.rent * (c.cpi_base / b.cpi)                 AS rent_real
FROM base b CROSS JOIN latest_cpi c;
