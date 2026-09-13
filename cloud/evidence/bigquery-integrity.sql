-- BigQuery does not enforce primary keys: check uniqueness before evaluation.
SELECT
  (SELECT COUNT(*) FROM `workforce-replay-yv-260913.workforce_demo.daily_cms_ny50_v1`) AS daily_rows,
  (SELECT COUNTIF(reported) FROM `workforce-replay-yv-260913.workforce_demo.daily_cms_ny50_v1`) AS reported_days,
  (SELECT COUNT(*) FROM `workforce-replay-yv-260913.workforce_demo.forecasts_cms_ny50_v1`) AS forecast_rows,
  (SELECT COUNT(*) FROM `workforce-replay-yv-260913.workforce_demo.outcomes_cms_ny50_v1`) AS outcome_rows,
  (SELECT COUNTIF(actual IS NOT NULL) FROM `workforce-replay-yv-260913.workforce_demo.outcomes_cms_ny50_v1`) AS known_outcomes,
  (SELECT COUNT(*) FROM (SELECT dataset_version, facility, date
    FROM `workforce-replay-yv-260913.workforce_demo.daily_cms_ny50_v1` GROUP BY 1,2,3 HAVING COUNT(*) > 1)) AS duplicate_daily_keys,
  (SELECT COUNT(*) FROM (SELECT dataset_version, facility, origin, model_version
    FROM `workforce-replay-yv-260913.workforce_demo.forecasts_cms_ny50_v1` GROUP BY 1,2,3,4 HAVING COUNT(*) > 1)) AS duplicate_forecast_keys,
  (SELECT COUNT(*) FROM (SELECT dataset_version, facility, origin
    FROM `workforce-replay-yv-260913.workforce_demo.outcomes_cms_ny50_v1` GROUP BY 1,2,3 HAVING COUNT(*) > 1)) AS duplicate_outcome_keys,
  (SELECT COUNT(*) FROM `workforce-replay-yv-260913.workforce_demo.forecasts_cms_ny50_v1` f
    LEFT JOIN `workforce-replay-yv-260913.workforce_demo.outcomes_cms_ny50_v1` o
    USING (dataset_version, facility, origin, target_end)
    WHERE o.facility IS NULL) AS forecasts_without_outcome_row;
