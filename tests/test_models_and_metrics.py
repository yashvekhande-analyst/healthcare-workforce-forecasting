import joblib
import numpy as np
import pandas as pd
import pytest
from threadpoolctl import threadpool_limits
from workforce.metrics import metrics
from workforce.modeling import make_model, FEATURES, conformal_quantile, point_predict, forecast_frame
from workforce.monitoring import psi
from workforce.storage import immutable_parquet, attach_actuals
from test_data_and_time import sql_features
from workforce.validation import canonicalize


def test_metrics_and_zero_denominator():
    m = metrics([0, 10, 20], [2, 8, 25], [0, 8, 21], [3, 12, 30])
    assert m["mae_hours"] == 3
    assert m["wape"] == .3
    assert m["signed_error_hours"] == pytest.approx(5 / 3)
    assert m["coverage"] == pytest.approx(2 / 3)
    assert m["mean_width_hours"] == pytest.approx(16 / 3)
    assert metrics([0, 0], [0, 1])["wape"] is None
    with pytest.raises(ValueError):
        metrics([], [])


def test_finite_sample_conformal_rank():
    assert conformal_quantile(np.arange(1, 20), .1) == 18
    with pytest.raises(ValueError, match="Too few"):
        conformal_quantile([1, 2], .1)


def test_save_load_prediction_consistency_and_unknown_category(scratch, raw_factory):
    f = sql_features(canonicalize(raw_factory(days=90))).dropna(subset=["target"])
    f = f.loc[f.eligible]
    model = make_model({"max_leaf_nodes": 7, "l2_regularization": 1})
    with threadpool_limits(limits=1):
        model.fit(f[FEATURES], f.target)
    joblib.dump(model, scratch / "model.joblib")
    loaded = joblib.load(scratch / "model.joblib")
    np.testing.assert_array_equal(point_predict("gradient_boosted", model, f), point_predict("gradient_boosted", loaded, f))
    unknown = f.head(1).copy()
    unknown["facility"] = "999999"
    assert np.isfinite(point_predict("gradient_boosted", loaded, unknown)).all()


def test_forecasts_immutable_and_actuals_mature_separately(scratch):
    f = pd.DataFrame({"facility": ["000001"], "origin": pd.to_datetime(["2024-04-01"]), "prediction": [12.]})
    path = scratch / "forecasts.parquet"
    assert immutable_parquet(path, f, ["facility", "origin"])
    assert not immutable_parquet(path, f, ["facility", "origin"])
    changed = f.copy()
    changed.prediction += 1
    with pytest.raises(ValueError, match="immutable"):
        immutable_parquet(path, changed, ["facility", "origin"])
    labels = f[["facility", "origin"]].copy()
    labels["target_end"], labels["target"] = pd.Timestamp("2024-04-08"), 13.
    assert attach_actuals(f, labels, "2024-04-07").actual.isna().all()
    assert attach_actuals(f, labels, "2024-04-08").actual.iloc[0] == 13
    assert "actual" not in pd.read_parquet(path)


def test_drift_response():
    reference = {"cutpoints": [1, 2, 3], "probabilities": [.25] * 4}
    assert psi([.5, 1.5, 2.5, 3.5], reference) == pytest.approx(0)
    assert psi([100] * 30, reference) > .2
    assert psi([], reference) is None
