# Healthcare Workforce Staffing Forecasting System

**Executive brief · Independent portfolio project · Historical replay**

**Purpose.** Help a workforce planning analyst review the next seven days of observed contract RN, LPN and CNA utilization for nursing homes, with uncertainty and reliability indicators. This is a local demonstration using public CMS data, not an Ascension implementation or professional employment.

**Evidence.** The project preserved eight CMS quarters (2024-04-01–2026-03-31) and selected 50 NY facilities using early training coverage and a deterministic sample. The untouched test covers forecast origins 2025-10-01–2026-03-24. The selected **previous_7 achieved 39.6 hours MAE and 7.3% WAPE across 8,660 evaluable facility-origins**. Signed error was **+1.2 hours**, where positive means overprediction. The preceding-seven-day baseline achieved 39.6 hours MAE.

**Uncertainty.** Earlier, separate calibration targeted 90% intervals. Held-out coverage was **86.2%**, with mean interval width **398.0 hours**. Interval reliability varies by facility and operating conditions; the display supports review rather than a coverage promise.

**Coverage.** 8,667 of 8,750 expected test facility-origins had sufficient history. 8,660 had complete realized targets. Missing or excluded records remain missing, and true reported zeros are retained.

**What works.** A rerunnable local Python/SQL pipeline, saved models, immutable forecasts with separate actuals, a Streamlit dashboard, and configurable alerts for completeness, freshness, failed jobs, distribution shifts and realized errors. Alerts do not retrain or deploy models. Verification status is recorded in `VERIFICATION.md`.

**Boundaries and next step.** CMS releases data quarterly. Daily availability, including historical census, is an explicit replay assumption, not verified operational availability. These nursing-home data do not reveal unmet staffing demand, clinically appropriate staffing or achievable savings. Cloud Run, Cloud Storage and BigQuery deployment preparation is included; cloud execution is unverified. Before operational use, validate source arrival timing and revisions, evaluate prospective forecasts, and review facility-level failures with workforce analysts.
