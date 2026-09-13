# Demo cleanup and cost controls

These instructions target only **`workforce-replay-yv-260913`**. Check [verification status](GCP_VERIFICATION.md) for which resources actually exist. At the preparation checkpoint only the empty project exists; do not infer that every resource below was created.

Before cleanup, save sanitized execution/query evidence and download any results you want to keep. Deletion stops future use but does not undo charges already incurred. Billing reports can lag. Close dashboard tabs after use: an open Streamlit WebSocket keeps the instance active.

## Stop public access or compute

To make an already-public dashboard authenticated again:

```powershell
gcloud run services remove-iam-policy-binding workforce-replay --project=workforce-replay-yv-260913 --region=us-central1 --member=allUsers --role=roles/run.invoker
```

This does not delete the service or stop authenticated usage. To remove the demo compute resources completely, first inspect active job executions and wait for or cancel any running execution, then:

```powershell
gcloud run services delete workforce-replay --project=workforce-replay-yv-260913 --region=us-central1
gcloud run jobs delete workforce-replay-batch --project=workforce-replay-yv-260913 --region=us-central1
```

No scheduler is part of this deployment. Leaving a job definition idle consumes no running-job compute; executions and stored results are separate resources.

## Remove stored resources

The following deletes the named demo data and images. Inspect each target and retain necessary evidence first. The Git repository's original artifacts remain independent of these cloud deletions.

```powershell
gcloud storage ls --all-versions gs://workforce-replay-yv-260913-wf-view/**
gcloud storage ls --all-versions gs://workforce-replay-yv-260913-wf-input/**
gcloud storage ls --all-versions gs://workforce-replay-yv-260913-wf-output/**
gcloud storage ls --all-versions gs://workforce-replay-yv-260913-wf-build/**

gcloud storage rm --recursive gs://workforce-replay-yv-260913-wf-view
gcloud storage rm --recursive gs://workforce-replay-yv-260913-wf-input
gcloud storage rm --recursive gs://workforce-replay-yv-260913-wf-output
gcloud storage rm --recursive gs://workforce-replay-yv-260913-wf-build

bq --project_id=workforce-replay-yv-260913 rm --recursive --dataset workforce_demo
gcloud artifacts repositories delete workforce --project=workforce-replay-yv-260913 --location=us-central1
```

Bucket recursive removal includes object versions; retained/soft-deleted objects may remain billable until their configured retention ends. The preparation policy keeps live releases and expires superseded generations after seven days. Dataset tables are configured to expire 30 days after creation; that is not a general cleanup of other services. Cloud Logging may retain existing logs for its configured retention period. Built images do not disappear when a Cloud Run service is deleted.

After workloads and build use are gone, remove the dedicated user-managed identities:

```powershell
gcloud iam service-accounts delete workforce-viewer@workforce-replay-yv-260913.iam.gserviceaccount.com --project=workforce-replay-yv-260913
gcloud iam service-accounts delete workforce-runner@workforce-replay-yv-260913.iam.gserviceaccount.com --project=workforce-replay-yv-260913
gcloud iam service-accounts delete workforce-builder@workforce-replay-yv-260913.iam.gserviceaccount.com --project=workforce-replay-yv-260913
```

Review Billing → Reports with the project filter after cleanup. Remove the project's budget if no longer useful; retain other projects' budgets and payment settings. Do not delete the billing account merely to clean up this demonstration.

## Dedicated-project alternative

If this project still contains only this portfolio demo and all evidence has been saved, deleting the entire dedicated project is the broad cleanup alternative:

```powershell
gcloud projects describe workforce-replay-yv-260913
gcloud projects delete workforce-replay-yv-260913
```

Review the confirmation in Google Cloud before proceeding. Never substitute either pre-existing starter project. Project shutdown is not instant invoice settlement; review Google's recovery/retention rules and final charges.

Official references: [Cloud Storage rm](https://docs.cloud.google.com/sdk/gcloud/reference/storage/rm), [Cloud Run service deletion](https://docs.cloud.google.com/run/docs/managing/services), [project shutdown](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects), [soft delete](https://docs.cloud.google.com/storage/docs/soft-delete), [budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets).
