# Reproduce or inspect the analysis

The [quick start](../README.md#quick-start--no-download-or-training-required) serves the frozen real analysis without raw data or model training. Use Python 3.12 and the complete `requirements.lock` for package/model compatibility.

## Verify the frozen evidence

```bash
python scripts/verify_publication.py
python -m pytest -q -p no:cacheprovider
```

The first command checks bundle hashes, recomputes MAE/WAPE/signed error/interval coverage/width with DuckDB from separate forecasts and outcomes, and checks relative documentation links. Tests use small synthetic data only for software behavior; the dashboard tests use the real included bundle. Routine verification needs no cloud credentials or full CMS acquisition.

## Reacquire and rerun without overwriting this release

```bash
python scripts/init_reproduction.py --directory reproduction
workforce --config reproduction/configs/full.json fetch
workforce --config reproduction/configs/full.json prepare
workforce --config reproduction/configs/full.json train
workforce --config reproduction/configs/full.json backtest
workforce --config reproduction/configs/full.json predict --origin 2026-03-24
workforce --config reproduction/configs/full.json predict --origin 2026-03-31
workforce --config reproduction/configs/full.json realize --asof 2026-03-31
workforce --config reproduction/configs/full.json monitor --asof 2026-03-31
workforce --config reproduction/configs/full.json monitor --asof 2026-03-31 --demo-alert
workforce --config reproduction/configs/full.json report
```

`run` combines every command after `fetch` above. `init_reproduction.py` copies the full/dev configurations into a **new empty directory**. The config location determines the experiment root. The new root begins with an empty provenance manifest and separate output files. The script refuses an existing destination. On Windows without an activated environment, use `.\.venv\Scripts\workforce.exe` in place of `workforce`.

`fetch` discovers official catalog distributions, requests state-filtered API pages, and stores bytes unchanged. A fresh NY snapshot requires approximately 301 MB; processing and dependencies need additional disk space. The final page is short/empty and pagination keys are checked. `fetch --national-csv` downloads much larger national files instead. Do not combine conflicting release revisions in one experiment.

The original [manifest](../data/manifest.json) preserves the recorded 2026-09-13 retrieval. A new fetch records new timestamps and checksums. CMS revisions, retired URLs, library/platform differences or changed snapshot contents can prevent exact numerical reproduction. Compare source checksums before interpreting differences; this release's metrics describe its preserved snapshot. Model version `c1b7f9939a74d3d1` and all published test predictions remain unchanged.

For byte-identical raw restoration, retrieve every original manifest entry's `source_url` to its recorded relative `path` **in a separate directory**, and validate its SHA-256 before registering it. Do not claim exact restoration if any checksum differs. Raw copies are not hosted as a release asset. The included derived evidence is enough to verify the reported evaluation even when a historical source URL is unavailable.

## Manual acquisition fallback

Download the requested official CSV releases from the [CMS dataset page](https://data.cms.gov/quality-of-care/payroll-based-journal-daily-nurse-staffing). After initializing a new experiment, ingest each unchanged CSV:

```bash
workforce --config reproduction/configs/full.json ingest-manual downloaded-quarter.csv --period "2024-04-01/2024-06-30" --source-url "OFFICIAL_CMS_DOWNLOAD_URL"
```

Use each file's actual reporting period and download URL. Repeat for all eight quarters, then `run`. Missing dates stay missing; reported zeros stay zero; conflicting facility/date records stop preparation. Current code supports the verified modern 33-column nursing schema. Older schema variants need explicit adaptation.

## Inspect a newly completed replay

Set `WORKFORCE_ARTIFACTS` to the new `reproduction/artifacts/full` directory, then launch `python -m streamlit run app.py`. To change an experiment inside an existing root, copy its configuration with a new `name`; immutable forecast files deliberately reject changed values at existing keys.

Docker build/run and GCP execution have not been verified. [Deployment preparation](GCP_DEPLOYMENT.md) remains separate from local reproduction and routine CI.
