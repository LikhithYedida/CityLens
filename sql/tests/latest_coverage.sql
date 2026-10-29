-- The latest month must have home values for most metros (a broken join would show up here).
SELECT count(*) AS metros_with_home_value FROM mart_metro_month
WHERE date = (SELECT max(date) FROM mart_metro_month) AND home_value IS NOT NULL
HAVING count(*) < 700;
