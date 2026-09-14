"""Visuals for the crop-mix what-if: hole-by-hole plan of every growing tier and a 3-D view."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mp
from matplotlib.lines import Line2D
import plotly.graph_objects as go

from .models import CROPS


def rack_plan_holes(assign, model, title="Crop mix — hole-by-hole plan of the growing tiers"):
    """One panel per tier (top tier first); each hole is a circle coloured by crop."""
    K = model["rack"]
    tiers = sorted(assign.tier.unique(), reverse=True)
    fig, axes = plt.subplots(len(tiers), 1, figsize=(18, 2.2 * len(tiers) + 1.2), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, t in zip(axes, tiers):
        g = assign[assign.tier == t]
        ax.add_patch(mp.Rectangle((K["x0"], K["y0"]), K["length"], K["width"], fc="#f7f7f7", ec="#2a7d2a", lw=1))
        for _, r in g.iterrows():
            ax.add_patch(mp.Circle((r.x, r.y), 0.055, fc=CROPS[r.crop]["color"], ec="#555", lw=0.4))
        counts = g.crop.value_counts()
        ax.text(K["x0"] - 0.05, K["y0"] + K["width"] / 2, f"tier {t}\n{len(g)} holes", ha="right", va="center", fontsize=9, fontweight="bold")
        ax.text(K["x1"] + 0.05, K["y0"] + K["width"] / 2, "\n".join(f"{k}: {v}" for k, v in counts.items()), ha="left", va="center", fontsize=7.5)
        ax.set_xlim(K["x0"] - 0.9, K["x1"] + 1.3); ax.set_ylim(K["y0"] - 0.1, K["y1"] + 0.1); ax.set_aspect("equal"); ax.set_yticks([])
    axes[-1].set_xlabel("X — room length (m)   (door end ←→ far end)")
    handles = [Line2D([0], [0], marker="o", ls="", ms=10, mfc=CROPS[k]["color"], mec="#555", label=k) for k in assign.crop.unique()]
    axes[0].legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=min(len(handles), 6), fontsize=8, frameon=False)
    fig.suptitle(title, y=0.995); fig.tight_layout()
    return fig


def rack_3d_holes(assign, model, base_traces=None, title=None):
    """Plotly 3-D: rack model + one marker per hole coloured by crop (legend per crop)."""
    from .viz import model_traces, figure_3d
    tr = list(base_traces) if base_traces is not None else model_traces(model, tier_color="#e0e0e0")
    for k, g in assign.groupby("crop"):
        tr.append(go.Scatter3d(x=g.x, y=g.y, z=g.z, mode="markers", name=f"{k} ({len(g)})",
                               marker=dict(size=4, color=CROPS[k]["color"], line=dict(color="#333", width=0.5)),
                               hovertext=[f"tier {r.tier} col {r.col} row {r.row}: {k}" for r in g.itertuples()], hoverinfo="text"))
    return figure_3d(tr, title=title or "Crop mix on the growing tiers (one marker per hole)", height=720)
