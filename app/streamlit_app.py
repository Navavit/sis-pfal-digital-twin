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
NEEDS_PKG = "2026.09.15.3"
APP_BUILD = "2026-09-15 g"          # shown in the footer so everyone can tell which version is running
import pfal_twin  # noqa: E402
if getattr(pfal_twin, "__version__", "") != NEEDS_PKG:
    for _m in [m for m in sys.modules if m == "pfal_twin" or m.startswith("pfal_twin.")]:
        del sys.modules[_m]
    st_cache_clear = True
else:
    st_cache_clear = False
from pfal_twin.twin import DigitalTwin  # noqa: E402
from pfal_twin import thingsboard as tb, models as M, store  # noqa: E402

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
/* Streamlit's icons are ligatures of an icon font -- keep that font, otherwise they render as text ("keyboard_arrow_right") */
.stApp [data-testid="stIconMaterial"], .stApp [data-testid="stExpanderToggleIcon"], .stApp [class*="material-symbols"],
.stApp span[translate="no"] {{ font-family: 'Material Symbols Rounded' !important; }}
</style>""", unsafe_allow_html=True)
import plotly.io as pio
pio.templates["sis"] = pio.templates["plotly_white"]; pio.templates["sis"].layout.font.family = f"{FONT}, sans-serif"; pio.templates.default = "sis"
TZ = tb.TZ
PLOTLY = dict(use_container_width=True, config=dict(displaylogo=False, modeBarButtonsToAdd=["resetCameraDefault3d"], responsive=True))


# ---------------------------------------------------------------------------- cached resources
if st_cache_clear:
    st.cache_resource.clear(); st.cache_data.clear()


@st.cache_data(ttl=600, show_spinner=False)
def store_version(_nonce: int = 0) -> str:
    """Every 10 min: if the `data` branch on GitHub has a newer store than the local file, download it.
    Returns the manifest timestamp that identifies the store version (keys the twin cache)."""
    try:
        r = store.sync_from_github()
    except Exception as e:  # GitHub unreachable -> keep the local copy
        r = dict(action=f"error: {e}", local=store.local_manifest())
    st.session_state["store_status"] = r
    lm = r.get("local") or {}
    return lm.get("updated_at", "local")


@st.cache_resource(show_spinner="loading digital twin ...")
def get_twin(version: str = "") -> DigitalTwin:
    return DigitalTwin.load()


STORE_VERSION = store_version()


@st.cache_data(ttl=600, show_spinner=False)
def top_up(version: str, _nonce: int = 0):
    """Every 10 min: append what ThingsBoard has since the stored table ended (in memory), so History is never behind
    even when the 30-min GitHub Actions job is delayed."""
    try:
        return get_twin(version).top_up()
    except Exception as e:
        return f"top-up failed: {e}"


TOP_UP = top_up(STORE_VERSION, int(time.time() // 600))


@st.cache_data(ttl=60, show_spinner=False)
def live_snapshot(_nonce: int):
    """Latest values from ThingsBoard (cached 60 s so many viewers do not hammer the server)."""
    st_, table = get_twin(STORE_VERSION).live()
    return st_, table


@st.cache_data(ttl=60, show_spinner=False)
def recent_window(hours: int, _nonce: int):
    """Last `hours` hours straight from ThingsBoard (5-min averages, raw pump events) — same window as the dashboard."""
    return get_twin(STORE_VERSION).recent(hours=hours, interval_min=5 if hours <= 24 else 15)


def ts_chart(df, cols, title, unit="", height=280, setpoints=None, step=False):
    import plotly.graph_objects as go
    fig = go.Figure()
    for k in cols:
        if k not in df.columns or df[k].dropna().empty:
            continue
        lab = tb.channel_label(k[3:-2]).split(" — ")[1] if k.startswith("gw.") else k.split(".")[0] + " " + tb.KEY_LABELS.get(k.split(".")[1], k.split(".")[1])
        d = df[k].dropna()
        fig.add_scatter(x=d.index, y=d.values, mode="lines", name=lab, line_shape="hv" if step else "linear", connectgaps=False)
    for k, lab in (setpoints or {}).items():
        if k in df.columns and df[k].dropna().size:
            fig.add_scatter(x=df.index, y=df[k].ffill().values, mode="lines", name=lab, line=dict(dash="dash", color="grey"), line_shape="hv")
    # title on top, legend directly under it (above the plot) -> never collides with the x-axis date labels
    n = len(fig.data); rows = 1 if n <= 3 else 2 if n <= 6 else 3
    fig.update_layout(title=dict(text=title, y=0.99, yanchor="top", x=0, xanchor="left", font=dict(size=14)), height=height,
                      margin=dict(l=45, r=10, t=36 + 22 * rows, b=35), yaxis_title=unit, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", font=dict(size=10), itemwidth=30))
    return fig


def dose_chart(df, dev, height=220):
    """ThingsBoard 'Dose stage' state chart: three lanes (A, B, pH) that go high while the pump runs."""
    import plotly.graph_objects as go
    fig = go.Figure(); lanes = (("pumpA", "part A", 2), ("pumpB", "part B", 1), ("pumpPH", "acid (pH)", 0))
    for k, lab, base in lanes:
        col = f"{dev}.{k}"
        if col in df.columns and df[col].dropna().size:
            d = df[col].dropna()
            fig.add_scatter(x=d.index, y=base + 0.8 * d.values, mode="lines", name=lab, line_shape="hv")
    fig.update_layout(title=dict(text=f"Dose stage — {dev} ({'growing 200 L' if dev == 'gc1' else 'nursery-2 100 L'})", y=0.99, yanchor="top", x=0, xanchor="left", font=dict(size=14)),
                      height=height, margin=dict(l=45, r=10, t=58, b=35), yaxis=dict(tickvals=[0, 1, 2], ticktext=["acid", "B", "A"], range=[-0.2, 3]),
                      hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", font=dict(size=10)))
    return fig


def stat_line(d, nd=2):
    d = d.dropna(); return f"now {d.iloc[-1]:.{nd}f} · min {d.min():.{nd}f} · avg {d.mean():.{nd}f} · max {d.max():.{nd}f}" if d.size else "no data"


@st.cache_data(show_spinner=False)
def availability_figure(version: str):
    """Per-device data coverage per day (share of 10-min bins with at least one value) -> shows the gaps at a glance."""
    import plotly.graph_objects as go
    w = get_twin(version).data
    w = w[[c for c in w.columns if c.split(".", 1)[1] not in tb.CONTROL_KEYS]]     # measured keys only (control keys are forward-filled)
    av = tb.availability(w, "1D")
    order = [d for d in ("gw", "gc1", "gc2", "co2") if d in av.columns]
    label = {"gw": "gw — XY-MD02 T/RH ×5", "gc1": "gc1 — growing controller", "gc2": "gc2 — nursery-2 controller", "co2": "co2 — CO₂ controller"}
    fig = go.Figure(go.Heatmap(z=av[order].T.values * 100, x=av.index, y=[label[d] for d in order], colorscale=[[0, "#f2f2f2"], [0.01, "#fde0c8"], [1, "#1f6f6b"]],
                               zmin=0, zmax=100, colorbar=dict(title="% of day", thickness=12, len=0.9), hovertemplate="%{y}<br>%{x|%d %b %Y}: %{z:.0f} % of the day<extra></extra>"))
    fig.update_layout(height=190, margin=dict(l=10, r=10, t=10, b=30), yaxis=dict(autorange="reversed"), font=dict(size=11))
    return fig


@st.cache_data(show_spinner=False)
def full_store_bytes(version: str, fmt: str) -> bytes:
    """Whole 10-min table as CSV or Parquet for the download buttons (cached per store version)."""
    import io as _io
    w = get_twin(version).data
    if fmt == "parquet":
        b = _io.BytesIO(); w.to_parquet(b); return b.getvalue()
    return w.to_csv(float_format="%.3f").encode()


@st.cache_resource(show_spinner="rendering layout ...")
def static_figure(kind: str):
    tw = get_twin(STORE_VERSION)
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
tw = get_twin(STORE_VERSION)
st.sidebar.markdown(f"**{PROJECT['name']}**  \n<small>{PROJECT['th']}</small>", unsafe_allow_html=True)
page = st.sidebar.radio("Page", ["Overview", "Live", "History", "Layout & water", "What-if"], label_visibility="collapsed")
VAR_LABEL = {"T": "air temperature (°C)", "RH": "relative humidity (%)", "VPD": "VPD (kPa)"}


def colour_picker(key):
    """Radio next to a 3-D view: which variable colours the rack and the XY-MD02 markers."""
    return st.radio("colour the 3-D twin by", list(VAR_LABEL), format_func=VAR_LABEL.get, horizontal=True, key=key)

RANGES = {"T": (20, 35), "RH": (40, 95), "VPD": (0.2, 2.0)}
extended = st.sidebar.toggle("show more than the ThingsBoard dashboard", value=True,
                             help="off = only the keys the public dashboard shows; on = also LED, pumps, dosing configuration, controller health, derived values")
d0, d1 = tw.data_span()
_ss = st.session_state.get("store_status", {}); _lm = _ss.get("local") or {}
st.sidebar.markdown(f"**History store**  \n{d0:%Y-%m-%d} → {d1:%Y-%m-%d %H:%M}  \n{len(tw.data):,} × 10-min bins  \n"
                    f"<small>updated {pd.Timestamp(_lm['updated_at']).tz_convert(TZ):%d %b %H:%M} · {_ss.get('action', '')}</small>" if _lm.get("updated_at") else
                    f"**History store**  \n{d0:%Y-%m-%d} → {d1:%Y-%m-%d %H:%M}  \n{len(tw.data):,} × 10-min bins", unsafe_allow_html=True)
if st.sidebar.button("↻ check for new data", help="GitHub Actions refreshes the store every 30 min and the app tops it up from ThingsBoard every 10 min — this checks now"):
    store_version.clear(); top_up.clear(); static_figure.clear(); st.rerun()
with st.sidebar.expander("about"):
    st.code(tw.summary(), language=None)
    st.markdown(f"{PROJECT['en']}  \nSIS PFAL = plant factory with artificial lighting at the School of Integrated Science.  \n"
                "Source: ThingsBoard public dashboard *Vertical Smart Farming* (cat-smartgrow.com). Geometry from the LiDAR scan of 2026-09-13.")

# ============================================================================ OVERVIEW
if page == "Overview":
    PH = ASSETS / "photos"
    st.title("SIS PFAL Digital Twin")
    st.markdown(f"**{PROJECT['th']}**  \n{PROJECT['en']}")
    c1, c2 = st.columns([1.35, 1])
    c1.image(str(PH / "IMG_2518.jpg"), caption="SIS PFAL — plant factory with artificial lighting, School of Integrated Science, Kasetsart University (13 Sep 2026)", width="stretch")
    c2.image(str(PH / "IMG_2519.jpg"), caption="Front of the unit: anteroom entrance beside the SIS KU coffee corner", width="stretch")
    c2.image(str(PH / "IMG_2520.jpg"), caption="Inside: one 5-tier rack, 5.4 × 1.0 m, in a 7.1 × 3.0 × 2.6 m room", width="stretch")

    st.markdown("""
#### แอปนี้ทำอะไรได้ · What this app does
Digital twin = แบบจำลองห้องปลูกจริง (รูปทรงจาก LiDAR) ที่ผูกกับข้อมูลเซ็นเซอร์จริงจาก ThingsBoard — ดูสภาพห้อง **ตอนนี้**, **ย้อนหลัง** และ **ลองสถานการณ์** ได้จากที่เดียว
""")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown("**📡 Live**  \nกราฟแบบ dashboard (T/RH 5 จุด, CO₂, EC/pH + set-point, การจ่ายปุ๋ย) + twin 3-D ระบายสีตามค่าจริง รีเฟรชทุก 60 วิ  \n*Real-time charts and the 3-D twin coloured by live readings*")
    k2.markdown("**🕓 History**  \nเลื่อนเวลาดูห้อง ณ ช่วงใดก็ได้ตั้งแต่ ธ.ค. 2025, กราฟ, KPI, เหตุการณ์ผิดปกติ, ดาวน์โหลด CSV  \n*Time slider, KPIs, events and CSV export since Dec 2025*")
    k3.markdown("**🗺️ Layout & water**  \nผัง as-built จาก point cloud, ระบบท่อน้ำ/ปุ๋ย, process flow และแอนิเมชันการไหล  \n*As-built layout, pipework and flow animation*")
    k4.markdown("**🌱 What-if**  \nเลือกสัดส่วนผักบน 700 หลุม (ชั้น 2–5) ดูผังรายหลุม 3-D + ผลผลิต/รายได้/แสงที่ต้องการ, สถานการณ์แสง–พลังงาน  \n*Crop-mix and light/energy scenarios*")

    st.markdown("#### ข้อมูลที่ใช้ · Data behind the twin")
    R_, K_ = tw.model["room"], tw.model["rack"]
    st.markdown(f"""
| | |
|---|---|
| **ห้อง · room** | {R_['L']:.2f} × {R_['W']:.2f} × {R_['H']:.2f} m — from 2 LiDAR scans (13 Sep 2026) |
| **ชั้นปลูก · rack** | {K_['length']:.2f} × {K_['width']:.2f} m, {len(K_['tiers'])} tiers · 700 planting holes on tiers 2–5 |
| **เซ็นเซอร์ / อุปกรณ์ · sensors / equipment** | {len(tw.sensors)} sensor units (5 × XY-MD02 T/RH, CO₂ controller, 2 grow controllers) · {len(tw.equipment)} mapped items |
| **ข้อมูล IoT · records** | {len(tw.data):,} × 10-min bins, {d0:%d %b %Y} → {d1:%d %b %Y} (refreshed every 30 min) |
| **แหล่งข้อมูล · source** | ThingsBoard dashboard *Vertical Smart Farming* — cat-smartgrow.com (Civic Agrotech) |
""")
    st.caption("Model parameters of the what-if layer are schematic until calibrated with PPFD, LED and harvest measurements. Photos: site survey 13 Sep 2026.")

# ============================================================================ LIVE
elif page == "Live":
    top = st.columns([2.2, 1, 1, 1.2])
    top[0].title("Live")
    auto = top[1].toggle("auto-refresh 60 s", value=True)
    if top[2].button("refresh now"):
        live_snapshot.clear(); recent_window.clear()
    hours = top[3].selectbox("window", [6, 12, 24, 72, 168], index=2, format_func=lambda h: f"{h} h" if h < 48 else f"{h // 24} days")

    @st.fragment(run_every="60s" if auto else None)
    def live_view():
        # ---- latest state (for the status line and the 3-D twin)
        try:
            state, table = live_snapshot(int(time.time() // 60))
        except Exception as e:  # network / ThingsBoard down -> fall back to the last stored bin
            st.error(f"ThingsBoard not reachable ({e}); showing the last stored 10-min bin instead.")
            state, table = tw.state(d1), None
        ages = table.groupby("device")["age"].min().to_dict() if table is not None else None
        row = table["value"] if table is not None else tw.data.loc[state.time]
        stale = [f"{d} {age_text(a)}" for d, a in (ages or {}).items() if a > pd.Timedelta("30min")]
        st.caption(f"**{state.time:%Y-%m-%d %H:%M:%S}** Asia/Bangkok · " + " · ".join(f"{d} {age_text(a)} ago" for d, a in (ages or {}).items())
                   + (f" · ⚠ stale: {', '.join(stale)}" if stale else ""))

        # ---- charts first (same window and 5-min averaging as the ThingsBoard dashboard)
        try:
            R = recent_window(hours, int(time.time() // 60))
        except Exception as e:
            st.error(f"could not load the window from ThingsBoard ({e})"); R = pd.DataFrame()
        if R.empty:
            st.info("no data in this window")
        else:
            ch = [f"gw.xy_md_{a}_t" for a in (20, 24, 21, 22, 23)]
            c1, c2 = st.columns(2)
            c1.plotly_chart(ts_chart(R, ch, "Temperature — 5 × XY-MD02 (°C)", "°C"), use_container_width=True, key="ts_T")
            c2.plotly_chart(ts_chart(R, [k[:-2] + "_h" for k in ch], "Humidity — 5 × XY-MD02 (% RH)", "% RH"), use_container_width=True, key="ts_RH")
            c1, c2 = st.columns(2)
            c1.plotly_chart(ts_chart(R, ["co2.CO2"], f"CO₂ (ppm) — {stat_line(R.get('co2.CO2', pd.Series(dtype=float)), 0)}", "ppm"), use_container_width=True, key="ts_co2")
            c2.plotly_chart(ts_chart(R, ["co2.VPD", "co2.VOC"], "VPD (kPa) / VOC — CO₂ controller", ""), use_container_width=True, key="ts_vpd")
            for dev, nm in (("gc1", "Grow controller gc1 — growing stage, 200 L tank"), ("gc2", "Grow controller gc2 — nursery 2, 100 L tank")):
                st.markdown(f"**{nm}**")
                c1, c2, c3 = st.columns([2, 2, 1.4])
                c1.plotly_chart(ts_chart(R, [f"{dev}.ec"], f"EC (mS/cm) — {stat_line(R.get(f'{dev}.ec', pd.Series(dtype=float)))}", "mS/cm", setpoints={f"{dev}.ecSetPoint": "set-point"}), use_container_width=True, key=f"ts_ec_{dev}")
                c2.plotly_chart(ts_chart(R, [f"{dev}.ph"], f"pH — {stat_line(R.get(f'{dev}.ph', pd.Series(dtype=float)))}", "pH", setpoints={f"{dev}.pHSetPoint": "set-point"}), use_container_width=True, key=f"ts_ph_{dev}")
                c3.plotly_chart(dose_chart(R, dev, height=280), use_container_width=True, key=f"dose_{dev}")
            if extended:
                st.plotly_chart(ts_chart(R, ["gc1.led", "gc1.pwmWater", "gc2.pwmWater", "co2.Relay_co2"], "LED / circulation pumps / CO₂ valve (beyond the dashboard)", "on = 1", step=True, height=220), use_container_width=True, key="ts_ctrl")

        # ---- the twin itself
        st.markdown("#### 3-D twin — coloured by the latest readings")
        var = colour_picker("var_live"); lo, hi = RANGES[var]
        st.plotly_chart(tw.figure_3d(var=var, st=state, cmin=lo, cmax=hi, height=620, title_prefix="LIVE ", public=not extended), **PLOTLY, key=f"live3d_{var}")

        # ---- details, collapsed (the charts already show the numbers)
        with st.expander("current values as cards" + (" + controller state / dosing configuration" if extended else "")):
            state_cards(state, None, row)
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
    days = (d1 - d0).days
    _lm = (st.session_state.get("store_status") or {}).get("local") or {}
    upd = f" · store updated {pd.Timestamp(_lm['updated_at']).tz_convert(TZ):%d %b %Y %H:%M}" if _lm.get("updated_at") else ""
    st.markdown(f"**ข้อมูลมีตั้งแต่ · data available from {d0:%d %b %Y %H:%M} → {d1:%d %b %Y %H:%M}** ({days} days, {len(tw.data):,} × 10-min bins, {tw.data.shape[1]} columns){upd}  \n"
                "Store refreshed by GitHub Actions every 30 min + topped up from ThingsBoard every 10 min; grey days below = the device sent nothing that day.")
    st.plotly_chart(availability_figure(STORE_VERSION), use_container_width=True, key="availability")
    with st.expander("⬇ download the whole store · ดาวน์โหลดข้อมูลทั้งหมด"):
        st.markdown("Columns are `device.key` (e.g. `gw.xy_md_21_t` = temperature of XY-MD02 unit 21, `gc1.ec` = EC of the growing-stage controller); "
                    "time index is Asia/Bangkok; see [docs/DATA_DICTIONARY.md](https://github.com/Navavit/sis-pfal-digital-twin/blob/main/docs/DATA_DICTIONARY.md).")
        b1, b2, b3 = st.columns(3)
        b1.download_button("10-min table — CSV", full_store_bytes(STORE_VERSION, "csv"), file_name=f"sis_pfal_10min_{d0:%Y%m%d}_{d1:%Y%m%d}.csv", mime="text/csv", use_container_width=True)
        b2.download_button("10-min table — Parquet", full_store_bytes(STORE_VERSION, "parquet"), file_name=f"sis_pfal_10min_{d0:%Y%m%d}_{d1:%Y%m%d}.parquet", mime="application/octet-stream", use_container_width=True)
        b3.link_button("raw samples — Parquet on GitHub (13 MB)", f"https://github.com/{store.REPO}/raw/{store.BRANCH}/data/raw/iot/thingsboard_long.parquet", use_container_width=True)
        st.caption(f"Same files on GitHub, branch `{store.BRANCH}`: https://github.com/{store.REPO}/tree/{store.BRANCH}")
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
    with st.expander(f"values at {state.time:%Y-%m-%d %H:%M} as cards"):
        state_cards(state, row=hist.loc[state.time] if state.time in hist.index else None)
    var = colour_picker("var_hist"); lo, hi = RANGES[var]
    st.plotly_chart(tw.figure_3d(var=var, st=state, cmin=lo, cmax=hi, height=600, public=not extended), **PLOTLY, key=f"hist3d_{var}")

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
        with st.expander("วิธีใช้ · How to use", expanded=True):
            st.markdown("""
**ทำอะไร** — ทดลองว่าถ้าปลูกผักหลายชนิดผสมกันบน **700 หลุม** ของชั้น 2–5 (ชั้นละ 175 หลุม = 25 คอลัมน์ × 7 แถว) จะวางตรงไหน ได้ผลผลิต/รายได้เท่าไร และแสงพอหรือไม่

**ขั้นตอน**
1. **crops** — เลือกชนิดผัก (เพิ่ม/ลบได้) จากรายการ 9 ชนิด
2. **% แต่ละชนิด** — เลื่อน slider ของทุกชนิดยกเว้นตัวสุดท้าย; **ตัวสุดท้ายรับส่วนที่เหลือให้ครบ 100 % เอง** (slider ถัดไปจะถูกจำกัดไว้ไม่ให้เกิน)
3. **placement** — `blocks` = จัดเป็นบล็อกต่อเนื่อง ไล่ทีละชั้น (จัดการง่าย เก็บเกี่ยวทั้งบล็อก) · `per_tier` = ทุกชั้นมีสัดส่วนเหมือนกัน (กระจายความเสี่ยงต่อชั้น)
4. **photoperiod** — ชั่วโมงเปิดไฟต่อวัน มีผลกับ DLI (แสงสะสมรายวัน) ที่ผักได้รับ
5. ดูผล: **ภาพ 3-D** 1 จุด = 1 หลุม สีตามชนิดผัก (หมุน/ซูม/กดขยายได้ · คลิกชื่อใน legend เพื่อซ่อน/แสดง) และ **ตาราง** ด้านล่าง; ดาวน์โหลดผังรายหลุมเป็น CSV ได้

**อ่านตาราง** — `holes` จำนวนหลุม · `days_to_harvest` วันถึงเก็บเกี่ยว · `plant_fw_g` น้ำหนักสดต่อต้น · `kg_per_cycle` / `cycles_per_year` / `kg_per_year` ผลผลิต · `THB_per_year` รายได้ (ราคาในแคตตาล็อก) · `DLI_need` vs `DLI_available` แสงที่ต้องการ vs ที่โมเดลคำนวณได้ · `light_ok` = `yes` หรือขาดอีกกี่ mol/m²/d

**ข้อจำกัด** — ตัวเลขผลผลิต/ราคา/DLI ที่ต้องการมาจากแคตตาล็อกเชิงสมมติ (`pfal_twin/models.py: CROPS`) และ DLI ที่มีคำนวณจากกำลัง LED โดยประมาณ **ยังไม่ได้สอบเทียบ**กับค่าวัดจริง (PPFD, จำนวนหลอด, น้ำหนักเก็บเกี่ยว) — ใช้เปรียบเทียบ *ระหว่างทางเลือก* ได้ แต่อย่านำตัวเลขสัมบูรณ์ไปอ้างอิง
""")
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
        with st.expander("วิธีใช้ · How to use", expanded=True):
            st.markdown("""
**ทำอะไร** — เปรียบเทียบสถานการณ์ **ชั่วโมงเปิดไฟ (photoperiod) × ระดับหรี่ไฟ (dimming)** ว่าแต่ละแบบให้แสงสะสม (DLI) เท่าไร ใช้ไฟฟ้ากี่ kWh/วัน ค่าไฟกี่บาท และวันถึงเก็บเกี่ยวของผักสลัดเปลี่ยนอย่างไร
โมเดลคิดทั้งไฟ LED และภาระแอร์ที่ต้องดึงความร้อนจาก LED ออก (สมดุลความร้อนแบบคงตัว ใช้อุณหภูมิภายนอก/anteroom เฉลี่ยจากข้อมูลจริง)

**ขั้นตอน** — เลือกชุด photoperiod และ dimming ที่อยากเทียบ → ตารางแสดงทุกคู่ผสม เรียงตามค่าที่เลือก; แถวที่ DLI ใกล้ที่ผักต้องการ (สลัด ≈ 13–17 mol/m²/d) แต่ kWh ต่ำสุดคือจุดที่น่าสนใจ

**ข้อจำกัด** — พารามิเตอร์ (กำลัง LED, ประสิทธิภาพ, COP แอร์, ค่าไฟ) อยู่ใน *model parameters* ด้านล่าง ยังเป็นค่าประมาณ ต้องสอบเทียบก่อนนำตัวเลขไปอ้างอิง
""")
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
st.caption(f"**{PROJECT['name']}** — {PROJECT['th']}  \n{PROJECT['en']}  \n<small>build {APP_BUILD} · pfal_twin {pfal_twin.__version__}</small>", unsafe_allow_html=True)
