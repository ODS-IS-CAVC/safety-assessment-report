"""
道路ネットワークのデータモデル。

Lane（車線）と Road（道路）クラスを定義する。
map_data.py から抽出された純粋なデータ構造モジュール。
"""
import math
from typing import List, Tuple, Dict


TOLERANCE = 0.00001


class Lane:
    def __init__(self, road_id: str, lane_id: str, coordinates: List[Tuple[float, float, float]]):
        self.road_id = road_id
        self.lane_id = lane_id
        # 座標をタプルのリストに変換
        processed_coordinates = []
        if coordinates:
            # 最初の座標を登録
            current_coord = tuple(coordinates[0]) if isinstance(
                coordinates[0], list) else coordinates[0]
            processed_coordinates.append(current_coord)
            prev_vector = None  # 前のベクトルを保持
            # 2つ目以降の座標を処理
            for i in range(1, len(coordinates)):
                next_coord = tuple(coordinates[i]) if isinstance(
                    coordinates[i], list) else coordinates[i]

                # 2点間の距離を計算
                dx = next_coord[0] - current_coord[0]
                dy = next_coord[1] - current_coord[1]
                segment_length = math.sqrt(dx*dx + dy*dy)

                current_vector = (dx, dy)

                # 距離が短い or 反対方向ならスキップ
                if segment_length <= TOLERANCE:
                    continue

                # 向きが逆の場合もスキップ（内積が負かつ、長さが近い）
                if prev_vector:
                    dot_product = prev_vector[0] * dx + prev_vector[1] * dy
                    if dot_product < 0:
                        continue

                processed_coordinates.append(next_coord)
                current_coord = next_coord
                prev_vector = current_vector

        self.coordinate = processed_coordinates

        self.segment_lengths = self._calculate_segment_lengths()
        self.total_length = sum(self.segment_lengths)
        self.predecessors: List[Tuple[str, str]] = []  # (road_id, lane_id)
        self.successors: List[Tuple[str, str]] = []    # (road_id, lane_id)

    def _calculate_segment_lengths(self) -> List[float]:
        lengths = []
        for i in range(len(self.coordinate) - 1):
            p1 = self.coordinate[i]
            p2 = self.coordinate[i + 1]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            lengths.append(math.hypot(dx, dy))
        return lengths


class Road:
    def __init__(self, road_dict: dict):
        self.id = road_dict["id"]
        self.name = road_dict.get("name")
        self.length = road_dict.get("length", 0.0)
        self.junction = road_dict.get("junction")
        self.links = road_dict.get("links", {})
        self.lanes = []

        for lane_dict in road_dict.get("lanes", []):
            lane = Lane(self.id, lane_dict["lane_id"], lane_dict["coordinate"])
            self.lanes.append(lane)

        # 接続情報の処理
        if self.links:
            self._process_links(self.links)

    def _process_links(self, links: Dict):
        """接続情報を処理し、各レーンに設定する"""
        if 'predecessor' in links:
            for lane_num_str, connections in links['predecessor'].items():
                for conn in connections:
                    road_id, target_lane = conn
                    # レーン番号に対応するLaneオブジェクトを探す
                    for lane in self.lanes:
                        if lane.lane_id == lane_num_str:
                            lane.predecessors.append(
                                (road_id, str(target_lane)))

        if 'successor' in links:
            for lane_num_str, connections in links['successor'].items():
                for conn in connections:
                    road_id, target_lane = conn
                    # レーン番号に対応するLaneオブジェクトを探す
                    for lane in self.lanes:
                        if lane.lane_id == lane_num_str:
                            lane.successors.append((road_id, str(target_lane)))
