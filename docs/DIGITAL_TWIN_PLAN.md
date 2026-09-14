# แผนการสร้าง Digital Twin ของ SIS PFAL ด้วย Jupyter Notebook

**โครงการโรงประลอง · วิทยาลัยบูรณาการศาสตร์ มหาวิทยาลัยเกษตรศาสตร์** — ระบบนี้เรียกว่า **SIS PFAL**

> จัดทำ 13 ก.ย. 2026 — อิงจากไฟล์ `SIS PFAL.ply`, เว็บผู้ผลิต Civic Agrotech และ dashboard ThingsBoard (cat-smartgrow.com) ที่ดึงข้อมูลจริงมาตรวจแล้ว
> รูปประกอบทั้งหมดใน `docs/plan_figures/` เป็นภาษาอังกฤษเพื่อนำไปใช้ในบทความได้
> **โครงสร้างโปรเจค / วิธีติดตั้ง / สถานะล่าสุด ดูที่ [`../README.md`](../README.md)** — เอกสารนี้เป็นแผนงานและบันทึกการวิเคราะห์ข้อมูล

---

## 1. สิ่งที่มีอยู่แล้ว (จากการตรวจสอบไฟล์จริง)

### 1.1 Point cloud `data/raw/pointcloud/SIS PFAL.ply`
| รายการ | ค่า |
|---|---|
| รูปแบบ | ASCII PLY, 80 MB, **1,020,300 จุด** |
| ข้อมูลต่อจุด | ตำแหน่ง (x,y,z), เวกเตอร์ normal (nx,ny,nz), สี RGB |
| ระบบพิกัด | หน่วยเมตร, **แกน Y ชี้ขึ้น** (ลักษณะสแกนจาก iPhone/iPad LiDAR เช่น Polycam/Scaniverse) |
| ห้องเอียงจากแกน | ~2° (ต้องหมุนให้ตรงก่อนใช้งาน) |
| โหลดด้วย numpy | ~0.3 วินาที (ไม่จำเป็นต้องแปลงไฟล์ แต่ควร cache เป็น `.npz`) |

### 1.2 ขนาดห้องและชั้นปลูกที่วัดได้จาก point cloud
| องค์ประกอบ | ขนาดที่วัดได้ |
|---|---|
| พื้นห้องภายใน | กว้าง **~3.2 ม.** × ยาว **~7.2 ม.** |
| ความสูงพื้น–เพดาน | **~2.56 ม.** (พื้น y = −1.46, เพดาน y = +1.10) |
| ชั้นปลูก (rack) | 1 แถวกลางห้อง กว้าง **~1.05 ม.** × ยาว **~5.3 ม.** มีทางเดินสองข้าง |
| จำนวนชั้น | **5 ชั้นปลูก** ที่ความสูงจากพื้น ≈ 0.38 / 0.86 / 1.22 / 1.66 / 2.02 ม. (ระยะห่างชั้น ~0.4 ม.) + โครงบน ~2.46 ม. |
| อื่นๆ | พื้นสีเขียว, มีอุปกรณ์สีเข้มติดผนังด้านขวา (น่าจะ AC / ตู้ควบคุม), จุดสแกนเลยประตูออกไปด้านนอกเล็กน้อย (ต้อง crop ทิ้ง) |

รูปประกอบ: `docs/plan_figures/scan_views.png` (มุมบน/ข้าง/หน้า) และ `docs/plan_figures/scan_height_slabs.png` (ตัดขวางตามความสูง)

### 1.3 สภาพแวดล้อม Python บนเครื่อง
- system Python 3.9.6 มี numpy, pandas, scipy, sklearn, matplotlib, plotly, ipywidgets แต่ไม่มี open3d และ `jupyter`
- **ทำแล้ว (13 ก.ย. 2026)**: สร้าง `.venv` (Python 3.9.6) ที่ root โปรเจค ติดตั้งตาม `requirements.txt` (รวม open3d 0.18, plotly, ipykernel) และลงทะเบียน kernel `pfal-twin` — ดูขั้นตอนใน README

### 1.4 ข้อมูล IoT — อุปกรณ์เป็นของ Civic Agrotech (civicagrotech.com)
จากข้อมูลบนเว็บผู้ผลิต (สายผลิตภัณฑ์ "PFAL ECO System") สรุปได้ว่า (ข้อมูลจริงที่ดึงมาแล้วอยู่ที่ `data/raw/iot/`):

| อุปกรณ์ | วัด/ควบคุมอะไร | การเชื่อมต่อ/ข้อมูล |
|---|---|---|
| **Controller Gen3 / Plus+** (Smart Grow Controller) | EC, pH, อุณหภูมิน้ำ, อุณหภูมิ/RH อากาศ; ควบคุมผสมปุ๋ย ปั๊ม ตั้งเวลาเปิด-ปิด และ **dim ไฟ LED** อัตโนมัติ | จอ touch screen, WiFi, LINE Notify |
| **CO₂ and Environment Controller** | CO₂ (NDIR + MOX), อุณหภูมิ, RH, VOC, ความดันอากาศ, **VPD**; ควบคุมจ่าย CO₂ ตาม set point | จอ 10.1", WiFi, ดูผ่านมือถือ, แจ้งเตือน LINE |
| **IoT Sensor System** | ชุดเซ็นเซอร์อุตสาหกรรม (ในภาพ): อุณหภูมิ/RH, CO₂ transmitter, PAR/แสง, มิเตอร์ไฟฟ้า (kWh), มิเตอร์น้ำ, ความดันต่าง (differential pressure), pH probe, EC/ระดับน้ำ, soil sensor | ดูสถานะออนไลน์ผ่านมือถือ, **เก็บประวัติย้อนหลัง 1 ปี**, แจ้งเตือนทุก 1 ชม. |
| **Control Box LED Grow Light** | ตั้งเวลา 16 โปรแกรม, หรี่ไฟ 0–220 Vac, สูงสุด 300 W/กล่อง | ไม่ระบุการเชื่อมต่อข้อมูล |
| **PPFD Meter** | วัด PPFD แบบพกพา | ใช้วัดด้วยมือ (สำหรับทำ light map) |

### 1.5 ระบบข้อมูลจริง: Dashboard "Vertical Smart Farming" บน cat-smartgrow.com = **ThingsBoard**
ลิงก์ dashboard สาธารณะที่ให้มาเป็นแพลตฟอร์ม **ThingsBoard** (open-source IoT platform) ซึ่ง **มี REST API ครบ** และ public dashboard ให้ token เข้าถึงข้อมูลได้โดยไม่ต้องขอสิทธิ์เพิ่ม — ทดสอบแล้วดึงข้อมูลย้อนหลังได้จริง (ตัวอย่าง 7 วันอยู่ที่ `data/raw/iot/sample_thingsboard_7d_hourly.csv` — คอลัมน์ใช้ prefix `gw.` = Gateway, `gc1.`/`gc2.` = Grow Controller 1/2, `co2.` = CO₂ controller)

| ขั้นตอน | API |
|---|---|
| ขอ token | `POST /api/auth/login/public` body `{"publicId": "b9506720-…"}` |
| โครงสร้าง dashboard | `GET /api/dashboard/c55eb730-…` |
| ค่าล่าสุด | `GET /api/plugins/telemetry/DEVICE/{id}/values/timeseries` |
| ประวัติ | `…/values/timeseries?keys=…&startTs=…&endTs=…&interval=…&agg=AVG` |

**อุปกรณ์ที่ public dashboard เปิดให้เห็น (4 ตัวในห้องนี้)**

| อุปกรณ์ (ThingsBoard) | ชื่อเครื่อง | ตัวแปรสำคัญ | ความถี่ |
|---|---|---|---|
| **IoT Gateway** `0f6e9810-…` | `DOAIoTGateway` (type PFALGateway) | `xy_md_20…24_t / _h` = อุณหภูมิ/RH จากเซ็นเซอร์ Modbus **XY-MD02** 5 ตัว (address 20–24), `waterLevel_1` | ทุก 10 นาที (มีช่วงขาดหายมาก ~20% uptime ในสัปดาห์ที่ดู) |
| **Grow Controller** (1) `0c57be70-…` | `GrowControllerPlus_30c922faf128` | `ec, ph, waterTemperature, ambTemperature, ambHumidity`, สถานะปั๊ม `pumpA/B/PH`, `led`, `currentStageBrightness1–4` (% dim 4 ช่อง), setpoint EC/pH, `plantDay` | ~5 นาที (ค่าตั้ง/สถานะเปลี่ยนเมื่อมี event) |
| **Grow Controller 2** `580b20b0-…` | `GrowControllerPlus_30c922fa7390` | เหมือนตัวที่ 1 + ค่าคาลิเบรต EC/pH, `rssiWiFi` | ~5 นาที |
| **CO₂ Controller** `ffc4b1f0-…` | `co2AndEnvironmentMeter_30c922faf2ec` | `CO2, temperature, humidity, VPD, VOC, pressure, Relay_co2` | ~30 นาที |
| GrowController 3–5 | — | **403 Forbidden** สำหรับ public user → น่าจะไม่ได้อยู่ในห้องนี้ / ไม่ได้แชร์ | — |

Dashboard จัดกลุ่มไว้: บล็อก **"ชั้นปลูกที่ 1"** = Grow Controller (1) + `xy_md_20`; บล็อก **"ชั้นปลูกที่ 2-5"** = Grow Controller 2 + `xy_md_21`
> ⚠️ **แก้ไข 14 ก.ย. 2026 (ยืนยันหน้างาน)**: ป้ายบล็อกนี้ไม่ตรงกับความจริง — **gc1 (ปลาย rack) = ถัง 200 L ผัก Growing stage ชั้น 2–5**, **gc2 (ข้าง rack) = ชุดปุ๋ยอนุบาล 2** (ถัง 100 L ใต้ชั้น 1 ปลายห้อง), อนุบาล 1 ไม่มีตัวควบคุม — และการจับคู่ `xy_md_20/21` กับชั้นก็ยังไม่ยืนยัน

**คุณภาพข้อมูลที่พบ (ต้องจัดการใน Notebook 04)**
- Gateway ขาดหายเป็นช่วงยาว (7 วันได้แค่ ~35 ชั่วโมงที่มีข้อมูล)
- `waterTemperature` ของ Grow Controller อ่านได้ 42–54 °C → ไม่สมเหตุสมผล (probe ไม่ได้ต่อ/เสีย) ห้ามใช้
- `ambTemperature` ของ Grow Controller อยู่ที่ 31–34 °C ตลอด ขณะที่เซ็นเซอร์ในชั้นปลูกอยู่ 21–30 °C → เป็นอุณหภูมิ **ในกล่องควบคุม** ไม่ใช่อากาศในห้อง
- CO₂ controller มี `humidity = −6` และ `pressure = 121.5` บางจุด → ต้องกรอง outlier
- `xy_md_24` ร้อนกว่าตัวอื่นชัดเจน (เฉลี่ย ~30 °C) และ `xy_md_20` รองลงมา (27 °C) ส่วน 21–23 ใกล้กัน (~24 °C) → ~~hot spot ชั้นบนสุด~~ **แก้ 14 ก.ย. 2026**: label บน dashboard ระบุ 24 = Outside (นอกห้อง), 20 = Inside (ห้องหน้า), 21–23 = Grower Room 1–3 (ผนังห้องปลูก) — ห้องปลูกจึงสม่ำเสมอที่ ~24 °C

### 1.6 การเดาตำแหน่งอุปกรณ์ในห้อง (จาก point cloud + dashboard + พฤติกรรมข้อมูล)
รูป: `docs/plan_figures/device_map_guess.png` (+ `.pdf` vector, ภาษาอังกฤษ ใช้ตีพิมพ์ได้) และ `docs/plan_figures/scan_wall_elevations.png`

| อุปกรณ์ | ตำแหน่งที่คาด (พิกัด scan, x = กว้าง, z = ยาว) | หลักฐาน | ความมั่นใจ |
|---|---|---|---|
| ชั้นปลูก 5 ชั้น | กลางห้อง x −1.7…−0.6, z −5.2…0.25 | ระนาบแนวนอน 5 ชั้นชัดเจน | สูง |
| เซ็นเซอร์ XY-MD02 ×5 (`xy_md_20…24`) | ~~1 ตัว/ชั้น~~ → **ติดผนังทั้งหมด** (ยืนยัน 14 ก.ย.): 21/22/23 บนผนังฝั่งแอร์ X 1.25 / 3.6 / 5.65 ม. สูง ~1.35 ม., 20 ห้องหน้าเหนือประตู, 24 นอกห้องบนกล่อง CO₂ | ภาพถ่าย + label widget บน dashboard (Grower Room 1–3 / Inside / Outside) | สูง (ลำดับ 1–3 ตามระยะจากประตูเป็นการเดา) |
| แอร์ติดผนัง ×2 | ผนังซ้าย (x ≈ −2.6) ที่ z ≈ −3.3…−2.4 และ −1.8…−0.9 สูง 2.0–2.3 ม. | รูปทรง indoor unit ~0.9×0.3 ม. ชัดในภาพผนัง | สูง |
| ท่อ PVC จ่ายน้ำ | ทางเดินซ้าย x ≈ −1.85 ตลอดความยาว rack แล้วหักไปปลายห้อง | สีฟ้าต่อเนื่อง | สูง |
| ถังสต็อกปุ๋ย A/B/pH ×3 | ทางเดินซ้าย x ≈ −1.85, z ≈ −4.1 / −4.6 / −5.0 บนพื้น | ถังกลมสีฟ้า 3 ใบเรียงกัน ตรงกับ 3 ปั๊ม (A, B, pH) ของ Grow Controller | ปานกลาง |
| ถังพักสารละลาย + Grow Controller 2 (ชั้น 2–5) | ปลายห้อง z −6.1…−5.2, x −2.0…−0.4 | ถังสีน้ำเงินเข้มบนพื้น + ท่อแยกขึ้นแต่ละชั้นที่ปลาย rack | ต่ำ–ปานกลาง |
| ถังพักสารละลาย + Grow Controller 1 (ชั้น 1) | ใต้/ข้างชั้น 1 ด้านหน้า z −1.25…−0.3, x −1.5…−0.6 | กล่องสีเข้ม 0.8×0.5×0.37 ม. บนพื้น + ขอบสีน้ำเงินเข้ม | ต่ำ |
| ตู้ควบคุม/ตู้ไฟ | ผนังซ้ายใกล้ประตู z ≈ −0.3…0.6 สูง 1.0–1.75 ม. มีท่อร้อยสายลงพื้น | กล่อง ~0.3×0.3 ม. + แผงสีเข้ม | ต่ำ (อาจเป็น Grow Controller, CO₂ controller หรือเบรกเกอร์) |
| CO₂ controller, IoT gateway | ไม่พบ | กล่องเล็ก ไม่ resolve ใน scan | — ต้องยืนยันหน้างาน |
| พัดลมระบายอากาศ | ผนังหน้า (z ≈ +1.0) x ≈ −2.1 สูง ~2.0 ม. | วงกลม ⌀ ~0.25 ม. | ปานกลาง |
| ประตู | ผนังหน้า z ≈ +1.0 ฝั่งขวา x ≈ −0.2…0.4 | จุด scan ทะลุออกนอกห้องบริเวณนี้ | ต่ำ |
| ชั้นวาง/โต๊ะ | มุมขวาปลายห้อง x −0.5…0.3, z −5.9…−4.6 | ระนาบหลายชั้น 0.25/0.45/0.85 ม. | ปานกลาง |
| แผงมืด ×2 บนผนังขวา | x ≈ +0.4, z −3.9…−1.6 สูง 1.1–2.2 ม. | สี่เหลี่ยม ~1.1×1.1 ม. สีเข้ม (หน้าต่าง/ช่องระบายอากาศ/แผงไฟ?) | ต่ำ |

> **อัปเดต 13 ก.ย. 2026 — ตรวจกับภาพถ่ายหน้างานแล้ว** (`docs/SITE_SURVEY_2026-09-13.md`): แอร์/ประตู/ชั้นวาง/ถังพักถูกต้อง; "แผงมืด" = หน้าต่างกระจก 2 บานหันเข้าร้านกาแฟ (มีไอน้ำเกาะ); "ตู้ควบคุม" = CO₂ & environment controller; ถังสต็อกเป็นแกลลอนไม่ใช่ถังกลม; gc1 อยู่ปลาย rack ข้างถังพัก (ยืนยันด้วยค่าบนจอ), gc2 ปลาย rack ฝั่ง Y=W; พบ gateway (เสาอากาศ 2 ต้น ผนัง Y=0), dosing box 2 ชุด, เครื่องลดความชื้น, พัดลมหมุนเวียน 3 ตัว/ชั้นที่ปลาย rack ทั้งสองด้าน; **XY-MD02 ทั้ง 5 ตัวติดผนัง (W1–W5) → สมมติฐาน 1 ตัว/ชั้นผิด; ยังไม่รู้ address↔จุด** · ชั้น 1 แบ่ง 2 ฝั่ง มีถังพักใต้ชั้นฝั่งละใบ · กล่องพัดลม 3 กล่อง (ชั้นล่าง / 4 ชั้น / อนุบาล) · สแกนชุด 2 ยืนยันขนาดห้องภายใน ±8 ซม.

> **อัปเดต 14 ก.ย. 2026** — ได้แปลนออกแบบของ Civic Agrotech (`data/raw/doc/`, สรุปใน `docs/DESIGN_VS_BUILT.md`): อาคาร 8.9 ม. ตามแปลน = ห้องปลูก 7.12 ม. + ห้องหน้า (ซิงค์) ~1.78 ม. ที่ point cloud ไม่ได้เก็บ; แปลนยืนยันโครงสร้าง อนุบาล 1/2 (ชั้นล่าง 2 ฝั่ง ถัง 100 L ×2) + growing 4 ชั้น (ถัง 200 L) และระบุทิศทางท่อ (จ่ายด้านประตู, กลับทางท่อยืนฟ้าปลายห้อง); spec ไฟฟ้า/LED เก็บใน `design_spec.json` สำหรับ L3

**สิ่งที่ต้องยืนยันหน้างาน (ใช้เวลา ~15 นาที)**: ถ่ายรูป + วัดตำแหน่งของ XY-MD02 ทั้ง 5 ตัว (ชั้นไหน, ช่วงหัว/กลาง/ท้าย rack, ความสูง), กล่อง CO₂ controller, gateway, Grow Controller ทั้ง 2 กล่อง, และแผงมืดบนผนังขวาคืออะไร

---

## 2. Digital Twin คืออะไรในบริบทนี้ (แนวคิด)

Digital twin ของห้อง PFAL = **แบบจำลอง 3 มิติของห้อง + ข้อมูลเซ็นเซอร์จริงที่ผูกกับตำแหน่งในห้อง + แบบจำลองคำนวณ** ที่ทำให้เรา

1. **เห็น** สภาพในห้อง ณ เวลาใดๆ บนโมเดล 3 มิติ (อุณหภูมิ/ความชื้น/แสง/CO₂ แต่ละชั้น แต่ละโซน)
2. **ย้อนดู** ประวัติ และหาจุดที่สภาพแวดล้อมไม่สม่ำเสมอ (hot spot, แสงไม่พอ)
3. **ทดลอง what-if** เช่น ปรับ photoperiod / ความเข้มแสง / setpoint แล้วดูผลต่อพลังงานและผลผลิตโดยยังไม่ต้องลองในห้องจริง
4. **เตือน/ตัดสินใจ** จาก KPI ที่คำนวณอัตโนมัติ

แบ่งเป็น 3 ระดับความสมบูรณ์ — ทำทีละระดับ ใช้งานได้ตั้งแต่ระดับแรก:

| ระดับ | ชื่อ | ได้อะไร |
|---|---|---|
| L1 | **Geometry twin** | โมเดล 3 มิติของห้อง+ชั้นปลูกที่ถูกต้องตามสัดส่วนจริง แบ่งโซนได้ |
| L2 | **Data twin** | เซ็นเซอร์ IoT แสดงบนโมเดล 3 มิติ ย้อนเวลาได้ heatmap รายชั้น |
| L3 | **Simulation twin** | โมเดลแสง/ความร้อน/CO₂/การเจริญเติบโต + what-if + KPI |

---

## 3. โครงสร้างโปรเจค (รวมเป็นโปรเจคเดียวที่ `PFAL/` แล้ว 13 ก.ย. 2026)

```
PFAL/
├─ README.md                    ← จุดเริ่มต้น: ติดตั้ง, โครงสร้าง, สถานะ
├─ requirements.txt / .venv/    ← สภาพแวดล้อม Python (kernel "pfal-twin")
├─ docs/
│   ├─ DIGITAL_TWIN_PLAN.md     ← เอกสารนี้
│   └─ plan_figures/            ← รูปวิเคราะห์เบื้องต้น (ภาษาอังกฤษ)
├─ data/
│   ├─ raw/                     ← ข้อมูลดิบ (ไม่แก้)
│   │   ├─ pointcloud/SIS PFAL.ply
│   │   └─ iot/sample_thingsboard_7d_hourly.csv   (+ Parquet จาก notebook 04)
│   ├─ processed/               ← raw.npz (cache PLY), pfal_clean.npz (align/crop/label แล้ว)
│   ├─ model/room_model.json    ← พารามิเตอร์ห้อง (ขนาด, ชั้น, transform) = single source of truth
│   └─ sensors/sensor_map.csv   ← ตำแหน่งเซ็นเซอร์ในห้อง (notebook 03)
├─ pfal_twin/                   ← โค้ดที่ใช้ซ้ำ
│   ├─ io.py        (โหลด PLY / model / clean cloud)
│   ├─ geometry.py  (align, crop, tiers, rack, segment, symmetrize, zones)
│   ├─ viz.py       (matplotlib + plotly 3D helpers, show3d เต็มจอ)
│   ├─ layout.py    (ตำแหน่งเซ็นเซอร์/อุปกรณ์ — notebook 03)
│   ├─ hydraulics.py   (โครงข่ายท่อ + แอนิเมชัน — notebook 03b)
│   ├─ schematic.py    (ผังระบบน้ำ + process flow — notebook 03b)
│   ├─ thingsboard.py  (REST API, backfill, QC, channel map — notebook 04)
│   ├─ models.py       (L3: แสง / ความร้อน / CO₂ / การเติบโต / crop mix 700 หลุม — notebook 06)
│   ├─ cropviz.py      (ผังรายหลุม 2D/3D)
│   └─ twin.py         (**DigitalTwin** facade — API เดียวรวมทุกชั้น; notebook 00/05/06 ใช้ตัวนี้)
├─ notebooks/
│   ├─ 00_quickstart.ipynb           ✅ ใช้ twin ผ่าน DigitalTwin API
│   ├─ 01_pointcloud_explore.ipynb   ✅
│   ├─ 02_geometry_model.ipynb       ✅ (+ สแกน 2, เทียบแปลนออกแบบ)
│   ├─ 03_zones_and_sensor_map.ipynb ✅
│   ├─ 03b_hydraulics.ipynb          ✅ (ท่อ + การไหล)
│   ├─ 04_iot_ingest.ipynb           ✅
│   ├─ 05_twin_dashboard.ipynb       ✅ (บาง — เรียก DigitalTwin)
│   └─ 06_simulation_whatif.ipynb    🟡 โครง L3 (พารามิเตอร์สมมติ; crop mix แสดง 3-D)
├─ app/streamlit_app.py         ← web dashboard บน DigitalTwin (ระยะ 5a)
├─ figures/                     ← รูปที่ notebook สร้าง (ภาษาอังกฤษ)
└─ scripts/make_notebooks.py    ← สร้าง notebook 00–06 ใหม่จากสคริปต์
```

### Notebook 01 — สำรวจ point cloud (L1)
- โหลด PLY → numpy (cache เป็น `.npz`)
- สถิติ: bounding box, histogram ความสูง, ความหนาแน่นจุด
- ภาพมุมบน / ข้าง / ตัดขวาง (แบบที่อยู่ใน `plan_figures/`)
- แสดง 3 มิติแบบหมุนได้ด้วย plotly (ลดจุดเหลือ ~200k เพื่อความลื่น)

### Notebook 02 — สร้างโมเดลเรขาคณิตห้อง (L1)
- **Align**: หมุนห้อง ~2° ให้ผนังขนานแกน, เลื่อนให้พื้น = 0 และมุมห้อง = (0,0), แปลงเป็น Z-up ตามมาตรฐานวิศวกรรม
- **Crop**: ตัดจุดนอกห้อง (ส่วนที่เลยประตูออกไป)
- **Segment** ด้วย normal vector + ความสูง: พื้น / เพดาน / ผนัง 4 ด้าน / ชั้นปลูกแต่ละชั้น (ใช้ RANSAC plane fitting ของ open3d หรือ sklearn)
- **Extract parameters**: ขนาดห้อง, ตำแหน่ง+ขนาด rack, ความสูงแต่ละชั้น → บันทึก `room_model.json`
- **Parametric model**: สร้างกล่องห้อง + ชั้นปลูกจาก JSON (เป็น mesh เบาๆ) ซ้อนทับ point cloud เพื่อตรวจว่าตรงกัน
- (ทางเลือก) สร้าง mesh ด้วย Poisson reconstruction เพื่อความสวยงาม — ไม่จำเป็นสำหรับ twin

### Notebook 03 — แบ่งโซน + แผนที่เซ็นเซอร์ (L1→L2)
- แบ่ง rack เป็น **โซน = ชั้น × ช่วงความยาว** เช่น 5 ชั้น × 3 ช่วง = 15 โซน (ปรับได้)
- แบ่งอากาศในห้องเป็น voxel grid (เช่น 0.5 ม.) สำหรับ interpolate ค่าเซ็นเซอร์
- กำหนดตำแหน่งเซ็นเซอร์แต่ละตัวในพิกัดห้อง (`sensor_map.csv`) — วัดจริงด้วยตลับเมตร หรือคลิกเลือกจุดบน point cloud
- ผลลัพธ์: ภาพ 3 มิติที่มีโซนและจุดเซ็นเซอร์แสดงชัดเจน

### Notebook 04 — นำเข้าข้อมูล IoT จาก ThingsBoard (L2)
- **ดึงตรงจาก ThingsBoard REST API** (ทดสอบแล้วใช้ได้ด้วย public token): ฟังก์ชัน `fetch_telemetry(device_id, keys, start, end, interval, agg)` แล้วเก็บเป็น Parquet แบบ long format `time, device, key, value`
- ดึงย้อนหลังให้มากที่สุดเท่าที่ ThingsBoard เก็บไว้ (ตรวจ TTL ของระบบ — เว็บผู้ผลิตบอกเก็บ 1 ปี) เป็น backfill ครั้งแรก จากนั้นดึงเพิ่มแบบ incremental
- ทำความสะอาด: timestamp → Asia/Bangkok, resample 10 นาที, กรอง outlier (humidity < 0, pressure > 110 kPa, waterTemperature ทั้งคอลัมน์), ทำเครื่องหมายช่วงที่ gateway offline
- แยก **ตัวแปรสภาพแวดล้อม** (T/RH 5 ชั้น, CO₂, VPD) ออกจาก **ตัวแปรควบคุม** (led, brightness, pump state, relay CO₂, setpoint) — ตัวหลังคือ input ของโมเดล L3
- ทางเลือกสำรองถ้าสิทธิ์ public ถูกปิดภายหลัง: ขอ user account ของ ThingsBoard จาก Civic Agrotech (API เดิมทุกอย่าง) หรืออ่าน RS485 จาก XY-MD02 โดยตรง (register map เป็นสาธารณะ: address 0x0001 = temp×10, 0x0002 = RH×10)

### Notebook 05 — Twin dashboard (L2)
- โมเดล 3 มิติ + ค่าเซ็นเซอร์ล่าสุดเป็นสี/ตัวเลขบนโซน
- **Time slider** (ipywidgets) เลื่อนดูย้อนหลัง
- Heatmap รายชั้น (มุมบน) ของอุณหภูมิ / RH / PPFD โดย interpolate จากเซ็นเซอร์ (IDW หรือ RBF)
- KPI cards: DLI ต่อชั้น, VPD, ความสม่ำเสมอของแสง (uniformity), ค่าเบี่ยงเบนจาก setpoint, พลังงาน/วัน
- แจ้งเตือนเมื่อค่าออกนอกช่วง (ตารางสรุปเหตุการณ์)

### Notebook 06 — Simulation & what-if (L3)
- **แสง**: โมเดล PPFD จากตำแหน่ง LED (Lambertian / inverse-square) → เทียบกับค่าที่วัดจริง → uniformity map แต่ละชั้น, คำนวณ DLI
- **ความร้อน**: สมดุลพลังงานอย่างง่าย (ความร้อนจาก LED + ผนัง + HVAC) → คาดการณ์อุณหภูมิ, โหลดแอร์
- **CO₂**: mass balance (การจ่าย CO₂ − การใช้ของพืช − การรั่ว)
- **การเจริญเติบโต**: โมเดลผักสลัดอย่างง่าย (thermal time + light-use efficiency) → คาดวันเก็บเกี่ยว/น้ำหนัก
- **What-if**: ปรับ photoperiod, PPFD, setpoint อุณหภูมิ → ดูผลต่อพลังงาน (kWh, บาท) และผลผลิต
- ปรับพารามิเตอร์โมเดลด้วยข้อมูลจริง (calibration) เมื่อมีข้อมูลสะสมพอ

---

## 4. เครื่องมือ (Tech stack) ที่แนะนำ

| งาน | ไลบรารี | เหตุผล |
|---|---|---|
| Point cloud | `open3d` (หลัก), `numpy`, `scipy` | อ่าน PLY, downsample, RANSAC plane, normal, mesh |
| 3D แสดงผลใน notebook | `plotly` (หลัก), `pyvista` + `trame` (ทางเลือกถ้าจุดเยอะ) | plotly ทำงานได้ทันทีใน JupyterLab, หมุน/ซูม/hover |
| ข้อมูล | `pandas`, `pyarrow` (Parquet) | เก็บ time series ได้เร็วและเล็ก |
| Interactive | `ipywidgets` | slider เวลา, เลือกโซน |
| แบบจำลอง | `scipy`, `numpy` | interpolate, สมการสมดุล |
| Dashboard แยกจาก notebook (ภายหลัง) | `voila` หรือ `panel` | เปลี่ยน notebook 05 เป็นเว็บให้ทีมดูได้โดยไม่ต้องรันโค้ด |

### การติดตั้ง
ใช้ `python3 -m venv` + `requirements.txt` ที่ root โปรเจค (ขั้นตอนอยู่ใน README) — ไม่ได้ใช้ `uv` ตามที่เสนอไว้เดิม เพราะ Python 3.9 บนเครื่องรองรับ open3d 0.18 ได้อยู่แล้ว

---

## 5. ข้อมูลที่ต้องการจากคุณก่อนเริ่ม L2

### 5A. คำถามที่ควรถาม Civic Agrotech
1. ขอ **user account ของ ThingsBoard** (สิทธิ์อ่าน) เผื่อ public dashboard ถูกปิด และเพื่อเข้าถึง GrowController 3–5 ถ้าเกี่ยวข้อง
2. ThingsBoard เก็บ telemetry ย้อนหลังนานเท่าไร (TTL) — ถ้าสั้นกว่า 1 ปี ต้องเริ่ม backfill ทันที
3. `waterTemperature` อ่านได้ 45–54 °C — probe เสียหรือไม่ได้ต่อ?
4. IoT Gateway (`DOAIoTGateway`) offline บ่อย — สาเหตุ (WiFi? ไฟ?) และแก้ได้ไหม
5. หลอด LED: รุ่น, W/หลอด, spectrum, จำนวน/ชั้น, และ `currentStageBrightness1–4` map กับชั้นไหน/โซนไหน
6. XY-MD02 แต่ละ address (20–24) ติดตั้งที่ชั้นไหน (ยืนยันการเดาในข้อ 1.6)

### 5B. ข้อมูลที่รวบรวมได้เองในห้อง
1. **รายการเซ็นเซอร์ที่ติดตั้งจริง** (จากชุด IoT + controller): ตัวไหนบ้าง จำนวนกี่ตัว
2. **ตำแหน่งเซ็นเซอร์**: อยู่ชั้นไหน ช่วงไหนของ rack หรือติดผนังตรงไหน (ถ่ายรูป + วัดระยะจากมุมห้อง จะแปลงเป็นพิกัดในโมเดล)
3. **screenshot หน้าจอแอป/controller** ที่แสดงตัวแปรทั้งหมด — ใช้กำหนด schema ของข้อมูล
4. **ตารางเปิด-ปิดไฟ / โปรแกรม dim** ที่ตั้งไว้ใน controller
5. **HVAC**: ขนาดแอร์ (BTU), จำนวน, ตำแหน่ง, setpoint
6. **พืชที่ปลูก** และรอบการปลูก (เพื่อเลือกโมเดลการเจริญเติบโต)
7. **สิ่งที่อยากได้มากที่สุด** — ดูสภาพห้อง real-time? หา hot spot? วางแผนพลังงาน? เพื่อจัดลำดับความสำคัญ

---

## 6. แผนงานตามลำดับ (Roadmap)

| ระยะ | งาน | ผลลัพธ์ที่จับต้องได้ | ต้องการจากคุณ |
|---|---|---|---|
| **ระยะ 1** (L1) ✅ เสร็จ 13 ก.ย. 2026 | ตั้งค่า env, Notebook 01–02 | โปรเจครวมที่ `PFAL/` — venv, แพ็กเกจ `pfal_twin/`, notebook 01–02 รันผ่านแล้ว, `data/model/room_model.json` (ห้อง 7.12 × 3.01 × 2.58 ม., rack 5.43 × 1.04 ม., ชั้นที่ 0.39/0.81/1.27/1.69/2.05 ม.), โมเดลบังคับสมมาตร (rack กึ่งกลางความกว้าง ทางเดิน 0.985 ม. เท่ากันสองข้าง), ผนังเบี่ยงจากโมเดล < 3 ซม. | ยืนยันขนาดด้วยตลับเมตร |
| **ระยะ 2** (L1→L2) ✅ เสร็จ 13 ก.ย. 2026 | Notebook 03 | `zones.json` (5 ชั้น × 3 ช่วง), `sensor_map.csv`, `equipment_map.csv` — ตำแหน่งตามข้อ 1.6 แปลงเป็นพิกัดห้องแล้ว (`verified=False`) | ยืนยันตำแหน่งหน้างาน (checklist ท้าย notebook 03) |
| **ระยะ 3** (L2) ✅ เสร็จ 13 ก.ย. 2026 | Notebook 04–05 | backfill 1.24 ล้านตัวอย่าง (26 ธ.ค. 2025 → 13 ก.ย. 2026) เป็น Parquet, wide 10 นาทีผ่าน QC, twin 3 มิติ + time slider, KPI รายชั้น, `iot_events.csv`; พบ hot spot tier 5 (เฉลี่ย 30.7 °C) และ gateway offline ตั้งแต่กลาง ก.ค. | ถาม Civic Agrotech เรื่อง gateway offline (5A.4) |
| **ระยะ 4** (L3) 🟡 โครงเสร็จ 14 ก.ย. 2026 | Notebook 06 + `models.py` | PPFD/DLI จากกำลัง LED, สมดุลความร้อน (LED ≈ 55 % ของภาระ ~2.9 kW), CO₂ mass balance (λ fit จากข้อมูล ≈ 0.08 h⁻¹), lettuce model schematic, ตาราง what-if photoperiod×dim (`whatif_light_energy.csv`) | calibrate: PPFD map, นับ LED bar, ความหมาย `led`/`currentStageBrightness1–4`, COP แอร์, T ฝั่งร้านกาแฟ, น้ำหนักผักตอนเก็บ, บันทึกเติม CO₂ |
| **ระยะ 4.5** ✅ 14 ก.ย. 2026 | `twin.py` + Notebook 00 | `DigitalTwin` facade — API เดียวเรียกทุกชั้น (state/show/kpi/layout/water/L3/crop_mix 700 หลุม 3-D) | — |
| **ระยะ 5a** (web app) ✅ 14 ก.ย. 2026 | `app/streamlit_app.py` + `twin.live()/history()` | dashboard 4 หน้า (Live auto-refresh 60 วิ, History + time slider, Layout & water, What-if) รันในเครื่อง `scripts/run_app.sh` | — |
| **ระยะ 5b** (นำขึ้นเว็บ) ⏳ รอตัดสินใจ | ดูข้อ 6.1 | URL ให้ทีม/ผู้อ่านบทความเปิดได้ | เลือกที่แขวน (Streamlit Cloud / VM มก.), บัญชี hosting |

### 6.1 ระยะ 5 — ทำเป็นเว็บไซต์ (แผน, ยังไม่เริ่ม — บันทึก 14 ก.ย. 2026)

พร้อมทำแล้ว: `figures/html/` มีรูป 3-D เป็น HTML แยกไฟล์ (~10 MB) และ `DigitalTwin` เป็น API เดียวที่หน้าเว็บเรียกได้ตรง ๆ

**รูปแบบ 3 ทาง**

| แบบ | ทำจากอะไร | ได้ | ไม่ได้ | ดูแล |
|---|---|---|---|---|
| **A. เว็บนิ่ง (static)** | export notebook + รูป plotly HTML → HTML ล้วน (`scripts/build_site.py`) | หมุน 3-D/เต็มจอได้, อ้างอิงถาวรได้, เหมาะเป็น supplementary material ของบทความ | ไม่ live, ปรับ what-if ไม่ได้ (ต้อง rebuild) | ฟรี ไม่ต้องมี server; GitHub Actions รัน notebook ใหม่ตามเวลาได้ → "กึ่ง live" |
| **B. Voilà** (อยู่ใน requirements แล้ว) | รัน notebook 00/05/06 เป็นหน้าเว็บ ซ่อนโค้ด | ทุกอย่างที่ notebook ทำ + widget | ต้องมีเครื่องรัน Python ตลอด, รับผู้ใช้พร้อมกันน้อย | เหมาะเดโมภายใน ไม่ใช่เว็บถาวร |
| **C. Web app (Streamlit)** ✅ มีแล้ว | `app/streamlit_app.py` ครอบ `DigitalTwin` | dashboard จริง: เลือกเวลา → 3-D, slider % ผัก → 3-D รายหลุม, ปุ่มดึง ThingsBoard | ต้องมี server | มี hosting ฟรี |

**แนะนำ: A + C คู่กัน** — A แนบบทความ (นิ่ง ไม่ล่ม), C ใช้งานจริง/เดโม

**ที่แขวน**

| เป้าหมาย | ที่ | หมายเหตุ |
|---|---|---|
| A | **GitHub Pages** (หรือ Cloudflare Pages / Netlify) | ฟรี; เปิดโค้ดคู่บทความ, ขอ DOI ผ่าน Zenodo ได้; Actions cron ดึง ThingsBoard แล้ว rebuild รายวัน |
| C (เดโมสาธารณะ) | **Streamlit Community Cloud** | ฟรี, deploy จาก GitHub 5 นาที; *สาธารณะ*, RAM ~1 GB → ห้ามโหลด point cloud ใช้แค่ `room_model.json` + `zones.json` + `pipe_network.json` + `iot_10min.parquet` |
| C (ใช้จริง/ภายใน) | **VM ของ มก./SIS** | URL ใต้ `ku.ac.th` น่าเชื่อถือในบทความ; Docker + nginx; ต้องเปิด port ได้ |
| ทั้งสอง | **ThingsBoard cat-smartgrow.com** | เพิ่ม widget HTML/iframe ใน dashboard เดิม ชี้ไปหน้า A/C → sensor กับ twin อยู่หน้าเดียว |

**การเชื่อมข้อมูลจาก dashboard (ThingsBoard) มายัง twin บนเว็บ** — ตัวเชื่อมมีแล้ว: `twin.update_data()` ดึงเฉพาะข้อมูลใหม่ผ่าน REST API (public token) แล้วสร้างตาราง 10 นาทีใหม่

| แบบ | วิธี | ความสด |
|---|---|---|
| A static | GitHub Actions cron รัน `update_data()` → notebook → build | ช้าสุดตามรอบ cron (~1 ชม.) |
| C app | เรียก `update_data()` เมื่อเปิดหน้า/กด refresh, cache 5–10 นาที | ใกล้ real-time (อุปกรณ์ส่งทุก ~1 นาที) |
| C + WebSocket | subscribe telemetry ThingsBoard โดยตรง | real-time — เกินจำเป็นสำหรับบทความ |

ย้อนกลับได้ด้วย: iframe widget ใน dashboard ThingsBoard ชี้มาหน้า twin. ข้อจำกัด: public token ถูกปิดได้ (ควรขอ read-only account จาก Civic Agrotech เก็บเป็น secret), gateway `gw` offline ตั้งแต่กลาง ก.ค. → สดเฉพาะ gc1/gc2/co2, browser เรียก ThingsBoard ตรงไม่ได้ (CORS) ต้องผ่าน build step หรือ server

**ต้องทำก่อนขึ้นเว็บ**
1. ห้ามเผยแพร่ `data/raw/picture/` — IMG_2550 มีรหัส WiFi (อยู่ใน `.gitignore` แล้ว) และ contact sheet ใน `figures/` ต้องตรวจก่อน
2. point cloud 117 MB + `data/processed` 71 MB ไม่ใส่ git ธรรมดา → Git LFS หรือฝาก Zenodo/Drive แล้วให้สคริปต์ดาวน์โหลด
3. token ThingsBoard เป็น public read-only ตอนนี้โอเค แต่ถ้าเว็บดึงเองให้ใส่เป็น secret ของ platform ไม่ hard-code
4. ตรวจ `equipment_map.csv` / รูปว่าไม่มีสิ่งที่ฟาร์มไม่อยากเผยถ้าเปิดสาธารณะ

**งานเมื่อเริ่ม**: (1) `scripts/build_site.py` + `.github/workflows/site.yml` → หน้า static, (2) `Dockerfile` + secret สำหรับ token ให้ `app/streamlit_app.py` (มีแล้ว)

**ข้อเสนอสำหรับก้าวต่อไป**: ระยะ 1–3 เริ่มได้เลยทั้งหมดเพราะข้อมูลทั้งสองด้าน (point cloud + ThingsBoard API) พร้อมแล้ว — สิ่งเดียวที่ต้องทำหน้างานคือยืนยันตำแหน่งเซ็นเซอร์/กล่องควบคุมตามข้อ 1.6 และควรเริ่ม **backfill ข้อมูลจาก ThingsBoard ทันที** ก่อนที่ข้อมูลเก่าจะหมดอายุ

---

## 7. ความเสี่ยง / ข้อควรระวัง

- **ความแม่นยำของ LiDAR มือถือ** ประมาณ ±2–3 ซม. และมี noise/จุดซ้อน — เพียงพอสำหรับ layout และโซน แต่ควรวัดขนาดสำคัญ (ความยาว rack, ระยะชั้น) ด้วยตลับเมตรเพื่อยืนยัน
- **จุดหาย** ใต้ชั้นปลูกและหลังอุปกรณ์ — ใช้ parametric model (กล่อง) แทน mesh จาก point cloud โดยตรง
- **ข้อมูล IoT** มักมีปัญหา timestamp/timezone และค่าหาย — ต้องทำ QC ก่อน (Notebook 04)
- **การพึ่งพา public token ของ ThingsBoard**: ผู้ดูแลอาจปิด public dashboard ได้ทุกเมื่อ → ขอ user account สำรอง และเก็บสำเนาข้อมูลไว้ในเครื่อง (Parquet) ตั้งแต่ต้น
- **Gateway offline บ่อย** ทำให้ข้อมูล T/RH รายชั้นขาดเป็นช่วง — twin ต้องแสดง "ไม่มีข้อมูล" ชัดเจน ไม่ interpolate ข้ามช่วงยาว
- **เซ็นเซอร์มีน้อยจุด** (ปกติ 1–2 จุดต่อห้อง) ทำให้ heatmap รายชั้นเป็นการประมาณ — ถ้าต้องการเห็นความต่างระหว่างชั้นจริงๆ ต้องเพิ่มเซ็นเซอร์อุณหภูมิ/แสงราคาถูกทุกชั้น
- **โมเดลจำลอง (L3)** ต้องสอบเทียบกับข้อมูลจริง อย่าใช้ตัวเลขจากโมเดลตัดสินใจก่อน calibrate
- อย่าให้ notebook โตเกินไป — ย้ายฟังก์ชันที่เสถียรแล้วเข้า `pfal_twin/` เพื่อใช้ซ้ำ
