"""Upload staged release bytes once, rejecting conflicting existing objects."""
import argparse
from pathlib import Path
from bigquery import access_token
from workforce.cloud_job import GCSStore, json_bytes

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", type=Path, required=True)
    p.add_argument("--dashboard-bucket", required=True)
    p.add_argument("--input-bucket", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    args = p.parse_args()
    token, receipt = access_token(), []
    for group, bucket in (("dashboard", args.dashboard_bucket), ("inputs", args.input_bucket)):
        store = GCSStore(bucket, token=token)
        root = args.stage / group
        files = sorted(path for path in root.rglob("*") if path.is_file())
        # Publish manifests last so a partial upload cannot appear complete.
        files.sort(key=lambda path: path.name in ("job-input.json", "inventory.json"))
        for path in files:
            key, payload = path.relative_to(root).as_posix(), path.read_bytes()
            item = store.create(key, payload)
            if store.get(key) != payload:
                raise ValueError("Uploaded object read-back differs: " + key)
            receipt.append({"bucket": bucket, **item, "read_back_verified": True})
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_bytes(json_bytes(receipt))
    print(f"Verified {len(receipt)} cloud objects by reading their bytes back")

if __name__ == "__main__":
    main()
