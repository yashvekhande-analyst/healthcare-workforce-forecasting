import shutil
import uuid
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from workforce.validation import META, HOURS


@pytest.fixture
def scratch():
    base = (Path.cwd() / ".test-runs").resolve()
    base.mkdir(exist_ok=True)
    target = base / uuid.uuid4().hex
    target.mkdir()
    yield target
    if target.resolve().is_relative_to(base):
        shutil.rmtree(target)


@pytest.fixture
def raw_factory():
    def make(days=70, facilities=2, start="2024-04-01"):
        dates = pd.date_range(start, periods=days)
        records = []
        for i in range(facilities):
            for j, day in enumerate(dates):
                row = {col: "0" for col in META + HOURS}
                row.update(PROVNUM=f"{i + 1:06d}", PROVNAME=f"Synthetic TEST Facility {i}", CITY="Test", STATE="NY",
                           COUNTY_NAME="TestCounty", COUNTY_FIPS="001", CY_Qtr=str(day.to_period("Q")),
                           WorkDate=day.strftime("%Y%m%d"), MDScensus=str(80 + i * 20))
                contract = max(0, 8 + i * 4 + 5 * np.sin(j / 7))
                for role in ("RN", "LPN", "CNA"):
                    row[f"Hrs_{role}_ctr"] = str(round(contract, 2))
                    row[f"Hrs_{role}_emp"] = "40"
                    row[f"Hrs_{role}"] = str(round(contract + 40, 2))
                records.append(row)
        return pd.DataFrame(records)
    return make
