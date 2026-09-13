import tempfile
import uuid
from pathlib import Path
import pytest

APP = Path(__file__).parents[1] / "app.py"
ARTIFACTS = APP.parent / "artifacts/full"


@pytest.fixture
def app_test(scratch, monkeypatch):
    # Use ordinary inherited ACLs in restricted Windows runners.
    def make_temp(suffix=None, prefix=None, dir=None):
        p = scratch / ((prefix or "tmp") + uuid.uuid4().hex + (suffix or ""))
        p.mkdir()
        return str(p)
    monkeypatch.setattr(tempfile, "mkdtemp", make_temp)
    monkeypatch.setenv("WORKFORCE_ARTIFACTS", str(ARTIFACTS))
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=30)


def find(elements, label):
    return next(x for x in elements if x.label == label)


@pytest.mark.skipif(not (ARTIFACTS / "evaluation.parquet").exists(), reason="Run real-data pipeline before dashboard artifact checks")
def test_dashboard_filters_empty_state_and_monitoring(app_test):
    app = app_test.run()
    assert not app.exception
    assert find(app.metric, "Forecast coverage").value == "49 / 50"
    find(app.multiselect, "Training staffing-volume groups").set_value([]).run()
    assert not app.exception
    assert any("No facilities selected" in x.value for x in app.info)
    find(app.multiselect, "Training staffing-volume groups").set_value(["high"]).run()
    assert not app.exception
    assert find(app.metric, "Forecast coverage").value != "49 / 50"
    find(app.radio, "Facility scope").set_value("Choose facilities").run()
    find(app.multiselect, "Facilities").set_value([]).run()
    assert any("No facilities selected" in x.value for x in app.info)
    find(app.radio, "Facility scope").set_value("All matching facilities").run()
    find(app.toggle, "Show alert demonstration — TEST SCENARIO").set_value(True).run()
    assert not app.exception
    assert any("TEST SCENARIO" in x.value for x in app.warning)


def test_dashboard_missing_artifact_state(app_test, scratch, monkeypatch):
    monkeypatch.setenv("WORKFORCE_ARTIFACTS", str(scratch / "not-prepared"))
    app = app_test.run()
    assert not app.exception
    assert any("No completed analysis" in x.value for x in app.info)
