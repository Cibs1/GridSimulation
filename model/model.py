"""Community model (ODD sections 3, 5, 7 and 8).

Per-step order (ODD section 3):
    1. environment update (hour, grid availability)
    3. demand response (daily, at local hour 0)
    4. self-consumption: own PV, then home battery
    5. local market and pricing
    6. community battery
    7. grid exchange and settlement
Process 2 (membership change, submodel 7.6) is not implemented yet.
"""

from functools import lru_cache
from pathlib import Path

import mesa
import numpy as np
import pandas as pd

from .agents import Household
from .battery import Battery

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
HOURS_PER_YEAR = 8760
PRICING_MECHANISMS = ("none", "fixed", "mid_market", "sdr", "bill_sharing")
STORAGE_MODES = ("none", "shared", "individual")


@lru_cache(maxsize=1)
def load_inputs():
    """Hourly PV yield per kWp, BTN C load shape and local hour of day (read once per process)."""
    pv = pd.read_csv(DATA_DIR / "pv_porto.csv")
    load = pd.read_csv(DATA_DIR / "load_btn_c.csv")
    if not (pv["time_utc"] == load["time_utc"]).all():
        raise ValueError("PV and load files are not aligned")
    local_hour = pd.to_datetime(pv["time_utc"], utc=True).dt.tz_convert("Europe/Lisbon").dt.hour
    return pv["pv_kwh_per_kwp"].to_numpy(), load["load_per_annual_kwh"].to_numpy(), local_hour.to_numpy()


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

    Prices are placeholders until the ERSE tariff values are decided.
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
        pricing="mid_market",
        fixed_price=0.10,  # EUR/kWh, used by pricing="fixed"
        import_price=0.20,  # EUR/kWh, placeholder
        export_price=0.05,  # EUR/kWh, placeholder
        storage_mode="none",
        storage_kwh=0.0,  # total capacity: one shared battery, or split over prosumers
        battery_c_rate=0.5,
        battery_efficiency=0.9,  # round trip
        outage_rate=4.0,  # outages per year
        outage_duration=(1, 8),  # hours, inclusive
        check_balance=True,
        rng=None,
    ):
        super().__init__(rng=rng)
        if pricing not in PRICING_MECHANISMS:
            raise ValueError(f"pricing must be one of {PRICING_MECHANISMS}")
        if storage_mode not in STORAGE_MODES:
            raise ValueError(f"storage_mode must be one of {STORAGE_MODES}")

        self.pv_yield, self.load_shape, self.local_hour = load_inputs()
        self.day_starts = np.flatnonzero(self.local_hour == 0)

        self.pricing = pricing
        self.fixed_price = fixed_price
        self.import_price = import_price
        self.export_price = export_price
        self.flexibility = flexibility
        self.check_balance = check_balance

        # Separate stream for outages, drawn first, so changing the outage
        # parameters does not change the household population (common random numbers).
        outage_rng = np.random.default_rng(self.rng.integers(2**63))
        self.grid_available = outage_schedule(outage_rng, outage_rate, outage_duration)

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
            )

        # Storage: one community battery, or the same total kWh split over
        # prosumers in proportion to their PV size (a home battery can only
        # charge from its own PV, so it would be idle in a consumer's home).
        self.battery = None
        battery_kw = dict(c_rate=battery_c_rate, round_trip_efficiency=battery_efficiency)
        if storage_mode == "shared" and storage_kwh > 0:
            self.battery = Battery(storage_kwh, **battery_kw)
        elif storage_mode == "individual" and storage_kwh > 0:
            prosumers = [h for h in self.households if h.is_prosumer]
            total_kwp = sum(h.pv_kwp for h in prosumers)
            for h in prosumers:
                h.battery = Battery(storage_kwh * h.pv_kwp / total_kwp, **battery_kw)

        self.hour = 0
        self.local_price = np.nan
        self.battery_cash_eur = 0.0  # net income of the community battery (counts as community savings)
        self.supply = self.bids = self.traded = 0.0
        self.bat_charge = self.bat_discharge = 0.0
        self.flows = dict.fromkeys(
            ["pv", "demand", "self_use", "shared", "battery_charge", "battery_discharge",
             "imported", "exported", "lost_load", "curtailment"], 0.0
        )

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "hour_of_day": lambda m: int(m.local_hour[m.hour]),
                "grid_available": lambda m: bool(m.grid_available[m.hour]),
                "local_price": "local_price",
                **{k: (lambda m, k=k: m.flows[k]) for k in self.flows},
                "net_load": lambda m: m.flows["imported"] - m.flows["exported"],
                "storage_soc": lambda m: m.storage_soc(),
            }
        )

    @property
    def households(self):
        return self.agents_by_type[Household]

    @property
    def members(self):
        return [h for h in self.households if h.is_member]

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

        # 3. Demand response, planned once per day at local midnight
        if self.flexibility > 0 and self.local_hour[self.hour] == 0:
            self.plan_demand_response()

        # 4. Self-consumption (synchronous: all households before the market)
        self.households.shuffle_do("compute_position")

        # 5-6. Local market and community battery
        self.supply = self.bids = self.traded = self.bat_charge = self.bat_discharge = 0.0
        self.local_price = np.nan
        if self.pricing != "none":
            self.clear_local_market()
            self.operate_community_battery()

        # 7. Grid exchange and settlement
        self.households.do("exchange_with_grid", grid_up)
        self.settle()

        self.update_flows()
        self.datacollector.collect(self)
        if self.steps >= HOURS_PER_YEAR:
            self.running = False

    def plan_demand_response(self):
        """Persistence forecast: today's PV is assumed equal to yesterday's (ODD 4, Prediction)."""
        start = self.hour
        if start < 24:
            return  # no yesterday on day one
        nxt = np.searchsorted(self.day_starts, start, side="right")
        end = self.day_starts[nxt] if nxt < len(self.day_starts) else HOURS_PER_YEAR
        forecast = self.pv_yield[start - 24:end - 24]
        if forecast.sum() <= 0:
            return
        weights = forecast / forecast.sum()
        for h in self.households:
            if h.flexibility > 0:
                h.plan_demand_response(slice(start, end), weights)

    def market_price(self, supply, bids):
        """Local price for this step under the active mechanism (submodel 7.3).

        Fixed, mid-market and SDR use one price for both sides of every local
        trade. Bill-sharing has no per-kWh price; it is settled in settle().
        """
        p_imp, p_exp = self.import_price, self.export_price
        if self.pricing == "fixed":
            return self.fixed_price
        if self.pricing == "mid_market":
            return (p_imp + p_exp) / 2
        if self.pricing == "sdr":
            # Liu et al. (2017). Buyers pay this price on their local share and
            # p_imp on the rest, which equals their P_buy on the whole deficit.
            if bids <= 0 or supply >= bids:
                return p_exp
            sdr = supply / bids
            return p_imp * p_exp / ((p_imp - p_exp) * sdr + p_exp)
        return np.nan  # bill_sharing

    def clear_local_market(self):
        """Match offers and bids pro rata (submodel 7.3)."""
        members = self.members
        self.supply = sum(h.offer for h in members)
        self.bids = sum(h.deficit for h in members)
        self.traded = min(self.supply, self.bids)
        self.local_price = self.market_price(self.supply, self.bids)
        if self.traded <= 0:
            return
        for h in members:
            h.sold_local = h.offer * self.traded / self.supply
            h.bought_local = h.deficit * self.traded / self.bids

    def operate_community_battery(self):
        """Leftover offers charge the shared battery; leftover bids are served from it (process 6)."""
        if self.battery is None:
            return
        members = self.members
        left_supply = self.supply - self.traded
        left_bids = self.bids - self.traded
        self.bat_charge = self.battery.charge(left_supply)
        if self.bat_charge > 0:
            for h in members:
                h.sold_local += (h.offer - h.sold_local) * self.bat_charge / left_supply
        self.bat_discharge = self.battery.discharge(left_bids)
        if self.bat_discharge > 0:
            for h in members:
                h.bought_local += (h.deficit - h.bought_local) * self.bat_discharge / left_bids

    def settle(self):
        """Book this step's costs and revenues to each household (process 7)."""
        p_imp, p_exp = self.import_price, self.export_price

        if self.pricing == "bill_sharing":
            # The community nets its members' grid exchange; the import bill is
            # split by each member's deficit and the export income by each
            # member's offer (Long et al. 2017). Non-members trade alone.
            members = self.members
            pool_cost = p_imp * sum(h.imported for h in members)
            pool_income = p_exp * sum(h.exported for h in members if h.offer > 0)
            if self.bids > 0:
                self.local_price = pool_cost / self.bids  # effective price per kWh of deficit, for reporting
            for h in self.households:
                if h.is_member:
                    cost = pool_cost * h.deficit / self.bids if self.bids > 0 else 0.0
                    income = pool_income * h.offer / self.supply if self.supply > 0 else 0.0
                    if h.offer == 0:
                        income += h.exported * p_exp  # surplus not offered is exported on its own
                else:
                    cost, income = h.imported * p_imp, h.exported * p_exp
                h.book(cost, income)
            return

        p_local = 0.0 if np.isnan(self.local_price) else self.local_price
        for h in self.households:
            h.book(h.imported * p_imp + h.bought_local * p_local,
                   h.exported * p_exp + h.sold_local * p_local)
        # The battery buys its charge from sellers and sells its discharge to buyers at the local price
        self.battery_cash_eur += (self.bat_discharge - self.bat_charge) * p_local

    def update_flows(self):
        f = self.flows
        hh = list(self.households)
        f["pv"] = sum(h.pv for h in hh)
        f["demand"] = sum(h.demand for h in hh)
        f["self_use"] = sum(h.self_use for h in hh)
        f["shared"] = self.traded
        f["battery_charge"] = sum(h.home_charge for h in hh) + self.bat_charge
        f["battery_discharge"] = sum(h.home_discharge for h in hh) + self.bat_discharge
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
        return {
            # savings = reference grid bill - actual grid bill; battery income stays in the community
            "community_savings_eur": savings.sum() + self.battery_cash_eur,
            "self_sufficiency": (demand - df["imported"].sum() - df["lost_load"].sum()) / demand,
            "self_consumption": (pv - df["exported"].sum() - df["curtailment"].sum()) / pv if pv > 0 else np.nan,
            "peak_import_kw": df["imported"].max(),  # kWh in a 1 h step = mean kW
            "gini_savings": gini(savings),
            "prosumer_consumer_savings_ratio": np.mean(pros) / np.mean(cons) if pros and cons and np.mean(cons) else np.nan,
            "outage_hours": int(outage.sum()),
            "served_during_outages": 1 - df.loc[outage, "lost_load"].sum() / outage_demand if outage_demand else np.nan,
            "lost_load_kwh": df["lost_load"].sum(),
            "lost_load_alone_kwh": sum(h.lost_load_alone_kwh for h in hh),
            "curtailment_kwh": df["curtailment"].sum(),
            "battery_cash_eur": self.battery_cash_eur,
        }

    def household_table(self):
        """One row per household with its attributes and annual results."""
        return pd.DataFrame([
            {
                "id": h.unique_id, "pv_kwp": h.pv_kwp, "annual_kwh": h.annual_kwh,
                "battery_kwh": h.battery.capacity_kwh if h.battery else 0.0,
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
