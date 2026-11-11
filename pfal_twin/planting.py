"""Planting rounds and the tray map of growing tiers 2-5, read from the public Google Sheet "PFAL รอบปลูก (สาธารณะ)".

That sheet is an IMPORTRANGE of the `รอบปลูก` tab of PFAL Management (the team's private workbook), reduced to tiers
2-5 and to the columns below; it is viewable by anyone with the link, the workbook itself is not. Tier 1 (nursery) is
left out on purpose: seedling records there are not reliable enough to show.

    rounds = load()                       # one row per crop block: tier, tray_from..tray_to, on_tray..off_tray, ...
    grid = tray_map(rounds)               # one row per (tier, tray) for today, with conflicts flagged
"""
from __future__ import annotations

import io

import pandas as pd
import requests

SHEET_ID = "16jLM95w9yY-YoV-N34A4ql0Lp6y3Y0ZoJPc454Ck68w"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
TZ = "Asia/Bangkok"
TIERS = (2, 3, 4, 5)
TRAYS = 10              # per tier; tray 1 = door side, tray 10 = far side
HOLES_PER_TRAY = 18     # 6 x 3 -> 180 holes per tier, 720 on tiers 2-5
DATES = ["sown", "on_tray", "off_tray", "harvest_plan", "harvest_actual"]
INTS = ["tier", "tray_from", "tray_to", "holes"]


def load(url: str = CSV_URL, timeout: int = 20) -> pd.DataFrame:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    if r.text.lstrip().startswith("<"):   # sign-in page: the sheet is not shared by link
        raise RuntimeError("planting sheet is not public")
    df = pd.read_csv(io.StringIO(r.content.decode("utf-8")), dtype=str).dropna(how="all")
    if "crop" not in df.columns:          # e.g. "#REF!" until someone allows the IMPORTRANGE
        raise RuntimeError(f"planting sheet has no data yet ({df.columns[0] if len(df.columns) else 'empty'})")
    for c in DATES:
        df[c] = pd.to_datetime(df.get(c), format="%Y-%m-%d", errors="coerce")
    for c in INTS:
        df[c] = pd.to_numeric(df.get(c), errors="coerce").astype("Int64")
    df = df[df["crop"].notna() & df["tier"].isin(TIERS)]
    return df.reset_index(drop=True)


def tray_map(rounds: pd.DataFrame, day=None) -> pd.DataFrame:
    """Occupancy of every tray of tiers 2-5 on `day` (default today): crop, round, harvest date, days left.
    A tray claimed by more than one block (a data conflict in the sheet) has n > 1 and lists every crop."""
    day = pd.Timestamp(day if day is not None else pd.Timestamp.now(tz=TZ).date()).normalize()
    on = rounds[(rounds["on_tray"] <= day) & (rounds["off_tray"] > day) & rounds["harvest_actual"].isna()]
    rows = []
    for tier in TIERS:
        for tray in range(1, TRAYS + 1):
            b = on[(on["tier"] == tier) & (on["tray_from"] <= tray) & (on["tray_to"] >= tray)]
            harvest = b["harvest_plan"].min() if len(b) else pd.NaT
            rows.append(dict(tier=tier, tray=tray, n=len(b), crop=" / ".join(b["crop"]), round=" / ".join(dict.fromkeys(b["round"].fillna(""))),
                             harvest_plan=harvest, days_left=(harvest - day).days if pd.notna(harvest) else None))
    return pd.DataFrame(rows)


def upcoming_harvests(rounds: pd.DataFrame, day=None, days: int = 21) -> pd.DataFrame:
    """Blocks still on the tiers whose planned harvest is within `days` (or overdue), soonest first."""
    day = pd.Timestamp(day if day is not None else pd.Timestamp.now(tz=TZ).date()).normalize()
    b = rounds[rounds["harvest_actual"].isna() & rounds["harvest_plan"].notna() & (rounds["on_tray"] <= day)
               & (rounds["harvest_plan"] <= day + pd.Timedelta(days=days))].copy()
    b["days_left"] = (b["harvest_plan"] - day).dt.days
    return b.sort_values(["harvest_plan", "tier", "tray_from"])
