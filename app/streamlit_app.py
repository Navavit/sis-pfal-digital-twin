"""SIS PFAL digital-twin web dashboard (Streamlit) — a thin UI over `pfal_twin.twin.DigitalTwin`.
โรงประลอง (Fab Lab) · School of Integrated Science, Kasetsart University.

    streamlit run app/streamlit_app.py

Pages:  Live  (latest ThingsBoard values in the 3-D twin, auto-refresh)
        History  (browse the local 10-min store, time-slider 3-D, KPI, events, heat-map)
        Layout & water  (as-built layout, water-system plan, process flow, flow animation)
        What-if  (crop mix on the 720 holes, light/energy scenarios)
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
NEEDS_PKG = "2026.11.11.4"
APP_BUILD = "2026-11-11 o"          # shown in the footer so everyone can tell which version is running
import pfal_twin  # noqa: E402
if getattr(pfal_twin, "__version__", "") != NEEDS_PKG:
    for _m in [m for m in sys.modules if m == "pfal_twin" or m.startswith("pfal_twin.")]:
        del sys.modules[_m]
    st_cache_clear = True
else:
    st_cache_clear = False
from pfal_twin.twin import DigitalTwin  # noqa: E402
from pfal_twin import thingsboard as tb, models as M, store, planting, plants3d  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"
# Devices known to be out of service on purpose (edit when one goes away or comes back). Shown instead of "stale".
FLOOD = dict(th="น้ำท่วม PFAL", en="flood damage")
DEVICE_STATUS = {"gc2": dict(since="2026-09-16", **FLOOD), "gc1": dict(since="2026-09-18", **FLOOD),
                 "co2": dict(since="2026-10-26", th="ติดตั้งกลับหลังซ่อมแล้ว แต่ยังไม่ส่งข้อมูล (ระบบอื่นกลับมา 26 ต.ค.)",
                             en="reinstalled after flood repair, not reporting yet"),
                 "gw": dict(since="2026-09-26", **FLOOD)}
# "since" = last valid data (flood) or the date of the note; a device that reports after that day clears its own note
PROJECT = dict(name="SIS PFAL Digital Twin", th="โรงประลอง · วิทยาลัยบูรณาการศาสตร์ มหาวิทยาลัยเกษตรศาสตร์",
               en="Fab Lab · School of Integrated Science, Kasetsart University")
# Two URLs: / = the site (pages in the sidebar radio below), /dashboard = the TV screen. Hidden navigation only routes;
# both run this same script, which then draws the page that belongs to the URL.
_SITE = st.Page(lambda: None, title="SIS PFAL", url_path="site", default=True)
_DASH = st.Page(lambda: None, title="SIS PFAL Dashboard", url_path="dashboard")
_nav = st.navigation([_SITE, _DASH], position="hidden")
_nav.run()
ON_DASHBOARD = _nav.url_path == "dashboard"
# tab title in the same pattern as BURANA and SISoil: "NAME ชื่อไทย · คำอธิบาย"
st.set_page_config(page_title="SIS PFAL ห้องปลูกพืชระบบปิด · ดิจิทัลทวินของห้องปลูกพืชด้วยแสงเทียม", layout="wide",
                   page_icon=str(ASSETS / "favicon.png"))
FONT = "IBM Plex Sans Thai"   # loopless (ไม่มีหัว) Thai + Latin in one family
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');
html, body, .stApp, .stApp * {{ font-family: '{FONT}', sans-serif !important; }}
code, pre, .stCode *, [data-testid="stCode"] * {{ font-family: 'IBM Plex Mono', ui-monospace, monospace !important; }}
/* Streamlit's icons are ligatures of an icon font -- keep that font, otherwise they render as text ("keyboard_arrow_right") */
.stApp [data-testid="stIconMaterial"], .stApp [data-testid="stExpanderToggleIcon"], .stApp [class*="material-symbols"],
.stApp span[translate="no"] {{ font-family: 'Material Symbols Rounded' !important; }}
/* family header (same pattern as BURANA and SISoil): product mark + name, KU then SIS logos on the right */
.pfal-top {{ display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: center;
             padding: 4px 0 14px; margin-bottom: 6px; border-bottom: 1px solid #e3dfd4; }}
.pfal-top .brand {{ display: flex; align-items: center; gap: 14px; min-width: 0; }}
.pfal-top .brand-mark {{ flex: none; border-radius: 11px; display: block; }}
.pfal-top .name {{ font-size: 1.5rem; font-weight: 700; line-height: 1.25; color: #22201c; }}
.pfal-top .brand-th {{ font-weight: 500; font-size: .8em; color: #6b665c; margin-left: 4px; }}
.pfal-top .sub {{ margin: 2px 0 0; color: #6b665c; font-size: 14px; }}
.pfal-top .logos {{ display: inline-flex; align-items: center; gap: 12px; background: #ffffff; padding: 6px 10px;
                    border-radius: 10px; border: 1px solid #e3dfd4; }}
.pfal-top .logos img {{ height: 48px; width: auto; display: block; }}
</style>""", unsafe_allow_html=True)


def _data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + __import__("base64").b64encode(path.read_bytes()).decode()


st.markdown(f"""<div class="pfal-top">
  <div class="brand"><img class="brand-mark" src="{_data_uri(ASSETS / 'pfal.svg', 'image/svg+xml')}" alt="" width="48" height="48">
    <div><div class="name">SIS PFAL <span class="brand-th">ห้องปลูกพืชระบบปิด</span></div>
      <p class="sub">Digital twin ของห้องปลูกพืชด้วยแสงเทียม · โรงประลอง (Fab Lab) วิทยาลัยบูรณาการศาสตร์</p></div></div>
  <a class="logos" href="https://sis.ku.ac.th/" target="_blank" rel="noopener" title="วิทยาลัยบูรณาการศาสตร์ มหาวิทยาลัยเกษตรศาสตร์">
    <img src="{_data_uri(ASSETS / 'logo_ku.png', 'image/png')}" alt="มหาวิทยาลัยเกษตรศาสตร์ (Kasetsart University)">
    <img src="{_data_uri(ASSETS / 'logo_sis.png', 'image/png')}" alt="วิทยาลัยบูรณาการศาสตร์ (School of Integrated Science)"></a>
</div>""", unsafe_allow_html=True)
import plotly.io as pio
pio.templates["sis"] = pio.templates["plotly_white"]; pio.templates["sis"].layout.font.family = f"{FONT}, sans-serif"; pio.templates.default = "sis"
TZ = tb.TZ
PLOTLY = dict(use_container_width=True, config=dict(displaylogo=False, modeBarButtonsToAdd=["resetCameraDefault3d"], responsive=True))


# ---------------------------------------------------------------------------- cached resources
if st_cache_clear:
    st.cache_resource.clear(); st.cache_data.clear()


@st.cache_data(ttl=600, show_spinner=False, max_entries=2)
def store_version(_nonce: int = 0) -> str:
    """Every 10 min: if the SQL database (or, as a fallback, the `data` branch on GitHub) has a newer store than the
    local file, top the local copy up.
    Returns the manifest timestamp that identifies the store version (keys the twin cache)."""
    try:
        r = store.sync()
    except Exception as e:  # database and GitHub unreachable -> keep the local copy
        r = dict(action=f"error: {e}", local=store.local_manifest())
    st.session_state["store_status"] = r
    lm = r.get("local") or {}
    return lm.get("updated_at", "local")


@st.cache_resource(show_spinner="loading digital twin ...", max_entries=1)   # keep only the current twin (~75 MB)
def get_twin(version: str = "", pkg: str = "", cls_id: int = 0) -> DigitalTwin:
    """Cached per store version, package version AND class identity: after a redeploy / hot reload Streamlit gives us a
    new DigitalTwin class, and an instance built from the old class must not survive in the cache."""
    return DigitalTwin.load(start=HISTORY_START)


HISTORY_START = "2026-06-13"       # continuous operation from 13 June 2026; earlier samples are commissioning tests
STORE_VERSION = store_version()


@st.cache_data(ttl=600, show_spinner=False, max_entries=2)
def top_up(version: str, _nonce: int = 0):
    """Every 10 min: append what ThingsBoard has since the stored table ended (in memory), so History is never behind
    even when the 30-min GitHub Actions job is delayed."""
    try:
        return get_twin(version, NEEDS_PKG, id(DigitalTwin)).top_up()
    except Exception as e:
        return f"top-up failed: {e}"


TOP_UP = top_up(STORE_VERSION, int(time.time() // 600))


@st.cache_resource(ttl=60, show_spinner=False, max_entries=2)
def live_snapshot(_nonce: int):
    """Latest values from ThingsBoard (cached 60 s so many viewers do not hammer the server).
    cache_resource (no pickling): a TwinState built by a hot-reloaded module cannot be pickled by cache_data."""
    st_, table = get_twin(STORE_VERSION, NEEDS_PKG, id(DigitalTwin)).live()
    return st_, table


@st.cache_data(ttl=60, show_spinner=False, max_entries=10)
def recent_window(hours: int, _nonce: int):
    """Last `hours` hours straight from ThingsBoard (5-min averages, raw pump events) — same window as the dashboard."""
    return get_twin(STORE_VERSION, NEEDS_PKG, id(DigitalTwin)).recent(hours=hours, interval_min=5 if hours <= 24 else 15)


def ts_chart(df, cols, title, unit="", height=280, setpoints=None, step=False, subtitle=None):
    """title = short (must fit half/third of the page); subtitle = statistics, drawn smaller on a second line."""
    import plotly.graph_objects as go
    fig = go.Figure()
    for k in cols:
        if k not in df.columns or df[k].dropna().empty:
            continue
        lab = tb.channel_label(k[3:-2]).split(" — ")[1] if k.startswith("gw.") else k.split(".")[0] + " " + tb.KEY_LABELS.get(k.split(".")[1], k.split(".")[1])
        d = df[k].dropna()
        fig.add_scatter(x=d.index, y=d.values, mode="lines", name=lab, line_shape="hv" if step else "linear", connectgaps=False)
    for k, lab in (setpoints or {}).items():       # set-point: bold red so it stands out against the measured line
        if k in df.columns and df[k].dropna().size:
            sp = df[k].ffill().bfill(); last = sp.dropna().iloc[-1]        # set-points are published on change only -> hold across the window
            fig.add_scatter(x=df.index, y=sp.values, mode="lines", name=f"<b>{lab}</b>", line=dict(color="#c0392b", width=3, dash="dash"), line_shape="hv")
            fig.add_annotation(x=df.index[-1], y=last, text=f"<b>set {last:.2f}</b>", showarrow=False, xanchor="left", xshift=4, font=dict(color="#c0392b", size=12))
            fig.update_layout(margin=dict(r=70))
    # title on top, legend directly under it (above the plot) -> never collides with the x-axis date labels
    n = len(fig.data); rows = 1 if n <= 3 else 2 if n <= 6 else 3
    top = 34 + 22 * rows + (18 if subtitle else 0)             # title line + optional statistics line + legend rows
    fig.update_layout(title=dict(text=title, yref="container", y=1, yanchor="top", x=0, xanchor="left", font=dict(size=14), pad=dict(t=8)),
                      height=height, margin=dict(l=45, r=10, t=top, b=35), yaxis_title=unit, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", font=dict(size=10), itemwidth=30))
    if subtitle:   # statistics line between the title and the legend
        fig.add_annotation(text=subtitle, xref="paper", yref="paper", x=0, y=1.0, xanchor="left", yanchor="bottom", yshift=22 * rows + 2,
                           showarrow=False, font=dict(size=11, color="#555"))
    return fig


def dose_chart(df, dev, height=220):
    """ThingsBoard 'Dose stage' state chart: three lanes (A, B, pH) that go high while the pump runs."""
    import plotly.graph_objects as go
    fig = go.Figure(); lanes = (("pumpA", "part A", 2), ("pumpB", "part B", 1), ("pumpPH", "acid (pH)", 0))
    x0, x1 = df.index.min(), df.index.max()
    for k, lab, base in lanes:
        col = f"{dev}.{k}"
        if col in df.columns and df[col].dropna().size:
            d = df[col].dropna()          # events; hold the state from the window start to its end so a quiet pump still draws a flat lane
            xs = [x0] + list(d.index) + [x1]; ys = [d.iloc[0]] + list(d.values) + [d.iloc[-1]]
            fig.add_scatter(x=xs, y=[base + 0.8 * v for v in ys], mode="lines", name=lab, line_shape="hv")
    fig.update_xaxes(range=[x0, x1])
    fig.update_layout(title=dict(text=f"Dose stage — {dev}", yref="container", y=1, yanchor="top", x=0, xanchor="left", font=dict(size=14), pad=dict(t=8)),
                      height=height, margin=dict(l=45, r=10, t=78, b=35), yaxis=dict(tickvals=[0, 1, 2], ticktext=["acid", "B", "A"], range=[-0.2, 3]),
                      hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", font=dict(size=10)))
    return fig


def stat_line(d, nd=2):
    d = d.dropna(); return f"now {d.iloc[-1]:.{nd}f} · min {d.min():.{nd}f} · avg {d.mean():.{nd}f} · max {d.max():.{nd}f}" if d.size else "no data"


@st.cache_data(show_spinner=False, max_entries=2)
def availability_figure(version: str):
    """Per-device data coverage per day (share of 10-min bins with at least one value) -> shows the gaps at a glance."""
    import plotly.graph_objects as go
    w = get_twin(version, NEEDS_PKG, id(DigitalTwin)).data
    w = w[[c for c in w.columns if c.split(".", 1)[1] not in tb.CONTROL_KEYS]]     # measured keys only (control keys are forward-filled)
    av = tb.availability(w, "1D")
    order = [d for d in ("gw", "gc1", "gc2", "co2") if d in av.columns]
    label = {"gw": "gw — XY-MD02 T/RH ×5", "gc1": "gc1 — growing controller", "gc2": "gc2 — nursery-2 controller", "co2": "co2 — CO₂ controller"}
    fig = go.Figure(go.Heatmap(z=av[order].T.values * 100, x=av.index, y=[label[d] for d in order], colorscale=[[0, "#f2f2f2"], [0.01, "#fde0c8"], [1, "#1f6f6b"]],
                               zmin=0, zmax=100, colorbar=dict(title="% of day", thickness=12, len=0.9), hovertemplate="%{y}<br>%{x|%d %b %Y}: %{z:.0f} % of the day<extra></extra>"))
    fig.update_layout(height=190, margin=dict(l=10, r=10, t=10, b=30), yaxis=dict(autorange="reversed"), font=dict(size=11))
    return fig


@st.cache_data(show_spinner=False, max_entries=4)
def full_store_bytes(version: str, fmt: str) -> bytes:
    """Whole 10-min table (from the first sample, not only the shown period) as CSV or Parquet (cached per store version)."""
    import io as _io
    w = pd.read_parquet(store.WIDE)
    if fmt == "parquet":
        b = _io.BytesIO(); w.to_parquet(b); return b.getvalue()
    return w.to_csv(float_format="%.3f").encode()


@st.cache_data(show_spinner="reading raw samples from the database ...", max_entries=1)
def raw_store_bytes(version: str) -> bytes:
    """All raw samples (ts, device, key, value) as Parquet, read from the SQL database on request."""
    import io as _io
    from pfal_twin import dbstore
    from pfal_twin.sqlapi import SqlApi
    b = _io.BytesIO(); dbstore.pull_long(SqlApi.from_secrets()).to_parquet(b); return b.getvalue()


@st.cache_resource(show_spinner="rendering point cloud ...", max_entries=4)
def cloud_figure(n: int, open_up: bool, version: str):
    return get_twin(version, NEEDS_PKG, id(DigitalTwin)).cloud_figure(n=n, height=680, open_up=open_up)


@st.cache_resource(show_spinner="rendering flow animation ...", max_entries=1)
def flow_animation(version: str):
    return get_twin(version, NEEDS_PKG, id(DigitalTwin)).flow_animation()


@st.cache_data(show_spinner="rendering layout ...", max_entries=8)
def static_png(kind: str, version: str) -> bytes:
    """The matplotlib drawings as PNG, rendered once (st.pyplot would redraw them on every rerun)."""
    import io as _io
    b = _io.BytesIO(); static_figure(kind, version).savefig(b, format="png", dpi=150, bbox_inches="tight"); return b.getvalue()


@st.cache_resource(show_spinner="rendering layout ...", max_entries=5)
def static_figure(kind: str, version: str = ""):   # keyed by store version: the heat-map changes with the data
    tw = get_twin(STORE_VERSION, NEEDS_PKG, id(DigitalTwin))
    return {"layout": tw.layout_figure, "water": tw.water_plan, "flow": tw.flow_diagram, "corner": tw.corner_detail, "heatmap": tw.heatmap}[kind]()


@st.cache_data(ttl=600, show_spinner=False, max_entries=2)
def planting_rounds(_nonce: int) -> pd.DataFrame:
    """Planting rounds of tiers 2-5 from the public sheet (re-read every 10 min)."""
    return planting.load()


@st.cache_resource(ttl=600, show_spinner=False, max_entries=2)
def plant_meshes(_nonce: int, day: str) -> list:
    """3-D plants of tiers 2-5 for `day` (one mesh per crop), rebuilt when the planting sheet is re-read."""
    holes = M.hole_positions(tw.model, M.HoleLayout())
    return plants3d.plant_traces(plants3d.plant_table(planting_rounds(_nonce), holes, day))


def add_plants(fig) -> bool:
    """Add today's plants to a 3-D twin figure; fade the rack's temperature box so they show through. False if unavailable."""
    try:
        meshes = plant_meshes(int(time.time() // 600), str(pd.Timestamp.now(tz=TZ).date()))
    except Exception:
        return False
    fig.add_traces(meshes)
    for t in fig.data:
        if t.type == "mesh3d" and t.opacity == 0.55:
            t.opacity = 0.15
    return True


CROP_COLOURS = ["#cfe3c4", "#f3d9b1", "#c9dcef", "#ead1e4", "#f1e7a8", "#cde9e3", "#e4d6c3", "#d8d3ef", "#f2cfc4", "#dfe7c0"]


def tray_map_html(grid: pd.DataFrame) -> str:
    """Tiers 5 (top) to 2 as rows, trays 1 (door) to 10 as columns; one colour per crop, red = two blocks on one tray."""
    crops = sorted({c for c in grid.loc[grid.n == 1, "crop"]})
    colour = {c: CROP_COLOURS[i % len(CROP_COLOURS)] for i, c in enumerate(crops)}
    cell = "padding:6px 4px;border:1px solid #e3dfd4;text-align:center;font-size:12px;line-height:1.3;min-width:76px"
    head = "".join(f"<th style='{cell};background:#f7f6f2;font-weight:600'>{t}</th>" for t in range(1, planting.TRAYS + 1))
    body = ""
    for tier in sorted(planting.TIERS, reverse=True):
        tds = ""
        for _, r in grid[grid.tier == tier].iterrows():
            if r.n == 0:
                tds += f"<td style='{cell};background:#ffffff;color:#a19c90'>ว่าง</td>"
                continue
            left = "" if r.days_left is None else ("ถึงกำหนดเก็บ" if r.days_left <= 0 else f"อีก {r.days_left:.0f} วัน")
            if r.n > 1:
                tds += f"<td style='{cell};background:#f4cccc;border:2px solid #c0392b' title='{r['round']}'><b>⚠ ข้อมูลชนกัน</b><br>{r.crop}</td>"
            else:
                tds += f"<td style='{cell};background:{colour[r.crop]}' title='{r['round']}'><b>{r.crop}</b><br><span style='color:#6b665c'>{left}</span></td>"
        body += f"<tr><th style='{cell};background:#f7f6f2;font-weight:600'>ชั้น {tier}</th>{tds}</tr>"
    return (f"<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%'>"
            f"<tr><th style='{cell};background:#f7f6f2'>ชั้น \\ ถาด</th>{head}</tr>{body}</table>"
            "<div style='display:flex;justify-content:space-between;font-size:12px;color:#6b665c;padding:2px 2px 0 80px'>"
            "<span>← ฝั่งประตู · door</span><span>ฝั่งด้านใน · far side →</span></div></div>")


def planting_section():
    st.markdown("#### ผังชั้นปลูกวันนี้ · what is growing (tiers 2–5)")
    try:
        rounds = planting_rounds(int(time.time() // 600))
    except Exception as e:
        st.info(f"ยังอ่านข้อมูลรอบปลูกไม่ได้ · planting sheet unavailable ({str(e)[:120]})")
        return
    grid = planting.tray_map(rounds)
    used = int((grid.n > 0).sum()); total = len(grid)
    m = st.columns(3)
    m[0].metric("ถาดที่ใช้ · trays in use", f"{used} / {total}")
    m[1].metric("หลุมที่ใช้ · holes in use", f"{used * planting.HOLES_PER_TRAY} / {total * planting.HOLES_PER_TRAY}")
    m[2].metric("ชนิดพืช · crops", len({c for cs in grid.crop if cs for c in cs.split(" / ")}))
    st.markdown(tray_map_html(grid), unsafe_allow_html=True)
    st.caption(f"จากบันทึกรอบปลูกของทีม ([PFAL รอบปลูก]({planting.SHEET_URL})) อัปเดตทุก 10 นาที · ชั้น 1 (เพาะกล้า) ไม่แสดง · "
               "1 ถาด = 18 หลุม (6 × 3), ชั้นละ 10 ถาด · วันเก็บเป็นค่าคาดตามชนิดพืช")


def fmt(v, nd=1, unit=""):
    return "—" if v is None or v != v else f"{v:.{nd}f}{unit}"


def age_text(td: pd.Timedelta) -> str:
    s = int(td.total_seconds())
    return f"{s} s" if s < 90 else f"{s // 60} min" if s < 5400 else f"{s / 3600:.1f} h" if s < 172800 else f"{s / 86400:.1f} d"


def device_note(dev: str, last=None) -> str:
    """'🔧 <note> since <date>' for devices in DEVICE_STATUS, else ''. `last` = the device's latest data; data newer than
    the day after `since` means the device is back, so the note no longer applies."""
    d = DEVICE_STATUS.get(dev)
    if not d:
        return ""
    since = pd.Timestamp(d["since"], tz=TZ)
    if last is not None and last == last and pd.Timestamp(last) > since + pd.Timedelta("1D"):
        return ""
    return f"🔧 {d['en']} ({d['th']}) since {since:%d %b %Y}"


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
        now = pd.Timestamp.now(tz=TZ)
        st.caption("last message per device: " + " · ".join(f"**{d}** {device_note(d, now - a) or age_text(a) + ' ago'}" for d, a in ages.items()))


# ---------------------------------------------------------------------------- sidebar
tw = get_twin(STORE_VERSION, NEEDS_PKG, id(DigitalTwin))
st.sidebar.markdown(f"**{PROJECT['name']}**  \n<small>{PROJECT['th']}</small>", unsafe_allow_html=True)
PAGES = {"Overview": "ภาพรวม (Overview)", "Live": "ข้อมูลสด (Live)", "History": "ข้อมูลย้อนหลัง (History)",
         "Layout & water": "ผังห้องและระบบน้ำ (Layout & water)", "What-if": "จำลองสถานการณ์ (What-if)"}
# closed to the public for now (code kept): remove a name to show it again
HIDDEN_PAGES = {"Layout & water"}
SHOW_ALL_KEYS = False   # Live page: raw table of every ThingsBoard key (an engineering view; charts and cards show the values)
PAGES = {k: v for k, v in PAGES.items() if k not in HIDDEN_PAGES}
_label = st.sidebar.radio("Page", list(PAGES.values()), label_visibility="collapsed")
page = {v: k for k, v in PAGES.items()}[_label]
if ON_DASHBOARD:                                     # …/dashboard (the TV bookmarks this)
    page = "Dashboard"
elif st.query_params.get("page") == "dashboard":    # an old ?page=dashboard link (the way in now: a button on Live)
    st.switch_page(_DASH)
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
    store_version.clear(); top_up.clear(); static_figure.clear(); static_png.clear(); st.rerun()
with st.sidebar.expander("about"):
    st.code(tw.summary(), language=None)
    st.markdown(f"{PROJECT['en']}  \nSIS PFAL = plant factory with artificial lighting at the School of Integrated Science.  \n"
                "Source: ThingsBoard public dashboard *Vertical Smart Farming* (cat-smartgrow.com). Geometry from the LiDAR scan of 2026-09-13.")
SPONSOR_URL = "https://www.civicagrotech.com/"
_sponsor_b64 = __import__("base64").b64encode((ASSETS / "civic_agrotech_logo.png").read_bytes()).decode()


def sponsor_logo(width: int) -> str:
    """CIVIC Agrotech logo linking to their site (st.image cannot carry a link)."""
    return (f'<a href="{SPONSOR_URL}" target="_blank" title="CIVIC Agrotech">'
            f'<img src="data:image/png;base64,{_sponsor_b64}" width="{width}" alt="CIVIC Agrotech"></a>')


st.sidebar.caption("ผู้สนับสนุน (Sponsor)")
st.sidebar.markdown(sponsor_logo(60) + f'  \n<small><a href="{SPONSOR_URL}" target="_blank">CIVIC Agrotech</a></small>', unsafe_allow_html=True)

# ============================================================================ OVERVIEW
if page == "Overview":
    PH = ASSETS / "photos"
    st.title("SIS PFAL Digital Twin")
    st.markdown(f"**{PROJECT['th']}**  \n{PROJECT['en']}")
    st.image(str(PH / "IMG_2413.jpg"), caption="SIS PFAL in production — five tiers of leafy greens under LED bars (growing stage on tiers 2–5, nursery on tier 1)", width="stretch")
    c1, c2, c3 = st.columns(3)
    c1.image(str(PH / "IMG_2518.jpg"), caption="PFAL @ SIS KU — School of Integrated Science, Kasetsart University (13 Sep 2026)", width="stretch")
    c2.image(str(PH / "IMG_2519.jpg"), caption="Front of the unit: anteroom entrance beside the SIS KU coffee corner", width="stretch")
    c3.image(str(PH / "IMG_2520.jpg"), caption="Inside: one 5-tier rack, 5.4 × 1.0 m, in a 7.1 × 3.0 × 2.6 m room", width="stretch")

    st.markdown("""
#### แอปนี้ทำอะไรได้ · What this app does
Digital twin = แบบจำลองห้องปลูกจริง (รูปทรงจาก LiDAR) ที่ผูกกับข้อมูลเซ็นเซอร์จริงจาก ThingsBoard — ดูสภาพห้อง **ตอนนี้**, **ย้อนหลัง** และ **ลองสถานการณ์** ได้จากที่เดียว
""")
    cards = st.columns(4 - ("Layout & water" in HIDDEN_PAGES))
    k1, k2, k4 = cards[0], cards[1], cards[-1]
    k3 = cards[2] if len(cards) == 4 else None
    k1.markdown("**📡 Live**  \nกราฟแบบ dashboard (T/RH 5 จุด, CO₂, EC/pH + set-point, การจ่ายปุ๋ย) + twin 3-D ระบายสีตามค่าจริง รีเฟรชทุก 60 วิ  \n*Real-time charts and the 3-D twin coloured by live readings*")
    k2.markdown("**🕓 History**  \nเลื่อนเวลาดูห้อง ณ ช่วงใดก็ได้ตั้งแต่ ธ.ค. 2025, กราฟ, KPI, เหตุการณ์ผิดปกติ, ดาวน์โหลด CSV  \n*Time slider, KPIs, events and CSV export since Dec 2025*")
    if k3: k3.markdown("**🗺️ Layout & water**  \nผัง as-built จาก point cloud, ระบบท่อน้ำ/ปุ๋ย, process flow และแอนิเมชันการไหล  \n*As-built layout, pipework and flow animation*")
    k4.markdown("**🌱 What-if**  \nเลือกสัดส่วนผักบน 720 หลุม (ชั้น 2–5) ดูผังรายหลุม 3-D + ผลผลิต/รายได้/แสงที่ต้องการ, สถานการณ์แสง–พลังงาน  \n*Crop-mix and light/energy scenarios*")

    def device_status_text() -> str:
        """Last data per device from the store; devices in DEVICE_STATUS carry their note."""
        out = []
        measured = {"gw": [c for c in tw.data.columns if c.startswith("gw.xy_md_")], "gc1": ["gc1.ec", "gc1.ph"],
                    "gc2": ["gc2.ec", "gc2.ph"], "co2": ["co2.CO2", "co2.temperature"]}   # not the forward-filled set-points
        for dev in ("gw", "gc1", "gc2", "co2"):
            cols = [c for c in measured[dev] if c in tw.data.columns]
            last = tw.data[cols].dropna(how="all").index.max() if cols else None
            txt = f"last data {last:%d %b %Y}" if last is not None and last == last else "no data"
            out.append(f"**{dev}** {device_note(dev, last) or txt}")
        return " · ".join(out)

    st.markdown("#### ข้อมูลที่ใช้ · Data behind the twin")
    R_, K_ = tw.model["room"], tw.model["rack"]
    st.markdown(f"""
| | |
|---|---|
| **ห้อง · room** | {R_['L']:.2f} × {R_['W']:.2f} × {R_['H']:.2f} m — from 2 LiDAR scans (13 Sep 2026) |
| **ชั้นปลูก · rack** | {K_['length']:.2f} × {K_['width']:.2f} m, {len(K_['tiers'])} tiers · 720 planting holes on tiers 2–5 (6 × 30 per tier) · nursery 2 (tier 1): 126 holes (6 × 21) |
| **เซ็นเซอร์ / อุปกรณ์ · sensors / equipment** | {len(tw.sensors)} sensor units (5 × XY-MD02 T/RH, CO₂ controller, 2 grow controllers) · {len(tw.equipment)} mapped items |
| **ข้อมูล IoT · records** | {len(tw.data):,} × 10-min bins, {d0:%d %b %Y} → {d1:%d %b %Y} (refreshed every 30 min) |
| **สถานะอุปกรณ์ · device status** | {device_status_text()} |
| **แหล่งข้อมูล · source** | ThingsBoard dashboard *Vertical Smart Farming* — cat-smartgrow.com (Civic Agrotech) |
""")
    st.caption("Model parameters of the what-if layer are schematic until calibrated with PPFD and harvest measurements (LED: 30 × 42 W lamps per growing tier). Photos: site survey 13 Sep 2026.")

# ============================================================================ LIVE
elif page == "Dashboard":
    # TV screen, 1920 x 1080, no scrolling. Header: name + live clock + logos. Centre: 3-D twin with plants over the tray
    # map. Left: the air in the room. Right: nutrient solution and light. Each side ends with a 24-h trend.
    st.markdown("""<style>
    section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"],
    [data-testid="stToolbar"], footer, .pfal-top {display: none !important;}
    .block-container {padding: 0.2rem 1.4rem 0 1.4rem !important; max-width: 100% !important;}
    /* screens >= 1000 px: lay the page out at 1920 px from the start (charts are drawn at that width); the script in
       tv_controls() then only scales it (CSS transform) to fit the screen */
    @media (min-width: 1000px) {
      .block-container {width: 1920px !important; max-width: 1920px !important; flex: none !important;
                        align-self: flex-start !important; transform-origin: top left;}
      [data-testid="stMain"] {overflow: hidden !important;}
    }
    .stApp [data-testid="stVerticalBlock"] {gap: 0.45rem;}
    .tv-head {display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; padding: 2px 0 10px;
              border-bottom: 1px solid #e3dfd4; margin-bottom: 6px;}
    .tv-head .brand {display: flex; align-items: center; gap: 14px;}
    .tv-head .brand img {border-radius: 12px;}
    .tv-head .name {font-size: 30px; font-weight: 700; color: #22201c; line-height: 1.1;}
    .tv-head .name span {font-size: 20px; font-weight: 500; color: #6b665c; margin-left: 8px;}
    .tv-head .sub {font-size: 14px; color: #6b665c;}
    .tv-head .clock {text-align: center;}
    .tv-head .clock .t {font-size: 38px; font-weight: 700; color: #22201c; line-height: 1;}
    .tv-head .clock .d {font-size: 14px; color: #6b665c;}
    .tv-head .live {display: inline-block; font-size: 13px; font-weight: 600; color: #1f6b67; background: #e4f1ee;
                    border-radius: 999px; padding: 2px 10px; margin-bottom: 4px;}
    .tv-head .live.stale {color: #9a6a12; background: #f8ecd2;}
    .tv-head .logos {justify-self: end; display: flex; gap: 14px; align-items: center; background: #fff; padding: 8px 14px;
                     border-radius: 12px; border: 1px solid #e3dfd4;}
    .tv-head .logos img {height: 56px;}
    .tv-group {font-size: 15px; font-weight: 700; letter-spacing: .02em; padding: 0 2px 2px; display: flex; gap: 8px; align-items: center;}
    .tv-group i {display: inline-block; width: 10px; height: 10px; border-radius: 3px;}
    .tv-tile {background: #fff; border: 1px solid #e3dfd4; border-left: 6px solid var(--acc); border-radius: 12px;
              padding: 7px 16px 7px 14px; margin-bottom: 7px; position: relative;}
    .tv-tile .l {font-size: 15px; color: #6b665c;}
    .tv-tile .v {font-size: 46px; font-weight: 700; color: #22201c; line-height: 1.08; white-space: nowrap;}
    .tv-tile .v small {font-size: 20px; font-weight: 500; color: #6b665c; margin-left: 5px;}
        .tv-tile .s {font-size: 14px; color: #6b665c;}
    .tv-tile .dot {position: absolute; top: 12px; right: 14px; font-size: 13px; font-weight: 600; padding: 1px 9px; border-radius: 999px;}
    .tv-tile .dot.ok {color: #2e7d4f; background: #e3f2e8;}
    .tv-tile .dot.warn {color: #9a6a12; background: #f8ecd2;}
    .tv-tile.off .v {color: #a19c90; font-size: 26px;}
    .tv-foot {font-size: 13px; color: #8a857a;}
    </style>""", unsafe_allow_html=True)
    AIR, WATER, LIGHT = "#1f6b67", "#2f6fa3", "#c98a1b"     # group accents: air, nutrient solution, light & plants
    # Chart widths are fixed for the 1920-px layout (columns 1 : 2.65 : 1).
    # With use_container_width Streamlit re-measures on every refresh - and measures the *scaled* box, so charts shrank.
    SIDE_W, CENTRE_W = 374, 1040   # a little under the measured column widths (382, 1047): wider would be clamped
    LIM = tw.limits

    def tv_controls():
        """Full-screen button + fit-to-screen: the page is laid out for 1920 x 1080 and scaled (CSS transform) to any
        screen at least 1000 px wide, so a 4K TV, a 1080p TV and a laptop all show the whole page without scrolling;
        narrower screens (phones) get the normal stacked layout. Runs in a component iframe and acts on the app page."""
        import streamlit.components.v1 as components
        components.html("""
<div style="display:flex;gap:8px;justify-content:flex-start;align-items:center;font:13px 'IBM Plex Sans Thai',sans-serif">
  <button id="fs" style="font:inherit;padding:4px 12px;border:1px solid #e3dfd4;border-radius:8px;background:#fff;cursor:pointer">⛶ เต็มจอ · full screen</button>
  <span id="hint" style="color:#6b665c"></span>
</div>
<script>
const P = window.parent, D = P.document, W0 = 1920, H0 = 1080;
function fit() {            // the 1920-px layout itself comes from the page CSS; here only the scale and centring
  const bc = D.querySelector('.block-container');
  if (!bc) return;
  const w = P.innerWidth, h = P.innerHeight;
  if (w < 1000) { bc.style.removeProperty('transform'); bc.style.removeProperty('margin-left'); return; }   // phones: stacked page
  const k = Math.min(w / W0, h / H0);
  bc.style.setProperty('transform', 'scale(' + k + ')', 'important');
  bc.style.setProperty('margin-left', Math.max(0, (w - W0 * k) / 2) + 'px', 'important');
}
P.addEventListener('resize', fit); setInterval(fit, 1500); fit();
// leaving the dashboard (the exit button switches page and removes this frame): undo the scaling, leave full screen
window.addEventListener('pagehide', () => {
  const bc = D.querySelector('.block-container');
  if (bc) { bc.style.removeProperty('transform'); bc.style.removeProperty('margin-left'); }
  P.removeEventListener('resize', fit);
  if (D.fullscreenElement) D.exitFullscreen().catch(() => {});
});
const btn = document.getElementById('fs'), hint = document.getElementById('hint');
function label() { btn.textContent = D.fullscreenElement ? '⤢ ออกจากเต็มจอ' : '⛶ เต็มจอ · full screen'; }
D.addEventListener('fullscreenchange', () => { label(); setTimeout(fit, 200); });
btn.onclick = async () => {
  try {
    if (D.fullscreenElement) await D.exitFullscreen(); else await D.documentElement.requestFullscreen();
  } catch (e) { hint.textContent = 'เบราว์เซอร์ไม่อนุญาต: กด F11 แทน'; }
};
</script>""", height=34)

    def tile(label, value, unit="", sub="", acc=AIR, ok=None, off=False):
        """One reading: label, big value, unit, small line; ok=True/False adds a 'ปกติ' / 'ควรตรวจ' badge."""
        badge = "" if ok is None or off else (f"<span class='dot ok'>ปกติ</span>" if ok else f"<span class='dot warn'>ควรตรวจ</span>")
        return (f"<div class='tv-tile{' off' if off else ''}' style='--acc:{acc}'>{badge}<div class='l'>{label}</div>"
                f"<div class='v'>{value if not off else 'ไม่มีสัญญาณ'}<small>{'' if off else unit}</small></div><div class='s'>{sub}</div></div>")

    def group(title, acc):
        return f"<div class='tv-group' style='color:{acc}'><i style='background:{acc}'></i>{title}</div>"

    def dash_state():
        try:
            st_, table = live_snapshot(int(time.time() // 60))
            return st_, table["value"], table.groupby("device")["age"].min().to_dict()
        except Exception:   # ThingsBoard down -> last stored bin
            return tw.state(d1), tw.data.loc[tw.state(d1).time], {}

    def framed_chart(fig, height: int, static: bool = True):
        """A chart in its own frame. st.plotly_chart measures its width from the *scaled* page (on a refresh, or when it is
        drawn after the scaling) and shrank; inside a frame plotly measures the frame, laid out at the unscaled size."""
        import streamlit.components.v1 as components
        components.html('<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;600&display=swap" rel="stylesheet">'
                        '<style>body{margin:0;background:#fff}</style>'
                        + fig.to_html(full_html=False, include_plotlyjs="cdn", config=dict(displayModeBar=False, staticPlot=static)),
                        height=height + 4)

    def trend(lines: dict, title: str, unit: str, height: int, ref: float | None = None, width: int = SIDE_W):
        """Compact 24-h trend for the TV: a few thick lines, legend on top, optional dashed reference (set-point)."""
        import plotly.graph_objects as go
        fig = go.Figure()
        for (name, ser), col in zip(lines.items(), ("#1f6b67", "#c98a1b", "#2f6fa3")):
            ser = ser.dropna()
            if len(ser):
                fig.add_scatter(x=ser.index, y=ser.values, mode="lines", name=name, line=dict(color=col, width=2.6))
        if ref == ref and ref is not None:
            fig.add_hline(y=ref, line=dict(color="#c0392b", width=2, dash="dash"), annotation_text=f"set {ref:.2f}",
                          annotation_position="top left", annotation_font=dict(color="#c0392b", size=12))
        fig.update_layout(title=dict(text=title, x=0, font=dict(size=15)), height=height, width=width, autosize=False,
                          margin=dict(l=40, r=10, t=56, b=28),
                          legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(size=12)), yaxis_title=unit,
                          paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", xaxis=dict(tickformat="%H:%M", nticks=7))
        return fig

    @st.fragment(run_every="60s")
    def dash_header():
        state, _, ages = dash_state()
        now = pd.Timestamp.now(tz=TZ)
        fresh = bool(ages) and min(ages.values()) < pd.Timedelta("15min")
        st.markdown(f"""<div class="tv-head">
  <div class="brand"><img src="{_data_uri(ASSETS / 'pfal.svg', 'image/svg+xml')}" width="62" height="62" alt="">
    <div><div class="name">SIS PFAL<span>ห้องปลูกพืชระบบปิดด้วยแสงเทียม</span></div>
      <div class="sub">Digital twin · โรงประลอง (Fab Lab) วิทยาลัยบูรณาการศาสตร์ มหาวิทยาลัยเกษตรศาสตร์</div></div></div>
  <div class="clock"><span class="live{'' if fresh else ' stale'}">{'● LIVE' if fresh else '● ข้อมูลล่าสุด'}</span>
    <div class="t">{now:%H:%M}</div><div class="d">{now:%d %b %Y} · ค่าวัด {state.time:%H:%M}</div></div>
  <div class="logos"><img src="{_data_uri(ASSETS / 'logo_ku.png', 'image/png')}" alt="KU"><img src="{_data_uri(ASSETS / 'logo_sis.png', 'image/png')}" alt="SIS"></div>
</div>""", unsafe_allow_html=True)
    dash_header()

    left, centre, right = st.columns([1, 2.65, 1], gap="medium")

    def side_data():
        """Latest state, value getter, 'device offline' test and the last 24 h (all cached, shared by both sides)."""
        state, row, ages = dash_state()
        g = lambda k: float(row.get(k, float("nan"))) if row is not None else float("nan")
        now = pd.Timestamp.now(tz=TZ)
        off = lambda d: bool(device_note(d, now - ages[d])) if d in ages else False
        try:
            R = recent_window(24, int(time.time() // 60))
        except Exception:
            R = pd.DataFrame()
        return state, g, off, R

    @st.fragment(run_every="60s")
    def dash_left():
        state, g, off, R = side_data()
        T, RH, V, CO2 = state.room_T, state.room_RH, state.room_VPD, state.co2
        st.markdown(group("อากาศในห้อง · AIR", AIR) +
                    tile("อุณหภูมิห้อง · temperature", fmt(T, 1), "°C", "เฉลี่ย 3 จุดในห้องปลูก", AIR, T == T and T <= LIM["T_max"], off("gw")) +
                    tile("ความชื้นสัมพัทธ์ · humidity", fmt(RH, 0), "%", f"สูงสุดที่เหมาะ {LIM['RH_max']:.0f} %", AIR, RH == RH and RH <= LIM["RH_max"], off("gw")) +
                    tile("VPD · ความต่างแรงดันไอน้ำ", fmt(V, 2), "kPa", f"ช่วงเหมาะ {LIM['VPD_lo']}–{LIM['VPD_hi']} kPa", AIR,
                         V == V and LIM["VPD_lo"] <= V <= LIM["VPD_hi"], off("gw")) +
                    tile("CO₂", fmt(CO2, 0), "ppm", "ในห้องปลูก", AIR, None, off("co2")) +
                    tile("ภายนอก · ห้องเตรียม", f"{fmt(state.ch_T['xy_md_24'], 1)}<small>°C</small> · {fmt(state.ch_T['xy_md_20'], 1)}", "°C",
                         f"RH {fmt(state.ch_RH['xy_md_24'], 0)} % · {fmt(state.ch_RH['xy_md_20'], 0)} %", AIR, None, off("gw")),
                    unsafe_allow_html=True)
        if not R.empty:
            walls = [c for c in (f"gw.xy_md_{a}_t" for a in (21, 22, 23)) if c in R]
            framed_chart(trend({"ในห้อง": R[walls].mean(axis=1) if walls else pd.Series(dtype=float),
                                "ภายนอก": R.get("gw.xy_md_24_t", pd.Series(dtype=float))}, "อุณหภูมิ 24 ชม.", "°C", 232), 232)
    @st.fragment(run_every="60s")
    def dash_right():
        state, g, off, R = side_data()
        ecg, phg, ecn, phn = state.ec["growing (gc1)"], state.ph["growing (gc1)"], state.ec["nursery-2 (gc2)"], state.ph["nursery-2 (gc2)"]
        ecg_sp, ecn_sp = g("gc1.ecSetPoint"), g("gc2.ecSetPoint")
        led = "—" if state.led != state.led else ("เปิด" if state.led >= 0.5 else "ปิด")
        try:
            grid = planting.tray_map(planting_rounds(int(time.time() // 600)))
            used = int((grid.n > 0).sum()); trays_v, trays_s = f"{used}<small>/ {len(grid)} ถาด</small>", f"{used * planting.HOLES_PER_TRAY} ต้น บนชั้น 2–5"
        except Exception:
            trays_v, trays_s = "—", "ไม่มีข้อมูลรอบปลูก"
        st.markdown(group("น้ำ ปุ๋ย และไฟ · WATER & LIGHT", WATER) +
                    tile("EC ชั้นปลูก · growing", fmt(ecg, 2), "mS/cm", f"ค่าตั้ง {fmt(ecg_sp, 2)}", WATER,
                         ecg == ecg and ecg_sp == ecg_sp and abs(ecg - ecg_sp) <= LIM["EC_tol"], off("gc1")) +
                    tile("pH ชั้นปลูก", fmt(phg, 2), "", f"ค่าตั้ง {fmt(g('gc1.pHSetPoint'), 2)}", WATER,
                         phg == phg and LIM["pH_lo"] <= phg <= LIM["pH_hi"], off("gc1")) +
                    tile("ชั้นอนุบาล · EC / pH", f"{fmt(ecn, 2)}<small>mS/cm</small> · {fmt(phn, 2)}", "",
                         f"ค่าตั้ง {fmt(ecn_sp, 2)} / {fmt(g('gc2.pHSetPoint'), 2)}", WATER,
                         ecn == ecn and phn == phn and abs(ecn - ecn_sp) <= LIM["EC_tol"] and LIM["pH_lo"] <= phn <= LIM["pH_hi"], off("gc2")) +
                    tile("ไฟ LED · ปั๊มน้ำ", f"{led}<small>ไฟ</small> · {'ทำงาน' if state.pump_on['gc1'] else 'หยุด'}", "",
                         f"วันปลูกที่ {fmt(state.plant_day['growing (gc1)'], 0)} ตามตัวควบคุม", LIGHT, None, off("gc1")) +
                    tile("ต้นพืชตอนนี้ · plants", trays_v, "", trays_s, LIGHT),
                    unsafe_allow_html=True)
        if not R.empty:
            co2 = R.get("co2.CO2", pd.Series(dtype=float))
            if co2.notna().any():
                fig = trend({"CO₂": co2}, "CO₂ 24 ชม.", "ppm", 232)
            else:
                fig = trend({"EC ชั้นปลูก": R.get("gc1.ec", pd.Series(dtype=float))}, "EC ชั้นปลูก 24 ชม.", "mS/cm", 232, ecg_sp)
            framed_chart(fig, 232)

    with left:
        dash_left()
    with right:
        dash_right()

    with centre:
        @st.fragment(run_every="600s")
        def dash_twin():
            state, _, _ = dash_state()
            fig = tw.figure_3d(var="T", st=state, cmin=20, cmax=35, height=660, title_prefix="", public=True)
            add_plants(fig)
            fig.update_layout(title=dict(text="ห้องปลูก 3 มิติ · ต้นพืชตามบันทึกรอบปลูก · สีชั้นปลูก = อุณหภูมิห้อง", x=0.5, xanchor="center",
                                         font=dict(size=17)),
                              showlegend=False, margin=dict(l=0, r=0, t=40, b=0), width=CENTRE_W, autosize=False,
                              scene_camera=dict(eye=dict(x=0.62, y=-0.95, z=0.48), center=dict(x=0.05, y=0, z=-0.12)))
            framed_chart(fig, 660, static=False)   # the 3-D view can still be turned with the mouse
            try:
                grid = planting.tray_map(planting_rounds(int(time.time() // 600)))
                st.markdown(tray_map_html(grid), unsafe_allow_html=True)
            except Exception as e:
                st.caption(f"planting sheet unavailable ({str(e)[:80]})")
        dash_twin()

    c_fs, c_exit, c_note = st.columns([1.2, 1.2, 9.6])
    with c_fs:
        tv_controls()
    if c_exit.button("ออกจากโหมดจอ", type="tertiary", key="tv_exit"):
        st.switch_page(_SITE)
    c_note.markdown("<div class='tv-foot' style='text-align:right;padding-top:6px'>ข้อมูลจากเซ็นเซอร์ IoT ในห้องปลูก (ThingsBoard) · "
                    "ต้นพืช 3 มิติเป็นภาพประกอบตามบันทึกรอบปลูก · sis-pfal-digital-twin.streamlit.app</div>", unsafe_allow_html=True)
    st.stop()   # no footer: the screen ends here

elif page == "Live":
    top = st.columns([2.2, 1, 1, 1.2, 1.5])
    top[0].title("ข้อมูลสด (Live)")
    top[4].page_link(_DASH, label="จอแสดงผล · TV dashboard", icon=":material/tv:", help="หน้าจอเดียวสำหรับขึ้นจอ TV (มีปุ่มเต็มจอ) — /dashboard")
    auto = top[1].toggle("auto-refresh 60 s", value=True)
    if top[2].button("refresh now"):
        live_snapshot.clear(); recent_window.clear()
    hours = top[3].selectbox("window", [6, 12, 24, 72, 168], index=2, format_func=lambda h: f"{h} h" if h < 48 else f"{h // 24} days")

    planting_section()   # top of the page, outside the 60-s fragment: the sheet is re-read every 10 min

    def current_state():
        """Latest TwinState and key table from ThingsBoard, or the last stored bin when it is unreachable."""
        try:
            return live_snapshot(int(time.time() // 60))
        except Exception as e:  # network / ThingsBoard down -> fall back to the last stored bin
            st.error(f"ThingsBoard not reachable ({e}); showing the last stored 10-min bin instead.")
            return tw.state(d1), None

    # the twin carries ~700 plant meshes (a few MB): its own fragment, redrawn every 10 min instead of every minute
    @st.fragment(run_every="600s" if auto else None)
    def twin_view():
        state, _ = current_state()
        st.markdown("#### 3-D twin — coloured by the latest readings")
        c = st.columns([3, 1])
        with c[0]:
            var = colour_picker("var_live")
        show_plants = c[1].toggle("แสดงต้นพืช · plants", value=True)
        lo, hi = RANGES[var]
        fig = tw.figure_3d(var=var, st=state, cmin=lo, cmax=hi, height=620, title_prefix="LIVE ", public=not extended)
        if show_plants:
            if add_plants(fig):
                fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="left", x=0, font=dict(size=11)),
                                  margin=dict(b=90))
            else:
                st.caption("plants unavailable (planting sheet not reachable)")
        st.plotly_chart(fig, **PLOTLY, key=f"live3d_{var}_{show_plants}")
        if show_plants:
            st.caption("ต้นพืชวาดตามบันทึกรอบปลูก หนึ่งต้นต่อหลุม ทรงใบตามชนิดผัก ขนาดตามจำนวนวันบนชั้นปลูกเทียบกับวันที่วางแผนไว้ (ภาพประกอบ ไม่ใช่ขนาดที่วัดจริง)")

    twin_view()

    @st.fragment(run_every="60s" if auto else None)
    def live_view():
        # ---- latest state (status line, cards)
        state, table = current_state()
        ages = table.groupby("device")["age"].min().to_dict() if table is not None else None
        row = table["value"] if table is not None else tw.data.loc[state.time]
        now = pd.Timestamp.now(tz=TZ)
        stale = [f"{d} {age_text(a)}" for d, a in (ages or {}).items() if a > pd.Timedelta("30min") and not device_note(d, now - a)]
        st.caption(f"**{state.time:%Y-%m-%d %H:%M:%S}** Asia/Bangkok · " + " · ".join(f"{d} {device_note(d, now - a) or age_text(a) + ' ago'}" for d, a in (ages or {}).items())
                   + (f" · ⚠ stale: {', '.join(stale)}" if stale else ""))

        # ---- charts (same window and 5-min averaging as the ThingsBoard dashboard)
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
            c1.plotly_chart(ts_chart(R, ["co2.CO2"], "CO₂ (ppm)", "ppm", subtitle=stat_line(R.get("co2.CO2", pd.Series(dtype=float)), 0)), use_container_width=True, key="ts_co2")
            c2.plotly_chart(ts_chart(R, ["co2.VPD", "co2.VOC"], "VPD (kPa) / VOC — CO₂ controller", ""), use_container_width=True, key="ts_vpd")
            for dev, nm in (("gc1", "Grow controller gc1 — growing stage, 200 L tank"), ("gc2", "Grow controller gc2 — nursery 2, 100 L tank")):
                st.markdown(f"**{nm}**")
                c1, c2, c3 = st.columns([2, 2, 1.4])
                sp_ec = R.get(f"{dev}.ecSetPoint", pd.Series(dtype=float)).dropna(); sp_ph = R.get(f"{dev}.pHSetPoint", pd.Series(dtype=float)).dropna()
                red = lambda v: f" · <span style='color:#c0392b'><b>set {v.iloc[-1]:.2f}</b></span>" if v.size else ""
                c1.plotly_chart(ts_chart(R, [f"{dev}.ec"], f"EC (mS/cm){red(sp_ec)}", "mS/cm", setpoints={f"{dev}.ecSetPoint": "set-point"},
                                         subtitle=stat_line(R.get(f"{dev}.ec", pd.Series(dtype=float)))), use_container_width=True, key=f"ts_ec_{dev}")
                c2.plotly_chart(ts_chart(R, [f"{dev}.ph"], f"pH{red(sp_ph)}", "pH", setpoints={f"{dev}.pHSetPoint": "set-point"},
                                         subtitle=stat_line(R.get(f"{dev}.ph", pd.Series(dtype=float)))), use_container_width=True, key=f"ts_ph_{dev}")
                c3.plotly_chart(dose_chart(R, dev, height=300), use_container_width=True, key=f"dose_{dev}")
            if extended:
                st.plotly_chart(ts_chart(R, ["gc1.led", "gc1.pwmWater", "gc2.pwmWater", "co2.Relay_co2"], "LED / circulation pumps / CO₂ valve (beyond the dashboard)", "on = 1", step=True, height=220), use_container_width=True, key="ts_ctrl")

        # ---- details, collapsed (the charts already show the numbers)
        with st.expander("current values as cards" + (" + controller state / dosing configuration" if extended else "")):
            state_cards(state, None, row)
        if SHOW_ALL_KEYS and table is not None:
            with st.expander("latest values — all keys" if extended else "latest values — dashboard keys"):
                t2 = table if extended else table[table.index.isin(tb.DASHBOARD_COLUMNS)]
                t2 = t2.copy(); t2["age"] = t2["age"].map(age_text); t2["ts"] = t2["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
                t2.insert(0, "meaning", [tb.KEY_LABELS.get(k, "") for k in t2["key"]]); t2["on dashboard"] = t2.index.isin(tb.DASHBOARD_COLUMNS)
                st.dataframe(t2[["meaning", "value", "ts", "age", "on dashboard"]], width="stretch", height=480)

    live_view()

# ============================================================================ HISTORY
elif page == "History":
    st.title("ข้อมูลย้อนหลัง (History)")
    days = (d1 - d0).days
    _lm = (st.session_state.get("store_status") or {}).get("local") or {}
    upd = f" · store updated {pd.Timestamp(_lm['updated_at']).tz_convert(TZ):%d %b %Y %H:%M}" if _lm.get("updated_at") else ""
    st.markdown(f"**ข้อมูลมีตั้งแต่ · data available from {d0:%d %b %Y %H:%M} → {d1:%d %b %Y %H:%M}** ({days} days, {len(tw.data):,} × 10-min bins, {tw.data.shape[1]} columns){upd}  \n"
                f"Shown from {pd.Timestamp(HISTORY_START):%d %b %Y} (start of continuous operation; earlier commissioning samples are in the full store — download below). "
                "Store (SIS PFAL SQL database) refreshed every 30 min + topped up from ThingsBoard every 10 min; grey days below = the device sent nothing that day.")
    st.plotly_chart(availability_figure(STORE_VERSION), use_container_width=True, key="availability")
    with st.expander("⬇ download the whole store · ดาวน์โหลดข้อมูลทั้งหมด"):
        st.markdown("Columns are `device.key` (e.g. `gw.xy_md_21_t` = temperature of XY-MD02 unit 21, `gc1.ec` = EC of the growing-stage controller); "
                    "time index is Asia/Bangkok; the data dictionary explains every column. "
                    "Source: the SIS PFAL SQL database (tables `iot_10min`, `iot_long`), from the first sample on.")
        b1, b2, b3, b4 = st.columns(4)
        b1.download_button("10-min table — CSV", full_store_bytes(STORE_VERSION, "csv"), file_name=f"sis_pfal_10min_{d0:%Y%m%d}_{d1:%Y%m%d}.csv", mime="text/csv", use_container_width=True)
        b2.download_button("10-min table — Parquet", full_store_bytes(STORE_VERSION, "parquet"), file_name=f"sis_pfal_10min_{d0:%Y%m%d}_{d1:%Y%m%d}.parquet", mime="application/octet-stream", use_container_width=True)
        b4.download_button("data dictionary (Markdown)", (ROOT / "docs" / "DATA_DICTIONARY.md").read_bytes(), file_name="SIS_PFAL_DATA_DICTIONARY.md", mime="text/markdown", use_container_width=True)
        if b3.button("raw samples — prepare Parquet (~11 MB)", use_container_width=True, help="read all raw samples from the database (takes ~20 s)"):
            st.session_state["raw_ready"] = True
        if st.session_state.get("raw_ready"):
            try:
                b3.download_button("⬇ raw samples — Parquet", raw_store_bytes(STORE_VERSION), file_name="sis_pfal_raw_samples.parquet", mime="application/octet-stream", use_container_width=True)
            except Exception as e:
                b3.error(f"database unavailable: {str(e)[:120]}")
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

    # time cursor: drives the dotted line on the charts and the (collapsed) 3-D view of that moment
    idx = hist.index
    pick = st.slider("time cursor", min_value=idx[0].to_pydatetime(), max_value=idx[-1].to_pydatetime(), value=idx[-1].to_pydatetime(), step=pd.Timedelta("10min").to_pytimedelta(), format="DD MMM HH:mm")
    state = tw.state(pd.Timestamp(pick))

    st.markdown("#### Time series")
    import plotly.graph_objects as go
    for g in chosen:
        cols = [k for k in groups[g] if k in hist.columns]
        D = hist[cols].resample(freq).mean() if freq != "10min" else hist[cols]
        fig = go.Figure()
        for k in cols:
            lab = tb.channel_label(k[3:-2]) + k[-2:] if k.startswith("gw.") else (k.split(".")[0] + " " + tb.KEY_LABELS.get(k.split(".")[1], k.split(".")[1]))
            is_sp = "SetPoint" in k
            fig.add_scatter(x=D.index, y=D[k].ffill().bfill() if is_sp else D[k], mode="lines", name=f"<b>{lab}</b>" if is_sp else lab, connectgaps=is_sp,
                            line=dict(color="#c0392b", width=3, dash="dash") if is_sp else None,
                            line_shape="hv" if (is_sp or "mode" in k or "Time" in k or "Waiting" in k or "shots" in k) else "linear")
        fig.add_vline(x=pd.Timestamp(pick), line_dash="dot", line_color="grey")
        fig.update_layout(title=g, height=300, margin=dict(l=40, r=20, t=40, b=30), legend=dict(orientation="h", y=-0.25), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, key=f"ts_{g}")

    with st.expander(f"3-D twin at the cursor — {state.time:%Y-%m-%d %H:%M} (same view as Live, but for that moment)"):
        var = colour_picker("var_hist"); lo, hi = RANGES[var]
        st.plotly_chart(tw.figure_3d(var=var, st=state, cmin=lo, cmax=hi, height=600, public=not extended), **PLOTLY, key=f"hist3d_{var}")
        with st.expander(f"values at {state.time:%Y-%m-%d %H:%M} as cards"):
            state_cards(state, row=hist.loc[state.time] if state.time in hist.index else None)
    t1, t2, t3 = st.tabs(["KPI per channel (whole store)", "Events", "Heat-map (whole store)"])
    with t1:
        st.dataframe(tw.kpi(), width="stretch")
    with t2:
        ev = tw.events(save=False)
        ev = ev[(ev.start >= pd.Timestamp(start).tz_localize(TZ)) & (ev.start < (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize(TZ))]
        st.dataframe(ev, width="stretch", height=350)
        st.caption(f"thresholds: {tw.limits}")
    with t3:
        st.image(static_png("heatmap", STORE_VERSION), width="stretch")
    st.download_button("download selected range (CSV)", hist.to_csv().encode(), file_name=f"pfal_{start}_{end}.csv", mime="text/csv")

# ============================================================================ LAYOUT
elif page == "Layout & water":
    st.title("ผังห้องและระบบน้ำ (Layout & water)")
    t0, t1, t2, t3, t4, t5 = st.tabs(["LiDAR point cloud", "Layout (plan + elevation)", "Water-system plan", "Process flow", "Flow animation (3-D)", "Pipe corner detail"])
    with t0:
        st.markdown("**ที่มาของรูปทรงห้อง · where the geometry comes from** — the room was scanned twice on 13 Sep 2026 with a hand-held LiDAR; "
                    "this is scan 2 (true colour), aligned to the room frame and thinned to a 4-cm grid. The green slabs and frame are the parametric model "
                    "the twin uses (room 7.12 × 3.01 × 2.58 m, rack 5.43 × 1.04 m, 5 tiers) — the two scans agree within 5–8 cm.")
        cc = st.columns([2, 1])
        npts = cc[0].select_slider("points shown", options=[50000, 100000, 150000, 200000], value=50000, help="fewer points = faster loading and smoother rotation")
        open_up = cc[1].toggle("hide ceiling and front wall", value=True, help="off = the complete scan, as recorded")
        fig_pc, meta_pc = cloud_figure(npts, open_up, STORE_VERSION)
        st.plotly_chart(fig_pc, **PLOTLY, key=f"cloud_{npts}_{open_up}")
        st.caption(meta_pc + " · raw scans (119 MB) are kept out of the repository; notebooks 01–02 process them.")
    with t1:
        st.image(static_png("layout", STORE_VERSION), width="stretch")
    with t2:
        st.image(static_png("water", STORE_VERSION), width="stretch")
    with t3:
        st.image(static_png("flow", STORE_VERSION), width="stretch")
    with t4:
        st.plotly_chart(flow_animation(STORE_VERSION), **PLOTLY)
        st.caption("schematic — direction from photos and the design drawing; there is no flow sensor")
    with t5:
        st.image(static_png("corner", STORE_VERSION), width="stretch")
    with st.expander("equipment table"):
        st.dataframe(tw.equipment, width="stretch")
    with st.expander("sensor table"):
        st.dataframe(tw.sensors, width="stretch")

# ============================================================================ WHAT-IF
elif page == "What-if":
    st.title("จำลองสถานการณ์ (What-if)")
    tab_crop, tab_light = st.tabs(["Crop mix on the 720 holes (tiers 2–5)", "Light / energy scenarios"])
    with tab_crop:
        with st.expander("วิธีใช้ · How to use", expanded=True):
            st.markdown("""
**ทำอะไร** — ทดลองว่าถ้าปลูกผักหลายชนิดผสมกันบน **720 หลุม** ของชั้น 2–5 (ชั้นละ 180 หลุม = 30 คอลัมน์ × 6 แถว) จะวางตรงไหน ได้ผลผลิต/รายได้เท่าไร และแสงพอหรือไม่

**ขั้นตอน**
1. **crops** — เลือกชนิดผัก (เพิ่ม/ลบได้) จากรายการ 9 ชนิด
2. **% แต่ละชนิด** — เลื่อน slider ของทุกชนิดยกเว้นตัวสุดท้าย; **ตัวสุดท้ายรับส่วนที่เหลือให้ครบ 100 % เอง** (slider ถัดไปจะถูกจำกัดไว้ไม่ให้เกิน)
3. **placement** — `blocks` = จัดเป็นบล็อกต่อเนื่อง ไล่ทีละชั้น (จัดการง่าย เก็บเกี่ยวทั้งบล็อก) · `per_tier` = ทุกชั้นมีสัดส่วนเหมือนกัน (กระจายความเสี่ยงต่อชั้น)
4. **photoperiod** — ชั่วโมงเปิดไฟต่อวัน มีผลกับ DLI (แสงสะสมรายวัน) ที่ผักได้รับ
5. ดูผล: **ภาพ 3-D** 1 จุด = 1 หลุม สีตามชนิดผัก (หมุน/ซูม/กดขยายได้ · คลิกชื่อใน legend เพื่อซ่อน/แสดง) และ **ตาราง** ด้านล่าง; ดาวน์โหลดผังรายหลุมเป็น CSV ได้

**อ่านตาราง** — `holes` จำนวนหลุม · `days_to_harvest` วันถึงเก็บเกี่ยว · `plant_fw_g` น้ำหนักสดต่อต้น · `kg_per_cycle` / `cycles_per_year` / `kg_per_year` ผลผลิต · `THB_per_year` รายได้ (ราคาในแคตตาล็อก) · `DLI_need` vs `DLI_available` แสงที่ต้องการ vs ที่โมเดลคำนวณได้ · `light_ok` = `yes` หรือขาดอีกกี่ mol/m²/d

**ข้อจำกัด** — ตัวเลขผลผลิต/ราคา/DLI ที่ต้องการมาจากแคตตาล็อกเชิงสมมติ (`pfal_twin/models.py: CROPS`) และ DLI ที่มีคำนวณจากกำลัง LED (ชั้นละ 30 หลอด × 42 W) และประสิทธิภาพหลอดที่สมมติไว้ **ยังไม่ได้สอบเทียบ**กับค่าวัดจริง (PPFD, น้ำหนักเก็บเกี่ยว) — ใช้เปรียบเทียบ *ระหว่างทางเลือก* ได้ แต่อย่านำตัวเลขสัมบูรณ์ไปอ้างอิง
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
        st.caption("heat balance / energy use the steady-state model of notebook 06; calibrate with a PPFD map and the AC COP before quoting numbers")

# ---------------------------------------------------------------------------- footer
st.divider()
st.caption(f"**{PROJECT['name']}** — {PROJECT['th']}  \n{PROJECT['en']}  \n<small>build {APP_BUILD} · pfal_twin {pfal_twin.__version__}</small>", unsafe_allow_html=True)
