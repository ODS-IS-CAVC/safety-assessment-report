import math
import json
import logging
from typing import List, Tuple, Dict, Optional

from road_network import Lane, Road, TOLERANCE
from spatial_query import SpatialIndex
from map_data_base import MapDataBase

logger = logging.getLogger(__name__)


class MapData(MapDataBase):
    def __init__(self, map_json_path: str):
        """
        道路ネットワークデータを読み込む

        Args:
            map_json_path (str): マップデータのJSONファイルパス
        """
        with open(map_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

            # データがリストの場合は最初の要素を使用
            if isinstance(data, list):
                if not data:
                    raise ValueError("Empty JSON data")
                self.data = data[0]
            else:
                self.data = data

        # マップのオフセット（座標変換用）
        self.map_offset = self._parse_map_offset(self.data.get("map_offset"))

        # 座標系EPSG（デフォルトは6677）
        self.epsg = int(self.data.get("EPSG") or self.data.get("epsg", 6677))

        # 道路データの整理
        self.roads = {road_data["id"]: Road(
            road_data) for road_data in self.data.get("roads", [])}

        # links 情報から predecessor を補完
        self._ensure_bidirectional_links()

        # 座標を -90 度回転
        self._rotate_coordinates(-90)

        # 道路とレーンの接続を滑らかに補間
        self._smooth_all_connections()

        # 空間インデックスの構築
        self._spatial_index = SpatialIndex(self.roads)

    @property
    def coordinate_rotation(self) -> float:
        """JSON形式のマップデータは-90度回転が適用されている"""
        return -90.0

    def _parse_map_offset(self, map_offset) -> Tuple[float, float]:
        if isinstance(map_offset, list):
            return map_offset[0], map_offset[1]
        elif isinstance(map_offset, dict):
            return map_offset.get("x", 0), map_offset.get("y", 0)
        return 0, 0

    def _ensure_bidirectional_links(self):
        """successor の情報を使って逆向きの predecessor を補完する"""
        for road in self.roads.values():
            for lane in road.lanes:
                for succ_road_id, succ_lane_id in lane.successors:
                    succ_road = self.roads.get(succ_road_id)
                    if not succ_road:
                        continue
                    for succ_lane in succ_road.lanes:
                        if succ_lane.lane_id == succ_lane_id:
                            if (road.id, lane.lane_id) not in succ_lane.predecessors:
                                succ_lane.predecessors.append(
                                    (road.id, lane.lane_id))

    def _rotate_coordinates(self, angle_deg: float):
        """すべての座標を指定された角度だけ回転する。"""
        angle_rad = math.radians(angle_deg)
        cos_angle = math.cos(angle_rad)
        sin_angle = math.sin(angle_rad)

        for road in self.roads.values():
            for lane in road.lanes:
                lane.coordinate = [
                    (
                        cos_angle * x - sin_angle * y,
                        sin_angle * x + cos_angle * y,
                        z
                    )
                    for x, y, z in lane.coordinate
                ]

    def _smooth_all_connections(self):
        """すべての道路とレーンの接続を滑らかに補間する。"""
        for road in self.roads.values():
            for lane in road.lanes:
                self._process_connections(
                    lane.predecessors, lane, is_predecessor=True)
                self._process_connections(
                    lane.successors, lane, is_predecessor=False)

    def _process_connections(self, connections: List[Tuple[str, str]], lane: Lane, is_predecessor: bool):
        for road_id, lane_id in connections:
            connected_road = self.roads.get(road_id)
            if not connected_road:
                continue
            connected_lane = next(
                (l for l in connected_road.lanes if l.lane_id == lane_id), None)
            if not connected_lane:
                continue
            if is_predecessor:
                self._smooth_connection(connected_lane, lane)
            else:
                self._smooth_connection(lane, connected_lane)

    def _smooth_connection(self, lane1: Lane, lane2: Lane):
        """2つのレーンの接続を滑らかにするため、接続する2点を中点に移動する。"""
        if not lane1.coordinate or not lane2.coordinate:
            return

        end_point = lane1.coordinate[-1]
        start_point = lane2.coordinate[0]

        midpoint = (
            (end_point[0] + start_point[0]) / 2,
            (end_point[1] + start_point[1]) / 2,
            (end_point[2] + start_point[2]) / 2
        )

        lane1.coordinate[-1] = midpoint
        lane2.coordinate[0] = midpoint

    def get_lane_coords(self, road_id: str, lane_id: str) -> List[Tuple[float, float, float]]:
        """指定された road_id と lane_id の lane の座標列を取得する"""
        road = self.roads.get(road_id)
        if not road:
            raise ValueError(f"Road ID {road_id} not found")

        for lane in road.lanes:
            if lane.lane_id == lane_id:
                return lane.coordinate

        raise ValueError(f"Lane ID {lane_id} not found in road {road_id}")

    def get_closest_lane_and_road(self, x: float, y: float) -> Tuple[str, str, Dict]:
        """与えられた座標 (x, y) に最も近い lane とその道路情報を返す。"""
        return self._spatial_index.get_closest_lane_and_road(x, y, self.roads)

    def calculate_lateral_offset(self, x: float, y: float) -> Tuple[float, str, str, Tuple[float, float, float]]:
        """
        指定された位置の、最近傍車線からの横方向オフセットを計算

        Returns:
            Tuple[float, str, str, Tuple]: (lateral_offset, road_id, lane_id, closest_point)
        """
        road_id, lane_id, info = self.get_closest_lane_and_road(x, y)
        if not road_id or not lane_id:
            return 0.0, "", "", (x, y, 0.0)

        closest_point = info["closest_point"]
        closest_index = info["closest_index"]
        coords = info["coordinates"]

        # 最近傍点での車線の接線方向を計算
        if closest_index + 1 < len(coords):
            p1 = coords[closest_index]
            p2 = coords[closest_index + 1]
            tangent_x = p2[0] - p1[0]
            tangent_y = p2[1] - p1[1]
        elif closest_index > 0:
            p1 = coords[closest_index - 1]
            p2 = coords[closest_index]
            tangent_x = p2[0] - p1[0]
            tangent_y = p2[1] - p1[1]
        else:
            return 0.0, road_id, lane_id, closest_point

        tangent_len = math.sqrt(tangent_x**2 + tangent_y**2)
        if tangent_len == 0:
            return 0.0, road_id, lane_id, closest_point
        tangent_x /= tangent_len
        tangent_y /= tangent_len

        dx = x - closest_point[0]
        dy = y - closest_point[1]

        lateral_offset = dx * (-tangent_y) + dy * tangent_x

        return lateral_offset, road_id, lane_id, closest_point

    def get_successor_lane(self, road_id: str, lane_id: str) -> Tuple[Optional[str], Optional[str]]:
        """指定された road_id と lane_id に対する successor を取得する。"""
        road = self.roads.get(road_id)
        if road and road.links:
            successor = road.links.get("successor", {}).get(lane_id)
            if successor:
                return successor[0]
        return None, None

    def get_lane(self, road_id: str, lane_id: str) -> Optional[dict]:
        for road in self.data["roads"]:
            if road["id"] == road_id:
                for lane in road["lanes"]:
                    if lane["lane_id"] == lane_id:
                        return lane
        return None

    def get_lane_and_successors(self, road_id: str, lane_id: str, include_successors: bool = False) -> List[Tuple[str, str, List[Tuple[float, float, float]]]]:
        """指定された road_id と lane_id の lane とその次に接続されているレーン情報を取得する。"""
        road = self.roads.get(road_id)
        if not road:
            raise ValueError(f"Road ID {road_id} not found")

        for lane in road.lanes:
            if lane.lane_id == lane_id:
                lanes_info = [(road_id, lane_id, lane.coordinate)]

                if include_successors:
                    current_lane = lane
                    while current_lane.successors:
                        next_road_id, next_lane_id = current_lane.successors[0]
                        next_road = self.roads.get(next_road_id)
                        if not next_road:
                            break

                        next_lane = next(
                            (l for l in next_road.lanes if l.lane_id == next_lane_id), None)
                        if not next_lane:
                            break

                        lanes_info.append(
                            (next_road_id, next_lane_id, next_lane.coordinate))
                        current_lane = next_lane

                return lanes_info

        raise ValueError(f"Lane ID {lane_id} not found in road {road_id}")

    def get_lane_yaw(self, x: float, y: float) -> Tuple[float, float]:
        """指定された座標に最も近いレーンの進行方向（ヨー角）と高さ（z）を取得する。"""
        road_id, lane_id, _ = self.get_closest_lane_and_road(x, y)
        if not road_id or not lane_id:
            raise ValueError("指定された位置がレーン上にありません")

        lane_coords = self.get_lane_coords(road_id, lane_id)

        min_dist = float('inf')
        closest_index = 0
        for i, (px, py, _) in enumerate(lane_coords[:-1]):
            dist = math.hypot(px - x, py - y)
            if dist < min_dist:
                min_dist = dist
                closest_index = i

        p1 = lane_coords[closest_index]
        p2 = lane_coords[closest_index + 1]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        z = 0
        yaw = math.atan2(dy, dx)
        length = (dx**2 + dy**2)

        if length > 0:
            ratio = ((x - p1[0]) * dx + (y - p1[1]) * dy) / length
            ratio = max(0, min(1, ratio))
            z = p1[2] + ratio * dz

        return yaw, z, road_id, lane_id

    def _move_to_next_lane(self, current_road_id: str, current_lane_id: str, direction: int) -> Tuple[Optional[str], Optional[str]]:
        """次のレーンに移動するためのヘルパー関数。"""
        road = self.roads.get(current_road_id)
        if not road:
            return None, None

        lane = next(
            (l for l in road.lanes if l.lane_id == current_lane_id), None)
        if not lane:
            return None, None

        if direction > 0 and lane.successors:
            return lane.successors[0]
        elif direction < 0 and lane.predecessors:
            return lane.predecessors[0]
        return None, None

    def get_travel_coordinates(self,
                               start_position: Tuple[float, float],
                               total_distance: float,
                               ) -> List[Tuple[float, float, float]]:
        """
        初期位置と移動距離を基に、道路接続を考慮した線形データを生成する。

        Args:
            start_position (Tuple[float, float]): 初期位置 (x, y)
            total_distance (float): 総移動距離（正の値で前進、負の値で後退）

        Returns:
            List[Tuple[float, float, float]]: FPSごとの座標データ [(x, y, z)]
        """
        road_id, lane_id, info = self.get_closest_lane_and_road(
            start_position[0], start_position[1]
        )
        if not road_id or not lane_id:
            logger.warning("近接する道路が見つかりません")
            return []

        closest_point = info["closest_point"]
        closest_index = info["closest_index"]
        lane_coords = info["coordinates"]
        direction = 1 if total_distance > 0 else -1

        if direction < 0:
            logger.debug("後退方向: road_id=%s, lane_id=%s", road_id, lane_id)
            logger.debug("開始位置: (%.6f, %.6f)", closest_point[0], closest_point[1])
            logger.debug("開始インデックス: %d, レーン座標数: %d", closest_index, len(lane_coords))
            logger.debug("必要距離=%.4fm", abs(total_distance))

        accumulated_coords = [closest_point]
        accumulated_distance = 0.0
        current_road_id = road_id
        current_lane_id = lane_id
        current_coords = lane_coords

        if direction < 0:
            current_index = closest_index + 1
            logger.debug("後退開始: current_index=%d (セグメント終点側)", current_index)
        else:
            current_index = closest_index

        while accumulated_distance < abs(total_distance):
            if direction > 0:
                if current_index + 1 >= len(current_coords):
                    next_road_id, next_lane_id = self._move_to_next_lane(
                        current_road_id, current_lane_id, direction)
                    if not next_road_id or not next_lane_id:
                        logger.error("successorが見つかりません")
                        break

                    new_coords = self.get_lane_coords(next_road_id, next_lane_id)
                    if not new_coords:
                        logger.error("新しいレーンの座標が取得できません")
                        break

                    last_point = accumulated_coords[-1]
                    new_start_point = new_coords[0]
                    jump_distance = self._calculate_segment_length(last_point, new_start_point)
                    if jump_distance > 10.0:
                        logger.warning("successorへの移動で大きなジャンプ検出: %.1fm - 延長を停止", jump_distance)
                        break

                    current_road_id, current_lane_id = next_road_id, next_lane_id
                    current_coords = new_coords
                    current_index = -1
                else:
                    current_point = accumulated_coords[-1]
                    next_point = current_coords[current_index + 1]
                    segment_len = self._calculate_segment_length(current_point, next_point)
                    remaining_distance = abs(total_distance) - accumulated_distance

                    if accumulated_distance + segment_len <= abs(total_distance):
                        accumulated_coords.append(next_point)
                        accumulated_distance += segment_len
                        current_index += 1
                    else:
                        ratio = remaining_distance / segment_len
                        interpolated = tuple(
                            current_point[j] + ratio * (next_point[j] - current_point[j]) for j in range(3))
                        accumulated_coords.append(interpolated)
                        accumulated_distance = abs(total_distance)
                        break
            else:
                if current_index <= 0:
                    next_road_id, next_lane_id = self._move_to_next_lane(
                        current_road_id, current_lane_id, direction)
                    if not next_road_id or not next_lane_id:
                        logger.error("predecessorが見つかりません: road=%s..., lane=%s", current_road_id[:20], current_lane_id)
                        logger.error("累積距離=%.4fm / 必要距離=%.4fm (%.1f%%)", accumulated_distance, abs(total_distance), accumulated_distance/abs(total_distance)*100)
                        break

                    logger.debug("predecessorに移動: %s... -> %s..., lane=%s", current_road_id[:20], next_road_id[:20], next_lane_id)

                    new_coords = self.get_lane_coords(next_road_id, next_lane_id)
                    if not new_coords:
                        logger.error("新しいレーンの座標が取得できません")
                        break

                    last_point = accumulated_coords[-1]
                    new_end_point = new_coords[-1]
                    jump_distance = self._calculate_segment_length(last_point, new_end_point)
                    if jump_distance > 10.0:
                        logger.warning("predecessorへの移動で大きなジャンプ検出: %.1fm - 延長を停止", jump_distance)
                        break

                    current_road_id, current_lane_id = next_road_id, next_lane_id
                    current_coords = new_coords
                    current_index = len(current_coords)
                    logger.debug("新しいレーンの座標数=%d", len(current_coords))
                else:
                    current_point = accumulated_coords[-1]

                    if len(accumulated_coords) == 1 and current_point != current_coords[current_index]:
                        next_point = current_coords[current_index]
                        segment_len = self._calculate_segment_length(current_point, next_point)

                        if direction < 0:
                            logger.debug("最初のステップ: closest_point -> segment_start, len=%.4fm", segment_len)

                        if accumulated_distance + segment_len <= abs(total_distance):
                            accumulated_coords.append(next_point)
                            accumulated_distance += segment_len
                        else:
                            ratio = (abs(total_distance) - accumulated_distance) / segment_len
                            interpolated = tuple(
                                current_point[j] + ratio * (next_point[j] - current_point[j]) for j in range(3))
                            accumulated_coords.append(interpolated)
                            accumulated_distance = abs(total_distance)
                            if direction < 0:
                                logger.debug("必要距離に到達（最初のセグメント内）: 累積=%.4fm, 最終座標数=%d", accumulated_distance, len(accumulated_coords))
                            break
                    else:
                        prev_point = current_coords[current_index - 1]
                        segment_len = self._calculate_segment_length(current_point, prev_point)
                        remaining_distance = abs(total_distance) - accumulated_distance

                        if direction < 0 and len(accumulated_coords) <= 5:
                            logger.debug("セグメント: current=(%.6f, %.6f), prev=(%.6f, %.6f), len=%.4fm", current_point[0], current_point[1], prev_point[0], prev_point[1], segment_len)
                            logger.debug("判定: %.4f + %.4f <= %.4f? → %s", accumulated_distance, segment_len, abs(total_distance), accumulated_distance + segment_len <= abs(total_distance))

                        if accumulated_distance + segment_len <= abs(total_distance):
                            accumulated_coords.append(prev_point)
                            accumulated_distance += segment_len
                            current_index -= 1
                            if direction < 0 and len(accumulated_coords) <= 5:
                                logger.debug("座標追加: index=%d, 累積=%.4fm, 座標数=%d", current_index, accumulated_distance, len(accumulated_coords))
                        else:
                            ratio = remaining_distance / segment_len
                            interpolated = tuple(
                                current_point[j] + ratio * (prev_point[j] - current_point[j]) for j in range(3))
                            accumulated_coords.append(interpolated)
                            accumulated_distance = abs(total_distance)
                            if direction < 0:
                                logger.debug("必要距離に到達: 累積=%.4fm, 最終座標数=%d", accumulated_distance, len(accumulated_coords))
                            break

        if direction < 0:
            logger.debug("reverse前の座標数=%d", len(accumulated_coords))
            accumulated_coords.reverse()
            logger.debug("reverse後の座標数=%d", len(accumulated_coords))

        actual_distance = self._calculate_coordinate_length(accumulated_coords)
        diff = abs(total_distance) - actual_distance
        if diff > TOLERANCE:
            logger.warning("距離に差分あり: 必要=%.4fm, 実際=%.4fm, 差分=%.4fm", abs(total_distance), actual_distance, diff)

        if direction < 0:
            logger.debug("返す座標数=%d, 実際の距離=%.4fm", len(accumulated_coords), actual_distance)
        return accumulated_coords
