"""Plants on the growing tiers as 3-D meshes: one plant per hole, shaped by crop and scaled by how far the block is
through its time on the tier (from the planting log, see planting.py).

Illustrative, not measured: size follows days on the tier / planned days, not a canopy measurement.

Three plant forms cover the 30 crops of the `ข้อมูลพืช` tab of PFAL Management:
    rosette   leaves from one point (lettuces, bok choy, spinach, chard, kale, rocket, mizuna, celery, coriander, parsley),
              optionally with a head (iceberg, butterhead) and flower stalks (choy sum)
    bush      upright or sprawling stems with leaves in opposite pairs (basil, holy basil, mint, water spinach,
              amaranth, watercress)
    tubes     hollow upright leaves (spring onion)

    traces = plant_traces(plant_table(rounds, holes))     # -> list of go.Mesh3d, one per crop (legend entry)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Colour of a vertex = its intensity on a per-crop scale: 0 stem / petiole, 0.3 leaf base -> 0.94 leaf tip, 1 flower.
STEM, BASE, TIP, FLOWER = 0.0, 0.3, 0.94, 1.0

# Leaf parameters (lengths in m at harvest size): n leaves, L length, w width/length, tilt from horizontal (deg),
# droop, cup across the blade, ruffle amplitude and waves along the margin, lobes (count, depth), petiole fraction
# (and its width), blade outline lance / oval / spade / round, head radius. Colours: stem, leaf base, leaf tip[, flower].
_ROSETTE = dict(form="rosette", shape="oval", petiole=0.0, lobes=0, lobe_depth=0.0, head=0.0, flowers=0)
STYLES = {
    # ---- lettuces
    "oak":       {**_ROSETTE, "n": 8, "L": 0.14, "w": 0.42, "tilt": 38, "droop": 0.35, "cup": 0.10, "ruffle": 0.20, "waves": 5,
                  "lobes": 4, "lobe_depth": 0.35, "colors": ("#b9d77a", "#b9d77a", "#5d9b35")},
    "redoak":    {**_ROSETTE, "n": 8, "L": 0.13, "w": 0.42, "tilt": 38, "droop": 0.35, "cup": 0.10, "ruffle": 0.20, "waves": 5,
                  "lobes": 4, "lobe_depth": 0.35, "colors": ("#a7c46a", "#a7c46a", "#7a2533")},
    "redcoral":  {**_ROSETTE, "n": 10, "L": 0.12, "w": 0.60, "tilt": 45, "droop": 0.25, "cup": 0.15, "ruffle": 0.45, "waves": 9,
                  "colors": ("#9fbf63", "#9fbf63", "#6e1f35")},
    "cos":       {**_ROSETTE, "n": 7, "L": 0.19, "w": 0.34, "tilt": 70, "droop": 0.10, "cup": 0.30, "ruffle": 0.03, "waves": 2,
                  "shape": "lance", "colors": ("#cfe39a", "#cfe39a", "#4f8f2f")},
    "minicos":   {**_ROSETTE, "n": 7, "L": 0.15, "w": 0.34, "tilt": 68, "droop": 0.10, "cup": 0.30, "ruffle": 0.03, "waves": 2,
                  "shape": "lance", "colors": ("#cfe39a", "#cfe39a", "#4f8f2f")},
    "redcos":    {**_ROSETTE, "n": 7, "L": 0.17, "w": 0.34, "tilt": 68, "droop": 0.10, "cup": 0.30, "ruffle": 0.04, "waves": 2,
                  "shape": "lance", "colors": ("#c7d98e", "#c7d98e", "#7b2a3a")},
    "butter":    {**_ROSETTE, "n": 9, "L": 0.12, "w": 0.85, "tilt": 45, "droop": 0.15, "cup": 0.45, "ruffle": 0.04, "waves": 2,
                  "shape": "round", "head": 0.035, "colors": ("#e2eeb0", "#e2eeb0", "#86b94a")},
    "frilly":    {**_ROSETTE, "n": 9, "L": 0.14, "w": 0.70, "tilt": 42, "droop": 0.30, "cup": 0.15, "ruffle": 0.30, "waves": 7,
                  "colors": ("#d5e8a0", "#d5e8a0", "#77b23c")},
    "batavia":   {**_ROSETTE, "n": 9, "L": 0.15, "w": 0.75, "tilt": 48, "droop": 0.20, "cup": 0.25, "ruffle": 0.25, "waves": 6,
                  "shape": "round", "colors": ("#d9eba4", "#d9eba4", "#5f9e33")},
    "iceberg":   {**_ROSETTE, "n": 6, "L": 0.13, "w": 0.90, "tilt": 30, "droop": 0.30, "cup": 0.40, "ruffle": 0.06, "waves": 3,
                  "shape": "round", "head": 0.06, "colors": ("#e6f0bd", "#e6f0bd", "#7fb24a")},
    # ---- other rosettes
    "rocket":    {**_ROSETTE, "n": 10, "L": 0.13, "w": 0.30, "tilt": 50, "droop": 0.25, "cup": 0.05, "ruffle": 0.05, "waves": 2,
                  "shape": "lance", "petiole": 0.25, "lobes": 3, "lobe_depth": 0.6, "colors": ("#9cc06a", "#7fae4c", "#3f7a2a")},
    "mizuna":    {**_ROSETTE, "n": 12, "L": 0.16, "w": 0.30, "tilt": 55, "droop": 0.30, "cup": 0.0, "ruffle": 0.10, "waves": 3,
                  "shape": "lance", "petiole": 0.35, "lobes": 5, "lobe_depth": 0.75, "colors": ("#e6f0d0", "#8fc155", "#4f8f2f")},
    "bokchoy":   {**_ROSETTE, "n": 8, "L": 0.17, "w": 0.55, "tilt": 72, "droop": 0.05, "cup": 0.45, "ruffle": 0.02, "waves": 2,
                  "petiole": 0.45, "petiole_w": 0.35, "colors": ("#e9f3d4", "#7fb04f", "#3d7a33")},
    "tokyo":     {**_ROSETTE, "n": 9, "L": 0.16, "w": 0.55, "tilt": 66, "droop": 0.10, "cup": 0.30, "ruffle": 0.04, "waves": 2,
                  "petiole": 0.40, "petiole_w": 0.25, "colors": ("#f1f6e2", "#a6cf6d", "#64a33d")},
    "choysum":   {**_ROSETTE, "n": 7, "L": 0.17, "w": 0.45, "tilt": 62, "droop": 0.15, "cup": 0.15, "ruffle": 0.03, "waves": 2,
                  "petiole": 0.40, "flowers": 3, "colors": ("#8fbf5a", "#76ad46", "#3f7a2a", "#f2d23c")},
    "kana":      {**_ROSETTE, "n": 7, "L": 0.16, "w": 0.55, "tilt": 62, "droop": 0.15, "cup": 0.20, "ruffle": 0.04, "waves": 2,
                  "petiole": 0.35, "colors": ("#7fa889", "#5f8f74", "#2f5a4a")},
    "kale":      {**_ROSETTE, "n": 6, "L": 0.18, "w": 0.45, "tilt": 55, "droop": 0.30, "cup": 0.05, "ruffle": 0.35, "waves": 8,
                  "petiole": 0.20, "colors": ("#8fb39a", "#7fa889", "#2f5a45")},
    "spinach":   {**_ROSETTE, "n": 9, "L": 0.13, "w": 0.55, "tilt": 42, "droop": 0.25, "cup": 0.10, "ruffle": 0.05, "waves": 3,
                  "shape": "spade", "petiole": 0.30, "colors": ("#7fae4c", "#4f8f2f", "#2e6a25")},
    "chard":     {**_ROSETTE, "n": 6, "L": 0.20, "w": 0.55, "tilt": 66, "droop": 0.15, "cup": 0.15, "ruffle": 0.15, "waves": 5,
                  "petiole": 0.40, "petiole_w": 0.18, "colors": ("#c0392b", "#4f8f2f", "#2e6a25")},
    "celery":    {**_ROSETTE, "n": 10, "L": 0.20, "w": 0.40, "tilt": 74, "droop": 0.10, "cup": 0.05, "ruffle": 0.10, "waves": 3,
                  "shape": "round", "petiole": 0.65, "lobes": 3, "lobe_depth": 0.5, "colors": ("#b6d58a", "#6fa846", "#3f7a2a")},
    "coriander": {**_ROSETTE, "n": 10, "L": 0.15, "w": 0.55, "tilt": 60, "droop": 0.25, "cup": 0.0, "ruffle": 0.15, "waves": 4,
                  "shape": "round", "petiole": 0.60, "lobes": 3, "lobe_depth": 0.6, "colors": ("#9cc06a", "#6fa846", "#3f8a2a")},
    "parsley":   {**_ROSETTE, "n": 9, "L": 0.15, "w": 0.65, "tilt": 62, "droop": 0.20, "cup": 0.10, "ruffle": 0.45, "waves": 9,
                  "shape": "round", "petiole": 0.55, "lobes": 3, "lobe_depth": 0.4, "colors": ("#7fae4c", "#4f8f2f", "#2e6a25")},
    # ---- bushes: `stems` stems of height H (tilted outward by stem_tilt), `nodes` opposite leaf pairs per stem, L = leaf length
    "basil":     dict(form="bush", stems=3, H=0.22, stem_tilt=12, nodes=4, L=0.06, w=0.55, tilt=30, droop=0.25, cup=0.35,
                      ruffle=0.03, waves=2, shape="oval", colors=("#6b4f6e", "#4f8f2f", "#2f6e25")),
    "holybasil": dict(form="bush", stems=4, H=0.20, stem_tilt=18, nodes=5, L=0.045, w=0.50, tilt=30, droop=0.20, cup=0.15,
                      ruffle=0.12, waves=5, shape="oval", colors=("#7a3b52", "#5f9440", "#3a6e2e")),
    "sweetbasil": dict(form="bush", stems=3, H=0.24, stem_tilt=10, nodes=4, L=0.07, w=0.60, tilt=28, droop=0.30, cup=0.45,
                       ruffle=0.02, waves=2, shape="oval", colors=("#5f8f3a", "#5fa03a", "#2f7a25")),
    "mint":      dict(form="bush", stems=4, H=0.15, stem_tilt=28, nodes=5, L=0.04, w=0.60, tilt=25, droop=0.15, cup=0.10,
                      ruffle=0.15, waves=6, shape="oval", colors=("#5f7f4a", "#6fae4c", "#3f8a35")),
    "kangkong":  dict(form="bush", stems=5, H=0.26, stem_tilt=14, nodes=4, L=0.09, w=0.32, tilt=35, droop=0.20, cup=0.05,
                      ruffle=0.02, waves=2, shape="spade", colors=("#b9d98f", "#6fae4c", "#3f8a2a")),
    "amaranth":  dict(form="bush", stems=2, H=0.20, stem_tilt=8, nodes=5, L=0.07, w=0.60, tilt=35, droop=0.25, cup=0.10,
                      ruffle=0.04, waves=2, shape="oval", colors=("#9cbf6a", "#6fa846", "#3f7a2a")),
    "watercress": dict(form="bush", stems=5, H=0.14, stem_tilt=55, nodes=4, L=0.03, w=0.85, tilt=20, droop=0.10, cup=0.10,
                       ruffle=0.02, waves=2, shape="round", colors=("#8fbf5a", "#5f9e33", "#2f6e25")),
    # ---- tubes
    "onion":     dict(form="tubes", tubes=6, H=0.30, r=0.0045, lean=10, colors=("#f4f6ec", "#f4f6ec", "#4f9a3a")),
}
# crop name in the planting log -> style (first match wins; Thai names as in the ข้อมูลพืช tab, English in brackets)
MATCH = [("เรดโอ๊ค", "redoak"), ("red oak", "redoak"), ("โอ๊ค", "oak"), ("oak", "oak"), ("เรดคอรัล", "redcoral"),
         ("คอสแดง", "redcos"), ("red romaine", "redcos"), ("มินิคอส", "minicos"), ("คอส", "cos"), ("romaine", "cos"),
         ("บัตเตอร์", "butter"), ("butter", "butter"), ("ปัตตาเวีย", "batavia"), ("batavia", "batavia"),
         ("ผักกาดแก้ว", "iceberg"), ("ฟิลเลย์", "frilly"), ("iceberg", "iceberg"),
         ("ร็อกเก็ต", "rocket"), ("arugula", "rocket"), ("rocket", "rocket"), ("มิซูน่า", "mizuna"), ("mizuna", "mizuna"),
         ("ฮ่องเต้", "bokchoy"), ("bok choy", "bokchoy"), ("ไดโตเกียว", "tokyo"), ("กวางตุ้งดอก", "choysum"), ("กวางตุ้ง", "bokchoy"),
         ("คะน้า", "kana"), ("เคล", "kale"), ("kale", "kale"), ("ปวยเล้ง", "spinach"), ("spinach", "spinach"),
         ("สวิสชาร์ด", "chard"), ("chard", "chard"), ("ขึ้นฉ่าย", "celery"), ("celery", "celery"), ("ผักชี", "coriander"),
         ("พาร์สลีย์", "parsley"), ("parsley", "parsley"), ("เบซิล", "sweetbasil"), ("basil", "sweetbasil"), ("โหระพา", "basil"),
         ("กะเพรา", "holybasil"), ("สะระแหน่", "mint"), ("mint", "mint"), ("ผักบุ้ง", "kangkong"), ("ผักโขม", "amaranth"),
         ("วอเตอร์เครส", "watercress"), ("watercress", "watercress"), ("ต้นหอม", "onion"), ("onion", "onion")]


def style_for(crop: str) -> dict:
    c = crop.lower()
    for key, name in MATCH:
        if key in crop or key in c:
            return STYLES[name]
    return STYLES["frilly"]   # any other leafy green


def colorscale(sty: dict) -> list:
    stem, base, tip, *flower = sty["colors"]
    return [[STEM, stem], [BASE, base], [TIP, tip], [FLOWER, flower[0] if flower else tip]]


# ---------------------------------------------------------------------------------------------------- primitives
_TEMPLATES: dict[tuple[int, int], tuple] = {}


def _template(ns: int, nt: int = 4):
    """Leaf grid: s along the midrib (0..1), t across (-1..1), and its triangles."""
    if (ns, nt) not in _TEMPLATES:
        s, t = np.meshgrid(np.linspace(0, 1, ns), np.linspace(-1, 1, nt), indexing="ij")
        idx = np.arange(ns * nt).reshape(ns, nt)
        a, b, c, d = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel()
        _TEMPLATES[(ns, nt)] = (s.ravel(), t.ravel(), np.concatenate([np.stack([a, b, c], 1), np.stack([b, d, c], 1)]))
    return _TEMPLATES[(ns, nt)]


def _outline(shape: str, b: np.ndarray) -> np.ndarray:
    """Blade half-width (0..1) along the blade (b = 0 base .. 1 tip)."""
    bb = np.clip(b, 0.02, 1)
    if shape == "lance":
        return np.sin(np.pi * bb) ** 0.7 * (1 - 0.3 * b)
    if shape == "spade":     # widest near the base (spinach, water spinach)
        return np.where(b < 0.3, (bb / 0.3) ** 0.5, np.cos((b - 0.3) / 0.7 * np.pi / 2) ** 0.8)
    if shape == "round":
        return np.sin(np.pi * bb) ** 0.35
    return np.sin(np.pi * bb) ** 0.55 * (1 - 0.15 * b)   # oval


def _leaf(o, ang, tilt, L, sty, k, small=False):
    """One leaf from point o towards `ang` (rad, horizontal), `tilt` (rad, up from horizontal) -> (V, F, intensity).
    small=True: a coarser grid for the many small leaves of a bush."""
    pf = sty.get("petiole", 0.0)
    s, t, tri = _template(4, 3) if small else _template(7 if pf else 5)
    b = np.clip((s - pf) / (1 - pf), 0, 1)                               # position on the blade
    W = L * sty["w"] * (1 - pf)
    prof = _outline(sty.get("shape", "oval"), b)
    if sty.get("lobes"):
        prof = prof * (1 - sty["lobe_depth"] * np.abs(np.sin(sty["lobes"] * np.pi * b)))
    width = np.where(s < pf, sty.get("petiole_w", 0.06) * L * sty["w"], W * prof)
    along = L * s * np.cos(tilt)
    up = L * s * np.sin(tilt) - sty["droop"] * L * b ** 2                # midrib arches and droops (blade only)
    across = t * width
    up = up + sty["cup"] * width * t ** 2 \
        + sty["ruffle"] * W * np.abs(t) ** 1.5 * np.sin(sty["waves"] * np.pi * b + k) * (s >= pf)   # cupped, frilled blade
    ca, sa = np.cos(ang), np.sin(ang)
    V = np.stack([o[0] + along * ca - across * sa, o[1] + along * sa + across * ca, o[2] + np.maximum(up, 0.0) + 0.003], 1)
    inten = np.where(s < pf, STEM, BASE + (TIP - BASE) * np.clip(b * 1.1, 0, 1) * (0.8 + 0.2 * (1 - np.abs(t))))
    return V, tri, inten


def _stalk(p0, p1, r, inten=STEM):
    """A thin stem as two crossed quads (cheap, reads as a stem from any angle)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    V = np.array([p0 + [-r, 0, 0], p0 + [r, 0, 0], p1 + [r, 0, 0], p1 + [-r, 0, 0],
                  p0 + [0, -r, 0], p0 + [0, r, 0], p1 + [0, r, 0], p1 + [0, -r, 0]])
    return V, np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]), np.full(8, inten)


def _cap(o, rad, h, inten=0.55, nu=8, nv=4):
    """A half-ellipsoid: the head of a heading lettuce, or a flower cluster."""
    u, v = np.meshgrid(np.linspace(0, 2 * np.pi, nu), np.linspace(0, np.pi / 2, nv))
    V = np.stack([o[0] + rad * (np.cos(u) * np.sin(v)).ravel(), o[1] + rad * (np.sin(u) * np.sin(v)).ravel(),
                  o[2] + h * np.cos(v).ravel()], 1)
    F = [(a * nu + b, a * nu + b + 1, (a + 1) * nu + b) for a in range(nv - 1) for b in range(nu - 1)] + \
        [(a * nu + b + 1, (a + 1) * nu + b + 1, (a + 1) * nu + b) for a in range(nv - 1) for b in range(nu - 1)]
    return V, np.array(F), np.full(len(V), inten)


def _tube(o, h, r, lean, ang, sides=5, rings=3):
    """Hollow leaf of a spring onion: a thin leaning cylinder, white at the base."""
    V, I, F = [], [], []
    for zi in np.linspace(0, 1, rings):
        off = np.sin(lean) * h * zi ** 1.3
        rr = r * (1 - 0.6 * zi ** 2)
        V += [(o[0] + off * np.cos(ang) + rr * np.cos(a), o[1] + off * np.sin(ang) + rr * np.sin(a), o[2] + h * zi)
              for a in np.linspace(0, 2 * np.pi, sides, endpoint=False)]
        I += [BASE + (TIP - BASE) * min(zi * 1.6, 1)] * sides
    for a in range(rings - 1):
        for b in range(sides):
            p, q = a * sides + b, a * sides + (b + 1) % sides
            F += [(p, q, p + sides), (q, q + sides, p + sides)]
    return np.array(V), np.array(F), np.array(I)


def plant_mesh(x, y, z, sty: dict, size: float, rng: np.random.Generator):
    """Vertices, triangles and colour intensities of one plant at (x, y, z) (tray surface); `size` 0..1 of harvest size."""
    parts = []
    form = sty.get("form", "rosette")
    rot0 = rng.uniform(0, 2 * np.pi)
    o = np.array([x, y, z])
    if form == "rosette":
        n = sty["n"]
        for k in range(n):
            inner = k % 2 == 1                                   # alternate outer / inner leaves
            L = sty["L"] * size * (0.75 if inner else 1.0) * rng.uniform(0.9, 1.1)
            tilt = np.radians(min(sty["tilt"] + (15 if inner else 0) + rng.uniform(-6, 6), 85))
            parts.append(_leaf(o, rot0 + 2 * np.pi * k / n + rng.uniform(-0.15, 0.15), tilt, L, sty, k))
        if sty["head"]:
            parts.append(_cap(o, sty["head"] * size * 1.1, sty["head"] * size * 1.3))
        for f in range(sty["flowers"]):                          # flower stalks with a yellow cluster on top
            a = rot0 + 2 * np.pi * f / sty["flowers"]
            top = o + [0.02 * np.cos(a) * size, 0.02 * np.sin(a) * size, sty["L"] * 1.25 * size]
            parts.append(_stalk(o, top, 0.0025))
            parts.append(_cap(top - [0, 0, 0.004], 0.012 * size, 0.012 * size, inten=FLOWER, nu=6, nv=3))
    elif form == "bush":
        H = sty["H"] * size
        for k in range(sty["stems"]):
            a = rot0 + 2 * np.pi * k / sty["stems"] + rng.uniform(-0.3, 0.3)
            lean = 0.0 if k == 0 and sty["stems"] > 2 else np.radians(sty["stem_tilt"] + rng.uniform(-5, 5))   # a central leader
            h = H * rng.uniform(0.8, 1.05) * (1.0 if k == 0 else 0.85)
            top = o + [np.sin(lean) * h * np.cos(a), np.sin(lean) * h * np.sin(a), np.cos(lean) * h]
            parts.append(_stalk(o, top, 0.002))
            for j in range(sty["nodes"]):                        # opposite pairs, each pair turned 90 deg
                f = (j + 1) / sty["nodes"]
                L = sty["L"] * size * (1.1 - 0.45 * f) * rng.uniform(0.9, 1.1)
                for side in (0.0, np.pi):
                    parts.append(_leaf(o + (top - o) * f, a + side + (np.pi / 2) * (j % 2), np.radians(sty["tilt"]), L, sty, j, small=True))
    else:                                                        # tubes
        for k in range(sty["tubes"]):
            parts.append(_tube(o, sty["H"] * size * rng.uniform(0.8, 1.05), sty["r"] * (0.6 + 0.4 * size),
                               np.radians(sty["lean"] + rng.uniform(-4, 8)), rot0 + 2 * np.pi * k / sty["tubes"]))
    V, F, I, n0 = [], [], [], 0
    for v, f, i in parts:
        V.append(v); F.append(f + n0); I.append(i); n0 += len(v)
    V = np.concatenate(V)
    return V[:, 0], V[:, 1], V[:, 2], np.concatenate(F), np.concatenate(I)


# ---------------------------------------------------------------------------------------------------- planting log -> meshes
def plant_table(rounds: pd.DataFrame, holes: pd.DataFrame, day=None, trays_per_tier: int = 10) -> pd.DataFrame:
    """One row per occupied hole on `day`: position, crop, round, growth fraction (days on tier / planned days)."""
    day = pd.Timestamp(day if day is not None else pd.Timestamp.now(tz="Asia/Bangkok").date()).normalize()
    cols = holes["col"].max() + 1
    holes = holes.assign(tray=holes["col"] // (cols // trays_per_tier) + 1)      # tray 1 = door end (x0)
    on = rounds[(rounds["on_tray"] <= day) & (rounds["off_tray"] > day) & rounds["harvest_actual"].isna()]
    out = []
    for b in on.itertuples():
        h = holes[(holes["tier"] == b.tier) & holes["tray"].between(b.tray_from, b.tray_to)]
        span = max((b.off_tray - b.on_tray).days, 1)
        grow = float(np.clip((day - b.on_tray).days / span, 0.0, 1.0))
        left = (b.harvest_plan - day).days if pd.notna(b.harvest_plan) else None
        out.append(h.assign(crop=b.crop, round=b.round, grow=grow, days_left=left,
                            harvest=b.harvest_plan.strftime("%d %b %Y") if pd.notna(b.harvest_plan) else "?"))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=list(holes.columns) + ["crop", "round", "grow", "days_left", "harvest"])


MAX_VERTICES = 120_000   # ~5 MB in the browser; above it plants get fewer leaves (e.g. every hole planted with a herb)


def _lighter(sty: dict, f: float) -> dict:
    """Same plant with about f x the leaves."""
    if sty.get("form") == "bush":
        return {**sty, "stems": max(2, round(sty["stems"] * f ** 0.5)), "nodes": max(2, round(sty["nodes"] * f ** 0.5))}
    if sty.get("form", "rosette") == "rosette":
        return {**sty, "n": max(4, round(sty["n"] * f))}
    return {**sty, "tubes": max(3, round(sty["tubes"] * f))}


def plant_traces(plants: pd.DataFrame, seed: int = 7) -> list:
    """One Mesh3d per crop (so the legend lists crops); plants seeded by position so they look the same on every redraw."""
    traces = []
    rng0 = np.random.default_rng(0)
    per_plant = {c: len(plant_mesh(0, 0, 0, style_for(c), 1.0, rng0)[0]) for c in plants["crop"].unique()}
    total = sum(per_plant[c] for c in plants["crop"])
    detail = min(1.0, MAX_VERTICES / total) if total else 1.0
    for crop, g in plants.groupby("crop", sort=True):
        sty = style_for(crop) if detail >= 1 else _lighter(style_for(crop), detail)
        X, Y, Z, F, C, n = [], [], [], [], [], 0
        for r in g.itertuples():
            rng = np.random.default_rng(int(r.x * 1000) * 7919 + int(r.y * 1000) * 104729 + int(r.tier) + seed)
            size = 0.3 + 0.7 * r.grow                        # a transplanted seedling is already ~1/3 of harvest size
            vx, vy, vz, f, c = plant_mesh(r.x, r.y, r.z, sty, size, rng)
            X.append(vx); Y.append(vy); Z.append(vz); F.append(f + n); C.append(c); n += len(vx)
        F = np.concatenate(F)
        f32 = lambda a: np.concatenate(a).astype(np.float32)    # float32 halves what the browser downloads
        hover = (f"<b>{crop}</b> · {len(g)} ต้น<br>รอบ {', '.join(dict.fromkeys(g['round']))}<br>"
                 f"ชั้น {', '.join(str(t) for t in sorted(g['tier'].unique()))}<br>เก็บ (คาด) {', '.join(dict.fromkeys(g['harvest']))}")
        traces.append(go.Mesh3d(x=f32(X), y=f32(Y), z=f32(Z), i=F[:, 0], j=F[:, 1], k=F[:, 2],
                                intensity=f32(C), cmin=0, cmax=1, colorscale=colorscale(sty), showscale=False,
                                name=f"{crop} ({len(g)})", showlegend=True, hovertext=hover, hoverinfo="text",
                                flatshading=False, lighting=dict(ambient=0.45, diffuse=0.85, specular=0.15, roughness=0.8),
                                lightposition=dict(x=0, y=0, z=1e5)))
    return traces
