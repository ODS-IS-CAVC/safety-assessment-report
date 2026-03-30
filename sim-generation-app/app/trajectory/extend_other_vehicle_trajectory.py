"""
他車両軌跡をOpenDRIVE上で前後に延長する

CSVファイルから軌跡を読み込み、OpenDRIVE地図上でレーンに沿って
前後に軌跡を延長し、新しいCSVファイルとして保存する。
"""

import argparse
import logging
import pandas as pd
import numpy as np
import math
from typing import List
from map_data_base import MapDataBase
from map_data_factory import create_map_data
from coordinate_utils import interpolate_position_on_lane

logger = logging.getLogger(__name__)


class TrajectoryExtender:
    """軌跡延長クラス"""

    def __init__(self, map_data: MapDataBase, fps: float = 30.0):
        """
        Args:
            map_data: マップデータ
            fps: フレームレート
        """
        self.map_data = map_data
        self.fps = fps

    def _interpolate_position_on_lane(
        self, lane_coords, start_index, target_distance,
        lateral_offset=0.0, delta_lane=0
    ):
        """
        lane_coords上を target_distance 進んだ位置を補間する。
        coordinate_utils.interpolate_position_on_lane に委譲。
        """
        return interpolate_position_on_lane(
            lane_coords, start_index, target_distance,
            lateral_offset, delta_lane
        )

    def _calculate_velocity_vector(
        self, trajectory_df: pd.DataFrame,
        direction: str = "forward"
    ) -> tuple:
        """
        軌跡の速度ベクトルを計算

        Args:
            trajectory_df: 軌跡データフレーム
            direction: "forward" (最初の5フレーム) or "backward" (最後の5フレーム)

        Returns:
            tuple: (vx, vy, vz) 速度ベクトル (m/s)
        """
        velocity_window = min(5, len(trajectory_df))

        if velocity_window >= 2:
            if direction == "forward":
                frames = trajectory_df.iloc[:velocity_window]
            else:  # "backward"
                frames = trajectory_df.iloc[-velocity_window:]

            dx = frames.iloc[-1]["pos_x"] - frames.iloc[0]["pos_x"]
            dy = frames.iloc[-1]["pos_y"] - frames.iloc[0]["pos_y"]
            dz = frames.iloc[-1]["pos_z"] - frames.iloc[0]["pos_z"]
            dt = (velocity_window - 1) / self.fps
            return (dx / dt, dy / dt, dz / dt)
        else:
            # フレームが1つしかない場合は、yaw_radから速度ベクトルを推定
            row = trajectory_df.iloc[0] if direction == "forward" else trajectory_df.iloc[-1]
            yaw = row["yaw_rad"]
            avg_speed = row.get("speed", 0.0)
            if avg_speed == 0.0:
                # speedカラムがない、または0の場合
                avg_speed = 25.0  # デフォルト速度
            return (avg_speed * math.cos(yaw), avg_speed * math.sin(yaw), 0.0)

    def _blend_trajectories(
        self, reference_position: tuple, velocity_vector: tuple,
        frames: np.ndarray, avg_speed: float,
        opendrive_trajectory: List[tuple], direction: str = "after"
    ) -> List[dict]:
        """
        OpenDRIVE軌跡に沿ってフレームデータを生成（道路上を走行）

        Args:
            reference_position: 基準位置 (x, y, z)
            velocity_vector: 速度ベクトル (vx, vy, vz) - フォールバック用
            frames: フレーム番号の配列
            avg_speed: 平均速度
            opendrive_trajectory: OpenDRIVEの線形座標リスト
            direction: "before" or "after"

        Returns:
            List[dict]: 延長された軌跡データ
        """
        num_frames = len(frames)
        if num_frames == 0:
            return []

        # 距離計算
        total_time = num_frames / self.fps
        total_distance = avg_speed * total_time
        if direction == "before":
            total_distance = -total_distance

        distance_increment = abs(total_distance) / num_frames

        extended_trajectory = []

        for i in range(num_frames):
            # OpenDRIVEの線形上の位置（道路上を走行）
            if len(opendrive_trajectory) > 0:
                target_distance = distance_increment * (i + 1)
                pos_x, pos_y, pos_z, yaw_deg = (
                    self._interpolate_position_on_lane(
                        opendrive_trajectory, 0, target_distance,
                        lateral_offset=0.0, delta_lane=0))
            else:
                # OpenDRIVE軌跡が取得できない場合のみ速度ベクトルで移動
                if direction == "before":
                    time_offset = (num_frames - i) / self.fps
                    pos_x = reference_position[0] - velocity_vector[0] * time_offset
                    pos_y = reference_position[1] - velocity_vector[1] * time_offset
                    pos_z = reference_position[2] - velocity_vector[2] * time_offset
                else:
                    time_offset = (i + 1) / self.fps
                    pos_x = reference_position[0] + velocity_vector[0] * time_offset
                    pos_y = reference_position[1] + velocity_vector[1] * time_offset
                    pos_z = reference_position[2] + velocity_vector[2] * time_offset
                yaw_deg = math.degrees(math.atan2(velocity_vector[1], velocity_vector[0]))

            # レーンの向きを取得
            try:
                lane_yaw, _, road_id, lane_id = self.map_data.get_lane_yaw(pos_x, pos_y)
            except ValueError:
                lane_yaw = math.radians(yaw_deg)
                road_id = ""
                lane_id = "0"

            source = "before_first_frame" if direction == "before" else "after_last_frame"

            extended_trajectory.append({
                "timestamp": int(frames[i]) / self.fps,
                "frame": int(frames[i]),
                "pos_x": pos_x,
                "pos_y": pos_y,
                "pos_z": pos_z,
                "roll_rad": 0,
                "pitch_rad": 0,
                "yaw_rad": lane_yaw,
                "speed": avg_speed,
                "a_vel_yaw_rad": 0.0,
                "a_vel_pitch_rad": 0.0,
                "a_vel_roll_rad": 0.0,
                "road_id": road_id,
                "lane_id": lane_id,
                "source": source
            })

        return extended_trajectory

    def extend_before(
        self, trajectory_df: pd.DataFrame,
        start_frame: int, avg_speed: float
    ) -> List[dict]:
        """
        初めて認識されたフレーム以前の補完（レーン上を走行する軌跡）
        1秒（30フレーム）かけて、OpenDRIVEの線形から元の軌跡の速度ベクトルへ滑らかに移行

        Args:
            trajectory_df: 軌跡データフレーム
            start_frame: 補完を開始するフレーム番号
            avg_speed: 平均速度

        Returns:
            List[dict]: 補完された軌跡データ
        """
        if len(trajectory_df) == 0 or avg_speed <= 0:
            return []

        first_row = trajectory_df.iloc[0]
        first_frame = int(first_row["frame"])
        first_position = (first_row["pos_x"], first_row["pos_y"], first_row["pos_z"])

        # フレーム番号を生成
        pre_frames = np.arange(start_frame, first_frame, 1)
        num_frames = len(pre_frames)
        if num_frames <= 0:
            return []

        # 速度ベクトルを計算
        velocity_vector = self._calculate_velocity_vector(trajectory_df, direction="forward")

        # 総移動距離を計算
        total_time = num_frames / self.fps
        total_distance = -1 * avg_speed * total_time  # 負の方向に移動

        # OpenDRIVEの線形上の軌跡を取得
        opendrive_trajectory = self.map_data.get_travel_coordinates(
            (first_position[0], first_position[1]), total_distance)

        if opendrive_trajectory is None:
            opendrive_trajectory = []

        # デバッグ: 取得した座標数と実際の距離を確認
        if len(opendrive_trajectory) > 0:
            trajectory_length = 0.0
            for i in range(len(opendrive_trajectory) - 1):
                dx = opendrive_trajectory[i+1][0] - opendrive_trajectory[i][0]
                dy = opendrive_trajectory[i+1][1] - opendrive_trajectory[i][1]
                trajectory_length += math.sqrt(dx**2 + dy**2)
            logger.debug("extend_before: 取得した座標数=%d, 実際の距離=%.4fm, 必要な距離=%.4fm", len(opendrive_trajectory), trajectory_length, abs(total_distance))

        # 共通関数でブレンド処理
        return self._blend_trajectories(
            first_position, velocity_vector, pre_frames,
            avg_speed, opendrive_trajectory, direction="before"
        )

    def extend_after(
        self, trajectory_df: pd.DataFrame,
        end_frame: int, avg_speed: float
    ) -> List[dict]:
        """
        最後に認識されたフレーム以降の補完
        1秒（30フレーム）かけて、元の速度ベクトルで進む軌跡からOpenDRIVEの線形へ滑らかに移行

        Args:
            trajectory_df: 軌跡データフレーム
            end_frame: 補完を終了するフレーム番号
            avg_speed: 平均速度

        Returns:
            List[dict]: 補完された軌跡データ
        """
        if len(trajectory_df) == 0 or avg_speed <= 0:
            return []

        last_row = trajectory_df.iloc[-1]
        last_frame = int(last_row["frame"])
        last_position = (last_row["pos_x"], last_row["pos_y"], last_row["pos_z"])

        # フレーム番号を生成
        post_frames = np.arange(last_frame + 1, end_frame + 1, 1)
        num_frames = len(post_frames)
        if num_frames <= 0:
            return []

        # 速度ベクトルを計算
        velocity_vector = self._calculate_velocity_vector(trajectory_df, direction="backward")

        # 総移動距離を計算
        total_time = num_frames / self.fps
        total_distance = avg_speed * total_time

        if total_distance <= 0:
            return []

        # OpenDRIVEの線形上の軌跡を取得
        opendrive_trajectory = self.map_data.get_travel_coordinates(
            (last_position[0], last_position[1]), total_distance)

        if opendrive_trajectory is None:
            opendrive_trajectory = []

        # 共通関数でブレンド処理
        return self._blend_trajectories(
            last_position, velocity_vector, post_frames,
            avg_speed, opendrive_trajectory, direction="after"
        )


def calculate_avg_speed(
        trajectory_df: pd.DataFrame, fps: float,
        window: int = 10) -> float:
    """
    軌跡の平均速度を計算

    Args:
        trajectory_df: 軌跡データフレーム
        fps: フレームレート
        window: 速度計算のウィンドウサイズ

    Returns:
        float: 平均速度 (m/s)
    """
    # before_first_frameとafter_last_frameのデータを除外
    if 'source' in trajectory_df.columns:
        original_data = trajectory_df[
            ~trajectory_df['source'].isin(['before_first_frame', 'after_last_frame'])
        ].copy()
        if len(original_data) < 2:
            # 元データがない場合は、全データで計算
            original_data = trajectory_df
    else:
        original_data = trajectory_df

    if len(original_data) < 2:
        return 0.0

    speeds = []
    for i in range(1, min(window + 1, len(original_data))):
        dx = original_data.iloc[i]["pos_x"] - \
            original_data.iloc[i - 1]["pos_x"]
        dy = original_data.iloc[i]["pos_y"] - \
            original_data.iloc[i - 1]["pos_y"]
        distance = math.sqrt(dx**2 + dy**2)
        frame_time = 1 / fps
        speed = distance / frame_time
        speeds.append(speed)

    return sum(speeds) / len(speeds) if speeds else 0.0


def main():
    parser = argparse.ArgumentParser(
        description='Extend other vehicle trajectories on OpenDRIVE')
    parser.add_argument('--input_csv', required=True,
                        help='Path to input trajectory CSV file')
    parser.add_argument('--output_csv', required=True,
                        help='Path to output extended trajectory CSV file')
    parser.add_argument('--road_network', required=True,
                        help='Path to road network JSON file')
    parser.add_argument('--start_frame', type=int, default=0,
                        help='Frame to start extension before first frame')
    parser.add_argument('--end_frame', type=int, required=True,
                        help='Frame to end extension after last frame')
    parser.add_argument('--fps', type=float, default=30.0,
                        help='Frames per second')
    parser.add_argument('--extend_before', action='store_true',
                        help='Enable extension before first frame')
    parser.add_argument('--extend_after', action='store_true',
                        help='Enable extension after last frame')

    args = parser.parse_args()

    # マップデータの読み込み
    map_data = create_map_data(args.road_network)
    extender = TrajectoryExtender(map_data=map_data, fps=args.fps)

    # 軌跡データの読み込み
    trajectory_df = pd.read_csv(args.input_csv)
    logger.info("Loaded trajectory: %d frames", len(trajectory_df))
    frame_min = trajectory_df['frame'].min()
    frame_max = trajectory_df['frame'].max()
    logger.info("  Frame range: %s - %s", frame_min, frame_max)

    # 平均速度を計算
    avg_speed = calculate_avg_speed(trajectory_df, args.fps)
    logger.info("  Average speed: %.2f m/s", avg_speed)

    # 前方への延長
    before_trajectory = []
    if args.extend_before:
        before_trajectory = extender.extend_before(
            trajectory_df, args.start_frame, avg_speed)
        logger.info("Extended before: %d frames", len(before_trajectory))

    # 後方への延長
    after_trajectory = []
    if args.extend_after:
        after_trajectory = extender.extend_after(
            trajectory_df, args.end_frame, avg_speed)
        logger.info("Extended after: %d frames", len(after_trajectory))

    # 全軌跡を統合
    all_trajectory = before_trajectory + \
        trajectory_df.to_dict('records') + after_trajectory

    # DataFrameに変換して保存
    extended_df = pd.DataFrame(all_trajectory)

    # sourceカラムがない場合は追加
    if 'source' not in extended_df.columns:
        extended_df['source'] = 'camera_view'

    extended_df.to_csv(args.output_csv, index=False)
    logger.info("Saved extended trajectory: %s", args.output_csv)
    logger.info("  Total frames: %d", len(extended_df))
    ext_frame_min = extended_df['frame'].min()
    ext_frame_max = extended_df['frame'].max()
    logger.info("  Frame range: %s - %s", ext_frame_min, ext_frame_max)


if __name__ == "__main__":
    main()
