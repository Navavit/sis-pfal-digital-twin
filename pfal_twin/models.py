"""L3 simulation models for the PFAL twin — deliberately simple, parameter-explicit and
calibratable. Every parameter carries a `source` so that assumptions are visible.

Models
------
light   : LED electrical power -> PPFD on a tier (efficacy, tray area) -> DLI
heat    : steady-state sensible heat balance of the grow room -> cooling load & AC energy
co2     : first-order mass balance  dC/dt = -lambda (C - C_out) + S/V ; lambda fitted from data
crop    : lettuce growth as a function of DLI and temperature (thermal time + light use) — schematic
whatif  : combine the above for photoperiod / dimming / setpoint scenarios
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- parameters

@dataclass
class Params:
    # --- lighting
    led_bars_per_tier: int = 8            # counted from photos (IMG_2522/2533: ~8-9 bars) — COUNT ON SITE
    led_w_per_bar: float = 42.0           # design spec: 42 W per LED module
    led_tiers: int = 4                    # growing tiers 2-5 (nursery tier 1 has its own bars, treated separately)
    nursery_bars: int = 8                 # tier 1 (nursery 1 + 2)
    led_efficacy_umol_per_j: float = 2.3  # white+red 660 nm bar, typical 2.0-2.6 umol/J — MEASURE WITH THE PPFD METER
    canopy_fraction: float = 0.85         # share of photons landing on the tray (rest hits frame / aisle)
    photoperiod_h: float = 16.0           # from gc1.led duty (data) — default until confirmed
    dim_pct: float = 100.0                # currentStageBrightness (0-100)
    # --- room envelope
    wall_u: float = 0.6                   # W/m2K, 50 mm PS-foam sandwich panel (design)
    roof_u: float = 0.5                   # W/m2K, 2 in PU metal sheet
    floor_u: float = 0.3                  # W/m2K, concrete on ground
    window_u: float = 5.8                 # W/m2K, single glazing (2 panes facing the cafe)
    window_area_m2: float = 2.3 * 1.1
    cafe_t: float = 27.0                  # temperature on the cafe side of the windows — ASSUMED
    infiltration_ach: float = 0.3         # air changes per hour — fitted from CO2 decay in the notebook
    # --- other internal loads (W, electrical -> heat)
    fans_w: float = 15 * 15.0             # 15 DC fan sets x 15 W (design)
    pumps_w: float = 3 * 150.0 * 0.5      # 3 pumps x 150 W at ~50 % duty (design + data)
    dehumidifier_w: float = 420.0
    # --- HVAC
    ac_units: int = 2
    ac_input_w_each: float = 2000.0       # design spec (electrical)
    ac_cop: float = 3.0                   # cooling COP — ASSUMED (typical split-type)
    setpoint_t: float = 24.0              # observed room mean
    # --- economics
    thb_per_kwh: float = 4.5

    def to_frame(self):
        src = {"led_bars_per_tier": "photos (count on site)", "led_w_per_bar": "design spec p.4", "led_tiers": "site", "nursery_bars": "photos",
               "led_efficacy_umol_per_j": "ASSUMED - measure PPFD", "canopy_fraction": "ASSUMED", "photoperiod_h": "gc1.led duty (data)", "dim_pct": "gc1.currentStageBrightness",
               "wall_u": "material (design)", "roof_u": "material (design)", "floor_u": "ASSUMED", "window_u": "single glazing", "window_area_m2": "scan",
               "cafe_t": "ASSUMED", "infiltration_ach": "fitted from CO2 decay", "fans_w": "design spec", "pumps_w": "design spec + pwmWater duty",
               "dehumidifier_w": "design spec", "ac_units": "site", "ac_input_w_each": "design spec", "ac_cop": "ASSUMED", "setpoint_t": "data", "thb_per_kwh": "ASSUMED"}
        d = asdict(self)
        return pd.DataFrame({"value": d, "source": {k: src.get(k, "") for k in d}})


# --------------------------------------------------------------------------- light

def led_power_w(p: Params, tiers=None):
    n = (tiers if tiers is not None else p.led_tiers) * p.led_bars_per_tier
    return n * p.led_w_per_bar * p.dim_pct / 100.0


def ppfd_per_tier(p: Params, tray_area_m2: float):
    """Mean PPFD (umol m-2 s-1) on one growing tray from one tier's bars."""
    P_tier = p.led_bars_per_tier * p.led_w_per_bar * p.dim_pct / 100.0
    return P_tier * p.led_efficacy_umol_per_j * p.canopy_fraction / tray_area_m2


def dli(ppfd: float, photoperiod_h: float):
    """Daily light integral (mol m-2 d-1)."""
    return ppfd * photoperiod_h * 3600 / 1e6


# --------------------------------------------------------------------------- heat

def envelope_ua(p: Params, model: dict, anteroom_len=1.78):
    """U*A (W/K) per boundary of the grow room."""
    L, W, H = model["room"]["L"], model["room"]["W"], model["room"]["H"]
    return {
        "long wall (AC side, Y=W) -> outside": p.wall_u * L * H,
        "long wall (Y=0) minus windows -> outside/cafe": p.wall_u * (L * H - p.window_area_m2),
        "windows -> cafe": p.window_u * p.window_area_m2,
        "far wall (X=L) -> outside": p.wall_u * W * H,
        "partition (X=0) -> anteroom": p.wall_u * W * H,
        "roof -> outside": p.roof_u * L * W,
        "floor -> ground": p.floor_u * L * W,
    }


def heat_balance(p: Params, model: dict, t_out: float, t_ante: float, t_ground: float = 27.0, led_on: bool = True):
    """Steady-state sensible loads (W, positive = heat INTO the room) and the cooling needed to hold the setpoint."""
    L, W, H = model["room"]["L"], model["room"]["W"], model["room"]["H"]
    ua = envelope_ua(p, model)
    dT = {"long wall (AC side, Y=W) -> outside": t_out, "long wall (Y=0) minus windows -> outside/cafe": p.cafe_t, "windows -> cafe": p.cafe_t,
          "far wall (X=L) -> outside": t_out, "partition (X=0) -> anteroom": t_ante, "roof -> outside": t_out, "floor -> ground": t_ground}
    q = {k: ua[k] * (dT[k] - p.setpoint_t) for k in ua}
    vol = L * W * H
    q["infiltration"] = 1.2 * 1005 * vol * p.infiltration_ach / 3600 * (t_out - p.setpoint_t)
    q["LED (growing tiers)"] = led_power_w(p) if led_on else 0.0
    q["LED (nursery tier)"] = p.nursery_bars * p.led_w_per_bar * p.dim_pct / 100 if led_on else 0.0
    q["fans"] = p.fans_w; q["pumps"] = p.pumps_w; q["dehumidifier"] = p.dehumidifier_w
    q["cooling required"] = sum(q.values())            # net heat gain that the AC must remove (W)
    q["AC electrical (at COP)"] = max(q["cooling required"], 0) / p.ac_cop
    q["AC capacity (electrical, design)"] = p.ac_units * p.ac_input_w_each
    return q


def daily_energy(p: Params, model: dict, t_out_day: float, t_out_night: float, t_ante_day: float, t_ante_night: float):
    """kWh/day by consumer for a day with `photoperiod_h` lit hours."""
    on = heat_balance(p, model, t_out_day, t_ante_day, led_on=True)
    off = heat_balance(p, model, t_out_night, t_ante_night, led_on=False)
    h_on, h_off = p.photoperiod_h, 24 - p.photoperiod_h
    e = {
        "LED": (on["LED (growing tiers)"] + on["LED (nursery tier)"]) * h_on / 1000,
        "AC": (on["AC electrical (at COP)"] * h_on + off["AC electrical (at COP)"] * h_off) / 1000,
        "fans + pumps + dehumidifier": (p.fans_w + p.pumps_w + p.dehumidifier_w) * 24 / 1000,
    }
    e["total"] = sum(e.values()); e["THB/day"] = e["total"] * p.thb_per_kwh
    e["cooling load lit (kW)"] = on["cooling required"] / 1000; e["cooling load dark (kW)"] = off["cooling required"] / 1000
    return e


# --------------------------------------------------------------------------- CO2

def fit_co2_decay(co2: pd.Series, relay: pd.Series | None, led: pd.Series | None, c_out: float = 420.0,
                  min_len: int = 6, max_len: int = 36):
    """Fit lambda (h-1) of  C(t) - C_out = (C0 - C_out) exp(-lambda t)  on segments where CO2 is
    NOT injected and lights are OFF (no photosynthesis) -> lambda ~ air-exchange rate."""
    s = co2.dropna()
    ok = pd.Series(True, index=s.index)
    if relay is not None:
        ok &= (relay.reindex(s.index).fillna(0) < 0.5)
    if led is not None:
        ok &= (led.reindex(s.index).fillna(1) < 0.5)
    ok &= s.diff() < 0                         # falling
    grp = (ok != ok.shift()).cumsum()
    fits = []
    for _, g in s[ok].groupby(grp[ok]):
        if min_len <= len(g) <= max_len and (g.iloc[0] - c_out) > 150:
            t = (g.index - g.index[0]).total_seconds() / 3600
            y = np.log(np.clip(g.values - c_out, 1, None))
            k = np.polyfit(t, y, 1)[0]
            fits.append(dict(start=g.index[0], n=len(g), c0=float(g.iloc[0]), lam_per_h=float(-k)))
    return pd.DataFrame(fits)


def co2_balance(p: Params, model: dict, lam_per_h: float, c_target: float = 900.0, c_out: float = 420.0,
                uptake_umol_m2_s: float = 6.0, canopy_m2: float = 22.0):
    """Steady-state CO2 supply (g/h) to hold c_target: leakage + canopy uptake."""
    L, W, H = model["room"]["L"], model["room"]["W"], model["room"]["H"]
    vol = L * W * H
    rho_co2 = 1.8e-3                           # g per ppm per m3 (44 g/mol / 24.4 L/mol * 1e-6)
    leak_g_h = lam_per_h * vol * (c_target - c_out) * rho_co2
    uptake_g_h = uptake_umol_m2_s * canopy_m2 * 3600 * 44e-6
    total = leak_g_h + uptake_g_h
    return dict(volume_m3=round(vol, 1), leakage_g_h=round(leak_g_h, 1), canopy_uptake_g_h=round(uptake_g_h, 1), total_g_h=round(total, 1),
                kg_per_day_lit_hours=round(total * p.photoperiod_h / 1000, 2), cylinder_6kg_days=round(6000 / max(total * p.photoperiod_h, 1e-9), 1))


# --------------------------------------------------------------------------- crop (schematic)

def lettuce_days_to_harvest(dli_mol: float, t_mean: float, target_fw_g: float = 150.0):
    """Very simple lettuce model: relative growth rate rises with DLI up to ~17 mol/m2/d and is
    optimal at 20-24 C. Returns days from transplant (~5 g) to `target_fw_g`.  SCHEMATIC — calibrate."""
    rgr_max = 0.20                              # d-1 at optimum
    f_light = min(dli_mol / 17.0, 1.0) ** 0.7
    f_temp = max(0.0, 1 - ((t_mean - 22.0) / 8.0) ** 2)
    rgr = rgr_max * f_light * f_temp
    if rgr <= 0:
        return np.inf
    return float(np.log(target_fw_g / 5.0) / rgr)


def whatif_table(p: Params, model: dict, tray_area_m2: float, t_out_day, t_out_night, t_ante_day, t_ante_night, t_room=24.0,
                 photoperiods=(12, 14, 16, 18), dims=(60, 80, 100)):
    rows = []
    for ph in photoperiods:
        for dm in dims:
            q = Params(**{**asdict(p), "photoperiod_h": ph, "dim_pct": dm})
            ppfd = ppfd_per_tier(q, tray_area_m2); d = dli(ppfd, ph)
            e = daily_energy(q, model, t_out_day, t_out_night, t_ante_day, t_ante_night)
            rows.append(dict(photoperiod_h=ph, dim_pct=dm, PPFD=round(ppfd), DLI=round(d, 1), kWh_LED=round(e["LED"], 1), kWh_AC=round(e["AC"], 1),
                             kWh_total=round(e["total"], 1), THB_day=round(e["THB/day"]), cooling_lit_kW=round(e["cooling load lit (kW)"], 2),
                             days_to_150g=round(lettuce_days_to_harvest(d, t_room), 1)))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- crop mix what-if (tiers 2-5, 700 holes)

# Crop catalogue — agronomic defaults for NFT/DFT lettuce-type crops in a PFAL. ALL VALUES ASSUMED
# (typical literature / grower numbers) — replace with the farm's own harvest records.
CROPS = {
    "green oak":   dict(color="#7fbf3f", days=35, fw_g=150, dli=13, price_thb_kg=120, group="lettuce"),
    "red oak":     dict(color="#b03a2e", days=38, fw_g=140, dli=14, price_thb_kg=140, group="lettuce"),
    "butterhead":  dict(color="#a8d08d", days=40, fw_g=180, dli=13, price_thb_kg=130, group="lettuce"),
    "cos/romaine": dict(color="#2e7d32", days=45, fw_g=220, dli=15, price_thb_kg=110, group="lettuce"),
    "frillice":    dict(color="#c5e384", days=42, fw_g=160, dli=15, price_thb_kg=150, group="lettuce"),
    "kale":        dict(color="#1b4d3e", days=50, fw_g=200, dli=16, price_thb_kg=180, group="brassica"),
    "rocket":      dict(color="#6b8e23", days=28, fw_g=60,  dli=12, price_thb_kg=250, group="brassica"),
    "basil":       dict(color="#3cb371", days=40, fw_g=80,  dli=16, price_thb_kg=200, group="herb"),
    "coriander":   dict(color="#8fd18f", days=32, fw_g=40,  dli=12, price_thb_kg=180, group="herb"),
    "empty":       dict(color="#eeeeee", days=0,  fw_g=0,   dli=0,  price_thb_kg=0,   group="-"),
}

@dataclass
class HoleLayout:
    tiers: tuple = (2, 3, 4, 5)
    holes_total: int = 700              # site note 2026-09-14: 700 planting holes on tiers 2-5
    rows: int = 7                       # holes across the tray width (1.04 m) — ASSUMED, count on site
    def __post_init__(self):
        self.per_tier = self.holes_total // len(self.tiers)
        self.cols = int(round(self.per_tier / self.rows))


def hole_positions(model: dict, hl: HoleLayout) -> pd.DataFrame:
    """Room-frame (x, y, z) of every hole: tiers x cols x rows, evenly spaced over the tray."""
    K = model["rack"]; tz = {t["index"]: t["z"] for t in K["tiers"]}
    xs = np.linspace(K["x0"] + 0.12, K["x1"] - 0.12, hl.cols)
    ys = np.linspace(K["y0"] + 0.08, K["y1"] - 0.08, hl.rows)
    rows = []
    for t in hl.tiers:
        for ci, x in enumerate(xs):
            for ri, y in enumerate(ys):
                rows.append(dict(tier=t, col=ci, row=ri, x=float(x), y=float(y), z=tz[t] + 0.04))
    return pd.DataFrame(rows)


def allocate_holes(mix: dict, holes: pd.DataFrame, policy: str = "blocks") -> pd.DataFrame:
    """Assign crops to holes. `mix` = {crop: percent}; percentages are normalised to 100.
    policy 'blocks'  : fill holes tier by tier, column by column (contiguous blocks — easy to manage)
           'per_tier': every tier gets the same mix (columns split proportionally within each tier)"""
    total = sum(max(v, 0) for v in mix.values())
    shares = {k: max(v, 0) / total for k, v in mix.items() if v > 0} if total > 0 else {"empty": 1.0}
    h = holes.sort_values(["tier", "col", "row"]).reset_index(drop=True).copy()
    n = len(h); labels = np.array(["empty"] * n, dtype=object)
    if policy == "blocks":
        counts = {k: int(round(s * n)) for k, s in shares.items()}
        diff = n - sum(counts.values()); counts[max(counts, key=counts.get)] += diff
        i = 0
        for k, c in counts.items():
            labels[i:i + c] = k; i += c
    else:
        for t, g in h.groupby("tier"):
            idx = g.sort_values(["col", "row"]).index.values; m = len(idx)
            counts = {k: int(round(s * m)) for k, s in shares.items()}
            diff = m - sum(counts.values()); counts[max(counts, key=counts.get)] += diff
            i = 0
            for k, c in counts.items():
                labels[idx[i:i + c]] = k; i += c
    h["crop"] = labels
    return h


def crop_summary(assign: pd.DataFrame, dli_available: float, crops: dict = CROPS) -> pd.DataFrame:
    rows = []
    for k, g in assign.groupby("crop"):
        c = crops[k]; n = len(g)
        if k == "empty":
            rows.append(dict(crop=k, holes=n, share_pct=round(100 * n / len(assign), 1)))
            continue
        cycles = 365 / c["days"]
        kg_cycle = n * c["fw_g"] / 1000
        rows.append(dict(crop=k, holes=n, share_pct=round(100 * n / len(assign), 1), days_to_harvest=c["days"], plant_fw_g=c["fw_g"],
                         kg_per_cycle=round(kg_cycle, 1), cycles_per_year=round(cycles, 1), kg_per_year=round(kg_cycle * cycles),
                         THB_per_year=round(kg_cycle * cycles * c["price_thb_kg"]), DLI_need=c["dli"], DLI_available=round(dli_available, 1),
                         light_ok="yes" if dli_available >= c["dli"] else f"short by {c['dli'] - dli_available:.1f}"))
    df = pd.DataFrame(rows).set_index("crop")
    tot = dict(holes=int(df.holes.sum()), share_pct=100.0, kg_per_year=float(df.get("kg_per_year", pd.Series(dtype=float)).fillna(0).sum()),
               THB_per_year=float(df.get("THB_per_year", pd.Series(dtype=float)).fillna(0).sum()))
    df.loc["TOTAL", list(tot)] = list(tot.values())
    return df
