"""
MapDataファクトリ関数。

ファイル拡張子に基づいて適切なMapData実装を自動選択する。
- .json → MapData（JSON形式の道路座標ファイル）
- .xodr → EsminiMapData（OpenDRIVEファイル直接読み込み）
"""
from typing import List, Optional

from map_data_base import MapDataBase


def create_map_data(
    path: str,
    map_offset: Optional[List[float]] = None,
    epsg: Optional[int] = None,
) -> MapDataBase:
    """
    ファイル拡張子に基づいて適切なMapData実装を返す。

    Args:
        path: マップデータファイルパス（.json または .xodr）
        map_offset: マップのオフセット [x, y]
        epsg: EPSGコード

    Returns:
        MapDataBase: MapData または EsminiMapData のインスタンス
    """
    if path.endswith('.xodr'):
        from esmini_map_data import EsminiMapData
        return EsminiMapData(path, map_offset=map_offset, epsg=epsg)
    else:
        from map_data import MapData
        return MapData(path)
