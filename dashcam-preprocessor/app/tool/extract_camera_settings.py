#!/usr/bin/env python3
"""
camera_view_angles.jsonからカメラごとの設定を抽出して、
従来のpos_est_setting形式のJSONファイルを生成する
"""
import argparse
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)


def extract_camera_setting(camera_view_angles_file, camera_direction, output_file, nearmiss_info_file=None):
    """
    camera_view_angles.jsonから指定したカメラ方向の設定を抽出

    Args:
        camera_view_angles_file: camera_view_angles.jsonのパス
        camera_direction: カメラ方向 ("front", "rear", "left", "right")
        output_file: 出力JSONファイルのパス
        nearmiss_info_file: NearMiss_Info.jsonのパス (オプション、max_distance等を取得)
    """

    # camera_view_angles.jsonを読み込む
    if not os.path.exists(camera_view_angles_file):
        logger.error("%s not found", camera_view_angles_file)
        sys.exit(1)

    with open(camera_view_angles_file, 'r', encoding='utf-8') as f:
        camera_data = json.load(f)

    # カメラ方向の設定を取得
    if 'cameras' not in camera_data:
        logger.error("'cameras' key not found in %s", camera_view_angles_file)
        sys.exit(1)

    if camera_direction not in camera_data['cameras']:
        logger.error("Camera direction '%s' not found in %s", camera_direction, camera_view_angles_file)
        logger.error("Available cameras: %s", list(camera_data['cameras'].keys()))
        sys.exit(1)

    camera_settings = camera_data['cameras'][camera_direction]

    # 出力用の設定を構築
    output_settings = {
        "theta": camera_settings.get("theta", 120),
        "camera_elevation_angle": camera_settings.get("elevation_angle", 0),
        "camera_height": camera_settings.get("camera_height", 2.5),
        "proj_mode": 0,  # デフォルト: 中心射影
        "max_distance": 100,  # デフォルト値
        "max_dissappear_frame_num": 20  # デフォルト値
    }

    # horizontal_angleがあれば追加
    if "horizontal_angle" in camera_settings:
        output_settings["camera_horizontal_angle"] = camera_settings["horizontal_angle"]

    # NearMiss_Info.jsonからmax_distance等を上書き（オプション）
    if nearmiss_info_file and os.path.exists(nearmiss_info_file):
        with open(nearmiss_info_file, 'r', encoding='utf-8') as f:
            nearmiss_data = json.load(f)

        if "max_distance" in nearmiss_data:
            output_settings["max_distance"] = nearmiss_data["max_distance"]
        if "max_dissappear_frame_num" in nearmiss_data:
            output_settings["max_dissappear_frame_num"] = nearmiss_data["max_dissappear_frame_num"]
        if "proj_mode" in nearmiss_data:
            output_settings["proj_mode"] = nearmiss_data["proj_mode"]

    # 出力ファイルに書き込む
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_settings, f, ensure_ascii=False, indent=2)

    logger.info("Extracted %s camera settings to: %s", camera_direction, output_file)
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="camera_view_angles.jsonからカメラごとの設定を抽出"
    )
    parser.add_argument(
        "--camera_view_angles_file",
        type=str,
        required=True,
        help="camera_view_angles.jsonのパス"
    )
    parser.add_argument(
        "--camera_direction",
        type=str,
        required=True,
        choices=["front", "rear", "left", "right"],
        help="カメラ方向 (front, rear, left, right)"
    )
    parser.add_argument(
        "--output_file",
        type=str,
        required=True,
        help="出力JSONファイルのパス"
    )
    parser.add_argument(
        "--nearmiss_info_file",
        type=str,
        default=None,
        help="NearMiss_Info.jsonのパス (オプション)"
    )

    args = parser.parse_args()

    extract_camera_setting(
        args.camera_view_angles_file,
        args.camera_direction,
        args.output_file,
        args.nearmiss_info_file
    )


if __name__ == "__main__":
    main()
