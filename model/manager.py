"""Community manager agent: local market operator, community battery and billing (processes 5-7, submodel 7.3)."""

import mesa
import numpy as np

HOURS_PER_YEAR = 8760


class CommunityManager(mesa.Agent):
    """The entity that runs the energy community on behalf of its members.

    Households do not trade with each other directly. Each hour the manager
    collects the members' offers (surplus) and bids (deficit), matches them
    pro rata, sets the local price under the active mechanism, operates the
    community battery with what is left, and books every household's costs
    and revenues once the grid exchange is known. It also publishes the
    price members paid per kWh and its smoothed forecast by hour of day,
    which flexible households use for demand response.
    """

    def __init__(self, model, fixed_price=0.10, battery=None, price_memory=0.3):
        super().__init__(model)
        self.fixed_price = fixed_price  # EUR/kWh, used by pricing="fixed"
        self.battery = battery  # community battery, or None
        self.price_memory = price_memory  # weight of the latest day in the price forecast

        # This step's market outcome (kWh, EUR/kWh)
        self.supply = self.bids = self.traded = 0.0
        self.bat_charge = self.bat_discharge = 0.0
        self.local_price = np.nan

        self.battery_cash_eur = 0.0  # net income of the community battery (counts as community savings)
        # Price a member pays per extra kWh in each hour (local share at the local
        # price, the rest at p_imp), and its smoothed forecast by local hour of day
        self.effective_price = np.full(HOURS_PER_YEAR, np.nan)
        self.price_forecast = np.full(24, np.nan)

    # ---- price forecast (ODD 4, Prediction) -----------------------------------

    def update_price_forecast(self, yesterday_start):
        """Exponentially smoothed effective price by local hour, updated with yesterday's prices."""
        m, a = self.model, self.price_memory
        for k in range(yesterday_start, m.hour):
            h, p = m.local_hour[k], self.effective_price[k]
            f = self.price_forecast[h]
            self.price_forecast[h] = p if np.isnan(f) else (1 - a) * f + a * p

    # ---- local market (process 5, submodel 7.3) -------------------------------

    def market_price(self, supply, bids):
        """Local price for this step under the active mechanism.

        Fixed, mid-market and SDR use one price for both sides of every local
        trade. Bill-sharing has no per-kWh price; it is settled in settle().
        """
        m = self.model
        p_imp, p_exp = m.import_price, m.export_price
        if m.pricing == "fixed":
            return self.fixed_price
        if m.pricing == "mid_market":
            return (p_imp + p_exp) / 2
        if m.pricing == "sdr":
            # Liu et al. (2017). Buyers pay this price on their local share and
            # p_imp on the rest, which equals their P_buy on the whole deficit.
            if bids <= 0 or supply >= bids:
                return p_exp
            sdr = supply / bids
            return p_imp * p_exp / ((p_imp - p_exp) * sdr + p_exp)
        if m.pricing == "dynamic":
            # Symmetric supply-demand price: p_exp with a large surplus, the
            # mid-point when supply equals demand, p_imp under scarcity.
            if supply + bids <= 0:
                return (p_imp + p_exp) / 2
            return p_exp + (p_imp - p_exp) * bids / (supply + bids)
        return np.nan  # bill_sharing

    def reset_step(self):
        self.supply = self.bids = self.traded = self.bat_charge = self.bat_discharge = 0.0
        self.local_price = np.nan

    def clear_market(self):
        """Match the members' offers and bids pro rata."""
        members = self.model.members
        self.supply = sum(h.offer for h in members)
        self.bids = sum(h.deficit for h in members)
        self.traded = min(self.supply, self.bids)
        self.local_price = self.market_price(self.supply, self.bids)
        if self.traded <= 0:
            return
        for h in members:
            h.sold_local = h.offer * self.traded / self.supply
            h.bought_local = h.deficit * self.traded / self.bids

    # ---- community battery (process 6) ----------------------------------------

    def operate_battery(self):
        """Leftover offers charge the shared battery; leftover bids are served from it."""
        if self.battery is None:
            return
        members = self.model.members
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

    # ---- settlement (process 7) -----------------------------------------------

    def settle(self):
        """Book this step's costs and revenues to each household."""
        m = self.model
        p_imp, p_exp = m.import_price, m.export_price

        if m.pricing == "bill_sharing":
            # The community nets its members' grid exchange; the import bill is
            # split by each member's deficit and the export income by each
            # member's offer (Long et al. 2017). Non-members trade alone.
            members = m.members
            pool_cost = p_imp * sum(h.imported for h in members)
            pool_income = p_exp * sum(h.exported for h in members if h.offer > 0)
            if self.bids > 0:
                self.local_price = pool_cost / self.bids  # effective price per kWh of deficit, for reporting
            for h in m.households:
                if h.is_member:
                    cost = pool_cost * h.deficit / self.bids if self.bids > 0 else 0.0
                    income = pool_income * h.offer / self.supply if self.supply > 0 else 0.0
                    if h.offer == 0:
                        income += h.exported * p_exp  # surplus not offered is exported on its own
                else:
                    cost, income = h.imported * p_imp, h.exported * p_exp
                h.book(cost, income)
        else:
            p_local = 0.0 if np.isnan(self.local_price) else self.local_price
            for h in m.households:
                h.book(h.imported * p_imp + h.bought_local * p_local,
                       h.exported * p_exp + h.sold_local * p_local)
            # The battery buys its charge from sellers and sells its discharge to buyers at the local price
            self.battery_cash_eur += (self.bat_discharge - self.bat_charge) * p_local

        self.effective_price[m.hour] = self.member_price()

    def member_price(self):
        """Average price a member paid per kWh of deficit this step: the share served
        locally (market + community battery) at the local price, the rest at p_imp.
        With no deficits, an extra kWh would come from the local surplus."""
        m = self.model
        if m.pricing == "none":
            return m.import_price
        if m.pricing == "bill_sharing":
            return self.local_price if self.bids > 0 else m.export_price
        if self.bids <= 0:
            return self.local_price if self.supply > 0 else m.import_price
        local_share = (self.traded + self.bat_discharge) / self.bids
        return local_share * self.local_price + (1 - local_share) * m.import_price
