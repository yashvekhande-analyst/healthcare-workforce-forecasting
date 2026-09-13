import html
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd
from .config import paths, save_json

CMS = "https://data.cms.gov/quality-of-care/payroll-based-journal-daily-nurse-staffing"


def table(df):
    # Keep reporting dependency-free; tabulate is not needed.
    def fmt(v):
        if isinstance(v, float):
            return "N/A" if pd.isna(v) else f"{v:,.3f}"
        return str(v).replace("|", " ")
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "| " + " | ".join(["---"] * len(df.columns)) + " |"]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False, name=None)]
    return "\n".join(lines)


def reports(c):
    _, run = paths(c)
    cache = run / ".cache" / "matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    report = run / "reports"
    figures = report / "figures"
    figures.mkdir(exist_ok=True)
    daily = pd.read_parquet(run / "daily.parquet")
    features = pd.read_parquet(run / "features.parquet")
    facilities = pd.read_parquet(run / "facilities.parquet")
    q = json.loads((run / "quality.json").read_text())
    meta = json.loads((run / "models" / "metadata.json").read_text())
    bt = json.loads((run / "backtest_summary.json").read_text())
    metric = pd.read_csv(report / "test_metrics.csv")
    selected = metric.loc[metric.model == meta["selected_model"]].iloc[0]
    baseline = metric.loc[metric.model == "previous_7"].iloc[0]
    validation = pd.read_csv(report / "validation_metrics.csv")
    failures = pd.read_csv(report / "representative_failures.csv", dtype={"facility": str})
    volumes = pd.read_csv(report / "volume_metrics.csv")
    selected_volumes = volumes.loc[volumes.model == meta["selected_model"]]
    transitions = failures.loc[failures.previous_7.eq(0) & failures.actual.gt(0)]
    failure_note = ""
    if len(transitions):
        failure = transitions.iloc[0]
        failure_note = f"For example, facility {failure.facility} at origin {failure.origin} had zero preceding-seven-day hours but then reported {failure.actual:.2f} hours in the target window; the forecast was {failure.prediction:.2f} hours with an upper bound of {failure.upper:.2f}. A change from zero history to substantial utilization exposes the interval method's weakness."
    # EDA is restricted to the initial training period; test failures are separately labeled.
    train = daily.loc[daily.date <= pd.Timestamp(c["initial_train_end"])].copy()
    valid = train.dropna(subset=["contract_hours"])
    zero = float(valid.contract_hours.eq(0).mean())
    corr = float(valid[["census", "contract_hours"]].corr().iloc[0, 1])
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "figure.facecolor": "white"})
    colors = ["#126E82", "#BB5A2B", "#65758B"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    monthly = valid.assign(month=valid.date.dt.to_period("M").dt.to_timestamp()).groupby("month")[["contract_hours", "employee_hours"]].mean()
    monthly.plot(ax=axes[0, 0], color=colors, linewidth=2)
    axes[0, 0].set(title="Monthly staffing patterns", ylabel="Mean hours / observed facility-day", xlabel="Training month")
    weekday = valid.assign(weekday=valid.date.dt.dayofweek).groupby("weekday").contract_hours.mean()
    axes[0, 1].bar(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], weekday.reindex(range(7)), color=colors[0])
    axes[0, 1].set(title="Weekday contract utilization", ylabel="Mean hours / observed facility-day")
    axes[1, 0].hist(valid.contract_hours, bins=50, color=colors[0])
    axes[1, 0].set(title=f"Daily contract distribution · {zero:.1%} reported zeros", xlabel="Contract RN + LPN + CNA hours", ylabel="Facility-days")
    axes[1, 1].scatter(valid.census, valid.contract_hours, s=5, alpha=0.14, color=colors[0], rasterized=True)
    axes[1, 1].set(title=f"Census relationship · pooled r = {corr:.2f}", xlabel="Resident census (MDS)", ylabel="Daily contract hours")
    fig.suptitle("Training-period exploration · nursing homes · historical replay", fontsize=15)
    fig.savefig(figures / "eda_patterns.png", dpi=160)
    plt.close(fig)
    per_fac = valid.groupby("facility").contract_hours.agg(["mean", "std", "max"]).sort_values("mean")
    per_fac.to_csv(report / "training_facility_patterns.csv")
    fig, ax = plt.subplots(figsize=(12, 4.8), constrained_layout=True)
    ax.bar(per_fac.index, per_fac["mean"], color=colors[0])
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    ax.set(title="Facilities differ substantially in historical contract utilization", ylabel="Mean daily contract hours", xlabel="CMS facility identifier · initial training period")
    fig.savefig(figures / "facility_variation.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].barh(metric.model, metric.mae_hours, color=[colors[0] if name == meta["selected_model"] else colors[2] for name in metric.model])
    axes[0].set(title="Held-out forecast accuracy", xlabel="MAE · seven-day contract hours (lower is better)")
    axes[1].barh(metric.model, metric.coverage, color=colors[0])
    axes[1].axvline(1 - c["alpha"], color=colors[1], linestyle="--", label="Nominal coverage")
    axes[1].set(title="Observed prediction-interval coverage", xlabel="Fraction of observed outcomes covered", xlim=(0, 1))
    axes[1].legend()
    fig.savefig(figures / "backtest.png", dpi=160)
    plt.close(fig)
    train_features = features.loc[(features.origin <= pd.Timestamp(c["initial_train_end"])) & (features.target_end <= pd.Timestamp(c["initial_train_end"]))]
    weekly_zero = float(train_features.target.dropna().eq(0).mean())
    extremes = valid.nlargest(10, "contract_hours")[["facility", "date", "contract_hours", "employee_hours", "census"]]
    extremes.to_csv(report / "training_unusual_observations.csv", index=False)
    stats = {"training_daily_zero_fraction": zero, "training_weekly_zero_fraction": weekly_zero,
             "training_census_contract_correlation": corr, "training_contract_daily_mean": float(valid.contract_hours.mean()),
             "training_employee_daily_mean": float(valid.employee_hours.mean()), "training_daily_contract_p99": float(valid.contract_hours.quantile(.99)),
             "training_daily_contract_max": float(valid.contract_hours.max())}
    save_json(report / "eda_statistics.json", stats)
    eda = f"""# Exploratory analysis

Independent portfolio project. Nursing-home contract staffing utilization; historical replay.

The EDA used **{c['start']} through {c['initial_train_end']} only**, before validation, calibration or final testing. The {len(facilities)} selected {c['state']} facilities were sampled by a seeded identifier hash among {q['eligible_facilities']} facilities with at least {c['eligibility_coverage']:.0%} valid training dates. This is an engineering cohort, not a representative state survey.

![Staffing patterns](figures/eda_patterns.png)

Average daily RN/LPN/CNA contract hours were **{stats['training_contract_daily_mean']:.1f}** versus **{stats['training_employee_daily_mean']:.1f} employee hours**. Reported daily contract zeros comprised **{zero:.1%}** of valid training days; complete seven-day targets were zero **{weekly_zero:.1%}** of the time. The 99th percentile was {stats['training_daily_contract_p99']:.1f} hours and the maximum was {stats['training_daily_contract_max']:.1f} hours. Extreme positive observations were retained and exported for review. No outcome clipping or test-driven exclusions were applied.

The pooled census/contract-hours correlation was **{corr:.3f}**. Facility size and staffing mix confound this association: it is descriptive, not causal. Historical census is included as context. Future census is unavailable to prediction.

![Facility differences](figures/facility_variation.png)

The monthly and weekday plots motivate trailing summaries and calendar features. Only nine training months are available at initial eligibility, so the EDA does not establish repeatable annual seasonality. Full training later expands chronologically. Strong facility differences motivate facility indicators and training-defined volume groups. Zero-heavy behavior motivates absolute-error loss and a strong persistence baseline.

## Data quality and coverage audit (all quarters, descriptive)

There are {q['unique_state_rows']:,} unique state source records and {q['expected_facility_days']:,} expected selected facility-days. Of these, {q['reported_days']:,} are reported, {q['missing_dates']:,} are missing dates, and {q['invalid_contract_days']:,} reported days have invalid contract targets. Validation found {q['negative_hours']} negative-hour rows, {q['component_mismatch']} total/component mismatches, and {q['missing_hours']} rows with missing hours among selected facilities. Full calendar coverage by quarter is in `quarter_coverage.csv`; no future coverage was used to replace selected facilities.

Missing observations stay null; reported zeros stay zero. Missing source quarters can reflect CMS inclusion/exclusion criteria, closure, or reporting changes; these data alone cannot distinguish causes. Modeling requires 28 valid contract history days and seven observed outcome days. Missing employee/census predictors use training-only median imputation plus missing indicators. Quarterly schemas are recorded in the manifest; current source column definitions were consistent across the downloaded files.

Sources and interpretation: [CMS dataset]({CMS}); see `docs/SOURCES.md` and `data/manifest.json`. Source data are quarterly releases, not an operational daily feed. The modeled hours do not establish unmet demand or clinically appropriate staffing.
"""
    (report / "EDA.md").write_text(eda, encoding="utf-8")
    evaluation = f"""# Backtesting report

## Design fixed before test evaluation

- Initial facility eligibility ends {c['initial_train_end']}.
- Expanding validation origins: {c['validation']}. Each fit uses only labels ending before the next validation origin.
- Four histogram gradient-boosting candidates: leaf counts 7/15 × L2 1/10, absolute-error loss, 180 iterations, learning rate 0.06. No random early-stopping split. Preprocessing is refit only on each training prefix.
- Final point fit cutoff: **{c['fit_cutoff']}**, {meta['training_n']:,} examples; origins {meta['training_origin_start']}–{meta['training_origin_end']}.
- Separate calibration: {meta['calibration_origins'][0]}–{meta['calibration_origins'][1]}, {meta['calibration_n']:,} facility-origins, every seventh day. Last calibration label ends {meta['calibration_target_end']}.
- Untouched test origins: **{c['test'][0]}–{c['test'][1]}**, each predicting T+1…T+7. Frozen models are not refitted on calibration or test data.

## Model selection from validation only

{table(validation[['model','n','mae_hours','wape','signed_error_hours']])}

Selected model: **{meta['selected_model']}** (candidate {meta['selected_validation_candidate']}). The best gradient candidate was {meta['gradient_candidate']} with {meta['gradient_parameters']}. The selected model is retained even if a different method happens to score better on the final test.

## Final test results

{table(metric[['model','n','mae_hours','wape','signed_error_hours','coverage','mean_width_hours']])}

![Accuracy and coverage](figures/backtest.png)

MAE is mean absolute forecast error in seven-day contract hours. WAPE is sum absolute error divided by sum absolute actual hours; a zero denominator yields N/A, even if all predictions are zero. Signed error is prediction minus actual: positive means overprediction. Coverage is the fraction inside inclusive interval endpoints. Width is upper minus lower. Samples are pooled facility-origins; daily origins have overlapping outcome windows, so counts are not independent observations and summed actuals repeat hours across forecasts. These totals must not be interpreted as unique labor volume.

Expected facility-origins: **{bt['expected_test_facility_origins']:,}**; forecastable: **{bt['forecastable_origins']:,}**; evaluable: **{bt['evaluated_origins']:,}**; issued forecasts with unknown outcomes: **{bt['unobserved_outcomes']:,}**. Accuracy and coverage are conditional on evaluable data. See `facility_metrics.csv`, `volume_metrics.csv`, and `nonoverlap_test_metrics.csv` for facility, training-volume and weekly-origin sensitivity analyses.

Selected-model performance by initial-training staffing-volume group:

{table(selected_volumes[['volume_group','n','mae_hours','wape','coverage','mean_width_hours']])}

Pooled accuracy can conceal much higher relative errors or lower interval coverage in individual volume groups. The groups are descriptive, fixed using training data, and not a basis for post-test model switching.

## Intervals

The 90% interval uses the finite-sample quantile of |actual − prediction| / (1 + preceding-seven-day hours), computed on earlier calibration data separately for each fitted model. Forecast bounds are max(0, prediction − q×scale) and prediction + q×scale. The lower truncation respects the nonnegative outcome. No residuals from the test period enter calibration. Temporal and facility dependence, revised source data, reporting exclusions and distribution changes violate simple exchangeability assumptions; nominal coverage is a target, not a guarantee. Facility intervals are not additive portfolio confidence intervals.

## Representative failures (selected model, final test)

{table(failures[['facility','origin','prediction','actual','lower','upper','absolute_error']].head(6))}

These are measured large errors, not selected successes. Abrupt shifts in contract use, zero-to-positive transitions and unusual staffing reports can overwhelm recent-history predictors. This dataset cannot identify their operational causes. Use analyst review, inspect recent staffing, and withhold a forecast when its input history is incomplete. The system is unsuitable for clinical staffing adequacy, unmet demand estimation, staffing mandates, cost-saving claims, or decisions at facilities outside the evaluated domain.

{failure_note}

All values can be recomputed from immutable `test_forecasts.parquet`, separate `test_outcomes.parquet`, and `evaluation.parquet`. Validation and calibration predictions retain their own split/model identifiers.
"""
    (report / "BACKTEST.md").write_text(evaluation, encoding="utf-8")
    result_phrase = f"{meta['selected_model']} achieved {selected.mae_hours:.1f} hours MAE and {selected.wape:.1%} WAPE across {int(selected.n):,} evaluable facility-origins"
    brief = f"""# Healthcare Workforce Staffing Forecasting System

**Executive brief · Independent portfolio project · Historical replay**

**Purpose.** Help a workforce planning analyst review the next seven days of observed contract RN, LPN and CNA utilization for nursing homes, with uncertainty and reliability indicators. This is a local demonstration using public CMS data, not an Ascension implementation or professional employment.

**Evidence.** The project preserved eight CMS quarters ({c['start']}–{c['end']}) and selected {len(facilities)} {c['state']} facilities using early training coverage and a deterministic sample. The untouched test covers forecast origins {c['test'][0]}–{c['test'][1]}. The selected **{result_phrase}**. Signed error was **{selected.signed_error_hours:+.1f} hours**, where positive means overprediction. The preceding-seven-day baseline achieved {baseline.mae_hours:.1f} hours MAE.

**Uncertainty.** Earlier, separate calibration targeted 90% intervals. Held-out coverage was **{selected.coverage:.1%}**, with mean interval width **{selected.mean_width_hours:.1f} hours**. Interval reliability varies by facility and operating conditions; the display supports review rather than a coverage promise.

**Coverage.** {bt['forecastable_origins']:,} of {bt['expected_test_facility_origins']:,} expected test facility-origins had sufficient history. {bt['evaluated_origins']:,} had complete realized targets. Missing or excluded records remain missing, and true reported zeros are retained.

**What works.** A rerunnable local Python/SQL pipeline, saved models, immutable forecasts with separate actuals, a Streamlit dashboard, and configurable alerts for completeness, freshness, failed jobs, distribution shifts and realized errors. Alerts do not retrain or deploy models. Verification status is recorded in `VERIFICATION.md`.

**Boundaries and next step.** CMS releases data quarterly. Daily availability, including historical census, is an explicit replay assumption, not verified operational availability. These nursing-home data do not reveal unmet staffing demand, clinically appropriate staffing or achievable savings. Cloud Run, Cloud Storage and BigQuery deployment preparation is included; cloud execution is unverified. Before operational use, validate source arrival timing and revisions, evaluate prospective forecasts, and review facility-level failures with workforce analysts.
"""
    (report / "EXECUTIVE_BRIEF.md").write_text(brief, encoding="utf-8")
    paragraphs = brief.split("\n\n")
    brief_html = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Executive brief</title><style>@page{size:letter;margin:.65in}body{font:11pt/1.4 Arial;color:#18334b;max-width:7.2in;margin:30px auto}h1{font-size:23pt;color:#126e82}p{margin:12px 0}strong{color:#126e82}</style><body>'
    import re
    for paragraph in paragraphs:
        escaped = html.escape(paragraph)
        escaped = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", escaped)
        brief_html += f"<h1>{escaped[2:]}</h1>" if paragraph.startswith("# ") else f"<p>{escaped}</p>"
    (report / "EXECUTIVE_BRIEF.html").write_text(brief_html + "</body></html>", encoding="utf-8")
    (report / "RESUME_OPTIONS.md").write_text(f"""# Resume bullet options

Use under **Independent Projects**, not employment. Choose wording that fits the rest of the resume.

- Built an independent healthcare workforce forecasting portfolio in Python, DuckDB and Streamlit using eight quarters of public CMS nursing-home staffing data and {len(facilities)} training-selected {c['state']} facilities.
- Implemented leakage-safe expanding-window validation, baseline comparison and separate interval calibration; the selected {result_phrase}, with {selected.coverage:.1%} held-out coverage for nominal 90% intervals.
- Developed a local historical replay with immutable forecasts, data-quality checks, configurable drift/error alerts and GCP deployment configuration; cloud deployment has not been executed or verified.

No professional employment, Ascension implementation, production users, savings, retention impact or verified cloud deployment is claimed.
""", encoding="utf-8")
    return {"reports": str(report), "selected_model": meta["selected_model"], "mae_hours": float(selected.mae_hours), "wape": float(selected.wape), "coverage": float(selected.coverage)}
