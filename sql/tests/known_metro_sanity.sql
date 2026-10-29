-- Spot check: Detroit in mid-2023 (the latest year every source covers) has every core field.
SELECT * FROM mart_metro_month
WHERE cbsa_code = '19820' AND date = DATE '2023-06-01'
  AND (home_value IS NULL OR rent IS NULL OR employment IS NULL OR median_household_income IS NULL
       OR permits_units IS NULL OR net_migration IS NULL OR mortgage_rate_30y IS NULL);
