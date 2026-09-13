# Model card

**System:** Healthcare Workforce Staffing Forecasting System v1.0.0. Independent portfolio; local historical replay. **Domain:** nursing homes. **User:** workforce planning analyst.

**Prediction:** observed contract RN + LPN + CNA hours for one facility during T+1…T+7. End-of-day T staffing history and lagged census are assumed available. The model does not measure staffing need, quality, clinical adequacy, savings, retention or compliance.

**Training data:** eight public CMS PBJ quarters, 2024Q2–2026Q1; 50 New York facilities selected from 591 eligible facilities using only April–December 2024 coverage. A seeded hash chooses facilities with at least 95% training coverage. No future completeness or test performance enters cohort selection. Source data contain CMS's upstream inclusion/exclusion decisions and retrospective corrections.

**Selection:** the preceding-seven-day baseline won pooled validation MAE (40.88 hours), compared with 41.38 for the 28-day average and 42.70 for the best gradient candidate. It has no fitted point-prediction weights. Its interval calibration and monitoring references are learned from earlier data. The alternative scikit-learn histogram gradient model uses historical staffing/census summaries, calendar features, facility and county; four candidates were tested, with preprocessing fitted separately in each expanding fold.

**Chronology:** validation origins January 1–March 24 and April 1–June 23, 2025; frozen final model fit cutoff June 30; calibration origins July 1–September 23 at seven-day steps, with labels finished by September 30. Test origins October 1, 2025–March 24, 2026. All training labels have fully matured by the cutoff.

**Measured held-out behavior:** 8,660 evaluable facility-origins; selected baseline MAE **39.59 hours**, WAPE **7.29%**, signed error **+1.17 hours**. Nominal 90% intervals covered **86.22%**, with mean width **398.03 hours**. They undercovered the held-out data. Counts include overlapping seven-day windows and are not independent samples. Weekly-origin sensitivity and facility/volume breakdowns are provided in the backtest report.

**Coverage limits:** 8,667 of 8,750 expected test facility-origins were forecastable; seven issued forecasts had unobserved targets. Across the full cohort calendar, 181 facility-days were absent from source files. Scoring only complete outcomes can hide performance in periods with reporting problems. Facility selection is an engineering sample, not a representative survey.

**Uncertainty:** scaled absolute residual conformal intervals use 646 earlier calibration facility-origins. Weekly spacing reduces within-facility target overlap but does not remove cross-facility or serial dependence. Distribution shifts, zeros transitioning to contract use, large facility changes and unusual reported hours are failure modes. Bounds are not jointly calibrated across facilities.

The medium training-volume group had only **74.54%** held-out coverage (versus 92.84% for high volume and 90.75% for low volume). At facility 335133 on January 25, 2026, zero preceding-week hours produced a 0-hour forecast and a 0.365-hour upper bound, but the subsequent week had 696.56 reported hours. This is a concrete failure of the interval's reliance on recent volume. No test-driven adjustment was made.

**Availability limits:** the public CMS feed is quarterly. The project assumes daily staffing and historical census arrival. Census is derived retrospectively from MDS assessments; source vintages were not reconstructed. Accuracy is conditional on this replay assumption. No operational daily forecasting ability is established from these results alone.

**Use boundaries:** analyst exploration, reproducible evaluation and interview demonstration. Unsuitable for automatic staffing allocation, employee decisions, clinical judgments, new facilities without history, hospitals, or unseen states without evaluation. Monitor missingness, stale inputs, failures, feature shifts and matured errors; review alerts before making changes. No automatic retraining.

**Execution:** local real-data pipeline and saved-model path verified; see the [verification record](../VERIFICATION.md) for tests and browser checks. Docker and GCP configuration are included, but container execution and cloud deployment remain unverified. No production users or business impact are claimed.
