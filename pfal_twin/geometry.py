"""Geometry processing: alignment, cropping, tier detection, room model, segmentation.

Coordinate frames
-----------------
scan frame  : as exported by the LiDAR app — metres, **Y up**, arbitrary origin/yaw.
room frame  : engineering frame used by the twin — **Z up**,
              X along the room length, Y along the room width,
              origin at the interior floor corner (min X, min Y, floor level).
`align_room` returns the 4x4 matrix T so that  p_room = T @ [p_scan, 1].
"""
from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

# --------------------------------------------------------------------------- helpers

def _rot_from_to(a, b):
    """Rotation matrix taking unit vector a onto unit vector b (Rodrigues)."""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def apply_T(T, pts):
    return pts @ T[:3, :3].T + T[:3, 3]


def apply_T_normals(T, n):
    return n @ T[:3, :3].T


def edge_peak(v, side="low", bin_m=0.02, frac=0.25):
    """Position of the outermost *strong* histogram peak of 1-D coordinates.

    Used to locate walls / floor / ceiling robustly: stray points scanned
    through the door lie outside the wall but never form a dense plane, so
    they are ignored (bins with < frac * max count don't qualify).
    """
    edges = np.arange(v.min() - bin_m, v.max() + 2 * bin_m, bin_m)
    hist, _ = np.histogram(v, bins=edges)
    strong = np.where(hist >= frac * hist.max())[0]
    k = strong.min() if side == "low" else strong.max()
    # refine with the median of points inside that bin ± 1
    sel = (v >= edges[max(k - 1, 0)]) & (v < edges[min(k + 2, len(edges) - 1)])
    return float(np.median(v[sel]))


# --------------------------------------------------------------------------- alignment

def fit_floor_plane(xyz, normals, up_axis=1, ny_min=0.9, low_quantile=0.15):
    """Least-squares plane through the lowest horizontal-facing points (the floor)."""
    horiz = np.abs(normals[:, up_axis]) > ny_min
    h = xyz[:, up_axis]
    low = h < np.quantile(h[horiz], low_quantile)
    pts = xyz[horiz & low]
    c = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = vt[2]
    if n[up_axis] < 0:
        n = -n
    return n, c, pts.shape[0]


def dominant_wall_yaw(normals_zup, min_vertical=0.95, bins=180):
    """Yaw angle (deg, in (-45, 45]) of the dominant wall direction, Z-up frame."""
    wall = np.abs(normals_zup[:, 2]) < (1 - min_vertical)
    ang = np.degrees(np.arctan2(normals_zup[wall, 1], normals_zup[wall, 0])) % 90.0
    hist, edges = np.histogram(ang, bins=bins, range=(0, 90))
    k = hist.argmax()
    yaw = 0.5 * (edges[k] + edges[k + 1])
    if yaw > 45:
        yaw -= 90
    return yaw


def align_room(xyz, normals, length_axis_hint: str = "auto"):
    """Compute T (scan -> room frame). See module docstring.

    Steps: level the floor -> swap to Z-up -> remove wall yaw -> put origin at
    the interior floor corner. Returns (T, info).
    """
    # 1. level floor (scan frame, Y up)
    n_floor, c_floor, n_pts = fit_floor_plane(xyz, normals, up_axis=1)
    R1 = _rot_from_to(n_floor, np.array([0, 1.0, 0]))
    # 2. Y-up -> Z-up : (x, y, z) -> (x, -z, y)   [keeps right-handedness]
    R2 = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    R12 = R2 @ R1
    n12 = normals @ R12.T
    # 3. yaw so walls are axis-aligned
    yaw = dominant_wall_yaw(n12)
    cz, sz = np.cos(np.radians(-yaw)), np.sin(np.radians(-yaw))
    R3 = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    R = R3 @ R12
    p = xyz @ R.T
    n = normals @ R.T
    # 4. make X the long axis
    wall = np.abs(n[:, 2]) < 0.1
    ext = np.percentile(p[wall], 99.5, axis=0) - np.percentile(p[wall], 0.5, axis=0)
    if (length_axis_hint == "auto" and ext[1] > ext[0]) or length_axis_hint == "y":
        Rswap = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], dtype=float)  # rotate -90° about Z
        R = Rswap @ R
        p = xyz @ R.T
        n = normals @ R.T
    # 5. refine yaw on the two long walls (most points): fit a line through
    #    per-bin medians of each wall and remove the mean residual tilt
    floor_z0 = edge_peak(p[np.abs(n[:, 2]) > 0.9, 2], "low")
    wall = (np.abs(n[:, 2]) < 0.2) & (p[:, 2] > floor_z0 + 0.3)
    y_lo = edge_peak(p[wall, 1], "low"); y_hi = edge_peak(p[wall, 1], "high")
    tilts = []
    for pos in (y_lo, y_hi):
        q = p[wall & (np.abs(p[:, 1] - pos) < 0.30)]
        edges = np.arange(q[:, 0].min(), q[:, 0].max() + 0.1, 0.1)
        cx, cy = [], []
        for a, b in zip(edges[:-1], edges[1:]):
            mm = (q[:, 0] >= a) & (q[:, 0] < b)
            if mm.sum() >= 50:
                cx.append(0.5 * (a + b)); cy.append(np.median(q[mm, 1]))
        tilts.append(np.degrees(np.arctan(np.polyfit(cx, cy, 1)[0])))
    dyaw = float(np.mean(tilts))
    cz, sz = np.cos(np.radians(-dyaw)), np.sin(np.radians(-dyaw))
    R = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ R
    p = xyz @ R.T
    n = normals @ R.T
    # 6. origin at interior floor corner: floor level from horizontal points, walls from vertical points
    floor_z = edge_peak(p[np.abs(n[:, 2]) > 0.9, 2], "low")
    wallpts = p[(np.abs(n[:, 2]) < 0.1) & (p[:, 2] > floor_z + 0.3)]
    x0 = edge_peak(wallpts[:, 0], "low")
    y0 = edge_peak(wallpts[:, 1], "low")
    t = -np.array([x0, y0, floor_z])
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = t
    info = dict(floor_normal_scan=n_floor, floor_points=int(n_pts), wall_yaw_deg=float(yaw) + dyaw,
                yaw_histogram_deg=float(yaw), yaw_refine_deg=dyaw, long_wall_tilts_deg=[float(t) for t in tilts])
    return T, info


# --------------------------------------------------------------------------- interior / crop

def interior_bounds(p_room, n_room, margin=0.05):
    """(L, W, H) of the room interior from wall / floor / ceiling points (room frame)."""
    vert = np.abs(n_room[:, 2]) < 0.1
    horiz = np.abs(n_room[:, 2]) > 0.9
    w = p_room[vert & (p_room[:, 2] > 0.3)]
    L = edge_peak(w[:, 0], "high") - edge_peak(w[:, 0], "low")
    W = edge_peak(w[:, 1], "high") - edge_peak(w[:, 1], "low")
    H = edge_peak(p_room[horiz, 2], "high")
    return dict(L=float(L), W=float(W), H=float(H), margin=margin)


def crop_to_room(p_room, bounds, pad=0.15):
    L, W, H = bounds["L"], bounds["W"], bounds["H"]
    m = ((p_room[:, 0] > -pad) & (p_room[:, 0] < L + pad) &
         (p_room[:, 1] > -pad) & (p_room[:, 1] < W + pad) &
         (p_room[:, 2] > -pad) & (p_room[:, 2] < H + pad))
    return m


# --------------------------------------------------------------------------- tiers / rack

def detect_horizontal_levels(p_room, n_room, bin_m=0.02, prominence=3000, min_sep_m=0.25):
    """Heights (m above floor) of horizontal surfaces: floor, rack tiers, ceiling."""
    horiz = np.abs(n_room[:, 2]) > 0.9
    z = p_room[horiz, 2]
    edges = np.arange(z.min() - bin_m, z.max() + 2 * bin_m, bin_m)
    hist, _ = np.histogram(z, bins=edges)
    pk, props = find_peaks(hist, prominence=prominence, distance=max(1, int(min_sep_m / bin_m)))
    levels = 0.5 * (edges[pk] + edges[pk + 1])
    return levels, hist[pk], (edges, hist)


def classify_levels(levels, room_H, floor_tol=0.08, ceiling_tol=0.10, top_frame_gap=0.25):
    """Split detected levels into floor / growing tiers / rack top frame / ceiling.

    The top frame (light-bar / canopy of the rack) is the highest non-ceiling
    level if it sits within `top_frame_gap` of the ceiling — plants can't grow there.
    """
    floor = [l for l in levels if abs(l) < floor_tol]
    ceiling = [l for l in levels if abs(l - room_H) < ceiling_tol]
    rest = [float(l) for l in levels if l not in floor and l not in ceiling]
    top_frame = None
    if rest and room_H - rest[-1] < top_frame_gap:
        top_frame = rest.pop()
    return dict(floor=float(floor[0]) if floor else 0.0,
                ceiling=float(ceiling[-1]) if ceiling else room_H,
                tiers=rest, top_frame=top_frame if top_frame is not None else room_H)


def rack_footprint(p_room, n_room, tier_heights, tol=0.03, q=(2, 98)):
    """Union of the XY extents of horizontal points at each tier height."""
    horiz = np.abs(n_room[:, 2]) > 0.9
    boxes = []
    for h in tier_heights:
        m = horiz & (np.abs(p_room[:, 2] - h) < tol)
        pts = p_room[m]
        lo = np.percentile(pts[:, :2], q[0], axis=0)
        hi = np.percentile(pts[:, :2], q[1], axis=0)
        boxes.append(dict(z=float(h), x0=float(lo[0]), x1=float(hi[0]), y0=float(lo[1]), y1=float(hi[1]), n=int(m.sum())))
    # robust rack extent = median of per-tier extents (tiers with pipes/tanks can be wider)
    x0 = float(np.median([b["x0"] for b in boxes])); x1 = float(np.median([b["x1"] for b in boxes]))
    y0 = float(np.median([b["y0"] for b in boxes])); y1 = float(np.median([b["y1"] for b in boxes]))
    return dict(x0=x0, x1=x1, y0=y0, y1=y1, per_tier=boxes)


def build_room_model(bounds, levels, rack, T, info, source="SIS PFAL.ply"):
    tiers = [dict(index=i + 1, z=round(float(z), 3)) for i, z in enumerate(levels["tiers"])]
    return dict(
        source=source,
        frame="room: Z up, X = length, Y = width, origin = interior floor corner (m)",
        room=dict(L=round(bounds["L"], 3), W=round(bounds["W"], 3), H=round(bounds["H"], 3)),
        rack=dict(x0=round(rack["x0"], 3), x1=round(rack["x1"], 3), y0=round(rack["y0"], 3), y1=round(rack["y1"], 3),
                  length=round(rack["x1"] - rack["x0"], 3), width=round(rack["y1"] - rack["y0"], 3),
                  tiers=tiers, top_frame_z=round(levels.get("top_frame", levels["ceiling"]), 3)),
        transform_scan_to_room=np.asarray(T).round(6).tolist(),
        alignment_info=dict(wall_yaw_deg=round(info["wall_yaw_deg"], 3),
                            floor_normal_scan=np.asarray(info["floor_normal_scan"]).round(5).tolist()),
    )


# --------------------------------------------------------------------------- segmentation

LABELS = {0: "other", 1: "floor", 2: "ceiling", 3: "wall_x0", 4: "wall_x1", 5: "wall_y0", 6: "wall_y1", 10: "rack_tier"}


def segment_points(p_room, n_room, model, wall_tol=0.12, plane_tol=0.05, tier_tol=0.04):
    """Coarse semantic labels. Tier k gets label 10 + k."""
    L, W, H = model["room"]["L"], model["room"]["W"], model["room"]["H"]
    lab = np.zeros(len(p_room), dtype=np.int16)
    horiz = np.abs(n_room[:, 2]) > 0.85
    vert = np.abs(n_room[:, 2]) < 0.2
    z = p_room[:, 2]
    lab[horiz & (np.abs(z) < plane_tol)] = 1
    lab[horiz & (np.abs(z - H) < plane_tol * 2)] = 2
    lab[vert & (p_room[:, 0] < wall_tol)] = 3
    lab[vert & (p_room[:, 0] > L - wall_tol)] = 4
    lab[vert & (p_room[:, 1] < wall_tol)] = 5
    lab[vert & (p_room[:, 1] > W - wall_tol)] = 6
    r = model["rack"]
    inrack = (p_room[:, 0] > r["x0"] - 0.05) & (p_room[:, 0] < r["x1"] + 0.05) & \
             (p_room[:, 1] > r["y0"] - 0.05) & (p_room[:, 1] < r["y1"] + 0.05)
    for t in r["tiers"]:
        lab[horiz & inrack & (np.abs(z - t["z"]) < tier_tol)] = 10 + t["index"]
    return lab


def label_names(model):
    d = dict(LABELS)
    for t in model["rack"]["tiers"]:
        d[10 + t["index"]] = f"tier_{t['index']}"
    return d


# --------------------------------------------------------------------------- accuracy diagnostics

def wall_tilts(p_room, n_room, model, band=0.30, step=0.10, min_pts=50):
    """Residual in-plane tilt (deg) and offset of each wall vs. the rectangular model.

    For each wall, vertical-normal points within `band` of the model plane are
    binned along the wall; a line is fitted through the per-bin medians. Non-zero
    and mutually inconsistent tilts indicate scan drift (walls that are not
    parallel in the scan although the real room is rectangular).
    """
    L, W = model["room"]["L"], model["room"]["W"]
    vert = np.abs(n_room[:, 2]) < 0.2
    specs = {"wall y=0": (1, 0.0, 0), "wall y=W": (1, W, 0), "wall x=0": (0, 0.0, 1), "wall x=L": (0, L, 1)}
    out = {}
    for name, (ax_across, pos, ax_along) in specs.items():
        m = vert & (np.abs(p_room[:, ax_across] - pos) < band) & (p_room[:, 2] > 0.3) & (p_room[:, 2] < model["room"]["H"] - 0.3)
        q = p_room[m]
        x, y = q[:, ax_along], q[:, ax_across]
        edges = np.arange(x.min(), x.max() + step, step)
        cx, cy = [], []
        for a, b in zip(edges[:-1], edges[1:]):
            mm = (x >= a) & (x < b)
            if mm.sum() >= min_pts:
                cx.append(0.5 * (a + b)); cy.append(np.median(y[mm]))
        k = np.polyfit(cx, cy, 1)
        out[name] = dict(tilt_deg=float(np.degrees(np.arctan(k[0]))), offset_cm=float(100 * (np.polyval(k, np.mean(cx)) - pos)),
                         span_cm=float(100 * k[0] * (max(cx) - min(cx))), n=int(m.sum()))
    return out


# --------------------------------------------------------------------------- idealisation

def symmetrize_model(model, centre_width=True, centre_length=False, round_to=None):
    """Idealise the parametric model: the real room is rectangular and the rack
    is centred across its width, so scan noise (a few cm) must not leave the
    twin asymmetric. Measured values are preserved under model["measured"].

    centre_width  : rack centred on Y = W/2 (aisles equal)        [default on]
    centre_length : rack centred on X = L/2 (only if true on site) [default off]
    round_to      : e.g. 0.01 to round room/rack dimensions to 1 cm
    """
    import copy
    m = copy.deepcopy(model)
    m.setdefault("measured", {})["rack"] = copy.deepcopy(model["rack"])
    m["measured"]["room"] = copy.deepcopy(model["room"])
    R, K = m["room"], m["rack"]
    if round_to:
        for k in ("L", "W", "H"):
            R[k] = round(round(R[k] / round_to) * round_to, 6)
        K["length"] = round(round(K["length"] / round_to) * round_to, 6)
        K["width"] = round(round(K["width"] / round_to) * round_to, 6)
        K["top_frame_z"] = round(min(round(K["top_frame_z"] / round_to) * round_to, R["H"]), 6)
    if centre_width:
        K["y0"] = round(R["W"] / 2 - K["width"] / 2, 3)
        K["y1"] = round(R["W"] / 2 + K["width"] / 2, 3)
    if centre_length:
        K["x0"] = round(R["L"] / 2 - K["length"] / 2, 3)
        K["x1"] = round(R["L"] / 2 + K["length"] / 2, 3)
    K.pop("per_tier", None)
    m["idealised"] = dict(centre_width=centre_width, centre_length=centre_length, round_to=round_to)
    return m


# --------------------------------------------------------------------------- zones

def make_zones(model, n_segments=3, canopy_height=0.35, seg_names=("S1", "S2", "S3"), segments_per_tier=None, splits=None):
    """Growing zones = tier x segment along the rack length (X). Zone k of tier t is
    the box above tier plate t, `canopy_height` tall. Segment 1 is nearest X=0 (door end).
    `segments_per_tier` = {tier_index: n} overrides `n_segments` for specific tiers
    (e.g. {1: 2} because tier 1 is split into nursery 1 (door end) and nursery 2 (far end), each with its own 100 L tank).
    `splits` = {tier_index: [x, ...]} gives explicit boundary positions (m) instead of equal segments,
    e.g. {1: [2.22]} — the nursery-1 / nursery-2 boundary measured in the point cloud."""
    K = model["rack"]
    spt = segments_per_tier or {}
    zones = []
    for t in K["tiers"]:
        n = spt.get(t["index"], n_segments)
        if splits and t["index"] in splits:
            xs = np.array([K["x0"], *splits[t["index"]], K["x1"]], float); n = len(xs) - 1
        else:
            xs = np.linspace(K["x0"], K["x1"], n + 1)
        for s in range(n):
            if n == 2:
                name = ("N1", "N2")[s]                     # tier-1 halves: nursery 1 (door end), nursery 2 (far end, by the growing tank)
            else:
                name = seg_names[s] if s < len(seg_names) else f"S{s+1}"
            stage = ("nursery 1" if s == 0 else "nursery 2") if (t["index"] == 1 and n == 2) else ("growing stage" if t["index"] >= 2 else "tier 1")
            zones.append(dict(zone=f"T{t['index']}-{name}", tier=t["index"], stage=stage, segment=s + 1, n_segments=n,
                              x0=round(float(xs[s]), 3), x1=round(float(xs[s + 1]), 3),
                              y0=K["y0"], y1=K["y1"],
                              z0=t["z"], z1=round(t["z"] + canopy_height, 3)))
    return zones


def zone_of(zones, x, y, z):
    """Name of the zone containing point (x, y, z) in room frame, or None."""
    for q in zones:
        if q["x0"] <= x <= q["x1"] and q["y0"] <= y <= q["y1"] and q["z0"] <= z <= q["z1"]:
            return q["zone"]
    return None


def air_grid(model, dx=0.5):
    """Voxel grid over the room air volume (for interpolating sparse sensors later)."""
    R = model["room"]
    nx, ny, nz = (int(np.ceil(R[k] / dx)) for k in ("L", "W", "H"))
    return dict(dx=dx, nx=nx, ny=ny, nz=nz, n_cells=nx * ny * nz,
                x=np.linspace(dx / 2, R["L"] - dx / 2, nx).round(3).tolist(),
                y=np.linspace(dx / 2, R["W"] - dx / 2, ny).round(3).tolist(),
                z=np.linspace(dx / 2, R["H"] - dx / 2, nz).round(3).tolist())
