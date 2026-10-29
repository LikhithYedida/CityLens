-- Monthly jobs and weekly wages by metro, with year-over-year growth.
CREATE OR REPLACE TABLE stg_jobs AS
SELECT
    cbsa_code,
    date::DATE AS date,
    employment,
    avg_weekly_wage,
    employment / lag(employment, 12) OVER w - 1           AS job_growth_yoy,
    avg_weekly_wage / lag(avg_weekly_wage, 12) OVER w - 1 AS wage_growth_yoy
FROM read_parquet('{clean}/qcew_metro.parquet')
WINDOW w AS (PARTITION BY cbsa_code ORDER BY date);
