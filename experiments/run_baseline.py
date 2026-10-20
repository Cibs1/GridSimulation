"""Run the baseline community for one year and print its KPIs.

Usage (from the repo root):
    python -m experiments.run_baseline [--seed 42]
"""

import argparse
import time

from model.model import Community


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    start = time.perf_counter()
    model = Community(rng=args.seed)
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
