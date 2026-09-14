"""Nutrient-solution pipework of the PFAL room and a schematic flow animation.

Sources: blue PVC points extracted from the point cloud (colour), the pipe photos of
2026-09-13 (IMG_2555-2573), the site notes and the DESIGN drawing
(data/raw/doc/Plan Layout PFAL SISKU.pdf, pages 6-7) which names the risers:
"inlet circulation set" at the DOOR end and "return pipe to tank" at the FAR end.
The network is a hand-modelled polyline graph in the ROOM frame — centre-lines to
about ±5 cm where the scan shows the pipe, photo/drawing-based elsewhere. There is NO
flow-rate sensor, so the animation shows direction and on/off state only.

Growing loop (tiers 2-5, gc1, 200 L tank at the far end) — CONFIRMED on site 2026-09-14
----------------------------------------------------------------------------------------
pump in the 200 L tank -> white 1" line out of the tank side (bulkhead, IMG_2535) running
along the rack at ~0.3 m -> DOOR end -> white 1" riser -> per-tier header with two red ball
valves (flow balancing, IMG_2570-2573) -> tray inlet -> tray (door -> far) -> tray outlet ->
blue branch with red valve -> blue 1.5" riser at the far end (IMG_2561-2564) -> tank.

Nursery loops (tier 1): nursery 1 = door-end half, nursery 2 = far-end half by the growing
tank; each has its own 100 L tank below and — by design — its own pump. The pump lines up to
the trays were not photographed (dashed); the nursery-1 header (IMG_2569, white 1" with three
red ball valves) sits at the door-end corner next to the growing riser. Each tray drains by
gravity through a blue drop into its own tank (green valve "ก๊อกน้ำวนถัง", IMG_2558/2565).
gc2 + dosing box A + sample pot dose the nursery-2 tank.

Blue 1.5" floor line = DRAIN / OVERFLOW MANIFOLD, not a supply: it joins the bottom of all
three tanks through unions + green valves (IMG_2559/2560/2565) and leaves through the
far-end wall to a discharge outside (IMG_2559/2553). Fresh water: wall valves labelled tap /
RO -> two white lines on the floor -> fill valves.

Kinds
-----
supply      blue 1.5" floor main (tank pump -> door end) + branches to the nursery boxes
supply_hdr  white 1" riser + per-tier headers with balancing valves at the door end
tray        flow along the tray (door -> far)
return      blue 1.5" far-end riser with tees: tray outlets -> tank (SEEN, solid)
return_hyp  assumed pump risers of the nursery loop (dashed) — the only unseen part left
drain       blue waste line through the far-end wall to outside
fill_tap / fill_ro   white 1" lines from the labelled wall valves
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import MODEL_DIR

KIND_STYLE = {
    "supply":     dict(color="#1f77b4", width=7, dash="solid", name="supply: white 1\" from the 200 L tank pump -> door-end riser"),
    "supply_hdr": dict(color="#6baed6", width=6, dash="solid", name="supply: white riser + headers with balancing valves (door end)"),
    "tray":       dict(color="#2ca02c", width=6, dash="solid", name="flow along tray (door -> far end)"),
    "return":     dict(color="#08519c", width=8, dash="solid", name="return: blue riser with tees (far end) / tray drops -> tanks"),
    "manifold":   dict(color="#4a4a8a", width=7, dash="dashdot", name="blue 1.5\" floor manifold: drain / overflow between tanks"),
    "return_hyp": dict(color="#b15928", width=4, dash="dash",  name="nursery pump lines (assumed, not seen)"),
    "drain":      dict(color="#08306b", width=6, dash="dot",   name="waste drain to outside through the wall (blue)"),
    "dosing":     dict(color="#7f3fbf", width=3, dash="dot",   name="dosing tubes A / B / pH (peristaltic, 6 mm)"),
    "fill_tap":   dict(color="#e6550d", width=5, dash="solid", name="tap water (white PVC, wall valve labelled tap)"),
    "fill_ro":    dict(color="#7fc8d8", width=5, dash="solid", name="RO water (white PVC, wall valve labelled RO)"),
}
DASH_MPL = {"solid": "-", "dash": (0, (5, 3)), "dot": (0, (1, 2)), "dashdot": (0, (6, 2, 1, 2))}

# fittings / valves: how they are drawn (matplotlib marker, plotly symbol, colour)
FITTING_STYLE = {
    "valve_green": dict(mpl="s", plotly="square",  color="#2ca02c", name="ball valve (green handle)"),
    "valve_red":   dict(mpl="s", plotly="square",  color="#d62728", name="ball valve (red handle)"),
    "union":       dict(mpl="o", plotly="circle",  color="#1f77b4", name="union"),
    "tee":         dict(mpl="^", plotly="diamond", color="#1f77b4", name="tee"),
    "wall_outlet": dict(mpl=">", plotly="x",       color="#08306b", name="wall penetration -> discharge outside"),
    "wall_valve":  dict(mpl="s", plotly="square",  color="#e6550d", name="wall valve (tap / RO)"),
    "pump":        dict(mpl="P", plotly="circle-open", color="#7f3fbf", name="pump"),
}

# --------------------------------------------------------------------------- pipe-point extraction

def blue_pvc_mask(xyz, rgb, z_min=0.03):
    """Light-blue PVC points (colour rule tuned on the SIS PFAL scan)."""
    r, g, b = (rgb[:, i].astype(int) for i in range(3))
    return (b > r + 40) & (b > 120) & (g > 100) & (xyz[:, 2] > z_min)


def white_floor_pipe_mask(xyz, rgb, y_range=(2.03, 2.14), z_range=(0.02, 0.12), min_rgb=170):
    """Bright points in the narrow floor strip next to the rack where the two white 1" lines run.

    CAUTION: the rack frame itself is cream/white PVC pipe, so a colour rule alone cannot
    separate white *water* pipes from *structure*. This mask is restricted to a floor strip
    and still catches rack-post feet; use it only as a sanity overlay. The white network in
    `build_network` is taken from the photos, not from this mask.
    """
    bright = rgb.min(axis=1) >= min_rgb
    return (bright & (xyz[:, 1] > y_range[0]) & (xyz[:, 1] < y_range[1])
            & (xyz[:, 2] > z_range[0]) & (xyz[:, 2] < z_range[1]))


# --------------------------------------------------------------------------- network definition

def build_network(model, zones=None):
    """Polyline pipe graph for this room. Coordinates depend on the rack position and tier heights."""
    K = model["rack"]
    tz = {t["index"]: t["z"] for t in K["tiers"]}
    x_far, x_door = K["x1"] - 0.05, K["x0"] + 0.08          # tray inlet / drain ends
    yc = 0.5 * (K["y0"] + K["y1"])                          # rack centre line
    Y_BLUE, Y_TAP, Y_RO, Z_FLOOR = 2.20, 2.06, 2.11, 0.05     # floor lines in the Y=W aisle (scan / IMG_2568)
    X_RISER, X_WRISER = 6.15, 0.83                            # blue riser (far end), white riser (door end)
    R_L = model["room"]["L"]
    edges = []

    def add(name, kind, loop, pts, dia=0.048, evidence=""):
        edges.append(dict(name=name, kind=kind, loop=loop, dia=dia, evidence=evidence,
                          pts=[[round(float(v), 3) for v in p] for p in pts]))

    # ---- blue 1.5" floor manifold: tank bottoms <-> each other <-> drain to outside (gravity / emptying / overflow)
    add("200 L tank bottom outlet (union, green valve) -> tee at the rack end", "manifold", "shared",
        [(6.45, 1.40, 0.10), (6.45, 1.40, Z_FLOOR), (X_RISER, 1.40, Z_FLOOR), (X_RISER, 2.10, Z_FLOOR)],
        evidence="IMG_2559/2567/2544: blue 1.5\" pipe out of the 200 L tank through a union and a green valve to a tee; scan manifold X 6.15, Y 0.9-2.2")
    add("tee -> floor manifold", "manifold", "shared", [(X_RISER, 2.10, Z_FLOOR), (X_RISER, Y_BLUE, Z_FLOOR)], evidence="IMG_2559")
    add("waste drain -> through the X=L wall to outside", "drain", "shared",
        [(X_RISER, Y_BLUE, Z_FLOOR), (R_L, Y_BLUE, Z_FLOOR), (R_L + 0.35, Y_BLUE, Z_FLOOR)], dia=0.048,
        evidence="IMG_2559 + scan: blue elbow at the wall corner passes through the wall at floor level; IMG_2553: blue pipe on the ground outside")
    add("floor manifold along the aisle (far end -> door end)", "manifold", "shared",
        [(X_RISER, Y_BLUE, Z_FLOOR), (1.60, Y_BLUE, Z_FLOOR)],
        evidence="IMG_2555/2568 + scan: blue 1.5\" line on the floor along the Y=W aisle; it connects the nursery tanks (unions + green valves) and the 200 L tank bottom with the outside drain -> drain / overflow manifold, not a pressurised supply")
    # ---- growing loop (gc1): pump in the 200 L tank -> white 1" supply line -> door end
    add("200 L tank pump -> white 1\" pipe through the lid (tee) -> rack side", "supply", "gc1",
        [(6.60, 1.50, 0.62), (6.60, 1.95, 0.62), (6.40, 2.04, 0.30)], dia=0.025,
        evidence="IMG_2585: white 1\" pipe across the 200 L tank lid with a tee dropping through the lid into the tank = pump outlet")
    add("white 1\" line along the rack (~0.3 m high) -> door end", "supply", "gc1",
        [(6.40, 2.04, 0.30), (X_WRISER, 2.04, 0.30), (X_WRISER, 2.10, 0.30)], dia=0.025,
        evidence="IMG_2555/2568/2584: white line at ~0.3 m on the rack side running the whole aisle to the door-end riser. CAUTION: the nursery-2 tank also has a white bulkhead outlet into this line (IMG_2535) — which pump feeds which branch is not confirmed")
    add("white 0.3 m line -> red valve -> nursery-2 tray inlet", "supply_hdr", "gc2",
        [(3.30, 2.04, 0.30), (3.30, 2.04, tz[1] + 0.06), (3.30, yc + 0.35, tz[1] + 0.06)], dia=0.025,
        evidence="IMG_2584: white pipe rises from the 0.3 m line next to the '4 tiers' fan box and enters the nursery-2 tray through a red ball valve (door end of the T1-N2 tray)")
    add("white supply riser (door end)", "supply_hdr", "gc1", [(X_WRISER, 2.10, 0.30), (X_WRISER, 2.10, tz[5] + 0.02)], dia=0.025,
        evidence="IMG_2570 (confirmed 2026-09-14 = growing-stage inlet circulation set): white 1\" riser at the rack corner")
    for t in (2, 3, 4, 5):
        z = tz[t]
        add(f"tier {t} supply header + balancing valves -> tray inlet", "supply_hdr", "gc1",
            [(X_WRISER, 2.10, z + 0.02), (x_door, 2.02, z + 0.02), (x_door, yc, z + 0.02)], dia=0.025,
            evidence="IMG_2570-2573 (confirmed 2026-09-14): white 1\" header with two red ball valves teeing into the tray at the door end")
        add(f"tray {t} (door -> far)", "tray", "gc1", [(x_door, yc, z + 0.06), (x_far, yc, z + 0.06)])
        add(f"tier {t} outlet -> return riser tee", "return", "gc1",
            [(x_far, yc, z + 0.10), (X_RISER, yc, z + 0.12), (X_RISER, 2.10, z + 0.12)], dia=0.034,
            evidence="IMG_2561-2564 (confirmed 2026-09-14 = return to tank): blue branch across the tier end into the far-end riser")
    add("blue return riser (far end) -> 200 L tank", "return", "gc1",
        [(X_RISER, 2.10, tz[5] + 0.12), (X_RISER, 2.10, 0.70), (6.40, 1.60, 0.62)],
        evidence="IMG_2557 + scan: vertical blue pipe at X 6.15 with a tee at every tier; drawing p.7 shows it discharging into the 200 L tank")
    # ---- nursery loops: own 100 L tank + own pump each (by design); pump lines not photographed
    z1 = {q["zone"]: q for q in (zones or [])}
    x_n1_end = z1["T1-N1"]["x1"] if "T1-N1" in z1 else K["x0"] + 0.5 * K["length"]
    x_n2_start = z1["T1-N2"]["x0"] if "T1-N2" in z1 else x_n1_end
    # nursery 1 (n1): header with 3 valves at the door end (seen), pump line from the N1 tank up the corner (assumed)
    add("N1 tank pump -> door-end corner -> nursery-1 header (line assumed)", "return_hyp", "n1",
        [(1.66, 1.90, 0.30), (1.66, 2.00, 0.28), (X_WRISER + 0.06, 2.00, 0.28), (X_WRISER + 0.06, 2.06, tz[1] + 0.02)], dia=0.025,
        evidence="by design each nursery tank has its own pump; the line up to the nursery-1 header was not photographed (a second white pipe at the door-end corner?)")
    add("nursery-1 header with 3 valves -> tray T1-N1", "supply_hdr", "n1",
        [(X_WRISER + 0.06, 2.06, tz[1] + 0.02), (x_door, 1.98, tz[1] + 0.02), (x_door, 1.10, tz[1] + 0.02)], dia=0.025,
        evidence="IMG_2569: white 1\" header above the tray end with three red ball valves, one per tray channel (door end)")
    add("tray T1-N1 (nursery 1, flat flood tray, 3 channels)", "tray", "n1", [(x_door, yc, tz[1] + 0.06), (x_n1_end - 0.05, yc, tz[1] + 0.06)])
    add("tray T1-N1 drain -> blue drop -> green valve -> N1 tank", "return", "n1",
        [(1.66, yc, tz[1] - 0.02), (1.66, yc, 0.40), (1.72, 1.85, 0.30)], dia=0.034,
        evidence="IMG_2565/2555: blue drop from the tray bottom above the tank; green valve into the tank side")
    add("N1 tank bottom <-> floor manifold (union + green valve)", "manifold", "shared",
        [(1.90, 1.85, 0.12), (1.90, 1.95, Z_FLOOR), (1.90, Y_BLUE, Z_FLOOR)], dia=0.034,
        evidence="IMG_2555/2558: blue elbows between the N1 tank side and the floor manifold — for emptying / overflow")
    # nursery 2 (gc2): pump line + inlet not photographed; drops seen
    add("N2 tank pump -> white bulkhead outlet -> white 0.3 m line", "supply", "gc2",
        [(5.60, 1.85, 0.25), (5.60, 2.00, 0.30), (5.60, 2.04, 0.30)], dia=0.025,
        evidence="IMG_2535: white 1\" pipe out of the nursery-2 tank side (bulkhead) with an elbow into the white line along the rack; joins the same line as the 200 L pump - which pump serves the nursery-2 inlet vs. the growing riser is not confirmed")
    add("tray T1-N2 (nursery 2, flat flood tray)", "tray", "gc2", [(3.30, yc, tz[1] + 0.06), (5.45, yc, tz[1] + 0.06)])
    add("tray T1-N2 drain -> drop with valve 'tank circulation' -> N2 tank", "return", "gc2",
        [(5.70, yc + 0.15, tz[1] - 0.02), (5.70, yc + 0.15, 0.40), (5.70, 1.80, 0.30)], dia=0.034,
        evidence="IMG_2558: blue drop with a green ball valve labelled 'ก๊อกน้ำวนถัง' entering the nursery-2 tank")
    add("tray T1-N2 second drop -> floor manifold", "manifold", "shared",
        [(5.45, yc + 0.15, tz[1] - 0.02), (5.45, yc + 0.15, Z_FLOOR + 0.02), (5.45, 1.95, Z_FLOOR + 0.02), (5.45, Y_BLUE, Z_FLOOR)], dia=0.034,
        evidence="IMG_2558: left blue drop without a valve to the floor manifold (overflow / emptying)")
    add("N2 tank side unions (+ green valve) -> floor manifold -> 200 L tank corner", "manifold", "shared",
        [(5.93, 1.85, 0.12), (6.05, 1.95, Z_FLOOR + 0.02), (X_RISER, 1.95, Z_FLOOR + 0.02)], dia=0.034,
        evidence="IMG_2560/2544: two unions on the tank side, one through a green valve, teeing into the blue floor pipe to the tee at the 200 L tank")
    # ---- dosing tubes (peristaltic pumps A / B / pH in the dosing boxes -> tanks)
    add("dosing box A (gc2) -> nursery-2 tank", "dosing", "gc2",
        [(5.55, 2.05, 0.55), (5.55, 1.95, 0.40), (5.70, 1.80, 0.36)], dia=0.006,
        evidence="site confirmation 2026-09-14: dosing box A (item 14) doses into the nursery-2 tank (item 20); IMG_2541 tubes")
    add("dosing box B (gc1) -> 200 L tank", "dosing", "gc1",
        [(6.05, 2.05, 0.60), (6.30, 2.00, 0.60), (6.50, 1.90, 0.62)], dia=0.006,
        evidence="by elimination: dosing box B beside the return riser serves the growing-stage tank; IMG_2542")
    # ---- OUTSIDE (service passage beyond the X=L wall): RO plant -> wall valve 'RO'; municipal tap -> wall valve 'tap'; drain -> buried tank
    add("RO storage tank -> centrifugal pump -> RO filter set", "fill_ro", "shared",
        [(7.85, 0.50, 0.15), (7.70, 1.05, 0.15), (7.70, 1.35, 0.15), (7.70, 1.45, 1.10)], dia=0.025,
        evidence="IMG_2579: blue pipe from the slim tank to the yellow pump and up to the filter cartridges (schematic route)")
    add("RO filter set -> along the outside wall -> wall valve 'RO'", "fill_ro", "shared",
        [(7.70, 1.75, 1.10), (7.35, 2.20, 1.10), (7.35, 2.62, 0.60), (7.12, 2.62, 0.45)], dia=0.025,
        evidence="IMG_2579/2577: two blue lines run along the container wall at ~1 m and come through the far-end wall at the valves (IMG_2566)")
    add("municipal tap -> along the outside wall -> wall valve 'tap'", "fill_tap", "shared",
        [(7.90, 2.90, 0.10), (7.35, 2.90, 1.05), (7.35, 2.55, 0.60), (7.12, 2.55, 0.45)], dia=0.025,
        evidence="pptx slide 3: tap water 1/2 in; IMG_2577: second blue line along the wall (source not photographed)")
    add("waste outlet -> along the ground -> buried spent-solution tank (per plan)", "drain", "shared",
        [(R_L + 0.35, Y_BLUE, Z_FLOOR), (8.20, Y_BLUE, 0.02), (8.60, 2.35, -0.30)], dia=0.048,
        evidence="IMG_2577: blue pipes leave the far-end wall at ground level and run along the ground; pptx slide 3: to a buried tank for used solution (tank not seen)")
    # ---- fresh water: two wall valves labelled tap / RO -> two white lines on the floor along the aisle
    add("wall valve 'tap water' -> floor line", "fill_tap", "shared",
        [(7.08, 2.55, 0.45), (7.08, 2.55, 0.06), (7.08, Y_TAP, 0.06), (X_WRISER + 0.3, Y_TAP, 0.06)], dia=0.025,
        evidence="IMG_2566: left valve labelled 'น้ำประปา'; IMG_2568: two white lines on the floor next to the rack")
    add("wall valve 'RO water' -> floor line", "fill_ro", "shared",
        [(7.08, 2.62, 0.45), (7.08, 2.62, 0.06), (7.08, Y_RO, 0.06), (X_WRISER + 0.3, Y_RO, 0.06)], dia=0.025,
        evidence="IMG_2566: right valve labelled 'น้ำ RO'; drawing p.3/5: RO filter set at the far end")
    add("tank fill (small red valve)", "fill_tap", "shared", [(6.62, Y_TAP, 0.06), (6.62, 1.95, 0.40), (6.60, 1.85, 0.55)], dia=0.020,
        evidence="IMG_2559/2567: one of the two white lines branches through a small red valve into the tank; which line (tap / RO) not read")
    add("nursery-1 tank fill", "fill_ro", "n1", [(1.66, Y_RO, 0.06), (1.66, 1.90, 0.30)], dia=0.020, evidence="assumed: RO make-up water for the nursery tanks")
    add("nursery-2 tank fill", "fill_ro", "gc2", [(5.65, Y_RO, 0.06), (5.65, 1.90, 0.30)], dia=0.020, evidence="assumed")
    # ---- fittings (IMG_2559 / 2567 / 2555 / 2561 / 2570-2573)
    fittings = [
        dict(name="200 L tank bottom union (manifold)", type="union", xyz=(6.35, 1.40, 0.05), evidence="IMG_2559"),
        dict(name="tee: manifold / drain", type="tee", xyz=(X_RISER, 2.10, 0.05), evidence="IMG_2559"),
        dict(name="green valve (200 L tank bottom -> manifold)", type="valve_green", xyz=(X_RISER, 1.75, 0.05), evidence="IMG_2559/2567"),
        dict(name="white 1\" bulkhead outlet of the 200 L tank (pump supply)", type="union", xyz=(6.55, 2.00, 0.30), evidence="IMG_2535"),
        dict(name="drain outlet through the wall", type="wall_outlet", xyz=(R_L, Y_BLUE, 0.05), evidence="IMG_2559: blue elbow at the wall corner leaving the room; IMG_2553: blue pipe on the ground outside"),
        dict(name="tank fill valve (small, red)", type="valve_red", xyz=(6.62, 1.95, 0.40), evidence="IMG_2559/2567"),
        dict(name="wall valve 'tap water'", type="wall_valve", xyz=(7.08, 2.55, 0.45), evidence="IMG_2566 label"),
        dict(name="wall valve 'RO water'", type="wall_valve", xyz=(7.08, 2.62, 0.45), evidence="IMG_2566 label"),
        dict(name="RO plant pump (outside)", type="pump", xyz=(7.70, 1.20, 0.20), evidence="IMG_2579"),
        dict(name="wall penetration of the fresh-water lines", type="wall_outlet", xyz=(R_L, 2.58, 0.45), evidence="IMG_2577/2566"),
        dict(name="pump in nursery-1 tank", type="pump", xyz=(1.66, yc - 0.3, 0.15), evidence="assumed (Jecod DC pump controller IMG_2542)"),
        dict(name="pump in nursery-2 tank", type="pump", xyz=(5.65, yc - 0.3, 0.15), evidence="assumed"),
        dict(name="green valve, nursery-1 tank return", type="valve_green", xyz=(1.74, 1.90, 0.10), evidence="IMG_2565 (same arrangement seen at both tanks)"),
        *[dict(name=f"nursery-1 header valve {k+1} (red)", type="valve_red", xyz=(x_door, yv, tz[1] + 0.02), evidence="IMG_2569: three red ball valves on the nursery header, door end") for k, yv in enumerate((1.20, 1.50, 1.80))],
        dict(name="green valve, nursery-2 tank return", type="valve_green", xyz=(5.73, 1.90, 0.10), evidence="IMG_2565"),
        dict(name="pump in growing-stage tank", type="pump", xyz=(6.65, 1.60, 0.15), evidence="design p.6: pump in the 200 L tank; outlet = white bulkhead line (IMG_2535)"),
    ]
    for t in (2, 3, 4, 5):
        z = tz[t]
        fittings.append(dict(name=f"tier {t} outlet valve (red, return branch)", type="valve_red", xyz=(X_RISER, yc + 0.3, z + 0.12), evidence="IMG_2555/2569: red-handle valves on the blue branches at the far end"))
        for k, yv in enumerate((1.25, 1.65)):
            fittings.append(dict(name=f"tier {t} balancing valve {k+1} (red, supply header)", type="valve_red", xyz=(x_door, yv, z + 0.02), evidence="IMG_2570-2573: two red ball valves per tier on the door-end header"))
    return dict(frame="room", kinds=KIND_STYLE, edges=edges, fittings=fittings,
                note="Hand-modelled centre-lines. Growing supply = white 1\" from the 200 L tank pump (bulkhead, IMG_2535) along the rack to the "
                     "door-end riser; return = blue far-end riser. Blue 1.5\" floor line = drain/overflow manifold joining all tank bottoms and the "
                     "outside outlet. Each nursery tank has its own pump by design; their lines to the trays are assumed (dashed). "
                     "No flow sensor: velocities are schematic.")


def save_network(net, name="pipe_network.json"):
    p = MODEL_DIR / name
    with open(p, "w", encoding="utf-8") as f:
        json.dump(net, f, indent=1, ensure_ascii=False)
    return p


def load_network(name="pipe_network.json"):
    with open(MODEL_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def edges_table(net) -> pd.DataFrame:
    rows = []
    for e in net["edges"]:
        p = np.array(e["pts"]); L = float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
        rows.append(dict(name=e["name"], kind=e["kind"], loop=e["loop"], dia_mm=round(1000 * e["dia"]), length_m=round(L, 2), evidence=e["evidence"]))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- plotly

def pipe_traces(net, loops=None, kinds=None, opacity=1.0):
    """One line trace per kind (legend-friendly). `loops` / `kinds` filter what is drawn."""
    by_kind = {}
    for e in net["edges"]:
        if (loops and e["loop"] not in loops) or (kinds and e["kind"] not in kinds):
            continue
        xs, ys, zs, txt = by_kind.setdefault(e["kind"], ([], [], [], []))
        for p in e["pts"]:
            xs.append(p[0]); ys.append(p[1]); zs.append(p[2]); txt.append(f"{e['name']} [{e['loop']}] Ø{1000*e['dia']:.0f} mm")
        xs.append(None); ys.append(None); zs.append(None); txt.append("")
    tr = []
    for kind, (xs, ys, zs, txt) in by_kind.items():
        st = KIND_STYLE[kind]
        tr.append(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", name=st["name"], hovertext=txt, hoverinfo="text",
                               line=dict(color=st["color"], width=st["width"], dash=st.get("dash", "solid")), opacity=opacity))
    return tr


def fitting_traces(net, size=5):
    """One marker trace per fitting type (valves, unions, tees, drains, pumps)."""
    tr = []
    by = {}
    for f in net.get("fittings", []):
        by.setdefault(f["type"], []).append(f)
    for typ, items in by.items():
        st = FITTING_STYLE[typ]
        tr.append(go.Scatter3d(x=[f["xyz"][0] for f in items], y=[f["xyz"][1] for f in items], z=[f["xyz"][2] for f in items],
                               mode="markers", name=st["name"], hovertext=[f"{f['name']}<br>{f['evidence']}" for f in items], hoverinfo="text",
                               marker=dict(size=size, color=st["color"], symbol=st["plotly"], line=dict(color="black", width=1))))
    return tr


def _resample(pts, step):
    p = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    L = seg.sum()
    if L == 0:
        return p[:1], np.array([0.0])
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, L, step)
    out = np.stack([np.interp(t, s, p[:, k]) for k in range(3)], axis=1)
    return out, t


def flow_particles(net, phase, spacing=0.25, active_loops=None):
    """Positions of markers along every active edge, shifted by `phase` (0..1) in flow direction."""
    xs, ys, zs, cs = [], [], [], []
    for e in net["edges"]:
        if e["kind"] in ("manifold", "drain", "fill_tap", "fill_ro", "dosing"):
            continue                                        # no continuous flow on the manifold / fill / dosing lines
        if active_loops is not None and e["loop"] not in active_loops and e["loop"] not in ("shared", "n1"):
            continue                                        # nursery 1 has no pump state -> always animated
        p = np.asarray(e["pts"], float)
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1); L = seg.sum()
        if L < spacing / 2:
            continue
        s = np.concatenate([[0], np.cumsum(seg)])
        offs = (np.arange(0, L, spacing) + phase * spacing) % L
        q = np.stack([np.interp(offs, s, p[:, k]) for k in range(3)], axis=1)
        xs += q[:, 0].tolist(); ys += q[:, 1].tolist(); zs += q[:, 2].tolist(); cs += [KIND_STYLE[e["kind"]]["color"]] * len(q)
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="markers", marker=dict(size=4, color=cs), name="flow", hoverinfo="skip")


def flow_figure(net, base_traces, n_frames=20, spacing=0.25, active_loops=None, title=None, height=800, frame_ms=120):
    """Animated plotly figure: static room/model traces + pipes + moving particles (Play button)."""
    fig = go.Figure(data=list(base_traces) + pipe_traces(net) + fitting_traces(net) + [flow_particles(net, 0.0, spacing, active_loops)])
    fig.frames = [go.Frame(data=[flow_particles(net, k / n_frames, spacing, active_loops)], traces=[len(fig.data) - 1], name=str(k))
                  for k in range(n_frames)]
    fig.update_layout(
        title=title, height=height, margin=dict(l=0, r=0, t=40, b=0), legend=dict(itemsizing="constant"),
        scene=dict(aspectmode="data", xaxis_title="X (m)", yaxis_title="Y (m)", zaxis_title="Z (m)"),
        updatemenus=[dict(type="buttons", showactive=False, x=0.02, y=0.98,
                          buttons=[dict(label="▶ Play", method="animate",
                                        args=[None, dict(frame=dict(duration=frame_ms, redraw=True), fromcurrent=True, transition=dict(duration=0))]),
                                   dict(label="❚❚ Pause", method="animate",
                                        args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])])])
    return fig
