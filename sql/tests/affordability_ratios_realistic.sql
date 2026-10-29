-- Rent and mortgage payments should be a plausible share of household income.
SELECT cbsa_code, date, rent_to_income, mortgage_to_income FROM mart_metro_month
WHERE (rent_to_income IS NOT NULL AND rent_to_income NOT BETWEEN 0.03 AND 1.5)
   OR (mortgage_to_income IS NOT NULL AND mortgage_to_income NOT BETWEEN 0.02 AND 2.5);
