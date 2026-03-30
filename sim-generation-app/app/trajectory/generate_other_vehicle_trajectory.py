import argparse
import json
import logging
from math import sqrt
import os
from map_data_factory import create_map_data
from trajectory_generator import TrajectoryGenerator, TRAJECTORY_CSV_HEADR
import pandas as pd
from visualize import plot_trajectories
import numpy as np

logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """
    NumPy型をPython標準型に変換する再帰関数
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj


def load_detection_data(json_path: str):
    """
    detection_distance_result.jsonを読み込み、オブジェクトIDごとの相対位置データを作成する。

    Args:
        json_path (str): JSONファイルのパス

    Returns:
        dict: オブジェクトIDごとの相対位置データ
    """
    if os.path.exists(json_path) == False:
        return {}

    with open(json_path, 'r') as f:
        data = json.load(f)

    object_trajectories = {}

    for result in data["results"]:
        frame = result["frame"]
        for seg in result["segmentations"]:
            obj_id = seg["obj_id"]
            vehicle_type = seg.get("vehicle_type", "unknown")
            if obj_id not in object_trajectories:
                object_trajectories[obj_id] = []
            for calc in seg["calculate"]:
                if calc.get("calculate_position") == "BBox_center":
                    # "distance"の全要素を取得
                    distance = calc.get("distance", [])[:2]  # x, y のみを使用
                    object_trajectories[obj_id].append(
                        {"frame": frame, "vehicle_type": vehicle_type, "distance": tuple(distance)})

    return object_trajectories


def generate_updated_json(input_json_path: str, output_json_path: str, self_vehicle_df: pd.DataFrame, object_trajectories: dict, other_vehicles: dict):
    """
    detection_distance_result.jsonを更新し、car_abs_pos_result.jsonのような形式で出力する。

    Args:
        input_json_path (str): 元のJSONファイルのパス
        output_json_path (str): 更新後のJSONファイルの出力パス
        self_vehicle_df (pd.DataFrame): 自車両のデータフレーム
        object_trajectories (dict): 他車両の軌跡データ
        other_vehicles (dict): 他車両軌跡絶対座標
    """
    if os.path.exists(input_json_path) == False:
        return

    with open(input_json_path, 'r') as f:
        data = json.load(f)

    camera_parameter = data.get("camera_parameter", {})
    updated_results = []
    epsg = data.get("EPSG", "6678")

    for result in data["results"]:
        frame = int(result["frame"])  # Convert to Python int
        updated_result = {"frame": int(frame), "self": {}, "detections": []}

        # 自車両のデータを追加
        self_data = self_vehicle_df[self_vehicle_df["frame"] == frame]
        if not self_data.empty:
            self_row = self_data.iloc[0]
            vx = self_row.get("vel_x", 0)
            vy = self_row.get("vel_y", 0)
            vz = self_row.get("vel_z", 0)
            velocity = sqrt(vx**2 + vy**2 + vz**2) * 3.6  # m/s to km/h
            updated_result["self"] = {
                "world_coordinate": [
                    float(self_row["pos_x"]),
                    float(self_row["pos_y"]),
                    float(self_row.get("pos_z", 0.0))  # Ensure float type
                ],
                "velocity": float(velocity),
                "yaw": float(self_row.get("yaw_rad", 0.0)),
                "road_correction": {
                    "road": str(self_row.get("road_id", "")),
                    "lane": self_row.get("lane_id", "0")
                }
            }

        # 他車両のデータを追加
        for obj_id, trajectory in object_trajectories.items():
            obj_data = next(
                (item for item in trajectory if item["frame"] == frame), None)
            if obj_data:
                trajectory_df = other_vehicles.get(obj_id)
                if trajectory_df is None:
                    continue
                obj_row = trajectory_df[trajectory_df["frame"] == frame]
                if obj_row.empty:
                    continue

                obj_row = obj_row.iloc[0]
                vehicle_type = obj_data.get("vehicle_type", "unknown")
                updated_result["detections"].append({
                    "obj_id": int(obj_id),
                    "vehicle_type": str(vehicle_type),
                    "world_coordinate": [
                        float(obj_row["pos_x"]),
                        float(obj_row["pos_y"]),
                        float(obj_row.get("pos_z", 0.0))
                    ],
                    "velocity": float(obj_row.get("speed", 0)),
                    "yaw": float(obj_row.get("yaw_rad", 0.0)),
                    "interpolation_type": str(obj_row.get("source", "")),
                    "road_correction": {
                        "road": str(obj_row.get("road_id", "")),
                        "lane": str(obj_row.get("lane_id", "0"))
                    }
                })

        updated_results.append(updated_result)

    # 出力データの作成
    output_data = {
        "camera_parameter": camera_parameter,
        "results": updated_results,
        "EPSG": epsg
    }

    # NumPy型をPython標準型に変換
    output_data = convert_numpy_types(output_data)

    with open(output_json_path, 'w') as f:
        json.dump(output_data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='Generate other vehicle trajectories from detection data')
    parser.add_argument('--self_trajectory', required=True,
                        help='Path to ego vehicle trajectory CSV file')
    parser.add_argument('--input_json', required=True,
                        help='Path to detection_distance_result.json')
    parser.add_argument('--road_network', required=True,
                        help='Path to road network JSON file')
    parser.add_argument('--output_dir', required=True,
                        help='Directory to save generated trajectories')
    parser.add_argument('--fps', type=float, default=30.0,
                        help='Frames per second for trajectory generation')
    parser.add_argument('--camera_offset', type=float, default=9.33,
                        help='Camera offset from vehicle rear axle center (meters)')
    parser.add_argument('--plot', default=False, action="store_true",
                        help="グラフにプロットする")
    args = parser.parse_args()

    # マップデータの読み込み
    map_data = create_map_data(args.road_network)
    generator = TrajectoryGenerator(
        map_data=map_data, fps=args.fps, camera_offset=args.camera_offset)

    # 自車両の軌跡データを読み込み
    self_vehicle_df = pd.read_csv(args.self_trajectory)

    # 自車両の最終フレームを取得
    self_end_frame = self_vehicle_df["frame"].max()

    # detection_distance_result.jsonの読み込み
    object_trajectories = load_detection_data(args.input_json)

    # 出力ディレクトリの作成
    os.makedirs(args.output_dir, exist_ok=True)

    # 各オブジェクトの軌跡を生成
    other_vehicles = {}
    for obj_id, relative_positions in object_trajectories.items():
        # 軌跡データを生成
        start_frame = 0
        trajectory = generator.generate_other_vehicle_trajectory(
            relative_positions, self_vehicle_df, start_frame=start_frame, end_frame=self_end_frame, check_direction=True)

        if trajectory is None:
            continue

        # CSVファイルとして保存
        output_path = os.path.join(
            args.output_dir, f"vehicle_route_{obj_id}.csv")
        trajectory_df_reordered = trajectory[TRAJECTORY_CSV_HEADR[:-1]]
        trajectory_df_reordered.to_csv(output_path, index=False)
        logger.info("Saved trajectory for object %s to %s", obj_id, output_path)

        # 道路情報を保存
        other_vehicles[obj_id] = trajectory

    # 更新されたJSONを保存
    infer_dir = os.path.dirname(args.input_json)
    updated_json_path = os.path.join(
        infer_dir, "updated_detection_result.json")
    generate_updated_json(args.input_json, updated_json_path,
                          self_vehicle_df, object_trajectories, other_vehicles)
    logger.info("Updated detection result saved to %s", updated_json_path)

    if args.plot:
        plot_trajectories(
            self_trajectory=self_vehicle_df,
            other_trajectory_dir=args.output_dir,
            output_plot=os.path.join(args.output_dir, "trajectories_plot.png"),
            map_data=map_data
        )


if __name__ == "__main__":
    main()
