import os
import re
import json
import logging
import argparse
import shutil
import pandas as pd
import copy
import xml.etree.ElementTree as ET

from scenario_util import save_xml_data

logger = logging.getLogger(__name__)

def extract_frame(image_name):
    match = re.search(r'_(\d{5})', image_name)
    if match:
        return int(match.group(1))
    return None

# launch.json
# {
#     "name": "scenario_xml_initialize.py",
#     "type": "debugpy",
#     "request": "launch",
#     "program": "try_bravs/scenario/scenario_xml_initialize.py",
#     "console": "integratedTerminal",
#      "args": [
#         "--abs_coord_file","try_bravs/divp/no18/infer/detection_distance_result_abs_coord.json",
#         "--base_scenario_xml","try_bravs/scenario/data/base_scenario.xml",
#         "--car_data_xml","try_bravs/scenario/data/car_object_data.xml"
#         "--output_dir","./"
#     ]
# }

def main():
    parser = argparse.ArgumentParser(description="対象の相対座標の計算")
    parser.add_argument(
        "--base_scenario_xml",
        type=str,
        required=True,
        help="相対距離推定結果jsonファイルパス",
    )
    parser.add_argument(
        "--car_data_xml",
        type=str,
        required=True,
        help="objectの初期データ（ファイル固定）",
    )
    parser.add_argument(
        "--xosc_actor_json",
        type=str,
        required=False,
        default="./data/base_actor_data.json",
        help="objectの初期データ（ファイル固定）",
    )
    parser.add_argument(
        "--abs_coord_file",
        type=str,
        required=True,
        help="自車と検出車の絶対座標のjsonファイルパス",
    )    
    parser.add_argument(
        "--output_dir",
        type=str,
        # required=True,
        default="./",
        help="出力ディレクトリパス",
    )
    
    args = parser.parse_args()
    base_scenario_xml = args.base_scenario_xml
    assert isinstance(base_scenario_xml, str)
    car_data_xml = args.car_data_xml
    assert isinstance(car_data_xml, str)
    xosc_actor_json = args.xosc_actor_json
    assert isinstance(xosc_actor_json, str)
    abs_coord_file = args.abs_coord_file
    assert isinstance(abs_coord_file, str)
    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    # scenario file initialize
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    scenario_file = os.path.join(output_dir, "scenario.xml")
    shutil.copy(base_scenario_xml, scenario_file)
    
    tree = ET.parse(scenario_file)
    scenario_root = tree.getroot()
    scenario_objects = scenario_root.find('space').find('objects')

    tree = ET.parse(car_data_xml)
    car_data_root = tree.getroot()
    car_obj_dict = {}
    for car_data in car_data_root.findall('object'):
        car_type = car_data.get('subtype')
        car_obj_dict[car_type] = car_data

    # OpenScenario config
    xosc_config_json = {
        "actors":[
            {
                "csv_file": "",
                "name": "divp_Veh_HinoProfia_self",
                "vehicleCategory": "bus",
                "model3d": "asset\\divp_Veh_HinoProfia.fbx",
                "boundingBox": {
                    "center": {
                        "x": 2.536,
                        "y": 0.0,
                        "z": 1.849
                    },
                    "dimensions": {
                        "width": 3.698,
                        "length": 11.87,
                        "height": 2.564
                    }
                }
            }
        ]
    }

    # OpenScenario actorデータ読込
    actor_data_dict = {}
    xosc_actor_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), xosc_actor_json)
    with open(xosc_actor_json_path, mode='r', encoding='utf-8') as f:
        actor_data_dict = json.load(f)

    if os.path.exists(abs_coord_file) == False:
        det_abs_coord_result = {
            "results": []
        }
    else:
        # add object
        with open(abs_coord_file, mode='r', encoding='utf-8') as f:
            det_abs_coord_result = json.load(f)


    # オブジェクト
    for item in det_abs_coord_result['results']:
        frame = item['frame']

        # other
        for i, detect in enumerate(item['detections']):
            obj_id = detect['obj_id']
            world_coordinate = detect.get('world_coordinate')
            if world_coordinate is None:
                continue

            obj_label_class = detect['vehicle_type']

            obj_element = None
            actor_data = None
            if obj_label_class == 'Truck' or obj_label_class == 'bus':
                obj_element = copy.deepcopy(car_obj_dict['bus'])
                actor_data = copy.deepcopy(actor_data_dict['truck'])
            elif obj_label_class == 'Car' or obj_label_class == 'bus':
                obj_element = copy.deepcopy(car_obj_dict['car'])
                actor_data = copy.deepcopy(actor_data_dict['car'])
            elif obj_label_class == 'Van':
                obj_element = copy.deepcopy(car_obj_dict['car'])
                actor_data = copy.deepcopy(actor_data_dict['car'])
            else:
                logger.warning("class_name : %s", obj_label_class)
                continue
            
            scenario_obj_id = obj_element.get('id') + f'_{obj_id}'
            
            # 既に登録済みか確認
            is_appended = False
            for s_object in scenario_objects.findall(".//object"):
                if str(obj_id) in s_object.get('id'):
                    is_appended = True
                    break
                
            if is_appended:
                continue
            
            obj_element.set('id', scenario_obj_id)
            scenario_objects.append(obj_element)

            # add actor data
            actor_data["name"] = scenario_obj_id
            xosc_config_json['actors'].append(actor_data)

    # 修正されたXMLデータをファイルに保存
    scenario_xml_file = os.path.join(output_dir, "scenario.xml")
    save_xml_data(scenario_root, scenario_xml_file)

    # OpenScenario configファイル出力
    output_file_path = os.path.join(output_dir, "xosc_config.json")
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(xosc_config_json, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
    