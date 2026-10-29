-- Every metro x every month, so gaps show up as NULLs instead of missing rows.
CREATE OR REPLACE TABLE spine AS
WITH months AS (
    SELECT unnest(generate_series(
        DATE '2015-01-01',
        (SELECT max(date) FROM stg_zillow_metro),
        INTERVAL 1 MONTH))::DATE AS date
)
SELECT m.cbsa_code, months.date, year(months.date) AS year
FROM dim_metro m CROSS JOIN months;
