import json
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import pytest
from workforce.ingest import manual, manifest, sha256
from workforce.validation import canonicalize, deduplicate
from workforce.prepare import select_facilities
from workforce.predict import features_at
from workforce.modeling import training_rows, window_rows


def sql_features(daily):
    daily = daily.copy()
    daily["volume_group"] = "low"
    with duckdb.connect() as db:
        db.register("daily", daily)
        return db.execute((Path(__file__).parents[1] / "src/workforce/sql/features.sql").read_text()).df()


def test_duplicate_ingestion_and_raw_preservation(scratch, raw_factory):
    f = scratch / "official-shape-TEST.csv"
    raw_factory().to_csv(f, index=False)
    before = sha256(f)
    a = manual(scratch, f, "2024-04-01/2024-06-30", source_url="synthetic:test-only")
    b = manual(scratch, f, "2024-04-01/2024-06-30", source_url="synthetic:test-only")
    assert a == b and len(manifest(scratch)["files"]) == 1
    assert before == sha256(f) == sha256(scratch / a["path"])
    frame = canonicalize(raw_factory())
    assert len(deduplicate(pd.concat([frame, frame]))) == len(frame)
    conflict = frame.iloc[[0]].copy()
    conflict["contract_hours"] += 1
    with pytest.raises(ValueError, match="Conflicting"):
        deduplicate(pd.concat([frame, conflict]))


def test_missing_zero_negative_identity_and_schema(raw_factory):
    raw = raw_factory(days=5, facilities=1)
    for role in ("RN", "LPN", "CNA"):
        raw.loc[0, f"Hrs_{role}_ctr"] = "0"
        raw.loc[0, f"Hrs_{role}"] = "40"
    raw.loc[1, "Hrs_RN_ctr"] = ""
    raw.loc[2, "Hrs_RN_ctr"] = "-1"
    raw.loc[3, "Hrs_RN"] = "999"
    raw.loc[4, "Hrs_RNDON_ctr"], raw.loc[4, "Hrs_RNDON"] = "1000", "1000"
    df = canonicalize(raw)
    assert df.loc[0, "contract_hours"] == 0
    assert df.loc[1:3, "contract_hours"].isna().all()
    assert df.loc[2, "negative_hours"] and df.loc[3, "component_mismatch"]
    assert df.loc[4, "contract_hours"] < 1000  # Administrative DON excluded, never double counted.
    assert df.loc[0, "facility"] == "000001"
    with pytest.raises(ValueError, match="columns"):
        canonicalize(raw.drop(columns="Hrs_RN_ctr"))
    raw.loc[0, "WorkDate"] = "20240231"
    with pytest.raises(ValueError):
        canonicalize(raw)


def test_exact_target_window_and_missing_day(raw_factory):
    daily = canonicalize(raw_factory(days=50, facilities=1))
    daily["contract_hours"] = np.arange(50, dtype=float)
    f = sql_features(daily).set_index("origin")
    origin = pd.Timestamp("2024-04-28")
    assert f.loc[origin, "target"] == sum(range(28, 35))
    assert f.loc[origin, "previous_7"] == sum(range(21, 28))
    assert f.loc[origin, "trailing_28"] == np.mean(range(28)) * 7
    assert pd.isna(f.iloc[-1].target)
    daily.loc[29, "contract_hours"] = np.nan
    missing = sql_features(daily).set_index("origin")
    assert pd.isna(missing.loc[origin, "target"])
    assert not missing.loc[pd.Timestamp("2024-05-01"), "eligible"]


def test_future_mutation_cannot_change_predictors(raw_factory):
    daily = canonicalize(raw_factory(days=70))
    daily["volume_group"] = "low"
    origin = pd.Timestamp("2024-05-10")
    before = features_at(daily, origin).sort_values("facility").reset_index(drop=True)
    daily.loc[daily.date > origin, ["contract_hours", "employee_hours", "census"]] = 999999
    after = features_at(daily, origin).sort_values("facility").reset_index(drop=True)
    pd.testing.assert_frame_equal(before, after)
    assert before.target.isna().all()
    assert (before.origin == origin).all()


def test_label_availability_and_split_boundaries(raw_factory):
    f = sql_features(canonicalize(raw_factory(days=120)))
    cutoff = pd.Timestamp("2024-06-01")
    train = training_rows(f, cutoff)
    val = window_rows(f, ["2024-06-02", "2024-06-10"])
    assert train.target_end.max() <= cutoff
    assert train.origin.max() == cutoff - pd.Timedelta(days=7)
    assert train.target_end.max() < val.origin.min()
    assert not set(zip(train.facility, train.origin)) & set(zip(val.facility, val.origin))


def test_facility_selection_ignores_future_completeness(raw_factory):
    daily = canonicalize(raw_factory(days=120, facilities=3))
    c = {"start": "2024-04-01", "initial_train_end": "2024-05-31", "seed": 42, "facilities": 2, "eligibility_coverage": .95}
    chosen, _ = select_facilities(daily, c)
    future = daily.date > "2024-05-31"
    daily.loc[future, "contract_hours"] = np.nan
    other, _ = select_facilities(daily, c)
    pd.testing.assert_frame_equal(chosen, other)
