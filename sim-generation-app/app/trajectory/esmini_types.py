"""
esmini RoadManager 用 ctypes 構造体定義

esminiライブラリのC構造体をPython ctypesで定義。
try_tools/shared/esmini_types.py から必要な型のみ抽出。
"""
import ctypes


class RM_PositionXYZ(ctypes.Structure):
    """3D位置座標"""
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
    ]


class RM_PositionData(ctypes.Structure):
    """RoadManager用の位置データ"""
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
        ("h", ctypes.c_float),
        ("p", ctypes.c_float),
        ("r", ctypes.c_float),
        ("hRelative", ctypes.c_float),
        ("roadId", ctypes.c_uint32),
        ("junctionId", ctypes.c_uint32),
        ("laneId", ctypes.c_int),
        ("laneOffset", ctypes.c_float),
        ("s", ctypes.c_float),
    ]


class RM_RoadLaneInfo(ctypes.Structure):
    """道路レーン情報"""
    _fields_ = [
        ("pos", RM_PositionXYZ),
        ("heading", ctypes.c_float),
        ("pitch", ctypes.c_float),
        ("roll", ctypes.c_float),
        ("width", ctypes.c_float),
        ("curvature", ctypes.c_float),
        ("speed_limit", ctypes.c_float),
        ("roadId", ctypes.c_uint32),
        ("junctionId", ctypes.c_uint32),
        ("laneId", ctypes.c_int),
        ("laneOffset", ctypes.c_float),
        ("s", ctypes.c_float),
        ("t", ctypes.c_float),
        ("road_type", ctypes.c_int),
        ("road_rule", ctypes.c_int),
        ("lane_type", ctypes.c_int),
    ]


class RM_RoadProbeInfo(ctypes.Structure):
    """道路プローブ情報"""
    _fields_ = [
        ("road_lane_info", RM_RoadLaneInfo),
        ("relative_pos", RM_PositionXYZ),
        ("relative_h", ctypes.c_float),
    ]


class RM_PositionDiff(ctypes.Structure):
    """位置差分"""
    _fields_ = [
        ("ds", ctypes.c_float),
        ("dt", ctypes.c_float),
        ("dLaneId", ctypes.c_int),
    ]
