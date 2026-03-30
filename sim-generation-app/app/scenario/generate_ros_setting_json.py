import os
import math
import json
import pandas as pd
import argparse

def main():
    parser = argparse.ArgumentParser(description="相対距離推定結果jsonファイルCSV変換")
    parser.add_argument(
        "--divp_route_csv_file",
        type=str,
        required=True,
        help="",
    )
    parser.add_argument(
        "--base_setting_json",
        type=str,
        required=True,
        help="出力先ディレクトリ",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="出力先ディレクトリ",
    )
    parser.add_argument(
        "--camera_fps",
        type=int,
        required=False,
        default=3,
        help="出力先ディレクトリ",
    )

    args = parser.parse_args()
    divp_route_csv_file = args.divp_route_csv_file
    assert isinstance(divp_route_csv_file, str)

    base_setting_json = args.base_setting_json
    assert isinstance(base_setting_json, str)

    output_path = args.output_path
    assert isinstance(output_path, str)

    camera_fps = args.camera_fps
    assert isinstance(camera_fps, int)

    # load xodr json file
    setting_data = {}
    with open(base_setting_json, "r", encoding="utf-8") as f:
        setting_data = json.load(f)
    
    # set camera fps
    if setting_data['camera'][0]['rendering']['fps'] != camera_fps:
        setting_data['camera'][0]['rendering']['fps'] = camera_fps
        setting_data['camera'][0]['perception']['fps'] = camera_fps

    # set end time
    divp_route_df = pd.read_csv(divp_route_csv_file)
    route_end_time = divp_route_df.loc[divp_route_df.index[-1], "timestamp"]
    setting_data['scenario_end_time']['end_time'] = math.ceil(route_end_time)

    # dump json
    output_file_path = os.path.join(output_path, "setting.json")
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(setting_data, f, ensure_ascii=False, indent=2)
            

if __name__ == "__main__":
    main()