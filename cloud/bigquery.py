"""Explicit WRITE_EMPTY loads, bounded queries, and local/cloud reconciliation.

Uses the deployer's normal gcloud login. Tokens stay in process memory; the
dashboard and batch runtime need no BigQuery permissions.
"""
import argparse
import json
import math
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import pandas as pd
import requests
from workforce.cloud_job import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1024 ** 3


def access_token():
    command = [os.environ.get("GCLOUD_EXECUTABLE", "gcloud"), "auth", "print-access-token"]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return result.stdout.strip()


class BigQuery:
    def __init__(self, project, region):
        self.project, self.region = project, region
        self.session = requests.Session()
        self.session.headers["Authorization"] = "Bearer " + access_token()
        self.base = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}"

    def request(self, method, path, **kwargs):
        response = self.session.request(method, self.base + path, timeout=60, **kwargs)
        if not response.ok:
            # Google API error objects contain diagnostics, not Authorization headers.
            raise RuntimeError(f"BigQuery {response.status_code}: {response.text[:1500]}")
        return response.json()

    def job(self, configuration, job_id):
        body = {"jobReference": {"projectId": self.project, "location": self.region, "jobId": job_id},
                "configuration": configuration}
        response = self.session.post(self.base + "/jobs", json=body, timeout=60)
        if response.status_code == 409:
            job = self.request("GET", f"/jobs/{job_id}", params={"location": self.region})
            kind = "load" if "load" in configuration else "query"
            for key, value in configuration[kind].items():
                if job["configuration"][kind].get(key) != value:
                    raise ValueError(f"Existing job configuration differs: {job_id}/{key}")
        elif response.ok:
            job = response.json()
        else:
            raise RuntimeError(f"BigQuery job submission {response.status_code}: {response.text[:1500]}")
        deadline = time.monotonic() + 300
        while job["status"]["state"] != "DONE":
            if time.monotonic() > deadline:
                raise TimeoutError(f"Inspect outstanding BigQuery job {job_id}")
            time.sleep(2)
            job = self.request("GET", f"/jobs/{job_id}", params={"location": self.region})
        if "errorResult" in job["status"]:
            raise RuntimeError(f"BigQuery job {job_id} failed: {job['status']['errorResult']}")
        return job

    def query(self, sql, evidence, name):
        dry = self.request("POST", "/jobs", json={"configuration": {
            "dryRun": True, "query": {"query": sql, "useLegacySql": False,
                                      "maximumBytesBilled": str(MAX_BYTES)}},
            "jobReference": {"projectId": self.project, "location": self.region}})
        estimated = int(dry["statistics"]["totalBytesProcessed"])
        if estimated > MAX_BYTES:
            raise ValueError(f"Query exceeds {MAX_BYTES} bytes: {estimated}")
        job_id = f"workforce_{name}_{uuid.uuid4().hex[:16]}"
        job = self.job({"query": {"query": sql, "useLegacySql": False,
                                   "maximumBytesBilled": str(MAX_BYTES), "useQueryCache": False}}, job_id)
        result = self.request("GET", f"/queries/{job_id}", params={"location": self.region, "maxResults": 100})
        if result.get("pageToken"):
            raise ValueError("Unexpected paginated evaluation result")
        rows = []
        for row in result.get("rows", []):
            parsed = {}
            for field, cell in zip(result["schema"]["fields"], row["f"]):
                value = cell["v"]
                if value is not None and field["type"] in ("INTEGER", "INT64"):
                    value = int(value)
                elif value is not None and field["type"] in ("FLOAT", "FLOAT64", "NUMERIC"):
                    value = float(value)
                parsed[field["name"]] = value
            rows.append(parsed)
        (evidence / (name + ".sql")).write_text(sql, encoding="utf-8")
        (evidence / (name + ".json")).write_bytes(json_bytes({"job_id": job_id,
            "location": self.region, "dry_run_bytes": estimated, "maximum_bytes_billed": MAX_BYTES,
            "statistics": job["statistics"], "rows": rows}))
        return rows


def render(name, project, dataset, tag):
    for value in (project, dataset, tag):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
            raise ValueError("Unsafe SQL identifier")
    return (ROOT / "cloud" / name).read_text().replace("{{PROJECT}}", project).replace("{{DATASET}}", dataset).replace("{{TABLE_TAG}}", tag)


def reconcile(rows):
    expected = pd.read_csv(ROOT / "artifacts/full/reports/test_metrics.csv").set_index("model")
    if len(rows) != 3 or set(row["model"] for row in rows) != set(expected.index):
        raise ValueError("Unexpected model rows")
    differences = []
    for row in rows:
        if (row["issued_forecasts"], row["n"], row["unknown_outcomes"]) != (8667, 8660, 7):
            raise ValueError("Forecast counts changed")
        for metric in ("mae_hours", "wape", "signed_error_hours", "coverage", "mean_width_hours"):
            actual, reference = row[metric], float(expected.loc[row["model"], metric])
            # FLOAT64 reductions may sum in another order across workers.
            if not math.isclose(actual, reference, rel_tol=1e-9, abs_tol=1e-8):
                raise ValueError(f"Cloud/local mismatch: {row['model']}/{metric}: {actual} vs {reference}")
            differences.append({"model": row["model"], "metric": metric, "cloud": actual,
                                "local": reference, "absolute_difference": abs(actual - reference)})
    return {"status": "pass", "relative_tolerance": 1e-9, "absolute_tolerance": 1e-8, "differences": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--dataset", default="workforce_demo")
    parser.add_argument("--table-tag", default="cms_ny50_v1")
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--input-bucket", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--load", action="store_true", help="Use only after billing authorization")
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    plan = json.loads((args.stage / "plan.json").read_text())
    client = BigQuery(args.project, args.region)
    if args.load:
        loads = []
        for item in plan["bigquery_exports"]:
            if digest((args.stage / "inputs" / item["path"]).read_bytes()) != item["sha256"]:
                raise ValueError("Staged export checksum changed")
            table_id = item["table"] + "_" + args.table_tag
            job_id = "workforce_load_" + digest(json_bytes([args.dataset, table_id, item["sha256"]]))[:28]
            config = {"load": {"sourceUris": [f"gs://{args.input_bucket}/{item['path']}"],
                      "sourceFormat": "PARQUET", "writeDisposition": "WRITE_EMPTY",
                      "destinationTable": {"projectId": args.project, "datasetId": args.dataset, "tableId": table_id},
                      "timePartitioning": {"type": "DAY", "field": "date" if item["table"] == "daily" else "origin"}}}
            job = client.job(config, job_id)
            table = client.request("GET", f"/datasets/{args.dataset}/tables/{table_id}")
            if int(table["numRows"]) != item["rows"]:
                raise ValueError(f"Loaded row count mismatch: {table_id}")
            for field in table["schema"]["fields"]:
                if field["name"] in ("facility", "dataset_version", "model", "model_version") and field["type"] != "STRING":
                    raise ValueError("Cloud identifier type mismatch")
                if field["name"] in ("date", "origin", "target_end", "training_cutoff", "calibration_target_end") and field["type"] != "DATE":
                    raise ValueError("Cloud date type mismatch")
            loads.append({"job_id": job_id, "table": table_id, "source_sha256": item["sha256"],
                          "rows": int(table["numRows"]), "schema": table["schema"], "statistics": job["statistics"]})
        (args.evidence / "loads.json").write_bytes(json_bytes(loads))
    integrity = client.query(render("integrity.sql", args.project, args.dataset, args.table_tag), args.evidence, "integrity")
    expected = {"daily_rows": 36500, "reported_days": 36319, "forecast_rows": 26001,
                "outcome_rows": 8667, "known_outcomes": 8660, "duplicate_daily_keys": 0,
                "duplicate_forecast_keys": 0, "duplicate_outcome_keys": 0, "forecasts_without_outcome_row": 0}
    if integrity != [expected]:
        raise ValueError(f"Integrity mismatch: {integrity}")
    rows = client.query(render("evaluation.sql", args.project, args.dataset, args.table_tag), args.evidence, "evaluation")
    verification = reconcile(rows)
    (args.evidence / "reconciliation.json").write_bytes(json_bytes(verification))
    print(json.dumps({"integrity": integrity, "results": rows, "reconciliation": verification["status"]}, indent=2))

if __name__ == "__main__":
    main()
