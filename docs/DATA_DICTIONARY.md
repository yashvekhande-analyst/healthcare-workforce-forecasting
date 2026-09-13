# Data dictionary and transformations

Source schema: **CMS PBJ nursing dictionary 2023-06-02**, verified against all downloaded quarters. The [official dictionary](https://data.cms.gov/sites/default/files/2023-06/Payroll%20Based%20Journal%20Daily%20Nursing%20Staffing%20Data%20Dictionary.pdf) is the authority for source fields.

| Source fields | Meaning and handling |
| --- | --- |
| PROVNUM | Six-character facility identifier; read and persist as a string, including leading zeros |
| PROVNAME, CITY, STATE | Reported facility name, city, and state; state defaults to NY |
| COUNTY_NAME, COUNTY_FIPS | County name/code; identifiers remain strings |
| CY_Qtr | Calendar reporting quarter, cross-checked with WorkDate |
| WorkDate | Work day; explicitly parsed as YYYYMMDD |
| MDScensus | MDS-derived resident count; finite nonnegative integer; invalid becomes null |
| Hrs_RNDON, Hrs_RNadmin, Hrs_RN, Hrs_LPNadmin, Hrs_LPN, Hrs_CNA, Hrs_NAtrn, Hrs_MedAide | Role totals; each also has `_emp` and `_ctr` employee/contract components |

All eight role total/employee/contract identities are checked within **0.051 hours** to allow rounding. Missing, nonnumeric, nonfinite or negative values are flagged. A broken RN/LPN/CNA identity or invalid related component makes that day's target unavailable. Problems in excluded roles remain audit flags but do not remove an otherwise valid target. Positive extremes are retained for inspection.

| Derived field | Definition / availability |
| --- | --- |
| contract_hours | Hrs_RN_ctr + Hrs_LPN_ctr + Hrs_CNA_ctr; null if any relevant input is invalid |
| employee_hours | Corresponding employee components; same units, no administrative roles |
| rn_contract, lpn_contract, cna_contract | Individual target components for charting |
| reported | True when a source facility-day row exists; false for inserted calendar gaps |
| missing_hours, negative_hours, component_mismatch, invalid_census | Source audit flags; check `reported` separately for missing dates |
| origin | End-of-day T, when predictors are assumed known |
| target_end | T+7; full outcome window must finish by a training cutoff |
| target / actual | Contract total over T+1…T+7, only if all seven dates are observed |
| contract_today | Contract hours at T |
| previous_7 | Contract sum T−6…T; persistence baseline prediction |
| trailing_28 | Contract average T−27…T × 7; trailing-average baseline prediction |
| contract_lag7, contract_lag14 | Contract hours at T−7 / T−14 |
| contract_std7, contract_std28 | Historical population standard deviations over 7/28 dates |
| zero_fraction28 | Share of reported zero contract days during T−27…T |
| employee_mean7, employee_mean28 | Historical means over matching windows |
| census_today, census_mean7, census_lag7 | Census at T, trailing 7-day average, census at T−7 |
| next_weekday, season_sin, season_cos | Known calendar features for T+1; sine/cosine use day of year |
| history_count, eligible | Valid contract days in preceding 28 calendar dates; eligible iff count is 28 |
| facility, county | Categorical predictors with one-hot categories fitted on training only |
| volume_group | Low/medium/high initial-training contract volume, divided at selected-facility 1/3 and 2/3 quantiles |
| prediction, lower, upper | Forecast and interval endpoints in seven-day contract hours |
| interval_level | Nominal interval probability (default 0.90) |
| model_version, split | Reproducibility identifier and validation/calibration/test/replay assignment |

Facility descriptors are fixed at the initial training cutoff for this cohort; no future descriptor backfill is used. Numerical preprocessing is a training-only median imputer with missing indicators. Calendar-grid windows prevent a missing date from being mistaken for an adjacent day. Administrative totals and employee components are never added to the contract target.
