-- Replace PROJECT_ID and portfolio_v1 with the authorized project and uploaded version.
-- Independent recomputation from immutable forecasts plus separately stored outcomes.
SELECT
  f.model,
  COUNT(*) AS n,
  AVG(ABS(f.prediction - o.actual)) AS mae_hours,
  SAFE_DIVIDE(SUM(ABS(f.prediction - o.actual)), SUM(ABS(o.actual))) AS wape,
  AVG(f.prediction - o.actual) AS signed_error_hours,
  AVG(CAST(o.actual BETWEEN f.lower AND f.upper AS INT64)) AS coverage,
  AVG(f.upper - f.lower) AS mean_width_hours
FROM `PROJECT_ID.workforce.forecasts_portfolio_v1` AS f
JOIN `PROJECT_ID.workforce.outcomes_portfolio_v1` AS o
  USING (facility, origin, target_end)
WHERE o.actual IS NOT NULL
GROUP BY f.model;
