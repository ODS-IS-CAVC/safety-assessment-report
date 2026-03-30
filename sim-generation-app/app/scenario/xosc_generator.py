import csv
import xml.dom.minidom
import xml.etree.ElementTree as ET
import os
import json
import argparse
import math
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


def load_config_from_json(json_file):
    """
    JSONファイルから車両設定とロードネットワーク設定を読み込む。

    Args:
        json_file (str): JSONファイルのパス

    Returns:
        tuple: (vehicles_config, road_network)
            - vehicles_config (dict): 車両設定の辞書
            - road_network (dict): ロードネットワーク設定

    Raises:
        ValueError: JSONファイルの形式が不正な場合

    Note:
        Expected JSON format:
    {
      "actors": [
        {
          "name": "ego_vehicle",
          "csv_file": "ego_trajectory.csv",
          "vehicleCategory": "car",
          "model3d": "vehicle.tesla.model3",
          "boundingBox": {
            "center": {
              "x": 1.5,
              "y": 0.0,
              "z": 0.9
            },
            "dimensions": {
              "width": 2.0,
              "length": 5.0,
              "height": 1.8
            }
          }
        },
        {
          "name": "vehicle_1",
          "csv_file": "vehicle1_trajectory.csv",
          "vehicleCategory": "truck",
          "model3d": "vehicle.toyota.hilux"
        }
      ],
      "roadNetwork": {
        "logicFile": "path/to/map.xodr",
        "sceneGraphFile": "path/to/map.osgb"
      }
    }
    """
    try:
        with open(json_file, 'r') as f:
            json_data = json.load(f)

        # JSON形式の検証
        if not isinstance(json_data, dict):
            raise ValueError("JSONファイルはオブジェクト形式である必要があります。")

        # actorsキーの存在確認 (vehiclesキーから変更)
        if "actors" not in json_data:
            raise ValueError("JSONファイルに 'actors' キーが存在しません。")

        if not isinstance(json_data["actors"], list):
            raise ValueError("'actors' は配列である必要があります。")

        # roadNetworkの取得（ない場合は空のディクショナリ）
        road_network = json_data.get(
            "roadNetwork", {"logicFile": "", "sceneGraphFile": ""})

        # 車両情報の処理 (actorsから取得)
        vehicles_config = {}
        for vehicle in json_data["actors"]:
            if not isinstance(vehicle, dict):
                raise ValueError("車両設定はオブジェクト形式である必要があります。")

            if "name" not in vehicle:
                raise ValueError("車両設定に 'name' キーがありません。")

            if "csv_file" not in vehicle:
                raise ValueError(
                    f"車両 '{vehicle['name']}' の設定に "
                    f"'csv_file' キーがありません。")

            vehicle_name = vehicle["name"]
            vehicles_config[vehicle_name] = vehicle

        return vehicles_config, road_network

    except Exception as e:
        logger.error("JSONファイルの読み込みに失敗しました: %s", e)
        return None, None


def rotate_coordinates(x, y, angle_deg):
    """
    座標を指定角度で回転変換する。

    2D座標を原点を中心に指定された角度だけ回転させる。

    Args:
        x (float): X座標
        y (float): Y座標
        angle_deg (float): 回転角度（度）。正の値で反時計回り

    Returns:
        tuple: (new_x, new_y)
            - new_x (float): 回転後のX座標
            - new_y (float): 回転後のY座標
    """
    angle_rad = np.deg2rad(angle_deg)
    cos_theta = np.cos(angle_rad)
    sin_theta = np.sin(angle_rad)

    new_x = cos_theta * x - sin_theta * y
    new_y = sin_theta * x + cos_theta * y

    return new_x, new_y


def _load_trajectory_data(vehicles_config, rotation_angle=0.0):
    """
    各車両のCSVファイルから軌跡データを読み込む。

    Args:
        vehicles_config (dict): 車両設定の辞書
        rotation_angle (float): 座標系の回転角度（度）

    Returns:
        dict: 車両データの辞書
    """
    # デフォルトのBoundingBox設定
    DEFAULT_BOUNDING_BOX = {
        'center_x': 1.5,
        'center_y': 0.0,
        'center_z': 0.9,
        'width': 2.0,
        'length': 5.0,
        'height': 1.8
    }

    vehicles_data = {}

    # 各車両のCSVファイルを読み込む
    for vehicle_name, config in vehicles_config.items():
        csv_file = config.get("csv_file")
        if not csv_file or not os.path.exists(csv_file):
            logger.warning(
                "警告: %s が見つかりません。"
                "車両 %s はスキップされます。", csv_file, vehicle_name)
            continue

        trajectory = []
        initial_speed = None

        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                # 元の座標を取得
                orig_x = float(row['pos_x'])
                orig_y = float(row['pos_y'])

                # 座標を回転変換
                if rotation_angle != 0.0:
                    rotated_x, rotated_y = rotate_coordinates(
                        orig_x, orig_y, rotation_angle)
                else:
                    rotated_x, rotated_y = orig_x, orig_y

                # yaw角度も同じ角度だけ回転
                orig_yaw = float(row.get('yaw_rad') or 0.0)
                if rotation_angle != 0.0:
                    adjusted_yaw = orig_yaw + np.deg2rad(rotation_angle)
                else:
                    adjusted_yaw = orig_yaw

                # 位置と姿勢の情報を取得
                point = {
                    'time': float(row['timestamp']),
                    'x': rotated_x,
                    'y': rotated_y,
                    'z': float(row.get('pos_z') or 0.0),
                    'h': adjusted_yaw,
                    'p': float(row.get('pitch_rad') or 0.0),
                    'r': float(row.get('roll_rad') or 0.0)
                }

                # 最初のポイントの速度を記録
                if i == 0:
                    # 速度情報の取得（存在する場合）
                    # 空文字列の場合も0.0を使用
                    orig_vel_x = float(row.get('vel_x') or 0.0)
                    orig_vel_y = float(row.get('vel_y') or 0.0)
                    vel_z = float(row.get('vel_z') or 0.0)

                    # 速度ベクトルも回転変換
                    if rotation_angle != 0.0:
                        vel_x, vel_y = rotate_coordinates(
                            orig_vel_x, orig_vel_y, rotation_angle)
                    else:
                        vel_x, vel_y = orig_vel_x, orig_vel_y

                    # 速度の大きさを計算
                    speed = math.sqrt(vel_x**2 + vel_y**2 + vel_z**2)
                    point['speed'] = speed
                    initial_speed = speed

                trajectory.append(point)

        # デフォルトの初期速度
        default_speed = 15.0 if vehicle_name == 'ego_vehicle' else 12.0

        # 車両の基本設定 (デフォルト値)
        vehicle_data = {
            'trajectory': trajectory,
            # JSONから'vehicleName'を取得、なければデフォルト'car'
            'type': config.get('vehicleName', 'car'),
            # JSONから'vehicleCategory'を取得
            'category': config.get('vehicleCategory', 'car'),
            'model3d': config.get('model3d', ''),  # JSONから'model3d'を取得
            # 計算した速度を使用
            'speed': initial_speed if initial_speed is not None
            else default_speed
        }

        # BoundingBoxの情報をデフォルト値で初期化
        for key, value in DEFAULT_BOUNDING_BOX.items():
            vehicle_data[key] = value

        # BoundingBoxの情報をJSONから取得 (ネストした形式)
        if 'boundingBox' in config:
            bb = config['boundingBox']
            # Center
            if 'center' in bb:
                center = bb['center']
                if 'x' in center:
                    vehicle_data['center_x'] = float(center['x'])
                if 'y' in center:
                    vehicle_data['center_y'] = float(center['y'])
                if 'z' in center:
                    vehicle_data['center_z'] = float(center['z'])

            # Dimensions
            if 'dimensions' in bb:
                dim = bb['dimensions']
                if 'width' in dim:
                    vehicle_data['width'] = float(dim['width'])
                if 'length' in dim:
                    vehicle_data['length'] = float(dim['length'])
                if 'height' in dim:
                    vehicle_data['height'] = float(dim['height'])

        # BoundingBoxの情報をJSONから取得 (フラット形式)
        if 'center_x' in config:
            vehicle_data['center_x'] = float(config['center_x'])
        if 'center_y' in config:
            vehicle_data['center_y'] = float(config['center_y'])
        if 'center_z' in config:
            vehicle_data['center_z'] = float(config['center_z'])
        if 'width' in config:
            vehicle_data['width'] = float(config['width'])
        if 'length' in config:
            vehicle_data['length'] = float(config['length'])
        if 'height' in config:
            vehicle_data['height'] = float(config['height'])

        # 速度設定をJSONから取得（あれば）
        if 'speed' in config:
            vehicle_data['speed'] = float(config['speed'])

        vehicles_data[vehicle_name] = vehicle_data

    return vehicles_data


def _create_file_header(root):
    """
    OpenSCENARIOのFileHeaderを作成する。

    Args:
        root: XMLルート要素
    """
    current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    file_header = ET.SubElement(root, "FileHeader")
    file_header.set("revMajor", "1")
    file_header.set("revMinor", "0")
    file_header.set("date", current_date)
    file_header.set("description", "")
    file_header.set("author", "Generated by Python Script")


def _create_road_network(root, road_network):
    """
    RoadNetwork要素を作成する。

    Args:
        root: XMLルート要素
        road_network (dict): ロードネットワーク設定
    """
    road_network_elem = ET.SubElement(root, "RoadNetwork")
    logic_file = ET.SubElement(road_network_elem, "LogicFile")
    logic_file.set("filepath", road_network.get("logicFile", ""))
    scene_graph_file = ET.SubElement(road_network_elem, "SceneGraphFile")
    scene_graph_file.set("filepath", road_network.get("sceneGraphFile", ""))


def _create_entities(root, vehicles_data):
    """
    Entities要素を作成する。

    Args:
        root: XMLルート要素
        vehicles_data (dict): 車両データの辞書
    """
    entities = ET.SubElement(root, "Entities")

    for vehicle_name, config in vehicles_data.items():
        # 車両オブジェクトの作成
        scenario_object = ET.SubElement(entities, "ScenarioObject")
        scenario_object.set("name", vehicle_name)

        vehicle = ET.SubElement(scenario_object, "Vehicle")
        vehicle.set("name", config['type'])
        vehicle.set("vehicleCategory", config['category'])
        if config['model3d']:  # model3dが指定されている場合のみ設定
            vehicle.set("model3d", config['model3d'])

        ET.SubElement(vehicle, "ParameterDeclarations")

        # Performanceの属性を全て1000.0に設定
        performance = ET.SubElement(vehicle, "Performance")
        performance.set("maxSpeed", "1000.0")
        performance.set("maxAcceleration", "1000.0")
        performance.set("maxDeceleration", "1000.0")

        # BoundingBoxの設定 - JSONから取得した値またはデフォルト値を使用
        bbox = ET.SubElement(vehicle, "BoundingBox")
        center = ET.SubElement(bbox, "Center")
        center.set("x", str(config['center_x']))
        center.set("y", str(config['center_y']))
        center.set("z", str(config['center_z']))

        dimensions = ET.SubElement(bbox, "Dimensions")
        dimensions.set("width", str(config['width']))
        dimensions.set("length", str(config['length']))
        dimensions.set("height", str(config['height']))

        # 車軸の定義 - 全ての値を0.0に設定
        axles = ET.SubElement(vehicle, "Axles")
        front_axle = ET.SubElement(axles, "FrontAxle")
        front_axle.set("maxSteering", "0.0")
        front_axle.set("wheelDiameter", "0.0")
        front_axle.set("trackWidth", "0.0")
        front_axle.set("positionX", "0.0")
        front_axle.set("positionZ", "0.0")

        rear_axle = ET.SubElement(axles, "RearAxle")
        rear_axle.set("maxSteering", "0.0")
        rear_axle.set("wheelDiameter", "0.0")
        rear_axle.set("trackWidth", "0.0")
        rear_axle.set("positionX", "0.0")
        rear_axle.set("positionZ", "0.0")

        # 空のプロパティ要素
        ET.SubElement(vehicle, "Properties")


def _create_init_actions(storyboard, vehicles_data):
    """
    Init内のActions要素を作成する。

    Args:
        storyboard: Storyboard要素
        vehicles_data (dict): 車両データの辞書
    """
    init = ET.SubElement(storyboard, "Init")
    actions = ET.SubElement(init, "Actions")

    for vehicle_name, config in vehicles_data.items():
        if not config['trajectory']:
            continue  # 軌跡データがない車両はスキップ

        private = ET.SubElement(actions, "Private")
        private.set("entityRef", vehicle_name)

        # 初期位置設定 (TeleportAction)
        first_point = config['trajectory'][0]
        teleport_pa = ET.SubElement(private, "PrivateAction")
        teleport_action = ET.SubElement(teleport_pa, "TeleportAction")
        position = ET.SubElement(teleport_action, "Position")
        world_pos = ET.SubElement(position, "WorldPosition")
        world_pos.set("x", str(first_point['x']))
        world_pos.set("y", str(first_point['y']))
        world_pos.set("z", str(first_point['z']))
        world_pos.set("h", str(first_point['h']))
        world_pos.set("p", str(first_point['p']))
        world_pos.set("r", str(first_point['r']))

        # 初期速度設定 - CSVから計算した速度を使用
        speed_pa = ET.SubElement(private, "PrivateAction")
        longitudinal = ET.SubElement(speed_pa, "LongitudinalAction")
        speed_action = ET.SubElement(longitudinal, "SpeedAction")

        dynamics = ET.SubElement(speed_action, "SpeedActionDynamics")
        dynamics.set("dynamicsShape", "step")
        dynamics.set("value", "0.0")
        dynamics.set("dynamicsDimension", "time")

        target = ET.SubElement(speed_action, "SpeedActionTarget")
        abs_target = ET.SubElement(target, "AbsoluteTargetSpeed")
        abs_target.set("value", str(config['speed']))

        # Init内では軌跡設定は含めない（動作確認済み版に合わせる）


def _create_maneuver_groups(act, vehicles_data):
    """
    ManeuverGroup要素を作成する。

    Args:
        act: Act要素
        vehicles_data (dict): 車両データの辞書
    """
    # 各車両のManeuverGroup
    for vehicle_name in vehicles_data.keys():
        if not vehicles_data[vehicle_name]['trajectory']:
            continue

        maneuver_group = ET.SubElement(act, "ManeuverGroup")
        maneuver_group.set("name", f"{vehicle_name}ManeuverGroup")
        maneuver_group.set("maximumExecutionCount", "1")

        actors = ET.SubElement(maneuver_group, "Actors")
        actors.set("selectTriggeringEntities", "false")
        ET.SubElement(actors, "EntityRef").set("entityRef", vehicle_name)

        # マニューバーとイベント構造を作成
        maneuver = ET.SubElement(maneuver_group, "Maneuver")
        maneuver.set("name", f"{vehicle_name}Maneuver")

        # Event要素を作成
        event = ET.SubElement(maneuver, "Event")
        event.set("name", "event_1")
        event.set("priority", "overwrite")

        # Action要素を作成
        action = ET.SubElement(event, "Action")
        action.set("name", "event_1_Action")

        # PrivateAction内にRoutingActionを作成
        private_action = ET.SubElement(action, "PrivateAction")
        routing_action = ET.SubElement(private_action, "RoutingAction")
        follow_trajectory = ET.SubElement(
            routing_action, "FollowTrajectoryAction")

        # TrajectoryFollowingMode
        traj_follow_mode = ET.SubElement(
            follow_trajectory, "TrajectoryFollowingMode")
        if vehicle_name == "target":
            traj_follow_mode.set("followingMode", "follow")
        else:
            traj_follow_mode.set("followingMode", "position")

        # Trajectory
        trajectory = ET.SubElement(follow_trajectory, "Trajectory")
        trajectory.set("name", f"{vehicle_name}Trajectory")
        trajectory.set("closed", "false")

        ET.SubElement(trajectory, "ParameterDeclarations")
        shape = ET.SubElement(trajectory, "Shape")
        polyline = ET.SubElement(shape, "Polyline")

        # CSV軌跡データからポリラインを作成
        for point in vehicles_data[vehicle_name]['trajectory']:
            vertex = ET.SubElement(polyline, "Vertex")
            vertex.set("time", str(point['time']))
            v_pos = ET.SubElement(vertex, "Position")
            v_world = ET.SubElement(v_pos, "WorldPosition")
            v_world.set("x", str(point['x']))
            v_world.set("y", str(point['y']))
            v_world.set("z", str(point['z']))
            v_world.set("h", str(point['h']))
            v_world.set("p", str(point['p']))
            v_world.set("r", str(point['r']))

        # TimeReference
        time_ref = ET.SubElement(follow_trajectory, "TimeReference")
        timing = ET.SubElement(time_ref, "Timing")
        timing.set("domainAbsoluteRelative", "absolute")
        timing.set("offset", "0.0")
        timing.set("scale", "1.0")


def _create_triggers(act, storyboard, vehicles_data):
    """
    StartTriggerとStopTriggerを作成する。

    Args:
        act: Act要素
        storyboard: Storyboard要素
        vehicles_data (dict): 車両データの辞書
    """
    # Act開始条件
    start_trigger = ET.SubElement(act, "StartTrigger")
    condition_group = ET.SubElement(start_trigger, "ConditionGroup")
    condition = ET.SubElement(condition_group, "Condition")
    condition.set("name", "ActStartCondition")
    condition.set("delay", "0")
    condition.set("conditionEdge", "rising")
    by_value = ET.SubElement(condition, "ByValueCondition")
    sim_time = ET.SubElement(by_value, "SimulationTimeCondition")
    sim_time.set("value", "0.0")
    sim_time.set("rule", "greaterThan")

    # シミュレーション終了条件
    stop_trigger = ET.SubElement(storyboard, "StopTrigger")
    stop_condition_group = ET.SubElement(stop_trigger, "ConditionGroup")
    stop_condition = ET.SubElement(stop_condition_group, "Condition")
    stop_condition.set("name", "StopCondition")
    stop_condition.set("delay", "0")
    stop_condition.set("conditionEdge", "rising")
    stop_by_value = ET.SubElement(stop_condition, "ByValueCondition")
    stop_sim_time = ET.SubElement(stop_by_value, "SimulationTimeCondition")

    # シミュレーション終了時間を自車両のタイムスタンプ最大値で設定
    max_time = 40.0  # デフォルト値
    ego_vehicle_time = None
    ego_vehicle_name = None

    # 自車両を特定：優先順位 1) "ego", 2) "_self"が含まれる車両, 3) 最初の車両
    for vehicle_name, config in vehicles_data.items():
        if config['trajectory']:
            if vehicle_name.lower() == "ego":
                ego_vehicle_time = config['trajectory'][-1]['time']
                ego_vehicle_name = vehicle_name
                break
            elif '_self' in vehicle_name.lower() and ego_vehicle_time is None:
                ego_vehicle_time = config['trajectory'][-1]['time']
                ego_vehicle_name = vehicle_name

    # 自車両が見つからない場合は最初の車両を使用
    if ego_vehicle_time is None:
        for vehicle_name, config in vehicles_data.items():
            if config['trajectory']:
                ego_vehicle_time = config['trajectory'][-1]['time']
                ego_vehicle_name = vehicle_name
                break

    # 自車両のタイムスタンプ最大値でシミュレーション終了時間を設定
    if ego_vehicle_time is not None:
        max_time = ego_vehicle_time
        logger.info("自車両（%s）のタイムスタンプ最大値で"
                    "シミュレーション終了時間を設定: %s秒", ego_vehicle_name, max_time)
    else:
        logger.warning(
            "自車両が見つからないため、デフォルト終了時間を使用: %s秒", max_time)

    stop_sim_time.set("value", str(max_time))
    stop_sim_time.set("rule", "greaterThan")


def generate_openscenario_from_csv(
        vehicles_config, road_network,
        output_file="generated_scenario.xosc", rotation_angle=0.0):
    """
    CSVファイルから新規のOpenSCENARIOファイルを生成する。

    複数の車両の軌跡データ（CSV形式）を読み込み、OpenSCENARIO 1.0形式の
    シナリオファイルを生成する。座標系の回転変換もサポート。

    Args:
        vehicles_config (dict): 車両設定の辞書
            キーは車両名、値は設定辞書
            例: {"ego_vehicle": {"csv_file": "ego_trajectory.csv",
                                "vehicleName": "car",
                                "vehicleCategory": "car",
                                "model3d": "vehicle.tesla.model3",
                                "boundingBox": {...}}}
        road_network (dict): ロードネットワーク設定
            - logicFile (str): OpenDRIVEファイルパス
            - sceneGraphFile (str): シーングラフファイルパス
        output_file (str, optional): 出力するOpenSCENARIOファイルのパス。
            デフォルトは "generated_scenario.xosc"
        rotation_angle (float, optional): 座標系の回転角度（度）。
            CSVの座標系をXODRの座標系に変換する際の回転角度。
            デフォルトは0.0

    Returns:
        str: 生成されたOpenSCENARIOファイルのパス。
            エラーが発生した場合はNone

    Note:
        CSV形式（必須列）:
        - timestamp: 時刻（秒）
        - pos_x, pos_y, pos_z: 位置座標
        - yaw_rad, pitch_rad, roll_rad: 姿勢角（ラジアン）
        - vel_x, vel_y, vel_z: 速度成分（m/s）
    """
    # 車両データを読み込む
    vehicles_data = _load_trajectory_data(vehicles_config, rotation_angle)

    # 少なくとも1つの有効な車両データがあるか確認
    if not vehicles_data:
        logger.error("エラー: 有効な車両データがありません。OpenSCENARIOを生成できません。")
        return None

    # 出力ディレクトリが存在しない場合は作成
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logger.info("出力ディレクトリを作成しました: %s", output_dir)

    # OpenSCENARIOのルート要素を作成
    root = ET.Element("OpenSCENARIO")

    # FileHeaderを作成
    _create_file_header(root)

    # ParameterDeclarations
    ET.SubElement(root, "ParameterDeclarations")

    # 空のCatalogLocations
    ET.SubElement(root, "CatalogLocations")

    # RoadNetworkを作成
    _create_road_network(root, road_network)

    # Entitiesを作成
    _create_entities(root, vehicles_data)

    # Storyboard
    storyboard = ET.SubElement(root, "Storyboard")

    # Init Actionsを作成
    _create_init_actions(storyboard, vehicles_data)

    # Story
    story = ET.SubElement(storyboard, "Story")
    story.set("name", "MyStory")
    ET.SubElement(story, "ParameterDeclarations")

    act = ET.SubElement(story, "Act")
    act.set("name", "MyAct")

    # ManeuverGroupsを作成
    _create_maneuver_groups(act, vehicles_data)

    # Triggersを作成
    _create_triggers(act, storyboard, vehicles_data)

    # XMLを整形して保存
    rough_string = ET.tostring(root, 'utf-8')
    reparsed = xml.dom.minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")

    with open(output_file, "w") as f:
        f.write(pretty_xml)

    logger.info("OpenSCENARIOファイルが生成されました: %s", output_file)
    return output_file


def main():
    """
    コマンドラインからスクリプトを実行するためのメイン関数。

    コマンドライン引数を解析し、JSONコンフィグファイルから設定を読み込んで
    OpenSCENARIOファイルを生成する。

    コマンドライン引数:
        -c, --config: JSONコンフィグファイルのパス（必須）
        -o, --output: 出力OpenSCENARIOファイルのパス
        -r, --rotation: 座標回転角度（度）

    Returns:
        None

    Example:
        $ python xosc_generator.py -c config.json -o output.xosc -r -90
    """
    parser = argparse.ArgumentParser(
        description='CSVファイルからOpenSCENARIOを生成')
    parser.add_argument(
        '-c', '--config', required=True, help='JSONコンフィグファイルのパス')
    parser.add_argument(
        '-o', '--output', default="generated_scenario.xosc",
        help='出力するOpenSCENARIOファイルのパス')
    parser.add_argument(
        '-r', '--rotation', type=float, default=0.0,
        help='座標系の回転角度（度）。CSVの座標をXODRの座標系に変換するための'
        '回転角度を指定。例: -90で反時計回りに90度回転')
    args = parser.parse_args()

    # JSONファイルから設定を読み込む
    vehicles_config, road_network = load_config_from_json(args.config)

    if vehicles_config is None:
        logger.error("エラー: JSONファイルの読み込みに失敗しました。プログラムを終了します。")
        return

    # コマンドライン引数で指定された出力ファイルパスを使用
    output_file = args.output

    # 回転角度が指定されている場合はログ出力
    if args.rotation != 0.0:
        logger.info("座標系を%s度回転して変換します。", args.rotation)

    # OpenSCENARIOファイルを生成
    generate_openscenario_from_csv(
        vehicles_config, road_network, output_file, args.rotation)


if __name__ == "__main__":
    main()
