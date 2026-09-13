param(
  [Parameter(Mandatory=$true)][ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')][string]$ProjectId,
  [Parameter(Mandatory=$true)][string]$Stage,
  [ValidateSet('Infrastructure','Build','Deploy','Job','FailureTest')][string]$Phase = 'Infrastructure',
  [string]$Region = 'us-central1',
  [string]$ImageTag = 'cloud-v1',
  [string]$ImageDigest,
  [string]$Gcloud = 'gcloud',
  [string]$Bq = 'bq',
  [switch]$Public,
  [switch]$Execute,
  [switch]$BudgetConfirmed
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$plan = Get-Content -LiteralPath (Join-Path $Stage 'plan.json') -Raw | ConvertFrom-Json
$viewBucket = "$ProjectId-wf-view"
$inputBucket = "$ProjectId-wf-input"
$outputBucket = "$ProjectId-wf-output"
$buildBucket = "$ProjectId-wf-build"
$viewer = "workforce-viewer@$ProjectId.iam.gserviceaccount.com"
$runner = "workforce-runner@$ProjectId.iam.gserviceaccount.com"
$builder = "workforce-builder@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/workforce/runtime:$ImageTag"
$dataset = $plan.dataset_version
$release = $plan.input_prefix
$manifestPath = Join-Path $Stage "dashboard/$release/inventory.json"
$viewHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLower()
if (-not $Execute) {
  [pscustomobject]@{Mode='PREVIEW'; Phase=$Phase; Project=$ProjectId; Region=$Region;
    Dashboard='workforce-replay'; Job='workforce-replay-batch'; Public=$Public.IsPresent;
    Buckets=@($viewBucket,$inputBucket,$outputBucket,$buildBucket); Image=$image;
    Dataset=$dataset; UploadBytes=$plan.upload_bytes} | ConvertTo-Json
  exit 0
}
if (-not $BudgetConfirmed) { throw 'Explicit spending authorization is required.' }
function GC { & $Gcloud @args; if ($LASTEXITCODE -ne 0) { throw "gcloud command failed: $args" } }
function BQ { & $Bq @args; if ($LASTEXITCODE -ne 0) { throw "bq command failed: $args" } }
function Ensure-Resource([string[]]$Describe, [string[]]$Create) {
  $read = & $Gcloud @Describe 2>&1
  if ($LASTEXITCODE -eq 0) { return }
  if (($read -join "`n") -notmatch 'NOT_FOUND|not found|does not exist|404') {
    throw "Resource inspection failed; refusing to assume absence: $read"
  }
  GC @Create
}
$billing = GC billing projects describe $ProjectId --format=json | ConvertFrom-Json
if (-not $billing.billingEnabled) { throw 'Billing is not enabled for the selected project.' }
$project = GC projects describe $ProjectId --format=json | ConvertFrom-Json
if ($project.labels.portfolio -ne 'workforce') { throw 'Use the dedicated project labeled portfolio=workforce; inspect other projects manually.' }
Set-Location -LiteralPath $repoRoot
switch ($Phase) {
  Infrastructure {
    GC services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com bigquery.googleapis.com iam.googleapis.com logging.googleapis.com --project=$ProjectId
    foreach ($bucket in @($viewBucket,$inputBucket,$outputBucket,$buildBucket)) {
      Ensure-Resource @('storage','buckets','describe',"gs://$bucket",'--format=json') @('storage','buckets','create',"gs://$bucket","--project=$ProjectId","--location=$Region",'--uniform-bucket-level-access','--public-access-prevention','--default-storage-class=STANDARD')
      GC storage buckets update "gs://$bucket" --versioning --lifecycle-file=cloud/retention.json
    }
    foreach ($name in @('workforce-viewer','workforce-runner','workforce-builder')) {
      Ensure-Resource @('iam','service-accounts','describe',"$name@$ProjectId.iam.gserviceaccount.com","--project=$ProjectId") @('iam','service-accounts','create',$name,"--project=$ProjectId")
    }
    Ensure-Resource @('artifacts','repositories','describe','workforce',"--location=$Region","--project=$ProjectId") @('artifacts','repositories','create','workforce','--repository-format=docker',"--location=$Region","--project=$ProjectId")
    GC storage buckets add-iam-policy-binding "gs://$viewBucket" --member="serviceAccount:$viewer" --role=roles/storage.objectViewer
    GC storage buckets add-iam-policy-binding "gs://$inputBucket" --member="serviceAccount:$runner" --role=roles/storage.objectViewer
    GC storage buckets add-iam-policy-binding "gs://$outputBucket" --member="serviceAccount:$runner" --role=roles/storage.objectViewer
    GC storage buckets add-iam-policy-binding "gs://$outputBucket" --member="serviceAccount:$runner" --role=roles/storage.objectCreator
    GC storage buckets add-iam-policy-binding "gs://$buildBucket" --member="serviceAccount:$builder" --role=roles/storage.objectViewer
    GC artifacts repositories add-iam-policy-binding workforce --location=$Region --project=$ProjectId --member="serviceAccount:$builder" --role=roles/artifactregistry.writer
    GC projects add-iam-policy-binding $ProjectId --member="serviceAccount:$builder" --role=roles/logging.logWriter --condition=None
    $datasets = BQ --project_id=$ProjectId --format=json ls | ConvertFrom-Json
    if ('workforce_demo' -notin @($datasets | ForEach-Object {$_.datasetReference.datasetId})) {
      BQ --project_id=$ProjectId --location=$Region mk --dataset --default_table_expiration=2592000 workforce_demo
    }
    Write-Output 'Infrastructure created. Upload verified artifacts and load/reconcile BigQuery before deploying.'
  }
  Build {
    GC builds submit . --project=$ProjectId --region=$Region --config=cloud/cloudbuild.yaml --substitutions="_IMAGE=$image" --service-account="projects/$ProjectId/serviceAccounts/$builder" --gcs-source-staging-dir="gs://$buildBucket/source" --timeout=1200 --format=json
  }
  Deploy {
    if ($ImageDigest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Deploy the verified build digest, not a mutable tag.' }
    $pinned = "$Region-docker.pkg.dev/$ProjectId/workforce/runtime@$ImageDigest"
    $serviceEnv = "WORKFORCE_RELEASE_ROOT=/mnt/release,WORKFORCE_ARTIFACTS=/mnt/release/full,DATASET_VERSION=$dataset,DASHBOARD_RELEASE_PREFIX=$release,DASHBOARD_MANIFEST_SHA256=$viewHash"
    GC run deploy workforce-replay --project=$ProjectId --region=$Region --image=$pinned --service-account=$viewer --no-allow-unauthenticated --execution-environment=gen2 --memory=1Gi --cpu=1 --cpu-throttling --min=0 --max=1 --concurrency=10 --timeout=3600 --session-affinity --port=8080 --command=python '--args=-m,workforce.cloud_dashboard' --add-volume="mount-path=/mnt/release,type=cloud-storage,bucket=$viewBucket,readonly=true,mount-options=only-dir=$release" --set-env-vars=$serviceEnv --labels=portfolio=workforce
    if ($Public) {
      GC run services add-iam-policy-binding workforce-replay --project=$ProjectId --region=$Region --member=allUsers --role=roles/run.invoker
    }
    $jobEnv = "INPUT_BUCKET=$inputBucket,OUTPUT_BUCKET=$outputBucket,INPUT_PREFIX=$release,INPUT_MANIFEST_SHA256=$($plan.input_manifest_sha256),ORIGIN=2026-03-24,ASOF=2026-03-31,OUTPUT_PREFIX=runs"
    GC run jobs deploy workforce-replay-batch --project=$ProjectId --region=$Region --image=$pinned --service-account=$runner --memory=1Gi --cpu=1 --tasks=1 --parallelism=1 --max-retries=1 --task-timeout=600 --command=python '--args=-m,workforce.cloud_job' --set-env-vars=$jobEnv --labels=portfolio=workforce
  }
  Job {
    GC run jobs execute workforce-replay-batch --project=$ProjectId --region=$Region --wait --format=json
  }
  FailureTest {
    # Overrides apply only to this execution, leaving the saved job configuration intact.
    & $Gcloud run jobs execute workforce-replay-batch --project=$ProjectId --region=$Region --update-env-vars='INPUT_PREFIX=tests/intentionally-missing,OUTPUT_PREFIX=tests/missing-input' --task-timeout=120 --wait --format=json
    if ($LASTEXITCODE -eq 0) { throw 'The controlled missing-input execution unexpectedly succeeded.' }
    Write-Output 'Execution failed as expected. Inspect its status and replay_failed logs; failure alone does not prove the intended cause.'
  }
}
