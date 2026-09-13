import numpy as np
import pandas as pd

ROLES = ["RNDON", "RNadmin", "RN", "LPNadmin", "LPN", "CNA", "NAtrn", "MedAide"]
META = ["PROVNUM", "PROVNAME", "CITY", "STATE", "COUNTY_NAME", "COUNTY_FIPS", "CY_Qtr", "WorkDate", "MDScensus"]
HOURS = [f"Hrs_{r}{suffix}" for r in ROLES for suffix in ("", "_emp", "_ctr")]
CONTRACT = [f"Hrs_{r}_ctr" for r in ("RN", "LPN", "CNA")]
EMPLOYEE = [f"Hrs_{r}_emp" for r in ("RN", "LPN", "CNA")]


def canonicalize(raw):
    missing = set(META + HOURS) - set(raw.columns)
    if missing:
        raise ValueError(f"Required CMS columns missing: {sorted(missing)}")
    raw = raw.copy()
    raw["PROVNUM"] = raw["PROVNUM"].astype("string").str.strip()
    if not raw["PROVNUM"].str.fullmatch(r"[A-Za-z0-9]{6}").fillna(False).all():
        raise ValueError("Invalid provider identifier; read source identifiers as strings")
    dates = pd.to_datetime(raw["WorkDate"].astype(str), format="%Y%m%d", errors="raise")
    if not (raw["CY_Qtr"].astype(str).str.upper().values == dates.dt.to_period("Q").astype(str).values).all():
        raise ValueError("WorkDate does not match reported calendar quarter")
    num = raw[HOURS + ["MDScensus"]].apply(pd.to_numeric, errors="coerce")
    nonfinite = ~np.isfinite(num)
    invalid = (num < 0) | nonfinite
    missing_hours = num[HOURS].isna().any(axis=1)
    negative = (num[HOURS] < 0).any(axis=1)
    inconsistent = pd.Series(False, index=raw.index)
    target_bad = invalid[CONTRACT].any(axis=1)
    employee_bad = invalid[EMPLOYEE].any(axis=1)
    for role in ROLES:
        cols = [f"Hrs_{role}", f"Hrs_{role}_emp", f"Hrs_{role}_ctr"]
        mismatch = (num[cols[0]] - num[cols[1]] - num[cols[2]]).abs() > 0.051
        inconsistent |= mismatch
        if role in ("RN", "LPN", "CNA"):
            # A broken identity or invalid total/component makes that target day unreliable.
            target_bad |= mismatch | invalid[cols].any(axis=1)
            employee_bad |= mismatch | invalid[cols].any(axis=1)
    census_bad = invalid["MDScensus"] | (num["MDScensus"] % 1 != 0)
    result = pd.DataFrame({
        "facility": raw["PROVNUM"], "date": dates, "name": raw["PROVNAME"],
        "county": raw["COUNTY_NAME"], "state": raw["STATE"],
        "contract_hours": num[CONTRACT].sum(axis=1, min_count=3).mask(target_bad),
        "employee_hours": num[EMPLOYEE].sum(axis=1, min_count=3).mask(employee_bad),
        "census": num["MDScensus"].mask(census_bad),
        "rn_contract": num[CONTRACT[0]].mask(target_bad),
        "lpn_contract": num[CONTRACT[1]].mask(target_bad),
        "cna_contract": num[CONTRACT[2]].mask(target_bad),
        "reported": True, "missing_hours": missing_hours, "negative_hours": negative,
        "component_mismatch": inconsistent, "invalid_census": census_bad,
    })
    return result.reset_index(drop=True)


def deduplicate(frame):
    exact = frame.drop_duplicates()
    if exact.duplicated(["facility", "date"]).any():
        raise ValueError("Conflicting facility/date records: choose a single CMS snapshot explicitly")
    return exact.sort_values(["facility", "date"]).reset_index(drop=True)
