-- Run integrity.sql and require zero duplicate/unmatched keys first.
-- LEFT JOIN preserves issued forecasts with unknown realized outcomes.
SELECT f.dataset_version, f.model, f.model_version,
       COUNT(*) AS issued_forecasts, COUNT(o.actual) AS n,
       COUNTIF(o.actual IS NULL) AS unknown_outcomes,
       AVG(ABS(f.prediction - o.actual)) AS mae_hours,
       SAFE_DIVIDE(SUM(ABS(f.prediction - o.actual)), SUM(ABS(o.actual))) AS wape,
       AVG(f.prediction - o.actual) AS signed_error_hours,
       AVG(IF(o.actual IS NULL, NULL, CAST(o.actual BETWEEN f.lower AND f.upper AS INT64))) AS coverage,
       AVG(IF(o.actual IS NULL, NULL, f.upper - f.lower)) AS mean_width_hours
FROM `workforce-replay-yv-260913.workforce_demo.forecasts_cms_ny50_v1` f
LEFT JOIN `workforce-replay-yv-260913.workforce_demo.outcomes_cms_ny50_v1` o
USING (dataset_version, facility, origin, target_end)
GROUP BY 1,2,3 ORDER BY model;
