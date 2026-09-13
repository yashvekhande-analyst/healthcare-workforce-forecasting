"""Read-only analyst dashboard. Runs locally without cloud credentials."""
import json
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Healthcare Workforce | Historical replay", page_icon="🏥", layout="wide")
ROOT = Path(__file__).resolve().parent
RUN = Path(os.environ.get("WORKFORCE_ARTIFACTS", str(ROOT / "artifacts" / "full")))
TEAL, NAVY, ORANGE = "#126E82", "#18334B", "#B55428"
st.markdown("""<style>
.stApp {background:#f6f8fb;color:#18334b}
.block-container {padding-top:3.7rem;max-width:1500px}
h1,h2,h3 {color:#18334b;letter-spacing:-.025em}
[data-testid="stSidebar"] {background:#eaf0f5}
[data-testid="stMetric"] {background:white;padding:20px;border:1px solid #dce4ed;border-radius:12px}
[data-testid="stMetricLabel"] {color:#53677c}
[data-testid="stMetricValue"] {color:#126e82}
.eyebrow {font-size:12px;font-weight:700;letter-spacing:.13em;color:#126e82}
.replay {display:inline-block;background:#fff0d7;color:#704514;border:1px solid #e3c591;border-radius:20px;padding:5px 12px;font-size:12px;font-weight:700}
.subtitle {font-size:17px;color:#52687c;max-width:950px;line-height:1.5}
.stTabs [data-baseweb="tab-list"] {gap:20px}
footer {visibility:hidden}
</style>""", unsafe_allow_html=True)


@st.cache_data
def read_parquet(path, modified):
    return pd.read_parquet(path)


def parquet(name):
    p = RUN / name
    return read_parquet(str(p), p.stat().st_mtime_ns)


def read_json(name):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def plot_style(fig, y_title, height=320):
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=10, r=10, t=30, b=10),
                      font=dict(family="Arial, sans-serif", color=NAVY),
                      legend=dict(orientation="h", y=1.12, x=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white", yaxis_title=y_title)
    return fig


def main():
    st.markdown('<span class="eyebrow">WORKFORCE INTELLIGENCE / INDEPENDENT PORTFOLIO</span>', unsafe_allow_html=True)
    st.title("Healthcare Workforce Staffing Forecasting System")
    st.markdown('<span class="replay">HISTORICAL REPLAY</span>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Review seven-day contract nursing utilization across nursing homes. Compare recent staffing, inspect uncertainty, and find forecasts that need attention.</p>', unsafe_allow_html=True)
    required = ["daily.parquet", "facilities.parquet", "test_forecasts.parquet", "evaluation.parquet", "quality.json", "models/metadata.json", "backtest_summary.json"]
    missing = [name for name in required if not (RUN / name).exists()]
    if missing:
        st.info("No completed analysis is available in this artifact folder. Fetch CMS data and run the pipeline to create real forecasts.")
        st.code("workforce --config configs/full.json fetch\nworkforce --config configs/full.json run", language="powershell")
        st.caption("Missing artifacts: " + ", ".join(missing))
        return
    daily, facilities = parquet("daily.parquet"), parquet("facilities.parquet")
    forecasts, evaluation = parquet("test_forecasts.parquet"), parquet("evaluation.parquet")
    meta, quality, backtest = read_json("models/metadata.json"), read_json("quality.json"), read_json("backtest_summary.json")
    selected_model = meta["selected_model"]
    selected_forecasts = forecasts.loc[forecasts.model == selected_model].copy()
    for p in sorted((RUN / "forecasts" / meta["version"]).glob("*.parquet")):
        extra = read_parquet(str(p), p.stat().st_mtime_ns)
        selected_forecasts = pd.concat([selected_forecasts, extra], ignore_index=True)
    selected_forecasts = selected_forecasts.drop_duplicates(["facility", "origin"], keep="first")
    st.sidebar.markdown("### Analysis controls")
    st.sidebar.caption(f"{quality['state']} · {len(facilities)} nursing homes · CMS PBJ")
    origins = sorted(selected_forecasts.origin.dt.date.unique())
    # Default to last held-out origin with realized comparisons; latest replay is also selectable.
    test_last = pd.Timestamp(backtest["test"][1]).date()
    default_index = origins.index(test_last) if test_last in origins else len(origins) - 1
    origin = pd.Timestamp(st.sidebar.selectbox("Historical forecast origin (end of day)", origins, index=default_index))
    st.sidebar.caption(f"Outcome window: {(origin + pd.Timedelta(days=1)).date()} to {(origin + pd.Timedelta(days=7)).date()}")
    volume_options = ["low", "medium", "high"]
    volume = st.sidebar.multiselect("Training staffing-volume groups", volume_options, default=volume_options)
    roster = facilities.loc[facilities.volume_group.isin(volume)].sort_values("name")
    labels = dict(zip(roster.facility, roster.facility + " · " + roster.name.str.title()))
    scope = st.sidebar.radio("Facility scope", ["All matching facilities", "Choose facilities"])
    chosen = roster.facility.tolist() if scope == "All matching facilities" else st.sidebar.multiselect("Facilities", roster.facility.tolist(), default=roster.facility.head(3).tolist(), format_func=lambda x: labels[x])
    st.sidebar.caption(f"{len(chosen)} facilities selected")
    st.sidebar.markdown("---")
    st.sidebar.caption("CMS publishes quarterly. Daily staffing and census availability are assumed for this replay. The app is read-only.")
    st.sidebar.caption(f"Selected model: {selected_model}\n\nVersion: {meta['version']}")
    if not chosen:
        st.info("No facilities selected. Choose at least one facility and a volume group in the sidebar to review forecasts.")
        return
    rows = selected_forecasts.loc[(selected_forecasts.origin == origin) & selected_forecasts.facility.isin(chosen)].copy()
    interval_pct = f"{100 * (1 - meta['alpha']):.0f}%"
    selected_eval = evaluation.loc[(evaluation.model == selected_model) & evaluation.facility.isin(chosen)]
    rollup = facilities.loc[facilities.facility.isin(chosen), ["facility", "name", "volume_group"]].merge(rows.drop(columns="volume_group"), on="facility", how="left", validate="one_to_one")
    facility_metric = pd.read_csv(RUN / "reports" / "facility_metrics.csv", dtype={"facility": str})
    historical_coverage = facility_metric.loc[facility_metric.model == selected_model].set_index("facility").coverage
    rollup["interval_width"] = rollup.upper - rollup.lower
    rollup["review_status"] = "Available"
    rollup.loc[rollup.interval_width > 2 * (rollup.prediction + 1), "review_status"] = "Wide interval — review"
    rollup.loc[rollup.facility.map(historical_coverage) < .8, "review_status"] = "Low historical coverage — review"
    rollup.loc[rollup.prediction.isna(), "review_status"] = "Withheld — incomplete history"
    overview, detail, performance, monitoring, methods = st.tabs(["Portfolio overview", "Facility detail", "Model evaluation", "Data quality & monitoring", "Methodology & sources"])
    with overview:
        st.subheader(f"Seven-day outlook · {(origin + pd.Timedelta(days=1)).strftime('%b %d')}–{(origin + pd.Timedelta(days=7)).strftime('%b %d, %Y')}")
        cols = st.columns(4)
        cols[0].metric("Forecast · next 7 days", f"{rows.prediction.sum():,.0f} h" if len(rows) else "Unavailable")
        cols[1].metric("Actual · prior 7 days", f"{rows.previous_7.sum():,.0f} h" if len(rows) else "Unavailable")
        cols[2].metric("Forecast coverage", f"{len(rows)} / {len(chosen)}")
        cols[3].metric("Needs review", str(rollup.review_status.ne("Available").sum()))
        st.caption("All staffing values above are contract RN + LPN + CNA hours. Coverage is the number of forecastable facilities out of the selected cohort.")
        st.caption("Portfolio totals include only facilities with sufficient history. Uncertainty intervals below apply to individual facilities; they are not a joint portfolio interval. Review status uses retrospective test coverage and interval width, not information available at the historical origin.")
        if len(rows) < len(chosen):
            missing_count = len(chosen) - len(rows)
            st.warning(f"Forecasts withheld for {missing_count} selected {'facility' if missing_count == 1 else 'facilities'}: 28 complete history days are unavailable.")
        st.markdown("#### Facility forecast review")
        show = rollup[["facility", "name", "prediction", "lower", "upper", "previous_7", "review_status"]].rename(columns={"facility": "CMS ID", "name": "Nursing home", "prediction": "Next 7 days (h)", "lower": f"{interval_pct} lower (h)", "upper": f"{interval_pct} upper (h)", "previous_7": "Previous 7 days (h)", "review_status": "Review status"})
        st.dataframe(show, use_container_width=True, hide_index=True, height=360,
                     column_config={col: st.column_config.NumberColumn(format="%.1f") for col in ["Next 7 days (h)", f"{interval_pct} lower (h)", f"{interval_pct} upper (h)", "Previous 7 days (h)"]})
        download = rollup.copy()
        download["selected_origin"] = origin
        st.download_button("Download selected forecasts (CSV)", download.to_csv(index=False).encode("utf-8"), file_name=f"contract_forecasts_{origin.date()}.csv", mime="text/csv")
        st.markdown("#### Recent observed staffing")
        recent = daily.loc[daily.facility.isin(rows.facility) & daily.date.between(origin - pd.Timedelta(days=55), origin)]
        if recent.empty:
            st.info("No complete forecast history is available for the selected facilities.")
        else:
            summed = recent.groupby("date")[["contract_hours", "employee_hours"]].sum(min_count=len(rows)).reset_index()
            summed = summed.rename(columns={"contract_hours": "Contract", "employee_hours": "Employee"})
            fig = px.line(summed, x="date", y=["Contract", "Employee"], color_discrete_sequence=[TEAL, ORANGE], labels={"date": "Work date", "variable": "RN + LPN + CNA"})
            st.plotly_chart(plot_style(fig, "Observed hours / day"), use_container_width=True)
            st.caption(f"Daily actuals through the origin for the same {len(rows)} forecastable facilities. Withheld facilities are excluded explicitly. Gaps indicate missing hours within this fixed subset; daily totals are never silently reduced.")
    with detail:
        facility = st.selectbox("Inspect one facility", chosen, format_func=lambda x: labels[x])
        facility_rows = rollup.loc[rollup.facility == facility]
        r = facility_rows.iloc[0]
        st.subheader(str(r['name']).title())
        st.caption(f"CMS {facility} · training-volume group: {r.volume_group} · {r.review_status}")
        if pd.isna(r.prediction):
            st.warning("Forecast unavailable: the preceding 28 calendar days do not contain complete contract staffing observations.")
        else:
            a, b, d = st.columns(3)
            a.metric("Next 7 calendar days", f"{r.prediction:,.1f} h")
            b.metric(f"Nominal {interval_pct} interval", f"{r.lower:,.1f}–{r.upper:,.1f} h")
            d.metric("Previous 7 calendar days", f"{r.previous_7:,.1f} h")
        history = selected_eval.loc[(selected_eval.facility == facility) & (selected_eval.origin <= origin)].sort_values("origin")
        reveal = st.toggle("Show subsequently observed outcomes (retrospective)", value=True)
        if history.empty:
            st.info("No evaluated forecasts are available for this facility and origin.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=history.origin, y=history.upper, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=history.origin, y=history.lower, mode="lines", fill="tonexty", fillcolor="rgba(18,110,130,.14)", line=dict(width=0), name=f"Nominal {interval_pct} interval"))
            fig.add_trace(go.Scatter(x=history.origin, y=history.prediction, mode="lines", name="Forecast", line=dict(color=TEAL, width=2)))
            if reveal:
                fig.add_trace(go.Scatter(x=history.origin, y=history.actual, mode="lines", name="Subsequently observed outcome", line=dict(color=ORANGE, width=2)))
            st.plotly_chart(plot_style(fig, "Total contract hours in T+1…T+7", 400), use_container_width=True)
            st.caption("X-axis: forecast origin T. Each point is a seven-day total, not daily hours. Actual outcomes were observed after the origin and were never used as predictors.")
        recent = daily.loc[(daily.facility == facility) & daily.date.between(origin - pd.Timedelta(days=55), origin)]
        fig = px.bar(recent, x="date", y=["rn_contract", "lpn_contract", "cna_contract"], color_discrete_sequence=[TEAL, "#7674A9", ORANGE], labels={"variable": "Contract role", "date": "Work date"})
        st.plotly_chart(plot_style(fig, "Reported contract hours / day"), use_container_width=True)
    with performance:
        st.subheader("Held-out model evaluation")
        st.caption(f"Fixed full cohort · origins {backtest['test'][0]} through {backtest['test'][1]} · {backtest['evaluated_origins']:,} evaluable facility-origins. Sidebar facility filters do not change model selection or this cohort-level benchmark.")
        scores = pd.read_csv(RUN / "reports" / "test_metrics.csv")
        st.dataframe(scores[["model", "n", "mae_hours", "wape", "signed_error_hours", "coverage", "mean_width_hours"]], hide_index=True, use_container_width=True,
                     column_config={"wape": st.column_config.NumberColumn("WAPE (fraction)", format="%.3f"), "coverage": st.column_config.NumberColumn("Interval coverage (fraction)", format="%.3f")})
        st.info(f"Selected using validation MAE: {selected_model}. The test period was excluded from tuning, selection and calibration.")
        fig = px.bar(scores, x="mae_hours", y="model", orientation="h", color="model", color_discrete_sequence=[TEAL, ORANGE, "#65758B"])
        st.plotly_chart(plot_style(fig, "Model", 280).update_layout(xaxis_title="MAE · seven-day contract hours", showlegend=False), use_container_width=True)
        st.markdown("#### Error by training staffing-volume group")
        st.dataframe(pd.read_csv(RUN / "reports" / "volume_metrics.csv"), hide_index=True, use_container_width=True)
        st.markdown("#### Representative failures")
        st.dataframe(pd.read_csv(RUN / "reports" / "representative_failures.csv", dtype={"facility": str}).head(6)[["facility", "origin", "prediction", "actual", "lower", "upper", "absolute_error"]], hide_index=True, use_container_width=True)
        st.caption("Positive signed error means overprediction. WAPE is undefined when total actual hours are zero. Overlapping daily targets are not independent samples. Interval widths are in seven-day contract hours.")
        st.download_button("Download model evaluation (CSV)", scores.to_csv(index=False), "test_metrics.csv", "text/csv")
    with monitoring:
        st.subheader("Coverage and reliability")
        a, b, d = st.columns(3)
        a.metric("Source coverage", f"{quality['reported_days'] / quality['expected_facility_days']:.1%}")
        b.metric("Missing facility-days", f"{quality['missing_dates']:,}")
        d.metric("Invalid reported contract days", f"{quality['invalid_contract_days']:,}")
        st.dataframe(pd.read_csv(RUN / "reports" / "quarter_coverage.csv"), hide_index=True, use_container_width=True)
        demo = st.toggle("Show alert demonstration — TEST SCENARIO", value=False)
        monitor_file = "monitoring_demo.json" if demo else "monitoring.json"
        if (RUN / monitor_file).exists():
            status = read_json(monitor_file)
            st.markdown(f"#### {status['status']} · as of {status['asof']}")
            st.caption(status["mode"] + ". Monitoring uses the replay clock and the full cohort, independently of the selected origin.")
            if demo:
                st.warning("TEST SCENARIO: missing input, stale dates, feature shifts and a failed job were injected into copies. Source records, model and forecasts are unchanged.")
            if status["alerts"]:
                for alert in status["alerts"]:
                    st.warning(f"{alert['check']} — {alert['action']}")
            else:
                st.success("No configured thresholds exceeded at this replay date.")
            with st.expander("Measurements and thresholds"):
                st.json(status)
        else:
            st.info("Monitoring has not run. Use the monitor command with a replay date.")
        st.caption("Alerts trigger analyst review. No automatic model retraining or deployment occurs.")
    with methods:
        st.subheader("What this forecast means")
        st.markdown("**Target:** the sum of reported contract RN, LPN and CNA hours for each facility during the seven calendar days after the selected origin. This is observed contract staffing utilization. It does not establish unmet staffing demand, clinically appropriate staffing or achievable cost savings.")
        st.markdown("**Availability:** CMS publishes the public files quarterly. This historical replay assumes an internal end-of-day feed for staffing and historical census; operational arrival timing and retrospective revisions have not been verified.")
        st.markdown("**Leakage controls:** calendar-aligned history only; complete seven-day labels at training cutoffs; training-only facility selection and preprocessing; expanding validation; separate calibration; untouched final test.")
        st.markdown("**Intervals:** scaled absolute calibration residuals produce nonnegative nominal 90% intervals. Every seventh calibration origin avoids overlapping weekly labels within a facility. Time-series shifts and dependence can reduce coverage. Individual-facility bounds do not form a portfolio interval.")
        st.markdown("**Missingness:** reported zeros remain zero. Missing or excluded observations stay missing. The app withholds forecasts without 28 complete contract-history days; evaluation requires seven observed future days.")
        st.markdown("**Independent portfolio:** implemented locally for demonstration. No Ascension affiliation, professional employment, production customer use or verified cloud deployment is claimed.")
        st.markdown("[CMS dataset](https://data.cms.gov/quality-of-care/payroll-based-journal-daily-nurse-staffing) · [Current dictionary](https://data.cms.gov/sites/default/files/2023-06/Payroll%20Based%20Journal%20Daily%20Nursing%20Staffing%20Data%20Dictionary.pdf) · [Methodology](https://data.cms.gov/sites/default/files/2023-06/PBJ_PUF_Documentation_July_2023.pdf)")
        st.caption("Download locations verified against the CMS catalog on September 13, 2026. The checked release spans April 2024–March 2026. Source URLs, exact retrieval timestamps, checksums, schemas and transformations are in data/manifest.json.")


main()
