"""
esmini RoadManager を使用した OpenDRIVE マップデータ。

OpenDRIVE(.xodr)ファイルを直接読み込み、esminiのネイティブC++エンジンで
座標計算を行う。MapDataBase と同じ公開APIを提供する。
"""
import ctypes
import logging
import math
import os
from typing import List, Tuple, Dict, Optional

from esmini_types import (
    RM_PositionData,
    RM_RoadLaneInfo,
)
from esmini_utils import find_esmini_lib, suppress_esmini_output
from map_data_base import MapDataBase
from road_network import Lane, Road
from spatial_query import SpatialIndex

logger = logging.getLogger(__name__)


class EsminiMapData(MapDataBase):
    """
    esmini RoadManagerを使用したOpenDRIVEマップデータ。

    OpenDRIVEファイルを直接読み込み、MapDataと同じAPIを提供する。
    esminiはグローバル状態を使用するため、同時に1インスタンスのみ利用可能。
    """

    def __init__(
        self,
        xodr_path: str,
        map_offset: Optional[List[float]] = None,
        epsg: Optional[int] = None,
        sampling_step: float = 1.0,
    ):
        """
        OpenDRIVEファイルを読み込み、RoadManagerを初期化する。

        Args:
            xodr_path: OpenDRIVEファイル(.xodr)のパス
            map_offset: マップのオフセット [x, y]
            epsg: EPSGコード
            sampling_step: レーン座標のサンプリング間隔（メートル）
        """
        if not os.path.exists(xodr_path):
            raise FileNotFoundError(f"OpenDRIVE file not found: {xodr_path}")

        self._sampling_step = sampling_step
        self._position_handles: List[int] = []

        # esminiライブラリのロード
        self._load_library()

        # OpenDRIVEファイルの初期化
        with suppress_esmini_output():
            result = self._lib.RM_Init(xodr_path.encode('utf-8'))
        if result != 0:
            raise RuntimeError(f"Failed to initialize RoadManager with file: {xodr_path}")

        self._xodr_path = xodr_path

        # 属性の設定
        self.map_offset = tuple(map_offset[:2]) if map_offset else (0.0, 0.0)
        self.epsg = int(epsg) if epsg is not None else 6677

        # 道路/レーン構造の構築
        self.roads: Dict[str, Road] = {}
        self._build_roads()

        # 空間インデックスの構築
        self._spatial_index = SpatialIndex(self.roads)

    def _load_library(self):
        """esminiRMLibライブラリを読み込む。"""
        lib_path = find_esmini_lib()
        if lib_path is None:
            raise FileNotFoundError(
                "Could not find esmini RoadManager library. "
                "Set ESMINI_LIB_PATH or ESMINI_PATH environment variable."
            )
        self._lib = ctypes.CDLL(lib_path)
        self._define_function_signatures()

    def _define_function_signatures(self):
        """ctypes関数シグネチャを定義する。"""
        self._lib.RM_Init.argtypes = [ctypes.c_char_p]
        self._lib.RM_Init.restype = ctypes.c_int

        self._lib.RM_Close.argtypes = []
        self._lib.RM_Close.restype = ctypes.c_int

        self._lib.RM_CreatePosition.argtypes = []
        self._lib.RM_CreatePosition.restype = ctypes.c_int

        self._lib.RM_DeletePosition.argtypes = [ctypes.c_int]
        self._lib.RM_DeletePosition.restype = ctypes.c_int

        self._lib.RM_SetWorldXYHPosition.argtypes = [
            ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float
        ]
        self._lib.RM_SetWorldXYHPosition.restype = ctypes.c_int

        self._lib.RM_GetPositionData.argtypes = [
            ctypes.c_int, ctypes.POINTER(RM_PositionData)
        ]
        self._lib.RM_GetPositionData.restype = ctypes.c_int

        self._lib.RM_GetLaneInfo.argtypes = [
            ctypes.c_int, ctypes.c_float, ctypes.POINTER(RM_RoadLaneInfo),
            ctypes.c_int, ctypes.c_bool
        ]
        self._lib.RM_GetLaneInfo.restype = ctypes.c_int

        self._lib.RM_GetNumberOfRoads.argtypes = []
        self._lib.RM_GetNumberOfRoads.restype = ctypes.c_int

        self._lib.RM_GetIdOfRoadFromIndex.argtypes = [ctypes.c_uint]
        self._lib.RM_GetIdOfRoadFromIndex.restype = ctypes.c_uint32

        self._lib.RM_GetRoadLength.argtypes = [ctypes.c_uint32]
        self._lib.RM_GetRoadLength.restype = ctypes.c_float

        self._lib.RM_GetRoadNumberOfLanes.argtypes = [ctypes.c_uint32, ctypes.c_float]
        self._lib.RM_GetRoadNumberOfLanes.restype = ctypes.c_int

        self._lib.RM_GetLaneIdByIndex.argtypes = [
            ctypes.c_uint32, ctypes.c_int, ctypes.c_float
        ]
        self._lib.RM_GetLaneIdByIndex.restype = ctypes.c_int

        self._lib.RM_SetLanePosition.argtypes = [
            ctypes.c_int, ctypes.c_uint32, ctypes.c_int, ctypes.c_float,
            ctypes.c_float, ctypes.c_bool
        ]
        self._lib.RM_SetLanePosition.restype = ctypes.c_int

        self._lib.RM_PositionMoveForward.argtypes = [
            ctypes.c_int, ctypes.c_float, ctypes.c_float
        ]
        self._lib.RM_PositionMoveForward.restype = ctypes.c_int

    def _create_position(self) -> int:
        """位置ハンドルを作成する。"""
        handle = self._lib.RM_CreatePosition()
        if handle < 0:
            raise RuntimeError("Failed to create position handle")
        self._position_handles.append(handle)
        return handle

    def _delete_position(self, handle: int):
        """位置ハンドルを削除する。"""
        if handle in self._position_handles:
            self._lib.RM_DeletePosition(handle)
            self._position_handles.remove(handle)

    def _build_roads(self):
        """esminiから全道路/レーン情報を読み取り、Road/Laneオブジェクトを構築する。"""
        num_roads = self._lib.RM_GetNumberOfRoads()
        if num_roads < 0:
            raise RuntimeError("Failed to get number of roads")

        handle = self._create_position()
        try:
            for i in range(num_roads):
                road_id_int = self._lib.RM_GetIdOfRoadFromIndex(i)
                road_id = str(road_id_int)
                road_length = float(self._lib.RM_GetRoadLength(road_id_int))

                # レーンIDを探索的に検出
                # RM_SetLanePositionで各候補lane_idを試し、成功したものを採用
                lane_ids = self._probe_lane_ids(handle, road_id_int, road_length)

                lane_objects = []
                for lane_id_int in lane_ids:
                    lane_id = str(lane_id_int)
                    coords = self._sample_lane_coordinates(
                        handle, road_id_int, lane_id_int, road_length
                    )
                    if not coords:
                        continue

                    lane = Lane(road_id, lane_id, coords)
                    lane_objects.append(lane)

                if not lane_objects:
                    continue

                road = _SimpleRoad(road_id, road_length, lane_objects)
                self.roads[road_id] = road

            # successor/predecessor検出
            self._detect_connections(handle)

        finally:
            self._delete_position(handle)

    def _probe_lane_ids(
        self, handle: int, road_id_int: int, road_length: float, max_lane_id: int = 10
    ) -> List[int]:
        """RM_SetLanePositionで各lane_idを試して有効なレーンIDを検出する。"""
        s_sample = road_length / 2.0
        valid_ids = []
        for lane_id in range(-max_lane_id, max_lane_id + 1):
            if lane_id == 0:
                continue
            with suppress_esmini_output():
                result = self._lib.RM_SetLanePosition(
                    handle, road_id_int, lane_id, 0.0, s_sample, True
                )
            if result >= 0:
                # 設定成功 → 実際にこのroad/laneに配置されたか確認
                pos_data = RM_PositionData()
                self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))
                if int(pos_data.roadId) == road_id_int and int(pos_data.laneId) == lane_id:
                    valid_ids.append(lane_id)
        return valid_ids

    def _sample_lane_coordinates(
        self, handle: int, road_id_int: int, lane_id_int: int, road_length: float
    ) -> List[Tuple[float, float, float]]:
        """レーンの座標をサンプリングする。"""
        coords = []
        pos_data = RM_PositionData()
        step = self._sampling_step
        s = 0.0

        while s <= road_length:
            with suppress_esmini_output():
                result = self._lib.RM_SetLanePosition(
                    handle, road_id_int, lane_id_int, 0.0, s, True
                )
            if result >= 0:
                self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))
                coords.append((float(pos_data.x), float(pos_data.y), float(pos_data.z)))
            s += step

        # 末端が road_length と一致しない場合、最後のポイントを追加
        if s - step < road_length - 0.01:
            with suppress_esmini_output():
                result = self._lib.RM_SetLanePosition(
                    handle, road_id_int, lane_id_int, 0.0, road_length, True
                )
            if result >= 0:
                self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))
                coords.append((float(pos_data.x), float(pos_data.y), float(pos_data.z)))

        return coords

    def _detect_connections(self, handle: int):
        """レーン末端で前進/後退してsuccessor/predecessorを検出する。"""
        pos_data = RM_PositionData()
        probe_distance = 0.5  # 境界を越えるための移動距離

        for road_id, road in self.roads.items():
            road_id_int = int(road_id)
            road_length = road.length

            for lane in road.lanes:
                lane_id_int = int(lane.lane_id)

                # successor検出: レーン末端付近から少し前進
                with suppress_esmini_output():
                    self._lib.RM_SetLanePosition(
                        handle, road_id_int, lane_id_int, 0.0,
                        road_length - 0.1, True
                    )
                    self._lib.RM_PositionMoveForward(handle, probe_distance, -1.0)
                self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))

                next_road_id = str(pos_data.roadId)
                next_lane_id = str(pos_data.laneId)

                if next_road_id != road_id and next_road_id in self.roads:
                    succ_pair = (next_road_id, next_lane_id)
                    if succ_pair not in lane.successors:
                        lane.successors.append(succ_pair)
                    # 逆方向のpredecessorも設定
                    next_road = self.roads[next_road_id]
                    for next_lane in next_road.lanes:
                        if next_lane.lane_id == next_lane_id:
                            pred_pair = (road_id, lane.lane_id)
                            if pred_pair not in next_lane.predecessors:
                                next_lane.predecessors.append(pred_pair)
                            break

                # predecessor検出: レーン先頭付近から少し後退
                with suppress_esmini_output():
                    self._lib.RM_SetLanePosition(
                        handle, road_id_int, lane_id_int, 0.0, 0.1, True
                    )
                    self._lib.RM_PositionMoveForward(handle, -probe_distance, -1.0)
                self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))

                prev_road_id = str(pos_data.roadId)
                prev_lane_id = str(pos_data.laneId)

                if prev_road_id != road_id and prev_road_id in self.roads:
                    pred_pair = (prev_road_id, prev_lane_id)
                    if pred_pair not in lane.predecessors:
                        lane.predecessors.append(pred_pair)
                    # 逆方向のsuccessorも設定
                    prev_road = self.roads[prev_road_id]
                    for prev_lane in prev_road.lanes:
                        if prev_lane.lane_id == prev_lane_id:
                            succ_pair = (road_id, lane.lane_id)
                            if succ_pair not in prev_lane.successors:
                                prev_lane.successors.append(succ_pair)
                            break

    @property
    def coordinate_rotation(self) -> float:
        """esminiの座標系は回転不要（0度）"""
        return 0.0

    # --- MapDataBase 抽象メソッド実装 ---

    def get_closest_lane_and_road(self, x: float, y: float) -> Tuple[str, str, Dict]:
        """SpatialIndexに委譲して最近傍のレーンと道路を返す。"""
        return self._spatial_index.get_closest_lane_and_road(x, y, self.roads)

    def get_lane_yaw(self, x: float, y: float) -> Tuple[float, float, str, str]:
        """esmini RM_GetLaneInfo でヨー角とZ座標を直接取得する。"""
        handle = self._create_position()
        try:
            with suppress_esmini_output():
                result = self._lib.RM_SetWorldXYHPosition(handle, x, y, 0.0)
            if result < 0:
                raise ValueError(f"Failed to set world position for ({x}, {y})")

            pos_data = RM_PositionData()
            self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))

            lane_info = RM_RoadLaneInfo()
            self._lib.RM_GetLaneInfo(handle, 0.0, ctypes.byref(lane_info), 0, True)

            return lane_info.heading, pos_data.z, str(pos_data.roadId), str(pos_data.laneId)
        finally:
            self._delete_position(handle)

    def get_travel_coordinates(
        self,
        start_position: Tuple[float, float],
        total_distance: float,
    ) -> List[Tuple[float, float, float]]:
        """esmini RM_PositionMoveForward で道路接続を自動追従しながら座標列を生成する。"""
        handle = self._create_position()
        coords = []

        try:
            x, y = start_position
            with suppress_esmini_output():
                result = self._lib.RM_SetWorldXYHPosition(handle, x, y, 0.0)
            if result < 0:
                logger.error("Failed to set initial position (%s, %s)", x, y)
                return []

            pos_data = RM_PositionData()
            self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))
            coords.append((float(pos_data.x), float(pos_data.y), float(pos_data.z)))

            distance = abs(total_distance)
            direction = 1 if total_distance > 0 else -1
            step = 1.0
            traveled = 0.0

            while traveled < distance:
                move_dist = min(step, distance - traveled) * direction

                with suppress_esmini_output():
                    result = self._lib.RM_PositionMoveForward(handle, move_dist, -1.0)
                if result < 0:
                    logger.error("Failed to move forward at distance %s", traveled)
                    break

                self._lib.RM_GetPositionData(handle, ctypes.byref(pos_data))
                coords.append((float(pos_data.x), float(pos_data.y), float(pos_data.z)))
                traveled += step

            return coords
        finally:
            self._delete_position(handle)

    def get_lane_and_successors(
        self, road_id: str, lane_id: str, include_successors: bool = False
    ) -> List[Tuple[str, str, List[Tuple[float, float, float]]]]:
        """Road/Laneオブジェクトからsuccessorsを辿る。"""
        road = self.roads.get(road_id)
        if not road:
            raise ValueError(f"Road ID {road_id} not found")

        for lane in road.lanes:
            if lane.lane_id == lane_id:
                lanes_info = [(road_id, lane_id, lane.coordinate)]

                if include_successors:
                    current_lane = lane
                    while current_lane.successors:
                        next_road_id, next_lane_id = current_lane.successors[0]
                        next_road = self.roads.get(next_road_id)
                        if not next_road:
                            break
                        next_lane = next(
                            (l for l in next_road.lanes if l.lane_id == next_lane_id), None
                        )
                        if not next_lane:
                            break
                        lanes_info.append(
                            (next_road_id, next_lane_id, next_lane.coordinate)
                        )
                        current_lane = next_lane

                return lanes_info

        raise ValueError(f"Lane ID {lane_id} not found in road {road_id}")

    def get_successor_lane(
        self, road_id: str, lane_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Road/Laneオブジェクトからsuccessorを参照する。"""
        road = self.roads.get(road_id)
        if not road:
            return None, None

        for lane in road.lanes:
            if lane.lane_id == lane_id:
                if lane.successors:
                    return lane.successors[0]
                return None, None

        return None, None

    def get_lane_coords(
        self, road_id: str, lane_id: str
    ) -> List[Tuple[float, float, float]]:
        """Road/Laneオブジェクトから座標を参照する。"""
        road = self.roads.get(road_id)
        if not road:
            raise ValueError(f"Road ID {road_id} not found")

        for lane in road.lanes:
            if lane.lane_id == lane_id:
                return lane.coordinate

        raise ValueError(f"Lane ID {lane_id} not found in road {road_id}")

    def calculate_lateral_offset(
        self, x: float, y: float
    ) -> Tuple[float, str, str, Tuple[float, float, float]]:
        """最近傍車線からの横方向オフセットを計算する。"""
        road_id, lane_id, info = self.get_closest_lane_and_road(x, y)
        if not road_id or not lane_id:
            return 0.0, "", "", (x, y, 0.0)

        closest_point = info["closest_point"]
        closest_index = info["closest_index"]
        coords = info["coordinates"]

        if closest_index + 1 < len(coords):
            p1 = coords[closest_index]
            p2 = coords[closest_index + 1]
            tangent_x = p2[0] - p1[0]
            tangent_y = p2[1] - p1[1]
        elif closest_index > 0:
            p1 = coords[closest_index - 1]
            p2 = coords[closest_index]
            tangent_x = p2[0] - p1[0]
            tangent_y = p2[1] - p1[1]
        else:
            return 0.0, road_id, lane_id, closest_point

        tangent_len = math.sqrt(tangent_x**2 + tangent_y**2)
        if tangent_len == 0:
            return 0.0, road_id, lane_id, closest_point
        tangent_x /= tangent_len
        tangent_y /= tangent_len

        dx = x - closest_point[0]
        dy = y - closest_point[1]

        lateral_offset = dx * (-tangent_y) + dy * tangent_x

        return lateral_offset, road_id, lane_id, closest_point

    def __del__(self):
        """デストラクタ：リソースをクリーンアップする。"""
        if hasattr(self, '_position_handles'):
            for handle in self._position_handles[:]:
                try:
                    self._lib.RM_DeletePosition(handle)
                except Exception:
                    pass
            self._position_handles.clear()

        if hasattr(self, '_lib'):
            try:
                self._lib.RM_Close()
            except Exception:
                pass


class _SimpleRoad:
    """EsminiMapData内部用の簡易Roadオブジェクト。

    road_network.Roadはdict入力を前提としているため、
    esminiから構築したLaneオブジェクトを直接保持する軽量クラスを使用する。
    """

    def __init__(self, road_id: str, length: float, lanes: List[Lane]):
        self.id = road_id
        self.name = None
        self.length = length
        self.junction = None
        self.links = {}
        self.lanes = lanes
