from pathlib import Path
import duckdb
import pandas as pd
from .config import paths
from .modeling import load_bundle, forecast_frame
from .storage import immutable_parquet, attach_actuals


def features_at(daily, origin):
    # Rebuild from the prefix; the live prediction path never loads future feature values.
    prefix = daily.loc[daily.date <= pd.Timestamp(origin)].copy()
    with duckdb.connect() as db:
        db.register("daily", prefix)
        features = db.execute((Path(__file__).parent / "sql" / "features.sql").read_text()).df()
    return features.loc[(features.origin == pd.Timestamp(origin)) & features.eligible].copy()


def predict(c, origin):
    _, run = paths(c)
    bundle = load_bundle(run)
    daily = pd.read_parquet(run / "daily.parquet")
    if pd.Timestamp(origin) > daily.date.max() or pd.Timestamp(origin) < pd.Timestamp(bundle["metadata"]["valid_from"]):
        raise ValueError("Origin outside available replay history for this calibrated model")
    f = features_at(daily, origin)
    predictions = forecast_frame(f, bundle, bundle["metadata"]["selected_model"], "replay")
    dest = run / "forecasts" / bundle["metadata"]["version"] / f"{pd.Timestamp(origin).date()}.parquet"
    immutable_parquet(dest, predictions, ["facility", "origin", "model_version"])
    return {"path": str(dest), "forecast_count": len(predictions), "withheld_facilities": int(daily.facility.nunique() - len(predictions)), "origin": origin}


def realize(c, asof):
    _, run = paths(c)
    bundle = load_bundle(run)
    files = sorted((run / "forecasts" / bundle["metadata"]["version"]).glob("*.parquet"))
    if not files:
        raise ValueError("Generate replay forecasts first")
    forecasts = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    f = pd.read_parquet(run / "features.parquet")
    joined = attach_actuals(forecasts, f, asof)
    known = joined.dropna(subset=["actual"])[["facility", "origin", "model_version", "target_end", "actual"]]
    dest = run / "actuals" / bundle["metadata"]["version"] / f"asof-{pd.Timestamp(asof).date()}.parquet"
    immutable_parquet(dest, known, ["facility", "origin", "model_version"])
    return {"known_outcomes": len(known), "path": str(dest)}
