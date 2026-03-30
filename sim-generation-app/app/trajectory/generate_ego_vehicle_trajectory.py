from typing import List, Tuple, Dict, Optional
import argparse
import json
import logging
import os
from map_data_factory import create_map_data
from trajectory_generator import TrajectoryGenerator, TRAJECTORY_CSV_HEADR
from visualize import plot_road_and_trajectory
import pandas as pd

logger = logging.getLogger(__name__)


def load_map_select_result(file_path: str):
    """
    マップ選択結果を読み込み、road_idとlane_idのペアのリストを返します。
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    # wayIDリストから道路とレーンの組み合わせを取得
    way_ids = [(way["road"], way["lane"]) for way in data["wayID"]]
    return way_ids


def save_trajectory_csv(trajectory_df: pd.DataFrame, output_path: str):
    """
    軌跡データをCSVファイルとして保存します。
    """
    trajectory_df_reordered = trajectory_df[TRAJECTORY_CSV_HEADR]
    trajectory_df_reordered.to_csv(output_path, index=False)
    logger.info("Trajectory data saved to %s", output_path)


def generate_trajectory(
    map_json_path: str,
    map_select_result_path: str,
    gps_csv_path: str,
    output_dir: str = "output",
    config_json_path: str = None,
    fps: float = 30.0,
    is_plot: bool = False
):
    """
    GPSデータとマップ選択結果から車両軌跡を生成します。

    Args:
        map_json_path: 道路ネットワークデータのJSONファイルパス
        map_select_result_path: マップ選択結果のJSONファイルパス
        gps_csv_path: GPSデータのCSVファイルパス
        output_dir: 出力ディレクトリ
    """
    # 出力ディレクトリの作成
    os.makedirs(output_dir, exist_ok=True)

    # マップデータの読み込み
    map_data = create_map_data(map_json_path)

    # マップ選択結果の読み込み
    way_ids = load_map_select_result(map_select_result_path)
    if not way_ids:
        raise ValueError("マップ選択結果が空です")

    # 軌跡生成器の初期化
    generator = TrajectoryGenerator(map_data, fps)

    # GPSデータの読み込み
    generator.load_vehicle_data(gps_csv_path)

    # レーンチェンジ設定の読み込み
    lane_changes = []
    initial_position = None
    if config_json_path:
        """
        NearMiss_Info.json に初期位置とレーンチェンジ情報が含まれている場合の例:
        "initial_position":[
          -2.030213340610741,
          -23.2859032921558
        ],
        "lane_change":[
          {
            "start_frame": 190,
            "end_frame": 300,
            "delta_lane": -1
          }
        ],
        """
        with open(config_json_path, 'r') as f:
            config_data = json.load(f)
            lane_changes = config_data.get("lane_change", [])
            lane_id = config_data.get("lane_id", None)
            initial_position = config_data.get("initial_position", None)
            if initial_position:
                initial_x, initial_y = initial_position
                closest_road_id, closest_lane_id, _ = map_data.get_closest_lane_and_road(
                        initial_x, initial_y)
                way_ids[0] = (closest_road_id, lane_id)


    if lane_changes:
        # レーンチェンジ情報をセット
        generator.set_lane_change_schedule(lane_changes)

    # GPSデータの先頭座標を取得
    vehicle_data_df = generator.get_vehicle_data_df()
    if initial_position is None and not vehicle_data_df.empty:
        first_gps_point = vehicle_data_df.iloc[0]
        initial_position = (first_gps_point["x"], first_gps_point["y"])

    offset_vehicle = 9.33
    # 軌跡の生成
    if initial_position:
        generator.generate(way_ids[0], initial_position=tuple(
            initial_position), offset_vehicle=offset_vehicle)
    else:
        # 軌跡の生成（指定されたroad_idとlane_idを開始位置とする）
        generator.generate(way_ids[0], offset_vehicle=offset_vehicle)

    # 軌跡データをDataFrameとして取得
    trajectory_df = generator.get_trajectory_df()

    # CSVファイルの保存
    save_trajectory_csv(
        trajectory_df,
        os.path.join(output_dir, "vehicle_route_self.csv")
    )

    if is_plot:
        # 軌跡の可視化用のポイントリストを作成
        gps_points = [
            (row["x"], row["y"], row["z"])
            for _, row in vehicle_data_df.iterrows()
        ]
        # 可視化画像の保存
        plot_road_and_trajectory(
            map_data,
            trajectory_df,
            os.path.join(output_dir, "trajectory_visualization.png"),
            way_ids,
            gps_points
        )
        logger.info(
            "Visualization saved as %s",
            os.path.join(output_dir, 'trajectory_visualization.png'))


def main():
    parser = argparse.ArgumentParser(
        description='Generate vehicle trajectory from GPS data and map')
    parser.add_argument('--input_road', required=True,
                        help='Road network JSON file')
    parser.add_argument('--map_select', required=True,
                        help='Map selection result JSON file')
    parser.add_argument('--gps_csv', required=True, help='GPS data CSV file')
    parser.add_argument('--output_dir', default='output',
                        help='Output directory')
    parser.add_argument('--config_path', required=False,
                        help='Lane change configuration JSON file')
    parser.add_argument('--fps', type=float, default=30.0,
                        help='Frames per second for trajectory generation')
    parser.add_argument('--plot', default=False, action="store_true",
                        help="グラフにプロットする")
    args = parser.parse_args()

    generate_trajectory(
        args.input_road,
        args.map_select,
        args.gps_csv,
        args.output_dir,
        args.config_path,
        args.fps,
        args.plot
    )


if __name__ == "__main__":
    main()
