"""Model verification tests. Run from the repo root with: python -m pytest

The energy balance is checked inside the model at every step (check_balance),
so every test that runs the model also verifies it.
"""

import numpy as np
import pytest

from model.battery import Battery
from model.model import PRICING_MECHANISMS, Community


def run(**kwargs):
    model = Community(**{"rng": 1, **kwargs})
    model.run_year()
    return model


def grid_bill(model):
    df = model.datacollector.get_model_vars_dataframe()
    return model.import_price * df["imported"].sum() - model.export_price * df["exported"].sum()


@pytest.fixture(scope="module")
def reference():
    return run(pricing="none")


def test_no_community_has_zero_savings(reference):
    assert reference.kpis()["community_savings_eur"] == pytest.approx(0, abs=1e-6)


def test_reference_is_shared_across_scenarios(reference):
    """Same seed -> same households and same reference bill, whatever the scenario (common random numbers)."""
    other = Community(rng=1, pricing="sdr", storage_mode="shared", storage_kwh=100, flexibility=0.1)
    a, b = list(reference.households), list(other.households)
    assert [h.pv_kwp for h in a] == [h.pv_kwp for h in b]
    assert all(np.array_equal(x.base_demand, y.base_demand) for x, y in zip(a, b))
    assert np.array_equal(reference.grid_available, other.grid_available)
    assert reference.weather_year == other.weather_year


def test_same_seed_reproduces_results():
    assert run(rng=3).kpis() == run(rng=3).kpis()


@pytest.mark.parametrize("pricing", PRICING_MECHANISMS)
@pytest.mark.parametrize("storage_mode", ["none", "shared", "individual"])
def test_community_savings_equal_grid_bill_reduction(reference, pricing, storage_mode):
    """Local trades are transfers between members: total savings = reference grid bill - actual grid bill."""
    model = run(pricing=pricing, storage_mode=storage_mode, storage_kwh=60)
    expected = grid_bill(reference) - grid_bill(model)
    assert model.kpis()["community_savings_eur"] == pytest.approx(expected, rel=1e-9, abs=1e-6)


def test_pricing_redistributes_but_does_not_change_total():
    """Without storage or demand response, energy flows do not depend on the price rule."""
    totals = {p: run(pricing=p, outage_rate=0).kpis()["community_savings_eur"] for p in PRICING_MECHANISMS[1:]}
    assert max(totals.values()) == pytest.approx(min(totals.values()), rel=1e-9)


def test_storage_increases_self_sufficiency(reference):
    base = run().kpis()["self_sufficiency"]
    for mode in ["shared", "individual"]:
        assert run(storage_mode=mode, storage_kwh=100).kpis()["self_sufficiency"] > base


def test_community_savings_with_membership_and_dr(reference):
    model = run(pricing="dynamic", membership=True, initial_member_share=0.8, savings_threshold=2, flexibility=0.1)
    expected = grid_bill(reference) - grid_bill(model)
    assert model.kpis()["community_savings_eur"] == pytest.approx(expected, rel=1e-9, abs=1e-6)


def test_demand_response_keeps_daily_totals():
    model = run(flexibility=0.2)
    shifted = 0
    for h in model.households:
        assert h.demand_profile.sum() == pytest.approx(h.base_demand.sum())
        shifted += not np.allclose(h.demand_profile, h.base_demand)
    assert shifted >= 0.9 * len(model.households)


def test_price_responsive_dr_lowers_rebound_peak():
    """Spreading load over cheaper hours avoids everyone piling into the same hours.

    Checked on the 2023 weather: in other years a sunny day followed by a cloudy
    one can still create a midday rebound peak, because the forecast is wrong.
    """
    assert run(flexibility=0.2, weather_year=2023).kpis()["peak_import_kw"] < 38


def test_dynamic_price_bounds():
    m = Community(rng=1, pricing="dynamic")
    assert m.manager.market_price(100, 0) == pytest.approx(m.export_price)
    assert m.manager.market_price(10, 10) == pytest.approx((m.import_price + m.export_price) / 2)
    assert m.manager.market_price(0, 100) == pytest.approx(m.import_price)


def test_membership_off_keeps_everyone():
    k = run(pricing="bill_sharing").kpis()
    assert k["members_final"] == 30 and k["leaves"] == 0


def test_bill_sharing_drives_prosumers_out():
    k = run(pricing="bill_sharing", membership=True, savings_threshold=2).kpis()
    assert k["prosumer_members_final"] < 12 and k["leaves"] > 0


def test_non_members_do_not_trade():
    model = Community(rng=1, initial_member_share=0.5)
    for _ in range(24 * 7):
        model.step()
    for h in model.households:
        if not h.is_member:
            assert h.energy_shared_kwh == 0


def test_no_grid_exchange_during_outages():
    model = run(outage_rate=20)
    df = model.datacollector.get_model_vars_dataframe()
    down = ~df["grid_available"].astype(bool)
    assert down.sum() > 0
    assert (df.loc[down, ["imported", "exported"]].to_numpy() == 0).all()
    assert (df.loc[~down, ["lost_load", "curtailment"]].to_numpy() == 0).all()


def test_shared_battery_reduces_lost_load():
    alone = run(outage_rate=20, pricing="none").kpis()["lost_load_kwh"]
    shared = run(outage_rate=20, storage_mode="shared", storage_kwh=100).kpis()["lost_load_kwh"]
    assert shared < alone


def test_weather_year_varies_with_seed_and_can_be_fixed():
    years = {Community(rng=s).weather_year for s in range(10)}
    assert len(years) > 1
    m = Community(rng=1, weather_year=2023)
    assert m.weather_year == 2023 and m.pv_yield.sum() == pytest.approx(1520, rel=0.01)
    with pytest.raises(ValueError):
        Community(rng=1, weather_year=1990)


def test_no_temperature_effect_keeps_annual_demand():
    m = Community(rng=1, heat_sensitivity=0, cool_sensitivity=0)
    assert np.all(m.demand_factor == 1)
    for h in m.households:
        assert h.base_demand.sum() == pytest.approx(h.annual_kwh)


def test_colder_than_usual_days_raise_demand():
    """Demand goes up on days colder than the average climate, and down on milder ones (winter)."""
    m = Community(rng=1, weather_year=2023)
    day_index = np.cumsum(m.local_hour == 0) - 1
    winter = day_index < 59  # January and February
    daily_t = np.bincount(day_index, weights=m.temperature) / np.bincount(day_index)
    factor = np.bincount(day_index, weights=m.demand_factor) / np.bincount(day_index)
    cold, mild = np.argmin(daily_t[:59]), np.argmax(daily_t[:59])
    assert factor[cold] > factor[mild]
    assert 0.8 < m.demand_factor[winter].mean() < 1.2


def test_relative_savings():
    assert run(pricing="none").kpis()["relative_savings"] == pytest.approx(0, abs=1e-9)
    assert 0 < run(pricing="mid_market").kpis()["relative_savings"] < 1


def test_battery_limits_and_losses():
    b = Battery(10, c_rate=0.5, round_trip_efficiency=0.81, soc=0.5)
    assert b.charge(100) == pytest.approx(5)  # power limit 5 kW
    assert b.soc == pytest.approx(0.95)  # 5 kWh * 0.9 stored
    assert b.charge(100) == pytest.approx(0.5 / 0.9)  # limited by room
    assert b.soc == pytest.approx(1.0)
    assert b.discharge(100) == pytest.approx(5)
    assert b.stored_kwh == pytest.approx(10 - 5 / 0.9)
