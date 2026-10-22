"""Interactive Mesa (Solara) visualisation of the community microgrid.

Run from the repo root:
    solara run app.py

Add --no-open to start the server without opening a browser.

The model has no spatial grid (ODD section 2): houses are drawn on a ring
around the community manager only for display. Tip: set "Steps per frame" to 24 to advance a day per frame.
"""

import sys
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import solara
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
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


def house_glyph(ax, x, y, w, h, color, member):
    """Small house centred on (x, y): body coloured by state, dark blue roof if it has PV."""
    alpha = 1.0 if member else 0.4
    bw, bh = w, w * 0.62
    base = y - bh / 2 - w * 0.1
    ax.add_patch(FancyBboxPatch((x - bw / 2, base), bw, bh, boxstyle="round,pad=0,rounding_size=0.008",
                                facecolor=color, alpha=alpha, edgecolor=INK2, lw=0.7, ls="-" if member else "--",
                                zorder=4))
    roof = "#184f95" if h.is_prosumer else "#7a7975"  # dark blue roof = PV panels
    top = base + bh
    ax.add_patch(Polygon([(x - bw * 0.62, top), (x, top + w * 0.5), (x + bw * 0.62, top)],
                         facecolor=roof, alpha=alpha, edgecolor=INK2, lw=0.7, zorder=4))
    if h.pv > 0.05:  # sun above the roof, larger when the panels produce more
        ax.add_patch(Circle((x + bw * 0.55, top + w * 0.5), w * (0.12 + 0.1 * min(h.pv / 3, 1)),
                            facecolor=YELLOW, lw=0, zorder=5))
    if h.battery is not None:  # home battery gauge next to the right wall
        gx = x + bw / 2 + w * 0.06
        ax.add_patch(Rectangle((gx, base), w * 0.12, bh, facecolor="white", edgecolor=INK2, lw=0.5, zorder=4))
        ax.add_patch(Rectangle((gx, base), w * 0.12, bh * h.battery.soc, facecolor=AQUA, lw=0, zorder=5))


def flow_line(ax, a, b, kwh, color, scale, ls="-", alpha=1.0):
    """Line from a to b, wider for larger flows, with an arrowhead in the middle pointing the way energy flows."""
    k = min(kwh / scale, 1.0)
    ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=0.6 + 4.0 * k, ls=ls, alpha=alpha,
            solid_capstyle="round", zorder=2)
    if kwh > 1e-6:
        m0 = (a[0] * 0.55 + b[0] * 0.45, a[1] * 0.55 + b[1] * 0.45)
        m1 = (a[0] * 0.45 + b[0] * 0.55, a[1] * 0.45 + b[1] * 0.55)
        ax.add_patch(FancyArrowPatch(m0, m1, arrowstyle="-|>", mutation_scale=7 + 6 * k,
                                     color=color, alpha=alpha, lw=0, zorder=3))


def community_figure(model):
    """Households on a ring around the community manager, which links them to the
    community battery and to the grid. Lines show this hour's energy flows."""
    hh = sorted(model.households, key=lambda h: (-h.pv_kwp, h.unique_id))
    n = len(hh)
    mgr = model.manager
    started = model.steps > 0
    grid_up = bool(model.grid_available[model.hour]) if started else True
    night = started and model.flows["pv"] <= 1e-6

    fig = Figure(figsize=(7.6, 7.6), facecolor=SURFACE)
    ax = fig.add_axes([0.0, 0.09, 1.0, 0.84])
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.55, 1.62)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Circle((0, 0), 1.3, facecolor="#e9ecf3" if night else "#fbf6ea", lw=0, zorder=0))

    hub_r = 0.27
    grid_xy, bat_xy = (0.0, 1.45), (0.0, -1.3)

    # One ring of houses (two staggered rings for large communities), with a gap at the top
    # for the grid line and one at the bottom for the community battery
    gap_top, gap_bottom = np.radians(40), np.radians(40 if mgr.battery is not None else 0)
    two_rings = n > 34
    arc = 2 * np.pi - gap_top - gap_bottom
    t = arc * (np.arange(n) + 0.5) / n
    angles = np.pi / 2 - gap_top / 2 - t - np.where(t > arc / 2, gap_bottom, 0)
    radii = np.where(np.arange(n) % 2, 1.13, 0.9) if two_rings else np.full(n, 1.0)
    w = min(0.15, 0.75 * arc / n * (2 if two_rings else 1))

    for h, a, r in zip(hh, angles, radii):
        x, y = r * np.cos(a), r * np.sin(a)
        color = STATES[house_state(h) if started else "idle"][0]
        member = h.is_member and model.pricing != "none"
        house = (x - 0.6 * w * np.cos(a), y - 0.6 * w * np.sin(a))
        hub = (hub_r * np.cos(a), hub_r * np.sin(a))
        out_kwh, in_kwh = h.sold_local + h.exported, h.bought_local + h.imported
        line = dict(ls="-" if member else (0, (2, 2)), alpha=1.0 if member else 0.5)
        if out_kwh >= in_kwh:
            flow_line(ax, house, hub, out_kwh, color if out_kwh > 1e-6 else GRID, 3.0, **line)
        else:
            flow_line(ax, hub, house, in_kwh, color, 3.0, **line)
        house_glyph(ax, x, y, w, h, color, member)

    # Grid: all exchange with the grid goes through the community's connection point
    imp, exp = model.flows["imported"], model.flows["exported"]
    if not grid_up:
        ax.plot([0, 0], [hub_r, grid_xy[1] - 0.09], color=RED, lw=1.5, ls=(0, (3, 3)), zorder=2)
        ax.text(0.07, 1.1, "no connection", fontsize=8, color=RED, va="center", zorder=6)
    elif imp >= exp:
        flow_line(ax, grid_xy, (0, hub_r), imp, BLUE if imp > 1e-6 else GRID, 25.0)
        if imp >= 0.05:
            ax.text(0.07, 1.1, f"import {imp:.1f} kWh", fontsize=8, color=BLUE, va="center", zorder=6)
    else:
        flow_line(ax, (0, hub_r), grid_xy, exp, YELLOW, 25.0)
        if exp >= 0.05:
            ax.text(0.07, 1.1, f"export {exp:.1f} kWh", fontsize=8, color="#a87200", va="center", zorder=6)
    edge = INK2 if grid_up else RED
    ax.add_patch(FancyBboxPatch((grid_xy[0] - 0.26, grid_xy[1] - 0.085), 0.52, 0.17,
                                boxstyle="round,pad=0,rounding_size=0.04", facecolor="white", edgecolor=edge,
                                lw=1.4, zorder=6))
    ax.text(grid_xy[0], grid_xy[1], "GRID" if grid_up else "GRID OUTAGE", ha="center", va="center",
            fontsize=9, weight="bold", color=edge, zorder=7)

    # Community battery, held by the manager
    if mgr.battery is not None:
        ch, dis = mgr.bat_charge, mgr.bat_discharge
        top = (bat_xy[0], bat_xy[1] + 0.13)
        if dis > ch:
            flow_line(ax, top, (0, -hub_r), dis, AQUA, 15.0)
            label = f"out {dis:.1f} kWh"
        else:
            flow_line(ax, (0, -hub_r), top, ch, AQUA if ch > 1e-6 else GRID, 15.0)
            label = f"in {ch:.1f} kWh" if ch >= 0.05 else ""
        bw, bh = 0.2, 0.2
        x0, y0 = bat_xy[0] - bw / 2, bat_xy[1] - bh / 2
        ax.add_patch(FancyBboxPatch((x0, y0), bw, bh, boxstyle="round,pad=0,rounding_size=0.02",
                                    facecolor="white", edgecolor=INK2, lw=1.2, zorder=6))
        ax.add_patch(Rectangle((x0 + 0.02, y0 + 0.02), bw - 0.04, (bh - 0.04) * mgr.battery.soc,
                               facecolor=AQUA, lw=0, zorder=7))
        ax.add_patch(Rectangle((bat_xy[0] - 0.04, y0 + bh), 0.08, 0.025, facecolor=INK2, lw=0, zorder=6))
        ax.text(x0 + bw + 0.05, bat_xy[1], f"Community battery\n{mgr.battery.soc:.0%} of "
                f"{mgr.battery.capacity_kwh:.0f} kWh", ha="left", va="center", fontsize=7.5, color=INK2, zorder=7)
        ax.text(0.07, -0.95, label, fontsize=8, color="#11815a", va="center", zorder=7)

    # Community manager in the centre
    active = model.pricing != "none"
    ax.add_patch(Circle((0, 0), hub_r, facecolor=INK if active else "#7a7975", edgecolor="white", lw=2, zorder=8))
    ax.text(0, 0.085, "Community\nmanager", ha="center", va="center", fontsize=8.5, color="white", weight="bold",
            zorder=9)
    if not active:
        hub_text = "inactive\n(no community)"
    elif not started:
        hub_text = model.pricing
    else:
        price = "–" if np.isnan(mgr.local_price) else f"{mgr.local_price:.3f} €/kWh"
        hub_text = f"{price}\n{mgr.traded:.1f} kWh shared"
    ax.text(0, -0.1, hub_text, ha="center", va="center", fontsize=7.5, color="#d8d7d0", zorder=9)

    title = LOCAL_TIME.iloc[model.hour].strftime("%a %d %b %Y, %H:00") if started else "Not started"
    fig.text(0.03, 0.965, title, fontsize=13, weight="bold", color=INK)
    if started:
        fig.text(0.97, 0.965, "night" if night else "daylight", fontsize=9, color=INK2, ha="right")
    handles = [Rectangle((0, 0), 1, 1, facecolor=c) for c, _ in STATES.values()]
    labels = [lab for _, lab in STATES.values()]
    handles += [Polygon([(0, 0), (0.5, 1), (1, 0)], facecolor="#184f95"),
                Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=INK2, ls="--")]
    labels += ["roof with PV", "not a member (grid prices)"]
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.025), ncol=4, fontsize=7.5,
               frameon=False, labelcolor=INK2)
    fig.text(0.5, 0.012, "Line width = energy this hour; arrows show the direction of flow", ha="center",
             fontsize=7.5, color=GRAY)
    return fig


def ManagerPanel(model):
    """What the community manager did in the current hour."""
    if model.steps == 0:
        return solara.Markdown("")
    if model.pricing == "none":
        return solara.Markdown("#### Community manager, this hour\n\n"
                               "No community: every household trades with the grid on its own.")
    mgr = model.manager
    rows = [
        ("Offers from members (surplus)", f"{mgr.supply:.1f} kWh"),
        ("Bids from members (deficit)", f"{mgr.bids:.1f} kWh"),
        ("Matched locally", f"{mgr.traded:.1f} kWh"),
        ("Community battery in / out",
         f"{mgr.bat_charge:.1f} / {mgr.bat_discharge:.1f} kWh" if mgr.battery else "no battery"),
        ("Grid import / export", f"{model.flows['imported']:.1f} / {model.flows['exported']:.1f} kWh"),
        (f"Local price ({model.pricing})", "–" if np.isnan(mgr.local_price) else f"{mgr.local_price:.3f} EUR/kWh"),
    ]
    table = "\n".join(f"| {k} | **{v}** |" for k, v in rows)
    return solara.Markdown(f"#### Community manager, this hour\n\n| Step | Value |\n|---|---|\n{table}")


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
    savings = sum(h.savings_eur for h in hh) + model.manager.battery_cash_eur
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
        solara.FigureMatplotlib(community_figure(model), format="png")
        with solara.Column():
            ManagerPanel(model)
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
