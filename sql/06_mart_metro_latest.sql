-- Latest snapshot per metro: the month with both rent and home value, plus the latest
-- available jobs month. Feeds rankings and the app.
CREATE OR REPLACE TABLE mart_metro_latest AS
WITH latest_housing AS (
    SELECT * FROM mart_metro_month
    WHERE home_value IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY cbsa_code ORDER BY date DESC) = 1
),
latest_jobs AS (
    SELECT cbsa_code, date AS jobs_date, employment AS jobs_latest, job_growth_yoy AS job_growth_latest
    FROM mart_metro_month WHERE job_growth_yoy IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY cbsa_code ORDER BY date DESC) = 1
),
latest_migration AS (
    SELECT cbsa_code, year AS migration_year, net_migration_rate_per_1k AS migration_latest_per_1k
    FROM mart_metro_month WHERE net_migration_rate_per_1k IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY cbsa_code ORDER BY date DESC) = 1
)
SELECT h.cbsa_code, h.cbsa_title, h.cbsa_type, h.principal_state, h.date AS housing_date,
       h.home_value, h.rent, h.home_value_growth_yoy, h.rent_growth_yoy,
       h.median_household_income, h.population, h.rent_to_income, h.price_to_income,
       h.mortgage_rate_30y, h.mortgage_payment, h.mortgage_to_income,
       j.jobs_date, j.jobs_latest, j.job_growth_latest,
       m.migration_year, m.migration_latest_per_1k
FROM latest_housing h
LEFT JOIN latest_jobs j USING (cbsa_code)
LEFT JOIN latest_migration m USING (cbsa_code);
