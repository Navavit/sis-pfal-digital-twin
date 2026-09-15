"""The PFAL digital twin as one object.

    from pfal_twin.twin import DigitalTwin
    twin = DigitalTwin.load()                 # geometry + zones + layout + pipework + IoT data + L3 parameters
    twin.state("2026-09-11 12:00")            # every variable at one moment
    twin.figure_3d("2026-09-11 12:00")        # plotly 3-D view (rack, sensors, pipes, pump state)
    twin.snapshot("2026-09-11 12:00", path)   # 2-D PNG for a paper
    twin.kpi(); twin.events()                 # tables
    twin.layout_figure(); twin.water_plan(); twin.flow_diagram(); twin.flow_animation()
    twin.heat_balance(); twin.whatif_light(); twin.crop_mix({"green oak": 60, "basil": 40})
    twin.update_data()                        # pull new telemetry from ThingsBoard
    twin.live()                               # latest values straight from ThingsBoard -> (TwinState, table)
    twin.figure_3d_live()                     # 3-D view of the live state
    twin.history("2026-09-01", "2026-09-07", ["gw.xy_md_21_t", "gc1.ec"], freq="1h")
Web dashboard: `streamlit run app/streamlit_app.py` (live view, history browser, layout, what-if).

Layers (all files produced by notebooks 01-04):
    data/model/room_model.json, zones.json, pipe_network.json, design_spec.json
    data/sensors/sensor_map.csv, equipment_map.csv
    data/processed/iot_10min.parquet (+ raw long parquet in data/raw/iot)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import io, geometry as G, viz, layout, thingsboard as tb, hydraulics as H, schematic as S, models as M, cropviz as CV
from . import FIG_DIR, PROCESSED

EXTRA_KEYS = ["gc1.ecSetPoint", "gc1.pHSetPoint", "gc2.ecSetPoint", "gc2.pHSetPoint", "gc1.task", "gc2.task", "gc1.stage", "gc2.stage",
              "gc1.modePumpWater", "gc2.modePumpWater", "gc1.ecDosingCount", "gc2.ecDosingCount", "gc1.pHDosingCount", "gc2.pHDosingCount",
              "gc1.ambTemperature", "gc2.ambTemperature", "gc1.upTime", "gc2.upTime",
              "co2.VOC", "co2.humidity", "co2.pressure", "co2.Relay_co2", "gw.waterLevel_1"]
LIMITS = dict(T_max=30.0, RH_max=85.0, VPD_lo=0.4, VPD_hi=1.6, EC_tol=0.3, pH_lo=5.5, pH_hi=6.5)


@dataclass
class TwinState:
    time: pd.Timestamp
    ch_T: dict; ch_RH: dict; ch_VPD: dict
    room_T: float; room_RH: float; room_VPD: float
    co2: float; co2_T: float; co2_VPD: float
    ec: dict; ph: dict; led: float; brightness: list; plant_day: dict; pump_on: dict
    extra: dict = field(default_factory=dict)      # setpoints, VOC, relay, modes ... (raw "alias.key" -> value)

    def as_dict(self):
        return self.__dict__


class DigitalTwin:
    # ------------------------------------------------------------------ construction
    def __init__(self, model, zones, sensors, equipment, network, data=None, params=None, design=None):
        self.model, self.zones, self.sensors, self.equipment, self.network = model, zones, sensors, equipment, network
        self.data = data
        self.params = params or M.Params()
        self.design = design
        self.limits = dict(LIMITS)
        self.rack_area = model["rack"]["length"] * model["rack"]["width"]
        self._rack_box = G.make_zones(model, n_segments=1, seg_names=("all",), canopy_height=0.35)
        self._prepare_data()

    @classmethod
    def load(cls, with_data: bool = True):
        model = io.load_model(); zones = io.load_model("zones.json")["zones"]
        sensors, equipment = layout.load_layout()
        try:
            network = H.load_network()
        except FileNotFoundError:
            network = H.build_network(model, zones)
        try:
            design = io.load_model("design_spec.json")
        except FileNotFoundError:
            design = None
        data = pd.read_parquet(tb.WIDE_PARQUET) if (with_data and tb.WIDE_PARQUET.exists()) else None
        return cls(model, zones, sensors, equipment, network, data, None, design)

    def _prepare_data(self):
        w = self.data
        if w is None:
            self.T = self.RH = self.VPD = self.room_mean = None; return
        self.T = tb.channel_frame(w, "t"); self.RH = tb.channel_frame(w, "h"); self.VPD = tb.vpd_kpa(self.T, self.RH)
        self.room_channels = [c for c in tb.ROOM_CHANNELS if c in self.T.columns]
        self.room_mean = self.T[self.room_channels].mean(axis=1)
        self.has_room = self.T[self.room_channels].notna().any(axis=1)
        # data-driven L3 defaults
        if "gc1.led" in w:
            self.params.photoperiod_h = float(w["gc1.led"].resample("1D").mean().mean() * 24)
        self.params.setpoint_t = float(self.room_mean.mean())
        self._unit_xyz = self.sensors.dropna(subset=["key_prefix"]).set_index("key_prefix")
        self._unit_xyz = self._unit_xyz.loc[[c for c in tb.CHANNEL_ORDER if c in self._unit_xyz.index], ["sensor", "x", "y", "z"]]

    # ------------------------------------------------------------------ data
    def update_data(self, backfill_from="2025-12-20", verbose=True):
        """Pull new telemetry from ThingsBoard (incremental), rebuild the 10-min table, reload."""
        client = tb.Client().login_public()
        long = tb.update_store(client, backfill_from=backfill_from, verbose=verbose)
        w, qc = tb.clean_wide(tb.to_wide(long, "10min"))
        env, ctrl = tb.split_env_control(w); w = pd.concat([env, tb.state_ffill(ctrl)], axis=1)
        w.to_parquet(tb.WIDE_PARQUET); qc.to_csv(PROCESSED / "iot_qc_report.csv")
        self.data = w; self._prepare_data()
        return w

    @property
    def equipment_inside(self):
        return self.equipment[self.equipment.location == "inside"] if "location" in self.equipment else self.equipment

    def summary(self):
        R, K = self.model["room"], self.model["rack"]
        lines = [f"room {R['L']} x {R['W']} x {R['H']} m | rack {K['length']} x {K['width']} m, {len(K['tiers'])} tiers | zones {len(self.zones)}",
                 f"equipment {len(self.equipment)} items ({int(self.equipment.verified.sum())} verified) | sensors {len(self.sensors)} | pipe edges {len(self.network['edges'])}"]
        if self.data is not None:
            lines.append(f"IoT {self.data.index.min():%Y-%m-%d} -> {self.data.index.max():%Y-%m-%d %H:%M}, {len(self.data):,} x 10-min bins, room T/RH in {int(self.has_room.sum()):,} bins")
        return "\n".join(lines)

    # ------------------------------------------------------------------ state at a time
    def state(self, t, tol="30min", lookback_bins=12) -> TwinState:
        """Every variable at the 10-min bin nearest to t (NaN if the nearest bin is more than `tol` away).
        Devices publish each key only when it changes (the CO₂ controller's T/RH/VOC can be 30-60 min apart), so each
        variable takes its last value within the previous `lookback_bins` bins (2 h) instead of "—" whenever the exact bin is empty."""
        w = self.data
        t = pd.Timestamp(t); t = t.tz_localize(tb.TZ) if t.tzinfo is None else t
        i = w.index.get_indexer([t], method="nearest")[0]
        row = w.iloc[max(0, i - lookback_bins):i + 1].ffill().iloc[-1]
        if abs(w.index[i] - t) > pd.Timedelta(tol):
            row = row * np.nan
        return self._state_from_row(row, w.index[i])

    def _state_from_row(self, row: pd.Series, t) -> TwinState:
        g = lambda k: float(row.get(k, np.nan))
        ch_T = {c: g(f"gw.{c}_t") for c in tb.CHANNEL_ORDER}; ch_RH = {c: g(f"gw.{c}_h") for c in tb.CHANNEL_ORDER}
        ch_VPD = {c: float(tb.vpd_kpa(ch_T[c], ch_RH[c])) for c in tb.CHANNEL_ORDER}
        rt = [ch_T[c] for c in self.room_channels if ch_T[c] == ch_T[c]]; rh = [ch_RH[c] for c in self.room_channels if ch_RH[c] == ch_RH[c]]
        room_T = float(np.mean(rt)) if rt else np.nan; room_RH = float(np.mean(rh)) if rh else np.nan
        return TwinState(time=pd.Timestamp(t), ch_T=ch_T, ch_RH=ch_RH, ch_VPD=ch_VPD, room_T=room_T, room_RH=room_RH, room_VPD=float(tb.vpd_kpa(room_T, room_RH)),
                         co2=g("co2.CO2"), co2_T=g("co2.temperature"), co2_VPD=g("co2.VPD"),
                         ec={"growing (gc1)": g("gc1.ec"), "nursery-2 (gc2)": g("gc2.ec")}, ph={"growing (gc1)": g("gc1.ph"), "nursery-2 (gc2)": g("gc2.ph")},
                         led=g("gc1.led"), brightness=[g(f"gc1.currentStageBrightness{i}") for i in range(1, 5)],
                         plant_day={"growing (gc1)": g("gc1.plantDay"), "nursery-2 (gc2)": g("gc2.plantDay")},
                         pump_on={"gc1": g("gc1.pwmWater") >= 0.5, "gc2": g("gc2.pwmWater") >= 0.5},
                         extra={k: g(k) for k in EXTRA_KEYS})

    # ------------------------------------------------------------------ live (ThingsBoard "latest values")
    def live(self, max_age="24h"):
        """Latest value of every key straight from ThingsBoard -> (TwinState, table of key/value/timestamp/age).
        Values older than `max_age` are kept in the table but dropped from the state (NaN)."""
        client = tb.Client().login_public(); rows = []
        for alias, dev in tb.DEVICES.items():
            try:
                df = client.latest(dev["id"], tb.KEYS[alias])
            except Exception as e:  # one device offline must not kill the view
                print(f"live: {alias} -> {e}"); continue
            df["device"] = alias; rows.append(df)
        long = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ts", "key", "value", "device"])
        now = pd.Timestamp.now(tz=tb.TZ); long["age"] = now - long["ts"]
        long["column"] = long["device"] + "." + long["key"]
        fresh = long[(long["age"] <= pd.Timedelta(max_age)) | long["key"].isin(tb.CONTROL_KEYS)]   # state keys are published on change only
        row = pd.Series(fresh["value"].values, index=fresh["column"].values, dtype=float)
        st = self._state_from_row(row, long["ts"].max() if len(long) else now)
        table = long.set_index("column")[["value", "ts", "age", "device", "key"]].sort_values("ts", ascending=False)
        return st, table

    def top_up(self, overlap="1h", verbose=False) -> pd.Timestamp:
        """Fill the gap between the stored table and now straight from ThingsBoard (in memory only, no files written).
        Cheap: only samples newer than data.index.max() - overlap. Returns the new end of the table."""
        client = tb.Client().login_public()
        start = self.data.index.max() - pd.Timedelta(overlap)
        long = tb.fetch_history(client, start, verbose=verbose)
        if long.empty:
            return self.data.index.max()
        w, _ = tb.clean_wide(tb.to_wide(long, "10min"))
        env, ctrl = tb.split_env_control(w); w = pd.concat([env, tb.state_ffill(ctrl)], axis=1)
        merged = w.combine_first(self.data) if len(w) else self.data
        merged = merged.reindex(pd.date_range(merged.index.min(), merged.index.max(), freq="10min", tz=tb.TZ))
        ctrl_cols = [c for c in merged.columns if c.split(".", 1)[1] in tb.CONTROL_KEYS]
        merged[ctrl_cols] = merged[ctrl_cols].ffill(limit=6 * 24 * 7)
        self.data = merged; self._prepare_data()
        return self.data.index.max()

    def recent(self, hours=24, interval_min=5, keys=None):
        """Straight from ThingsBoard like the dashboard's real-time window: last `hours` hours, `interval_min`-minute averages
        for measurements and raw on/off events for the dosing pumps -> wide frame ("alias.key" columns)."""
        client = tb.Client().login_public()
        end = pd.Timestamp.now(tz=tb.TZ); start = end - pd.Timedelta(hours=hours)
        keys = keys or tb.DASHBOARD_COLUMNS + ["gc1.led", "gc1.pwmWater", "gc2.pwmWater", "co2.Relay_co2", "co2.temperature", "co2.humidity"]
        by_dev = {}
        for col in keys:
            a, k = col.split(".", 1); by_dev.setdefault(a, []).append(k)
        frames = []
        for a, ks in by_dev.items():
            avg = [k for k in ks if k not in tb.CONTROL_KEYS]; raw = [k for k in ks if k in tb.CONTROL_KEYS]
            try:
                if avg:
                    df = client.timeseries(tb.DEVICES[a]["id"], avg, start, end, interval_ms=interval_min * 60000, agg="AVG"); df["device"] = a; frames.append(df)
                if raw:
                    df = client.timeseries(tb.DEVICES[a]["id"], raw, start, end); df["device"] = a; frames.append(df)
            except Exception as e:
                print(f"recent: {a} -> {e}")
        if not frames:
            return pd.DataFrame()
        long = pd.concat(frames, ignore_index=True); long["col"] = long["device"] + "." + long["key"]
        return long.pivot_table(index="ts", columns="col", values="value", aggfunc="last").sort_index()

    def history(self, start=None, end=None, columns=None, freq=None):
        """Slice of the local 10-min table (columns like "gw.xy_md_21_t", "gc1.ec"); freq="1h" etc. resamples by mean.
        Call update_data() first if you need data newer than data.index.max()."""
        w = self.data
        loc = lambda t: None if t is None else (pd.Timestamp(t).tz_localize(tb.TZ) if pd.Timestamp(t).tzinfo is None else pd.Timestamp(t))
        w = w.loc[loc(start):loc(end)]
        if columns is not None:
            w = w[[c for c in columns if c in w.columns]]
        return w.resample(freq).mean() if freq else w

    def data_span(self):
        return (self.data.index.min(), self.data.index.max()) if self.data is not None else (None, None)

    def warmest_moment(self, require_full=True):
        ok = self.room_mean.notna()
        if require_full:
            ok &= self.data["gc1.ec"].notna() & self.data["co2.CO2"].notna()
        return self.room_mean[ok].idxmax()

    # ------------------------------------------------------------------ tables
    def kpi(self):
        T, RH, VPD, L = self.T, self.RH, self.VPD, self.limits
        k = pd.DataFrame({"location": [tb.CHANNELS[c]["short"] for c in T.columns], "zone": [tb.CHANNELS[c]["zone"] for c in T.columns],
                          "T mean °C": T.mean().values, "T max °C": T.max().values, f"hours T > {L['T_max']:.0f} °C": ((T > L["T_max"]).sum() / 6).values,
                          "RH mean %": RH.mean().values, f"hours RH > {L['RH_max']:.0f} %": ((RH > L["RH_max"]).sum() / 6).values,
                          "VPD mean kPa": VPD.mean().values, "hours VPD out of range": (((VPD < L["VPD_lo"]) | (VPD > L["VPD_hi"])).sum() / 6).values,
                          "data hours": (T.count() / 6).values}, index=T.columns).round(2)
        k.index.name = "channel"; return k

    @staticmethod
    def _runs(series, cond, label, min_len=3):
        m = cond.fillna(False).astype(int); grp = (m.diff() != 0).cumsum(); out = []
        for _, g in series[m == 1].groupby(grp[m == 1]):
            if len(g) >= min_len:
                out.append(dict(event=label, start=g.index[0], end=g.index[-1], hours=round(len(g) / 6, 1), peak=round(float(g.max()), 2)))
        return out

    def events(self, save=True):
        w, L, ev = self.data, self.limits, []
        for c in self.room_channels:
            ev += self._runs(self.T[c], self.T[c] > L["T_max"], f"{c} (room) T > {L['T_max']:.0f} °C")
            ev += self._runs(self.RH[c], self.RH[c] > L["RH_max"], f"{c} (room) RH > {L['RH_max']:.0f} %")
        for a, nm in (("gc1", "growing 200 L"), ("gc2", "nursery-2 100 L")):
            if f"{a}.ec" in w and f"{a}.ecSetPoint" in w:
                dev = (w[f"{a}.ec"] - w[f"{a}.ecSetPoint"]).abs(); ev += self._runs(dev, dev > L["EC_tol"], f"{nm} |EC − setpoint| > {L['EC_tol']}")
            if f"{a}.ph" in w:
                ev += self._runs(w[f"{a}.ph"], (w[f"{a}.ph"] < L["pH_lo"]) | (w[f"{a}.ph"] > L["pH_hi"]), f"{nm} pH outside {L['pH_lo']}–{L['pH_hi']}")
        df = pd.DataFrame(ev).sort_values("start", ascending=False).reset_index(drop=True) if ev else pd.DataFrame(columns=["event", "start", "end", "hours", "peak"])
        if save:
            df.to_csv(PROCESSED / "iot_events.csv", index=False)
        return df

    # ------------------------------------------------------------------ figures: geometry & systems
    def layout_figure(self, path=None, figsize=(27, 17)):
        import matplotlib.pyplot as plt
        try:
            pc = io.load_clean(); P, RGB = pc["xyz"], pc["rgb"]
        except FileNotFoundError:  # deployed without the point-cloud cache: draw the elevation from the model only
            P = RGB = None
        fig = plt.figure(figsize=figsize)
        gs = fig.add_gridspec(2, 2, width_ratios=[3.3, 1], height_ratios=[1.25, 1], wspace=0.01, hspace=0.12)
        ax_plan, ax_key, ax_elev = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[:, 1]), fig.add_subplot(gs[1, 0])
        viz.plan_layout(self.model, self.zones, self.equipment, self.sensors, ax=ax_plan, key_ax=ax_key, net=self.network)
        eq2 = self.equipment[self.equipment.location != "outside_far"]; s2 = self.sensors[self.sensors.location != "outside_far"]
        viz.elevation_layout(self.model, P, RGB, eq2, s2, ax=ax_elev, net=self.network)
        if path:
            fig.savefig(path, dpi=170, bbox_inches="tight")
        return fig

    def water_plan(self, path=None):
        fig = S.water_system_plan(self.model, self.network, self.equipment, self.sensors)
        if path: fig.savefig(path, dpi=150, bbox_inches="tight")
        return fig

    def flow_diagram(self, path=None):
        fig = S.water_flow_diagram()
        if path: fig.savefig(path, dpi=150, bbox_inches="tight")
        return fig

    def flow_animation(self, n_frames=24, title="Nutrient-solution flow — schematic (no flow sensor)"):
        base = viz.model_traces(self.model, tier_color="#dddddd") + viz.equipment_traces(self.equipment_inside, opacity=0.15)
        return H.flow_figure(self.network, base, n_frames=n_frames, spacing=0.25, title=title)

    def corner_detail(self, path=None):
        fig = viz.pipe_corner_detail(self.model, self.network, self.equipment_inside)
        if path: fig.savefig(path, dpi=150, bbox_inches="tight")
        return fig

    # ------------------------------------------------------------------ figures: data twin
    def _unit_trace(self, st: TwinState, var, cmin, cmax):
        import plotly.graph_objects as go
        vals = {"T": st.ch_T, "RH": st.ch_RH, "VPD": st.ch_VPD}[var]; unit = {"T": " °C", "RH": " %", "VPD": " kPa"}[var]
        xs, ys, zs, cs, txt = [], [], [], [], []
        for c, r in self._unit_xyz.iterrows():
            v = vals.get(c, np.nan); xs.append(r.x); ys.append(r.y); zs.append(r.z); cs.append(v if v == v else cmin)
            txt.append(f"{r.sensor}<br>{tb.channel_label(c)}<br>T {st.ch_T[c]:.1f} °C · RH {st.ch_RH[c]:.0f} % · VPD {st.ch_VPD[c]:.2f} kPa")
        return go.Scatter3d(x=xs, y=ys, z=zs, mode="markers+text", text=[c.replace("xy_md_", "ch ") for c in self._unit_xyz.index], textposition="top center",
                            hovertext=txt, hoverinfo="text", name=f"XY-MD02 units ({var})",
                            marker=dict(size=9, color=cs, colorscale="RdYlBu_r", cmin=cmin, cmax=cmax, symbol="diamond", line=dict(color="black", width=1),
                                        colorbar=dict(title=var + unit, x=1.02, xanchor="left", y=0.0, yanchor="bottom", len=0.42, thickness=14)))

    # ------------------------------------------------------------------ hover text (sensor values on the 3-D objects)
    @staticmethod
    def _f(v, nd=1, unit=""):
        return "—" if v is None or v != v else f"{v:.{nd}f}{unit}"

    @classmethod
    def _sp(cls, v, nd=2):
        """set-point, bold red so it stands out next to the measured value"""
        return f"<span style='color:#c0392b'><b>set {cls._f(v, nd)}</b></span>"

    def _hover_controller(self, st: TwinState, alias: str) -> str:
        f, x = self._f, st.extra
        if alias == "co2":
            rel = x.get("co2.Relay_co2"); rel = "—" if rel != rel else ("ON" if rel >= 0.5 else "off")
            return (f"<b>CO₂ & environment controller</b><br>CO₂ {f(st.co2, 0, ' ppm')} · valve {rel}<br>"
                    f"T {f(st.co2_T)} °C · RH {f(x.get('co2.humidity'), 0)} % · VPD {f(st.co2_VPD, 2)} kPa<br>VOC {f(x.get('co2.VOC'), 0)} · p {f(x.get('co2.pressure'))} kPa")
        if alias in ("gc1", "gc2"):
            loop = "growing (gc1)" if alias == "gc1" else "nursery-2 (gc2)"
            name = "Grow controller gc1 — growing stage, 200 L" if alias == "gc1" else "Grow controller gc2 — nursery 2, 100 L"
            mode = tb.PUMP_MODE.get(x.get(f"{alias}.modePumpWater"), "—")
            led = "" if alias != "gc1" else f"<br>LED {'—' if st.led != st.led else ('ON' if st.led >= 0.5 else 'off')} · brightness {'/'.join(f(b, 0) for b in st.brightness)} %"
            up = x.get(f"{alias}.upTime"); up = f(up / 3.6e9 if up == up else up, 1, " h")
            return (f"<b>{name}</b><br>EC {f(st.ec[loop], 2)} mS/cm ({self._sp(x.get(f'{alias}.ecSetPoint'))}) · pH {f(st.ph[loop], 2)} ({self._sp(x.get(f'{alias}.pHSetPoint'))})<br>"
                    f"circulation pump {'ON' if st.pump_on[alias] else 'off'} ({mode}) · plant day {f(st.plant_day[loop], 0)} · task {f(x.get(f'{alias}.task'), 0)}{led}<br>"
                    f"doses EC {f(x.get(f'{alias}.ecDosingCount'), 0)} / pH {f(x.get(f'{alias}.pHDosingCount'), 0)} · box T {f(x.get(f'{alias}.ambTemperature'))} °C · uptime {up}")
        if alias == "gw":
            return "<b>IoT gateway</b> (5 × XY-MD02 on RS-485)<br>" + "<br>".join(f"ch {c[-2:]}: {f(st.ch_T[c])} °C / {f(st.ch_RH[c], 0)} %" for c in tb.CHANNEL_ORDER)
        if alias == "waterLevel_1":
            return f"<b>water-level sensor</b> (200 L tank)<br>reading {f(x.get('gw.waterLevel_1'), 0)} — not connected"
        return alias

    def _hover_zone(self, st: TwinState, zone: str) -> str:
        f = self._f; tier = int(zone[1]) if zone[0] == "T" and zone[1].isdigit() else None
        head = f"<b>{zone}</b> — " + ("nursery tier 1" if tier == 1 else f"growing tier {tier}" if tier else "rack")
        air = f"room air (mean of 3 wall units): {f(st.room_T)} °C · RH {f(st.room_RH, 0)} % · VPD {f(st.room_VPD, 2)} kPa"
        x = st.extra
        if tier == 1:
            sol = (f"nursery-2 solution (gc2): EC {f(st.ec['nursery-2 (gc2)'], 2)} ({self._sp(x.get('gc2.ecSetPoint'))}) · "
                   f"pH {f(st.ph['nursery-2 (gc2)'], 2)} ({self._sp(x.get('gc2.pHSetPoint'))}) · pump {'ON' if st.pump_on['gc2'] else 'off'}")
        else:
            sol = (f"growing solution (gc1): EC {f(st.ec['growing (gc1)'], 2)} ({self._sp(x.get('gc1.ecSetPoint'))}) · "
                   f"pH {f(st.ph['growing (gc1)'], 2)} ({self._sp(x.get('gc1.pHSetPoint'))}) · pump {'ON' if st.pump_on['gc1'] else 'off'}<br>"
                   f"LED {'—' if st.led != st.led else ('ON' if st.led >= 0.5 else 'off')} · plant day {f(st.plant_day['growing (gc1)'], 0)}")
        return f"{head}<br>{air}<br>{sol}<br>CO₂ {f(st.co2, 0)} ppm"

    def _hover_equipment(self, st: TwinState, name: str) -> str | None:
        n = name.lower(); f = self._f
        if "grow controller gc1" in n or "grow controller gc2" in n:
            return self._hover_controller(st, "gc1" if "gc1" in n else "gc2")
        x = st.extra
        if "growing-stage tank" in n or ("tank" in n and "gc1" in n) or "dosing box b" in n:
            return (f"EC {f(st.ec['growing (gc1)'], 2)} mS/cm ({self._sp(x.get('gc1.ecSetPoint'))}) · pH {f(st.ph['growing (gc1)'], 2)} ({self._sp(x.get('gc1.pHSetPoint'))}) · "
                    f"pump {'ON' if st.pump_on['gc1'] else 'off'}")
        if "nursery-2 tank" in n or "dosing box a" in n:
            return (f"EC {f(st.ec['nursery-2 (gc2)'], 2)} mS/cm ({self._sp(x.get('gc2.ecSetPoint'))}) · pH {f(st.ph['nursery-2 (gc2)'], 2)} ({self._sp(x.get('gc2.pHSetPoint'))}) · "
                    f"pump {'ON' if st.pump_on['gc2'] else 'off'}")
        if "co2 & environment controller" in n:
            return self._hover_controller(st, "co2")
        if "ac indoor" in n or "dehumidifier" in n:
            return f"room air now: {f(st.room_T)} °C · RH {f(st.room_RH, 0)} %"
        return None

    def figure_3d(self, t=None, var="T", cmin=20, cmax=35, show_cloud=False, height=720, st: TwinState | None = None, title_prefix="",
                  pipes=False, compact=True, public=False):
        """Plotly 3-D twin at time t (or at a given TwinState, e.g. from live()): rack coloured by the room mean, XY-MD02 units by value.
        pipes=True also draws the pipework (solid = pump running); compact=True -> grouped legend under the scene;
        public=True -> title limited to what the public ThingsBoard dashboard shows (no LED / pump state)."""
        if st is None:
            st = self.state(t if t is not None else self.warmest_moment())
        unit = {"T": " °C", "RH": " %", "VPD": " kPa"}[var]
        room_val = {"T": st.room_T, "RH": st.room_RH, "VPD": st.room_VPD}[var]
        zv = {q["zone"]: room_val for q in self._rack_box}
        others = self.sensors[~self.sensors.key_prefix.isin(tb.CHANNELS.keys())]
        zones_tr = viz.zone_traces(self._rack_box, zv, cmin=cmin, cmax=cmax, unit=unit, opacity=0.55)
        for q, m in zip(self._rack_box, zones_tr):           # rack boxes: full sensor summary on hover
            m.update(hovertext=self._hover_zone(st, q["zone"]))
        tr = viz.model_traces(self.model, tier_color="#cccccc", group_legend=compact) + zones_tr
        eq_tr = viz.equipment_traces(self.equipment_inside, opacity=0.2, group_legend=compact)
        for r, m in zip(self.equipment_inside.itertuples(), eq_tr):   # tanks / controllers / AC: live values on hover
            extra = self._hover_equipment(st, r.name)
            if extra:
                m.update(hovertext=extra if extra.startswith("<b>") else f"<b>{r.name}</b><br>{extra}")
        tr += eq_tr
        tr += [viz.sensor_trace(others, text=[self._hover_controller(st, r.sensor) for r in others.itertuples()], name="other IoT boxes (hover)", size=5, labels=not compact),
               self._unit_trace(st, var, cmin, cmax)]
        on = [lp for lp, v in st.pump_on.items() if v]
        if pipes:
            tr += H.pipe_traces(self.network, loops=on + ["shared", "n1"]) + H.pipe_traces(self.network, loops=[lp for lp in ("gc1", "gc2") if lp not in on], opacity=0.2)
        if show_cloud:
            pc = io.load_clean(); tr = [viz.points_trace(pc["xyz"], pc["rgb"], n=40000, size=1, opacity=0.35)] + tr
        led_txt = "LED ?" if st.led != st.led else "LED on" if st.led >= 0.5 else "LED off"
        pump_txt = "pumps: " + ", ".join(f"{'growing' if lp == 'gc1' else 'nursery-2'} {'ON' if v else 'off'}" for lp, v in st.pump_on.items())
        line1 = f"{title_prefix}{st.time:%Y-%m-%d %H:%M} — room {var} = mean of 3 wall sensors ({cmin}–{cmax}{unit}); anteroom {st.ch_T['xy_md_20']:.1f} °C, outside {st.ch_T['xy_md_24']:.1f} °C"
        line2 = (f"CO₂ {st.co2:.0f} ppm | EC growing {st.ec['growing (gc1)']:.2f} / nursery-2 {st.ec['nursery-2 (gc2)']:.2f} | "
                 f"pH {st.ph['growing (gc1)']:.2f} / {st.ph['nursery-2 (gc2)']:.2f}" + ("" if public else f" | {led_txt} | {pump_txt}"))
        title = f"{line1}<br><span style='font-size:0.85em'>{line2}</span>" if compact else f"{line1} | {line2}"
        return viz.figure_3d(tr, title=title, height=height, compact=compact)

    def show(self, t=None, var="T", name=None, **kw):
        """Display figure_3d in a notebook with the full-screen button (and write figures/html/<name>.html)."""
        return viz.show3d(self.figure_3d(t, var, **kw), name)

    def figure_3d_live(self, var="T", **kw):
        st, _ = self.live()
        return self.figure_3d(var=var, st=st, title_prefix="LIVE ", **kw)

    def heatmap(self, path=None):
        import matplotlib.pyplot as plt
        Th = self.T[self.has_room].resample("1h").mean(); Hh = self.RH[self.has_room].resample("1h").mean()
        fig, axes = plt.subplots(2, 1, figsize=(17, 6.5), sharex=True)
        for ax, D, label, cmap, vmin, vmax in ((axes[0], Th, "air temperature (°C)", "RdYlBu_r", 20, 35), (axes[1], Hh, "relative humidity (%)", "YlGnBu", 40, 95)):
            A = np.ma.masked_invalid(D.T.values[::-1])
            im = ax.imshow(A, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
            ax.set_facecolor("#dddddd"); ax.set_yticks(range(len(D.columns))); ax.set_yticklabels([tb.channel_label(c) for c in D.columns[::-1]], fontsize=8)
            plt.colorbar(im, ax=ax, pad=0.01, label=label)
        step = max(1, len(Th) // 16); axes[1].set_xticks(range(0, len(Th), step)); axes[1].set_xticklabels([t.strftime("%d %b %H:%M") for t in Th.index[::step]], rotation=45, ha="right", fontsize=8)
        axes[0].set_title("XY-MD02 channels — temperature and humidity (hourly means; grey = no data)")
        fig.tight_layout()
        if path: fig.savefig(path, dpi=150)
        return fig

    def snapshot(self, t=None, path=None):
        """2-D elevation snapshot (for a paper): rack = room mean, wall sensors with values, side panel with everything else."""
        import matplotlib.pyplot as plt
        st = self.state(t if t is not None else self.warmest_moment()); R, K = self.model["room"], self.model["rack"]
        fig, (ax, ax2) = plt.subplots(1, 2, figsize=(16, 5.2), gridspec_kw=dict(width_ratios=[2.6, 1]))
        cmap = plt.cm.RdYlBu_r; norm = plt.Normalize(20, 35)
        ax.add_patch(plt.Rectangle((0, 0), R["L"], R["H"], fill=False, lw=2))
        rc = cmap(norm(st.room_T)) if st.room_T == st.room_T else "#cccccc"
        for tier in K["tiers"]:
            ax.add_patch(plt.Rectangle((K["x0"], tier["z"]), K["length"], 0.35, fc=rc, ec="k", lw=.6, alpha=0.55))
        ax.text(K["x0"] + K["length"] / 2, K["tiers"][-1]["z"] + 0.17,
                f"rack (all tiers) = room mean of 3 wall sensors: {st.room_T:.1f} °C, RH {st.room_RH:.0f} %, VPD {st.room_VPD:.2f} kPa" if st.room_T == st.room_T else "no room data",
                ha="center", va="center", fontsize=9, bbox=dict(fc="white", ec="none", alpha=0.8))
        for c, r in self._unit_xyz.iterrows():
            if r.x < 0: continue
            v = st.ch_T[c]; col = cmap(norm(v)) if v == v else "#cccccc"
            ax.scatter([r.x], [r.z], marker="D", s=90, c=[col], ec="black", zorder=6)
            ax.annotate(f"{r.sensor.split(' (')[0]} · {c.replace('xy_md_', 'ch ')}\n{v:.1f} °C / {st.ch_RH[c]:.0f} %" if v == v else f"{r.sensor.split(' (')[0]}: no data",
                        (r.x, r.z), xytext=(0, 12), textcoords="offset points", ha="center", fontsize=7.5, bbox=dict(fc="white", ec="none", alpha=0.8))
        for _, r in self.equipment_inside.iterrows():
            ax.add_patch(plt.Rectangle((r.x0, r.z0), r.x1 - r.x0, r.z1 - r.z0, fill=False, ec="#777", lw=.8, ls=":"))
        ax.set_xlim(-0.1, R["L"] + 0.1); ax.set_ylim(-0.05, R["H"] + 0.15); ax.set_aspect("equal")
        ax.set_xlabel("X — room length (m)"); ax.set_ylabel("Z (m)"); ax.set_title(f"Digital twin snapshot — {st.time:%Y-%m-%d %H:%M} (Asia/Bangkok)")
        plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, fraction=0.025, pad=0.01, label="air temperature (°C)")
        ax2.axis("off")
        onoff = lambda v: "?" if v != v else ("on" if v >= 0.5 else "off")
        lines = [f"Anteroom (ch 20):  {st.ch_T['xy_md_20']:.1f} °C / {st.ch_RH['xy_md_20']:.0f} %", f"Outside  (ch 24):  {st.ch_T['xy_md_24']:.1f} °C / {st.ch_RH['xy_md_24']:.0f} %", "",
                 f"CO₂: {st.co2:.0f} ppm", f"CO₂-controller T: {st.co2_T:.1f} °C, VPD {st.co2_VPD:.2f} kPa", "",
                 f"Growing stage (gc1, 200 L): EC {st.ec['growing (gc1)']:.2f} mS/cm, pH {st.ph['growing (gc1)']:.2f}",
                 f"Nursery 2 (gc2, 100 L):     EC {st.ec['nursery-2 (gc2)']:.2f} mS/cm, pH {st.ph['nursery-2 (gc2)']:.2f}", "",
                 f"LED (gc1): {onoff(st.led)}   brightness ch1–4: " + "/".join(f"{b:.0f}" for b in st.brightness) + " %",
                 f"plant day: growing {st.plant_day['growing (gc1)']:.0f}, nursery-2 {st.plant_day['nursery-2 (gc2)']:.0f}", "",
                 "circulation pump: " + ", ".join(f"{'growing' if lp == 'gc1' else 'nursery-2'} {'ON' if v else 'off'}" for lp, v in st.pump_on.items())]
        ax2.text(0, 0.95, "\n".join(lines), va="top", fontsize=10, family="monospace")
        fig.tight_layout()
        if path: fig.savefig(path, dpi=150)
        return fig

    # ------------------------------------------------------------------ L3
    def _design_day(self):
        led = self.data["gc1.led"]; day = led >= 0.5
        to, ta = self.T["xy_md_24"], self.T["xy_md_20"]
        return dict(t_out_day=float(to[day].mean()), t_out_night=float(to[~day].mean()), t_ante_day=float(ta[day].mean()), t_ante_night=float(ta[~day].mean()))

    def heat_balance(self, led_on=True):
        d = self._design_day()
        return M.heat_balance(self.params, self.model, d["t_out_day"] if led_on else d["t_out_night"], d["t_ante_day"] if led_on else d["t_ante_night"], led_on=led_on)

    def daily_energy(self):
        return M.daily_energy(self.params, self.model, **self._design_day())

    def light(self, dim_pct=None, photoperiod_h=None):
        q = M.Params(**{**M.asdict(self.params), **({"dim_pct": dim_pct} if dim_pct is not None else {}), **({"photoperiod_h": photoperiod_h} if photoperiod_h is not None else {})})
        ppfd = M.ppfd_per_tier(q, self.rack_area)
        return dict(ppfd=ppfd, dli=M.dli(ppfd, q.photoperiod_h), led_kw=M.led_power_w(q) / 1000)

    def fit_co2(self):
        fits = M.fit_co2_decay(self.data["co2.CO2"], self.data.get("co2.Relay_co2"), self.data["gc1.led"])
        if len(fits):
            self.params.infiltration_ach = float(fits.lam_per_h.median())
        return fits

    def co2_balance(self, c_target=900.0):
        return M.co2_balance(self.params, self.model, self.params.infiltration_ach, c_target=c_target)

    def whatif_light(self, photoperiods=(12, 14, 16, 18), dims=(60, 80, 100)):
        d = self._design_day()
        return M.whatif_table(self.params, self.model, self.rack_area, d["t_out_day"], d["t_out_night"], d["t_ante_day"], d["t_ante_night"],
                              t_room=self.params.setpoint_t, photoperiods=photoperiods, dims=dims)

    def crop_mix(self, mix: dict, policy="blocks", holes_total=700, rows=7, photoperiod_h=16.0, view="3d", path=None, name=None):
        """Assign crops to the 700 holes of tiers 2-5 -> (assignment, summary, figure).
        view="3d" (default): plotly 3-D rack with one marker per hole, shown in the notebook with the full-screen button
        view="2d": matplotlib hole-by-hole plan per tier (paper figure, saved to `path`); view=None: no figure."""
        hl = M.HoleLayout(holes_total=holes_total, rows=rows)
        holes = M.hole_positions(self.model, hl)
        assign = M.allocate_holes(mix, holes, policy=policy)
        summary = M.crop_summary(assign, self.light(photoperiod_h=photoperiod_h)["dli"])
        fig = None
        if view == "3d":
            fig = self.crop_mix_3d(assign, title=f"Crop mix on tiers 2-5 — {mix} (policy: {policy})")
            viz.show3d(fig, name)
        elif view == "2d":
            fig = CV.rack_plan_holes(assign, self.model, title=f"Crop mix {mix} — policy: {policy}")
            if path: fig.savefig(path, dpi=150, bbox_inches="tight")
        return assign, summary, fig

    def crop_mix_3d(self, assign, title=None, pipes=False):
        base = viz.model_traces(self.model, tier_color="#e0e0e0", group_legend=True) + viz.equipment_traces(self.equipment_inside, opacity=0.12, group_legend=True)
        if pipes:
            base += H.pipe_traces(self.network, opacity=0.35)
        return CV.rack_3d_holes(assign, self.model, base_traces=base, title=title)
