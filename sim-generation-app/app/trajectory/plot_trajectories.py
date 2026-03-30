
import argparse
import logging
import os
import pandas as pd
from map_data_factory import create_map_data
from visualize import plot_trajectories

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Generate other vehicle trajectories from detection data')
    parser.add_argument('--self_trajectory', required=True,
                        help='Path to ego vehicle trajectory CSV file')
    parser.add_argument('--other_trajectory_dir', required=True,
                        help='Directory containing other vehicle trajectories')
    parser.add_argument('--road_network', required=True,
                        help='Path to road network JSON file')
    parser.add_argument('--output_path', required=True,
                        help='path to save generated trajectories')
    args = parser.parse_args()

    # マップデータオブジェクト
    map_data = create_map_data(args.road_network)

    # 自車両の軌跡データを読み込む
    if not os.path.exists(args.self_trajectory):
        logger.error("Self trajectory file not found: %s", args.self_trajectory)
        return
    self_trajectory = pd.read_csv(args.self_trajectory)

    # 他車両の軌跡データディレクトリを確認
    output_dir = os.path.dirname(args.output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(args.other_trajectory_dir):
        logger.error(
            "Other trajectory directory not found: %s", args.other_trajectory_dir)
        return

    # プロットを実行
    plot_trajectories(self_trajectory,
                      args.other_trajectory_dir,
                      args.output_path,
                      map_data)
    logger.info("Plot saved to %s", args.output_path)


if __name__ == "__main__":
    main()
