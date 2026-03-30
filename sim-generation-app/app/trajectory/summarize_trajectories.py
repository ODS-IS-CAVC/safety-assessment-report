import argparse
import json
import csv
import os
import sys
import re
import pandas as pd
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# scenario_util から get_route_csv_files をインポート
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scenario'))
from scenario_util import get_route_csv_files


def extract_number_from_filename(filename):
    if "route" not in filename:
        return None

    if "self" in filename:
        return "self"
    elif "ego" in filename:
        return "ego"
    else:
        match = re.search(r'_(\d+)+', filename)
        if match:
            return match.group(1)
    return None


def get_vehicle_type(segmentation_result_json_path):
    """
    segmentation_detection_result.json から obj_id ごとに各フレームの vehicle_type を集計し、
    最頻値（最も多い vehicle_type）を返す。
    Args:
        segmentation_result_json_path (str): segmentation_detection_result.json のパス
    Returns:
        dict: obj_id ごとの最頻 vehicle_type
    """
    if not os.path.exists(segmentation_result_json_path):
        logger.warning("Input JSON file %s does not exist.", segmentation_result_json_path)
        return {}
    with open(segmentation_result_json_path, 'r') as f:
        data = json.load(f)
    if "results" not in data:
        logger.warning("No 'results' in %s", segmentation_result_json_path)
        return {}

    # obj_id ごとに vehicle_type を集計
    from collections import Counter, defaultdict
    obj_vehicle_types = defaultdict(list)
    for result in data["results"]:
        segmentations = result.get("segmentations", [])
        for seg in segmentations:
            obj_id = seg.get("obj_id")
            vehicle_type = seg.get("vehicle_type")
            if obj_id is not None and vehicle_type is not None:
                obj_vehicle_types[obj_id].append(vehicle_type)
    # 最頻値を決定
    vehicle_type_dict = {}
    for obj_id, types in obj_vehicle_types.items():
        if types:
            most_common = Counter(types).most_common(1)[0][0]
            vehicle_type_dict[obj_id] = most_common
    return vehicle_type_dict


def summarize_trajectories(detection_result_path, trajectory_dir, prefer_extended=True, exclude_camera_outside=False):
    """
    車両の軌跡を要約し、JSON形式で保存する。
    Args:
        detect_result_json (str): 測距結果のJSONファイルパス
        trajectory_dir (str): 軌跡データのディレクトリパス
        prefer_extended (bool): _extended.csvを優先するかどうか
        exclude_camera_outside (bool): カメラ外データを除外するかどうか
    """
    vehicle_type_dic = get_vehicle_type(detection_result_path)

    # CSVファイルの読み込み
    if not os.path.exists(trajectory_dir):
        logger.error("Trajectory directory %s does not exist.", trajectory_dir)
        return None

    car_route_files = get_route_csv_files(trajectory_dir, prefer_extended=prefer_extended)

    route_file_list = {}
    for route_file in car_route_files:
        if not os.path.exists(route_file):
            logger.warning("not exists file: %s", route_file)
            continue
        file_tag = extract_number_from_filename(os.path.basename(route_file))
        if file_tag is None:
            logger.warning("not contain tag. filename: %s", route_file)
            continue
        if file_tag == "self" or file_tag == "ego":
            vechicle_id = 0
        else:
            vechicle_id = int(file_tag)
        route_file_list[vechicle_id] = route_file

    # 車両ID順にソート
    route_file_list = dict(sorted(route_file_list.items()))
    frame_aggregated = defaultdict(list)

    for vechicle_id, route_file in route_file_list.items():
        logger.info("Processing file: %s", route_file)
        try:
            trajectory_df = pd.read_csv(route_file, skipinitialspace=True)
            if trajectory_df.empty:
                logger.warning("Empty trajectory file %s", route_file)
                continue
        except Exception as e:
            logger.error("Error reading file %s: %s", route_file, e)
            continue
        trajectory_data = {}
        for _, row in trajectory_df.iterrows():
            frame = int(row['frame'])
            if frame not in trajectory_data:
                trajectory_data[frame] = []
            row_dict = row.to_dict()
            if vechicle_id == 0:
                vehicle_type = "Truck"
            else:
                vehicle_type = vehicle_type_dic.get(vechicle_id, "unknown")

            vel_x = row_dict.get("vel_x", 0)
            vel_y = row_dict.get("vel_y", 0)
            vel_z = row_dict.get("vel_z", 0)

            # front_left, rear_right の座標を計算

            # sourceフィールド（カメラ内/外の判定用）
            source = row_dict.get("source", "interpolated")

            # カメラ外データを除外する場合
            if exclude_camera_outside and source in ["before_first_frame", "after_last_frame"]:
                continue

            frame_aggregated[frame].append({
                "timestamp": row_dict["timestamp"],
                "frame": row_dict["frame"],
                "vehicle_id": vechicle_id,
                "vehicle_type": vehicle_type,
                "pos_x": row_dict["pos_x"],
                "pos_y": row_dict["pos_y"],
                "pos_z": row_dict["pos_z"],
                "roll_rad": row_dict["roll_rad"],
                "pitch_rad": row_dict["pitch_rad"],
                "yaw_rad": row_dict["yaw_rad"],
                "speed": row_dict["speed"],
                "vel_x": vel_x,
                "vel_y": vel_y,
                "vel_z": vel_z,
                "road_id": row_dict["road_id"],
                "lane_id": row_dict["lane_id"],
                "source": source,
            })

    return frame_aggregated


def save_trajectories_to_csv(summary_data, output_path):
    # データが空でないかチェック
    if not summary_data:
        logger.warning("No data to save to CSV")
        return
    
    # 最初の要素からヘッダーを取得
    first_key = next(iter(summary_data))
    if not summary_data[first_key]:
        logger.warning("Empty data entries")
        return
    
    first_entry = summary_data[first_key][0]
    fieldnames = list(first_entry.keys())

    # CSV出力
    with open(output_path, mode='w', newline='') as csvfile:
        writer = csv.DictWriter(
            csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for frame_data in summary_data.values():
            for entry in frame_data:
                writer.writerow(entry)


def main():
    parser = argparse.ArgumentParser(
        description="Append vehicle type to JSON data")
    parser.add_argument("--detection_result", type=str,
                        help="detect result JSON file path")
    parser.add_argument("--trajectory_dir", type=str,
                        help="trajectory directory path")
    parser.add_argument("--output_dir", type=str,
                        help="Output directory path")
    parser.add_argument("--prefer_extended", action="store_true", default=True,
                        help="_extended.csvがあればそれを優先する（デフォルト: True）")
    parser.add_argument("--no_prefer_extended", action="store_true",
                        help="元のCSVを優先する（_extended.csvは使用しない）")
    parser.add_argument("--exclude_camera_outside", action="store_true",
                        help="カメラ外データ（before_first_frame, after_last_frame）を除外する")
    args = parser.parse_args()

    # --no_prefer_extended が指定された場合は prefer_extended を False に
    prefer_extended = args.prefer_extended
    if args.no_prefer_extended:
        prefer_extended = False

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # 測距結果の読み込み
    detection_result_path = args.detection_result

    summary_data = summarize_trajectories(
        detection_result_path, args.trajectory_dir,
        prefer_extended=prefer_extended,
        exclude_camera_outside=args.exclude_camera_outside)

    if not summary_data:
        logger.error("No trajectory data found or processed")
        return

    # Save updated JSON data
    output_json_path = os.path.join(output_dir, "trajectory_summary.json")
    with open(output_json_path, 'w') as f:
        json.dump(summary_data, f, indent=2)
    logger.info("Successfully processed and saved to %s", output_json_path)

    # CSVファイルに保存
    csv_filename = "trajectories_summary.csv"
    csv_path = os.path.join(output_dir, csv_filename)
    save_trajectories_to_csv(summary_data, csv_path)
    logger.info("CSV file saved to %s", csv_path)


if __name__ == "__main__":
    main()
