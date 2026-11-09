# CLAUDE.md — Community Microgrid ABM (M&S project)

Context for Claude Code. Read this first, then `docs/ODD.md` (the model specification).

## The project
- Course: **Modelling & Simulation**, FEUP (M.EIC / M.IA), 2026-27. Lecturers: Rosaldo Rossetti, Zafeiris Kokkinogenis, Ana Paula Rocha. Teaching language: English.
- Theme 12: **Community Microgrid and Local Energy Sharing**: households (consumers + prosumers with PV) share locally generated electricity and interact with the wider grid. Compare sharing/pricing mechanisms, collective storage and demand response, fairness, and resilience to uncertain generation, demand peaks, grid outages and membership changes.
- Paradigm: **agent-based model**, with discrete events for outages.
- Group of 3; Ricardo and Guilherme both work with Claude Code and prefer **European Portuguese** in the chat. Code, comments and project docs are in **English**.
- Current version: **ODD v0.5** (Nov 9, 2026), which merges Ricardo's v0.4 (tariffs, battery rule, E1c/E2b) with Guilherme's v0.4 (weather years, temperature effect, relative savings, E6). How to run (Portuguese): `COMO_CORRER.md`.

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

## Repo structure
```
correr_visual.bat        run the Solara app (app.py)
correr_experiencias.bat  run all experiments + statistics + figures (experiments/run_all.py)
COMO_CORRER.md           how to run, parameters and code map (Portuguese)
data/raw/            original downloads, untouched
data/processed/      pv_porto.csv, load_btn_c.csv (hourly, 8,760 rows, 2023, indexed by time_utc + time_local)
                     pv_kwh_per_kwp; load_per_annual_kwh (sums to 1, x household annual kWh in the model)
                     weather_porto.csv: pv_kwh_per_kwp + temp_c per hour for each year 2014-2023 (2023 timeline)
scripts/get_pvgis.py download PVGIS hourly data (2023; the calendar/time axis of the model)
scripts/get_weather.py download PVGIS 2014-2023 PV yield + temperature -> weather_porto.csv
scripts/prep_load.py E-REDES BTN C profile -> hourly kWh
model/agents.py      Household
model/manager.py     CommunityManager (agent: local market, community battery, billing)
model/model.py       Community (Mesa Model; environment, grid, schedule)
experiments/         designs.py (E1-E6), run_experiments.py, run_all.py (runs + notebook), stats.py, results/
notebooks/           analysis and plots
docs/ODD.md          model documentation
```

## Data decisions
- **PV**: PVGIS API `https://re.jrc.ec.europa.eu/api/v5_3/seriescalc`, Porto (lat 41.15, lon -8.61), `pvcalculation=1`, `peakpower=1` (per-kWp profile), `loss=14`, `optimalangles=1`, `outputformat=json`. Column `P` is in W → `/1000` = kWh per kWp per hour. Timestamps are **UTC** (format `%Y%m%d:%H%M`), so shift to local time. Use a **non-leap year** (e.g. 2023). Save to CSV; the model never calls the API.
- **Weather years**: `scripts/get_weather.py` downloads 2014-2023 with the same point, losses and fixed angles (35°, azimuth 3°) and lays each year on the 2023 hourly timeline (29 Feb dropped). Each run draws one year from its own random stream (`weather_year=None`), so scenarios with the same seed share it; `weather_year=2023` fixes it.
- **Temperature effect**: demand x (1 + 0.02 x (HDD - usual HDD) + 0.02 x (CDD - usual CDD)) per local day, HDD base 15 °C, CDD base 22 °C, 'usual' = mean over the ten years for that day (the BTN C profile already has the average seasonal effect). `heat_sensitivity` / `cool_sensitivity = 0` switch it off. The 2% has no source yet.
- **Load**: E-REDES/ERSE standard profile **BTN C** (residential, ≤13.8 kVA, ≤7,140 kWh/yr), 15-min, normalised → sum to hourly, scale by each household's annual kWh, add per-household noise (±10–20%) and a small peak shift. UPAC profiles exist for self-consumption. Optional realism: London Smart Meters dataset (UK, rescale). UCI ElectricityLoadDiagrams20112014 (PT, 370 clients, mixed types) only for variability checks.
- **Tariffs**: ERSE regulated simple tariff 0.1711 EUR/kWh (base); bi-hourly 0.2045 / 0.1143 off-peak 22:00-08:00 (E5 sensitivity; off-peak moves to 22:30-08:30 in H2 2027, kept at 22-8 with 1 h steps). Export 0.05 EUR/kWh (fixed buy-back offers; OMIE minus retailer fee gives the same).

## Model summary (full spec in docs/ODD.md)
- Agents: `Household` (demand, `pv_kwp`, optional home battery, `flexibility`, `cooperation`, `is_member`, cost/revenue accumulators) and one `CommunityManager` (`model.manager`: market clearing, pricing, community battery, settlement, price forecast). Entities: Battery, Grid, Community (model).
- Step = 1 h, horizon = 1 year (8,760 steps); baseline 30 households, 40% with PV.
- Per-step order: environment update → membership (every 30 days) → demand response → self-consumption (PV, then home battery) → local market + pricing → community battery → grid exchange + settlement.
- Pricing mechanisms: no community (reference), fixed, mid-market, supply–demand ratio (SDR, Liu et al. 2017), dynamic, bill-sharing (Long et al. 2017).
- KPIs: community savings, relative savings (community savings / sum of reference bills), self-sufficiency, self-consumption, peak import, fairness (Gini of savings), resilience (share served during outages, lost load).
- Experiments: E1, E1b, E1c, E2, E2b, E3, E4, E5, E6 (weather year x temperature on/off); 30 seeds per scenario, mean ± 95% CI, ANOVA/Kruskal–Wallis + Tukey, paired tests, Friedman (E6).

## Terminology
- **Lost load** = demand not met (deficit with no source). **Curtailment** = surplus wasted (can't be used, stored or exported). They are different things.
- Energy balance check every step: `PV + import + discharge + lost_load = demand + export + charge + curtailment`

## Open decisions (with the group)
- Source for the temperature sensitivity (2% per degree-day) and for p_leave / p_join
- Battery investment cost (none in the model)

## Decided (Oct 2026)
- Membership change (7.6) is in: monthly review, 20% start outside, leave if 30-day savings < threshold (p_leave 0.5), join if same-type members saved (p_join 0.2).
- Grid price stays flat; new `dynamic` community price p_exp + (p_imp - p_exp) * D / (S + D). SDR (Liu) kept for comparison.
- Demand response is price-responsive: shifts evening load to hours with the lowest forecast effective price (exponentially smoothed past prices).
- Tariffs as above (Oct 22).
- Membership threshold 0 EUR in the base (real communities: free entry/exit, 30 days' notice); 2 / 5 EUR per 30 days only as a nuisance cost in E1b.
- The community battery only stores surplus (no trading). Members pay the local price for energy it delivers, and that money goes to the prosumers who filled it, pro rata to the energy each put in (`battery_income="prosumers"`). Losses are reported in kWh (`storage_losses_kwh`). Its deliverable energy counts as supply in the price (SDR, dynamic), with a floor of p_exp / round-trip efficiency when it delivers, so storing never pays less than exporting and buyers never pay more than p_imp.
- Research questions (Nov 9, group decision): **RQ1 pricing mechanisms, RQ2 relative savings, RQ3 flexibility, RQ4 resilience**.
- Weather: ten PVGIS years drawn per seed; temperature effect on demand (Nov 2). E6 shows the temperature effect is statistically significant but small (+0.3% savings, +4% peak import) and the weather year explains ~43% of the variance of savings.
- Joining needs member savings above threshold + 1e-6 EUR (float noise around 0 EUR is not a saving), like leaving.
- docs/ODD.md is at **v0.5** (Nov 9); keep it in sync with every model change. docs/PROJECT_CONTEXT.md is a generated snapshot for other assistants.

## Next steps
1. ~~Create repo structure, push to GitHub~~ (done)
2. ~~`scripts/get_pvgis.py` and `scripts/prep_load.py` → two hourly CSVs~~ (done)
3. ~~Sanity plots~~ (done, `notebooks/01_data_check.ipynb`)
4. ~~Minimal working model~~ (done)
5. ~~Storage, pricing mechanisms, outages, demand response, membership~~ (done, `tests/test_model.py`)
6. ~~Batch experiments + statistical analysis~~ (done, `experiments/`, `notebooks/02_experiments.ipynb`)
7. ~~Group decisions (RQs, tariffs, threshold)~~ (done); ~~run script~~ (done: the two .bat files + run_all)
8. Slides, demo video, report
