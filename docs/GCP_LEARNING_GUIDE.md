# Learning and interview guide

This is a hands-on portfolio exercise using historical CMS nursing-home data. Automated execution supplies evidence to inspect; it does not establish that the owner already understands each service. Use [cloud verification](GCP_VERIFICATION.md) to distinguish completed work from pending work.

## Explain the architecture

| Question | Answer grounded in this project |
|---|---|
| Why both Cloud Storage and BigQuery? | Storage preserves files: Parquet, the existing model, manifests, predictions, and reports. BigQuery provides typed tables and independent SQL aggregation. A bucket alone does not supply a SQL warehouse. |
| Service versus job? | The Cloud Run service listens on port 8080 and serves Streamlit requests. The job runs one historical origin, writes results, and exits. One image supports two explicit entry points. There is no recurring schedule. |
| What is a service account? | A runtime identity. `workforce-viewer` reads the dashboard bucket; `workforce-runner` reads the input bucket and reads/creates objects in a separate output bucket. Neither receives BigQuery access. The human deployer loads and queries BigQuery. |
| Why a separate build identity? | `workforce-builder` reads the build source bucket, writes only the selected Artifact Registry repository, and writes build logs. Runtime identities do not build or deploy. No downloaded service-account key is needed. |
| What is versioned? | Input release, source manifest, model bundle, container digest, query text, and output artifact ID. Checksums identify bytes; an execution ID identifies one attempt to produce or reuse them. |
| How do retries work? | The same inputs/origin/as-of/contract produce the same artifact ID. GCS creation uses generation-match zero. Existing identical bytes are accepted, conflicting bytes fail, and each execution gets a receipt. A report is the completion marker after both Parquet outputs exist. |
| How do you prevent leakage? | The existing `features_at` function truncates daily observations at the origin before running SQL windows. Future labels are read by the evaluator only after prediction. Tests change all future observations and require identical predictions. |
| How do you reconcile results? | Check table types, row counts, unique keys, and unmatched joins first. Then compare all three model metrics to frozen local CSV values. Counts must match exactly; FLOAT64 metrics use relative tolerance 1e-9 and absolute tolerance 1e-8. |
| What did the cloud run change about the model? | Nothing: the selected preceding-week baseline and earlier calibration are reused. No model search or training is part of the batch demonstration. |

## Inspect evidence at each milestone

1. **Storage:** inspect `uploads.json` for names, sizes, SHA-256, and byte-for-byte read-back. Inspect each bucket's IAM policy and public-access prevention. A successful read by the deployer alone does not verify the runtime identity; confirm runtime startup and job reads too.
2. **BigQuery:** inspect `loads.json`, `integrity.json`, `evaluation.sql`, `evaluation.json`, and `reconciliation.json`. Explain why 8,667 issued rows per model become 8,660 evaluated rows. A null outcome is neither zero nor a missing forecast.
3. **Dashboard:** inspect the deployed image digest, runtime account, environment, read-only mount, and `dashboard_artifacts_verified` event. Open the actual service URL, change the origin and facility selection, inspect intervals, and download a CSV.
4. **Batch:** inspect execution status, `replay_success`, artifact IDs, two separate Parquet files, metrics, and the execution receipt. Compare March 24 predictions with the previously saved March 24 replay.
5. **Failure:** the intentionally missing input should end with a nonzero exit and `replay_failed` naming `FileNotFoundError`. A deployment/API failure is not evidence for this test. A second task attempt is an automatic retry, not a second logical forecast batch.

## Small repeat operation after the first successful deployment

Open BigQuery Studio in the selected project. Paste the concrete `evaluation.sql` saved in cloud evidence. Before **Run**, open query settings and set **maximum bytes billed to 1,073,741,824 (1 GiB)**; check the editor's estimated bytes. Run it, then record the job ID and compare the selected `previous_7` row:

- `issued_forecasts = 8667`, `n = 8660`, `unknown_outcomes = 7`.
- MAE approximately 39.59393187 hours; WAPE approximately 0.072878684 (7.29%).
- Signed error approximately +1.16747229 hours; coverage approximately 0.862240185.

Explain out loud why WAPE is a fraction, why signed error can cancel, and why coverage differs from the nominal 90%. This repeat operation is a guided exercise until a user-performed query and job ID have been observed; do not describe it as completed beforehand.

## Troubleshooting and costs

| Symptom | First place to inspect |
|---|---|
| Cloud Build cannot read source or push | Build log and builder IAM grants on staging bucket/repository |
| Service cannot start | Cloud Run revision logs; manifest hash, mount prefix, read-only flag, port and memory |
| WebSocket disconnect after an hour | Cloud Run request timeout; reconnect is expected, and state is not durable |
| Job fails before prediction | `replay_failed` event; input prefix and checksum; job service account |
| Job fails saving output | Output IAM permissions or conflicting immutable object; never delete evidence merely to make a retry pass |
| SQL counts multiply | Duplicate forecast/outcome keys, missing dataset version in join, or accidental append load |
| Costs exceed estimate | Billing reports filtered to this project; open public dashboard connections, rebuilds, stored image versions, query volume, network egress |

Budget alerts notify; they do not stop spending. Zero minimum instances does not mean zero cost while a WebSocket remains open. One maximum instance limits service scale, not Artifact Registry, Storage, builds, queries, logs, egress, or occasional platform scaling overshoot. Use [resource-specific cleanup](GCP_CLEANUP.md).

## Honest interview boundaries

The dataset is one state's 50-facility cohort, public CMS data are quarterly and revisable, and daily availability is assumed. Prediction intervals under-cover some groups. There is no live hospital integration, prospective clinical validation, production SLA, disaster-recovery exercise, load test, enterprise security assessment, or staffing recommendation. The dashboard can have cold starts. A public demo is suitable for portfolio review, not operational workforce planning.

Describe only the cloud steps marked **verified** in the evidence report. Prefer concrete statements about an executed query or job over claiming enterprise production ownership.
