"""Make a small point-cloud asset for the web app from the second LiDAR scan (SIS PFAL2.ply):
align to the room frame with the same pipeline as notebook 02, crop to the room, voxel-downsample, store as
float16 xyz + uint8 rgb in app/assets/pointcloud_scan2.npz (~1-2 MB, committed so the cloud app can show it)."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from pfal_twin import io, geometry as G  # noqa: E402

VOXEL = 0.04      # m
OUT = ROOT / "app" / "assets" / "pointcloud_scan2.npz"

pc = io.load_ply(io.RAW / "pointcloud" / "SIS PFAL2.ply")
T, info = G.align_room(pc["xyz"], pc["normals"])
P = G.apply_T(T, pc["xyz"]); N = G.apply_T_normals(T, pc["normals"])
b = G.interior_bounds(P, N); keep = G.crop_to_room(P, b)
P, RGB = P[keep], pc["rgb"][keep]
# voxel grid: one point per occupied voxel (mean colour)
key = np.floor(P / VOXEL).astype(np.int64)
_, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
cnt = np.bincount(inv)
Pm = np.zeros((len(idx), 3)); Cm = np.zeros((len(idx), 3))
for d in range(3):
    Pm[:, d] = np.bincount(inv, P[:, d]) / cnt; Cm[:, d] = np.bincount(inv, RGB[:, d].astype(float)) / cnt
np.savez_compressed(OUT, xyz=Pm.astype(np.float16), rgb=Cm.round().astype(np.uint8),
                    meta=np.array([f"SIS PFAL2.ply, scanned 2026-09-13, {len(pc['xyz']):,} raw points, {keep.sum():,} inside the room, voxel {VOXEL*100:.0f} cm -> {len(idx):,} points; "
                                   f"room {b['L']:.2f} x {b['W']:.2f} x {b['H']:.2f} m"]))
print(OUT, f"{OUT.stat().st_size/1e6:.2f} MB", len(idx), "points")
