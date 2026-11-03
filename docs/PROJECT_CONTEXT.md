# GridSimulation: full project context

Snapshot of the repository on 2026-10-22. One file meant to give an assistant everything needed to discuss, extend or present the model: the project brief, how the code is organised and run, the complete model specification (ODD protocol), a summary of all experiment results, and findings and known modelling issues that came up while analysing them.

Contents:

- Part A. Project brief
- Part B. Code map, how to run, interactive app
- Part C. Key findings and known modelling issues
- Part D. Model specification (ODD protocol, v0.4, verbatim)
- Part E. Experiment results (mean ± 95% CI over 30 seeds)

---

# Part A. Project brief

- **Course:** Modelling & Simulation, FEUP (M.EIC / M.IA), 2026-27. Theme 12: *Community Microgrid and Local Energy Sharing*. Households (consumers, and prosumers with PV) share locally generated electricity and interact with the wider grid. The project compares sharing/pricing mechanisms, collective storage and demand response, and looks at fairness and resilience to uncertain generation, demand peaks, grid outages and membership changes.
- **Paradigm:** agent-based model (Mesa 3.5, Python ≥ 3.12), with discrete outage events.
- **Team member using this file:** Ricardo, who prefers to talk in European Portuguese. Code, comments and project documents are in English.
- **Deliverables:** Git repository with documented code and a "How to Build & Run" README; ODD documentation (`docs/ODD.md`); presentation (15 min + 10 min discussion) with commented PPTX slides (problem statement and formalisation, methods and materials, results and discussion); demo video and recorded oral presentation. A statistical/quantitative analysis is mandatory.
- **Dates:** mini-test 15 Dec 2026; project submission 5 Jan 2027; presentations 6–8 Jan 2027.
- **Status:** model, tests, experiments (E1–E5, E2b) and statistical notebook are done. Still to do: group decisions (below), slides, video, final run script.

**Open decisions (with the group)**

- Narrow the four research questions (pricing, storage, demand response, resilience) to 2–3.
- Justify p_leave and p_join.
- Battery investment cost (none in the model).
- Whether the community battery keeps a reserve for outages.

**Already decided:**
- Membership change is in: monthly review, 20% start outside, leave if 30-day savings < threshold (p_leave 0.5), join if same-type members saved (p_join 0.2).
- **Membership threshold 0 € in the base**: real Portuguese communities charge consumers nothing to join or leave (Iberdrola: no costs, 30 days' notice, which matches the monthly review; Greenvolt: no joining cost; HEN is the exception, with a 15-year contract). 2 and 5 € per 30 days are tested in E1b as a nuisance cost; ERSE estimates average bills of 37.77 €/month (1,900 kWh/yr) to 97.73 €/month (5,000 kWh/yr), so 2 € is 2–5% of a bill.
- **Tariffs**: ERSE simple tariff 0.1711 €/kWh at all hours as the base. The bi-hourly tariff (0.1143 €/kWh off-peak 22:00–08:00, 0.2045 otherwise) is a sensitivity scenario in E5; ERSE moves off-peak to 22:30–08:30 in the second half of 2027, kept at 22–08 with 1 h steps. Export 0.05 €/kWh: typical fixed buy-back offers (e.g. Repsol), and OMIE's 2025 average (65.6 €/MWh, APREN) minus a 20–25% retailer fee gives the same.
- **The community battery only stores surplus.** Members pay the local price for the energy it delivers, and that money goes to the prosumers who filled it, in proportion to the energy each put in (`battery_income="prosumers"`). Its deliverable energy counts as supply in the price, and its energy is never priced below p_exp / round-trip efficiency, so storing never pays less than exporting and buyers never pay more than the grid.
- The `dynamic` community price was added and SDR kept for comparison; demand response is price-responsive.

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
experiments/         designs.py (E1-E5, E2b), run_experiments.py, run_baseline.py, stats.py, results/*.csv
notebooks/           01_data_check.ipynb (input sanity plots), 02_experiments.ipynb (statistics, figures)
tests/test_model.py  33 verification tests
docs/ODD.md          model specification (reproduced in Part D)
```

## Main classes

- `Community(mesa.Model)` in `model/model.py`. Holds the inputs (PV yield per kWp, load shape, local hour), grid tariffs and the outage schedule; creates the households and the manager; runs the hourly step; computes `kpis()` and `household_table()`. Constructor parameters and defaults: `n_households=30`, `pv_share=0.4`, `pv_kwp_range=(2, 5)`, `annual_kwh_range=(2500, 5000)`, `noise_sd_range=(0.10, 0.20)`, `max_shift_h=1`, `cooperation=1.0`, `flexibility=0.0`, `dr_threshold_range=(0, 0.03)`, `price_memory=0.3`, `membership=False`, `initial_member_share=1.0`, `review_days=30`, `savings_threshold=0.0`, `p_leave=0.5`, `p_join=0.2`, `pricing="mid_market"`, `fixed_price=0.10`, `tariff="simple"` (or `"bi_hourly"`), `import_price=0.1711`, `import_price_peak=0.2045`, `import_price_offpeak=0.1143`, `export_price=0.05`, `storage_mode="none"`, `storage_kwh=0.0`, `battery_c_rate=0.5`, `battery_efficiency=0.9`, `battery_income="prosumers"` (or `"unallocated"`), `outage_rate=4.0`, `outage_duration=(1, 8)`, `check_balance=True`, `rng=None` (seed).
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

Left column: play/step/reset controls (play interval, steps per frame; 24 = one day per frame) and scenario parameters (seed, households, PV share, pricing, grid tariff, storage mode and capacity, flexibility, outages per year, membership on/off, members at start, savings threshold). Changing a parameter needs Reset.

Main panel: a radial view of the community for the current hour. The community manager is a dark circle in the centre showing the local price and the kWh shared. Houses sit on a ring around it (two staggered rings above 34 houses). Each house has a line to the manager whose width is the energy exchanged that hour and whose arrow shows the direction. The house colour gives its state: orange = surplus (sharing or exporting), green = deficit covered locally, blue = importing from the grid, red = unserved (outage), grey = balanced. A dark blue roof means PV (a sun appears when it produces); a small gauge shows a home battery's charge; faded houses with dashed lines are non-members. The grid sits at the top, linked to the manager (blue line = import, yellow = export, red dashed with "GRID OUTAGE" during outages). The community battery sits at the bottom with its charge level. The background turns blue-grey at night.

Side panels: "Community manager, this hour" (offers, bids, matched locally, battery in/out, grid import/export, local price) and running KPIs since 1 January (members, community savings, mean savings of prosumers and consumers, community battery income, self-sufficiency, self-consumption, peak import, outage hours and unserved energy). Below: 72-hour charts of community energy flows and of prices.

---

# Part C. Key findings and known modelling issues

Numbers come from Part E (30 seeds, ERSE simple tariff 0.1711 / export 0.05 €/kWh, membership threshold 0 €, community battery energy paid to the prosumers who filled it) unless a single run is cited (seed 42, 30 households, 40% PV).

**1. Pricing only redistributes savings; it changes the total only through behaviour.** Each kWh shared locally instead of going through the grid saves the community p_imp − p_exp (0.1211 € with the simple tariff), whatever the local price P: the seller gains P − p_exp, the buyer p_imp − P. With free entry and exit (threshold 0) and no demand response, fixed, mid-market, SDR and dynamic give exactly the same total savings (E1, 40% PV: 2,297 €/yr each; Tukey p = 1). There is a test for this. Totals differ only when the price changes behaviour: who leaves or joins (when taking part has a cost, E1b), or how load is shifted (demand response, E3).

**2. SDR gives almost all the gain to buyers in this community.** SDR (Liu et al. 2017) sets the price to p_exp as soon as supply ≥ demand (SDR ≥ 1), and its curve is convex. With 40% PV and 2–5 kWp systems, supply covers demand in 59% of the hours with offers, and 81% of locally traded kWh are traded in those hours (seed 42). Without storage, SDR gives prosumers 6.6 €/yr and consumers 123 €/yr (E1, 40% PV; Gini 0.46), against 71 / 80 € under dynamic (Gini 0.21).

With a 0 € threshold nobody leaves under SDR: prosumers gain almost nothing but never lose, so they stay. **"SDR pushes prosumers out" holds only if taking part has a cost**: with a 2 € per 30 days nuisance cost (E1b), prosumers' ~0.5 €/month falls below it, they leave and rejoin (19 leaves, 16 joins a year) and total savings drop 21%; fixed, mid-market and dynamic are unaffected at 2 €. The unequal split under SDR holds in every case.

This is a finding, not a bug: the implementation matches Liu (buyers pay the SDR price on their local share and p_imp on the rest, which equals Liu's P_buy on their whole deficit; the manager's budget balances). Liu's setting differs: all participants are prosumers, so the asymmetry between seller and buyer roles cancels within each participant, and prosumers adjust consumption to the price (Stackelberg game), so the p_exp price at surplus is a signal to consume more. E3 supports this: with demand response, SDR prosumer savings rise from 7 € (flex 0) to 65 € (flex 0.2) and the Gini falls from 0.43 to 0.25. Our model amplifies the imbalance through fixed roles (60% of households never sell), frequent surplus and little flexibility by default.

**3. Dynamic is the symmetric alternative, but only while supply and demand are balanced.** p_local = p_exp + (p_imp − p_exp)·D/(S + D): mid-point at S = D, approaching p_exp only with a large surplus. At 40% PV it is as fair as the fixed price (Gini 0.21 vs 0.20). With more PV it also drifts towards p_exp and favours consumers (Gini 0.44 at 60% PV, 0.70 at 80%); mid-market is then the fairest.

**4. The community battery only stores energy, and the prosumers who filled it are paid when it is used.** Surplus that goes into the battery is not sold at that moment. Members served from the battery pay the local price of that hour, like any local energy, and that money goes to the households that filled it, in proportion to the energy each has put in since 1 January (`battery_income="prosumers"`, decided by the group). Round-trip losses are reported in kWh (about 10% of what goes in: ~2,240 kWh/yr at 100 kWh). Two rules make sure both sides always gain. (a) When members' offers leave a deficit, all the energy the battery can deliver that hour counts as local supply when the price is set, so under SDR and dynamic the price falls when the battery is full and rises when it is nearly empty. (b) When the battery delivers, the price is never below p_exp / round-trip efficiency (0.0556 €/kWh), so after losses a prosumer earns at least the export price for each kWh stored, and it never exceeds p_imp, so buyers always pay less than the grid. The money for the initial 50% charge (a few euros) stays with the community. The rule changes only the split, not total savings.

E2b (shared 100 kWh, all members, 30 seeds; total savings 4,803 €/yr under every mechanism):

| | Prosumers €/yr | Consumers €/yr | Gini | Paid for battery energy €/yr |
|---|---|---|---|---|
| Fixed (0.10) | 203 | 131 | 0.18 | 2,022 |
| Mid-market | 232 | 112 | 0.25 | 2,235 |
| SDR | 76 | 216 | 0.27 | 1,154 |
| **Dynamic** | 173 | 152 | **0.13** | 1,777 |
| Bill-sharing | −75 | 317 | 0.70 | 0 |

Dynamic pricing with a shared battery is the fairest combination (every Tukey pair p < 0.001). Under SDR night supply usually covers demand once the battery is counted, so the price sits at the floor and prosumers earn about the export price for what they store. Under mid-market prosumers earn about 0.10 € per kWh stored (vs 0.05 for exporting). Bill-sharing has no per-kWh price, so battery energy is free to buyers and prosumers end up worse off than alone; this follows from Long et al.'s definition but breaks the rule that prosumers are paid for their surplus. The model has no battery investment cost, so storage still looks free.

**5. Bill-sharing penalises prosumers.** Energy exchanged between members is effectively free to buyers, and sellers are paid only for the part of their offer that is exported. Prosumers end up worse off than alone (−25 €/yr at 40% PV), so they leave even at threshold 0 (12 leaves a year; 63% of households are members on average), savings are ~68% lower than the other mechanisms, and the Gini exceeds 1.

**6. The participation cost decides whether membership matters.** At 0 € only bill-sharing loses members; at 2 € SDR too; at 5 € every mechanism loses members (savings −12% to −22% for fixed, mid-market and dynamic; −55% for SDR) (E1b). An earlier version compared the 30-day savings over hours shifted by one, which made a few prosumers with near-zero savings leave by mistake; this is fixed and covered by a test.

**7. More PV lowers total savings.** E1: 2,324 €/yr at 20% PV, 2,297 at 40%, 1,713 at 60%, 919 at 80% (same for fixed, mid-market, SDR and dynamic). With more prosumers there are fewer deficits to sell to, and the extra surplus is exported at p_exp anyway.

**8. Storage (E2, mid-market).** At the same total capacity, one shared battery beats batteries spread over prosumers' homes: at 100 kWh, savings are 4,803 € vs 3,605 € (+1,199 €, paired p < 0.001) and self-sufficiency is 53% vs 44%. Home batteries concentrate the gain on prosumers and even lower consumers' savings (38 vs 68 €/yr without storage; Gini 0.46). The shared battery raises both groups (prosumers 232, consumers 112 €/yr; Gini 0.25 under mid-market, 0.13 under dynamic, see finding 4). Returns diminish above 100 kWh: at 200 kWh the shared battery already uses all the PV (self-consumption ≈ 100%). Peak import does not change (≈ 26.7 kW), because the battery charges only from local surplus and does no peak shaving.

**9. Demand response (E3, no storage).** Flexibility 0.1 adds ~720–750 €/yr and slightly lowers peak import (26.8 → 25.3 kW). At 0.2 savings rise by ~1,220–1,260 €/yr, but peak import rises to 32–35 kW: much load moves into the same hours and is imported on cloudy days (rebound peak). Under SDR, demand response mainly helps prosumers (finding 2).

**10. Tariff (E5, mid-market + shared 100 kWh).** The bi-hourly tariff raises community savings by 16% (5,577 vs 4,803 €/yr): most sharing happens in daytime, when the bi-hourly import price (0.2045) is above the simple one, so each shared kWh is worth more. Demand response interacts with the tariff: with the simple tariff and a shared battery, flexibility 0.1 adds only 1.6% (the battery already shifts midday surplus to the evening); with the bi-hourly tariff it adds 7% on top of bi-hourly alone (+24% against the baseline), because households move load to the cheap off-peak night hours rather than to midday, so self-sufficiency falls slightly (52.6% vs 53.1%) while bills fall, and consumers gain most (154 vs 112 €/yr). If the community instead bought the surplus when the battery charges (`battery_income="unallocated"`), prosumers would be paid for every kWh that goes in (253 vs 232 €/yr) and the community would bear the losses.

**11. Resilience (E4).** Without storage, about 31% of demand during outages is still served (by daytime PV). Individual batteries raise this to about 42% and a shared 100 kWh battery to about 50% (shared vs none: paired p < 0.001 in every regime; shared vs individual: p < 0.05 for base and frequent outages, not significant for long outages, when both run empty). The share falls for a 50-household community with the same 100 kWh battery. Confidence intervals are wide because outage timing (day or night) varies between seeds. The battery keeps no reserve for outages.

**12. Sensitivity (E5).** Cooperation matters most: savings fall 47% at cooperation 0.5. Then the export price (+18% at 0.03 €/kWh, −27% at 0.08) and the tariff (above). Battery efficiency matters less (−7% to +3% within 80–95%).

**Known simplifications:** flat export price; no battery capital cost; no network constraints or losses; a single local price for both sides (except bill-sharing); perfect metering; a non-member still sits behind the same connection point but is billed at grid prices; the community battery does not charge from the grid and keeps no outage reserve; battery ownership shares are cumulative from 1 January and do not depreciate; E1 also reports membership columns for the `none` scenario, where membership has no effect.

---

# Part D. Model specification (ODD protocol)

The text below is `docs/ODD.md` verbatim, with its headings moved down one level.

## Community Microgrid ABM — ODD Protocol (Draft v0.4)

Oct 22, 2026 · @Ricardo

Changes since v0.3: real tariffs (ERSE simple tariff 0.1711 €/kWh as the base;
bi-hourly tariff as a sensitivity scenario; export 0.05 €/kWh justified); base
membership threshold set to 0 € (joining and leaving real communities is free);
the community battery only stores energy: what members pay for the energy it
delivers goes to the prosumers who filled it; its round-trip losses are reported in kWh;
the energy it can deliver counts as local supply when the price is set, and its energy
is never priced below p_exp / round-trip efficiency, so storing is never worse than exporting.

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
| Grid | `import_prices` (import price for each hour; flat under the simple tariff), `export_price` | €/kWh | input |
| Grid | `grid_available` (false during an outage) | bool per hour | generated at start |
| Community | `pricing`, `storage_mode` (none / individual / shared), `storage_kwh`, `membership` | – | scenario parameter |
| CommunityManager | `supply`, `bids`, `traded` (members' offers, bids and energy matched locally this step) | kWh | dynamic |
| CommunityManager | `battery` (the community battery, only in the "shared" storage mode), `fixed_price` | –, €/kWh | static |
| CommunityManager | `local_price` (internal price this step) | €/kWh | dynamic |
| CommunityManager | `effective_price` (average price a member paid per kWh of deficit this step) and `price_forecast` (by hour of day) | €/kWh | dynamic |
| CommunityManager | `battery_revenue_eur` (paid by members for energy delivered by the community battery) and `battery_cash_unallocated_eur` (battery money paid to no household) | € | dynamic, accumulated |
| Household | `to_battery` (surplus put into the community battery this step), `battery_energy_kwh` (all the energy it has put in: its stake in the battery), `battery_income_eur` (money received for that energy) | kWh, € | dynamic |
| Battery | `charged_kwh`, `discharged_kwh`, `losses_kwh` (energy lost in charging and discharging) | kWh | dynamic, accumulated |

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
| Grid import tariff | ERSE simple tariff: 0.1711 €/kWh at all hours | ERSE bi-hourly: 0.1143 €/kWh off-peak (22:00–08:00), 0.2045 €/kWh otherwise |
| Grid export price | 0.05 €/kWh | 0.03 / 0.08 |
| Payment for community battery energy | to the prosumers who filled it, when the energy is used (7.2) | the community buys the surplus when it charges and keeps the income (unallocated) |
| Fixed local price | 0.10 €/kWh | – |
| Storage | none | shared or individual, 50 / 100 / 200 kWh total |
| Battery C-rate, round-trip efficiency | 0.5, 90% | efficiency 80% / 95% |
| `flexibility` | 0 (off) | 0.1, 0.2 |
| `dr_threshold` | 0–0.03 €/kWh (uniform per household) | – |
| `cooperation` | 1.0 (all cooperate) | 0.5, 0.75 |
| Outages | 4 per year, 1–8 h | 12 per year; 4–12 h |
| Membership change | off; all households members | on: 80% members at start, threshold 0 € (base) or 2 / 5 € per 30 days, p_leave 0.5, p_join 0.2 |

In the "individual" storage mode the total capacity is split over prosumers in proportion to their PV size: a home battery charges only from its own PV, so it would be idle in a consumer's home.

Household attributes are drawn from the seeded `model.random` and `model.rng`, so a seed fully reproduces the initial population. Every scenario run with the same seed has the same households, weather and outages (common random numbers).

### 6. Input data

Two hourly time series drive the model. They are prepared once by scripts, saved as CSV (8,760 rows each, indexed by the start of the hour in UTC, with local time alongside), and read at start-up. The model never calls an external API.

| Input | Source | Processing |
| --- | --- | --- |
| PV yield per kWp, Porto | [PVGIS v5.3](https://re.jrc.ec.europa.eu/pvg_tools/en/) (EU JRC), PVGIS-SARAH3, lat 41.15, lon −8.61, year 2023, optimal angles (35°, azimuth 3°), 14% system losses | `scripts/get_pvgis.py`: hourly power of a 1 kWp system (W) → kWh per kWp. Annual yield 1,520 kWh/kWp. Scaled by each household's `pv_kwp`. |
| Household load shape | [E-REDES](https://www.e-redes.pt/pt-pt/perfis-de-consumo) / ERSE standard profile **BTN C** for 2023 (low-voltage residential, ≤13.8 kVA, ≤7,140 kWh/yr), 15-min, legal time | `scripts/prep_load.py`: quarter-hours summed to hours and normalised to sum to 1. Scaled by each household's annual demand, with noise and shift added in the model (section 5). |
| Grid import price | ERSE regulated tariffs for low-voltage households ([ERSE](https://www.erse.pt/)): simple 0.1711 €/kWh; bi-hourly 0.2045 €/kWh outside off-peak and 0.1143 €/kWh off-peak | Energy price per kWh. Bi-hourly uses the daily cycle with off-peak 22:00–08:00 legal time. From the second half of 2027 ERSE moves off-peak to 22:30–08:30; with 1 h steps the model keeps 22:00–08:00. |
| Grid export price | Typical fixed-price buy-back offers for small producers (about 0.05 €/kWh, e.g. Repsol). Indexed offers pay the OMIE wholesale price (average 65.6 €/MWh in Jan–Oct 2025, APREN) minus a 20–25% retailer fee, also about 0.05 €/kWh. | 0.05 €/kWh; 0.03 and 0.08 in the sensitivity analysis. |
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

Here *C* is capacity (kWh), η\_c = η\_d = √(round-trip efficiency), and *E\_ch*, *E\_dis* (measured on the AC side) are limited by *p\_max* × 1 h and by SoC staying within \[0, 1\]. The community battery charges only from members' offers left over after the market and discharges only to members' bids left over after the market; it does not charge from the grid and keeps no reserve for outages. The battery does not trade: it only stores the members' leftover surplus and gives it back to members with a deficit. Surplus that goes into the battery is not sold at that moment; each seller's share is recorded (`to_battery`) and adds to its stake (`battery_energy_kwh`). Members served from the battery pay for that energy at the local price of the hour it is delivered, like any local energy. That money is paid to the households that filled the battery, in proportion to the energy each has put in since 1 January, whether or not it is still a member. So prosumers are compensated for the surplus they store when it is used, at the price of that hour; because of the round-trip losses, less energy comes out than went in (`losses_kwh`, about 10% at 90% efficiency). In the baseline (seed 42, shared 100 kWh, mid-market) prosumers receive about 0.10 € per kWh they put in, against 0.05 € for exporting it. Only prosumers can charge it. Money for the initial charge (50% SoC), before anyone has filled the battery, is not paid out and counts directly towards community savings; energy still stored at the end of the year is not paid for (the two roughly offset each other). The alternative rule `battery_income="unallocated"` treats the battery as owned by the community: the community buys the surplus from the sellers at the local price when it charges and keeps the income from discharging. Neither rule changes total community savings; they only change how savings are split. The model has no battery investment cost.

#### 7.3 Local market and pricing mechanisms

Total supply *S* = sum of members' offers and total demand *D* = sum of members' bids. Traded volume = min(*S*, *D*), allocated pro rata to sellers and buyers.

When there is a community battery and the members' offers leave part of the deficit unserved (*S* < *D*), all the energy the battery can deliver this hour, *B* (limited by its power limit and stored energy), also counts as local supply when the price is set: the formulas below use *S* + *B* in place of *S*. So under SDR and dynamic pricing, the fuller the battery the lower the price in the evening and at night, and a nearly empty battery leaves it close to *p\_imp*. The battery is not counted when members' offers already cover demand, since it then delivers nothing. In hours when the battery delivers energy, the local price is at least *p\_exp* / (round-trip efficiency) (0.0556 €/kWh at 90%). After losses, a prosumer then earns at least the export price for each kWh it stores, so storing is never worse than exporting; buyers still pay less than *p\_imp*. The floor binds mostly under SDR, whose price falls to *p\_exp* whenever supply covers demand, and occasionally under dynamic pricing when a full battery meets a small deficit. *p\_imp* and *p\_exp* are the grid import and export prices in that hour (*p\_imp* changes over the day under the bi-hourly tariff). Except for bill-sharing, both sides of every local trade use the same price.

| Mechanism | Local price rule |
| --- | --- |
| No community (reference) | Every household trades only with the grid |
| Fixed price | One constant price between *p\_exp* and *p\_imp* (0.10 €/kWh) |
| Mid-market rate | (*p\_imp* + *p\_exp*) / 2; constant under the simple tariff |
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

Every 30 days (at local midnight), each household compares its savings over the last 30 days with the no-community reference (7.7). A **member** whose savings are below a threshold leaves with probability *p\_leave* (0.5). The threshold stands for the cost of taking part. Real Portuguese energy communities charge consumers nothing to join or leave (Iberdrola: no joining or leaving costs, 30 days' notice; Greenvolt: no joining cost; HEN is the exception, with a 15-year contract and a penalty for leaving early), so the base threshold is 0 €, and the 30-day notice matches the monthly review. Thresholds of 2 and 5 € per 30 days are tested as a nuisance cost (time, attention, paperwork); against ERSE's estimated average bills of 37.77 €/month (couple, 1,900 kWh/year) and 97.73 €/month (family, 5,000 kWh/year), 2 € is about 2–5% of the bill. A **non-member** joins with probability *p\_join* (0.2) if the average 30-day savings of current members of its own type (prosumer or consumer) exceed the threshold. Decisions use the state before the review. Non-members trade only with the grid; they keep any home battery and can still do demand response on their own (7.4). In membership scenarios 20% of households start outside the community.

#### 7.7 No-community reference

Savings are measured against a reference computed per household at initialisation: the same household, weather and outages, using its own PV only, with no community, no battery and no demand response, at the same grid prices. Because the reference depends only on the seed, all scenarios with the same seed share it and their savings are directly comparable.

### 8. Experiments, KPIs and statistical analysis

Each scenario runs 30 times with seeds 0–29 (`experiments/run_experiments.py`, process pool; `mesa.batch_run` is not used because the KPIs are run-level quantities computed once at the end). Every KPI is reported as a mean with a 95% t confidence interval. This covers the course requirement for quantitative analysis.

**KPIs (per run)**

| KPI | Definition | Answers |
| --- | --- | --- |
| Community savings | Σ households (reference bill − actual bill) + community battery money not paid to any household, €/year; equals reference grid bill − actual grid bill | RQ1–3 |
| Storage | energy paid for from the community battery, €; energy lost in all batteries, kWh | RQ2 |
| Self-sufficiency | (demand − imported − lost load) / demand, % | RQ2, RQ3 |
| Self-consumption | (PV − exported − curtailment) / PV, % | RQ2 |
| Peak grid import | highest hourly import, kW | RQ2, RQ3 |
| Fairness | Gini coefficient of per-household savings (0 = equal; can exceed 1 when some savings are negative), mean savings of prosumers and consumers | RQ1 |
| Membership | average share of households in the community over the year; members and prosumer members at the end; number of leaves and joins | RQ1 |
| Resilience | share of demand served during outages, %; lost load, kWh (and lost load of the reference); curtailment, kWh | RQ4 |

**Experiment design** (`experiments/designs.py`)

| | Design | Scenarios |
| --- | --- | --- |
| E1 | Pricing: 6 mechanisms × PV share 20/40/60/80%, membership on (threshold 0 €) | 24 |
| E1b | Pricing × membership threshold 0 / 2 / 5 € per 30 days, 40% PV | 18 |
| E2 | Storage: none vs. individual vs. shared, same total 50 / 100 / 200 kWh | 7 |
| E2b | Pricing with storage: fixed, mid-market, SDR, dynamic, bill-sharing, each with a 100 kWh shared battery | 5 |
| E3 | Demand response: flexibility 0 / 0.1 / 0.2 × mid-market, SDR, dynamic | 9 |
| E4 | Resilience: 3 outage regimes (4/yr 1–8 h, 12/yr 1–8 h, 4/yr 4–12 h) × no / individual / shared 100 kWh storage × 20 / 30 / 50 households | 27 |
| E5 | Sensitivity (one at a time, around mid-market + 100 kWh shared battery): cooperation 0.5 / 0.75, battery efficiency 80% / 95%, export price 0.03 / 0.08 €/kWh, battery income unallocated, bi-hourly tariff, flexibility 0.1 with the simple and the bi-hourly tariff | 11 |

**Statistics** (`experiments/stats.py`, `notebooks/02_experiments.ipynb`): Shapiro–Wilk and Levene checks, one-way ANOVA and Kruskal–Wallis (used as the robust test when normality or equal variances fail) to compare scenarios, Tukey HSD for pairs, and, because scenarios share seeds, paired t-tests and Wilcoxon signed-rank tests on seed-matched differences for direct two-scenario comparisons. A replication check reports the largest relative CI half-width per KPI to confirm that 30 replications give narrow enough intervals.

**Verification and validation:** automated tests (`tests/test_model.py`) check, among others, the energy balance at every step

PV + import + discharge + lost load = demand + export + charge + curtailment

(charge and discharge include home and community batteries), that community savings equal the reduction of the grid bill under every mechanism (local trades are transfers between members), reproducibility with a fixed seed, that the reference is shared across scenarios, battery limits, no grid exchange during outages, conservation of daily demand under demand response, price bounds, and membership behaviour. Validation checks the four patterns in section 1 (`notebooks/01_data_check.ipynb` and model output).

**Open decisions**

- [ ] Final 2–3 research questions to keep (four may be too many for the timeline)
- [x] Tariff values: ERSE simple tariff as the base, bi-hourly as a sensitivity scenario; export 0.05 €/kWh
- [x] Participation threshold: 0 € as the base (free entry and exit); 2 / 5 € as a nuisance cost
- [x] Community battery: stores energy only; members pay for its energy when used, and that money goes to the prosumers who filled it
- [ ] Justify *p\_leave* / *p\_join*; add them to the sensitivity analysis
- [ ] Battery investment cost (currently none)
- [ ] Outage reserve for the community battery (minimum SoC) as a resilience policy

**References**

- Grimm, V. et al. (2020). The ODD protocol for describing agent-based and other simulation models: a second update. *JASSS* 23(2), 7.
- Liu, N. et al. (2017). Energy-sharing model with price-based demand response for microgrids of peer-to-peer prosumers. *IEEE Transactions on Power Systems* 32(5).
- Long, C. et al. (2017). Peer-to-peer energy trading in a community microgrid. *IEEE PES General Meeting*.
- ERSE (2022). Diretiva n.º 27/2022: perfis de consumo, de produção e de autoconsumo para 2023.
- Huld, T. et al. / EU JRC. PVGIS — Photovoltaic Geographical Information System, v5.3.
- ERSE. Regulated tariffs for low-voltage households (simple and bi-hourly), new time periods from 2027, and average bill estimates (press release).
- APREN. OMIE wholesale price statistics, January–October 2025.
- Commercial terms of Portuguese energy-community and buy-back offers: Iberdrola, Greenvolt, HEN, Repsol (websites).

*Citations are approximate and should be checked before submission.*

---

# Part E. Experiment results

Source: `experiments/results/*.csv` (one row per scenario and seed). Each cell is the mean ± 95% t confidence half-width over 30 seeds (0–29). Savings are €/year against the no-community reference (community total, or mean per prosumer / consumer). Baseline unless stated: 30 households, 40% PV, mid-market, no storage, 4 outages/year, ERSE simple tariff 0.1711 €/kWh, export 0.05 €/kWh, community battery energy paid to the prosumers who filled it. Figures are in `notebooks/figures/`; statistical tests (ANOVA, Kruskal–Wallis, Tukey, paired tests) are in `notebooks/02_experiments.ipynb`.

## E1. Pricing x PV share (membership on, threshold 0 €)

| scenario | savings € | Gini | prosumer € | consumer € | member share | prosumer members (end) | leaves | joins |
|---|---|---|---|---|---|---|---|---|
| none / pv 20% | 0 | 0 | 0 | 0 | 0.800 | 4.87 ± 0.376 | 0 | 0 |
| fixed / pv 20% | 2,324 ± 104 | 0.304 ± 0.00698 | 161 ± 7.20 | 56.7 ± 2.54 | 0.932 ± 0.00896 | 5.97 ± 0.0682 | 0 | 5.70 ± 0.200 |
| mid_market / pv 20% | 2,324 ± 104 | 0.382 ± 0.00615 | 194 ± 8.72 | 48.2 ± 2.16 | 0.932 ± 0.00896 | 5.97 ± 0.0682 | 0 | 5.70 ± 0.200 |
| sdr / pv 20% | 2,324 ± 104 | 0.233 ± 0.0146 | 34.7 ± 2.46 | 88.2 ± 4.72 | 0.932 ± 0.00896 | 5.97 ± 0.0682 | 0 | 5.70 ± 0.200 |
| dynamic / pv 20% | 2,324 ± 104 | 0.415 ± 0.0137 | 207 ± 6.45 | 45.1 ± 2.97 | 0.932 ± 0.00896 | 5.97 ± 0.0682 | 0 | 5.70 ± 0.200 |
| bill_sharing / pv 20% | 541 ± 58.5 | 0.874 ± 0.0181 | -37.2 ± 4.02 | 31.9 ± 3.44 | 0.778 ± 0.0103 | 0.767 ± 0.363 | 7.30 ± 0.581 | 7.50 ± 0.732 |
| none / pv 40% | 0 | 0 | 0 | 0 | 0.800 | 9.20 ± 0.409 | 0 | 0 |
| fixed / pv 40% | 2,297 ± 45.3 | 0.196 ± 0.0124 | 79.6 ± 1.53 | 74.5 ± 1.50 | 0.929 ± 0.00912 | 11.9 ± 0.114 | 0 | 5.70 ± 0.200 |
| mid_market / pv 40% | 2,297 ± 45.3 | 0.235 ± 0.0122 | 96.3 ± 1.86 | 63.4 ± 1.29 | 0.929 ± 0.00912 | 11.9 ± 0.114 | 0 | 5.70 ± 0.200 |
| sdr / pv 40% | 2,297 ± 45.3 | 0.457 ± 0.00819 | 6.58 ± 0.367 | 123 ± 2.45 | 0.929 ± 0.00912 | 11.9 ± 0.114 | 0 | 5.70 ± 0.200 |
| dynamic / pv 40% | 2,297 ± 45.3 | 0.205 ± 0.0120 | 71.3 ± 2.12 | 80.1 ± 1.74 | 0.929 ± 0.00912 | 11.9 ± 0.114 | 0 | 5.70 ± 0.200 |
| bill_sharing / pv 40% | 732 ± 78.6 | 1.06 ± 0.0127 | -25.1 ± 2.70 | 57.4 ± 6.17 | 0.628 ± 0.0109 | 1.53 ± 0.507 | 12.3 ± 0.826 | 7.50 ± 0.897 |
| none / pv 60% | 0 | 0 | 0 | 0 | 0.800 | 14.3 ± 0.438 | 0 | 0 |
| fixed / pv 60% | 1,713 ± 48.6 | 0.290 ± 0.0111 | 39.9 ± 1.12 | 82.9 ± 2.39 | 0.927 ± 0.00956 | 17.9 ± 0.129 | 0 | 5.63 ± 0.208 |
| mid_market / pv 60% | 1,713 ± 48.6 | 0.233 ± 0.0124 | 48.1 ± 1.35 | 70.5 ± 2.03 | 0.927 ± 0.00956 | 17.9 ± 0.129 | 0 | 5.63 ± 0.208 |
| sdr / pv 60% | 1,713 ± 48.6 | 0.639 ± 0.00769 | 2.53 ± 0.186 | 139 ± 3.94 | 0.927 ± 0.00956 | 17.9 ± 0.129 | 0 | 5.63 ± 0.208 |
| dynamic / pv 60% | 1,713 ± 48.6 | 0.442 ± 0.0126 | 24.1 ± 1.19 | 107 ± 2.53 | 0.927 ± 0.00956 | 17.9 ± 0.129 | 0 | 5.63 ± 0.208 |
| bill_sharing / pv 60% | 765 ± 46.4 | 1.26 ± 0.0151 | -17.4 ± 1.06 | 89.9 ± 5.45 | 0.478 ± 0.00915 | 1.33 ± 0.442 | 18.5 ± 0.745 | 7.57 ± 0.908 |
| none / pv 80% | 0 | 0 | 0 | 0 | 0.800 | 19.1 ± 0.330 | 0 | 0 |
| fixed / pv 80% | 919 ± 40.1 | 0.470 ± 0.00630 | 16.7 ± 0.697 | 86.1 ± 3.96 | 0.926 ± 0.00956 | 23.8 ± 0.161 | 0 | 5.67 ± 0.204 |
| mid_market / pv 80% | 919 ± 40.1 | 0.406 ± 0.00712 | 20.0 ± 0.839 | 73.3 ± 3.37 | 0.926 ± 0.00956 | 23.8 ± 0.161 | 0 | 5.67 ± 0.204 |
| sdr / pv 80% | 919 ± 40.1 | 0.796 ± 0.00449 | 2.02 ± 0.198 | 145 ± 6.61 | 0.926 ± 0.00956 | 23.8 ± 0.161 | 0 | 5.67 ± 0.204 |
| dynamic / pv 80% | 919 ± 40.1 | 0.697 ± 0.00584 | 6.80 ± 0.411 | 126 ± 5.29 | 0.926 ± 0.00956 | 23.8 ± 0.161 | 0 | 5.67 ± 0.204 |
| bill_sharing / pv 80% | 514 ± 47.8 | 1.46 ± 0.0102 | -8.54 ± 0.795 | 120 ± 11.1 | 0.326 ± 0.0106 | 1.40 ± 0.577 | 23.5 ± 1.25 | 6.73 ± 1.42 |

## E1b. Pricing x membership threshold (40% PV)

| scenario | savings € | Gini | prosumer € | consumer € | member share | leaves | joins |
|---|---|---|---|---|---|---|---|
| none / threshold 0 | 0 | 0 | 0 | 0 | 0.800 | 0 | 0 |
| fixed / threshold 0 | 2,297 ± 45.3 | 0.196 ± 0.0124 | 79.6 ± 1.53 | 74.5 ± 1.50 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| mid_market / threshold 0 | 2,297 ± 45.3 | 0.235 ± 0.0122 | 96.3 ± 1.86 | 63.4 ± 1.29 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| sdr / threshold 0 | 2,297 ± 45.3 | 0.457 ± 0.00819 | 6.58 ± 0.367 | 123 ± 2.45 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| dynamic / threshold 0 | 2,297 ± 45.3 | 0.205 ± 0.0120 | 71.3 ± 2.12 | 80.1 ± 1.74 | 0.929 ± 0.00912 | 0 | 5.70 ± 0.200 |
| bill_sharing / threshold 0 | 732 ± 78.6 | 1.06 ± 0.0127 | -25.1 ± 2.70 | 57.4 ± 6.17 | 0.628 ± 0.0109 | 12.3 ± 0.826 | 7.50 ± 0.897 |
| none / threshold 2 | 0 | 0 | 0 | 0 | 0.800 | 0 | 0 |
| fixed / threshold 2 | 2,300 ± 48.5 | 0.197 ± 0.0122 | 79.7 ± 1.65 | 74.6 ± 1.60 | 0.928 ± 0.00890 | 0.900 ± 0.371 | 5.97 ± 0.208 |
| mid_market / threshold 2 | 2,297 ± 45.3 | 0.236 ± 0.0123 | 96.3 ± 1.86 | 63.4 ± 1.28 | 0.928 ± 0.00924 | 0.400 ± 0.186 | 5.70 ± 0.200 |
| sdr / threshold 2 | 1,809 ± 53.6 | 0.430 ± 0.00918 | 11.9 ± 0.567 | 92.6 ± 3.07 | 0.718 ± 0.0135 | 19.3 ± 1.85 | 16.0 ± 1.00 |
| dynamic / threshold 2 | 2,306 ± 46.5 | 0.205 ± 0.0113 | 71.9 ± 2.13 | 80.2 ± 1.76 | 0.923 ± 0.00962 | 1.63 ± 0.465 | 6.03 ± 0.302 |
| bill_sharing / threshold 2 | 464 ± 58.8 | 1.10 ± 0.0142 | -15.9 ± 2.02 | 36.4 ± 4.61 | 0.339 ± 0.0342 | 25.7 ± 0.679 | 2.27 ± 0.415 |
| none / threshold 5 | 0 | 0 | 0 | 0 | 0.800 | 0 | 0 |
| fixed / threshold 5 | 2,012 ± 72.9 | 0.295 ± 0.0203 | 69.6 ± 2.48 | 65.3 ± 2.40 | 0.755 ± 0.0203 | 26.2 ± 1.46 | 15.0 ± 1.07 |
| mid_market / threshold 5 | 1,783 ± 91.4 | 0.358 ± 0.0222 | 74.8 ± 3.77 | 49.2 ± 2.57 | 0.689 ± 0.0275 | 31.2 ± 2.11 | 16.8 ± 1.25 |
| sdr / threshold 5 | 1,034 ± 100 | 0.487 ± 0.0147 | 8.95 ± 0.916 | 51.5 ± 5.03 | 0.463 ± 0.0332 | 37.5 ± 1.73 | 18.8 ± 2.43 |
| dynamic / threshold 5 | 1,976 ± 73.2 | 0.318 ± 0.0178 | 62.4 ± 2.51 | 68.2 ± 2.63 | 0.734 ± 0.0189 | 28.0 ± 1.88 | 16.8 ± 1.67 |
| bill_sharing / threshold 5 | 480 ± 68.1 | 1.11 ± 0.0182 | -16.5 ± 2.34 | 37.6 ± 5.34 | 0.301 ± 0.0317 | 27.2 ± 0.954 | 3.50 ± 0.939 |

## E2. Storage: none / individual / shared, same total capacity (mid-market)

| scenario | savings € | self-sufficiency | self-consumption | peak import kW | paid for battery energy € | battery losses kWh | served in outages | Gini | prosumer € | consumer € |
|---|---|---|---|---|---|---|---|---|---|---|
| none | 2,471 ± 37.7 | 0.350 ± 0.00255 | 0.626 ± 0.0123 | 26.8 ± 0.378 | 0 | 0 | 0.315 ± 0.0721 | 0.201 ± 0.00646 | 104 ± 1.54 | 68.2 ± 1.08 |
| individual 50 kWh | 3,187 ± 39.1 | 0.409 ± 0.00453 | 0.755 ± 0.0121 | 26.3 ± 0.410 | 0 | 1,573 ± 11.8 | 0.375 ± 0.0544 | 0.425 ± 0.00523 | 201 ± 1.88 | 43.0 ± 1.01 |
| shared 50 kWh | 3,941 ± 48.5 | 0.464 ± 0.00539 | 0.852 ± 0.0128 | 26.8 ± 0.378 | 1,410 ± 22.5 | 1,416 ± 22.6 | 0.446 ± 0.0897 | 0.227 ± 0.00407 | 183 ± 2.11 | 96.9 ± 1.40 |
| individual 100 kWh | 3,605 ± 42.6 | 0.442 ± 0.00507 | 0.823 ± 0.0135 | 26.0 ± 0.420 | 0 | 2,132 ± 24.1 | 0.418 ± 0.0398 | 0.464 ± 0.00609 | 243 ± 2.29 | 38.5 ± 1.20 |
| shared 100 kWh | 4,803 ± 103 | 0.531 ± 0.0106 | 0.983 ± 0.00602 | 26.7 ± 0.377 | 2,235 ± 83.6 | 2,244 ± 84.0 | 0.495 ± 0.0959 | 0.246 ± 0.00392 | 232 ± 5.48 | 112 ± 2.24 |
| individual 200 kWh | 3,692 ± 45.7 | 0.448 ± 0.00533 | 0.836 ± 0.0136 | 25.5 ± 0.476 | 0 | 2,262 ± 27.8 | 0.421 ± 0.0372 | 0.474 ± 0.00600 | 252 ± 2.65 | 37.0 ± 1.18 |
| shared 200 kWh | 4,929 ± 141 | 0.541 ± 0.0135 | 1.000 ± 0.000133 | 26.7 ± 0.377 | 2,353 ± 119 | 2,360 ± 120 | 0.500 ± 0.0955 | 0.248 ± 0.00392 | 239 ± 7.60 | 114 ± 2.89 |

## E2b. Pricing mechanism with a 100 kWh shared battery (all members)

| scenario | savings € | Gini | prosumer € | consumer € | paid for battery energy € | battery losses kWh |
|---|---|---|---|---|---|---|
| fixed / shared 100 kWh | 4,803 ± 103 | 0.177 ± 0.00449 | 203 ± 4.96 | 131 ± 2.62 | 2,022 ± 75.6 | 2,244 ± 84.0 |
| mid_market / shared 100 kWh | 4,803 ± 103 | 0.246 ± 0.00392 | 232 ± 5.48 | 112 ± 2.24 | 2,235 ± 83.6 | 2,244 ± 84.0 |
| sdr / shared 100 kWh | 4,803 ± 103 | 0.269 ± 0.00506 | 75.9 ± 2.87 | 216 ± 4.36 | 1,154 ± 41.8 | 2,244 ± 84.0 |
| dynamic / shared 100 kWh | 4,803 ± 103 | 0.130 ± 0.00567 | 173 ± 3.05 | 152 ± 3.77 | 1,777 ± 58.3 | 2,244 ± 84.0 |
| bill_sharing / shared 100 kWh | 4,803 ± 103 | 0.704 ± 0.00872 | -75.1 ± 2.65 | 317 ± 6.28 | 0 | 2,244 ± 84.0 |

## E3. Demand response x pricing (all members)

| scenario | savings € | self-sufficiency | peak import kW | Gini | prosumer € | consumer € |
|---|---|---|---|---|---|---|
| mid_market / flex 0.0 | 2,471 ± 37.7 | 0.350 ± 0.00255 | 26.8 ± 0.378 | 0.201 ± 0.00646 | 104 ± 1.54 | 68.2 ± 1.08 |
| mid_market / flex 0.1 | 3,192 ± 42.3 | 0.403 ± 0.00295 | 25.2 ± 0.402 | 0.227 ± 0.00415 | 148 ± 1.73 | 78.8 ± 1.23 |
| mid_market / flex 0.2 | 3,689 ± 48.4 | 0.440 ± 0.00417 | 31.8 ± 0.574 | 0.251 ± 0.00409 | 180 ± 1.98 | 85.2 ± 1.45 |
| sdr / flex 0.0 | 2,471 ± 37.7 | 0.350 ± 0.00255 | 26.8 ± 0.378 | 0.433 ± 0.00326 | 6.91 ± 0.292 | 133 ± 2.07 |
| sdr / flex 0.1 | 3,207 ± 42.3 | 0.404 ± 0.00296 | 25.3 ± 0.416 | 0.320 ± 0.00442 | 37.5 ± 0.729 | 153 ± 2.36 |
| sdr / flex 0.2 | 3,734 ± 49.4 | 0.443 ± 0.00435 | 35.1 ± 0.784 | 0.250 ± 0.00645 | 64.5 ± 1.31 | 164 ± 3.01 |
| dynamic / flex 0.0 | 2,471 ± 37.7 | 0.350 ± 0.00255 | 26.8 ± 0.378 | 0.169 ± 0.00710 | 75.9 ± 1.59 | 86.7 ± 1.57 |
| dynamic / flex 0.1 | 3,222 ± 42.4 | 0.405 ± 0.00296 | 25.3 ± 0.431 | 0.168 ± 0.00798 | 127 ± 2.22 | 94.5 ± 1.87 |
| dynamic / flex 0.2 | 3,724 ± 50.0 | 0.443 ± 0.00447 | 32.8 ± 0.698 | 0.214 ± 0.00839 | 168 ± 2.18 | 95.0 ± 2.42 |

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

| scenario | savings € | self-sufficiency | peak import kW | Gini | prosumer € | consumer € | paid for battery energy € |
|---|---|---|---|---|---|---|---|
| baseline | 4,803 ± 103 | 0.531 ± 0.0106 | 26.7 ± 0.377 | 0.246 ± 0.00392 | 232 ± 5.48 | 112 ± 2.24 | 2,235 ± 83.6 |
| cooperation 0.5 | 2,568 ± 74.7 | 0.359 ± 0.00728 | 26.8 ± 0.378 | 0.199 ± 0.00469 | 111 ± 3.63 | 68.4 ± 1.76 | 548 ± 44.6 |
| cooperation 0.75 | 3,758 ± 108 | 0.450 ± 0.0104 | 26.8 ± 0.378 | 0.225 ± 0.00412 | 174 ± 5.74 | 92.4 ± 2.25 | 1,379 ± 84.7 |
| efficiency 0.8 | 4,457 ± 98.4 | 0.514 ± 0.0104 | 26.7 ± 0.377 | 0.230 ± 0.00393 | 209 ± 5.06 | 108 ± 2.23 | 2,025 ± 83.0 |
| efficiency 0.95 | 4,969 ± 105 | 0.539 ± 0.0107 | 26.7 ± 0.379 | 0.253 ± 0.00392 | 243 ± 5.63 | 114 ± 2.24 | 2,334 ± 83.5 |
| export price 0.03 | 5,659 ± 122 | 0.531 ± 0.0106 | 26.7 ± 0.377 | 0.250 ± 0.00387 | 276 ± 6.57 | 130 ± 2.60 | 2,033 ± 76.0 |
| export price 0.08 | 3,520 ± 74.1 | 0.531 ± 0.0106 | 26.7 ± 0.377 | 0.236 ± 0.00405 | 167 ± 3.83 | 83.9 ± 1.69 | 2,538 ± 94.9 |
| battery income unallocated | 4,803 ± 103 | 0.531 ± 0.0106 | 26.7 ± 0.377 | 0.266 ± 0.00400 | 253 ± 6.24 | 112 ± 2.24 | 2,235 ± 83.6 |
| bi-hourly tariff | 5,577 ± 94.9 | 0.531 ± 0.0106 | 26.7 ± 0.377 | 0.237 ± 0.00379 | 265 ± 4.71 | 133 ± 2.31 | 2,281 ± 73.4 |
| flexibility 0.1 | 4,878 ± 107 | 0.536 ± 0.0110 | 25.4 ± 0.581 | 0.254 ± 0.00371 | 239 ± 5.49 | 111 ± 2.42 | 1,968 ± 97.7 |
| bi-hourly tariff + flexibility 0.1 | 5,972 ± 82.2 | 0.526 ± 0.00984 | 26.2 ± 0.454 | 0.202 ± 0.00399 | 267 ± 3.69 | 154 ± 2.36 | 2,065 ± 68.2 |
