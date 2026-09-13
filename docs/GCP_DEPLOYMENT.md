# GCP deployment preparation — execution unverified

No cloud resources have been created, and no external site has been published. The local application runs without credentials. Docker was not available for a container run in this environment. Configuration files alone are not evidence of successful cloud deployment.

## Prepared design

- **Cloud Storage:** immutable version prefixes for processed artifacts, raw provenance and model outputs; object versioning protects revisions.
- **Cloud Run:** authenticated read-only Streamlit dashboard with a read-only bucket mount. No training or DuckDB writes on the mount.
- **BigQuery:** separate daily, forecast and outcome tables loaded from Parquet; `cloud/evaluation.sql` recomputes the metrics.

The server can also serve bundled snapshot artifacts from the image. Keep a dated artifact version, model checksum, image digest and deployment result together. Changing a model requires a new version and explicit review.

## Before execution

Resolve the target project, billing authorization and a budget with its owner. Estimate Cloud Build, Artifact Registry, Storage, Cloud Run and BigQuery costs in that project's region. Budget alerts are notifications, not hard spending caps; max instances of 1 and min instances of 0 limit this demonstration's serving footprint but do not cap all charges.

Install the Google Cloud CLI and Docker or authorize Cloud Build. Use `gcloud auth login` (or the organization's federation flow); do not commit credentials. The deployment operator needs permission to enable APIs, create the described resources, run builds and act as the runtime service account. The build service identity needs the project-appropriate build and Artifact Registry permissions. Inspect the identity used by your project's Cloud Build setup before granting access. The runtime viewer gets only `roles/storage.objectViewer` on the artifact bucket. BigQuery loading is performed by the operator, not by the web app.

## Concrete PowerShell path

First inspect the proposed resource scope without cloud changes:

```powershell
.\cloud\deploy.ps1 -ProjectId "YOUR_AUTHORIZED_PROJECT" -Bucket "YOUR_GLOBALLY_UNIQUE_BUCKET" -Region "us-central1"
```

After project/budget authorization, review `cloud/deploy.ps1` and execute explicitly:

```powershell
gcloud auth login
.\cloud\deploy.ps1 -ProjectId "YOUR_AUTHORIZED_PROJECT" -Bucket "YOUR_GLOBALLY_UNIQUE_BUCKET" -Region "us-central1" -ArtifactTag "portfolio-v1" -Execute -BudgetConfirmed
```

The initial-creation script stops on errors and does not silently replace existing resources. For a pre-existing project bucket/repository/service account, inspect and reuse those resources manually, following the individual commands in the script. Never repeatedly run creation commands as a substitute for checking external state.

The script enables required services, creates the named bucket/repository/service account, uploads `artifacts/full`, loads separate versioned BigQuery tables, builds the Docker image, and deploys an authenticated Cloud Run service. Storage and BigQuery use the same region. The application reads `WORKFORCE_ARTIFACTS` at `/mnt/artifacts/releases/portfolio-v1/full`; serving requires no cloud SDK inside Python.

## Verify before claiming deployment

```powershell
gcloud run services describe workforce-replay --project YOUR_AUTHORIZED_PROJECT --region us-central1
gcloud run services proxy workforce-replay --project YOUR_AUTHORIZED_PROJECT --region us-central1 --port 8081
```

Open the proxy's localhost URL while authenticated. Check health, loaded model version, historical origin selection, facility filters, charts, download contents, missing-data states and alert demonstration. Confirm no Cloud Storage writes occur. The request timeout is set to 3,600 seconds for Streamlit's WebSocket sessions; verify reconnect behavior after timeout.

Replace placeholders in `cloud/evaluation.sql`, run it in BigQuery with a query cost limit, and compare row counts and results with `artifacts/full/reports/test_metrics.csv`. Use new version tables for new snapshots; do not overwrite forecast history. Keep outcome corrections as new dated snapshots with provenance. A future multiwriter inference service would require object-generation preconditions or transactional storage; the present design deliberately serves frozen artifacts.

Delete or disable the named demonstration service after use if ongoing serving is unnecessary. Review retained bucket objects and images with the project owner before deletion. Do not delete the entire project merely to clean up this demo.

## Official documentation checked 2026-09-13

- [Cloud Run Python deployment and prerequisites](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-service)
- [Cloud Run read-only Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [BigQuery Parquet loading from Cloud Storage](https://docs.cloud.google.com/bigquery/docs/loading-data-cloud-storage-parquet)
- [Cloud Run WebSockets and timeouts](https://docs.cloud.google.com/run/docs/triggering/websockets)

These sources informed the configuration. Deployment authentication, billing, image build, IAM behavior, mounted artifacts, BigQuery loading and hosted application behavior are all **unverified** until the above steps are actually executed in an authorized project.
