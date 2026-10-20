"""Battery entity, used for the community battery and for home batteries (submodel 7.2)."""

import math


class Battery:
    """Energy store with a power limit and symmetric charge/discharge efficiency.

    All energies passed in or returned are measured on the AC side (what the
    community bus gives or receives in one 1 h step). Losses show up only as a
    smaller change in stored energy:
        SoC(t+1) = SoC(t) + (eta_c * E_ch - E_dis / eta_d) / C
    """

    def __init__(self, capacity_kwh, c_rate=0.5, round_trip_efficiency=0.9, soc=0.5):
        self.capacity_kwh = capacity_kwh
        self.p_max_kw = c_rate * capacity_kwh
        self.eta = math.sqrt(round_trip_efficiency)  # eta_c = eta_d
        self.soc = soc  # 0-1

    @property
    def stored_kwh(self):
        return self.soc * self.capacity_kwh

    def charge(self, available_kwh):
        """Take up to `available_kwh` from the bus; return the energy actually taken."""
        if self.capacity_kwh <= 0 or available_kwh <= 0:
            return 0.0
        room = (1 - self.soc) * self.capacity_kwh / self.eta
        e = min(available_kwh, self.p_max_kw, room)
        self.soc = min(1.0, self.soc + self.eta * e / self.capacity_kwh)
        return e

    def discharge(self, needed_kwh):
        """Deliver up to `needed_kwh` to the bus; return the energy actually delivered."""
        if self.capacity_kwh <= 0 or needed_kwh <= 0:
            return 0.0
        e = min(needed_kwh, self.p_max_kw, self.stored_kwh * self.eta)
        self.soc = max(0.0, self.soc - e / self.eta / self.capacity_kwh)
        return e
