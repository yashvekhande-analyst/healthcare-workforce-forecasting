"""Bounded historical prediction/evaluation; never trains or updates the model.

Cloud credentials come from the attached Cloud Run service identity. Local tests
use the same calculation with a filesystem store and need no cloud credentials.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .metrics import metrics
from .modeling import forecast_frame, load_bundle
from .predict import features_at
from .storage import attach_actuals

CONTRACT_VERSION = "cloud-replay-v1"
INPUT_FILES = ("daily.parquet", "features.parquet", "models/metadata.json", "models/bundle.joblib")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def safe_key(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("Invalid object key")
    return value


class LocalStore:
    def __init__(self, root):
        self.root = Path(root)

    def get(self, key):
        return (self.root / safe_key(key)).read_bytes()

    def create(self, key, data):
        path = self.root / safe_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as output:
                output.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f"Conflicting immutable object: {key}") from None
        return {"key": key, "sha256": digest(data), "bytes": len(data)}


class GCSStore:
    """Small-object JSON API adapter with bounded retries and exclusive writes."""
    def __init__(self, bucket, token=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket):
            raise ValueError("Invalid bucket name")
        self.bucket = bucket
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "POST"])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        if token is None:
            response = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"}, timeout=10)
            response.raise_for_status()
            token = response.json()["access_token"]
        self.session.headers["Authorization"] = "Bearer " + token

    def get(self, key):
        safe_key(key)
        url = f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{quote(key, safe='')}"
        response = self.session.get(url, params={"alt": "media"}, timeout=60)
        if response.status_code == 404:
            raise FileNotFoundError(f"Missing input/object: gs://{self.bucket}/{key}")
        if not response.ok:
            raise RuntimeError(f"GCS read failed HTTP {response.status_code}: {key}")
        return response.content

    def create(self, key, data):
        safe_key(key)
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o"
        response = self.session.post(url, params={"uploadType": "media", "name": key,
                                                "ifGenerationMatch": "0"}, data=data,
                                     headers={"Content-Type": "application/octet-stream"}, timeout=60)
        if response.status_code == 412:
            if self.get(key) != data:
                raise ValueError(f"Conflicting immutable object: gs://{self.bucket}/{key}")
        elif not response.ok:
            raise RuntimeError(f"GCS create failed HTTP {response.status_code}: {key}")
        result = {"key": key, "sha256": digest(data), "bytes": len(data)}
        if response.ok:
            result["generation"] = response.json()["generation"]
        return result


def read_inputs(store, prefix, expected_manifest_sha256, target):
    manifest_data = store.get(safe_key(prefix + "/job-input.json"))
    if digest(manifest_data) != expected_manifest_sha256:
        raise ValueError("Input manifest checksum mismatch")
    manifest = json.loads(manifest_data)
    entries = {item["path"]: item for item in manifest["files"]}
    if set(entries) != set(INPUT_FILES) or len(manifest["files"]) != len(INPUT_FILES):
        raise ValueError("Unexpected or duplicate job inputs")
    for name in INPUT_FILES:
        data = store.get(safe_key(prefix + "/full/" + name))
        if digest(data) != entries[name]["sha256"] or len(data) != entries[name]["bytes"]:
            raise ValueError(f"Input checksum mismatch: {name}")
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return manifest


def calculate(run, origin, asof, dataset_version, input_manifest_sha256):
    origin_date, asof_date = pd.Timestamp(origin), pd.Timestamp(asof)
    if origin_date.time().isoformat() != "00:00:00" or asof_date.time().isoformat() != "00:00:00":
        raise ValueError("Origin and as-of must be dates")
    daily = pd.read_parquet(run / "daily.parquet")
    bundle = load_bundle(run)
    if origin_date < pd.Timestamp(bundle["metadata"]["valid_from"]):
        raise ValueError("Model was not available at origin")
    if origin_date + pd.Timedelta(days=7) > asof_date or asof_date > daily.date.max():
        raise ValueError("Historical replay requires seven later outcome days within the saved data")
    if daily.duplicated(["facility", "date"]).any():
        raise ValueError("Duplicate daily observation keys")
    # This existing function truncates daily data BEFORE executing feature SQL.
    features = features_at(daily, origin_date)
    if features.empty:
        raise ValueError("No eligible facilities at origin")
    prediction = forecast_frame(features, bundle, bundle["metadata"]["selected_model"], "cloud_replay")
    identifiers = {"contract": CONTRACT_VERSION, "dataset_version": dataset_version,
                   "input_manifest_sha256": input_manifest_sha256, "origin": str(origin_date.date()),
                   "asof": str(asof_date.date()), "model_version": prediction.model_version.iloc[0]}
    artifact_id = digest(json_bytes(identifiers))[:24]
    prediction["dataset_version"], prediction["artifact_id"] = dataset_version, artifact_id
    prediction = prediction.sort_values(["facility", "origin"]).reset_index(drop=True)
    # Future labels are read only after forecasts exist, by the separate evaluator.
    labels = pd.read_parquet(run / "features.parquet")
    realized = attach_actuals(prediction, labels, asof_date)
    actuals = realized[["facility", "origin", "target_end", "actual", "dataset_version", "artifact_id"]]
    known = realized.dropna(subset=["actual"])
    if known.empty:
        raise ValueError("No eligible actual outcomes")
    score = metrics(known.actual, known.prediction, known.lower, known.upper)
    report = {**identifiers, "artifact_id": artifact_id, "historical_replay": True,
              "prediction_input_max_date": str(daily.loc[daily.date <= origin_date, "date"].max().date()),
              "issued_forecasts": len(prediction), "evaluable_forecasts": len(known),
              "withheld_facilities": int(daily.facility.nunique() - len(prediction)),
              "unknown_outcomes": int(realized.actual.isna().sum()), "metrics": score,
              "monitoring": {"coverage_below_80_percent": score["coverage"] < .8,
                             "incomplete_forecast_cohort": len(prediction) < daily.facility.nunique()},
              "availability_assumption": "Historical replay with daily internal feed through origin; CMS publishes quarterly"}
    return prediction, actuals, report


def publish_result(store, prediction, actuals, report, execution, attempt=0, output_root="runs"):
    prefix = safe_key(f"{output_root}/{report['dataset_version']}/{report['artifact_id']}")
    objects = []
    for name, frame in (("predictions", prediction), ("actuals", actuals)):
        buffer = io.BytesIO()
        frame.to_parquet(buffer, index=False)
        objects.append(store.create(prefix + f"/{name}.parquet", buffer.getvalue()))
    # Report is the completion marker; consumers must require it before reading.
    objects.append(store.create(prefix + "/report.json", json_bytes(report)))
    receipt = {"execution": execution, "attempt": attempt, "artifact_id": report["artifact_id"],
               "objects": [{k: v for k, v in item.items() if k != "generation"} for item in objects],
               "status": "success"}
    store.create(safe_key(f"{output_root}/executions/{execution}/attempt-{attempt}.json"), json_bytes(receipt))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, help="Local test store instead of GCS")
    parser.add_argument("--output-dir", type=Path, help="Local test store instead of GCS")
    args = parser.parse_args(argv)
    execution = os.environ.get("CLOUD_RUN_EXECUTION", "local-replay")
    context = {"execution": execution, "attempt": int(os.environ.get("CLOUD_RUN_TASK_ATTEMPT", "0"))}
    try:
        input_store = LocalStore(args.input_dir) if args.input_dir else GCSStore(os.environ["INPUT_BUCKET"])
        output_store = LocalStore(args.output_dir) if args.output_dir else GCSStore(os.environ["OUTPUT_BUCKET"])
        expected = os.environ["INPUT_MANIFEST_SHA256"]
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            manifest = read_inputs(input_store, os.environ["INPUT_PREFIX"], expected, run)
            prediction, actuals, report = calculate(run, os.environ.get("ORIGIN", "2026-03-24"),
                                                   os.environ.get("ASOF", "2026-03-31"),
                                                   manifest["dataset_version"], expected)
            receipt = publish_result(output_store, prediction, actuals, report, **context,
                                     output_root=os.environ.get("OUTPUT_PREFIX", "runs"))
        print(json.dumps({"severity": "INFO", "event": "replay_success", **context,
                          "artifact_id": report["artifact_id"], "issued": len(prediction),
                          "evaluable": report["evaluable_forecasts"], "metrics": report["metrics"],
                          "output_keys": [item["key"] for item in receipt["objects"]]}, allow_nan=False), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"severity": "ERROR", "event": "replay_failed", **context,
                          "error_type": type(exc).__name__, "message": str(exc)[:1000]}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
