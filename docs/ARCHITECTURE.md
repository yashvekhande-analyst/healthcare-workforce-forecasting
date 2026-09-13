# Architecture

```mermaid
flowchart LR
    CMS[CMS quarterly catalog and PBJ releases] --> RAW[Immutable raw API pages or CSVs]
    RAW --> MAN[Provenance manifest and checksums]
    RAW --> VALID[Schema and value validation]
    VALID --> COHORT[Training-only facility selection]
    COHORT --> SQL[DuckDB calendar grid and SQL windows]
    SQL --> PARQUET[Daily and feature Parquet]
    PARQUET --> CV[Expanding validation and model selection]
    CV --> FIT[Frozen model and earlier interval calibration]
    FIT --> MODEL[Versioned saved model]
    PARQUET --> REPLAY[Prefix-only historical replay]
    MODEL --> REPLAY
    REPLAY --> FORECAST[Immutable forecasts]
    PARQUET --> ACTUAL[Later matured actuals]
    FORECAST --> EVAL[Joined evaluation and reports]
    ACTUAL --> EVAL
    EVAL --> APP[Read-only Streamlit analyst dashboard]
    FORECAST --> APP
    PARQUET --> MON[Completeness freshness job drift error monitoring]
    EVAL --> MON
    MON --> APP
```

The replay advances an assumed daily clock over quarterly public data. `predict` rebuilds features from the daily prefix ending at T and loads the saved bundle. The seven-day label is unavailable in that prefix. Outcomes are attached in separate dated files once their target window matures; forecasts remain unchanged.

DuckDB owns analytical SQL and materialized local tables. Parquet is the portable interface among the pipeline, reports and dashboard. Python owns source validation, model orchestration and monitoring. The dashboard never writes source files or fits models. Local persistence is single-writer, and changed immutable records are rejected.

## Prepared GCP mapping (unverified)

```mermaid
flowchart LR
    LOCAL[Verified local pipeline] --> GCS[Cloud Storage versioned artifact prefix]
    GCS --> CR[Cloud Run read-only dashboard]
    GCS --> BQ[BigQuery daily forecast outcome tables]
    BQ --> SQLVIEW[Recomputable evaluation view]
```

The proposed cloud path serves a frozen analyzed snapshot. Cloud Storage holds provenance/raw/processed artifacts; Cloud Run mounts the artifact bucket read-only; BigQuery supports larger SQL audit and analysis queries. A daily cloud ingestion schedule would misrepresent CMS release frequency, so none is included. Training jobs and any future internal feed require a separate, justified operational design.
