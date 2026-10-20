# Community Microgrid ABM — ODD Protocol (Draft v0.1)

Oct 6, 2026 · @Ricardo

## 1. Purpose and patterns

The model tests which local energy-sharing and pricing rules give a residential energy community the largest and fairest savings, and how well it copes with uncertainty and grid outages. It is a what-if tool comparing policies, not a forecast of one real community.

**Research questions**

1. **Pricing:** Which internal pricing mechanism (fixed price, mid-market price, supply–demand ratio price, bill-sharing) maximises total savings versus no community, and how fairly are the savings split?
2. **Storage:** Does one shared community battery beat the same total capacity spread across individual home batteries, in self-sufficiency and cost?
3. **Flexibility:** How much does demand response (shifting flexible load to solar hours) add on top of sharing?
4. **Resilience:** During a grid outage, what share of critical demand can the community cover, and how does that change with membership size and the PV/storage mix?

**Patterns the model must reproduce** (checked during validation)

- A daily "duck curve": community net load drops at midday and peaks in the evening.
- Clearly higher self-consumption in summer than in winter.
- Without storage, most PV surplus is exported around midday.
- Households without PV still benefit from cheaper local energy, but less than prosumers.

## 2. Entities, state variables and scales

The model has one agent type, the **Household**, plus three non-agent entities: the community **Battery**, the **Grid** and the **Community** (the Mesa model itself, which runs the local market).

| Entity | State variable | Unit | Type |
| --- | --- | --- | --- |
| Household | `demand_profile` (base load per step) | kWh | input, varies by household |
| Household | `pv_kwp` (installed solar, 0 = consumer only) | kWp | static |
| Household | `battery_kwh`, `battery_soc` (home battery, optional) | kWh, % | static / dynamic |
| Household | `flexibility` (share of daily load it can shift) | 0–1 | static |
| Household | `cooperation` (probability it offers surplus to the community instead of exporting) | 0–1 | static |
| Household | `is_member` (in the community or not) | bool | dynamic |
| Household | `cost_eur`, `revenue_eur`, `energy_imported_kwh`, `energy_shared_kwh` | €, kWh | dynamic, accumulated |
| Battery (community) | `capacity_kwh`, `soc`, `p_max_kw`, `efficiency` | kWh, %, kW, – | static / dynamic |
| Grid | `import_price`, `export_price` (by hour) | €/kWh | input |
| Grid | `available` (false during an outage) | bool | dynamic |
| Community | `pricing_mechanism`, `storage_mode` (none / individual / shared), `dr_enabled` | – | scenario parameter |
| Community | `local_price` (internal price this step) | €/kWh | dynamic |

**Scales**

- **Time step:** 1 hour. **Horizon:** 1 year (8,760 steps), so seasonal variation is captured. A shorter run (e.g. 4 typical weeks) can be used while testing.
- **Space:** not explicit. All households sit behind one connection point, and grid losses and line limits are ignored. The agents are not placed on a spatial grid.
- **Size:** 20–50 households (baseline 30).

## 3. Process overview and scheduling

Each hourly step runs the same seven processes in a fixed order. Households act in random order (`model.agents.shuffle_do`) wherever order matters.

1. **Update environment:** read this hour's PV yield, base demand and grid prices, and update grid availability using the outage process.
2. **Membership (daily, at hour 0 only):** households may join or leave depending on their savings so far (scenario-dependent; off in the baseline).
3. **Demand response:** if enabled, flexible households move part of their shiftable load into hours with expected surplus.
4. **Self-consumption:** each household covers its own demand from its PV, then from its home battery, and computes its net position: surplus (+) or deficit (−).
5. **Local market:** the Community collects offers (surplus from cooperating members) and bids (deficits), matches them and sets `local_price` with the active pricing mechanism.
6. **Community storage:** leftover surplus charges the shared battery, and leftover deficit is discharged from it, within power and SoC limits.
7. **Grid exchange and settlement:** any remaining deficit is imported and any surplus exported (if the grid is available; otherwise unmet demand is logged as *lost load*). Costs and revenues are booked to each household.

State updates are **synchronous within a step**: all households compute their net position (step 4) before the market clears (step 5). The `DataCollector` records model- and agent-level variables at the end of every step.

## 4. Design concepts

Community-level self-sufficiency, savings and fairness *emerge* from household-level rules. None of them is imposed directly.

| Concept | In this model |
| --- | --- |
| Basic principles | Collective self-consumption and peer-to-peer energy sharing behind one grid connection; local prices sit between the grid export and import prices, so trading locally beats trading with the grid for both sides. |
| Emergence | Community self-sufficiency, peak grid import, total savings and how savings are distributed (fairness). |
| Adaptation | Households with demand response shift load toward expected surplus hours. In membership scenarios, a household leaves if its savings fall below a threshold. |
| Objectives | Each household minimises its energy bill. The community has no objective of its own; it only applies the market rule. |
| Learning | Not included in the baseline. Possible extension: households adjust `cooperation` based on past gains. |
| Prediction | Simple: flexible households assume tomorrow's PV looks like today's (persistence forecast). |
| Sensing | Households know their own state and the current `local_price`, but not other households' data. |
| Interaction | Indirect, through the local market and the shared battery (no direct agent-to-agent negotiation). |
| Stochasticity | Weather-driven PV variation, random noise on demand, random outage start and duration, random cooperation decisions, random activation order. Controlled by the model seed. |
| Collectives | The community itself; optionally sub-groups (prosumers versus consumers) for reporting. |
| Observation | Per step: energy flows (PV, demand, shared, stored, imported, exported), `local_price`, battery SoC, lost load. Per run: KPIs in section 8. |

## 5. Initialisation

The baseline starts on 1 January with 30 households, all members, and every battery at 50% state of charge. All values below are **starting assumptions** to calibrate later.

| Parameter | Baseline value | Varied in experiments |
| --- | --- | --- |
| Number of households | 30 | 20, 30, 50 |
| Share with PV | 40% | 20–80% |
| PV size per prosumer | 2–5 kWp (uniform) | – |
| Share with home battery | 0% | used in the "individual storage" scenario |
| Community battery | 0 kWh (off) | 0, 50, 100, 200 kWh |
| Annual demand per household | 2,500–5,000 kWh (uniform) | – |
| `flexibility` | 0 (off) | 0–0.2 |
| `cooperation` | 1.0 (all cooperate) | 0.5–1.0 |
| Battery efficiency (round trip) | 90% | – |

Household attributes are drawn from the seeded `model.random`, so a seed fully reproduces the initial population.

## 6. Input data

Three hourly time series drive the model. They are read from CSV files at start-up and are not changed by the model.

| Input | Planned source | Notes |
| --- | --- | --- |
| PV yield per kWp, hourly, for Porto | [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/en/) (EU JRC) hourly data | Scaled by each household's `pv_kwp`; a year with typical weather |
| Household load profiles, hourly | An open residential load dataset, or synthetic profiles (morning and evening peaks plus noise) | Scaled to each household's annual demand |
| Grid import and export prices | Portuguese regulated tariffs from [ERSE](https://www.erse.pt/), with optional time-of-use periods | Export price well below import price |
| Outage events | Generated inside the model (no external data) | See submodel 7.5 |

*Open question:* which load dataset to use. Synthetic profiles are fine for the first prototype.

## 7. Submodels

Each process in section 3 maps to one submodel below. The pricing rule is the main experimental factor.

### 7.1 Household net position

For household *i* at step *t*, with PV yield per kWp *y(t)* and demand *d\_i(t)*:

```latex
n_i(t) = pv_i \cdot y(t) - d_i(t)
```

If *n\_i* > 0 the household first charges its home battery (if any), then offers the rest. If *n\_i* < 0 it first discharges its home battery, then bids for the rest.

### 7.2 Battery (home and community)

```latex
SoC(t+1) = SoC(t) + \frac{\eta_c \, E_{ch}(t) - E_{dis}(t) / \eta_d}{C}
```

Here *C* is capacity (kWh), η\_c and η\_d are charge and discharge efficiencies, and *E\_ch*, *E\_dis* are limited by *p\_max* × 1 h and by SoC staying within \[0, 1\].

### 7.3 Local market and pricing mechanisms

Total supply *S* = sum of offers and total demand *D* = sum of bids. Traded volume = min(*S*, *D*), allocated pro rata. *p\_imp* and *p\_exp* are the grid import and export prices.

| Mechanism | Local price rule |
| --- | --- |
| No community (reference) | Every household trades only with the grid |
| Fixed price | One constant price between *p\_exp* and *p\_imp* |
| Mid-market rate | (*p\_imp* + *p\_exp*) / 2 when *S* = *D*; when unbalanced, the short side's excess goes to the grid |
| Supply–demand ratio (SDR) | Price falls as local supply grows relative to demand (formula below) |
| Bill-sharing | Community nets total import and export with the grid, then splits the bill in proportion to each member's net consumption |

SDR pricing (Liu et al., 2017), with SDR = *S* / *D*. For 0 ≤ SDR ≤ 1:

```latex
P_{sell} = \frac{p_{imp} \, p_{exp}}{(p_{imp} - p_{exp}) \, SDR + p_{exp}}, \qquad P_{buy} = P_{sell} \, SDR + p_{imp} \, (1 - SDR)
```

For SDR > 1, both prices equal *p\_exp*.

### 7.4 Demand response

A flexible household moves up to `flexibility` × its daily demand from evening hours (17:00–22:00) into the hours with the highest forecast PV of the same day. Total daily demand stays the same.

### 7.5 Grid outages

Outages start as a Poisson process with rate λ (baseline: 4 per year) and last a random 1–8 hours. During an outage, only local PV and batteries can serve demand. Demand not served is booked as *lost load* (kWh).

### 7.6 Membership change

In the membership scenario, each day a member compares its 30-day savings with a no-community baseline. If the gain is below a threshold (e.g. €0), it leaves with probability *p\_leave*. Non-members join with probability *p\_join* when average member savings are positive.

## 8. Experiments, KPIs and statistical analysis

Each scenario runs 30 times with different seeds via `mesa.batch_run`, and every KPI is reported as a mean with a 95% confidence interval. This covers the course requirement for quantitative analysis.

**KPIs (per run)**

| KPI | Definition | Answers |
| --- | --- | --- |
| Community savings | (bill without community − bill with community), €/year | RQ1–3 |
| Self-sufficiency | share of community demand met by local PV and storage, % | RQ2, RQ3 |
| Self-consumption | share of local PV used inside the community, % | RQ2 |
| Peak grid import | highest hourly import, kW | RQ2, RQ3 |
| Fairness | Gini coefficient of per-household savings (0 = equal), plus prosumer/consumer savings ratio | RQ1 |
| Resilience | share of demand served during outages, %; lost load, kWh | RQ4 |

**Experiment design**

1. **Pricing:** 5 mechanisms × PV share (20/40/60/80%).
2. **Storage:** none vs. individual vs. shared, same total kWh (50/100/200).
3. **Demand response:** `flexibility` 0 / 0.1 / 0.2, crossed with the best pricing rule.
4. **Resilience:** outage rate and duration × storage mode × community size.
5. **Sensitivity:** one-at-a-time variation of `cooperation`, battery efficiency and the export price.

**Statistics:** one-way ANOVA (or Kruskal–Wallis if normality fails) to compare scenarios, Tukey post-hoc tests for pairs, and a check that 30 replications give narrow enough intervals.

**Validation:** check the four patterns in section 1, and check energy balance every step (PV + import + discharge + lost load = demand + export + charge).

**Open decisions**

- [ ] Final 2–3 research questions to keep (four may be too many for the timeline)
- [ ] Load-profile dataset or synthetic profiles
- [ ] Exact tariff values and whether to use time-of-use pricing
- [ ] Include membership dynamics (7.6) or leave it as an extension

**References**

- Grimm, V. et al. (2020). The ODD protocol for describing agent-based and other simulation models: a second update. *JASSS* 23(2), 7.
- Liu, N. et al. (2017). Energy-sharing model with price-based demand response for microgrids of peer-to-peer prosumers. *IEEE Transactions on Power Systems* 32(5).

*Citations are approximate and should be checked before submission.*
