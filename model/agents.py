"""Household agent (ODD section 2 and submodels 7.1, 7.4)."""

import mesa
import numpy as np

from .battery import Battery


class Household(mesa.Agent):
    """A consumer or prosumer behind the community's grid connection.

    The household's hourly base demand for the whole year is built once at
    creation from the shared BTN C shape (ODD section 5): scaled to its annual
    demand, shifted by a few hours and multiplied by hourly noise. Demand
    response may move load within a day, so `demand_profile` (what is actually
    consumed) can differ from `base_demand` while daily totals stay the same.
    """

    def __init__(self, model, annual_kwh, pv_kwp, noise_sd, shift_h, cooperation=1.0, flexibility=0.0):
        super().__init__(model)
        self.annual_kwh = annual_kwh
        self.pv_kwp = pv_kwp
        self.cooperation = cooperation
        self.flexibility = flexibility
        self.is_member = True
        self.battery = None  # home battery, set by the model in the "individual" storage mode

        shape = np.roll(model.load_shape, shift_h)
        noisy = shape * np.clip(1 + model.rng.normal(0, noise_sd, len(shape)), 0, None)
        self.base_demand = noisy * annual_kwh / noisy.sum()  # kWh per hour, sums to annual_kwh
        self.demand_profile = self.base_demand.copy()

        self._init_reference(model)

        # This step's flows (kWh)
        self.demand = self.pv = self.self_use = 0.0
        self.home_charge = self.home_discharge = 0.0
        self.surplus = self.deficit = 0.0  # after self-consumption and home battery
        self.offer = 0.0  # part of the surplus offered to the community
        self.sold_local = self.bought_local = 0.0  # to/from other members and the community battery
        self.imported = self.exported = 0.0
        self.lost_load = self.curtailed = 0.0

        # Accumulators over the run
        self.cost_eur = self.revenue_eur = 0.0
        self.energy_imported_kwh = self.energy_exported_kwh = 0.0
        self.energy_shared_kwh = 0.0  # bought + sold locally
        self.lost_load_kwh = 0.0

    def _init_reference(self, model):
        """Hourly bill of the no-community reference, as a cumulative series.

        Reference = same household, same weather and outages, PV only: no
        community, no battery, no demand response. Every scenario with the
        same seed shares this reference, so savings are comparable across them.
        """
        pv = self.pv_kwp * model.pv_yield
        deficit = np.clip(self.base_demand - pv, 0, None)
        surplus = np.clip(pv - self.base_demand, 0, None)
        up = model.grid_available
        bill = np.where(up, deficit * model.import_price - surplus * model.export_price, 0.0)
        self._bill_alone_cum = np.cumsum(bill)
        self._lost_load_alone_cum = np.cumsum(np.where(up, 0.0, deficit))

    @property
    def is_prosumer(self):
        return self.pv_kwp > 0

    @property
    def bill_eur(self):
        return self.cost_eur - self.revenue_eur

    @property
    def bill_alone_eur(self):
        return self._bill_alone_cum[self.model.hour] if self.model.steps else 0.0

    @property
    def lost_load_alone_kwh(self):
        return self._lost_load_alone_cum[self.model.hour] if self.model.steps else 0.0

    @property
    def savings_eur(self):
        return self.bill_alone_eur - self.bill_eur

    def plan_demand_response(self, today, weights):
        """Move up to `flexibility` x daily demand from 17:00-22:00 into forecast PV hours (submodel 7.4).

        `today` is the slice of steps in the current local day and `weights`
        the forecast PV share of each of those steps (sums to 1).
        """
        d = self.demand_profile[today]
        evening = (self.model.local_hour[today] >= 17) & (self.model.local_hour[today] < 22)
        evening_kwh = d[evening].sum()
        shift = min(self.flexibility * d.sum(), evening_kwh)
        if shift <= 0:
            return
        d[evening] *= 1 - shift / evening_kwh
        d += shift * weights  # writes through to demand_profile (d is a view)

    def compute_position(self):
        """Self-consumption, home battery and net position for this step (process 4)."""
        t = self.model.hour
        self.demand = self.demand_profile[t]
        self.pv = self.pv_kwp * self.model.pv_yield[t]
        self.self_use = min(self.pv, self.demand)
        self.surplus = self.pv - self.self_use
        self.deficit = self.demand - self.self_use

        self.home_charge = self.home_discharge = 0.0
        if self.battery is not None:
            self.home_charge = self.battery.charge(self.surplus)
            self.surplus -= self.home_charge
            self.home_discharge = self.battery.discharge(self.deficit)
            self.deficit -= self.home_discharge

        cooperates = self.is_member and self.random.random() < self.cooperation
        self.offer = self.surplus if cooperates else 0.0
        self.sold_local = self.bought_local = 0.0

    def exchange_with_grid(self, grid_available):
        """Import what is still missing and export what is still left (process 7)."""
        remaining_deficit = self.deficit - self.bought_local
        remaining_surplus = self.surplus - self.sold_local
        if grid_available:
            self.imported, self.exported = remaining_deficit, remaining_surplus
            self.lost_load = self.curtailed = 0.0
        else:
            self.imported = self.exported = 0.0
            self.lost_load, self.curtailed = remaining_deficit, remaining_surplus

    def book(self, cost, revenue):
        self.cost_eur += cost
        self.revenue_eur += revenue
        self.energy_imported_kwh += self.imported
        self.energy_exported_kwh += self.exported
        self.energy_shared_kwh += self.sold_local + self.bought_local
        self.lost_load_kwh += self.lost_load
