import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from .config import paths, save_json
from .modeling import load_bundle
from .metrics import metrics


def psi(values, reference):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    bins = np.r_[-np.inf, reference["cutpoints"], np.inf]
    counts, _ = np.histogram(values, bins=bins)
    actual, expected = counts / counts.sum(), np.array(reference["probabilities"])
    actual, expected = np.maximum(actual, 1e-6), np.maximum(expected, 1e-6)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def monitor(c, asof, scenario=False):
    _, run = paths(c)
    bundle = load_bundle(run)
    meta, thresholds = bundle["metadata"], c["monitoring"]
    asof = pd.Timestamp(asof)
    daily = pd.read_parquet(run / "daily.parquet")
    features = pd.read_parquet(run / "features.parquet")
    start = asof - pd.Timedelta(days=27)
    recent = daily.loc[daily.date.between(start, asof)].copy()
    count = daily.facility.nunique()
    latest = daily.loc[daily.reported & (daily.date <= asof)].groupby("facility").date.max()
    current = features.loc[features.origin.between(start, asof) & features.eligible].copy()
    jobs_path = run / "job_status.json"
    jobs = json.loads(jobs_path.read_text()) if jobs_path.exists() else {}
    failed = [name for name, job in jobs.items() if job["status"] == "failed"]
    for name, job in jobs.items():
        if name == "monitor" or job["status"] != "running":
            continue
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["started_at"])).total_seconds() / 60
        if age > thresholds.get("job_stale_minutes", 60):
            failed.append(name + " (incomplete job)")
    if scenario:
        # Perturb copies only: immutable data, model and forecasts are untouched.
        recent.loc[recent.index[::3], "contract_hours"] = np.nan
        latest = latest - pd.Timedelta(days=10)
        current["previous_7"] = current.previous_7 * 5 + 1000
        failed.append("TEST SCENARIO: simulated ingestion failure")
    completeness = float(recent.contract_hours.notna().sum() / (28 * count))
    stale = int(((asof - latest).dt.days > thresholds["stale_days"]).sum() + count - len(latest))
    alerts = []
    def alert(name, value, limit, action):
        alerts.append({"check": name, "value": value, "threshold": limit, "action": action})
    if completeness < thresholds["minimum_completeness"]:
        alert("input_completeness", completeness, thresholds["minimum_completeness"], "Investigate missing facility-days; withhold incomplete-history forecasts.")
    if stale:
        alert("stale_facilities", stale, thresholds["stale_days"], "Check assumed daily feed freshness and source exclusions.")
    if failed:
        alert("failed_jobs", failed, 0, "Review job logs and rerun the failed step after diagnosis.")
    shifts = {col: psi(current[col], ref) for col, ref in meta["reference_features"].items()}
    for col, score in shifts.items():
        if score is not None and score > thresholds["psi"]:
            alert("feature_shift:" + col, score, thresholds["psi"], "Compare facility mix and recent distributions with training; review before model changes.")
    realized = None
    ep = run / "evaluation.parquet"
    if ep.exists():
        ev = pd.read_parquet(ep)
        ev = ev.loc[(ev.model == meta["selected_model"]) & ev.target_end.between(start, asof)].dropna(subset=["actual"])
        if len(ev) >= thresholds["minimum_realized"]:
            realized = metrics(ev.actual, ev.prediction, ev.lower, ev.upper)
            validation_name = meta["selected_validation_candidate"]
            reference_mae = next(s["mae_hours"] for s in meta["validation_scores"] if s["model"] == validation_name)
            if realized["mae_hours"] > thresholds["mae_ratio"] * reference_mae:
                alert("realized_error", realized["mae_hours"], thresholds["mae_ratio"] * reference_mae, "Inspect recent forecast failures; do not automatically retrain.")
            if realized["coverage"] < thresholds["minimum_coverage"]:
                alert("interval_coverage", realized["coverage"], thresholds["minimum_coverage"], "Review interval reliability and temporal shifts.")
    result = {"mode": "TEST SCENARIO — injected missing input, staleness, drift and failed job" if scenario else "historical replay monitoring",
              "asof": str(asof.date()), "clock_basis": "replay date (not today's date)", "model_version": meta["version"],
              "status": "REVIEW" if alerts else "OK", "completeness_28d": completeness,
              "stale_facilities": stale, "feature_psi": shifts, "realized_last_28_days": realized,
              "realized_status": "available" if realized else "insufficient matured outcomes",
              "thresholds": thresholds, "alerts": alerts, "automatic_retraining": False}
    save_json(run / ("monitoring_demo.json" if scenario else "monitoring.json"), result)
    return result
