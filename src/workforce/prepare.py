import hashlib
import json
from pathlib import Path
import duckdb
import pandas as pd
from .config import paths, save_json
from .ingest import manifest, sha256, write_manifest
from .validation import canonicalize, deduplicate


def load_raw(c):
    root, _ = paths(c)
    m = manifest(root)
    records, audit = [], []
    for e in m["files"]:
        if e["kind"] not in ("api_page", "csv") or not e.get("row_count"):
            continue
        if e.get("state") not in (None, c["state"]):
            continue
        if not e.get("period") or e["period"].split("/")[0] > c["end"] or e["period"].split("/")[1] < c["start"]:
            continue
        p = root / e["path"]
        if sha256(p) != e["sha256"]:
            raise ValueError(f"Raw checksum failed: {p}")
        if e["kind"] == "api_page":
            chunks = [pd.DataFrame(json.loads(p.read_bytes()))]
        else:
            chunks = pd.read_csv(p, dtype=str, chunksize=100000, encoding="utf-8-sig")
        count = 0
        for chunk in chunks:
            chunk = chunk.loc[chunk.STATE == c["state"]]
            if chunk.empty:
                continue
            transformed = canonicalize(chunk)
            begin, finish = e["period"].split("/")
            if not transformed.date.between(begin, finish).all():
                raise ValueError("Raw records outside their registered reporting period")
            transformed = transformed.loc[transformed.date.between(c["start"], c["end"])]
            count += len(transformed)
            records.append(transformed)
        audit.append({"path": e["path"], "sha256": e["sha256"], "state_rows_in_range": count})
    if not records:
        raise ValueError("No registered real data. Run fetch or ingest-manual first.")
    combined = pd.concat(records, ignore_index=True)
    before = len(combined)
    combined = deduplicate(combined)
    return combined, {"sources": audit, "input_rows": before, "unique_state_rows": len(combined), "duplicates_removed": before - len(combined)}


def select_facilities(frame, c):
    train = frame.loc[frame.date.between(c["start"], c["initial_train_end"])].copy()
    days = len(pd.date_range(c["start"], c["initial_train_end"]))
    stats = train.groupby("facility").agg(valid_days=("contract_hours", "count"), training_daily_mean=("contract_hours", "mean"))
    stats["training_coverage"] = stats.valid_days / days
    stats["eligible"] = stats.training_coverage >= c["eligibility_coverage"]
    stats["selection_hash"] = [hashlib.sha256(f"{c['seed']}:{i}".encode()).hexdigest() for i in stats.index]
    eligible = stats.loc[stats.eligible].sort_values("selection_hash").head(c["facilities"]).copy()
    if eligible.empty:
        raise ValueError("No facilities meet training-only eligibility")
    # Volume cutpoints are fixed from selected facilities' initial training means.
    q1, q2 = eligible.training_daily_mean.quantile([1 / 3, 2 / 3])
    eligible["volume_group"] = eligible.training_daily_mean.apply(lambda x: "low" if x <= q1 else "medium" if x <= q2 else "high")
    names = train.sort_values("date").groupby("facility")[["name", "county", "state"]].last()
    selected = eligible.join(names).reset_index()
    stats["selected"] = stats.index.isin(selected.facility)
    return selected, stats.reset_index()


def prepare(c):
    root, run = paths(c)
    all_data, audit = load_raw(c)
    facilities, eligibility = select_facilities(all_data, c)
    daily = all_data.loc[all_data.facility.isin(facilities.facility)].copy()
    index = pd.MultiIndex.from_product([facilities.facility, pd.date_range(c["start"], c["end"])], names=["facility", "date"])
    daily = daily.set_index(["facility", "date"]).reindex(index).reset_index()
    for col in ["reported", "missing_hours", "negative_hours", "component_mismatch", "invalid_census"]:
        daily[col] = daily[col].astype("boolean").fillna(False).astype(bool)
    # Descriptors fixed at the initial training cutoff; no future-name backfill.
    daily = daily.drop(columns=["name", "county", "state"]).merge(facilities[["facility", "name", "county", "state", "volume_group"]], on="facility", validate="many_to_one")
    daily = daily.sort_values(["facility", "date"]).reset_index(drop=True)
    daily.to_parquet(run / "daily.parquet", index=False)
    facilities.to_parquet(run / "facilities.parquet", index=False)
    eligibility.to_csv(run / "eligibility.csv", index=False)
    with duckdb.connect(str(run / "workforce.duckdb")) as db:
        db.register("daily_input", daily)
        db.execute("CREATE OR REPLACE TABLE daily AS SELECT * FROM daily_input")
        sql = (Path(__file__).parent / "sql" / "features.sql").read_text()
        db.execute("CREATE OR REPLACE TABLE features AS " + sql)
        features = db.execute("SELECT * FROM features ORDER BY facility, origin").df()
    features.to_parquet(run / "features.parquet", index=False)
    by_quarter = daily.assign(quarter=daily.date.dt.to_period("Q").astype(str)).groupby("quarter").agg(expected=("date", "size"), reported=("reported", "sum"), valid=("contract_hours", "count"))
    by_quarter.to_csv(run / "reports" / "quarter_coverage.csv")
    quality = {
        "state": c["state"], "selected_facilities": len(facilities), "eligible_facilities": int(eligibility.eligible.sum()),
        "expected_facility_days": len(daily), "reported_days": int(daily.reported.sum()),
        "missing_dates": int((~daily.reported).sum()), "invalid_contract_days": int((daily.reported & daily.contract_hours.isna()).sum()),
        "missing_hours": int(daily.missing_hours.sum()), "negative_hours": int(daily.negative_hours.sum()),
        "component_mismatch": int(daily.component_mismatch.sum()), "invalid_census": int(daily.invalid_census.sum()),
        "reported_zero_contract_days": int(daily.contract_hours.eq(0).sum()),
        "valid_contract_days": int(daily.contract_hours.notna().sum()),
        "valid_feature_rows": int(features.eligible.sum()),
        "complete_labeled_rows": int((features.eligible & features.target.notna()).sum()), **audit,
    }
    save_json(run / "quality.json", quality)
    save_json(run / "config_snapshot.json", {k: v for k, v in c.items() if k != "root"})
    transform = {"profile": c["name"], "version": "canonical-v1_sql-calendar-v1", "state": c["state"],
                 "dates": [c["start"], c["end"]], "selected_ids": facilities.facility.tolist(),
                 "selection_cutoff": c["initial_train_end"], "rows": len(daily),
                 "daily_sha256": sha256(run / "daily.parquet"), "features_sha256": sha256(run / "features.parquet"),
                 "operations": ["explicit string IDs and YYYYMMDD dates", "exact duplicate removal; reject conflicts", "validate all role identities with 0.051h tolerance", "sum RN/LPN/CNA contract components only", "training-only coverage/hash selection", "calendar reindex; missing remains null", "DuckDB trailing windows and forward labels"]}
    m = manifest(root)
    if transform not in m["transformations"]:
        m["transformations"].append(transform)
        write_manifest(root, m)
    return quality
