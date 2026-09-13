"""Upload an explicit, checksummed source archive without temporary directories."""
import argparse
import gzip
import io
import json
import tarfile
from pathlib import Path

from bigquery import access_token
from workforce.cloud_job import GCSStore, digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bucket", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    args = p.parse_args()
    files = [ROOT / name for name in ("Dockerfile", "requirements.lock", "pyproject.toml", "app.py")]
    for directory in ("src", ".streamlit", "artifacts/full"):
        files.extend(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    inventory, raw = [], io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for path in sorted(files):
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise ValueError("Source must stay within the repository")
            name, payload = path.relative_to(ROOT).as_posix(), path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(payload), 0o644, 0
            archive.addfile(info, io.BytesIO(payload))
            inventory.append({"path": name, "sha256": digest(payload), "bytes": len(payload)})
    payload = gzip.compress(raw.getvalue(), mtime=0)
    key = "source/" + digest(payload) + ".tar.gz"
    store = GCSStore(args.bucket, token=access_token())
    receipt = store.create(key, payload)
    if store.get(key) != payload:
        raise ValueError("Source archive read-back mismatch")
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_bytes(json_bytes({"bucket": args.bucket, **receipt, "files": inventory}))
    print(json.dumps({"source": f"gs://{args.bucket}/{key}", "files": len(files), "bytes": len(payload)}))


if __name__ == "__main__":
    main()
