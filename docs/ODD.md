# Community Microgrid ABM — ODD Protocol (Draft v0.3)

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

## 1. Purpose and patterns

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

## 2. Entities, state variables and scales

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

## 3. Process overview and scheduling

Each hourly step runs the same processes in a fixed order. Households act in random order (`model.agents.shuffle_do`) where order matters.

1. **Update environment:** read this hour's PV yield and demand, and grid availability from the outage schedule. At local midnight, update the price forecast with yesterday's effective prices.
2. **Membership (every 30 days, at local midnight):** households may leave or join depending on their recent savings (7.6). Off in the baseline.
3. **Demand response (daily, at local midnight):** flexible households plan today's load shift from the price forecast (7.4).
4. **Self-consumption:** each household covers its own demand from its PV, then charges or discharges its home battery (if any), and computes its net position: surplus or deficit (7.1).
5. **Local market:** the CommunityManager collects offers (surplus of cooperating members) and bids (deficits of members), matches them pro rata and sets `local_price` with the active pricing mechanism (7.3).
6. **Community storage:** the CommunityManager charges the shared battery with leftover offers and serves leftover bids from it, within power and SoC limits (7.2).
7. **Grid exchange and settlement:** any remaining deficit is imported and any remaining surplus exported if the grid is available; during an outage they become *lost load* and *curtailment* (7.5). The CommunityManager then books costs and revenues to each household.

State updates are **synchronous within a step**: all households compute their net position (step 4) before the market clears (step 5), and membership decisions use the state before the review. The `DataCollector` records community-level flows and prices at the end of every step; household results are read at the end of the run.

## 4. Design concepts

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

## 5. Initialisation

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

## 6. Input data

Two hourly time series drive the model. They are prepared once by scripts, saved as CSV (8,760 rows each, indexed by the start of the hour in UTC, with local time alongside), and read at start-up. The model never calls an external API.

| Input | Source | Processing |
| --- | --- | --- |
| PV yield per kWp, Porto | [PVGIS v5.3](https://re.jrc.ec.europa.eu/pvg_tools/en/) (EU JRC), PVGIS-SARAH3, lat 41.15, lon −8.61, year 2023, optimal angles (35°, azimuth 3°), 14% system losses | `scripts/get_pvgis.py`: hourly power of a 1 kWp system (W) → kWh per kWp. Annual yield 1,520 kWh/kWp. Scaled by each household's `pv_kwp`. |
| Household load shape | [E-REDES](https://www.e-redes.pt/pt-pt/perfis-de-consumo) / ERSE standard profile **BTN C** for 2023 (low-voltage residential, ≤13.8 kVA, ≤7,140 kWh/yr), 15-min, legal time | `scripts/prep_load.py`: quarter-hours summed to hours and normalised to sum to 1. Scaled by each household's annual demand, with noise and shift added in the model (section 5). |
| Grid import and export prices | Portuguese regulated tariffs ([ERSE](https://www.erse.pt/)) | Placeholders until decided (flat 0.20 / 0.05 €/kWh). |
| Outage events | Generated inside the model | See 7.5. |

## 7. Submodels

Each process in section 3 maps to one submodel below.

### 7.1 Household net position

For household *i* at step *t*, with PV yield per kWp *y(t)* and demand *d\_i(t)*:

```latex
n_i(t) = pv_i \cdot y(t) - d_i(t)
```

The household first uses its own PV (self-use = min(PV, demand)). If *n\_i* > 0 it charges its home battery (if any), and offers the rest to the community with probability `cooperation` (if it is a member; otherwise the rest is exported). If *n\_i* < 0 it discharges its home battery, then bids for the rest (members) or imports it.

### 7.2 Battery (home and community)

```latex
SoC(t+1) = SoC(t) + \frac{\eta_c \, E_{ch}(t) - E_{dis}(t) / \eta_d}{C}
```

Here *C* is capacity (kWh), η\_c = η\_d = √(round-trip efficiency), and *E\_ch*, *E\_dis* (measured on the AC side) are limited by *p\_max* × 1 h and by SoC staying within \[0, 1\]. The community battery charges only from members' offers left over after the market and discharges only to members' bids left over after the market; it does not charge from the grid and keeps no reserve for outages. It buys its charge from sellers and sells its discharge to buyers at the step's local price; its net income (`battery_cash_eur`) belongs to the community and counts towards community savings.

### 7.3 Local market and pricing mechanisms

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

### 7.4 Demand response

Once a day, at local midnight, each flexible household plans the day. It values each hour of the day at an expected price: for members, the community's smoothed effective-price forecast for that hour of day (section 4, Prediction); for non-members (or with no community), *p\_exp* in hours where it expects its own PV to exceed its demand (persistence forecast) and *p\_imp* otherwise. Let *p\_eve* be the demand-weighted expected price of the evening hours (17:00–22:00). The expected gain of moving load to hour *h* outside the evening is max(0, *p\_eve* − *p\_h*). If the largest gain is at least the household's `dr_threshold`, it moves min(`flexibility` × daily demand, evening demand) out of the evening, proportionally, and into the other hours in proportion to their gains. Total daily demand stays the same.

### 7.5 Grid outages

Outages start as a Poisson process with rate λ (baseline: 4 per year) and last a random whole number of hours (baseline 1–8, uniform); outages do not overlap. During an outage, only local PV and batteries can serve demand: deficits that cannot be served are booked as **lost load** (kWh) and surpluses that cannot be used or stored as **curtailment** (kWh). Neither is billed.

### 7.6 Membership change

Every 30 days (at local midnight), each household compares its savings over the last 30 days with the no-community reference (7.7). A **member** whose savings are below a threshold leaves with probability *p\_leave* (0.5). The threshold stands for the cost of taking part (fees, effort). A **non-member** joins with probability *p\_join* (0.2) if the average 30-day savings of current members of its own type (prosumer or consumer) exceed the threshold. Decisions use the state before the review. Non-members trade only with the grid; they keep any home battery and can still do demand response on their own (7.4). In membership scenarios 20% of households start outside the community.

### 7.7 No-community reference

Savings are measured against a reference computed per household at initialisation: the same household, weather and outages, using its own PV only, with no community, no battery and no demand response, at the same grid prices. Because the reference depends only on the seed, all scenarios with the same seed share it and their savings are directly comparable.

## 8. Experiments, KPIs and statistical analysis

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
