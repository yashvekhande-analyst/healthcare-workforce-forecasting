import numpy as np
import pandas as pd


def metrics(actual, predicted, lower=None, upper=None):
    y, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if len(y) != len(p) or not len(y) or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("Metrics require nonempty, aligned, finite observations")
    err = p - y
    denom = np.abs(y).sum()
    result = {"n": len(y), "mae_hours": float(np.abs(err).mean()),
              "wape": float(np.abs(err).sum() / denom) if denom > 0 else None,
              "signed_error_hours": float(err.mean()), "actual_hours_sum": float(y.sum()),
              "absolute_error_sum": float(np.abs(err).sum())}
    if lower is not None:
        lo, hi = np.asarray(lower), np.asarray(upper)
        if len(lo) != len(y) or len(hi) != len(y) or not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(lo > hi):
            raise ValueError("Invalid intervals")
        result.update(coverage=float(((y >= lo) & (y <= hi)).mean()), mean_width_hours=float((hi - lo).mean()))
    return result


def metric_table(predictions, group):
    rows = []
    for key, frame in predictions.groupby(group, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(group, key))
        row.update(metrics(frame.actual, frame.prediction,
                           frame.lower if "lower" in frame else None,
                           frame.upper if "upper" in frame else None))
        row.update(origin_start=str(frame.origin.min().date()), origin_end=str(frame.origin.max().date()),
                   facility_count=frame.facility.nunique())
        rows.append(row)
    return pd.DataFrame(rows)
