-- Each metro-month appears exactly once.
SELECT cbsa_code, date, count(*) AS n FROM mart_metro_month GROUP BY 1, 2 HAVING count(*) > 1;
