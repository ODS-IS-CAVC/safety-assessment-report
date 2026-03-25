#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make exposure (distance/time) aggregated by Excel road grouping (route_group_main_v2).

This script bridges:
  - Driving exposure from E1A_ab_dist_scan_v3 (totals_by_carweek_label.csv + totals_by_label.csv)
  - Near-miss Excel road grouping (route_group_main_v2 / route_group_main / route_group / route_name)

It outputs:
  1) exposure_by_roadgroup.csv              (group, distance_km, duration_h, steps)
  2) exposure_by_carweek_roadgroup.csv      (car_week, group, distance_km, duration_h, steps)

Usage example:
  python make_exposure_by_excel_routegroup_v1.py ^
    --excel "route_nearmiss_analysis_with_dx_and_unknown_GROUPED_v12_all1018 (1).xlsx" ^
    --sheet "AllPoints_1018" ^
    --totals_carweek_label "exposure_out/totals_by_carweek_label.csv" ^
    --totals_label "exposure_out/totals_by_label.csv" ^
    --outdir "exposure_out"

Notes:
- label_name in totals_by_* should roughly match Excel's route_name (OSM 'name/ref').
- Mapping is learned from Excel itself: route_name -> route_group_main_v2 (majority vote).
- If a label_name cannot be mapped, it falls back to:
    - if totals_by_label provides 'group' (Highway/National/...), then:
        Highway -> "高速ランプ（道路名なし）"
        else -> "一般道（道路名なし）"
    - else -> "Unknown"
"""

import argparse
from pathlib import Path
import pandas as pd

def build_name_to_group_mapping(df: pd.DataFrame) -> dict:
    # Choose best road group column available (prefer v2)
    group_cols = [c for c in ["route_group_main_v2", "route_group_main", "route_group", "route_name"] if c in df.columns]
    if not group_cols:
        raise ValueError("Excelに道路列がありません（route_group_main_v2 等）。")

    # We learn mapping from route_name -> route_group_main_v2 (or best available)
    if "route_name" not in df.columns:
        # If no route_name, fall back to mapping from route_ref
        key_col = "route_ref" if "route_ref" in df.columns else None
        if key_col is None:
            return {}
    else:
        key_col = "route_name"

    # target group column: prefer v2
    target_col = "route_group_main_v2" if "route_group_main_v2" in df.columns else group_cols[0]

    tmp = df[[key_col, target_col]].copy()
    tmp[key_col] = tmp[key_col].astype(str).str.strip()
    tmp[target_col] = tmp[target_col].astype(str).str.strip()
    tmp = tmp[(tmp[key_col] != "") & (tmp[key_col].str.lower() != "nan")]
    tmp = tmp[(tmp[target_col] != "") & (tmp[target_col].str.lower() != "nan")]

    # Ignore Unknown target in mapping training
    tmp = tmp[tmp[target_col].str.lower() != "unknown"]

    if tmp.empty:
        return {}

    # Majority vote mapping
    gb = tmp.groupby([key_col, target_col]).size().reset_index(name="n")
    gb = gb.sort_values(["n"], ascending=False)
    # pick top for each key
    mapping = {}
    for key, sub in gb.groupby(key_col, sort=False):
        mapping[key] = sub.iloc[0][target_col]
    return mapping

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True)
    ap.add_argument("--sheet", default="AllPoints_1018")
    ap.add_argument("--totals_carweek_label", required=True, help="totals_by_carweek_label.csv from E1A_ab_dist_scan")
    ap.add_argument("--totals_label", default=None, help="totals_by_label.csv from E1A_ab_dist_scan (for label group fallback)")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(args.excel, sheet_name=args.sheet)
    name_to_group = build_name_to_group_mapping(df)

    cw = pd.read_csv(args.totals_carweek_label, encoding="utf-8-sig")
    if "car_week" not in cw.columns or "label_name" not in cw.columns:
        raise ValueError("totals_by_carweek_label.csv に car_week / label_name がありません。")
    # Normalize
    cw["label_name"] = cw["label_name"].astype(str).str.strip()

    # Optional label meta for fallback
    label_meta = None
    if args.totals_label:
        tl = pd.read_csv(args.totals_label, encoding="utf-8-sig")
        if "label_name" in tl.columns:
            label_meta = tl.set_index("label_name").to_dict(orient="index")

    def map_label_to_group(label: str) -> str:
        if label in name_to_group:
            return name_to_group[label]
        # fallback: try simple normalization for refs (e.g., "E1A" etc.) if present in excel
        if label.startswith("E") and label in name_to_group:
            return name_to_group[label]
        # fallback by label_meta group (Highway etc.)
        if label_meta and label in label_meta:
            g = str(label_meta[label].get("group","")).strip()
            if g.lower() == "highway":
                return "高速ランプ（道路名なし）"
            return "一般道（道路名なし）"
        return "Unknown"

    cw["road_group_excel"] = cw["label_name"].map(map_label_to_group)
    # Choose distance/time columns
    # Prefer geo-clamped km (matches expected E1A total), then hv-clamped, then speed-based.
    if "dist_geo_clamped_km" in cw.columns:
        dist_col = "dist_geo_clamped_km"
    elif "dist_hv_clamped_km" in cw.columns:
        dist_col = "dist_hv_clamped_km"
    elif "dist_speed_km" in cw.columns:
        dist_col = "dist_speed_km"
    else:
        raise ValueError("totals_by_carweek_label.csv に距離列がありません（dist_geo_clamped_km / dist_hv_clamped_km / dist_speed_km）。")
    time_col = "duration_h" if "duration_h" in cw.columns else None

    # Aggregate by car_week + road_group
    # Aggregate by car_week + road_group
    agg_cols = {dist_col:"sum", "steps":"sum"}
    if time_col: agg_cols[time_col] = "sum"
    out_cw = cw.groupby(["car_week","road_group_excel"], as_index=False).agg(agg_cols)
    out_cw = out_cw.rename(columns={
        dist_col:"distance_km",
        time_col or "duration_h":"duration_h" if time_col else "duration_h",
        "road_group_excel":"road_group"
    })
    if not time_col:
        out_cw["duration_h"] = float("nan")
    out_cw.to_csv(outdir / "exposure_by_carweek_roadgroup.csv", index=False, encoding="utf-8-sig")

    # Aggregate overall by road_group
    out_rg = out_cw.groupby(["road_group"], as_index=False).agg({"distance_km":"sum","duration_h":"sum","steps":"sum"})
    out_rg = out_rg.sort_values("distance_km", ascending=False)
    out_rg.to_csv(outdir / "exposure_by_roadgroup.csv", index=False, encoding="utf-8-sig")

    print("[ok] wrote:")
    print(" -", (outdir / "exposure_by_carweek_roadgroup.csv").resolve())
    print(" -", (outdir / "exposure_by_roadgroup.csv").resolve())

if __name__ == "__main__":
    main()
