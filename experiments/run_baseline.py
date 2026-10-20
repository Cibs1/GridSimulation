"""Run one community scenario for one year and print its KPIs.

Usage (from the repo root):
    python -m experiments.run_baseline [--seed 42] [--pricing sdr] [--storage-mode shared --storage-kwh 100]
                                       [--flexibility 0.1] [--outage-rate 4]
"""

import argparse
import time

from model.model import PRICING_MECHANISMS, STORAGE_MODES, Community


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--households", type=int, default=30)
    parser.add_argument("--pv-share", type=float, default=0.4)
    parser.add_argument("--pricing", choices=PRICING_MECHANISMS, default="mid_market")
    parser.add_argument("--storage-mode", choices=STORAGE_MODES, default="none")
    parser.add_argument("--storage-kwh", type=float, default=0.0)
    parser.add_argument("--flexibility", type=float, default=0.0)
    parser.add_argument("--outage-rate", type=float, default=4.0)
    args = parser.parse_args()

    start = time.perf_counter()
    model = Community(
        n_households=args.households, pv_share=args.pv_share, pricing=args.pricing,
        storage_mode=args.storage_mode, storage_kwh=args.storage_kwh,
        flexibility=args.flexibility, outage_rate=args.outage_rate, rng=args.seed,
    )
    model.run_year()
    elapsed = time.perf_counter() - start

    print(f"Ran {model.steps} steps with {len(model.households)} households in {elapsed:.1f} s (seed {args.seed})")
    for name, value in model.kpis().items():
        print(f"  {name:32s} {value:10.3f}")

    table = model.household_table()
    print("\nSavings by group (EUR/yr):")
    print(table.groupby(table["pv_kwp"] > 0)["savings_eur"].describe().rename(index={True: "prosumer", False: "consumer"}).round(1))


if __name__ == "__main__":
    main()
