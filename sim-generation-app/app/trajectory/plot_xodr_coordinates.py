import argparse
import json
import logging
import os
from map_data_factory import create_map_data
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import LineString

logger = logging.getLogger(__name__)

"""launch.json
{
    "name": "XODR Plot",
    "type": "debugpy",
    "request": "launch",
    "program": "try_bravs/app/trajectory/plot_xodr_coordinates.py",
    "console": "integratedTerminal",
    "args": [
    "--input_road", "/mnt/efs/try/try_map_data/map_data/02_241129-241210_Scene10/xodr_road_coordinates.json",
    "--output_path", "/mnt/efs/mobilitydx/2_02_241129-241210_Scene10/output/road_network.png",
    ]
}
"""


def plot_map(map_json_path: str, output_path: str = None):
    """
    指定されたJSONファイルから道路情報を読み込み、プロットする

    Args:
        map_json_path (str): 道路情報を含むJSONファイルのパス
        output_path (str): プロット画像を保存するパス（指定しない場合は表示のみ）
    """
    # MapDataクラスを使用してデータを読み込む
    map_data = create_map_data(map_json_path)

    # プロットの準備
    plt.figure(figsize=(10, 8))
    plt.title("Road Network")
    plt.xlabel("X Coordinate")
    plt.ylabel("Y Coordinate")

    # 道路とレーンをプロット
    for road_id, road in map_data.roads.items():
        for lane in road.lanes:
            coords = lane.coordinate
            line = LineString(coords)
            x, y = line.xy
            plt.plot(x, y, label=f"{road.name} {road_id}, Lane {lane.lane_id}")

    # 凡例を追加（グラフの外に配置）
    plt.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize="small")

    # グリッドを追加
    plt.grid(True)

    # プロットを保存または表示
    if output_path:
        # bbox_inches="tight"で凡例を含めて保存
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        plt.savefig(output_path, bbox_inches="tight")
        logger.info("プロットを保存しました: %s", output_path)
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description='道路ネットワークをグラフにプロット')
    parser.add_argument('--input_road', required=True,
                        help='Road network JSON file')
    parser.add_argument('--output_path', default='',
                        help='Output directory')
    args = parser.parse_args()

    # プロット
    plot_map(args.input_road, args.output_path)


if __name__ == "__main__":
    main()
