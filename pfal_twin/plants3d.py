"""Plants on the growing tiers as 3-D meshes: one rosette of curved leaves per hole, shaped by crop type and scaled by
how far the block is through its time on the tier (from the planting log, see planting.py).

Illustrative, not measured: leaf size follows days on the tier / planned days, not a canopy measurement.

    traces = plant_traces(plant_table(rounds, holes))     # -> list of go.Mesh3d, one per crop (legend entry)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# leaf shape per crop type (lengths in m at harvest size):
#   n leaves, length, width/length, tilt from horizontal (deg), droop, cup across the blade, ruffle amplitude & waves,
#   base colour -> tip colour
STYLES = {
    "oak":    dict(n=8, L=0.14, w=0.42, tilt=38, droop=0.35, cup=0.10, ruffle=0.20, waves=5, base="#b9d77a", tip="#5d9b35"),
    "redoak": dict(n=8, L=0.13, w=0.42, tilt=38, droop=0.35, cup=0.10, ruffle=0.20, waves=5, base="#a7c46a", tip="#7a2533"),
    "cos":    dict(n=7, L=0.17, w=0.34, tilt=68, droop=0.10, cup=0.30, ruffle=0.03, waves=2, base="#cfe39a", tip="#4f8f2f"),
    "butter": dict(n=9, L=0.12, w=0.85, tilt=45, droop=0.15, cup=0.45, ruffle=0.04, waves=2, base="#e2eeb0", tip="#86b94a"),
    "frilly": dict(n=9, L=0.14, w=0.70, tilt=42, droop=0.30, cup=0.15, ruffle=0.30, waves=7, base="#d5e8a0", tip="#77b23c"),
    "kale":   dict(n=6, L=0.18, w=0.45, tilt=55, droop=0.30, cup=0.05, ruffle=0.35, waves=8, base="#7fa889", tip="#2f5a45"),
}
NS, NT = 5, 4          # vertices along / across a leaf: 20 per leaf, ~160 per plant (keeps the page light)


def style_for(crop: str) -> dict:
    c = crop.lower()
    if "เรดโอ๊ค" in crop or "red oak" in c or "เรดคอรัล" in crop:
        return STYLES["redoak"]
    if "โอ๊ค" in crop or "oak" in c:
        return STYLES["oak"]
    if "คอส" in crop or "cos" in c or "romaine" in c:
        return STYLES["cos"]
    if "บัตเตอร์" in crop or "butter" in c:
        return STYLES["butter"]
    if "เคล" in crop or "kale" in c:
        return STYLES["kale"]
    return STYLES["frilly"]   # iceberg / batavia / other leafy greens


def _leaf_template():
    """Unit leaf in its own frame: x along the midrib (0..1), y across (-1..1). Returns s, t grids and the triangles."""
    s, t = np.meshgrid(np.linspace(0, 1, NS), np.linspace(-1, 1, NT), indexing="ij")
    idx = np.arange(NS * NT).reshape(NS, NT)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel()
    tri = np.concatenate([np.stack([a, b, c], 1), np.stack([b, d, c], 1)])
    return s.ravel(), t.ravel(), tri


_S, _T, _TRI = _leaf_template()


def plant_mesh(x, y, z, sty: dict, size: float, rng: np.random.Generator):
    """Vertices, triangles and per-vertex colours of one plant at (x, y, z) (tray surface), `size` 0..1 of harvest size."""
    V, F, C = [], [], []
    rot0 = rng.uniform(0, 2 * np.pi)
    for k in range(sty["n"]):
        inner = k % 2 == 1                                   # alternate outer / inner leaves: inner ones shorter, more upright
        L = sty["L"] * size * (0.75 if inner else 1.0) * rng.uniform(0.9, 1.1)
        W = L * sty["w"]
        tilt = np.radians(sty["tilt"] + (18 if inner else 0) + rng.uniform(-6, 6))
        ang = rot0 + 2 * np.pi * k / sty["n"] + rng.uniform(-0.15, 0.15)
        s, t = _S, _T
        width = W * np.sin(np.pi * np.clip(s, 0.02, 1)) ** 0.7 * (1 - 0.25 * s)   # narrow at base and tip
        along = L * s * np.cos(tilt)
        up = L * s * np.sin(tilt) - sty["droop"] * L * s ** 2                      # midrib arches and droops
        across = t * width
        up = up + sty["cup"] * width * t ** 2                                    # blade cups upward at the edges
        up = up + sty["ruffle"] * W * np.abs(t) ** 1.5 * np.sin(sty["waves"] * np.pi * s + k)   # frilled margin
        ca, sa = np.cos(ang), np.sin(ang)
        vx = x + along * ca - across * sa
        vy = y + along * sa + across * ca
        vz = z + 0.004 + np.maximum(up, 0.0)
        n0 = sum(len(v[0]) for v in V)
        V.append((vx, vy, vz)); F.append(_TRI + n0)
        C.append(np.clip(s * 1.1, 0, 1) * (0.8 + 0.2 * (1 - np.abs(t))))      # 0 = pale base, 1 = crop colour at the tip
    vx, vy, vz = (np.concatenate([v[i] for v in V]) for i in range(3))
    return vx, vy, vz, np.concatenate(F), np.concatenate(C)


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


def plant_traces(plants: pd.DataFrame, seed: int = 7) -> list:
    """One Mesh3d per crop (so the legend lists crops); plants seeded by position so they look the same on every redraw."""
    traces = []
    for crop, g in plants.groupby("crop", sort=True):
        sty = style_for(crop)
        X, Y, Z, F, C, n = [], [], [], [], [], 0
        for r in g.itertuples():
            rng = np.random.default_rng(int(r.x * 1000) * 7919 + int(r.y * 1000) * 104729 + int(r.tier) + seed)
            size = 0.3 + 0.7 * r.grow                        # a transplanted seedling is already ~1/3 of harvest size
            vx, vy, vz, f, c = plant_mesh(r.x, r.y, r.z, sty, size, rng)
            X.append(vx); Y.append(vy); Z.append(vz); F.append(f + n); C.append(c); n += len(vx)
        F = np.concatenate(F); C = np.concatenate(C)
        hover = (f"<b>{crop}</b> · {len(g)} ต้น<br>รอบ {', '.join(dict.fromkeys(g['round']))}<br>"
                 f"ชั้น {', '.join(str(t) for t in sorted(g['tier'].unique()))}<br>เก็บ (คาด) {', '.join(dict.fromkeys(g['harvest']))}")
        f32 = lambda a: np.concatenate(a).astype(np.float32)    # float32 halves what the browser downloads
        traces.append(go.Mesh3d(x=f32(X), y=f32(Y), z=f32(Z), i=F[:, 0], j=F[:, 1], k=F[:, 2],
                                intensity=C.astype(np.float32), cmin=0, cmax=1, colorscale=[[0, sty["base"]], [1, sty["tip"]]], showscale=False,
                                name=f"{crop} ({len(g)})", showlegend=True, hovertext=hover, hoverinfo="text",
                                flatshading=False, lighting=dict(ambient=0.45, diffuse=0.85, specular=0.15, roughness=0.8),
                                lightposition=dict(x=0, y=0, z=1e5)))
    return traces
