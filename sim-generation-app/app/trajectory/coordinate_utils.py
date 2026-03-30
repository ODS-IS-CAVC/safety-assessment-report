"""
座標変換ユーティリティモジュール

レーン上の座標計算、距離計算、補間などの純粋な幾何学関数を提供します。
"""

import math
from typing import List, Tuple, Optional


def closest_point_on_segment(
    position: Tuple[float, float],
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float]
) -> Tuple[float, float]:
    """
    指定された位置とセグメント上の最近点を計算します。

    Args:
        position: 指定された位置 (x, y)
        p1: セグメントの始点 (x, y, z)
        p2: セグメントの終点 (x, y, z)

    Returns:
        Tuple[float, float]: セグメント上の最近点 (cx, cy)
    """
    x, y = position
    x1, y1 = p1[0], p1[1]
    x2, y2 = p2[0], p2[1]

    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return x1, y1

    t = ((x - x1) * dx + (y - y1) * dy) / (dx**2 + dy**2)
    t = max(0, min(1, t))

    cx = x1 + t * dx
    cy = y1 + t * dy
    return cx, cy


def calculate_distance_from_start(
    lane_coords: List[Tuple[float, float, float]],
    position: Tuple[float, float]
) -> float:
    """
    レーン上の先頭から指定された位置までの距離を計算します。

    Args:
        lane_coords: レーンの座標リスト
        position: 指定された位置 (x, y)

    Returns:
        float: レーン上の先頭からの距離
    """
    distance_accum = 0.0
    closest_distance = float('inf')
    closest_segment_distance = 0.0

    for i in range(len(lane_coords) - 1):
        p1 = lane_coords[i]
        p2 = lane_coords[i + 1]

        cx, cy = closest_point_on_segment(position, p1, p2)
        segment_distance = math.sqrt((cx - p1[0])**2 + (cy - p1[1])**2)
        total_distance = distance_accum + segment_distance

        dx = position[0] - cx
        dy = position[1] - cy
        distance_to_position = math.sqrt(dx**2 + dy**2)

        if distance_to_position < closest_distance:
            closest_distance = distance_to_position
            closest_segment_distance = total_distance

        segment_length = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
        distance_accum += segment_length

    return closest_segment_distance


def is_point_on_segment(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    position: Tuple[float, float]
) -> bool:
    """
    指定された位置がセグメント上にあるかを判定します。

    Args:
        p1: セグメントの始点
        p2: セグメントの終点
        position: 判定する位置 (x, y)

    Returns:
        bool: セグメント上にある場合はTrue
    """
    cross_product = (position[1] - p1[1]) * (p2[0] - p1[0]) - \
                    (position[0] - p1[0]) * (p2[1] - p1[1])
    if abs(cross_product) > 1e-6:
        return False

    dot_product = (position[0] - p1[0]) * (p2[0] - p1[0]) + \
                  (position[1] - p1[1]) * (p2[1] - p1[1])
    if dot_product < 0:
        return False

    squared_length = (p2[0] - p1[0])**2 + (p2[1] - p1[1])**2
    if dot_product > squared_length:
        return False

    return True


def interpolate_position_on_lane(
    lane_coords: List[Tuple[float, float, float]],
    start_index: int,
    target_distance: float,
    lateral_offset: float = 0.0,
    delta_lane: int = 0
) -> Tuple[float, float, float, float]:
    """
    lane_coords上を target_distance 進んだ位置を補間する。
    lateral_offsetを指定すると、進行方向に対して垂直方向にオフセットした位置を返す。

    Args:
        lane_coords: レーンの座標リスト
        start_index: 開始インデックス
        target_distance: 目標距離
        lateral_offset: 横方向オフセット
        delta_lane: レーンチェンジの方向

    Returns:
        Tuple[float, float, float, float]: pos_x, pos_y, pos_z, yaw_deg（進行方向）
    """
    if not lane_coords:
        return 0.0, 0.0, 0.0, 0.0

    distance_accum = 0.0

    for i in range(start_index, len(lane_coords) - 1):
        p1 = lane_coords[i]
        p2 = lane_coords[i + 1]

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2] if len(p2) > 2 else 0.0 if len(p1) > 2 else 0.0
        segment_length = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance_accum + segment_length >= target_distance:
            remaining = target_distance - distance_accum
            ratio = remaining / segment_length if segment_length > 0 else 0

            x = p1[0] + ratio * dx
            y = p1[1] + ratio * dy
            z = p1[2] + ratio * dz

            yaw_rad = math.atan2(dy, dx)
            yaw_deg = math.degrees(yaw_rad)

            if lateral_offset != 0.0:
                sign = 1 if delta_lane > 0 else -1
                perpendicular_dx = -dy / segment_length
                perpendicular_dy = dx / segment_length
                x += sign * lateral_offset * perpendicular_dx
                y += sign * lateral_offset * perpendicular_dy

            return x, y, z, yaw_deg

        distance_accum += segment_length

    # 最後の点を返す
    last = lane_coords[-1]
    prev = lane_coords[-2]
    yaw_rad = math.atan2(last[1] - prev[1], last[0] - prev[0])

    if lateral_offset != 0.0:
        sign = 1 if delta_lane > 0 else -1
        segment_length = math.sqrt(
            (last[0] - prev[0])**2 + (last[1] - prev[1])**2)
        perpendicular_dx = -(last[1] - prev[1]) / segment_length
        perpendicular_dy = (last[0] - prev[0]) / segment_length
        last_x = last[0] + sign * lateral_offset * perpendicular_dx
        last_y = last[1] + sign * lateral_offset * perpendicular_dy
        last_z = last[2] if len(last) > 2 else 0.0
        return last_x, last_y, last_z, math.degrees(yaw_rad)

    last_z = last[2] if len(last) > 2 else 0.0
    return last[0], last[1], last_z, math.degrees(yaw_rad)


def find_point_at_distance(
    coords: List[Tuple[float, float, float]],
    target_distance: float
) -> Tuple[float, float, float]:
    """
    指定された距離の位置の座標を見つけます。

    Args:
        coords: 座標リスト
        target_distance: 目標距離

    Returns:
        Tuple[float, float, float]: 指定された距離の位置
    """
    distance_accum = 0.0
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2] if len(p2) > 2 else 0.0
        segment_length = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance_accum + segment_length >= target_distance:
            remaining = target_distance - distance_accum
            ratio = remaining / segment_length

            x = p1[0] + ratio * dx
            y = p1[1] + ratio * dy
            z = p1[2] + ratio * dz
            return (x, y, z)

        distance_accum += segment_length

    return coords[-1]


def calculate_lane_distance(
    current_coords: List[Tuple[float, float, float]],
    target_coords: List[Tuple[float, float, float]],
    current_distance: float
) -> float:
    """
    現在のレーンと目標レーンの間の距離を計算します。

    Args:
        current_coords: 現在のレーン座標
        target_coords: 目標レーン座標
        current_distance: 現在の進行距離

    Returns:
        float: レーン間の距離（メートル）
    """
    current_point = find_point_at_distance(current_coords, current_distance)
    target_point = find_point_at_distance(target_coords, current_distance)

    dx = target_point[0] - current_point[0]
    dy = target_point[1] - current_point[1]
    return math.sqrt(dx*dx + dy*dy)
