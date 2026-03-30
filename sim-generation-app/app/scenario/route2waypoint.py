import xml.etree.ElementTree as ET
import pandas as pd
import argparse
import os
import math
import logging

logger = logging.getLogger(__name__)

from scenario_util import create_initialize_entity, create_execution_entity, set_action_value,\
                        get_current_event_id, find_object_id, get_current_action_id,\
                        extract_number_from_filename, save_xml_data, get_route_csv_files

def main():
    parser = argparse.ArgumentParser(description="対象の相対座標の計算")
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
        "--output_dir",
        type=str,
        required=True,
        help="output directory",
    )
    parser.add_argument(
        "--time_threshold",
        type=float,
        default=0.5,
        help="イベントとして追加しない時間のしきい値",
    )
    parser.add_argument(
        "--vel_threshold",
        type=int,
        default=3,
        help="イベントとして追加しない速度のしきい値",
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
    output_dir = args.output_dir
    assert isinstance(output_dir, str)
    time_threshold = args.time_threshold
    assert isinstance(time_threshold, float)
    vel_threshold = args.vel_threshold
    assert isinstance(vel_threshold, int)

    car_route_files = get_route_csv_files(car_routes_dir, prefer_extended=args.prefer_extended)

    tree = ET.parse(scenario_xml_file)
    root = tree.getroot()
    map = root.find('space').find('maps').find('map')
    scenario_root = root.find('scenarios').find('concreteScenarios').find('concreteScenario')
    initialize_event = scenario_root.find('initialization')
    execution_event = scenario_root.find('execution')
    if execution_event is None:
        execution_event =ET.Element('execution')
        scenario_root.append(execution_event)

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
        route_id = "route_" + file_tag
        route = ET.SubElement(routes, 'route', id=route_id, laneType='driving', shape='bezier', type='waypoint')
        # read route data
        route_data = pd.read_csv(route_file)
        route_data_first = route_data.iloc[0]
        route_data_timestamp = route_data['timestamp'].values
        route_data_pos_x = route_data['pos_x'].values
        route_data_pos_y = route_data['pos_y'].values
        route_data_pos_z = route_data['pos_z'].values
        route_data_source = route_data['source'].values
        if len(route_data_pos_x) != len(route_data_pos_y):
            logger.warning("Invalid route data. file: %s", route_file)
            continue

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
        
        prev_vel = None
        initialize_speed_flg = (route_data_first['timestamp'] == 0.000)
        if initialize_speed_flg:
            obj_event = obj_init_entity.find(f".//event[@id='event_{event_id}']")
            if obj_event is not None:
                action_id = get_current_action_id(obj_init_entity)
                x = route_data_first['vel_x']
                y = route_data_first['vel_y']
                vel = math.sqrt(x**2 + y**2)
                # set value is speed divided by 3.6
                event_vel = vel / 3.6
                action_speed = ET.fromstring(
                    f'''
                    <action index="{action_id}">
                        <speed value="{event_vel}"/>
                    </action>
                    '''
                )
                obj_event.append(action_speed)
                prev_vel = vel

        initialize_event.append(obj_init_entity)
        event_id += 1

        obj_execution_entity = None
        event_index = 0
        prev_timestamp = -time_threshold
        prev_vel_timestamp = 0.0
        prev_pos_x = 0.0
        prev_pos_y = 0.0
        prev_source = route_data_source[0] if initialize_speed_flg else ""
        for i in range(len(route_data_pos_x)):
            current_timestamp = route_data_timestamp[i]
            if current_timestamp - prev_timestamp < time_threshold:
                continue
            x = route_data_pos_x[i]
            y = route_data_pos_y[i]
            if x == 0.0 and y == 0.0:
                continue
            if prev_pos_x == x and prev_pos_y == y:
                continue
            z = route_data_pos_z[i]
            # end side point
            if i == 0:
                ex = ey = 0
            else:
                dx = x - route_data_pos_x[i-1]
                dy = y - route_data_pos_y[i-1]
                ex = x - dx / 3
                ey = y - dy / 3
            # start side point
            if i == len(route_data_pos_x) - 1:
                sx = sy = 0
            else:
                dx = route_data_pos_x[i+1] - x
                dy = route_data_pos_y[i+1] - y
                sx = x + dx / 3
                sy = y + dy / 3

            waypoint = ET.Element('waypoint', {
                'ex': str(ex), 'ey': str(ey), 'ez': str(z),                     # end側のベジェ点
                'index': str(i), 'sx': str(sx), 'sy': str(sy), 'sz': str(z),    # start側のベジェ点
                'x': str(x), 'y': str(y), 'z': str(z)                           # 実際の点
            })
            route.append(waypoint)

            # distance and time
            movement_time = current_timestamp - prev_timestamp
            movement_distance = math.sqrt(
                math.pow(route_data_pos_x[i]-prev_pos_x, 2)
                + math.pow(route_data_pos_y[i]-prev_pos_y, 2)
            )
            
            # update previous data
            prev_timestamp = current_timestamp
            prev_pos_x = x
            prev_pos_y = y

            if i == 0 and initialize_speed_flg:
                continue

            # vel_x = route_data_vel_x[i]
            # vel_y = route_data_vel_y[i]
            # vel = math.sqrt(vel_x**2 + vel_y**2)
            vel = (movement_distance / movement_time) * 3.6
            # set value is speed divided by 3.6(convert km/h -> m/s)
            event_vel = vel / 3.6
            
            if prev_vel is not None:
                # 速度の誤差が少ない場合はイベントに追加しない
                if prev_vel - vel_threshold < vel < prev_vel + vel_threshold:
                    continue
            
            if obj_execution_entity is None:
                obj_execution_entity = create_execution_entity(object_id, event_id, event_index)
                entity_event = obj_execution_entity.find('event')
                event_id += 1
            else:
                entity_event = ET.SubElement(obj_execution_entity, 'event', id=f'event_{event_id}', index=str(event_index))
                event_id += 1
            
            # event start time
            event_start_time = 0
            if not (prev_source == "interpolated" or prev_source == "normal"):
                event_start_time = current_timestamp
                event_start_time = current_timestamp - 0.5 if current_timestamp > 1 else current_timestamp
            else:
                event_start_time = prev_vel_timestamp
            stopwatch_et = ET.fromstring(
                f'''
                <startCondition delay="0.0000000000" edge="none" index="0">
                    <stopwatch id="" operator="&gt;=" type="simulation" value="{event_start_time}"/>
                </startCondition>
                '''
            )
            entity_event.append(stopwatch_et)

            # target speed event
            elapsed_time = current_timestamp - event_start_time
            action_speed = ET.fromstring(
                f'''
                <action index="1">
                    <targetSpeed continuous="true" type="absolute" value="{event_vel}">
                        <transitionDynamics dimension="time" s="{elapsed_time}" shape="linear"/>
                    </targetSpeed>
                </action>
                '''
            )
            
            entity_event.append(action_speed)
            prev_vel = vel
            prev_vel_timestamp = current_timestamp
            prev_source = route_data_source[i]

        if obj_execution_entity is not None:
            execution_event.append(obj_execution_entity)
            
    # 修正されたXMLデータをファイルに保存
    scenario_way_xml = os.path.splitext(scenario_xml_file)[0] + "_waypoint.xml"
    scenario_csv_path = os.path.join(output_dir, os.path.basename(scenario_way_xml))
    save_xml_data(root, scenario_csv_path)

if __name__ == "__main__":
    main()



