#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ab_dist_scan.py

Scan all trips (text CSV logs) under a root folder, find the best-matching
segment that goes from landmark A to B, clip that A→B slice, then compute /
compare three distance methods on the slice:

(1) speed_integral_km_ab: sum(speed_kph * dt_hours) on the clipped slice
(2) haversine_min_km_ab: per-step min(haversine_m, fallback_kph * dt_sec/3600*1000) with gap/jump guard by construction
(3) ellipsoid_min_km_ab: same as (2) but WGS84 (pyproj.Geod)

Selection of the "best" slice (across files):
- A file is a candidate if it has at least one point within --radius-m of A
  and at least one point within --radius-m of B, and there exists a pair
  (i ∈ nearA, j ∈ nearB) with j > i (i.e., B happens after A).
- For each candidate, we evaluate all valid pairs (i, j), compute a pair score
  score_m = dist(i,A) + dist(j,B). For that file, we keep the pair with the
  minimal score.
- Across files, the winner is the file whose best pair has the smallest score.
  If ties, pick the one with the longest sliced duration (j_time - i_time).

Input format (per row; header lines may repeat within file):
  day,time,x,y,z,latitude,longitude,speed
  2024/12/17,17:27:29.538,-0.100,+0.132,-1.264,35.64766,139.84002,69

Notes
-----
* Files may repeat the header line; those rows are ignored.
* Timestamps use local time; we only need relative differences.
* "speed" is assumed to be km/h.
* UNC and JP paths supported. We open files with errors='ignore'.
* Car ID is inferred from path (e.g., HDD08 folder or leading "08_" segment).

Outputs
-------
- A summary CSV of all candidates (ab_candidates.csv) sorted by score.
- A detailed per-step CSV of the best slice (ab_best_slice.csv).
- A JSON sidecar with the winning metadata (ab_best_slice.json).

Example
-------
python ab_dist_scan.py \
  --root "Path_To_Log" \
  --glob "**/csv/*.txt" \
  --a 35.46463,139.43556 \
  --b 35.35033,139.22489 \
  --radius-m 200 \
  --fallback-kph 80 \
  --outdir ./ab_out

Requires: Python 3.9+, pandas, numpy. Optional: pyproj for WGS84 distance.
"""

from __future__ import annotations
import argparse
import csv
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from functools import lru_cache


try:
    from pyproj import Geod  # optional
    _GEOD = Geod(ellps="WGS84")
except Exception:
    _GEOD = None

def _is_e1a(meta: dict) -> bool:
    if not meta:
        return False
    ref = str(meta.get("ref", "")).upper()
    name = str(meta.get("name", ""))
    if "E1A" in ref:
        return True
    if "新東名" in name:
        return True
    return False


# ----------------------------- geo utilities -----------------------------

EARTH_R_M = 6371000.0

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Vector/Scalar-safe haversine distance in meters."""
    # Convert to radians
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return EARTH_R_M * c


def geod_m(lat1, lon1, lat2, lon2) -> float:
    """WGS84 ellipsoidal distance in meters via pyproj.Geod if available; otherwise haversine."""
    if _GEOD is not None:
        az12, az21, dist_m = _GEOD.inv(lon1, lat1, lon2, lat2)
        return dist_m
    else:
        return haversine_m(lat1, lon1, lat2, lon2)

# --------------------------- parsing & loading ----------------------------

HEADER_RE = re.compile(r"^\s*day\s*,\s*time\s*,", re.IGNORECASE)
DATE_FMT_HINTS = [
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
]

@dataclass
class Row:
    ts: pd.Timestamp
    lat: float
    lon: float
    speed_kph: float


def parse_file_rows(path: Path) -> List[Row]:
    rows: List[Row] = []
    def _open_text_any(p: Path):
        for enc in ("utf-8-sig", "cp932", "utf-8"):
            try:
                return open(p, "r", encoding=enc, newline="")
            except Exception:
                continue
        return open(p, "r", encoding="utf-8", errors="replace", newline="")

    with _open_text_any(path) as f:
        reader = csv.reader(f)
        for rec in reader:
            if not rec:
                continue
            # Handle repeated header lines anywhere
            head = ",".join(rec[:2]).strip().lower()
            if HEADER_RE.match(head):
                continue
            try:
                # Expect 8 columns: day,time,x,y,z,lat,lon,speed
                if len(rec) < 8:
                    continue
                day_str = rec[0].strip()
                time_str = rec[1].strip()
                lat = float(rec[5])
                lon = float(rec[6])

                # 1.A) Sanity check: drop impossible coordinates
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    continue  # skip corrupted line
                speed_kph = float(rec[7])
                ts = _parse_ts(day_str + " " + time_str)
                if ts is None:
                    continue
                rows.append(Row(ts=pd.Timestamp(ts), lat=lat, lon=lon, speed_kph=speed_kph))
            except Exception:
                # Ignore malformed lines
                continue
    return rows


def _parse_ts(s: str) -> Optional[datetime]:
    for fmt in DATE_FMT_HINTS:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    try:
        # Fallback to pandas parser
        return pd.to_datetime(s, errors="coerce").to_pydatetime()
    except Exception:
        return None


# ------------------------------ car id util -------------------------------

CARID_RE = re.compile(
    r"(?:^|[\\/])(?:result_[^\\/]*_)?(?P<cid>\d{2})_\d{6}-\d{6}(?:[\\/]|$)",
    re.IGNORECASE
)
HDD_RE = re.compile(r"(?:^|[\\/])HDD(\d{2})(?:[\\/]|$)")

# ------------------------------ car week util ------------------------------

CARWEEK_RE = re.compile(r"(?:^|[\\/])(?P<cw>\d{2}_\d{6}-\d+)(?:[\\/]|$)", re.IGNORECASE)
CARWEEK_INLINE_RE = re.compile(r"(?P<cw>\d{2}_\d{6}-\d+)", re.IGNORECASE)
CARWEEK_RESULT_RE = re.compile(r"result_(?P<car>\d{2})_(?P<start>\d{6})-(?P<end>\d+)", re.IGNORECASE)


def _looks_like_yymmdd(value: str) -> bool:
    if len(value) != 6 or not value.isdigit():
        return False
    try:
        datetime.strptime(value, "%y%m%d")
        return True
    except Exception:
        return False


def _repair_carweek_end(start_ymd: str, tail_digits: str) -> Optional[str]:
    digits = re.sub(r"\D", "", tail_digits or "")
    if not start_ymd or not digits:
        return None
    if len(digits) >= 6:
        candidates = [digits[:6]]
    else:
        prefix = start_ymd[: max(0, 6 - len(digits))]
        candidates = [(prefix + digits)[-6:]]
    for cand in candidates:
        if _looks_like_yymmdd(cand):
            return cand
    return candidates[0] if candidates else None


def normalize_carweek_token(raw: str) -> str:
    s = str(raw or "").strip().replace("\\", "/")
    m = CARWEEK_INLINE_RE.search(s)
    if not m:
        return s
    full = m.group("cw")
    parts = re.match(r"(?P<car>\d{1,2})_(?P<start>\d{6})-(?P<end>\d+)", full)
    if not parts:
        return full
    car = parts.group("car").zfill(2)
    start = parts.group("start")
    end_raw = parts.group("end")
    end = end_raw[:6] if _looks_like_yymmdd(end_raw[:6]) else _repair_carweek_end(start, end_raw)
    return f"{car}_{start}-{end}" if end else f"{car}_{start}-{end_raw[:6]}"


def _infer_car_week_value(pathish) -> Optional[str]:
    s = str(pathish or "").replace("\\", "/")
    for rx in (CARWEEK_RE, CARWEEK_INLINE_RE):
        m = rx.search(s)
        if m:
            return normalize_carweek_token(m.group("cw"))
    m = CARWEEK_RESULT_RE.search(s)
    if m:
        return normalize_carweek_token(f"{m.group('car')}_{m.group('start')}-{m.group('end')}")
    return None


def infer_car_week_from_path(p: Path) -> Optional[str]:
    return _infer_car_week_value(p)


def _strip_hidden_text(raw: Optional[str]) -> str:
    text = str(raw or "")
    for ch in ("\ufeff", "\u200b", "\u200e", "\u200f", "\u2060"):
        text = text.replace(ch, "")
    return text.strip()


def read_allowlist_carweek(path: Optional[str]) -> Optional[set]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    s = p.read_text(encoding='utf-8', errors='replace')
    allow = set()
    for raw in s.splitlines():
        line = _strip_hidden_text(raw)
        if not line:
            continue
        if line.startswith('#') or line.startswith(';'):
            continue
        norm = normalize_carweek_token(line)
        if norm:
            allow.add(norm)
    return allow

def infer_car_id_from_path(p: Path) -> Optional[str]:
    s = str(p)
    m = CARID_RE.search(s)
    if m:
        return m.group("cid")
    m = HDD_RE.search(s)
    if m:
        return m.group(1)
    return None

def infer_car_id_with_source(p: Path) -> Tuple[Optional[str], str]:
    """
    Return (car_id, source), where source ∈ {'result','hdd','none'}.
    - 'result' hits ...result_*_NN_YYYYMM-YYYYMM...
    - 'hdd'    hits HDDNN folder
    - 'none'   nothing found
    """
    s = str(p)
    m = CARID_RE.search(s)
    if m:
        return m.group("cid"), "result"
    m = HDD_RE.search(s)
    if m:
        return m.group(1), "hdd"
    return None, "none"

# ---------------------------- candidate search ----------------------------

@dataclass
class PairChoice:
    iA: int
    jB: int
    dA_m: float
    dB_m: float
    score_m: float


# -------- cross-file stitch support --------

@dataclass
class FileMeta:
    file: Path
    car_id: Optional[str]
    t_first: pd.Timestamp
    t_last: pd.Timestamp
    n_rows: int

@dataclass
class ABEvent:
    file: Path
    car_id: Optional[str]
    idx: int
    ts: pd.Timestamp
    lat: float
    lon: float
    dist_m: float
    kind: str  # 'A' or 'B'

@dataclass
class StitchChoice:
    a_evt: ABEvent
    b_evt: ABEvent
    score_m: float


def find_best_AB_pair(df: pd.DataFrame, a_lat: float, a_lon: float,
                      b_lat: float, b_lon: float, radius_m: float) -> Optional[PairChoice]:
    lat = df["lat"].to_numpy()
    lon = df["lon"].to_numpy()

    dA = haversine_m(lat, lon, a_lat, a_lon)
    dB = haversine_m(lat, lon, b_lat, b_lon)

    nearA = np.where(dA <= radius_m)[0]
    nearB = np.where(dB <= radius_m)[0]
    if len(nearA) == 0 or len(nearB) == 0:
        return None

    best: Optional[PairChoice] = None
    j_idx = 0
    for i in nearA:
        while j_idx < len(nearB) and nearB[j_idx] <= i:
            j_idx += 1
        if j_idx >= len(nearB):
            break
        j_post = nearB[j_idx:]
        if len(j_post) == 0:
            continue
        k = int(np.argmin(dB[j_post]))
        j = int(j_post[k])
        cand = PairChoice(
            iA=int(i), jB=j,
            dA_m=float(dA[i]), dB_m=float(dB[j]),
            score_m=float(dA[i] + dB[j]),
        )
        if (best is None) or (cand.score_m < best.score_m) or (
            abs(cand.score_m - best.score_m) < 1e-6
            and df["ts"].iat[cand.jB] - df["ts"].iat[cand.iA]
                > df["ts"].iat[best.jB] - df["ts"].iat[best.iA]
        ):
            best = cand
    return best

def find_best_AB_events(
    a_evts: List[ABEvent],
    b_evts: List[ABEvent],
    mode: str = "nearest",                 # "nearest" | "longest" | "balanced"
    lambda_per_min: float = 0.0,           # only for "balanced"
    same_car_only: bool = False,
    max_span_min: Optional[float] = None,  # None = unlimited
) -> Optional[StitchChoice]:
    if not a_evts or not b_evts:
        return None

    # sort by time
    a_evts = sorted(a_evts, key=lambda e: e.ts)
    b_evts = sorted(b_evts, key=lambda e: e.ts)

    best: Optional[StitchChoice] = None
    best_duration_s: float = -1.0  # for tiebreaks

    for ai in a_evts:
        # gather all valid B after this A
        candidates_b = []
        for bj in b_evts:
            if bj.ts <= ai.ts:
                continue
            if same_car_only and (bj.car_id != ai.car_id):
                continue
            span_min = (bj.ts - ai.ts).total_seconds() / 60.0
            if span_min <= 0:
                continue
            if (max_span_min is not None) and (span_min > max_span_min):
                continue
            candidates_b.append(bj)

        if not candidates_b:
            continue

        pick_b: Optional[ABEvent] = None

        if mode == "longest":
            # maximize duration among valid pairs for this A
            pick_b = max(candidates_b, key=lambda bj: (bj.ts - ai.ts).total_seconds())
        elif mode == "balanced":
            # minimize (dA + dB - lambda * minutes)
            def balanced_score(bj: ABEvent) -> float:
                duration_min = (bj.ts - ai.ts).total_seconds() / 60.0
                return ai.dist_m + bj.dist_m - lambda_per_min * duration_min
            pick_b = min(candidates_b, key=balanced_score)
        else:  # "nearest"
            # minimize (dA + dB) for this A -> equivalent to minimizing dB since dA is fixed
            pick_b = min(candidates_b, key=lambda bj: bj.dist_m)

        # evaluate global best
        duration_s = (pick_b.ts - ai.ts).total_seconds()
        score = ai.dist_m + pick_b.dist_m if mode != "balanced" else (
            ai.dist_m + pick_b.dist_m - lambda_per_min * (duration_s / 60.0)
        )
        if best is None:
            best = StitchChoice(a_evt=ai, b_evt=pick_b, score_m=float(score))
            best_duration_s = duration_s
        else:
            improve = score < best.score_m
            tie = abs(score - best.score_m) < 1e-9
            if improve or (tie and duration_s > best_duration_s):
                best = StitchChoice(a_evt=ai, b_evt=pick_b, score_m=float(score))
                best_duration_s = duration_s

    return best


def build_stitched_slice(a_evt: ABEvent, b_evt: ABEvent,
                         file_metas: List[FileMeta],
                         same_car_only: bool) -> Tuple[List[Path], pd.DataFrame]:
    """Re-read files overlapping [tA, tB], concatenate rows, and hard-clip to indices at ends."""
    tA, tB = a_evt.ts, b_evt.ts

    def overlaps(fm: FileMeta) -> bool:
        return not (fm.t_last < tA or fm.t_first > tB)

    # Pick files to read according to same-car policy
    if same_car_only or (a_evt.car_id == b_evt.car_id):
        selected = [fm.file for fm in file_metas if overlaps(fm) and fm.car_id == a_evt.car_id]
    else:
        # allow cross-car stitching: include all files overlapping the window
        selected = [fm.file for fm in file_metas if overlaps(fm)]
    selected = sorted(selected, key=lambda p: str(p))  # deterministic order

    # Read & time-clip each file, keep source annotation
    all_rows = []
    for p in selected:
        df = load_df_cached(p)
        if df.empty:
            continue
        df = df.copy()
        df["src_file"] = str(PureWindowsPath(p))
        df = df[(df["ts"] >= tA) & (df["ts"] <= tB)].copy()
        all_rows.append(df)

    if not all_rows:
        return selected, pd.DataFrame(columns=["ts", "lat", "lon", "speed_kph", "src_file"])

    stitched = pd.concat(all_rows, ignore_index=True)
    stitched = stitched.sort_values("ts").reset_index(drop=True)

    # Ensure inclusion of the exact A/B points by forcing endpoints from their files
    def boundary_df(evt: ABEvent, is_start: bool) -> pd.DataFrame:
        df_b = load_df_cached(evt.file).copy()
        df_b["src_file"] = str(PureWindowsPath(evt.file))
        return df_b.iloc[evt.idx:] if is_start else df_b.iloc[:evt.idx+1]

    start_tail = boundary_df(a_evt, True)
    end_head  = boundary_df(b_evt, False)

    # Hard clip again and union with boundary pieces to guarantee endpoints
    stitched = stitched[(stitched["ts"] >= tA) & (stitched["ts"] <= tB)].copy()
    stitched = pd.concat(
        [start_tail[start_tail["ts"] >= tA], stitched, end_head[end_head["ts"] <= tB]],
        ignore_index=True
    )
    stitched = (
        stitched.sort_values("ts")
        .reset_index(drop=True)
    )

    # Final columns
    stitched = stitched[["ts", "lat", "lon", "speed_kph", "src_file"]]
    return selected, stitched

def _find_runs(mask: np.ndarray) -> list[tuple[int,int]]:
    runs = []
    i, n = 0, int(mask.size)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and mask[j + 1]:
            j += 1
        runs.append((i, j))  # inclusive
        i = j + 1
    return runs

# --------- simple in-memory DataFrame cache ---------
_DF_CACHE: dict[str, pd.DataFrame] = {}

def load_df_cached(p: Path) -> pd.DataFrame:
    """Parse + build DataFrame once per file path, then reuse."""
    key = str(PureWindowsPath(p))  # stable across OS
    if key in _DF_CACHE:
        return _DF_CACHE[key]
    rows = parse_file_rows(p)
    df = make_df(rows)
    _DF_CACHE[key] = df
    return df



def infer_car_week_from_path(path: str) -> str:
    """Extract a normalized car-week token from a file path."""
    return _infer_car_week_value(path) or ""

# ------------------------------- OSM helpers -------------------------------

@dataclass
class _Snap:
    way_id: int
    s_m: float           # cumulative length along way to projection point (meters)
    dist_m: float        # lateral snap distance (meters)
    seg_idx: int         # segment index
    t: float             # segment param [0,1]

@dataclass
class _OSMWay:
    way_id: int | str
    lats: np.ndarray
    lons: np.ndarray
    cumlen_m: np.ndarray
    bbox: tuple
    name: str = ""
    ref: str = ""
    highway: str = ""

class OSMIndex:
    def __init__(self, ways: list[_OSMWay], grid_ddeg: float = 0.01):
        self.ways = ways
        self.grid_ddeg = float(grid_ddeg)
        self._meta = {w.way_id: {"name": w.name, "ref": w.ref, "highway": w.highway} for w in self.ways}
        self._grid: dict[tuple[int,int], list[int]] = {}

        # Build simple bbox-based index
        for idx, w in enumerate(self.ways):
            min_la, min_lo, max_la, max_lo = w.bbox
            gx0 = int(np.floor(min_lo / self.grid_ddeg))
            gx1 = int(np.floor(max_lo / self.grid_ddeg))
            gy0 = int(np.floor(min_la / self.grid_ddeg))
            gy1 = int(np.floor(max_la / self.grid_ddeg))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    self._grid.setdefault((gx, gy), []).append(idx)

        # de-dup in each cell (念のため)
        for k, lst in self._grid.items():
            self._grid[k] = list(dict.fromkeys(lst))

    # NEW: helpers
    def get_meta(self, way_id):
        return self._meta.get(way_id, {})

    def way_key(self, way_id):
        m = self.get_meta(way_id)
        if m.get("name"): return m["name"]
        if m.get("ref"):  return m["ref"]
        return f"way:{way_id}"

    @staticmethod
    def from_json(path: str, grid_ddeg: float = 0.01) -> "OSMIndex":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and "ways" in raw:
            ways_in = raw["ways"]
        elif isinstance(raw, dict):
            ways_in = []
            for k, v in raw.items():
                if isinstance(v, dict):
                    vv = dict(v)
                    vv.setdefault("id", int(k) if str(k).isdigit() else k)
                    ways_in.append(vv)
                    continue
                if isinstance(v, (list, tuple)):
                    ways_in.append({"id": int(k) if str(k).isdigit() else k, "geometry": v, "tags": {}})
                    continue
                continue
        elif isinstance(raw, list):
            ways_in = raw
        else:
            raise ValueError("Unrecognized OSM cache format")

        ways: list[_OSMWay] = []
        for wd in ways_in:
            way_id = wd.get("id", wd.get("way_id"))
            geom = wd.get("geometry") or wd.get("nodes")
            if way_id is None or not geom or len(geom) < 2:
                continue
            lat_list, lon_list = [], []
            for p in geom:
                if isinstance(p, dict):
                    la, lo = float(p.get("lat")), float(p.get("lon"))
                else:
                    la, lo = float(p[0]), float(p[1])
                lat_list.append(la); lon_list.append(lo)
            lats = np.asarray(lat_list, dtype=float)
            lons = np.asarray(lon_list, dtype=float)
            seg_m = np.zeros(len(lats)-1, dtype=float)
            for i in range(len(seg_m)):
                seg_m[i] = geod_m(lats[i], lons[i], lats[i+1], lons[i+1])
            cumlen = np.r_[0.0, np.cumsum(seg_m)]
            bbox = (float(lats.min()), float(lons.min()), float(lats.max()), float(lons.max()))

            # NEW: pull tags (Overpass: under "tags", or top-level fallbacks)
            tags = wd.get("tags") or wd
            name = (tags.get("name") or "").strip()
            ref  = (tags.get("ref") or "").strip()
            hwy  = (tags.get("highway") or "").strip()

            ways.append(_OSMWay(
                int(way_id) if str(way_id).isdigit() else way_id,
                lats, lons, cumlen, bbox,
                name=name, ref=ref, highway=hwy
            ))
        return OSMIndex(ways, grid_ddeg=grid_ddeg)

    @staticmethod
    def _to_xy_m(lat, lon, lat0: float) -> tuple:
        # supports scalars or numpy arrays
        R = 6371000.0
        lat_rad = np.radians(lat)
        lon_rad = np.radians(lon)
        lat0_rad = np.radians(lat0)
        x = lon_rad * R * np.cos(lat0_rad)
        y = lat_rad * R
        return x, y

    def _candidates(self, lat: float, lon: float) -> list[int]:
        gx = int(np.floor(lon / self.grid_ddeg))
        gy = int(np.floor(lat / self.grid_ddeg))
        ids = []
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                ids.extend(self._grid.get((gx+dx, gy+dy), []))
        return ids

    def snap(self, lat: float, lon: float, max_dist_m: float) -> Optional[_Snap]:
        cand_ids = self._candidates(lat, lon)
        if not cand_ids:
            return None
        best: Optional[_Snap] = None
        for idx in cand_ids:
            w = self.ways[idx]
            min_la, min_lo, max_la, max_lo = w.bbox
            # quick bbox grow ~max_dist_m
            lat_pad = max_dist_m / 111111.0
            lon_pad = max_dist_m / (111111.0 * max(1e-6, np.cos(np.radians(lat))))
            if not (min_la - lat_pad <= lat <= max_la + lat_pad and
                    min_lo - lon_pad <= lon <= max_lo + lon_pad):
                continue

            # project to XY around local lat
            xy_lat0 = np.clip(lat, -85.0, 85.0)
            xq, yq = self._to_xy_m(lat, lon, xy_lat0)
            xs, ys = self._to_xy_m(w.lats, w.lons, xy_lat0)

            # nearest segment by perpendicular projection
            for i in range(len(xs)-1):
                x1, y1 = xs[i], ys[i]; x2, y2 = xs[i+1], ys[i+1]
                vx, vy = x2 - x1, y2 - y1
                wx, wy = xq - x1, yq - y1
                seg_len2 = vx*vx + vy*vy
                if seg_len2 <= 0.0:
                    t = 0.0
                else:
                    t = max(0.0, min(1.0, (wx*vx + wy*vy) / seg_len2))
                xp, yp = x1 + t*vx, y1 + t*vy
                dist = float(np.hypot(xq - xp, yq - yp))
                if dist <= max_dist_m:
                    # s along polyline in meters: cumlen to segment start + t * seg_length
                    seg_len_m = float(w.cumlen_m[i+1] - w.cumlen_m[i]) 
                    s_m = float(w.cumlen_m[i] + t * seg_len_m)
                    snap = _Snap(w.way_id, s_m, dist, i, t)
                    if (best is None) or (dist < best.dist_m):
                        best = snap
        return best

def load_osm_cache_with_attrs(path: str):
    """
    Return (ways_map, attrs_map)
      ways_map: {way_id: [[lat,lon], ...]}
      attrs_map: {way_id: {"name":..., "ref":..., "highway":...}}
    Supports Overpass JSON (elements[] with tags/geometry), FeatureCollection, or dict/list caches.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ways_map, attrs_map = {}, {}

    def _flat(coords):
        if not coords: return []
        if isinstance(coords[0][0], (float, int)): return coords
        out = [];  [out.extend(line) for line in coords];  return out

    def _lonlat_to_latlon(pt):
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x, y = pt[0], pt[1]
            return [float(y), float(x)]
        return [float("nan"), float("nan")]

    # Overpass JSON
    if isinstance(data, dict) and isinstance(data.get("elements"), list):
        nodes = {}
        for el in data["elements"]:
            if el.get("type") == "node" and "lat" in el and "lon" in el:
                nodes[el["id"]] = [float(el["lat"]), float(el["lon"])]
        for el in data["elements"]:
            if el.get("type") != "way": continue
            wid = str(el.get("id"))
            coords = []
            if "geometry" in el and isinstance(el["geometry"], list) and el["geometry"]:
                coords = [[float(g["lat"]), float(g["lon"])] for g in el["geometry"] if "lat" in g and "lon" in g]
            elif "nodes" in el and nodes:
                coords = [nodes[nid] for nid in el["nodes"] if nid in nodes]
            if len(coords) >= 2:
                ways_map[wid] = coords
                tags = el.get("tags", {})
                attrs_map[wid] = {
                    "name": (tags.get("name") or "").strip(),
                    "ref":  (tags.get("ref") or "").strip(),
                    "highway": (tags.get("highway") or "").strip(),
                }
        return ways_map, attrs_map

    # GeoJSON FeatureCollection / list
    if (isinstance(data, dict) and data.get("type") == "FeatureCollection") or (
        isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("type") == "Feature"
    ):
        feats = data.get("features", data if isinstance(data, list) else [])
        for i, feat in enumerate(feats):
            geom = feat.get("geometry") or {}
            if geom.get("type") not in ("LineString", "MultiLineString"): continue
            props = feat.get("properties", {})
            wid = str(props.get("id") or props.get("osm_id") or feat.get("id") or f"feat_{i}")
            coords = [_lonlat_to_latlon(p) for p in _flat(geom.get("coordinates") or [])]
            if len(coords) >= 2:
                ways_map[wid] = coords
                attrs_map[wid] = {
                    "name": (props.get("name") or "").strip(),
                    "ref":  (props.get("ref") or "").strip(),
                    "highway": (props.get("highway") or "").strip(),
                }
        return ways_map, attrs_map

    # Simple dict/list caches
    if isinstance(data, dict) and "ways" in data:
        ways_in = data["ways"]
    elif isinstance(data, dict):
        ways_in = []
        for k, v in data.items():
            v = dict(v); v.setdefault("id", k)
            ways_in.append(v)
    elif isinstance(data, list):
        ways_in = data
    else:
        raise ValueError("Unsupported osm_cache schema")

    for i, wd in enumerate(ways_in):
        wid = str(wd.get("id") or wd.get("way_id") or f"w{i}")
        geom = wd.get("geometry") or wd.get("nodes") or wd.get("coords") or []
        coords = []
        for p in geom:
            if isinstance(p, dict) and "lat" in p and "lon" in p:
                coords.append([float(p["lat"]), float(p["lon"])])
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                la, lo = float(p[0]), float(p[1])
                coords.append([la, lo])
        if len(coords) >= 2:
            ways_map[wid] = coords
            tags = wd.get("tags") or wd
            attrs_map[wid] = {
                "name": (tags.get("name") or "").strip(),
                "ref":  (tags.get("ref") or "").strip(),
                "highway": (tags.get("highway") or "").strip(),
            }
    return ways_map, attrs_map


def _flatten_coords(coords):
    # Accept LineString [[x,y], ...] or MultiLineString [[[x,y],...], ...]
    if not coords:
        return []
    if isinstance(coords[0][0], (float, int)):  # LineString
        return coords
    flat = []
    for line in coords:  # MultiLineString
        flat.extend(line)
    return flat

def _lonlat_to_latlon(pt):
    # GeoJSON is [lon, lat]; we normalize to [lat, lon]
    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
        x, y = pt[0], pt[1]
        return [float(y), float(x)]
    return [float("nan"), float("nan")]

def _from_geojson_features(features):
    out = {}
    for i, feat in enumerate(features):
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        if gtype not in ("LineString", "MultiLineString"):
            continue
        way_id = str(
            feat.get("id")
            or feat.get("properties", {}).get("id")
            or feat.get("properties", {}).get("osm_id")
            or f"feat_{i}"
        )
        coords = geom.get("coordinates") or []
        out[way_id] = [_lonlat_to_latlon(p) for p in _flatten_coords(coords)]
    return out

def load_osm_cache_any(path: str) -> dict:
    """
    Return dict: {way_id(str): [[lat,lon], ...]} from several common formats:
      - {way_id: [[lat,lon], ...]}
      - GeoJSON FeatureCollection / list-of-Feature
      - list of dict entries with way_id/coords/geometry
      - Overpass JSON with {"elements":[...]} (ways + optional node table)
    """
    def _flatten_coords(coords):
        if not coords:
            return []
        # LineString [[x,y], ...] or MultiLineString [[[x,y],...], ...]
        if isinstance(coords[0][0], (float, int)):
            return coords
        flat = []
        for line in coords:
            flat.extend(line)
        return flat

    def _lonlat_to_latlon(pt):
        # GeoJSON is [lon,lat]; normalize to [lat,lon]
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x, y = pt[0], pt[1]
            return [float(y), float(x)]
        return [float("nan"), float("nan")]

    def _from_geojson_features(features):
        out = {}
        for i, feat in enumerate(features):
            if not isinstance(feat, dict):
                continue
            geom = feat.get("geometry") or {}
            gtype = geom.get("type")
            if gtype not in ("LineString", "MultiLineString"):
                continue
            way_id = str(
                feat.get("id")
                or feat.get("properties", {}).get("id")
                or feat.get("properties", {}).get("osm_id")
                or f"feat_{i}"
            )
            coords = geom.get("coordinates") or []
            out[way_id] = [_lonlat_to_latlon(p) for p in _flatten_coords(coords)]
        return out

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Case 1: mapping {way_id: [[lat,lon], ...]}
    if isinstance(data, dict) and data and isinstance(next(iter(data.values())), list) and "elements" not in data:
        norm = {}
        for k, v in data.items():
            if v and isinstance(v[0], (list, tuple)) and len(v[0]) >= 2:
                norm[str(k)] = [
                    _lonlat_to_latlon(p) if isinstance(p, (list, tuple)) else p
                    for p in v
                ]
        return norm

    # Case 2: GeoJSON FeatureCollection
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return _from_geojson_features(data.get("features", []))

    # Case 3: list of GeoJSON Features
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("type") == "Feature":
        return _from_geojson_features(data)

    # Case 4: generic list of entries (coords / geometry.coordinates / way_id)
    if isinstance(data, list):
        out = {}
        for i, e in enumerate(data):
            if not isinstance(e, dict):
                continue
            way_id = str(e.get("way_id") or e.get("id") or e.get("osm_id") or f"entry_{i}")
            coords = (
                e.get("coords")
                or (e.get("geometry") or {}).get("coordinates")
                or []
            )
            out[way_id] = [_lonlat_to_latlon(p) for p in _flatten_coords(coords)]
        # prune empties
        return {k: v for k, v in out.items() if v and len(v) >= 2}

    # Case 5: Overpass JSON with {"elements":[...]}
    if isinstance(data, dict) and "elements" in data and isinstance(data["elements"], list):
        elements = data["elements"]
        nodes = {}
        ways = {}

        # Build node table (if nodes present)
        for el in elements:
            if el.get("type") == "node" and "lat" in el and "lon" in el:
                nodes[el["id"]] = [float(el["lat"]), float(el["lon"])]

        # Extract ways
        for el in elements:
            if el.get("type") != "way":
                continue
            way_id = str(el.get("id", ""))
            coords = []
            if "geometry" in el and isinstance(el["geometry"], list) and el["geometry"]:
                # geometry = [{lat,lon}, ...] (requires 'out geom' in Overpass)
                for g in el["geometry"]:
                    if "lat" in g and "lon" in g:
                        coords.append([float(g["lat"]), float(g["lon"])])
            elif "nodes" in el and nodes:
                # resolve via node ids if node table is present
                for nid in el["nodes"]:
                    pt = nodes.get(nid)
                    if pt:
                        coords.append(pt)
            if len(coords) >= 2 and way_id:
                ways[way_id] = coords
        return ways

    raise ValueError("Unsupported osm_cache schema")

# ---- Label cache (lat,lon -> [group, level, name, facility]) ----
class LabelIndex:
    def __init__(self, m: dict[str, list]):
        # store both 1e-4 and 1e-3 rounded maps to be robust to key precision
        self.map4 = {}
        self.map3 = {}
        for k, v in m.items():
            try:
                la, lo = [float(x) for x in k.split(",")]
                self.map4[(round(la, 4), round(lo, 4))] = v
                self.map3[(round(la, 3), round(lo, 3))] = v
            except Exception:
                continue

    @staticmethod
    def from_json(path: str) -> "LabelIndex":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("label-cache must be a dict of 'lat,lon' -> [group, level, name, facility]")
        return LabelIndex(raw)

    def lookup(self, lat: float, lon: float):
        k4 = (round(float(lat), 4), round(float(lon), 4))
        v = self.map4.get(k4)
        if v is not None:
            return v
        # fallback to 1e-3 bin; try small neighborhood
        la3, lo3 = round(float(lat), 3), round(float(lon), 3)
        v = self.map3.get((la3, lo3))
        if v is not None:
            return v
        for dla in (-0.001, 0.0, 0.001):
            for dlo in (-0.001, 0.0, 0.001):
                v = self.map3.get((round(la3 + dla, 3), round(lo3 + dlo, 3)))
                if v is not None:
                    return v
        return None

# --------------------------- distance calculators -------------------------

KMH2MS = 1000.0 / 3600.0

@dataclass
class Metrics:
    n_points: int
    duration_s: float
    speed_integral_km: float
    haversine_min_km: float
    ellipsoid_min_km: Optional[float]
    haversine_path_km: float  # pure sum of haversine step lengths (no fallback)
    dt_stats: dict            # {'sum_s': float, 'median_s': float}
    haversine_caponly_km: float = 0.0
    ellipsoid_caponly_km: float = 0.0

def compute_metrics(df_slice: pd.DataFrame,
                    fallback_kph: float,
                    speed_spike_kph: Optional[float] = None,
                    gap_threshold_s: Optional[float] = None,
                    tunnel_freeze_min_speed_kph: Optional[float] = 15.0,
                    tunnel_freeze_eps_m: float = 2.0,
                    osm_index: Optional[OSMIndex] = None,
                    osm_snap_radius_m: float = 25.0) -> Metrics:
    ts  = df_slice["ts"].to_numpy()
    lat = df_slice["lat"].to_numpy()
    lon = df_slice["lon"].to_numpy()
    spd = df_slice["speed_kph"].to_numpy()

    if len(ts) < 2:
        return Metrics(n_points=len(ts), duration_s=0.0,
                       speed_integral_km=0.0, haversine_min_km=0.0,
                       ellipsoid_min_km=0.0, haversine_path_km=0.0,
                       dt_stats={"sum_s":0.0,"median_s":0.0},
                       haversine_caponly_km=0.0, ellipsoid_caponly_km=0.0)

    dt_s = np.diff(ts).astype("timedelta64[ns]").astype(np.int64) / 1e9
    dt_s = np.maximum(dt_s, 0.0)

    hv_m = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    hv_m = np.where(dt_s == 0.0, 0.0, hv_m)

    if _GEOD is not None:
        _, _, geo_m = _GEOD.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
    else:
        geo_m = hv_m.copy()

    with np.errstate(divide="ignore", invalid="ignore"):
        hv_speed_kph = (hv_m / 1000.0) / (dt_s / 3600.0)

    # 動的しきい値
    if gap_threshold_s is None:
        med = float(np.nanmedian(dt_s)) if dt_s.size else 0.0
        gap_threshold_s = max(5.0, 6.0 * med)
    if speed_spike_kph is None:
        speed_spike_kph = 200.0

    big_lat = np.abs(np.diff(lat)) > 0.20
    big_lon = np.abs(np.diff(lon)) > 0.20
    mask_absurd = (dt_s <= 10.0) & (big_lat | big_lon)

    mask_spike  = (dt_s > 0) & (hv_speed_kph > float(speed_spike_kph))
    mask_gap    = (dt_s > float(gap_threshold_s))
    if tunnel_freeze_min_speed_kph is not None:
        mask_frozen = (hv_m <= float(tunnel_freeze_eps_m)) & (spd[:-1] >= float(tunnel_freeze_min_speed_kph))
    else:
        mask_frozen = np.zeros_like(mask_gap, dtype=bool)
    mask_spike = mask_spike | mask_absurd

    hv_used_m  = hv_m.copy()
    geo_used_m = geo_m.copy()

    # まずスパイクのみを上限キャップ
    cap_m = float(speed_spike_kph) * 1000.0 * (dt_s / 3600.0)
    with np.errstate(invalid="ignore"):
        hv_used_m[mask_spike]  = np.minimum(hv_used_m[mask_spike],  cap_m[mask_spike])
        geo_used_m[mask_spike] = np.minimum(geo_used_m[mask_spike], cap_m[mask_spike])

    # 「キャップのみ」の集計（後で返す）
    hv_caponly_km  = float(np.nansum(hv_used_m)  / 1000.0)
    geo_caponly_km = float(np.nansum(geo_used_m) / 1000.0)

    # 次に gap/frozen/absurd の連続ブロックを置換（OSM優先、ダメなら速度積分の時間配分）
    runs = _find_runs(mask_gap | mask_frozen | mask_absurd)
    for i0, i1 in runs:
        dt_sum = float(np.nansum(dt_s[i0:i1+1]))
        if dt_sum <= 0.0:
            continue
        p0, p1 = i0, i1 + 1

        d_block_m = None
        # OSM同一路：両端が同一wayにスナップできたらその累積長差
        if osm_index is not None:

            s0 = osm_index.snap(float(lat[p0]), float(lon[p0]), float(osm_snap_radius_m))
            s1 = osm_index.snap(float(lat[p1]), float(lon[p1]), float(osm_snap_radius_m))
            if (s0 is not None) and (s1 is not None) and (s0.way_id == s1.way_id):
                d_block_m = abs(s1.s_m - s0.s_m)

        if d_block_m is None:
            step_speed_cap = np.minimum(spd[i0:i1+1], float(speed_spike_kph))
            d_block_m = float(np.nansum(step_speed_cap * 1000.0 * (dt_s[i0:i1+1] / 3600.0)))

        # ブロック全体のcap（時間×上限速度）
        cap_block_m = float(speed_spike_kph) * 1000.0 * (dt_sum / 3600.0)
        d_block_m = min(d_block_m, cap_block_m)

        w = (dt_s[i0:i1+1] / dt_sum)
        hv_used_m[i0:i1+1]  = d_block_m * w
        geo_used_m[i0:i1+1] = d_block_m * w

    speed_integral_km = float(np.nansum(spd[:-1] * (dt_s / 3600.0)))
    haversine_path_km = float(np.nansum(hv_m) / 1000.0)
    haversine_min_km  = float(np.nansum(hv_used_m) / 1000.0)
    ellipsoid_min_km  = float(np.nansum(geo_used_m) / 1000.0)

    duration_s = float((ts[-1] - ts[0]).astype("timedelta64[ns]").astype(np.int64) / 1e9)
    return Metrics(
        n_points=len(ts),
        duration_s=duration_s,
        speed_integral_km=speed_integral_km,
        haversine_min_km=haversine_min_km,
        ellipsoid_min_km=ellipsoid_min_km,
        haversine_path_km=haversine_path_km,
        dt_stats={"sum_s": float(np.nansum(dt_s)), "median_s": float(np.median(dt_s))},
        haversine_caponly_km=hv_caponly_km,
        ellipsoid_caponly_km=geo_caponly_km
    )

def stepwise_arrays(df: pd.DataFrame,
                    fallback_kph: float,
                    speed_spike_kph: Optional[float] = None,
                    gap_threshold_s: Optional[float] = None,
                    tunnel_freeze_min_speed_kph: Optional[float] = 15.0,
                    tunnel_freeze_eps_m: float = 2.0,
                    osm_index: Optional[OSMIndex] = None,
                    osm_snap_radius_m: float = 25.0,
                    osm_sameway_on: Optional[set] = None,
                    label_index: Optional["LabelIndex"] = None,
                    label_speeds: Optional[dict] = None):

    # 入力配列
    ts  = df["ts"].to_numpy()
    lat = df["lat"].to_numpy()
    lon = df["lon"].to_numpy()
    spd = df["speed_kph"].to_numpy()

    if speed_spike_kph is None:
        speed_spike_kph = float(fallback_kph)

    # 地表距離（先にhaversine）
    hv_m = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    if _GEOD is not None:
        _, _, geo_m = _GEOD.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
    else:
        geo_m = hv_m.copy()

    # 時間差と動的しきい値
    dt_s = np.diff(ts).astype("timedelta64[ns]").astype(np.int64) / 1e9
    dt_s = np.maximum(dt_s, 0.0)
    if gap_threshold_s is None:
        med = float(np.nanmedian(dt_s)) if dt_s.size else 0.0
        gap_threshold_s = max(5.0, 6.0 * med)

    with np.errstate(divide="ignore", invalid="ignore"):
        step_speed_kph = (hv_m / 1000.0) / (dt_s / 3600.0)

    big_lat = np.abs(np.diff(lat)) > 0.20
    big_lon = np.abs(np.diff(lon)) > 0.20
    mask_absurd = (dt_s <= 10.0) & (big_lat | big_lon)

    mask_spike  = (dt_s > 0) & (step_speed_kph > float(speed_spike_kph))
    mask_gap    = (dt_s > float(gap_threshold_s))
    if tunnel_freeze_min_speed_kph is not None:
        mask_frozen = (hv_m <= float(tunnel_freeze_eps_m)) & (spd[:-1] >= float(tunnel_freeze_min_speed_kph))
    else:
        mask_frozen = np.zeros_like(mask_gap, dtype=bool)
    mask_spike = mask_spike | mask_absurd

    hv_used_m  = hv_m.copy()
    geo_used_m = geo_m.copy()

    cap_m = float(speed_spike_kph) * 1000.0 * (dt_s / 3600.0)
    with np.errstate(invalid="ignore"):
        hv_used_m[mask_spike]  = np.minimum(hv_used_m[mask_spike],  cap_m[mask_spike])
        geo_used_m[mask_spike] = np.minimum(geo_used_m[mask_spike], cap_m[mask_spike])

    mask_osm_sameway = np.zeros_like(dt_s, dtype=bool)
    osm_used_m_total = 0.0
    osm_attempts = 0

    try_osm_flags = (osm_sameway_on or set())
    runs = _find_runs(mask_gap | mask_frozen | mask_absurd)
    for i0, i1 in runs:
        dt_sum = float(np.nansum(dt_s[i0:i1+1]))
        if dt_sum <= 0.0:
            continue
        p0, p1 = i0, i1 + 1
        d_block_m = None
        used_osm = False

        want_osm = (osm_index is not None) and (
            ("gap" in try_osm_flags and np.any(mask_gap[i0:i1+1])) or
            ("frozen" in try_osm_flags and np.any(mask_frozen[i0:i1+1])) or
            ("spike" in try_osm_flags and np.any(mask_spike[i0:i1+1]))
        )
        if want_osm:
            osm_attempts += 1
            s0 = osm_index.snap(float(lat[p0]), float(lon[p0]), float(osm_snap_radius_m))
            s1 = osm_index.snap(float(lat[p1]), float(lon[p1]), float(osm_snap_radius_m))
            if (s0 is not None) and (s1 is not None) and (s0.way_id == s1.way_id):
                d_block_m = abs(s1.s_m - s0.s_m)
                used_osm = True

        if d_block_m is None:
            step_speed_cap = np.minimum(spd[i0:i1+1], float(speed_spike_kph))
            d_block_m = float(np.nansum(step_speed_cap * 1000.0 * (dt_s[i0:i1+1] / 3600.0)))

        cap_block_m = float(speed_spike_kph) * 1000.0 * (dt_sum / 3600.0)
        d_block_m = min(d_block_m, cap_block_m)

        w = (dt_s[i0:i1+1] / dt_sum)
        hv_used_m[i0:i1+1]  = d_block_m * w
        geo_used_m[i0:i1+1] = d_block_m * w
        if used_osm:
            mask_osm_sameway[i0:i1+1] = True
            osm_used_m_total += d_block_m

    # 付帯情報（時刻・曜日・ラベル）
    ts0   = pd.to_datetime(ts[:-1])
    day   = ts0.floor("D")
    hour  = ts0.hour.to_numpy()
    dow   = ts0.dayofweek.to_numpy()

    label_group = np.array([], dtype=object)
    label_level = np.array([], dtype=object)
    label_name  = np.array([], dtype=object)
    label_fac   = np.array([], dtype=object)
    if label_index is not None and len(ts) >= 2:
        L = [label_index.lookup(float(lat[i]), float(lon[i])) for i in range(len(lat)-1)]
        def _col(j): return np.array([(v[j] if (v is not None and len(v) > j) else None) for v in L], dtype=object)
        label_group = _col(0); label_level = _col(1); label_name = _col(2); label_fac = _col(3)

    def _align_same_length(**arrs):
        lens = {k: len(v) for k, v in arrs.items() if v is not None}
        n = min(lens.values())
        bad = {k: l for k, l in lens.items() if l != n}
        return n, bad, {k: (v[:n] if v is not None else None) for k, v in arrs.items()}

    # Canonical step length
    n = int(min(
        len(dt_s),
        len(ts0),
        len(lat) - 1,
        len(lon) - 1,
        len(spd) - 1,
        len(hv_used_m),
        len(geo_used_m),
        len(mask_gap),
        len(mask_spike),
        len(mask_frozen),
    ))

    # Hard-trim EVERYTHING that is step-based to n
    dt_s        = dt_s[:n]
    ts0         = ts0[:n]
    day         = day[:n]
    hour        = hour[:n]
    dow         = dow[:n]

    lat0        = lat[:-1][:n]
    lon0        = lon[:-1][:n]
    speed_km    = (spd[:-1][:n] * (dt_s / 3600.0))

    hv_path_km  = (hv_m[:n] / 1000.0)
    hv_clamped_km = (hv_used_m[:n] / 1000.0)
    geo_clamped_km = (geo_used_m[:n] / 1000.0)

    mask_gap    = mask_gap[:n]
    mask_spike  = mask_spike[:n]
    mask_frozen = mask_frozen[:n]
    imputed_mask = (mask_gap | mask_spike | mask_frozen)

    mask_osm_sameway = mask_osm_sameway[:n] if len(mask_osm_sameway) else np.zeros(n, dtype=bool)

    # labels (only if present / correct length)
    def _trim_label(a):
        return a[:n] if (a is not None and len(a) >= n) else np.array([None]*n, dtype=object)

    label_group = _trim_label(label_group)
    label_level = _trim_label(label_level)
    label_name  = _trim_label(label_name)
    label_fac   = _trim_label(label_fac)

    return {
        "ts_start": pd.to_datetime(ts0).astype("datetime64[ns]"),
        "day": day,
        "hour": hour,
        "dow": dow,
        "lat0": lat0,
        "lon0": lon0,
        "dt_s": dt_s,
        "speed_km": speed_km,
        "hv_path_km": hv_path_km,
        "hv_clamped_km": hv_clamped_km,
        "geo_clamped_km": geo_clamped_km,
        "imputed_mask": imputed_mask,
        "mask_gap": mask_gap,
        "mask_spike": mask_spike,
        "mask_frozen": mask_frozen,
        "mask_osm_sameway": mask_osm_sameway,
        "osm_used_km": float(osm_used_m_total / 1000.0),
        "osm_attempted_steps": int(osm_attempts),
        "label_group": label_group,
        "label_level": label_level,
        "label_name":  label_name,
        "label_facility": label_fac,
    }



# ------------------------------ main routine ------------------------------

def make_df(rows: List[Row]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ts", "lat", "lon", "speed_kph"])
    df = pd.DataFrame(
        {
            "ts": [r.ts for r in rows],
            "lat": [r.lat for r in rows],
            "lon": [r.lon for r in rows],
            "speed_kph": [r.speed_kph for r in rows],
        }
    )
    df = df.dropna(subset=["ts", "lat", "lon"]).sort_values("ts").reset_index(drop=True)
    return df


def scan_files(root: Path, pattern: str) -> List[Path]:
    raw_pattern = str(pattern or "**/*.csv").strip()
    patterns: List[str] = []

    def _add_pattern(pat: str) -> None:
        pat = str(pat or "").strip()
        if pat and pat not in patterns:
            patterns.append(pat)

    normalized = raw_pattern.replace("\\", "/")
    _add_pattern(normalized)
    if normalized.endswith(".txt"):
        _add_pattern(normalized[:-4] + ".csv")
    elif normalized.endswith(".csv"):
        _add_pattern(normalized[:-4] + ".txt")

    seen: set[str] = set()
    files: List[Path] = []
    for pat in patterns:
        try:
            matches = sorted(root.glob(pat))
        except Exception:
            continue
        for p in matches:
            if not p.is_file():
                continue
            key = str(PureWindowsPath(p)).lower()
            if key in seen:
                continue
            seen.add(key)
            files.append(p)
    return sorted(files)


def load_manifest_files(manifest_path: Optional[str]) -> List[Path]:
    if not manifest_path:
        return []
    p = Path(manifest_path)
    if not p.exists():
        return []
    files: List[Path] = []
    seen: set[str] = set()
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []
    for raw in text.splitlines():
        line = _strip_hidden_text(raw)
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        fp = Path(line)
        key = str(PureWindowsPath(fp)).lower()
        if key in seen:
            continue
        seen.add(key)
        files.append(fp)
    return files


def _downsample_coords(coords, max_points: int):
    if not max_points or max_points <= 0:
        return coords
    n = len(coords)
    if n <= max_points:
        return coords
    import math
    step = int(math.ceil(n / float(max_points)))
    if step <= 1:
        return coords
    return coords[::step]


def export_routes_geojson(files: List[Path], out_dir: Path, max_points: int = 20000) -> None:
    """Export route polylines from trip logs.

    Writes:
      - routes_by_carweek.geojson (Feature per car_week; concatenated)
      - routes_by_car.geojson     (Feature per car_id; concatenated)
      - routes_by_scene.geojson   (Feature per scene/file; start→finish polyline of that scene)

    Geometry is LineString of [lon, lat]. Invalid points (NaN/out-of-range/0,0) are skipped.
    """
    import math
    import json
    import re
    from collections import defaultdict

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _is_valid(lon: float, lat: float) -> bool:
        if lon is None or lat is None:
            return False
        if not (math.isfinite(lon) and math.isfinite(lat)):
            return False
        if abs(lat) > 90.0 or abs(lon) > 180.0:
            return False
        # Treat (0,0) as invalid placeholder
        if abs(lat) < 1e-12 and abs(lon) < 1e-12:
            return False
        return True

    def _route_geo_km(rows_local: List[Row]) -> float:
        total_m = 0.0
        prev = None
        for rr in rows_local:
            if prev is not None:
                total_m += float(geod_m(prev.lat, prev.lon, rr.lat, rr.lon))
            prev = rr
        return total_m / 1000.0

    scene_re = re.compile(r"(\d{2}_\d{6}-\d{6}_Scene\d+)", re.IGNORECASE)
    scene_only_re = re.compile(r"(Scene\d+)", re.IGNORECASE)

    def infer_scene_key_from_path(p: Path) -> Optional[str]:
        s = str(p)
        m = scene_re.search(s)
        if m:
            return m.group(1)
        # fallback: build from car_week + SceneNN if available
        m2 = scene_only_re.search(p.stem)
        cw = infer_car_week_from_path(p)
        if cw and m2:
            return f"{cw}_{m2.group(1)}"
        return None

    by_cw = defaultdict(list)      # cw -> coords
    cw_files = defaultdict(int)    # cw -> n files
    cw_meta = defaultdict(lambda: {
        "route_geo_km": 0.0,
        "duration_h": 0.0,
        "scene_count": 0,
        "t_start": None,
        "t_end": None,
    })
    by_scene = {}                  # scene_key -> coords (one feature per scene)
    scene_meta = {}                # scene_key -> properties

    for fp in files:
        cw = infer_car_week_from_path(fp)
        if not cw:
            continue
        try:
            rows = parse_file_rows(fp)
        except Exception:
            continue
        if not rows:
            continue

        coords = []
        valid_rows = []
        last_lon = None
        last_lat = None
        for r in rows:
            lon = float(r.lon)
            lat = float(r.lat)
            if not _is_valid(lon, lat):
                continue
            valid_rows.append(r)
            if last_lon is not None and abs(lon - last_lon) < 1e-12 and abs(lat - last_lat) < 1e-12:
                continue
            coords.append([lon, lat])
            last_lon, last_lat = lon, lat

        if not coords or not valid_rows:
            continue

        cid = cw[:2] if len(cw) >= 2 else (infer_car_id_from_path(fp) or "UNK")
        route_geo_km = _route_geo_km(valid_rows)
        duration_h = 0.0
        if len(valid_rows) >= 2:
            duration_h = max(0.0, float((valid_rows[-1].ts - valid_rows[0].ts).total_seconds()) / 3600.0)
        t_start = valid_rows[0].ts.isoformat(sep=" ")
        t_end = valid_rows[-1].ts.isoformat(sep=" ")

        # per-scene route (start→finish for that incident file)
        scene_key = infer_scene_key_from_path(fp)
        if scene_key:
            # downsample the scene polyline to avoid huge HTML
            sc_coords = _downsample_coords(coords, max_points)
            by_scene[scene_key] = sc_coords
            scene_meta[scene_key] = {
                "scene_key": scene_key,
                "car_week": cw,
                "car_id": cid,
                "source_file": fp.name,
                "n_points": len(sc_coords),
                "route_geo_km": round(route_geo_km, 6),
                "duration_h": round(duration_h, 6),
                "t_start": t_start,
                "t_end": t_end,
            }

        # aggregate per car_week
        cw_files[cw] += 1
        by_cw[cw].extend(coords)
        meta_cw = cw_meta[cw]
        meta_cw["route_geo_km"] += route_geo_km
        meta_cw["duration_h"] += duration_h
        meta_cw["scene_count"] += 1
        meta_cw["t_start"] = t_start if (meta_cw["t_start"] is None or t_start < meta_cw["t_start"]) else meta_cw["t_start"]
        meta_cw["t_end"] = t_end if (meta_cw["t_end"] is None or t_end > meta_cw["t_end"]) else meta_cw["t_end"]
        if max_points and len(by_cw[cw]) > max_points * 3:
            by_cw[cw] = _downsample_coords(by_cw[cw], max_points * 2)

    # finalize downsample
    for cw in list(by_cw.keys()):
        by_cw[cw] = _downsample_coords(by_cw[cw], max_points)

    # build by-car by concatenation
    by_car = defaultdict(list)
    car_weeks = defaultdict(set)
    car_meta = defaultdict(lambda: {
        "route_geo_km": 0.0,
        "duration_h": 0.0,
        "scene_count": 0,
        "source_files": 0,
        "t_start": None,
        "t_end": None,
    })
    for cw, coords in by_cw.items():
        cid = cw[:2] if len(cw) >= 2 else (infer_car_id_from_path(Path(cw)) or "UNK")
        by_car[cid].extend(coords)
        car_weeks[cid].add(cw)
        meta_cw = cw_meta.get(cw, {})
        meta_car = car_meta[cid]
        meta_car["route_geo_km"] += float(meta_cw.get("route_geo_km") or 0.0)
        meta_car["duration_h"] += float(meta_cw.get("duration_h") or 0.0)
        meta_car["scene_count"] += int(meta_cw.get("scene_count") or 0)
        meta_car["source_files"] += int(cw_files.get(cw, 0))
        t_start = meta_cw.get("t_start")
        t_end = meta_cw.get("t_end")
        meta_car["t_start"] = t_start if (meta_car["t_start"] is None or (t_start and t_start < meta_car["t_start"])) else meta_car["t_start"]
        meta_car["t_end"] = t_end if (meta_car["t_end"] is None or (t_end and t_end > meta_car["t_end"])) else meta_car["t_end"]
        if max_points and len(by_car[cid]) > max_points * 4:
            by_car[cid] = _downsample_coords(by_car[cid], max_points * 2)

    for cid in list(by_car.keys()):
        by_car[cid] = _downsample_coords(by_car[cid], max_points)

    fc_cw = {"type": "FeatureCollection", "features": []}
    for cw in sorted(by_cw.keys()):
        coords = by_cw[cw]
        if len(coords) < 2:
            continue
        cid = cw[:2] if len(cw) >= 2 else "UNK"
        fc_cw["features"].append({
            "type": "Feature",
            "properties": {
                "car_week": cw,
                "car_id": cid,
                "n_points": len(coords),
                "source_files": cw_files.get(cw, 0),
                "scene_count": int(cw_meta.get(cw, {}).get("scene_count") or 0),
                "route_geo_km": round(float(cw_meta.get(cw, {}).get("route_geo_km") or 0.0), 6),
                "duration_h": round(float(cw_meta.get(cw, {}).get("duration_h") or 0.0), 6),
                "t_start": cw_meta.get(cw, {}).get("t_start"),
                "t_end": cw_meta.get(cw, {}).get("t_end"),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    fc_car = {"type": "FeatureCollection", "features": []}
    for cid in sorted(by_car.keys()):
        coords = by_car[cid]
        if len(coords) < 2:
            continue
        fc_car["features"].append({
            "type": "Feature",
            "properties": {
                "car_id": cid,
                "n_points": len(coords),
                "car_weeks": sorted(list(car_weeks.get(cid, set()))),
                "source_files": int(car_meta.get(cid, {}).get("source_files") or 0),
                "scene_count": int(car_meta.get(cid, {}).get("scene_count") or 0),
                "route_geo_km": round(float(car_meta.get(cid, {}).get("route_geo_km") or 0.0), 6),
                "duration_h": round(float(car_meta.get(cid, {}).get("duration_h") or 0.0), 6),
                "t_start": car_meta.get(cid, {}).get("t_start"),
                "t_end": car_meta.get(cid, {}).get("t_end"),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    fc_scene = {"type": "FeatureCollection", "features": []}
    for sk in sorted(by_scene.keys()):
        coords = by_scene[sk]
        if len(coords) < 2:
            continue
        props = dict(scene_meta.get(sk, {}))
        fc_scene["features"].append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    (out_dir / "routes_by_carweek.geojson").write_text(json.dumps(fc_cw, ensure_ascii=False), encoding="utf-8")
    (out_dir / "routes_by_car.geojson").write_text(json.dumps(fc_car, ensure_ascii=False), encoding="utf-8")
    (out_dir / "routes_by_scene.geojson").write_text(json.dumps(fc_scene, ensure_ascii=False), encoding="utf-8")

@dataclass
class Candidate:
    file: Path
    car_id: Optional[str]
    iA: int
    jB: int
    dA_m: float
    dB_m: float
    score_m: float
    n_points: int
    t_start: pd.Timestamp
    t_end: pd.Timestamp
    duration_s: float
    speed_integral_km: float
    haversine_min_km: float
    ellipsoid_min_km: Optional[float]
    haversine_caponly_km: float = 0.0
    ellipsoid_caponly_km: Optional[float] = 0.0


def main():
    ap = argparse.ArgumentParser(description="Find best A→B slice across trip files and compute distances.")
    ap.add_argument("--root", required=True, help="Root directory (can be UNC).")
    ap.add_argument("--glob", default="**/*.csv", help="Glob under root (default: **/*.csv)")
    ap.add_argument("--logs-manifest", default=None, help="Optional text file listing log paths (one CSV/TXT per line).")
    ap.add_argument("--a", required=False, help="A lat,lon (e.g., 35.46463,139.43556)")
    ap.add_argument("--b", required=False, help="B lat,lon (e.g., 35.35033,139.22489)")
    ap.add_argument("--radius-m", type=float, default=200.0, help="Landmark radius in meters (candidate window).")
    ap.add_argument("--fallback-kph", type=float, default=80.0, help="Fallback speed for gap/jump guard (km/h).")
    ap.add_argument("--car-id", default=None, help="Optional: only scan files whose inferred car id matches (e.g., 08).")
    ap.add_argument("--allowlist-carweek", default=None, help="Text file: one car_week per line (e.g., 06_241203-241207).")
    ap.add_argument("--routes-out", default=None, help="Directory to write routes_by_carweek.geojson and routes_by_car.geojson")
    ap.add_argument("--routes-only", action="store_true", help="Only export routes geojson and exit (skip totals / A->B).")
    ap.add_argument("--routes-max-points", type=int, default=20000, help="Max points per route (downsample).")
    ap.add_argument("--stitch-cross-files", action="store_true",
                    help="Enable cross-file stitching: pick A in file i and B in file j (j≥i) and stitch rows across files.")
    ap.add_argument("--stitch-score-mode", choices=["nearest","longest","balanced"], default="nearest",
                    help="How to choose A/B across files (default: nearest).")
    ap.add_argument("--stitch-balance-lambda", type=float, default=0.0,
                    help="Lambda for 'balanced' mode (score = dA+dB - lambda*minutes)")
    ap.add_argument("--outdir", default="./ab_out", help="Output directory.")
    ap.add_argument("--same-car-only", action="store_true",
                help="Only stitch A and B if both events are from the same car_id (recommended).")
    ap.add_argument("--max-span-min", type=float, default=None,
                    help="Max allowed span from A to B in minutes; pairs exceeding this are ignored.")
    ap.add_argument("--summarize-all", action="store_true",
                    help="Summarize distance/time over ALL trips (skip A→B).")
    ap.add_argument("--forbid-hdd-fallback", action="store_true",
                    help="If car_id cannot be taken from result_* pattern, do NOT fall back to HDD folder (use UNK).")
    ap.add_argument("--tunnel-freeze-min-speed-kph", type=float, default=15.0)
    ap.add_argument("--tunnel-freeze-eps-m", type=float, default=2.0)
    ap.add_argument("--gap-threshold-s", type=float, default=None,
                    help=("If dt exceeds this, treat it as a long gap (e.g., tunnel) and "
                        "force clamping by fallback. If omitted, use max(5s, 6×median(dt))."))
    ap.add_argument("--osm-cache", default=None,
                help="Path to osm_cache.json (ways with node geometry).")
    ap.add_argument("--osm-mode", choices=["off","sameway"], default="sameway",
                    help="Use OSM polyline distance when both step endpoints snap to the same way.")
    ap.add_argument("--osm-snap-radius-m", type=float, default=25.0,
                    help="Max distance to consider a point snapped onto a way.")
    ap.add_argument("--osm-grid-ddeg", type=float, default=0.01,
                    help="Spatial grid size in degrees for quick candidate lookup (≈1.1 km at equator).")
    ap.add_argument("--osm-sameway-on", default="frozen,gap",
                    help="Comma list from {frozen,gap,spike} selecting which imputed steps try OSM same-way distance.")
    ap.add_argument("--label-cache", default=None,
        help="Path to osm_label_cache.json (lat,lon -> [group, level, name, facility]).")
    ap.add_argument("--label-speeds", default="Highway=100,National=80,Prefectural=60,Local=40",
        help="Comma list mapping group->kph, e.g. 'Highway=100,National=80,Prefectural=60,Local=40'")
    ap.add_argument("--freeze-min-seconds", type=float, default=180.0)
    ap.add_argument("--require-wgs84", action="store_true",
                help="Fail if pyproj.Geod (WGS84) is unavailable.")
    ap.add_argument("--stop-kph", type=float, default=1.0,
                    help="Speed threshold to count 'stopped' time (kph).")
    ap.add_argument("--speed-spike-kph", type=float, default=200.0,
                    help="Treat implied step speeds above this as spikes (default: 200 kph).")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Exclude any file whose path contains this substring (repeatable)")
    ap.add_argument("--emit-annotations-csv", action="store_true",
                    help="Write per-step annotations (ts_start, car_id, hour, label_*, lat/lon) to step_annotations.csv")
    ap.add_argument("--only-e1a", action="store_true",
                help="OSMでE1A/新東名にスナップできたステップのみを距離集計に使う")
    ap.add_argument("--e1a-snap-required", dest="e1a_snap_required",
                    action="store_true", default=True,
                    help="(default) --only-e1a: require OSM snap else exclude step")
    ap.add_argument("--allow-unsnapped", dest="e1a_snap_required",
                    action="store_false",
                    help="--only-e1a: allow unsnapped steps (keep distance)")
    
    args = ap.parse_args()

    if args.require_wgs84 and _GEOD is None:
        print("[error] --require-wgs84 set but pyproj.Geod unavailable. Install pyproj.", file=sys.stderr)
        sys.exit(2)

    # Build OSM index if requested
    osm_index = None
    if getattr(args, "osm_cache", None):
        try:
            ways_map, attrs_map = load_osm_cache_with_attrs(args.osm_cache)
            # Guard: --only-e1a needs tags (ref/name/highway). If cache has geometry only, filtering is impossible.
            if args.only_e1a and (not attrs_map) :
                print('[error] --only-e1a was requested, but the OSM cache has no tags/attributes.\n'
                              '        Use an Overpass JSON cache that contains elements[].tags (ref/name/highway),\n'
                              '        or re-export/merge your cache while preserving tags.\n'
                              '        Quick workaround: remove --only-e1a (will include non-E1A roads).')
                raise SystemExit(2)
            
            ways_list = []
            kept = 0
            skipped = 0

            for way_id, coords in ways_map.items():
                if not coords or len(coords) < 2:
                    continue

                meta = attrs_map.get(str(way_id), {})

                # If user wants E1A-only index, keep only E1A/新東名 ways
                if args.only_e1a and (not _is_e1a(meta)):
                    skipped += 1
                    continue

                lats = np.asarray([c[0] for c in coords], dtype=float)
                lons = np.asarray([c[1] for c in coords], dtype=float)

                if _GEOD is not None:
                    _, _, seg_m = _GEOD.inv(lons[:-1], lats[:-1], lons[1:], lats[1:])
                else:
                    seg_m = haversine_m(lats[:-1], lons[:-1], lats[1:], lons[1:])

                cumlen = np.r_[0.0, np.cumsum(seg_m)]
                bbox = (float(lats.min()), float(lons.min()), float(lats.max()), float(lons.max()))

                ways_list.append(_OSMWay(
                    int(way_id) if str(way_id).isdigit() else way_id,
                    lats, lons, cumlen, bbox,
                    name=meta.get("name", ""),
                    ref=meta.get("ref", ""),
                    highway=meta.get("highway", ""),
                ))
                kept += 1

            osm_index = OSMIndex(ways_list, grid_ddeg=args.osm_grid_ddeg)
            print(f"[ok] OSM index ready: kept={kept}, skipped={skipped}, grid={args.osm_grid_ddeg}°")

        except Exception as e:
            print(f"[warn] Failed to build OSM index: {e}")
            osm_index = None

    def build_e1a_step_mask(A, args, osm_index, snap_cached):
        """
        Return boolean mask for steps (len = len(A["dt_s"])) indicating E1A/新東名.
        If osm_index is None -> all False (cannot classify).
        If snap is None:
        - args.e1a_snap_required True  -> False
        - args.e1a_snap_required False -> True  (treat unsnapped as keep)
        """
        n = int(len(A["dt_s"]))
        if n <= 0:
            return np.zeros(0, dtype=bool)

        if osm_index is None:
            return np.zeros(n, dtype=bool)

        lat0 = A["lat0"]; lon0 = A["lon0"]
        mask = np.zeros(n, dtype=bool)

        for i_step in range(n):
            lat_r = int(round(float(lat0[i_step]) * 1e5))
            lon_r = int(round(float(lon0[i_step]) * 1e5))
            snap = snap_cached(lat_r, lon_r, float(args.osm_snap_radius_m))

            if snap is None:
                mask[i_step] = (not args.e1a_snap_required)
                continue

            meta = osm_index.get_meta(snap.way_id)
            mask[i_step] = _is_e1a(meta)

        return mask

    def apply_step_mask(A, m):
        """Return a shallow copy of step arrays filtered by mask m (len dt_s)."""
        out = dict(A)
        # arrays with step length n
        keys = [
            "dt_s","speed_km","hv_path_km","hv_clamped_km","geo_clamped_km",
            "imputed_mask","mask_gap","mask_spike","mask_frozen","mask_osm_sameway",
            "lat0","lon0","hour","dow","day","ts_start",
            "label_group","label_level","label_name","label_facility",
        ]
        for k in keys:
            if k in out and len(out[k]) == len(m):
                out[k] = out[k][m]
        # scalar stats remain as-is
        return out


    # Build LabelIndex (optional)
    label_index = None
    label_speeds = {"Highway": 100.0, "National": 80.0, "Prefectural": 60.0, "Local": 40.0}
    if getattr(args, "label_speeds", None):
        try:
            tmp = {}
            for part in (args.label_speeds or "").split(","):
                if not part.strip():
                    continue
                k, v = part.split("=")
                tmp[k.strip()] = float(v.strip())
            if tmp:
                label_speeds = tmp
        except Exception as e:
            print(f"[warn] failed to parse --label-speeds: {e} (using defaults)")
    if getattr(args, "label_cache", None):
        try:
            label_index = LabelIndex.from_json(args.label_cache)
            print(f"[ok] Label cache ready: ~{len(label_index.map4)} keys (1e-4 grid)")
        except Exception as e:
            print(f"[warn] Failed to load label cache: {e}")
            label_index = None


    # Respect --osm-mode
    if args.osm_mode == "off":
        osm_index = None

    # Which imputed categories should try OSM same-way replacement
    _osm_sameway_on = set([s.strip().lower() for s in (args.osm_sameway_on or "").split(",") if s.strip()])

    @lru_cache(maxsize=500_000)
    def snap_cached(lat_r: int, lon_r: int, max_dist_m: float):
        lat = lat_r / 1e5
        lon = lon_r / 1e5
        return osm_index.snap(lat, lon, max_dist_m) if osm_index else None

    root = Path(args.root)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    files = load_manifest_files(getattr(args, "logs_manifest", None))
    if files:
        print(f"[info] logs-manifest applied: {len(files)} files")
    else:
        files = scan_files(root, args.glob)
        if not files:
            print(f"[warn] no files matched root/glob: {root} / {args.glob}")
    if args.car_id is not None:
        files = [p for p in files if infer_car_id_from_path(p) == args.car_id]

    if args.max_span_min is not None and args.max_span_min <= 0:
        args.max_span_min = None

    if args.exclude:
        def _norm(p: Path) -> str:
            return str(PureWindowsPath(p)).lower()
        excl = [s.lower() for s in args.exclude]
        files = [p for p in files if not any(x in _norm(p) for x in excl)]

    # allowlist by car_week (e.g., '06_241203-241207')
    allow_cw = read_allowlist_carweek(getattr(args, 'allowlist_carweek', None))
    if allow_cw is not None:
        before = len(files)
        files = [p for p in files if (infer_car_week_from_path(p) in allow_cw)]
        after = len(files)
        print(f'[info] allowlist-carweek applied: {before} -> {after} files')

    # routes-only mode: export routes then exit
    if getattr(args, 'routes_only', False):
        if not getattr(args, 'routes_out', None):
            raise SystemExit('[error] --routes-only requires --routes-out <dir>')
        export_routes_geojson(files, Path(args.routes_out), max_points=int(getattr(args, 'routes_max_points', 20000) or 0))
        print('[ok] routes exported (routes-only)')
        return

    if args.summarize_all:
        from collections import defaultdict

        def _span_from_steps(A):
            n = int(len(A["dt_s"]))
            if n <= 0:
                return 0.0
            t0 = pd.Timestamp(A["ts_start"][0])
            t1 = pd.Timestamp(A["ts_start"][-1]) + pd.to_timedelta(float(A["dt_s"][-1]), unit="s")
            return float((t1 - t0).total_seconds())

        def _accumulate_car_and_total(by_car_dst, total_dst, A_use, car_id_eff, df_for_rows):
            if A_use is None or len(A_use.get("dt_s", [])) == 0:
                return

            dt_sum_s = float(np.nansum(A_use["dt_s"]))
            t_span_s = _span_from_steps(A_use)

            frozen_time_s = float(np.nansum(A_use["dt_s"][A_use["mask_frozen"]]))
            gap_time_s    = float(np.nansum(A_use["dt_s"][A_use["mask_gap"]]))

            valid = (A_use["dt_s"] > 0) & np.isfinite(A_use["dt_s"]) & np.isfinite(A_use["speed_km"])
            speed_step_kph = np.divide(
                A_use["speed_km"],
                (A_use["dt_s"] / 3600.0),
                out=np.zeros_like(A_use["dt_s"], dtype=float),
                where=valid
            )
            stopped_mask = speed_step_kph <= args.stop_kph
            active_mask  = ~stopped_mask
            stopped_s = float(np.nansum(A_use["dt_s"][stopped_mask]))
            active_s  = float(np.nansum(A_use["dt_s"][active_mask]))

            mask = A_use["imputed_mask"]
            mask_gap   = A_use["mask_gap"]
            mask_spike = A_use["mask_spike"]
            mask_frozen = A_use["mask_frozen"]

            steps = int(A_use["dt_s"].size)
            steps_imputed = int(np.count_nonzero(mask))
            steps_gap = int(np.count_nonzero(mask_gap))
            steps_spike = int(np.count_nonzero(mask_spike))
            steps_frozen = int(np.count_nonzero(mask_frozen))

            dist_speed_km = float(np.nansum(A_use["speed_km"]))
            dist_hv_path_km = float(np.nansum(A_use["hv_path_km"]))
            dist_hv_clamped_km = float(np.nansum(A_use["hv_clamped_km"]))
            dist_geo_clamped_km = float(np.nansum(A_use["geo_clamped_km"]))

            imputed_km = float(np.nansum(A_use["hv_clamped_km"][mask]))
            removed_km = float(np.nansum(np.maximum(0.0, (A_use["hv_path_km"] - A_use["hv_clamped_km"])[mask])))
            replaced_km_val = -removed_km

            tunnel_km = float(np.nansum(A_use["hv_clamped_km"][mask_gap]))
            spike_km  = float(np.nansum(A_use["hv_clamped_km"][mask_spike]))

            removed_km_tunnel = float(np.nansum(np.maximum(0.0, (A_use["hv_path_km"] - A_use["hv_clamped_km"])[mask_gap])))
            removed_km_spike  = float(np.nansum(np.maximum(0.0, (A_use["hv_path_km"] - A_use["hv_clamped_km"])[mask_spike])))

            frozen_km = float(np.nansum(A_use["hv_clamped_km"][mask_frozen]))
            removed_km_frozen = float(np.nansum(np.maximum(0.0, (A_use["hv_path_km"] - A_use["hv_clamped_km"])[mask_frozen])))

            steps_osm_sameway = int(np.count_nonzero(A_use.get("mask_osm_sameway", np.zeros(0, dtype=bool))))
            osm_used_km = float(A_use.get("osm_used_km", 0.0))

            cid = car_id_eff or ""

            C = by_car_dst[cid]
            C["files"] += 1
            C["rows"] += len(df_for_rows)
            C["time_s"] += dt_sum_s
            C["dist_speed_km"] += dist_speed_km
            C["dist_hv_path_km"] += dist_hv_path_km
            C["dist_hv_clamped_km"] += dist_hv_clamped_km
            C["dist_geo_clamped_km"] += dist_geo_clamped_km
            C["steps"] += steps
            C["steps_imputed"] += steps_imputed
            C["imputed_km"] += imputed_km
            C["removed_km"] += removed_km
            C["replaced_km"] += replaced_km_val
            C["steps_gap"] += steps_gap
            C["steps_spike"] += steps_spike
            C["tunnel_km"] += tunnel_km
            C["spike_km"] += spike_km
            C["removed_km_tunnel"] += removed_km_tunnel
            C["removed_km_spike"] += removed_km_spike
            C["steps_osm_sameway"] += steps_osm_sameway
            C["osm_used_km"] += osm_used_km
            C["steps_frozen"] += steps_frozen
            C["frozen_km"] += frozen_km
            C["removed_km_frozen"] += removed_km_frozen
            C["time_stopped_s"] += stopped_s
            C["time_active_s"] += active_s
            C["time_frozen_s"] += frozen_time_s
            C["time_gap_s"] += gap_time_s
            C["time_span_s"] += t_span_s

            total_dst["time_s"] += dt_sum_s
            total_dst["dist_speed_km"] += dist_speed_km
            total_dst["dist_hv_path_km"] += dist_hv_path_km
            total_dst["dist_hv_clamped_km"] += dist_hv_clamped_km
            total_dst["dist_geo_clamped_km"] += dist_geo_clamped_km
            total_dst["steps"] += steps
            total_dst["steps_imputed"] += steps_imputed
            total_dst["imputed_km"] += imputed_km
            total_dst["removed_km"] += removed_km
            total_dst["replaced_km"] += replaced_km_val
            total_dst["steps_gap"] += steps_gap
            total_dst["steps_spike"] += steps_spike
            total_dst["tunnel_km"] += tunnel_km
            total_dst["spike_km"] += spike_km
            total_dst["removed_km_tunnel"] += removed_km_tunnel
            total_dst["removed_km_spike"] += removed_km_spike
            total_dst["steps_osm_sameway"] += steps_osm_sameway
            total_dst["osm_used_km"] += osm_used_km
            total_dst["steps_frozen"] += steps_frozen
            total_dst["frozen_km"] += frozen_km
            total_dst["removed_km_frozen"] += removed_km_frozen
            total_dst["time_stopped_s"] += stopped_s
            total_dst["time_active_s"] += active_s
            total_dst["time_frozen_s"] += frozen_time_s
            total_dst["time_gap_s"] += gap_time_s
            total_dst["time_span_s"] += t_span_s


        by_car = defaultdict(lambda: {
            "files": 0, "rows": 0,
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0,
            "dist_hv_clamped_km": 0.0,
            "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0,
            "imputed_km": 0.0,
            "removed_km": 0.0,        # total removed (gap+spike)
            "replaced_km": 0.0,       # compat (-removed_km)

            # NEW: split by cause
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            # NEW: OSM / frozen / time split
            "steps_osm_sameway": 0,
            "osm_used_km": 0.0,
            "steps_frozen": 0,
            "frozen_km": 0.0,
            "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0,
            "time_active_s": 0.0,
            "time_frozen_s": 0.0,
            "time_gap_s": 0.0,
            "time_span_s": 0.0,
        })

        by_way = defaultdict(lambda: {
            "name": "", "ref": "", "highway": "",
            "duration_s": 0.0, "dist_hv_clamped_km": 0.0,
            "steps": 0,
            "cars": set(),
            "t_first": None,
            "t_last": None,
        })

        by_car_way = defaultdict(lambda: {
            "name": "", "ref": "", "highway": "",
            "duration_s": 0.0, "dist_hv_clamped_km": 0.0,
            "steps": 0, "t_first": None, "t_last": None,
        })

        by_hour = defaultdict(lambda: {
            "time_s": 0.0, "dist_speed_km": 0.0, "dist_hv_clamped_km": 0.0, "steps": 0
        })
        by_car_hour = defaultdict(lambda: {
            "time_s": 0.0, "dist_speed_km": 0.0, "dist_hv_clamped_km": 0.0, "steps": 0
        })
        by_label = defaultdict(lambda: {
            "time_s": 0.0, "dist_speed_km": 0.0, "dist_hv_clamped_km": 0.0, "dist_geo_clamped_km": 0.0, "steps": 0,
            "steps_imputed": 0, "imputed_km": 0.0, "frozen_km": 0.0, "time_gap_s": 0.0, "time_frozen_s": 0.0,
            "group": "", "level": ""
        })
        by_car_label = defaultdict(lambda: {
            "time_s": 0.0, "dist_speed_km": 0.0, "dist_hv_clamped_km": 0.0, "dist_geo_clamped_km": 0.0, "steps": 0,
            "steps_imputed": 0, "imputed_km": 0.0, "frozen_km": 0.0, "time_gap_s": 0.0, "time_frozen_s": 0.0
        })

        ann_rows = [] if args.emit_annotations_csv else None

        by_day = defaultdict(lambda: {
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_clamped_km": 0.0
        })
        by_car_day = defaultdict(lambda: {
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_clamped_km": 0.0
        })

        by_car_e1a = defaultdict(lambda: {
            "files": 0, "rows": 0,
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0,
            "dist_hv_clamped_km": 0.0,
            "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0,
            "imputed_km": 0.0,
            "removed_km": 0.0,
            "replaced_km": 0.0,
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            "steps_osm_sameway": 0, "osm_used_km": 0.0,
            "steps_frozen": 0, "frozen_km": 0.0, "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0, "time_active_s": 0.0,
            "time_frozen_s": 0.0, "time_gap_s": 0.0,
            "time_span_s": 0.0,
        })

        total_e1a = {
            "time_s": 0.0, "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0, "dist_hv_clamped_km": 0.0, "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0, "imputed_km": 0.0,
            "removed_km": 0.0, "replaced_km": 0.0,
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            "steps_osm_sameway": 0, "osm_used_km": 0.0,
            "steps_frozen": 0, "frozen_km": 0.0, "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0, "time_active_s": 0.0,
            "time_frozen_s": 0.0, "time_gap_s": 0.0,
            "time_span_s": 0.0,
        }



        # NEW: per car-week totals (key like '02_241007-241011')
        by_carweek = defaultdict(lambda: {
            "files": 0, "rows": 0,
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0,
            "dist_hv_clamped_km": 0.0,
            "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0,
            "imputed_km": 0.0,
            "removed_km": 0.0,
            "replaced_km": 0.0,
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            "frozen_s": 0.0,
            "t_first": None, "t_last": None,
            # NEW: OSM / frozen / time split
            "steps_osm_sameway": 0,
            "osm_used_km": 0.0,
            "steps_frozen": 0,
            "frozen_km": 0.0,
            "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0,
            "time_active_s": 0.0,
            "time_frozen_s": 0.0,
            "time_gap_s": 0.0,
            "time_span_s": 0.0,
        })
        by_carweek_car = defaultdict(lambda: {
            "files": 0, "rows": 0,
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0,
            "dist_hv_clamped_km": 0.0,
            "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0,
            "imputed_km": 0.0,
            "removed_km": 0.0,
            "replaced_km": 0.0,
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            "frozen_s": 0.0,
            "t_first": None, "t_last": None,
            "steps_osm_sameway": 0,
            "osm_used_km": 0.0,
            "steps_frozen": 0,
            "frozen_km": 0.0,
            "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0,
            "time_active_s": 0.0,
            "time_frozen_s": 0.0,
            "time_gap_s": 0.0,
            "time_span_s": 0.0,
        })
        total_carweek_car = {
            "files": 0, "rows": 0,
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0,
            "dist_hv_clamped_km": 0.0,
            "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0,
            "imputed_km": 0.0,
            "removed_km": 0.0,
            "replaced_km": 0.0,
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            "frozen_s": 0.0,
            "steps_osm_sameway": 0,
            "osm_used_km": 0.0,
            "steps_frozen": 0,
            "frozen_km": 0.0,
            "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0,
            "time_active_s": 0.0,
            "time_frozen_s": 0.0,
            "time_gap_s": 0.0,
            "time_span_s": 0.0,
        }
        total_carweek = {
            "files": 0, "rows": 0,
            "time_s": 0.0,
            "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0,
            "dist_hv_clamped_km": 0.0,
            "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0,
            "imputed_km": 0.0,
            "removed_km": 0.0,
            "replaced_km": 0.0,
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            "frozen_s": 0.0,
            # NEW: OSM / frozen / time split
            "steps_osm_sameway": 0,
            "osm_used_km": 0.0,
            "steps_frozen": 0,
            "frozen_km": 0.0,
            "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0,
            "time_active_s": 0.0,
            "time_frozen_s": 0.0,
            "time_gap_s": 0.0,
            "time_span_s": 0.0,
        }
        by_carweek_label = defaultdict(lambda: {
            "time_s": 0.0, "dist_speed_km": 0.0, "dist_hv_clamped_km": 0.0, "dist_geo_clamped_km": 0.0, "steps": 0,
            "steps_imputed": 0, "imputed_km": 0.0, "frozen_km": 0.0, "time_gap_s": 0.0, "time_frozen_s": 0.0
        })
        by_carweek_car_label = defaultdict(lambda: {
            "time_s": 0.0, "dist_speed_km": 0.0, "dist_hv_clamped_km": 0.0, "dist_geo_clamped_km": 0.0, "steps": 0,
            "steps_imputed": 0, "imputed_km": 0.0, "frozen_km": 0.0, "time_gap_s": 0.0, "time_frozen_s": 0.0
        })


        total = {
            "time_s": 0.0, "dist_speed_km": 0.0,
            "dist_hv_path_km": 0.0, "dist_hv_clamped_km": 0.0, "dist_geo_clamped_km": 0.0,
            "steps": 0, "steps_imputed": 0, "imputed_km": 0.0,
            "removed_km": 0.0, "replaced_km": 0.0,

            # NEW: split by cause
            "steps_gap": 0, "steps_spike": 0,
            "tunnel_km": 0.0, "spike_km": 0.0,
            "removed_km_tunnel": 0.0, "removed_km_spike": 0.0,
            # NEW: OSM / frozen / time split
            "steps_osm_sameway": 0,
            "osm_used_km": 0.0,
            "steps_frozen": 0,
            "frozen_km": 0.0,
            "removed_km_frozen": 0.0,
            "time_stopped_s": 0.0,
            "time_active_s": 0.0,
            "time_frozen_s": 0.0,
            "time_gap_s": 0.0,
            "time_span_s": 0.0,
        }

        audit_rows = []

        for i, fpath in enumerate(files, 1):
            if i % 200 == 0:
                print(f"[progress] {i}/{len(files)} ... {PureWindowsPath(fpath)}", flush=True)
            try:
                df = load_df_cached(fpath)
                if df.empty or len(df) < 2:
                    continue

                # Resolve car_id (also keep raw/source for audit)
                car_id_raw, cid_source = infer_car_id_with_source(fpath)
                car_id_eff = car_id_raw
                if getattr(args, "forbid_hdd_fallback", False) and cid_source != "result":
                    car_id_eff = "UNK"

                car_week = infer_car_week_from_path(fpath) or "UNK"

                # Step arrays (TOTAL)
                A_total = stepwise_arrays(
                    df,
                    fallback_kph=args.fallback_kph,
                    speed_spike_kph=(args.speed_spike_kph or args.fallback_kph),
                    gap_threshold_s=args.gap_threshold_s,
                    tunnel_freeze_min_speed_kph=args.tunnel_freeze_min_speed_kph,
                    tunnel_freeze_eps_m=args.tunnel_freeze_eps_m,
                    osm_index=osm_index,
                    osm_snap_radius_m=args.osm_snap_radius_m,
                    osm_sameway_on=_osm_sameway_on,
                    label_index=label_index,
                    label_speeds=label_speeds,
                )

                # Build E1A mask + slice
                e1a_mask = build_e1a_step_mask(A_total, args, osm_index, snap_cached)
                A_e1a = apply_step_mask(A_total, e1a_mask)

                # Primary scope behavior (keep legacy)
                # --only-e1a: primary = E1A, else primary = TOTAL
                A = A_e1a if args.only_e1a else A_total

                # --- Per-way 集計（各ステップを最近傍wayへスナップ） ---
                if osm_index is not None:
                    dt_s  = A["dt_s"]
                    hv_km = A["hv_clamped_km"]  # 走行距離はクランプ後を採用
                    lat0  = A["lat0"]
                    lon0  = A["lon0"]

                    for i_step in range(len(dt_s)):
                        if not np.isfinite(dt_s[i_step]) or dt_s[i_step] <= 0.0:
                            continue

                        # (optional) skip zero distance steps early
                        if not np.isfinite(hv_km[i_step]) or hv_km[i_step] <= 0.0:
                            continue

                        lat_r = int(round(float(lat0[i_step]) * 1e5))
                        lon_r = int(round(float(lon0[i_step]) * 1e5))
                        snap = snap_cached(lat_r, lon_r, float(args.osm_snap_radius_m)) if osm_index else None

                        if snap is None:
                            if args.only_e1a and args.e1a_snap_required:
                                continue
                            # allow-unsnapped: we keep distance in totals_by_car etc. already,
                            # but we cannot attribute to a way, so just skip by_way/by_car_way
                            continue

                        wid  = snap.way_id
                        meta = osm_index.get_meta(wid)

                        wid  = snap.way_id
                        key  = osm_index.way_key(wid)    # name > ref > way:<id>
                        meta = osm_index.get_meta(wid)

                        W = by_way[key]
                        if not W["name"]:    W["name"]    = meta.get("name", "")
                        if not W["ref"]:     W["ref"]     = meta.get("ref", "")
                        if not W["highway"]: W["highway"] = meta.get("highway", "")
                        W["duration_s"]          += float(dt_s[i_step])
                        W["dist_hv_clamped_km"]  += float(hv_km[i_step])
                        W["steps"]               += 1
                        if car_id_eff:
                            W["cars"].add(car_id_eff)
                            t_cur = df["ts"].iat[i_step]
                            if W["t_first"] is None or t_cur < W["t_first"]:
                                W["t_first"] = t_cur
                            if W["t_last"] is None or t_cur > W["t_last"]:
                                W["t_last"] = t_cur

                        CW = by_car_way[(car_id_eff or "", key)]
                        if not CW["name"]:    CW["name"]    = W["name"]
                        if not CW["ref"]:     CW["ref"]     = W["ref"]
                        if not CW["highway"]: CW["highway"] = W["highway"]
                        CW["duration_s"]         += float(dt_s[i_step])
                        CW["dist_hv_clamped_km"] += float(hv_km[i_step])
                        CW["steps"]              += 1
                        t_cur = df["ts"].iat[i_step]
                        if CW["t_first"] is None or t_cur < CW["t_first"]:
                            CW["t_first"] = t_cur
                        if CW["t_last"] is None or t_cur > CW["t_last"]:
                            CW["t_last"] = t_cur

                dt_sum_s = float(np.nansum(A["dt_s"]))
                t_span_s = float((df["ts"].iat[-1] - df["ts"].iat[0]).total_seconds())

                # Per-car (keyed by effective id) — define C BEFORE using it
                C = by_car[car_id_eff or ""]

                # NEW: per car-week totals
                CW = by_carweek[car_week or ""]
                _accumulate_car_and_total(by_carweek, total_carweek, A_total, (car_week or ""), df)
                combo_key = f"{car_week or ''}__{car_id_eff or ''}"
                _accumulate_car_and_total(by_carweek_car, total_carweek_car, A_total, combo_key, df)

                # Dual accumulation:
                # - totals (not filtered): by_car / total は既存のまま（primaryの集計に使っている）
                # - E1A filtered: by_car_e1a / total_e1a を追加で更新する
                _accumulate_car_and_total(by_car_e1a, total_e1a, A_e1a, car_id_eff, df)

                # Accumulate wall-clock span separate from integrated time
                C["time_span_s"]    = C.get("time_span_s", 0.0) + t_span_s
                total["time_span_s"] = total.get("time_span_s", 0.0) + t_span_s

                frozen_time_s = float(np.nansum(A["dt_s"][A["mask_frozen"]]))
                gap_time_s    = float(np.nansum(A["dt_s"][A["mask_gap"]]))

                # --- Frozen metrics (GPS frozen, speed says moving)
                mask_frozen = A["mask_frozen"]
                steps_frozen = int(np.count_nonzero(mask_frozen))
                frozen_km = float(np.nansum(A["hv_clamped_km"][mask_frozen]))
                removed_km_frozen = float(np.nansum(
                    np.maximum(0.0, (A["hv_path_km"] - A["hv_clamped_km"])[mask_frozen])
                ))

                # --- Stop/Active time split
                # reconstruct per-step speed (kph) robustly
                valid = (A["dt_s"] > 0) & np.isfinite(A["dt_s"]) & np.isfinite(A["speed_km"])
                speed_step_kph = np.divide(
                    A["speed_km"],
                    (A["dt_s"] / 3600.0),
                    out=np.zeros_like(A["dt_s"], dtype=float),
                    where=valid
                )
                stopped_mask = speed_step_kph <= args.stop_kph
                active_mask  = ~stopped_mask

                stopped_s = float(np.nansum(A["dt_s"][stopped_mask]))
                active_s  = float(np.nansum(A["dt_s"][active_mask]))

                # Aggregates
                time_s = dt_sum_s
                dist_speed_km = float(np.nansum(A["speed_km"]))
                dist_hv_path_km = float(np.nansum(A["hv_path_km"]))
                dist_hv_clamped_km = float(np.nansum(A["hv_clamped_km"]))
                dist_geo_clamped_km = float(np.nansum(A["geo_clamped_km"]))
                steps = int(A["dt_s"].size)
                mask = A["imputed_mask"]
                steps_imputed = int(np.count_nonzero(mask))
                imputed_km = float(np.nansum(A["hv_clamped_km"][mask]))  # kept distance after guard
                removed_km = float(np.nansum(np.maximum(
                    0.0, (A["hv_path_km"] - A["hv_clamped_km"])[mask]
                )))  # positive distance we cut away
                replaced_km_val = -removed_km  # compatibility

                # --- NEW: split imputation by cause
                mask_gap   = A["mask_gap"]
                mask_spike = A["mask_spike"]

                steps_gap   = int(np.count_nonzero(mask_gap))
                steps_spike = int(np.count_nonzero(mask_spike))

                tunnel_km = float(np.nansum(A["hv_clamped_km"][mask_gap]))
                spike_km  = float(np.nansum(A["hv_clamped_km"][mask_spike]))

                removed_km_tunnel = float(np.nansum(np.maximum(0.0, (A["hv_path_km"] - A["hv_clamped_km"])[mask_gap])))
                removed_km_spike  = float(np.nansum(np.maximum(0.0, (A["hv_path_km"] - A["hv_clamped_km"])[mask_spike])))

                steps_osm_sameway = int(np.count_nonzero(A.get("mask_osm_sameway", np.zeros(0, dtype=bool))))
                osm_used_km = float(A.get("osm_used_km", 0.0))

                # Per-car (keyed by effective id)
                C = by_car[car_id_eff or ""]
                C["files"] += 1
                C["rows"] += len(df)
                C["time_s"] += time_s
                C["dist_speed_km"] += dist_speed_km
                C["dist_hv_path_km"] += dist_hv_path_km
                C["dist_hv_clamped_km"] += dist_hv_clamped_km
                C["dist_geo_clamped_km"] += dist_geo_clamped_km
                C["steps"] += steps
                C["steps_imputed"] += steps_imputed
                C["imputed_km"] += imputed_km
                C["removed_km"] += removed_km
                C["replaced_km"] += replaced_km_val

                # NEW split by cause
                C["steps_gap"] += steps_gap
                C["steps_spike"] += steps_spike
                C["tunnel_km"]  += tunnel_km
                C["spike_km"]   += spike_km
                C["removed_km_tunnel"] += removed_km_tunnel
                C["removed_km_spike"]  += removed_km_spike
                C["steps_osm_sameway"] = C.get("steps_osm_sameway", 0) + steps_osm_sameway
                C["osm_used_km"] = C.get("osm_used_km", 0.0) + osm_used_km

                C["steps_frozen"] = C.get("steps_frozen", 0) + steps_frozen
                C["frozen_km"] = C.get("frozen_km", 0.0) + frozen_km
                C["removed_km_frozen"] = C.get("removed_km_frozen", 0.0) + removed_km_frozen
                C["time_stopped_s"] = C.get("time_stopped_s", 0.0) + stopped_s
                C["time_active_s"]  = C.get("time_active_s", 0.0) + active_s
                C["time_frozen_s"]  = C.get("time_frozen_s", 0.0) + frozen_time_s
                C["time_gap_s"]     = C.get("time_gap_s", 0.0) + gap_time_s

                # Per-day / per-car-day
                tmp = pd.DataFrame({
                    "day": A["day"],
                    "dt_s": A["dt_s"],
                    "speed_km": A["speed_km"],
                    "hv_clamped_km": A["hv_clamped_km"],
                })
                g = tmp.groupby("day").sum(numeric_only=True)
                for d, r in g.iterrows():
                    k = str(pd.Timestamp(d).date())
                    by_day[k]["time_s"] += float(r["dt_s"])
                    by_day[k]["dist_speed_km"] += float(r["speed_km"])
                    by_day[k]["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                    by_car_day[(car_id_eff or "", k)]["time_s"] += float(r["dt_s"])
                    by_car_day[(car_id_eff or "", k)]["dist_speed_km"] += float(r["speed_km"])
                    by_car_day[(car_id_eff or "", k)]["dist_hv_clamped_km"] += float(r["hv_clamped_km"])

                # --- by hour ---
                tmp_h = pd.DataFrame({
                    "hour": A["hour"],
                    "dt_s": A["dt_s"],
                    "speed_km": A["speed_km"],
                    "hv_clamped_km": A["hv_clamped_km"],
                })
                g_h = tmp_h.groupby("hour", dropna=True).sum(numeric_only=True)
                for h, r in g_h.iterrows():
                    h_int = int(h)
                    by_hour[h_int]["time_s"] += float(r["dt_s"])
                    by_hour[h_int]["dist_speed_km"] += float(r["speed_km"])
                    by_hour[h_int]["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                    by_hour[h_int]["steps"] += int((A["hour"] == h_int).sum())

                    BCH = by_car_hour[(car_id_eff or "", h_int)]
                    BCH["time_s"] += float(r["dt_s"])
                    BCH["dist_speed_km"] += float(r["speed_km"])
                    BCH["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                    BCH["steps"] += int((A["hour"] == h_int).sum())

                # --- by label (only if label cache is present) ---
                if "label_name" in A and len(A["label_name"]) == len(A["dt_s"]):
                    tmp_l = pd.DataFrame({
                        "label_name": A["label_name"],
                        "group": A.get("label_group", []),
                        "level": A.get("label_level", []),
                        "dt_s": A["dt_s"],
                        "speed_km": A["speed_km"],
                        "hv_clamped_km": A["hv_clamped_km"],
                        "geo_clamped_km": A["geo_clamped_km"],
                        "imputed_step": np.where(A["imputed_mask"], 1, 0),
                        "imputed_km": np.where(A["imputed_mask"], A["hv_clamped_km"], 0.0),
                        "frozen_km": np.where(A["mask_frozen"], A["hv_clamped_km"], 0.0),
                        "time_gap_s": np.where(A["mask_gap"], A["dt_s"], 0.0),
                        "time_frozen_s": np.where(A["mask_frozen"], A["dt_s"], 0.0),
                    })
                    # drop rows with empty label_name
                    tmp_l = tmp_l[tmp_l["label_name"].notna()]
                    if not tmp_l.empty:
                        g_l = tmp_l.groupby("label_name").agg({
                            "dt_s": "sum",
                            "speed_km": "sum",
                            "hv_clamped_km": "sum",
                            "geo_clamped_km": "sum",
                            "imputed_step": "sum",
                            "imputed_km": "sum",
                            "frozen_km": "sum",
                            "time_gap_s": "sum",
                            "time_frozen_s": "sum",
                        })
                        # store group/level (sample from first occurrence)
                        ref = tmp_l.groupby("label_name").agg({"group":"first","level":"first"})
                        for name, r in g_l.iterrows():
                            BL = by_label[str(name)]
                            BL["time_s"] += float(r["dt_s"])
                            BL["dist_speed_km"] += float(r["speed_km"])
                            BL["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                            BL["dist_geo_clamped_km"] += float(r["geo_clamped_km"])
                            BL["steps"] += int((A["label_name"] == name).sum())
                            BL["steps_imputed"] += int(r["imputed_step"])
                            BL["imputed_km"] += float(r["imputed_km"])
                            BL["frozen_km"] += float(r["frozen_km"])
                            BL["time_gap_s"] += float(r["time_gap_s"])
                            BL["time_frozen_s"] += float(r["time_frozen_s"])
                            if not BL["group"]:
                                BL["group"] = str(ref.loc[name, "group"]) if pd.notna(ref.loc[name, "group"]) else ""
                            if not BL["level"]:
                                BL["level"] = str(ref.loc[name, "level"]) if pd.notna(ref.loc[name, "level"]) else ""

                            BCL = by_car_label[(car_id_eff or "", str(name))]
                            BCL["time_s"] += float(r["dt_s"])
                            BCL["dist_speed_km"] += float(r["speed_km"])
                            BCL["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                            BCL["dist_geo_clamped_km"] += float(r["geo_clamped_km"])
                            BCL["steps"] += int((A["label_name"] == name).sum())
                            BCL["steps_imputed"] += int(r["imputed_step"])
                            BCL["imputed_km"] += float(r["imputed_km"])
                            BCL["frozen_km"] += float(r["frozen_km"])
                            BCL["time_gap_s"] += float(r["time_gap_s"])
                            BCL["time_frozen_s"] += float(r["time_frozen_s"])

                            BWCL = by_carweek_label[((car_week or ""), str(name))]
                            BWCL["time_s"] += float(r["dt_s"])
                            BWCL["dist_speed_km"] += float(r["speed_km"])
                            BWCL["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                            BWCL["dist_geo_clamped_km"] += float(r["geo_clamped_km"])
                            BWCL["steps"] += int((A["label_name"] == name).sum())
                            BWCL["steps_imputed"] += int(r["imputed_step"])
                            BWCL["imputed_km"] += float(r["imputed_km"])
                            BWCL["frozen_km"] += float(r["frozen_km"])
                            BWCL["time_gap_s"] += float(r["time_gap_s"])
                            BWCL["time_frozen_s"] += float(r["time_frozen_s"])

                            BWCCl = by_carweek_car_label[((car_week or ""), (car_id_eff or ""), str(name))]
                            BWCCl["time_s"] += float(r["dt_s"])
                            BWCCl["dist_speed_km"] += float(r["speed_km"])
                            BWCCl["dist_hv_clamped_km"] += float(r["hv_clamped_km"])
                            BWCCl["dist_geo_clamped_km"] += float(r["geo_clamped_km"])
                            BWCCl["steps"] += int((A["label_name"] == name).sum())
                            BWCCl["steps_imputed"] += int(r["imputed_step"])
                            BWCCl["imputed_km"] += float(r["imputed_km"])
                            BWCCl["frozen_km"] += float(r["frozen_km"])
                            BWCCl["time_gap_s"] += float(r["time_gap_s"])
                            BWCCl["time_frozen_s"] += float(r["time_frozen_s"])

                # --- optional per-step annotations for near-miss joining ---
                if ann_rows is not None:
                    n = len(A["dt_s"])
                    if n:
                        df_ann = pd.DataFrame({
                            "ts_start": pd.to_datetime(A["ts_start"]).astype("datetime64[ns]"),
                            "car_id": (car_id_eff or ""),
                            "hour": A["hour"],
                            "dow": A["dow"],
                            "day": A["day"],
                            "file": [fpath] * len(A["ts_start"]),
                            "lat": A["lat0"],
                            "lon": A["lon0"],
                            "label_group": A.get("label_group", [None]*n),
                            "label_level": A.get("label_level", [None]*n),
                            "label_name":  A.get("label_name",  [None]*n),
                            "label_facility": A.get("label_facility", [None]*n),
                            "dt_s": A["dt_s"],
                            "hv_clamped_km": A["hv_clamped_km"],
                        })
                        df_ann["ts_end"] = df_ann["ts_start"] + pd.to_timedelta(df_ann["dt_s"], unit="s")
                        df_ann["date"] = df_ann["ts_start"].dt.strftime("%Y-%m-%d")
                        ann_rows.append(df_ann)


                # Totals
                total["time_s"] += time_s
                total["dist_speed_km"] += dist_speed_km
                total["dist_hv_path_km"] += dist_hv_path_km
                total["dist_hv_clamped_km"] += dist_hv_clamped_km
                total["dist_geo_clamped_km"] += dist_geo_clamped_km
                total["steps"] += steps
                total["steps_imputed"] += steps_imputed
                total["imputed_km"] += imputed_km
                total["removed_km"] += removed_km
                total["replaced_km"] += replaced_km_val

                # NEW split by cause
                total["steps_gap"] += steps_gap
                total["steps_spike"] += steps_spike
                total["tunnel_km"]  += tunnel_km
                total["spike_km"]   += spike_km
                total["removed_km_tunnel"] += removed_km_tunnel
                total["removed_km_spike"]  += removed_km_spike
                total["steps_osm_sameway"] = total.get("steps_osm_sameway", 0) + steps_osm_sameway
                total["osm_used_km"] = total.get("osm_used_km", 0.0) + osm_used_km
                total["steps_frozen"] = total.get("steps_frozen", 0) + steps_frozen
                total["frozen_km"] = total.get("frozen_km", 0.0) + frozen_km
                total["removed_km_frozen"] = total.get("removed_km_frozen", 0.0) + removed_km_frozen
                total["time_stopped_s"] = total.get("time_stopped_s", 0.0) + stopped_s
                total["time_active_s"]  = total.get("time_active_s", 0.0) + active_s
                total["time_frozen_s"]  = total.get("time_frozen_s", 0.0) + frozen_time_s
                total["time_gap_s"]     = total.get("time_gap_s", 0.0) + gap_time_s

                # Audit row
                t_first = df["ts"].iat[0]
                t_last  = df["ts"].iat[-1]
                audit_rows.append({
                    "file": str(PureWindowsPath(fpath)),
                    "car_id_raw": car_id_raw or "",
                    "cid_source": cid_source,  # 'result' | 'hdd' | 'none'
                    "forbid_hdd_fallback": bool(getattr(args, "forbid_hdd_fallback", False)),
                    "car_id_effective": car_id_eff or (
                        "UNK" if (getattr(args, "forbid_hdd_fallback", False) and cid_source != "result") else ""
                    ),
                    "t_first": t_first.isoformat(),
                    "t_last": t_last.isoformat(),
                    "n_rows": len(df),
                    "dt_sum_s": dt_sum_s,
                    "t_span_s": t_span_s,
                    "time_mismatch_s": round(abs(t_span_s - dt_sum_s), 6),
                })


            except Exception as e:
                print(f"[warn] Totals pass failed {fpath}: {e}")
                continue

        # --- WRITE: OSM way summaries ---
        if by_way:
            rows_w = [{
                "way_key": key,
                "name": v["name"],
                "ref": v["ref"],
                "highway": v["highway"],
                "duration_h": round(v["duration_s"] / 3600.0, 6),
                "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                "steps": v["steps"],
                "cars_n": len(v["cars"]),
                "cars": "|".join(sorted(v["cars"])),
                "t_first": (v["t_first"].isoformat(sep=" ") if v["t_first"] else ""),
                "t_last": (v["t_last"].isoformat(sep=" ") if v["t_last"] else ""),
            } for key, v in by_way.items()]
            pd.DataFrame(rows_w).sort_values("dist_hv_clamped_km", ascending=False)\
                .to_csv(outdir / "totals_by_way.csv", index=False, encoding="utf-8-sig")

        if by_car_way:
            rows_cw = [{
                "car_id": cid, "way_key": key,
                "name": v["name"], "ref": v["ref"], "highway": v["highway"],
                "duration_h": round(v["duration_s"] / 3600.0, 6),
                "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                "steps": v["steps"],
                "t_first": (v["t_first"].isoformat(sep=" ") if v["t_first"] else ""),
                "t_last": (v["t_last"].isoformat(sep=" ") if v["t_last"] else ""),
            } for (cid, key), v in by_car_way.items()]
            pd.DataFrame(rows_cw).sort_values(["car_id","dist_hv_clamped_km"], ascending=[True, False])\
                .to_csv(outdir / "totals_by_car_way.csv", index=False, encoding="utf-8-sig")


        # --- WRITE: car-id audit ---
        audit_df = pd.DataFrame(audit_rows)
        if not audit_df.empty:
            audit_df = audit_df.sort_values(["cid_source","car_id_effective","file"])
        else:
            print("[warn] car_id_audit: no rows collected (all files failed earlier)")
        audit_df.to_csv(outdir / "car_id_audit.csv", index=False, encoding="utf-8-sig")

        car_rows = []
        for cid, v in by_car.items():
            car_rows.append({
                "car_id": cid,
                "files": v["files"],
                "rows": v["rows"],
                "duration_h": round(v["time_s"] / 3600.0, 6),
                "dist_speed_km": round(v["dist_speed_km"], 6),
                "dist_hv_path_km": round(v["dist_hv_path_km"], 6),
                "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                "dist_geo_clamped_km": round(v["dist_geo_clamped_km"], 6),
                "steps": v["steps"],
                "steps_imputed": v["steps_imputed"],
                "imputed_km": round(v["imputed_km"], 6),
                "removed_km": round(v["removed_km"], 6),     # new
                "replaced_km": round(v["replaced_km"], 6),   # compat
                "steps_gap": v["steps_gap"],
                "steps_spike": v["steps_spike"],
                "tunnel_km": round(v["tunnel_km"], 6),
                "spike_km":  round(v["spike_km"], 6),
                "removed_km_tunnel": round(v["removed_km_tunnel"], 6),
                "removed_km_spike":  round(v["removed_km_spike"], 6),
                "steps_osm_sameway": v.get("steps_osm_sameway", 0),
                "osm_used_km": round(v.get("osm_used_km", 0.0), 6),
                "imputed_step_pct": round((v["steps_imputed"] / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
                "steps_frozen": v.get("steps_frozen", 0),
                "frozen_km": round(v.get("frozen_km", 0.0), 6),
                "removed_km_frozen": round(v.get("removed_km_frozen", 0.0), 6),
                "time_stopped_h": round(v.get("time_stopped_s", 0.0) / 3600.0, 6),
                "time_active_h":  round(v.get("time_active_s", 0.0) / 3600.0, 6),
                "time_frozen_h":  round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
                "time_gap_h":     round(v.get("time_gap_s", 0.0) / 3600.0, 6),
                "time_span_h": round(v.get("time_span_s", 0.0) / 3600.0, 6),
                "avg_sensor_kph_total":  round((v["dist_speed_km"] / (v["time_s"]/3600.0)) if v["time_s"]>0 else 0.0, 6),
                "avg_sensor_kph_active": round((v["dist_speed_km"] / (v.get("time_active_s",0.0)/3600.0)) if v.get("time_active_s",0.0)>0 else 0.0, 6),
                # 参考：幾何距離ベースの見かけ速度（報告用にのみ。速度判断には使わない）
                "avg_geo_clamped_kph_total": round((v["dist_geo_clamped_km"] / (v["time_s"]/3600.0)) if v["time_s"]>0 else 0.0, 6),
            })

        df_car = pd.DataFrame(car_rows)
        if (not df_car.empty) and ('car_id' in df_car.columns):
            df_car = df_car.sort_values(['car_id'])
        df_car.to_csv(outdir / 'totals_by_car.csv', index=False, encoding='utf-8-sig')


        # --- WRITE: totals_by_car_e1a.csv ---
        car_rows_e1a = []
        for cid, v in by_car_e1a.items():
            car_rows_e1a.append({
                "car_id": cid,
                "files": v["files"],
                "rows": v["rows"],
                "duration_h": round(v["time_s"] / 3600.0, 6),
                "dist_speed_km": round(v["dist_speed_km"], 6),
                "dist_hv_path_km": round(v["dist_hv_path_km"], 6),
                "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                "dist_geo_clamped_km": round(v["dist_geo_clamped_km"], 6),
                "steps": v["steps"],
                "steps_imputed": v["steps_imputed"],
                "imputed_km": round(v["imputed_km"], 6),
                "removed_km": round(v["removed_km"], 6),
                "replaced_km": round(v["replaced_km"], 6),
                "steps_gap": v["steps_gap"],
                "steps_spike": v["steps_spike"],
                "tunnel_km": round(v["tunnel_km"], 6),
                "spike_km":  round(v["spike_km"], 6),
                "removed_km_tunnel": round(v["removed_km_tunnel"], 6),
                "removed_km_spike":  round(v["removed_km_spike"], 6),
                "steps_osm_sameway": v.get("steps_osm_sameway", 0),
                "osm_used_km": round(v.get("osm_used_km", 0.0), 6),
                "imputed_step_pct": round((v["steps_imputed"] / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
                "steps_frozen": v.get("steps_frozen", 0),
                "frozen_km": round(v.get("frozen_km", 0.0), 6),
                "removed_km_frozen": round(v.get("removed_km_frozen", 0.0), 6),
                "time_stopped_h": round(v.get("time_stopped_s", 0.0) / 3600.0, 6),
                "time_active_h":  round(v.get("time_active_s", 0.0) / 3600.0, 6),
                "time_frozen_h":  round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
                "time_gap_h":     round(v.get("time_gap_s", 0.0) / 3600.0, 6),
                "time_span_h": round(v.get("time_span_s", 0.0) / 3600.0, 6),
                "avg_sensor_kph_total":  round((v["dist_speed_km"] / (v["time_s"]/3600.0)) if v["time_s"]>0 else 0.0, 6),
                "avg_sensor_kph_active": round((v["dist_speed_km"] / (v.get("time_active_s",0.0)/3600.0)) if v.get("time_active_s",0.0)>0 else 0.0, 6),
                "avg_geo_clamped_kph_total": round((v["dist_geo_clamped_km"] / (v["time_s"]/3600.0)) if v["time_s"]>0 else 0.0, 6),
            })
        df_car_e1a = pd.DataFrame(car_rows_e1a)
        # E1A subset can be empty when OSM cache is missing or classification yields nothing.
        if (not df_car_e1a.empty) and ('car_id' in df_car_e1a.columns):
            df_car_e1a = df_car_e1a.sort_values(['car_id'])
        df_car_e1a.to_csv(outdir / 'totals_by_car_e1a.csv', index=False, encoding='utf-8-sig')

        # --- WRITE: by hour ---
        rows_h = [{
            "hour": h,
            "duration_h": round(v["time_s"]/3600.0, 6),
            "dist_speed_km": round(v["dist_speed_km"], 6),
            "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
            "steps": v["steps"],
        } for h, v in sorted(by_hour.items())]
        pd.DataFrame(rows_h).to_csv(outdir / "totals_by_hour.csv", index=False, encoding="utf-8-sig")

        rows_ch = [{
            "car_id": cid, "hour": h,
            "duration_h": round(v["time_s"]/3600.0, 6),
            "dist_speed_km": round(v["dist_speed_km"], 6),
            "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
            "steps": v["steps"],
        } for (cid, h), v in sorted(by_car_hour.items(), key=lambda kv:(kv[0][0], kv[0][1]))]
        pd.DataFrame(rows_ch).to_csv(outdir / "totals_by_car_hour.csv", index=False, encoding="utf-8-sig")

        # --- WRITE: by label ---
        rows_l = [{
            "label_name": name,
            "group": v["group"],
            "level": v["level"],
            "duration_h": round(v["time_s"]/3600.0, 6),
            "dist_speed_km": round(v["dist_speed_km"], 6),
            "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
            "dist_geo_clamped_km": round(v.get("dist_geo_clamped_km", 0.0), 6),
            "steps": v["steps"],
            "steps_imputed": v.get("steps_imputed", 0),
            "imputed_km": round(v.get("imputed_km", 0.0), 6),
            "frozen_km": round(v.get("frozen_km", 0.0), 6),
            "time_gap_h": round(v.get("time_gap_s", 0.0) / 3600.0, 6),
            "time_frozen_h": round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
            "imputed_step_pct": round((v.get("steps_imputed", 0) / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
            "expected_distance_km": round(v.get("dist_geo_clamped_km", 0.0) + v.get("imputed_km", 0.0), 6),
        } for name, v in by_label.items()]
        if rows_l:
            pd.DataFrame(rows_l).sort_values("dist_geo_clamped_km", ascending=False)\
                .to_csv(outdir / "totals_by_label.csv", index=False, encoding="utf-8-sig")

        rows_cl = [{
            "car_id": cid,
            "label_name": name,
            "duration_h": round(v["time_s"]/3600.0, 6),
            "dist_speed_km": round(v["dist_speed_km"], 6),
            "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
            "dist_geo_clamped_km": round(v.get("dist_geo_clamped_km", 0.0), 6),
            "steps": v["steps"],
            "steps_imputed": v.get("steps_imputed", 0),
            "imputed_km": round(v.get("imputed_km", 0.0), 6),
            "frozen_km": round(v.get("frozen_km", 0.0), 6),
            "time_gap_h": round(v.get("time_gap_s", 0.0) / 3600.0, 6),
            "time_frozen_h": round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
            "imputed_step_pct": round((v.get("steps_imputed", 0) / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
            "expected_distance_km": round(v.get("dist_geo_clamped_km", 0.0) + v.get("imputed_km", 0.0), 6),
        } for (cid, name), v in by_car_label.items()]
        if rows_cl:
            pd.DataFrame(rows_cl).sort_values(["car_id","label_name"])\
                .to_csv(outdir / "totals_by_car_label.csv", index=False, encoding="utf-8-sig")

        # NEW: totals by car-week (for joining with near-miss Excel)
        if by_carweek:
            rows_cw = []
            for cw, v in by_carweek.items():
                rows_cw.append({
                    "car_week": cw,
                    "files": v["files"],
                    "rows": v["rows"],
                    "duration_h": round(v["time_s"]/3600.0, 6),
                    "dist_speed_km": round(v["dist_speed_km"], 6),
                    "dist_hv_path_km": round(v["dist_hv_path_km"], 6),
                    "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                    "dist_geo_clamped_km": round(v.get("dist_geo_clamped_km", 0.0), 6),
                    "steps": v["steps"],
                    "steps_imputed": v["steps_imputed"],
                    "imputed_km": round(v["imputed_km"], 6),
                    "frozen_km": round(v.get("frozen_km", 0.0), 6),
                    "time_gap_h": round(v.get("time_gap_s", 0.0) / 3600.0, 6),
                    "time_frozen_h": round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
                    "time_active_h": round(v.get("time_active_s", 0.0) / 3600.0, 6),
                    "time_stopped_h": round(v.get("time_stopped_s", 0.0) / 3600.0, 6),
                    "imputed_step_pct": round((v["steps_imputed"] / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
                })
            pd.DataFrame(rows_cw).sort_values("dist_hv_clamped_km", ascending=False)                .to_csv(outdir / "totals_by_carweek.csv", index=False, encoding="utf-8-sig")

        if by_carweek_car:
            rows_cwc = []
            for combo_key, v in by_carweek_car.items():
                cw, cid = (combo_key.split("__", 1) + [""])[:2]
                rows_cwc.append({
                    "car_week": cw,
                    "car_id": cid,
                    "duration_h": round(v["time_s"]/3600.0, 6),
                    "dist_speed_km": round(v["dist_speed_km"], 6),
                    "dist_hv_path_km": round(v["dist_hv_path_km"], 6),
                    "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                    "dist_geo_clamped_km": round(v.get("dist_geo_clamped_km", 0.0), 6),
                    "steps": v["steps"],
                    "steps_imputed": v["steps_imputed"],
                    "imputed_km": round(v["imputed_km"], 6),
                    "frozen_km": round(v.get("frozen_km", 0.0), 6),
                    "time_gap_h": round(v.get("time_gap_s", 0.0) / 3600.0, 6),
                    "time_frozen_h": round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
                    "time_active_h": round(v.get("time_active_s", 0.0) / 3600.0, 6),
                    "time_stopped_h": round(v.get("time_stopped_s", 0.0) / 3600.0, 6),
                    "imputed_step_pct": round((v["steps_imputed"] / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
                })
            pd.DataFrame(rows_cwc).sort_values("dist_geo_clamped_km", ascending=False)\
                .to_csv(outdir / "totals_by_carweek_car.csv", index=False, encoding="utf-8-sig")

        if by_carweek_label:
            rows_cwl = [{
                "car_week": cw,
                "label_name": name,
                "duration_h": round(v["time_s"]/3600.0, 6),
                "dist_speed_km": round(v["dist_speed_km"], 6),
                "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                "dist_geo_clamped_km": round(v.get("dist_geo_clamped_km", 0.0), 6),
                "steps": v["steps"],
                "steps_imputed": v.get("steps_imputed", 0),
                "imputed_km": round(v.get("imputed_km", 0.0), 6),
                "frozen_km": round(v.get("frozen_km", 0.0), 6),
                "time_gap_h": round(v.get("time_gap_s", 0.0) / 3600.0, 6),
                "time_frozen_h": round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
                "imputed_step_pct": round((v.get("steps_imputed", 0) / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
                "expected_distance_km": round(v.get("dist_geo_clamped_km", 0.0) + v.get("imputed_km", 0.0), 6),
            } for (cw, name), v in by_carweek_label.items()]
            pd.DataFrame(rows_cwl).sort_values("dist_geo_clamped_km", ascending=False)\
                .to_csv(outdir / "totals_by_carweek_label.csv", index=False, encoding="utf-8-sig")

        if by_carweek_car_label:
            rows_cwcl = [{
                "car_week": cw,
                "car_id": cid,
                "label_name": name,
                "duration_h": round(v["time_s"]/3600.0, 6),
                "dist_speed_km": round(v["dist_speed_km"], 6),
                "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
                "dist_geo_clamped_km": round(v.get("dist_geo_clamped_km", 0.0), 6),
                "steps": v["steps"],
                "steps_imputed": v.get("steps_imputed", 0),
                "imputed_km": round(v.get("imputed_km", 0.0), 6),
                "frozen_km": round(v.get("frozen_km", 0.0), 6),
                "time_gap_h": round(v.get("time_gap_s", 0.0) / 3600.0, 6),
                "time_frozen_h": round(v.get("time_frozen_s", 0.0) / 3600.0, 6),
                "imputed_step_pct": round((v.get("steps_imputed", 0) / v["steps"] * 100.0) if v["steps"] else 0.0, 3),
                "expected_distance_km": round(v.get("dist_geo_clamped_km", 0.0) + v.get("imputed_km", 0.0), 6),
            } for (cw, cid, name), v in by_carweek_car_label.items()]
            pd.DataFrame(rows_cwcl).sort_values("dist_geo_clamped_km", ascending=False)\
                .to_csv(outdir / "totals_by_carweek_car_label.csv", index=False, encoding="utf-8-sig")



        # --- WRITE: per-step annotations (optional) ---
        if ann_rows:
            ann_df = pd.concat(ann_rows, ignore_index=True)
            ann_df.sort_values(["car_id", "ts_start"]).to_csv(outdir / "step_annotations.csv", index=False, encoding="utf-8-sig")


        day_rows = [{
            "day": d,
            "duration_h": round(v["time_s"] / 3600.0, 6),
            "dist_speed_km": round(v["dist_speed_km"], 6),
            "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
        } for d, v in by_day.items()]
        day_df = pd.DataFrame(day_rows, columns=["day", "duration_h", "dist_speed_km", "dist_hv_clamped_km"])
        if "day" in day_df.columns:
            day_df = day_df.sort_values("day")
        day_df.to_csv(outdir / "totals_by_day.csv", index=False, encoding="utf-8-sig")

        cday_rows = [{
            "car_id": cid,
            "day": d,
            "duration_h": round(v["time_s"] / 3600.0, 6),
            "dist_speed_km": round(v["dist_speed_km"], 6),
            "dist_hv_clamped_km": round(v["dist_hv_clamped_km"], 6),
        } for (cid, d), v in by_car_day.items()]
        cday_df = pd.DataFrame(
            cday_rows,
            columns=["car_id", "day", "duration_h", "dist_speed_km", "dist_hv_clamped_km"],
        )
        if all(col in cday_df.columns for col in ["car_id", "day"]):
            cday_df = cday_df.sort_values(["car_id", "day"])
        cday_df.to_csv(outdir / "totals_by_car_day.csv", index=False, encoding="utf-8-sig")

        with open(outdir / "totals_overall.json", "w", encoding="utf-8") as jf:
            json.dump({
                "duration_h": round(total["time_s"] / 3600.0, 6),
                "dist_speed_km": round(total["dist_speed_km"], 6),
                "dist_hv_path_km": round(total["dist_hv_path_km"], 6),
                "dist_hv_clamped_km": round(total["dist_hv_clamped_km"], 6),
                "dist_geo_clamped_km": round(total["dist_geo_clamped_km"], 6),
                "steps": total["steps"],
                "steps_imputed": total["steps_imputed"],
                "imputed_km": round(total["imputed_km"], 6),
                "removed_km": round(total["removed_km"], 6),   # new
                "replaced_km": round(total["replaced_km"], 6), # compat
                "imputed_step_pct": round((total["steps_imputed"] / total["steps"] * 100.0) if total["steps"] else 0.0, 3),
                "steps_gap": total["steps_gap"],
                "steps_spike": total["steps_spike"],
                "tunnel_km": round(total["tunnel_km"], 6),
                "spike_km":  round(total["spike_km"], 6),
                "removed_km_tunnel": round(total["removed_km_tunnel"], 6),
                "removed_km_spike":  round(total["removed_km_spike"], 6),
                "steps_osm_sameway": total.get("steps_osm_sameway", 0),
                "osm_used_km": round(total.get("osm_used_km", 0.0), 6),
                "steps_frozen": total.get("steps_frozen", 0),
                "frozen_km": round(total.get("frozen_km", 0.0), 6),
                "removed_km_frozen": round(total.get("removed_km_frozen", 0.0), 6),
                "time_stopped_h": round(total.get("time_stopped_s", 0.0) / 3600.0, 6),
                "time_active_h":  round(total.get("time_active_s", 0.0) / 3600.0, 6),
                "time_frozen_h": round(total.get("time_frozen_s", 0.0) / 3600.0, 6),
                "time_gap_h":    round(total.get("time_gap_s", 0.0) / 3600.0, 6),
                "time_span_h":   round(total.get("time_span_s", 0.0) / 3600.0, 6),
                "params": {
                    "fallback_kph": args.fallback_kph,
                    "speed_spike_kph": (args.speed_spike_kph or args.fallback_kph),
                    "gap_threshold_s": args.gap_threshold_s,
                    "root": str(PureWindowsPath(root)),
                    "glob": args.glob,
                    "forbid_hdd_fallback": bool(getattr(args, "forbid_hdd_fallback", False)),
                    "osm_mode": args.osm_mode,
                    "osm_cache": str(args.osm_cache) if args.osm_cache else None,
                    "osm_snap_radius_m": args.osm_snap_radius_m,
                    "osm_grid_ddeg": args.osm_grid_ddeg,
                    "osm_sameway_on": list(_osm_sameway_on),
                }
            }, jf, ensure_ascii=False, indent=2)

            with open(outdir / "totals_overall_e1a.json", "w", encoding="utf-8") as jf:
                json.dump({
                    "duration_h": round(total_e1a["time_s"] / 3600.0, 6),
                    "dist_speed_km": round(total_e1a["dist_speed_km"], 6),
                    "dist_hv_path_km": round(total_e1a["dist_hv_path_km"], 6),
                    "dist_hv_clamped_km": round(total_e1a["dist_hv_clamped_km"], 6),
                    "dist_geo_clamped_km": round(total_e1a["dist_geo_clamped_km"], 6),
                    "steps": total_e1a["steps"],
                    "steps_imputed": total_e1a["steps_imputed"],
                    "imputed_km": round(total_e1a["imputed_km"], 6),
                    "removed_km": round(total_e1a["removed_km"], 6),
                    "replaced_km": round(total_e1a["replaced_km"], 6),
                    "imputed_step_pct": round((total_e1a["steps_imputed"] / total_e1a["steps"] * 100.0) if total_e1a["steps"] else 0.0, 3),
                    "steps_gap": total_e1a["steps_gap"],
                    "steps_spike": total_e1a["steps_spike"],
                    "tunnel_km": round(total_e1a["tunnel_km"], 6),
                    "spike_km":  round(total_e1a["spike_km"], 6),
                    "removed_km_tunnel": round(total_e1a["removed_km_tunnel"], 6),
                    "removed_km_spike":  round(total_e1a["removed_km_spike"], 6),
                    "steps_osm_sameway": total_e1a.get("steps_osm_sameway", 0),
                    "osm_used_km": round(total_e1a.get("osm_used_km", 0.0), 6),
                    "steps_frozen": total_e1a.get("steps_frozen", 0),
                    "frozen_km": round(total_e1a.get("frozen_km", 0.0), 6),
                    "removed_km_frozen": round(total_e1a.get("removed_km_frozen", 0.0), 6),
                    "time_stopped_h": round(total_e1a.get("time_stopped_s", 0.0) / 3600.0, 6),
                    "time_active_h":  round(total_e1a.get("time_active_s", 0.0) / 3600.0, 6),
                    "time_frozen_h": round(total_e1a.get("time_frozen_s", 0.0) / 3600.0, 6),
                    "time_gap_h":    round(total_e1a.get("time_gap_s", 0.0) / 3600.0, 6),
                    "time_span_h":   round(total_e1a.get("time_span_s", 0.0) / 3600.0, 6),
                    "params": {
                        "scope": "E1A_only",
                        "e1a_snap_required": bool(args.e1a_snap_required),
                        "fallback_kph": args.fallback_kph,
                        "speed_spike_kph": (args.speed_spike_kph or args.fallback_kph),
                        "gap_threshold_s": args.gap_threshold_s,
                        "root": str(PureWindowsPath(root)),
                        "glob": args.glob,
                        "osm_mode": args.osm_mode,
                        "osm_cache": str(args.osm_cache) if args.osm_cache else None,
                        "osm_snap_radius_m": args.osm_snap_radius_m,
                    }
                }, jf, ensure_ascii=False, indent=2)

        print(f"[ok] Totals written → {outdir}")
        print("  - totals_by_car.csv, totals_by_day.csv, totals_by_car_day.csv, totals_overall.json, car_id_audit.csv")

        # optional: export routes geojson
        if getattr(args, 'routes_out', None):
            try:
                export_routes_geojson(files, Path(args.routes_out), max_points=int(getattr(args, 'routes_max_points', 20000) or 0))
                print(f'[ok] Routes written → {Path(args.routes_out)}')
            except Exception as e:
                print(f'[warn] routes export failed: {e}', file=sys.stderr)
        return
    
    if not args.a or not args.b:
        ap.error("--a and --b are required unless --summarize-all is set")

    a_lat, a_lon = [float(x) for x in args.a.split(",")]
    b_lat, b_lon = [float(x) for x in args.b.split(",")]
    ab_direct_km = geod_m(a_lat, a_lon, b_lat, b_lon) / 1000.0
    
    candidates: List[Candidate] = []
    diag_rows: List[dict] = []
    file_metas: List[FileMeta] = []
    nearA_events: List[ABEvent] = []
    nearB_events: List[ABEvent] = []

    for idx, fpath in enumerate(files, 1):
        if idx % 200 == 0:
            print(f"[progress] {idx}/{len(files)} ... {PureWindowsPath(fpath)}", flush=True)
        try:
            df = load_df_cached(fpath)
            if df.empty or len(df) < 2:
                continue

            # File meta
            car_id = infer_car_id_from_path(fpath)
            t_first = df["ts"].iat[0]
            t_last = df["ts"].iat[-1]
            file_metas.append(FileMeta(file=fpath, car_id=car_id, t_first=t_first, t_last=t_last, n_rows=len(df)))

            # Diagnostics: nearest distances to A/B for this file
            lat = df["lat"].to_numpy()
            lon = df["lon"].to_numpy()
            dA_all = haversine_m(lat, lon, a_lat, a_lon)
            dB_all = haversine_m(lat, lon, b_lat, b_lon)
            iA_min = int(np.argmin(dA_all))
            iB_min = int(np.argmin(dB_all))
            dA_min = float(dA_all[iA_min])
            dB_min = float(dB_all[iB_min])
            straight_m = float(haversine_m(lat[iA_min], lon[iA_min], lat[iB_min], lon[iB_min]))
            diag_rows.append({
                "file": str(PureWindowsPath(fpath)),
                "car_id": car_id or "",
                "minA_m": round(dA_min, 3),
                "ts_at_minA": df["ts"].iat[iA_min].isoformat(),
                "lat_at_minA": float(lat[iA_min]),
                "lon_at_minA": float(lon[iA_min]),
                "minB_m": round(dB_min, 3),
                "ts_at_minB": df["ts"].iat[iB_min].isoformat(),
                "lat_at_minB": float(lat[iB_min]),
                "lon_at_minB": float(lon[iB_min]),
                "A_then_B_order": bool(iA_min < iB_min),
                "straight_AB_m": round(straight_m, 3),
            })

            # Gather near events for stitching
            if args.stitch_cross_files:
                nearA_idx = np.where(dA_all <= args.radius_m)[0]
                nearB_idx = np.where(dB_all <= args.radius_m)[0]
                for i in nearA_idx:
                    nearA_events.append(ABEvent(file=fpath, car_id=car_id, idx=int(i), ts=df["ts"].iat[int(i)], lat=float(lat[i]), lon=float(lon[i]), dist_m=float(dA_all[i]), kind='A'))
                for j in nearB_idx:
                    nearB_events.append(ABEvent(file=fpath, car_id=car_id, idx=int(j), ts=df["ts"].iat[int(j)], lat=float(lat[j]), lon=float(lon[j]), dist_m=float(dB_all[j]), kind='B'))

            # Per-file candidate (for non-stitch mode)
            if not args.stitch_cross_files:
                pair = find_best_AB_pair(df, a_lat, a_lon, b_lat, b_lon, args.radius_m)
                if pair is None:
                    continue
                df_slice = df.iloc[pair.iA : pair.jB + 1].copy()
                metrics = compute_metrics(
                    df_slice,
                    args.fallback_kph,
                    speed_spike_kph=(args.speed_spike_kph or 200.0),
                    gap_threshold_s=args.gap_threshold_s,
                    tunnel_freeze_min_speed_kph=args.tunnel_freeze_min_speed_kph,
                    tunnel_freeze_eps_m=args.tunnel_freeze_eps_m,
                    osm_index=osm_index,
                    osm_snap_radius_m=args.osm_snap_radius_m,
                )
                cand = Candidate(
                    file=fpath,
                    car_id=car_id,
                    iA=pair.iA,
                    jB=pair.jB,
                    dA_m=pair.dA_m,
                    dB_m=pair.dB_m,
                    score_m=pair.score_m,
                    n_points=metrics.n_points,
                    t_start=df_slice["ts"].iat[0],
                    t_end=df_slice["ts"].iat[-1],
                    duration_s=metrics.duration_s,
                    speed_integral_km=metrics.speed_integral_km,
                    haversine_min_km=metrics.haversine_min_km,
                    ellipsoid_min_km=metrics.ellipsoid_min_km,
                    haversine_caponly_km=metrics.haversine_caponly_km,
                    ellipsoid_caponly_km=metrics.ellipsoid_caponly_km
                )
                candidates.append(cand)
        except Exception as e:
            print(f"[warn] Failed {fpath}: {e}")
            continue

    # Always write diagnostics summary
    if diag_rows:
        diag_df = pd.DataFrame(diag_rows)
        diag_all_csv = outdir / "nearAB_all.csv"
        diag_df.to_csv(diag_all_csv, index=False, encoding="utf-8-sig")
        nearA_top = diag_df.sort_values("minA_m").head(20)
        nearB_top = diag_df.sort_values("minB_m").head(20)
        nearA_top.to_csv(outdir / "nearA_top20.csv", index=False, encoding="utf-8-sig")
        nearB_top.to_csv(outdir / "nearB_top20.csv", index=False, encoding="utf-8-sig")
        print(f"[diag] wrote nearAB_all.csv, nearA_top20.csv, nearB_top20.csv → {outdir}")
        try:
            print("[diag] Top 5 near A:")
            print(nearA_top[["minA_m","file","car_id","ts_at_minA"]].head(5).to_string(index=False))
            print("[diag] Top 5 near B:")
            print(nearB_top[["minB_m","file","car_id","ts_at_minB"]].head(5).to_string(index=False))
        except Exception:
            pass

    # ---- stitch mode ----
    if args.stitch_cross_files:
        if (not nearA_events) or (not nearB_events):
            print("No A/B near events within radius across files. Increase --radius-m (e.g., 1000–3000).")
            return
        choice = find_best_AB_events(
            nearA_events, nearB_events,
            mode=args.stitch_score_mode, lambda_per_min=args.stitch_balance_lambda,
            same_car_only=args.same_car_only, max_span_min=args.max_span_min
        )
        if choice is None:
            print("Could not pair A then B across files. Check chronology or increase --radius-m.")
            return
        # Build stitched slice between choice.a_evt.ts and choice.b_evt.ts
        sel_files, stitched = build_stitched_slice(choice.a_evt, choice.b_evt, file_metas, same_car_only=args.same_car_only)
        if stitched.empty or len(stitched) < 2:
            print("Stitched slice is empty. Check radius or timestamps.")
            return
        # Compute metrics
        metrics = compute_metrics(
            stitched,
            args.fallback_kph,
            speed_spike_kph=(args.speed_spike_kph or 200.0),
            gap_threshold_s=args.gap_threshold_s,
            tunnel_freeze_min_speed_kph=args.tunnel_freeze_min_speed_kph,
            tunnel_freeze_eps_m=args.tunnel_freeze_eps_m,
            osm_index=osm_index,
            osm_snap_radius_m=args.osm_snap_radius_m,
        )
     
        # Export per-step (with src_file kept)
        ts = stitched["ts"].to_numpy()
        dt_s = np.r_[0.0, np.diff(ts).astype("timedelta64[ns]").astype(np.int64)/1e9]
        out_df = stitched.copy()
        out_df.insert(1, "dt_s_from_prev", dt_s)
        best_csv = outdir / "ab_best_slice.csv"
        out_df.to_csv(best_csv, index=False, encoding="utf-8-sig")

        # Export window file list
        win_rows = []
        for fm in file_metas:
            if fm.file in sel_files:
                win_rows.append({
                    "file": str(PureWindowsPath(fm.file)),
                    "car_id": fm.car_id or "",
                    "t_first": fm.t_first.isoformat(),
                    "t_last": fm.t_last.isoformat(),
                    "n_rows": fm.n_rows,
                    "included": True,
                })
        win_csv = outdir / "ab_window_files.csv"
        pd.DataFrame(win_rows).to_csv(win_csv, index=False, encoding="utf-8-sig")

        # Metadata JSON
        meta = {
            "winner": {
                "file": "<stitched>",
                "car_id": args.car_id,
                "iA": choice.a_evt.idx,
                "jB": choice.b_evt.idx,
                "nearestA_m": round(choice.a_evt.dist_m, 3),
                "nearestB_m": round(choice.b_evt.dist_m, 3),
                "score_m": round(choice.score_m, 3),
                "t_start": choice.a_evt.ts.isoformat(),
                "t_end": choice.b_evt.ts.isoformat(),
                "duration_s": float((choice.b_evt.ts - choice.a_evt.ts).total_seconds()),
                "speed_integral_km": round(metrics.speed_integral_km, 6),
                "haversine_min_km": round(metrics.haversine_min_km, 6),
                "haversine_path_km": round(metrics.haversine_path_km, 6),
                "ellipsoid_min_km": (round(metrics.ellipsoid_min_km, 6) if metrics.ellipsoid_min_km is not None else None),
                "haversine_caponly_km": round(metrics.haversine_caponly_km, 6),      # NEW
                "ellipsoid_caponly_km": round(metrics.ellipsoid_caponly_km, 6),      # NEW
                "dt_sum_s": round(metrics.dt_stats.get("sum_s", 0.0), 3),
                "dt_median_s": round(metrics.dt_stats.get("median_s", 0.0), 3),
                "ab_direct_km": round(ab_direct_km, 6),
            },
            "inputs": {
                "A": {"lat": a_lat, "lon": a_lon},
                "B": {"lat": b_lat, "lon": b_lon},
                "radius_m": args.radius_m,
                "fallback_kph": args.fallback_kph,
                "root": str(PureWindowsPath(root)),
                "glob": args.glob,
                "car_id_filter": args.car_id,
                "pyproj_available": _GEOD is not None,
                "stitch_cross_files": True,
                "stitch_score_mode": args.stitch_score_mode,
                "stitch_balance_lambda": args.stitch_balance_lambda,
            },
            "outputs": {
                "best_slice_csv": str(PureWindowsPath(best_csv)),
                "window_files_csv": str(PureWindowsPath(win_csv)),
                "diag_all_csv": str(PureWindowsPath(outdir / "nearAB_all.csv")),
                "nearA_top20_csv": str(PureWindowsPath(outdir / "nearA_top20.csv")),
                "nearB_top20_csv": str(PureWindowsPath(outdir / "nearB_top20.csv")),
            },
        }
        with open(outdir / "ab_best_slice.json", "w", encoding="utf-8") as jf:
            json.dump(meta, jf, ensure_ascii=False, indent=2)

            print(f"[ok] Stitched A→B across files.")
            print(f"[ok] Wrote best slice → {best_csv}")
            print(f"[ok] Wrote window file list → {win_csv}")
            print(f"Direct A→B (km, WGS84): {ab_direct_km:.6f}")
            print(
                f"Distances (km): speed={meta['winner']['speed_integral_km']}, "
                f"hv_min={meta['winner']['haversine_min_km']}, "
                f"hv_path={meta['winner']['haversine_path_km']}, "
                f"ellip_min={meta['winner']['ellipsoid_min_km']}, "
                f"hv_caponly={meta['winner']['haversine_caponly_km']}, "
                f"ellip_caponly={meta['winner']['ellipsoid_caponly_km']}, "
                f"ab_direct={ab_direct_km:.6f}"
            )
        return

    # ---- per-file mode (legacy) ----
    if not candidates:
        print("No candidates found within radius for both A and B.")
        print("Hint: increase --radius-m (e.g., 1000–3000), or filter by --car-id to the likely vehicle.")
        return

    def sort_key(c: Candidate):
        return (round(c.score_m, 6), -c.duration_s)

    candidates.sort(key=sort_key)

    # Write candidates table
    cand_rows = []
    for c in candidates:
        cand_rows.append(
            {
                "file": str(PureWindowsPath(c.file)),
                "car_id": c.car_id or "",
                "iA": c.iA,
                "jB": c.jB,
                "nearestA_m": round(c.dA_m, 3),
                "nearestB_m": round(c.dB_m, 3),
                "score_m": round(c.score_m, 3),
                "n_points": c.n_points,
                "t_start": c.t_start.isoformat(),
                "t_end": c.t_end.isoformat(),
                "duration_s": round(c.duration_s, 3),
                "speed_integral_km": round(c.speed_integral_km, 6),
                "haversine_min_km": round(c.haversine_min_km, 6),
                "ellipsoid_min_km": (round(c.ellipsoid_min_km, 6) if c.ellipsoid_min_km is not None else None),
            }
        )

    cand_df = pd.DataFrame(cand_rows)
    cand_csv = outdir / "ab_candidates.csv"
    cand_df.to_csv(cand_csv, index=False, encoding="utf-8-sig")

    best = candidates[0]
    df = load_df_cached(best.file)
    df_slice = df.iloc[best.iA : best.jB + 1].copy()

    step_rows = []
    ts  = df_slice["ts"].to_numpy()
    lat = df_slice["lat"].to_numpy()
    lon = df_slice["lon"].to_numpy()
    spd = df_slice["speed_kph"].to_numpy()
    dt_s = np.r_[0.0, np.diff(ts).astype("timedelta64[ns]").astype(np.int64)/1e9]

    for i in range(len(df_slice)):
        step_rows.append(
            {
                "idx": i,
                "ts": df_slice["ts"].iat[i].isoformat(),
                "lat": float(lat[i]),
                "lon": float(lon[i]),
                "speed_kph": float(spd[i]),
                "dt_s_from_prev": float(dt_s[i]),
            }
        )
    best_csv = outdir / "ab_best_slice.csv"
    pd.DataFrame(step_rows).to_csv(best_csv, index=False, encoding="utf-8-sig")

    meta = {
        "winner": {
            "file": str(PureWindowsPath(best.file)),
            "car_id": best.car_id,
            "iA": best.iA,
            "jB": best.jB,
            "nearestA_m": round(best.dA_m, 3),
            "nearestB_m": round(best.dB_m, 3),
            "score_m": round(best.score_m, 3),
            "t_start": best.t_start.isoformat(),
            "t_end": best.t_end.isoformat(),
            "duration_s": round(best.duration_s, 3),
            "speed_integral_km": round(best.speed_integral_km, 6),
            "haversine_min_km": round(best.haversine_min_km, 6),
            "ellipsoid_min_km": (round(best.ellipsoid_min_km, 6) if best.ellipsoid_min_km is not None else None),
            "ab_direct_km": round(ab_direct_km, 6),

        },
        "inputs": {
            "A": {"lat": a_lat, "lon": a_lon},
            "B": {"lat": b_lat, "lon": b_lon},
            "ab_direct_km": round(ab_direct_km, 6),
            "radius_m": args.radius_m,
            "fallback_kph": args.fallback_kph,
            "root": str(PureWindowsPath(root)),
            "glob": args.glob,
            "car_id_filter": args.car_id,
            "pyproj_available": _GEOD is not None,
            "stitch_cross_files": False,
        },
        "outputs": {
            "candidates_csv": str(PureWindowsPath(cand_csv)),
            "best_slice_csv": str(PureWindowsPath(best_csv)),
            "diag_all_csv": str(PureWindowsPath(outdir / "nearAB_all.csv")),
            "nearA_top20_csv": str(PureWindowsPath(outdir / "nearA_top20.csv")),
            "nearB_top20_csv": str(PureWindowsPath(outdir / "nearB_top20.csv")),
        },
    }
    with open(outdir / "ab_best_slice.json", "w", encoding="utf-8") as jf:
        json.dump(meta, jf, ensure_ascii=False, indent=2)

    print(f"[ok] Wrote candidates → {cand_csv}")
    print(f"[ok] Wrote best slice → {best_csv}")
    print(f"Best file: {meta['winner']['file']}")
    print(f"Duration: {meta['winner']['duration_s']} s  Score: {meta['winner']['score_m']} m")
    print(
        f"Distances (km): speed={meta['winner']['speed_integral_km']}, "
        f"hv_min={meta['winner']['haversine_min_km']}, "
        f"ellip_min={meta['winner']['ellipsoid_min_km']}, "
        f"ab_direct={round(ab_direct_km, 6)}")


if __name__ == "__main__":
    pd.options.mode.copy_on_write = True
    main()
