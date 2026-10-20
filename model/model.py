"""Community model (ODD sections 3, 5 and 7).

Minimal version (step 4 in CLAUDE.md): households, local sharing at a fixed
price, and grid exchange. Not yet included: community/home batteries, the
other pricing mechanisms, demand response, outages and membership change.
"""

from functools import lru_cache
from pathlib import Path

import mesa
import numpy as np
import pandas as pd

from .agents import Household

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
HOURS_PER_YEAR = 8760


@lru_cache(maxsize=1)
def load_inputs():
    """Hourly PV yield per kWp, BTN C load shape and local hour of day (read once per process)."""
    pv = pd.read_csv(DATA_DIR / "pv_porto.csv")
    load = pd.read_csv(DATA_DIR / "load_btn_c.csv")
    if not (pv["time_utc"] == load["time_utc"]).all():
        raise ValueError("PV and load files are not aligned")
    local_hour = pd.to_datetime(pv["time_utc"], utc=True).dt.tz_convert("Europe/Lisbon").dt.hour
    return pv["pv_kwh_per_kwp"].to_numpy(), load["load_per_annual_kwh"].to_numpy(), local_hour.to_numpy()


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
        community_enabled=True,
        import_price=0.20,  # EUR/kWh, placeholder
        export_price=0.05,  # EUR/kWh, placeholder
        local_price=None,  # EUR/kWh; default mid-point of import and export
        check_balance=True,
        rng=None,
    ):
        super().__init__(rng=rng)
        self.pv_yield, self.load_shape, self.local_hour = load_inputs()

        self.community_enabled = community_enabled
        self.import_price = import_price
        self.export_price = export_price
        self.fixed_local_price = (import_price + export_price) / 2 if local_price is None else local_price
        self.check_balance = check_balance

        # Exactly round(n * pv_share) prosumers, chosen at random
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
            )

        self.hour = 0
        self.local_price = 0.0
        self.flows = dict.fromkeys(
            ["pv", "demand", "self_use", "shared", "imported", "exported", "lost_load", "curtailment"], 0.0
        )

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "hour_of_day": lambda m: int(m.local_hour[m.hour]),
                "local_price": "local_price",
                **{k: (lambda m, k=k: m.flows[k]) for k in self.flows},
                "net_load": lambda m: m.flows["imported"] - m.flows["exported"],
            }
        )

    @property
    def households(self):
        return self.agents_by_type[Household]

    def step(self):
        self.hour = self.steps - 1  # Mesa increments steps before calling step()

        # 4. Self-consumption and net position (synchronous: all before the market)
        self.households.shuffle_do("compute_position")
        # 5. Local market
        self.clear_local_market()
        # 7. Grid exchange and settlement
        self.households.do("settle", self.import_price, self.export_price, self.local_price)

        self.update_flows()
        self.datacollector.collect(self)
        if self.steps >= HOURS_PER_YEAR:
            self.running = False

    def clear_local_market(self):
        """Match offers and bids pro rata at a fixed local price (submodel 7.3)."""
        members = self.households.select(lambda h: h.is_member)
        supply = sum(h.offer for h in members)
        demand = sum(h.deficit for h in members)
        traded = min(supply, demand) if self.community_enabled else 0.0
        self.local_price = self.fixed_local_price if traded > 0 else 0.0
        if traded == 0:
            return
        for h in members:
            h.sold_local = h.offer * traded / supply
            h.bought_local = h.deficit * traded / demand

    def update_flows(self):
        f = self.flows
        hh = self.households
        f["pv"] = sum(h.pv for h in hh)
        f["demand"] = sum(h.demand for h in hh)
        f["self_use"] = sum(h.self_use for h in hh)
        f["shared"] = sum(h.bought_local for h in hh)
        f["imported"] = sum(h.imported for h in hh)
        f["exported"] = sum(h.exported for h in hh)
        f["lost_load"] = 0.0  # no outages yet
        f["curtailment"] = 0.0  # export is always possible while the grid is up

        if self.check_balance:
            # PV + import + discharge + lost_load = demand + export + charge + curtailment (no batteries yet)
            residual = f["pv"] + f["imported"] + f["lost_load"] - f["demand"] - f["exported"] - f["curtailment"]
            if abs(residual) > 1e-9 * max(1.0, f["demand"]):
                raise RuntimeError(f"Energy balance violated at hour {self.hour}: residual {residual:.3e} kWh")

    def run_year(self):
        while self.running:
            self.step()

    def kpis(self):
        """Run-level KPIs (ODD section 8) from the collected data and household accumulators."""
        df = self.datacollector.get_model_vars_dataframe()
        hh = list(self.households)
        savings = np.array([h.savings_eur for h in hh])
        local_pv = df["self_use"].sum() + df["shared"].sum()  # PV used inside the community
        pros = [h.savings_eur for h in hh if h.is_prosumer]
        cons = [h.savings_eur for h in hh if not h.is_prosumer]
        return {
            "community_savings_eur": savings.sum(),
            "self_sufficiency": local_pv / df["demand"].sum(),
            "self_consumption": local_pv / df["pv"].sum() if df["pv"].sum() > 0 else np.nan,
            "peak_import_kw": df["imported"].max(),  # kWh in a 1 h step = mean kW
            "gini_savings": gini(savings),
            "prosumer_consumer_savings_ratio": np.mean(pros) / np.mean(cons) if pros and cons and np.mean(cons) else np.nan,
            "lost_load_kwh": df["lost_load"].sum(),
            "curtailment_kwh": df["curtailment"].sum(),
        }

    def household_table(self):
        """One row per household with its attributes and annual results."""
        return pd.DataFrame([
            {
                "id": h.unique_id, "pv_kwp": h.pv_kwp, "annual_kwh": h.annual_kwh,
                "imported_kwh": h.energy_imported_kwh, "exported_kwh": h.energy_exported_kwh,
                "shared_kwh": h.energy_shared_kwh, "bill_eur": h.bill_eur,
                "bill_alone_eur": h.bill_alone_eur, "savings_eur": h.savings_eur,
            }
            for h in self.households
        ]).set_index("id")


def gini(x):
    """Gini coefficient of a 1-D array (0 = perfectly equal). Defined for non-negative values."""
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return 0.0
    n = len(x)
    return (2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum())
