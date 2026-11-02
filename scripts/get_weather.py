"""Download several years of hourly PV yield and air temperature for Porto from PVGIS.

Each simulation run draws one of these weather years (ODD section 6), so the
weather is a stochastic input instead of a single fixed year.

Output: data/processed/weather_porto.csv, 8,760 rows per year:
    year            weather year
    hour            hour of the (2023) model year, 0-8759, aligned with pv_porto.csv / load_btn_c.csv
    pv_kwh_per_kwp  energy produced in that hour by 1 kWp of installed PV
    temp_c          air temperature at 2 m (ERA5, as delivered by PVGIS), deg C

Every year is laid on the 2023 hourly UTC timeline by day of year and hour, so
it lines up with the 2023 load profile; in leap years 29 February is dropped.
The raw API response is kept (gzipped) in data/raw/ so the processing can be
rerun offline with --offline. The model only reads the CSV, never the API.

Usage:
    python scripts/get_weather.py [--start 2014] [--end 2023] [--offline]
"""

import argparse
import gzip
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_FILE = ROOT / "data" / "processed" / "weather_porto.csv"

API_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
LAT, LON = 41.15, -8.61  # Porto, same point, losses and angles as get_pvgis.py


def download(start: int, end: int, raw_file: Path) -> dict:
    params = {
        "lat": LAT,
        "lon": LON,
        "startyear": start,
        "endyear": end,
        "pvcalculation": 1,
        "peakpower": 1,  # 1 kWp -> per-kWp profile
        "loss": 14,  # system losses, %
        # Same panels as pv_porto.csv: the optimal angles PVGIS gives for 2023.
        # (Asking for optimal angles over several years gives 36 deg / 4 deg.)
        "angle": 35,
        "aspect": 3,
        "outputformat": "json",
    }
    resp = requests.get(API_URL, params=params, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(raw_file, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Saved raw response to {raw_file.relative_to(ROOT)}")
    return data


def process(data: dict) -> pd.DataFrame:
    hourly = pd.DataFrame(data["outputs"]["hourly"])
    # Timestamps look like "20230101:0010" (UTC); flooring gives the start of the hour.
    time_utc = pd.to_datetime(hourly["time"], format="%Y%m%d:%H%M", utc=True).dt.floor("h")
    df = pd.DataFrame({
        "time_utc": time_utc,
        "pv_kwh_per_kwp": hourly["P"] / 1000.0,  # mean W over 1 h -> kWh
        "temp_c": hourly["T2m"],
    })
    df = df[~((df["time_utc"].dt.month == 2) & (df["time_utc"].dt.day == 29))]  # leap days
    df["year"] = df["time_utc"].dt.year

    years = []
    for year, g in df.groupby("year"):
        if len(g) != 8760:
            raise ValueError(f"{year}: expected 8760 hours after dropping 29 Feb, got {len(g)}")
        g = g.sort_values("time_utc").reset_index(drop=True)
        years.append(pd.DataFrame({
            "year": year,
            "hour": range(8760),
            "pv_kwh_per_kwp": g["pv_kwh_per_kwp"],
            "temp_c": g["temp_c"],
        }))
    return pd.concat(years, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=int, default=2014, help="first year (PVGIS-SARAH3 covers 2005-2023)")
    parser.add_argument("--end", type=int, default=2023, help="last year")
    parser.add_argument("--offline", action="store_true", help="reuse the raw JSON in data/raw instead of calling the API")
    args = parser.parse_args()

    raw_file = RAW_DIR / f"pvgis_porto_{args.start}_{args.end}.json.gz"
    if args.offline:
        with gzip.open(raw_file, "rt", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = download(args.start, args.end, raw_file)

    df = process(data)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False, float_format="%.5g")

    summary = df.groupby("year").agg(pv=("pv_kwh_per_kwp", "sum"), temp=("temp_c", "mean"))
    print(f"Saved {len(df)} rows ({df['year'].nunique()} years) to {OUT_FILE.relative_to(ROOT)}")
    print(summary.round(1).to_string())


if __name__ == "__main__":
    main()
