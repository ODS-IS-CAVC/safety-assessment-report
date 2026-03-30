"""
検出データのI/O処理

detection_distance_result.json / filtered_detections.json の
読み込み・書き込み・更新を行うユーティリティ関数群。
"""

import json
import logging
import os
import numpy as np
from typing import Tuple, Dict

logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """NumPy型をPython標準型に変換する再帰関数"""
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


def load_detection_data(json_path: str) -> Tuple[Dict, Dict, bool, Dict]:
    """
    detection_distance_result.jsonまたはfiltered_detections.jsonを読み込み、
    オブジェクトIDごとの相対位置データを作成する

    Args:
        json_path: JSONファイルのパス

    Returns:
        tuple: (元のJSONデータ, オブジェクトIDごとの相対位置データ,
                再フィルタモードかどうか, メタデータ)
    """
    if not os.path.exists(json_path):
        return {}, {}, False, {}

    with open(json_path, 'r') as f:
        data = json.load(f)

    # メタデータを保存（camera_parameter, EPSGなど）
    metadata = {
        k: v for k, v in data.items()
        if k not in ["results", "filtered_detections"]
    }

    object_trajectories = {}

    # filtered_detections.jsonの場合（再フィルタモード）
    if "filtered_detections" in data:
        logger.info("Loading from filtered_detections.json (re-filtering mode)")
        filtered_detections = data["filtered_detections"]
        for obj_id, obj_data in filtered_detections.items():
            frames = obj_data["frames"]
            positions = obj_data["positions"]
            vehicle_type = obj_data.get("vehicle_type", "unknown")

            object_trajectories[int(obj_id)] = []
            for frame, pos in zip(frames, positions):
                object_trajectories[int(obj_id)].append({
                    "frame": frame,
                    "vehicle_type": vehicle_type,
                    "distance": tuple(pos)
                })
        return data, object_trajectories, True, metadata

    # 元のdetection_distance_result.jsonの場合
    for result_idx, result in enumerate(data["results"]):
        frame = result["frame"]
        for seg_idx, seg in enumerate(result["segmentations"]):
            obj_id = seg["obj_id"]
            vehicle_type = seg.get("vehicle_type", "unknown")
            fully_contained = seg.get("fully_contained", False)
            if obj_id not in object_trajectories:
                object_trajectories[obj_id] = []
            for calc_idx, calc in enumerate(seg["calculate"]):
                if calc.get("calculate_position") == "BBox_center":
                    distance = calc.get("distance", [])[:2]  # x, y のみを使用
                    object_trajectories[obj_id].append({
                        "frame": frame,
                        "vehicle_type": vehicle_type,
                        "fully_contained": fully_contained,
                        "distance": tuple(distance),
                        "result_idx": result_idx,
                        "seg_idx": seg_idx,
                        "calc_idx": calc_idx
                    })

    return data, object_trajectories, False, metadata


def update_segmentation_json(
    original_data: Dict,
    filtered_trajectories: Dict
) -> Dict:
    """
    元のJSONデータからフィルタリング後のデータで新しいJSONを構築
    （除去されたポイントは含めない、それ以外の情報は全て保持）

    Args:
        original_data: 元のJSONデータ
        filtered_trajectories: フィルタリング後のオブジェクト軌跡

    Returns:
        更新されたJSONデータ
    """
    # トップレベルのメタデータをコピー（results以外）
    updated_data = {
        k: v for k, v in original_data.items()
        if k != "results"
    }

    # フィルタリング後のポイントをマッピング（残すべきポイント）
    filtered_set = set()
    filtered_coords = {}
    for detections in filtered_trajectories.values():
        for det in detections:
            key = (det["result_idx"], det["seg_idx"], det["calc_idx"])
            filtered_set.add(key)
            filtered_coords[key] = det["distance"]

    # 新しいresultsを構築
    new_results = []
    for result_idx, result in enumerate(original_data["results"]):
        # result要素の全ての情報をコピー（frameやfile等）
        new_result = {k: v for k, v in result.items() if k != "segmentations"}
        new_segmentations = []

        for seg_idx, seg in enumerate(result["segmentations"]):
            # segmentation要素の全ての情報をコピー（fully_contained等）
            new_seg = {k: v for k, v in seg.items() if k != "calculate"}
            new_calculate = []

            for calc_idx, calc in enumerate(seg["calculate"]):
                # BBox_centerの場合のみフィルタリング対象
                if calc.get("calculate_position") == "BBox_center":
                    key = (result_idx, seg_idx, calc_idx)
                    if key in filtered_set:
                        # フィルタリングされたポイント：座標を更新して保持
                        new_calc = calc.copy()
                        new_distance = filtered_coords[key]
                        if len(new_calc["distance"]) >= 2:
                            new_calc["distance"][0] = float(new_distance[0])
                            new_calc["distance"][1] = float(new_distance[1])
                        new_calculate.append(new_calc)
                    # filtered_setに無いものは除去（追加しない）
                else:
                    # BBox_center以外のcalculate_positionは常に保持
                    new_calculate.append(calc.copy())

            # calculateが空でない場合のみsegmentationを追加
            if new_calculate:
                new_seg["calculate"] = new_calculate
                new_segmentations.append(new_seg)

        # segmentationsが空でない場合のみresultを追加
        if new_segmentations:
            new_result["segmentations"] = new_segmentations
            new_results.append(new_result)

    updated_data["results"] = new_results
    return updated_data
