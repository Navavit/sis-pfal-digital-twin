"""pfal_twin — helper package for the SIS PFAL digital twin (notebooks + web app)."""
from pathlib import Path

__version__ = "2026.09.15.6"   # bump when the web app depends on new package code (see app/streamlit_app.py)

PKG_DIR = Path(__file__).resolve().parent
ROOT = PKG_DIR.parent                      # PFAL/  (project root)
DATA = ROOT / "data"
RAW = DATA / "raw"
PLY_PATH = RAW / "pointcloud" / "SIS PFAL.ply"
IOT_RAW = RAW / "iot"                      # CSV/Parquet exported from ThingsBoard
PROCESSED = DATA / "processed"
MODEL_DIR = DATA / "model"
SENSOR_DIR = DATA / "sensors"
FIG_DIR = ROOT / "figures"
for _d in (PROCESSED, MODEL_DIR, SENSOR_DIR, FIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)
