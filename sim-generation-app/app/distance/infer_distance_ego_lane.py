import os
import sys
import argparse
import json
import math
import numpy as np
from tqdm import tqdm

from commons import image_util
ROUNDED_DIGIT_NUM = 6
# from infer_distance_to_car import ROUNDED_DIGIT_NUM, \
#       calc_relative_coord_ctr_proj, calc_relative_coord_equidistant_proj
                               
def calc_dist_ctr_proj(
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
    #if not os.path.exists(img_path):
    #    print(f"File [{img_path}] is not found.")
    #    return

    # 画像の解像度を(w, h)とする。
    #img = image_util.read_image(img_path)
    #h, w, _ = img.shape
    h, w = 1080, 1920

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
    #c_x, c_y = image_util.get_center_coordinates(img_path)
    
    c_x, c_y = 1920/2, 1080/2
    
    

    if return_extra:
        test = calc_dist_ctr_proj(
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
        print(f"File [{img_path}] is not found.")
        return

    # 画像の解像度を(w, h)とする。
    #img = image_util.read_image(img_path)
    #h, w, _ = img.shape
    h, w = 1080, 1920

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


def calculate_point(
    output_dir,
    json_file_name,
    df_frame,
    lane_detection_data,
    theta,
    camera_height,
    camera_elevation_angle,
    proj_mode
):

    phi_deg = 0.0
    h, w = 1080, 1920

    data_results = []
    # tqdmで進捗表示を追加
    print("\n=== 距離推定処理を開始 ===")

    frame_whiteline_map = {}

    for data in lane_detection_data['results']:
        frame = data['frame']
        whiteline_datas = data['lane_data']
        frame_whiteline_map[frame] = whiteline_datas

    frames = df_frame['frame']

    bar = tqdm(total=len(frames), dynamic_ncols=True, desc="infer ego lane distance")
    for frame in frames:

        if frame in frame_whiteline_map:
            whiteline_datas = frame_whiteline_map[frame]

            ego_whiteline_result = []
            for whiteline_data in whiteline_datas:
                id = whiteline_data["ID"]
                p1_x = whiteline_data["AccuracyLimitPoint_X"]
                p1_y = whiteline_data["AccuracyLimitPoint_Y"]
                p2_x = whiteline_data["ImageBottomPoint_X"]
                p2_y = whiteline_data["ImageBottomPoint_Y"]

                if proj_mode == 0:
                    whiteline_results_1 = calc_relative_coord_ctr_proj(
                        theta, p1_y, p1_x, camera_elevation_angle, camera_height, True
                    )
                    whiteline_results_2 = calc_relative_coord_ctr_proj(
                        theta, p2_y, p2_x, camera_elevation_angle, camera_height, True
                    )
                elif proj_mode == 1:
                    whiteline_results_1 = calc_relative_coord_equidistant_proj(
                        theta, p1_y, p1_x, camera_elevation_angle, camera_height, True
                    )
                    whiteline_results_2 = calc_relative_coord_equidistant_proj(
                        theta, p2_y, p2_x, camera_elevation_angle, camera_height, True
                    )

                whiteline_relative_coordinates_1 = whiteline_results_1[0]
                whiteline_p1_dx = round(whiteline_relative_coordinates_1[0], ROUNDED_DIGIT_NUM)
                whiteline_p1_dy = round(whiteline_relative_coordinates_1[1], ROUNDED_DIGIT_NUM)

                whiteline_relative_coordinates_2 = whiteline_results_2[0]
                whiteline_p2_dx = round(whiteline_relative_coordinates_2[0], ROUNDED_DIGIT_NUM)
                whiteline_p2_dy = round(whiteline_relative_coordinates_2[1], ROUNDED_DIGIT_NUM)

                w, h = whiteline_results_1[1], whiteline_results_1[2]
                phi_deg = round(math.degrees(whiteline_results_1[3]), ROUNDED_DIGIT_NUM)

                obj_distance_from_whiteline = {
                    "whiteline_id": id,
                    "accuracy_limit_point_dx": whiteline_p1_dx,
                    "accuracy_limit_point_dy": whiteline_p1_dy,
                    "image_bottom_point_dx": whiteline_p2_dx,
                    "image_bottom_point_dy": whiteline_p2_dy
                }
                ego_whiteline_result.append(obj_distance_from_whiteline)

            data_result = {
                "frame": frame,
                "whiteline_distance": ego_whiteline_result
            }
            data_results.append(data_result)

        bar.update(1)

    bar.close()

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
    #json_file_name = os.path.join(
    #    output_dir, "ego_lane_detection_result.json")
    print(f"\n結果をJSONファイルに保存中: {json_file_name}")
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
