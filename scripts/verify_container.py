"""Linux Docker smoke verification. This is NOT Cloud Run deployment evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def docker(*args, check=True):
    result = subprocess.run(["docker", *map(str, args)], text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result

def main():
    image = os.environ.get("WORKFORCE_TEST_IMAGE", "workforce:test")
    spec = importlib.util.spec_from_file_location("prepare", ROOT / "cloud/prepare.py")
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        stage, output = root / "stage", root / "output"
        output.mkdir()
        plan = prepare.prepare(stage)
        prefix = plan["input_prefix"]
        # Match the host's nonroot UID only for the disposable writable bind mount.
        job_args = ["run", "--rm", "--memory=1g", "--cpus=1", "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{stage / 'inputs'}:/inputs:ro", "-v", f"{output}:/outputs",
            "-e", f"INPUT_PREFIX={prefix}", "-e", f"INPUT_MANIFEST_SHA256={plan['input_manifest_sha256']}",
            "-e", "CLOUD_RUN_EXECUTION=container-smoke", "--entrypoint", "python", image,
            "-m", "workforce.cloud_job", "--input-dir=/inputs", "--output-dir=/outputs"]
        first = docker(*job_args)
        before = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in output.rglob("*") if p.is_file()}
        docker(*job_args)
        after = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in output.rglob("*") if p.is_file()}
        assert before == after and len(list(output.rglob("predictions.parquet"))) == 1
        failed_args = [a.replace(f"INPUT_PREFIX={prefix}", "INPUT_PREFIX=tests/intentionally-missing") for a in job_args]
        failure = docker(*failed_args, check=False)
        assert failure.returncode == 1 and '"error_type": "FileNotFoundError"' in failure.stdout
        release = stage / "dashboard" / prefix
        env = {"WORKFORCE_RELEASE_ROOT": "/mnt/release", "WORKFORCE_ARTIFACTS": "/mnt/release/full",
               "DATASET_VERSION": plan["dataset_version"], "DASHBOARD_RELEASE_PREFIX": prefix,
               "DASHBOARD_MANIFEST_SHA256": hashlib.sha256((release / "inventory.json").read_bytes()).hexdigest(),
               "PORT": "8080"}
        args = ["run", "--detach", "--memory=1g", "--cpus=1", "-p", "127.0.0.1:8877:8080",
                "-v", f"{release}:/mnt/release:ro"]
        for key, value in env.items():
            args += ["-e", f"{key}={value}"]
        container = docker(*args, "--entrypoint", "python", image, "-m", "workforce.cloud_dashboard").stdout.strip()
        healthy = False
        try:
            for _ in range(40):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8877/_stcore/health", timeout=3) as response:
                        healthy = response.read() == b"ok"
                    if healthy:
                        break
                except OSError:
                    time.sleep(1)
            logs = docker("logs", container)
            assert healthy, logs.stdout + logs.stderr
            assert '"mount_read_only": true' in logs.stdout
            print(logs.stdout)
        finally:
            docker("rm", "--force", container)
        print(first.stdout)
        print(failure.stdout)
        print(json.dumps({"environment": "GitHub Actions Linux Docker, not GCP",
                          "dashboard_health": healthy, "read_only_mount": True,
                          "batch_retry_unchanged": before == after, "controlled_failure_exit": failure.returncode,
                          "output_files": len(after)}, indent=2))

if __name__ == "__main__":
    main()
