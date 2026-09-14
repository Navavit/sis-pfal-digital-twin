"""Loading / caching of the point cloud and model files."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import PLY_PATH, RAW, IOT_RAW, PROCESSED, MODEL_DIR, SENSOR_DIR, FIG_DIR

def _read_ply_header(path: Path):
    """Return (n_header_lines, property_names) of an ASCII PLY."""
    props, n = [], 0
    with open(path, "r") as f:
        for line in f:
            n += 1
            t = line.split()
            if t and t[0] == "property" and len(t) == 3:
                props.append(t[2])
            if line.strip() == "end_header":
                break
    return n, props


def load_ply(path: Path = PLY_PATH, cache: bool = True, estimate_normals: bool = True) -> dict:
    """Return dict(xyz, normals, rgb) as float32/uint8 arrays.

    Any ASCII PLY with x y z [nx ny nz] red green blue columns is accepted. If the file
    has no normals they are estimated with open3d (needed by the alignment code).
    Parsed once and cached as data/processed/<stem>.npz (raw.npz for the primary scan).
    """
    path = Path(path)
    cache_file = PROCESSED / ("raw.npz" if path == PLY_PATH else f"raw_{path.stem.replace(' ', '_')}.npz")
    if cache and cache_file.exists():
        z = np.load(cache_file)
        return {k: z[k] for k in ("xyz", "normals", "rgb")}
    n_hdr, props = _read_ply_header(path)
    data = np.loadtxt(path, skiprows=n_hdr, dtype=np.float32)
    col = {p: i for i, p in enumerate(props)}
    xyz = data[:, [col["x"], col["y"], col["z"]]].copy()
    rgb = data[:, [col["red"], col["green"], col["blue"]]].astype(np.uint8)
    if "nx" in col:
        normals = data[:, [col["nx"], col["ny"], col["nz"]]].copy()
    elif estimate_normals:
        import open3d as o3d
        pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz.astype(np.float64)))
        pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.08, max_nn=30))
        normals = np.asarray(pc.normals, dtype=np.float32)
    else:
        normals = np.zeros_like(xyz)
    out = {"xyz": xyz, "normals": normals, "rgb": rgb}
    if cache:
        np.savez_compressed(cache_file, **out)
    return out


def save_clean(xyz, normals, rgb, labels=None, name: str = "pfal_clean.npz") -> Path:
    p = PROCESSED / name
    arrs = dict(xyz=xyz.astype(np.float32), normals=normals.astype(np.float32), rgb=rgb.astype(np.uint8))
    if labels is not None:
        arrs["labels"] = labels.astype(np.int16)
    np.savez_compressed(p, **arrs)
    return p


def load_clean(name: str = "pfal_clean.npz") -> dict:
    z = np.load(PROCESSED / name)
    return {k: z[k] for k in z.files}


def save_model(model: dict, name: str = "room_model.json") -> Path:
    p = MODEL_DIR / name
    with open(p, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, ensure_ascii=False, default=_json_default)
    return p


def load_model(name: str = "room_model.json") -> dict:
    with open(MODEL_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    raise TypeError(type(o))
