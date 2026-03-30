import logging
import matplotlib.pyplot as plt
from typing import List, Tuple, Dict, Set, Optional
from map_data import MapData
import matplotlib.cm as cm
import numpy as np
import os
import pandas as pd

logger = logging.getLogger(__name__)


def plot_road_and_trajectory(
    map_data: MapData,
    self_trajectory: pd.DataFrame,
    output_path: str,
    way_ids: Optional[List[Tuple[str, str]]] = None,
    gps_points: Optional[List[Tuple[float, float]]] = None
):
    """
    道路ネットワークと軌跡を可視化して保存する。
    自車両の範囲に基づいてプロット範囲を絞る。
    """
    fig, ax = plt.subplots(figsize=(14, 10))

    # 自車両の範囲を計算
    x_coords = self_trajectory["pos_x"]
    y_coords = self_trajectory["pos_y"]
    margin = 50  # 自車両の範囲に余白を追加
    x_min, x_max = x_coords.min() - margin, x_coords.max() + margin
    y_min, y_max = y_coords.min() - margin, y_coords.max() + margin
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    # way_ids から対象となる道路IDのセットを取得
    target_road_ids: Set[str] = set()
    if way_ids:
        target_road_ids = {road_id for road_id, _ in way_ids}

    # 道路IDごとに色を割り当てる（対象道路のみ）
    target_road_ids_list = sorted(list(target_road_ids))
    colors = cm.viridis(np.linspace(0, 1, len(target_road_ids_list)))
    road_color_map: Dict[str, Tuple[float, float, float, float]] = {
        road_id: color for road_id, color in zip(target_road_ids_list, colors)
    }

    # 道路ネットワークの描画
    plotted_roads = set()  # 凡例の重複を防ぐ
    for road_id, road in map_data.roads.items():
        # 対象道路かどうかを判定
        if road_id not in target_road_ids:
            continue  # 対象外の道路はスキップ

        color = road_color_map.get(road_id, 'black')  # 対象道路の色
        # ラベルは未プロットの場合のみ設定
        label = f'Road {road_id}' if road_id not in plotted_roads else None
        linewidth = 0.5
        alpha = 0.9
        zorder = 3  # 道路を背景に描画

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
            # 最初のレーンのみラベル付け（対象道路の場合のみ）
            current_label = label if lane == road.lanes[0] and label else None
            ax.plot(
                x_coords,
                y_coords,
                color=color,
                linewidth=linewidth,
                alpha=alpha,
                label=current_label,
                zorder=zorder
            )

        if label:
            plotted_roads.add(road_id)  # プロット済みとして記録

    # GPS座標の描画
    if gps_points:
        gps_x_coords = [p[0] for p in gps_points]
        gps_y_coords = [p[1] for p in gps_points]
        ax.scatter(gps_x_coords, gps_y_coords, c='blue', s=5,
                   label='GPS Points', zorder=4)  # GPS座標を中間層に描画

    # 自車両の軌跡を最優先で描画
    for i in range(len(self_trajectory) - 1):
        row1 = self_trajectory.iloc[i]
        row2 = self_trajectory.iloc[i + 1]

        x1, y1, source1 = row1["pos_x"], row1["pos_y"], row1.get(
            "source", "normal")
        x2, y2, source2 = row2["pos_x"], row2["pos_y"], row2.get(
            "source", "normal")

        # 軌跡のスタイルを決定
        linestyle = '--' if source1 != "normal" or source2 != "normal" else '-'
        ax.plot(
            [x1, x2],
            [y1, y2],
            color='blue',
            linestyle=linestyle,
            linewidth=1,
            zorder=5
        )

    # 1秒ごとにフレーム数をプロット
    self_trajectory_1s = self_trajectory[self_trajectory["timestamp"] % 1 == 0]
    for _, row in self_trajectory_1s.iterrows():
        ax.text(row["pos_x"], row["pos_y"], str(int(row["frame"])),
                fontsize=8, color="blue", zorder=6)

    ax.axis('equal')
    ax.grid(True)

    # 凡例をグラフの外（右側）に表示
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels,
                  bbox_to_anchor=(1.05, 1),
                  loc='upper left',
                  borderaxespad=0.)

    plt.title('Road Network and Ego Vehicle Trajectory')
    plt.tight_layout(rect=[0, 0, 0.85, 1])  # 右側にスペースを確保
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.show()
    plt.close(fig)


def plot_trajectories(self_trajectory: pd.DataFrame, other_trajectory_dir: str, output_plot: str, map_data: MapData):
    """
    自車両と他車両の軌跡をプロットし、自車両の範囲に絞って道路や他車両の軌跡を表示する。
    また、sourceがinterpolated以外は点線で描画する。

    Args:
        self_trajectory (pd.DataFrame): 自車両の軌跡データ
        other_trajectory_dir (str): 他車両の軌跡データが保存されているディレクトリ
        output_plot (str): プロット画像を保存するファイルパス
        map_data (MapData): マップデータオブジェクト
    """
    fig, ax = plt.subplots(figsize=(14, 10))

    # 自車両の範囲を計算
    x_coords = self_trajectory["pos_x"]
    y_coords = self_trajectory["pos_y"]
    margin = 50  # 自車両の範囲に余白を追加
    x_min, x_max = x_coords.min() - margin, x_coords.max() + margin
    y_min, y_max = y_coords.min() - margin, y_coords.max() + margin
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)

    # 道路ネットワークの描画
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
            ax.plot(
                x_coords,
                y_coords,
                color="gray",
                linewidth=0.5,
                alpha=0.7,
                label=None,
                zorder=1
            )

    # 自車両の軌跡を描画
    ax.plot(
        self_trajectory["pos_x"],
        self_trajectory["pos_y"],
        label="Ego Vehicle",
        color="blue",
        linewidth=2,
        zorder=3
    )

    # 自車両の1秒ごとのframeをプロット
    self_trajectory_1s = self_trajectory[self_trajectory["timestamp"] % 1 == 0]
    for _, row in self_trajectory_1s.iterrows():
        ax.text(row["pos_x"], row["pos_y"], str(int(row["frame"])),
                fontsize=8, color="blue", zorder=4)

    # 他車両の軌跡を描画
    color_map = {}  # 車両ごとの色を保持
    color_palette = plt.cm.tab10(np.linspace(0, 1, 10))  # カラーパレット
    color_index = 0

    for file_name in os.listdir(other_trajectory_dir):
        if file_name.endswith(".csv"):
            other_trajectory_path = os.path.join(
                other_trajectory_dir, file_name)
            other_trajectory = pd.read_csv(other_trajectory_path)

            # 車両ごとの色を決定
            if file_name not in color_map:
                color_map[file_name] = color_palette[color_index %
                                                     len(color_palette)]
                color_index += 1
            vehicle_color = color_map[file_name]

            # 他車両の軌跡をsourceごとに描画
            for source, group in other_trajectory.groupby("source"):
                linestyle = "-" if source == "interpolated" else "--"
                ax.plot(
                    group["pos_x"],
                    group["pos_y"],
                    label=f"Other Vehicle ({file_name}, {source})",
                    linestyle=linestyle,
                    color=vehicle_color,  # 車両ごとに同じ色
                    linewidth=1.5,
                    zorder=2
                )

            # 他車両の1秒ごとのframeをプロット
            other_trajectory_1s = other_trajectory[other_trajectory["timestamp"] % 1 == 0]
            for _, row in other_trajectory_1s.iterrows():
                ax.text(row["pos_x"], row["pos_y"], str(
                    int(row["frame"])), fontsize=8, color=vehicle_color, zorder=4)

    # グラフの装飾
    ax.axis("equal")
    ax.grid(True)
    ax.set_title(
        "Vehicle Trajectories with Frames (1-second intervals)", fontsize=16)
    ax.set_xlabel("X Position (m)", fontsize=14)
    ax.set_ylabel("Y Position (m)", fontsize=14)

    # 凡例をグラフの外側に配置
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(handles, labels, loc="upper center",
                  bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=10)

    # プロットを保存
    plt.tight_layout()
    plt.savefig(output_plot, bbox_inches="tight")
    logger.info("Trajectory plot saved to %s", output_plot)

    # プロットを表示
    plt.show()
    plt.close(fig)


def plot_distance_graphs(results, output_plot_path):
    """
    フレームごとにdistance[0]とdistance[1]をobj_id毎に色分けしてプロットする。

    Args:
        results (list): JSONファイルの "results" セクション
        output_plot_path (str): プロット画像を保存するパス
    """
    # フレームごとのデータを収集
    frame_data = {}
    for result in results:
        frame = result["frame"]
        for detection in result.get("detections", []):
            obj_id = detection["obj_id"]
            distance = detection["distance"]
            if frame not in frame_data:
                frame_data[frame] = []
            frame_data[frame].append((obj_id, distance))

    # プロット用データを準備
    frames = sorted(frame_data.keys())
    obj_ids = set()
    distance_0_data = {}
    distance_1_data = {}

    for frame in frames:
        for obj_id, distance in frame_data[frame]:
            obj_ids.add(obj_id)
            if obj_id not in distance_0_data:
                distance_0_data[obj_id] = ([], [])
            if obj_id not in distance_1_data:
                distance_1_data[obj_id] = ([], [])
            distance_0_data[obj_id][0].append(frame)
            distance_0_data[obj_id][1].append(distance[0])
            distance_1_data[obj_id][0].append(frame)
            distance_1_data[obj_id][1].append(distance[1])

    # 色をobj_idごとに割り当て
    colors = plt.cm.tab10(np.linspace(0, 1, len(obj_ids)))
    obj_id_color_map = {obj_id: color for obj_id,
                        color in zip(sorted(obj_ids), colors)}

    # グラフの作成
    fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    # distance[0]のプロット
    for obj_id, (x, y) in distance_0_data.items():
        axes[0].plot(x, y, label=f"obj_id {obj_id}",
                     color=obj_id_color_map[obj_id])
    axes[0].set_title("Distance[0] vs Frame", fontsize=14)
    axes[0].set_ylabel("Distance[0]", fontsize=12)
    axes[0].grid(True)

    # distance[1]のプロット
    for obj_id, (x, y) in distance_1_data.items():
        axes[1].plot(x, y, label=f"obj_id {obj_id}",
                     color=obj_id_color_map[obj_id])
    axes[1].set_title("Distance[1] vs Frame", fontsize=14)
    axes[1].set_xlabel("Frame", fontsize=12)
    axes[1].set_ylabel("Distance[1]", fontsize=12)
    axes[1].grid(True)

    # 凡例をグラフの上部中央に表示
    handles, labels = axes[0].get_legend_handles_labels()  # 凡例を取得
    fig.legend(handles, labels, loc='upper center',
               bbox_to_anchor=(0.5, 1.05), ncol=5, fontsize=10)
    plt.tight_layout(rect=[0, 0, 1, 0.95])  # レイアウト調整

    # プロットを保存
    plt.savefig(output_plot_path, dpi=300, bbox_inches='tight')
    logger.info("Plot saved to %s", output_plot_path)

    # プロットを表示
    # plt.show()
