import argparse
import os
import json
import logging
import numpy as np
from collections import defaultdict, deque
from scipy.spatial.distance import euclidean
import csv
from visualize import plot_distance_graphs

logger = logging.getLogger(__name__)


def load_data(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data, data['results']


def save_data(path, data, results):
    data['results'] = results
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def save_results(data, updated_frames, out_path):
    data['results'] = updated_frames
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2)


def get_features(detection):
    point = np.array(detection['detection_point'])
    distance = np.array(detection['distance'])
    return point, distance


def track_objects(frames, pix_thresh=50, max_lost_frames=200):
    """
    フレームごとの物体をトラッキングし、obj_idを再割り当てする。

    Args:
        frames (list): 各フレームの検出結果リスト。
        pix_thresh (float): ピクセル距離の閾値。
        max_lost_frames (int): 最大追跡可能フレーム数。

    Returns:
        list: 更新されたフレームデータ。
        dict: トラッキング履歴。
    """
    next_id = 1
    # track_id -> deque of (frame_idx, point)
    track_history = defaultdict(deque)
    frame_idx_map = {}

    for frame in frames:
        frame_idx = frame['frame']
        frame_idx_map[frame_idx] = frame
        current_assignments = {}

        for det in frame['detections']:
            dp = np.array(det['detection_point'])
            best_match = None
            best_id = None

            for track_id, history in track_history.items():
                # 古い履歴は無視
                recent_entries = [
                    entry for entry in history if frame_idx - entry[0] <= max_lost_frames]
                if not recent_entries:
                    continue

                # 最新の位置と比較
                last_frame, last_dp = recent_entries[-1]
                pix_dist = euclidean(dp, last_dp)

                if pix_dist < pix_thresh:
                    if best_match is None or pix_dist < best_match:
                        best_match = pix_dist
                        best_id = track_id

            if best_id is None:
                best_id = next_id
                next_id += 1

            det['obj_id_prev'] = det.get('obj_id', None)
            det['obj_id'] = best_id
            current_assignments[best_id] = (frame_idx, dp)

        # トラック更新
        for tid, (f, p) in current_assignments.items():
            track_history[tid].append((f, p))
            # 履歴が長すぎないようにする（オプション）
            if len(track_history[tid]) > max_lost_frames:
                track_history[tid].popleft()

    return frames, track_history


def analyze_tracking(input_path, output_csv_path):
    _, results = load_data(input_path)

    obj_data = defaultdict(list)

    for frame in results:
        frame_idx = frame['frame']
        for det in frame['detections']:
            tid = det.get('obj_id')
            if tid is not None:
                obj_data[tid].append(frame_idx)

    with open(output_csv_path, 'w', newline='') as csvfile:
        fieldnames = ['obj_id', 'start_frame',
                      'end_frame', 'total_detections']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for tid, frames in obj_data.items():
            writer.writerow({
                'obj_id': tid,
                'start_frame': min(frames),
                'end_frame': max(frames),
                'total_detections': len(frames)
            })

    logger.info("統計を書き出しました: %s", output_csv_path)


def main():
    parser = argparse.ArgumentParser(
        description='Optimize Tracking Result by Reassigning IDs')
    parser.add_argument('--input_path', required=True,
                        help='Path to detection_distance_result.json')
    parser.add_argument('--output_path', required=True,
                        help='Path to save reassigned detection result')
    parser.add_argument('--pix_thresh', type=float, default=50.0,
                        help='Pixel distance threshold for ID reassignment')
    parser.add_argument('--max_lost_frames', type=int, default=300,
                        help='Max frames to keep track history')
    args = parser.parse_args()

    # 引数の取得
    data, results = load_data(args.input_path)
    plot_distance_graphs(results,
                         args.input_path.replace('.json', '_distance.png'))
    # トラッキング実行
    updated_results, track_history = track_objects(
        results, args.pix_thresh, args.max_lost_frames)

    # 保存
    output_dir = os.path.dirname(args.output_path)
    os.makedirs(output_dir, exist_ok=True)
    save_data(args.output_path, data, updated_results)
    logger.info("保存しました: %s", args.output_path)

    analyze_tracking(args.output_path,
                     args.output_path.replace('.json', '_analysis.csv'))

    # グラフをプロット
    plot_distance_graphs(updated_results,
                         args.output_path.replace('.json', '_distance.png'))


if __name__ == '__main__':
    main()
