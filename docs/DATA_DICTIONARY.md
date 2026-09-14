# SIS PFAL — data dictionary

Store: `iot_10min.parquet` (one row per 10-min bin, time index Asia/Bangkok, columns `device.key`) and `thingsboard_long.parquet` (raw samples: `ts, device, key, value`). Both are refreshed every 30 min on branch `data`: https://github.com/Navavit/sis-pfal-digital-twin/tree/data

Coverage in this build: 2025-12-26 → 2026-09-15, 37,805 bins, 95 columns.

## Devices

| alias | device |
|---|---|
| `gw` | DOA IoT gateway — 5 × XY-MD02 T/RH units on RS-485 |
| `gc1` | Grow Controller Plus at the rack END — growing-stage loop, 200 L tank, tiers 2–5 |
| `gc2` | Grow Controller Plus at the rack SIDE — nursery-2 dosing set, 100 L tank |
| `co2` | CO₂ & environment controller |

## Columns

| column | meaning | aggregation | on ThingsBoard dashboard | non-empty bins |
|---|---|---|---|---|
| `co2.CO2` | CO₂ concentration (ppm) | measurement (mean of the 10-min bin) | yes | 4,972 |
| `co2.VOC` | VOC index | measurement (mean of the 10-min bin) | yes | 1,206 |
| `co2.VPD` | vapour-pressure deficit at the CO₂ controller (kPa) | measurement (mean of the 10-min bin) | yes | 4,826 |
| `co2.humidity` | RH at the CO₂ controller (%) | measurement (mean of the 10-min bin) |  | 4,653 |
| `co2.pressure` | barometric pressure (kPa) | measurement (mean of the 10-min bin) |  | 4,769 |
| `co2.temperature` | air T at the CO₂ controller (°C) | measurement (mean of the 10-min bin) |  | 4,916 |
| `gc1.ambHumidity` | controller ambient RH | measurement (mean of the 10-min bin) |  | 11,774 |
| `gc1.ambTemperature` | controller ambient T | measurement (mean of the 10-min bin) |  | 11,774 |
| `gc1.ec` | EC of the nutrient solution (mS/cm) | measurement (mean of the 10-min bin) | yes | 11,718 |
| `gc1.ph` | pH of the nutrient solution | measurement (mean of the 10-min bin) | yes | 11,774 |
| `gc2.ambHumidity` | controller ambient RH | measurement (mean of the 10-min bin) |  | 11,112 |
| `gc2.ambTemperature` | controller ambient T | measurement (mean of the 10-min bin) |  | 11,112 |
| `gc2.ec` | EC of the nutrient solution (mS/cm) | measurement (mean of the 10-min bin) | yes | 11,094 |
| `gc2.ph` | pH of the nutrient solution | measurement (mean of the 10-min bin) | yes | 11,112 |
| `gc2.rssiWiFi` |  | measurement (mean of the 10-min bin) |  | 2 |
| `gw.waterLevel_1` | water-level sensor (always 0 — not connected) | measurement (mean of the 10-min bin) |  | 3,439 |
| `gw.xy_md_20_h` | relative humidity (%) — XY-MD02 unit 20: Inside = anteroom (above the door) | measurement (mean of the 10-min bin) | yes | 3,445 |
| `gw.xy_md_20_t` | temperature (°C) — XY-MD02 unit 20: Inside = anteroom (above the door) | measurement (mean of the 10-min bin) | yes | 3,445 |
| `gw.xy_md_21_h` | relative humidity (%) — XY-MD02 unit 21: Grower room 1 (wall, X 1.25 m) | measurement (mean of the 10-min bin) | yes | 3,455 |
| `gw.xy_md_21_t` | temperature (°C) — XY-MD02 unit 21: Grower room 1 (wall, X 1.25 m) | measurement (mean of the 10-min bin) | yes | 3,455 |
| `gw.xy_md_22_h` | relative humidity (%) — XY-MD02 unit 22: Grower room 2 (wall, X 3.6 m) | measurement (mean of the 10-min bin) | yes | 3,448 |
| `gw.xy_md_22_t` | temperature (°C) — XY-MD02 unit 22: Grower room 2 (wall, X 3.6 m) | measurement (mean of the 10-min bin) | yes | 3,448 |
| `gw.xy_md_23_h` | relative humidity (%) — XY-MD02 unit 23: Grower room 3 (wall, X 5.65 m) | measurement (mean of the 10-min bin) | yes | 3,437 |
| `gw.xy_md_23_t` | temperature (°C) — XY-MD02 unit 23: Grower room 3 (wall, X 5.65 m) | measurement (mean of the 10-min bin) | yes | 3,437 |
| `gw.xy_md_24_h` | relative humidity (%) — XY-MD02 unit 24: Outside (on the CO2 box) | measurement (mean of the 10-min bin) | yes | 3,449 |
| `gw.xy_md_24_t` | temperature (°C) — XY-MD02 unit 24: Outside (on the CO2 box) | measurement (mean of the 10-min bin) | yes | 3,449 |
| `co2.Relay_co2` | CO₂ valve relay | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,670 |
| `gc1.aDosingTime` | part-A dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.alarmEC` | EC alarm flag | state (last value in the bin, forward-filled ≤ 7 days) |  | 1,009 |
| `gc1.bDosingTime` | part-B dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.currentStageBrightness1` | LED brightness channel 1 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.currentStageBrightness2` | LED brightness channel 2 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.currentStageBrightness3` | LED brightness channel 3 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.currentStageBrightness4` | LED brightness channel 4 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.ecDosingCount` | EC doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.ecSetPoint` | EC set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 13,312 |
| `gc1.ecStamp` | EC at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.ecWaiting` | wait between EC doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.led` | LED | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.mode` | controller mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.modePumpA` | pump A mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.modePumpB` | pump B mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.modePumpPH` | pump pH mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.modePumpWater` | circulation pump mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pHDosingCount` | pH doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pHDosingTime` | acid dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pHSetPoint` | pH set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 13,312 |
| `gc1.pHStamp` | pH at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pHWaiting` | wait between pH doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.plantDay` | plant day | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pumpA` | dosing pump A running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 13,312 |
| `gc1.pumpASpeed` | pump A speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pumpB` | dosing pump B running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 13,312 |
| `gc1.pumpBSpeed` | pump B speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pumpPH` | acid (pH) dosing pump running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 13,312 |
| `gc1.pumpPHSpeed` | pump pH speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pumpTypeEnable` | pump type enable | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.pwmWater` | circulation pump | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.stage` | growth stage | state (last value in the bin, forward-filled ≤ 7 days) |  | 13,312 |
| `gc1.task` | controller task | state (last value in the bin, forward-filled ≤ 7 days) | yes | 13,312 |
| `gc1.upTime` | controller uptime | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,230 |
| `gc2.aDosingTime` | part-A dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.alarmEC` | EC alarm flag | state (last value in the bin, forward-filled ≤ 7 days) |  | 1,009 |
| `gc2.bDosingTime` | part-B dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.currentStageBrightness1` | LED brightness channel 1 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.currentStageBrightness2` | LED brightness channel 2 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.currentStageBrightness3` | LED brightness channel 3 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.currentStageBrightness4` | LED brightness channel 4 (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.ecDosingCount` | EC doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.ecSetPoint` | EC set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 11,221 |
| `gc2.ecStamp` | EC at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.ecWaiting` | wait between EC doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.led` | LED | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.mode` | controller mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.modePumpA` | pump A mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.modePumpB` | pump B mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.modePumpPH` | pump pH mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.modePumpWater` | circulation pump mode | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pHDosingCount` | pH doses (count) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pHDosingTime` | acid dose (s per shot) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pHSetPoint` | pH set-point | state (last value in the bin, forward-filled ≤ 7 days) | yes | 11,221 |
| `gc2.pHStamp` | pH at last dose | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pHWaiting` | wait between pH doses (s) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.plantDay` | plant day | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pumpA` | dosing pump A running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 11,221 |
| `gc2.pumpASpeed` | pump A speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pumpB` | dosing pump B running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 11,221 |
| `gc2.pumpBSpeed` | pump B speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pumpPH` | acid (pH) dosing pump running (1/0) | state (last value in the bin, forward-filled ≤ 7 days) | yes | 11,221 |
| `gc2.pumpPHSpeed` | pump pH speed (%) | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pumpTypeEnable` | pump type enable | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.pwmWater` | circulation pump | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.stage` | growth stage | state (last value in the bin, forward-filled ≤ 7 days) |  | 11,221 |
| `gc2.task` | controller task | state (last value in the bin, forward-filled ≤ 7 days) | yes | 11,221 |
| `gc2.upTime` | controller uptime | state (last value in the bin, forward-filled ≤ 7 days) |  | 14,310 |

QC: implausible values are removed (T 5–50 °C, RH 5–100 %, CO₂ 300–5000 ppm, EC 0.1–6, pH 3–10); `waterTemperature` is dropped (probe not immersed). `upTime` is in microseconds. Pump modes: 0 off, 1 manual, 2 auto.