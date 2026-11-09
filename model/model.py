"""Community model (ODD sections 3, 5, 7 and 8).

Per-step order (ODD section 3):
    1. environment update (hour, grid availability, daily price forecast)
    2. membership review (every `review_days` days, at local hour 0)
    3. demand response (daily, at local hour 0)
    4. self-consumption: own PV, then home battery
    5. local market and pricing        (CommunityManager)
    6. community battery               (CommunityManager)
    7. grid exchange and settlement    (households, then CommunityManager)
"""

from functools import lru_cache
from pathlib import Path

import mesa
import numpy as np
import pandas as pd

from .agents import Household
from .battery import Battery
from .manager import CommunityManager

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
HOURS_PER_YEAR = 8760
PRICING_MECHANISMS = ("none", "fixed", "mid_market", "sdr", "dynamic", "bill_sharing")
STORAGE_MODES = ("none", "shared", "individual")
TARIFFS = ("simple", "bi_hourly")
BATTERY_INCOME_RULES = ("prosumers", "unallocated")


@lru_cache(maxsize=1)
def load_inputs():
    """BTN C load shape, local hour of day and the weather years (read once per process).

    Returns (load_shape, local_hour, weather), where weather maps each year to
    a pair of hourly arrays (pv_kwh_per_kwp, temp_c) on the 2023 timeline.
    """
    pv = pd.read_csv(DATA_DIR / "pv_porto.csv")
    load = pd.read_csv(DATA_DIR / "load_btn_c.csv")
    if not (pv["time_utc"] == load["time_utc"]).all():
        raise ValueError("PV and load files are not aligned")
    local_hour = pd.to_datetime(pv["time_utc"], utc=True).dt.tz_convert("Europe/Lisbon").dt.hour
    w = pd.read_csv(DATA_DIR / "weather_porto.csv")
    weather = {
        int(year): (g["pv_kwh_per_kwp"].to_numpy(), g["temp_c"].to_numpy())
        for year, g in w.sort_values(["year", "hour"]).groupby("year")
    }
    return load["load_per_annual_kwh"].to_numpy(), local_hour.to_numpy(), weather


def temperature_factor(temp_c, all_temps, day_index, heat_base, cool_base, heat_sens, cool_sens):
    """Hourly demand multiplier from how much colder or hotter each day is than usual (submodel 7.1).

    The BTN C profile already contains the average seasonal effect of
    temperature, so only the deviation from the average climate is applied:
    heating and cooling degree-days of this year minus those of the average
    over all weather years, for the same day. A colder-than-usual winter day
    raises demand, a mild one lowers it; a typical day leaves it unchanged.
    """
    def degree_days(t):  # daily mean temperature -> (heating, cooling) degree-days
        daily = np.bincount(day_index, weights=t) / np.bincount(day_index)
        return np.clip(heat_base - daily, 0, None), np.clip(daily - cool_base, 0, None)

    hdd, cdd = degree_days(temp_c)
    clim = [degree_days(t) for t in all_temps]
    hdd_clim = np.mean([h for h, _ in clim], axis=0)
    cdd_clim = np.mean([c for _, c in clim], axis=0)
    daily = 1 + heat_sens * (hdd - hdd_clim) + cool_sens * (cdd - cdd_clim)
    return np.clip(daily, 0, None)[day_index]


def outage_schedule(rng, rate_per_year, duration_range):
    """Grid availability per hour: outages start as a Poisson process and last a random whole number of hours (7.5)."""
    available = np.ones(HOURS_PER_YEAR, dtype=bool)
    if rate_per_year <= 0:
        return available
    t = 0.0
    while True:
        t += rng.exponential(HOURS_PER_YEAR / rate_per_year)
        start = int(t)
        if start >= HOURS_PER_YEAR:
            return available
        duration = int(rng.integers(duration_range[0], duration_range[1] + 1))
        available[start:start + duration] = False
        t = start + duration


class Community(mesa.Model):
    """A residential energy community behind one grid connection.

    The model holds the environment (weather, load shapes, grid tariffs and
    availability) and the agents: the households and one CommunityManager
    that runs the local market, the community battery and billing.

    Grid import prices are the ERSE regulated tariffs for low-voltage households
    (simple, or bi-hourly with the daily-cycle off-peak 22:00-08:00); the export
    price is a typical fixed-price buy-back offer.
    """

    def __init__(
        self,
        n_households=30,
        pv_share=0.4,
        pv_kwp_range=(2.0, 5.0),
        annual_kwh_range=(2500.0, 5000.0),
        noise_sd_range=(0.10, 0.20),
        max_shift_h=1,
        cooperation=1.0,
        flexibility=0.0,
        dr_threshold_range=(0.0, 0.03),  # EUR/kWh, minimum expected saving to shift load
        price_memory=0.3,  # weight of the latest day in the price forecast (exponential smoothing)
        membership=False,  # membership change (7.6)
        initial_member_share=1.0,
        review_days=30,
        savings_threshold=0.0,  # EUR over the review window; members below it may leave
        p_leave=0.5,
        p_join=0.2,
        pricing="mid_market",
        fixed_price=0.10,  # EUR/kWh, used by pricing="fixed"
        tariff="simple",  # grid import tariff: "simple" (flat) or "bi_hourly" (time of use)
        import_price=0.1711,  # EUR/kWh, ERSE simple tariff
        import_price_peak=0.2045,  # EUR/kWh, ERSE bi-hourly, outside off-peak
        import_price_offpeak=0.1143,  # EUR/kWh, ERSE bi-hourly, off-peak (22:00-08:00)
        export_price=0.05,  # EUR/kWh, typical fixed buy-back offer for surplus
        storage_mode="none",
        storage_kwh=0.0,  # total capacity: one shared battery, or split over prosumers
        battery_c_rate=0.5,
        battery_efficiency=0.9,  # round trip
        battery_income="prosumers",  # who gets the community battery's income: "prosumers" or "unallocated"
        outage_rate=4.0,  # outages per year
        outage_duration=(1, 8),  # hours, inclusive
        weather_year=None,  # None: drawn per seed from the available years; or a year, e.g. 2023
        heat_sensitivity=0.02,  # extra demand per heating degree-day above the usual (0 = no temperature effect)
        cool_sensitivity=0.02,  # extra demand per cooling degree-day above the usual
        heat_base=15.0,  # deg C, daily mean below which homes heat
        cool_base=22.0,  # deg C, daily mean above which homes cool
        check_balance=True,
        rng=None,
    ):
        super().__init__(rng=rng)
        if pricing not in PRICING_MECHANISMS:
            raise ValueError(f"pricing must be one of {PRICING_MECHANISMS}")
        if storage_mode not in STORAGE_MODES:
            raise ValueError(f"storage_mode must be one of {STORAGE_MODES}")
        if tariff not in TARIFFS:
            raise ValueError(f"tariff must be one of {TARIFFS}")
        if battery_income not in BATTERY_INCOME_RULES:
            raise ValueError(f"battery_income must be one of {BATTERY_INCOME_RULES}")

        self.load_shape, self.local_hour, weather = load_inputs()
        self.day_starts = np.flatnonzero(self.local_hour == 0)
        day_index = np.cumsum(self.local_hour == 0) - 1  # local day of each hour (the year starts at local midnight)
        self.hour = 0

        self.pricing = pricing
        self.tariff = tariff
        # Grid import price for every hour of the year (EUR/kWh)
        if tariff == "bi_hourly":
            offpeak = (self.local_hour >= 22) | (self.local_hour < 8)
            self.import_prices = np.where(offpeak, import_price_offpeak, import_price_peak)
        else:
            self.import_prices = np.full(HOURS_PER_YEAR, import_price)
        self.export_price = export_price
        self.flexibility = flexibility
        self.membership = membership
        self.review_days = review_days
        self.savings_threshold = savings_threshold
        self.p_leave = p_leave
        self.p_join = p_join
        self.check_balance = check_balance

        # Separate stream for outages, drawn first, so changing the outage
        # parameters does not change the household population (common random numbers).
        outage_rng = np.random.default_rng(self.rng.integers(2**63))
        self.grid_available = outage_schedule(outage_rng, outage_rate, outage_duration)

        # Weather year (ODD 6): its own stream too, so every scenario with the same
        # seed gets the same year, whatever its other parameters.
        weather_rng = np.random.default_rng(self.rng.integers(2**63))
        years = sorted(weather)
        if weather_year is None:
            weather_year = int(weather_rng.choice(years))
        elif weather_year not in weather:
            raise ValueError(f"weather_year must be one of {years}")
        self.weather_year = weather_year
        self.pv_yield, self.temperature = weather[weather_year]
        self.demand_factor = temperature_factor(
            self.temperature, [t for _, t in weather.values()], day_index,
            heat_base, cool_base, heat_sensitivity, cool_sensitivity,
        )

        # Population: exactly round(n * pv_share) prosumers, chosen at random
        n_pv = round(n_households * pv_share)
        has_pv = [True] * n_pv + [False] * (n_households - n_pv)
        self.random.shuffle(has_pv)
        for pv in has_pv:
            Household(
                self,
                annual_kwh=self.random.uniform(*annual_kwh_range),
                pv_kwp=self.random.uniform(*pv_kwp_range) if pv else 0.0,
                noise_sd=self.random.uniform(*noise_sd_range),
                shift_h=self.random.randint(-max_shift_h, max_shift_h),
                cooperation=cooperation,
                flexibility=flexibility,
                dr_threshold=self.random.uniform(*dr_threshold_range),
            )

        n_out = round(n_households * (1 - initial_member_share))
        for h in self.random.sample(list(self.households), n_out):
            h.is_member = False

        # Storage: one community battery, or the same total kWh split over
        # prosumers in proportion to their PV size (a home battery can only
        # charge from its own PV, so it would be idle in a consumer's home).
        community_battery = None
        battery_kw = dict(c_rate=battery_c_rate, round_trip_efficiency=battery_efficiency)
        if storage_mode == "shared" and storage_kwh > 0:
            community_battery = Battery(storage_kwh, **battery_kw)
        elif storage_mode == "individual" and storage_kwh > 0:
            prosumers = [h for h in self.households if h.is_prosumer]
            total_kwp = sum(h.pv_kwp for h in prosumers)
            for h in prosumers:
                h.battery = Battery(storage_kwh * h.pv_kwp / total_kwp, **battery_kw)

        # Created after the households so their unique_ids do not depend on it
        self.manager = CommunityManager(self, fixed_price=fixed_price, battery=community_battery,
                                        price_memory=price_memory, battery_income=battery_income)

        self.settled_hour = -1  # last hour whose bills have been booked
        self.leaves = self.joins = 0
        self.flows = dict.fromkeys(
            ["pv", "demand", "self_use", "shared", "battery_charge", "battery_discharge",
             "imported", "exported", "lost_load", "curtailment"], 0.0
        )

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "hour_of_day": lambda m: int(m.local_hour[m.hour]),
                "temperature": lambda m: float(m.temperature[m.hour]),
                "grid_available": lambda m: bool(m.grid_available[m.hour]),
                "local_price": lambda m: m.manager.local_price,
                **{k: (lambda m, k=k: m.flows[k]) for k in self.flows},
                "net_load": lambda m: m.flows["imported"] - m.flows["exported"],
                "storage_soc": lambda m: m.storage_soc(),
                "effective_price": lambda m: m.manager.effective_price[m.hour],
                "n_members": lambda m: len(m.members),
            }
        )

    @property
    def households(self):
        return self.agents_by_type[Household]

    @property
    def members(self):
        return [h for h in self.households if h.is_member]

    @property
    def import_price(self):
        """Grid import price in the current hour (EUR/kWh)."""
        return self.import_prices[self.hour]

    @property
    def battery(self):
        """The community battery (held by the manager), or None."""
        return self.manager.battery

    def batteries(self):
        bats = [h.battery for h in self.households if h.battery is not None]
        return bats + ([self.battery] if self.battery is not None else [])

    def storage_soc(self):
        bats = self.batteries()
        capacity = sum(b.capacity_kwh for b in bats)
        return sum(b.stored_kwh for b in bats) / capacity if capacity else np.nan

    # ---- step ----------------------------------------------------------------

    def step(self):
        # 1. Environment update
        self.hour = self.steps - 1  # Mesa increments steps before calling step()
        grid_up = bool(self.grid_available[self.hour])

        if self.local_hour[self.hour] == 0 and self.hour > 0:
            day = np.searchsorted(self.day_starts, self.hour, side="right") - 1
            self.manager.update_price_forecast(self.day_starts[day - 1])
            # 2. Membership review
            if self.membership and self.pricing != "none" and day % self.review_days == 0:
                self.review_membership()
            # 3. Demand response, planned once per day
            if self.flexibility > 0:
                self.plan_demand_response()

        # 4. Self-consumption (synchronous: all households before the market)
        self.households.shuffle_do("compute_position")

        # 5-6. Local market and community battery, run by the manager
        self.manager.reset_step()
        if self.pricing != "none":
            self.manager.clear_market()
            self.manager.operate_battery()

        # 7. Grid exchange, then the manager settles every household's bill
        self.households.do("exchange_with_grid", grid_up)
        self.manager.settle()
        self.settled_hour = self.hour  # bills now include this hour

        self.update_flows()
        self.datacollector.collect(self)
        if self.steps >= HOURS_PER_YEAR:
            self.running = False

    def plan_demand_response(self):
        """Each flexible household plans today's load shift from forecast prices (submodel 7.4)."""
        start = self.hour
        nxt = np.searchsorted(self.day_starts, start, side="right")
        end = self.day_starts[nxt] if nxt < len(self.day_starts) else HOURS_PER_YEAR
        today = slice(start, end)
        price = self.manager.price_forecast[self.local_hour[today]]
        price = np.where(np.isnan(price), self.import_prices[today], price)
        pv_forecast = self.pv_yield[start - 24:end - 24]  # persistence: today's PV = yesterday's
        for h in self.households:
            if h.flexibility > 0:
                h.plan_demand_response(today, price, pv_forecast)

    def review_membership(self):
        """Members whose savings since the last review fall below the threshold may leave;
        non-members may join if members of their own type saved (submodel 7.6)."""
        hh = list(self.households)
        savings = {h: h.window_savings_eur for h in hh}
        members = [h for h in hh if h.is_member]

        def mean_member_savings(prosumer):
            same = [savings[h] for h in members if h.is_prosumer == prosumer]
            pool = same or [savings[h] for h in members]
            return np.mean(pool) if pool else -np.inf

        reference = {True: mean_member_savings(True), False: mean_member_savings(False)}
        self.random.shuffle(hh)
        for h in hh:  # decisions use the state before the review (synchronous)
            if h.is_member:
                if savings[h] < self.savings_threshold - 1e-6 and self.random.random() < self.p_leave:
                    h.is_member = False
                    self.leaves += 1
            # same 1e-6 EUR tolerance as for leaving, so float noise around 0 EUR is not a "saving"
            elif reference[h.is_prosumer] > self.savings_threshold + 1e-6 and self.random.random() < self.p_join:
                h.is_member = True
                self.joins += 1
        for h in hh:
            h.mark_review()

    def update_flows(self):
        f = self.flows
        hh = list(self.households)
        f["pv"] = sum(h.pv for h in hh)
        f["demand"] = sum(h.demand for h in hh)
        f["self_use"] = sum(h.self_use for h in hh)
        f["shared"] = self.manager.traded
        f["battery_charge"] = sum(h.home_charge for h in hh) + self.manager.bat_charge
        f["battery_discharge"] = sum(h.home_discharge for h in hh) + self.manager.bat_discharge
        f["imported"] = sum(h.imported for h in hh)
        f["exported"] = sum(h.exported for h in hh)
        f["lost_load"] = sum(h.lost_load for h in hh)
        f["curtailment"] = sum(h.curtailed for h in hh)

        if self.check_balance:
            # PV + import + discharge + lost_load = demand + export + charge + curtailment
            residual = (f["pv"] + f["imported"] + f["battery_discharge"] + f["lost_load"]
                        - f["demand"] - f["exported"] - f["battery_charge"] - f["curtailment"])
            if abs(residual) > 1e-9 * max(1.0, f["demand"]):
                raise RuntimeError(f"Energy balance violated at hour {self.hour}: residual {residual:.3e} kWh")

    def run_year(self):
        while self.running:
            self.step()

    # ---- results ---------------------------------------------------------------

    def kpis(self):
        """Run-level KPIs (ODD section 8)."""
        df = self.datacollector.get_model_vars_dataframe()
        hh = list(self.households)
        savings = np.array([h.savings_eur for h in hh])
        pros = [h.savings_eur for h in hh if h.is_prosumer]
        cons = [h.savings_eur for h in hh if not h.is_prosumer]
        demand, pv = df["demand"].sum(), df["pv"].sum()
        outage = ~df["grid_available"].to_numpy(dtype=bool)
        outage_demand = df.loc[outage, "demand"].sum()
        community_savings = savings.sum() + self.manager.battery_cash_unallocated_eur
        bill_alone = sum(h.bill_alone_eur for h in hh)
        return {
            "weather_year": self.weather_year,
            # savings = reference grid bill - actual grid bill; battery income not paid out stays in the community
            "community_savings_eur": community_savings,
            # the same savings as a share of what the households would pay without a community
            "relative_savings": community_savings / bill_alone if bill_alone > 0 else np.nan,
            "self_sufficiency": (demand - df["imported"].sum() - df["lost_load"].sum()) / demand,
            "self_consumption": (pv - df["exported"].sum() - df["curtailment"].sum()) / pv if pv > 0 else np.nan,
            "peak_import_kw": df["imported"].max(),  # kWh in a 1 h step = mean kW
            "gini_savings": gini(savings),
            "prosumer_savings_eur": np.mean(pros) if pros else np.nan,  # mean per household
            "consumer_savings_eur": np.mean(cons) if cons else np.nan,
            "prosumer_consumer_savings_ratio": np.mean(pros) / np.mean(cons) if pros and cons and np.mean(cons) else np.nan,
            "outage_hours": int(outage.sum()),
            "served_during_outages": 1 - df.loc[outage, "lost_load"].sum() / outage_demand if outage_demand else np.nan,
            "lost_load_kwh": df["lost_load"].sum(),
            "lost_load_alone_kwh": sum(h.lost_load_alone_kwh for h in hh),
            # Value of the panels alone: bill with no PV minus bill alone with PV (no community, no battery)
            "no_pv_bill_eur": sum(h.bill_no_pv_eur for h in hh),
            "panel_savings_eur": sum(h.bill_no_pv_eur - h.bill_alone_eur for h in hh),
            "curtailment_kwh": df["curtailment"].sum(),
            "battery_revenue_eur": self.manager.battery_revenue_eur,  # paid for energy from the community battery
            "battery_cash_unallocated_eur": self.manager.battery_cash_unallocated_eur,
            "storage_losses_kwh": sum(b.losses_kwh for b in self.batteries()),
            "members_final": len(self.members),
            "prosumer_members_final": sum(h.is_member and h.is_prosumer for h in hh),
            "member_share_mean": df["n_members"].mean() / len(hh),
            "leaves": self.leaves,
            "joins": self.joins,
        }

    def household_table(self):
        """One row per household with its attributes and annual results."""
        return pd.DataFrame([
            {
                "id": h.unique_id, "pv_kwp": h.pv_kwp, "annual_kwh": h.annual_kwh,
                "battery_kwh": h.battery.capacity_kwh if h.battery else 0.0,
                "to_community_battery_kwh": h.battery_energy_kwh, "battery_income_eur": h.battery_income_eur,
                "imported_kwh": h.energy_imported_kwh, "exported_kwh": h.energy_exported_kwh,
                "shared_kwh": h.energy_shared_kwh, "lost_load_kwh": h.lost_load_kwh,
                "bill_eur": h.bill_eur, "bill_alone_eur": h.bill_alone_eur, "savings_eur": h.savings_eur,
            }
            for h in self.households
        ]).set_index("id")


def gini(x):
    """Gini coefficient of a 1-D array (0 = perfectly equal).

    Meant for non-negative values; with negative savings it can exceed 1.
    """
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0 or np.allclose(x, 0, atol=1e-9):
        return 0.0  # no savings at all (e.g. the no-community reference)
    n = len(x)
    return (2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum())
