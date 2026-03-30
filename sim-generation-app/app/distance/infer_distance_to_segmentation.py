import os
import sys
import argparse
import json
import logging
import math
from tqdm import tqdm

logger = logging.getLogger(__name__)

from commons import image_util
ROUNDED_DIGIT_NUM = 6
# from infer_distance_to_car import ROUNDED_DIGIT_NUM, \
#       calc_relative_coord_ctr_proj, calc_relative_coord_equidistant_proj
                               
def calc_dist_ctr_proj(
    img_path,
    theta,
    y,
    camera_elevation_angle,
    camera_height,
    return_extra=False,
):
    """画像から検出した車両情報から車両までの距離を推定する機能です。(中心射影)

    Args:
        img_path (str): 入力画像のパス
        theta (float): 水平視野角θの値(degrees)
        y (float): 車を検出したときの下側の高さ方向のピクセル
        camera_elevation_angle (float): カメラの仰角(degrees)
        camera_height (float): カメラの高さ
        return_extra (float): 計算した距離の他は返すかどうか

    Returns:
        float: 車までの距離
    """
    if not os.path.exists(img_path):
        logger.warning("File [%s] is not found.", img_path)
        return

    # 画像の解像度を(w, h)とする。
    img = image_util.read_image(img_path)
    h, w, _ = img.shape

    # 垂直視野角Φ(phi)を計算する
    theta_rad = math.radians(theta)
    tan_phi_half = (h / w) * math.tan(theta_rad / 2)
    phi = 2 * math.atan(tan_phi_half)

    # 車を検出したときの下向きの視点の角度をψ(psi_y)と呼びます。
    cy = h / 2
    if y == cy and camera_elevation_angle == 0:
        return

    y = y - cy
    tan_psi_y = (y / cy) * math.tan(phi / 2)
    psi_y = math.atan(tan_psi_y)

    # 車までの奥行き方向の距離
    camera_elevation_angle_rad = math.radians(camera_elevation_angle)
    if camera_elevation_angle_rad == psi_y:
        # 0除算回避
        return None
    angle_to_horizon = psi_y - camera_elevation_angle_rad
    # 角度が0以下（水平線またはそれより上）の場合、物理的に無効なためNoneを返す
    # if angle_to_horizon < 0:
    #     return None
    dy = camera_height / math.tan(angle_to_horizon)

    if not return_extra:
        return dy
    return dy, w, h, phi, psi_y


# 対象の相対座標の計算(中心射影方式)
def calc_relative_coord_ctr_proj(
    img_path,
    theta,
    y,
    x,
    camera_elevation_angle,
    camera_height,
    return_extra=False,
):
    """対象の相対座標の計算(中心射影方式)

    Args:
        img_path (str): 入力画像のパス
        theta (float): 水平視野角θの値(degrees)
        y (float): 車を検出したときの下側の高さ方向のピクセル
        x (float): 検出車矩形の中央下部の座標
        camera_elevation_angle (float): カメラの仰角(degrees)
        camera_height (float): カメラの高さ
        return_extra (float): 計算した相対座標の他は返すかどうか

    Returns:
        Tuple[float, float, float]: 対象の相対座標
    """

    # 画像の中心座標
    c_x, c_y = image_util.get_center_coordinates(img_path)

    if return_extra:
        test = calc_dist_ctr_proj(
            img_path,
            theta,
            y,
            camera_elevation_angle,
            camera_height,
            return_extra=return_extra,
        )
        if test is None:
            return None
        dy, w, h, phi, psi_y = test
    else:
        dy = calc_dist_ctr_proj(
            img_path,
            theta,
            y,
            camera_elevation_angle,
            camera_height,
            return_extra=return_extra,
        )

    # x方向の距離
    x = x - c_x
    theta_rad = math.radians(theta)
    tan_psi_x = (x / c_x) * math.tan(theta_rad / 2)
    psi_x = math.atan(tan_psi_x)
    dx = dy * tan_psi_x

    # 対象車の空間座標
    # (dx, dy, -1.6)となる(単位m)
    relative_coordinates = (dx, dy, -camera_height)

    # 車までの直線距離
    d = math.sqrt(dx * dx + dy * dy)

    if not return_extra:
        return relative_coordinates

    return (relative_coordinates, w, h, phi, psi_y, psi_x, d)


# 対象の相対座標の計算(等距離射影方式)
def calc_relative_coord_equidistant_proj(
    img_path,
    theta,
    y,
    x,
    camera_elevation_angle,
    camera_height,
    return_extra=False,
):
    """対象の相対座標の計算(等距離射影方式)

    Args:
        img_path (str): 入力画像のパス
        theta (float): 水平視野角θの値(degrees)
        y (float): 車を検出したときの下側の高さ方向のピクセル
        x (float): 検出車矩形の中央下部の座標
        camera_elevation_angle (float): カメラの仰角(degrees)
        camera_height (float): カメラの高さ
        return_extra (float): 計算した相対座標の他は返すかどうか

    Returns:
        Tuple[float, float, float]: 対象の相対座標
    """
    if not os.path.exists(img_path):
        logger.warning("File [%s] is not found.", img_path)
        return

    # 画像の解像度を(w, h)とする。
    img = image_util.read_image(img_path)
    h, w, _ = img.shape

    # 画像中心の座標
    cx, cy = w / 2, h / 2

    theta_rad = math.radians(theta)

    # 垂直方向の視野角Φ
    phi = theta_rad * (h / w)

    # 対象点と画像中心の距離
    dist_to_center = math.sqrt((x - cx)**2 + (y - cy)**2)

    # 対象点への対角方向角
    psi_xy = dist_to_center / w * theta_rad

    # 奥行きピクセル距離
    ptemp = dist_to_center * (1 / math.tan(psi_xy))

    # 対象点への水平方向角
    psi_x = math.atan((x - cx) / ptemp)

    # 対象点への垂直方向角
    psi_y = math.atan((y - cy) / ptemp)

    camera_elevation_angle_rad = math.radians(camera_elevation_angle)
    dy = camera_height / math.tan(psi_y - camera_elevation_angle_rad)
    dx = dy * math.tan(psi_x)

    # 車までの直線距離
    d = math.sqrt(dx**2 + dy**2)

    # 対象車の空間座標
    relative_coordinates = (dx, dy, -camera_height)

    if not return_extra:
        return relative_coordinates

    return (relative_coordinates, w, h, phi, psi_y, psi_x, d)


def calculate_segmentation_point(
    output_dir,
    segment_data,
    theta,
    camera_height,
    camera_elevation_angle,
    proj_mode
):
    data_results = []
    # tqdmで進捗表示を追加
    logger.info("=== 距離推定処理を開始 ===")

    for ii, seg_res in enumerate(tqdm(segment_data["results"], desc="距離推定処理", unit="frame")):
        frame = seg_res["frame"]
        image_path = seg_res["file"]
        tensor_data = seg_res["tensor_data"]

        objects_result = []
        for tensor in tensor_data:
            id = tensor["ID"]
            vechile_type = tensor["Class"]
            seg_str_lists = [
                "BBox_center",
                "Front_Bottom_Left",
                "Rear_Bottom_Right"
            ]
            tensor["BBox_center"] = [
                (tensor["BBox_Xmax"] + tensor["BBox_Xmin"]) / 2,
                tensor["BBox_Ymax"]
            ]

            relative_dxs = []
            relative_coordinates_list = []
            segmentations = []
            for seg_str in seg_str_lists:
                x, y = tensor[seg_str]
                if proj_mode == 0:
                    results = calc_relative_coord_ctr_proj(
                        image_path, theta, y, x, camera_elevation_angle, camera_height, True
                    )
                elif proj_mode == 1:
                    results = calc_relative_coord_equidistant_proj(
                        image_path, theta, y, x, camera_elevation_angle, camera_height, True
                    )
                if results is None:
                    continue
                relative_coordinates = results[0]
                w, h = results[1], results[2]
                phi_deg = round(math.degrees(results[3]), ROUNDED_DIGIT_NUM)
                psi_y_deg = round(math.degrees(results[4]), ROUNDED_DIGIT_NUM)
                psi_x_deg = round(math.degrees(results[5]), ROUNDED_DIGIT_NUM)
                dx = round(relative_coordinates[0], ROUNDED_DIGIT_NUM)
                dy = round(relative_coordinates[1], ROUNDED_DIGIT_NUM)
                d = round(results[6], ROUNDED_DIGIT_NUM)
                relative_dxs.append(dx)
                relative_coordinates_list.append(relative_coordinates)
                # [カメラの中心から検出車下部までの幅に対応する角度 (β)]と
                # [カメラの仰角(γ)]との間の差(β-γ)を求めて

            # if (diff_angle < 0) or (abs(diff_angle) < CAMERA_ELEVATION_ANGLE_DIFF_THD):
            #     print(f"Warning: Object {obj_id} is higher than camera.")
                # continue

                calculate_result_elem = {
                    "calculate_position": seg_str,
                    "detection_point": [int(x), int(y)],
                    "distance": [dx, dy, d],
                    "angle": [psi_x_deg, psi_y_deg]
                }
                segmentations.append(calculate_result_elem)
            obj_seg_elem = {
                "obj_id": id,
                "vehicle_type": vechile_type,
                "fully_contained": tensor.get("Fully_Contained"),
                "calculate": segmentations
            }
            objects_result.append(obj_seg_elem)
        data_result = {
            "frame": frame,
            "file": image_path,
            "self": {},
            "segmentations": objects_result
        }
        data_results.append(data_result)

    data = {
        "camera_parameter": {
            "aov_horizontal": theta,
            "aov_vertical": phi_deg,
            "image_size": [w, h],
            "camera_height": camera_height,
            "camera_elevation_angle": camera_elevation_angle,
            "proj_mode": proj_mode
        },
        "results": data_results,
    }

    # write to json file
    json_file_name = os.path.join(
        output_dir, "segmentation_detection_result.json")
    logger.info("結果をJSONファイルに保存中: %s", json_file_name)
    with open(json_file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
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
    parser.add_argument(
        "--segmentation_result_json",
        type=str,
        required=True,
        default="input",
        help="入力画像フォルダパス",
    )
    parser.add_argument(
        "--pos_est_setting_file",
        type=str,
        required=True,
        default="input",
        help="入力画像フォルダパス",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    assert isinstance(input_dir, str)

    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    segmentation_result_json = args.segmentation_result_json
    assert isinstance(segmentation_result_json, str)

    pos_est_setting_file = args.pos_est_setting_file
    assert isinstance(pos_est_setting_file, str)

    # read segmentation result file
    seg_data = None
    with open(segmentation_result_json, mode='r', encoding='utf-8') as f:
        seg_data = json.load(f)

    # read setting file
    position_estimation_settings = None
    with open(pos_est_setting_file, "r", encoding="utf-8") as f:
        position_estimation_settings = json.load(f)

    os.makedirs(output_dir, exist_ok=True)

    calculate_segmentation_point(
        output_dir,
        seg_data,
        position_estimation_settings["theta"],
        position_estimation_settings["camera_height"],
        position_estimation_settings["camera_elevation_angle"],
        position_estimation_settings["proj_mode"]
    )


if __name__ == "__main__":
    main()
