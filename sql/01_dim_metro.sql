-- One row per official metro or micro area (July 2023 Census definitions).
CREATE OR REPLACE TABLE dim_metro AS
SELECT
    cbsa_code,
    any_value(cbsa_title)                          AS cbsa_title,
    any_value(cbsa_type)                           AS cbsa_type,
    count(*)                                       AS n_counties,
    -- principal state = first state after the comma, e.g. "Detroit-Warren-Dearborn, MI" -> MI
    split_part(trim(split_part(any_value(cbsa_title), ',', 2)), '-', 1) AS principal_state
FROM read_parquet('{clean}/county_to_cbsa.parquet')
GROUP BY cbsa_code;
