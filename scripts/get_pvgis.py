"""Download hourly PV yield for Porto from PVGIS and save it as an hourly CSV.

Output: data/processed/pv_porto.csv with 8,760 rows (one non-leap year):
    time_utc        start of the hour, UTC
    time_local      same instant in Europe/Lisbon legal time (with offset)
    pv_kwh_per_kwp  energy produced in that hour by 1 kWp of installed PV

The raw API response is kept in data/raw/ so the processing step can be rerun
offline with --offline. The model only reads the CSV, never the API.

Usage:
    python scripts/get_pvgis.py [--year 2023] [--offline]
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_FILE = ROOT / "data" / "processed" / "pv_porto.csv"

API_URL = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
LAT, LON = 41.15, -8.61  # Porto
LOCAL_TZ = "Europe/Lisbon"


def download(year: int, raw_file: Path) -> dict:
    params = {
        "lat": LAT,
        "lon": LON,
        "startyear": year,
        "endyear": year,
        "pvcalculation": 1,
        "peakpower": 1,  # 1 kWp -> per-kWp profile
        "loss": 14,  # system losses, %
        "optimalangles": 1,  # optimal slope and azimuth
        "outputformat": "json",
    }
    resp = requests.get(API_URL, params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(json.dumps(data), encoding="utf-8")
    print(f"Saved raw response to {raw_file.relative_to(ROOT)}")
    return data


def process(data: dict, year: int) -> pd.DataFrame:
    hourly = pd.DataFrame(data["outputs"]["hourly"])
    # Timestamps look like "20230101:0010" (UTC); the value is the hourly mean,
    # so flooring to the hour gives the start of the hour it represents.
    time_utc = pd.to_datetime(hourly["time"], format="%Y%m%d:%H%M", utc=True).dt.floor("h")

    df = pd.DataFrame({
        "time_utc": time_utc,
        "time_local": time_utc.dt.tz_convert(LOCAL_TZ),
        "pv_kwh_per_kwp": hourly["P"] / 1000.0,  # mean W over 1 h -> kWh
    })

    expected = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", tz="UTC", inclusive="left")
    if len(expected) != 8760:
        raise ValueError(f"{year} is a leap year; use a non-leap year")
    if not df["time_utc"].equals(pd.Series(expected, name="time_utc")):
        raise ValueError("PVGIS series is not a complete, ordered hourly year")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=2023, help="non-leap year (PVGIS-SARAH3 covers 2005-2023)")
    parser.add_argument("--offline", action="store_true", help="reuse the raw JSON in data/raw instead of calling the API")
    args = parser.parse_args()

    raw_file = RAW_DIR / f"pvgis_porto_{args.year}.json"
    if args.offline:
        data = json.loads(raw_file.read_text(encoding="utf-8"))
    else:
        data = download(args.year, raw_file)

    df = process(data, args.year)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False)

    angles = data["inputs"]["mounting_system"]["fixed"]
    print(f"Saved {len(df)} rows to {OUT_FILE.relative_to(ROOT)}")
    print(f"  slope {angles['slope']['value']} deg, azimuth {angles['azimuth']['value']} deg")
    print(f"  annual yield {df['pv_kwh_per_kwp'].sum():.0f} kWh/kWp, peak hour {df['pv_kwh_per_kwp'].max():.3f} kWh/kWp")


if __name__ == "__main__":
    main()
