import os
import logging
import pandas as pd
import argparse

from scenario_util import extract_number_from_filename, get_route_csv_files

logger = logging.getLogger(__name__)

DIVP_ROUTE_CSV_HEADER = [
    "timestamp",
    "pos_x", "pos_y", "pos_z",
    "yaw_rad", "roll_rad", "pitch_rad",
    "vel_x", "vel_y", "vel_z",
    "a_vel_yaw_rad", "a_vel_pitch_rad", "a_vel_roll_rad",
    "acc_x", "acc_y", "acc_z",
    "a_acc_yaw_rad", "a_acc_pitch_rad", "a_acc_roll_rad",
    "head_light", "fog_light", "turn_signal",
    "brake_light", "back_light", "other_light",
    "custom_light_a", "custom_light_b", "custom_light_c", "custom_light_d",
    "custom_light_e", "custom_light_f", "custom_light_g", "custom_light_h",
    "front_wiper", "rear_wiper"
]
FLOAT_HEADER = [
    "a_vel_yaw_rad", "a_vel_pitch_rad", "a_vel_roll_rad",
    "acc_x", "acc_y", "acc_z",
    "a_acc_yaw_rad", "a_acc_pitch_rad", "a_acc_roll_rad"
]

def convert_car_route_to_divp(car_routes_dir, environment, output_dir, prefer_extended=True):
    # change configuration according to environment
    head_light = 1
    front_wiper = 1
    rear_wiper = 1
    if environment == 2: # rainy
        front_wiper = 2 # lo
        rear_wiper = 2
    elif environment == 3:
        head_light = 4 # hi

    car_route_files = get_route_csv_files(car_routes_dir, prefer_extended=prefer_extended)
    self_route_file = [f for f in car_route_files if "self" in f]
    if len(self_route_file) > 0:
        self_route_data = pd.read_csv(self_route_file[0])
        self_route_data_length = len(self_route_data)

    for route_file in car_route_files:
        if not os.path.exists(route_file):
            logger.warning("not exists file: %s", route_file)
            continue
        file_tag = extract_number_from_filename(os.path.basename(route_file))
        if file_tag is None:
            logger.warning("not contain tag. filename: %s", route_file)
            continue
        
        # read route data
        route_data = pd.read_csv(route_file)
        route_data_length = len(route_data)

        # data length check
        if self_route_data_length != route_data_length:
            logger.warning("route data length is different from self route data length: %s", route_file)
            continue

        # add columns
        for idx in range(len(DIVP_ROUTE_CSV_HEADER)):
            header = DIVP_ROUTE_CSV_HEADER[idx]
            if header not in route_data.columns:
                route_data[header] = 0
            if header in FLOAT_HEADER:
                route_data[header] = route_data[header].astype(float)

        # set first of timestamp to zero
        first_timestamp = route_data.loc[0, 'timestamp']
        route_data['timestamp'] = route_data['timestamp'] - first_timestamp

        for i in range(len(route_data)):
            current_timestamp = route_data.loc[i, "timestamp"]
            current_vel_x = route_data.loc[i, "vel_x"]
            current_vel_y = route_data.loc[i, "vel_y"]
            current_yaw_rad = route_data.loc[i, "yaw_rad"]
            current_roll_rad = route_data.loc[i, "roll_rad"]
            current_pitch_rad = route_data.loc[i, "pitch_rad"]
            # last data same before
            if i != len(route_data) - 1:
                dist_timestamp = route_data.loc[i+1, "timestamp"]
                delta_t = dist_timestamp - current_timestamp
                # acceleration
                dist_vel_x = route_data.loc[i+1, "vel_x"]
                dist_vel_y = route_data.loc[i+1, "vel_y"]
                acc_x = (dist_vel_x - current_vel_x) / delta_t
                acc_y = (dist_vel_y - current_vel_y) / delta_t
                route_data.at[i, 'acc_x'] = acc_x
                route_data.at[i, 'acc_y'] = acc_y
                # angular velocity
                dist_yaw_rad = route_data.loc[i+1, "yaw_rad"]
                dist_roll_rad = route_data.loc[i+1, "roll_rad"]
                dist_pitch_rad = route_data.loc[i+1, "pitch_rad"]
                a_vel_yaw_rad = (dist_yaw_rad - current_yaw_rad) / delta_t
                a_vel_roll_rad = (dist_roll_rad - current_roll_rad) / delta_t
                a_vel_pitch_rad = (dist_pitch_rad - current_pitch_rad) / delta_t
                route_data.at[i, 'a_vel_yaw_rad'] = a_vel_yaw_rad
                route_data.at[i, 'a_vel_roll_rad'] = a_vel_roll_rad
                route_data.at[i, 'a_vel_pitch_rad'] = a_vel_pitch_rad

            # configuration
            route_data.at[i, 'head_light'] = head_light
            route_data.at[i, 'front_wiper'] = front_wiper
            route_data.at[i, 'rear_wiper'] = rear_wiper
            
            # angular acceleration
            if i == 0: # next angular velocity not available
                continue
            src_a_vel_yaw_rad = route_data.loc[i-1, "a_vel_yaw_rad"]
            src_a_vel_roll_rad = route_data.loc[i-1, "a_vel_roll_rad"]
            src_a_vel_pitch_rad = route_data.loc[i-1, "a_vel_pitch_rad"]
            a_acc_yaw_rad = (a_vel_yaw_rad - src_a_vel_yaw_rad) / delta_t
            a_acc_roll_rad = (a_vel_roll_rad - src_a_vel_roll_rad) / delta_t
            a_acc_pitch_rad = (a_vel_pitch_rad - src_a_vel_pitch_rad) / delta_t
            route_data.at[i, 'a_acc_yaw_rad'] = a_acc_yaw_rad
            route_data.at[i, 'a_acc_roll_rad'] = a_acc_roll_rad
            route_data.at[i, 'a_acc_pitch_rad'] = a_acc_pitch_rad
        
        # output file
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        divp_route_file = os.path.splitext(os.path.basename(route_file))[0] + "_divp.csv"
        divp_route_path = os.path.join(output_dir, divp_route_file)

        route_data.to_csv(divp_route_path, index=False, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description="対象の相対座標の計算")
    parser.add_argument(
        "--car_routes_dir",
        type=str,
        required=True,
        help="csv出力した車の経路が格納されているディレクトリ",
    )
    parser.add_argument(
        "--environment",
        type=int,
        default=0,
        help="環境情報(0:sunny, 1:cloudy, 2:rainy, 3:night)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="/simulation",
        help="出力ディレクトリ",
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
    car_routes_dir = args.car_routes_dir
    assert isinstance(car_routes_dir, str)

    environment = args.environment
    assert isinstance(environment, int)

    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    convert_car_route_to_divp(car_routes_dir, environment, output_dir, prefer_extended=args.prefer_extended)

if __name__ == "__main__":
    main()