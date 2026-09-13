"""CMS snapshots are immutable; preparation consumes registered raw files only."""
import csv
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CATALOG = "https://data.cms.gov/data.json"
TITLE = "Payroll Based Journal Daily Nurse Staffing"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def get_bytes(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": "WorkforcePortfolio/1.0 public-research"}), timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def manifest(root):
    p = Path(root) / "data" / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"manifest_version": 1, "source": TITLE, "files": [], "transformations": []}


def write_manifest(root, m):
    p = Path(root) / "data" / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2), encoding="utf-8")
    tmp.replace(p)


def register(root, path, url, kind, period=None, state=None, rows=None, columns=None):
    m = manifest(root)
    relative = Path(path).relative_to(root).as_posix()
    entry = dict(path=relative, source_url=url, retrieved_at=now(), sha256=sha256(path),
                 bytes=Path(path).stat().st_size, kind=kind, period=period, state=state,
                 row_count=rows, columns=columns,
                 schema_version="CMS-PBJ-nursing-2023-06-02" if columns else None)
    old = next((e for e in m["files"] if e["path"] == relative), None)
    if old:
        if old["sha256"] != entry["sha256"]:
            raise ValueError(f"Immutable raw file changed: {relative}")
        return old
    m["files"].append(entry)
    write_manifest(root, m)
    return entry


def preserved(root, path, url, kind, period=None, state=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = next((e for e in manifest(root)["files"] if e["path"] == path.relative_to(root).as_posix()), None)
        if old and sha256(path) != old["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
        return path.read_bytes()
    b = get_bytes(url)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_bytes(b)
    tmp.replace(path)
    return b


def fetch(root, start, end, state="NY", national_csv=False):
    root = Path(root)
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    # New catalog snapshots never overwrite previous retrievals.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    catalog_path = raw / f"cms-catalog-{stamp}.json"
    b = preserved(root, catalog_path, CATALOG, "catalog")
    register(root, catalog_path, CATALOG, "catalog")
    dataset = next(d for d in json.loads(b)["dataset"] if d["title"] == TITLE)
    dist = [d for d in dataset["distribution"] if d.get("format") == "CSV"
            and d["temporal"].split("/")[0] <= end and d["temporal"].split("/")[1] >= start]
    dist.sort(key=lambda d: d["temporal"])
    if not dist or dist[0]["temporal"].split("/")[0] > start or dist[-1]["temporal"].split("/")[1] < end:
        raise ValueError("Requested dates are not fully covered by current CMS catalog; supply manual files or change dates")
    resource_url = dist[-1]["resourcesAPI"]
    resource_path = raw / f"resources-{stamp}.json"
    resources = json.loads(preserved(root, resource_path, resource_url, "resources"))
    register(root, resource_path, resource_url, "resources")
    for res in resources["data"]:
        if res["downloadURL"].lower().endswith(".pdf"):
            doc = raw / Path(res["downloadURL"]).name.replace("%20", "_")
            preserved(root, doc, res["downloadURL"], "documentation")
            register(root, doc, res["downloadURL"], "documentation")
    for d in dist:
        period = d["temporal"]
        year, month = period[:4], int(period[5:7])
        quarter = f"{year}Q{(month - 1) // 3 + 1}"
        if national_csv:
            path = raw / f"{quarter}_national.csv"
            preserved(root, path, d["downloadURL"], "csv", period)
            with path.open(encoding="utf-8-sig", errors="strict", newline="") as f:
                reader = csv.reader(f)
                columns = next(reader)
                count = sum(1 for _ in reader)
            register(root, path, d["downloadURL"], "csv", period, rows=count, columns=columns)
            print(f"{quarter}: {count:,} national CSV records", flush=True)
            continue
        api = next(x["accessURL"] for x in dataset["distribution"]
                   if x.get("format") == "API" and x.get("temporal") == period and x.get("description") != "latest")
        offset = 0
        seen = set()
        while True:
            url = api + "?" + urlencode({"filter[STATE]": state, "size": 5000, "offset": offset, "sort": "PROVNUM,WorkDate"})
            path = raw / f"{quarter}_{state}" / f"page-{offset:06d}.json"
            data = json.loads(preserved(root, path, url, "api_page", period, state))
            if not isinstance(data, list):
                raise ValueError("Unexpected CMS API response")
            if any(row.get("STATE") != state for row in data):
                raise ValueError("CMS state filter was not applied")
            keys = [(r["PROVNUM"], r["WorkDate"]) for r in data]
            if len(set(keys)) != len(keys) or seen.intersection(keys):
                raise ValueError("Duplicate records across CMS pages: unstable pagination")
            seen.update(keys)
            register(root, path, url, "api_page", period, state, len(data), list(data[0]) if data else [])
            if len(data) < 5000:
                break
            offset += len(data)
        print(f"{quarter}: {len(seen):,} {state} facility-day records preserved", flush=True)
    return manifest(root)


def manual(root, file, period, state=None, source_url=None):
    """Copy an official CSV unchanged and register provenance supplied by the user."""
    root, file = Path(root), Path(file)
    checksum = sha256(file)
    dest = root / "data" / "raw" / "manual" / f"{checksum[:12]}_{file.name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(file, dest)
    with dest.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        columns = next(reader)
        rows = sum(1 for _ in reader)
    return register(root, dest, source_url or "manual: provenance URL not supplied", "csv", period, state, rows, columns)
