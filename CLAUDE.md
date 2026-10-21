# CLAUDE.md — Community Microgrid ABM (M&S project)

Context for Claude Code. Read this first, then `docs/ODD.md` (the model specification).

## The project
- Course: **Modelling & Simulation**, FEUP (M.EIC / M.IA), 2026-27. Lecturers: Rosaldo Rossetti, Zafeiris Kokkinogenis, Ana Paula Rocha. Teaching language: English.
- Theme 12: **Community Microgrid and Local Energy Sharing**: households (consumers + prosumers with PV) share locally generated electricity and interact with the wider grid. Compare sharing/pricing mechanisms, collective storage and demand response, fairness, and resilience to uncertain generation, demand peaks, grid outages and membership changes.
- Paradigm: **agent-based model**, with discrete events for outages.
- The user (Ricardo) prefers to talk in **European Portuguese**. Code, comments and project docs are in **English**.

## Deliverables and dates
- Git repo with documented code + a **"How to Build & Run"** script/README
- **ODD model documentation** (`docs/ODD.md`)
- Presentation (15 min + 10 min discussion), commented PPTX slides: problem statement and formalisation, methods and materials, results and discussion
- Demo video + recorded oral presentation
- **Statistical/quantitative analysis is mandatory**
- Grading: Project 40%, Demo/presentation 20%, Individual test 40% (each ≥ 8.0)
- Mini-test: **15 Dec 2026** · Project submission: **5 Jan 2027** · Presentations: **6–8 Jan 2027**

## Tech stack
- **Python ≥ 3.12**, conda env named `microgrid`
- **Mesa 3.x** (3.5.1 at setup): `pip install -U "mesa[rec]" pandas jupyter`
- Mesa 3 API, so DO NOT use Mesa 2 patterns (`RandomActivation`, `self.schedule`, `unique_id` passed manually). Use `model.agents`, `shuffle_do`, `model.steps` (incremented before `step()` runs, so the current hour is `steps - 1`), `super().__init__(rng=seed)` (`seed=` is deprecated in 3.5), `DataCollector`, `mesa.batch_run`.
- pandas/numpy for data; matplotlib/plotly for plots; Solara (via mesa[rec]) for an optional dashboard; scipy/statsmodels for stats.

## Planned repo structure
```
data/raw/            original downloads, untouched
data/processed/      pv_porto.csv, load_btn_c.csv (hourly, 8,760 rows, 2023, indexed by time_utc + time_local)
                     pv_kwh_per_kwp; load_per_annual_kwh (sums to 1, x household annual kWh in the model)
scripts/get_pvgis.py download PVGIS hourly data
scripts/prep_load.py E-REDES BTN C profile -> hourly kWh
model/agents.py      Household
model/model.py       Community (Mesa Model; runs local market, battery, grid)
experiments/         batch_run scripts + results
notebooks/           analysis and plots
docs/ODD.md          model documentation
```

## Data decisions
- **PV**: PVGIS API `https://re.jrc.ec.europa.eu/api/v5_3/seriescalc`, Porto (lat 41.15, lon -8.61), `pvcalculation=1`, `peakpower=1` (per-kWp profile), `loss=14`, `optimalangles=1`, `outputformat=json`. Column `P` is in W → `/1000` = kWh per kWp per hour. Timestamps are **UTC** (format `%Y%m%d:%H%M`), so shift to local time. Use a **non-leap year** (e.g. 2023). Save to CSV; the model never calls the API.
- **Load**: E-REDES/ERSE standard profile **BTN C** (residential, ≤13.8 kVA, ≤7,140 kWh/yr), 15-min, normalised → sum to hourly, scale by each household's annual kWh, add per-household noise (±10–20%) and a small peak shift. UPAC profiles exist for self-consumption. Optional realism: London Smart Meters dataset (UK, rescale). UCI ElectricityLoadDiagrams20112014 (PT, 370 clients, mixed types) only for variability checks.
- **Tariffs**: Portuguese regulated tariffs (ERSE); export price well below import price. Exact values still TBD.

## Model summary (full spec in docs/ODD.md)
- Agent: `Household` (demand, `pv_kwp`, optional home battery, `flexibility`, `cooperation`, `is_member`, cost/revenue accumulators). Entities: community Battery, Grid, Community (model).
- Step = 1 h, horizon = 1 year (8,760 steps); baseline 30 households, 40% with PV.
- Per-step order: environment update → membership (daily) → demand response → self-consumption (PV, then home battery) → local market + pricing → community battery → grid exchange + settlement.
- Pricing mechanisms: no community (reference), fixed, mid-market, supply–demand ratio (SDR, Liu et al. 2017), dynamic, bill-sharing (Long et al. 2017).
- KPIs: community savings, self-sufficiency, self-consumption, peak import, fairness (Gini of savings), resilience (share served during outages, lost load).
- Experiments: 30 seeds per scenario, mean ± 95% CI, ANOVA/Kruskal–Wallis + Tukey.

## Terminology
- **Lost load** = demand not met (deficit with no source). **Curtailment** = surplus wasted (can't be used, stored or exported). They are different things.
- Energy balance check every step: `PV + import + discharge + lost_load = demand + export + charge + curtailment`

## Open decisions (with the group)
- Narrow to 2–3 research questions (currently 4: pricing, storage, demand response, resilience)
- Exact tariff values / time-of-use or not
- Participation threshold for membership (2 EUR/30 days used in E1; needs a justification, e.g. real CER fees)

## Decided (Oct 2026)
- Membership change (7.6) is in: monthly review, 20% start outside, leave if 30-day savings < threshold (p_leave 0.5), join if same-type members saved (p_join 0.2).
- Grid price stays flat; new `dynamic` community price p_exp + (p_imp - p_exp) * D / (S + D). SDR (Liu) kept for comparison.
- Demand response is price-responsive: shifts evening load to hours with the lowest forecast effective price (exponentially smoothed past prices).
- docs/ODD.md updated to v0.2 (Oct 21) to match the code; keep it in sync with every model change.

## Next steps
1. ~~Create repo structure, push to GitHub~~ (done)
2. ~~`scripts/get_pvgis.py` and `scripts/prep_load.py` → two hourly CSVs~~ (done)
3. ~~Sanity plots~~ (done, `notebooks/01_data_check.ipynb`)
4. ~~Minimal working model~~ (done)
5. ~~Storage, pricing mechanisms, outages, demand response, membership~~ (done, `tests/test_model.py`)
6. ~~Batch experiments + statistical analysis~~ (done, `experiments/`, `notebooks/02_experiments.ipynb`)
7. Group decisions (RQs, tariffs, threshold), then dashboard (optional), slides, video, run script
