"""Interactive Mesa (Solara) visualisation of the community microgrid.

Run from the repo root:
    solara run app.py

The model has no spatial grid (ODD section 2), so houses are laid out in rows
only for display. Tip: set "Steps per frame" to 24 to advance a day per frame.
"""

import math
import sys
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import solara
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon, Rectangle
from mesa.visualization.solara_viz import ModelController, ModelCreator
from mesa.visualization.utils import update_counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model.model import DATA_DIR, PRICING_MECHANISMS, STORAGE_MODES, Community  # noqa: E402

LOCAL_TIME = pd.to_datetime(pd.read_csv(DATA_DIR / "pv_porto.csv")["time_utc"], utc=True).dt.tz_convert("Europe/Lisbon")
WINDOW_H = 72

# Colours (validated categorical palette, see notebooks); each state has a fixed colour
BLUE, ORANGE, AQUA, YELLOW, RED, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948", "#898781"
INK, INK2, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
STATES = {  # house body colour by what happens to it this hour
    "surplus": (ORANGE, "surplus (sharing / exporting)"),
    "local": (AQUA, "deficit covered locally"),
    "import": (BLUE, "importing from the grid"),
    "lost": (RED, "unserved (outage)"),
    "idle": ("#e1e0d9", "balanced / not started"),
}


def house_state(h):
    if h.lost_load > 1e-9:
        return "lost"
    if h.imported > 1e-9:
        return "import"
    if h.deficit > 1e-9:
        return "local"
    if h.surplus > 1e-9:
        return "surplus"
    return "idle"


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=GRAY, labelcolor=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def time_axis(ax, fig, model):
    """Fixed 72 h window ending at the current hour, labelled in local time."""
    start = max(0, model.hour - WINDOW_H + 1)
    ax.set_xlim(LOCAL_TIME.iloc[start], LOCAL_TIME.iloc[min(start + WINDOW_H - 1, len(LOCAL_TIME) - 1)])
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12], tz="Europe/Lisbon"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %Hh", tz="Europe/Lisbon"))
    fig.autofmt_xdate(rotation=0, ha="center")


def window(model):
    df = model.datacollector.get_model_vars_dataframe()
    if df.empty:
        return df, LOCAL_TIME.iloc[:0]
    df = df.iloc[-WINDOW_H:]
    return df, LOCAL_TIME.iloc[model.hour - len(df) + 1:model.hour + 1].to_numpy()


def neighbourhood_figure(model):
    """One house per household, the community battery and the grid connection."""
    hh = sorted(model.households, key=lambda h: (-h.pv_kwp, h.unique_id))
    n = len(hh)
    cols = math.ceil(math.sqrt(n * 1.6))
    rows = math.ceil(n / cols)

    fig = Figure(figsize=(7.5, 4.6), facecolor=SURFACE)
    ax = fig.add_axes([0.0, 0.18, 0.78, 0.74])
    ax.set_xlim(-0.3, cols)
    ax.set_ylim(-0.4, rows + 0.1)
    ax.axis("off")
    started = model.steps > 0

    for i, h in enumerate(hh):
        x, y = i % cols, rows - 1 - i // cols
        color = STATES[house_state(h) if started else "idle"][0]
        member = h.is_member and model.pricing != "none"
        alpha = 1.0 if member else 0.35
        ax.add_patch(Rectangle((x + 0.15, y + 0.05), 0.6, 0.45, facecolor=color, alpha=alpha,
                               edgecolor=INK2, lw=0.8, ls="-" if member else "--"))
        roof = "#184f95" if h.is_prosumer else "#7a7975"  # dark blue roof = PV panels
        ax.add_patch(Polygon([(x + 0.08, y + 0.5), (x + 0.45, y + 0.82), (x + 0.82, y + 0.5)],
                             facecolor=roof, alpha=alpha, edgecolor=INK2, lw=0.8))
        if started and h.pv > 0.05:  # sun on the roof when the panels produce
            ax.add_patch(Circle((x + 0.45, y + 0.9), 0.06 + 0.04 * min(h.pv / 3, 1), facecolor=YELLOW, lw=0))
        if h.battery is not None:  # home battery gauge
            ax.add_patch(Rectangle((x + 0.8, y + 0.05), 0.08, 0.45, facecolor="none", edgecolor=INK2, lw=0.6))
            ax.add_patch(Rectangle((x + 0.8, y + 0.05), 0.08, 0.45 * h.battery.soc, facecolor=AQUA, lw=0))

    # Community battery and grid status on the right
    side = fig.add_axes([0.80, 0.18, 0.18, 0.74])
    side.set_xlim(0, 1)
    side.set_ylim(0, 1)
    side.axis("off")
    grid_up = bool(model.grid_available[model.hour]) if started else True
    side.text(0.5, 0.97, "Grid", ha="center", va="top", fontsize=10, color=INK, weight="bold")
    side.text(0.5, 0.89, "connected" if grid_up else "OUTAGE", ha="center", va="top", fontsize=10,
              color=AQUA if grid_up else RED, weight="bold")
    side.text(0.5, 0.74, "Community\nbattery", ha="center", va="top", fontsize=9, color=INK, weight="bold")
    if model.battery is not None:
        soc = model.battery.soc
        side.add_patch(Rectangle((0.3, 0.12), 0.4, 0.45, facecolor="none", edgecolor=INK2, lw=1))
        side.add_patch(Rectangle((0.3, 0.12), 0.4, 0.45 * soc, facecolor=AQUA, lw=0))
        side.text(0.5, 0.05, f"{soc:.0%} of {model.battery.capacity_kwh:.0f} kWh", ha="center", fontsize=8, color=INK2)
    else:
        side.text(0.5, 0.4, "none", ha="center", fontsize=9, color=GRAY)

    title = LOCAL_TIME.iloc[model.hour].strftime("%a %d %b %Y, %H:00") if started else "Not started"
    fig.text(0.01, 0.96, title, fontsize=12, weight="bold", color=INK)
    handles = [Rectangle((0, 0), 1, 1, facecolor=c) for c, _ in STATES.values()]
    labels = [lab for _, lab in STATES.values()]
    handles += [Polygon([(0, 0), (0.5, 1), (1, 0)], facecolor="#184f95"),
                Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=INK2, ls="--")]
    labels += ["roof with PV", "not a member (faded)"]
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=7.5, frameon=False, labelcolor=INK2)
    return fig


def energy_figure(model):
    """Community energy flows over the last 72 hours."""
    fig = Figure(figsize=(6.2, 3.4), facecolor=SURFACE)
    ax = fig.add_subplot()
    style_axes(ax)
    df, t = window(model)
    if len(df):
        for col, c, lab, ls in [("demand", BLUE, "Demand", "-"), ("pv", ORANGE, "PV", "-"),
                                ("imported", AQUA, "Grid import", "--"), ("exported", YELLOW, "Grid export", "--")]:
            ax.plot(t, df[col], color=c, lw=1.6, ls=ls, label=lab)
        ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=4, labelcolor=INK2)
        ax.set_ylim(bottom=0)
        time_axis(ax, fig, model)
    ax.set_title(f"Community energy, last {WINDOW_H} h", loc="left", fontsize=10, weight="bold", color=INK)
    ax.set_ylabel("kWh per hour", color=INK2, fontsize=9)
    fig.tight_layout()
    return fig


def price_figure(model):
    """Local price and the average price members paid per kWh, over the last 72 hours."""
    fig = Figure(figsize=(6.2, 3.4), facecolor=SURFACE)
    ax = fig.add_subplot()
    style_axes(ax)
    df, t = window(model)
    ax.axhline(model.import_price, color=GRAY, ls="--", lw=1)
    ax.axhline(model.export_price, color=GRAY, ls=":", lw=1)
    if len(df):
        ax.plot(t, df["local_price"], color=ORANGE, lw=1.6, label="local price")
        ax.plot(t, df["effective_price"], color=BLUE, lw=1.6, label="price members paid per kWh")
        ax.text(t[0], model.import_price, " grid import", va="bottom", fontsize=8, color=INK2)
        ax.text(t[0], model.export_price, " grid export", va="bottom", fontsize=8, color=INK2)
        ax.legend(loc="lower right", fontsize=8, frameon=False, labelcolor=INK2, ncol=2)
        time_axis(ax, fig, model)
    ax.set_ylim(0, model.import_price * 1.15)
    ax.set_title(f"Prices ({model.pricing}), last {WINDOW_H} h", loc="left", fontsize=10, weight="bold", color=INK)
    ax.set_ylabel("EUR/kWh", color=INK2, fontsize=9)
    fig.tight_layout()
    return fig


def Indicators(model):
    """Running KPIs since 1 January."""
    if model.steps == 0:
        return solara.Markdown("Press **Step** or **▶** to start the simulation.")
    df = model.datacollector.get_model_vars_dataframe()
    hh = list(model.households)
    demand, pv = df["demand"].sum(), df["pv"].sum()
    savings = sum(h.savings_eur for h in hh) + model.battery_cash_eur
    pros = [h.savings_eur for h in hh if h.is_prosumer]
    cons = [h.savings_eur for h in hh if not h.is_prosumer]
    rows = [
        ("Members", f"{len(model.members)} of {len(hh)}" + (f"  (left {model.leaves}, joined {model.joins})" if model.membership else "")),
        ("Community savings", f"{savings:,.0f} EUR"),
        ("Mean savings: prosumer / consumer", f"{np.mean(pros) if pros else 0:,.1f} / {np.mean(cons) if cons else 0:,.1f} EUR"),
        ("Self-sufficiency", f"{(demand - df['imported'].sum() - df['lost_load'].sum()) / demand:.1%}"),
        ("Self-consumption", f"{(pv - df['exported'].sum() - df['curtailment'].sum()) / pv:.1%}" if pv > 0 else "–"),
        ("Peak grid import", f"{df['imported'].max():.1f} kW"),
        ("Outage hours / unserved energy", f"{int((~df['grid_available'].astype(bool)).sum())} h / {df['lost_load'].sum():.1f} kWh"),
    ]
    table = "\n".join(f"| {k} | **{v}** |" for k, v in rows)
    return solara.Markdown(f"#### Since 1 January (day {model.hour // 24 + 1})\n\n| Indicator | Value |\n|---|---|\n{table}")


model_params = {
    "rng": {"type": "SliderInt", "value": 42, "label": "Seed", "min": 0, "max": 99, "step": 1},
    "n_households": {"type": "SliderInt", "value": 30, "label": "Households", "min": 10, "max": 60, "step": 5},
    "pv_share": {"type": "SliderFloat", "value": 0.4, "label": "Share with PV", "min": 0.0, "max": 1.0, "step": 0.1},
    "pricing": {"type": "Select", "value": "mid_market", "label": "Pricing mechanism", "values": list(PRICING_MECHANISMS)},
    "storage_mode": {"type": "Select", "value": "none", "label": "Storage", "values": list(STORAGE_MODES)},
    "storage_kwh": {"type": "SliderInt", "value": 100, "label": "Battery capacity, total (kWh)", "min": 0, "max": 300, "step": 25},
    "flexibility": {"type": "SliderFloat", "value": 0.0, "label": "Demand-response flexibility", "min": 0.0, "max": 0.3, "step": 0.05},
    "outage_rate": {"type": "SliderFloat", "value": 4.0, "label": "Outages per year", "min": 0.0, "max": 24.0, "step": 1.0},
    "membership": {"type": "Checkbox", "value": False, "label": "Membership change (join / leave)"},
    "initial_member_share": {"type": "SliderFloat", "value": 0.8, "label": "Members at start", "min": 0.5, "max": 1.0, "step": 0.05},
    "savings_threshold": {"type": "SliderFloat", "value": 2.0, "label": "Min. savings to stay (EUR / 30 days)", "min": 0.0, "max": 10.0, "step": 0.5},
}


class CommunityViz(Community):
    """Community whose households all start as members unless membership change is on."""

    def __init__(self, membership=False, initial_member_share=0.8, scenario=None, **kwargs):
        # On Reset, Mesa passes the seed inside a Scenario object
        if scenario is not None and kwargs.get("rng") is None:
            kwargs["rng"] = scenario.rng
        super().__init__(membership=membership, initial_member_share=initial_member_share if membership else 1.0,
                         **kwargs)


DEFAULTS = {k: v["value"] for k, v in model_params.items()}


@solara.component
def Dashboard(model):
    """Main panels, redrawn after every step."""
    update_counter.get()  # re-render when Mesa signals a new step
    with solara.Columns([3, 2]):
        solara.FigureMatplotlib(neighbourhood_figure(model), format="png")
        Indicators(model)
    with solara.Columns([1, 1]):
        solara.FigureMatplotlib(energy_figure(model), format="png")
        solara.FigureMatplotlib(price_figure(model), format="png")


@solara.component
def Page():
    """Mesa's controls (ModelController, ModelCreator) in a left column and the panels on the right.

    SolaraViz's own layout (sidebar + draggable grid) does not render correctly
    with the Vue 3 front end installed here, so the page is assembled by hand.
    """
    model = solara.use_reactive(solara.use_memo(lambda: CommunityViz(**DEFAULTS), []))
    params = solara.use_reactive({})
    play_interval = solara.use_reactive(50)
    render_interval = solara.use_reactive(1)
    use_threads = solara.use_reactive(False)

    solara.Title("Community Microgrid")
    with solara.Columns([1, 4]):
        with solara.Column():
            with solara.Card("Controls"):
                solara.SliderInt("Play interval (ms)", value=play_interval, min=1, max=500, step=10)
                solara.SliderInt("Steps per frame", value=render_interval, min=1, max=168)
                solara.Text("1 step = 1 hour; 24 = one day per frame", style={"font-size": "0.8em"})
                ModelController(model, model_parameters=params, play_interval=play_interval,
                                render_interval=render_interval, use_threads=use_threads)
            with solara.Card("Scenario"):
                solara.Text("Change values, then press Reset", style={"font-size": "0.8em"})
                ModelCreator(model, model_params, model_parameters=params)
        with solara.Column():
            Dashboard(model.value)
