import os
import re
import json
import logging
import pandas as pd
import argparse
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

logger = logging.getLogger(__name__)

from scenario_util import create_initialize_entity, extract_number_from_filename, set_action_value,\
                        get_current_event_id, find_object_id, save_xml_data, get_route_csv_files


# launch.json
# {
#     "name": "route2event.py",
#     "type": "debugpy",
#     "request": "launch",
#     "program": "try_bravs/tool/scenario/route2event.py",
#     "console": "integratedTerminal",
#     "args": [
#         "--scenario_xml_file","scenario.xml",
#         "--car_routes_dir","try_bravs/divp/no18/infer"
#     ]
# }

ROUTE_CSV_ELEMENT = '''
<csvFile file="{}">
    <column dataType="double" headerName="timestamp" result="simulationTime"/>
    <column dataType="double" headerName="pos_x" result="positionX"/>
    <column dataType="double" headerName="pos_y" result="positionY"/>
    <column dataType="double" headerName="pos_z" result="positionZ"/>
    <column dataType="double" headerName="yaw_rad" result="attitudeZ"/>
    <column dataType="double" headerName="pitch_rad" result="attitudeY"/>
    <column dataType="double" headerName="roll_rad" result="attitudeX"/>
    <column dataType="double" headerName="vel_x" result="velocityX"/>
    <column dataType="double" headerName="vel_y" result="velocityY"/>
    <column dataType="double" headerName="vel_z" result="velocityZ"/>
    <column dataType="double" headerName="a_vel_yaw_rad" result="angularVelocityZ"/>
    <column dataType="double" headerName="a_vel_pitch_rad" result="angularVelocityY"/>
    <column dataType="double" headerName="a_vel_roll_rad" result="angularVelocityX"/>
    <column dataType="double" headerName="acc_x" result="accelerationX"/>
    <column dataType="double" headerName="acc_y" result="accelerationY"/>
    <column dataType="double" headerName="acc_z" result="accelerationZ"/>
    <column dataType="double" headerName="a_acc_yaw_rad" result="angularAccelerationZ"/>
    <column dataType="double" headerName="a_acc_pitch_rad" result="angularAccelerationY"/>
    <column dataType="double" headerName="a_acc_roll_rad" result="angularAccelerationX"/>
    <column dataType="uint64_t" headerName="head_light" result="head_light"/>
    <column dataType="uint64_t" headerName="fog_light" result="fog_light"/>
    <column dataType="uint64_t" headerName="turn_signal" result="turn_signal"/>
    <column dataType="uint64_t" headerName="brake_light" result="brake_light"/>
    <column dataType="uint64_t" headerName="back_light" result="back_light"/>
    <column dataType="uint64_t" headerName="other_light" result="other_light"/>
    <column dataType="uint64_t" headerName="custom_light_a" result="custom_light_a"/>
    <column dataType="uint64_t" headerName="custom_light_b" result="custom_light_b"/>
    <column dataType="uint64_t" headerName="custom_light_c" result="custom_light_c"/>
    <column dataType="uint64_t" headerName="custom_light_d" result="custom_light_d"/>
    <column dataType="uint64_t" headerName="custom_light_e" result="custom_light_e"/>
    <column dataType="uint64_t" headerName="custom_light_f" result="custom_light_f"/>
    <column dataType="uint64_t" headerName="custom_light_g" result="custom_light_g"/>
    <column dataType="uint64_t" headerName="custom_light_h" result="custom_light_h"/>
    <column dataType="uint64_t" headerName="front_wiper" result="front_wiper"/>
    <column dataType="uint64_t" headerName="rear_wiper" result="rear_wiper"/>
</csvFile>
'''

def extract_number_from_actor_name(actor_name):
    if "self" in actor_name:
        return "self"
    else:
        match = re.search(r'_(\d+)+', actor_name)
        if match:
            return match.group(1)
    return None


def main():
    parser = argparse.ArgumentParser(description="対象の相対座標の計算")
    parser.add_argument(
        "--scenario_xml_file",
        type=str,
        required=True,
        help="初期化したシナリオxmlファイル",
    )
    parser.add_argument(
        "--xosc_config_json",
        type=str,
        required=True,
        help="相対距離推定結果jsonファイルパス",
    )
    parser.add_argument(
        "--car_routes_dir",
        type=str,
        required=True,
        help="csv出力した車の経路が格納されているディレクトリ",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="output directory",
    )
    parser.add_argument(
        "--prefer_extended",
        action="store_true",
        default=True,
        help="_extended.csvがあればそれを優先する（デフォルト: True）",
    )
    parser.add_argument(
        "--no_prefer_extended",
        action="store_true",
        help="元のCSVを優先する（_extended.csvは使用しない）",
    )

    args = parser.parse_args()
    # --no_prefer_extended が指定された場合は prefer_extended を False に
    if args.no_prefer_extended:
        args.prefer_extended = False
    scenario_xml_file = args.scenario_xml_file
    assert isinstance(scenario_xml_file, str)
    xosc_config_json = args.xosc_config_json
    assert isinstance(xosc_config_json, str)
    car_routes_dir = args.car_routes_dir
    assert isinstance(car_routes_dir, str)
    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    car_route_files = get_route_csv_files(car_routes_dir, prefer_extended=args.prefer_extended)

    # read OpenScenario config file
    xosc_data_dict = {}
    with open(xosc_config_json, mode='r', encoding='utf-8') as f:
        xosc_data_dict = json.load(f)

    tree = ET.parse(scenario_xml_file)
    root = tree.getroot()
    map = root.find('space').find('maps').find('map')
    scenario_root = root.find('scenarios').find('concreteScenarios').find('concreteScenario')
    initialize_event = scenario_root.find('initialization')

    event_id = get_current_event_id(initialize_event)
    routes = map.find('routes')
    if routes is None:
        routes = ET.Element('routes')
        map.append(routes)
    
    for route_file in car_route_files:
        if not os.path.exists(route_file):
            logger.warning("not exists file: %s", route_file)
            continue
        route_file_name = os.path.basename(route_file)
        file_tag = extract_number_from_filename(route_file_name)
        if file_tag is None:
            logger.warning("not contain tag. filename: %s", route_file)
            continue

        # set csv route
        route_id = "route_" + file_tag
        route = ET.SubElement(routes, 'route', id=route_id, laneType='', type="csvFile")
        route_csv_element = ET.fromstring(ROUTE_CSV_ELEMENT)
        route_csv_element.set('file', route_file_name)
        route.append(route_csv_element)
        
        # read route data
        route_data = pd.read_csv(route_file)
        route_data_first = route_data.iloc[0]

        # add object event
        object_id = find_object_id(root, file_tag)
        if object_id is None:
            continue
        obj_init_entity = create_initialize_entity(object_id, event_id, route_id)

        # set initialize value
        set_action_value(obj_init_entity, "position",
                        route_data_first['pos_x'], route_data_first['pos_y'], route_data_first['pos_z'])
        set_action_value(obj_init_entity, "attitude",
                        route_data_first['roll_rad'], route_data_first['pitch_rad'], route_data_first['yaw_rad'])
        
        initialize_event.append(obj_init_entity)
        event_id += 1

        # OpenScenario configデータへのcsvファイル登録
        for actor in xosc_data_dict["actors"]:
            name_tag = extract_number_from_actor_name(actor["name"])
            if name_tag == file_tag:
                actor["csv_file"] = route_file
                break
            
    # 修正されたXMLデータをファイルに保存
    scenario_way_xml = os.path.splitext(scenario_xml_file)[0] + "_csv.xml"
    scenario_csv_path = os.path.join(output_dir, os.path.basename(scenario_way_xml))
    save_xml_data(root, scenario_csv_path)

    # OpenScenario configデータ出力
    with open(xosc_config_json, "w", encoding="utf-8") as f:
        json.dump(xosc_data_dict, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
