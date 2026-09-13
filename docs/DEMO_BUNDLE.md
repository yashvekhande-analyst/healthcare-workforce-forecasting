# Included real demonstration bundle

The bundle is approximately 4.6 MB before dashboard screenshots. It retains the **complete 50-facility analysis**, with all eight quarters of selected daily records and all saved validation, calibration and test predictions. No demonstration sampling changes the reported metrics.

| Location under `artifacts/full/` | Purpose |
| --- | --- |
| `daily.parquet`, `facilities.parquet` | Full selected calendar and facility descriptors; dashboard history and filters |
| `features.parquet`, `eligibility.csv` | Complete SQL features and training-only cohort audit |
| `models/bundle.joblib`, `models/metadata.json` | Frozen fitted alternative, selected baseline, calibration values and model checksum |
| `test_forecasts.parquet`, `test_outcomes.parquet` | Separate complete forecast and observed-target records |
| `evaluation.parquet`, `backtest_summary.json` | Full joined evaluation and expected/forecastable/evaluable counts |
| `validation_predictions.parquet`, `calibration_predictions.parquet` | Model-selection and interval-calibration evidence |
| `forecasts/`, `actuals/` | Saved March 24/31 replay forecasts and later matured outcomes |
| `quality.json`, `config_snapshot.json`, `monitoring*.json` | Data audit, configuration, real monitoring and explicitly labeled alert simulation |
| `reports/` | Full EDA, model comparisons, facility/volume metrics, failures, executive brief and figures |

The source manifest retains all original raw-file checksums. [bundle_checksums.json](../artifacts/bundle_checksums.json) covers the included analytical evidence. `python scripts/verify_publication.py` checks these hashes and independently recomputes aggregate metrics by joining saved forecasts to separate outcomes. It also checks local Markdown links and images. It does not train a model or fetch CMS data.

Excluded: the roughly 301 MB raw snapshot, redundant DuckDB database (rebuildable from Parquet), development-run artifacts, logs, caches, build products and personal preparation notes. The original local analysis is preserved separately by its owner. The default dashboard reads this repository's `artifacts/full` directly. `WORKFORCE_ARTIFACTS` can select a different completed analysis.

Joblib deserialization executes Python object reconstruction; use only trusted model bundles. The dashboard reads Parquet/JSON/CSV and does not deserialize the model. The command-line predictor checks the bundle hash before loading it.
