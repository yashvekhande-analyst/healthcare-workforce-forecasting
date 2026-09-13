import json
from pathlib import Path
import pandas as pd


def read_config(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["root"] = str(path.parent.parent)
    validate_config(cfg)
    return cfg


def validate_config(c):
    if not 1 <= c["facilities"] <= 50:
        raise ValueError("Facility count must be 1–50")
    if len(c["state"]) != 2 or not c["state"].isalpha():
        raise ValueError("Use a two-letter state code")
    t = pd.Timestamp
    assert t(c["start"]) < t(c["initial_train_end"]) < t(c["fit_cutoff"])
    assert t(c["fit_cutoff"]) < t(c["calibration"][0])
    assert t(c["calibration"][1]) + pd.Timedelta(days=7) < t(c["test"][0])
    assert t(c["test"][1]) + pd.Timedelta(days=7) <= t(c["end"])
    previous = t(c["initial_train_end"])
    for start, end in c["validation"]:
        assert previous < t(start) <= t(end)
        previous = t(end) + pd.Timedelta(days=7)
    assert previous <= t(c["fit_cutoff"])
    assert 0 < c["alpha"] < 1


def paths(c):
    root = Path(c["root"])
    run = root / "artifacts" / c["name"]
    for p in (root / "data" / "raw", run, run / "reports", run / "models"):
        p.mkdir(parents=True, exist_ok=True)
    return root, run


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, default=str, allow_nan=False), encoding="utf-8")
    temp.replace(path)
