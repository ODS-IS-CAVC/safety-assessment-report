"""
検出データの平滑化専用スクリプト

segmentation_detection_result.jsonを読み込み、フィルタリング処理を適用して
元のファイルを更新する。元のファイルは自動的にバックアップされる。
"""

import argparse
import json
import os
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Tuple
import numpy as np

logger = logging.getLogger(__name__)

from filters import (
    FilterChain, OutlierFilter, MedianFilter,
    MovingAverageFilter, SeparateAxisFilterChain
)


def convert_numpy_types(obj):
    """NumPy型をPython標準型に変換する再帰関数"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value)
                for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj


def load_segmentation_data(json_path: str) -> Tuple[Dict, Dict]:
    """
    segmentation_detection_result.jsonを読み込む

    Args:
        json_path: JSONファイルのパス

    Returns:
        tuple: (元のJSONデータ, オブジェクトIDごとの相対位置データ)
    """
    with open(json_path, 'r') as f:
        data = json.load(f)

    object_trajectories = {}

    # BBox_centerの距離データを抽出
    for result in data["results"]:
        frame = result["frame"]
        for seg in result["segmentations"]:
            obj_id = seg["obj_id"]
            vehicle_type = seg.get("vehicle_type", "unknown")
            if obj_id not in object_trajectories:
                object_trajectories[obj_id] = []

            # BBox_centerの距離を探す
            for calc in seg["calculate"]:
                if calc.get("calculate_position") == "BBox_center":
                    # distance[0]: x, distance[1]: y
                    distance = calc.get("distance", [])[:2]
                    object_trajectories[obj_id].append({
                        "frame": frame,
                        "vehicle_type": vehicle_type,
                        "distance": tuple(distance),
                        "result_idx": data["results"].index(result),
                        "seg_idx": result["segmentations"].index(seg),
                        "calc_idx": seg["calculate"].index(calc)
                    })
                    break

    return data, object_trajectories


def create_filter_chain(
    outlier_threshold: float,
    median_window: int,
    ma_window: int,
    use_separate_axis: bool = False,
    iterations_x: int = 1,
    iterations_y: int = 1
) -> FilterChain:
    """フィルタチェーンを作成"""
    if use_separate_axis and iterations_x != iterations_y:
        # X軸とY軸で異なるイテレーション回数の場合
        logger.info("Using separate axis filtering: X=%d, Y=%d",
                    iterations_x, iterations_y)
        return SeparateAxisFilterChain(
            outlier_threshold=outlier_threshold,
            median_window=median_window,
            ma_window=ma_window,
            iterations_x=iterations_x,
            iterations_y=iterations_y
        )
    else:
        # 通常のフィルタチェーン（最大イテレーション回数を使用）
        max_iterations = max(iterations_x, iterations_y)
        filters = []
        for i in range(max_iterations):
            filters.extend([
                OutlierFilter(threshold=outlier_threshold),
                MedianFilter(window_size=median_window),
                MovingAverageFilter(window_size=ma_window)
            ])
        return FilterChain(filters)


def apply_filtering(
    object_trajectories: Dict,
    filter_chain: FilterChain
) -> Dict:
    """
    各オブジェクトの軌跡にフィルタリングを適用

    Args:
        object_trajectories: オブジェクトIDごとの相対位置データ
        filter_chain: 適用するフィルタチェーン

    Returns:
        フィルタリング後のオブジェクト軌跡データ
    """
    filtered_trajectories = {}

    for obj_id, detections in object_trajectories.items():
        if len(detections) < 3:
            logger.warning("  Object %s: Too few points (%d), skipping",
                          obj_id, len(detections))
            filtered_trajectories[obj_id] = detections
            continue

        # フレーム番号と相対座標を抽出
        frames = [d["frame"] for d in detections]
        positions = [d["distance"] for d in detections]

        # フィルタリング適用
        filtered_frames, filtered_positions = filter_chain.apply(
            frames, positions
        )

        # 結果を再構築（元のメタデータを保持）
        filtered_detections = []
        for i, (frame, pos) in enumerate(
            zip(filtered_frames, filtered_positions)
        ):
            # 元のフレームに対応するメタデータを探す
            original = next(
                (d for d in detections if d["frame"] == frame), None
            )
            if original:
                filtered_detections.append({
                    "frame": frame,
                    "vehicle_type": original["vehicle_type"],
                    "distance": tuple(pos),
                    "result_idx": original["result_idx"],
                    "seg_idx": original["seg_idx"],
                    "calc_idx": original["calc_idx"]
                })

        filtered_trajectories[obj_id] = filtered_detections

        logger.info("  Object %s: %d -> %d points",
                    obj_id, len(detections), len(filtered_detections))

    return filtered_trajectories


def update_segmentation_json(
    original_data: Dict,
    filtered_trajectories: Dict
) -> Dict:
    """
    元のJSONデータをフィルタリング後の座標で更新

    Args:
        original_data: 元のJSONデータ
        filtered_trajectories: フィルタリング後のオブジェクト軌跡

    Returns:
        更新されたJSONデータ
    """
    # 元のデータをコピー
    updated_data = json.loads(json.dumps(original_data))

    # フィルタリング後の座標でマッピングを作成
    filtered_map = {}
    for obj_id, detections in filtered_trajectories.items():
        for det in detections:
            key = (det["result_idx"], det["seg_idx"], det["calc_idx"])
            filtered_map[key] = det["distance"]

    # JSONを更新
    for result_idx, result in enumerate(updated_data["results"]):
        for seg_idx, seg in enumerate(result["segmentations"]):
            for calc_idx, calc in enumerate(seg["calculate"]):
                if calc.get("calculate_position") == "BBox_center":
                    key = (result_idx, seg_idx, calc_idx)
                    if key in filtered_map:
                        new_distance = filtered_map[key]
                        # distance[0], distance[1]を更新
                        # distance[2] (z座標) は保持
                        if len(calc["distance"]) >= 2:
                            calc["distance"][0] = float(new_distance[0])
                            calc["distance"][1] = float(new_distance[1])

    return updated_data


def main():
    parser = argparse.ArgumentParser(
        description='検出データの平滑化を実行し、元のJSONを更新'
    )
    parser.add_argument(
        '--input_json',
        required=True,
        help='入力JSON (segmentation_detection_result.json)'
    )
    parser.add_argument(
        '--outlier_threshold',
        type=float,
        default=5.0,
        help='外れ値除去の閾値（標準偏差）'
    )
    parser.add_argument(
        '--median_window',
        type=int,
        default=5,
        help='中央値フィルタのウィンドウサイズ'
    )
    parser.add_argument(
        '--ma_window',
        type=int,
        default=9,
        help='移動平均フィルタのウィンドウサイズ'
    )
    parser.add_argument(
        '--iterations_x',
        type=int,
        default=1,
        help='X軸（左右）のフィルタイテレーション回数'
    )
    parser.add_argument(
        '--iterations_y',
        type=int,
        default=10,
        help='Y軸（前後）のフィルタイテレーション回数'
    )
    parser.add_argument(
        '--output_json',
        help='出力JSONファイルパス（省略時: 入力ファイル名_smoothed.json）'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='元のファイルを上書きする（デフォルト: 新しいファイルを作成）'
    )

    args = parser.parse_args()

    logger.info("=== 検出データ平滑化処理 ===")
    logger.info("入力JSON: %s", args.input_json)
    logger.info("外れ値閾値: %sσ", args.outlier_threshold)
    logger.info("中央値ウィンドウ: %d", args.median_window)
    logger.info("移動平均ウィンドウ: %d", args.ma_window)
    logger.info("イテレーション: X=%d, Y=%d", args.iterations_x, args.iterations_y)
    logger.info("")

    # JSONを読み込む
    logger.info("JSONファイルを読み込んでいます...")
    original_data, object_trajectories = load_segmentation_data(
        args.input_json
    )
    logger.info("検出オブジェクト数: %d", len(object_trajectories))
    logger.info("")

    # フィルタチェーンを作成
    use_separate_axis = (args.iterations_x != args.iterations_y)
    filter_chain = create_filter_chain(
        outlier_threshold=args.outlier_threshold,
        median_window=args.median_window,
        ma_window=args.ma_window,
        use_separate_axis=use_separate_axis,
        iterations_x=args.iterations_x,
        iterations_y=args.iterations_y
    )

    # フィルタリング適用
    logger.info("フィルタリングを適用しています...")
    filtered_trajectories = apply_filtering(
        object_trajectories, filter_chain
    )
    logger.info("")

    # JSONを更新
    logger.info("JSONを更新しています...")
    updated_data = update_segmentation_json(
        original_data, filtered_trajectories
    )

    # NumPy型を変換
    updated_data = convert_numpy_types(updated_data)

    # 出力ファイルパスを決定
    if args.overwrite:
        output_path = args.input_json
        # 元のファイルをバックアップ
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{args.input_json}.backup_{timestamp}"
        shutil.copy2(args.input_json, backup_path)
        logger.info("バックアップ作成: %s", backup_path)
    else:
        if args.output_json:
            output_path = args.output_json
        else:
            # デフォルト: 元のファイル名_smoothed.json
            base, ext = os.path.splitext(args.input_json)
            output_path = f"{base}_smoothed{ext}"

    # ファイルを書き込む
    with open(output_path, 'w') as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)

    if args.overwrite:
        logger.info("元のファイルを更新: %s", output_path)
    else:
        logger.info("新しいファイルを作成: %s", output_path)
        logger.info("  元のファイル: %s", args.input_json)
    logger.info("")
    logger.info("=== 処理完了 ===")


if __name__ == "__main__":
    main()
