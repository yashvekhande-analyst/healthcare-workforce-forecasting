-- BigQuery does not enforce primary keys: check uniqueness before evaluation.
SELECT
  (SELECT COUNT(*) FROM `{{PROJECT}}.{{DATASET}}.daily_{{TABLE_TAG}}`) AS daily_rows,
  (SELECT COUNTIF(reported) FROM `{{PROJECT}}.{{DATASET}}.daily_{{TABLE_TAG}}`) AS reported_days,
  (SELECT COUNT(*) FROM `{{PROJECT}}.{{DATASET}}.forecasts_{{TABLE_TAG}}`) AS forecast_rows,
  (SELECT COUNT(*) FROM `{{PROJECT}}.{{DATASET}}.outcomes_{{TABLE_TAG}}`) AS outcome_rows,
  (SELECT COUNTIF(actual IS NOT NULL) FROM `{{PROJECT}}.{{DATASET}}.outcomes_{{TABLE_TAG}}`) AS known_outcomes,
  (SELECT COUNT(*) FROM (SELECT dataset_version, facility, date
    FROM `{{PROJECT}}.{{DATASET}}.daily_{{TABLE_TAG}}` GROUP BY 1,2,3 HAVING COUNT(*) > 1)) AS duplicate_daily_keys,
  (SELECT COUNT(*) FROM (SELECT dataset_version, facility, origin, model_version
    FROM `{{PROJECT}}.{{DATASET}}.forecasts_{{TABLE_TAG}}` GROUP BY 1,2,3,4 HAVING COUNT(*) > 1)) AS duplicate_forecast_keys,
  (SELECT COUNT(*) FROM (SELECT dataset_version, facility, origin
    FROM `{{PROJECT}}.{{DATASET}}.outcomes_{{TABLE_TAG}}` GROUP BY 1,2,3 HAVING COUNT(*) > 1)) AS duplicate_outcome_keys,
  (SELECT COUNT(*) FROM `{{PROJECT}}.{{DATASET}}.forecasts_{{TABLE_TAG}}` f
    LEFT JOIN `{{PROJECT}}.{{DATASET}}.outcomes_{{TABLE_TAG}}` o
    USING (dataset_version, facility, origin, target_end)
    WHERE o.facility IS NULL) AS forecasts_without_outcome_row;
