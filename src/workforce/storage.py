from pathlib import Path
import pandas as pd


def immutable_parquet(path, frame, keys):
    """Single-writer local store. An existing forecast can never be silently changed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = frame.sort_values(keys).reset_index(drop=True)
    if ordered.duplicated(keys).any():
        raise ValueError("Duplicate immutable record keys")
    if path.exists():
        old = pd.read_parquet(path).sort_values(keys).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(old, ordered, check_dtype=False, check_exact=True)
        except AssertionError as exc:
            raise ValueError(f"Refusing to overwrite immutable records: {path}") from exc
        return False
    # Exclusive create prevents a second writer from replacing a completed object.
    with path.open("xb") as f:
        ordered.to_parquet(f, index=False)
    return True


def attach_actuals(forecasts, features, asof):
    known = features.loc[(features.target_end <= pd.Timestamp(asof)) & features.target.notna(), ["facility", "origin", "target"]]
    return forecasts.merge(known.rename(columns={"target": "actual"}), on=["facility", "origin"], how="left", validate="many_to_one")
