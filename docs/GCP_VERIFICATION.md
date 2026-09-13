# Google Cloud verification

Status as of 2026-09-13: **local cloud preparation verified; hosted deployment pending billing**.

| Component | Status | Evidence |
|---|---|---|
| Google Cloud CLI | Verified | SDK 584.0.0 official archive SHA-256 verified; normal browser authorization; project and billing read commands succeeded |
| Dedicated project | Created | `workforce-replay-yv-260913`, display name Healthcare Workforce Demo, labels `portfolio=workforce`, `environment=demo` |
| Billing | Pending user setup | No billing account available to authenticated login; new project has no linked billing account |
| Frozen local results | Verified | 39 original hashes pass; independent local SQL matches all three models |
| Cloud upload staging | Verified locally | 5,275,777 bytes; 16 required dashboard files, four batch inputs, three typed BigQuery exports, manifests; no raw snapshot |
| Batch contracts | Verified locally | Tests cover frozen prediction equivalence, future-data mutation, retry reuse, conflict refusal, checksum rejection, missing-input exit/logs, date/ID types and metric discrepancy detection |
| Full local tests | Verified | 22 tests passed; original analytical artifacts unchanged |
| GCS uploads and runtime permissions | Not executed | Requires enabled billing and infrastructure creation |
| BigQuery loads and reconciliation | Not executed | SQL and reconciliation runner prepared; local metrics are reference values only |
| Container build / hosted UI | Not executed | Build config and verified-mount entry point prepared; Docker unavailable locally |
| Cloud Run job success / controlled failure | Not executed | One manually triggered job configuration prepared; cloud execution IDs do not yet exist |
| User repeat operation | Pending | Follow the small query exercise after successful deployment |

## Reference values, not cloud results

| Model | Issued | Evaluated | MAE hours | WAPE | Signed error hours | Interval coverage |
|---|---:|---:|---:|---:|---:|---:|
| previous_7 (selected) | 8,667 | 8,660 | 39.5939318707 | 7.2878683563% | +1.1674722864 | 86.2240184758% |
| gradient_boosted | 8,667 | 8,660 | 39.9122461957 | 7.3464589733% | -1.3341939013 | 84.1916859122% |
| trailing_28 | 8,667 | 8,660 | 40.6907667436 | 7.4897575799% | +3.5087378753 | 86.4549653579% |

Dataset release: `cms-ny50-c1b7f9939a74d3d1-v1`. Existing model bundle: `c1b7f9939a74d3d1`. Batch input-manifest SHA-256: `e92a44c60ade1871ca4e70889997d79f49b81b50b4a775fa7606bcca588d229a`.

The original 50-facility analysis and model are preserved. Only an optional artifact-release caption was added to the existing dashboard. No real-data retraining occurred. Tests may train their existing small synthetic fixtures.

## Evidence required before marking deployment complete

Save sanitized copies of upload receipts, IAM policies, deployed service/job configuration, image digest/build ID, BigQuery load/query IDs and reconciliation, actual hosted screenshots and CSV checks, success/failure execution status and structured logs. Never publish OAuth files, auth headers, payment details, or private account identifiers. A successful deploy command alone is insufficient.

Current hosted dashboard URL: **none**. No application resources or uploads have been created at this status checkpoint; the dedicated project is empty. See [deployment procedure](GCP_DEPLOYMENT.md), [learning guide](GCP_LEARNING_GUIDE.md), and [cleanup](GCP_CLEANUP.md).
