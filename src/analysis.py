"""SQL analysis, forecast and charts. Run after clean.py.
Writes charts/*.png and data/processed/*.csv summary tables, and prints key findings."""
import json, sqlite3, pathlib, warnings
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mt
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC, CH = ROOT / "data" / "processed", ROOT / "charts"
CH.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": .3, "font.size": 10})
NHS_BLUE, NHS_DARK, RED = "#005EB8", "#003087", "#DA291C"

ts = pd.read_csv(PROC / "national_timeseries.csv", parse_dates=["month"])
ps = pd.read_csv(PROC / "provider_specialty.csv")
con = sqlite3.connect(":memory:")
ts.assign(month=ts.month.dt.strftime("%Y-%m")).to_sql("national", con)
ps.to_sql("rtt", con)
q = lambda sql: pd.read_sql(sql, con)
F = {}

# 1. National trend since 2019 ------------------------------------------------
nat = ts[ts.month >= "2019-01-01"]
latest, base = nat.iloc[-1], nat[nat.month == "2019-08-01"].iloc[0]
peak = nat.loc[nat.waiting_list.idxmax()]
F.update(latest_month=latest.month.strftime("%B %Y"),
         waiting_latest=int(latest.waiting_list), waiting_aug19=int(base.waiting_list),
         waiting_growth_pct=round((latest.waiting_list / base.waiting_list - 1) * 100, 1),
         peak_month=peak.month.strftime("%B %Y"), peak_waiting=int(peak.waiting_list),
         pct18_latest=round(latest.pct_within_18wks, 1), pct18_aug19=round(base.pct_within_18wks, 1),
         over52_latest=int(latest.over_52wks), over52_aug19=int(base.over_52wks),
         over52_peak=int(nat.over_52wks.max()),
         over52_peak_month=nat.loc[nat.over_52wks.idxmax(), "month"].strftime("%B %Y"),
         median_latest=round(latest.median_wait_wks, 1), median_aug19=round(base.median_wait_wks, 1),
         last_time_92pct=ts.loc[ts.pct_within_18wks >= 92, "month"].max().strftime("%B %Y"))

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(nat.month, nat.waiting_list / 1e6, color=NHS_BLUE, lw=2.2)
ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2021-03-01"), color="grey", alpha=.12)
ax.text(pd.Timestamp("2020-04-01"), nat.waiting_list.max() / 1e6 * .97, "COVID-19 first year", fontsize=8)
ax.axvline(pd.Timestamp("2024-02-01"), color="grey", ls=":", lw=1)
ax.text(pd.Timestamp("2024-03-01"), 4.6, "Community services\nremoved from RTT", fontsize=8)
ax.set(title="RTT waiting list, England (incomplete pathways, millions)", ylabel="Millions")
fig.tight_layout(); fig.savefig(CH / "01_waiting_list_trend.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(nat.month, nat.pct_within_18wks, color=NHS_BLUE, lw=2.2, label="% waiting < 18 weeks")
ax.axhline(92, color=RED, ls="--", label="92% constitutional standard")
ax.axhline(65, color="grey", ls=":", label="65% interim target (Mar 2026)")
ax.yaxis.set_major_formatter(mt.PercentFormatter())
ax.set(title="18-week performance, England", ylim=(40, 100)); ax.legend(loc="lower left")
fig.tight_layout(); fig.savefig(CH / "02_18_week_performance.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.bar(nat.month, nat.over_52wks / 1e3, width=25, color=NHS_DARK)
ax.set(title="Patients waiting over 52 weeks, England (thousands)", ylabel="Thousands")
fig.tight_layout(); fig.savefig(CH / "03_over_52_weeks.png"); plt.close(fig)

# 2. Demand vs activity (backlog drivers) --------------------------------------
dv = nat[nat.month >= "2021-04-01"].set_index("month")[["new_rtt_periods", "completed_pathways"]].rolling(3).mean()
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(dv.index, dv.new_rtt_periods / 1e6, label="New referrals (clock starts)", color=RED)
ax.plot(dv.index, dv.completed_pathways / 1e6, label="Completed pathways (treated)", color=NHS_BLUE)
ax.set(title="Demand vs activity, 3-month rolling average (millions per month)"); ax.legend()
fig.tight_layout(); fig.savefig(CH / "04_demand_vs_activity.png"); plt.close(fig)

# 3. Specialty comparison (SQL) ------------------------------------------------
spec = q("""
SELECT specialty_code, specialty, SUM(waiting) AS waiting,
       ROUND(100.0*SUM(within_18wks)/SUM(waiting),1) AS pct_within_18wks,
       SUM(over_52wks) AS over_52wks
FROM rtt WHERE period='2026-08' GROUP BY specialty_code, specialty ORDER BY waiting DESC""")
spec.to_csv(PROC / "specialty_aug26.csv", index=False)
s19 = q("""SELECT specialty_code, ROUND(100.0*SUM(within_18wks)/SUM(waiting),1) AS pct19
           FROM rtt WHERE period='2019-08' GROUP BY specialty_code""")
spec_c = spec.merge(s19, on="specialty_code", how="left")
F["largest_specialties"] = spec.head(3)[["specialty", "waiting", "pct_within_18wks"]].to_dict("records")
F["worst_specialties"] = spec[spec.waiting > 100000].nsmallest(3, "pct_within_18wks")[["specialty", "pct_within_18wks"]].to_dict("records")
top = spec_c.head(15).iloc[::-1]
fig, axs = plt.subplots(1, 2, figsize=(12, 6), sharey=True)
axs[0].barh(top.specialty, top.waiting / 1e3, color=NHS_BLUE); axs[0].set_title("Waiting list (thousands)")
axs[1].barh(top.specialty, top.pct_within_18wks, color=NHS_DARK, label="Aug 2026")
tt = top.dropna(subset=["pct19"]); axs[1].scatter(tt.pct19, tt.specialty, color=RED, zorder=3, label="Aug 2019")
axs[1].axvline(92, color=RED, ls="--", lw=1); axs[1].set_title("% within 18 weeks"); axs[1].legend(loc="lower right")
fig.suptitle("15 largest specialties, England, August 2026 (provider basis)")
fig.tight_layout(); fig.savefig(CH / "05_specialties.png"); plt.close(fig)

# 4. ICB / London comparison (SQL) ---------------------------------------------
icb = q("""
SELECT icb, london, SUM(waiting) AS waiting,
       ROUND(100.0*SUM(within_18wks)/SUM(waiting),1) AS pct_within_18wks,
       SUM(over_52wks) AS over_52wks,
       ROUND(100.0*SUM(over_52wks)/SUM(waiting),2) AS pct_over_52wks
FROM rtt WHERE period='2026-08' GROUP BY icb, london ORDER BY pct_within_18wks DESC""")
icb.to_csv(PROC / "icb_aug26.csv", index=False)
reg = q("""SELECT period, CASE WHEN london THEN 'London' ELSE 'Rest of England' END AS area,
           SUM(waiting) AS waiting, ROUND(100.0*SUM(within_18wks)/SUM(waiting),1) AS pct_within_18wks,
           SUM(over_52wks) AS over_52wks FROM rtt GROUP BY 1,2 ORDER BY 1,2""")
reg.to_csv(PROC / "london_vs_rest.csv", index=False)
F["london_vs_rest"] = reg.to_dict("records")
F["icb_rank_london"] = {r.icb: int(i) + 1 for i, r in icb.reset_index(drop=True).iterrows() if r.london}
F["n_icbs"] = len(icb)
F["best_icb"], F["worst_icb"] = icb.iloc[0][["icb", "pct_within_18wks"]].tolist(), icb.iloc[-1][["icb", "pct_within_18wks"]].tolist()
d = icb.iloc[::-1]
fig, ax = plt.subplots(figsize=(9, 9))
ax.barh(d.icb.str.replace("NHS ", ""), d.pct_within_18wks, color=[RED if l else "#A0AEC0" for l in d.london])
ax.axvline(92, color=RED, ls="--", lw=1); ax.xaxis.set_major_formatter(mt.PercentFormatter())
ax.set(title="% waiting under 18 weeks by provider ICB, Aug 2026 (London in red)", xlim=(40, 100))
fig.tight_layout(); fig.savefig(CH / "06_icb_comparison.png"); plt.close(fig)

# 5. London trusts -------------------------------------------------------------
lt = q("""
SELECT a.provider_code, a.provider_name, a.icb, a.waiting, a.pct_within_18wks, a.over_52wks,
       b.pct_within_18wks AS pct_within_18wks_2019, b.waiting AS waiting_2019
FROM (SELECT provider_code, provider_name, icb, SUM(waiting) waiting,
             ROUND(100.0*SUM(within_18wks)/SUM(waiting),1) pct_within_18wks, SUM(over_52wks) over_52wks
      FROM rtt WHERE period='2026-08' AND london GROUP BY 1,2,3) a
LEFT JOIN (SELECT provider_code, SUM(waiting) waiting,
             ROUND(100.0*SUM(within_18wks)/SUM(waiting),1) pct_within_18wks
      FROM rtt WHERE period='2019-08' GROUP BY 1) b USING (provider_code)
WHERE a.waiting >= 20000 ORDER BY a.waiting DESC""")
lt.to_csv(PROC / "london_trusts_aug26.csv", index=False)
F["london_trusts"] = lt[["provider_name", "waiting", "pct_within_18wks", "pct_within_18wks_2019", "over_52wks"]].to_dict("records")
d = lt.sort_values("pct_within_18wks")
fig, ax = plt.subplots(figsize=(10, 7))
nm = d.provider_name.str.title().str.replace(" Nhs Foundation Trust", "").str.replace(" Nhs Trust", "")
ax.hlines(nm, d.pct_within_18wks_2019, d.pct_within_18wks, color="#A0AEC0")
ax.scatter(d.pct_within_18wks_2019, nm, color="#A0AEC0", label="Aug 2019", zorder=3)
ax.scatter(d.pct_within_18wks, nm, color=NHS_BLUE, label="Aug 2026", zorder=3)
ax.axvline(92, color=RED, ls="--", lw=1); ax.xaxis.set_major_formatter(mt.PercentFormatter()); ax.legend()
ax.set(title="London trusts (20k+ waiting): % within 18 weeks, 2019 vs 2026")
fig.tight_layout(); fig.savefig(CH / "07_london_trusts.png"); plt.close(fig)

# 6. Forecast ------------------------------------------------------------------
# Fit on Mar 2024 onward (after community services left the RTT dataset, a definitional break).
y = ts.set_index("month").waiting_list[ts.month.values >= pd.Timestamp("2024-03-01")].asfreq("MS")
H = 6
bt = ExponentialSmoothing(y[:-H], trend="add", damped_trend=True).fit()
mape = float((abs(bt.forecast(H).values - y[-H:].values) / y[-H:].values).mean() * 100)
m = ExponentialSmoothing(y, trend="add", damped_trend=True).fit()
fc = m.forecast(12)
resid_sd = float((y - m.fittedvalues).std())
lo, hi = fc - 1.96 * resid_sd * (1 + pd.Series(range(12), index=fc.index) ** .5 * .3), \
         fc + 1.96 * resid_sd * (1 + pd.Series(range(12), index=fc.index) ** .5 * .3)
pd.DataFrame({"month": fc.index, "forecast": fc.round(), "lower": lo.round(), "upper": hi.round()}).to_csv(PROC / "forecast.csv", index=False)
F.update(forecast_month=fc.index[-1].strftime("%B %Y"), forecast_value=int(fc.iloc[-1]),
         forecast_lo=int(lo.iloc[-1]), forecast_hi=int(hi.iloc[-1]), backtest_mape_6m=round(mape, 2))
fig, ax = plt.subplots(figsize=(10, 4.5))
hist = ts[ts.month >= "2022-01-01"]
ax.plot(hist.month, hist.waiting_list / 1e6, color=NHS_BLUE, lw=2, label="Actual")
ax.plot(fc.index, fc / 1e6, color=RED, lw=2, ls="--", label="Forecast (damped Holt)")
ax.fill_between(fc.index, lo / 1e6, hi / 1e6, color=RED, alpha=.15, label="Approx. 95% band")
ax.set(title=f"Waiting list forecast to {F['forecast_month']} (6-month backtest MAPE {mape:.1f}%)", ylabel="Millions")
ax.legend(); fig.tight_layout(); fig.savefig(CH / "08_forecast.png"); plt.close(fig)

(PROC / "key_findings.json").write_text(json.dumps(F, indent=2, default=str))
print(json.dumps(F, indent=2, default=str))
