# GridSimulation: full project context

Snapshot of the repository on 2026-10-22. One file meant to give an assistant everything needed to discuss, extend or present the model: the project brief, how the code is organised and run, the complete model specification (ODD protocol), a summary of all experiment results, and findings and known modelling issues that came up while analysing them.

Contents:

- Part A. Project brief
- Part B. Code map, how to run, interactive app
- Part C. Key findings and known modelling issues
- Part D. Model specification (ODD protocol, v0.3, verbatim)
- Part E. Experiment results (mean ± 95% CI over 30 seeds)

---

# Part A. Project brief

- **Course:** Modelling & Simulation, FEUP (M.EIC / M.IA), 2026-27. Theme 12: *Community Microgrid and Local Energy Sharing*. Households (consumers, and prosumers with PV) share locally generated electricity and interact with the wider grid. The project compares sharing/pricing mechanisms, collective storage and demand response, and looks at fairness and resilience to uncertain generation, demand peaks, grid outages and membership changes.
- **Paradigm:** agent-based model (Mesa 3.5, Python ≥ 3.12), with discrete outage events.
- **Team member using this file:** Ricardo, who prefers to talk in European Portuguese. Code, comments and project documents are in English.
- **Deliverables:** Git repository with documented code and a "How to Build & Run" README; ODD documentation (`docs/ODD.md`); presentation (15 min + 10 min discussion) with commented PPTX slides (problem statement and formalisation, methods and materials, results and discussion); demo video and recorded oral presentation. A statistical/quantitative analysis is mandatory.
- **Dates:** mini-test 15 Dec 2026; project submission 5 Jan 2027; presentations 6–8 Jan 2027.
- **Status:** model, tests, experiments (E1–E5) and statistical notebook are done. Still to do: group decisions (below), slides, video, final run script.

**Open decisions (with the group)**

- Narrow the four research questions (pricing, storage, demand response, resilience) to 2–3.
- Exact tariff values; flat or time-of-use. Current prices are placeholders: import 0.20 €/kWh, export 0.05 €/kWh.
- Justify the membership participation threshold (2 € per 30 days in E1), e.g. with real Portuguese energy-community fees.
- What happens to the community battery's income (see Part C, finding 4).
- Whether the community battery keeps a reserve for outages.

**Already decided:** membership change is in (monthly review, 20% start outside, leave if 30-day savings < threshold with p_leave 0.5, join if same-type members saved with p_join 0.2); grid price stays flat; the `dynamic` community price was added and SDR kept for comparison; demand response is price-responsive.

---

# Part B. Code map, how to run, interactive app

## Repository

```
data/raw/            original downloads (PVGIS JSON, E-REDES profile xlsx)
data/processed/      pv_porto.csv, load_btn_c.csv (hourly, 8,760 rows, 2023)
scripts/             get_pvgis.py, prep_load.py (build the processed CSVs)
model/agents.py      Household agent
model/manager.py     CommunityManager agent (local market, pricing, community battery, billing, price forecast)
model/battery.py     Battery entity (home and community)
model/model.py       Community (Mesa Model: environment, grid, schedule, KPIs)
app.py               interactive Solara dashboard
experiments/         designs.py (E1-E5), run_experiments.py, run_baseline.py, stats.py, results/*.csv
notebooks/           01_data_check.ipynb (input sanity plots), 02_experiments.ipynb (statistics, figures)
tests/test_model.py  33 verification tests
docs/ODD.md          model specification (reproduced in Part D)
```

## Main classes

- `Community(mesa.Model)` in `model/model.py`. Holds the inputs (PV yield per kWp, load shape, local hour), grid tariffs and the outage schedule; creates the households and the manager; runs the hourly step; computes `kpis()` and `household_table()`. Constructor parameters and defaults: `n_households=30`, `pv_share=0.4`, `pv_kwp_range=(2, 5)`, `annual_kwh_range=(2500, 5000)`, `noise_sd_range=(0.10, 0.20)`, `max_shift_h=1`, `cooperation=1.0`, `flexibility=0.0`, `dr_threshold_range=(0, 0.03)`, `price_memory=0.3`, `membership=False`, `initial_member_share=1.0`, `review_days=30`, `savings_threshold=0.0`, `p_leave=0.5`, `p_join=0.2`, `pricing="mid_market"`, `fixed_price=0.10`, `import_price=0.20`, `export_price=0.05`, `storage_mode="none"`, `storage_kwh=0.0`, `battery_c_rate=0.5`, `battery_efficiency=0.9`, `outage_rate=4.0`, `outage_duration=(1, 8)`, `check_balance=True`, `rng=None` (seed).
- `Household(mesa.Agent)` in `model/agents.py`. Builds its yearly demand from the BTN C shape (scaled, shifted, noisy); computes its net position each hour (own PV, then home battery, then offer or bid); exchanges what is left with the grid; plans demand response daily; tracks its bill and its no-community reference bill.
- `CommunityManager(mesa.Agent)` in `model/manager.py`, one per model (`model.manager`). Collects members' offers and bids, matches them pro rata (`clear_market`), sets the local price (`market_price`), runs the community battery (`operate_battery`), books every household's costs and revenues (`settle`), records the effective price members paid and keeps its smoothed forecast by hour of day (`update_price_forecast`). Households never trade with each other directly; everything goes through the manager.
- `Battery` in `model/battery.py`: capacity, C-rate power limit, symmetric charge/discharge efficiency, SoC.

## How to run

```bash
pip install -r requirements.txt                     # Python >= 3.12 (repo uses a .venv)
python -m solara run app.py --no-open               # dashboard at http://localhost:8765 (omit --no-open to open the browser)
python -m experiments.run_baseline --seed 42 --pricing sdr --storage-mode shared --storage-kwh 100
python -m pytest                                    # 33 tests, energy balance checked every step
python -m experiments.run_experiments [e1_pricing ...]   # 6 designs x 30 seeds, ~2,800 runs
jupyter notebook notebooks/02_experiments.ipynb     # statistics and figures (notebooks/figures/)
```

```python
from model.model import Community
m = Community(pricing="dynamic", storage_mode="shared", storage_kwh=100, rng=42)
m.run_year()
m.kpis()                                    # run-level KPIs
m.datacollector.get_model_vars_dataframe()  # hourly community flows and prices
m.household_table()                         # per-household annual results
```

## Interactive app (`app.py`)

Left column: play/step/reset controls (play interval, steps per frame; 24 = one day per frame) and scenario parameters (seed, households, PV share, pricing, storage mode and capacity, flexibility, outages per year, membership on/off, members at start, savings threshold). Changing a parameter needs Reset.

Main panel: a radial view of the community for the current hour. The community manager is a dark circle in the centre showing the local price and the kWh shared. Houses sit on a ring around it (two staggered rings above 34 houses). Each house has a line to the manager whose width is the energy exchanged that hour and whose arrow shows the direction. The house colour gives its state: orange = surplus (sharing or exporting), green = deficit covered locally, blue = importing from the grid, red = unserved (outage), grey = balanced. A dark blue roof means PV (a sun appears when it produces); a small gauge shows a home battery's charge; faded houses with dashed lines are non-members. The grid sits at the top, linked to the manager (blue line = import, yellow = export, red dashed with "GRID OUTAGE" during outages). The community battery sits at the bottom with its charge level. The background turns blue-grey at night.

Side panels: "Community manager, this hour" (offers, bids, matched locally, battery in/out, grid import/export, local price) and running KPIs since 1 January (members, community savings, mean savings of prosumers and consumers, self-sufficiency, self-consumption, peak import, outage hours and unserved energy). Below: 72-hour charts of community energy flows and of prices.

---

# Part C. Key findings and known modelling issues

Numbers come from Part E unless a single run is cited (seed 42, 30 households, 40% PV, placeholder tariffs).

**1. Pricing only redistributes savings; it changes the total only through behaviour.** Each kWh shared locally instead of going through the grid saves the community p_imp − p_exp = 0.15 €, whatever the local price P: the seller gains P − p_exp, the buyer p_imp − P. With all households members and no demand response, energy flows are identical under every mechanism, so total community savings are identical (seed 42, no storage: 3,268 € for both SDR and dynamic). There is a test for this. Totals differ only when the price changes behaviour: who leaves or joins (membership), or how load is shifted (demand response).

**2. SDR gives almost all the gain to buyers in this community.** SDR (Liu et al. 2017) sets the price to p_exp as soon as supply ≥ demand (SDR ≥ 1), and its curve is convex (already 0.08 €/kWh at SDR = 0.5). With 40% PV and 2–5 kWp systems, supply covers demand in 59% of the hours with offers, and 81% of locally traded kWh are traded in those hours (seed 42). The volume-weighted price sellers receive is 0.055 €/kWh under SDR (vs 0.05 for exporting) and 0.107 under dynamic. In E1 (40% PV, membership on, threshold 2 €), SDR gives prosumers 12.8 € and consumers 122 € a year (dynamic: 88.6 / 99.4). Prosumers' monthly savings (~1 €) fall below the 2 € threshold, so they leave and later rejoin (16.5 leaves, 15.1 joins per year vs 0.6 / 5.9 under dynamic), and total savings drop (2,350 € vs 2,850 €).

This is a finding, not a bug: the implementation matches Liu (buyers pay the SDR price on their local share and p_imp on the rest, which equals Liu's P_buy on their whole deficit; the manager's budget balances). Liu's setting differs: all participants are prosumers, so the asymmetry between seller and buyer roles cancels within each participant, and prosumers adjust consumption to the price (Stackelberg game), so the p_exp price at surplus is a signal to consume more. E3 supports this: with demand response, SDR prosumer savings rise from 7.8 € (flex 0) to 78.8 € (flex 0.2) and the Gini falls from 0.44 to 0.25. Our model amplifies the imbalance through fixed roles (60% of households never sell), frequent surplus, little flexibility by default, and the membership threshold. The planned framing: SDR was designed for prosumer-only communities with flexible demand; in a mixed community with frequent surplus it hands the gain to consumers and pushes prosumers out.

**3. Dynamic is the symmetric alternative.** p_local = p_exp + (p_imp − p_exp)·D/(S + D): mid-point at S = D, approaching p_exp only with a large surplus. It splits the gain between both sides and keeps prosumers in. At 40% PV its Gini (0.20 in E1) is as low as the fixed price's, and its total savings match mid-market and fixed.

**4. The community battery's income is counted but not allocated to anyone.** The battery buys its charge from sellers and sells its discharge to buyers at the local price. Its net income (`battery_cash_eur`) is added to community savings but is not given to any household, so per-household savings, the Gini and membership decisions ignore it. Under SDR it is large and positive: the battery buys at p_exp during surplus and sells at a higher price during scarcity (seed 42, shared 100 kWh: 2,740 € of 6,190 € total, 44%; households get 3,450 €). Under mid-market it is negative (about −274 €/year in E2): it buys and sells at the same price and loses its round-trip losses. The model also has no battery capital cost, so storage looks free. Options under discussion: return the income to members (equally, or in proportion to consumption or production), use it to pay for the battery, or both.

**5. Bill-sharing penalises prosumers.** Energy exchanged between members is effectively free to buyers, and sellers are paid only for the part of their offer that is exported. Prosumers end up with negative savings (−16 € at 40% PV), most of them leave (25.7 leaves per year), and the Gini is close to or above 1.

**6. The membership threshold drives the churn.** At threshold 0 nobody leaves except under bill-sharing; at 2 € only SDR and bill-sharing lose members; at 5 € every mechanism loses members (E1b). The value is not justified yet (open decision).

**7. More PV lowers total savings when membership is on.** E1 under mid-market: 2,870 € (20% PV) → 2,850 (40%) → 2,130 (60%) → 1,120 (80%). With more prosumers there are fewer deficits to sell to, extra surplus is exported at p_exp anyway, savings per member fall below the threshold, and members leave.

**8. Storage (E2).** At the same total capacity, one shared battery beats batteries spread over prosumers' homes: at 100 kWh, savings are 5,980 € vs 4,490 € and self-sufficiency is 53% vs 44%. Fairness is also better: Gini 0.27 vs 0.47, because home batteries only benefit their owners. Returns diminish above 100 kWh: at 200 kWh the shared battery already uses all the PV (self-consumption ≈ 100%). Peak import does not change (≈ 26.7 kW), because the battery charges only from local surplus and does no peak shaving.

**9. Demand response (E3).** Flexibility 0.1 adds about 900 € a year and slightly lowers peak import (26.8 → 25.2 kW). At flexibility 0.2 savings keep rising (≈ 4,600 €), but peak import rises to 32–34 kW: many households move load into the same cheap hours (rebound peak). Under SDR, demand response mainly helps prosumers (finding 2).

**10. Resilience (E4).** Without storage, about 31% of demand during outages is still served (by daytime PV). Individual batteries raise this to about 42% and a shared 100 kWh battery to about 50%. The share falls for a 50-household community with the same 100 kWh battery. Confidence intervals are wide because outage timing (day or night) varies between seeds. The battery keeps no reserve for outages.

**11. Sensitivity (E5, mid-market + shared 100 kWh).** Cooperation matters most: savings fall from 5,980 € to 3,190 € at cooperation 0.5. A lower export price increases the value of sharing (0.03 €/kWh: 6,830 €; 0.08 €/kWh: 4,690 €). Battery efficiency matters less (5,570–6,170 €).

**Known simplifications:** placeholder flat tariffs; no battery capital cost; no network constraints or losses; a single local price for both sides (except bill-sharing); perfect metering; a non-member still sits behind the same connection point but is billed at grid prices; the community battery does not charge from the grid and keeps no outage reserve; E1 also reports membership columns for the `none` scenario, where membership has no effect.

---

# Part D. Model specification (ODD protocol)

The text below is `docs/ODD.md` verbatim, with its headings moved down one level.

## Community Microgrid ABM — ODD Protocol (Draft v0.3)

Oct 22, 2026 · @Ricardo

Changes since v0.2 (Oct 21): the local market, community battery and billing are
run by a new **CommunityManager** agent instead of the model itself. Behaviour and
results are unchanged.

Changes since v0.1 (Oct 6): load data source fixed (E-REDES BTN C); new `dynamic`
pricing mechanism; bill-sharing defined as in Long et al. (2017); demand response
made price-responsive; membership change included and made monthly; storage
modes, the no-community reference and battery settlement specified; curtailment
added to the KPIs and the energy balance; the seasonal validation pattern
corrected; experiment design and statistics updated to match the code.

### 1. Purpose and patterns

The model tests which local energy-sharing and pricing rules give a residential energy community the largest, fairest and most stable savings, and how well it copes with uncertainty and grid outages. It is a what-if tool comparing policies, not a forecast of one real community.

**Research questions**

1. **Pricing:** Which internal pricing mechanism (fixed price, mid-market, supply–demand ratio, dynamic, bill-sharing) maximises total savings versus no community when households can leave a community that does not pay off, and how fairly are the savings split?
2. **Storage:** Does one shared community battery beat the same total capacity spread across individual home batteries, in self-sufficiency and cost?
3. **Flexibility:** How much does price-responsive demand response (shifting flexible load to cheaper hours) add on top of sharing, and what does it do to the peak grid import?
4. **Resilience:** During a grid outage, what share of demand can the community cover, and how does that change with community size and the PV/storage mix?

**Patterns the model must reproduce** (checked during validation)

- A daily "duck curve": community net load drops at midday and peaks in the evening.
- Clearly higher **self-sufficiency** in summer than in winter. (Self-consumption, the share of PV used locally, is *lower* in summer, because the summer surplus exceeds local demand; v0.1 stated this pattern the wrong way round.)
- Without storage, most PV surplus is exported around midday.
- Households without PV still benefit from cheaper local energy, but less than prosumers (under mid-market pricing).

### 2. Entities, state variables and scales

The model has two agent types: the **Household** (many) and the **CommunityManager** (one), which operates the local market, holds the community battery and bills every household. There are three non-agent entities: the **Battery** (community or home), the **Grid** and the **Community** (the Mesa model, which holds the environment, the scenario parameters and the schedule).

| Entity | State variable | Unit | Type |
| --- | --- | --- | --- |
| Household | `base_demand` (hourly demand for the year, before demand response) | kWh | static, varies by household |
| Household | `demand_profile` (hourly demand after demand response) | kWh | dynamic |
| Household | `annual_kwh` (annual demand) | kWh | static |
| Household | `pv_kwp` (installed solar, 0 = consumer only) | kWp | static |
| Household | `battery` (home battery, only in the "individual" storage mode) | – | static / dynamic |
| Household | `flexibility` (share of daily load it can shift) | 0–1 | static |
| Household | `dr_threshold` (minimum expected saving that makes it shift load) | €/kWh | static |
| Household | `cooperation` (probability it offers its surplus to the community in a step) | 0–1 | static |
| Household | `is_member` (in the community or not) | bool | dynamic |
| Household | `cost_eur`, `revenue_eur`, `energy_imported_kwh`, `energy_exported_kwh`, `energy_shared_kwh`, `lost_load_kwh` | €, kWh | dynamic, accumulated |
| Household | reference bill and lost load without community (see 7.7) | €, kWh | static series |
| Battery | `capacity_kwh`, `soc`, `p_max_kw` (= C-rate × capacity), round-trip efficiency | kWh, 0–1, kW, – | static / dynamic |
| Grid | `import_price`, `export_price` | €/kWh | input, flat |
| Grid | `grid_available` (false during an outage) | bool per hour | generated at start |
| Community | `pricing`, `storage_mode` (none / individual / shared), `storage_kwh`, `membership` | – | scenario parameter |
| CommunityManager | `supply`, `bids`, `traded` (members' offers, bids and energy matched locally this step) | kWh | dynamic |
| CommunityManager | `battery` (the community battery, only in the "shared" storage mode), `fixed_price` | –, €/kWh | static |
| CommunityManager | `local_price` (internal price this step) | €/kWh | dynamic |
| CommunityManager | `effective_price` (average price a member paid per kWh of deficit this step) and `price_forecast` (by hour of day) | €/kWh | dynamic |
| CommunityManager | `battery_cash_eur` (net income of the community battery) | € | dynamic, accumulated |

**Scales**

- **Time step:** 1 hour. **Horizon:** 1 year (8,760 steps, 2023, a non-leap year), so seasonal variation is captured. Steps are indexed in UTC; rules that depend on the time of day use Portuguese legal time (Europe/Lisbon), so the daylight-saving changes are handled correctly.
- **Space:** not explicit. All households sit behind one connection point, and grid losses and line limits are ignored.
- **Size:** 20–50 households (baseline 30).

### 3. Process overview and scheduling

Each hourly step runs the same processes in a fixed order. Households act in random order (`model.agents.shuffle_do`) where order matters.

1. **Update environment:** read this hour's PV yield and demand, and grid availability from the outage schedule. At local midnight, update the price forecast with yesterday's effective prices.
2. **Membership (every 30 days, at local midnight):** households may leave or join depending on their recent savings (7.6). Off in the baseline.
3. **Demand response (daily, at local midnight):** flexible households plan today's load shift from the price forecast (7.4).
4. **Self-consumption:** each household covers its own demand from its PV, then charges or discharges its home battery (if any), and computes its net position: surplus or deficit (7.1).
5. **Local market:** the CommunityManager collects offers (surplus of cooperating members) and bids (deficits of members), matches them pro rata and sets `local_price` with the active pricing mechanism (7.3).
6. **Community storage:** the CommunityManager charges the shared battery with leftover offers and serves leftover bids from it, within power and SoC limits (7.2).
7. **Grid exchange and settlement:** any remaining deficit is imported and any remaining surplus exported if the grid is available; during an outage they become *lost load* and *curtailment* (7.5). The CommunityManager then books costs and revenues to each household.

State updates are **synchronous within a step**: all households compute their net position (step 4) before the market clears (step 5), and membership decisions use the state before the review. The `DataCollector` records community-level flows and prices at the end of every step; household results are read at the end of the run.

### 4. Design concepts

Community-level self-sufficiency, savings, fairness and size *emerge* from household-level rules. None of them is imposed directly.

| Concept | In this model |
| --- | --- |
| Basic principles | Collective self-consumption and peer-to-peer energy sharing behind one grid connection; local prices sit between the grid export and import prices, so trading locally is never worse than trading with the grid for either side (except under bill-sharing). |
| Emergence | Community self-sufficiency, peak grid import, total savings, how savings are distributed (fairness) and how many households stay in the community. |
| Adaptation | Flexible households shift load toward hours with the lowest expected price. In membership scenarios, a household leaves if its recent savings fall below a threshold, and joins if members like it are saving. |
| Objectives | Each household minimises its energy bill. The CommunityManager has no objective of its own; it only applies the market rule. |
| Learning | Not included. Possible extension: households adjust `cooperation` based on past gains. |
| Prediction | Prices: exponentially smoothed effective price per hour of day from past days (weight 0.3 on the latest day). PV (for non-members' demand response): persistence, today = yesterday. |
| Sensing | Households know their own state, the community's price forecast and, for membership decisions, the average recent savings of members of their own type (prosumer or consumer), as a community would publish them. They do not see other households' individual data. |
| Interaction | Households interact only through the CommunityManager: they send it offers and bids, and it returns matched energy, the price and the bill. There is no direct household-to-household negotiation. |
| Stochasticity | Demand noise and peak shift, PV sizes, annual demand, demand-response thresholds, initial members, outage start and duration, cooperation draws, membership draws, activation order. Weather is the real 2023 series. Controlled by the model seed; outages use a separate random stream so that changing outage parameters does not change the population. |
| Collectives | The community itself; prosumers versus consumers for reporting. |
| Observation | Per step: energy flows (PV, demand, self-use, shared, battery charge and discharge, imported, exported, lost load, curtailment), local and effective price, storage SoC, number of members. Per run: KPIs in section 8. |

### 5. Initialisation

The baseline starts on 1 January 2023 with 30 households and every battery at 50% state of charge. All values below are **starting assumptions** to calibrate later.

| Parameter | Baseline value | Varied in experiments |
| --- | --- | --- |
| Number of households | 30 | 20, 30, 50 |
| Share with PV | 40% (exactly round(n × share) prosumers, chosen at random) | 20–80% |
| PV size per prosumer | 2–5 kWp (uniform) | – |
| Annual demand per household | 2,500–5,000 kWh (uniform) | – |
| Demand noise | hourly multiplicative noise, standard deviation 10–20% (uniform per household); profile shifted by −1, 0 or +1 h | – |
| Pricing mechanism | mid-market | all six (7.3) |
| Grid prices | import 0.20 €/kWh, export 0.05 €/kWh, flat (placeholders) | export 0.03 / 0.08 |
| Fixed local price | 0.10 €/kWh | – |
| Storage | none | shared or individual, 50 / 100 / 200 kWh total |
| Battery C-rate, round-trip efficiency | 0.5, 90% | efficiency 80% / 95% |
| `flexibility` | 0 (off) | 0.1, 0.2 |
| `dr_threshold` | 0–0.03 €/kWh (uniform per household) | – |
| `cooperation` | 1.0 (all cooperate) | 0.5, 0.75 |
| Outages | 4 per year, 1–8 h | 12 per year; 4–12 h |
| Membership change | off; all households members | on: 80% members at start, threshold 0 / 2 / 5 € per 30 days, p_leave 0.5, p_join 0.2 |

In the "individual" storage mode the total capacity is split over prosumers in proportion to their PV size: a home battery charges only from its own PV, so it would be idle in a consumer's home.

Household attributes are drawn from the seeded `model.random` and `model.rng`, so a seed fully reproduces the initial population. Every scenario run with the same seed has the same households, weather and outages (common random numbers).

### 6. Input data

Two hourly time series drive the model. They are prepared once by scripts, saved as CSV (8,760 rows each, indexed by the start of the hour in UTC, with local time alongside), and read at start-up. The model never calls an external API.

| Input | Source | Processing |
| --- | --- | --- |
| PV yield per kWp, Porto | [PVGIS v5.3](https://re.jrc.ec.europa.eu/pvg_tools/en/) (EU JRC), PVGIS-SARAH3, lat 41.15, lon −8.61, year 2023, optimal angles (35°, azimuth 3°), 14% system losses | `scripts/get_pvgis.py`: hourly power of a 1 kWp system (W) → kWh per kWp. Annual yield 1,520 kWh/kWp. Scaled by each household's `pv_kwp`. |
| Household load shape | [E-REDES](https://www.e-redes.pt/pt-pt/perfis-de-consumo) / ERSE standard profile **BTN C** for 2023 (low-voltage residential, ≤13.8 kVA, ≤7,140 kWh/yr), 15-min, legal time | `scripts/prep_load.py`: quarter-hours summed to hours and normalised to sum to 1. Scaled by each household's annual demand, with noise and shift added in the model (section 5). |
| Grid import and export prices | Portuguese regulated tariffs ([ERSE](https://www.erse.pt/)) | Placeholders until decided (flat 0.20 / 0.05 €/kWh). |
| Outage events | Generated inside the model | See 7.5. |

### 7. Submodels

Each process in section 3 maps to one submodel below.

#### 7.1 Household net position

For household *i* at step *t*, with PV yield per kWp *y(t)* and demand *d\_i(t)*:

```latex
n_i(t) = pv_i \cdot y(t) - d_i(t)
```

The household first uses its own PV (self-use = min(PV, demand)). If *n\_i* > 0 it charges its home battery (if any), and offers the rest to the community with probability `cooperation` (if it is a member; otherwise the rest is exported). If *n\_i* < 0 it discharges its home battery, then bids for the rest (members) or imports it.

#### 7.2 Battery (home and community)

```latex
SoC(t+1) = SoC(t) + \frac{\eta_c \, E_{ch}(t) - E_{dis}(t) / \eta_d}{C}
```

Here *C* is capacity (kWh), η\_c = η\_d = √(round-trip efficiency), and *E\_ch*, *E\_dis* (measured on the AC side) are limited by *p\_max* × 1 h and by SoC staying within \[0, 1\]. The community battery charges only from members' offers left over after the market and discharges only to members' bids left over after the market; it does not charge from the grid and keeps no reserve for outages. It buys its charge from sellers and sells its discharge to buyers at the step's local price; its net income (`battery_cash_eur`) belongs to the community and counts towards community savings.

#### 7.3 Local market and pricing mechanisms

Total supply *S* = sum of members' offers and total demand *D* = sum of members' bids. Traded volume = min(*S*, *D*), allocated pro rata to sellers and buyers. *p\_imp* and *p\_exp* are the grid import and export prices. Except for bill-sharing, both sides of every local trade use the same price.

| Mechanism | Local price rule |
| --- | --- |
| No community (reference) | Every household trades only with the grid |
| Fixed price | One constant price between *p\_exp* and *p\_imp* (0.10 €/kWh) |
| Mid-market rate | (*p\_imp* + *p\_exp*) / 2; with flat grid prices this is also constant |
| Supply–demand ratio (SDR) | Liu et al. (2017), formula below |
| Dynamic | Symmetric supply–demand price, formula below |
| Bill-sharing | Long et al. (2017): the community nets its members' grid exchange; the import bill is split by each member's deficit and the export income by each member's offer. Energy exchanged between members has no price. |

SDR pricing, with SDR = *S* / *D*. For 0 ≤ SDR ≤ 1:

```latex
P_{sell} = \frac{p_{imp} \, p_{exp}}{(p_{imp} - p_{exp}) \, SDR + p_{exp}}, \qquad P_{buy} = P_{sell} \, SDR + p_{imp} \, (1 - SDR)
```

For SDR > 1 (or *D* = 0), both prices equal *p\_exp*. Buyers pay *P\_sell* on their local share and *p\_imp* on the rest, which equals *P\_buy* on their whole deficit. Note that already at SDR = 1 the price is *p\_exp*, so sellers gain nothing whenever supply covers demand.

Dynamic pricing:

```latex
p_{local} = p_{exp} + (p_{imp} - p_{exp}) \, \frac{D}{S + D}
```

It equals *p\_exp* with a large surplus, the mid-point when *S* = *D*, and *p\_imp* under scarcity.

After settlement, the community records the **effective price** a member paid per kWh of deficit in that step: the share served locally (market and community battery) at the local price and the rest at *p\_imp* (under bill-sharing: the import bill divided by total bids). This is the price signal used by demand response.

#### 7.4 Demand response

Once a day, at local midnight, each flexible household plans the day. It values each hour of the day at an expected price: for members, the community's smoothed effective-price forecast for that hour of day (section 4, Prediction); for non-members (or with no community), *p\_exp* in hours where it expects its own PV to exceed its demand (persistence forecast) and *p\_imp* otherwise. Let *p\_eve* be the demand-weighted expected price of the evening hours (17:00–22:00). The expected gain of moving load to hour *h* outside the evening is max(0, *p\_eve* − *p\_h*). If the largest gain is at least the household's `dr_threshold`, it moves min(`flexibility` × daily demand, evening demand) out of the evening, proportionally, and into the other hours in proportion to their gains. Total daily demand stays the same.

#### 7.5 Grid outages

Outages start as a Poisson process with rate λ (baseline: 4 per year) and last a random whole number of hours (baseline 1–8, uniform); outages do not overlap. During an outage, only local PV and batteries can serve demand: deficits that cannot be served are booked as **lost load** (kWh) and surpluses that cannot be used or stored as **curtailment** (kWh). Neither is billed.

#### 7.6 Membership change

Every 30 days (at local midnight), each household compares its savings over the last 30 days with the no-community reference (7.7). A **member** whose savings are below a threshold leaves with probability *p\_leave* (0.5). The threshold stands for the cost of taking part (fees, effort). A **non-member** joins with probability *p\_join* (0.2) if the average 30-day savings of current members of its own type (prosumer or consumer) exceed the threshold. Decisions use the state before the review. Non-members trade only with the grid; they keep any home battery and can still do demand response on their own (7.4). In membership scenarios 20% of households start outside the community.

#### 7.7 No-community reference

Savings are measured against a reference computed per household at initialisation: the same household, weather and outages, using its own PV only, with no community, no battery and no demand response, at the same grid prices. Because the reference depends only on the seed, all scenarios with the same seed share it and their savings are directly comparable.

### 8. Experiments, KPIs and statistical analysis

Each scenario runs 30 times with seeds 0–29 (`experiments/run_experiments.py`, process pool; `mesa.batch_run` is not used because the KPIs are run-level quantities computed once at the end). Every KPI is reported as a mean with a 95% t confidence interval. This covers the course requirement for quantitative analysis.

**KPIs (per run)**

| KPI | Definition | Answers |
| --- | --- | --- |
| Community savings | Σ households (reference bill − actual bill) + community battery income, €/year; equals reference grid bill − actual grid bill | RQ1–3 |
| Self-sufficiency | (demand − imported − lost load) / demand, % | RQ2, RQ3 |
| Self-consumption | (PV − exported − curtailment) / PV, % | RQ2 |
| Peak grid import | highest hourly import, kW | RQ2, RQ3 |
| Fairness | Gini coefficient of per-household savings (0 = equal; can exceed 1 when some savings are negative), mean savings of prosumers and consumers | RQ1 |
| Membership | average share of households in the community over the year; members and prosumer members at the end; number of leaves and joins | RQ1 |
| Resilience | share of demand served during outages, %; lost load, kWh (and lost load of the reference); curtailment, kWh | RQ4 |

**Experiment design** (`experiments/designs.py`)

| | Design | Scenarios |
| --- | --- | --- |
| E1 | Pricing: 6 mechanisms × PV share 20/40/60/80%, membership on (threshold 2 € per 30 days) | 24 |
| E1b | Pricing × membership threshold 0 / 2 / 5 € per 30 days, 40% PV | 18 |
| E2 | Storage: none vs. individual vs. shared, same total 50 / 100 / 200 kWh | 7 |
| E3 | Demand response: flexibility 0 / 0.1 / 0.2 × mid-market, SDR, dynamic | 9 |
| E4 | Resilience: 3 outage regimes (4/yr 1–8 h, 12/yr 1–8 h, 4/yr 4–12 h) × no / individual / shared 100 kWh storage × 20 / 30 / 50 households | 27 |
| E5 | Sensitivity (one at a time, around mid-market + 100 kWh shared battery): cooperation 0.5 / 0.75, battery efficiency 80% / 95%, export price 0.03 / 0.08 €/kWh | 7 |

**Statistics** (`experiments/stats.py`, `notebooks/02_experiments.ipynb`): Shapiro–Wilk and Levene checks, one-way ANOVA and Kruskal–Wallis (used as the robust test when normality or equal variances fail) to compare scenarios, Tukey HSD for pairs, and, because scenarios share seeds, paired t-tests and Wilcoxon signed-rank tests on seed-matched differences for direct two-scenario comparisons. A replication check reports the largest relative CI half-width per KPI to confirm that 30 replications give narrow enough intervals.

**Verification and validation:** automated tests (`tests/test_model.py`) check, among others, the energy balance at every step

PV + import + discharge + lost load = demand + export + charge + curtailment

(charge and discharge include home and community batteries), that community savings equal the reduction of the grid bill under every mechanism (local trades are transfers between members), reproducibility with a fixed seed, that the reference is shared across scenarios, battery limits, no grid exchange during outages, conservation of daily demand under demand response, price bounds, and membership behaviour. Validation checks the four patterns in section 1 (`notebooks/01_data_check.ipynb` and model output).

**Open decisions**

- [ ] Final 2–3 research questions to keep (four may be too many for the timeline)
- [ ] Exact tariff values and whether to use time-of-use pricing
- [ ] Justify the participation threshold and *p\_leave* / *p\_join* (e.g. real Portuguese energy-community fees); add them to the sensitivity analysis
- [ ] Outage reserve for the community battery (minimum SoC) as a resilience policy

**References**

- Grimm, V. et al. (2020). The ODD protocol for describing agent-based and other simulation models: a second update. *JASSS* 23(2), 7.
- Liu, N. et al. (2017). Energy-sharing model with price-based demand response for microgrids of peer-to-peer prosumers. *IEEE Transactions on Power Systems* 32(5).
- Long, C. et al. (2017). Peer-to-peer energy trading in a community microgrid. *IEEE PES General Meeting*.
- ERSE (2022). Diretiva n.º 27/2022: perfis de consumo, de produção e de autoconsumo para 2023.
- Huld, T. et al. / EU JRC. PVGIS — Photovoltaic Geographical Information System, v5.3.

*Citations are approximate and should be checked before submission.*

---

# Part E. Experiment results

Source: `experiments/results/*.csv` (one row per scenario and seed). Each cell is the mean ± 95% t confidence half-width over 30 seeds (0–29). Savings are €/year against the no-community reference (community total, or mean per prosumer / consumer). Baseline unless stated: 30 households, 40% PV, mid-market, no storage, 4 outages/year, placeholder tariffs 0.20 / 0.05 €/kWh. Figures are in `notebooks/figures/`; statistical tests (ANOVA, Kruskal–Wallis, Tukey, paired tests) are in `notebooks/02_experiments.ipynb`.

## E1. Pricing x PV share (membership on, threshold 2 €/30 days)

| scenario | savings € | Gini | prosumer € | consumer € | member share | prosumer members (end) | leaves | joins |
|---|---|---|---|---|---|---|---|---|
| none / pv 20% | 0 | 0 | 0 | 0 | 0.800 | 4.87 ± 0.376 | 0 | 0 |
| fixed / pv 20% | 2,884 ± 124 | 0.238 ± 0.00877 | 161 ± 6.90 | 79.9 ± 3.43 | 0.927 ± 0.0116 | 5.97 ± 0.0682 | 0.400 ± 0.625 | 5.93 ± 0.537 |
| mid_market / pv 20% | 2,874 ± 127 | 0.386 ± 0.00706 | 240 ± 10.6 | 59.7 ± 2.64 | 0.920 ± 0.0146 | 5.97 ± 0.0682 | 2.27 ± 1.34 | 6.47 ± 0.739 |
| sdr / pv 20% | 2,709 ± 135 | 0.242 ± 0.0144 | 42.1 ± 2.31 | 102 ± 5.81 | 0.894 ± 0.0159 | 5.07 ± 0.293 | 3.47 ± 1.29 | 8.17 ± 1.07 |
| dynamic / pv 20% | 2,852 ± 135 | 0.416 ± 0.0126 | 249 ± 10.7 | 56.5 ± 3.23 | 0.893 ± 0.0218 | 5.97 ± 0.0682 | 6.30 ± 2.09 | 8.07 ± 1.22 |
| bill_sharing / pv 20% | 427 ± 79.6 | 0.825 ± 0.0139 | -23.7 ± 4.42 | 23.7 ± 4.42 | 0.344 ± 0.0490 | 0 | 27.0 ± 0.514 | 3.13 ± 0.526 |
| none / pv 40% | 0 | 0 | 0 | 0 | 0.800 | 9.20 ± 0.409 | 0 | 0 |
| fixed / pv 40% | 2,845 ± 55.4 | 0.199 ± 0.0106 | 79.7 ± 1.51 | 105 ± 2.08 | 0.927 ± 0.00924 | 11.2 ± 0.335 | 0.833 ± 0.368 | 5.93 ± 0.218 |
| mid_market / pv 40% | 2,845 ± 56.2 | 0.235 ± 0.0123 | 119 ± 2.30 | 78.6 ± 1.59 | 0.929 ± 0.00921 | 11.8 ± 0.142 | 0.0667 ± 0.0947 | 5.70 ± 0.200 |
| sdr / pv 40% | 2,345 ± 65.2 | 0.433 ± 0.00782 | 12.8 ± 0.578 | 122 ± 3.72 | 0.735 ± 0.00928 | 4.80 ± 0.558 | 16.5 ± 1.05 | 15.1 ± 1.01 |
| dynamic / pv 40% | 2,852 ± 57.4 | 0.204 ± 0.0119 | 88.6 ± 2.70 | 99.4 ± 2.15 | 0.928 ± 0.00943 | 11.4 ± 0.234 | 0.633 ± 0.286 | 5.93 ± 0.258 |
| bill_sharing / pv 40% | 580 ± 69.5 | 0.986 ± 0.0134 | -16.0 ± 1.93 | 42.9 ± 5.15 | 0.341 ± 0.0327 | 0 | 25.7 ± 0.635 | 2.17 ± 0.368 |
| none / pv 60% | 0 | 0 | 0 | 0 | 0.800 | 14.3 ± 0.438 | 0 | 0 |
| fixed / pv 60% | 2,101 ± 66.7 | 0.375 ± 0.0102 | 39.5 ± 1.24 | 116 ± 3.69 | 0.868 ± 0.0106 | 13.1 ± 0.526 | 7.70 ± 0.905 | 8.50 ± 0.807 |
| mid_market / pv 60% | 2,130 ± 58.8 | 0.234 ± 0.0108 | 59.8 ± 1.64 | 87.8 ± 2.45 | 0.919 ± 0.00911 | 15.7 ± 0.429 | 3.00 ± 0.643 | 6.53 ± 0.447 |
| sdr / pv 60% | 1,624 ± 110 | 0.630 ± 0.00790 | 4.79 ± 0.354 | 128 ± 8.82 | 0.527 ± 0.0269 | 4.07 ± 0.665 | 25.5 ± 1.31 | 16.3 ± 1.51 |
| dynamic / pv 60% | 2,116 ± 54.8 | 0.442 ± 0.0116 | 31.8 ± 1.36 | 129 ± 2.93 | 0.812 ± 0.0154 | 12.4 ± 0.457 | 13.8 ± 1.39 | 14.1 ± 1.34 |
| bill_sharing / pv 60% | 628 ± 66.3 | 1.17 ± 0.0150 | -11.5 ± 1.22 | 69.6 ± 7.36 | 0.299 ± 0.0234 | 0 | 25.5 ± 0.447 | 1.70 ± 0.406 |
| none / pv 80% | 0 | 0 | 0 | 0 | 0.800 | 19.1 ± 0.330 | 0 | 0 |
| fixed / pv 80% | 1,112 ± 44.0 | 0.604 ± 0.00802 | 16.0 ± 0.620 | 121 ± 4.87 | 0.627 ± 0.0146 | 11.1 ± 0.913 | 29.8 ± 1.39 | 22.8 ± 1.25 |
| mid_market / pv 80% | 1,123 ± 46.2 | 0.473 ± 0.0103 | 23.9 ± 0.979 | 91.3 ± 3.80 | 0.731 ± 0.0162 | 13.9 ± 0.720 | 22.6 ± 1.20 | 18.5 ± 1.16 |
| sdr / pv 80% | 820 ± 83.7 | 0.813 ± 0.00611 | 1.55 ± 0.176 | 130 ± 13.4 | 0.337 ± 0.0229 | 2.73 ± 0.975 | 28.6 ± 1.47 | 11.9 ± 2.47 |
| dynamic / pv 80% | 1,099 ± 45.4 | 0.702 ± 0.00657 | 10.5 ± 0.482 | 141 ± 5.77 | 0.520 ± 0.0124 | 9.43 ± 0.751 | 31.8 ± 1.82 | 23.2 ± 1.73 |
| bill_sharing / pv 80% | 391 ± 38.7 | 1.36 ± 0.0106 | -5.17 ± 0.531 | 85.9 ± 8.57 | 0.211 ± 0.0140 | 0 | 24.6 ± 0.288 | 0.733 ± 0.276 |

## E1b. Pricing x membership threshold (40% PV)

| scenario | savings € | Gini | prosumer € | consumer € | member share | leaves | joins |
|---|---|---|---|---|---|---|---|
| none / threshold 0 | 0 | 0 | 0 | 0 | 0.800 | 0 | 0 |
| fixed / threshold 0 | 2,845 ± 56.2 | 0.199 ± 0.0107 | 79.7 ± 1.53 | 105 ± 2.10 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| mid_market / threshold 0 | 2,845 ± 56.2 | 0.235 ± 0.0122 | 119 ± 2.30 | 78.6 ± 1.59 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| sdr / threshold 0 | 2,845 ± 56.2 | 0.459 ± 0.00810 | 7.43 ± 0.414 | 153 ± 3.04 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| dynamic / threshold 0 | 2,845 ± 56.2 | 0.205 ± 0.0120 | 88.3 ± 2.63 | 99.2 ± 2.15 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| bill_sharing / threshold 0 | 882 ± 85.8 | 0.979 ± 0.0163 | -24.4 ± 2.38 | 65.3 ± 6.35 | 0.531 ± 0.0267 | 22.7 ± 1.71 | 13.5 ± 1.65 |
| none / threshold 2 | 0 | 0 | 0 | 0 | 0.800 | 0 | 0 |
| fixed / threshold 2 | 2,845 ± 55.4 | 0.199 ± 0.0106 | 79.7 ± 1.51 | 105 ± 2.08 | 0.927 ± 0.00924 | 0.833 ± 0.368 | 5.93 ± 0.218 |
| mid_market / threshold 2 | 2,845 ± 56.2 | 0.235 ± 0.0123 | 119 ± 2.30 | 78.6 ± 1.59 | 0.929 ± 0.00921 | 0.0667 ± 0.0947 | 5.70 ± 0.200 |
| sdr / threshold 2 | 2,345 ± 65.2 | 0.433 ± 0.00782 | 12.8 ± 0.578 | 122 ± 3.72 | 0.735 ± 0.00928 | 16.5 ± 1.05 | 15.1 ± 1.01 |
| dynamic / threshold 2 | 2,852 ± 57.4 | 0.204 ± 0.0119 | 88.6 ± 2.70 | 99.4 ± 2.15 | 0.928 ± 0.00943 | 0.633 ± 0.286 | 5.93 ± 0.258 |
| bill_sharing / threshold 2 | 580 ± 69.5 | 0.986 ± 0.0134 | -16.0 ± 1.93 | 42.9 ± 5.15 | 0.341 ± 0.0327 | 25.7 ± 0.635 | 2.17 ± 0.368 |
| none / threshold 5 | 0 | 0 | 0 | 0 | 0.800 | 0 | 0 |
| fixed / threshold 5 | 2,761 ± 62.3 | 0.241 ± 0.0116 | 77.2 ± 1.71 | 102 ± 2.33 | 0.844 ± 0.0113 | 13.6 ± 1.37 | 10.2 ± 0.946 |
| mid_market / threshold 5 | 2,616 ± 80.9 | 0.281 ± 0.0160 | 110 ± 3.33 | 72.3 ± 2.28 | 0.830 ± 0.0166 | 17.3 ± 1.29 | 11.7 ± 1.00 |
| sdr / threshold 5 | 1,520 ± 121 | 0.474 ± 0.0147 | 12.2 ± 1.00 | 76.3 ± 6.21 | 0.538 ± 0.0328 | 34.2 ± 2.57 | 17.9 ± 2.56 |
| dynamic / threshold 5 | 2,697 ± 77.4 | 0.256 ± 0.0159 | 85.4 ± 2.64 | 92.9 ± 2.91 | 0.830 ± 0.0146 | 17.0 ± 1.78 | 11.3 ± 1.06 |
| bill_sharing / threshold 5 | 573 ± 74.5 | 0.991 ± 0.0141 | -15.8 ± 2.06 | 42.4 ± 5.51 | 0.305 ± 0.0288 | 26.6 ± 0.800 | 2.67 ± 0.868 |

## E2. Storage: none / individual / shared, same total capacity (mid-market)

| scenario | savings € | self-sufficiency | self-consumption | peak import kW | battery cash € | served in outages | Gini |
|---|---|---|---|---|---|---|---|
| none | 3,060 ± 46.7 | 0.350 ± 0.00255 | 0.626 ± 0.0123 | 26.8 ± 0.378 | 0 | 0.315 ± 0.0721 | 0.201 ± 0.00645 |
| individual 50 kWh | 3,966 ± 48.5 | 0.409 ± 0.00453 | 0.755 ± 0.0121 | 26.3 ± 0.410 | 0 | 0.375 ± 0.0544 | 0.426 ± 0.00522 |
| shared 50 kWh | 4,898 ± 60.2 | 0.464 ± 0.00539 | 0.852 ± 0.0128 | 26.8 ± 0.378 | -174 ± 2.82 | 0.446 ± 0.0897 | 0.242 ± 0.00389 |
| individual 100 kWh | 4,490 ± 53.0 | 0.442 ± 0.00507 | 0.823 ± 0.0135 | 26.0 ± 0.420 | 0 | 0.418 ± 0.0398 | 0.465 ± 0.00607 |
| shared 100 kWh | 5,976 ± 129 | 0.531 ± 0.0106 | 0.983 ± 0.00602 | 26.7 ± 0.377 | -274 ± 10.5 | 0.495 ± 0.0959 | 0.266 ± 0.00398 |
| individual 200 kWh | 4,598 ± 56.9 | 0.448 ± 0.00533 | 0.836 ± 0.0136 | 25.5 ± 0.476 | 0 | 0.421 ± 0.0372 | 0.475 ± 0.00598 |
| shared 200 kWh | 6,133 ± 176 | 0.541 ± 0.0135 | 1.000 ± 0.000133 | 26.7 ± 0.377 | -282 ± 15.0 | 0.500 ± 0.0955 | 0.268 ± 0.00404 |

## E3. Demand response x pricing (all members)

| scenario | savings € | self-sufficiency | peak import kW | Gini | prosumer € | consumer € |
|---|---|---|---|---|---|---|
| mid_market / flex 0.0 | 3,060 ± 46.7 | 0.350 ± 0.00255 | 26.8 ± 0.378 | 0.201 ± 0.00645 | 128 ± 1.91 | 84.5 ± 1.33 |
| mid_market / flex 0.1 | 3,958 ± 52.4 | 0.403 ± 0.00297 | 25.2 ± 0.403 | 0.228 ± 0.00414 | 183 ± 2.15 | 97.6 ± 1.51 |
| mid_market / flex 0.2 | 4,601 ± 60.6 | 0.442 ± 0.00427 | 32.1 ± 0.615 | 0.253 ± 0.00403 | 225 ± 2.48 | 106 ± 1.80 |
| sdr / flex 0.0 | 3,060 ± 46.7 | 0.350 ± 0.00255 | 26.8 ± 0.378 | 0.436 ± 0.00322 | 7.81 ± 0.330 | 165 ± 2.56 |
| sdr / flex 0.1 | 3,972 ± 52.5 | 0.404 ± 0.00296 | 25.3 ± 0.413 | 0.323 ± 0.00437 | 45.5 ± 0.872 | 190 ± 2.92 |
| sdr / flex 0.2 | 4,625 ± 61.3 | 0.443 ± 0.00436 | 34.5 ± 0.806 | 0.253 ± 0.00635 | 78.8 ± 1.58 | 204 ± 3.72 |
| dynamic / flex 0.0 | 3,060 ± 46.7 | 0.350 ± 0.00255 | 26.8 ± 0.378 | 0.169 ± 0.00709 | 93.9 ± 1.98 | 107 ± 1.95 |
| dynamic / flex 0.1 | 3,994 ± 52.6 | 0.406 ± 0.00297 | 25.4 ± 0.423 | 0.169 ± 0.00798 | 157 ± 2.75 | 117 ± 2.32 |
| dynamic / flex 0.2 | 4,634 ± 62.6 | 0.444 ± 0.00452 | 33.7 ± 0.764 | 0.217 ± 0.00846 | 210 ± 2.73 | 117 ± 3.02 |

## E4. Resilience: outage regime x storage x community size (mid-market)

| scenario | served in outages | lost load kWh | lost load alone kWh | outage h | self-sufficiency |
|---|---|---|---|---|---|
| base (4/yr, 1-8 h) / no storage / n=20 | 0.311 ± 0.0722 | 111 ± 23.7 | 142 ± 28.0 | 19.0 ± 3.77 | 0.347 ± 0.00362 |
| base (4/yr, 1-8 h) / no storage / n=30 | 0.315 ± 0.0721 | 162 ± 35.5 | 205 ± 41.4 | 19.0 ± 3.77 | 0.350 ± 0.00255 |
| base (4/yr, 1-8 h) / no storage / n=50 | 0.317 ± 0.0722 | 271 ± 58.4 | 346 ± 68.5 | 19.0 ± 3.77 | 0.352 ± 0.00218 |
| base (4/yr, 1-8 h) / individual 100 / n=20 | 0.413 ± 0.0368 | 97.5 ± 19.9 | 142 ± 28.0 | 19.0 ± 3.77 | 0.435 ± 0.00745 |
| base (4/yr, 1-8 h) / individual 100 / n=30 | 0.418 ± 0.0398 | 141 ± 29.6 | 205 ± 41.4 | 19.0 ± 3.77 | 0.442 ± 0.00507 |
| base (4/yr, 1-8 h) / individual 100 / n=50 | 0.392 ± 0.0489 | 245 ± 51.0 | 346 ± 68.5 | 19.0 ± 3.77 | 0.421 ± 0.00414 |
| base (4/yr, 1-8 h) / shared 100 / n=20 | 0.494 ± 0.0925 | 80.3 ± 18.4 | 142 ± 28.0 | 19.0 ± 3.77 | 0.527 ± 0.0180 |
| base (4/yr, 1-8 h) / shared 100 / n=30 | 0.495 ± 0.0959 | 114 ± 27.9 | 205 ± 41.4 | 19.0 ± 3.77 | 0.531 ± 0.0106 |
| base (4/yr, 1-8 h) / shared 100 / n=50 | 0.457 ± 0.0916 | 207 ± 49.3 | 346 ± 68.5 | 19.0 ± 3.77 | 0.484 ± 0.00506 |
| frequent (12/yr, 1-8 h) / no storage / n=20 | 0.358 ± 0.0420 | 307 ± 43.6 | 401 ± 51.2 | 55.2 ± 7.14 | 0.347 ± 0.00362 |
| frequent (12/yr, 1-8 h) / no storage / n=30 | 0.359 ± 0.0418 | 452 ± 66.9 | 586 ± 77.8 | 55.2 ± 7.14 | 0.350 ± 0.00255 |
| frequent (12/yr, 1-8 h) / no storage / n=50 | 0.362 ± 0.0420 | 754 ± 107 | 983 ± 126 | 55.2 ± 7.14 | 0.352 ± 0.00218 |
| frequent (12/yr, 1-8 h) / individual 100 / n=20 | 0.437 ± 0.0327 | 267 ± 34.8 | 401 ± 51.2 | 55.2 ± 7.14 | 0.435 ± 0.00745 |
| frequent (12/yr, 1-8 h) / individual 100 / n=30 | 0.440 ± 0.0340 | 393 ± 56.6 | 586 ± 77.8 | 55.2 ± 7.14 | 0.442 ± 0.00507 |
| frequent (12/yr, 1-8 h) / individual 100 / n=50 | 0.421 ± 0.0353 | 677 ± 92.7 | 983 ± 126 | 55.2 ± 7.14 | 0.421 ± 0.00414 |
| frequent (12/yr, 1-8 h) / shared 100 / n=20 | 0.526 ± 0.0541 | 222 ± 36.8 | 401 ± 51.2 | 55.2 ± 7.14 | 0.527 ± 0.0180 |
| frequent (12/yr, 1-8 h) / shared 100 / n=30 | 0.528 ± 0.0545 | 327 ± 58.4 | 586 ± 77.8 | 55.2 ± 7.14 | 0.531 ± 0.0106 |
| frequent (12/yr, 1-8 h) / shared 100 / n=50 | 0.485 ± 0.0466 | 600 ± 93.9 | 983 ± 126 | 55.2 ± 7.14 | 0.484 ± 0.00506 |
| long (4/yr, 4-12 h) / no storage / n=20 | 0.295 ± 0.0669 | 197 ± 35.8 | 248 ± 45.1 | 33.3 ± 6.20 | 0.347 ± 0.00362 |
| long (4/yr, 4-12 h) / no storage / n=30 | 0.298 ± 0.0679 | 287 ± 52.6 | 360 ± 65.9 | 33.3 ± 6.20 | 0.350 ± 0.00255 |
| long (4/yr, 4-12 h) / no storage / n=50 | 0.299 ± 0.0678 | 484 ± 88.8 | 609 ± 111 | 33.3 ± 6.20 | 0.352 ± 0.00218 |
| long (4/yr, 4-12 h) / individual 100 / n=20 | 0.413 ± 0.0338 | 170 ± 31.8 | 248 ± 45.1 | 33.3 ± 6.20 | 0.435 ± 0.00745 |
| long (4/yr, 4-12 h) / individual 100 / n=30 | 0.420 ± 0.0362 | 244 ± 45.9 | 360 ± 65.9 | 33.3 ± 6.20 | 0.442 ± 0.00507 |
| long (4/yr, 4-12 h) / individual 100 / n=50 | 0.394 ± 0.0472 | 426 ± 81.1 | 609 ± 111 | 33.3 ± 6.20 | 0.421 ± 0.00414 |
| long (4/yr, 4-12 h) / shared 100 / n=20 | 0.465 ± 0.0791 | 147 ± 31.6 | 248 ± 45.1 | 33.3 ± 6.20 | 0.527 ± 0.0180 |
| long (4/yr, 4-12 h) / shared 100 / n=30 | 0.462 ± 0.0780 | 215 ± 44.6 | 360 ± 65.9 | 33.3 ± 6.20 | 0.531 ± 0.0106 |
| long (4/yr, 4-12 h) / shared 100 / n=50 | 0.417 ± 0.0727 | 396 ± 78.9 | 609 ± 111 | 33.3 ± 6.20 | 0.484 ± 0.00506 |

## E5. One-at-a-time sensitivity (mid-market + shared 100 kWh)

| scenario | savings € | self-sufficiency | Gini | battery cash € |
|---|---|---|---|---|
| baseline | 5,976 ± 129 | 0.531 ± 0.0106 | 0.266 ± 0.00398 | -274 ± 10.5 |
| cooperation 0.5 | 3,187 ± 93.0 | 0.359 ± 0.00728 | 0.208 ± 0.00449 | -62.3 ± 5.60 |
| cooperation 0.75 | 4,671 ± 134 | 0.450 ± 0.0104 | 0.241 ± 0.00430 | -167 ± 10.6 |
| efficiency 0.8 | 5,575 ± 124 | 0.514 ± 0.0104 | 0.273 ± 0.00409 | -565 ± 23.5 |
| efficiency 0.95 | 6,167 ± 130 | 0.539 ± 0.0107 | 0.262 ± 0.00393 | -133 ± 4.97 |
| export price 0.03 | 6,831 ± 148 | 0.531 ± 0.0106 | 0.265 ± 0.00393 | -252 ± 9.66 |
| export price 0.08 | 4,693 ± 99.6 | 0.531 ± 0.0106 | 0.266 ± 0.00408 | -307 ± 11.8 |
