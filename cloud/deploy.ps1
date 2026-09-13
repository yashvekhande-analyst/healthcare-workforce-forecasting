param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [Parameter(Mandatory=$true)][string]$Bucket,
    [string]$Region = 'us-central1',
    [string]$Service = 'workforce-replay',
    [string]$ArtifactTag = 'portfolio-v1',
    [switch]$Execute,
    [switch]$BudgetConfirmed
)
$ErrorActionPreference = 'Stop'
# Preparation only by default. Review the concrete commands and billing scope in docs/GCP_DEPLOYMENT.md.
if (-not $Execute) {
    Write-Output "PREVIEW ONLY: project=$ProjectId region=$Region bucket=$Bucket service=$Service version=$ArtifactTag"
    Write-Output 'Would enable APIs, create a bucket, Artifact Registry repository and service account, upload artifacts, load BigQuery tables, build an image, and deploy an authenticated read-only service.'
    Write-Output 'Nothing was created. Review docs/GCP_DEPLOYMENT.md, establish a budget, then pass -Execute -BudgetConfirmed.'
    exit 0
}
if (-not $BudgetConfirmed) { throw 'Explicit project authorization and a reviewed budget are required. No resources were created.' }
function Invoke-Gcloud { & gcloud @args; if ($LASTEXITCODE -ne 0) { throw "gcloud failed: $args" } }
function Invoke-Bq { & bq @args; if ($LASTEXITCODE -ne 0) { throw "bq failed: $args" } }
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$image = "${Region}-docker.pkg.dev/${ProjectId}/workforce/dashboard:${ArtifactTag}"
$serviceAccount = "workforce-viewer@${ProjectId}.iam.gserviceaccount.com"
Invoke-Gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com bigquery.googleapis.com --project=$ProjectId
# This script is for initial creation in an explicitly authorized project. Existing resources should be inspected and reused manually.
Invoke-Gcloud storage buckets create "gs://$Bucket" --project=$ProjectId --location=$Region --uniform-bucket-level-access
Invoke-Gcloud storage buckets update "gs://$Bucket" --versioning
Invoke-Gcloud artifacts repositories create workforce --repository-format=docker --location=$Region --project=$ProjectId
Invoke-Gcloud iam service-accounts create workforce-viewer --project=$ProjectId --display-name='Workforce read-only dashboard'
Invoke-Gcloud storage buckets add-iam-policy-binding "gs://$Bucket" --member="serviceAccount:$serviceAccount" --role=roles/storage.objectViewer
Invoke-Gcloud storage cp --recursive artifacts/full "gs://$Bucket/releases/$ArtifactTag/"
Invoke-Gcloud storage cp data/manifest.json "gs://$Bucket/releases/$ArtifactTag/manifest.json"
Invoke-Bq --project_id=$ProjectId --location=$Region mk --dataset workforce
# Separate versioned tables avoid overwriting existing forecast records.
$tableTag = $ArtifactTag.Replace('-', '_')
Invoke-Bq --project_id=$ProjectId --location=$Region load --source_format=PARQUET "workforce.daily_$tableTag" "gs://$Bucket/releases/$ArtifactTag/full/daily.parquet"
Invoke-Bq --project_id=$ProjectId --location=$Region load --source_format=PARQUET "workforce.forecasts_$tableTag" "gs://$Bucket/releases/$ArtifactTag/full/test_forecasts.parquet"
Invoke-Bq --project_id=$ProjectId --location=$Region load --source_format=PARQUET "workforce.outcomes_$tableTag" "gs://$Bucket/releases/$ArtifactTag/full/test_outcomes.parquet"
Invoke-Gcloud builds submit --tag=$image --project=$ProjectId .
Invoke-Gcloud run deploy $Service --project=$ProjectId --region=$Region --image=$image --service-account=$serviceAccount --no-allow-unauthenticated --execution-environment=gen2 --memory=1Gi --cpu=1 --min=0 --max=1 --concurrency=10 --timeout=3600 --port=8080 --add-volume="mount-path=/mnt/artifacts,type=cloud-storage,bucket=$Bucket,readonly=true" --set-env-vars="WORKFORCE_ARTIFACTS=/mnt/artifacts/releases/$ArtifactTag/full"
Write-Output 'Deployment command completed. Validate authenticated access, WebSocket reconnects, mounts, charts, downloads, and BigQuery metrics before claiming verified deployment.'
