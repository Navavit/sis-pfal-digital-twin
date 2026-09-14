"""Where things are in the room: sensors and equipment.

Two sources, merged here:
* point-cloud survey (docs/DIGITAL_TWIN_PLAN.md §1.6) — boxes given in the SCAN frame
  (LiDAR export, Y up) and converted with `room_model.json["transform_scan_to_room"]`;
* site photos of 2026-09-13 (data/raw/picture/IMG_2518–2573, see docs/SITE_SURVEY_2026-09-13.md)
  — items identified or re-located from photos are given directly in the ROOM frame.

`verified` = True only when a photo shows the item at that location. Positions estimated
from photos without a tape measure carry confidence "medium" (±0.3 m).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import SENSOR_DIR
from .geometry import apply_T, zone_of

SCAN_FLOOR_Y = -1.46   # floor level in the scan frame (Y up)

# Each entry: (name, frame, x0, x1, y0/z0..., category, confidence, verified, evidence)
#   frame "scan": (x0, x1, z0, z1) horizontal extent in scan coords + (h0, h1) height above floor
#   frame "room": (x0, x1, y0, y1, z0, z1) directly in the room frame
EQUIPMENT = [
    # --- structure / HVAC (scan geometry confirmed by photos)
    dict(name="AC indoor unit 1", frame="scan", box=(-2.60, -2.35, -3.30, -2.40, 2.00, 2.30), category="hvac",
         confidence="high", verified=True, evidence="IMG_2533/2537: two split-type indoor units on the Y=W wall; scan box 0.9 x 0.3 m"),
    dict(name="AC indoor unit 2", frame="scan", box=(-2.60, -2.35, -1.80, -0.90, 2.00, 2.30), category="hvac",
         confidence="high", verified=True, evidence="IMG_2533"),
    dict(name="Windows (2 panes, face the cafe)", frame="scan", box=(0.15, 0.40, -3.90, -1.60, 1.10, 2.20), category="structure",
         confidence="high", verified=True, evidence="IMG_2530/2549: the two 'dark panels' on the Y=0 wall are glass windows into SISKU Coffee; heavy condensation = heat gain / thermal bridge"),
    dict(name="Door (aluminium, glass top)", frame="scan", box=(-0.20, 0.40, 0.90, 1.00, 0.00, 2.00), category="structure",
         confidence="high", verified=True, evidence="IMG_2531: single leaf, Y=0 side of the X=0 wall"),
    dict(name="Exhaust fan (Hatari 200 mm, 23 W)", frame="scan", box=(-2.20, -1.95, 0.90, 1.00, 1.90, 2.15), category="hvac",
         confidence="high", verified=True, evidence="IMG_2532/2545: on the X=0 wall, Y=W side, near the ceiling"),
    dict(name="Seed germination shelf (3 tiers, T5 tubes, own fan box)", frame="scan", box=(-0.50, 0.30, -5.90, -4.60, 0.00, 0.85), category="furniture",
         confidence="high", verified=True, evidence="IMG_2529/2530/2551: PVC shelf with tube lights in the far corner, Y=0 side = 'ชั้นเพาะเมล็ด' (seed germination shelf) of the design drawing p.7; the fan box labelled 'อนุบาลพืช' belongs to it"),
    # --- controls / IoT boxes (photos)
    dict(name="CO2 & environment controller (display + sensor box + junction box)", frame="scan", box=(-2.60, -2.30, -0.30, 0.60, 1.00, 1.75), category="electrical",
         confidence="high", verified=True, evidence="IMG_2521/2539/2540: 10\" touch display, 'CO2 and environment meter sensor' box (3-OT-N000526) and a junction box where the RS485 cables converge, Y=W wall next to the door"),
    dict(name="TP-Link WiFi router (4 antennas)", frame="room", box=(1.85, 2.05, 0.00, 0.08, 1.30, 1.70), category="electrical",
         confidence="medium", verified=True, evidence="IMG_2549/2550: TP-Link router on the Y=0 wall ~1.5 m high before the windows — WiFi uplink of the grow controllers (rssiWiFi); the DOAIoTGateway box itself was not identified"),
    dict(name="Grow Controller gc1 - rack END = GROWING stage (200 L tank, tiers 2-5)", frame="room", box=(6.18, 6.26, 1.20, 1.55, 1.15, 1.45), category="electrical",
         confidence="high", verified=True, evidence="IMG_2527/2528: mounted on the far-end face of the rack, cables to the probe box on the 200 L tank; screen EC 1.75 / pH 5.7 / day 16 = ThingsBoard gc1; design p.7 'Grow Controller'. Loop CONFIRMED on site 2026-09-14 (the dashboard block title 'tier 1' is misleading)"),
    dict(name="Grow Controller gc2 - rack SIDE = NURSERY-2 dosing set (100 L tank)", frame="room", box=(5.65, 5.95, 2.02, 2.10, 1.10, 1.45), category="electrical",
         confidence="high", verified=True, evidence="IMG_2526: on the Y=W aisle face near the far end, cables to the junction box and dosing box by the nursery-2 tank; design p.7 'nursery-2 dosing control set'. Confirmed 2026-09-14; nursery 1 has no controller"),
    dict(name="Fan control box 'lower tier' (1 switch)", frame="room", box=(3.92, 4.25, 2.02, 2.30, 0.45, 0.78), category="electrical",
         confidence="high", verified=True, evidence="IMG_2545 (foreground box, FAN switch) / 2546 / 2533 + point cloud (box cluster X 3.92-4.25, z 0.45-0.78, protruding ~25 cm from the Y=W face): third box from the door; label 'กล่องควบคุมพัดลม ชั้นล่าง' -> tier-1 fans (probably the nursery-2 / far-end panel, since box 13 covers nursery 1)"),
    dict(name="Fan control box '4 tiers' (FAN1-FAN4 = tiers 2-5)", frame="room", box=(2.72, 3.08, 2.02, 2.30, 0.45, 0.78), category="electrical",
         confidence="high", verified=True, evidence="IMG_2545 (second box, 4 switches) / 2547 / 2533 + point cloud (box cluster X 2.72-3.08, z 0.45-0.78): second box from the door; label 'กล่องควบคุมพัดลม 4 ชั้น', FAN1-FAN4 -> growing tiers 2-5"),
    dict(name="Fan control box 'nursery plants' = nursery-1 fans (3 switches)", frame="room", box=(0.62, 0.80, 2.02, 2.30, 0.45, 0.76), category="electrical",
         confidence="high", verified=True, evidence="IMG_2548 + point cloud (dense cluster X 0.55-0.80, z 0.45-0.9 on the door-end post, Y=W side) + site note 2026-09-14: all three fan boxes are on the Y=W face; this one is on the end post nearest the door. 200 mm Sunon fan + 3 switches = the 3 circulation fans of the nursery-1 (door-end) panel; label 'กล่องควบคุมพัดลม อนุบาลพืช'"),
    dict(name="Dosing box A (gc2) + sample pot -> doses the nursery-2 tank", frame="room", box=(5.30, 5.85, 2.02, 2.15, 0.40, 0.70), category="nutrient",
         confidence="high", verified=True, evidence="IMG_2523/2524/2541 + site confirmation 2026-09-14: peristaltic dosing box (A/B 500 mL/min, pH 85 mL/min) with sample pot (EC/pH/water-temp probes) on the Y=W face, below gc2; its tubes go into the nursery-2 tank (item 20); jerrycans A, B and 3 % nitric acid below"),
    dict(name="Dosing box B (gc1) + Jecod 50 W DC pump controller -> doses the 200 L tank", frame="room", box=(5.90, 6.20, 2.02, 2.15, 0.40, 0.80), category="nutrient",
         confidence="medium", verified=True, evidence="IMG_2525/2542: second dosing box beside the blue return riser at the rack end -> by elimination the growing-stage (gc1) dosing set for the 200 L tank; Jecod DC controller = its circulation pump"),
    dict(name="Circulation fans, door end (3 per tier)", frame="room", box=(0.77, 0.85, 0.985, 2.025, 0.39, 2.40), category="hvac",
         confidence="high", verified=True, evidence="IMG_2520/2531/2551: fan panels with 3 axial fans at the end of every tier"),
    dict(name="Circulation fans, far end (3 per tier)", frame="room", box=(6.12, 6.20, 0.985, 2.025, 0.39, 2.40), category="hvac",
         confidence="high", verified=True, evidence="IMG_2533/2545"),
    # --- nutrient storage
    dict(name="Growing-stage tank (200 L, lid, sample pot + level sensor) - gc1", frame="room", box=(6.25, 7.05, 0.90, 1.95, 0.00, 0.60), category="nutrient",
         confidence="high", verified=True, evidence="IMG_2528/2543 + point cloud (blue, X 6.25-7.05, Y 0.9-1.95); design p.4/7: 200 L tank of the growing stage (tiers 2-5) with sample pot; controlled by gc1 (confirmed 2026-09-14)"),
    dict(name="Nursery-1 tank (100 L) under tier 1, door end - no controller", frame="room", box=(1.42, 1.90, 1.15, 1.85, 0.00, 0.33), category="nutrient",
         confidence="high", verified=True, evidence="IMG_2534/2535 + point cloud (blue box 0.48 x 0.70 x 0.33 m at X 1.4-1.9); site note: door-end half of tier 1 = nursery 1 (design p.7: 100 L)"),
    dict(name="Nursery-2 tank (100 L) under tier 1, far end - gc2", frame="room", box=(5.40, 5.90, 1.20, 1.85, 0.00, 0.33), category="nutrient",
         confidence="high", verified=True, evidence="IMG_2534/2535/2542 + point cloud (blue box at X 5.4-5.9); site note: far-end half (by the growing tank) = nursery 2 (design p.7: 100 L)"),
    dict(name="Stock-solution jerrycans (A, B, 3 % nitric acid)", frame="room", box=(5.10, 6.00, 2.15, 2.45, 0.00, 0.40), category="nutrient",
         confidence="high", verified=True, evidence="IMG_2523/2526/2541/2542 + point cloud (round blobs at X 5.2 / 5.5 / 5.75, Y 2.3 — the 'three drums' of the first scan analysis): 5-10 L jerrycans on the floor of the Y=W aisle under dosing box A"),
    dict(name="Dehumidifier (portable)", frame="room", box=(1.50, 1.95, 0.02, 0.36, 0.00, 0.60), category="hvac",
         confidence="high", verified=True, evidence="IMG_2520/2549 + point cloud (rounded object at X 1.5-1.95 against the Y=0 wall): on the floor of the Y=0 aisle below the router"),
    # --- ANTEROOM in front of the grow room (X < 0): the 8.9 m building of the design drawing is partitioned into a
    #     ~1.78 m anteroom with the sink (PVC outer door, IMG_2553) and the 7.12 m grow room (aluminium glass door).
    #     The anteroom was NOT scanned — its length is the design length minus the scanned room.
    dict(name="Anteroom with sink (not scanned; length = design 8.9 m - scanned 7.12 m)", frame="room", box=(-1.78, 0.00, 0.00, 3.01, 0.00, 2.58), category="structure", location="anteroom",
         confidence="medium", verified=True, evidence="site note 2026-09-14 + design drawing p.3/5 (sink + work table at the entrance end); outer PVC door in IMG_2553"),
    # --- OUTSIDE the building (under the porch in front of the anteroom) — drawn in a separate strip
    dict(name="CO2 cylinders x2 + regulator/flowmeter (outside)", frame="room", box=(-2.35, -1.95, 2.35, 2.75, 0.00, 1.55), category="co2", location="outside",
         confidence="medium", verified=True, evidence="IMG_2553/2554: two CO2 cylinders with a heated regulator (220 V, 210 W) and LPM flowmeter under the porch, left of the outer door seen from outside (Y=W side)"),
    dict(name="CO2 control box (outside, green pilot lamp)", frame="room", box=(-2.08, -1.88, 2.65, 2.95, 1.10, 1.50), category="co2", location="outside",
         confidence="medium", verified=True, evidence="IMG_2554: wall box with pilot lamp + socket feeding the regulator heater — the 'Relay_co2' actuator of the CO2 controller"),
    # --- OUTSIDE, service side beyond the far-end (X=L) wall: RO water plant + drain (positions schematic, from IMG_2577-2579 + pptx slide 3)
    dict(name="RO storage tank (slim, design 5 m3) - outside", frame="room", box=(7.45, 8.25, 0.20, 0.75, 0.00, 2.00), category="water", location="outside_far",
         confidence="low", verified=True, evidence="IMG_2577/2578/2579: grey slim tank in the service passage beside the container; pptx slide 3: 'RO storage tank 5 cu m'. Position schematic"),
    dict(name="Centrifugal pump (>= 3000 L/h) - outside", frame="room", box=(7.55, 7.85, 1.05, 1.35, 0.00, 0.35), category="water", location="outside_far",
         confidence="low", verified=True, evidence="IMG_2579: yellow centrifugal pump on a plinth in the passage; pptx slide 3: 'centrifugal pump not less than 3000 L/h'"),
    dict(name="RO filter set (3-stage cartridges, on the wall) - outside", frame="room", box=(7.60, 7.80, 1.45, 1.75, 0.90, 1.60), category="water", location="outside_far",
         confidence="low", verified=True, evidence="IMG_2579: filter housings on the masonry wall above the pump; pptx slide 3: 'RO filtration system'"),
    dict(name="Buried spent-solution tank (per plan; not seen)", frame="room", box=(8.45, 9.05, 2.05, 2.65, -0.60, 0.00), category="water", location="outside_far",
         confidence="low", verified=False, evidence="pptx slide 3: waste line leaves the far end to a buried tank for used nutrient solution; IMG_2577 shows the blue pipes running along the ground from the wall"),
]

# Sensors. placement: the name of an EQUIPMENT item, or (x, y, z) in the room frame.
# XY-MD02: the gateway reports FIVE Modbus addresses (xy_md_20..24) but only FOUR physical units were found in the
# photos (W1-W3 inside on the walls, W6 outside) — IMG_2536 is a close-up of W2 and the 'high white box' in IMG_2552/2527
# is an AC unit. The 5th reporting unit is in the ANTEROOM above the door (W4, IMG_2587). The ThingsBoard dashboard
# labels give the channel mapping (20 Inside, 24 Outside, 21-23 Grower Room 1-3) -> `key_prefix` below;
# the 1/2/3 order along the wall is assumed (door -> far end).
SENSORS = [
    # id,          device, key_prefix,  tier, placement,   confidence, verified, evidence
    ("XY-MD02 W1 (by CO2 display)",   "gw", "xy_md_21", 0, (1.25, 2.98, 1.35), "high",   True, "IMG_2521/2539: on the junction box beside the CO2 display, Y=W wall, ~1.35 m. Dashboard: 'Grower Room 1' = xy_md_21 (order 1-3 along the wall assumed)"),
    ("XY-MD02 W2 (under AC 1)",       "gw", "xy_md_22", 0, (3.60, 2.98, 1.30), "high", True, "IMG_2537 (+ close-up IMG_2536, same unit by the single conduit): on the Y=W wall below AC indoor unit 1; point cloud shows a small box at X~3.6, z~1.3"),
    ("XY-MD02 W3 (by conduit, above the nursery-2 tank)", "gw", "xy_md_23", 0, (5.65, 2.98, 1.40), "medium", True, "IMG_2538 + site note 2026-09-14: on the same Y=W wall as W2, beside the two vertical conduits, at about the same X as the nursery-2 tank (item 20, X 5.4-5.9); wall coverage in the scan is sparse there"),
    ("XY-MD02 W4 (ANTEROOM, above the door)", "gw", "xy_md_20", 0, (-0.06, 0.85, 2.20), "high", True, "IMG_2587: XY-MD02 with a small junction box on the anteroom side of the partition wall, above the door to the grow room, ~2.2 m high; channel xy_md_20 (mean 27.3 °C, 3.6 °C diurnal swing) fits an un-conditioned anteroom"),
    ("co2",        "co2", "",           0, "CO2 & environment controller (display + sensor box + junction box)", "high", True, "IMG_2521/2540: sensor box labelled 'CO2 and environment meter sensor'"),
    ("gw",         "gw",  "",           0, "CO2 & environment controller (display + sensor box + junction box)", "medium", True, "IMG_2539: the RS485 cables of the XY-MD02 units converge in the junction box beside the CO2 display — the gateway most likely sits there"),
    ("gc1",        "gc1", "",           0, "Grow Controller gc1 - rack END = GROWING stage (200 L tank, tiers 2-5)", "high", True, "IMG_2527/2528; growing-stage loop confirmed 2026-09-14"),
    ("gc2",        "gc2", "",           0, "Grow Controller gc2 - rack SIDE = NURSERY-2 dosing set (100 L tank)", "high", True, "IMG_2526; nursery-2 loop confirmed 2026-09-14"),
    ("waterLevel_1", "gw", "waterLevel_1", 0, (6.35, 1.90, 0.62), "medium", True, "IMG_2528/2544: small white float/level box on the 200 L growing-stage tank rim"),
    ("XY-MD02 W6 (OUTSIDE, on CO2 box)", "gw", "xy_md_24", 0, (-1.98, 2.80, 1.25), "high", True, "IMG_2554: XY-MD02 mounted outdoors on the CO2 control box; channel xy_md_24 (mean 30.7 °C, 7 °C day-night swing, peak 13:00) behaves like OUTDOOR air and is the likely match"),
]

# Hand-held reference readings (Testo 608-H1) taken during the photo survey — for checking the fixed sensors
REFERENCE_READINGS = [
    dict(time="2026-09-13 12:03", place="tray surface, tier 3 area, mid rack", t_c=22.5, rh=52.0, source="IMG_2551"),
    dict(time="2026-09-13 12:04", place="tray surface, tier 2-3 area", t_c=22.4, rh=49.1, source="IMG_2552"),
]


def equipment_room(model) -> pd.DataFrame:
    """EQUIPMENT -> axis-aligned boxes in the room frame, clipped to the room."""
    T = np.asarray(model["transform_scan_to_room"])
    L, W, H = model["room"]["L"], model["room"]["W"], model["room"]["H"]
    rows = []
    for e in EQUIPMENT:
        if e["frame"] == "scan":
            x0, x1, z0, z1, h0, h1 = e["box"]
            corners = np.array([[x, SCAN_FLOOR_Y + h, z] for x in (x0, x1) for z in (z0, z1) for h in (h0, h1)])
            r = apply_T(T, corners)
            lo, hi = r.min(0), r.max(0)
        else:
            x0, x1, y0, y1, z0, z1 = e["box"]
            lo, hi = np.array([x0, y0, z0]), np.array([x1, y1, z1])
        outside = e.get("location", "inside") != "inside"      # anteroom / porch items are not clipped to the grow room
        clip = (lambda v, hi_: float(v)) if outside else (lambda v, hi_: float(np.clip(v, 0, hi_)))
        rows.append(dict(name=e["name"], category=e["category"], frame=e["frame"], location=e.get("location", "inside"),
                         x0=clip(lo[0], L), x1=clip(hi[0], L), y0=clip(lo[1], W), y1=clip(hi[1], W), z0=clip(lo[2], H), z1=clip(hi[2], H),
                         confidence=e["confidence"], verified=e["verified"], evidence=e["evidence"]))
    return pd.DataFrame(rows).round(3)


def sensor_map(model, zones=None, equipment: pd.DataFrame | None = None, canopy_offset=0.20) -> pd.DataFrame:
    """Sensor positions in the room frame (see module docstring for provenance)."""
    K = model["rack"]
    eq = equipment if equipment is not None else equipment_room(model)
    eq = eq.set_index("name")
    xc, yc = 0.5 * (K["x0"] + K["x1"]), 0.5 * (K["y0"] + K["y1"])
    rows = []
    for sid, dev, prefix, tier, place, conf, ver, ev in SENSORS:
        if place == "tier":
            z = next(t["z"] for t in K["tiers"] if t["index"] == tier) + canopy_offset
            x, y = xc, yc
            placed_on = f"tier {tier} canopy (assumed)"
        elif isinstance(place, tuple):
            x, y, z = place
            placed_on = "photo estimate"
        else:
            b = eq.loc[place]
            x, y, z = 0.5 * (b.x0 + b.x1), 0.5 * (b.y0 + b.y1), 0.5 * (b.z0 + b.z1)
            placed_on = place
        rows.append(dict(sensor=sid, device=dev, key_prefix=prefix, tier=tier or np.nan, x=x, y=y, z=z,
                         zone=zone_of(zones, x, y, z) if zones else None, placed_on=placed_on,
                         location="outside" if x < -1.78 else "anteroom" if x < 0 else "outside_far" if x > 7.12 else "inside", confidence=conf, verified=ver, evidence=ev))
    return pd.DataFrame(rows).round(3)


def save_layout(sensors: pd.DataFrame, equipment: pd.DataFrame):
    p1 = SENSOR_DIR / "sensor_map.csv"; p2 = SENSOR_DIR / "equipment_map.csv"
    sensors.to_csv(p1, index=False); equipment.to_csv(p2, index=False)
    return p1, p2


def load_layout():
    return (pd.read_csv(SENSOR_DIR / "sensor_map.csv"), pd.read_csv(SENSOR_DIR / "equipment_map.csv"))
