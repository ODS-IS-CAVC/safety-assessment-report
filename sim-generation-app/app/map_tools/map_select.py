import logging
import os
import json
import argparse
import numpy as np
import pandas as pd
import cv2
import matplotlib.pyplot as plt
from pyproj import CRS, Transformer
import re

logger = logging.getLogger(__name__)

DEBUG=0

def get_angle(start, end):
    vec = end - start
    radian = np.arctan2(vec[0], vec[1])
    deg = np.degrees(radian)
    if deg < 0:
        deg += 360
    return deg

def get_wayid_list(route_path, coordinates_path, lane_id_org, column_names, epsg, center, tolerance=15):
    # routeデータを取得
    # get_routepoints(route_path)
    csv_data = pd.read_csv(route_path)
    route_points = []
    lon = column_names[0]
    lat = column_names[1]
    for i in range(1,len(csv_data)):
        route_points.append(np.array([csv_data[lat][i],csv_data[lon][i]]))

    epsg_from = 4326 # WGS84
    start = route_points[0]
    end = route_points[-1]
    start = transform_coordinates(epsg_from, epsg, start)
    end = transform_coordinates(epsg_from, epsg, end)
    start_point = np.array([start[0]-center[0],start[1]-center[1]])
    end_point = np.array([end[0]-center[0],end[1]-center[1]])

    route_point_temp = []
    for i in route_points:
        point = transform_coordinates(epsg_from, epsg, i)
        route_point_temp.append([point[0]-center[0],point[1]-center[1]])
    route_points = route_point_temp

    route_vec = get_angle(start_point,end_point)

    # xodr_road_jsonを取得
    xodr_data = {}
    with open(coordinates_path, "r", encoding="utf-8") as f:
        xodr_data = json.load(f)

    if DEBUG:
        # レーン情報の座標データ取得
        roads_points = []
        for road in xodr_data["roads"]:
            lanes = road["lanes"]
            for lane in lanes:
                coordinate = np.array(lane["coordinate"])
                roads_points.append(coordinate)
        roads_points = np.concatenate(roads_points)

        # リストを2次元に変換
        points_2d = np.array([[x, y] for x, y, z in roads_points], dtype=np.float32)
        for point in points_2d:
            plt.plot(point[0],point[1],".",color="black",markersize=1)

    # レーン情報の座標データ取得
    way_ids = []
    flg = int(lane_id_org) == -100
    for road in xodr_data["roads"]:
        lanes = road["lanes"]
        roads_points = []
        lane_ids = []
        for lane in lanes:
            roads_points.append(np.array(lane["coordinate"]))
            lane_ids.append(lane["lane_id"])
        if len(roads_points) == 0:
            continue
        lane_ids = sorted(lane_ids, key=int)
        roads_points = np.concatenate(roads_points)
        aabb = get_aabb(roads_points, tolerance)
        if DEBUG:
            plt.plot([aabb[0][0],aabb[1][0]], [aabb[0][1],aabb[1][1]], color="green")
            plt.plot([aabb[0][0],aabb[2][0]], [aabb[0][1],aabb[2][1]], color="green")
            plt.plot([aabb[2][0],aabb[3][0]], [aabb[2][1],aabb[3][1]], color="green")
            plt.plot([aabb[3][0],aabb[1][0]], [aabb[3][1],aabb[1][1]], color="green")
        road_vec = get_angle(np.array([roads_points[0][0], roads_points[0][1]]), np.array([roads_points[-1][0], roads_points[-1][1]]))
        if flg:
            lane_id = lane_ids[-1]
        elif len(lane_ids) == 1 and int(lane_ids[0]) == abs(1):
            lane_id = lane_ids[0]
        elif int(lane_id_org) > int(lane_ids[-1]):
            continue
            lane_id = lane_ids[-1]
        else :
            lane_id = lane_id_org
        for route_point in route_points:
            if in_aabb(aabb, route_point):
                vec = [route_vec,road_vec]
                vec.sort()
                # ルートと道に90度以上の差がなければ追加する。
                if abs(vec[0] - vec[1]) < 90:
                    way_ids.append({"road":road["id"], "lane":lane_id})
                    if DEBUG:
                        for point in roads_points:
                            plt.plot(point[0],point[1],".",color="yellow",markersize=1)
                        plt.plot([aabb[0][0],aabb[1][0]], [aabb[0][1],aabb[1][1]], color="blue")
                        plt.plot([aabb[0][0],aabb[2][0]], [aabb[0][1],aabb[2][1]], color="blue")
                        plt.plot([aabb[2][0],aabb[3][0]], [aabb[2][1],aabb[3][1]], color="blue")
                        plt.plot([aabb[3][0],aabb[1][0]], [aabb[3][1],aabb[1][1]], color="blue")
                break

    if DEBUG:
        for i in route_point_temp:
            plt.plot(i[0],i[1],'.',color="red")
        plt.savefig(route_path+'_figure.png')

    return way_ids

def transform_coordinates(epsg_from, epsg_to, points):
    srcCRS = CRS(f'EPSG:{epsg_from}')
    dstCRS = CRS(f'EPSG:{epsg_to}')
    transformer = Transformer.from_crs(srcCRS, dstCRS, always_xy=True)
    results = transformer.transform(points[1],points[0])

    return results

def get_aabb(points, tolerance):
    points_2d = np.array([[x, y] for x, y, z in points], dtype=np.float32)

    # 外接矩形を求める
    rect = cv2.boundingRect(points_2d)

    # 外接矩形を描画
    x, y, w, h = rect
    a = [x-tolerance,y-tolerance]
    b = [x+w+tolerance,y-tolerance]
    c = [x-tolerance,y+h+tolerance]
    d = [x+w+tolerance,y+h+tolerance]
    aabb = [a, b, c, d]

    return aabb

def check_road_rect(aabb,route_data_path,map_data_path):
    '''
    データ確認用
    点群、点群の外接矩形（aabb）を描画
    '''
    csv_data = pd.read_csv(route_data_path).values.tolist()
    x = []
    y = []
    for i in range(1,len(csv_data)):
        x.append(csv_data[i][2])
        y.append(csv_data[i][3])

    plt.scatter(y, x)
    plt.grid()

    x = (aabb[0][0],aabb[1][0],aabb[3][0],aabb[2][0],aabb[0][0])
    y = (aabb[0][1],aabb[1][1],aabb[3][1],aabb[2][1],aabb[0][1])
    plt.plot(x,y)
    plt.savefig(map_data_path+"sin.png") 
    plt.clf()
    plt.close()

def in_aabb(aabb,target):
    if aabb[0][0] < target[0] < aabb[3][0] and aabb[0][1] < target[1] < aabb[3][1]:
        return True
    else:
        return False

def find_min_max(csv_path, column_names):
    """CSVファイルから緯度経度の最大、最小値を取得する

    Args:
        csv_path (string): CSV ファイルパス
        column_names (dic): 緯度経度のヘッダー文字列

    Returns:
        dic: 緯度経度 (min, max)
    """
    df = pd.read_csv(csv_path)
    results = {}

    for column in column_names:
        if column in df.columns:
            min_value = df[column].min()
            max_value = df[column].max()
            results[column] = (min_value, max_value)

    return results

def main():
    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "--route_data_path",
        type=str,
        # required=True,
        help="route_dataファイルパス",
    )
    parser.add_argument(
        "--map_data_path",
        type=str,
        # required=True,
        default="try_bravs/map_tools/map_data",
        help="map_dataファイルパス",
    )
    parser.add_argument(
        "--vdrive_path",
        type=str,
        # required=True,
        default="/mnt/efs/try/",
        help="V-Drive Rootパス",
    )
    parser.add_argument(
        "--lane_id",
        type=str,
        # required=True,
        default="-100",
        help="laneのID",
    )
    parser.add_argument(
        "--output_correct_target",
        type=str,
        # required=True,
        default="try_bravs/map_tools/map_data/",
        help="correct_targetを格納するパス",
    )
    parser.add_argument(
        "--lon_column_name",
        type=str,
        # required=True,
        default="lon",
        help="経度のcolumn名",
    )
    parser.add_argument(
        "--lat_column_name",
        type=str,
        # required=True,
        default="lat",
        help="緯度のcolumn名",
    )
    parser.add_argument(
        "--priority_map",
        type=str,
        default="",
        help="優先マップ名",
    )
    args = parser.parse_args()
    route_data_path = args.route_data_path
    map_data_path = args.map_data_path
    vdrive_path = args.vdrive_path
    lane_id = args.lane_id
    lon_name = args.lon_column_name
    lat_name = args.lat_column_name
    priority_map = args.priority_map

    # route_csvから、最小,最大の緯度経度を取得する
    column_names = [lon_name, lat_name]
    lat_lon_min_max = find_min_max(route_data_path, column_names)
    min_point = [lat_lon_min_max[lon_name][0], lat_lon_min_max[lat_name][0]]
    max_point = [lat_lon_min_max[lon_name][1], lat_lon_min_max[lat_name][1]]

    map_data_list = os.listdir(map_data_path)
    if "V-DriveROOT" in map_data_list: map_data_list.remove("V-DriveROOT")

    candidate_data = []
    for map_data_name in map_data_list:
        map_info_path = os.path.join(map_data_path, map_data_name)
        map_data = os.listdir(map_info_path)
        if not "map_info.json" in map_data:
            logger.warning("%sのファイルが足りません。", map_data_name)
            continue
        # map_jsonからAABBを取得する。
        with open(os.path.join(map_info_path, "map_info.json"), "r", encoding="utf-8") as f:
            map_info = json.load(f)
        aabb = map_info["aabb"]
        if DEBUG:
            check_road_rect(aabb, route_data_path, map_info_path)
        flg = in_aabb(aabb, min_point) and in_aabb(aabb, max_point)
        if flg:
            candidate_data.append(map_data_name)
    if len(candidate_data) == 0:
        logger.warning("ルートに対応するマップがありません。")
        return

    # 優先マップを使うように設定する。
    select_map_name = ""
    map_flg = 0

    # 指定された優先マップの文字列を除く数値を確認
    priority_map_number = ""
    if priority_map != "":
        index = priority_map.find('_')
        # 最初の'_'以降の部分を取得
        if index != -1:
            priority_map_trim = priority_map[index+1:]
        else:
            priority_map_trim = priority_map
        priority_map_number = re.sub(r'[^1-9]', '', priority_map_trim)

    for map_name in candidate_data:
        map_name_number = re.sub(r'[^1-9]', '', map_name)
        if map_name[:2] == "E1" \
        or "MEXC1_South" in map_name \
        or "MEXC1_North" in map_name:
            select_map_name = map_name
            map_flg = 1
        elif map_name_number == priority_map_number:
            select_map_name = map_name
            map_flg = 1
        elif map_name[:5] == "MEXC1":
            select_map_name = map_name
            map_flg = 1
        elif map_flg == 0:
            select_map_name = map_name

    map_info = {}
    map_info_path = os.path.join(map_data_path, select_map_name, "map_info.json")
    with open(map_info_path, "r", encoding="utf-8") as f:
        map_info = json.load(f)
    center = map_info["center"]
    epsg = map_info["epsg"]
    opendrive_path = os.path.join(vdrive_path, map_info["opendrive_path"])
    map_model_path = os.path.join(vdrive_path, map_info["3dmapModel_path"])
    road_coordinates_path = os.path.join(map_data_path, map_info["road_coordinates_path"])
    json_path = os.path.normpath(os.path.join(map_data_path, road_coordinates_path))

    wayid_list = get_wayid_list(route_data_path, json_path, lane_id ,column_names, epsg, center)

    json_data = {
        "name": route_data_path,
        "center": center,
        "epsg": epsg,
        "opendrive_path": opendrive_path,
        "3dmapModel_path": map_model_path,
        "road_coordinates_path": json_path,
        "wayID": wayid_list
    }

    map_select_result_path = route_data_path[:-4] + "_MapSelectResult.json"
    with open(map_select_result_path,"w") as file :
        json.dump(json_data, file, indent = 2)

    map_self_path = route_data_path[:-4] + "_self.json"
    json_data = {
        "self": {
            "targets": wayid_list
        },
        "detections": []
    }
    with open(map_self_path,"w") as file :
        json.dump(json_data, file, indent = 2)

if __name__ == "__main__":
    main()