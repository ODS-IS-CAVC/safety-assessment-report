"""
空間クエリ機能。

KDTreeを用いた空間インデックスの構築と最近傍検索を提供する。
map_data.py から抽出された純粋関数モジュール。
"""
import math
from typing import List, Tuple, Dict, Optional
from scipy.spatial import KDTree
from road_network import Lane


def closest_point_on_segment(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float
) -> Tuple[float, float]:
    """
    点 (px, py) から線分 (ax, ay)-(bx, by) への最近点を返す。

    Args:
        px, py: 対象点の座標
        ax, ay: 線分始点の座標
        bx, by: 線分終点の座標

    Returns:
        Tuple[float, float]: 線分上の最近点 (x, y)
    """
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab_len2 = abx ** 2 + aby ** 2
    if ab_len2 == 0:
        return ax, ay
    t = max(0, min(1, (apx * abx + apy * aby) / ab_len2))
    return ax + t * abx, ay + t * aby


def interpolate_z_on_segment(
    cx: float, cy: float,
    ax: float, ay: float, az: float,
    bx: float, by: float, bz: float,
) -> float:
    """
    線分上の点(cx, cy)のZ座標を線形補間で求める。

    Args:
        cx, cy: 対象点のXY座標（線分上の点）
        ax, ay, az: 線分始点の座標
        bx, by, bz: 線分終点の座標

    Returns:
        float: 補間されたZ座標
    """
    abx, aby = bx - ax, by - ay
    apx, apy = cx - ax, cy - ay
    ab_len2 = abx ** 2 + aby ** 2
    if ab_len2 == 0:
        return az
    t = max(0, min(1, (apx * abx + apy * aby) / ab_len2))
    return az + t * (bz - az)


def find_closest_point_on_segments(
    x: float, y: float,
    coords: List[Tuple[float, float, float]],
    start_idx: int,
    end_idx: int,
) -> Tuple[Tuple[float, float, float], int, float]:
    """
    座標リスト内の指定範囲のセグメントから、点(x, y)に最も近い点を求める。

    Args:
        x, y: 対象点の座標
        coords: 座標リスト [(x, y, z), ...]
        start_idx: 検索開始インデックス
        end_idx: 検索終了インデックス（排他的）

    Returns:
        Tuple: (closest_point, segment_index, distance)
    """
    min_dist = float('inf')
    result_point = None
    result_index = None

    for i in range(start_idx, min(end_idx, len(coords) - 1)):
        ax, ay = coords[i][0], coords[i][1]
        bx, by = coords[i + 1][0], coords[i + 1][1]
        cx, cy = closest_point_on_segment(x, y, ax, ay, bx, by)
        cz = interpolate_z_on_segment(
            cx, cy, ax, ay, coords[i][2], bx, by, coords[i + 1][2]
        )
        d = math.hypot(x - cx, y - cy)
        if d < min_dist:
            min_dist = d
            result_point = (cx, cy, cz)
            result_index = i

    return result_point, result_index, min_dist


class SpatialIndex:
    """
    道路ネットワークの空間インデックス。
    KDTreeを用いて高速な最近傍検索を提供する。
    """

    def __init__(self, roads: Dict):
        """
        空間インデックスを構築する。

        Args:
            roads: {road_id: Road} の辞書
        """
        self._roads = roads
        self._spatial_points: List[Tuple[float, float]] = []
        self._spatial_point_info: List[Tuple[str, str, int, float]] = []
        self._spatial_kdtree: Optional[KDTree] = None
        self._build(roads)

    def _build(self, roads: Dict):
        """全レーンの全座標点をKDTreeに登録する。"""
        for road in roads.values():
            for lane in road.lanes:
                for idx, (x, y, z) in enumerate(lane.coordinate):
                    self._spatial_points.append((x, y))
                    self._spatial_point_info.append(
                        (road.id, lane.lane_id, idx, z))
        if self._spatial_points:
            self._spatial_kdtree = KDTree(self._spatial_points)

    def get_closest_lane_and_road(
        self, x: float, y: float, roads: Dict
    ) -> Tuple[str, str, Dict]:
        """
        与えられた座標 (x, y) に最も近い lane とその道路情報を返す。

        Args:
            x, y: 対象点の座標
            roads: {road_id: Road} の辞書

        Returns:
            Tuple[str, str, Dict]: (road_id, lane_id, info_dict)
        """
        if self._spatial_kdtree is not None:
            return self._query_kdtree(x, y, roads)
        return self._query_brute_force(x, y, roads)

    def _query_kdtree(
        self, x: float, y: float, roads: Dict
    ) -> Tuple[str, str, Dict]:
        """KDTreeを使った高速な最近傍検索。"""
        dist, idx = self._spatial_kdtree.query((x, y))
        road_id, lane_id, point_idx, z = self._spatial_point_info[idx]
        lane = next(
            l for l in roads[road_id].lanes if l.lane_id == lane_id
        )
        coords = lane.coordinate

        # 最も近い点の前後のセグメントで最近傍点を再計算
        start = max(0, point_idx - 1)
        end = min(len(coords) - 1, point_idx + 1)
        closest_point, closest_idx, min_dist = find_closest_point_on_segments(
            x, y, coords, start, end
        )

        return road_id, lane_id, {
            "road_id": road_id,
            "lane_id": lane_id,
            "closest_index": closest_idx,
            "coordinates": coords,
            "closest_point": closest_point,
            "distance": min_dist,
        }

    def _query_brute_force(
        self, x: float, y: float, roads: Dict
    ) -> Tuple[str, str, Dict]:
        """全探索による最近傍検索（フォールバック）。"""
        min_distance = float('inf')
        closest_point = None
        closest_lane = None
        closest_road_id = None
        closest_lane_id = None
        closest_segment_index = -1

        for road in roads.values():
            for lane in road.lanes:
                coords = lane.coordinate
                point, seg_idx, dist = find_closest_point_on_segments(
                    x, y, coords, 0, len(coords) - 1
                )
                if point is not None and dist < min_distance:
                    min_distance = dist
                    closest_point = point
                    closest_lane = lane
                    closest_road_id = road.id
                    closest_lane_id = lane.lane_id
                    closest_segment_index = seg_idx

        return closest_road_id, closest_lane_id, {
            "road_id": closest_road_id,
            "lane_id": closest_lane_id,
            "closest_index": closest_segment_index,
            "coordinates": closest_lane.coordinate if closest_lane else None,
            "closest_point": closest_point,
            "distance": min_distance,
        }
