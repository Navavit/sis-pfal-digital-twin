# SIS PFAL — data dictionary

Store: `iot_10min.parquet` (one row per 10-min bin, time index Asia/Bangkok, columns `device.key`) and `thingsboard_long.parquet` (raw samples: `ts, device, key, value`). The primary copy is the SIS PFAL SQL database (tables `iot_10min`, `iot_long`), updated every hour; a backup of both files is kept on branch `data`: https://github.com/Navavit/sis-pfal-digital-twin/tree/data. Electricity-meter readings (device `pm`, below) are stored the same way

Coverage when this page was last updated (17 Nov 2026): 2025-12-26 → 2026-11-17, 46,945 bins, 95 columns (the store keeps growing; the web app shows the current span).

## Devices

| alias | device |
|---|---|
| `gw` | DOA IoT gateway — 5 × XY-MD02 T/RH units on RS-485 |
| `gc1` | Grow Controller Plus at the rack END — growing-stage loop, 200 L tank, tiers 2–5 |
| `gc2` | Grow Controller Plus at the rack SIDE — nursery-2 dosing set, 100 L tank |
| `co2` | CO₂ & environment controller |
| `pm` | 3-phase electricity meter on the room's supply (Tuya, CTs on the mains; from 17 Nov 2026) — not in ThingsBoard, read by the collector; columns `pm.*`, see below |

## Electricity meter `pm`

Read every 10 min by `scripts/collector.py` through the Tuya device-sharing API (`pfal_twin/tuya_meter.py`) and kept with the sensors: raw readings are device `pm` in the raw store (`thingsboard_long.parquet`, database `iot_long`), and the 10-min table has them as columns `pm.<metric>` (10-min means; database columns `pm_<metric>`). They reach the database and branch `data` every hour, from 17 Nov 2026.

| metric | meaning |
|---|---|
| `power` | total active power, sum of the three phases (W) |
| `power_a`, `power_b`, `power_c` | active power per phase (W): **a = L1** (brown) socket outlets (breaker 2) + right-hand air conditioner (20); **b = L2** (black) LED lights of the growing tiers (22); **c = L3** (grey) room lighting (1) + left-hand air conditioner (18) (left/right facing the AC units). The meter sits on breakers 19/21/23 for its voltage but reads the whole panel |
| `voltage_a`, `voltage_b`, `voltage_c` | phase-to-neutral voltage (V) |
| `current_a`, `current_b`, `current_c` | phase current (A) |
| `energy` | energy counter, total forward energy (kWh; the meter counts 0.01 kWh) — only grows, so kWh per day = difference at midnight, interpolated between the readings around it |
| `temp` | breaker temperature (°C) |
| `leakage` | leakage current reported by the breaker |
| `fault` | fault code (0 = none) |
| `switch` | breaker closed = 1, open = 0 |

## Columns

| column | meaning | aggregation | on ThingsBoard dashboard | non-empty bins |
|---|---|---|---|---|
| `co2.CO2` | CO₂ concentration (ppm) | measurement (mean of the 10-min bin) | yes | 6,907 |
| `co2.VOC` | VOC index | measurement (mean of the 10-min bin) | yes | 3,040 |
| `co2.VPD` | vapour-pressure deficit at the CO₂ controller (kPa) | measurement (mean of the 10-min bin) | yes | 6,714 |
| `co2.humidity` | RH at the CO₂ controller (%) | measurement (mean of the 10-min bin) |  | 6,532 |
| `co2.pressure` | barometric pressure (kPa) | measurement (mean of the 10-min bin) |  | 6,648 |
| `co2.temperature` | air T at the CO₂ controller (°C) | measurement (mean of the 10-min bin) |  | 6,826 |
| `gc1.ambHumidity` | controller ambient RH | measurement (mean of the 10-min bin) |  | 15,141 |
| `gc1.ambTemperature` | controller ambient T | measurement (mean of the 10-min bin) |  | 15,141 |
| `gc1.ec` | EC of the nutrient solution (mS/cm) | measurement (mean of the 10-min bin) | yes | 15,085 |
| `gc1.ph` | pH of the nutrient solution | measurement (mean of the 10-min bin) | yes | 15,141 |
| `gc2.ambHumidity` | controller ambient RH | measurement (mean of the 10-min bin) |  | 14,083 |
| `gc2.ambTemperature` | controller ambient T | measurement (mean of the 10-min bin) |  | 14,083 |
| `gc2.ec` | EC of the nutrient solution (mS/cm) | measurement (mean of the 10-min bin) | yes | 13,947 |
| `gc2.ph` | pH of the nutrient solution | measurement (mean of the 10-min bin) | yes | 14,083 |
| `gc2.rssiWiFi` |  | measurement (mean of the 10-min bin) |  | 2 |
| `gw.waterLevel_1` | water-level sensor (always 0 — not connected) | measurement (mean of the 10-min bin) |  | 6,410 |
| `gw.xy_md_20_h` | relative humidity (%) — XY-MD02 unit 20: Inside = anteroom (above the door) | measurement (mean of the 10-min bin) | yes | 6,414 |
| `gw.xy_md_20_t` | temperature (°C) — XY-MD02 unit 20: Inside = anteroom (above the door) | measurement (mean of the 10-min bin) | yes | 6,414 |
| `gw.xy_md_21_h` | relative humidity (%) — XY-MD02 unit 21: Grower room 1 (wall, X 1.25 m) | measurement (mean of the 10-min bin) | yes | 6,428 |
| `gw.xy_md_21_t` | temperature (°C) — XY-MD02 unit 21: Grower room 1 (wall, X 1.25 m) | measurement (mean of the 10-min bin) | yes | 6,428 |
| `gw.xy_md_22_h` | relative humidity (%) — XY-MD02 unit 22: Grower room 2 (wall, X 3.6 m) | measurement (mean of the 10-min bin) | yes | 6,419 |
| `gw.xy_md_22_t` | temperature (°C) — XY-MD02 unit 22: Grower room 2 (wall, X 3.6 m) | measurement (mean of the 10-min bin) | yes | 6,419 |
| `gw.xy_md_23_h` | relative humidity (%) — XY-MD02 unit 23: Grower room 3 (wall, X 5.65 m) | measurement (mean of the 10-min bin) | yes | 6,413 |
| `gw.xy_md_23_t` | temperature (°C) — XY-MD02 unit 23: Grower room 3 (wall, X 5.65 m) | measurement (mean of the 10-min bin) | yes | 6,413 |
| `gw.xy_md_24_h` | relative humidity (%) — XY-MD02 unit 24: Outside (on the CO2 box) | measurement (mean of the 10-min bin) | yes | 6,430 |
| `gw.xy_md_24_t` | temperature (°C) — XY-MD02 unit 24: Outside (on the CO2 box) | measurement (mean of the 10-min bin) | yes | 6,430 |
| `co2.Relay_co2` | CO₂ valve relay | state (last value in the bin, forward-filled ≤ 7 days) |  | 18,614 |
| `gc1.aDosingTime` | part-A dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.alarmEC` | EC alarm flag | state (last value in the bin, forward-filled ≤ 7 days) |  | 1,009 |
| `gc1.bDosingTime` | part-B dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.currentStageBrightness1` | LED brightness channel 1 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.currentStageBrightness2` | LED brightness channel 2 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.currentStageBrightness3` | LED brightness channel 3 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.currentStageBrightness4` | LED brightness channel 4 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.ecDosingCount` | EC doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.ecSetPoint` | EC set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 17,834 |
| `gc1.ecStamp` | EC at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.ecWaiting` | wait between EC doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.led` | LED | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.mode` | controller mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.modePumpA` | pump A mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.modePumpB` | pump B mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.modePumpPH` | pump pH mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.modePumpWater` | circulation pump mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pHDosingCount` | pH doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pHDosingTime` | acid dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pHSetPoint` | pH set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 17,834 |
| `gc1.pHStamp` | pH at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pHWaiting` | wait between pH doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.plantDay` | plant day | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pumpA` | dosing pump A running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 17,834 |
| `gc1.pumpASpeed` | pump A speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pumpB` | dosing pump B running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 17,834 |
| `gc1.pumpBSpeed` | pump B speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pumpPH` | acid (pH) dosing pump running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 17,834 |
| `gc1.pumpPHSpeed` | pump pH speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pumpTypeEnable` | pump type enable | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.pwmWater` | circulation pump | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.stage` | growth stage | state (last value in the bin, forward-filled ≤ 7 days) |  | 17,834 |
| `gc1.task` | controller task | state (last value in the bin, forward-filled ≤ 7 days) | yes | 17,834 |
| `gc1.upTime` | controller uptime | state (last value in the bin, forward-filled ≤ 7 days) |  | 18,874 |
| `gc2.aDosingTime` | part-A dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.alarmEC` | EC alarm flag | state (last value in the bin, forward-filled ≤ 7 days) |  | 2,592 |
| `gc2.bDosingTime` | part-B dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.currentStageBrightness1` | LED brightness channel 1 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.currentStageBrightness2` | LED brightness channel 2 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.currentStageBrightness3` | LED brightness channel 3 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.currentStageBrightness4` | LED brightness channel 4 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.ecDosingCount` | EC doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.ecSetPoint` | EC set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 14,253 |
| `gc2.ecStamp` | EC at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.ecWaiting` | wait between EC doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.led` | LED | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.mode` | controller mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.modePumpA` | pump A mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.modePumpB` | pump B mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.modePumpPH` | pump pH mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.modePumpWater` | circulation pump mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pHDosingCount` | pH doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pHDosingTime` | acid dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pHSetPoint` | pH set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 14,253 |
| `gc2.pHStamp` | pH at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pHWaiting` | wait between pH doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.plantDay` | plant day | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pumpA` | dosing pump A running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 14,253 |
| `gc2.pumpASpeed` | pump A speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pumpB` | dosing pump B running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 14,253 |
| `gc2.pumpBSpeed` | pump B speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pumpPH` | acid (pH) dosing pump running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 14,253 |
| `gc2.pumpPHSpeed` | pump pH speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pumpTypeEnable` | pump type enable | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.pwmWater` | circulation pump | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.stage` | growth stage | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,253 |
| `gc2.task` | controller task | state (last value in the bin, forward-filled ≤ 7 days) | yes | 14,253 |
| `gc2.upTime` | controller uptime | state (last value in the bin, forward-filled ≤ 7 days) |  | 18,657 |

QC: implausible values are removed (T 5–50 °C, RH 5–100 %, CO₂ 300–5000 ppm, EC 0.1–6, pH 3–10); `waterTemperature` is dropped (probe not immersed). `upTime` is in microseconds. Pump modes: 0 off, 1 manual, 2 auto.