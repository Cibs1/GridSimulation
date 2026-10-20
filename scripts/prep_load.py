"""Convert the E-REDES BTN C consumption profile (15-min) into an hourly CSV.

Input: data/raw/E-REDES_Perfil_Consumo_<year>.xlsx, the regulated standard
profiles published by E-REDES/ERSE (downloaded if missing). Values are in
per-mille of annual consumption per quarter-hour, in Portuguese legal time, so
the spring DST day has 92 quarter-hours and the autumn one has 100.

Output: data/processed/load_btn_c.csv with 8,760 rows:
    time_utc             start of the hour, UTC
    time_local           same instant in Europe/Lisbon legal time (with offset)
    load_per_annual_kwh  share of annual consumption used in that hour (sums to 1)

A household with annual demand E kWh uses E * load_per_annual_kwh kWh in each
hour. Per-household noise and peak shifts are added in the model, not here.

Usage:
    python scripts/prep_load.py [--year 2023]
"""

import argparse
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_FILE = ROOT / "data" / "processed" / "load_btn_c.csv"

SOURCE_URL = "https://www.e-redes.pt/sites/eredes/files/{year}-01/E-REDES_Perfil_Consumo_{year}.xlsx"
PROFILE = "BTN C"
LOCAL_TZ = "Europe/Lisbon"


def download(year: int, raw_file: Path) -> None:
    resp = requests.get(SOURCE_URL.format(year=year), headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
    resp.raise_for_status()
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_bytes(resp.content)
    print(f"Saved raw profile to {raw_file.relative_to(ROOT)}")


def read_profile(raw_file: Path) -> pd.DataFrame:
    # Sheet layout: 4 header rows; profile names (BTN A, BTN B, BTN C, IP) on row 4.
    header = pd.read_excel(raw_file, header=None, nrows=4)
    col = header.iloc[3].tolist().index(PROFILE)
    df = pd.read_excel(raw_file, header=None, skiprows=4, usecols=[0, col], names=["date", "value"])
    return df.dropna(subset=["value"]).reset_index(drop=True)


def process(df: pd.DataFrame, year: int) -> pd.DataFrame:
    # The time labels around the autumn DST change are inconsistent in the
    # source file, so they are not used. Rows are contiguous quarter-hours
    # starting at local midnight on 1 Jan (= 00:00 UTC, winter time), so the
    # row position gives the physical time.
    start = pd.Timestamp(f"{year}-01-01", tz=LOCAL_TZ).tz_convert("UTC")
    qh_utc = start + pd.to_timedelta(15 * df.index, unit="min")

    # Check: the local date of every quarter-hour must match the "Data" column.
    local_date = qh_utc.tz_convert(LOCAL_TZ).tz_localize(None).normalize()
    mismatched = (local_date != df["date"].dt.normalize()).sum()
    if mismatched:
        raise ValueError(f"{mismatched} quarter-hours do not match their date; file layout changed?")

    hourly = df.groupby(qh_utc.floor("h"))["value"].sum()
    expected = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", tz="UTC", inclusive="left")
    if len(expected) != 8760:
        raise ValueError(f"{year} is a leap year; use a non-leap year")
    if not hourly.index.equals(expected):
        raise ValueError("profile is not a complete, ordered hourly year")

    return pd.DataFrame({
        "time_utc": expected,
        "time_local": expected.tz_convert(LOCAL_TZ),
        "load_per_annual_kwh": (hourly / hourly.sum()).to_numpy(),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=2023, help="non-leap year, same as the PV data")
    args = parser.parse_args()

    raw_file = RAW_DIR / f"E-REDES_Perfil_Consumo_{args.year}.xlsx"
    if not raw_file.exists():
        download(args.year, raw_file)

    raw = read_profile(raw_file)
    print(f"Read {len(raw)} quarter-hours of {PROFILE}, raw sum {raw['value'].sum():.3f} (per-mille)")

    df = process(raw, args.year)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False)

    by_hour = df.groupby(df["time_local"].dt.hour)["load_per_annual_kwh"].mean() * 8760
    print(f"Saved {len(df)} rows to {OUT_FILE.relative_to(ROOT)}")
    print(f"  peak local hour {by_hour.idxmax()}h, minimum at {by_hour.idxmin()}h (mean hourly shape, 1 = average)")
    print(f"  for 3,500 kWh/yr: peak hour {df['load_per_annual_kwh'].max() * 3500:.2f} kWh")


if __name__ == "__main__":
    main()
