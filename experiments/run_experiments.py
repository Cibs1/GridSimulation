"""Run the experiment designs in parallel and save one row per run.

Output: experiments/results/<experiment>.csv with columns
    scenario, seed, <scenario parameters>, <KPIs from Community.kpis()>

We use a process pool instead of mesa.batch_run because the KPIs are
run-level quantities computed once at the end (Community.kpis()), not
per-step DataCollector variables.

Usage (from the repo root):
    python -m experiments.run_experiments              # all experiments
    python -m experiments.run_experiments e2_storage   # one or more by name
"""

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from experiments.designs import DESIGNS, SEEDS
from model.model import Community

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def run_one(job):
    scenario, params, seed = job
    model = Community(**params, check_balance=False, rng=seed)
    model.run_year()
    flat = {k: str(v) if isinstance(v, tuple) else v for k, v in params.items()}
    return {"scenario": scenario, "seed": seed, **flat, **model.kpis()}


def run_experiment(name, workers):
    scenarios = DESIGNS[name]()
    jobs = [(label, params, seed) for label, params in scenarios.items() for seed in SEEDS]
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(run_one, jobs, chunksize=4))
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / f"{name}.csv", index=False)
    print(f"{name}: {len(scenarios)} scenarios x {len(SEEDS)} seeds = {len(jobs)} runs "
          f"in {time.perf_counter() - start:.0f} s")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiments", nargs="*", help=f"any of {', '.join(DESIGNS)} (default: all)")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    args = parser.parse_args()
    unknown = set(args.experiments) - set(DESIGNS)
    if unknown:
        parser.error(f"unknown experiments: {', '.join(sorted(unknown))}")
    for name in args.experiments or DESIGNS:
        run_experiment(name, args.workers)


if __name__ == "__main__":
    main()
