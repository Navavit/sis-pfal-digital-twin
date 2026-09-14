"""Plotting helpers (matplotlib for static figures, plotly for interactive 3D)."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go

plt.rcParams.update({"font.family": ["Helvetica", "Arial", "DejaVu Sans"], "font.size": 10})


def subsample(n_total, n_keep, seed=0):
    if n_total <= n_keep:
        return np.arange(n_total)
    return np.random.default_rng(seed).choice(n_total, n_keep, replace=False)


# --------------------------------------------------------------------------- matplotlib

def plan_view(xyz, rgb, ax=None, n=300000, s=0.2, title=None, xy=(0, 1), equal=True):
    """Scatter of two axes coloured by RGB (default XY plan view)."""
    idx = subsample(len(xyz), n)
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(xyz[idx, xy[0]], xyz[idx, xy[1]], s=s, c=rgb[idx] / 255.0, linewidths=0)
    if equal:
        ax.set_aspect("equal")
    if title:
        ax.set_title(title)
    return ax


def height_histogram(hist_tuple, levels, ax=None, title="Horizontal-surface height histogram"):
    edges, hist = hist_tuple
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 4))
    ax.bar(edges[:-1], hist, width=np.diff(edges), align="edge", color="#8aa")
    for l in levels:
        ax.axvline(l, color="#c33", lw=1)
        ax.text(l, hist.max() * 0.95, f"{l:.2f}", rotation=90, va="top", ha="right", fontsize=8, color="#c33")
    ax.set_xlabel("height above floor (m)"); ax.set_ylabel("points"); ax.set_title(title)
    return ax


# --------------------------------------------------------------------------- plotly

def points_trace(xyz, rgb=None, n=200000, size=1.2, name="point cloud", color=None, opacity=1.0):
    idx = subsample(len(xyz), n)
    p = xyz[idx]
    if color is None:
        c = ["rgb(%d,%d,%d)" % tuple(v) for v in rgb[idx]] if rgb is not None else "#888"
    else:
        c = color
    return go.Scatter3d(x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="markers", name=name,
                        marker=dict(size=size, color=c, opacity=opacity), hoverinfo="skip")


def box_mesh(x0, x1, y0, y1, z0, z1, color="#2a7d2a", opacity=0.25, name="box"):
    xs = [x0, x1, x1, x0, x0, x1, x1, x0]
    ys = [y0, y0, y1, y1, y0, y0, y1, y1]
    zs = [z0, z0, z0, z0, z1, z1, z1, z1]
    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4]
    k = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7]
    return go.Mesh3d(x=xs, y=ys, z=zs, i=i, j=j, k=k, color=color, opacity=opacity, name=name, showlegend=True, flatshading=True)


def box_wire(x0, x1, y0, y1, z0, z1, color="#333", width=3, name="room"):
    c = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    xs, ys, zs = [], [], []
    for a, b in edges:
        xs += [c[a, 0], c[b, 0], None]; ys += [c[a, 1], c[b, 1], None]; zs += [c[a, 2], c[b, 2], None]
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=color, width=width), name=name)


def model_traces(model, tier_thickness=0.03, tier_color="#2a7d2a", frame_color="#555", group_legend=False):
    """Room wireframe + one slab per rack tier + rack frame posts. group_legend=True -> the tiers share one legend entry."""
    R, K = model["room"], model["rack"]
    tr = [box_wire(0, R["L"], 0, R["W"], 0, R["H"], name=f"room {R['L']:.2f}×{R['W']:.2f}×{R['H']:.2f} m")]
    for t in K["tiers"]:
        tr.append(box_mesh(K["x0"], K["x1"], K["y0"], K["y1"], t["z"] - tier_thickness, t["z"],
                           color=tier_color, opacity=0.35, name=f"tier {t['index']} {'growing' if t['index'] >= 2 else 'nursery'} (z={t['z']:.2f} m)"))
        if group_legend:
            tr[-1].update(legendgroup="tiers", name=f"rack tiers 1-{len(K['tiers'])}", showlegend=t["index"] == 1)
    top = K.get("top_frame_z", R["H"])
    tr.append(box_wire(K["x0"], K["x1"], K["y0"], K["y1"], 0, top, color=frame_color, width=2, name="rack frame"))
    return tr


def figure_3d(traces, title=None, height=800, compact=False):
    """compact=True: small horizontal legend under the scene (for the web app) instead of the tall list on the right."""
    fig = go.Figure(data=traces)
    fig.update_layout(title=title, height=height, margin=dict(l=0, r=0, t=40, b=0),
                      scene=dict(aspectmode="data", xaxis_title="X (m)", yaxis_title="Y (m)", zaxis_title="Z (m)"),
                      legend=dict(itemsizing="constant"))
    if compact:
        fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.01, xanchor="left", x=0, font=dict(size=10), itemwidth=30),
                          title=dict(font=dict(size=13), y=0.98, yanchor="top"), margin=dict(l=0, r=0, t=55, b=45))
    return fig


# --------------------------------------------------------------------------- layout (zones / equipment / sensors)

EQUIP_COLORS = {"hvac": "#4c8ed9", "nutrient": "#2ca9a1", "electrical": "#e08b2c", "structure": "#999999",
                "furniture": "#b58b5a", "co2": "#6a51a3", "water": "#3182bd", "unknown": "#c05fb0"}


def zone_traces(zones, values=None, cmin=None, cmax=None, colorscale="RdYlBu_r", opacity=0.45, unit=""):
    """One translucent box per zone. `values` = {zone_name: value} colours the boxes; missing -> grey."""
    tr = []
    if values:
        vals = [v for v in values.values() if v is not None and not np.isnan(v)]
        cmin = min(vals) if cmin is None and vals else cmin
        cmax = max(vals) if cmax is None and vals else cmax
    for q in zones:
        v = values.get(q["zone"]) if values else None
        if v is None or (isinstance(v, float) and np.isnan(v)):
            col, label = "#bbbbbb", f"{q['zone']}: no data"
        else:
            col = _sample_colorscale(colorscale, (v - cmin) / max(cmax - cmin, 1e-9))
            label = f"{q['zone']}: {v:.1f}{unit}"
        m = box_mesh(q["x0"], q["x1"], q["y0"], q["y1"], q["z0"], q["z1"], color=col, opacity=opacity, name=label)
        m.update(hovertext=label, hoverinfo="text", showlegend=False)
        tr.append(m)
    return tr


EQUIP_GROUP_LABEL = {"hvac": "HVAC / fans", "nutrient": "nutrient system", "electrical": "electrical / control boxes", "structure": "structure",
                     "furniture": "furniture", "co2": "CO2 system", "water": "water / tanks", "unknown": "other"}


def equipment_traces(eq, opacity=0.5, group_legend=False):
    """One box per equipment item. group_legend=True -> one legend entry per category (item names stay in the hover text)."""
    tr, seen = [], set()
    for _, r in eq.iterrows():
        m = box_mesh(r.x0, r.x1, r.y0, r.y1, r.z0, r.z1, color=EQUIP_COLORS.get(r.category, "#888"), opacity=opacity,
                     name=f"{r['name']} [{r.confidence}]")
        m.update(hovertext=f"{r['name']}<br>{r.category} — confidence {r.confidence}<br>{r.evidence}", hoverinfo="text")
        if group_legend:
            m.update(legendgroup=r.category, name=EQUIP_GROUP_LABEL.get(r.category, r.category), showlegend=r.category not in seen)
            seen.add(r.category)
        tr.append(m)
    return tr


def sensor_trace(sensors, text=None, size=7, color="#d62728", name="sensors", labels=True):
    """labels=False -> markers only (names in the hover text) so co-located boxes do not print on top of each other."""
    txt = text if text is not None else sensors["sensor"].tolist()
    return go.Scatter3d(x=sensors.x, y=sensors.y, z=sensors.z, mode="markers+text" if labels else "markers", text=sensors["sensor"], textposition="top center",
                        hovertext=txt, hoverinfo="text", name=name,
                        marker=dict(size=size, color=color, symbol="diamond", line=dict(color="black", width=1)))


def _stack_labels(ax, pts, labels, color, fontsize=7, dx=5, dy=5, line=9):
    """Annotate points; items sharing (x, y) are stacked vertically so text never overlaps."""
    groups = {}
    for (x, y), lab in zip(pts, labels):
        groups.setdefault((round(x, 2), round(y, 2)), []).append(lab)
    for (x, y), labs in groups.items():
        for i, lab in enumerate(labs):
            ax.annotate(lab, (x, y), xytext=(dx, dy + i * line), textcoords="offset points", fontsize=fontsize, color=color,
                        bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none", alpha=0.75), zorder=8)


def draw_pipes_2d(ax, net, axes=(0, 1), lw_scale=0.3, alpha=0.9, kinds=None, fittings=True, fitting_size=22):
    """Polyline pipe network projected on two axes (0=X, 1=Y, 2=Z); one legend handle per kind."""
    from matplotlib.lines import Line2D
    from .hydraulics import KIND_STYLE, DASH_MPL
    i, j = axes; seen = {}
    for e in net["edges"]:
        if kinds and e["kind"] not in kinds:
            continue
        q = np.asarray(e["pts"]); st = KIND_STYLE[e["kind"]]; ls = DASH_MPL.get(st.get("dash", "solid"), "-")
        ax.plot(q[:, i], q[:, j], color=st["color"], lw=st["width"] * lw_scale, ls=ls, alpha=alpha, solid_capstyle="round", zorder=3)
        seen[e["kind"]] = Line2D([0], [0], color=st["color"], lw=3, ls=ls, label=st["name"])
    if fittings:
        from .hydraulics import FITTING_STYLE
        for f in net.get("fittings", []):
            st = FITTING_STYLE[f["type"]]
            ax.scatter([f["xyz"][i]], [f["xyz"][j]], marker=st["mpl"], s=fitting_size, c=st["color"], ec="black", lw=0.5, zorder=6)
            seen.setdefault("fit_" + f["type"], Line2D([0], [0], marker=st["mpl"], ls="", color=st["color"], mec="black", label=st["name"]))
    return list(seen.values())


PIPE_PLAN_LABELS = {   # kind -> (text, label x, label y, x on the pipe to point at)
    "manifold": ("drain / overflow manifold between tanks (blue 1.5\")", 3.4, 2.75, 3.4),
    "supply":   ("growing supply: 200 L tank pump -> door end (white 1\", 0.3 m up)", 3.2, 2.58, 3.2),
    "fill_ro":  ("RO water (white PVC)",         4.8, 2.44, 4.8),
    "fill_tap": ("tap water (white PVC)",        1.7, 2.40, 1.7),
    "drain":    ("waste drain to outside",       6.55, 2.72, 6.6),
}


def label_pipes_plan(ax, net, labels=PIPE_PLAN_LABELS, fontsize=7.5):
    """Text labels with leader lines on the long floor runs so the white tap / RO lines and the
    blue nutrient main can be told apart directly on the drawing."""
    for kind, (text, lx, ly, px) in labels.items():
        best = None
        for e in net["edges"]:
            if e["kind"] != kind:
                continue
            q = np.asarray(e["pts"]); L = np.abs(q[-1, 0] - q[0, 0])
            if best is None or L > best[0]:
                best = (L, q)
        if best is None:
            continue
        q = best[1]
        # y of the pipe at x = px (interpolate along the polyline's x)
        xs, ys = q[:, 0], q[:, 1]
        order = np.argsort(xs); py = float(np.interp(px, xs[order], ys[order]))
        from .hydraulics import KIND_STYLE
        ax.annotate(text, (px, py), xytext=(lx, ly), fontsize=fontsize, color=KIND_STYLE[kind]["color"], ha="center",
                    arrowprops=dict(arrowstyle="-", color=KIND_STYLE[kind]["color"], lw=0.8, shrinkA=0, shrinkB=2), zorder=7)


def pipe_corner_detail(model, net, eq=None, xr=(5.7, 7.2), yr=(0.7, 2.9), zr=(-0.1, 2.5), figsize=(17, 8)):
    """Zoomed plan + elevation of the far-end tank corner with every pipe and fitting labelled."""
    from .hydraulics import FITTING_STYLE
    R, K = model["room"], model["rack"]
    xr = (xr[0], max(xr[1], R["L"] + 0.45))          # show the drain leaving through the wall
    fig, axes = plt.subplots(1, 2, figsize=figsize, gridspec_kw=dict(width_ratios=[1, 1]))
    for ax, (i, j, lab, lim) in zip(axes, [(0, 1, "Y (m)", yr), (0, 2, "Z (m)", zr)]):
        if eq is not None:
            for _, r in eq.iterrows():
                lo, hi = (r.y0, r.y1) if j == 1 else (r.z0, r.z1)
                if r.x1 < xr[0] or r.x0 > xr[1]:
                    continue
                ax.add_patch(plt.Rectangle((r.x0, lo), r.x1 - r.x0, hi - lo, fc=EQUIP_COLORS.get(r.category, "#888"), alpha=0.15, ec="#888", lw=0.6))
                if r["name"].startswith("Tank"):
                    ax.annotate("TANK", (r.x1 - 0.04, lo + 0.04), fontsize=9, color="#1a7a74", ha="right", va="bottom", alpha=0.8)
        handles = draw_pipes_2d(ax, net, axes=(i, j), lw_scale=0.6, fittings=True, fitting_size=55)
        # label fittings, stacked where they coincide
        pts, labs = [], []
        for f in net.get("fittings", []):
            x, y = f["xyz"][i], f["xyz"][j]
            if xr[0] <= x <= xr[1] and lim[0] <= y <= lim[1]:
                pts.append((x, y)); labs.append(f["name"])
        _stack_labels_near(ax, pts, labs, "#222", fontsize=6.5, tol=(0.35, 0.12))
        if j == 1:
            ax.add_patch(plt.Rectangle((0, 0), R["L"], R["W"], fill=False, lw=2, ec="black"))
            ax.add_patch(plt.Rectangle((K["x0"], K["y0"]), K["length"], K["width"], fill=False, ec="#2a7d2a", ls="--"))
        else:
            ax.axhline(0, color="black", lw=2); ax.axvline(R["L"], color="black", lw=2)
            for t in K["tiers"]:
                ax.plot([K["x0"], K["x1"]], [t["z"], t["z"]], color="#2a7d2a", lw=1.5)
        ax.set_xlim(*xr); ax.set_ylim(*lim); ax.set_aspect("equal"); ax.set_xlabel("X (m)"); ax.set_ylabel(lab); ax.grid(alpha=.25)
    axes[0].set_title("Far-end tank corner — plan view"); axes[1].set_title("Far-end tank corner — elevation (X–Z)")
    axes[0].legend(handles=handles, fontsize=7, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=3, frameon=False)
    return fig


def _stack_labels_near(ax, pts, labels, color, fontsize=7, tol=(0.3, 0.1), dx=6, dy=4, line=8):
    """Like _stack_labels but groups points that are merely *close* (within tol in data units)."""
    groups = []            # [anchor(x, y), [labels]]
    for (x, y), lab in zip(pts, labels):
        for g in groups:
            if abs(g[0][0] - x) <= tol[0] and abs(g[0][1] - y) <= tol[1]:
                g[1].append(lab); break
        else:
            groups.append([(x, y), [lab]])
    for (x, y), labs in groups:
        for i, lab in enumerate(labs):
            ax.annotate(lab, (x, y), xytext=(dx, dy + i * line), textcoords="offset points", fontsize=fontsize, color=color,
                        bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none", alpha=0.75), zorder=8)


def layout_key(eq, sensors=None):
    """Numbered key used by plan_layout / elevation_layout: equipment -> 1..N, sensors -> a, b, c ..."""
    eq_key = {r["name"]: str(i + 1) for i, r in eq.reset_index(drop=True).iterrows()}
    s_key = {} if sensors is None else {r["sensor"]: chr(ord("a") + i) for i, r in sensors.reset_index(drop=True).iterrows()}
    return eq_key, s_key


def plan_layout(model, zones=None, eq=None, sensors=None, ax=None, title="Room layout — plan view (room frame)", key_ax=None, net=None):
    """Matplotlib plan view of the parametric model with zones, equipment and sensors.
    Equipment boxes carry numbers and sensors letters; the key is printed in `key_ax`
    (or to the right of `ax`) so labels never overlap on the drawing."""
    import matplotlib.patches as mp
    R, K = model["room"], model["rack"]
    if ax is None:
        _, ax = plt.subplots(figsize=(14, 6.5))
    ax.add_patch(mp.Rectangle((0, 0), R["L"], R["W"], fill=False, lw=2, ec="black"))
    ax.add_patch(mp.Rectangle((K["x0"], K["y0"]), K["length"], K["width"], fc="#d9f0d3", ec="#2a7d2a", lw=1.5, label="rack (5 tiers)"))
    if zones:
        for q in [z for z in zones if z["tier"] == 1]:
            if q["segment"] < q.get("n_segments", 3):
                ax.plot([q["x1"], q["x1"]], [q["y0"], q["y1"]], color="#2a7d2a", lw=0.8, ls="--")
            ax.text(0.5 * (q["x0"] + q["x1"]), q["y0"] + 0.06, q["zone"], ha="center", fontsize=7, color="#2a7d2a")
    eq_key, s_key = layout_key(eq, sensors) if eq is not None else ({}, {})
    if eq is not None:
        seen = set()
        for _, r in eq.iterrows():
            lab = r.category if r.category not in seen else None; seen.add(r.category)
            if r.get("location", "inside") == "anteroom":
                continue                                    # drawn as the hatched strip above
            ax.add_patch(mp.Rectangle((r.x0, r.y0), r.x1 - r.x0, r.y1 - r.y0, fc=EQUIP_COLORS.get(r.category, "#888"),
                                      ec="black", lw=0.5, alpha=0.55, label=lab))
            ax.annotate(eq_key[r["name"]], (0.5 * (r.x0 + r.x1), 0.5 * (r.y0 + r.y1)), fontsize=7.5, ha="center", va="center",
                        fontweight="bold", bbox=dict(boxstyle="circle,pad=0.15", fc="white", ec="none", alpha=0.85))
    pipe_handles = draw_pipes_2d(ax, net, axes=(0, 1)) if net is not None else []
    if net is not None:
        label_pipes_plan(ax, net)
    if sensors is not None:
        ax.scatter(sensors.x, sensors.y, marker="D", s=36, c="#d62728", ec="black", zorder=5, label="sensor / IoT box")
        _stack_labels(ax, sensors[["x", "y"]].values, [s_key[s] for s in sensors.sensor], "#d62728", fontsize=8)
    ext = eq[eq.location != "inside"] if (eq is not None and "location" in eq) else None
    x_lo = (float(ext.x0.min()) - 0.3) if ext is not None and len(ext) else -0.2
    far = ext[ext.location == "outside_far"] if ext is not None else None
    x_hi = (float(far.x1.max()) + 0.3) if far is not None and len(far) else R["L"] + 0.2
    if far is not None and len(far):
        ax.add_patch(mp.Rectangle((R["L"] + 0.05, -0.1), x_hi - R["L"] - 0.08, R["W"] + 0.2, fill=True, fc="#efefef", ec="#bbbbbb", ls=":", lw=1))
        ax.text(0.5 * (R["L"] + x_hi), R["W"] + 0.05, "OUTSIDE (service side)\nRO plant / drain — schematic", ha="center", va="top", fontsize=7, color="#555")
    if ext is not None and len(ext):
        ante = ext[ext.location == "anteroom"]
        if len(ante):
            a = ante.iloc[0]
            ax.add_patch(mp.Rectangle((a.x0, 0), a.x1 - a.x0, R["W"], fill=True, fc="#f7f7f7", ec="#888888", ls="--", lw=1.2, hatch="//", alpha=0.6))
            ax.text(0.5 * (a.x0 + a.x1), R["W"] * 0.5, f"ANTEROOM\n(sink)\nnot scanned\n~{a.x1 - a.x0:.2f} m", ha="center", va="center", fontsize=7.5, color="#444")
            porch_x1 = a.x0
        else:
            porch_x1 = -0.05
        ax.add_patch(mp.Rectangle((x_lo + 0.03, -0.1), porch_x1 - 0.03 - (x_lo + 0.03), R["W"] + 0.2, fill=True, fc="#efefef", ec="#bbbbbb", ls=":", lw=1))
        ax.text(0.5 * (x_lo + porch_x1), R["W"] + 0.05, "OUTSIDE\n(porch)", ha="center", va="top", fontsize=7.5, color="#555")
    ax.set_xlim(x_lo, x_hi); ax.set_ylim(-0.2, R["W"] + 0.2); ax.set_aspect("equal")
    ax.set_xlabel("X — room length (m)"); ax.set_ylabel("Y — room width (m)"); ax.set_title(title)
    if key_ax is not None:
        write_key(key_ax, eq, sensors, eq_key, s_key)
        h, l = ax.get_legend_handles_labels()
        key_ax.legend(h + pipe_handles, l + [ph.get_label() for ph in pipe_handles], fontsize=7.5, loc="lower left", ncol=2, frameon=False, title="categories / pipes", title_fontsize=8)
    else:
        ax.legend(fontsize=7.5, loc="upper left", bbox_to_anchor=(1.01, 1))
    return ax


def write_key(ax, eq, sensors, eq_key, s_key, fontsize=7.5):
    """Print the numbered equipment / lettered sensor key into an axis."""
    ax.axis("off")
    lines = ["EQUIPMENT"] + [f"{eq_key[r['name']]:>2}  {r['name']}" + ("" if r.verified else "  (unverified)") for _, r in eq.iterrows()]
    if sensors is not None:
        lines += ["", "SENSORS / IoT"] + [f"{s_key[r.sensor]:>2}  {r.sensor}" + (f"  — {r.placed_on}" if isinstance(r.placed_on, str) and r.placed_on else "")
                                          for _, r in sensors.iterrows()]
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=fontsize, family="monospace", transform=ax.transAxes)


def elevation_layout(model, P=None, RGB=None, eq=None, sensors=None, ax=None, n=120000,
                     title="Side elevation (X–Z): tiers, equipment envelopes, sensor heights", net=None):
    """X–Z elevation with the point-cloud silhouette, tier plates, equipment boxes (numbered) and sensors (lettered)."""
    R, K = model["room"], model["rack"]
    if ax is None:
        _, ax = plt.subplots(figsize=(14, 5.5))
    if P is not None:
        idx = subsample(len(P), n)
        ax.scatter(P[idx, 0], P[idx, 2], s=0.15, c=RGB[idx] / 255.0 if RGB is not None else "#bbb", linewidths=0)
    for t in K["tiers"]:
        ax.plot([K["x0"], K["x1"]], [t["z"], t["z"]], color="#2a7d2a", lw=2)
        xl = K["x0"] + 0.27 * K["length"]          # mid-left of the rack: clear of the wall sensors (X~3.9) and the far-end boxes
        if t["index"] >= 2:
            ax.text(xl, t["z"] + 0.03, f"tier {t['index']} (growing)  z = {t['z']:.2f} m", va="bottom", fontsize=7.5, color="#2a7d2a",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
        else:
            ax.text(xl, t["z"] - 0.03, f"tier 1 (nursery 1 | nursery 2)  z = {t['z']:.2f} m", va="top", fontsize=7.5, color="#2a7d2a",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
    eq_key, s_key = layout_key(eq, sensors) if eq is not None else ({}, {})
    if eq is not None:
        for _, r in eq.iterrows():
            if r.get("location", "inside") == "anteroom":
                continue
            ax.add_patch(plt.Rectangle((r.x0, r.z0), r.x1 - r.x0, r.z1 - r.z0, fill=False, ec=EQUIP_COLORS.get(r.category, "#888"), lw=1.2))
            ax.annotate(eq_key[r["name"]], (r.x0, r.z1), xytext=(2, -8), textcoords="offset points", fontsize=7, fontweight="bold",
                        color=EQUIP_COLORS.get(r.category, "#888"), bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.7))
    if net is not None:
        draw_pipes_2d(ax, net, axes=(0, 2), alpha=0.8)
    if sensors is not None:
        ax.scatter(sensors.x, sensors.z, marker="D", s=36, c="#d62728", ec="black", zorder=5)
        _stack_labels(ax, sensors[["x", "z"]].values, [s_key[s] for s in sensors.sensor], "#d62728", fontsize=8)
    ext = eq[eq.location != "inside"] if (eq is not None and "location" in eq) else None
    x_lo = (float(ext.x0.min()) - 0.3) if ext is not None and len(ext) else -0.2
    far = ext[ext.location == "outside_far"] if ext is not None else None
    x_hi = (float(far.x1.max()) + 0.3) if far is not None and len(far) else R["L"] + 0.2
    if far is not None and len(far):
        ax.axvspan(R["L"] + 0.05, x_hi, color="#efefef", zorder=0); ax.text(0.5 * (R["L"] + x_hi), R["H"] + 0.02, "OUTSIDE (service side)", ha="center", va="bottom", fontsize=7.5, color="#555")
    if ext is not None and len(ext):
        ante = ext[ext.location == "anteroom"]
        if len(ante):
            a = ante.iloc[0]
            ax.axvspan(a.x0, a.x1, color="#f7f7f7", zorder=0, hatch="//", ec="#bbbbbb")
            ax.text(0.5 * (a.x0 + a.x1), R["H"] + 0.02, "ANTEROOM (not scanned)", ha="center", va="bottom", fontsize=7.5, color="#444")
            porch_x1 = a.x0
        else:
            porch_x1 = -0.05
        ax.axvspan(x_lo + 0.03, porch_x1, color="#efefef", zorder=0); ax.text(0.5 * (x_lo + porch_x1), R["H"] + 0.02, "OUTSIDE", ha="center", va="bottom", fontsize=7.5, color="#555")
    ax.set_xlim(x_lo, x_hi); ax.set_ylim(-0.7 if (far is not None and len(far)) else -0.05, R["H"] + 0.1); ax.set_aspect("equal")
    ax.set_xlabel("X — room length (m)"); ax.set_ylabel("Z — height (m)"); ax.set_title(title)
    return ax


def _sample_colorscale(name, t):
    import plotly.colors as pc
    t = float(np.clip(t, 0, 1))
    scale = pc.get_colorscale(name)
    return pc.sample_colorscale(scale, [t])[0]


# --------------------------------------------------------------------------- 3-D display with full-screen support

_FULLSCREEN_JS = """
(function(){
  var gd = document.getElementById('{plot_id}');
  if (!gd) return;
  var bar = document.createElement('div');
  bar.style.cssText = 'font: 12px sans-serif; margin: 2px 0 4px 0;';
  var btn = document.createElement('button');
  btn.textContent = '⛶  Full screen';
  btn.style.cssText = 'cursor:pointer; padding:3px 10px; border:1px solid #888; border-radius:4px; background:#f4f4f4;';
  bar.appendChild(btn);
  var note = document.createElement('span');
  note.style.cssText = 'margin-left:10px; color:#666;';
  note.textContent = 'Esc to exit. If the button does nothing here, open the .html file below in a browser.';
  bar.appendChild(note);
  gd.parentNode.insertBefore(bar, gd);
  function resize(){ if (window.Plotly) { Plotly.Plots.resize(gd); } }
  btn.onclick = function(){
    var el = gd;
    var req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
    if (req) { req.call(el).then(function(){ setTimeout(resize, 150); }).catch(function(){}); }
  };
  document.addEventListener('fullscreenchange', function(){
    if (document.fullscreenElement === gd) { gd.style.width='100vw'; gd.style.height='100vh'; gd.style.background='white'; }
    else { gd.style.width=''; gd.style.height=''; }
    setTimeout(resize, 100);
  });
})();
"""


def show3d(fig, name: str | None = None, height: int = 800, out_dir=None):
    """Display a plotly figure in the notebook with a 'Full screen' button, and (if `name`
    is given) also write a stand-alone HTML file `figures/html/<name>.html` that fills the
    whole browser window — the reliable way to view the 3-D model at full size.
    """
    from IPython.display import HTML, display
    from . import FIG_DIR
    fig.update_layout(autosize=True, height=height, margin=dict(l=0, r=0, t=40, b=0))
    cfg = dict(responsive=True, displaylogo=False, scrollZoom=True)
    html = fig.to_html(full_html=False, include_plotlyjs="cdn", config=cfg, post_script=_FULLSCREEN_JS)
    display(HTML(html))
    if name:
        out_dir = out_dir or (FIG_DIR / "html")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.html"
        f2 = go.Figure(fig); f2.update_layout(height=None, autosize=True)
        body = f2.to_html(full_html=False, include_plotlyjs="cdn", config=cfg, default_height="100vh", default_width="100vw")
        page = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + name + "</title>"
                "<style>html,body{margin:0;height:100%;overflow:hidden;background:white}</style></head><body>" + body + "</body></html>")
        path.write_text(page, encoding="utf-8")
        print(f"full-window version: {path}   (open in a browser)")
        return path
