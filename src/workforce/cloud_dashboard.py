"""Verify the mounted dashboard release before starting Streamlit on Cloud Run."""
import json
import os
import sys
from pathlib import Path
from .cloud_job import digest, safe_key


def verify_mount():
    root = Path(os.environ["WORKFORCE_RELEASE_ROOT"])
    payload = (root / "inventory.json").read_bytes()
    if digest(payload) != os.environ["DASHBOARD_MANIFEST_SHA256"]:
        raise ValueError("Dashboard manifest checksum mismatch")
    prefix = os.environ["DASHBOARD_RELEASE_PREFIX"].rstrip("/") + "/"
    entries = json.loads(payload)["files"]
    for item in entries:
        name = safe_key(item["path"])
        if not name.startswith(prefix):
            raise ValueError("Unexpected dashboard object path")
        data = (root / name[len(prefix):]).read_bytes()
        if digest(data) != item["sha256"] or len(data) != item["bytes"]:
            raise ValueError("Dashboard artifact checksum mismatch: " + name)
    # Cloud Run's read-only CSI mount exposes ST_RDONLY. No test file is created.
    read_only = bool(os.statvfs(root).f_flag & os.ST_RDONLY)
    if not read_only:
        raise ValueError("Dashboard artifact mount is not read-only")
    print(json.dumps({"severity": "INFO", "event": "dashboard_artifacts_verified",
                      "dataset_version": os.environ["DATASET_VERSION"],
                      "model_version": json.loads((root / "full/models/metadata.json").read_text())["version"],
                      "verified_files": len(entries), "mount_read_only": read_only}), flush=True)


def main():
    try:
        verify_mount()
    except Exception as exc:
        print(json.dumps({"severity": "ERROR", "event": "dashboard_startup_failed",
                          "error_type": type(exc).__name__, "message": str(exc)[:500]}), flush=True)
        return 1
    os.execv(sys.executable, [sys.executable, "-m", "streamlit", "run", "/app/app.py",
             "--server.address=0.0.0.0", "--server.port=" + os.environ.get("PORT", "8080"),
             "--server.headless=true"])

if __name__ == "__main__":
    sys.exit(main())
