# GridSimulation — Community Microgrid ABM

Agent-based model of a residential energy community in Porto: households
(consumers and prosumers with PV) share locally generated electricity, use
shared or home storage, and trade with the wider grid. The model compares
local pricing mechanisms, storage options and demand response, and measures
savings, fairness and resilience to grid outages.

Modelling & Simulation, FEUP, 2026-27 (Theme 12). Full specification in
[docs/ODD.md](docs/ODD.md).

## Repository structure

```
data/raw/            original downloads, untouched
data/processed/      hourly inputs for the model (8,760 rows, year 2023)
scripts/             data download and preparation
model/               Mesa model (agents.py, model.py)
experiments/         batch_run scripts; results/ holds their output
notebooks/           analysis and plots
docs/ODD.md          model documentation (ODD protocol)
```

## How to build & run

Requires Python 3.12 or newer.

```bash
# 1. Environment (either venv or conda)
python -m venv .venv
.venv\Scripts\activate            # Windows; on Linux/macOS: source .venv/bin/activate
# or: conda create -n microgrid python=3.12 && conda activate microgrid
pip install -r requirements.txt

# 2. Input data (already committed in data/; rerun only to rebuild)
python scripts/get_pvgis.py       # PVGIS hourly PV yield -> data/processed/pv_porto.csv
python scripts/prep_load.py       # E-REDES BTN C profile  -> data/processed/load_btn_c.csv

# 3. Run the baseline community for one year and print its KPIs
python -m experiments.run_baseline --seed 42
```

```python
# Or from Python / a notebook (run from the repo root)
from model.model import Community
m = Community(n_households=30, pv_share=0.4, rng=42)
m.run_year()
m.kpis()                                   # run-level KPIs (ODD section 8)
m.datacollector.get_model_vars_dataframe() # hourly community flows
m.household_table()                        # per-household annual results
```

Current model: households, local sharing at a fixed price, grid exchange.
Batteries, other pricing mechanisms, demand response, outages and membership
are added in later steps. Tariffs are placeholders (0.20 / 0.05 EUR/kWh).

## Input data

| File | Source | Content |
| --- | --- | --- |
| `pv_porto.csv` | [PVGIS v5.3](https://re.jrc.ec.europa.eu/pvg_tools/en/) (EU JRC), SARAH3, Porto (41.15, -8.61), 2023, optimal angles, 14% losses | `pv_kwh_per_kwp`: energy per kWp installed in each hour |
| `load_btn_c.csv` | [E-REDES](https://www.e-redes.pt/pt-pt/perfis-de-consumo) / ERSE standard profile BTN C, 2023 | `load_per_annual_kwh`: share of annual consumption in each hour (sums to 1) |

Both files are indexed by `time_utc` (start of the hour) and also carry
`time_local` (Europe/Lisbon legal time), so the rows line up one-to-one and
hour-of-day rules use local time.
