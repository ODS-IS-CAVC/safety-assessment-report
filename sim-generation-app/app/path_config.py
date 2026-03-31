"""パス定義モジュール

BASE_DIR を起点に intermediate/ と output/ のパスを一元管理する。
"""

import os


def build_paths(base_dir):
    """全ディレクトリパスを構築して辞書で返す。

    Args:
        base_dir: データディレクトリのルートパス (例: /mnt/data)

    Returns:
        dict: パス名をキー、絶対パスを値とする辞書
    """
    inter = os.path.join(base_dir, 'intermediate')
    out = os.path.join(base_dir, 'output')

    return {
        # === 入力 ===
        'input': os.path.join(base_dir, 'input'),

        # === 中間生成物 ===
        'intermediate': inter,

        # 画像処理系
        'image_src': os.path.join(inter, 'image', 'src'),
        'image_src_front': os.path.join(inter, 'image', 'src', 'front'),
        'image_src_rear': os.path.join(inter, 'image', 'src', 'rear'),

        'image_distortion': os.path.join(inter, 'image', 'distortion'),
        'image_distortion_front': os.path.join(inter, 'image', 'distortion', 'front'),
        'image_distortion_rear': os.path.join(inter, 'image', 'distortion', 'rear'),

        'image_segmentation': os.path.join(inter, 'image', 'segmentation'),
        'image_segmentation_front': os.path.join(inter, 'image', 'segmentation', 'front'),
        'image_segmentation_rear': os.path.join(inter, 'image', 'segmentation', 'rear'),

        'image_lane': os.path.join(inter, 'image', 'lane'),
        'image_lane_front': os.path.join(inter, 'image', 'lane', 'front'),
        'image_lane_rear': os.path.join(inter, 'image', 'lane', 'rear'),

        'image_frame': os.path.join(inter, 'image', 'frame'),
        'image_frame_front': os.path.join(inter, 'image', 'frame', 'front'),
        'image_frame_rear': os.path.join(inter, 'image', 'frame', 'rear'),

        # グラフ・マップ可視化
        'plot': os.path.join(inter, 'plot'),

        # 一時ファイル
        'tmp': os.path.join(inter, 'tmp'),
        'tmp_graph': os.path.join(inter, 'tmp', 'graph'),

        # 中間データ（SCT計算の入力）
        'intermediate_distance': os.path.join(inter, 'distance'),
        'intermediate_lane_distance': os.path.join(inter, 'lane_distance'),

        # === 最終成果物 ===
        'output': out,

        # 軌跡・SCT/TTC
        'output_trajectory': os.path.join(out, 'trajectory'),

        # シナリオ生成
        'output_scenario': os.path.join(out, 'scenario'),

        # 動画
        'output_video': os.path.join(out, 'video'),
    }


def ensure_dirs(paths, keys):
    """指定されたキーのディレクトリを作成する。

    Args:
        paths: build_paths() の戻り値
        keys: 作成するディレクトリのキーリスト
    """
    for key in keys:
        os.makedirs(paths[key], exist_ok=True)
