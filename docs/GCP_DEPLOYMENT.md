# Google Cloud deployment

This extends the existing historical replay. It never acquires new CMS data, retunes, or retrains the model. **Consult [verification status](GCP_VERIFICATION.md) for the executed resources, query results, and runtime evidence.**

## Region, identity, and cost

Use `us-central1` (Iowa) for Cloud Run, Cloud Build, Artifact Registry, Storage buckets, and the BigQuery dataset. These services support the region; co-location avoids unnecessary cross-region data transfer. This is a US public-data portfolio choice, not a clinical data-residency assessment.

Dedicated project: `workforce-replay-yv-260913`. The owner authorized a public dashboard and $5 demonstration spending over 30 days. All underlying buckets stay private with uniform bucket-level access and enforced public-access prevention. Public access applies only to the Cloud Run service's invoker role.

Planning rates checked against official Google pages on 2026-09-13; USD list prices, without assuming free-tier availability:

| Service / assumption | Estimated charge |
|---|---:|
| [Cloud Run service](https://cloud.google.com/run/pricing): 1 vCPU + 1 GiB, 10 active viewing hours; $0.000024/vCPU-second + $0.0000025/GiB-second | $0.954 plus requests/egress |
| [Cloud Run jobs](https://cloud.google.com/run/pricing): three runs, at most 10 minutes each, 1 vCPU + 1 GiB; $0.000018 + $0.000002 per second | $0.036 before retries |
| [Cloud Build](https://cloud.google.com/build/pricing): three 20-minute E2_STANDARD_2 builds at $0.006/minute | $0.36 |
| [Artifact Registry](https://cloud.google.com/artifact-registry/pricing): assume up to 2 GiB of stored images; roughly $0.10/GiB-month | about $0.20 before free allowance |
| [Cloud Storage](https://cloud.google.com/storage/pricing): 0.1 GiB including staging/versions; about $0.02/GiB-month, plus modest operation volume | storage about $0.002; operations extra |
| [BigQuery](https://cloud.google.com/bigquery/pricing): at most 20 queries, each capped at 1 GiB, $6.25/TiB; tiny logical storage | queries at most about $0.122 under these assumptions |
| [Cloud Logging](https://cloud.google.com/products/observability/pricing): assume 10 MiB logs, $0.50/GiB ingestion beyond allowance | below $0.005 |

Plan for **$1–$3 under light use**. Charges depend on actual billed resources, region, credits, traffic, operation minimums, build failures/retries, storage versions, logs and egress. This is an estimate, not a quote or a hard cap. Storage/Registry monthly prices above convert their hourly rates using about 730 hours; per-month duration varies.

A public dashboard with a continuously active connection is materially different: one 1-vCPU/1-GiB instance active for 30 days is about **$68.69** before requests, egress, other services, and credits. [WebSocket connections remain active requests](https://docs.cloud.google.com/run/docs/triggering/websockets); close tabs after demonstrations. Min=0 and max=1 are scale controls, not total-spend controls or guarantees against transient platform overshoot.

[Budget alerts do not cap spending](https://docs.cloud.google.com/billing/docs/how-to/budgets). A project-filtered $5 budget was created for September 13–October 13, 2026 with 50%, 80%, and 100% thresholds. It excludes credits from the cost calculation so credits do not hide gross usage. Project billing is enabled; account identifiers, payment details and credit balances are omitted from public evidence. Review billing frequently and use [cleanup](GCP_CLEANUP.md) when the demo is no longer needed. No paid reservation, recurring batch schedule, Vertex AI, Kubernetes, or load balancer is used.

## Preparation and access

Install the [official Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk) and authenticate using `gcloud auth login` in the browser. Do not paste tokens into chat, create service-account keys, or commit SDK configuration. The deployer needs authority to enable services, create the listed resources, grant the listed IAM permissions, use the runtime/build identities, and load/query BigQuery. A dedicated personal project avoids granting these rights inside an employer's project.

From the repository root, install the pinned Python dependencies and current package as in the README. Then:

```powershell
$project = 'workforce-replay-yv-260913'
$region = 'us-central1'
$stage = Join-Path (Split-Path (Get-Location) -Parent) 'cloud-stage'
$evidence = Join-Path (Split-Path (Get-Location) -Parent) 'cloud-evidence'
gcloud auth list
gcloud projects describe $project
gcloud billing projects describe $project
python cloud/prepare.py --destination $stage
python scripts/verify_publication.py
python -m pytest -q -p no:cacheprovider
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Public
```

The last command is a preview. It creates nothing. Staging verifies the original 39 checksums, copies 16 dashboard dependencies, four batch inputs and provenance, and exports separate BigQuery Parquet tables. It converts calendar fields to Parquet DATE and retains six-character facility strings, missing values, model identifiers, and dataset version. The approximately 301 MB raw snapshot is not uploaded.

## Create resources and load artifacts

Only after billing is enabled and the estimate/spending scope are authorized:

```powershell
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Phase Infrastructure -Execute -BudgetConfirmed
python cloud/upload.py --stage $stage --dashboard-bucket "$project-wf-view" --input-bucket "$project-wf-input" --evidence "$evidence/uploads.json"
python cloud/bigquery.py --project $project --stage $stage --input-bucket "$project-wf-input" --evidence "$evidence/bigquery" --load
```

The dedicated project must have label `portfolio=workforce`; the script refuses unlabelled projects. Inspect existing resources before reuse. The script recognizes missing resources only from explicit not-found responses; permission errors are not treated as absence.

| Identity | Granted access |
|---|---|
| Human deployer | Creates/configures resources, uploads verified files, loads/queries BigQuery; credentials stay in CLI storage |
| `workforce-viewer` | `roles/storage.objectViewer` on `$project-wf-view` only |
| `workforce-runner` | `roles/storage.objectViewer` on `$project-wf-input`; objectViewer + objectCreator on `$project-wf-output` |
| `workforce-builder` | ObjectViewer on `$project-wf-build`, Artifact Registry Writer on `workforce` repository, project Logging Writer |
| Cloud-managed service agents | Standard service-agent permissions needed by Run/Build; inspect separately from user-managed runtime accounts |
| Anonymous visitor, when authorized | `roles/run.invoker` on dashboard service only |

Storage creates use `ifGenerationMatch=0` and compare bytes on conflicts. Each upload is read back. Versioning preserves noncurrent generations; the lifecycle policy removes superseded generations after seven days when a newer version exists. It does not delete the current release. Input/output storage are different buckets, so runtime grants never allow batch writes into its model or input location.

BigQuery loads use deterministic job IDs derived from table name and export hash, plus **WRITE_EMPTY**. Repeated completed jobs are retrieved and checked. If an unknown pre-existing table contains data, loading fails; it never silently appends or truncates. Tables have a 30-day expiration in the dedicated dataset. A changed export requires a new dataset/table version, not an overwrite.

`integrity.sql` checks 36,500 grid rows (36,319 reported), 26,001 forecasts across three models, 8,667 outcome rows, 8,660 known outcomes, zero duplicate keys and zero unmatched outcome rows. Only then does `evaluation.sql` run. Every query is dry-run and capped at 1 GiB billed. The runner records SQL, job IDs, bytes, schema, result rows, and differences from all saved model metrics. Integer counts must match exactly; distributed FLOAT64 reductions use 1e-9 relative / 1e-8 absolute tolerance. No BigQuery result is claimed until these files show success.

## Build and deploy

```powershell
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Phase Build -Execute -BudgetConfirmed
```

The build uses a dedicated identity, private regional source bucket, `.gcloudignore` allowlist, pinned Python dependencies, and the existing Dockerfile. It tests imports inside the built container. Record the successful build ID and its `results.images[].digest` using `gcloud builds describe BUILD_ID --region=$region --project=$project --format=json`.

The verified Windows environment could not create the CLI's temporary archive directory. This supported alternative packages only the Dockerfile, pinned package files, application, source, Streamlit config, and existing artifact bundle. It normalizes archive metadata, names the object by SHA-256, creates it exclusively, and checks its downloaded bytes. No credentials or local work directory enter the archive:

```powershell
python cloud/package_source.py --bucket "$project-wf-build" --evidence "$evidence/build-source.json"
# Copy the gs:// source URL printed by the command above.
$sourceArchive = 'gs://REPLACE_WITH_PRINTED_SOURCE_URL'
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Phase Build -SourceArchive $sourceArchive -Execute -BudgetConfirmed
```

Bucket lifecycle configuration similarly uses the official Storage JSON API with a metageneration precondition, avoiding the CLI's Windows multiprocessing limitation. BigQuery operations use REST with the normal CLI access token held only in process memory; no service-account key or separate application-default login is required. Coverage SQL converts the Boolean interval indicator to INT64 before averaging, as required by GoogleSQL.

```powershell
$digest = 'sha256:REPLACE_WITH_SUCCESSFUL_BUILD_DIGEST'
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Phase Deploy -ImageDigest $digest -Public -Execute -BudgetConfirmed
```

Use `-Public` only for authorized public access; omit it for an authenticated initial service. The service uses 8080, 1 GiB, 1 CPU, min=0, max=1, concurrency=10, session affinity, and a one-hour request timeout. Streamlit reconnects after timeout; session state is not durable. Its mounted release is read-only. Startup verifies the manifest and artifact hashes and the mount's read-only flag before starting the server, emitting `dashboard_artifacts_verified`. The artifact-release caption identifies the intended data version. The app contains no training or artifact writes.

Verify the real hosted URL: initial load, sidebar version, two origins, facility selection, empty selection/missing-history states, plots and interval bounds, a downloaded CSV's IDs/counts/values, and accessible runtime logs. Record screenshots and sanitized checks. Deployment-command success is not UI verification.

## Run the one batch job and failure test

```powershell
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Phase Job -Execute -BudgetConfirmed
./cloud/deploy.ps1 -ProjectId $project -Stage $stage -Phase FailureTest -Execute -BudgetConfirmed
```

The saved job has one task, parallelism 1, one retry, a 600-second limit, 1 CPU and 1 GiB. It loads the existing model from a checksum-verified release and predicts origin **2026-03-24**, evaluating outcomes through **2026-03-31**. Prefix-only feature construction is reused. Predictions and actuals are separate objects; metrics and monitoring are computed afterward. No retraining occurs.

Logical results live at `runs/DATASET_VERSION/ARTIFACT_ID/`; attempts have separate receipts at `runs/executions/EXECUTION/attempt-N.json`. Identical retries reuse existing objects. Conflicting bytes fail. Require `report.json` as the completion marker before consuming outputs. A partial attempt may leave immutable intermediate objects, which the next identical attempt can finish safely.

The controlled failure overrides the input to `tests/intentionally-missing` and uses a separate `tests/missing-input` output namespace for that execution only. It must fail for **FileNotFoundError**, not merely any error. Inspect the execution's status and `replay_failed` logs; verify that no main-result files changed. Record successful and failed execution IDs. Re-execute the normal job to demonstrate safe reuse if budget allows. No scheduler is created.

Useful evidence commands:

```powershell
gcloud run services describe workforce-replay --region=$region --project=$project --format=export
gcloud run services get-iam-policy workforce-replay --region=$region --project=$project
gcloud run jobs describe workforce-replay-batch --region=$region --project=$project --format=export
gcloud run jobs executions list --job=workforce-replay-batch --region=$region --project=$project
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="workforce-replay-batch"' --project=$project --limit=30 --format=json
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="workforce-replay"' --project=$project --limit=30 --format=json
```

After success, do the [small repeat query exercise](GCP_LEARNING_GUIDE.md). Sanitize evidence before committing. Never publish local auth directories, tokens, payment details, or account emails. Published screenshots must show this hosted deployment, not a local dashboard relabelled as cloud.

## Official implementation references

- [Storage request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions), [Storage IAM roles](https://docs.cloud.google.com/storage/docs/access-control/iam-roles), [Cloud Run read-only storage mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts).
- [BigQuery Parquet loads](https://docs.cloud.google.com/bigquery/docs/loading-data-cloud-storage-parquet), [job configuration / WRITE_EMPTY](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job).
- [Cloud Run jobs](https://docs.cloud.google.com/run/docs/create-jobs), [execution overrides](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/execute), [runtime contract and service-identity metadata](https://docs.cloud.google.com/run/docs/container-contract).
- [Build service accounts](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts), [build schema](https://docs.cloud.google.com/build/docs/build-config-file-schema), [Cloud Run deploy flags](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).
