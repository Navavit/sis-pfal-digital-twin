"""Generate notebooks/01-05 (kept as a script so they can be regenerated).

Run from anywhere:  .venv/bin/python scripts/make_notebooks.py
"""
from pathlib import Path
import nbformat as nbf

KERNEL = dict(kernelspec=dict(name="pfal-twin", display_name="Python (pfal-twin)", language="python"),
              language_info=dict(name="python"))
SETUP = '''import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import plotly.io as pio
from pfal_twin import io, geometry as G, viz, layout, thingsboard as tb, hydraulics as H, schematic as S
pio.renderers.default = "vscode+notebook"   # works in VS Code and JupyterLab
FIG = ROOT / "figures"; FIG.mkdir(exist_ok=True)
print("project root:", ROOT)'''

def nb(cells):
    n = nbf.v4.new_notebook(); n.metadata.update(KERNEL)
    n.cells = [nbf.v4.new_markdown_cell(c[1]) if c[0] == "md" else nbf.v4.new_code_cell(c[1]) for c in cells]
    return n

# ----------------------------------------------------------------------------- 01
nb01 = nb([
("md", """# 01 — สำรวจ point cloud ของห้อง PFAL (SIS KU)

**เป้าหมาย (L1 Geometry twin, ขั้นแรก)**: ทำความรู้จักไฟล์ `SIS PFAL.ply` — จำนวนจุด, ระบบพิกัด, ขนาดคร่าวๆ, การกระจายตัวตามความสูง และดูภาพ 3 มิติแบบหมุนได้

ข้อมูลดิบ: สแกนด้วย LiDAR มือถือ, ASCII PLY, ต่อจุดมี ตำแหน่ง (x,y,z) / เวกเตอร์ตั้งฉาก (nx,ny,nz) / สี (RGB)
ระบบพิกัดของสแกน: หน่วยเมตร, **แกน Y ชี้ขึ้น** (Notebook 02 จะแปลงเป็น Z-up และจัดให้ผนังขนานแกน)

> รูปทุกรูปใช้ป้ายภาษาอังกฤษเพื่อนำไปใช้ในบทความได้โดยตรง (บันทึกใน `figures/`)"""),
("code", SETUP),
("md", "## 1. โหลดไฟล์ (ครั้งแรก ~1 วินาที แล้ว cache เป็น `data/processed/raw.npz`)"),
("code", '''pc = io.load_ply()
xyz, normals, rgb = pc["xyz"], pc["normals"], pc["rgb"]
print(f"points: {len(xyz):,}")
print("PLY path:", io.PLY_PATH)'''),
("md", "## 2. สถิติพื้นฐาน — bounding box และขนาดตามแกน (ยังเป็นพิกัดสแกน)"),
("code", '''stats = pd.DataFrame({
    "min": xyz.min(0), "p1": np.percentile(xyz, 1, axis=0), "median": np.median(xyz, axis=0),
    "p99": np.percentile(xyz, 99, axis=0), "max": xyz.max(0),
}, index=["x", "y (up)", "z"])
stats["extent (max-min)"] = stats["max"] - stats["min"]
stats["extent (p99-p1)"] = stats["p99"] - stats["p1"]
stats.round(3)'''),
("md", """`extent (p99-p1)` ตัดจุดหลงที่สแกนทะลุประตูออกไปแล้ว → ห้องกว้าง ~3.2 ม. ยาว ~7.2 ม. สูง ~2.6 ม.
ค่า `max-min` ที่ใหญ่กว่ามากในแกน z คือจุดนอกห้อง (จะ crop ทิ้งใน Notebook 02)"""),
("md", "## 3. การกระจายตัวตามความสูง — ใช้เฉพาะจุดที่หันขึ้น/ลง (|ny| > 0.9) เพื่อให้เห็นพื้น, ชั้นปลูก, เพดาน เป็น peak"),
("code", '''horiz = np.abs(normals[:, 1]) > 0.9
h = xyz[horiz, 1]
edges = np.arange(h.min(), h.max() + 0.02, 0.02)
fig, ax = plt.subplots(figsize=(10, 4))
ax.hist(h, bins=edges, color="#7a9")
ax.set_xlabel("scan y (m)  — up axis, arbitrary origin"); ax.set_ylabel("horizontal-facing points")
ax.set_title("Height distribution of horizontal surfaces (floor, rack tiers, ceiling appear as peaks)")
fig.tight_layout(); fig.savefig(FIG / "01_height_histogram.png", dpi=150)'''),
("md", "เห็น peak ของพื้น 1 อัน, ชั้นปลูก 5 อัน (ห่างกัน ~0.42 ม.) และเพดาน — ตรงกับชั้นปลูก 5 ชั้นในห้องจริง"),
("md", "## 4. มุมมอง 2 มิติ: plan view (มุมบน) / side / front — สีจริงจากกล้อง"),
("code", '''fig, axes = plt.subplots(1, 3, figsize=(20, 8), gridspec_kw=dict(width_ratios=[1, 2.2, 1]))
viz.plan_view(xyz, rgb, ax=axes[0], xy=(0, 2), title="Plan view (scan x vs z)")
viz.plan_view(xyz, rgb, ax=axes[1], xy=(2, 1), title="Side view (scan z vs y)")
viz.plan_view(xyz, rgb, ax=axes[2], xy=(0, 1), title="End view (scan x vs y)")
for a in axes: a.set_xlabel("m"); a.set_ylabel("m")
fig.tight_layout(); fig.savefig(FIG / "01_views.png", dpi=130)'''),
("md", """สังเกต: ห้องเอียงจากแกนเล็กน้อย (~2°), มีชั้นปลูก 1 แถวกลางห้อง ทางเดินสองข้าง, พื้นสีเขียว
จุดที่กระจายอยู่นอกกรอบด้านบนของ plan view คือส่วนที่สแกนเลยประตูออกไป"""),
("md", "## 5. ตัดขวางตามความสูง (horizontal slabs) — ช่วยดูว่าแต่ละระดับมีอะไร"),
("code", '''floor_y = np.percentile(xyz[horiz, 1], 1)
slabs = [(0.02, 0.35, "floor level: tanks, pipes, reservoirs"),
         (0.60, 1.10, "tiers 2–3"), (1.30, 2.30, "tiers 4–5, wall-mounted AC / boxes")]
fig, axes = plt.subplots(1, 3, figsize=(20, 9))
for ax, (lo, hi, name) in zip(axes, slabs):
    m = (xyz[:, 1] - floor_y > lo) & (xyz[:, 1] - floor_y < hi)
    viz.plan_view(xyz[m], rgb[m], ax=ax, xy=(0, 2), n=250000, s=0.3,
                  title=f"{lo:.2f}–{hi:.2f} m above floor\\n{name}")
fig.tight_layout(); fig.savefig(FIG / "01_slabs.png", dpi=130)'''),
("md", "## 6. ภาพ 3 มิติแบบโต้ตอบ (สุ่ม 80k จุดเพื่อความลื่น — ลาก/หมุน/ซูมได้; ปุ่ม **Full screen** เหนือรูป หรือเปิดไฟล์ `figures/html/*.html` ในเบราว์เซอร์เพื่อดูเต็มจอ)"),
("code", '''fig3d = viz.figure_3d([viz.points_trace(xyz, rgb, n=80000, size=1.5)],
                      title="SIS PFAL — raw LiDAR point cloud (scan frame, Y up)")
fig3d.update_layout(scene=dict(xaxis_title="x (m)", yaxis_title="y (m, up)", zaxis_title="z (m)"))
viz.show3d(fig3d, "01_raw_pointcloud")'''),
("md", "## 7. คุณภาพข้อมูล: ความยาว normal, การกระจายสี"),
("code", '''nlen = np.linalg.norm(normals, axis=1)
print(f"normal length: mean={nlen.mean():.4f}  min={nlen.min():.3f}  max={nlen.max():.3f}  (should be ~1)")
print("mean RGB:", rgb.mean(0).round(1), " | fraction of near-black points:", np.mean(rgb.mean(1) < 40).round(4))
# nearest-neighbour spacing on a random subset = effective point density
from scipy.spatial import cKDTree
idx = viz.subsample(len(xyz), 50000)
d, _ = cKDTree(xyz).query(xyz[idx], k=2)
print(f"median nearest-neighbour spacing: {np.median(d[:,1])*100:.1f} cm  (p90 {np.percentile(d[:,1],90)*100:.1f} cm)")'''),
("md", """## สรุปจาก Notebook 01
- 1.02 ล้านจุด, มี normal และสีครบ, ระยะห่างจุดระดับ ~1–3 ซม. → พอสำหรับ layout ระดับห้อง/ชั้นปลูก แต่ไม่พอสำหรับวัตถุเล็ก (เซ็นเซอร์, กล่องควบคุมเล็ก)
- ห้อง ~7.2 × 3.2 × 2.6 ม., ชั้นปลูก 5 ชั้นกลางห้อง
- ต้องแก้ใน Notebook 02: หมุนให้ผนังขนานแกน, ย้ายจุดกำเนิดไปมุมห้อง, แปลงเป็น Z-up, crop จุดนอกห้อง"""),
])

# ----------------------------------------------------------------------------- 02
nb02 = nb([
("md", """# 02 — สร้างโมเดลเรขาคณิตของห้อง (Geometry twin)

**เป้าหมาย**: จาก point cloud ดิบ → พิกัดมาตรฐานของห้อง (Z-up, ผนังขนานแกน, จุดกำเนิดที่มุมพื้น) → ตรวจจับพื้น/เพดาน/ผนัง/ชั้นปลูก → **`room_model.json`** (พารามิเตอร์ห้องที่ notebook ถัดไปทุกตัวใช้) และ point cloud ที่ทำความสะอาดแล้ว (`pfal_clean.npz`) พร้อม label

ขั้นตอน
1. Align: ปรับพื้นให้ราบ → Z-up → หมุนตามผนัง → ย้ายจุดกำเนิด (ได้เมทริกซ์ `T` 4×4 เก็บไว้ใช้แปลงพิกัดเซ็นเซอร์ภายหลัง)
2. Crop จุดนอกห้อง
3. หา peak ความสูงของระนาบแนวนอน → พื้น, ชั้นปลูก, เพดาน
4. หา footprint ของชั้นปลูก
5. บันทึกโมเดล + segment จุด + ซ้อนโมเดลกับ point cloud เพื่อตรวจสอบ"""),
("code", SETUP),
("md", "## 1. โหลดและ align"),
("code", '''pc = io.load_ply()
T, info = G.align_room(pc["xyz"], pc["normals"])
P = G.apply_T(T, pc["xyz"]); N = G.apply_T_normals(T, pc["normals"]); RGB = pc["rgb"]
print("wall yaw corrected (deg):", round(info["wall_yaw_deg"], 2))
print("floor normal in scan frame:", np.round(info["floor_normal_scan"], 4), f"(fit on {info['floor_points']:,} pts)")
print("T (scan -> room):\\n", np.round(T, 4))'''),
("md", "## 2. ขอบเขตภายในห้อง และ crop จุดที่อยู่นอกห้อง (สแกนทะลุประตู)"),
("code", '''bounds = G.interior_bounds(P, N)
keep = G.crop_to_room(P, bounds, pad=0.15)
print(f"interior L x W x H = {bounds['L']:.3f} x {bounds['W']:.3f} x {bounds['H']:.3f} m")
print(f"kept {keep.sum():,} points, removed {(~keep).sum():,} outside the room")
P, N, RGB = P[keep], N[keep], RGB[keep]'''),
("md", "## 3. ระดับความสูงของระนาบแนวนอน → พื้น / ชั้นปลูก / เพดาน"),
("code", '''levels, counts, hist = G.detect_horizontal_levels(P, N)
cls = G.classify_levels(levels, bounds["H"])
fig, ax = plt.subplots(figsize=(10, 4))
viz.height_histogram(hist, levels, ax=ax, title="Horizontal-surface heights in room frame (peaks = floor, tiers, ceiling)")
fig.tight_layout(); fig.savefig(FIG / "02_levels.png", dpi=150)
pd.DataFrame({"level (m)": np.round(levels, 3), "points": counts,
              "class": ["floor" if abs(l - cls["floor"]) < 1e-9 else "ceiling" if abs(l - cls["ceiling"]) < 1e-9
                        else "top frame" if abs(l - cls["top_frame"]) < 1e-9 else "tier" for l in levels]})'''),
("md", "## 4. Footprint ของชั้นปลูก (จากจุดแนวนอนที่แต่ละระดับชั้น)"),
("code", '''rack = G.rack_footprint(P, N, cls["tiers"])
per_tier = pd.DataFrame(rack["per_tier"]).round(3)
per_tier.index = [f"tier {i+1}" for i in range(len(per_tier))]
print(f"rack (median over tiers): x {rack['x0']:.2f}–{rack['x1']:.2f} m, y {rack['y0']:.2f}–{rack['y1']:.2f} m "
      f"→ {rack['x1']-rack['x0']:.2f} x {rack['y1']-rack['y0']:.2f} m")
print(f"aisles: left {rack['y0']:.2f} m, right {bounds['W']-rack['y1']:.2f} m")
per_tier'''),
("md", "ชั้นที่ footprint กว้างกว่าปกติ (เช่นชั้นล่างสุดยาวถึงผนัง) เกิดจากถัง/อุปกรณ์ที่อยู่ระดับเดียวกัน — จึงใช้ค่า median ของทุกชั้นเป็นขนาด rack"),
("md", """## 5. ทำให้โมเดลสมมาตร แล้วบันทึก `room_model.json`
ห้องจริงเป็นสี่เหลี่ยมมุมฉากและชั้นปลูกอยู่กึ่งกลางความกว้างห้อง — ค่าที่วัดจากสแกนต่างจากสมมาตรเพียงไม่กี่ซม. (noise ของ LiDAR)
จึง **บังคับสมมาตรในโมเดล**: rack อยู่กึ่งกลาง Y พอดี (ทางเดินสองข้างเท่ากัน) และปัดขนาดเป็น 1 ซม. ค่าที่วัดได้จริงเก็บไว้ใน `model["measured"]`
ตามความยาว (X) ไม่บังคับ เพราะปลายห้องด้านหนึ่งมีถัง/อุปกรณ์ → ถ้าหน้างาน rack อยู่กึ่งกลางความยาวด้วย ให้ตั้ง `centre_length=True`"""),
("code", '''measured = G.build_room_model(bounds, cls, rack, T, info)
model = G.symmetrize_model(measured, centre_width=True, centre_length=False, round_to=0.01)
cmp = pd.DataFrame({
    "measured": dict(room_W=measured["room"]["W"], rack_y0=measured["rack"]["y0"], rack_y1=measured["rack"]["y1"],
                     aisle_left=measured["rack"]["y0"], aisle_right=measured["room"]["W"] - measured["rack"]["y1"],
                     rack_centre_offset=(measured["rack"]["y0"] + measured["rack"]["y1"]) / 2 - measured["room"]["W"] / 2),
    "model (symmetric)": dict(room_W=model["room"]["W"], rack_y0=model["rack"]["y0"], rack_y1=model["rack"]["y1"],
                     aisle_left=model["rack"]["y0"], aisle_right=model["room"]["W"] - model["rack"]["y1"],
                     rack_centre_offset=(model["rack"]["y0"] + model["rack"]["y1"]) / 2 - model["room"]["W"] / 2),
}).round(3)
path = io.save_model(model)
print("saved", path)
display(cmp)
import json; print(json.dumps({k: v for k, v in model.items() if k not in ("transform_scan_to_room", "measured")}, indent=2, ensure_ascii=False))'''),
("md", "## 6. Segment จุดเป็น พื้น / เพดาน / ผนัง 4 ด้าน / ชั้นปลูกแต่ละชั้น"),
("code", '''labels = G.segment_points(P, N, model)
names = G.label_names(model)
u, c = np.unique(labels, return_counts=True)
seg = pd.DataFrame({"label": [names[k] for k in u], "points": c, "share %": (100 * c / c.sum()).round(1)})
seg'''),
("code", '''# plan view coloured by label (English labels for publication)
palette = {0: "#d0d0d0", 1: "#9ecae1", 2: "#c7c7c7", 3: "#fdae6b", 4: "#fdae6b", 5: "#fdd0a2", 6: "#fdd0a2"}
tier_cols = ["#1b7f3b", "#41ab5d", "#74c476", "#a1d99b", "#c7e9c0", "#e5f5e0"]
for t in model["rack"]["tiers"]: palette[10 + t["index"]] = tier_cols[(t["index"] - 1) % len(tier_cols)]
idx = viz.subsample(len(P), 300000)
fig, ax = plt.subplots(figsize=(16, 7))
for k in u:
    m = labels[idx] == k
    ax.scatter(P[idx][m, 0], P[idx][m, 1], s=0.3, c=palette[k], label=names[k], linewidths=0)
ax.set_aspect("equal"); ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
ax.set_title("Semantic segmentation — plan view (room frame)")
ax.legend(markerscale=20, ncol=2, fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5))
fig.tight_layout(); fig.savefig(FIG / "02_segmentation_plan.png", dpi=150)'''),
("md", "## 7. ตรวจสอบ: ซ้อน parametric model (กล่องห้อง + ชั้นปลูก) บน point cloud"),
("code", '''traces = [viz.points_trace(P, RGB, n=80000, size=1.4, name="point cloud")] + viz.model_traces(model)
fig3d = viz.figure_3d(traces, title="Parametric room model over the aligned point cloud (room frame, Z up)")
viz.show3d(fig3d, "02_room_model")'''),
("md", "ถ้าแผ่นสีเขียว (ชั้นปลูก) และกรอบห้องทับกับจุดพอดี แปลว่า alignment และการตรวจจับใช้ได้ — ตัวเลขทั้งหมดอยู่ใน `room_model.json`"),
("md", "## 8. ตรวจความแม่นยำเชิงตัวเลข: ระยะเบี่ยงเบนของจุดผนัง/พื้น/เพดานจากระนาบโมเดล"),
("code", '''L, W, H = model["room"]["L"], model["room"]["W"], model["room"]["H"]
resid = {
    "floor (z=0)": P[labels == 1, 2], "ceiling (z=H)": P[labels == 2, 2] - H,
    "wall x=0": P[labels == 3, 0], "wall x=L": P[labels == 4, 0] - L,
    "wall y=0": P[labels == 5, 1], "wall y=W": P[labels == 6, 1] - W,
}
pd.DataFrame({k: dict(n=len(v), mean_cm=100 * v.mean(), std_cm=100 * v.std(), p95_abs_cm=100 * np.percentile(np.abs(v), 95))
              for k, v in resid.items()}).T.round(2)'''),
("md", "std ระดับ 2–4 ซม. เป็นค่าปกติของ LiDAR มือถือ — ถ้าค่า mean ห่างจาก 0 มากกว่า ~3 ซม. แปลว่าตำแหน่งผนังในโมเดลควรปรับ"),
("md", """### ความไม่ตั้งฉากของผนังจาก scan drift
LiDAR มือถือสะสม drift ระหว่างเดินสแกน ทำให้ผนังที่จริงขนานกันอาจไม่ขนานในข้อมูล ตรวจด้วยการ fit เส้นผ่านจุดผนังแต่ละด้าน:
`tilt_deg` = มุมเอียงที่เหลือหลัง align, `span_cm` = ระยะที่ผนังเบี่ยงไปตลอดความยาว"""),
("code", '''tilts = pd.DataFrame(G.wall_tilts(P, N, model)).T.round(2)
tilts'''),
("md", "ถ้า `span_cm` อยู่ในระดับ ≤ 10 ซม. การใช้กล่องสี่เหลี่ยมแทนห้องยังเหมาะสมสำหรับ twin (โซนปลูกกว้างระดับเมตร) — แต่ควรรายงานเป็นข้อจำกัดของข้อมูลในบทความ และหากต้องการความแม่นยำสูงกว่านี้ ให้สแกนใหม่แบบวนปิด loop (loop closure) หรือใช้ terrestrial scanner"),
("md", """## 9. ตรวจสอบข้ามกับสแกนชุดที่ 2 (`SIS PFAL2.ply`, สแกนซ้ำห้องเดิม 13 ก.ย. 2026)
ไฟล์ที่ 2 ไม่มี normal (ประมาณด้วย open3d) — รัน pipeline เดียวกันแล้วเทียบขนาดห้อง/ชั้น/rack กับสแกนแรก เพื่อประเมินความคลาดเคลื่อนของ LiDAR มือถือแบบอิสระ"""),
("code", '''pc2 = io.load_ply(io.RAW / "pointcloud" / "SIS PFAL2.ply")
T2, info2 = G.align_room(pc2["xyz"], pc2["normals"])
P2 = G.apply_T(T2, pc2["xyz"]); N2 = G.apply_T_normals(T2, pc2["normals"])
b2 = G.interior_bounds(P2, N2); k2 = G.crop_to_room(P2, b2); P2, N2 = P2[k2], N2[k2]
lv2, _, _ = G.detect_horizontal_levels(P2, N2); cls2 = G.classify_levels(lv2, b2["H"]); rack2 = G.rack_footprint(P2, N2, cls2["tiers"])
rows = {"room L": (measured["room"]["L"], b2["L"]), "room W": (measured["room"]["W"], b2["W"]), "room H": (measured["room"]["H"], b2["H"]),
        "rack length": (measured["rack"]["length"], rack2["x1"] - rack2["x0"]), "rack width": (measured["rack"]["width"], rack2["y1"] - rack2["y0"]),
        "rack x0": (measured["rack"]["x0"], rack2["x0"]), "rack y0": (measured["rack"]["y0"], rack2["y0"])}
for t1, z2 in zip(measured["rack"]["tiers"], cls2["tiers"]):
    rows[f"tier {t1['index']} z"] = (t1["z"], z2)
rows["top frame z"] = (measured["rack"]["top_frame_z"], cls2["top_frame"])
cmp2 = pd.DataFrame(rows, index=["scan 1 (SIS PFAL.ply)", "scan 2 (SIS PFAL2.ply)"]).T
cmp2["diff cm"] = 100 * (cmp2.iloc[:, 1] - cmp2.iloc[:, 0])
cmp2.round(3).to_csv(io.MODEL_DIR / "scan_comparison.csv")
print(f"scan 2: {len(pc2['xyz']):,} points, {k2.sum():,} inside the room | max |diff| = {cmp2['diff cm'].abs().max():.1f} cm")
cmp2.round(3)'''),
("md", "ทั้งสองสแกนต่างกันระดับ ≤ 5–8 ซม. (ผนัง W ต่างมากสุดเพราะ scan drift) — ยืนยันว่า `room_model.json` จากสแกนแรกใช้ได้ และเป็นตัวเลขความไม่แน่นอนที่ควรรายงานในบทความ"),
("md", """## 9b. เทียบกับแปลนออกแบบ (`data/raw/doc/Plan Layout PFAL SISKU.pdf` — แปลนที่ใช้วางแผน ไม่ใช่ as-built)
ค่าจากแปลนเก็บใน `data/model/design_spec.json` รายละเอียดใน `docs/DESIGN_VS_BUILT.md`"""),
("code", '''design = io.load_model("design_spec.json")["room_design"]
cmp3 = pd.DataFrame({"design drawing (m)": [design["L"], design["W"], design["H"]],
                     "as-built scan 1 (m)": [measured["room"]["L"], measured["room"]["W"], measured["room"]["H"]],
                     "as-built scan 2 (m)": [b2["L"], b2["W"], b2["H"]]}, index=["room L", "room W", "room H"]).round(2)
cmp3["built - design (m)"] = (cmp3["as-built scan 1 (m)"] - cmp3["design drawing (m)"]).round(2)
cmp3'''),
("md", "ความยาวต่างกัน 1.78 ม. **ไม่ใช่สร้างสั้นกว่า** — อาคารยาว 8.9 ม. ตามแปลน แต่ถูกกั้นเป็น**ห้องหน้าสำหรับวางซิงค์ (~1.78 ม.)** ก่อนถึงประตูห้องปลูก ซึ่ง point cloud ไม่ได้สแกน (ผังใน notebook 03 แสดงเป็นพื้นที่ 'not scanned'); ความสูงต่ำกว่าแปลน 0.27 ม. จำนวนถาด/LED ต่อชั้นในแปลน (141 โมดูล) จึงใช้กับ rack จริง 5.43 ม. ไม่ได้โดยตรง ต้องนับหน้างาน"),
("md", "## 10. บันทึก point cloud ที่ทำความสะอาดแล้ว + label"),
("code", '''out = io.save_clean(P, N, RGB, labels)
print("saved", out, f"({out.stat().st_size/1e6:.1f} MB)")'''),
("md", """## สิ่งที่ควรยืนยันด้วยตลับเมตร (เขียนค่าจริงลง `room_model.json` ถ้าต่างกัน)
| รายการ | ค่าจากสแกน |
|---|---|
| ความยาวห้อง (L) | ดูข้อ 2 |
| ความกว้างห้อง (W) | ดูข้อ 2 |
| ความสูงพื้น–เพดาน (H) | ดูข้อ 2 |
| ขนาดชั้นปลูก (ยาว × กว้าง) | ดูข้อ 4 |
| ความสูงชั้น 1–5 จากพื้น | ดูข้อ 3 |

**ถัดไป — Notebook 03**: แบ่งโซน (ชั้น × ช่วงความยาว) และวางตำแหน่งเซ็นเซอร์ XY-MD02 ทั้ง 5 ตัว, CO₂ controller, Grow Controller ลงในพิกัดห้องนี้"""),
])


# ----------------------------------------------------------------------------- 03
nb03 = nb([
("md", """# 03 — โซนปลูก + แผนที่เซ็นเซอร์และอุปกรณ์ (L1 → L2)

**เป้าหมาย**: วาง "สิ่งที่วัด" ลงบน "รูปทรงห้อง" — แบ่งชั้นปลูกเป็นโซน, กำหนดตำแหน่งเซ็นเซอร์ XY-MD02 ทั้ง 5 ตัว / กล่องควบคุม / อุปกรณ์อื่นในพิกัดห้อง แล้วบันทึกเป็นไฟล์ที่ notebook 04–05 ใช้ผูกข้อมูล IoT กับตำแหน่ง

ผลลัพธ์
- `data/model/zones.json` — โซน = ชั้น × ช่วงความยาว (5 × 3 = 15 โซน) + voxel grid ของอากาศในห้อง
- `data/sensors/equipment_map.csv` — กล่องอุปกรณ์ (แอร์, ถัง, ตู้ไฟ, พัดลม, ประตู…) ในพิกัดห้อง
- `data/sensors/sensor_map.csv` — ตำแหน่งเซ็นเซอร์/กล่อง IoT + โซนที่สังกัด

ที่มาของตำแหน่ง (รวมอยู่ใน `pfal_twin/layout.py`)
1. การวิเคราะห์ point cloud + dashboard + พฤติกรรมข้อมูล (แผน §1.6) — เขียนในพิกัดสแกน แปลงด้วย `transform_scan_to_room`
2. **ภาพถ่ายหน้างาน 13 ก.ย. 2026** 2 ชุด (IMG_2518–2533 และ IMG_2534–2552 ใน `data/raw/picture/`, สรุปใน `docs/SITE_SURVEY_2026-09-13.md`) — ยืนยัน/แก้ไข/เพิ่มรายการ คอลัมน์ `verified=True` เมื่อภาพเห็นชัด, `confidence=medium` เมื่อกะตำแหน่งจากภาพ (±0.3 ม.)

โครงสร้างระบบที่ได้จากป้ายกล่องควบคุม (ภาพชุด 2)
- **ชั้นล่าง (tier 1)** = ระบบอนุบาล: **อนุบาล 1 = ฝั่งประตู (T1-N1)**, **อนุบาล 2 = ฝั่งถังสารอาหารชั้นปลูก (T1-N2)** แต่ละฝั่งมีถัง 100 L ใต้ชั้นของตัวเอง, กล่องพัดลม "ชั้นล่าง"; **อนุบาล 2 คุมด้วย gc2** (ชุดปุ๋ยข้าง rack), อนุบาล 1 ไม่มีตัวควบคุม
- **4 ชั้นบน (tier 2–5) = ผัก Growing stage** ระบบร่วม ถัง 200 L: กล่องพัดลม "4 ชั้น" (FAN1–4), **Grow Controller gc1** ที่ปลาย rack (ยืนยัน 14 ก.ย. — ป้ายบน dashboard "ชั้นปลูกที่ 1/2-5" ไม่ตรงกับความจริง)
- **ชั้นเพาะเมล็ด** (ป้ายกล่องพัดลม "อนุบาลพืช") = ชั้นวาง 3 ชั้นมุมห้อง (หลอด T5) มีกล่องพัดลมของตัวเอง — ตรงกับ "ชั้นเพาะเมล็ด" ในแปลนหน้า 7

> ⚠️ **XY-MD02 ติดผนัง** — พบตัวเครื่อง 4 ตัว (ข้างจอ CO₂ W1, ใต้แอร์ 1 W2, ถัดจากแอร์ 1 ไปทางปลายห้อง W3, นอกห้อง W6) ขณะที่ gateway รายงาน 5 address (`xy_md_20–24`) → ตัวที่ 5 **อยู่ห้องหน้า เหนือประตู** (W4, ภาพ 2587 — ยืนยันแล้ว) ครบ 5 ตัว; ยังไม่รู้ว่า address ไหนคือตัวไหน; `thingsboard.TIER_SENSOR` คงสมมติฐาน "1 ช่อง/ชั้น" ไว้ให้ notebook 04–05 รันได้เท่านั้น"""),
("code", SETUP),
("md", "## 1. โหลดโมเดลห้อง + point cloud ที่จัดแนวแล้ว"),
("code", '''model = io.load_model()
pc = io.load_clean(); P, RGB, LAB = pc["xyz"], pc["rgb"], pc["labels"]
R, K = model["room"], model["rack"]
print(f"room {R['L']} x {R['W']} x {R['H']} m | rack {K['length']} x {K['width']} m, {len(K['tiers'])} tiers | {len(P):,} points")'''),
("md", """## 2. โซนปลูก: ชั้น × ช่วงความยาว
ชั้น 2–5 (**Growing stage**, `stage="growing stage"` ใน zones.json) แบ่งเป็น 3 ช่วงตามความยาว rack (S1 = ด้านประตู X≈0, S3 = ปลายห้อง); **ชั้น 1 แบ่งตามรอยต่อถาดจริงที่ X ≈ 2.22 ม.: T1-N1 อนุบาล 1 (ประตู, ~1.4 ม., ถาด 3 ร่องมีน้ำขัง) / T1-N2 อนุบาล 2 (ปลายห้อง, ~3.9 ม., ถาดเทา)** — สัดส่วนตรงกับแปลนหน้า 7; แต่ละฝั่งมีถัง 100 L ของตัวเอง (ดูรูปตัดในข้อ 2b) แต่ละโซนคือกล่องเหนือแผ่นชั้นสูง 0.35 ม. (ระยะ canopy)"""),
("code", '''NURSERY_SPLIT_X = 2.22     # boundary nursery 1 | nursery 2 on tier 1, measured in the point cloud (tray gap at X 2.15-2.30)
zones = G.make_zones(model, n_segments=3, canopy_height=0.35, segments_per_tier={1: 2}, splits={1: [NURSERY_SPLIT_X]})
grid = G.air_grid(model, dx=0.5)
io.save_model(dict(zones=zones, air_grid=grid, n_segments=3, segments_per_tier={"1": 2}, splits={"1": [NURSERY_SPLIT_X]}, canopy_height=0.35), name="zones.json")
print(f"{len(zones)} zones, air grid {grid['nx']} x {grid['ny']} x {grid['nz']} = {grid['n_cells']} cells of {grid['dx']} m")
pd.DataFrame(zones).head(6)'''),
("md", "### 2b. หลักฐานจุดแบ่งอนุบาล 1 / 2 — รูปตัดชั้น 1 ตามความยาวจาก point cloud"),
("code", '''sel = (P[:, 1] > K["y0"] + 0.05) & (P[:, 1] < K["y1"] - 0.05) & (P[:, 2] > 0.30) & (P[:, 2] < 0.75)
fig, axes = plt.subplots(2, 1, figsize=(18, 7.5))
axes[0].scatter(P[sel, 0], P[sel, 2], s=0.6, c=RGB[sel] / 255.0, linewidths=0); axes[0].set_ylim(0.3, 0.75); axes[0].set_ylabel("Z (m)")
axes[0].set_title("Tier 1 side profile (X–Z, rack interior, true colour): nursery-1 trays (3 channels, olive) end at X ≈ 2.15 m; nursery-2 trays (grey) start at X ≈ 2.30 m")
sl = sel & (P[:, 2] > 0.38) & (P[:, 2] < 0.50)
axes[1].scatter(P[sl, 0], P[sl, 1], s=0.8, c=RGB[sl] / 255.0, linewidths=0); axes[1].set_ylabel("Y (m)"); axes[1].set_title("Tier 1 plan view, z 0.38–0.50 m")
for ax in axes:
    ax.axvline(NURSERY_SPLIT_X, color="#d62728", ls="--", lw=1.5); ax.text(NURSERY_SPLIT_X + 0.03, ax.get_ylim()[1] - 0.02, f"split X = {NURSERY_SPLIT_X} m", color="#d62728", va="top", fontsize=8)
    ax.set_xlim(0.6, 6.4); ax.set_aspect("equal"); ax.grid(alpha=.3); ax.set_xlabel("X (m)")
fig.tight_layout(); fig.savefig(FIG / "03_tier1_nursery_split.png", dpi=150)'''),
("md", """## 3. อุปกรณ์ในห้อง — scan + ภาพถ่าย → พิกัดห้อง
รายการใน `layout.EQUIPMENT` ระบุ `frame="scan"` (จากการวิเคราะห์ point cloud, แปลงด้วย `transform_scan_to_room`) หรือ `frame="room"` (กะจากภาพถ่าย) — ย้ายจุดใน PLY หรือแก้ตัวเลขแล้วรันใหม่ได้ทันที"""),
("code", '''eq = layout.equipment_room(model)
print(f"{len(eq)} items, {eq.verified.sum()} verified by photos")
eq[["name", "category", "frame", "x0", "x1", "y0", "y1", "z0", "z1", "confidence", "verified"]]'''),
("md", "### ตรวจกล่องระดับพื้นกับ point cloud — ชั้นตัดขวาง z 0.04–0.36 ม. (ใต้แผ่นชั้น 1) ซ้อนกรอบอุปกรณ์ที่ z0 < 0.36"),
("code", '''sl = (P[:, 2] > 0.04) & (P[:, 2] < 0.36)
idx = np.where(sl)[0]; idx = idx[:: max(1, len(idx) // 250000)]
fig, ax = plt.subplots(figsize=(19, 7))
ax.scatter(P[idx, 0], P[idx, 1], s=0.4, c=RGB[idx] / 255.0, linewidths=0)
ax.add_patch(plt.Rectangle((K["x0"], K["y0"]), K["length"], K["width"], fill=False, ec="#2a7d2a", lw=1.5, ls="--"))
eq_key, _ = viz.layout_key(eq)                      # same numbers as the layout figure
low = eq[eq.z0 < 0.36]
for _, r in low.iterrows():
    ax.add_patch(plt.Rectangle((r.x0, r.y0), r.x1 - r.x0, r.y1 - r.y0, fill=False, ec="#d62728", lw=1.5))
    ax.annotate(eq_key[r["name"]], (r.x0, r.y1), xytext=(3, -10), textcoords="offset points", fontsize=8, fontweight="bold", color="#d62728")
ax.text(1.01, 1, "\\n".join(f"{eq_key[n]:>2}  {n}" for n in low["name"]), transform=ax.transAxes, va="top", fontsize=8, family="monospace")
ax.set_aspect("equal"); ax.set_xlim(-0.1, R["L"] + 0.1); ax.set_ylim(-0.1, R["W"] + 0.1)
ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)"); ax.set_title("Floor-level slab of the point cloud (z 0.04–0.36 m) with floor-standing equipment boxes (red, numbered as in the layout key)")
fig.savefig(FIG / "03_floor_slab_check.png", dpi=150, bbox_inches="tight")'''),
("md", "ถังอนุบาลทั้งสองใบ (100 L) เห็นชัดใน point cloud (อนุบาล 1 ที่ X≈1.4–1.9 ฝั่งประตู, อนุบาล 2 ที่ X≈5.4–5.9 ฝั่งถังชั้นปลูก; ~0.5 × 0.7 × 0.33 ม.) — ขนาดใน `layout.py` อ้างอิงจากภาพนี้"),
("md", "## 3b. ภาพถ่ายหน้างาน (13 ก.ย. 2026) — contact sheet 2 ชุด สำหรับอ้างอิงในบทความ / ตรวจสอบตำแหน่ง"),
("code", '''import textwrap
from PIL import Image, ImageOps          # EXIF orientation of phone photos
PHOTOS = io.RAW / "picture" / "jpg"          # สร้างด้วย  sh scripts/photos_to_jpg.sh
SHEETS = {
 "03_site_photos_1.png": ("Site photos, 13 Sep 2026 (set 1, 10:45-10:49) — room, walls, controllers", {
    "IMG_2519": "Exterior: PFAL unit attached to SISKU Coffee (the grow-room windows face the cafe)",
    "IMG_2520": "Y=0 aisle: router on the wall, portable dehumidifier, windows and seed-germination shelf at the far end",
    "IMG_2521": "CO2 & environment controller: display, sensor box 3-OT-N000526, junction box with XY-MD02 W1",
    "IMG_2522": "Grow Controller Plus on the rack; LED bars (white + red) under every tier",
    "IMG_2523": "Dosing box A: pumps A/B 500 mL/min, pH 85 mL/min; 3 % nitric-acid jerrycan",
    "IMG_2524": "Sample pot with pH probe and EC / water-temperature probe",
    "IMG_2526": "Far end, Y=W aisle: Grow Controller gc2 (nursery-2 dosing set) on the rack side, stock-solution jerrycans, wall taps",
    "IMG_2527": "Grow Controller gc1 (growing stage, rack end) screen: EC 1.75, pH 5.7, day 16 (= ThingsBoard gc1 at 10:47)",
    "IMG_2528": "Far end corner: 200 L growing tank with probe box, gc1 on the rack end wired to it, seed-germination shelf",
    "IMG_2530": "Y=0 wall: two glass windows with heavy condensation (thermal bridge to the cafe)",
    "IMG_2531": "Door: aluminium with glass upper half, X=0 wall, Y=0 side",
    "IMG_2533": "Y=W aisle: CO2 controller by the door, two AC units, circulation-fan panels at the rack ends"}),
 "03_site_photos_3.png": ("Site photos, 13 Sep 2026 (set 3) — outside, pipework (blue nutrient supply / white tap + RO water)", {
    "IMG_2553": "OUTSIDE, front porch: two CO2 cylinders with heated regulator, control box, door",
    "IMG_2554": "OUTSIDE: CO2 control box (green pilot lamp), a sixth XY-MD02 mounted outdoors, LPM flowmeter and regulator heater",
    "IMG_2555": "Blue 1.5-inch supply on the floor turning under tier 1 into reservoir box A; white tap/RO lines on the floor and at 0.3 m",
    "IMG_2557": "Blue riser at the rack far end with a tee at every tier",
    "IMG_2558": "Blue supply elbows into the blue reservoir box under tier 1",
    "IMG_2559": "Far-end floor: white lines from the wall taps, blue manifold with valves, tank",
    "IMG_2561": "Tier feed: blue branch from the riser across the tier end into the tray",
    "IMG_2565": "Blue 1.5-inch pipe between the far-end tank and reservoir box B",
    "IMG_2566": "Two wall valves on the X=L wall labelled tap water (left) and RO water (right)",
    "IMG_2567": "Tank connections: blue outlet with green valves, white fill line with red valve, white lines on the floor",
    "IMG_2568": "Y=W aisle: blue nutrient main on the floor, the two white tap / RO lines next to the rack + one at 0.3 m; fan control boxes above",
    "IMG_2570": "Door end of a tier: white 1-inch fill header with red ball valves teeing into the tray from above, white riser (the rack frame is the same cream PVC!)",
    "IMG_2573": "Door-end fill header of another tier, circulation-fan panel above"}),
 "03_site_photos_2.png": ("Site photos, 13 Sep 2026 (set 2, 11:53-12:04) — tier 1, sensors, control boxes", {
    "IMG_2534": "Tier 1 is split in two halves: NFT channels with water (far half) and flat trays; blue reservoir box underneath",
    "IMG_2535": "Two blue reservoir boxes under tier 1 (one per half) with the supply / return piping",
    "IMG_2536": "XY-MD02 close-up (RS485, DC 5-30 V) — the same unit as W2 in IMG_2537",
    "IMG_2537": "XY-MD02 W2 on the Y=W wall below AC indoor unit 1",
    "IMG_2538": "XY-MD02 W3 beside two vertical conduits on the Y=W wall, just past AC unit 1 towards the far end",
    "IMG_2539": "CO2 controller assembly: display, sensor box, junction box (RS485 cables converge) with XY-MD02 W1",
    "IMG_2541": "Dosing box A with sample pot; jerrycans A, B, nitric acid and water below",
    "IMG_2542": "Dosing box B with Jecod 50 W DC pump controller; blue reservoir box under tier 1 behind",
    "IMG_2543": "Sample pot on the far-end tank (EC / pH probes into the tank)",
    "IMG_2544": "Far-end floor piping: tank, valves, wall taps and stock jerrycans",
    "IMG_2545": "Fan control boxes on the rack side (Y=W aisle) — 'lower tier' box in front, '4 tiers' box behind; exhaust fan on the X=0 wall",
    "IMG_2546": "Fan control box labelled 'lower tier' (tier 1): one FAN switch, 12 V fan",
    "IMG_2547": "Fan control box labelled '4 tiers': switches FAN1-FAN4 = tiers 2-5",
    "IMG_2548": "Fan control box labelled 'nursery plants': 3 switches, for the seed-germination shelf",
    "IMG_2550": "TP-Link WiFi router (WiFi uplink of the grow controllers)",
    "IMG_2552": "Hand-held Testo 608-H1 on a tray: 22.4 °C / 49.1 % RH at 12:04 (reference reading)",
    "IMG_2584": "White 1-inch line at 0.3 m rises through a red ball valve into the nursery-2 tray (door end of T1-N2), beside the '4 tiers' fan box",
    "IMG_2585": "White 1-inch pipe across the 200 L tank lid with a tee dropping into the tank = pump outlet",
    "IMG_2586": "Anteroom: window and glass door into the grow room, wall cabinet, stored trays",
    "IMG_2587": "XY-MD02 W4 with junction box above the door on the anteroom side (5th reporting unit)"}),
}
for fname, (title, captions) in SHEETS.items():
    n = len(captions); ncol = 4; nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(20, 4.9 * nrow))
    for ax, (name, cap) in zip(axes.flat, captions.items()):
        f = PHOTOS / f"{name}.jpg"
        if f.exists(): ax.imshow(ImageOps.exif_transpose(Image.open(f)))
        ax.set_title(f"{name}\\n" + "\\n".join(textwrap.wrap(cap, 48)), fontsize=7.5, loc="left"); ax.axis("off")
    for ax in axes.flat[n:]: ax.axis("off")
    fig.suptitle(title, y=0.995, fontsize=12)
    fig.tight_layout(); fig.savefig(FIG / fname, dpi=100)'''),
("md", """## 4. ตำแหน่งเซ็นเซอร์
- **ยืนยันจากภาพ**: CO₂ controller (ผนัง Y=W ใกล้ประตู), gateway (ผนัง Y=0, X≈2), gc1 (ปลาย rack สายเข้าถัง 200 L = growing — ตรวจด้วยค่าบนจอเทียบ ThingsBoard), gc2 (ข้าง rack เหนือ dosing box = อนุบาล 2), เซ็นเซอร์ระดับน้ำที่ถังพัก, XY-MD02 1 ตัวบนผนังข้างจอ CO₂ (ยังไม่รู้ address)
- **ช่องข้อมูล `xy_md_20…24` (5 ช่อง) ยังไม่ผูกกับตัวเครื่อง** — ภาพพบ XY-MD02 จริง **4 ตัว** (W1 ข้างจอ CO₂, W2 ใต้แอร์ 1, W3 ถัดจากแอร์ 1 ไปทางปลายห้อง, W6 นอกห้อง) แต่ gateway รายงาน 5 address → มีอย่างน้อย 1 ตัวที่ยังไม่ได้ถ่ายภาพ; **ไม่วาดช่องข้อมูลเป็นจุดแยก**ในผังอีก; `thingsboard.TIER_SENSOR` (20→ชั้น 1 … 24→ชั้น 5) คงไว้เป็นสมมติฐานให้ notebook 04–05 รันได้ และ `xy_md_24` (แกว่งวันละ 7 °C พีค 13:00) น่าจะเป็นตัวนอกห้อง W6"""),
("code", '''sensors = layout.sensor_map(model, zones, eq)
p1, p2 = layout.save_layout(sensors, eq)
pd.DataFrame(layout.REFERENCE_READINGS).to_csv(io.SENSOR_DIR / "reference_readings.csv", index=False)   # hand-held Testo readings
print("saved", p1.name, ",", p2.name, "and reference_readings.csv in", p1.parent)
sensors[["sensor", "device", "tier", "x", "y", "z", "zone", "placed_on", "confidence", "verified", "evidence"]]'''),
("md", "## 5. ผัง 2 มิติ (plan + side elevation) — อุปกรณ์เป็นหมายเลข, เซ็นเซอร์เป็นตัวอักษร, ท่อตามสีชนิด (ฟ้า = ท่อจ่ายขาวจากปั๊มถัง 200 L, ฟ้าอ่อน = ท่อยืน/หัวจ่ายพร้อมวาล์ว, เขียว = ในถาด, น้ำเงิน = น้ำกลับ, ม่วงเทา dash-dot = ท่อรวม drain/ล้นบนพื้น, จุด = ระบายทิ้ง, ส้ม/ฟ้าซีด = ประปา/RO, เส้นประ = สายปั๊มอนุบาลที่ยังไม่เห็น), คำอธิบายอยู่ด้านขวา"),
("code", '''net = H.build_network(model, zones)          # pipework (detail + flow animation in notebook 03b)
fig = plt.figure(figsize=(27, 17))
gs = fig.add_gridspec(2, 2, width_ratios=[3.3, 1], height_ratios=[1.25, 1], wspace=0.01, hspace=0.12)
ax_plan, ax_key, ax_elev = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[:, 1]), fig.add_subplot(gs[1, 0])
viz.plan_layout(model, zones, eq, sensors, ax=ax_plan, key_ax=ax_key, net=net)
# elevation: room + anteroom + porch only (the outside RO plant is schematic and clutters the section)
viz.elevation_layout(model, P, RGB, eq[eq.location != "outside_far"], sensors[sensors.location != "outside_far"], ax=ax_elev, net=net)
fig.savefig(FIG / "03_layout_plan.png", dpi=170, bbox_inches="tight")'''),
("md", "## 6. ภาพ 3 มิติ: โมเดล + โซน + อุปกรณ์ + เซ็นเซอร์ + ท่อ ซ้อน point cloud (hover ดูหลักฐาน/ความมั่นใจ; คลิก legend เพื่อซ่อน/แสดงแต่ละชั้นข้อมูล)"),
("code", '''traces = ([viz.points_trace(P, RGB, n=60000, size=1.2, name="point cloud", opacity=0.5)]
          + viz.model_traces(model) + viz.zone_traces(zones, opacity=0.15)
          + viz.equipment_traces(eq) + H.pipe_traces(net) + H.fitting_traces(net) + [viz.sensor_trace(sensors, text=sensors["evidence"])])
fig3d = viz.figure_3d(traces, title="Zones, equipment, sensors and pipework in the room frame")
viz.show3d(fig3d, "03_zones_equipment_sensors")'''),
("md", """## สถานะการยืนยัน (หลังดูภาพ 2 ชุด 13 ก.ย. 2026 — รายละเอียดใน `docs/SITE_SURVEY_2026-09-13.md`)
| รายการ | สถานะ |
|---|---|
| แอร์ 2 ตัว, ประตู, ชั้นเพาะเมล็ดมุมห้อง, ถังปลายห้อง, พัดลมระบายอากาศ | ✅ ตรงกับ scan |
| "แผงมืด" บนผนัง Y=0 | ✅ = **หน้าต่างกระจก 2 บาน** หันเข้าร้านกาแฟ มีไอน้ำเกาะ (thermal bridge) |
| "ตู้ควบคุม" ใกล้ประตู | ✅ = **CO₂ & environment controller** + กล่องต่อสาย RS485 (น่าจะเป็นที่อยู่ของ gateway) + XY-MD02 W1 |
| ชั้น 1 | ✅ อนุบาล 1 (ฝั่งประตู, T1-N1, X 0.77–2.22) / อนุบาล 2 (ฝั่งถังชั้นปลูก, T1-N2, X 2.22–6.20) จุดแบ่งวัดจาก point cloud; แต่ละฝั่งมีถัง 100 L ใต้ชั้น; ระบบแยกจากชั้น 2–5 (กล่องพัดลม "ชั้นล่าง"; อนุบาล 2 = gc2, อนุบาล 1 ไม่มีตัวควบคุม) |
| ชั้น 2–5 | ✅ **ผัก Growing stage** ระบบร่วม ถัง 200 L (กล่องพัดลม "4 ชั้น" FAN1–4, **gc1**) |
| ถังสต็อกปุ๋ย | ✏️ แกลลอน 5–10 ลิตรบนพื้นปลายห้อง; dosing box 2 ชุด + sample pot 3 จุด |
| Grow Controller | ✅ **gc1 ปลาย rack = ถัง 200 L growing** (ยืนยันด้วยค่าบนจอ + สาย + คำยืนยัน 14 ก.ย.), **gc2 ข้าง rack = ชุดปุ๋ยอนุบาล 2** |
| กล่องเสาอากาศ | ✏️ เป็น **TP-Link WiFi router** ไม่ใช่ gateway |
| XY-MD02 | ✅ ครบ 5 ตัว = 5 address: W1 ข้างจอ CO₂, W2 ใต้แอร์ 1, W3 ถัดจากแอร์ 1 ไปทางปลายห้อง (X≈5.65), **W4 ห้องหน้าเหนือประตู (2587)**, W6 นอกห้อง; address ↔ ตัวเครื่องยังไม่รู้; เดา `xy_md_24` = W6 (นอกห้อง), `xy_md_20` = W4 (ห้องหน้า), 21–23 = W1–W3 (ในห้อง) |
| ห้องหน้า (ซิงค์) | อาคาร 8.9 ม. ตามแปลน กั้นเป็นห้องหน้า ~1.78 ม. ก่อนประตูห้องปลูก — **ไม่ได้สแกน** แสดงเป็นแถบลายในผัง |
| นอกอาคาร (หน้าห้องหน้า) | ถัง CO₂ 2 ถัง + regulator/flowmeter + กล่องควบคุม CO₂ + XY-MD02 W6 — แสดงเป็นแถบ "OUTSIDE" ในผัง |
| ค่าอ้างอิง | Testo 608-H1 บนถาดชั้น 2–3 เวลา 12:03–12:04: 22.4–22.5 °C / 49–52 % (CO₂ controller ผนัง 11:52: 23.4 °C / 59.5 %; gateway offline ตั้งแต่ 07:44) |

**ที่ต้องทำหน้างานครั้งถัดไป (~15 นาที)**: เปิดหน้า dashboard บนมือถือ แล้วเอามือกุม/เป่าลมอุ่นใส่ XY-MD02 ทีละตัว (W1→W5) ดูว่า `xy_md_XX` ตัวไหนขยับ → แก้ `layout.SENSORS` และ `thingsboard.TIER_SENSOR` (ต้องรอ gateway กลับมา online)

**ถัดไป — Notebook 04**: ดึงข้อมูลย้อนหลังทั้งหมดจาก ThingsBoard, ทำ QC, เก็บเป็น Parquet"""),
])


# ----------------------------------------------------------------------------- 03b
nb03b = nb([
("md", """# 03b — ระบบท่อและการไหลของสารละลาย (Hydraulic network)

**เป้าหมาย**: ใส่ท่อน้ำลงใน twin — ท่อสีฟ้า (จ่ายสารละลาย), ราง/ถาดปลูก, ท่อสีขาว (น้ำกลับ/drain และน้ำประปาจากก๊อก) — แล้วแสดง **ทิศทางการไหล** แบบแอนิเมชันบนโมเดล 3 มิติ

ที่มา
- **ท่อสีฟ้า**: สกัดจาก point cloud ด้วยสี (~8.9k จุด) → เห็นท่อบนพื้นทางเดิน Y≈2.2, ท่อยืนที่ปลาย rack X≈6.15 พร้อมสามทางทุกชั้น, ท่อแยกลงถังใต้ชั้น 1
- **ท่อฟ้าบนพื้น = ท่อรวม drain/ล้นระหว่างถัง ไม่ใช่ท่อจ่าย** (แก้ 14 ก.ย.): ต่อกับก้นถังทั้ง 3 ใบผ่านยูเนียน+วาล์วเขียว และทะลุผนังไปทิ้งข้างนอก; **ท่อจ่าย growing คือท่อขาว 1" ที่ออกจากข้างถัง 200 L (bulkhead, ภาพ 2535) วิ่งตามหน้า rack ที่ระดับ ~0.3 ม.** ไปโคนท่อยืนขาวด้านประตู
- **ท่อสีขาว**: จากภาพถ่าย IMG_2555–2573 เท่านั้น — ⚠️ **โครง rack เป็นท่อ PVC สีครีม/ขาวเหมือนกัน** จึงแยกด้วยสีจาก point cloud ไม่ได้
- **ป้ายวาล์วบนผนัง X=L (IMG_2566)**: ซ้าย "น้ำประปา", ขวา "น้ำ RO" → ท่อขาวคู่บนพื้นทางเดินคือ **น้ำเติม 2 ชนิด** (ประปา / RO)
- **ยืนยันหน้างาน 14 ก.ย. (ตรงกับแปลนหน้า 6–7)**: ท่อขาวด้านประตู (ภาพ 2569–2573) = **"ท่อน้ำเวียนขาเข้า" growing stage** พร้อมวาล์วปรับสมดุล; ท่อยืนฟ้าปลาย rack (ภาพ 2561–2564) = **"ท่อน้ำเวียนลงถัง"** 200 L → น้ำในถาดไหล **ประตู → ปลายห้อง**
- **วงจรอนุบาล**: ถังอนุบาลแต่ละใบมีปั๊มของตัวเองตามแปลน (สายขึ้นถาดยังไม่มีภาพ → เส้นประ); หัวจ่ายอนุบาล 1 = หัวท่อขาว + วาล์วแดง 3 ตัว (2569); ถาดระบายจากก้นถาดลงท่อฟ้าตั้ง → วาล์วเขียว "ก๊อกน้ำวนถัง" → ถังของตัวเอง (2558/2565); ถังต่อท่อรวมพื้นด้วยยูเนียน+วาล์วเขียว (ถ่ายน้ำ/ล้น)
- โครงข่ายอยู่ใน `pfal_twin/hydraulics.py` (`build_network`) เป็น polyline ในพิกัดห้อง แต่ละเส้นมี `kind` (supply / supply_hdr / tray / return / return_hyp / drain / fill_tap / fill_ro), `loop` (gc1 = growing ชั้น 2–5 ถัง 200 L, gc2 = อนุบาล 2, n1 = อนุบาล 1 ไม่มีตัวควบคุม), เส้นผ่านศูนย์กลาง, และหลักฐาน

> ข้อจำกัด: **ไม่มีเซ็นเซอร์อัตราการไหล** — แอนิเมชันแสดงทิศทางและสถานะปั๊ม (`pwmWater` จาก ThingsBoard) เท่านั้น ความเร็วเป็นภาพแทน; ท่อใต้ถาด/ในถังที่มองไม่เห็นวาดตามหลักไฮดรอลิก"""),
("code", SETUP),
("md", "## 1. โหลดโมเดล + point cloud และสกัดจุดท่อสีฟ้า"),
("code", '''model = io.load_model(); zones = io.load_model("zones.json")["zones"]
sensors, eq = layout.load_layout()
pc = io.load_clean(); P, RGB = pc["xyz"], pc["rgb"]; R, K = model["room"], model["rack"]
blue = H.blue_pvc_mask(P, RGB)
print(f"blue PVC points: {blue.sum():,}")'''),
("md", "## 2. โครงข่ายท่อ (hand-modelled) — ตารางเส้นท่อ"),
("code", '''net = H.build_network(model, zones)
H.save_network(net)
tab = H.edges_table(net)
print(f"{len(tab)} edges, total {tab.length_m.sum():.1f} m"); display(tab.groupby(["kind", "loop"]).length_m.sum().round(1).to_frame("length m"))
tab[["name", "kind", "loop", "dia_mm", "length_m", "evidence"]]'''),
("md", "## 3. ตรวจสอบกับ point cloud — จุดสีฟ้าจากสแกน ซ้อนเส้นท่อของโมเดล (plan + elevation)"),
("code", '''from matplotlib.lines import Line2D
fig, axes = plt.subplots(2, 1, figsize=(18, 11), gridspec_kw=dict(height_ratios=[1, 0.85]))
for ax, (i, j, lab) in zip(axes, [(0, 1, "Y (m)"), (0, 2, "Z (m)")]):
    sc = ax.scatter(P[blue, i], P[blue, j], s=1.2, c=P[blue, 2 if j == 1 else 1], cmap="viridis", linewidths=0)
    for e in net["edges"]:
        q = np.array(e["pts"]); st = H.KIND_STYLE[e["kind"]]
        ax.plot(q[:, i], q[:, j], color=st["color"], lw=st["width"] * 0.35, alpha=0.9, solid_capstyle="round")
    ax.add_patch(plt.Rectangle((K["x0"], K["y0"] if j == 1 else 0), K["length"], K["width"] if j == 1 else K["top_frame_z"], fill=False, ec="#2a7d2a", ls="--", lw=1))
    ax.set_aspect("equal"); ax.set_xlim(-0.1, R["L"] + 0.1); ax.set_xlabel("X (m)"); ax.set_ylabel(lab); ax.grid(alpha=.25)
axes[0].set_ylim(-0.1, R["W"] + 0.1); axes[1].set_ylim(-0.05, R["H"] + 0.05)
axes[0].set_title("Pipe network vs. blue PVC points from the scan — plan view (point colour = height)")
axes[1].set_title("Side elevation (point colour = Y)")
axes[0].legend(handles=[Line2D([0], [0], color=v["color"], lw=3, label=v["name"]) for v in H.KIND_STYLE.values()] + [Line2D([0], [0], marker="o", ls="", color="#440154", label="blue PVC points (scan)")],
               fontsize=7.5, loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2, frameon=False)
plt.colorbar(sc, ax=axes[0], fraction=0.02, pad=0.01, label="z (m)")
fig.tight_layout(); fig.savefig(FIG / "03b_pipes_vs_scan.png", dpi=150)'''),
("md", "เส้นสีฟ้าของโมเดลควรทับกลุ่มจุดสแกน (ท่อเมนบนพื้น, ท่อยืน, ท่อแยกลงถัง) — เส้นสีขาว/เขียวไม่มีจุดสแกนให้เทียบ เพราะแยกสีไม่ได้และรางถูกบัง"),
("md", "### 3b. รายละเอียดมุมถังปลายห้อง (เทียบภาพ IMG_2559 / 2567) — ท่อทุกเส้น + ข้อต่อ/วาล์ว"),
("code", '''fig = viz.pipe_corner_detail(model, net, eq[eq.location == "inside"])
fig.savefig(FIG / "03b_tank_corner_detail.png", dpi=150, bbox_inches="tight")'''),
("md", "ลำดับตามภาพ 2559 + แปลน: ถัง (ปั๊ม) → ยูเนียน → สามทาง → ท่อเมนบนพื้นไปด้านประตู (จ่าย) / ท่อระบายทิ้งทะลุผนัง X=L ออกนอกห้อง (เห็นท่อฟ้าบนพื้นข้างนอกในภาพ 2553); ท่อยืนฟ้าที่มุมนี้คือ**น้ำกลับ**จากถาดทุกชั้นลงถัง; ท่อขาวประปา/RO จากวาล์วผนัง เส้นหนึ่งแยกผ่านวาล์วแดงเล็กเข้าถัง; ท่อขาวประปา/RO จากวาล์วบนผนังวิ่งตามพื้น เส้นหนึ่งแยกผ่านวาล์วแดงเล็กเข้าถัง"),
("md", "## 4. ภาพ 3 มิติ + แอนิเมชันการไหล (กด ▶ Play; ใช้ปุ่ม Full screen หรือเปิดไฟล์ html)"),
("code", '''base = viz.model_traces(model, tier_color="#dddddd") + viz.equipment_traces(eq[eq.location == "inside"], opacity=0.15)
fig3d = H.flow_figure(net, base, n_frames=24, spacing=0.25, title="Nutrient-solution flow — schematic direction (no flow sensor)")
viz.show3d(fig3d, "03b_flow_animation", height=820)'''),
("md", """## 4b. ระบบน้ำภายนอกห้อง — ภาพ IMG_2577–2579 + แปลนสไลด์ 3 ("ตำแหน่งและเส้นทางท่อน้ำดีและน้ำทิ้ง")
- **ทางเดินบริการข้างอาคาร**: ถังเก็บน้ำ RO (ถังสลิมสีเทา, แปลน 5 m³) → ปั๊มหอยโข่ง (สีเหลือง, แปลน ≥3000 L/h) → ชุดกรอง RO 3 ขั้น → ท่อฟ้า 2 เส้นวิ่งตามผนังคอนเทนเนอร์ → ทะลุผนังปลายห้องที่วาล์ว "น้ำประปา" / "น้ำ RO"
- **ท่อน้ำทิ้ง**: ท่อฟ้าออกจากผนังปลายห้องระดับพื้น วิ่งตามพื้นด้านนอก → ตามแปลนไป**ถังเก็บสารละลายใช้แล้วฝังใต้ดิน** (ยังไม่เห็นถัง)
- ตำแหน่งภายนอกในโมเดลเป็น **schematic** (ไม่ได้สแกน)"""),
("code", '''from PIL import Image, ImageOps
import textwrap
fig, axes = plt.subplots(1, 4, figsize=(22, 6.5))
for ax, (f, cap) in zip(axes, [("picture/jpg/IMG_2577.jpg", "IMG_2577 — far-end (X=L) wall outside: blue lines leave/enter at ground level"),
                               ("picture/jpg/IMG_2578.jpg", "IMG_2578 — service passage: RO storage tank (slim, grey) beside the container"),
                               ("picture/jpg/IMG_2579.jpg", "IMG_2579 — RO plant: tank -> centrifugal pump -> 3-stage filter -> lines along the wall"),
                               ("doc/../../../docs/plan_drawing/slide-3.png", "Design pptx slide 3 — routes of supply (RO / tap) and waste water")]):
    pth = io.RAW / f
    ax.imshow(ImageOps.exif_transpose(Image.open(pth))); ax.set_title("\\n".join(textwrap.wrap(cap, 46)), fontsize=8, loc="left"); ax.axis("off")
fig.tight_layout(); fig.savefig(FIG / "03b_outside_water.png", dpi=100)'''),
("md", "## 4c. ผังเฉพาะระบบน้ำและปุ๋ย — ถัง, ชุดจ่ายปุ๋ย, ตัวควบคุม, วาล์ว, ท่อทุกชนิด, RO plant และท่อทิ้งภายนอก"),
("code", '''fig = S.water_system_plan(model, net, eq, sensors)
fig.savefig(FIG / "03b_water_system_plan.png", dpi=150, bbox_inches="tight")'''),
("md", "## 4d. แผนภาพการไหลของระบบน้ำ (process flow, ไม่ตามสเกล) — เส้นทึบ = เห็นจริง/ยืนยัน, เส้นประ = สมมติ/ตามแปลน"),
("code", '''fig = S.water_flow_diagram()
fig.savefig(FIG / "03b_water_flow_diagram.png", dpi=150, bbox_inches="tight")'''),
("md", "## 5. สถานะปั๊มจากข้อมูลจริง — `pwmWater` (ปั๊มหมุนเวียน) และปั๊ม dosing ของแต่ละวงจร"),
("code", '''w = pd.read_parquet(tb.WIDE_PARQUET)
cols = [c for c in ("gc1.pwmWater", "gc2.pwmWater", "gc1.pumpA", "gc1.pumpB", "gc1.pumpPH", "gc2.pumpA", "gc2.pumpB", "gc2.pumpPH") if c in w]
st = w[cols]
duty = pd.DataFrame({"on fraction": st.mean(), "hours on": st.sum() / 6, "n bins": st.count()}).round(2); display(duty)
fig, ax = plt.subplots(figsize=(16, 3.2))
for c, col in zip(("gc1.pwmWater", "gc2.pwmWater"), ("#1f77b4", "#ff7f0e")):
    if c in st: d = st[c].resample("1D").mean(); ax.plot(d.index, d, color=col, lw=1.5, label=f"{c} (daily on-fraction)")
ax.set_ylim(-0.05, 1.05); ax.set_ylabel("fraction of day"); ax.set_title("Circulation pump state — gc1 = growing stage (200 L), gc2 = nursery 2 (100 L); state keys held forward between events"); ax.legend(); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(FIG / "03b_pump_state.png", dpi=150)'''),
("md", """## สรุป / สิ่งที่ยังไม่ยืนยัน
- วงจรปลูก (ชั้น 2–5): ปั๊มในถัง 200 L → **ท่อขาว 1" ออกข้างถัง วิ่งตามหน้า rack ที่ 0.3 ม.** → ท่อยืนขาวด้านประตู → หัวท่อ + วาล์วปรับสมดุล → ถาด (ประตู → ปลายห้อง) → กิ่งฟ้า + วาล์วแดง → ท่อยืนฟ้าปลายห้อง → ลงถัง — ยืนยันหน้างาน 14 ก.ย.
- ท่อฟ้า 1.5" บนพื้น = **ท่อรวม drain/ล้น** เชื่อมก้นถังทั้ง 3 ใบ (ยูเนียน + วาล์วเขียว) และทะลุผนังไปทิ้งข้างนอก; ท่อขาวบนพื้น 2 เส้น = น้ำประปา + น้ำ RO จากวาล์วที่มีป้าย
- **อนุบาล 2 (ภาพ 2558/2560/2544)**: ท่อฟ้าตั้ง 2 ท่อจากก้นถาดเหนือถัง — ท่อหนึ่งมีวาล์วเขียว "ก๊อกน้ำวนถัง" ลงถัง 100 L (ระบายกลับถัง), อีกท่อลงท่อรวมพื้น (ล้น/ถ่าย); ข้างถังมียูเนียน 2 ตัว (+วาล์วเขียว) ต่อท่อรวมพื้นไปมุมถัง 200 L; **dosing box A (14) ของ gc2 จ่ายปุ๋ยลงถังนี้** (ยืนยัน 14 ก.ย.) ส่วน dosing box B (15, Jecod) เป็นของ gc1 → ถัง 200 L
- **ทางเข้าถาดอนุบาล 2 (ภาพ 2584/2585/2535)**: ท่อขาว 1" ระดับ 0.3 ม. ตามหน้า rack ยกขึ้นผ่านวาล์วแดงเข้าหัวถาดที่ X≈3.3; ท่อขาวเส้นนี้ต่อกับ**ปั๊มถัง 200 L (ท่อผ่านฝาถัง, 2585)** และ **bulkhead ข้างถังอนุบาล 2 (2535)** และวิ่งต่อไปถึงท่อยืน growing ด้านประตู → ⚠️ ยังไม่รู้ว่าปั๊มถังไหนจ่ายกิ่งไหน
- **ยังไม่ยืนยัน (เส้นประ)**: สายจากปั๊มถังอนุบาล 1 ขึ้นหัวจ่าย
- ถ้าต้องการอัตราการไหลจริง: วัดด้วยถ้วยตวงที่ปลายรางแต่ละชั้น (L/min) แล้วใส่ใน `pipe_network.json` หรือติด flow meter บนท่อเมนสีฟ้า

**ถัดไป**: notebook 05 แสดงท่อพร้อมสถานะปั๊ม ณ เวลาที่เลือกบน time slider"""),
])

# ----------------------------------------------------------------------------- 04
nb04 = nb([
("md", """# 04 — นำเข้าข้อมูล IoT จาก ThingsBoard (L2 Data twin)

**เป้าหมาย**: ดึง telemetry ทั้งหมดที่ ThingsBoard (cat-smartgrow.com) เก็บไว้ของอุปกรณ์ 4 ตัวในห้อง → เก็บสำเนาในเครื่อง → ทำความสะอาด → ตารางเวลา 10 นาที พร้อมใช้กับ twin

ไฟล์ที่ได้
- `data/raw/iot/thingsboard_long.parquet` — ข้อมูลดิบทุกตัวอย่าง (`ts, device, key, value`) เพิ่มแบบ incremental ทุกครั้งที่รัน
- `data/processed/iot_10min.parquet` — wide 10 นาที ผ่าน QC แล้ว (คอลัมน์ `device.key`)
- `data/processed/iot_qc_report.csv` — จำนวนค่าที่ถูกตัดต่อคอลัมน์

โค้ดดึงข้อมูลอยู่ใน `pfal_twin/thingsboard.py` (public token ของ dashboard — ถ้าถูกปิดให้ใช้ `Client.login_user`) และถ้าออฟไลน์ notebook จะ fallback ไปใช้ CSV ตัวอย่าง 7 วัน"""),
("code", SETUP),
("md", "## 1. เชื่อมต่อและสำรวจ: อุปกรณ์, key, ข้อมูลเก่าสุดที่มี"),
("code", '''try:
    client = tb.Client().login_public()
    ONLINE = True
except Exception as e:
    print("ThingsBoard unreachable ->", type(e).__name__, "| falling back to sample CSV"); ONLINE = False
if ONLINE:
    probe = dict(gw="xy_md_20_t", gc1="ec", gc2="ec", co2="CO2")
    rows = []
    for a, d in tb.DEVICES.items():
        ks = client.keys(d["id"])
        rows.append(dict(alias=a, device=d["name"], role=d["role"], n_keys=len(ks), stored_keys=len(tb.KEYS[a] or ks),
                         earliest=client.earliest_ts(d["id"], probe[a])))
    display(pd.DataFrame(rows).set_index("alias"))'''),
("md", """## 2. ดาวน์โหลด (backfill ครั้งแรก ~1–2 นาที, ครั้งถัดไปดึงเฉพาะส่วนที่ใหม่กว่าไฟล์เดิม)
ดึงแบบ `agg=NONE` ทีละ 7 วัน เพื่อได้ทุกตัวอย่างจริง (ไม่ใช่ค่าเฉลี่ยจาก server) — เก็บ key ที่มีความหมายเท่านั้น (ข้าม firmware/calibration)"""),
("code", '''if ONLINE:
    long = tb.update_store(client, backfill_from="2025-12-20")
else:
    long = tb.sample_csv_to_long()
print(f"{len(long):,} samples | {long['ts'].min():%Y-%m-%d} → {long['ts'].max():%Y-%m-%d %H:%M}")
summ = (long.groupby(["device", "key"])
            .agg(n=("value", "size"), first=("ts", "min"), last=("ts", "max"), median=("value", "median"), min=("value", "min"), max=("value", "max"))
            .round(2))
summ["typical_interval_min"] = long.sort_values("ts").groupby(["device", "key"])["ts"].apply(lambda t: t.diff().median().total_seconds() / 60).round(1)
summ'''),
("md", "## 3. Wide 10 นาที + QC (ช่วงค่าที่เป็นไปได้ทางกายภาพ, ตัด `waterTemperature` ที่ probe ไม่ได้ต่อ)"),
("code", '''w_raw = tb.to_wide(long, freq="10min")
w, qc = tb.clean_wide(w_raw)
env, ctrl = tb.split_env_control(w)
ctrl = tb.state_ffill(ctrl)                       # ค่าสถานะ/ตั้งค่าเปลี่ยนเมื่อมี event -> hold forward
w = pd.concat([env, ctrl], axis=1)
w.to_parquet(tb.WIDE_PARQUET); qc.to_csv(io.PROCESSED / "iot_qc_report.csv")
print(f"wide table {w.shape[0]:,} rows x {w.shape[1]} columns  ({w.index.min():%Y-%m-%d} → {w.index.max():%Y-%m-%d})  saved -> {tb.WIDE_PARQUET.name}")
qc[qc.removed > 0].sort_values("removed", ascending=False)'''),
("md", "## 4. ความครบถ้วนของข้อมูล — สัดส่วนช่วง 10 นาทีที่มีข้อมูล ต่ออุปกรณ์ต่อวัน"),
("code", '''av = tb.availability(env, "1D")
fig, ax = plt.subplots(figsize=(16, 3.2))
im = ax.imshow(av.T.values, aspect="auto", cmap="YlGn", vmin=0, vmax=1, interpolation="nearest")
ax.set_yticks(range(av.shape[1])); ax.set_yticklabels([f"{a}  ({tb.DEVICES[a]['name']})" for a in av.columns], fontsize=8)
step = max(1, len(av) // 14); ax.set_xticks(range(0, len(av), step)); ax.set_xticklabels([d.strftime("%d %b") for d in av.index[::step]], rotation=45, ha="right", fontsize=8)
plt.colorbar(im, ax=ax, label="fraction of 10-min bins with data"); ax.set_title("Data availability per device and day")
fig.tight_layout(); fig.savefig(FIG / "04_availability.png", dpi=150)
print("overall availability:"); print(av.mean().round(2).to_string())'''),
("md", "## 5. อุณหภูมิ/ความชื้นจาก XY-MD02 5 จุด — ห้องปลูก 3 จุดบนผนัง (21–23), ห้องหน้า (20), นอกห้อง (24); mapping จาก label บน dashboard"),
("code", '''T = tb.channel_frame(w, "t"); H = tb.channel_frame(w, "h")
STYLE = {"room": ("-", 2.0), "anteroom": ("--", 1.6), "outside": (":", 1.8)}
cols = {"xy_md_21": "#1b9e77", "xy_md_22": "#1f78b4", "xy_md_23": "#7570b3", "xy_md_20": "#e6ab02", "xy_md_24": "#d62728"}
fig, axes = plt.subplots(1, 2, figsize=(18, 4.8), gridspec_kw=dict(width_ratios=[2.2, 1]))
Td = T.resample("1D").mean(); prof = T.groupby(T.index.hour).mean()
for c in T.columns:
    ls, lw = STYLE[tb.CHANNELS[c]["zone"]]
    axes[0].plot(Td.index, Td[c], ls=ls, lw=lw, marker="o", ms=2, color=cols[c], label=tb.channel_label(c))
    axes[1].plot(prof.index, prof[c], ls=ls, lw=lw, color=cols[c], label=c)
axes[0].set_ylabel("air temperature (°C)"); axes[0].set_title("Daily mean temperature per XY-MD02 channel (gaps = gateway offline)"); axes[0].legend(fontsize=7.5, ncol=2); axes[0].grid(alpha=.3)
axes[1].set_xlabel("hour of day (Asia/Bangkok)"); axes[1].set_ylabel("°C"); axes[1].set_title("Mean diurnal profile"); axes[1].grid(alpha=.3); axes[1].set_xticks(range(0, 24, 3)); axes[1].legend(fontsize=7.5)
fig.tight_layout(); fig.savefig(FIG / "04_channel_temperature.png", dpi=150)
stats = pd.DataFrame({"location": [tb.CHANNELS[c]["short"] for c in T.columns], "zone": [tb.CHANNELS[c]["zone"] for c in T.columns],
                      "mean °C": T.mean().values, "p95 °C": T.quantile(.95).values, "max °C": T.max().values, "hours > 30 °C": ((T > 30).sum() / 6).values,
                      "day-night swing °C": (prof.max() - prof.min()).values, "mean RH %": H.mean().values, "mean VPD kPa": tb.vpd_kpa(T, H).mean().values,
                      "n bins": T.count().values}, index=T.columns).round(2)
stats.index.name = "channel"; stats'''),
("md", """**ห้องปลูก** (21–23, ผนังฝั่งแอร์ที่ 1.3–1.4 ม.) อยู่ที่ ~24 °C ทั้ง 3 จุด แกว่งวันละ ~1–1.6 °C → ห้องควบคุมอุณหภูมิได้สม่ำเสมอตามความยาว
**ห้องหน้า** (20) ~27 °C และ **นอกห้อง** (24) ~31 °C แกว่ง 7 °C/วัน พีค 13:00 — ค่า "ร้อน" ที่เคยตีความเป็น hot spot ชั้นบนคืออากาศนอกห้อง
(ลำดับ Grower Room 1/2/3 ↔ W1/W2/W3 ตามระยะจากประตูเป็นการเดา — ทั้ง 3 ค่าใกล้กันมากจึงไม่กระทบผล)"""),
("md", "## 6. CO₂ / VPD และวงจรปุ๋ย (EC, pH เทียบ setpoint)"),
("code", '''fig, axes = plt.subplots(1, 3, figsize=(18, 4.2))
c = w.filter(like="co2.")
for k, ax, unit in zip(["co2.CO2", "co2.VPD"], axes[:2], ["ppm", "kPa"]):
    if k in c:
        g = c[k].groupby(c.index.hour); m_, lo, hi = g.mean(), g.quantile(.1), g.quantile(.9)
        ax.fill_between(m_.index, lo, hi, alpha=.25); ax.plot(m_.index, m_, lw=2)
        ax.set_title(f"{k} — diurnal mean (band = p10–p90)"); ax.set_xlabel("hour"); ax.set_ylabel(unit); ax.grid(alpha=.3); ax.set_xticks(range(0, 24, 3))
ax = axes[2]
for a, col in (("gc1", "#1f77b4"), ("gc2", "#ff7f0e")):
    if f"{a}.ec" in w:
        e = w[f"{a}.ec"].resample("1D").mean(); ax.plot(e.index, e, color=col, lw=1.5, label=f"{a} EC")
        if f"{a}.ecSetPoint" in w: ax.plot(e.index, w[f"{a}.ecSetPoint"].resample("1D").mean(), color=col, ls="--", lw=1, label=f"{a} EC setpoint")
ax.set_ylabel("EC (mS/cm)"); ax.set_title("Nutrient EC vs. setpoint (daily mean) — gc1 = growing stage (200 L), gc2 = nursery 2 (100 L)"); ax.legend(fontsize=8); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(FIG / "04_co2_vpd_ec.png", dpi=150)
ph = w[[k for k in ("gc1.ph", "gc1.pHSetPoint", "gc2.ph", "gc2.pHSetPoint") if k in w]].describe().T.round(2); ph'''),
("md", """## สรุปจาก Notebook 04
- ข้อมูลย้อนหลังดึงได้ตั้งแต่ปลาย ธ.ค. 2025 (CO₂), ม.ค. 2026 (Grow Controller) และ มิ.ย. 2026 (Gateway T/RH 5 จุด: ห้องปลูก 3 จุดบนผนัง, ห้องหน้า, นอกห้อง) — เก็บสำเนาไว้แล้วใน Parquet รันซ้ำเพื่ออัปเดต
- ค่าที่ใช้ไม่ได้: `waterTemperature` (ทั้งคอลัมน์), `ambTemperature/ambHumidity` ของ Grow Controller = อุณหภูมิในกล่อง (ยังเก็บไว้แต่ไม่ใช้เป็นอากาศห้อง), outlier ของ CO₂ controller ถูกตัดตาม `QC_RANGES`
- Gateway offline เป็นช่วง → dashboard ต้องแสดง "no data" ไม่ interpolate ข้าม
- ตัวแปรควบคุม (led, brightness, ปั๊ม, setpoint, plantDay) ถูก forward-fill เป็น state ต่อเนื่อง → เป็น input ของโมเดล L3

**ถัดไป — Notebook 05**: แสดงข้อมูลนี้บนโมเดล 3 มิติ + time slider + KPI"""),
])

# ----------------------------------------------------------------------------- 05
nb05 = nb([
("md", """# 05 — Twin dashboard: สภาพห้องบนโมเดล 3 มิติ ย้อนเวลาได้ (L2)

ทุกอย่างในหน้านี้เป็นเมธอดของ **`DigitalTwin`** (`pfal_twin/twin.py`) ซึ่งรวมทุกชั้นของ twin ไว้ในวัตถุเดียว:
`state(t)` · `figure_3d(t)` / `show(t)` · `snapshot(t)` · `heatmap()` · `kpi()` · `events()` · `layout_figure()` · `water_plan()` · `flow_diagram()` · `flow_animation()` · `update_data()`

> จุดวัด T/RH ในห้องปลูกมี 3 จุดบนผนังฝั่งแอร์ (xy_md_21/22/23) + ห้องหน้า (20) + นอกห้อง (24) — rack ระบายสีด้วยค่าเฉลี่ย 3 จุดในห้อง; ช่วงที่ gateway offline แสดงเป็นสีเทา "no data" """),
("code", SETUP),
("md", "## 1. โหลด twin (geometry + zones + layout + pipework + IoT + พารามิเตอร์ L3)"),
("code", '''from pfal_twin.twin import DigitalTwin
twin = DigitalTwin.load()
print(twin.summary())'''),
("md", "## 2. Heatmap จุดวัด × เวลา"),
("code", '''twin.heatmap(path=FIG / "05_channel_heatmap.png");'''),
("md", "## 3. KPI ต่อจุดวัด + เหตุการณ์ค่าออกนอกช่วง (บันทึก `iot_events.csv`)"),
("code", '''display(twin.kpi())
events_df = twin.events(); print(f"{len(events_df)} events"); events_df.groupby("event")["hours"].agg(["count", "sum"]).round(1)'''),
("md", "## 4. สถานะ ณ เวลาใดๆ → ภาพ 3 มิติ (rack = ค่าเฉลี่ย 3 จุดในห้อง, จุดวัดระบายสีตามค่าจริง, ท่อทึบ = ปั๊มทำงาน)"),
("code", '''t_hot = twin.warmest_moment()
st = twin.state(t_hot); print(f"warmest in-room moment with full data: {st.time:%Y-%m-%d %H:%M} — room {st.room_T:.1f} °C, outside {st.ch_T['xy_md_24']:.1f} °C, CO₂ {st.co2:.0f} ppm, EC growing {st.ec['growing (gc1)']:.2f}")
twin.show(t_hot, "T", name="05_twin_snapshot")'''),
("md", "## 5. Time slider — เลื่อนดูย้อนหลัง (เฉพาะช่วงที่มีข้อมูลในห้อง)"),
("code", '''import ipywidgets as widgets
times = twin.T.index[twin.has_room][::3]      # every 30 min
slider = widgets.SelectionSlider(options=[(t.strftime("%d %b %H:%M"), t) for t in times], value=times[-1],
                                 description="time", layout=widgets.Layout(width="90%"), continuous_update=False)
var = widgets.ToggleButtons(options=["T", "RH", "VPD"], description="variable")
def _show(t, var):
    rng = {"T": (20, 35), "RH": (40, 95), "VPD": (0, 2.5)}[var]
    twin.show(t, var, cmin=rng[0], cmax=rng[1])
widgets.interact(_show, t=slider, var=var);'''),
("md", "## 6. Snapshot 2 มิติสำหรับบทความ"),
("code", '''twin.snapshot(t_hot, path=FIG / "05_twin_snapshot.png");'''),
("md", """## สรุป / ข้อจำกัด
- twin L2 ใช้งานได้ผ่าน API เดียว — เปิดเป็นเว็บให้ทีมดู: `.venv/bin/voila notebooks/05_twin_dashboard.ipynb`
- ในห้องปลูกมีจุดวัด T/RH แค่ 3 จุดบนผนังฝั่งแอร์ที่ 1.35 ม. — ไม่มีค่าที่ระดับใบพืชหรือฝั่งหน้าต่าง → ควรเพิ่ม XY-MD02 ในชั้นปลูก
- ยังไม่มี PPFD/DLI และพลังงาน (kWh) จากเซ็นเซอร์ — เป็น input ที่ต้องเก็บเพิ่มสำหรับ L3 (notebook 06)"""),
])

# ----------------------------------------------------------------------------- 06
nb06 = nb([
("md", """# 06 — Simulation twin (L3): แสง · ความร้อน · CO₂ · การเติบโต · what-if (แสง, ชนิดผัก)

ทุกแบบจำลองเป็นเมธอดของ **`DigitalTwin`**: `light()` · `heat_balance()` · `daily_energy()` · `fit_co2()` · `co2_balance()` · `whatif_light()` · `crop_mix()` · `crop_mix_3d()` — สมการอยู่ใน `pfal_twin/models.py` และ**พารามิเตอร์ทุกตัวมีที่มา** (`twin.params.to_frame()`; `ASSUMED` = ต้องวัด/ยืนยัน)

> ⚠️ นี่คือโครงแบบจำลอง — ก่อนใช้ตัดสินใจต้อง calibrate: จำนวน LED bar/ชั้น, efficacy (วัด PPFD), อุณหภูมิฝั่งร้านกาแฟ, COP แอร์, ค่าไฟ, น้ำหนักผักตอนเก็บ"""),
("code", SETUP),
("code", '''from pfal_twin.twin import DigitalTwin
from pfal_twin import models as M
twin = DigitalTwin.load(); p = twin.params
bright = {i: twin.data[f"gc1.currentStageBrightness{i}"].dropna().mode().iloc[0] for i in range(1, 5)}
print(f"photoperiod from gc1.led duty: {p.photoperiod_h:.1f} h/day | gc1 brightness ch1-4 (mode): {bright} → model uses dim {p.dim_pct:.0f} % | room mean {p.setpoint_t:.1f} °C")
display(p.to_frame())'''),
("md", "## 1. แสง — PPFD และ DLI ต่อชั้นจากกำลังไฟ LED (ใช้จนกว่าจะมี PPFD map จริง)"),
("code", '''rows = [dict(dim_pct=d, **{k: round(v, 1) for k, v in twin.light(dim_pct=d).items()}, DLI_16h=round(twin.light(dim_pct=d, photoperiod_h=16)["dli"], 1)) for d in (100, 80, 60, 40)]
display(pd.DataFrame(rows).set_index("dim_pct")); print("target DLI for lettuce: 12–17 mol/m²/d; tray area %.2f m²" % twin.rack_area)'''),
("md", "ด้วย 8 bar × 42 W ต่อชั้น PPFD ~120 µmol/m²/s ที่ 100 % — ต่ำกว่าช่วงแนะนำผักสลัด (150–250) → ถ้าวัดจริงได้สูงกว่านี้แปลว่า efficacy สูงกว่าที่สมมติหรือ bar มากกว่า 8 — เหตุผลที่ต้องวัด PPFD"),
("md", "## 2. ความร้อน — สมดุลพลังงานสถานะคงตัวของห้องปลูก (LED, อุปกรณ์, ผนัง/หลังคา/หน้าต่าง, อากาศรั่ว vs กำลังแอร์)"),
("code", '''q_on, q_off = twin.heat_balance(led_on=True), twin.heat_balance(led_on=False)
heat = pd.DataFrame({"lights ON (W)": q_on, "lights OFF (W)": q_off}).round(0); display(heat)
fig, ax = plt.subplots(figsize=(11, 4.5))
items = [k for k in q_on if k not in ("cooling required", "AC electrical (at COP)", "AC capacity (electrical, design)")]
ax.barh(items, [q_on[k] for k in items], color=["#d62728" if q_on[k] > 0 else "#1f77b4" for k in items]); ax.axvline(0, color="k", lw=.8)
ax.set_xlabel("sensible heat gain (W), lights ON, design-day outside temperature"); ax.set_title(f"Grow-room heat balance — cooling required ≈ {q_on['cooling required']/1000:.1f} kW (AC electrical ≈ {q_on['AC electrical (at COP)']/1000:.1f} kW at COP {p.ac_cop})")
ax.grid(alpha=.3, axis="x"); fig.tight_layout(); fig.savefig(FIG / "06_heat_balance.png", dpi=150)
pd.Series(twin.daily_energy()).round(1).to_frame("per day")'''),
("md", "LED เป็นภาระความร้อนหลัก (~55 %) รองลงมาคือเครื่องลดความชื้น/พัดลม/ปั๊ม ส่วนผนัง+หน้าต่างรวมกันไม่ถึง 15 % — what-if เรื่องแสงกระทบค่าไฟแอร์โดยตรง"),
("md", "## 3. CO₂ — fit อัตรารั่ว (air exchange) จากช่วงที่ CO₂ ลดลงเองตอนไฟปิดและไม่มีการจ่าย แล้วคำนวณสมดุล"),
("code", '''fits = twin.fit_co2(); lam = p.infiltration_ach
print(f"{len(fits)} decay segments | λ median {lam:.3f} h⁻¹ (IQR {fits.lam_per_h.quantile(.25):.3f}–{fits.lam_per_h.quantile(.75):.3f}) → ~{lam:.2f} air changes per hour")
w = twin.data
fig, axes = plt.subplots(1, 2, figsize=(15, 4.2))
axes[0].hist(fits.lam_per_h.clip(0, 0.5), bins=20, color="#7a9"); axes[0].set_xlabel("decay rate λ (h⁻¹)"); axes[0].set_title("Fitted CO₂ decay rates (lights off, no injection)")
c = w["co2.CO2"].groupby(w.index.hour).mean(); r = w["co2.Relay_co2"].groupby(w.index.hour).mean()
axes[1].plot(c.index, c, lw=2, label="CO₂ (ppm)"); ax2 = axes[1].twinx(); ax2.plot(r.index, r, color="#d62728", lw=1.5, label="Relay_co2 on-fraction"); ax2.set_ylim(0, 1)
axes[1].set_xlabel("hour"); axes[1].set_ylabel("ppm"); axes[1].set_title("Mean diurnal CO₂ and injection relay"); axes[1].grid(alpha=.3); axes[1].legend(loc="upper left"); ax2.legend(loc="upper right")
fig.tight_layout(); fig.savefig(FIG / "06_co2_decay.png", dpi=150)
pd.Series(twin.co2_balance(c_target=900))'''),
("md", "λ ≈ 0.08 h⁻¹ = ห้องรั่วน้อยมาก → รักษา 900 ppm ใช้ CO₂ ระดับสิบกรัม/ชม. ถัง 6 กก. ใช้ได้ ~1 เดือน — ควรเทียบกับบันทึกการเติมถังจริง"),
("md", "## 4. What-if แสง — photoperiod × ความสว่าง → PPFD/DLI, kWh/วัน, บาท/วัน, ภาระแอร์, วันเก็บเกี่ยว (schematic)"),
("code", '''wi = twin.whatif_light(); wi.to_csv(io.PROCESSED / "whatif_light_energy.csv", index=False); display(wi)
fig, axes = plt.subplots(1, 2, figsize=(14, 4.3))
for dm in wi.dim_pct.unique():
    s = wi[wi.dim_pct == dm]; axes[0].plot(s.photoperiod_h, s.kWh_total, "-o", label=f"dim {dm} %"); axes[1].plot(s.DLI, s.days_to_150g, "-o", label=f"dim {dm} %")
axes[0].set_xlabel("photoperiod (h/day)"); axes[0].set_ylabel("kWh/day (LED + AC + others)"); axes[0].set_title("Daily electricity vs photoperiod"); axes[0].grid(alpha=.3); axes[0].legend()
axes[1].set_xlabel("DLI (mol/m²/d)"); axes[1].set_ylabel("days to 150 g (schematic lettuce model)"); axes[1].set_title("Growth vs light — SCHEMATIC, calibrate with harvest data"); axes[1].grid(alpha=.3); axes[1].legend()
fig.tight_layout(); fig.savefig(FIG / "06_whatif.png", dpi=150)'''),
("md", """## 5. What-if ชนิดผัก — สัดส่วนผักบน 700 หลุมของชั้น 2–5 → ผังรายหลุม (2D/3D) + ผลผลิต/รายได้/ความต้องการแสง
- 700 หลุม (ผู้ใช้ 14 ก.ย.) = 175/ชั้น → กริด 25 × 7 (จำนวนแถวสมมติ — นับหน้างานแล้วแก้ `rows=`)
- แคตตาล็อกผัก `models.CROPS` เป็นค่าทั่วไป ต้องแทนด้วยบันทึกของฟาร์ม; นโยบาย `blocks` (บล็อกต่อเนื่องทีละชั้น) / `per_tier` (ทุกชั้นผสมเท่ากัน)"""),
("code", '''pd.DataFrame(M.CROPS).T.drop(columns="color")'''),
("code", '''MIX = {"green oak": 40, "red oak": 30, "butterhead": 20, "basil": 10}      # percent — edit freely
assign, summary, fig3d = twin.crop_mix(MIX, policy="blocks", view="3d", name="06_crop_mix_3d")     # 3-D: one marker per hole, click legend to toggle crops
assign.to_csv(io.PROCESSED / "crop_mix_assignment.csv", index=False); display(summary)'''),
("md", "แบบ 2 มิติ (รายหลุมต่อชั้น) สำหรับใส่บทความ และนโยบาย `per_tier` เปรียบเทียบ"),
("code", '''_ = twin.crop_mix(MIX, policy="blocks", view="2d", path=FIG / "06_crop_mix_plan.png")
_ = twin.crop_mix(MIX, policy="per_tier", view="2d", path=FIG / "06_crop_mix_plan_per_tier.png")'''),
("md", "### โต้ตอบ: เลื่อน % ของแต่ละชนิด (normalise ให้เอง)"),
("code", '''import ipywidgets as widgets
crops_ui = [c for c in M.CROPS if c != "empty"]
sliders = {c: widgets.IntSlider(value=MIX.get(c, 0), min=0, max=100, step=5, description=c, continuous_update=False, layout=widgets.Layout(width="45%")) for c in crops_ui}
policy_ui = widgets.ToggleButtons(options=["blocks", "per_tier"], description="policy")
def _run(policy, **pct):
    mix = {k: v for k, v in pct.items() if v > 0} or {"empty": 100}
    a, s, f = twin.crop_mix(mix, policy=policy, view="3d"); display(s)
widgets.interact(_run, policy=policy_ui, **sliders);'''),
("md", """## 6. Sanity check กับข้อมูลจริง
- ห้องปลูก ~24 °C คงที่ (แกว่ง 1–1.6 °C) → แอร์ 2 ตัวรับภาระ ~3 kW ได้สบาย ยกเว้นวันที่ระบบดับ (9–12 ก.ย. 2026 ห้องขึ้นถึง 28–31 °C)
- `gc1.led` duty ≈ 9 ชม./วัน (น้อยกว่า 16 ชม. ที่มักใช้) และ `currentStageBrightness1–4` = 0/22/0/0 % → ต้องเช็กความหมายของ key เหล่านี้กับ Civic
- CO₂ กลางวัน ~500–700 ppm พร้อม relay ทำงาน แต่ไม่ถึง 900 ppm → ดู setpoint ใน CO₂ controller

## ข้อมูลที่ต้องเก็บเพื่อ calibrate (ลำดับความสำคัญ)
1. **PPFD map** ทุกชั้น (grid 3×3) → efficacy, canopy_fraction · 2. นับ LED bar/ชั้น + วัตต์จริง · 3. ตาราง photoperiod/dim + ความหมาย `led`/`currentStageBrightness` · 4. BTU/รุ่นแอร์ + กระแสจริง → COP; T ฝั่งร้านกาแฟ · 5. น้ำหนักผักตอนเก็บ + วันปลูก → growth model · 6. บันทึกเติมถัง CO₂"""),
])

# ----------------------------------------------------------------------------- 00 quick start
nb00 = nb([
("md", """# 00 — Quick start: ใช้ digital twin ผ่าน `DigitalTwin` วัตถุเดียว

Notebook 01–04 เป็น *pipeline สร้าง* twin (point cloud → โมเดลห้อง → โซน/อุปกรณ์/ท่อ → ข้อมูล IoT) — เมื่อไฟล์ใน `data/model`, `data/sensors`, `data/processed` มีแล้ว ใช้งานทั้งหมดได้จากหน้านี้"""),
("code", SETUP),
("code", '''from pfal_twin.twin import DigitalTwin
twin = DigitalTwin.load()
print(twin.summary())'''),
("md", "## สภาพห้อง ณ เวลาหนึ่ง"),
("code", '''st = twin.state("2026-09-11 12:10")
{k: v for k, v in st.as_dict().items() if k in ("time", "room_T", "room_RH", "co2", "ec", "ph", "pump_on")}'''),
("code", '''twin.show("2026-09-11 12:10", "T")          # 3-D (ปุ่ม Full screen / ไฟล์ html)'''),
("code", '''twin.snapshot("2026-06-26 14:00");         # 2-D สำหรับบทความ'''),
("md", "## ตาราง"),
("code", '''display(twin.kpi()); twin.events(save=False).head()'''),
("md", "## ผัง / ระบบน้ำ / การไหล"),
("code", '''twin.water_plan(); twin.flow_diagram();'''),
("code", '''viz.show3d(twin.flow_animation(), None, height=700)'''),
("md", "## L3 what-if"),
("code", '''print(twin.light()); pd.Series(twin.heat_balance()).round(0).to_frame("W")'''),
("code", '''assign, summary, fig = twin.crop_mix({"green oak": 50, "kale": 30, "basil": 20})     # 3-D by default
summary'''),
("md", """## ข้อมูลย้อนหลัง — `twin.history(start, end, columns, freq)`
ดึงจากคลัง 10 นาทีในเครื่อง (ชื่อคอลัมน์ = `อุปกรณ์.key` เช่น `gw.xy_md_21_t`, `gc1.ec`, `co2.CO2`)"""),
("code", '''h = twin.history("2026-09-08", "2026-09-13", ["gw.xy_md_21_t", "gw.xy_md_22_t", "gw.xy_md_23_t", "gw.xy_md_24_t", "co2.CO2", "gc1.ec"], freq="1h")
ax = h.filter(like="_t").plot(figsize=(14, 3.5), title="wall / outside temperature (hourly mean)"); ax.set_ylabel("°C")
h[["co2.CO2", "gc1.ec"]].describe().round(2)'''),
("md", """## ค่า live จาก ThingsBoard (ต้องมีอินเทอร์เน็ต) — `twin.live()` / `twin.figure_3d_live()`
ค่าล่าสุดของทุก key ตรงจาก server (ไม่ผ่านคลังในเครื่อง) พร้อมอายุของแต่ละค่า; ค่าที่เก่ากว่า 24 ชม. จะไม่ถูกใส่ใน twin"""),
("code", '''try:
    st_live, latest = twin.live()
    print(st_live.time, "| room T", st_live.room_T, "| CO2", st_live.co2, "| EC", st_live.ec, "| pumps", st_live.pump_on)
    display(latest.groupby("device")["age"].min().rename("age of newest value"))
    viz.show3d(twin.figure_3d(st=st_live, title_prefix="LIVE "), None, height=650)
except Exception as e:
    print("ThingsBoard not reachable:", e)'''),
("md", "## อัปเดตคลังในเครื่องจาก ThingsBoard (ต้องมีอินเทอร์เน็ต)"),
("code", '''# twin.update_data()      # ดึงเฉพาะส่วนที่ใหม่กว่าไฟล์เดิม แล้วโหลดใหม่'''),
("md", """## Web dashboard
ทุกอย่างข้างบนอยู่ในหน้าเว็บ `app/streamlit_app.py` (Live / History / Layout & water / What-if) — เปิดด้วย `scripts/run_app.sh` → http://localhost:8501"""),
])

ROOT = Path(__file__).resolve().parent.parent
for name, book in [("00_quickstart", nb00), ("01_pointcloud_explore", nb01), ("02_geometry_model", nb02), ("03_zones_and_sensor_map", nb03),
                   ("03b_hydraulics", nb03b), ("04_iot_ingest", nb04), ("05_twin_dashboard", nb05), ("06_simulation_whatif", nb06)]:
    nbf.write(book, ROOT / "notebooks" / f"{name}.ipynb")
print("notebooks written")
