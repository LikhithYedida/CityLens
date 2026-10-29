-- Migration is yearly: every month in a metro-year must carry the same value.
SELECT cbsa_code, year FROM mart_metro_month WHERE net_migration IS NOT NULL
GROUP BY 1, 2 HAVING count(DISTINCT net_migration) > 1;
