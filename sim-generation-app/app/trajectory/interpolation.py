"""
データ補間ユーティリティモジュール

外れ値除去、スプライン補間、外挿などのデータ処理関数を提供します。
"""

import numpy as np
import scipy.interpolate
from typing import List, Tuple, Optional


def remove_outliers_with_frames(
    frames: List[int],
    data: List[Tuple[float, float]],
    threshold: float = 5.0
) -> Tuple[List[int], List[Tuple[float, float]]]:
    """
    ハズレ値を除去する（フレーム番号との同期を保つ）

    Args:
        frames: フレーム番号のリスト
        data: (x, y) のリスト
        threshold: 外れ値を除去するための閾値（標準偏差の倍数）

    Returns:
        Tuple[List[int], List[Tuple[float, float]]]: 外れ値を除去したフレーム番号とデータ
    """
    if len(data) == 0:
        return [], []

    x_values = [d[0] for d in data]
    y_values = [d[1] for d in data]
    x_mean, x_std = np.mean(x_values), np.std(x_values)
    y_mean, y_std = np.mean(y_values), np.std(y_values)

    # 標準偏差が0の場合の処理
    if x_std == 0:
        x_std = 1.0
    if y_std == 0:
        y_std = 1.0

    # 外れ値でないインデックスを特定
    valid_indices = [
        i for i, (x, y) in enumerate(data)
        if abs(x - x_mean) <= threshold * x_std and
           abs(y - y_mean) <= threshold * y_std
    ]

    return (
        [frames[i] for i in valid_indices],
        [data[i] for i in valid_indices]
    )


def interpolate_positions(
    frames: List[int],
    distances: List[Tuple[float, float]],
    smoothing_factor: float = 0.5
) -> Optional[Tuple[np.ndarray, List[Tuple[float, float]]]]:
    """
    スプライン補間または線形補間を行い、1fpsごとの軌跡を生成する

    Args:
        frames: フレーム番号のリスト
        distances: 各フレームでの位置 (x, y) のリスト
        smoothing_factor: スプライン補間の平滑化係数

    Returns:
        Optional[Tuple[np.ndarray, List[Tuple[float, float]]]]:
            補間されたフレームと位置、データが不足している場合はNone
    """
    if len(frames) < 2:
        return None

    interpolated_frames = np.arange(frames[0], frames[-1] + 1, 1)

    if len(frames) <= 4:
        # 線形補間を使用
        x_values = [d[0] for d in distances]
        y_values = [d[1] for d in distances]
        interpolated_x = np.interp(interpolated_frames, frames, x_values)
        interpolated_y = np.interp(interpolated_frames, frames, y_values)
    else:
        # スプライン補間を使用
        x_values = [d[0] for d in distances]
        y_values = [d[1] for d in distances]
        spline_x = scipy.interpolate.UnivariateSpline(
            frames, x_values, s=smoothing_factor)
        spline_y = scipy.interpolate.UnivariateSpline(
            frames, y_values, s=smoothing_factor)
        interpolated_x = spline_x(interpolated_frames)
        interpolated_y = spline_y(interpolated_frames)

    return interpolated_frames, list(zip(interpolated_x, interpolated_y))


def interpolate_lane_id(lane_from: int, lane_to: int, ratio: float) -> int:
    """
    レーンIDを補間する

    Args:
        lane_from: 元のレーンID
        lane_to: 目標レーンID
        ratio: 補間比率 (0.0-1.0)

    Returns:
        int: 補間されたレーンID
    """
    return int(round((1 - ratio) * lane_from + ratio * lane_to))
