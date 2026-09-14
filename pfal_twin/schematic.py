"""Water & nutrient system views: a filtered plan (tanks, dosing, controllers, valves, every
pipe, RO plant and drain outside) and a not-to-scale process flow diagram.

Both are pure matplotlib so they render identically in the notebook and in the exported PNG.
Text is English (the default fonts have no Thai glyphs)."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mp
from matplotlib.lines import Line2D

from .viz import EQUIP_COLORS, draw_pipes_2d, _stack_labels_near
from .hydraulics import KIND_STYLE, FITTING_STYLE, DASH_MPL

WATER_CATEGORIES = ("nutrient", "water")
WATER_NAME_KEYS = ("Grow Controller", "Dosing box", "tank", "Tank", "RO ", "pump", "Buried")


def water_items(eq):
    m = eq.category.isin(WATER_CATEGORIES) | eq.name.str.contains("|".join(WATER_NAME_KEYS), regex=True)
    return eq[m].reset_index(drop=True)


def water_system_plan(model, net, eq, sensors=None, figsize=(21, 8.5)):
    """Plan view restricted to the water / nutrient system, with a numbered key and all pipe kinds."""
    R, K = model["room"], model["rack"]
    W = water_items(eq)
    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(1, 2, width_ratios=[3.0, 1.35], wspace=0.03)
    ax, kax = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    # room, anteroom, outside strips
    ante = eq[eq.location == "anteroom"] if "location" in eq else eq.iloc[0:0]
    far = W[W.location == "outside_far"] if "location" in W else W.iloc[0:0]
    x_lo = float(ante.x0.min()) - 0.4 if len(ante) else -0.3
    x_hi = float(far.x1.max()) + 0.3 if len(far) else R["L"] + 0.3
    ax.add_patch(mp.Rectangle((0, 0), R["L"], R["W"], fill=False, lw=2, ec="black"))
    ax.add_patch(mp.Rectangle((K["x0"], K["y0"]), K["length"], K["width"], fc="#eef6ec", ec="#2a7d2a", lw=1.2, ls="--"))
    ax.text(K["x0"] + 0.1, K["y1"] - 0.12, "rack: tiers 2-5 growing (above), tier 1 nursery 1 | nursery 2", fontsize=7.5, color="#2a7d2a")
    if len(ante):
        a = ante.iloc[0]
        ax.add_patch(mp.Rectangle((a.x0, 0), a.x1 - a.x0, R["W"], fc="#f7f7f7", ec="#888", ls="--", hatch="//", alpha=0.5))
        ax.text(0.5 * (a.x0 + a.x1), R["W"] * 0.5, "ANTEROOM\n(sink, not scanned)", ha="center", va="center", fontsize=7.5, color="#444")
    if len(far):
        ax.add_patch(mp.Rectangle((R["L"] + 0.05, -0.1), x_hi - R["L"] - 0.08, R["W"] + 0.2, fc="#efefef", ec="#bbb", ls=":"))
        ax.text(0.5 * (R["L"] + x_hi), R["W"] + 0.06, "OUTSIDE (service side)\nRO plant / drain — schematic", ha="center", va="top", fontsize=7, color="#555")
    # equipment boxes (numbered)
    key = {}
    for i, r in W.iterrows():
        n = str(i + 1); key[r["name"]] = n
        ax.add_patch(mp.Rectangle((r.x0, r.y0), r.x1 - r.x0, r.y1 - r.y0, fc=EQUIP_COLORS.get(r.category, "#888"), ec="black", lw=0.6, alpha=0.5))
        ax.annotate(n, (0.5 * (r.x0 + r.x1), 0.5 * (r.y0 + r.y1)), fontsize=8, ha="center", va="center", fontweight="bold",
                    bbox=dict(boxstyle="circle,pad=0.15", fc="white", ec="none", alpha=0.9), zorder=6)
    # pipes + fittings
    handles = draw_pipes_2d(ax, net, axes=(0, 1), lw_scale=0.45, fittings=True, fitting_size=28)
    # inline labels for the long runs
    for kind, (txt, lx, ly, px) in {
        "manifold": ("blue 1.5\" floor manifold: drain / overflow (all tanks -> outside)", 3.3, 3.32, 3.3),
        "supply":   ("growing supply: white 1\" from the 200 L tank pump (0.3 m up) -> door-end riser", 3.0, 2.72, 3.0),
        "fill_tap": ("tap water (white)", 1.4, 2.46, 1.4),
        "fill_ro":  ("RO water (white)", 4.9, 2.46, 4.9),
    }.items():
        best = None
        for e in net["edges"]:
            if e["kind"] == kind:
                q = np.asarray(e["pts"]); L = abs(q[-1, 0] - q[0, 0])
                if best is None or L > best[0]: best = (L, q)
        if best:
            q = best[1]; o = np.argsort(q[:, 0]); py = float(np.interp(px, q[o, 0], q[o, 1]))
            ax.annotate(txt, (px, py), xytext=(lx, ly), fontsize=7.5, ha="center", color=KIND_STYLE[kind]["color"],
                        arrowprops=dict(arrowstyle="-", color=KIND_STYLE[kind]["color"], lw=0.8), zorder=7)
    # sensors related to water
    if sensors is not None:
        ws = sensors[sensors.sensor.isin(["gc1", "gc2", "waterLevel_1"])]
        ax.scatter(ws.x, ws.y, marker="D", s=40, c="#d62728", ec="black", zorder=7)
        _stack_labels_near(ax, ws[["x", "y"]].values, ws.sensor.tolist(), "#d62728", fontsize=8)
    ax.set_xlim(x_lo, x_hi); ax.set_ylim(-0.25, R["W"] + 0.6); ax.set_aspect("equal")
    ax.set_xlabel("X — room length (m)"); ax.set_ylabel("Y — room width (m)")
    ax.set_title("Water & nutrient system — plan view (tanks, dosing, controllers, valves, pipework; RO plant and drain outside)")
    # key
    kax.axis("off")
    import textwrap
    lines = ["WATER / NUTRIENT ITEMS"]
    for _, r in W.iterrows():
        wrapped = textwrap.wrap(r["name"] + ("" if r.verified else "  (not seen)"), 46)
        lines.append(f"{key[r['name']]:>2}  {wrapped[0]}"); lines += ["    " + w for w in wrapped[1:]]
    kax.text(0, 0.98, "\n".join(lines), va="top", ha="left", fontsize=7.2, family="monospace", transform=kax.transAxes)
    kax.legend(handles=handles, fontsize=7, loc="lower left", frameon=False, title="pipes / fittings", title_fontsize=8, ncol=1)
    return fig


# --------------------------------------------------------------------------- process flow diagram

def _box(ax, x, y, w, h, text, fc="#ffffff", ec="#333333", fs=8, lw=1.2, ls="-", bold=False):
    ax.add_patch(mp.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal")
    return (x, y, w, h)


def _arrow(ax, p0, p1, color, text=None, ls="-", lw=1.8, tpos=0.5, dx=0.0, dy=0.12, fs=7):
    ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls=ls, shrinkA=2, shrinkB=2, mutation_scale=14))
    if text:
        ax.text(p0[0] + (p1[0] - p0[0]) * tpos + dx, p0[1] + (p1[1] - p0[1]) * tpos + dy, text, fontsize=fs, color=color, ha="center", va="bottom")


def water_flow_diagram(figsize=(22, 12)):
    """Not-to-scale process flow of the whole water system (as understood on 2026-09-14).
    Solid = seen on site / confirmed, dashed = assumed / from the design drawing only."""
    C = {k: v["color"] for k, v in KIND_STYLE.items()}
    fig, ax = plt.subplots(figsize=figsize); ax.set_xlim(0, 24); ax.set_ylim(0, 11.6); ax.axis("off")
    ax.set_title("PFAL SISKU — water & nutrient process flow (not to scale; dashed = assumed / design only)", fontsize=12, pad=12)
    # zones
    ax.add_patch(mp.Rectangle((0.3, 0.3), 4.6, 10.6, fc="#f2f2f2", ec="#bbb", ls=":")); ax.text(2.6, 10.65, "OUTSIDE — service side (RO plant, drain)", ha="center", fontsize=8, color="#555")
    ax.add_patch(mp.Rectangle((5.2, 0.3), 18.4, 10.6, fc="#ffffff", ec="#333", lw=1.5)); ax.text(14.4, 10.65, "GROW ROOM", ha="center", fontsize=8, color="#333")
    # outside
    _box(ax, 0.7, 9.1, 3.8, 0.8, "Municipal tap water", fc="#fde9dc", ec=C["fill_tap"])
    _box(ax, 0.7, 6.6, 1.7, 1.1, "RO storage\ntank (5 m³)", fc="#e0f0f7", ec=C["fill_ro"])
    _box(ax, 2.8, 6.75, 1.7, 0.8, "pump\n≥3000 L/h", fc="#e0f0f7", ec=C["fill_ro"])
    _box(ax, 0.7, 3.9, 3.8, 0.8, "RO filter set (3-stage)", fc="#e0f0f7", ec=C["fill_ro"])
    _box(ax, 0.7, 1.1, 3.8, 1.0, "Buried spent-solution tank\n(design; not seen)", fc="#eeeeee", ec=C["drain"], ls="--")
    _arrow(ax, (2.4, 7.15), (2.8, 7.15), C["fill_ro"]); _arrow(ax, (3.65, 6.75), (3.65, 4.7), C["fill_ro"])
    _arrow(ax, (4.5, 4.3), (5.2, 4.3), C["fill_ro"], "wall valve 'RO'", dy=0.12, fs=6.5)
    _arrow(ax, (4.5, 9.5), (5.2, 9.5), C["fill_tap"], "wall valve 'tap'", dy=0.12, fs=6.5)
    # tanks (row y 1.2-2.8)
    _box(ax, 5.7, 1.2, 2.8, 1.6, "NURSERY-1 TANK 100 L\nno controller\n(pump: assumed)", fc="#d9ecea", ec="#1a7a74")
    _box(ax, 9.0, 1.2, 3.4, 1.6, "NURSERY-2 TANK 100 L\ngc2 · dosing box A · sample pot\n(pump: assumed)", fc="#d9ecea", ec="#1a7a74")
    _box(ax, 13.0, 1.2, 4.6, 1.6, "200 L GROWING TANK\npump · gc1 · dosing box B (Jecod)\nsample pot EC/pH · level sensor", fc="#d9ecea", ec="#1a7a74", bold=True)
    # trays (row y 7.2-8.5)
    _box(ax, 5.7, 7.2, 2.8, 1.0, "nursery-1 tray (T1-N1)", fc="#eaf5e6", ec=C["tray"])
    _box(ax, 9.0, 7.2, 3.4, 1.0, "nursery-2 tray (T1-N2)", fc="#eaf5e6", ec=C["tray"])
    _box(ax, 13.0, 7.0, 7.0, 1.4, "GROWING TRAYS, tiers 2–5\nflow: door end → far end", fc="#eaf5e6", ec=C["tray"], bold=True)
    # growing loop: tank -> white line -> riser -> headers -> trays -> blue riser -> tank
    _arrow(ax, (16.9, 2.8), (16.9, 4.6), C["supply"]); ax.text(17.1, 3.95, "white 1\" bulkhead outlet → line along the rack (0.3 m)", fontsize=6.8, color=C["supply"], va="center")
    _arrow(ax, (16.9, 4.6), (13.9, 4.6), C["supply"])
    _arrow(ax, (13.9, 4.6), (13.9, 7.0), C["supply_hdr"]); ax.text(14.1, 5.8, "white riser (door end)\n+ header with 2 balancing\nvalves per tier", fontsize=6.8, color=C["supply_hdr"], ha="left", va="center")
    _arrow(ax, (20.0, 7.7), (21.2, 7.7), C["return"]); _arrow(ax, (21.2, 7.7), (21.2, 2.0), C["return"]); _arrow(ax, (21.2, 2.0), (17.6, 2.0), C["return"])
    ax.text(21.4, 4.9, "blue 1.5\" return riser\n(tee at every tier, far end)", fontsize=6.8, color=C["return"], va="center")
    # nursery 1
    _arrow(ax, (6.3, 2.8), (6.3, 7.2), C["return_hyp"], ls="--"); ax.text(6.1, 5.0, "pump line\n(assumed)", fontsize=6.8, color=C["return_hyp"], ha="right", va="center")
    ax.text(7.1, 8.35, "header with 3 red valves (seen)", fontsize=6.5, color=C["supply_hdr"], ha="center")
    _arrow(ax, (7.9, 7.2), (7.9, 2.8), C["return"]); ax.text(7.75, 5.0, "drop +\ngreen valve", fontsize=6.8, color=C["return"], ha="right", va="center")
    # nursery 2
    _arrow(ax, (9.6, 2.8), (9.6, 7.2), C["return_hyp"], ls="--"); ax.text(9.8, 5.0, "pump line\n(assumed)", fontsize=6.8, color=C["return_hyp"], ha="left", va="center")
    _arrow(ax, (11.8, 7.2), (11.8, 2.8), C["return"]); ax.text(12.0, 5.0, "drop + valve\n'tank circulation'", fontsize=6.8, color=C["return"], va="center")
    # dosing
    for x in (11.3, 15.0):
        _arrow(ax, (x, 3.35), (x, 2.8), C["dosing"], ls=":", lw=1.2); ax.text(x, 3.45, "dosing A / B / pH", fontsize=6.5, color=C["dosing"], ha="center")
    # fills
    _arrow(ax, (5.2, 9.5), (22.6, 9.5), C["fill_tap"]); ax.text(11.0, 9.62, "white floor line — tap water", fontsize=6.8, color=C["fill_tap"], ha="center")
    _arrow(ax, (22.6, 9.5), (22.6, 3.3), C["fill_tap"]); _arrow(ax, (22.6, 3.3), (17.6, 3.3), C["fill_tap"]); ax.text(20.1, 3.42, "fill valve (small, red)", fontsize=6.5, color=C["fill_tap"], ha="center")
    _arrow(ax, (5.2, 4.3), (7.2, 4.3), C["fill_ro"], ls="--"); _arrow(ax, (7.2, 4.3), (7.2, 2.8), C["fill_ro"], ls="--")
    ax.text(7.35, 3.6, "RO make-up\n(assumed)", fontsize=6.5, color=C["fill_ro"], va="center")
    _arrow(ax, (7.2, 4.3), (10.2, 4.3), C["fill_ro"], ls="--"); _arrow(ax, (10.2, 4.3), (10.2, 2.8), C["fill_ro"], ls="--")
    # manifold + drain
    ax.plot([5.7, 17.6], [0.75, 0.75], color=C["manifold"], lw=3, ls=DASH_MPL["dashdot"])
    for x in (7.1, 10.7, 15.3):
        _arrow(ax, (x, 1.2), (x, 0.8), C["manifold"], lw=1.4)
    ax.text(11.6, 0.38, "blue 1.5\" floor manifold — drain / overflow; unions + green valves at every tank bottom", fontsize=7, color=C["manifold"], ha="center")
    _arrow(ax, (5.7, 0.75), (4.5, 1.6), C["drain"], ls=":"); ax.text(5.0, 0.42, "through the wall → outside", fontsize=6.5, color=C["drain"], ha="center")
    handles = [Line2D([0], [0], color=v["color"], lw=3, ls=DASH_MPL.get(v.get("dash", "solid"), "-"), label=v["name"]) for v in KIND_STYLE.values()]
    ax.legend(handles=handles, fontsize=6.8, loc="upper right", bbox_to_anchor=(0.995, 0.985), frameon=True, ncol=2)
    return fig
