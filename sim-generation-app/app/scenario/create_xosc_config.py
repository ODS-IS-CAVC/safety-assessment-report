import os
import re
import json
import logging
import argparse
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_vehicle_type_from_filename(filename):
    """
    ファイル名から車種を抽出する

    Parameters:
    filename (str): ファイル名

    Returns:
    str: 車種名（例: "HinoProfia", "HondaNbox"など）
    """
    # scenario_*_divp_Veh_プレフィックスを除去
    cleaned_filename = filename
    if 'scenario_' in filename.lower() and '_divp_veh_' in filename.lower():
        # scenario_数字_divp_Veh_の部分を除去
        match = re.search(r'scenario_\d+_divp_veh_(.+)', filename.lower())
        if match:
            cleaned_filename = match.group(1)

    # 車種のパターンを定義
    vehicle_patterns = [
        "HinoProfia", "HondaNbox", "HondaVezel",
        "SubaruLevorg", "ToyotaAqua", "ToyotaHiace"
    ]

    for pattern in vehicle_patterns:
        if pattern.lower() in cleaned_filename.lower():
            return pattern

    return None


def get_vehicle_category_and_bounding_box(vehicle_type, is_ego_vehicle=False):
    """
    車種に基づいてvehicleCategoryとboundingBoxを取得する

    Parameters:
    vehicle_type (str): 車種名
    is_ego_vehicle (bool): 自車両かどうか

    Returns:
    tuple: (vehicleCategory, boundingBox)
    """
    # 自車両の場合は大型車両設定
    if is_ego_vehicle:
        return "truck", {
            "center": {"x": 2.536, "y": 0.0, "z": 1.849},
            "dimensions": {"width": 3.698, "length": 11.87, "height": 2.564}
        }

    # HinoProfiaはトラック
    if vehicle_type == "HinoProfia":
        return "truck", {
            "center": {"x": 2.536, "y": 0.0, "z": 1.849},
            "dimensions": {"width": 3.698, "length": 11.87, "height": 2.564}
        }

    # その他は乗用車
    return "car", {
        "center": {"x": 1.385, "y": 0.0, "z": 0.859},
        "dimensions": {"width": 1.717, "length": 4.29, "height": 1.695}
    }


def extract_actor_info_from_csv(csv_filename):
    """
    CSVファイル名からアクター情報を抽出する

    Parameters:
    csv_filename (str): CSVファイル名

    Returns:
    dict: アクター情報の辞書
    """
    # ファイル名から拡張子を除去
    base_name = os.path.splitext(csv_filename)[0]

    # 自車両かどうかを判定（self, ego, _self, _egoを含む場合）
    is_ego_vehicle = any(keyword in base_name.lower()
                         for keyword in ["self", "ego", "_self", "_ego"])

    # 車種を抽出
    vehicle_type = extract_vehicle_type_from_filename(base_name)

    # actor_nameを決定
    if vehicle_type:
        # 車種が特定できた場合、番号も抽出してactor_nameを作成
        if is_ego_vehicle:
            actor_name = f"{vehicle_type}_self"
        else:
            # 番号を抽出（最後の数字を使用）
            numbers = re.findall(r'_(\d+)', base_name)
            if numbers:
                number = numbers[-1]  # 最後の数字を使用
                actor_name = f"{vehicle_type}_{number}"
            else:
                actor_name = vehicle_type
    else:
        # 車種が特定できない場合はファイル名をそのまま使用
        actor_name = base_name

    # vehicleCategoryとboundingBoxを取得
    vehicle_category, bounding_box = get_vehicle_category_and_bounding_box(
        vehicle_type, is_ego_vehicle)

    actor_info = {
        "csv_file": csv_filename,
        "name": actor_name,
        "vehicleCategory": vehicle_category,
        "boundingBox": bounding_box
    }

    return actor_info


def extract_number_from_actor_name(actor_name):
    """
    アクター名から番号を抽出する（divp_scenario.pyから参考）
    """
    # 自車両を表すキーワードをチェック
    if any(keyword in actor_name.lower()
           for keyword in ["self", "ego", "_self", "_ego"]):
        return "self"
    else:
        match = re.search(r'_(\d+)', actor_name)
        if match:
            return match.group(1)
    return None


def create_xosc_config(input_dir, output_path, xodr_file=None):
    """
    指定されたディレクトリ内のCSVファイルと指定されたXODRファイルからxosc_config.jsonを作成する

    Parameters:
    input_dir (str): 入力ディレクトリパス
    output_path (str): 出力するxosc_config.jsonのパス
    xodr_file (str, optional): 使用するXODRファイルパス
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        raise ValueError(f"入力ディレクトリが存在しません: {input_dir}")

    # CSVファイルを検索
    csv_files = list(input_path.glob("*.csv"))
    if not csv_files:
        raise ValueError(f"CSVファイルが見つかりません: {input_dir}")

    # XODRファイルの決定
    if xodr_file:
        # 指定されたXODRファイルを使用
        xodr_path = Path(xodr_file)
        if not xodr_path.exists():
            raise ValueError(f"指定されたXODRファイルが存在しません: {xodr_file}")

        # 相対パスを計算（入力ディレクトリからの）
        try:
            xodr_file_name = os.path.relpath(xodr_file, input_dir)
        except ValueError:
            # 相対パス変換に失敗した場合は絶対パスを使用
            xodr_file_name = str(xodr_path)
    else:
        # XODRファイルをディレクトリ内で検索
        xodr_files = list(input_path.glob("*.xodr"))
        if not xodr_files:
            raise ValueError(f"XODRファイルが見つかりません: {input_dir}")

        # 最初のXODRファイルを使用
        xodr_file = xodr_files[0]
        xodr_file_name = xodr_file.name

    logger.info("見つかったCSVファイル: %s", [f.name for f in csv_files])
    logger.info("使用するXODRファイル: %s", xodr_file_name)

    # OpenScenario configデータの初期化
    xosc_data_dict = {
        "actors": [],
        "roadNetwork": {}
    }

    # CSVファイルからアクター情報を作成
    ego_actors = []
    other_actors = []

    for csv_file in csv_files:
        # 相対パスでCSVファイルを指定
        relative_csv_path = str(Path(input_dir) / csv_file.name)

        actor_info = extract_actor_info_from_csv(csv_file.name)
        actor_info["csv_file"] = relative_csv_path

        # 自車両かどうかを判定
        base_name = os.path.splitext(csv_file.name)[0]
        is_ego_vehicle = any(keyword in base_name.lower()
                             for keyword in ["self", "ego", "_self", "_ego"])

        if is_ego_vehicle:
            ego_actors.append(actor_info)
        else:
            other_actors.append(actor_info)

        logger.info("アクター追加: %s -> %s", actor_info['name'], relative_csv_path)

    # 自車両を先頭に、その他の車両を後に配置
    xosc_data_dict["actors"] = ego_actors + other_actors

    # OpenScenario configにマップ追加
    xosc_data_dict['roadNetwork'] = {
        "logicFile": xodr_file_name,
    }

    logger.info("ロードネットワーク設定: %s", xodr_file_name)

    # 出力ディレクトリを作成
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # OpenScenario configファイル出力
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(xosc_data_dict, f, ensure_ascii=False, indent=2)

    logger.info("xosc_config.jsonを作成しました: %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="ディレクトリ内のCSVファイルと指定されたXODRファイルからxosc_config.jsonを作成")
    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="CSVファイルが格納されているディレクトリパス"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="出力するxosc_config.jsonのパス（省略時は入力ディレクトリに作成）"
    )
    parser.add_argument(
        "-x", "--xodr",
        type=str,
        help="使用するXODRファイルのパス（省略時は入力ディレクトリ内のXODRファイルを使用）"
    )

    args = parser.parse_args()

    # 出力パスが指定されていない場合は、入力ディレクトリに作成
    if args.output is None:
        input_path = Path(args.input)
        output_path = input_path / "config.json"
    else:
        output_path = args.output

    try:
        create_xosc_config(args.input, str(output_path), args.xodr)
    except Exception as e:
        logger.error("エラー: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
