
import argparse
import logging
import os
import json
import numpy as np
from map_data_factory import create_map_data
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

logger = logging.getLogger(__name__)


"""
VSCodeのデバッグ設定
{
    "name": "Plot Trajectories Summary",
    "type": "debugpy",
    "request": "launch",
    "program": "try_bravs/plot_trajectories_summary.py",
    "console": "integratedTerminal",
    "args": [
        "--summary_json", "/mnt/efs/mobilitydx/1_02_241013-241018_Scene05/trajectory/output/trajectory_summary.json",
        "--road_network", "/mnt/efs/try/try_map_data/map_data/02_241013-241018_Scene5/xodr_road_coordinates.json",
        "--output_dir",   "/mnt/efs/mobilitydx/1_02_241013-241018_Scene05/trajectory/scenario",
        "--limit_normal", "70",
        "--limit_zoom",   "20",
    ]
},
"""


def transform_relative_to_absolute(x_rel, y_rel, x_car, y_car, theta_car):
    """
    相対座標を絶対座標系に変換します。

    Parameters:
    - x_rel, y_rel: 自車から見た相対座標
    - x_car, y_car: 自車の絶対座標
    - theta_car: 自車の向き（ラジアン）

    Returns:
    - x_global, y_global: 絶対座標系における座標
    """

    # 回転行列を作成
    rotation_matrix = np.array([
        [np.cos(theta_car), -np.sin(theta_car)],
        [np.sin(theta_car), np.cos(theta_car)]
    ])

    # 相対座標を転置し、2x1のベクトルに
    relative_position = np.array([x_rel, y_rel])

    # 絶対座標系での位置を計算
    global_position = rotation_matrix.dot(
        relative_position) + np.array([x_car, y_car])

    return global_position[0], global_position[1]


def get_square_points(vehicle_type, pos_x, pos_y, yaw_rad):
    # トラックのサイズ
    t_w = 2.5
    t_l = 12.0

    # 普通車のサイズ
    v_w = 1.8
    v_l = 4.7
    if vehicle_type == "Truck":
        # Hino Proria（トラック）
        # 　前方向：9.33
        # 　後方向：2.54
        # 　横方向：1.28
        x_front = 9.33
        x_rear = -2.54
        width = 1.28
    elif vehicle_type == "Car":
        # Honda Freed（カー）
        #  前方向：2.9
        #  後方向：1.39
        #  横方向：0.85
        x_front = 2.9
        x_rear = -1.39
        width = 0.85
    elif vehicle_type == "motorcycle":
        # Honda CB1300（バイク）
        #  前方向：1.47
        #  後方向：0.73
        #  横方向：0.405
        x_front = 1.47
        x_rear = -0.73
        width = 0.405
    else:
        # Honda Freed（カー）
        #  前方向：2.9
        #  後方向：1.39
        #  横方向：0.85
        x_front = 2.9
        x_rear = -1.39
        width = 0.85

    fr_x, fr_y = transform_relative_to_absolute(
        x_front, width, pos_x, pos_y, yaw_rad)
    fl_x, fl_y = transform_relative_to_absolute(
        x_front, -width, pos_x, pos_y, yaw_rad)
    rr_x, rr_y = transform_relative_to_absolute(
        x_rear, width, pos_x, pos_y, yaw_rad)
    rl_x, rl_y = transform_relative_to_absolute(
        x_rear, -width, pos_x, pos_y, yaw_rad)

    square_points = np.array([
        [fr_x, fr_y],
        [rr_x, rr_y],
        [rl_x, rl_y],
        [fl_x, fl_y],
        [fr_x, fr_y]
    ])

    return square_points


def plot_trajectories(trajectory_data, map_data, output_dir: str, limit_normal=70, limit_zoom=20, skip_zoom=False):
    normal_dir = os.path.join(output_dir, "normal")
    os.makedirs(normal_dir, exist_ok=True)
    if not skip_zoom:
        zoom_dir = os.path.join(output_dir, "zoom")
        os.makedirs(zoom_dir, exist_ok=True)

    fig = plt.figure()
    plt.tick_params(labelsize=9)
    plt.subplots_adjust(left=0.2, right=0.95, bottom=0.15, top=0.90)

    # 車両IDごとの色を設定（タブカラーマップを使用）
    color_list = list(mcolors.TABLEAU_COLORS.values())

    # 0フレーム目のデータを取り出す
    data = trajectory_data.get("0", [])
    if data:
        vehicle = data[0]
        if vehicle:
            ego_x = vehicle.get("pos_x", 0)
            ego_y = vehicle.get("pos_y", 0)
            x_min = ego_x - limit_normal
            x_max = ego_x + limit_normal
            y_min = ego_y - limit_normal
            y_max = ego_y + limit_normal

    for frame, data in trajectory_data.items():
        # フレームごとにデータを処理
        # まず自車両を探して表示範囲を設定
        ego_found = False
        for vehicle in data:
            if vehicle.get("vehicle_id") == 0:
                ego_x = vehicle.get("pos_x", 0)
                ego_y = vehicle.get("pos_y", 0)
                x_min = ego_x - limit_normal
                x_max = ego_x + limit_normal
                y_min = ego_y - limit_normal
                y_max = ego_y + limit_normal
                plt.xlim(x_min, x_max)
                plt.ylim(y_min, y_max)
                ego_found = True
                break

        # 自車両がいない場合は前のフレームの範囲を維持（xlim/ylimを更新しない）

        for vehicle in data:
            vechicle_id = vehicle.get("vehicle_id", None)
            if vechicle_id is None:
                continue

            # カメラ内/外の判定（破線/実線）
            source = vehicle.get("source", "interpolated")
            is_camera_outside = source in ["before_first_frame", "after_last_frame"]
            linestyle = '--' if is_camera_outside else '-'

            if vechicle_id == 0:
                # 自車両は常に赤
                color = 'r'
            else:
                # 他車両は車両IDに応じた色
                color_index = (vechicle_id - 1) % len(color_list)
                color = color_list[color_index]

            vehicle_type = vehicle.get("vehicle_type", "unknown")
            square_points = get_square_points(
                vehicle_type,
                vehicle.get("pos_x", 0),
                vehicle.get("pos_y", 0),
                vehicle.get("yaw_rad", 0)
            )
            plt.plot(square_points[:, 0], square_points[:, 1], color=color, linestyle=linestyle)

        # OpenDRIVEの車線を描画
        for road_id, road in map_data.roads.items():
            for lane in road.lanes:
                coords = lane.coordinate
                # 自車両の範囲内にある座標のみをフィルタリング
                filtered_coords = [
                    (x, y) for coord in coords for x, y in [coord[:2]] if x_min <= x <= x_max and y_min <= y <= y_max
                ]
                if not filtered_coords:
                    continue  # 範囲内に座標がない場合はスキップ

                x_coords = [p[0] for p in filtered_coords]
                y_coords = [p[1] for p in filtered_coords]
                plt.plot(
                    x_coords,
                    y_coords,
                    color="gray",
                    linewidth=0.5,
                    alpha=0.7,
                    label=None,
                    zorder=1
                )

        plt.xlabel('X (m)', fontsize=10)
        plt.ylabel('Y (m)', fontsize=10)
        plt.title('Top view', fontsize=10)
        # 通常表示
        normal_path = os.path.join(normal_dir, f"{frame}.png")
        plt.savefig(normal_path)
        # ズーム表示（skip_zoomがFalseの場合のみ）
        if not skip_zoom:
            plt.xlim(ego_x - limit_zoom, ego_x + limit_zoom)
            plt.ylim(ego_y - limit_zoom, ego_y + limit_zoom)
            zoom_path = os.path.join(zoom_dir, f"{frame}.png")
            plt.savefig(zoom_path)
        # 表示クリア
        plt.cla()


def main():
    parser = argparse.ArgumentParser(
        description='Generate other vehicle trajectories from detection data')
    parser.add_argument('--summary_json', required=True,
                        help='Path to ego vehicle trajectory summary json file')
    parser.add_argument('--road_network', required=True,
                        help='Path to road network JSON file')
    parser.add_argument('--output_dir', required=True,
                        help='path to save generated trajectories')
    parser.add_argument('--limit_normal', default=70, type=int,
                        help='Limit for normal view')
    parser.add_argument('--limit_zoom', default=20, type=int,
                        help='Limit for zoomed view')
    parser.add_argument('--skip_zoom', action='store_true',
                        help='Skip generating zoom images')
    args = parser.parse_args()

    # マップデータオブジェクト
    map_data = create_map_data(args.road_network)

    # 自車両の軌跡データを読み込む
    summary_json_path = args.summary_json
    if not os.path.exists(summary_json_path):
        logger.error("Trajectory summary file not found: %s", summary_json_path)
        return

    with open(summary_json_path, 'r') as f:
        summary_data = json.load(f)

    # 他車両の軌跡データディレクトリを確認
    output_dir = args.output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    limit_normal = args.limit_normal
    limit_zoom = args.limit_zoom
    plot_trajectories(summary_data, map_data, output_dir,
                      limit_normal, limit_zoom, skip_zoom=args.skip_zoom)


if __name__ == "__main__":
    main()
