"""Household agent (ODD section 2 and submodel 7.1)."""

import mesa
import numpy as np


class Household(mesa.Agent):
    """A consumer or prosumer behind the community's grid connection.

    The household's hourly demand for the whole year is built once at creation
    from the shared BTN C shape (ODD section 5): scaled to its annual demand,
    shifted by up to `max_shift_h` hours and multiplied by hourly noise.
    """

    def __init__(self, model, annual_kwh, pv_kwp, noise_sd, shift_h, cooperation=1.0):
        super().__init__(model)
        self.annual_kwh = annual_kwh
        self.pv_kwp = pv_kwp
        self.cooperation = cooperation
        self.is_member = True

        shape = np.roll(model.load_shape, shift_h)
        noisy = shape * np.clip(1 + model.rng.normal(0, noise_sd, len(shape)), 0, None)
        self.demand_profile = noisy * annual_kwh / noisy.sum()  # kWh per hour, sums to annual_kwh

        # This step's flows (kWh), set in compute_position and settle
        self.demand = self.pv = self.self_use = 0.0
        self.surplus = self.deficit = 0.0  # after self-consumption
        self.offer = 0.0  # part of the surplus offered to the community
        self.sold_local = self.bought_local = 0.0
        self.imported = self.exported = 0.0

        # Accumulators over the run
        self.cost_eur = self.revenue_eur = 0.0
        self.energy_imported_kwh = self.energy_exported_kwh = 0.0
        self.energy_shared_kwh = 0.0  # bought + sold locally
        self.bill_alone_eur = 0.0  # bill if the household traded only with the grid

    @property
    def is_prosumer(self):
        return self.pv_kwp > 0

    @property
    def bill_eur(self):
        return self.cost_eur - self.revenue_eur

    @property
    def savings_eur(self):
        return self.bill_alone_eur - self.bill_eur

    def compute_position(self):
        """Self-consumption and net position for this step (process 4)."""
        t = self.model.hour
        self.demand = self.demand_profile[t]
        self.pv = self.pv_kwp * self.model.pv_yield[t]
        self.self_use = min(self.pv, self.demand)
        self.surplus = self.pv - self.self_use
        self.deficit = self.demand - self.self_use

        cooperates = self.is_member and self.random.random() < self.cooperation
        self.offer = self.surplus if cooperates else 0.0
        self.sold_local = self.bought_local = 0.0

    def settle(self, p_import, p_export, p_local):
        """Grid exchange for what the local market left over, and booking (process 7)."""
        self.imported = self.deficit - self.bought_local
        self.exported = self.surplus - self.sold_local

        self.cost_eur += self.imported * p_import + self.bought_local * p_local
        self.revenue_eur += self.exported * p_export + self.sold_local * p_local
        self.bill_alone_eur += self.deficit * p_import - self.surplus * p_export

        self.energy_imported_kwh += self.imported
        self.energy_exported_kwh += self.exported
        self.energy_shared_kwh += self.sold_local + self.bought_local
