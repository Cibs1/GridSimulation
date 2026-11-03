"""Run every experiment and then rebuild the statistics and figures.

This is what correr_experiencias.bat calls. It does two things in order:
    1. experiments.run_experiments: all designs in experiments/designs.py
       (30 seeds each) -> experiments/results/<experiment>.csv
    2. executes notebooks/02_experiments.ipynb in place: statistical tests
       and figures -> notebooks/figures/*.png (the notebook keeps the tables)

Usage (from the repo root, with the .venv active):
    python -m experiments.run_all                     # everything
    python -m experiments.run_all e1_pricing e4_resilience   # only some experiments, then the figures
    python -m experiments.run_all --workers 6         # use fewer CPU cores (default: all)
    python -m experiments.run_all --figures-only      # skip the runs, rebuild the figures from the CSVs
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from experiments.designs import DESIGNS
from experiments.run_experiments import run_experiment

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "02_experiments.ipynb"


def build_figures():
    print(f"Running {NOTEBOOK.relative_to(ROOT)} (statistics and figures)...")
    subprocess.run(
        [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
         "--ExecutePreprocessor.timeout=1800", str(NOTEBOOK)],
        check=True, cwd=NOTEBOOK.parent,
    )
    print(f"Figures saved in {(NOTEBOOK.parent / 'figures').relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiments", nargs="*", help=f"any of {', '.join(DESIGNS)} (default: all)")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="CPU cores to use")
    parser.add_argument("--figures-only", action="store_true", help="do not run the experiments, only the notebook")
    args = parser.parse_args()
    unknown = set(args.experiments) - set(DESIGNS)
    if unknown:
        parser.error(f"unknown experiments: {', '.join(sorted(unknown))}")

    start = time.perf_counter()
    if not args.figures_only:
        for name in args.experiments or DESIGNS:
            run_experiment(name, args.workers)
    build_figures()
    print(f"Done in {(time.perf_counter() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
