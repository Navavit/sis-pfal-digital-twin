"""SIS PFAL digital-twin web dashboard (Streamlit) — a thin UI over `pfal_twin.twin.DigitalTwin`.
Rong Pralong (โรงประลอง) project · School of Integrated Science, Kasetsart University.

    streamlit run app/streamlit_app.py

Pages:  Live  (latest ThingsBoard values in the 3-D twin, auto-refresh)
        History  (browse the local 10-min store, time-slider 3-D, KPI, events, heat-map)
        Layout & water  (as-built layout, water-system plan, process flow, flow animation)
        What-if  (crop mix on the 700 holes, light/energy scenarios)
Notebooks 01-04 produce the files the twin loads; this app only reads them (+ live/incremental pulls from ThingsBoard).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Streamlit only hot-reloads modules inside the script folder or on PYTHONPATH. On Streamlit Cloud a new commit
# re-runs this file but would keep the old `pfal_twin` in memory -> make the package watchable and, if a stale copy
# is already loaded (version mismatch), drop it and re-import.
import os  # noqa: E402
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
NEEDS_PKG = "2026.09.14.3"
import pfal_twin  # noqa: E402
if getattr(pfal_twin, "__version__", "") != NEEDS_PKG:
    for _m in [m for m in sys.modules if m == "pfal_twin" or m.startswith("pfal_twin.")]:
        del sys.modules[_m]
    st_cache_clear = True
else:
    st_cache_clear = False
from pfal_twin.twin import DigitalTwin  # noqa: E402
from pfal_twin import thingsboard as tb, models as M  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
PROJECT = dict(name="SIS PFAL Digital Twin", th="โรงประลอง · วิทยาลัยบูรณาการศาสตร์ มหาวิทยาลัยเกษตรศาสตร์",
               en="Rong Pralong project · School of Integrated Science, Kasetsart University")
st.set_page_config(page_title=PROJECT["name"], layout="wide", page_icon=str(ASSETS / "favicon.png"))
st.logo(str(ASSETS / "sis_logo.png"), size="large", link="https://sis.ku.ac.th")
FONT = "IBM Plex Sans Thai"   # loopless (ไม่มีหัว) Thai + Latin in one family
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');
html, body, .stApp, .stApp * {{ font-family: '{FONT}', sans-serif !important; }}
code, pre, .stCode *, [data-testid="stCode"] * {{ font-family: 'IBM Plex Mono', ui-monospace, monospace !important; }}
</style>""", unsafe_allow_html=True)
import plotly.io as pio
pio.templates["sis"] = pio.templates["plotly_white"]; pio.templates["sis"].layout.font.family = f"{FONT}, sans-serif"; pio.templates.default = "sis"
TZ = tb.TZ
PLOTLY = dict(use_container_width=True, config=dict(displaylogo=False, modeBarButtonsToAdd=["resetCameraDefault3d"], responsive=True))


# ---------------------------------------------------------------------------- cached resources
if st_cache_clear:
    st.cache_resource.clear(); st.cache_data.clear()


@st.cache_resource(show_spinner="loading digital twin ...")
def get_twin() -> DigitalTwin:
    return DigitalTwin.load()


@st.cache_data(ttl=60, show_spinner=False)
def live_snapshot(_nonce: int):
    """Latest values from ThingsBoard (cached 60 s so many viewers do not hammer the server)."""
    st_, table = get_twin().live()
    return st_, table


@st.cache_resource(show_spinner="rendering layout ...")
def static_figure(kind: str):
    tw = get_twin()
    return {"layout": tw.layout_figure, "water": tw.water_plan, "flow": tw.flow_diagram, "corner": tw.corner_detail, "heatmap": tw.heatmap}[kind]()


def fmt(v, nd=1, unit=""):
    return "—" if v is None or v != v else f"{v:.{nd}f}{unit}"


def age_text(td: pd.Timedelta) -> str:
    s = int(td.total_seconds())
    return f"{s} s" if s < 90 else f"{s // 60} min" if s < 5400 else f"{s / 3600:.1f} h" if s < 172800 else f"{s / 86400:.1f} d"


def state_cards(state, ages: dict | None = None, row=None):
    """Metric cards — limited to what the public ThingsBoard dashboard shows (T/RH per unit, CO₂, VPD, VOC, EC/pH + setpoints)."""
    g = lambda k: (float(row.get(k, float("nan"))) if row is not None else float("nan"))
    c = st.columns(6)
    c[0].metric("Room T (mean of 3 walls)", fmt(state.room_T, 1, " °C"))
    c[1].metric("Room RH", fmt(state.room_RH, 0, " %"))
    c[2].metric("Room VPD (from T/RH)", fmt(state.room_VPD, 2, " kPa"))
    c[3].metric("CO₂", fmt(state.co2, 0, " ppm"))
    c[4].metric("Anteroom (ch 20)", fmt(state.ch_T["xy_md_20"], 1, " °C"), fmt(state.ch_RH["xy_md_20"], 0, " % RH"), delta_color="off")
    c[5].metric("Outside (ch 24)", fmt(state.ch_T["xy_md_24"], 1, " °C"), fmt(state.ch_RH["xy_md_24"], 0, " % RH"), delta_color="off")
    c = st.columns(6)
    c[0].metric("EC growing (gc1, 200 L)", fmt(state.ec["growing (gc1)"], 2, " mS/cm"), "set " + fmt(g("gc1.ecSetPoint"), 2), delta_color="off")
    c[1].metric("pH growing", fmt(state.ph["growing (gc1)"], 2), "set " + fmt(g("gc1.pHSetPoint"), 2), delta_color="off")
    c[2].metric("EC nursery-2 (gc2, 100 L)", fmt(state.ec["nursery-2 (gc2)"], 2, " mS/cm"), "set " + fmt(g("gc2.ecSetPoint"), 2), delta_color="off")
    c[3].metric("pH nursery-2", fmt(state.ph["nursery-2 (gc2)"], 2), "set " + fmt(g("gc2.pHSetPoint"), 2), delta_color="off")
    c[4].metric("VOC (CO₂ controller)", fmt(g("co2.VOC"), 0))
    c[5].metric("VPD (CO₂ controller)", fmt(state.co2_VPD, 2, " kPa"))
    if extended:
        st.markdown("<small>**Beyond the ThingsBoard dashboard** — controller state, lighting, dosing configuration</small>", unsafe_allow_html=True)
        c = st.columns(6)
        led = "—" if state.led != state.led else ("ON" if state.led >= 0.5 else "off")
        c[0].metric("LED (gc1)", led, "brightness " + "/".join(fmt(b, 0) for b in state.brightness) + " %", delta_color="off")
        c[1].metric("Circulation pumps", "grow " + ("ON" if state.pump_on["gc1"] else "off") + " · nur-2 " + ("ON" if state.pump_on["gc2"] else "off"),
                    "mode " + tb.PUMP_MODE.get(g("gc1.modePumpWater"), "—") + " / " + tb.PUMP_MODE.get(g("gc2.modePumpWater"), "—"), delta_color="off")
        c[2].metric("Plant day", fmt(state.plant_day["growing (gc1)"], 0) + " / " + fmt(state.plant_day["nursery-2 (gc2)"], 0),
                    "task " + fmt(g("gc1.task"), 0) + " / " + fmt(g("gc2.task"), 0) + " · stage " + fmt(g("gc1.stage"), 0) + " / " + fmt(g("gc2.stage"), 0), delta_color="off")
        c[3].metric("Dosing gc1 (A / B / acid)", f"{fmt(g('gc1.aDosingTime'), 0)} / {fmt(g('gc1.bDosingTime'), 0)} / {fmt(g('gc1.pHDosingTime'), 0)} s",
                    f"wait {fmt(g('gc1.ecWaiting'), 0)} s · speed {fmt(g('gc1.pumpASpeed'), 0)} % · shots {fmt(g('gc1.ecDosingCount'), 0)}", delta_color="off")
        c[4].metric("Dosing gc2 (A / B / acid)", f"{fmt(g('gc2.aDosingTime'), 0)} / {fmt(g('gc2.bDosingTime'), 0)} / {fmt(g('gc2.pHDosingTime'), 0)} s",
                    f"wait {fmt(g('gc2.ecWaiting'), 0)} s · speed {fmt(g('gc2.pumpASpeed'), 0)} % · shots {fmt(g('gc2.ecDosingCount'), 0)}", delta_color="off")
        up1, up2 = g("gc1.upTime") / 3.6e9, g("gc2.upTime") / 3.6e9        # µs -> h
        c[5].metric("Controller uptime gc1 / gc2", f"{fmt(up1, 1)} / {fmt(up2, 1)} h",
                    f"CO₂ valve {'ON' if g('co2.Relay_co2') >= 0.5 else 'off' if g('co2.Relay_co2') == g('co2.Relay_co2') else '—'} · amb T {fmt(g('gc1.ambTemperature'), 1)} °C", delta_color="off")
    if ages:
        st.caption("last message per device: " + " · ".join(f"**{d}** {age_text(a)} ago" for d, a in ages.items()))


# ---------------------------------------------------------------------------- sidebar
tw = get_twin()
st.sidebar.markdown(f"**{PROJECT['name']}**  \n<small>{PROJECT['th']}</small>", unsafe_allow_html=True)
page = st.sidebar.radio("Page", ["Live", "History", "Layout & water", "What-if"], label_visibility="collapsed")
var = st.sidebar.selectbox("3-D colour variable", ["T", "RH", "VPD"], format_func=lambda v: {"T": "air temperature", "RH": "relative humidity", "VPD": "VPD"}[v])
RANGES = {"T": (20, 35), "RH": (40, 95), "VPD": (0.2, 2.0)}
extended = st.sidebar.toggle("show more than the ThingsBoard dashboard", value=True,
                             help="off = only the keys the public dashboard shows; on = also LED, pumps, dosing configuration, controller health, derived values")
d0, d1 = tw.data_span()
st.sidebar.markdown(f"**Local store**  \n{d0:%Y-%m-%d} → {d1:%Y-%m-%d %H:%M}  \n{len(tw.data):,} × 10-min bins")
if st.sidebar.button("⬇ Pull new data from ThingsBoard", help="incremental download since the last stored sample, then rebuild the 10-min table"):
    with st.spinner("downloading ..."):
        tw.update_data(verbose=False)
    static_figure.clear(); st.sidebar.success(f"store now ends {tw.data_span()[1]:%Y-%m-%d %H:%M}")
    st.rerun()
with st.sidebar.expander("about"):
    st.code(tw.summary(), language=None)
    st.markdown(f"{PROJECT['en']}  \nSIS PFAL = plant factory with artificial lighting at the School of Integrated Science.  \n"
                "Source: ThingsBoard public dashboard *Vertical Smart Farming* (cat-smartgrow.com). Geometry from the LiDAR scan of 2026-09-13.")

# ============================================================================ LIVE
if page == "Live":
    st.title("Live — latest values in the twin")
    top = st.columns([1, 1, 4])
    auto = top[0].toggle("auto-refresh (60 s)", value=True)
    if top[1].button("refresh now"):
        live_snapshot.clear()

    @st.fragment(run_every="60s" if auto else None)
    def live_view():
        try:
            state, table = live_snapshot(int(time.time() // 60))
        except Exception as e:  # network / ThingsBoard down -> fall back to the last stored bin
            st.error(f"ThingsBoard not reachable ({e}); showing the last stored 10-min bin instead.")
            state, table = tw.state(d1), None
        ages = table.groupby("device")["age"].min().to_dict() if table is not None else None
        row = table["value"] if table is not None else tw.data.loc[state.time]
        st.subheader(f"{state.time:%Y-%m-%d %H:%M:%S} (Asia/Bangkok)")
        state_cards(state, ages, row)
        if ages and any(a > pd.Timedelta("30min") for a in ages.values()):
            stale = ", ".join(f"{d} ({age_text(a)})" for d, a in ages.items() if a > pd.Timedelta("30min"))
            st.warning(f"stale devices: {stale} — values older than 24 h are hidden from the twin")
        lo, hi = RANGES[var]
        st.plotly_chart(tw.figure_3d(var=var, st=state, cmin=lo, cmax=hi, height=650, title_prefix="LIVE ", public=not extended), **PLOTLY)
        with st.expander("latest values — all keys" if extended else "latest values — dashboard keys"):
            if table is not None:
                t2 = table if extended else table[table.index.isin(tb.DASHBOARD_COLUMNS)]
                t2 = t2.copy(); t2["age"] = t2["age"].map(age_text); t2["ts"] = t2["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
                t2.insert(0, "meaning", [tb.KEY_LABELS.get(k, "") for k in t2["key"]]); t2["on dashboard"] = t2.index.isin(tb.DASHBOARD_COLUMNS)
                st.dataframe(t2[["meaning", "value", "ts", "age", "on dashboard"]], width="stretch", height=480)

    live_view()

# ============================================================================ HISTORY
elif page == "History":
    st.title("History — browse the stored 10-min data")
    c = st.columns([1, 1, 1, 2])
    start = c[0].date_input("from", value=(d1 - pd.Timedelta(days=7)).date(), min_value=d0.date(), max_value=d1.date())
    end = c[1].date_input("to", value=d1.date(), min_value=d0.date(), max_value=d1.date())
    freq = c[2].selectbox("resample", ["10min", "1h", "6h", "1D"], index=1)
    groups = {
        "Room T (3 wall sensors)": [f"gw.{ch}_t" for ch in tb.ROOM_CHANNELS],
        "Anteroom / outside T": ["gw.xy_md_20_t", "gw.xy_md_24_t"],
        "RH (all XY-MD02)": [f"gw.{ch}_h" for ch in tb.CHANNEL_ORDER],
        "CO₂ (ppm)": ["co2.CO2"],
        "EC (mS/cm)": ["gc1.ec", "gc1.ecSetPoint", "gc2.ec", "gc2.ecSetPoint"],
        "pH": ["gc1.ph", "gc1.pHSetPoint", "gc2.ph", "gc2.pHSetPoint"],
        "VOC (CO₂ controller)": ["co2.VOC"],
        "Dosing pumps A / B / pH (0–1)": ["gc1.pumpA", "gc1.pumpB", "gc1.pumpPH", "gc2.pumpA", "gc2.pumpB", "gc2.pumpPH"],
    }
    if extended:
        groups.update({
            "LED / circulation pump / CO₂ valve (0–1)": ["gc1.led", "gc1.pwmWater", "gc2.pwmWater", "co2.Relay_co2"],
            "LED brightness ch1–4 (%)": [f"gc1.currentStageBrightness{i}" for i in range(1, 5)],
            "Dose shots per day (derived from the counters)": ["derived.gc1_ec_shots", "derived.gc1_ph_shots", "derived.gc2_ec_shots", "derived.gc2_ph_shots"],
            "Dosing configuration (s per shot / wait s)": ["gc1.aDosingTime", "gc1.bDosingTime", "gc1.pHDosingTime", "gc1.ecWaiting", "gc2.aDosingTime", "gc2.bDosingTime", "gc2.pHDosingTime", "gc2.ecWaiting"],
            "Pump modes (0 off / 1 manual / 2 auto)": ["gc1.modePumpA", "gc1.modePumpB", "gc1.modePumpPH", "gc1.modePumpWater", "gc2.modePumpA", "gc2.modePumpWater"],
            "Controller ambient T / RH (inside the box)": ["gc1.ambTemperature", "gc1.ambHumidity", "gc2.ambTemperature", "gc2.ambHumidity"],
            "Controller uptime (h) — drops = reboot": ["derived.gc1_uptime_h", "derived.gc2_uptime_h"],
            "CO₂ controller T / RH / pressure": ["co2.temperature", "co2.humidity", "co2.pressure"],
            "Plant day / task / stage": ["gc1.plantDay", "gc2.plantDay", "gc1.task", "gc2.task", "gc1.stage", "gc2.stage"],
        })
    chosen = c[3].multiselect("series", list(groups), default=list(groups)[:2])
    hist = tw.history(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1), freq=None)
    if extended:
        for d in ("gc1", "gc2"):        # derived series
            for k, nm in (("ecDosingCount", "ec_shots"), ("pHDosingCount", "ph_shots")):
                if f"{d}.{k}" in hist:
                    daily = hist[f"{d}.{k}"].resample("1D").max().diff().clip(lower=0)
                    hist[f"derived.{d}_{nm}"] = daily.reindex(hist.index, method="ffill")
            if f"{d}.upTime" in hist:
                hist[f"derived.{d}_uptime_h"] = hist[f"{d}.upTime"] / 3.6e9
    else:
        hist = tb.public_columns(hist)
    if hist.empty:
        st.info("no data in this range"); st.stop()

    st.markdown("#### Twin at one moment")
    idx = hist.index
    pick = st.slider("time", min_value=idx[0].to_pydatetime(), max_value=idx[-1].to_pydatetime(), value=idx[-1].to_pydatetime(), step=pd.Timedelta("10min").to_pytimedelta(), format="DD MMM HH:mm")
    state = tw.state(pd.Timestamp(pick))
    state_cards(state, row=hist.loc[state.time] if state.time in hist.index else None)
    lo, hi = RANGES[var]
    st.plotly_chart(tw.figure_3d(var=var, st=state, cmin=lo, cmax=hi, height=600, public=not extended), **PLOTLY)

    st.markdown("#### Time series")
    import plotly.graph_objects as go
    for g in chosen:
        cols = [k for k in groups[g] if k in hist.columns]
        D = hist[cols].resample(freq).mean() if freq != "10min" else hist[cols]
        fig = go.Figure()
        for k in cols:
            lab = tb.channel_label(k[3:-2]) + k[-2:] if k.startswith("gw.") else (k.split(".")[0] + " " + tb.KEY_LABELS.get(k.split(".")[1], k.split(".")[1]))
            fig.add_scatter(x=D.index, y=D[k], mode="lines", name=lab, connectgaps=False, line_shape="hv" if ("mode" in k or "Time" in k or "Waiting" in k or "shots" in k) else "linear")
        fig.add_vline(x=pd.Timestamp(pick), line_dash="dot", line_color="grey")
        fig.update_layout(title=g, height=300, margin=dict(l=40, r=20, t=40, b=30), legend=dict(orientation="h", y=-0.25), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, key=f"ts_{g}")

    t1, t2, t3 = st.tabs(["KPI per channel (whole store)", "Events", "Heat-map (whole store)"])
    with t1:
        st.dataframe(tw.kpi(), width="stretch")
    with t2:
        ev = tw.events(save=False)
        ev = ev[(ev.start >= pd.Timestamp(start).tz_localize(TZ)) & (ev.start < (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize(TZ))]
        st.dataframe(ev, width="stretch", height=350)
        st.caption(f"thresholds: {tw.limits}")
    with t3:
        st.pyplot(static_figure("heatmap"), width="stretch")
    st.download_button("download selected range (CSV)", hist.to_csv().encode(), file_name=f"pfal_{start}_{end}.csv", mime="text/csv")

# ============================================================================ LAYOUT
elif page == "Layout & water":
    st.title("As-built layout and water system")
    t1, t2, t3, t4, t5 = st.tabs(["Layout (plan + elevation)", "Water-system plan", "Process flow", "Flow animation (3-D)", "Pipe corner detail"])
    with t1:
        st.pyplot(static_figure("layout"), width="stretch")
    with t2:
        st.pyplot(static_figure("water"), width="stretch")
    with t3:
        st.pyplot(static_figure("flow"), width="stretch")
    with t4:
        st.plotly_chart(tw.flow_animation(), **PLOTLY)
        st.caption("schematic — direction from photos and the design drawing; there is no flow sensor")
    with t5:
        st.pyplot(static_figure("corner"), width="stretch")
    with st.expander("equipment table"):
        st.dataframe(tw.equipment, width="stretch")
    with st.expander("sensor table"):
        st.dataframe(tw.sensors, width="stretch")

# ============================================================================ WHAT-IF
elif page == "What-if":
    st.title("What-if")
    tab_crop, tab_light = st.tabs(["Crop mix on the 700 holes (tiers 2–5)", "Light / energy scenarios"])
    with tab_crop:
        crops = [k for k in M.CROPS if k != "empty"]
        c = st.columns([1, 3])
        with c[0]:
            picked = st.multiselect("crops", crops, default=["green oak", "kale", "basil"])
            if not picked:
                st.warning("pick at least one crop"); st.stop()
            # shares must add up to exactly 100 %: the last crop takes whatever is left
            mix, used = {}, 0
            for k in picked[:-1]:
                key, room = f"mix_{k}", 100 - used
                st.session_state[key] = min(int(st.session_state.get(key, round(100 / len(picked)))), room)   # clamp before the widget is built
                if room > 0:
                    v = st.slider(f"{k} (%)", 0, room, key=key)
                else:
                    v = 0; st.session_state[key] = 0; st.caption(f"{k}: 0 % (nothing left)")
                mix[k] = v; used += v
            last = picked[-1]; mix[last] = 100 - used
            st.slider(f"{last} (%) — remainder", 0, 100, mix[last], disabled=True, key=f"mix_rem_{last}_{mix[last]}")
            st.progress(1.0, text=f"total = 100 %  ({', '.join(f'{k} {v}' for k, v in mix.items())})")
            mix = {k: v for k, v in mix.items() if v > 0}
            if not mix:
                st.warning("all shares are 0"); st.stop()
            policy = st.radio("placement", ["blocks", "per_tier"], horizontal=True, help="blocks = contiguous blocks tier by tier; per_tier = same mix on every tier")
            photoperiod = st.slider("photoperiod (h)", 10, 20, 16)
            st.caption("yields use the schematic crop catalogue and the modelled DLI — not calibrated yet")
        with c[1]:
            assign, summary, _ = tw.crop_mix(mix, policy=policy, photoperiod_h=photoperiod, view=None)
            st.plotly_chart(tw.crop_mix_3d(assign, title=f"Crop mix — {', '.join(f'{k} {v:.0f} %' for k, v in mix.items())}"), **PLOTLY)
        st.dataframe(summary, width="stretch")
        st.download_button("download hole assignment (CSV)", assign.to_csv(index=False).encode(), file_name="crop_mix_assignment.csv", mime="text/csv")
    with tab_light:
        c = st.columns(2)
        pps = c[0].multiselect("photoperiods (h)", [10, 12, 14, 16, 18, 20], default=[12, 14, 16, 18])
        dims = c[1].multiselect("dimming (%)", [40, 60, 80, 100], default=[60, 80, 100])
        if pps and dims:
            st.dataframe(tw.whatif_light(photoperiods=tuple(pps), dims=tuple(dims)), width="stretch")
        with st.expander("model parameters (L3, uncalibrated)"):
            st.dataframe(tw.params.to_frame(), width="stretch")
        st.caption("heat balance / energy use the steady-state model of notebook 06; calibrate with a PPFD map, LED count and the AC COP before quoting numbers")

# ---------------------------------------------------------------------------- footer
st.divider()
st.caption(f"**{PROJECT['name']}** — {PROJECT['th']}  \n{PROJECT['en']}")
