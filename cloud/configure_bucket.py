"""Set versioning/lifecycle through the API without CLI multiprocessing."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote
import requests
from bigquery import access_token

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bucket", required=True)
    p.add_argument("--project-number", required=True)
    p.add_argument("--region", default="us-central1")
    args = p.parse_args()
    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + access_token()
    url = "https://storage.googleapis.com/storage/v1/b/" + quote(args.bucket, safe="")
    response = session.get(url, timeout=30)
    response.raise_for_status()
    current = response.json()
    if str(current["projectNumber"]) != args.project_number or current["location"].lower() != args.region:
        raise ValueError("Refusing to modify a bucket in a different project or region")
    iam = current["iamConfiguration"]
    if not iam["uniformBucketLevelAccess"]["enabled"] or iam.get("publicAccessPrevention") != "enforced":
        raise ValueError("Bucket must already enforce private uniform access")
    desired = {"versioning": {"enabled": True},
               "lifecycle": json.loads((Path(__file__).parent / "retention.json").read_text())}
    if any(current.get(key) != value for key, value in desired.items()):
        response = session.patch(url, params={"ifMetagenerationMatch": current["metageneration"]},
                                 json=desired, timeout=30)
        response.raise_for_status()
        current = response.json()
    if any(current.get(key) != value for key, value in desired.items()):
        raise ValueError("Bucket configuration did not match after update")
    print(json.dumps({"bucket": args.bucket, "region": current["location"],
                      "versioning": current["versioning"], "private_uniform_access": True}))

if __name__ == "__main__":
    main()
