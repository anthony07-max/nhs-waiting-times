"""Streamlit dashboard: NHS England RTT waiting times. Run: streamlit run app/streamlit_app.py"""
import json, pathlib
import pandas as pd, plotly.express as px, plotly.graph_objects as go, streamlit as st

P = pathlib.Path(__file__).resolve().parents[1] / "data" / "processed"
st.set_page_config(page_title="NHS Waiting Times", layout="wide")

@st.cache_data
def load():
    ts = pd.read_csv(P / "national_timeseries.csv", parse_dates=["month"])
    return (ts, pd.read_csv(P / "provider_specialty.csv"), pd.read_csv(P / "forecast.csv", parse_dates=["month"]),
            json.loads((P / "key_findings.json").read_text()))
ts, ps, fc, F = load()

st.title("NHS England Referral to Treatment (RTT) waiting times")
st.caption(f"Public NHS England statistics, latest month {F['latest_month']}. Built by Anthony Adusei-Poku (github.com/anthony07-max).")
c = st.columns(4)
c[0].metric("Waiting list", f"{F['waiting_latest']/1e6:.2f}m", f"{F['waiting_growth_pct']:+.1f}% vs Aug 2019", delta_color="inverse")
c[1].metric("% within 18 weeks", f"{F['pct18_latest']}%", f"{F['pct18_latest']-F['pct18_aug19']:+.1f} pts vs Aug 2019")
c[2].metric("Waiting 52+ weeks", f"{F['over52_latest']:,}", f"peak {F['over52_peak']:,} ({F['over52_peak_month']})", delta_color="off")
c[3].metric("Median wait", f"{F['median_latest']} wks", f"{F['median_latest']-F['median_aug19']:+.1f} wks vs Aug 2019", delta_color="inverse")

t1, t2, t3, t4 = st.tabs(["National trend", "Specialties", "Regions & London", "Forecast"])
with t1:
    start = st.slider("From year", 2008, 2026, 2019)
    d = ts[ts.month.dt.year >= start]
    metric = st.selectbox("Metric", ["waiting_list", "pct_within_18wks", "over_52wks", "median_wait_wks", "new_rtt_periods", "completed_pathways"])
    fig = px.line(d, x="month", y=metric)
    if metric == "pct_within_18wks":
        fig.add_hline(y=92, line_dash="dash", line_color="red", annotation_text="92% standard")
    st.plotly_chart(fig, width="stretch")
with t2:
    s = ps[ps.period == "2026-08"].groupby("specialty", as_index=False)[["waiting", "within_18wks", "over_52wks"]].sum()
    s["pct_within_18wks"] = (100 * s.within_18wks / s.waiting).round(1)
    london_only = st.checkbox("London providers only")
    if london_only:
        s = ps[(ps.period == "2026-08") & ps.london].groupby("specialty", as_index=False)[["waiting", "within_18wks", "over_52wks"]].sum()
        s["pct_within_18wks"] = (100 * s.within_18wks / s.waiting).round(1)
    st.plotly_chart(px.scatter(s, x="waiting", y="pct_within_18wks", size="over_52wks", hover_name="specialty",
                               title="Specialty size vs 18-week performance (bubble = 52+ week waiters)"), width="stretch")
    st.dataframe(s.sort_values("waiting", ascending=False), width="stretch", hide_index=True)
with t3:
    i = ps[ps.period == "2026-08"].groupby(["icb", "london"], as_index=False)[["waiting", "within_18wks", "over_52wks"]].sum()
    i["pct_within_18wks"] = (100 * i.within_18wks / i.waiting).round(1)
    i = i.sort_values("pct_within_18wks")
    st.plotly_chart(px.bar(i, x="pct_within_18wks", y="icb", color="london", orientation="h", height=800,
                           title="% within 18 weeks by provider ICB, Aug 2026"), width="stretch")
    st.subheader("London trusts")
    lt = pd.read_csv(P / "london_trusts_aug26.csv")
    st.dataframe(lt, width="stretch", hide_index=True)
with t4:
    h = ts[ts.month >= "2022-01-01"]
    fig = go.Figure([go.Scatter(x=h.month, y=h.waiting_list, name="Actual"),
                     go.Scatter(x=fc.month, y=fc.forecast, name="Forecast", line=dict(dash="dash")),
                     go.Scatter(x=list(fc.month) + list(fc.month[::-1]), y=list(fc.upper) + list(fc.lower[::-1]),
                                fill="toself", opacity=.2, line=dict(width=0), name="Approx. 95% band")])
    st.plotly_chart(fig, width="stretch")
    st.write(f"Damped Holt exponential smoothing fitted on Mar 2024 onwards. 6-month backtest MAPE: {F['backtest_mape_6m']}%. "
             f"Forecast for {F['forecast_month']}: {F['forecast_value']/1e6:.2f}m.")
