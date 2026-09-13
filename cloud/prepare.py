"""Stage minimal verified cloud inputs; preserve all original evidence bytes."""
import argparse
import json
import re
import shutil
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from workforce.cloud_job import INPUT_FILES, digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
DATASET_VERSION = "cms-ny50-c1b7f9939a74d3d1-v1"
DATES = {"date", "origin", "target_end", "training_cutoff", "calibration_target_end"}
DASHBOARD_FILES = ["daily.parquet", "facilities.parquet", "test_forecasts.parquet", "evaluation.parquet",
                   "quality.json", "models/metadata.json", "backtest_summary.json", "monitoring.json",
                   "monitoring_demo.json", "reports/facility_metrics.csv", "reports/test_metrics.csv",
                   "reports/volume_metrics.csv", "reports/representative_failures.csv", "reports/quarter_coverage.csv",
                   "forecasts/c1b7f9939a74d3d1/2026-03-24.parquet", "forecasts/c1b7f9939a74d3d1/2026-03-31.parquet"]

def entry(path, name):
    data = path.read_bytes()
    return {"path": name, "bytes": len(data), "sha256": digest(data)}

def table_for_bigquery(frame, version=DATASET_VERSION):
    frame = frame.copy()
    if not frame.facility.map(lambda v: isinstance(v, str) and bool(re.fullmatch(r"\d{6}", v))).all():
        raise ValueError("Facility IDs must retain six-character strings")
    frame["dataset_version"] = version
    table = pa.Table.from_pandas(frame, preserve_index=False)
    for name in table.column_names:
        if name in DATES:
            table = table.set_column(table.schema.get_field_index(name), name, table.column(name).cast(pa.date32(), safe=True))
    return table.replace_schema_metadata(None)

def prepare(destination):
    destination = Path(destination).resolve()
    if destination == ROOT or destination.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Staging must not replace frozen evidence")
    destination.mkdir(parents=True, exist_ok=True)
    for item in json.loads((ROOT / "artifacts/bundle_checksums.json").read_text())["files"]:
        assert entry(ROOT / item["path"], item["path"]) == item, f"Changed evidence: {item['path']}"
    release, run = f"releases/{DATASET_VERSION}", ROOT / "artifacts/full"
    for group, names in (("dashboard", DASHBOARD_FILES), ("inputs", INPUT_FILES)):
        for name in names:
            target = destination / group / release / "full" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run / name, target)
    manifest = {"dataset_version": DATASET_VERSION, "historical_replay": True,
                "files": [entry(run / name, name) for name in INPUT_FILES],
                "source_manifest_sha256": digest((ROOT / "data/manifest.json").read_bytes())}
    manifest_data = json_bytes(manifest)
    (destination / "inputs" / release / "job-input.json").write_bytes(manifest_data)
    exports = []
    for name, source, keys in (("daily", "daily", ["facility", "date"]),
                               ("forecasts", "test_forecasts", ["facility", "origin", "model_version"]),
                               ("outcomes", "test_outcomes", ["facility", "origin"])):
        frame = pd.read_parquet(run / (source + ".parquet"))
        if frame.duplicated(keys).any():
            raise ValueError(f"Duplicate {name} keys")
        table = table_for_bigquery(frame.sort_values(keys).reset_index(drop=True))
        relative = f"{release}/bigquery/{name}.parquet"
        target = destination / "inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, target, compression="snappy", version="2.6")
        exports.append({**entry(target, relative), "table": name, "rows": len(frame),
                        "schema": [{"name": f.name, "type": str(f.type)} for f in table.schema]})
    for group in ("dashboard", "inputs"):
        shutil.copyfile(ROOT / "data/manifest.json", destination / group / release / "source-manifest.json")
        inventory = [entry(p, p.relative_to(destination / group).as_posix())
                     for p in sorted((destination / group / release).rglob("*"))
                     if p.is_file() and p.name != "inventory.json"]
        (destination / group / release / "inventory.json").write_bytes(json_bytes({"files": inventory}))
    result = {"dataset_version": DATASET_VERSION, "input_prefix": release,
              "input_manifest_sha256": digest(manifest_data), "bigquery_exports": exports,
              "dashboard_files": len(DASHBOARD_FILES),
              "upload_bytes": sum(p.stat().st_size for p in destination.rglob("*") if p.is_file() and p.name != "plan.json")}
    (destination / "plan.json").write_bytes(json_bytes(result))
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    result = prepare(parser.parse_args().destination)
    print(json.dumps({k: v for k, v in result.items() if k != "bigquery_exports"}, indent=2))
