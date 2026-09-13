import json
from pathlib import Path
import pandas as pd
from workforce.config import read_config
from workforce.ingest import manual
from workforce.prepare import prepare
from workforce import modeling
from workforce.modeling import train, backtest
from workforce.predict import predict, realize
from workforce.monitoring import monitor


def test_small_end_to_end(scratch, raw_factory, monkeypatch):
    """Synthetic fixture verifies software only; real modeling results are separate."""
    c = read_config(Path(__file__).parents[1] / "configs/dev.json")
    c.update(root=str(scratch), facilities=2, name="synthetic-test")
    raw = raw_factory(days=730, facilities=2)
    p = scratch / "SYNTHETIC_TEST_ONLY.csv"
    raw.to_csv(p, index=False)
    manual(scratch, p, "2024-04-01/2026-03-31", source_url="synthetic:test-only")
    q = prepare(c)
    assert q["expected_facility_days"] == 1460
    monkeypatch.setattr(modeling, "CANDIDATES", modeling.CANDIDATES[:1])
    model = train(c)
    result = backtest(c)
    assert result["evaluated_origins"] == result["expected_test_facility_origins"]
    run = scratch / "artifacts/synthetic-test"
    validation = pd.read_parquet(run / "validation_predictions.parquet")
    assert (validation.training_cutoff < validation.origin).all()
    assert model["calibration_target_end"] < c["test"][0]
    report = predict(c, "2026-03-24")
    assert report["forecast_count"] == 2
    before = Path(report["path"]).read_bytes()
    assert realize(c, "2026-03-30")["known_outcomes"] == 0
    assert realize(c, "2026-03-31")["known_outcomes"] == 2
    assert Path(report["path"]).read_bytes() == before
    demo = monitor(c, "2026-03-31", scenario=True)
    assert demo["status"] == "REVIEW" and not demo["automatic_retraining"]
    assert {"input_completeness", "stale_facilities", "failed_jobs"}.issubset({a["check"] for a in demo["alerts"]})
