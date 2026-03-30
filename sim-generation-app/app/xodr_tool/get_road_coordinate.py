import logging
import os
import json
import math
import numpy as np
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import argparse
import copy

logger = logging.getLogger(__name__)

DEBUG = 0
# util
def get_directories(path):
    if not os.path.exists(path):
        return []
    return [os.path.join(path, name) for name in os.listdir(path) if os.path.isdir(os.path.join(path, name))]

def check_file(filename, match_str):
    if match_str == "" or match_str in filename:
        return True
    
    return False

def find_first_matching_file(path, match_str="", extension=None):
    if not os.path.exists(path):
        return None
    for name in os.listdir(path):
        exstension_check = True if extension is None else name.endswith(extension)
        if check_file(name, match_str) and exstension_check:
            return os.path.join(path, name)
    return None

# opendrive
def cubic_polynomial(a, b, c, d, p):
    return a + b * p + c * p**2 + d * p**3

def calc_line(start_x, start_y, hdg, length, number_point):
    # 直線の終点を計算
    end_x = start_x + length * math.cos(hdg)
    end_y = start_y + length * math.sin(hdg)
    
    x_values = np.linspace(start_x, end_x, number_point)
    y_values = np.linspace(start_y, end_y, number_point)

    return x_values, y_values


def calc_poly3line(u_lists, v_lists, start_x, start_y, hdg, number_point):
    if len(u_lists) != 4 or len(v_lists) != 4:
        return
    # 点群100個
    p_values = np.linspace(0, 1, number_point)

    # uv座標を求める
    u_values = cubic_polynomial(u_lists[0], u_lists[1], u_lists[2], u_lists[3], p_values)
    v_values = cubic_polynomial(v_lists[0], v_lists[1], v_lists[2], v_lists[3], p_values)

    # 始点・終点・傾きから実際の座標を求める
    theta = hdg + math.atan(v_lists[1] / u_lists[1])
    x_values = start_x + u_values * math.cos(theta) - v_values * math.sin(theta)
    y_values = start_y + u_values * math.sin(theta) + v_values * math.cos(theta)
    return x_values, y_values, theta

def calc_tangent_vector(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx*dx + dy*dy)
    return (dx/length, dy/length) if length != 0 else (0, 0)

def shift_coordinates(x_values, y_values, offsets, hdg):
    # Calculate the shift in x and y direction

    if len(x_values) <= 1:
        dx = offsets * -np.sin(hdg)
        dy = offsets * np.cos(hdg)
        shift_x_vals = x_values + dx
        shift_y_vals = y_values + dy
        return shift_x_vals, shift_y_vals

    shift_x_vals = []
    shift_y_vals = []
    xy_values = list(zip(x_values, y_values))
    for i in range(len(xy_values)):
        if i == 0: # first
            tan_x, tan_y = calc_tangent_vector(xy_values[0], xy_values[1])
        elif i == len(xy_values) - 1: # last
            tan_x, tan_y = calc_tangent_vector(xy_values[-2], xy_values[-1])
        else: # middle
            tan_prev = calc_tangent_vector(xy_values[i-1], xy_values[i])
            tan_next = calc_tangent_vector(xy_values[i], xy_values[i+1])
            tan_x = (tan_prev[0] + tan_next[0]) / 2
            tan_y = (tan_prev[1] + tan_next[1]) / 2
            length = math.sqrt(tan_x**2 + tan_y**2)
            tan_x, tan_y = (tan_x/length, tan_y/length) if length != 0 else (0, 0)
        
        norm_x, norm_y = -tan_y, tan_x

        shift_x_vals.append(x_values[i] + offsets[i] * norm_x)
        shift_y_vals.append(y_values[i] + offsets[i] * norm_y)

    return shift_x_vals, shift_y_vals

def calc_cubic_polynomial(lists, dist, section=0):
    if len(lists) == 0:
        return 0.0
    # 
    for elevation in reversed(lists):
        s, a, b, c, d = elevation
        s = s + section
        if s > dist:
            continue
        ds = dist - s
        h = cubic_polynomial(a, b, c, d, ds)
        return h

def calc_value_according_to_dist(s, length, polynomial_lists, number_point):
   dists = np.linspace(0, length, number_point)
   dists = dists + s
   result = [calc_cubic_polynomial(polynomial_lists, d) for d in dists]
   return result

def shift_elevations(elevations, super_elevations, offsets):
    if len(elevations) != len(super_elevations):
        return elevations
    
    z_values = [e + o * math.tan(s) for e, s, o in zip(elevations, super_elevations, offsets)]
    return z_values

def calc_lane_offset(s, length, number_point, lane_id: str, center_offsets, lane_sections, lane_offsets):
    lane_id_num = int(lane_id)
    dists = np.linspace(0, length, number_point)
    dists = dists + s

    offsets = copy.deepcopy(center_offsets)
    lane_id_sign =  -1 if lane_id_num < 0 else 1

    lane_section_idx = 0
    lane_section_dist_dict = {}
    delete_keys = []
    for lane_s_idx, lane_s in enumerate(lane_sections):
        for d_idx, d in enumerate(dists):
            if float(lane_s) >= d:
                continue
            lane_section_idx = lane_s_idx
            if not any(lane_section_dist_dict):
                lane_section_dist_dict[str(lane_section_idx)] = [0, d_idx + 1]
            elif str(lane_section_idx) in lane_section_dist_dict.keys():
                lane_section_dist_dict[str(lane_section_idx)] = [lane_section_dist_dict[str(lane_section_idx)][0], d_idx + 1]        
            else:
                last_dict_key = next(reversed(lane_section_dist_dict), None)
                last_d_idx = lane_section_dist_dict[last_dict_key][1]
                if lane_section_dist_dict[last_dict_key][0] < d_idx:
                    lane_section_dist_dict[last_dict_key][1] = d_idx
                else:
                    delete_keys.append(last_dict_key)
                lane_section_dist_dict[str(lane_section_idx)] = [d_idx, last_d_idx]
                break

    last_val_key = None
    for k, v in reversed(lane_section_dist_dict.items()):
        if last_val_key is None:
            if v[0] == v[1]:
                last_val_key = (v[0], k)
            continue

        if last_val_key[0] == v[1]:
            lane_section_dist_dict[last_val_key[1]] = lane_section_dist_dict[k]
            delete_keys.append(k)
    
    for del_key in set(delete_keys):
        del lane_section_dist_dict[del_key]
        
    calculate_flg = False
    for i in range(1, abs(lane_id_num) + 1):
        for k, v in lane_section_dist_dict.items():
            lane_offsets_dict = lane_offsets[int(k)]
            if lane_id not in lane_offsets_dict.keys():
                offsets[v[0]:v[1]] = [0] * (v[1] - v[0])
                continue
            # no acquisition except on the driving route
            lane_type = lane_offsets_dict[lane_id][0]
            if lane_type != "driving":
                offsets[v[0]:v[1]] = [0] * (v[1] - v[0])
                continue
            lane_offset_values = [
                calc_cubic_polynomial(
                    lane_offsets_dict[str(lane_id_sign * i)][1],
                    d,
                    float(lane_sections[int(k)])
                ) 
                for d in dists[v[0]:v[1]]
            ]
            # padding zero
            if len(lane_offset_values) != number_point:
                def pad_with_zeros(sublist, length, offset=0):
                    return [0] * offset + sublist + [0] * (length - len(sublist) - offset)
                lane_offset_values = pad_with_zeros(lane_offset_values, number_point, v[0])

            lane_offset_values = np.array(lane_offset_values, dtype=np.float64)
            if i == abs(lane_id_num):
                # 対象ならオフセットの半分
                offsets = offsets + lane_id_sign * lane_offset_values / 2
                calculate_flg = True
            else:
                offsets = offsets + lane_id_sign * lane_offset_values

    if not calculate_flg and all(x == 0 for x in offsets):
        return None
    comparison = [a == b and b != 0.0 for a, b in zip(offsets, center_offsets)]
    if any(comparison):
        return None
    return offsets

   
def main():
    parser = argparse.ArgumentParser(description="OpenDRIVEファイルからレーン情報抽出")
    parser.add_argument(
        "--map_data_dir",
        type=str,
        # required=True,
        default="",
        help="OpenDRIVEファイル",
    )
    parser.add_argument(
        "--xodr_file",
        type=str,
        # required=True,
        default="try_osmtools/data/divp_Map_Shutoko_C1_notree.xodr",
        help="OpenDRIVEファイル",
    )
    parser.add_argument(
        "--catalog_json",
        type=str,
        # required=True,
        default="try_osmtools/data/divp_Map_Shutoko_C1_notree.xodr",
        help="OpenDRIVEファイル",
    )
    parser.add_argument(
        "--output_file_name",
        type=str,
        default="xodr_road_coordinates.json",
        help="出力ファイル名",
    )
    parser.add_argument(
        "--fixed_point_flg",
        type=bool,
        default=False,
        help='transform to'
    )
    parser.add_argument(
        "--number_point",
        type=int,
        default=100,
        help='transform to'
    )


    args = parser.parse_args()
    map_data_dir = args.map_data_dir
    assert isinstance(map_data_dir, str)
    
    xodr_file = args.xodr_file
    assert isinstance(xodr_file, str)

    catalog_json = args.catalog_json
    assert isinstance(catalog_json, str)
    
    output_file_name = args.output_file_name
    assert isinstance(output_file_name, str)

    fixed_point_flg = args.fixed_point_flg
    assert isinstance(fixed_point_flg, bool)

    number_point = args.number_point
    assert isinstance(number_point, int)
    
    map_dir_list = get_directories(map_data_dir)
    try:
        if len(map_dir_list) < 1:
            epsg_code, map_offset = catalog_json_parse(catalog_json)
            road_coordinate_json = get_xodr_road_coordinate(xodr_file, epsg_code, fixed_point_flg, number_point, map_offset)
            output_file_path = os.path.join(os.path.dirname(catalog_json), output_file_name)
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(road_coordinate_json, f, ensure_ascii=False, indent=2)
            return
    except Exception as e:
        logger.error(
            "error.\ninput_xodr_path:%s\ninput_catalog_path:%s\nerror_type: %s\nerror_message: %s",
            xodr_file, catalog_json, type(e), e
        )

    for map_dir in map_dir_list:
        try:
            catalog_path = find_first_matching_file(map_dir, "catalog", ".json")
            xodr_path = find_first_matching_file(map_dir, "", "xodr")
            if catalog_path is None:
                raise FileNotFoundError(f"file not found:{catalog_path}")
            if xodr_path is None:
                raise FileNotFoundError(f"file not found: {xodr_path}")
            epsg_code, map_offset = catalog_json_parse(catalog_path)
            road_coordinate_json = get_xodr_road_coordinate(xodr_path, epsg_code, fixed_point_flg, number_point, map_offset)
            output_file_path = os.path.join(map_dir, output_file_name)
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(road_coordinate_json, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(
                "File not created.\nmap directory:%s\nerror_type: %s\nerror_message: %s",
                map_dir, type(e), e
            )


def catalog_json_parse(catalog_path):
    epsg_code = ""
    map_offset = [0.0, 0.0]
    if not os.path.exists(catalog_path):
        return epsg_code, map_offset 
    # load xodr json file
    catalog_data = {}
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_data = json.load(f)

    catalog_map_data = catalog_data["map"]
    epsg_code = str(catalog_map_data["target_epsg"])
    
    map_offset = [catalog_map_data["map_origin_by_offset"]["north"], catalog_map_data["map_origin_by_offset"]["east"]]
    return epsg_code, map_offset



def get_xodr_road_coordinate(xodr_file, epsg_code, fixed_point_flg, number_point, catalog_map_offset=[0.0, 0.0]):
    # xodrファイルのパース
    tree = ET.parse(xodr_file)
    root = tree.getroot()
    # マップオフセット（world coordinate）取得
    offset_element = root.find('header').find('offset')
    if offset_element is not None:
        map_offset = [offset_element.get('x'), offset_element.get('y')]
    else:
        map_offset = catalog_map_offset

    # junctions for road link
    junctions_dict = {}
    for child in root:
        if child.tag == 'junction':
            id = child.get('id')
            if id not in junctions_dict:
                junctions_dict[id] = []
            junctions_dict[id] = child

    # roads
    roads_root = [child for child in root if child.tag == 'road']
    x_values = []
    y_values = []
    roads_json = []
    for road in roads_root:
        road_name = road.get('name')
        road_length = road.get('length')
        road_id = road.get('id')
        road_junction = road.get('junction')
        plan_view_root = road.find('planView')
        lanes_root = road.find('lanes')
        link_root = road.find('link')
        elevation_profile_root = road.find('elevationProfile')
        lateral_profile_root = road.find('lateralProfile')
        # elevation
        elevation_list = []
        if elevation_profile_root is not None:
            for elevation in elevation_profile_root:
                elevation_list.append([float(item[1]) for item in elevation.items()])
        # superelevation
        superelevation_list = []
        if lateral_profile_root is not None:
            for superelevation in lateral_profile_root:
                superelevation_list.append([float(item[1]) for item in superelevation.items()])

        # lane
        lanes_json = []
        # lane center offset
        lane_center_offsets = []
        for lane_center_offset in lanes_root.findall('laneOffset'):
            lane_center_offsets.append([float(item[1]) for item in lane_center_offset.items()])

        lane_offsets = [] # 2 dimensions
        lane_sections = []
        lane_sections_root = lanes_root.findall('laneSection')
        for lane_section_element in lane_sections_root:
            lane_sections.append(lane_section_element.get('s'))
            lane_offset = {}
            for lane_group in lane_section_element:
                lane_tag = lane_group.tag
                lane_dict = None
                for lane in lane_group:
                    lane_id = lane.get('id')
                    lane_type = lane.get('type')

                    if lane_tag == "center":
                        continue
                    
                    lane_offset[lane_id] = (lane_type,[])
                    for lane_width_element in lane.findall('width'):
                        lane_offset[lane_id][1].append([float(item[1]) for item in lane_width_element.items()])

                    # no acquisition except on the driving route
                    if lane_type != "driving":
                        continue

                    lane_dict = { "lane": lane_tag, "lane_id": lane_id, "coordinate": [] }
                    # duplicate lane id check
                    if not any(d["lane_id"] == lane_dict["lane_id"] for d in lanes_json):
                        lanes_json.append(lane_dict)
            
            lane_offsets.append(lane_offset)
        
        # lane count
        lane_count = len(lanes_json)

        x_road_vals = [[] for _ in range(lane_count)]
        y_road_vals = [[] for _ in range(lane_count)]
        z_road_vals = [[] for _ in range(lane_count)]
        # geometry
        if plan_view_root is None:
            continue
        for geometry in plan_view_root:
            s, x, y, hdg, length = [float(item[1]) for item in geometry.items()]
            
            x_vals = []
            y_vals = []
            poly3 = geometry.find('paramPoly3')
            # 
            point = number_point if fixed_point_flg else int(length)
            if poly3 is not None:
                # get uv data
                uv_lists = [float(item[1]) for item in poly3.items() if item[0] != "pRange"]
                x_vals, y_vals, hdg = calc_poly3line(uv_lists[:4], uv_lists[4:], x, y, hdg, point)
            else:
                x_vals, y_vals = calc_line(x, y, hdg, length, point)

            heights = calc_value_according_to_dist(s, length, elevation_list, point)
            radians = calc_value_according_to_dist(s, length, superelevation_list, point)

            center_offsets = calc_value_according_to_dist(s, length, lane_center_offsets, point)
            
            for idx, lane_dict in enumerate(lanes_json):
                offsets = calc_lane_offset(s, length, point, lane_dict["lane_id"], center_offsets, lane_sections, lane_offsets)
                # lane id not present in this geometry
                if offsets is None:
                    continue
                
                # レーンIDによって要素を消すため、一時
                x_tmp_vals = x_vals
                y_tmp_vals = y_vals
                tmp_offsets = offsets
                tmp_heights = heights
                tmp_radians = radians
                
                if not all(x == 0 for x in tmp_offsets):
                    tmp_offsets = np.array(tmp_offsets, dtype=np.float64)
                    indices_to_remove = np.where(tmp_offsets == 0.0)[0]
                    if len(indices_to_remove) > 0:
                        # インデックスを逆順にして削除（逆順にすることでインデックスのずれを防ぐ）
                        x_tmp_vals = np.delete(x_tmp_vals, indices_to_remove)
                        y_tmp_vals = np.delete(y_tmp_vals, indices_to_remove)
                        tmp_offsets = np.delete(tmp_offsets, indices_to_remove)
                        tmp_heights = np.delete(tmp_heights, indices_to_remove)
                        tmp_radians = np.delete(tmp_radians, indices_to_remove)
                x_vals_line, y_vals_line = shift_coordinates(x_tmp_vals, y_tmp_vals, tmp_offsets, hdg)
                x_road_vals[idx].append(x_vals_line)
                y_road_vals[idx].append(y_vals_line)
                z_vals_line = shift_elevations(tmp_heights, tmp_radians, tmp_offsets)
                z_road_vals[idx].append(z_vals_line)
        # off-lamp support
        invalid_lane_list = []
        for idx in range(0, lane_count):
            if len(x_road_vals[idx]) < 1:
                lane_id_dbg = lanes_json[idx]["lane_id"]
                logger.warning("road value invalid. road id:%s lane id:%s", road_id, lane_id_dbg)
                invalid_lane_list.append(idx)
                continue
            x_road_vals[idx] = np.concatenate(x_road_vals[idx])
            y_road_vals[idx] = np.concatenate(y_road_vals[idx])
            z_road_vals[idx] = np.concatenate(z_road_vals[idx])
            lanes_json[idx]["coordinate"] = list(zip(x_road_vals[idx].tolist(), y_road_vals[idx].tolist(), z_road_vals[idx].tolist()))
            # debug
            if DEBUG:
                x_values.append(x_road_vals[idx])
                y_values.append(y_road_vals[idx])
        # delete invalid lane
        for idx in sorted(invalid_lane_list, reverse=True):
            del lanes_json[idx]

        # link
        links = {}
        if link_root is not None:
            for link_child in link_root:
                link_json = {}
                link_child_tag = link_child.tag
                element_type = link_child.get('elementType')
                junction_id = link_child.get('elementId')
                if element_type =="road":
                    for lane_section_element in lane_sections_root:
                        for lane_group in lane_section_element:
                            for lane in lane_group:
                                lane_id = lane.get('id')
                                lane_link = lane.find('link')
                                lane_to = None
                                if lane_link is None:
                                    continue
                                lane_link_tag = lane_link.find(link_child_tag)
                                if lane_link_tag is None:
                                    continue
                                lane_to = lane_link_tag.get('id')
                                
                                if lane_id not in link_json:
                                    link_json[lane_id] = []
                                link_json[lane_id].append([junction_id, lane_to])

                elif element_type == "junction":
                    junction = junctions_dict[junction_id]
                    if link_child_tag == "successor":
                        # connected roads
                        for connection in junction.findall('connection'):
                            if road_id != connection.get('incomingRoad'):
                                continue
                            connect_road_id = connection.get('connectingRoad')
                            # Which lanes are connected
                            for lane_link in connection.findall('laneLink'):
                                lane_from = lane_link.get('from') 
                                if lane_from not in link_json:
                                    link_json[lane_from] = []
                                link_json[lane_from].append([connect_road_id, lane_link.get('to')])
                    # predecessor
                    else:
                        for connection in junction.findall('connection'):
                            connect_road_id = connection.get('connectingRoad')
                            predecessor_road = root.find(f".//road[@id='{connect_road_id}']")
                            if predecessor_road is None:
                                continue
                            predecessor_lane_section = predecessor_road.find('lanes').findall('laneSection')
                            for lane_group in predecessor_lane_section:
                                for lane in lane_group:
                                    lane_id = lane.get('id')
                                    lane_link = lane.find('link')
                                    lane_own = None
                                    if lane_link is None:
                                        continue
                                    # successor for the lane information want to connect to.
                                    lane_link_tag = lane_link.find('successor')
                                    lane_own = lane_link_tag.get('id')
                                    
                                    if lane_own not in link_json:
                                        link_json[lane_own] = []
                                    link_json[lane_own].append([connect_road_id, lane_id])

                else:
                    logger.warning("not implemented type: %s", element_type)
                links[link_child_tag] = link_json

        road_json = {
            "name": road_name,
            "id": road_id,
            "length": float(road_length),
            "junction": road_junction,
            "links": links,
            "lanes": lanes_json
        }
        roads_json.append(road_json)
    
    data = {
        "EPSG": epsg_code,
        "map_offset": [float(i) for i in map_offset],
        "roads": roads_json,
    }

    # debug
    if DEBUG:
        plotall_roaddata(x_values, y_values, "all")

    return data
        

# debug function
def plot_data(values, name=''):
    # Plot the x and y values
    plt.plot(range(0, len(values)), values)
    plt.title('Road Geometric Shape')
    plt.xlabel('X')
    plt.ylabel('Y')
    # plt.show()
    plt.savefig('figure_single' + name + '.png')

def plot_roaddata(x_values, y_values, name=''):
    # Plot the x and y values
    plt.plot(x_values, y_values)
    plt.title('Road Geometric Shape')
    plt.xlabel('X')
    plt.ylabel('Y')
    # plt.show()
    plt.savefig('figure_' + name + '.png')

def plotall_roaddata(x_values, y_values, name='all'):
    for idx in range(0, len(x_values)):
        plt.plot(x_values[idx], y_values[idx], label=f'Line {idx+1}')
    plt.title('Road Geometric Shape')
    plt.xlabel('X')
    plt.ylabel('Y')
    # plt.legend()
    plt.grid(True)
    plt.savefig('figure_' + name + '.png')

if __name__ == "__main__":
    main()