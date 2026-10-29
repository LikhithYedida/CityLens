-- No metro or month went missing: rows = metros x months.
SELECT (SELECT count(*) FROM mart_metro_month) AS rows,
       (SELECT count(*) FROM dim_metro) * (SELECT count(DISTINCT date) FROM spine) AS expected
WHERE (SELECT count(*) FROM mart_metro_month)
   <> (SELECT count(*) FROM dim_metro) * (SELECT count(DISTINCT date) FROM spine);
