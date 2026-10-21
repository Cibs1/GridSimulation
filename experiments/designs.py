"""Experiment designs (ODD section 8).

Each design maps a scenario label to the Community parameters that differ
from the baseline. Every scenario runs with the same seeds, so scenarios are
paired by seed (common random numbers: same households, weather and outages).
"""

SEEDS = range(30)

PRICING = ["none", "fixed", "mid_market", "sdr", "bill_sharing"]
STORAGE_KWH = [50, 100, 200]


def pricing():
    """E1: pricing mechanism x share of households with PV."""
    return {
        f"{p} | pv {int(s * 100)}%": {"pricing": p, "pv_share": s}
        for s in [0.2, 0.4, 0.6, 0.8]
        for p in PRICING
    }


def storage():
    """E2: no storage vs individual vs shared, same total capacity."""
    scenarios = {"none": {"storage_mode": "none"}}
    for kwh in STORAGE_KWH:
        for mode in ["individual", "shared"]:
            scenarios[f"{mode} {kwh} kWh"] = {"storage_mode": mode, "storage_kwh": kwh}
    return scenarios


def demand_response():
    """E3: demand-response flexibility. Mid-market pricing; with price-independent
    behaviour, the price rule does not change the energy flows (see E1)."""
    return {f"flex {f}": {"flexibility": f} for f in [0.0, 0.1, 0.2]}


def resilience():
    """E4: outage regime x storage x community size."""
    outages = {
        "base (4/yr, 1-8 h)": {"outage_rate": 4, "outage_duration": (1, 8)},
        "frequent (12/yr, 1-8 h)": {"outage_rate": 12, "outage_duration": (1, 8)},
        "long (4/yr, 4-12 h)": {"outage_rate": 4, "outage_duration": (4, 12)},
    }
    storage_opts = {
        "no storage": {"storage_mode": "none"},
        "individual 100": {"storage_mode": "individual", "storage_kwh": 100},
        "shared 100": {"storage_mode": "shared", "storage_kwh": 100},
    }
    return {
        f"{o} | {s} | n={n}": {**op, **sp, "n_households": n}
        for o, op in outages.items()
        for s, sp in storage_opts.items()
        for n in [20, 30, 50]
    }


def sensitivity():
    """E5: one-at-a-time sensitivity around the baseline with a 100 kWh shared battery."""
    base = {"storage_mode": "shared", "storage_kwh": 100}
    scenarios = {"baseline": base}
    for c in [0.5, 0.75]:
        scenarios[f"cooperation {c}"] = {**base, "cooperation": c}
    for e in [0.8, 0.95]:
        scenarios[f"efficiency {e}"] = {**base, "battery_efficiency": e}
    for p in [0.03, 0.08]:
        scenarios[f"export price {p}"] = {**base, "export_price": p}
    return scenarios


DESIGNS = {
    "e1_pricing": pricing,
    "e2_storage": storage,
    "e3_demand_response": demand_response,
    "e4_resilience": resilience,
    "e5_sensitivity": sensitivity,
}
