import hashlib
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits
from .config import paths, save_json
from .ingest import sha256
from .metrics import metrics, metric_table
from .storage import immutable_parquet, attach_actuals

NUMERIC = ["contract_today", "previous_7", "trailing_28", "contract_std7", "contract_std28",
           "zero_fraction28", "contract_lag7", "contract_lag14", "employee_mean7", "employee_mean28",
           "census_today", "census_mean7", "census_lag7", "next_weekday", "season_sin", "season_cos"]
CATEGORICAL = ["facility", "county"]
FEATURES = NUMERIC + CATEGORICAL
CANDIDATES = [dict(max_leaf_nodes=leaf, l2_regularization=l2) for leaf in (7, 15) for l2 in (1.0, 10.0)]


def distribution_reference(values):
    values = values.dropna().to_numpy()
    cutpoints = np.unique(np.quantile(values, np.linspace(0.1, 0.9, 9)))
    counts, _ = np.histogram(values, bins=np.r_[-np.inf, cutpoints, np.inf])
    return {"cutpoints": cutpoints.tolist(), "probabilities": (counts / counts.sum()).tolist()}


def make_model(params, seed=42):
    pre = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median", add_indicator=True), NUMERIC),
        ("facility_context", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ])
    model = HistGradientBoostingRegressor(loss="absolute_error", learning_rate=0.06, max_iter=180,
                                          early_stopping=False, min_samples_leaf=30, random_state=seed, **params)
    return Pipeline([("preprocess", pre), ("model", model)])


def training_rows(features, cutoff):
    return features.loc[features.eligible & features.target.notna() & (features.target_end <= pd.Timestamp(cutoff))].copy()


def window_rows(features, window, require_target=True):
    mask = features.eligible & features.origin.between(*window)
    if require_target:
        mask &= features.target.notna()
    return features.loc[mask].copy()


def point_predict(kind, model, frame):
    if kind in ("previous_7", "trailing_28"):
        return frame[kind].to_numpy(dtype=float)
    with threadpool_limits(limits=1):
        return np.maximum(0, model.predict(frame[FEATURES]))


def conformal_quantile(scores, alpha):
    scores = np.asarray(scores, dtype=float)
    if len(scores) == 0 or not np.isfinite(scores).all():
        raise ValueError("No finite calibration scores")
    rank = math.ceil((len(scores) + 1) * (1 - alpha))
    if rank > len(scores):
        raise ValueError("Too few calibration scores for requested interval level")
    return float(np.sort(scores)[rank - 1])


def model_version(c, run):
    code = [Path(__file__), Path(__file__).parent / "sql" / "features.sql", Path(__file__).parent / "validation.py"]
    spec = {k: v for k, v in c.items() if k != "root"}
    payload = json.dumps(spec, sort_keys=True) + sha256(run / "features.parquet") + "".join(sha256(p) for p in code)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def train(c):
    _, run = paths(c)
    features = pd.read_parquet(run / "features.parquet")
    version = model_version(c, run)
    validation = []
    for fold, window in enumerate(c["validation"], 1):
        cutoff = pd.Timestamp(window[0]) - pd.Timedelta(days=1)
        tr, va = training_rows(features, cutoff), window_rows(features, window)
        if tr.empty or va.empty:
            raise ValueError("Insufficient history for configured chronological split")
        assert tr.target_end.max() < va.origin.min()
        for name in ("previous_7", "trailing_28") + tuple(f"gb_{i}" for i in range(len(CANDIDATES))):
            model = None
            if name.startswith("gb_"):
                model = make_model(CANDIDATES[int(name[3:])], c["seed"])
                with threadpool_limits(limits=1):
                    model.fit(tr[FEATURES], tr.target)
            pred = va[["facility", "origin", "target_end", "volume_group", "target"]].rename(columns={"target": "actual"}).copy()
            pred["prediction"] = point_predict(name, model, va)
            pred["model"] = name
            pred["model_version"] = f"{version}-{name}-fold{fold}"
            pred["split"] = f"validation_{fold}"
            pred["training_cutoff"] = cutoff
            pred["training_n"] = len(tr)
            validation.append(pred)
        print(f"Validation {fold}: train={len(tr):,}, validation={len(va):,}, cutoff={cutoff.date()}", flush=True)
    validation = pd.concat(validation, ignore_index=True)
    immutable_parquet(run / "validation_predictions.parquet", validation, ["model", "split", "facility", "origin"])
    scores = metric_table(validation, ["model"]).sort_values(["mae_hours", "model"])
    gb_name = scores.loc[scores.model.str.startswith("gb_"), "model"].iloc[0]
    selected_candidate = scores.iloc[0].model
    selected = "gradient_boosted" if selected_candidate.startswith("gb_") else selected_candidate
    params = CANDIDATES[int(gb_name[3:])]
    fit = training_rows(features, c["fit_cutoff"])
    gb = make_model(params, c["seed"])
    with threadpool_limits(limits=1):
        gb.fit(fit[FEATURES], fit.target)
    calibration = window_rows(features, c["calibration"])
    calibration = calibration.loc[(calibration.origin - pd.Timestamp(c["calibration"][0])).dt.days % 7 == 0]
    if calibration.empty:
        raise ValueError("No calibration data")
    assert fit.target_end.max() < calibration.origin.min()
    assert calibration.target_end.max() < pd.Timestamp(c["test"][0])
    calibration_predictions, quantiles = [], {}
    for kind in ("previous_7", "trailing_28", "gradient_boosted"):
        p = point_predict(kind, gb, calibration)
        residual = np.abs(calibration.target.to_numpy() - p) / (1 + calibration.previous_7.to_numpy())
        quantiles[kind] = conformal_quantile(residual, c["alpha"])
        cp = calibration[["facility", "origin", "target_end", "volume_group", "target"]].rename(columns={"target": "actual"}).copy()
        cp["prediction"], cp["score"], cp["model"] = p, residual, kind
        cp["split"], cp["model_version"] = "calibration", f"{version}-{kind}"
        calibration_predictions.append(cp)
    immutable_parquet(run / "calibration_predictions.parquet", pd.concat(calibration_predictions), ["model", "facility", "origin"])
    metadata = {
        "version": version, "selected_model": selected, "selected_validation_candidate": selected_candidate,
        "gradient_parameters": params, "gradient_candidate": gb_name, "search_candidates": CANDIDATES,
        "selection_rule": "minimum pooled validation MAE; final test is untouched",
        "fit_cutoff": c["fit_cutoff"], "training_n": len(fit),
        "training_origin_start": str(fit.origin.min().date()), "training_origin_end": str(fit.origin.max().date()),
        "calibration_origins": [str(calibration.origin.min().date()), str(calibration.origin.max().date())],
        "calibration_target_end": str(calibration.target_end.max().date()), "calibration_n": len(calibration),
        "valid_from": c["test"][0], "alpha": c["alpha"], "quantiles": quantiles,
        "feature_columns": FEATURES, "feature_data_sha256": sha256(run / "features.parquet"),
        "validation_scores": scores.to_dict(orient="records"),
        "reference_features": {col: distribution_reference(fit[col]) for col in ["previous_7", "census_mean7", "employee_mean7"]},
    }
    bundle = {"gradient_model": gb, "metadata": metadata}
    joblib.dump(bundle, run / "models" / "bundle.joblib")
    loaded = joblib.load(run / "models" / "bundle.joblib")
    np.testing.assert_array_equal(point_predict("gradient_boosted", gb, fit.head(100)), point_predict("gradient_boosted", loaded["gradient_model"], fit.head(100)))
    metadata["bundle_sha256"] = sha256(run / "models" / "bundle.joblib")
    save_json(run / "models" / "metadata.json", metadata)
    scores.to_csv(run / "reports" / "validation_metrics.csv", index=False)
    metric_table(validation, ["model", "split"]).to_csv(run / "reports" / "validation_fold_metrics.csv", index=False)
    return metadata


def load_bundle(run):
    meta = json.loads((run / "models" / "metadata.json").read_text())
    if sha256(run / "models" / "bundle.joblib") != meta["bundle_sha256"]:
        raise ValueError("Saved model checksum mismatch")
    # Only load the trusted, locally generated joblib artifact.
    return joblib.load(run / "models" / "bundle.joblib")


def forecast_frame(frame, bundle, kind, split):
    meta = bundle["metadata"]
    if len(frame) and frame.origin.min() < pd.Timestamp(meta["valid_from"]):
        raise ValueError("This fitted/calibrated model was not available at the requested origin")
    out = frame[["facility", "origin", "target_end", "volume_group", "previous_7"]].copy()
    out["prediction"] = point_predict(kind, bundle["gradient_model"], frame) if len(frame) else np.array([])
    width = meta["quantiles"][kind] * (1 + frame.previous_7.to_numpy())
    out["lower"] = np.maximum(0, out.prediction - width)
    out["upper"] = out.prediction + width
    out["model"], out["model_version"], out["split"] = kind, f"{meta['version']}-{kind}", split
    out["interval_level"] = 1 - meta["alpha"]
    out["training_cutoff"] = pd.Timestamp(meta["fit_cutoff"])
    out["calibration_target_end"] = pd.Timestamp(meta["calibration_target_end"])
    out["availability_assumption"] = "historical replay: internal daily feed through end of origin"
    out["units"] = "contract RN + LPN + CNA hours over next seven calendar days"
    return out


def backtest(c):
    _, run = paths(c)
    bundle = load_bundle(run)
    features = pd.read_parquet(run / "features.parquet")
    # Preserve forecasts even when a future outcome is missing, then attach available actuals.
    test = window_rows(features, c["test"], require_target=False)
    forecasts = pd.concat([forecast_frame(test, bundle, kind, "test") for kind in ("previous_7", "trailing_28", "gradient_boosted")], ignore_index=True)
    immutable_parquet(run / "test_forecasts.parquet", forecasts, ["model", "facility", "origin"])
    evaluated = attach_actuals(forecasts, features, c["end"])
    outcomes = evaluated[["facility", "origin", "target_end", "actual"]].drop_duplicates()
    immutable_parquet(run / "test_outcomes.parquet", outcomes, ["facility", "origin"])
    evaluated.to_parquet(run / "evaluation.parquet", index=False)
    known = evaluated.dropna(subset=["actual"])
    if known.empty:
        raise ValueError("No realized test targets")
    result = metric_table(known, ["model"])
    result.to_csv(run / "reports" / "test_metrics.csv", index=False)
    metric_table(known, ["model", "facility"]).to_csv(run / "reports" / "facility_metrics.csv", index=False)
    metric_table(known, ["model", "volume_group"]).to_csv(run / "reports" / "volume_metrics.csv", index=False)
    weekly = known.loc[(known.origin - pd.Timestamp(c["test"][0])).dt.days % 7 == 0]
    metric_table(weekly, ["model"]).to_csv(run / "reports" / "nonoverlap_test_metrics.csv", index=False)
    selected = known.loc[known.model == bundle["metadata"]["selected_model"]].copy()
    selected["absolute_error"] = (selected.prediction - selected.actual).abs()
    selected.nlargest(12, "absolute_error").to_csv(run / "reports" / "representative_failures.csv", index=False)
    coverage = {"expected_test_facility_origins": len(pd.date_range(*c["test"])) * pd.read_parquet(run / "facilities.parquet").shape[0],
                "forecastable_origins": len(test), "evaluated_origins": len(selected),
                "unobserved_outcomes": int(evaluated.loc[evaluated.model == bundle["metadata"]["selected_model"], "actual"].isna().sum()),
                "selected_model": bundle["metadata"]["selected_model"], "test": c["test"], "metrics": result.to_dict(orient="records")}
    save_json(run / "backtest_summary.json", coverage)
    return coverage
