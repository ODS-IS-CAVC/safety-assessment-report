"""
MapData抽象基底クラス。

JSON形式（MapData）とOpenDRIVE形式（EsminiMapData）の共通インターフェースを定義する。
純粋幾何演算は具象メソッドとして共有する。
"""
import math
from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Optional


class MapDataBase(ABC):
    """MapData / EsminiMapData 共通の抽象基底クラス"""

    # サブクラスで設定が必要な属性:
    #   epsg: int - 座標系EPSGコード
    #   map_offset: Tuple[float, float] - マップのオフセット (x, y)
    #   roads: Dict - 道路データ辞書

    @property
    @abstractmethod
    def coordinate_rotation(self) -> float:
        """座標回転角度（度）。GPSデータに適用される回転と同じ角度。"""
        ...

    @abstractmethod
    def get_closest_lane_and_road(self, x: float, y: float) -> Tuple[str, str, Dict]:
        """与えられた座標 (x, y) に最も近い lane とその道路情報を返す。"""
        ...

    @abstractmethod
    def get_lane_yaw(self, x: float, y: float) -> Tuple[float, float, str, str]:
        """指定された座標に最も近いレーンの進行方向（ヨー角）と高さ（z）を取得する。"""
        ...

    @abstractmethod
    def get_travel_coordinates(
        self, start_position: Tuple[float, float], total_distance: float
    ) -> List[Tuple[float, float, float]]:
        """初期位置と移動距離を基に、道路接続を考慮した座標列を生成する。"""
        ...

    @abstractmethod
    def get_lane_and_successors(
        self, road_id: str, lane_id: str, include_successors: bool = False
    ) -> List[Tuple[str, str, List[Tuple[float, float, float]]]]:
        """指定された road_id と lane_id の lane とその次に接続されているレーン情報を取得する。"""
        ...

    @abstractmethod
    def get_successor_lane(
        self, road_id: str, lane_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """指定された road_id と lane_id に対する successor を取得する。"""
        ...

    @abstractmethod
    def get_lane_coords(
        self, road_id: str, lane_id: str
    ) -> List[Tuple[float, float, float]]:
        """指定された road_id と lane_id の lane の座標列を取得する。"""
        ...

    @abstractmethod
    def calculate_lateral_offset(
        self, x: float, y: float
    ) -> Tuple[float, str, str, Tuple[float, float, float]]:
        """指定された位置の、最近傍車線からの横方向オフセットを計算する。"""
        ...

    # --- 具象メソッド（純粋幾何演算） ---

    def _calculate_segment_length(
        self, p1: Tuple[float, float, float], p2: Tuple[float, float, float]
    ) -> float:
        """3次元空間における2点間の距離を計算する。"""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

    def _calculate_coordinate_length(
        self, coordinate: List[Tuple[float, float, float]]
    ) -> float:
        """座標リストの長さを計算する。"""
        if len(coordinate) < 2:
            return 0.0
        return sum(
            self._calculate_segment_length(coordinate[i], coordinate[i + 1])
            for i in range(len(coordinate) - 1)
        )

    def split_by_nearest_point(
        self,
        target_point: Tuple[float, float, float],
        coordinates: List[Tuple[float, float, float]],
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
        """指定された座標に最も近いセグメントで座標を分割する。"""
        if not coordinates:
            return [], []

        nearest_index = min(
            range(len(coordinates)),
            key=lambda i: self._calculate_segment_length(target_point, coordinates[i]),
        )
        return coordinates[: nearest_index + 1], coordinates[nearest_index + 1 :]

    def split_by_distance(
        self,
        coordinates: List[Tuple[float, float, float]],
        distance: float,
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
        """指定された距離で座標を分割する。"""
        if not coordinates or distance <= 0:
            return [], coordinates

        accumulated = 0.0
        for i in range(1, len(coordinates)):
            segment_length = self._calculate_segment_length(
                coordinates[i - 1], coordinates[i]
            )
            if accumulated + segment_length >= distance:
                ratio = (distance - accumulated) / segment_length
                interpolated = tuple(
                    coordinates[i - 1][j] + ratio * (coordinates[i][j] - coordinates[i - 1][j])
                    for j in range(3)
                )
                return coordinates[:i] + [interpolated], [interpolated] + coordinates[i:]
            accumulated += segment_length

        return coordinates, []
