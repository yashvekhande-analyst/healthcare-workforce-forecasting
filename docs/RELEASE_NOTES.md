# v1.0.0 — Healthcare workforce forecasting portfolio

Initial public release of the completed independent portfolio project: a Python/DuckDB pipeline and read-only Streamlit dashboard for seven-day contract RN, LPN and CNA utilization at nursing homes.

- Includes CMS acquisition/provenance, schema and value checks, calendar SQL, chronological validation, a saved model, separate interval calibration, immutable forecasts and later outcomes, monitoring, reports and a walkthrough with actual screenshots.
- Eight quarters (April 2024–March 2026), 50 New York nursing homes. The preceding-seven-day baseline won validation against another baseline and four gradient-boosting candidates.
- On **8,660 evaluable held-out facility-origins**: **39.59 hours MAE**, **7.29% WAPE**, and **86.22% coverage** for nominal 90% intervals. The best tuned gradient model achieved 39.91 hours test MAE. Overlapping daily outcomes are not independent samples.
- The full real derived bundle supports a local demo without CMS downloads or training. Full reproduction uses a separate experiment directory. Original source requests/checksums and complete evaluation reports are retained; the roughly 301 MB raw snapshot is excluded.
- Fresh local setup: **14 tests passed**, independent metric/bundle checks passed, and the dashboard ran from a clean copy containing only intended project files. Python 3.12 CI runs software/dashboard tests and independent bundle, metric and link checks. Publication preserves the existing model and results without retraining or test-period recalibration.

Known limitations: quarterly public releases require an assumed daily feed for replay; coverage falls below the nominal target; one-state cohort and conditional evaluability limit interpretation. Docker and GCP execution are unverified. This release does not claim production use, employer affiliation, adequate clinical staffing or savings.
