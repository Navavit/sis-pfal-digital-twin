"""pfal_twin — helper package for the SIS-KU PFAL digital twin notebooks."""
from pathlib import Path

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
