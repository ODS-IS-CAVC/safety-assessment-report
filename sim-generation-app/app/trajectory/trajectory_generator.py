import logging
import pandas as pd
import numpy as np
import math
from typing import List, Tuple, Optional
from pyproj import Transformer
from map_data import MapData

logger = logging.getLogger(__name__)
# 抽出したユーティリティモジュールをインポート
from coordinate_utils import (
    closest_point_on_segment,
    calculate_distance_from_start,
    is_point_on_segment,
    interpolate_position_on_lane,
    find_point_at_distance,
    calculate_lane_distance,
)
from interpolation import (
    remove_outliers_with_frames,
    interpolate_positions,
    interpolate_lane_id,
)

TRAJECTORY_CSV_HEADR = ["timestamp", "frame", "pos_x", "pos_y", "pos_z", "roll_rad", "pitch_rad", "yaw_rad", "speed", "vel_x",
                        "vel_y", "vel_z", "a_vel_yaw_rad", "a_vel_pitch_rad", "a_vel_roll_rad", "road_id", "lane_id", "source", "lateral_offset"]


class TrajectoryGenerator:
    def __init__(self, map_data: MapData, fps: float, camera_offset: float = 9.33):
        self.map_data = map_data
        self.fps = fps
        self.vehicle_data = []
        self.trajectory = []
        self.lane_change_schedule = []
        self.missing_gps_intervals = []
        self.current_lane_offset = 0.0  # レーンチェンジ時の横方向オフセット
        self.camera_offset = camera_offset  # カメラの前方オフセット（自車両後軸中央からの距離）

        # 緯度経度 → EPSG 変換器（WGS84 → 地図EPSG）
        self.transformer = Transformer.from_crs(
            "EPSG:4326", f"EPSG:{self.map_data.epsg}", always_xy=True)

    def load_vehicle_data(self, csv_path: str):
        df = pd.read_csv(csv_path)

        for _, row in df.iterrows():
            lon, lat = row["lon"], row["lat"]
            if pd.isna(lon) or pd.isna(lat):
                x, y = None, None
            else:
                x, y = self.transformer.transform(lon, lat)
                # map_offset補正
                x -= self.map_data.map_offset[0]
                y -= self.map_data.map_offset[1]
                rotation = getattr(self.map_data, 'coordinate_rotation', -90)
                if rotation != 0:
                    angle_rad = math.radians(rotation)
                    cos_angle = math.cos(angle_rad)
                    sin_angle = math.sin(angle_rad)
                    rot_x = cos_angle * x - sin_angle * y
                    rot_y = sin_angle * x + cos_angle * y
                    x = rot_x
                    y = rot_y
                z = float(row.get("z", 0))

            self.vehicle_data.append({
                "frame": int(row["frame"]),
                "timestamp": int(row["frame"]) / self.fps,
                "x": x,
                "y": y,
                "z": z,
                "speed": float(row["speed"]) * 1000 / 3600,  # km/h → m/s
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "jst_time": row["jst_time"]
            })

    def set_lane_change_schedule(self, schedule: list):
        """
        レーンチェンジのスケジュールを設定します。

        Args:
            schedule: レーンチェンジの情報を含むリスト。以下の形式:
                [
                    {
                        "start_frame": 開始フレーム,
                        "end_frame": 終了フレーム,
                        "delta_lane": レーンチェンジの方向,
                    }
                ]
        """
        self.lane_change_schedule = []
        for change in schedule:
            start_frame = change['start_frame']
            end_frame = change.get(
                'end_frame', start_frame + 60)  # デフォルト60フレーム
            lane_change_info = {
                'start_frame': start_frame,
                'end_frame': end_frame,
                'delta_lane': change.get('delta_lane', 0)  # レーンチェンジの方向
            }
            if 'target_road_id' in change:
                lane_change_info['target_road_id'] = change['target_road_id']
            if 'target_lane_id' in change:
                lane_change_info['target_lane_id'] = change['target_lane_id']
            self.lane_change_schedule.append(lane_change_info)

    def _get_lane_change_info(self, frame: int) -> Tuple[float, int]:
        """
        現在のフレームでのレーンチェンジ情報を取得します。

        Returns:
            Tuple[float, int]:
                - progress: レーンチェンジの進捗（0.0-1.0）
                - delta_lane: レーンチェンジの方向
        """
        for change in self.lane_change_schedule:
            if change['start_frame'] <= frame <= change['end_frame']:
                progress = (frame - change['start_frame']) / \
                    (change['end_frame'] - change['start_frame'])
                delta_lane = change.get('delta_lane', 0)
                return None, None, progress, delta_lane

        return None, None, 0.0, 0

    def set_missing_gps_ranges(self, ranges: list):
        """
        GPSが欠落している範囲を指定（補間用）
        例: [(200, 210), (450, 460)]
        """
        self.missing_ranges = ranges

    def _check_direction(self, self_lane_yaw, other_lane_yaw):
        """
        進行方向をチェックする
        """
        def yaw_to_vector(yaw):
            """
            yaw（角度）から単位ベクトルを作成
            """
            return math.cos(yaw), math.sin(yaw)

        # yaw -> unit vector
        self_vec = yaw_to_vector(self_lane_yaw)
        other_vec = yaw_to_vector(other_lane_yaw)

        # 内積を計算（方向が同じなら正、逆なら負になる）
        dot_product = self_vec[0] * other_vec[0] + self_vec[1] * other_vec[1]

        if dot_product < 0:  # 進行方向が逆（180度近く違う）とみなす
            return False
        return True

    def _check_opposite_lane(self, relative_positions, self_vehicle_df):
        """
        相対位置と移動方向を基に反対車線の車両をチェックする
        日本の道路では、相対位置が右側（rel_x > 0）の車両は反対車線の可能性が高い
        """
        if len(relative_positions) < 2:
            return True  # データが少ない場合は除外しない

        # 最初のフレームでの相対位置をチェック
        first_pos = relative_positions[0]
        rel_x, rel_y = first_pos["distance"]

        # 右側車線（反対車線）の閾値（メートル）
        opposite_lane_threshold = 5.0  # 5m以上右側にいる場合は反対車線と判定

        if rel_x > opposite_lane_threshold:
            logger.info("Vehicle filtered out: rel_x=%.2fm (> %.2fm threshold) - likely opposite lane", rel_x, opposite_lane_threshold)
            return False

        # 複数フレームがある場合は移動方向もチェック
        if len(relative_positions) >= 5:
            # 最初と最後の数フレームの平均位置を計算
            first_frames = relative_positions[:3]
            last_frames = relative_positions[-3:]

            # 平均相対位置を計算
            first_avg_x = sum(pos["distance"][0]
                              for pos in first_frames) / len(first_frames)
            first_avg_y = sum(pos["distance"][1]
                              for pos in first_frames) / len(first_frames)
            last_avg_x = sum(pos["distance"][0]
                             for pos in last_frames) / len(last_frames)
            last_avg_y = sum(pos["distance"][1]
                             for pos in last_frames) / len(last_frames)

            # 相対位置の変化
            delta_x = last_avg_x - first_avg_x
            delta_y = last_avg_y - first_avg_y

            # 右側に移動している場合（対向車的な動き）
            if delta_x > 2.0 and delta_y < 0:  # 右側に移動し、かつ後方に移動
                logger.info("Vehicle filtered out: moving right and backward (delta_x=%.2f, delta_y=%.2f) - likely oncoming vehicle", delta_x, delta_y)
                return False

        return True

    def _get_closest_gps_data(self, timestamp: float) -> Tuple[Optional[dict], Optional[dict]]:
        """
        指定されたタイムスタンプに最も近いGPSデータを取得します。

        Args:
            timestamp (float): タイムスタンプ

        Returns:
            Tuple[Optional[dict], Optional[dict]]: 前後のGPSデータ
        """
        prev_data, next_data = None, None
        for data in self.vehicle_data:
            if data["timestamp"] <= timestamp:
                prev_data = data
            elif data["timestamp"] > timestamp:
                next_data = data
                break
        return prev_data, next_data

    def _calculate_speed_and_distance_increment(self, prev_data: dict, next_data: dict, timestamp: float) -> Tuple[float, float]:
        """
        線形補間で速度を計算し、移動距離を算出します。

        Args:
            prev_data (dict): 前のGPSデータ
            next_data (dict): 次のGPSデータ
            timestamp (float): 現在のタイムスタンプ

        Returns:
            Tuple[float, float]: 補間された速度と移動距離
        """
        dt = next_data["timestamp"] - prev_data["timestamp"]
        if dt <= 0:
            return 0.0, 0.0

        ratio = (timestamp - prev_data["timestamp"]) / dt
        speed = prev_data["speed"] + ratio * \
            (next_data["speed"] - prev_data["speed"])
        distance_increment = speed / self.fps
        return speed, distance_increment

    def _update_lane_change_info(self, current_frame: int, current_road_id: str, current_lane_id: str) -> Tuple[str, str, float, int]:
        """
        レーンチェンジ情報を更新します。

        Args:
            current_frame (int): 現在のフレーム番号
            current_road_id (str): 現在の道路ID
            current_lane_id (str): 現在のレーンID

        Returns:
            Tuple[str, str, float, int]: 更新された道路ID、レーンID、進捗、レーンチェンジ方向
        """
        target_road_id, target_lane_id, change_progress, delta_lane = self._get_lane_change_info(
            current_frame)

        if target_road_id is None:
            target_road_id = current_road_id
        if target_lane_id is None:
            target_lane_id = current_lane_id

        if delta_lane != 0:
            try:
                target_lane_id = str(int(current_lane_id) + delta_lane)
            except ValueError:
                logger.warning("Invalid lane_id: %s", current_lane_id)
                target_lane_id = current_lane_id

        return target_road_id, target_lane_id, change_progress, delta_lane

    def generate(self, start_lane_id: Optional[Tuple[str, str]] = None, initial_position: Optional[Tuple[float, float]] = None, offset_vehicle: float = 0.0):
        """
        車両軌跡を生成する

        Parameters:
        - start_lane_id: Tuple(road_id, lane_id)（省略可能）
        - initial_position: Tuple(x, y) 初期位置の座標を強制的に指定する場合
        """
        if initial_position:
            initial_x, initial_y = initial_position
        else:
            # GPSデータの先頭座標を使用
            initial_x, initial_y = self.vehicle_data[0]["x"], self.vehicle_data[0]["y"]

        # 最も近い道路とレーンを取得
        if not start_lane_id:
            closest_road_id, closest_lane_id, _ = self.map_data.get_closest_lane_and_road(
                initial_x, initial_y)
            start_lane_id = (closest_road_id, closest_lane_id)

        # 初期位置のレーン上の先頭からの距離を計算
        lanes_info = self.map_data.get_lane_and_successors(
            *start_lane_id, include_successors=True)
        current_coords = [coord for _, _,
                          coords in lanes_info for coord in coords]
        accumulated_distance = self._calculate_distance_from_start(
            current_coords, (initial_x, initial_y))

        # トラックの後軸中央までの距離をオフセット
        accumulated_distance -= offset_vehicle

        if not start_lane_id:
            raise ValueError(
                "start_lane_id must be provided or determined from initial_position")

        current_road_id, current_lane_id = start_lane_id
        lane_segment_cursor = 0

        # 1FPSごとのタイムスタンプを生成
        start_time = self.vehicle_data[0]["timestamp"]
        end_time = self.vehicle_data[-1]["timestamp"]
        timestamps = np.arange(start_time, end_time, 1.0 / self.fps)

        # 1FPSごとに軌跡を生成
        for timestamp in timestamps:
            prev_data, next_data = self._get_closest_gps_data(timestamp)
            if prev_data is None or next_data is None:
                # タイムスタンプが範囲外の場合はスキップ
                continue

            # 現在のタイムスタンプに対応するフレーム番号を計算
            # 浮動小数点誤差を避けるためround()を使用
            current_frame = round(timestamp * self.fps)

            # 線形補間で速度を計算し、移動距離を算出
            speed, distance_increment = self._calculate_speed_and_distance_increment(
                prev_data, next_data, timestamp)
            accumulated_distance += distance_increment

            # レーンチェンジ情報の取得
            target_road_id, target_lane_id, change_progress, delta_lane = self._update_lane_change_info(
                current_frame, current_road_id, current_lane_id
            )
            if target_road_id is None:
                target_road_id = current_road_id
            if target_lane_id is None or target_lane_id == '0':
                target_lane_id = current_lane_id

            # 現在のレーンの情報を取得（次の道路も含める）
            try:
                lanes_info = self.map_data.get_lane_and_successors(
                    current_road_id, current_lane_id, include_successors=True)
                current_coords = [coord for _, _,
                                  coords in lanes_info for coord in coords]
            except ValueError as e:
                logger.error("Error: %s", e)
                break

            lateral_offset = 0.0
            source = "normal"

            if delta_lane != 0:
                source = "lane_change"
                try:
                    target_lanes_info = self.map_data.get_lane_and_successors(
                        target_road_id, target_lane_id, include_successors=True)
                    target_coords = [
                        coord for _, _, coords in target_lanes_info for coord in coords]
                    lane_distance = self._calculate_lane_distance(
                        current_coords, target_coords, accumulated_distance)

                    # 横方向の変化量を線形補間
                    lateral_offset = lane_distance * change_progress
                except ValueError as e:
                    logger.warning("Warning: %s", e)
                    target_coords = current_coords
                    lateral_offset = 0.0

                # レーンチェンジが完了したら現在のレーンを更新
                if change_progress >= 1.0:
                    current_road_id = target_road_id
                    current_lane_id = target_lane_id
                    current_coords = target_coords
                    lateral_offset = 0.0

            # 位置の補間
            pos_x, pos_y, pos_z, direction_deg = self._interpolate_position_on_lane(
                current_coords,
                lane_segment_cursor,
                accumulated_distance,
                lateral_offset,
                delta_lane
            )

            # 現在のレーン情報を更新（次のループで使用するため）
            if delta_lane != 0 and change_progress >= 1.0:
                current_lane_id = target_lane_id
                current_road_id = target_road_id

            # 軌跡に追加
            self.trajectory.append(
                {
                    "timestamp": timestamp,
                    "frame": current_frame,
                    "pos_x": pos_x,
                    "pos_y": pos_y,
                    "pos_z": pos_z,
                    "roll_rad": 0,
                    "pitch_rad": 0,
                    "yaw_rad": math.radians(direction_deg),
                    "speed": speed * 3.6,
                    "vel_x": speed * math.cos(math.radians(direction_deg)) * 3.6,
                    "vel_y": speed * math.sin(math.radians(direction_deg)) * 3.6,
                    "vel_z": 0,
                    "road_id": current_road_id,
                    "lane_id": current_lane_id,
                    "lateral_offset": lateral_offset,
                    "source": source,
                }
            )

        # 角速度の計算
        self._calculate_angular_velocity()

    def _calculate_distance_from_start(self, lane_coords: List[Tuple[float, float, float]], position: Tuple[float, float]) -> float:
        """
        レーン上の先頭から指定された位置までの距離を計算します。

        Args:
            lane_coords: レーンの座標リスト
            position: 指定された位置 (x, y)

        Returns:
            float: レーン上の先頭からの距離
        """
        return calculate_distance_from_start(lane_coords, position)

    def _is_point_on_segment(self, p1: Tuple[float, float], p2: Tuple[float, float], position: Tuple[float, float]) -> bool:
        """
        指定された位置がセグメント上にあるかを判定します。

        Args:
            p1: セグメントの始点
            p2: セグメントの終点
            position: 判定する位置 (x, y)

        Returns:
            bool: セグメント上にある場合はTrue
        """
        return is_point_on_segment(p1, p2, position)

    def _interpolate_position_on_lane(
        self,
        lane_coords: List[Tuple[float, float, float]],
        start_index: int,
        target_distance: float,
        lateral_offset: float = 0.0,
        delta_lane: int = 0
    ) -> Tuple[float, float, float, float]:
        """
        lane_coords上を target_distance 進んだ位置を補間する。
        lateral_offsetを指定すると、進行方向に対して垂直方向にオフセットした位置を返す。
        delta_laneの符号に基づいて横方向の向きを調整する。

        Returns:
            Tuple[float, float, float, float]: pos_x, pos_y, pos_z, yaw_deg（進行方向）
        """
        return interpolate_position_on_lane(
            lane_coords, start_index, target_distance, lateral_offset, delta_lane
        )

    def _calculate_lane_distance(
        self,
        current_coords: List[Tuple[float, float, float]],
        target_coords: List[Tuple[float, float, float]],
        current_distance: float
    ) -> float:
        """
        現在のレーンと目標レーンの間の距離を計算します。

        Returns:
            float: レーン間の距離（メートル）
        """
        return calculate_lane_distance(current_coords, target_coords, current_distance)

    def _find_point_at_distance(
        self,
        coords: List[Tuple[float, float, float]],
        target_distance: float
    ) -> Tuple[float, float, float]:
        """
        指定された距離の位置の座標を見つけます。
        """
        return find_point_at_distance(coords, target_distance)

    def _calculate_angular_velocity(self):
        """差分から角速度を求めて、各要素に追加"""
        for i in range(1, len(self.trajectory)):
            prev = self.trajectory[i - 1]
            curr = self.trajectory[i]
            dt = curr["timestamp"] - prev["timestamp"]
            if dt <= 0:
                continue
            a_vel_yaw = (curr["yaw_rad"] - prev["yaw_rad"]) / dt
            a_vel_pitch = 0.0
            a_vel_roll = 0.0
            self.trajectory[i]["a_vel_yaw_rad"] = a_vel_yaw
            self.trajectory[i]["a_vel_pitch_rad"] = a_vel_pitch
            self.trajectory[i]["a_vel_roll_rad"] = a_vel_roll

        # 最初のフレームはゼロ
        self.trajectory[0]["a_vel_yaw_rad"] = 0.0
        self.trajectory[0]["a_vel_pitch_rad"] = 0.0
        self.trajectory[0]["a_vel_roll_rad"] = 0.0

    def _is_missing(self, frame):
        return any(start <= frame <= end for (start, end) in self.missing_ranges)

    def _interpolate_lane_id(self, lane_from, lane_to, ratio):
        """今回は単純にlane_idが整数なら切り替えだけでもよいが、必要なら補間可"""
        return interpolate_lane_id(lane_from, lane_to, ratio)

    def get_trajectory_df(self):
        """最終的な出力用データフレーム"""
        return pd.DataFrame(self.trajectory)

    def get_vehicle_data_df(self):
        """入力したデータフレーム"""
        return pd.DataFrame(self.vehicle_data)

    def _closest_point_on_segment(self, position: Tuple[float, float], p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> Tuple[float, float]:
        """
        指定された位置とセグメント上の最近点を計算します。

        Args:
            position: 指定された位置 (x, y)
            p1: セグメントの始点 (x, y, z)
            p2: セグメントの終点 (x, y, z)

        Returns:
            Tuple[float, float]: セグメント上の最近点 (cx, cy)
        """
        return closest_point_on_segment(position, p1, p2)

    def generate_other_vehicle_trajectory(
        self,
        relative_positions: List[dict],
        self_vehicle_df: pd.DataFrame,
        start_frame: int,
        end_frame: int,
        check_direction: bool = True  # 進行方向のチェックを有効にするか
    ) -> Optional[pd.DataFrame]:
        """
        他車両の軌跡を生成する

        Args:
            relative_positions: 他車両の相対位置データ（例: [{"frame": 10, "distance": (x, y)}, ...]）
            self_vehicle_df: 自車両の軌跡データ
            start_frame: 軌跡生成の開始フレーム
            end_frame: 軌跡生成の終了フレーム
            check_direction: 進行方向のチェックを有効にするか

        Returns:
            Optional[pd.DataFrame]: 他車両の軌跡データ（1fpsごとの座標、向き、速度、角速度）、データが不足している場合はNone
        """
        # フレームと相対距離を取得
        frames = [item["frame"] for item in relative_positions]
        distances = [item["distance"] for item in relative_positions]

        # 反対車線の車両をチェック
        if check_direction and not self._check_opposite_lane(relative_positions, self_vehicle_df):
            return None

        # 各フレームで自車両の位置と向きから絶対座標を計算
        absolute_positions = []
        for frame, (rel_x, rel_y) in zip(frames, distances):
            self_vehicle_row = self_vehicle_df[self_vehicle_df["frame"] == frame]
            if self_vehicle_row.empty:
                continue

            self_vehicle_row = self_vehicle_row.iloc[0]
            self_x = self_vehicle_row["pos_x"]
            self_y = self_vehicle_row["pos_y"]
            self_yaw = self_vehicle_row["yaw_rad"]

            # カメラ位置から他車両の絶対位置を計算
            # rel_x: 右が正（カメラ座標系）、左が負
            # rel_y: 前方が正（カメラ座標系）、後方が負
            #
            # 注意: カメラ位置は自車両の後軸中央からオフセットした位置にある
            # self_x, self_y は自車両の後軸中央の位置
            # カメラは自車両の前方に設置されているため、オフセットを考慮する必要がある

            # カメラのオフセット（自車両の後軸中央からカメラまでの距離）
            # この値は車両の構造に依存する（例：フロントバンパーまでの距離）
            camera_offset = self.camera_offset  # メートル（車両の前端までの距離として設定）

            # カメラの絶対位置を計算
            camera_x = self_x + camera_offset * math.cos(self_yaw)
            camera_y = self_y + camera_offset * math.sin(self_yaw)

            # カメラ位置から見た他車両の相対位置を絶対座標に変換
            #
            # 座標変換の詳細：
            # - rel_x: カメラから見て右が正（+）、左が負（-）
            # - rel_y: カメラから見て前方が正（+）、後方が負（-）
            # - 自車両の向き（yaw）を考慮して回転変換を行う
            #
            # カメラ座標系と絶対座標系の関係：
            # - カメラ座標系: 右がx、前がy（自車両に対する相対座標）
            # - 絶対座標系: 東がx、北がy（ワールド座標）
            #
            # 2D回転変換の公式（反時計回りの回転）：
            # x' = x * cos(θ) - y * sin(θ)
            # y' = x * sin(θ) + y * cos(θ)
            #
            # カメラ相対座標をワールド座標に変換
            # 座標変換の符号を修正：左右の定義を正しく反映
            abs_x = camera_x + rel_y * \
                math.cos(self_yaw) + rel_x * math.sin(self_yaw)
            abs_y = camera_y + rel_y * \
                math.sin(self_yaw) - rel_x * math.cos(self_yaw)

            # 他車両が自車両と同じ進行方向か確認（マップベースの方向チェック）
            if check_direction and self.map_data is not None:
                try:
                    self_lane_yaw, _abs_z, _road_id, _lane_id = self.map_data.get_lane_yaw(
                        self_x, self_y)
                    other_lane_yaw, _abs_z, _road_id, _lane_id = self.map_data.get_lane_yaw(
                        abs_x, abs_y)
                    if not self._check_direction(self_lane_yaw, other_lane_yaw):
                        logger.debug("Skipping frame %d: Other vehicle is moving in the opposite direction.", frame)
                        return None
                except ValueError:
                    # マップデータで位置が見つからない場合は、マップベースの方向チェックをスキップ
                    logger.warning("Could not find lane information for position (%.2f, %.2f). Skipping map-based direction check.", abs_x, abs_y)
                    pass

            absolute_positions.append((frame, abs_x, abs_y))

        # フレームと絶対位置を分離
        abs_frames = [pos[0] for pos in absolute_positions]
        abs_coords = [(pos[1], pos[2]) for pos in absolute_positions]

        # 外れ値の除去（絶対座標で実施）
        abs_frames, abs_coords = self._remove_outliers_with_frames(
            abs_frames, abs_coords)

        if len(abs_frames) < 2:
            logger.warning("Insufficient data points after outlier removal. Skipping trajectory generation.")
            return None

        # スプライン補間または線形補間
        result = self._interpolate_positions(abs_frames, abs_coords)
        if result is None:
            logger.warning("Skipping trajectory generation due to insufficient data points.")
            return None

        interpolated_frames, interpolated_positions = result

        # 全フレームのデータを統合
        all_positions = [
            {"frame": frame, "position": position, "source": "interpolated"}
            for frame, position in zip(interpolated_frames, interpolated_positions)
        ]

        # 軌跡データを生成
        trajectory = []
        for data in all_positions:
            frame = data["frame"]
            position = data["position"]
            source = data["source"]

            # position が (x, y, z) または (x, y) の場合に対応
            if len(position) == 3:
                abs_x, abs_y, abs_z = position
            elif len(position) == 2:
                abs_x, abs_y = position
                abs_z = 0.0
            else:
                raise ValueError(f"Unexpected position format: {position}")

            self_vehicle_row = self_vehicle_df[self_vehicle_df["frame"] == frame]
            if self_vehicle_row.empty:
                continue

            # 現在の座標におけるレーンの向きを取得
            try:
                lane_yaw, abs_z, road_id, lane_id = self.map_data.get_lane_yaw(
                    abs_x, abs_y)
            except ValueError:
                # マップデータで位置が見つからない場合は、デフォルト値を使用
                lane_yaw = 0.0
                road_id = ""
                lane_id = "0"

            trajectory.append({
                "timestamp": frame / self.fps,
                "frame": frame,
                "pos_x": abs_x,
                "pos_y": abs_y,
                "pos_z": abs_z,  # 高さ情報を追加
                "roll_rad": 0,
                "pitch_rad": 0,
                "yaw_rad": lane_yaw,  # レーンの向き
                "speed": 0.0,  # 初期値
                "vel_x": 0.0,  # 初期値
                "vel_y": 0.0,  # 初期値
                "vel_z": 0.0,  # 初期値
                "a_vel_yaw_rad": 0.0,  # 初期値
                "a_vel_pitch_rad": 0.0,
                "a_vel_roll_rad": 0.0,
                "source": source,  # 補完の種類を追加
                "road_id": road_id,
                "lane_id": lane_id
            })

        logger.info("Generated trajectory for %d frames.", len(trajectory))
        # 速度と角速度を計算
        for i in range(1, len(trajectory)):
            prev = trajectory[i - 1]
            curr = trajectory[i]

            # 時間差を計算
            dt = curr["timestamp"] - prev["timestamp"]
            if dt <= 0:
                continue

            # 移動量から速度を計算
            dx = curr["pos_x"] - prev["pos_x"]
            dy = curr["pos_y"] - prev["pos_y"]
            speed = math.sqrt(dx**2 + dy**2) / dt * 3.6
            yaw_rad = curr["yaw_rad"]
            vel_x = speed * math.cos(yaw_rad)
            vel_y = speed * math.sin(yaw_rad)
            vel_z = 0.0

            # 角速度を計算
            a_vel_yaw = (curr["yaw_rad"] - prev["yaw_rad"]) / dt

            # データに追加
            trajectory[i]["speed"] = speed
            trajectory[i]["vel_x"] = vel_x
            trajectory[i]["vel_y"] = vel_y
            trajectory[i]["vel_z"] = vel_z
            trajectory[i]["a_vel_yaw_rad"] = a_vel_yaw

        # 最初のフレームの速度と角速度を0に設定
        # trajectory[0]["speed"] = 0.0
        trajectory[0]["speed"] = trajectory[1]["speed"]
        trajectory[0]["vel_x"] = trajectory[1]["vel_x"]
        trajectory[0]["vel_y"] = trajectory[1]["vel_y"]
        trajectory[0]["vel_z"] = trajectory[1]["vel_z"]
        trajectory[0]["a_vel_yaw_rad"] = 0.0

        return pd.DataFrame(trajectory)

    def _remove_outliers_with_frames(self, frames: List[int], data: List[Tuple[float, float]], threshold: float = 5.0) -> Tuple[List[int], List[Tuple[float, float]]]:
        """
        ハズレ値を除去する（フレーム番号との同期を保つ）
        Args:
            frames: フレーム番号のリスト
            data: (x, y) のリスト
            threshold: 外れ値を除去するための閾値
        Returns:
            Tuple[List[int], List[Tuple[float, float]]]: 外れ値を除去したフレーム番号とデータ
        """
        return remove_outliers_with_frames(frames, data, threshold)

    def _interpolate_positions(self, frames: List[int], distances: List[Tuple[float, float]], smoothing_factor: float = 0.5):
        """
        スプライン補間または線形補間を行い、1fpsごとの軌跡を生成する

        Args:
            frames: フレーム番号のリスト
            distances: 各フレームでの相対位置 (x, y) のリスト
            smoothing_factor: スプライン補間の平滑化係数

        Returns:
            Optional[Tuple[np.ndarray, List[Tuple[float, float]]]]: 補間されたフレームと位置、データが不足している場合はNone
        """
        return interpolate_positions(frames, distances, smoothing_factor)

    def _extrapolate_before_first_frame(
        self, first_position: Tuple[float, float],
        first_frame: int, start_frame: int, speed: float
    ):
        """
        初めて認識されたフレーム以前の補完（レーン上を走行する軌跡）

        Args:
            first_position: 初めて認識されたフレームの位置 (x, y)
            first_frame: 初めて認識されたフレーム番号
            start_frame: 補完を開始するフレーム番号
            speed: 平均速度

        Returns:
            Tuple[np.ndarray, List[dict]]: 補完されたフレームと位置（source情報を含む）
        """
        if speed <= 0:
            # 補完する距離がない場合は空のリストを返す
            return []

        # フレーム番号を生成
        pre_frames = np.arange(start_frame, first_frame, 1)
        num_frames = len(pre_frames)
        if num_frames <= 0:
            # 補完するフレームがない場合は空のリストを返す
            return []

        # 総移動距離を計算
        total_time = num_frames / self.fps  # 総移動時間
        total_distance = -1 * speed * total_time  # 総移動距離

        trajectory = self.map_data.get_travel_coordinates(
            first_position, total_distance)

        if trajectory is None:
            return []

        lane_segment_cursor = 0
        accumulated_distance = 0
        lateral_offset = 0.0
        delta_lane = 0
        distance_increment = abs(total_distance) / num_frames

        trajectory_with_source = []
        for i in range(num_frames):
            accumulated_distance += distance_increment
            # スプライン補間または線形補間
            # 位置の補間
            pos_x, pos_y, pos_z, direction_deg = self._interpolate_position_on_lane(
                trajectory, lane_segment_cursor, accumulated_distance, lateral_offset, delta_lane)

            trajectory_with_source.append({
                "frame": int(pre_frames[i]),
                "position": (pos_x, pos_y, pos_z),
                "source": "before_first_frame"
            })

        return trajectory_with_source

    def _extrapolate_after_last_frame(
        self, last_position: Tuple[float, float],
        last_frame: int, end_frame: int, speed: float
    ):
        """
        最後に認識されたフレーム以降の補完

        Args:
            second_last_position: 最後から2番目のフレームの位置 (x, y)
            last_position: 最後のフレームの位置 (x, y)
            last_frame: 最後のフレーム番号
            end_frame: 補完を終了するフレーム番号
            speed: 直前の速度

        Returns:
            Tuple[np.ndarray, List[dict]]: 補完されたフレームと位置（source情報を含む）
        """
        if speed <= 0:
            # 補完する距離がない場合は空のリストを返す
            return []

        # フレーム番号を生成
        post_frames = np.arange(last_frame + 1, end_frame + 1, 1)
        num_frames = len(post_frames)
        if num_frames <= 0:
            # 補完するフレームがない場合は空のリストを返す
            return []

        # 総移動距離を計算
        total_time = num_frames / self.fps
        # 総移動時間
        total_distance = speed * total_time  # 総移動距離

        if total_distance <= 0:
            # 補完する距離がない場合は空のリストを返す
            return []

        trajectory = self.map_data.get_travel_coordinates(
            last_position, total_distance)

        if trajectory is None:
            return []

        lane_segment_cursor = 0
        accumulated_distance = 0
        lateral_offset = 0.0
        delta_lane = 0
        distance_increment = abs(total_distance) / num_frames

        trajectory_with_source = []
        for i in range(num_frames):
            accumulated_distance += distance_increment
            # スプライン補間または線形補間
            # 位置の補間
            pos_x, pos_y, pos_z, direction_deg = self._interpolate_position_on_lane(
                trajectory, lane_segment_cursor, accumulated_distance, lateral_offset, delta_lane)

            trajectory_with_source.append({
                "frame": int(post_frames[i]),
                "position": (pos_x, pos_y, pos_z),
                "source": "after_last_frame"
            })

        return trajectory_with_source
