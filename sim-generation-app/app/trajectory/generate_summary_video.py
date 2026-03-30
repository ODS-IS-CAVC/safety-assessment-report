
import argparse
import logging
import os
import json
import numpy as np
import cv2

logger = logging.getLogger(__name__)


def imread(filename, flags=cv2.IMREAD_COLOR, dtype=np.uint8):
    # 日本語パスに対応したimread
    try:
        n = np.fromfile(filename, dtype)
        img = cv2.imdecode(n, flags)
        return img
    except Exception as e:
        logger.error("Failed to read image: %s", e)
        return None


def save_as_mp4(summary_data, infer_dir, distortion_dir, normal_dir, output_path, fps=15):
    """
    サマリー動画を作成する（左: セグメンテーション、右: 軌跡プロット）
    Args:
        summary_data (list): 自車両の軌跡データ
        infer_dir (str): infer カメラ画像のディレクトリ
        distortion_dir (str): 画像補正のディレクトリ
        normal_dir (str): 通常視画像のディレクトリ
        output_path (str): 出力動画ファイルパス
        fps (int): フレームレート
    """
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    # レイアウト: 左(セグメンテーション) + 右(プロット) を横並び
    img_width = 640
    img_height = 360
    width = img_width * 2
    height = img_height

    fmt = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
    writer = cv2.VideoWriter(output_path, fmt, fps, (width, height))
    font = cv2.FONT_HERSHEY_SIMPLEX
    blank = np.ones((img_height, img_width, 3), np.uint8) * 255

    front_dir = os.path.join(infer_dir, "front")
    front_distortion_dir = os.path.join(distortion_dir, "")

    for i in range(0, len(summary_data)):
        if i % 2 == 1:
            continue
        str_frm = str(i).zfill(5)

        # 左側: セグメンテーション画像（前方カメラ）
        front_file = os.path.join(
            front_dir, 'front_trim_' + str_frm + '_seg.jpg')
        if os.path.isfile(front_file) and os.path.exists(front_file):
            seg_img = imread(front_file)
            seg_img = cv2.resize(seg_img, (img_width, img_height))
        else:
            # distortion の画像にフォールバック
            front_file = os.path.join(
                front_distortion_dir, 'front_trim_' + str_frm + '.jpg')
            if os.path.isfile(front_file) and os.path.exists(front_file):
                seg_img = imread(front_file)
                seg_img = cv2.resize(seg_img, (img_width, img_height))
            else:
                seg_img = blank.copy()

        # 右側: 軌跡プロット画像
        plot_file = os.path.join(normal_dir, str(i) + '.png')
        if os.path.isfile(plot_file) and os.path.exists(plot_file):
            plot_img = imread(plot_file)
            plot_img = cv2.resize(plot_img, (img_width, img_height))
        else:
            plot_img = blank.copy()

        # 横に結合
        img = cv2.hconcat([seg_img, plot_img])

        # フレーム番号を表示
        font_size = 0.5
        cv2.putText(img, str(i), (5, 20), font,
                    font_size, (255, 255, 255), 1, cv2.LINE_AA)

        writer.write(img)

    writer.release()


def main():
    parser = argparse.ArgumentParser(
        description="Generate summary video from trajectory data")
    parser.add_argument('--summary_json', required=True,
                        help='Path to ego vehicle trajectory summary json file')
    parser.add_argument('--infer_dir', required=True,
                        help='path to infer camera images')
    parser.add_argument('--distortion_dir', required=True,
                        help='path to distortion camera images')
    parser.add_argument('--normal_dir', required=True,
                        help='path to normal view images')
    parser.add_argument('--output_path', required=True,
                        help='Output video file path')
    args = parser.parse_args()

    # 自車両の軌跡データを読み込む
    summary_json_path = args.summary_json
    if not os.path.exists(summary_json_path):
        logger.error("Trajectory summary file not found: %s", summary_json_path)
        return

    with open(summary_json_path, 'r') as f:
        summary_data = json.load(f)

    save_as_mp4(
        summary_data,
        args.infer_dir,
        args.distortion_dir,
        args.normal_dir,
        args.output_path,
    )


if __name__ == "__main__":
    main()
