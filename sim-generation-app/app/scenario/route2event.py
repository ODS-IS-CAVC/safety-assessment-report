import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import pandas as pd
import argparse
import os
import re
import logging

logger = logging.getLogger(__name__)

from scenario_util import create_initialize_entity, set_action_value,\
                        get_current_event_id, find_object_id, get_route_csv_files

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

def extract_number_from_filename(filename):
    if "route" not in filename:
        return None
    
    if "self" in filename:
        return "self"
    else:
        match = re.search(r'_(\d+)+', filename)
        if match:
            return match.group(1)
    return None

def main():
    parser = argparse.ArgumentParser(description="測距したCSVデータをシナリオにルートやオブジェクトのイベントに追加")
    parser.add_argument(
        "--scenario_xml_file",
        type=str,
        required=True,
        help="初期化したシナリオxmlファイル",
    )
    parser.add_argument(
        "--car_routes_dir",
        type=str,
        required=True,
        help="csv出力した車の経路が格納されているディレクトリ",
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
    car_routes_dir = args.car_routes_dir
    assert isinstance(car_routes_dir, str)

    car_route_files = get_route_csv_files(car_routes_dir, prefer_extended=args.prefer_extended)

    tree = ET.parse(scenario_xml_file)
    root = tree.getroot()
    map = root.find('space').find('maps').find('map')
    initialize_event = root.find('scenarios').find('concreteScenarios').find('concreteScenario').find('initialization')
    event_id = get_current_event_id(initialize_event)

    routes = map.find('routes')
    if routes is None:
        routes = ET.Element('routes')
        map.append(routes)

    for route_file in car_route_files:
        if not os.path.exists(route_file):
            logger.warning("not exists file: %s", route_file)
            continue
        file_tag = extract_number_from_filename(os.path.basename(route_file))
        if file_tag is None:
            logger.warning("not contain tag. filename: %s", route_file)
            continue
        route_id = "route_csv_" + file_tag
        # add route tag
        route = ET.SubElement(routes, 'route', id=route_id, laneType='driving', type="csvFile")
        csv_route_element = ET.fromstring(
            '''
            <csvFile file="" path=".\\">
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
            </csvFile>
            '''
        )
        test = os.path.basename(route_file)
        logger.info("%s", test)
        csv_route_element.set('file', test)
        route.append(csv_route_element)

        # add object event
        object_id = find_object_id(root, file_tag)
        if object_id is None:
            continue
        obj_entity = create_initialize_entity(object_id, event_id, route_id)

        # set initialize value
        route_data_first = pd.read_csv(route_file).iloc[0]
        set_action_value(obj_entity, "position",
                         route_data_first['pos_x'], route_data_first['pos_y'], route_data_first['pos_z'])
        set_action_value(obj_entity, "attitude",
                         route_data_first['roll_rad'], route_data_first['pitch_rad'], route_data_first['yaw_rad'])
        
        initialize_event.append(obj_entity)
        event_id = event_id + 1
        

    # 修正されたXMLデータを文字列に変換
    new_xml_data = ET.tostring(root, encoding='unicode')
    reparsed = minidom.parseString(new_xml_data)
    pretty_string = reparsed.toprettyxml(indent="    ")
    pretty_string = "\n".join([line for line in pretty_string.split('\n') if line.strip()])

    # 修正されたXMLデータをファイルに保存
    scenario_csv_xml = os.path.splitext(scenario_xml_file)[0] + "_csvFile.xml"
    with open(scenario_csv_xml, "w", encoding='utf-8') as file:
        file.write(pretty_string)


if __name__ == "__main__":
    main()