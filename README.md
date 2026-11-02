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
model/               Mesa model (agents.py, manager.py, model.py, battery.py)
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
python scripts/get_weather.py     # PVGIS 2014-2023 PV yield + temperature -> data/processed/weather_porto.csv

# 3a. Interactive visualisation (Mesa + Solara), opens in the browser
solara run app.py                 # or: python -m solara run app.py  (--no-open: no browser)

# 3b. Run the baseline community for one year and print its KPIs
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

Scenario options (see `Community.__init__` in `model/model.py`):
`pricing` (`none`, `fixed`, `mid_market`, `sdr`, `dynamic`, `bill_sharing`),
`storage_mode` (`none`, `shared`, `individual`) with `storage_kwh`,
`flexibility` (price-responsive demand response, 0-0.2), `outage_rate`
(outages per year), `membership` (monthly join/leave decisions, with
`initial_member_share` and `savings_threshold`), `weather_year` (default
`None`: drawn per seed from 2014-2023; or fix one, e.g. `2023`) and
`heat_sensitivity` / `cool_sensitivity` (demand change per degree-day colder or
hotter than usual; `0` switches the temperature effect off).
For example: `python -m experiments.run_baseline --pricing sdr --storage-mode shared --storage-kwh 100`.

Tariffs are placeholders (0.20 / 0.05 EUR/kWh).

```bash
# 4. Verification tests (energy balance, money conservation, reproducibility, ...)
python -m pytest

# 5. Experiments (ODD section 8): 6 designs x 30 seeds, ~2,800 runs, ~10 min on 16 cores
python -m experiments.run_experiments               # all, or name some: e1_pricing e2_storage ...
#    -> experiments/results/<experiment>.csv (one row per scenario x seed)

# 6. Statistical analysis and figures
jupyter notebook notebooks/02_experiments.ipynb     # figures saved to notebooks/figures/
```

Research questions (ODD v0.4): RQ1 best pricing mechanism, RQ2 relative
savings, RQ3 resilience; demand response is an extension. **The result CSVs
and figures in the repo are still from ODD v0.3 (weather year 2023 only, no
temperature effect); rerun step 5 to update them.**

| Experiment | Question | Design |
| --- | --- | --- |
| `e1_pricing` | RQ1 pricing, membership and fairness; RQ2 savings vs PV share | 6 mechanisms x PV share 20/40/60/80%, membership on (threshold 2 EUR/30 days) |
| `e1b_membership_threshold` | robustness of RQ1 | 6 mechanisms x threshold 0/2/5 EUR per 30 days |
| `e2_storage` | RQ2 relative savings: shared vs individual storage | none / individual / shared x 50/100/200 kWh |
| `e3_demand_response` | extension: flexibility | mid-market / SDR / dynamic x flexibility 0 / 0.1 / 0.2 |
| `e4_resilience` | RQ3 resilience to outages | 3 outage regimes x 3 storage options x 20/30/50 households |
| `e5_sensitivity` | robustness | one-at-a-time: cooperation, battery efficiency, export price, temperature sensitivity |

Scenarios share the same 30 seeds (same households, weather and outages), so
they can be compared with paired tests. Statistics live in `experiments/stats.py`
(95% CI, Shapiro, Levene, ANOVA, Kruskal-Wallis, Tukey HSD, paired t / Wilcoxon).

## Input data

| File | Source | Content |
| --- | --- | --- |
| `pv_porto.csv` | [PVGIS v5.3](https://re.jrc.ec.europa.eu/pvg_tools/en/) (EU JRC), SARAH3, Porto (41.15, -8.61), 2023, optimal angles, 14% losses | `pv_kwh_per_kwp`: energy per kWp installed in each hour |
| `weather_porto.csv` | PVGIS v5.3 (SARAH3 + ERA5), same point and panels, years 2014-2023 | `pv_kwh_per_kwp` and `temp_c` per `hour` (0-8759 on the 2023 timeline) for each `year`; each run uses one year |
| `load_btn_c.csv` | [E-REDES](https://www.e-redes.pt/pt-pt/perfis-de-consumo) / ERSE standard profile BTN C, 2023 | `load_per_annual_kwh`: share of annual consumption in each hour (sums to 1) |

Both files are indexed by `time_utc` (start of the hour) and also carry
`time_local` (Europe/Lisbon legal time), so the rows line up one-to-one and
hour-of-day rules use local time.
