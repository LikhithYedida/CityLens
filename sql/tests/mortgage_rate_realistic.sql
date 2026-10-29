-- 30-year rates since 2015 stayed between roughly 2.6% and 8%.
SELECT DISTINCT date, mortgage_rate_30y FROM mart_metro_month
WHERE mortgage_rate_30y IS NOT NULL AND mortgage_rate_30y NOT BETWEEN 2 AND 10;
