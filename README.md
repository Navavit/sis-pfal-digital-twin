<p align="center"><img src="app/assets/sis_logo.png" width="140" alt="School of Integrated Science, Kasetsart University"></p>

# SIS PFAL Digital Twin

**โครงการโรงประลอง (Rong Pralong) · วิทยาลัยบูรณาการศาสตร์ มหาวิทยาลัยเกษตรศาสตร์**
*Rong Pralong project · School of Integrated Science, Kasetsart University*

Digital twin ของ **SIS PFAL** — ห้องปลูกพืชระบบปิดด้วยแสงเทียม (plant factory with artificial lighting) ของวิทยาลัยบูรณาการศาสตร์ — ทำด้วย Python/Jupyter และมี web app
รวมข้อมูลทั้งสองด้านไว้ในโปรเจคเดียว: **point cloud** จาก LiDAR มือถือ (รูปทรงห้อง/ชั้นปลูก) และ
**ข้อมูล IoT** จาก ThingsBoard ของ Civic Agrotech (T/RH รายชั้น, EC/pH, CO₂, สถานะไฟ/ปั๊ม)

- แผนงาน, ผลวิเคราะห์ข้อมูล, คำถามที่ต้องถามผู้ผลิต → [`docs/DIGITAL_TWIN_PLAN.md`](docs/DIGITAL_TWIN_PLAN.md)
- ระดับความสมบูรณ์: **L1 Geometry** (เสร็จ) → **L2 Data** (เสร็จ — notebook 03–05) → **L3 Simulation** (รอข้อมูล LED/HVAC/พืช)

## โครงสร้าง
```
PFAL/
├─ README.md
├─ requirements.txt / .venv/    สภาพแวดล้อม Python (kernel "pfal-twin")
├─ docs/                        DIGITAL_TWIN_PLAN.md · SITE_SURVEY_2026-09-13.md (ภาพถ่าย) · DESIGN_VS_BUILT.md (แปลน vs จริง) · plan_drawing/ (PDF 7 หน้า + pptx 4 สไลด์) · plan_figures/
├─ data/
│   ├─ raw/pointcloud/SIS PFAL.ply            สแกนดิบ 1.02 ล้านจุด (อ้างอิง) · SIS PFAL2.ply สแกนซ้ำ 0.96 ล้านจุด (ตรวจสอบ)
│   ├─ raw/picture/             ภาพถ่ายหน้างาน 13 ก.ย. 2026 ×56 (HEIC; `sh scripts/photos_to_jpg.sh` → jpg/)
│   ├─ raw/doc/                 แปลนออกแบบของ Civic Agrotech (PDF/PPTX) — แปลนที่ใช้วางแผน ไม่ใช่ as-built
│   ├─ raw/iot/                 thingsboard_long.parquet (ทุกตัวอย่างจาก API, เพิ่มแบบ incremental)
│   │                           + sample_thingsboard_7d_hourly.csv (fallback ออฟไลน์)
│   ├─ processed/               raw.npz, pfal_clean.npz (point cloud) · iot_10min.parquet (IoT ผ่าน QC)
│   │                           iot_qc_report.csv · iot_events.csv (เหตุการณ์ค่าออกนอกช่วง)
│   ├─ model/                   room_model.json · zones.json · pipe_network.json (ท่อ) · design_spec.json (spec จากแปลน) · scan_comparison.csv
│   └─ sensors/                 sensor_map.csv · equipment_map.csv · reference_readings.csv (Testo)
├─ pfal_twin/                   โค้ดใช้ซ้ำ
│   ├─ io.py          โหลด/บันทึก PLY, npz, JSON
│   ├─ geometry.py    align, crop, tiers, rack, segment, zones, air grid
│   ├─ layout.py      ตำแหน่งอุปกรณ์/เซ็นเซอร์ (scan + ภาพถ่าย; verified/evidence; location inside/outside)
│   ├─ hydraulics.py  โครงข่ายท่อ (จ่ายด้านประตู, กลับทางท่อยืนฟ้าปลายห้อง, ท่อรวม drain, ประปา/RO), แอนิเมชันการไหล
│   ├─ schematic.py   ผังเฉพาะระบบน้ำ-ปุ๋ย + process flow diagram
│   ├─ models.py      L3: แสง/ความร้อน/CO₂/การเติบโต/what-if + แคตตาล็อกผัก `CROPS` และการจัดหลุม `allocate_holes` — พารามิเตอร์ทุกตัวระบุที่มา (ASSUMED = ต้อง calibrate)
│   ├─ cropviz.py     ผังรายหลุม (2D ต่อชั้น) และ 3D ของสัดส่วนผัก
│   └─ twin.py        **DigitalTwin** — facade รวมทุกชั้น: state/figure_3d/snapshot/kpi/events/layout/water/flow/L3/crop_mix/update_data
│   ├─ thingsboard.py REST client (public token), backfill/incremental, wide 10 นาที, QC, VPD
│   └─ viz.py         matplotlib + plotly 3D (โมเดล, โซนระบายสี, อุปกรณ์, เซ็นเซอร์)
├─ notebooks/
│   ├─ 00_quickstart             ใช้ twin ผ่าน DigitalTwin API
│   ├─ 01_pointcloud_explore     สำรวจสแกนดิบ
│   ├─ 02_geometry_model         align → crop → tiers → room_model.json
│   ├─ 03_zones_and_sensor_map   โซน + แผนที่เซ็นเซอร์/อุปกรณ์ (+ contact sheet ภาพถ่าย 3 ชุด)
│   ├─ 03b_hydraulics            ระบบน้ำทั้งหมด: ท่อ/ข้อต่อ/วาล์ว, RO plant + ท่อทิ้งภายนอก, ผังเฉพาะระบบน้ำ-ปุ๋ย, process flow diagram, แอนิเมชัน, สถานะปั๊ม
│   ├─ 04_iot_ingest             ดึง ThingsBoard ทั้งหมด → QC → iot_10min.parquet
│   ├─ 05_twin_dashboard         3D twin (จุดวัดจริง 5 จุด) + ท่อ (ปั๊ม on/off) + time slider + KPI + events
│   └─ 06_simulation_whatif      L3 โครง: PPFD/DLI, สมดุลความร้อน, CO₂ (fit λ จากข้อมูล), what-if photoperiod×dim → kWh/บาท/วันเก็บเกี่ยว, **what-if ชนิดผัก** (700 หลุม ชั้น 2–5: สัดส่วน → ผังรายหลุม 2D/3D + kg/ปี/รายได้/DLI)
├─ figures/                     รูปที่ notebook สร้าง (ป้ายภาษาอังกฤษ ใช้ในบทความได้)
├─ app/streamlit_app.py       web dashboard (Live / History / Layout & water / What-if) บน DigitalTwin — `scripts/run_app.sh`
└─ scripts/make_notebooks.py    สร้าง notebook 00–06 ใหม่ (notebook ถูก generate จากสคริปต์นี้)
```

## ใช้งาน twin ผ่านวัตถุเดียว (`pfal_twin/twin.py`) — ดู `notebooks/00_quickstart.ipynb`
```python
from pfal_twin.twin import DigitalTwin
twin = DigitalTwin.load()                       # geometry + zones + layout + pipework + IoT + พารามิเตอร์ L3
twin.summary()
st = twin.state("2026-09-11 12:10")             # ทุกตัวแปร ณ เวลาหนึ่ง (room_T, ch_T, co2, ec, ph, pump_on, ...)
twin.show("2026-09-11 12:10", "T")              # 3-D: rack = ค่าเฉลี่ยห้อง, จุดวัดตามค่าจริง, ท่อทึบ = ปั๊มทำงาน (ปุ่ม Full screen)
twin.snapshot(t, path)                          # 2-D PNG สำหรับบทความ
twin.heatmap(); twin.kpi(); twin.events()       # ตาราง/รูปสรุป
twin.layout_figure(); twin.water_plan(); twin.flow_diagram(); twin.flow_animation(); twin.corner_detail()
twin.light(); twin.heat_balance(); twin.daily_energy(); twin.fit_co2(); twin.co2_balance(); twin.whatif_light()
twin.crop_mix({"green oak": 50, "kale": 30, "basil": 20})   # 700 หลุมชั้น 2–5 → 3-D รายหลุม + ตารางผลผลิต/รายได้/DLI
twin.update_data()                              # ดึงข้อมูลใหม่จาก ThingsBoard (ส่วนเพิ่ม)
twin.live()                                     # ค่าล่าสุดตรงจาก ThingsBoard → (TwinState, ตาราง key/ค่า/เวลา/อายุ)
twin.figure_3d_live()                           # twin 3-D ของสถานะ live
twin.history("2026-09-01", "2026-09-07", ["gw.xy_md_21_t", "gc1.ec"], freq="1h")   # ย้อนหลัง
```
Notebook 01–04 = pipeline สร้างไฟล์ของ twin; 05–06 = ใช้งานผ่าน API นี้

## Web dashboard (Streamlit) — live + ย้อนหลัง + what-if
```bash
scripts/run_app.sh            # เปิด http://localhost:8501
```
| หน้า | ทำอะไร |
|---|---|
| **Overview** | หน้าแรก: ภาพหน้างาน, แอปทำอะไรได้, ข้อมูลที่ใช้ |
| **Live** | ค่าล่าสุดจาก ThingsBoard ทุก 60 วิ (`twin.live()`) → การ์ดค่า + twin 3-D ระบายสีตามค่าจริง + **กราฟแบบเดียวกับ dashboard ThingsBoard** (`twin.recent()`: หน้าต่าง 6 ชม.–7 วัน เฉลี่ย 5 นาที — T/RH 5 จุด, CO₂, VPD/VOC, EC/pH + set-point + สถิติ min/avg/max, Dose stage A/B/pH ต่อ controller), บอกอายุข้อมูลรายอุปกรณ์ — แสดง **มากกว่า dashboard ของ ThingsBoard**: LED/ความสว่าง, ปั๊มเวียน+โหมด, plant day/task/stage, ค่าตั้งการจ่ายปุ๋ย (วินาที/ครั้ง, รอ, ความเร็ว, จำนวนครั้ง), uptime ของ controller, วาล์ว CO₂ (สวิตช์ "show more than the ThingsBoard dashboard" ปิดได้) |
| **History** | เลือกช่วงวัน/ความละเอียด → slider เวลาเลื่อนดู twin 3-D ณ เวลานั้น (`twin.state()`), กราฟอนุกรมเวลา 17 กลุ่ม (รวมค่าอนุพันธ์: จำนวนครั้งจ่ายปุ๋ยต่อวัน, uptime → รีบูต), KPI, events, heat-map, ดาวน์โหลด CSV |
| **Layout & water** | ผัง as-built, ผังระบบน้ำ, process flow, แอนิเมชันการไหล 3-D, ตารางอุปกรณ์/เซ็นเซอร์ |
| **What-if** | slider สัดส่วนผัก → 700 หลุม 3-D + ตารางผลผลิต, ตาราง photoperiod × dimming |
ปุ่ม "Pull new data" ใน sidebar = `twin.update_data()` (ดึงส่วนเพิ่มจาก ThingsBoard ลง Parquet ในเครื่อง)
แอปอ่านไฟล์ที่ notebook 01–04 สร้างเท่านั้น ไม่โหลด point cloud → รันบนเครื่องเล็กได้; การนำขึ้นเว็บสาธารณะดู `docs/DIGITAL_TWIN_PLAN.md` ข้อ 6.1

## ติดตั้ง (ครั้งเดียว)
```bash
cd PFAL
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt      # notebook ทั้งหมด (รวม open3d, jupyter)
.venv/bin/python -m ipykernel install --user --name pfal-twin --display-name "Python (pfal-twin)"
```
เปิด notebook ใน VS Code แล้วเลือก kernel **Python (pfal-twin)**
(`requirements.txt` อย่างเดียว = ชุดเบาสำหรับรัน web app / Streamlit Cloud ไม่มี point-cloud library)

## สิ่งที่ไม่อยู่บน GitHub (ดู `.gitignore`)
| ไฟล์ | เหตุผล | ถ้าต้องการ |
|---|---|---|
| `data/raw/pointcloud/*.ply` (78 + 41 MB) | ใหญ่เกิน | ขอจากผู้ดูแลโครงการ / archive (Zenodo) → วางไว้แล้วรัน notebook 01–02 |
| `data/raw/picture/` | ภาพหน้างาน (มีข้อมูลส่วนตัวของฟาร์ม) | ขอจากผู้ดูแลโครงการ |
| `data/raw/doc/` | แบบแปลนของผู้รับเหมา | ขอจากผู้ดูแลโครงการ |
| `data/raw/iot/*.parquet`, `data/processed/*.npz` | cache สร้างใหม่ได้ | รัน notebook 04 / 01–02 |
`data/processed/iot_10min.parquet` (1 MB) **อยู่บน GitHub** เพื่อให้ web app มีข้อมูลทันทีหลัง deploy; กดปุ่ม "Pull new data" ในแอปเพื่ออัปเดต

## รันทั้งหมดแบบ headless
```bash
.venv/bin/python scripts/make_notebooks.py          # สร้าง notebook ใหม่ (ถ้าแก้สคริปต์)
.venv/bin/python -m nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=pfal-twin notebooks/0*.ipynb
```

## ระบบพิกัดของห้อง (room frame)
Z ชี้ขึ้น, X ตามความยาวห้อง, Y ตามความกว้าง, จุดกำเนิดที่มุมพื้นภายในห้อง (หน่วยเมตร)
`room_model.json` เก็บเมทริกซ์ 4×4 `transform_scan_to_room` — จุดใดๆ ในพิกัดสแกนเดิม (เช่น ตำแหน่งเซ็นเซอร์ที่คลิกใน PLY)
แปลงเป็นพิกัดห้องได้ด้วย `pfal_twin.geometry.apply_T`

| | ค่าจาก `room_model.json` |
|---|---|
| ห้อง L × W × H | 7.12 × 3.01 × 2.58 ม. |
| ชั้นปลูก (rack) | 5.43 × 1.04 ม. กึ่งกลางความกว้าง, ทางเดิน 0.985 ม. สองข้าง |
| ความสูงชั้น 1–5 | 0.39 / 0.81 / 1.27 / 1.69 / 2.05 ม. |

## ข้อมูล IoT (`data/raw/iot/`)
คอลัมน์ใน CSV ใช้ prefix ตามอุปกรณ์บน ThingsBoard

| prefix | อุปกรณ์ | ตัวแปรหลัก |
|---|---|---|
| `gw.` | IoT Gateway (`DOAIoTGateway`) | `xy_md_21/22/23_t/_h` = T/RH **ห้องปลูก 3 จุดบนผนังฝั่งแอร์** (X 1.25 / 3.6 / 5.65 ม.), `xy_md_20` = **ห้องหน้า** (เหนือประตู), `xy_md_24` = **นอกห้อง** (บนกล่อง CO₂) — mapping จาก label บน dashboard 14 ก.ย.; `waterLevel_1` |
| `gc1.` | Grow Controller ปลาย rack = **ผัก Growing stage ชั้น 2–5, ถัง 200 L** (ยืนยัน 14 ก.ย. — ป้าย dashboard "ชั้นปลูกที่ 1" ไม่ตรง) | `ec, ph, waterTemperature, ambTemperature, ambHumidity, led, currentStageBrightness1-4, pwmWater, pumpA/B/PH, plantDay` |
| `gc2.` | Grow Controller ข้าง rack = **ชุดปุ๋ยอนุบาล 2 (T1-N2), ถัง 100 L**; อนุบาล 1 ไม่มีตัวควบคุม | เหมือน gc1 + `rssiWiFi` |
| `co2.` | CO₂ & Environment controller | `CO2, temperature, humidity, VPD, pressure` |

ข้อควรระวังจากการตรวจข้อมูล (รายละเอียดใน plan ข้อ 1.5): `waterTemperature` อ่าน 42–54 °C ใช้ไม่ได้,
`ambTemperature` ของ gc คืออุณหภูมิในกล่องควบคุมไม่ใช่ห้อง, gateway offline บ่อย, `co2.humidity`/`pressure` มี outlier

## สถานะ (13 ก.ย. 2026)
| ระยะ | งาน | สถานะ |
|---|---|---|
| 1 (L1) | env + notebook 01–02 + `room_model.json` | ✅ เสร็จ — ตรวจกับสแกนชุด 2 (≤ 8 ซม.) และแปลนออกแบบ (อาคาร 8.9 ม. = ห้องปลูก 7.12 ม. + ห้องหน้าซิงค์ ~1.78 ม. ที่ไม่ได้สแกน; สูงต่ำกว่าแปลน 0.27 ม.) |
| 2 | notebook 03 + 03b โซน, แผนที่อุปกรณ์/เซ็นเซอร์, ระบบท่อ | ✅ เสร็จ — อุปกรณ์ 24 รายการ (2 รายการนอกห้อง) ยืนยันจากภาพ 56 รูป; ชั้น 1 = อนุบาล 1 ฝั่งประตู (T1-N1) / อนุบาล 2 ฝั่งถังชั้นปลูก (T1-N2), ชั้น 2–5 = ผัก Growing stage, มุมห้อง = ชั้นเพาะเมล็ด; ท่อ 26 เส้น 55 ม. + แอนิเมชันการไหล; XY-MD02 6 ตัว (5 ในห้อง + 1 นอกห้อง) **ยังไม่รู้ address↔จุด** |
| 3 (L2) | notebook 04–05 ดึง ThingsBoard + dashboard 3 มิติ | ✅ เสร็จ — backfill 1.24 ล้านตัวอย่าง (ธ.ค. 2025 → ก.ย. 2026) |
| 4 (L3) | notebook 06 โมเดลแสง/ความร้อน/CO₂ + what-if | 🟡 **โครงเสร็จ** (14 ก.ย.) — รันด้วยพารามิเตอร์สมมติ + ค่าที่ fit จากข้อมูล (λ CO₂ ≈ 0.08 h⁻¹, photoperiod ≈ 9 ชม.); รอ PPFD map / นับ LED / COP แอร์ / น้ำหนักผัก เพื่อ calibrate |
| 5 | voila dashboard | ติดตั้ง `voila` แล้ว: `.venv/bin/voila notebooks/05_twin_dashboard.ipynb` (หน้าเว็บ local); ยังไม่มีเซิร์ฟเวอร์/auto-refresh |

## สิ่งที่ข้อมูลบอกแล้ว (จาก notebook 04–05)
- **ห้องปลูกสม่ำเสมอ**: 3 จุดบนผนัง (`xy_md_21–23`) เฉลี่ย 24.2–24.4 °C แกว่งวันละ 1–1.6 °C; ค่า "ร้อน" ที่เคยตีความเป็น hot spot คือ**นอกห้อง** (`xy_md_24` 30.7 °C, แกว่ง 7 °C/วัน) และ**ห้องหน้า** (`xy_md_20` 27.3 °C) — ยืนยันจาก label บน dashboard (Outside / Inside / Grower Room 1–3) 14 ก.ย.
- **ข้อจำกัดของเซ็นเซอร์**: ในห้องปลูกไม่มีจุดวัดที่ระดับใบพืชและไม่มีฝั่งหน้าต่างเลย → twin ใช้ค่าเฉลี่ยห้อง; ควรเพิ่ม XY-MD02 ในชั้นปลูก
- **Gateway offline**: T/RH รายชั้นมีข้อมูลต่อเนื่องเฉพาะ 24 มิ.ย.–15 ก.ค. 2026 หลังจากนั้นมาเป็นช่วงสั้นๆ (ควรถาม Civic Agrotech ข้อ 5A.4 ในแผน)
- **หน้าต่างกระจก 2 บาน** บนผนัง Y=0 หันเข้าร้านกาแฟ มีไอน้ำเกาะหนา → thermal bridge ที่ต้องอยู่ในโมเดลความร้อน L3
- **spec จากแปลน** (`design_spec.json`): LED 42 W/โมดูล (แปลน 141 โมดูล = 5.9 kW สำหรับห้อง 8.9 ม. — ต้องนับจริง), แอร์ 2×2000 W, ปั๊ม 3×150 W, พัดลม 15×15 W, ถัง 200 L (ชั้น 2–5) + 100 L ×2 (อนุบาลชั้น 1) → input สำหรับ L3
- **ระบบดับ 9–12 ก.ย. 2026**: ห้องปลูกขึ้นถึง 28–31 °C หลายช่วง; 11 ก.ย. Grow Controller ทั้งสองไม่ส่งข้อมูลทั้งวัน ขณะที่ CO₂ controller อ่าน 31–34 °C ตลอดวัน → แอร์/ระบบดับ (ไฟดับ?) ควรถามผู้ดูแล
- **pH ออกนอกช่วง 5.5–6.5** บ่อย (gc1 ~840 ชม., gc2 ~990 ชม.) และ EC ต่างจาก setpoint >0.3 mS/cm นานๆ ครั้ง → ดูตาราง `iot_events.csv`
