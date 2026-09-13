# Verification record

Publication prepared on **September 13, 2026**, using the completed real-data implementation. No model was retrained, retuned or recalibrated for publication. Model version: **`c1b7f9939a74d3d1`**.

## Preserved evidence

- Eight CMS quarters, April 2024–March 2026; 433,437 unique New York source facility-days.
- Training-only cohort: 50 of 591 eligible facilities. Selected calendar: 36,500 expected days, 36,319 reported, 181 missing; zero invalid reported contract days.
- Two expanding validation folds (4,150 and 4,116 evaluation origins); preceding-seven-day baseline selected by minimum pooled validation MAE (40.876 hours).
- Final fit cutoff June 30, 2025; separate calibration: 646 facility-origins, outcomes ending no later than September 30.
- Held-out origins October 1, 2025–March 24, 2026: 8,750 expected, 8,667 forecastable, 8,660 evaluable, seven unavailable outcomes.
- Baseline MAE **39.593932 hours**, WAPE **7.287868%**, signed error **+1.167472 hours**, nominal 90% coverage **86.224018%**, mean interval width **398.030244 hours**.
- Weekly nonoverlapping-origin sensitivity: 1,238 observations; MAE 39.194 hours, coverage 86.107%. This removes within-facility target overlap; it does not establish independence across facilities or time.
- March 24/31 saved replay: 49 forecasts each. Later outcome attachment is separate from immutable forecasts.

The publication copies all 39 selected analytical artifact files unchanged. Their SHA-256 checksums are recorded in [bundle_checksums.json](artifacts/bundle_checksums.json). The original raw snapshot remains outside the repository; all 93 source-file hashes and source requests remain in [the manifest](data/manifest.json). The original verification checked all 93 raw hashes.

## Publication checks

**Current publication result: 14 tests passed** in 32.80 seconds in a fresh Python 3.12 environment and a clean directory exported exclusively from Git-tracked files. The original implementation also passed 14 tests. The publication check commands are:

```bash
python -m pip check
python scripts/verify_publication.py
python -m pytest -q -p no:cacheprovider
workforce --help
```

The independent verification script joins separate forecasts/outcomes with DuckDB and compares all three models' aggregate MAE, WAPE, signed error, coverage and interval width against saved reports within 1e-10 tolerance. It checks model/feature/evidence hashes and relative document/image links. These checks never fetch raw CMS data or retrain the published model.

Behavioral tests cover schema/value validation, duplicate conflicts, missing-versus-zero handling, exact calendar windows, predictor invariance under future-data mutation, label maturity, training-only selection, interval arithmetic, saved models, immutable persistence and outcome attachment, a small synthetic software-only pipeline, and dashboard filtering/empty/missing-artifact/monitoring states. Synthetic test data are never used for reported portfolio findings.

The [CI workflow](.github/workflows/ci.yml) uses Python 3.12 on an Ubuntu runner. It installs the pinned dependencies and the package, checks the real included bundle, runs the tests, and invokes the installed command. No cloud credentials, paid APIs or full raw-data acquisition are required.

The clean local check downloaded and installed the locked dependencies, built the package wheel from the clean copy, installed it into the fresh environment, and reported **no broken requirements**. The installed `workforce --help` command succeeded. The dashboard served from that copy passed its health check and displayed **26,521 hours** and **49 / 50** coverage. The separate reproduction-directory initializer also passed a configuration check. The restricted Windows runner required workspace temporary-directory staging during packaging; that workaround is not a project dependency.

The tracked-file audit found **91 files, approximately 4.9 MB**, with no raw downloads, virtual environments, caches, logs, local personal paths, recognizable credentials or private application documents. Application/pipeline source and all analytical evidence match the original bytes. The Git root contains only this project. Remote CI status is established separately by the GitHub Actions run after publication.

## Browser evidence and limits

The actual application was inspected and used to capture [overview](assets/dashboard-overview.png), [evaluation](assets/dashboard-evaluation.png) and [data-quality/monitoring](assets/dashboard-monitoring.png) screenshots. The application and displayed measurements are unchanged from the completed implementation. The [walkthrough](docs/DEMO_SCRIPT.md) explains the selected state and justified conclusions.

Historical replay is prominent. Daily source availability and retrospective data vintages remain assumptions. Intervals undercovered, including 74.54% coverage in the medium-volume group. The app's review flags include retrospective test coverage. These are measured and disclosed limitations.

**Not verified:** Docker build/run, GCP execution, hosted application behavior, production feed arrival, clinical staffing adequacy, financial savings, or generalization beyond the cohort. Cloud scripts are preparation only. Exhaustive accessibility/device and long-running operational testing were not performed.
