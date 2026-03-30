import os
import json
import logging
import argparse
import xml.etree.ElementTree as ET

from scenario_util import save_xml_data

logger = logging.getLogger(__name__)

def map_setup(map_info, xml_file, xosc_config_json):
    # read OpenScenario config file
    xosc_data_dict = {}
    with open(xosc_config_json, mode='r', encoding='utf-8') as f:
        xosc_data_dict = json.load(f)

    tree = ET.parse(xml_file)
    root = tree.getroot()
        
    map_root = root.find('space').find('maps').find('map')
    if map_root is None:
        logger.error("Incorrect xml file: %s", xml_file)
        return

    # set map and xodr
    model_file_fullpath = map_info["3dmapModel_path"]
    model_file_name = os.path.basename(model_file_fullpath)
    model_name = os.path.splitext(model_file_name)[0]
    model_object_elem = ET.fromstring(
        f'''
        <objects>
            <object id="{model_name}" type="town">
                <modelFile file="{model_file_name}"/>
                <position x="0.0000000000" y="0.0000000000" z="0.0000000000"/>
            </object>
        </objects>
        '''
    )
    map_root.append(model_object_elem)
    
    xodr_file_fullpath = map_info["opendrive_path"]
    xodr_file_name = os.path.basename(xodr_file_fullpath)
    xodr_object_elem = ET.fromstring(
        f'''
        <roadNetwork>
            <roadNetworkFile file="{xodr_file_name}" path="{xodr_file_fullpath}"/>
            <trafficSignals/>
        </roadNetwork>
        '''
    )
    map_root.append(xodr_object_elem)

    # xmlファイル保存
    save_xml_data(root, xml_file)

    # OpenScenario configにマップ追加
    xosc_data_dict['roadNetwork'] = {
        "logicFile": f"asset\\{xodr_file_name}",
        "sceneGraphFile": f"asset\\{model_file_name}"
    }

    # OpenScenario configファイル出力
    with open(xosc_config_json, "w", encoding="utf-8") as f:
        json.dump(xosc_data_dict, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(description="対象の相対座標の計算")
    parser.add_argument(
        "--scenario_xml_file",
        type=str,
        required=True,
        help="相対距離推定結果jsonファイルパス",
    )
    parser.add_argument(
        "--xosc_config_json",
        type=str,
        required=True,
        help="相対距離推定結果jsonファイルパス",
    )
    parser.add_argument(
        "--map_info_file",
        type=str,
        required=True,
        help="相対距離推定結果jsonファイルパス",
    )

    args = parser.parse_args()
    scenario_xml_file = args.scenario_xml_file
    assert isinstance(scenario_xml_file, str)
    xosc_config_json = args.xosc_config_json
    assert isinstance(xosc_config_json, str)
    map_info_file = args.map_info_file
    assert isinstance(map_info_file, str)

    # read data files
    map_info = {}
    with open(map_info_file, mode='r', encoding='utf-8') as f:
        map_info = json.load(f)

    map_setup(map_info, scenario_xml_file, xosc_config_json)

if __name__ == "__main__":
    main()