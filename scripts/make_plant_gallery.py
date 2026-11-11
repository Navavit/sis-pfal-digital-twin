"""Render docs/img/plant_gallery.png: every crop of the PFAL Management crop sheet as drawn by pfal_twin/plants3d.py,
at harvest size (one plant each, name and plant form underneath). Run after changing a style in plants3d.STYLES:

    .venv/bin/python scripts/make_plant_gallery.py
"""
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pfal_twin import plants3d as P  # noqa: E402

# the `ข้อมูลพืช` tab of PFAL Management, in sheet order
CROPS = ["กรีนโอ๊ค", "เรดโอ๊ค", "กรีนคอส", "กรีนมินิคอส", "บัตเตอร์เฮด", "ฟิลเลย์ไอซ์เบิร์ก", "วอเตอร์เครส", "เคลควีน", "เรดคอรัล",
         "ปัตตาเวีย (Batavia)", "คอสแดง (Red Romaine)", "ผักกาดแก้ว (Iceberg)", "ร็อกเก็ต (Arugula)", "มิซูน่า (Mizuna)",
         "กวางตุ้งฮ่องเต้", "กวางตุ้งดอก", "คะน้า", "ผักกาดขาวไดโตเกียว", "ผักบุ้งจีน", "ผักโขม", "ปวยเล้ง (Spinach)", "สวิสชาร์ด",
         "ขึ้นฉ่าย", "โหระพา", "กะเพรา", "เบซิลอิตาเลียน (Sweet Basil)", "ผักชี", "ต้นหอม", "สะระแหน่", "พาร์สลีย์"]
OUT = ROOT / "docs" / "img" / "plant_gallery.png"

style_name = {id(v): k for k, v in P.STYLES.items()}
traces, labels = [], []
for i, crop in enumerate(CROPS):
    sty = P.style_for(crop)
    x, y = (i % 6) * 0.45, -(i // 6) * 0.62
    vx, vy, vz, f, inten = P.plant_mesh(x, y, 0.0, sty, 1.0, np.random.default_rng(i))
    traces.append(go.Mesh3d(x=vx, y=vy, z=vz, i=f[:, 0], j=f[:, 1], k=f[:, 2], intensity=inten, cmin=0, cmax=1,
                            colorscale=P.colorscale(sty), showscale=False, flatshading=False,
                            lighting=dict(ambient=0.45, diffuse=0.85, specular=0.15, roughness=0.8), lightposition=dict(x=0, y=0, z=1e5)))
    labels.append((x, y - 0.20, f"{crop.split(' (')[0]} · {style_name[id(sty)]}"))
traces.append(go.Scatter3d(x=[a for a, _, _ in labels], y=[b for _, b, _ in labels], z=[0] * len(labels), mode="text",
                           text=[t for _, _, t in labels], textfont=dict(size=11)))
fig = go.Figure(traces)
fig.update_layout(scene=dict(aspectmode="data", xaxis_visible=False, yaxis_visible=False, zaxis_visible=False,
                             camera=dict(eye=dict(x=0.0, y=-0.95, z=0.62), projection=dict(type="orthographic"))),
                  margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
tmp = OUT.with_suffix(".tmp.png")
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.write_image(tmp, width=2400, height=1350)
im = Image.open(tmp).convert("RGB")
box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()   # trim the white margin
im.crop((max(box[0] - 30, 0), max(box[1] - 30, 0), min(box[2] + 30, im.width), min(box[3] + 30, im.height))).save(OUT, optimize=True)
tmp.unlink()
print(OUT)
