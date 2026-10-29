-- After removing absorbed areas, each metro has at most one Zillow series.
SELECT cbsa_code, count(*) FROM stg_zillow_xwalk WHERE NOT absorbed_series GROUP BY 1 HAVING count(*) > 1;
