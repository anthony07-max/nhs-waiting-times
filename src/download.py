"""Download public NHS England RTT waiting-times files into data/raw/.

Sources (NHS England Statistics, Consultant-led Referral to Treatment Waiting Times):
https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/
Direct file URLs are listed below. NHS England adds a suffix to each month's file
name, so when a newer month is published, update the URLs from the yearly data pages.
"""
import io, zipfile, pathlib, requests

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"
BASE = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/"
FILES = {
    # National monthly time series, April 2007 to August 2026 (commissioner basis)
    "rtt_overview_timeseries.xlsx": BASE + "2026/10/RTT-Overview-Timeseries-Including-Estimates-for-Missing-Trusts-Aug26-XLS-139K-vjgRdG.xlsx",
    # Full provider x commissioner x specialty extract, August 2026
    "rtt_full_aug26.zip": BASE + "2026/10/Full-CSV-data-file-Aug26-ZIP-3M-vjgRdG.zip",
    # Same extract for August 2019 (pre-pandemic baseline)
    "rtt_full_aug19.zip": BASE + "2020/01/Full-CSV-data-file-Aug19-ZIP-3493K-revised.zip",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (portfolio project; NHS open data)"}

def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        print("Downloading", url)
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                csv = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
                (RAW / name.replace(".zip", ".csv")).write_bytes(z.read(csv))
        else:
            (RAW / name).write_bytes(r.content)
    print("Done:", sorted(p.name for p in RAW.iterdir()))

if __name__ == "__main__":
    main()
