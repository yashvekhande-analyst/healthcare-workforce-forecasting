"""Cloud contracts checked locally; these do not claim deployed IAM or runtime QA."""
import importlib.util
import json
import shutil
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pytest
from workforce import cloud_job as job

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "artifacts/full"

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "cloud" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

@pytest.fixture
def copied_inputs(scratch):
    for name in job.INPUT_FILES:
        target = scratch / "input" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUN / name, target)
    return scratch / "input"

def test_cloud_replay_matches_frozen_forecasts_and_future_mutation(copied_inputs):
    pred, actuals, report = job.calculate(copied_inputs, "2026-03-24", "2026-03-31", "test-v1", "a" * 64)
    expected = pd.read_parquet(RUN / "forecasts/c1b7f9939a74d3d1/2026-03-24.parquet").sort_values("facility").reset_index(drop=True)
    # Parquet round-tripping changes datetime resolution, not the represented dates.
    pd.testing.assert_frame_equal(pred[expected.columns].drop(columns="split"), expected.drop(columns="split"),
                                  check_dtype=False, check_exact=True)
    assert len(pred) == len(actuals) == report["evaluable_forecasts"] == 49
    assert "actual" not in pred and "prediction" not in actuals
    daily = pd.read_parquet(copied_inputs / "daily.parquet")
    later = daily.date > pd.Timestamp("2026-03-24")
    daily.loc[later, ["contract_hours", "employee_hours", "census"]] = 1e8
    daily.to_parquet(copied_inputs / "daily.parquet", index=False)
    changed, _, _ = job.calculate(copied_inputs, "2026-03-24", "2026-03-31", "test-v1", "a" * 64)
    pd.testing.assert_frame_equal(pred, changed, check_exact=True)

def test_retry_reuses_artifact_and_conflicts_fail(copied_inputs, scratch):
    pred, actuals, report = job.calculate(copied_inputs, "2026-03-24", "2026-03-31", "test-v1", "a" * 64)
    store = job.LocalStore(scratch / "output")
    one = job.publish_result(store, pred, actuals, report, "execution-one")
    two = job.publish_result(store, pred, actuals, report, "execution-one", attempt=1)
    three = job.publish_result(store, pred, actuals, report, "execution-two")
    assert one["artifact_id"] == two["artifact_id"] == three["artifact_id"]
    assert len(list((scratch / "output").rglob("predictions.parquet"))) == 1
    pred.loc[0, "prediction"] += 1
    with pytest.raises(ValueError, match="Conflicting immutable"):
        job.publish_result(store, pred, actuals, report, "execution-conflict")

def test_input_checksum_prevents_untrusted_model_load(scratch):
    stage = module("prepare").prepare(scratch / "stage")
    store = job.LocalStore(scratch / "stage/inputs")
    target = scratch / "verified"
    job.read_inputs(store, stage["input_prefix"], stage["input_manifest_sha256"], target)
    model = scratch / "stage/inputs" / stage["input_prefix"] / "full/models/bundle.joblib"
    model.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        job.read_inputs(store, stage["input_prefix"], stage["input_manifest_sha256"], target)

def test_missing_input_returns_structured_failure(scratch, monkeypatch, capsys):
    # Local sandbox uses a readable scratch directory; Linux Cloud Run uses /tmp.
    from contextlib import contextmanager
    @contextmanager
    def temp():
        yield str(scratch / "temp")
    monkeypatch.setattr(job.tempfile, "TemporaryDirectory", temp)
    monkeypatch.setenv("INPUT_PREFIX", "tests/intentionally-missing")
    monkeypatch.setenv("INPUT_MANIFEST_SHA256", "a" * 64)
    code = job.main(["--input-dir", str(scratch / "input"), "--output-dir", str(scratch / "output")])
    event = json.loads(capsys.readouterr().out)
    assert code == 1 and event["event"] == "replay_failed" and event["error_type"] == "FileNotFoundError"
    assert not (scratch / "output").exists()

def test_bigquery_export_types_and_leading_zero():
    table = module("prepare").table_for_bigquery(pd.DataFrame({"facility": ["000123"],
        "origin": pd.to_datetime(["2026-03-24"]), "prediction": [0.0]}))
    assert table.schema.field("facility").type == pa.string()
    assert table.schema.field("origin").type == pa.date32()
    assert table["facility"].to_pylist() == ["000123"]

def test_bigquery_reconciliation_detects_error():
    bq = module("bigquery")
    rows = pd.read_csv(RUN / "reports/test_metrics.csv").to_dict(orient="records")
    for row in rows:
        row.update(issued_forecasts=8667, unknown_outcomes=7)
    assert bq.reconcile(rows)["status"] == "pass"
    rows[0]["mae_hours"] += .01
    with pytest.raises(ValueError, match="Cloud/local mismatch"):
        bq.reconcile(rows)

def test_gcs_retry_uses_generation_precondition_and_detects_conflict():
    class Response:
        status_code, ok = 412, False
    class Session:
        def post(self, url, **kwargs):
            assert kwargs["params"]["ifGenerationMatch"] == "0"
            return Response()
    store = object.__new__(job.GCSStore)
    store.bucket, store.session = "test-output", Session()
    store.get = lambda key: b"saved"
    assert store.create("runs/test/result", b"saved")["sha256"] == job.digest(b"saved")
    with pytest.raises(ValueError, match="Conflicting immutable"):
        store.create("runs/test/result", b"changed")

def test_incomplete_outcomes_and_early_model_rejected(copied_inputs):
    with pytest.raises(ValueError, match="seven later outcome days"):
        job.calculate(copied_inputs, "2026-03-31", "2026-04-07", "v1", "a" * 64)
    with pytest.raises(ValueError, match="Model was not available"):
        job.calculate(copied_inputs, "2025-01-01", "2025-01-08", "v1", "a" * 64)
