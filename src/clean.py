"""Clean raw NHS England RTT files into tidy CSVs in data/processed/."""
import re, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
LONDON_ICBS = ["NORTH EAST LONDON", "NORTH CENTRAL LONDON", "SOUTH EAST LONDON",
               "SOUTH WEST LONDON", "NORTH WEST LONDON", "WEST AND NORTH LONDON"]

def clean_timeseries():
    raw = pd.read_excel(RAW / "rtt_overview_timeseries.xlsx", header=None)
    data = raw.iloc[12:].copy()
    data = data[pd.to_datetime(data[2], errors="coerce").notna()]
    cols = {2: "month", 3: "median_wait_wks", 4: "p92_wait_wks",
            8: "pct_within_18wks", 10: "over_18wks", 12: "over_52wks",
            16: "over_65wks", 18: "over_78wks", 22: "waiting_list",
            38: "new_rtt_periods", 41: "completed_pathways"}
    ts = data[list(cols)].rename(columns=cols)
    ts["month"] = pd.to_datetime(ts["month"])
    for c in ts.columns[1:]:
        ts[c] = pd.to_numeric(ts[c], errors="coerce")   # '-' = not collected
    ts = ts[ts["waiting_list"].notna()]                # drop empty future rows
    if ts["pct_within_18wks"].max() <= 1:
        ts["pct_within_18wks"] *= 100
    ts.to_csv(OUT / "national_timeseries.csv", index=False)
    return ts

def band_cols(df):
    within18, over52 = [], []
    for c in df.columns:
        m = re.match(r"Gt (\d+)", c)
        if not m:
            continue
        lo = int(m.group(1))
        if lo < 18:
            within18.append(c)
        if lo >= 52:
            over52.append(c)
    return within18, over52

def clean_extract(fname, label):
    df = pd.read_csv(RAW / fname, low_memory=False)
    df = df[df["RTT Part Type"] == "Part_2"].copy()     # incomplete pathways = waiting list
    df = df[df["Treatment Function Code"] != "C_999"]  # drop the pre-summed 'Total' rows
    w18, o52 = band_cols(df)
    df = df.assign(within_18wks=df[w18].sum(axis=1), over_52wks=df[o52].sum(axis=1),
                   waiting=df["Total All"])            # 'Total' is blank in recent files
    keep = ["Provider Parent Name", "Provider Org Code", "Provider Org Name",
            "Treatment Function Code", "Treatment Function Name",
            "waiting", "within_18wks", "over_52wks"]
    g = df[keep].groupby(keep[:5], as_index=False).sum()
    g.columns = ["provider_parent", "provider_code", "provider_name",
                 "specialty_code", "specialty", "waiting", "within_18wks", "over_52wks"]
    g["period"] = label
    return g

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ts = clean_timeseries()
    a26 = clean_extract("rtt_full_aug26.csv", "2026-08")
    a19 = clean_extract("rtt_full_aug19.csv", "2019-08")
    # London flag: in 2026 the provider parent is an ICB; in 2019 it was the NHS region
    london26 = a26["provider_parent"].str.upper().str.contains("|".join(LONDON_ICBS))
    a26["london"] = london26
    a19["london"] = a19["provider_parent"].str.upper().str.contains("LONDON")
    a26["icb"] = a26["provider_parent"].str.replace(" INTEGRATED CARE BOARD", " ICB", regex=False)
    a19["icb"] = None
    both = pd.concat([a19, a26], ignore_index=True)
    both.to_csv(OUT / "provider_specialty.csv", index=False)
    print(f"timeseries rows {len(ts)}, provider-specialty rows {len(both)}")

if __name__ == "__main__":
    main()
