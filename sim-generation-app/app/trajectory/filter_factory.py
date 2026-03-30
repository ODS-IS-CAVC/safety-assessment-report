"""
フィルタチェーン生成ファクトリ

コマンドライン引数やJSON設定ファイルから
フィルタチェーンを構築するためのファクトリ関数群。
"""

import json
import os
from typing import Dict, List, Optional

from filters import (
    FilterChain, OutlierFilter, MedianFilter,
    MovingAverageFilter, Filter
)


def create_relative_filter_chain(args) -> FilterChain:
    """
    相対座標用のフィルタチェーンを作成する

    フィルタの適用順序（相対座標での処理）：
    1. OutlierFilter（ハズレ値除去）
    2. MovingAverageFilter（平均化で平滑化）
    3. MedianFilter（スムージング処理）

    Args:
        args: argparseのNamespace

    Returns:
        FilterChain: フィルタチェーン
    """
    filters = []

    # 1. 外れ値除去フィルタ
    if args.outlier_filter:
        filters.append(OutlierFilter(threshold=args.outlier_threshold))

    # 2. 移動平均フィルタ（平均化で平滑化）
    if args.moving_average_filter:
        filters.append(MovingAverageFilter(
            window_size=args.moving_average_window
        ))

    # 3. 中央値フィルタ（スムージング処理）
    if args.median_filter:
        filters.append(MedianFilter(window_size=args.median_window))

    return FilterChain(filters)


def get_axis_params(args, axis: str) -> tuple:
    """
    指定された軸のフィルタパラメータを取得する

    軸固有のパラメータが設定されていない場合は共通パラメータを使用。

    Args:
        args: argparseのNamespace
        axis: 'x' または 'y'

    Returns:
        (outlier_threshold, ma_window, median_window)
    """
    if axis == 'x':
        outlier_threshold = (
            args.outlier_threshold_x
            if args.outlier_threshold_x is not None
            else args.outlier_threshold
        )
        ma_window = (
            args.moving_average_window_x
            if args.moving_average_window_x is not None
            else args.moving_average_window
        )
        median_window = (
            args.median_window_x
            if args.median_window_x is not None
            else args.median_window
        )
    else:  # axis == 'y'
        outlier_threshold = (
            args.outlier_threshold_y
            if args.outlier_threshold_y is not None
            else args.outlier_threshold
        )
        ma_window = (
            args.moving_average_window_y
            if args.moving_average_window_y is not None
            else args.moving_average_window
        )
        median_window = (
            args.median_window_y
            if args.median_window_y is not None
            else args.median_window
        )

    return outlier_threshold, ma_window, median_window


def create_relative_filter_chain_for_axis(
    args, axis: str
) -> List[Filter]:
    """
    指定された軸用の相対座標フィルタチェーンを作成する

    Args:
        args: argparseのNamespace
        axis: 'x' または 'y'

    Returns:
        list: フィルタのリスト
    """
    outlier_threshold, ma_window, median_window = get_axis_params(args, axis)

    filters = []

    # 1. 外れ値除去フィルタ
    if args.outlier_filter:
        filters.append(OutlierFilter(threshold=outlier_threshold))

    # 2. 移動平均フィルタ（平均化で平滑化）
    if args.moving_average_filter:
        filters.append(MovingAverageFilter(window_size=ma_window))

    # 3. 中央値フィルタ（スムージング処理）
    if args.median_filter:
        filters.append(MedianFilter(window_size=median_window))

    return filters


def load_filter_config(config_path: Optional[str] = None) -> Optional[Dict]:
    """
    フィルタ設定をJSONファイルから読み込む

    Args:
        config_path: 設定ファイルのパス（Noneの場合はデフォルト設定）

    Returns:
        設定辞書（設定が見つからない場合はNone）
    """
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)

    # デフォルト設定
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(script_dir, 'filter_params.json')

    if os.path.exists(default_config):
        with open(default_config, 'r') as f:
            return json.load(f)

    return None


def create_filters_from_stages(
    iteration_stages: List[Dict], args
) -> List[Filter]:
    """
    iteration_stagesの設定から段階的にフィルタを生成する

    Args:
        iteration_stages: JSONから読み込んだiteration_stagesの設定
        args: コマンドライン引数

    Returns:
        フィルタのリスト
    """
    filters = []

    for stage in iteration_stages:
        repeat = stage.get('repeat', 1)
        ma_window = stage.get('moving_average_window', 3)
        median_window = stage.get('median_window', 3)
        outlier_threshold = stage.get('outlier_threshold', 5.0)

        for _ in range(repeat):
            # 各ステージの設定で指定された回数だけフィルタを追加
            if args.outlier_filter:
                filters.append(OutlierFilter(threshold=outlier_threshold))
            if args.moving_average_filter:
                filters.append(MovingAverageFilter(window_size=ma_window))
            if args.median_filter:
                filters.append(MedianFilter(window_size=median_window))

    return filters
