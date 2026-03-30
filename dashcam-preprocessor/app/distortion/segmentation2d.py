"""
車両セグメンテーションと追跡モジュール

このモジュールは、動画フレームから車両を検出し、セグメンテーションを行い、
フレーム間で車両を追跡する機能を提供します。YOLOv8を使用した物体検出と
セグメンテーション、そして独自の再識別アルゴリズムにより、一時的に見失った
車両でも同じIDを維持できるようになっています。

主な機能:
- YOLOv8による車両検出とセグメンテーション
- フレーム間での車両追跡
- 見失った車両の再識別
- 車両の底面ポイント（前部左下、後部右下、中央下部）の検出
- トラッキング結果のJSON形式での出力
"""

import os
import glob
import argparse
import shutil
import numpy as np
import cv2
from tqdm import tqdm
from ultralytics import YOLO
# import tensorflow as tf  # TensorFlow is not used in this code
from collections import deque
import json
import torch
import math
import logging

logger = logging.getLogger(__name__)

# 定数定義
OFFSET_THD = 0.03  # 車体全体が画像内にあるかを判定するためのオフセット閾値
MAX_LOST_FRAMES = 30 * 3  # 失われたオブジェクトの履歴を保持する最大フレーム数
POSITION_THRESHOLD = 100  # 位置マッチングのための最大ピクセル距離
IOU_THRESHOLD = 0.2  # バウンディングボックスマッチングのための最小IoU（より柔軟なマッチング）

# 各クラスの平均寸法（高さ、幅、長さ）
dims_avg = {
    'Car': np.asarray([1.52131309, 1.64441358, 3.85728004]),
    'Van': np.asarray([2.18560847, 1.91077601, 5.08042328]),
    'Truck': np.asarray([3.07044968, 2.62877944, 11.17126338]),
    'Pedestrian': np.asarray([1.75562272, 0.67027992, 0.87397566]),
    'Person_sitting': np.asarray([1.28627907, 0.53976744, 0.96906977]),
    'Cyclist': np.asarray([1.73456498, 0.58174006, 1.77485499]),
    'Tram': np.asarray([3.56020305, 2.40172589, 18.60659898])
}
logger.debug("dims_avg: %s", dims_avg)

# YOLOv8モデルの初期化
curr_dir = os.path.dirname(os.path.abspath(__file__))
yolov8_seg_path = os.path.join(curr_dir, 'yolov8x-seg.pt')

bbox2d_model = YOLO(yolov8_seg_path)  # 公式モデルをロード

# モデルパラメータの設定
bbox2d_model.overrides['conf'] = 0.6  # NMS信頼度閾値（より厳格に）
bbox2d_model.overrides['iou'] = 0.5  # NMS IoU閾値（より厳格に）
bbox2d_model.overrides['agnostic_nms'] = True  # クラスに依存しないNMS（異なるクラス間でも重複を除去）
bbox2d_model.overrides['max_det'] = 2000  # 画像あたりの最大検出数
bbox2d_model.overrides['classes'] = 2, 3, 5, 7  # 検出対象クラス（車、バン、トラック、バイク）
bbox2d_model.overrides['imgsz'] = 1280  # 入力画像サイズ

# YOLOクラス名のリスト
yolo_classes = ['Pedestrian', 'Cyclist', 'Car',
                'motorcycle', 'airplane', 'Van', 'train', 'Truck',]

# グローバル追跡変数
tracking_trajectories = {}  # 各オブジェクトの軌跡
lost_objects = {}  # 最近失われたオブジェクトの情報を保存（再識別用）
next_id_map = {}  # 新しいIDから以前のIDへのマッピング
used_ids_in_frame = set()  # 現在のフレームで既に使用されたID


def calculate_iou(box1, box2):
    """
    2つのバウンディングボックス間のIoU（Intersection over Union）を計算する。

    Args:
        box1 (tuple): 最初のバウンディングボックス (xmin, ymin, xmax, ymax)
        box2 (tuple): 2番目のバウンディングボックス (xmin, ymin, xmax, ymax)

    Returns:
        float: IoU値（0.0～1.0）
    """
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    # Calculate intersection area
    x_min = max(x1_min, x2_min)
    y_min = max(y1_min, y2_min)
    x_max = min(x1_max, x2_max)
    y_max = min(y1_max, y2_max)

    if x_max < x_min or y_max < y_min:
        return 0.0

    intersection_area = (x_max - x_min) * (y_max - y_min)

    # Calculate union area
    box1_area = (x1_max - x1_min) * (y1_max - y1_min)
    box2_area = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = box1_area + box2_area - intersection_area

    return intersection_area / union_area if union_area > 0 else 0.0


def calculate_distance(pos1, pos2):
    """
    2つの位置間のユークリッド距離を計算する。

    Args:
        pos1 (tuple): 最初の位置 (x, y)
        pos2 (tuple): 2番目の位置 (x, y)

    Returns:
        float: ユークリッド距離
    """
    return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)


def remove_duplicate_detections(detections, iou_threshold=0.8):
    """
    重複した検出結果を除去する後処理。
    同じ領域に複数の検出がある場合、スコアが最も高いものを残す。

    Args:
        detections (list): 検出結果のリスト [(bbox, score, class, id), ...]
        iou_threshold (float): 重複と判定するIoU閾値

    Returns:
        list: 重複を除去した検出結果
    """
    if len(detections) <= 1:
        return detections

    # スコアの降順でソート
    sorted_detections = sorted(detections, key=lambda x: x[1], reverse=True)
    keep = []

    for i, (bbox_i, score_i, class_i, id_i) in enumerate(sorted_detections):
        duplicate = False

        # 既に保持している検出結果と比較
        for bbox_j, score_j, class_j, id_j in keep:
            iou = calculate_iou(bbox_i, bbox_j)

            # 高いIoUの場合は重複と判定
            if iou > iou_threshold:
                duplicate = True
                # デバッグ情報
                logger.debug(
                    "Removing duplicate: ID %s (score=%.3f, class=%s) overlaps with ID %s (score=%.3f, class=%s), IoU=%.3f",
                    id_i, score_i, class_i, id_j, score_j, class_j, iou)
                break

            # 完全に包含されている場合も重複と判定
            # bbox_iがbbox_jに完全に含まれているか
            if (bbox_i[0] >= bbox_j[0] and bbox_i[1] >= bbox_j[1] and
                    bbox_i[2] <= bbox_j[2] and bbox_i[3] <= bbox_j[3]):
                duplicate = True
                logger.debug(
                    "Removing duplicate: ID %s is contained within ID %s",
                    id_i, id_j)
                break

        if not duplicate:
            keep.append(sorted_detections[i])

    return keep


def find_best_match(new_bbox, new_class, lost_objects_dict):
    """
    位置、IoU、クラスに基づいて、失われたオブジェクトの中から最適なマッチを見つける。

    Args:
        new_bbox (numpy.ndarray): 新しく検出されたバウンディングボックス (xmin, ymin, xmax, ymax)
        new_class (str): 新しく検出されたオブジェクトのクラス
        lost_objects_dict (dict): 失われたオブジェクトの辞書

    Returns:
        int or None: マッチしたオブジェクトのID、マッチがない場合はNone
    """
    best_match_id = None
    best_score = 0

    for lost_id, lost_info in lost_objects_dict.items():
        # Class must match (prefer same class, but allow different classes with penalty)
        class_match = lost_info['class'] == new_class
        if not class_match:
            # Apply penalty for class mismatch but don't completely skip
            class_penalty = 0.5
        else:
            class_penalty = 1.0

        # Calculate position distance
        new_center = ((new_bbox[0] + new_bbox[2]) / 2,
                      (new_bbox[1] + new_bbox[3]) / 2)
        lost_center = lost_info['last_position']
        distance = calculate_distance(new_center, lost_center)

        # Skip if too far away
        if distance > POSITION_THRESHOLD:
            continue

        # Calculate IoU
        iou = calculate_iou(new_bbox, lost_info['bbox'])

        # Calculate combined score (prioritize IoU over distance, apply class penalty)
        distance_score = max(0, 1 - distance / POSITION_THRESHOLD)
        combined_score = (0.7 * iou + 0.3 * distance_score) * class_penalty

        # Adaptive matching: prioritize IoU but allow distance-based matching for close objects
        adaptive_iou_threshold = IOU_THRESHOLD if distance > 50 else max(
            IOU_THRESHOLD * 0.7, 0.1)

        if combined_score > best_score and (iou > adaptive_iou_threshold or (distance < 30 and iou > 0.1)):
            best_score = combined_score
            best_match_id = lost_id

    return best_match_id


# Ensure that all coordinates are formatted uniformly as integers or rounded floats
def format_point(point):
    """
    座標点を統一されたフォーマットに変換する。

    Args:
        point: 変換する座標点（numpy配列またはリスト）

    Returns:
        list: 統一されたフォーマットの座標点
    """
    # If the point is float-based, round and convert to a consistent format
    if isinstance(point, np.ndarray):
        point_list = point.tolist()  # Convert to integer-based string with uniform format
        for i in range(len(point_list)):
            val = point_list[i]
            if isinstance(val, np.float32):
                point_list[i] = val.item()
        return point_list
    return point  # In case the point is already in the correct format


def detect_bottom_points(mask_array, bbox_coords):
    """
    セグメンテーションマスクから車両の前部左下、後部右下、中央下部の点を検出する。

    Args:
        mask_array (numpy.ndarray): セグメンテーションマスクの座標配列
        bbox_coords (tuple): バウンディングボックスの座標 (xmin, ymin, xmax, ymax)

    Returns:
        tuple: (前部左下の点, 後部右下の点, 中央下部の点)
    """
    # Unpack bounding box coordinates
    xmin, ymin, xmax, ymax = bbox_coords

    # Ensure mask_array has valid shape
    if len(mask_array.shape) < 2 or mask_array.shape[1] != 2:
        logger.warning("Invalid mask array shape, expected [x, y] points.")
        # Fallback to default points
        return [xmin, ymax], [xmax, ymax], [(xmin + xmax) / 2, ymax]

    # Focus on the lower part of the mask for bottom points
    bottom_threshold = ymin + (ymax - ymin) * 0.95
    bottom_points = mask_array[mask_array[:, 1] >= bottom_threshold]

    # If no points are found in the bottom 5%, expand the search upward
    expansion_factor = 0.1  # Expand by 10% at a time
    while len(bottom_points) == 0 and bottom_threshold >= ymax * 0.5:
        bottom_threshold -= (ymax - ymin) * expansion_factor
        bottom_points = mask_array[mask_array[:, 1] >= bottom_threshold]

    # If no points are found, default to bounding box corners
    if len(bottom_points) == 0:
        return [xmin, ymax], [xmax, ymax], [(xmin + xmax) / 2, ymax]

    # FRONT BOTTOM LEFT: Look for points on the leftmost side of the bottom region
    front_left_region = mask_array[mask_array[:, 0] <= (
        xmin + (xmax - xmin) * 0.1)]
    front_bottom_left = front_left_region[np.argmax(front_left_region[:, 1])] if len(
        front_left_region) > 0 else bottom_points[np.argmin(bottom_points[:, 0])]

    # REAR BOTTOM RIGHT: Look for points on the rightmost side of the bottom region
    rear_right_region = mask_array[mask_array[:, 0] >= (
        xmax - (xmax - xmin) * 0.1)]
    rear_bottom_right = rear_right_region[np.argmax(rear_right_region[:, 1])] if len(
        rear_right_region) > 0 else bottom_points[np.argmax(bottom_points[:, 0])]

    # MIDDLE BOTTOM: Focus on the middle of the mask
    min_x = np.min(mask_array[:, 0])
    max_x = np.max(mask_array[:, 0])
    middle_x = min_x + ((max_x - min_x) / 2)

    # Look for points near the middle
    middle_bottom_region = mask_array[np.abs(mask_array[:, 0] - middle_x) < 10]
    if len(middle_bottom_region) > 0:
        middle_bottom = middle_bottom_region[np.argmax(
            middle_bottom_region[:, 1])]
    else:
        middle_bottom = bottom_points[np.argmin(
            np.abs(bottom_points[:, 0] - middle_x))]

    return front_bottom_left, rear_bottom_right, middle_bottom


def process2D(image, track=True, device='cpu', tracking_info=None, current_time=None):
    """
    画像に対して2D物体検出とトラッキングを実行する。

    Args:
        image (numpy.ndarray): 処理する画像
        track (bool): トラッキングを有効にするかどうか（デフォルト: True）
        device (str): 使用するデバイス（'cpu'または'cuda'、デフォルト: 'cpu'）
        tracking_info (dict): トラッキング情報の辞書
        current_time (int): 現在のフレーム番号

    Returns:
        tuple: (処理済み画像, バウンディングボックスリスト, フレームデータ)
    """
    global lost_objects, next_id_map
    bboxes = []
    frame_data = []  # Collect data for the current frame

    if track:
        try:
            results = bbox2d_model.track(
                image, verbose=False, device=device, persist=True)
        except Exception as e:
            logger.error("tracking failed")
            return image, bboxes, frame_data

        # 現在のフレームで検出されたオブジェクトのIDを収集
        current_ids = set()
        for predictions in results:
            if predictions is not None and predictions.boxes is not None:
                for bbox in predictions.boxes:
                    if bbox.id is not None:
                        current_ids.add(int(bbox.id))

        # 消失したオブジェクトをlost_objectsに移動
        for id_ in list(tracking_trajectories.keys()):
            if id_ not in current_ids:
                # 現在のフレーム番号と共に失われたオブジェクトとして保存
                if id_ in tracking_info:
                    lost_objects[id_] = {
                        'last_position': tracking_info[id_]['trajectory'][-1] if tracking_info[id_]['trajectory'] else None,
                        'class': tracking_info[id_]['class'],
                        'bbox': tracking_info[id_]['bbox'],
                        'lost_frame': current_time,
                        'score': tracking_info[id_]['score']
                    }
                del tracking_trajectories[id_]

        # 古い失われたオブジェクトをクリーンアップ（MAX_LOST_FRAMESより古いものを削除）
        if current_time is not None:
            lost_objects = {k: v for k, v in lost_objects.items()
                            if current_time - v['lost_frame'] <= MAX_LOST_FRAMES}

        # フレームごとにIDマッピングと使用済みIDをリセット
        next_id_map.clear()
        used_ids_in_frame.clear()

        for predictions in results:
            if predictions is None or predictions.boxes is None or predictions.masks is None:
                continue

            for bbox, masks in zip(predictions.boxes, predictions.masks):
                # Ensure bbox attributes are not None before proceeding
                if bbox.conf is None or bbox.cls is None or bbox.xyxy is None or bbox.id is None:
                    continue  # Skip if any bounding box attributes are None

                # 画像内に完全に収まっているオブジェクトのみをチェック
                boxes_xyxy = bbox.xyxy.cpu()
                boxes_conf = bbox.conf.cpu()
                boxes_cls = bbox.cls.cpu()
                boxes_ids = bbox.id.int().cpu().tolist()

                # 画像の端にあるオブジェクトを除外
                img_height = image.shape[0]
                offset_height = int(OFFSET_THD * img_height)
                img_width = image.shape[1]
                offset_width = int(OFFSET_THD * img_width)
                del_idxes = []
                is_fully_contained_list = [True] * len(boxes_xyxy)
                for i, xyxyi in enumerate(boxes_xyxy):
                    for i in del_idxes:
                        continue
                    if xyxyi[1] < offset_height or xyxyi[3] > (img_width - offset_height):
                        del_idxes.append(i)
                        continue
                    if xyxyi[0] < offset_width or xyxyi[2] > (img_width - offset_width):
                        is_fully_contained_list[i] = False
                        continue

                # 有効なオブジェクトのみを保持
                if len(boxes_xyxy) > len(del_idxes):
                    boxes_xyxy, boxes_conf, boxes_cls, boxes_ids, is_fully_contained_list = zip(
                        *[(boxes_xyxy[i], boxes_conf[i], boxes_cls[i], boxes_ids[i], is_fully_contained_list[i]) for i in range(len(boxes_xyxy)) if i not in del_idxes])
                else:
                    continue

                for scores, classes, bbox_coords, id_, is_fully_contained in zip(boxes_conf, boxes_cls, boxes_xyxy, boxes_ids, is_fully_contained_list):
                    # Convert bbox_coords to a NumPy array if it is a tensor
                    if hasattr(bbox_coords, 'cpu'):
                        # PyTorch tensor
                        bbox_coords_np = bbox_coords.cpu().numpy()
                    else:
                        # Use asarray to avoid copy warning
                        bbox_coords_np = np.asarray(bbox_coords)

                    xmin, ymin, xmax, ymax = bbox_coords_np
                    
                    # Convert numpy.float32 to Python float
                    xmin = float(xmin)
                    ymin = float(ymin)
                    xmax = float(xmax)
                    ymax = float(ymax)

                    # この検出が失われたオブジェクトとマッチするかチェック
                    class_name = yolo_classes[int(classes)]
                    matched_id = find_best_match(
                        bbox_coords_np, class_name, lost_objects)

                    final_id = id_  # デフォルトは元のID

                    if matched_id is not None and matched_id not in used_ids_in_frame:
                        # 同じフレームで既に使用されていないことを確認
                        # 新しいIDを古いIDにマップ
                        next_id_map[id_] = matched_id
                        final_id = matched_id
                        # 失われたオブジェクトリストから削除
                        del lost_objects[matched_id]
                        # 使用済みIDとして記録
                        used_ids_in_frame.add(matched_id)
                    else:
                        # 既に使用されているか、マッチがない場合は元のIDを使用
                        if id_ not in used_ids_in_frame:
                            used_ids_in_frame.add(id_)
                        else:
                            # IDが既に使用されている場合は新しいIDを生成
                            new_id = max(
                                list(tracking_trajectories.keys()) + list(used_ids_in_frame) + [0]) + 1
                            final_id = new_id
                            used_ids_in_frame.add(new_id)
                            logger.warning(
                                "ID %s already used in frame, assigned new ID %s",
                                id_, new_id)

                    bboxes.append([bbox_coords_np, scores, classes, final_id])

                    # Convert ID and Score tensors to native Python types
                    final_id_python = int(final_id.item()) if hasattr(
                        final_id, 'item') else int(final_id)
                    score_python = float(scores.item()) if hasattr(
                        scores, 'item') else float(scores)

                    # Get extreme points from mask
                    front_bottom_left, rear_bottom_right, middle_bottom = None, None, None
                    if masks.xy is not None:
                        # Convert mask_array to NumPy
                        mask_array = np.asarray(masks.xy[0])

                        # Detect the three key points
                        front_bottom_left, rear_bottom_right, middle_bottom = detect_bottom_points(
                            mask_array, bbox_coords_np)

                    # Convert mask array to a more CSV/Excel-friendly format
                    mask_data_str = '; '.join(
                        [f"[{int(point[0])}, {int(point[1])}]" for point in mask_array])

                    # Collect data for the current frame and convert any tensor data to Python types
                    frame_data.append({
                        'ID': final_id_python,
                        'Class': yolo_classes[int(classes)],
                        'Score': score_python,
                        'BBox_Xmin': xmin,
                        'BBox_Ymin': ymin,
                        'BBox_Xmax': xmax,
                        'BBox_Ymax': ymax,
                        'Front_Bottom_Left': format_point(front_bottom_left) if front_bottom_left is not None else 'None',
                        'Rear_Bottom_Right': format_point(rear_bottom_right) if rear_bottom_right is not None else 'None',
                        'Middle_Bottom': format_point(middle_bottom) if middle_bottom is not None else 'None',
                        'Mask': mask_data_str,
                        'Fully_Contained': is_fully_contained,
                    })

                    # 車両の底面ポイントを画像に描画
                    circle_size = 5
                    if front_bottom_left is not None:
                        cv2.circle(image, (int(front_bottom_left[0]), int(
                            # 青：前部左下
                            front_bottom_left[1])), circle_size, (255, 0, 0), -1)
                    if rear_bottom_right is not None:
                        cv2.circle(image, (int(rear_bottom_right[0]), int(
                            # 緑：後部右下
                            rear_bottom_right[1])), circle_size, (0, 255, 0), -1)
                    # 中央下部の描画は無効化（必要に応じてコメントアウトを解除）
                    # if middle_bottom is not None:
                    #     cv2.circle(image, (int(middle_bottom[0]), int(middle_bottom[1])), circle_size, (0, 0, 255), -1)  # 赤：中央下部

                    # Update tracking information with trajectory
                    if final_id is not None:
                        if int(final_id) not in tracking_info:
                            tracking_info[int(final_id)] = {
                                'trajectory': deque(maxlen=5),
                                'class': predictions.names[int(classes)],
                                'score': round(float(scores) * 100, 1),
                                'bbox': [int(xmin), int(ymin), int(xmax), int(ymax)],
                                'segmentation': masks.xy if masks.xy else None
                            }
                        else:
                            # 既存のオブジェクトの情報を更新（クラスが変わる可能性があるため）
                            tracking_info[int(
                                final_id)]['class'] = predictions.names[int(classes)]
                            tracking_info[int(final_id)]['score'] = round(
                                float(scores) * 100, 1)
                            tracking_info[int(final_id)]['bbox'] = [
                                int(xmin), int(ymin), int(xmax), int(ymax)]

                        # Append the centroid to the trajectory
                        centroid_x = (xmin + xmax) / 2
                        centroid_y = (ymin + ymax) / 2
                        tracking_info[int(final_id)]['trajectory'].append(
                            (centroid_x, centroid_y))

                        # Update tracking trajectories
                        if int(final_id) not in tracking_trajectories:
                            tracking_trajectories[int(
                                final_id)] = deque(maxlen=30)
                        tracking_trajectories[int(final_id)].append(
                            (centroid_x, centroid_y))

                        cv2.putText(image, f"ID: {final_id_python}, {predictions.names[int(classes)]}", (int(
                            xmin), int(ymin) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
                        points = np.asarray([[xmin, ymin], [xmax, ymin], [
                            xmax, ymax], [xmin, ymax]],  dtype=np.int32)
                        cv2.polylines(image, [points],
                                      True, (0, 255, 0), thickness=2)

                # 軌跡を描画（線の太さは新しいポイントほど太く）
                for id_, trajectory in tracking_trajectories.items():
                    for i in range(1, len(trajectory)):
                        thickness = int(2 * (i / len(trajectory)) + 1)
                        cv2.line(image, (int(trajectory[i-1][0]), int(trajectory[i-1][1])), (int(
                            trajectory[i][0]), int(trajectory[i][1])), (255, 255, 255), thickness)

                # セグメンテーションのアウトラインを描画
                for mask in masks.xy:
                    polygon = np.int32(mask)  # ポリゴンをint32に変換して描画
                    cv2.polylines(image, [polygon], True,
                                  (255, 0, 0), thickness=2)

    else:
        # Handle non-tracking scenario (no changes here)
        results = bbox2d_model.predict(
            image, verbose=False, device=device)  # predict on an image
        # [...] Same as before for handling bounding boxes and masks when not tracking

    # 重複検出を除去
    if len(bboxes) > 0:
        # print(f"Before duplicate removal: {len(bboxes)} detections")
        bboxes = remove_duplicate_detections(bboxes, iou_threshold=0.8)
        # print(f"After duplicate removal: {len(bboxes)} detections")

        # frame_dataも更新（重複除去されたIDのみを保持）
        kept_ids = {int(bbox[3]) for bbox in bboxes}
        frame_data = [data for data in frame_data if data['ID'] in kept_ids]

    return image, bboxes, frame_data


def segmentation(input_dir, output_dir):
    """
    指定されたディレクトリ内の画像に対してセグメンテーションとトラッキングを実行する。

    Args:
        input_dir (str): 入力画像が格納されているディレクトリパス
        output_dir (str): 処理結果を出力するディレクトリパス

    Note:
        - 入力画像はJPEG形式である必要がある
        - 出力ディレクトリが存在する場合は削除して再作成される
        - 処理結果としてセグメンテーション画像、JSON形式の結果、トラッキング情報が出力される
    """
    global tracking_trajectories, lost_objects, next_id_map

    # Reset global tracking variables
    tracking_trajectories = {}
    lost_objects = {}
    next_id_map = {}

    # フォルダ内の画像のファイルリストを取得する
    files = glob.glob(os.path.join(input_dir, '*.jpg'))
    files.sort()
    frames = len(files)
    assert frames != 0, 'not found image file'    # 画像ファイルが見つからない

    # 出力フォルダ作成
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    TracK = True
    tracking_info = {}
    segmentation_results = {"results": []}

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info("Using device: %s", device)

    # 進捗表示用のプログレスバー
    bar = tqdm(total=frames, dynamic_ncols=True, desc="segmentation")
    for f in files:
        # 画像を1枚ずつ読み込む
        img = cv2.imread(f)

        name = os.path.splitext(os.path.basename(f))[0]
        current_time = int(name[-5:])  # ファイル名の末尾5文字をフレーム番号として使用

        # 2D物体検出とトラッキングを実行
        img2D, bboxes2d, frame_data = process2D(
            img, track=TracK, device=device, tracking_info=tracking_info, current_time=current_time)

        # セグメンテーション結果を保存
        output_fn = name + "_seg.jpg"
        output_path = os.path.join(output_dir, output_fn)
        cv2.imwrite(output_path, img2D)

        if len(frame_data) > 0:
            # numpy.float32型をPython floatに変換（再帰的に変換）
            def convert_numpy_types(obj):
                if isinstance(obj, np.float32):
                    return float(obj)
                elif isinstance(obj, np.int32):
                    return int(obj)
                elif isinstance(obj, np.int64):
                    return int(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(v) for v in obj]
                elif isinstance(obj, tuple):
                    return tuple(convert_numpy_types(v) for v in obj)
                return obj
            
            # frame_data全体を変換
            frame_data = convert_numpy_types(frame_data)

            # フレームデータを結果に追加
            segmentation_results["results"].append(
                {"frame": current_time, "file": output_path, "tensor_data": frame_data})

        bar.update(1)

    bar.close()

    # セグメンテーション結果をJSON形式で保存
    with open(os.path.join(output_dir, "segmentation_results.json"), "w", encoding="utf-8") as f:
        json.dump(segmentation_results, f, ensure_ascii=False, indent=2)

    # トラッキング情報をテキストファイルに保存
    text_output = str(tracking_info)
    with open(os.path.join(output_dir, "tracking_info.txt"), "w", encoding="utf-8") as f:
        f.write(text_output)


def main():
    """
    メイン関数：コマンドライン引数を解析してセグメンテーション処理を実行する。

    コマンドライン引数:
        --input_dir: 入力画像フォルダパス（必須）
        --output_dir: 出力結果フォルダパス（必須）
    """
    # 引数をパースする
    parser = argparse.ArgumentParser(description="画像の歪みを補正する")
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        default="input",
        help="入力画像フォルダパス",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        default="output",
        help="出力結果フォルダパス",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    assert isinstance(input_dir, str)

    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    segmentation(input_dir, output_dir)


if __name__ == "__main__":
    main()
