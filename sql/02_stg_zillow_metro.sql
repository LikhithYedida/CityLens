-- Zillow metro home values and rents, mapped to official metro codes.
-- Some official metros have two Zillow series because the 2023 Census update merged a
-- small area into a bigger metro (e.g. Madera into Fresno). Keep the stronger match:
-- the series whose name matches the metro, not the absorbed area found by county vote.
CREATE OR REPLACE TABLE stg_zillow_xwalk AS
WITH ranked AS (
    SELECT *,
        row_number() OVER (
            PARTITION BY cbsa_code
            ORDER BY CASE match_method
                WHEN 'both_agree' THEN 1 WHEN 'manual_override' THEN 2
                WHEN 'name_only' THEN 3 WHEN 'conflict_used_county_vote' THEN 4
                WHEN 'county_vote_only' THEN 5 ELSE 9 END,
            zillow_region_id
        ) AS rk
    FROM read_parquet('{clean}/zillow_metro_xwalk.parquet')
    WHERE cbsa_code IS NOT NULL
)
SELECT zillow_region_id, region_name, cbsa_code, match_method, rk > 1 AS absorbed_series
FROM ranked;

CREATE OR REPLACE TABLE stg_zillow_metro AS
SELECT
    x.cbsa_code,
    z.date::DATE                                            AS date,
    max(CASE WHEN z.metric = 'home_value' THEN z.value END) AS home_value,
    max(CASE WHEN z.metric = 'rent'       THEN z.value END) AS rent,
    any_value(x.region_name)                                AS zillow_region_name
FROM read_parquet('{clean}/zillow_housing.parquet') z
JOIN stg_zillow_xwalk x
  ON z.zillow_region_id = x.zillow_region_id AND NOT x.absorbed_series
WHERE z.geography = 'metro'
GROUP BY x.cbsa_code, z.date;
