import os
import sys
import shutil
import logging
import argparse
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from glob import glob
from natsort import natsorted
import json
from contextlib import contextmanager

# スクリプトの配置ディレクトリを基準にする
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# HybridNets リポジトリを別フォルダに分離した場合のパス
HYBRIDNETS_REPO_DIR = os.path.join(SCRIPT_DIR, 'hybridnets_repo')
if os.path.isdir(HYBRIDNETS_REPO_DIR) and HYBRIDNETS_REPO_DIR not in sys.path:
    sys.path.insert(1, HYBRIDNETS_REPO_DIR)


@contextmanager
def in_hybridnets_repo():
    """HybridNets のコードが CWD 相対パス (projects/bdd100k.yml 等) を
    参照するため、呼び出し中だけ CWD を hybridnets_repo/ に切り替える"""
    prev_cwd = os.getcwd()
    try:
        if os.path.isdir(HYBRIDNETS_REPO_DIR):
            os.chdir(HYBRIDNETS_REPO_DIR)
        yield
    finally:
        os.chdir(prev_cwd)

from lane import lane_detector
from tools import image2video
from distance import infer_distance_to_segmentation
from distance import infer_distance_to_segmentation_with_lane
from distance import infer_distance_ego_lane

from trajectory import extact_image
from trajectory import sensor
from trajectory import lane as lane_proc
from trajectory import distance as distance_calc
from trajectory import sct
from path_config import build_paths, ensure_dirs


def parse_args():
    parser = argparse.ArgumentParser(
        description="sim-generation-app: 距離推定・車線検出・軌跡計算・SCT/TTC算出パイプライン"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=os.environ.get("BASE_DIR", "/mnt/data"),
        help="データディレクトリのパス (デフォルト: 環境変数BASE_DIR or /mnt/data)",
    )
    parser.add_argument(
        "--ego-id",
        type=str,
        default=None,
        help="自車両ID (egospec.csvのid列に対応する2桁の番号。未指定時はデフォルト'01'を使用)",
    )
    parser.add_argument(
        "--frame-step",
        type=int,
        default=2,
        help="フレーム抽出間隔 (デフォルト: 2)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=15,
        help="処理FPS (デフォルト: 15)",
    )
    # シナリオ生成関連
    parser.add_argument(
        "--enable-scenario",
        action="store_true",
        default=False,
        help="シナリオ生成を有効にする",
    )
    parser.add_argument(
        "--map-data-path",
        type=str,
        default=os.environ.get("MAP_DATA_PATH", ""),
        help="マップデータのパス",
    )
    parser.add_argument(
        "--videos-fps",
        type=int,
        default=30,
        help="元動画のFPS (シナリオ生成用、デフォルト: 30)",
    )
    parser.add_argument(
        "--extend-trajectory",
        action="store_true",
        default=False,
        help="他車両軌跡をOpenDRIVE上で延長する",
    )
    parser.add_argument(
        "--start-step",
        type=int,
        default=None,
        help="指定したステップ番号から再開する (1-8)",
    )
    return parser.parse_args()


# ステップ名の定義
STEPS = [
    "DISTANCE_AND_LANE",        # 1+2
    "DISTANCE_WITH_LANE",       # 3
    "EXTRACT_IMAGES",           # 4
    "BUILD_EGO_DATA",           # 5
    "EGO_LANE_DISTANCE",        # 6
    "SCT_TTC",                  # 7
    "SCENARIO",                 # 8
]


def load_job_status(status_file):
    """前回の完了ステップを読み込む"""
    if os.path.isfile(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            status = json.load(f)
        return status.get("last_step", "NOT_STARTED")
    return "NOT_STARTED"


def save_job_status(status_file, step_name):
    """完了ステップを保存する"""
    status = {"last_step": step_name}
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def should_run_step(step_index, last_completed_index, start_step_override):
    """ステップを実行すべきかを判定する"""
    if start_step_override is not None:
        return step_index >= start_step_override
    return step_index > last_completed_index


def get_last_completed_index(last_step_name):
    """完了済みステップ名からインデックスを取得する"""
    if last_step_name == "NOT_STARTED":
        return -1
    if last_step_name in STEPS:
        return STEPS.index(last_step_name)
    return -1


def load_ego_spec():
    """自車両情報をegospec.csvから読み込む"""
    df_ego = pd.read_csv(
        os.path.join(SCRIPT_DIR, 'trajectory/egospec.csv'),
        header=0, index_col=False
    )
    egoid_map = {}
    for _, row in df_ego.iterrows():
        str_id = str(row['id']).zfill(2)
        egoid_map[str_id] = {
            'width': row['width'],
            'length': row['length'],
            'cam_pos': [row['f_x'], row['f_y'], row['f_z'],
                        row['r_x'], row['r_y'], row['r_z']],
        }
    return egoid_map


def load_lane_params(base_dir):
    """車線検出パラメータをlane_detector_param.csvから読み込む
    input/にあれば優先、なければデフォルト(SCRIPT_DIR/lane/)にフォールバック"""
    _default_lane_param = os.path.join(SCRIPT_DIR, 'lane', 'lane_detector_param.csv')
    _input_lane_param = os.path.join(base_dir, 'input', 'lane_detector_param.csv')
    _lane_param_path = _input_lane_param if os.path.exists(_input_lane_param) else _default_lane_param
    logging.info("lane_detector_param.csv: %s", _lane_param_path)
    df_lane_param = pd.read_csv(
        _lane_param_path,
        header=0, index_col=False
    )
    lane_param_map = {}
    for _, row in df_lane_param.iterrows():
        str_id = str(row['id']).zfill(2)
        key = str_id + '_' + row['front_rear']
        lane_param_map[key] = [row['lane_width_pixel'], row['horizontal_line']]
    return lane_param_map


def load_position_estimation_settings(input_dir, camera_direction):
    """カメラパラメータをNearMiss_Info.jsonから読み込む

    Args:
        input_dir: 入力ディレクトリパス
        camera_direction: 'front' or 'rear'
    Returns:
        dict: theta, camera_height, camera_elevation_angle, proj_mode を含む辞書。
              ファイルが存在しない場合はデフォルト値を返す。
    """
    if camera_direction == 'front':
        json_file = os.path.join(input_dir, 'NearMiss_Info.json')
    else:
        json_file = os.path.join(input_dir, 'Rear_NearMiss_Info.json')

    if os.path.isfile(json_file):
        with open(json_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return {
            'theta': settings.get('theta', 120),
            'camera_height': settings.get('camera_height', 1.6),
            'camera_elevation_angle': settings.get('camera_elevation_angle', 0),
            'proj_mode': settings.get('proj_mode', 0),
        }

    # pos_est_setting_*.json フォーマットも確認
    pos_est_file = os.path.join(input_dir, f'pos_est_setting_{camera_direction}.json')
    if os.path.isfile(pos_est_file):
        with open(pos_est_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
        return {
            'theta': settings.get('theta', 120),
            'camera_height': settings.get('camera_height', 1.6),
            'camera_elevation_angle': settings.get('camera_elevation_angle', 0),
            'proj_mode': settings.get('proj_mode', 0),
        }

    # デフォルト値
    logging.warning("カメラパラメータファイルが見つかりません: %s, %s", input_dir, camera_direction)
    return {
        'theta': 120,
        'camera_height': 1.6,
        'camera_elevation_angle': 0,
        'proj_mode': 0,
    }


def process_distance_estimation(seg_dir, input_dir, camera_direction):
    """距離推定処理 (旧SEG_INFER: try_bravsから移動した処理)

    segmentation_results.json → segmentation_detection_result.json を生成する。
    """
    segmentation_result_json = os.path.join(seg_dir, 'segmentation_results.json')
    if not os.path.isfile(segmentation_result_json):
        logging.warning("セグメンテーション結果が見つかりません: %s", segmentation_result_json)
        return None

    output_json = os.path.join(seg_dir, 'segmentation_detection_result.json')
    if os.path.isfile(output_json):
        logging.info("距離推定結果が既に存在します: %s", output_json)
        with open(output_json, mode='r', encoding='utf-8') as f:
            return json.load(f)

    with open(segmentation_result_json, mode='r', encoding='utf-8') as f:
        seg_data = json.load(f)

    pos_settings = load_position_estimation_settings(input_dir, camera_direction)

    infer_distance_to_segmentation.calculate_segmentation_point(
        seg_dir,
        seg_data,
        pos_settings['theta'],
        pos_settings['camera_height'],
        pos_settings['camera_elevation_angle'],
        pos_settings['proj_mode'],
    )

    with open(output_json, mode='r', encoding='utf-8') as f:
        return json.load(f)


def process_lane_detection(dist_dir, lane_dir, video_dir, lane_param_map, ego_id, camera_direction):
    """車線検出処理"""
    camera_lane_dir = os.path.join(lane_dir, camera_direction)
    lane_video = os.path.join(video_dir, f'{camera_direction}_lane.mp4')

    if os.path.isfile(lane_video):
        logging.info("車線検出結果が既に存在します: %s", lane_video)
        return

    os.makedirs(camera_lane_dir, exist_ok=True)
    param_key = ego_id + '_' + camera_direction

    if param_key not in lane_param_map:
        logging.warning("車線検出パラメータが見つかりません: %s", param_key)
        return

    lane_param = lane_param_map[param_key]
    with in_hybridnets_repo():
        lane_detector.detect_lane(dist_dir, camera_lane_dir, lane_param)
    image2video.image_to_video(camera_lane_dir, lane_video, frame_skip=1)


def process_distance_with_lane(seg_dir, lane_dir, camera_direction, seg_detect_data):
    """車線付き距離推定処理"""
    if seg_detect_data is None:
        return

    segmentation_result_json = os.path.join(seg_dir, 'segmentation_results.json')
    if not os.path.isfile(segmentation_result_json):
        return

    with open(segmentation_result_json, mode='r', encoding='utf-8') as f:
        seg_data = json.load(f)

    camera_lane_dir = os.path.join(lane_dir, camera_direction)
    lane_detection_file = os.path.join(camera_lane_dir, 'lane_detection_results.json')
    if not os.path.isfile(lane_detection_file):
        logging.warning("車線検出結果が見つかりません: %s", lane_detection_file)
        return None

    with open(lane_detection_file, "r", encoding="utf-8") as f:
        lane_detection_data = json.load(f)

    infer_distance_to_segmentation_with_lane.calculate_segmentation_point(
        seg_dir,
        seg_data,
        lane_detection_data,
        seg_detect_data["camera_parameter"]["aov_horizontal"],
        seg_detect_data["camera_parameter"]["camera_height"],
        seg_detect_data["camera_parameter"]["camera_elevation_angle"],
        seg_detect_data["camera_parameter"]["proj_mode"],
    )

    return lane_detection_data


def process_ego_lane_distance(traj_dir, df_frame, lane_detection_data, seg_detect_data, camera_direction, fps):
    """自車−車線距離の算出"""
    if seg_detect_data is None or lane_detection_data is None:
        return None

    ego_lane_json_file = os.path.join(traj_dir, f'{camera_direction}_ego_lane_detection_result.json')
    lane_data_file = os.path.join(traj_dir, f'{camera_direction}_lane.csv')

    infer_distance_ego_lane.calculate_point(
        traj_dir,
        ego_lane_json_file,
        df_frame,
        lane_detection_data,
        seg_detect_data["camera_parameter"]["aov_horizontal"],
        seg_detect_data["camera_parameter"]["camera_height"],
        seg_detect_data["camera_parameter"]["camera_elevation_angle"],
        seg_detect_data["camera_parameter"]["proj_mode"],
    )

    with open(ego_lane_json_file, mode='r', encoding='utf-8') as f:
        ego_lane_data = json.load(f)

    lane_proc.do_process(df_frame, ego_lane_data, lane_data_file, fps)

    return lane_data_file


def process_sct_calculation(seg_dir, ego_info, df_frame, ego_data_file, lane_data_file,
                            sct_dir, distance_dir, is_front, time_step, fps):
    """上面視距離 + SCT/TTC計算

    Args:
        sct_dir: SCT結果(trajectory_*.csv)の出力先
        distance_dir: 距離結果(distance_*.csv)の出力先（sct.pyからも読まれる）
    """
    result_json_name = 'segmentation_detection_result_with_lane.json'
    result_json = os.path.join(seg_dir, result_json_name)

    seg_detection_data = None
    if os.path.isfile(result_json):
        with open(result_json, mode='r', encoding='utf-8') as f:
            seg_detection_data = json.load(f)

    ego_width = ego_info['width']
    ego_length = ego_info['length']
    cam_pos = ego_info['cam_pos']

    distance_calc.do_process(
        seg_detection_data, ego_width, ego_length, cam_pos,
        ego_data_file, lane_data_file, distance_dir, is_front, fps
    )

    # sct.py (.so) は文字列結合でパスを構築するため末尾スラッシュが必要
    sct_dir_with_sep = sct_dir + os.sep
    distance_dir_with_sep = distance_dir + os.sep
    sct.do_process(
        seg_detection_data, ego_width, ego_length, cam_pos,
        df_frame, ego_data_file, lane_data_file, sct_dir_with_sep, distance_dir_with_sep,
        is_front, time_step, fps
    )


def main():
    args = parse_args()

    base_dir = args.base_dir
    ego_id = args.ego_id if args.ego_id else '01'
    frame_step = args.frame_step
    fps = args.fps
    time_step = 1.0 / fps

    # ロガー設定
    logging.basicConfig(
        filename=os.path.join(base_dir, 'pipeline.log'),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)

    logging.info("=== Pipeline開始: base_dir=%s, ego_id=%s ===", base_dir, ego_id)
    pipeline_start = time.monotonic()
    step_times = {}

    # ジョブステータス管理
    status_file = os.path.join(base_dir, 'job_status.json')
    last_step_name = load_job_status(status_file)
    last_completed = get_last_completed_index(last_step_name)

    # --start-step が指定された場合は0-indexedに変換 (ユーザー入力は1-8)
    start_step = None
    if args.start_step is not None:
        start_step = args.start_step - 1
        logging.info("ステップ %d から再開します", args.start_step)
    elif last_step_name != "NOT_STARTED":
        logging.info("前回の完了ステップ: %s (次のステップから再開)", last_step_name)

    # 自車情報・車線検出パラメータの読み込み
    egoid_map = load_ego_spec()
    lane_param_map = load_lane_params(base_dir)

    if ego_id not in egoid_map:
        logging.error("ego_id '%s' がegospec.csvに存在しません。利用可能なID: %s", ego_id, list(egoid_map.keys()))
        sys.exit(1)

    ego_info = egoid_map[ego_id]

    # ディレクトリパスの構築 (path_config で一元管理)
    paths = build_paths(base_dir)

    input_dir = paths['input']
    seg_front_dir = paths['image_segmentation_front']
    seg_rear_dir = paths['image_segmentation_rear']
    front_dist_dir = paths['image_distortion_front']
    rear_dist_dir = paths['image_distortion_rear']
    lane_dir = paths['image_lane']
    tmp_dir = paths['tmp']

    front_img_dir = paths['image_frame_front']
    rear_img_dir = paths['image_frame_rear']

    front_frame_file = os.path.join(tmp_dir, 'front_frame.csv')
    rear_frame_file = os.path.join(tmp_dir, 'rear_frame.csv')
    ego_data_file = os.path.join(paths['output_trajectory'], 'ego.csv')
    front_lane_data_file = os.path.join(paths['intermediate_lane_distance'], 'front_lane.csv')
    rear_lane_data_file = os.path.join(paths['intermediate_lane_distance'], 'rear_lane.csv')

    # 必要なディレクトリを作成
    ensure_dirs(paths, [
        'image_lane', 'image_lane_front', 'image_lane_rear',
        'image_frame_front', 'image_frame_rear',
        'plot', 'tmp', 'tmp_graph',
        'output_trajectory',
        'intermediate_distance', 'intermediate_lane_distance',
        'output_video',
    ])

    # 中間データの復元用（途中再開時に前ステップの出力を読み込む）
    front_seg_detect_data = None
    rear_seg_detect_data = None
    front_lane_detection_data = None
    rear_lane_detection_data = None
    df_frame = None

    def restore_seg_detect_data():
        nonlocal front_seg_detect_data, rear_seg_detect_data
        front_json = os.path.join(seg_front_dir, 'segmentation_detection_result.json')
        rear_json = os.path.join(seg_rear_dir, 'segmentation_detection_result.json')
        if os.path.isfile(front_json):
            with open(front_json, mode='r', encoding='utf-8') as f:
                front_seg_detect_data = json.load(f)
        if os.path.isfile(rear_json):
            with open(rear_json, mode='r', encoding='utf-8') as f:
                rear_seg_detect_data = json.load(f)

    def restore_lane_detection_data():
        nonlocal front_lane_detection_data, rear_lane_detection_data
        front_lane_file = os.path.join(lane_dir, 'front/lane_detection_results.json')
        rear_lane_file = os.path.join(lane_dir, 'rear/lane_detection_results.json')
        if os.path.isfile(front_lane_file):
            with open(front_lane_file, "r", encoding="utf-8") as f:
                front_lane_detection_data = json.load(f)
        if os.path.isfile(rear_lane_file):
            with open(rear_lane_file, "r", encoding="utf-8") as f:
                rear_lane_detection_data = json.load(f)

    def restore_df_frame():
        nonlocal df_frame
        if os.path.isfile(ego_data_file):
            df_frame = pd.read_csv(ego_data_file, header=0, index_col=False)
        elif os.path.isfile(front_frame_file):
            df_frame = pd.read_csv(front_frame_file, header=0, index_col=False)

    # ===================================================
    # Step 1+2. 距離推定 & 車線検出 (並列実行)
    # ===================================================
    if should_run_step(0, last_completed, start_step):
        logging.info("=== Step 1+2: 距離推定 & 車線検出 (並列) ===")
        _t0 = time.monotonic()

        with ThreadPoolExecutor() as executor:
            future_front_dist = executor.submit(process_distance_estimation, seg_front_dir, input_dir, 'front')
            future_rear_dist = executor.submit(process_distance_estimation, seg_rear_dir, input_dir, 'rear')

            future_front_lane = None
            future_rear_lane = None
            video_dir = paths['output_video']
            if os.path.isdir(front_dist_dir):
                future_front_lane = executor.submit(
                    process_lane_detection, front_dist_dir, lane_dir, video_dir, lane_param_map, ego_id, 'front'
                )
            if os.path.isdir(rear_dist_dir):
                future_rear_lane = executor.submit(
                    process_lane_detection, rear_dist_dir, lane_dir, video_dir, lane_param_map, ego_id, 'rear'
                )

            front_seg_detect_data = future_front_dist.result()
            rear_seg_detect_data = future_rear_dist.result()
            if future_front_lane is not None:
                future_front_lane.result()
            if future_rear_lane is not None:
                future_rear_lane.result()

        save_job_status(status_file, STEPS[0])
        step_times['Step 1+2'] = time.monotonic() - _t0
        logging.info("=== Step 1+2 完了 (%.1f秒) ===", step_times['Step 1+2'])
    else:
        logging.info("=== Step 1+2: スキップ ===")
        restore_seg_detect_data()

    # ===================================================
    # Step 3. 車線付き距離推定
    # ===================================================
    if should_run_step(1, last_completed, start_step):
        logging.info("=== Step 3: 車線付き距離推定 ===")
        _t0 = time.monotonic()
        if front_seg_detect_data is None:
            restore_seg_detect_data()
        front_lane_detection_data = process_distance_with_lane(
            seg_front_dir, lane_dir, 'front', front_seg_detect_data
        )
        rear_lane_detection_data = process_distance_with_lane(
            seg_rear_dir, lane_dir, 'rear', rear_seg_detect_data
        )
        save_job_status(status_file, STEPS[1])
        step_times['Step 3'] = time.monotonic() - _t0
        logging.info("=== Step 3 完了 (%.1f秒) ===", step_times['Step 3'])
    else:
        logging.info("=== Step 3: スキップ ===")
        restore_lane_detection_data()

    # ===================================================
    # Step 4. セグメンテーション画像抽出
    # ===================================================
    if should_run_step(2, last_completed, start_step):
        logging.info("=== Step 4: セグメンテーション画像抽出 ===")
        _t0 = time.monotonic()
        front_seg_video = os.path.join(seg_front_dir, 'segmentation_cv.mp4')
        if not os.path.isfile(front_frame_file) and os.path.isfile(front_seg_video):
            extact_image.extract(front_seg_video, front_img_dir, front_frame_file, frame_step, time_step)

        rear_seg_video = os.path.join(seg_rear_dir, 'segmentation_cv.mp4')
        if not os.path.isfile(rear_frame_file) and os.path.isfile(rear_seg_video):
            extact_image.extract(rear_seg_video, rear_img_dir, rear_frame_file, frame_step, time_step)

        # セグメンテーション動画を output/video にコピー（確認用）
        video_dir = paths['output_video']
        if os.path.isfile(front_seg_video):
            shutil.copyfile(front_seg_video, os.path.join(video_dir, 'segmentation_front.mp4'))
        if os.path.isfile(rear_seg_video):
            shutil.copyfile(rear_seg_video, os.path.join(video_dir, 'segmentation_rear.mp4'))

        save_job_status(status_file, STEPS[2])
        step_times['Step 4'] = time.monotonic() - _t0
        logging.info("=== Step 4 完了 (%.1f秒) ===", step_times['Step 4'])
    else:
        logging.info("=== Step 4: スキップ ===")

    # ===================================================
    # Step 5. 自車データファイルの構築
    # ===================================================
    if should_run_step(3, last_completed, start_step):
        logging.info("=== Step 5: 自車データファイル構築 ===")
        _t0 = time.monotonic()
        if not os.path.isfile(front_frame_file):
            logging.error("フロントカメラのフレームファイルが見つかりません: %s", front_frame_file)
            sys.exit(1)

        shutil.copyfile(front_frame_file, ego_data_file)
        df_frame = pd.read_csv(ego_data_file, header=0, index_col=False)

        sensor_files = glob(os.path.join(base_dir, 'gsensor_gps_*.txt'))
        if len(sensor_files) == 0:
            sensor_files = glob(os.path.join(input_dir, 'gsensor_gps_*.txt'))

        df_sensor = None
        if len(sensor_files) >= 1:
            try:
                original_sensor_file = sensor_files[0]
                df_sensor = pd.read_csv(original_sensor_file, header=0, index_col=False)
                df_sensor['datetime'] = pd.to_datetime(df_sensor['day'] + ' ' + df_sensor['time'])
                df_sensor['elapsed_time'] = (df_sensor['datetime'] - df_sensor['datetime'].iloc[0]).dt.total_seconds()
                df_sensor.rename(columns={'x': 'gx', 'y': 'gy', 'z': 'gz'}, inplace=True)
            except Exception as e:
                logging.error("センサーデータ読込エラー: %s", e, exc_info=True)
                df_sensor = None
        else:
            logging.warning("センサーデータファイルが見つかりません")

        sensor.do_process(df_frame, df_sensor, ego_data_file, time_step, fps)
        save_job_status(status_file, STEPS[3])
        step_times['Step 5'] = time.monotonic() - _t0
        logging.info("=== Step 5 完了 (%.1f秒) ===", step_times['Step 5'])
    else:
        logging.info("=== Step 5: スキップ ===")
        restore_df_frame()

    # ===================================================
    # Step 6. 自車−車線距離の算出
    # ===================================================
    if should_run_step(4, last_completed, start_step):
        logging.info("=== Step 6: 自車−車線距離算出 ===")
        _t0 = time.monotonic()
        if df_frame is None:
            restore_df_frame()
        if front_seg_detect_data is None:
            restore_seg_detect_data()
        if front_lane_detection_data is None:
            restore_lane_detection_data()
        process_ego_lane_distance(
            paths['intermediate_lane_distance'], df_frame, front_lane_detection_data, front_seg_detect_data, 'front', fps
        )
        process_ego_lane_distance(
            paths['intermediate_lane_distance'], df_frame, rear_lane_detection_data, rear_seg_detect_data, 'rear', fps
        )
        save_job_status(status_file, STEPS[4])
        step_times['Step 6'] = time.monotonic() - _t0
        logging.info("=== Step 6 完了 (%.1f秒) ===", step_times['Step 6'])
    else:
        logging.info("=== Step 6: スキップ ===")

    # ===================================================
    # Step 7. 上面視距離 + SCT/TTC計算
    # ===================================================
    if should_run_step(5, last_completed, start_step):
        logging.info("=== Step 7: SCT/TTC計算 ===")
        _t0 = time.monotonic()
        if df_frame is None:
            restore_df_frame()
        process_sct_calculation(
            seg_front_dir, ego_info, df_frame, ego_data_file,
            front_lane_data_file, paths['output_trajectory'], paths['intermediate_distance'], True, time_step, fps
        )
        process_sct_calculation(
            seg_rear_dir, ego_info, df_frame, ego_data_file,
            rear_lane_data_file, paths['output_trajectory'], paths['intermediate_distance'], False, time_step, fps
        )
        save_job_status(status_file, STEPS[5])
        step_times['Step 7'] = time.monotonic() - _t0
        logging.info("=== Step 7 完了 (%.1f秒) ===", step_times['Step 7'])
    else:
        logging.info("=== Step 7: スキップ ===")

    # ===================================================
    # Step 8. シナリオ生成 (オプション)
    # ===================================================
    if args.enable_scenario and should_run_step(6, last_completed, start_step):
        logging.info("=== Step 8: シナリオ生成 ===")
        _t0 = time.monotonic()
        run_scenario_generation(args, paths, seg_front_dir)
        save_job_status(status_file, STEPS[6])
        step_times['Step 8'] = time.monotonic() - _t0
        logging.info("=== Step 8 完了 (%.1f秒) ===", step_times['Step 8'])
    elif args.enable_scenario:
        logging.info("=== Step 8: スキップ ===")

    total_elapsed = time.monotonic() - pipeline_start
    logging.info("=== Pipeline完了 (トータル %.1f秒 / %.1f分) ===", total_elapsed, total_elapsed / 60)
    logging.info("--- ステップ別実行時間 ---")
    for step_name, elapsed in step_times.items():
        logging.info("  %s: %.1f秒 (%.1f分)", step_name, elapsed, elapsed / 60)


def run_python_script(script_path, script_args):
    """Pythonスクリプトをサブプロセスとして実行する"""
    cmd = [sys.executable, script_path] + script_args
    logging.info("実行: %s", ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error("スクリプト実行エラー: %s\n%s", script_path, result.stderr)
        raise RuntimeError(f"Script failed: {script_path}")
    if result.stdout:
        logging.info(result.stdout.rstrip())


def run_scenario_generation(args, paths, seg_front_dir):
    """シナリオ生成パイプライン (try_bravsのentrypoint.sh後半に相当)"""
    videos_fps = args.videos_fps
    extend_trajectory = args.extend_trajectory
    map_data_path = args.map_data_path

    input_dir = paths['input']

    # シナリオ関連ディレクトリ
    scenario_dir = paths['output_scenario']
    sdmg_dir = os.path.join(scenario_dir, 'sdmg')
    plot_dir = paths['plot']
    summary_dir = os.path.join(paths['output_video'], 'summary')
    for d in [scenario_dir, sdmg_dir, plot_dir, summary_dir]:
        os.makedirs(d, exist_ok=True)

    # 距離推定結果ファイル
    infer_rel_coord_file = os.path.join(seg_front_dir, 'segmentation_detection_result.json')

    # NearMiss_Info.json
    nearmiss_file = os.path.join(input_dir, 'NearMiss_Info.json')
    lane_id = "-100"
    if os.path.isfile(nearmiss_file):
        with open(nearmiss_file, "r", encoding="utf-8") as f:
            nearmiss_info = json.load(f)
        lane_id = str(nearmiss_info.get('lane_id', '-100'))

    # GPS座標ファイル
    gps_files = glob(os.path.join(input_dir, '*.csv'))
    gps_coord_file = gps_files[0] if gps_files else ""

    # シナリオ関連のスクリプトパス
    scenario_script_dir = os.path.join(SCRIPT_DIR, 'scenario')
    trajectory_script_dir = os.path.join(SCRIPT_DIR, 'trajectory')

    # テンプレートファイル
    base_scenario_file = os.path.join(scenario_script_dir, 'data/base_scenario.xml')
    car_object_data_file = os.path.join(scenario_script_dir, 'data/car_object_data.xml')
    setting_json = os.path.join(scenario_script_dir, 'data/setting.json')

    # シナリオ出力ファイル
    scenario_xml = os.path.join(sdmg_dir, 'scenario.xml')
    xosc_config = os.path.join(sdmg_dir, 'xosc_config.json')

    # マップ選択結果
    map_select_file = ""
    xodr_road_coordinate_file = ""
    map_select_files = glob(os.path.join(input_dir, '*MapSelectResult*.json'))
    if map_select_files:
        map_select_file = map_select_files[0]
        with open(map_select_file, "r", encoding="utf-8") as f:
            map_select_data = json.load(f)
        xodr_road_coordinate_file = map_select_data.get('road_coordinates_path', '')

    # --- Step 8a: マップ選択 ---
    if not map_select_file and map_data_path and gps_coord_file:
        logging.info("--- Step 8a: マップ選択 ---")
        _t0 = time.monotonic()
        map_select_script = os.path.join(SCRIPT_DIR, 'map_tools/map_select.py')
        run_python_script(map_select_script, [
            '--route_data_path', gps_coord_file,
            '--map_data_path', map_data_path,
            '--lane_id', lane_id,
        ])
        map_select_files = glob(os.path.join(input_dir, '*MapSelectResult*.json'))
        if map_select_files:
            map_select_file = map_select_files[0]
            with open(map_select_file, "r", encoding="utf-8") as f:
                map_select_data = json.load(f)
            xodr_road_coordinate_file = map_select_data.get('road_coordinates_path', '')
        logging.info("--- Step 8a 完了 (%.1f秒) ---", time.monotonic() - _t0)

    if not xodr_road_coordinate_file:
        logging.warning("マップ選択結果がありません。シナリオ生成をスキップします。")
        return

    # --- Step 8b: 検出結果の平滑化 ---
    logging.info("--- Step 8b: 検出結果の平滑化 ---")
    _t0 = time.monotonic()
    filter_debug_dir = os.path.join(paths['tmp'], 'filter_debug')
    os.makedirs(filter_debug_dir, exist_ok=True)
    filtered_detection_result = os.path.join(seg_front_dir, 'filtered_detection_result.json')

    run_python_script(os.path.join(trajectory_script_dir, 'smoothing_detection_result.py'), [
        '--input_json', infer_rel_coord_file,
        '--output_json', filtered_detection_result,
        '--debug_output_dir', filter_debug_dir,
    ])

    if os.path.isfile(filtered_detection_result):
        infer_rel_coord_file = filtered_detection_result
    logging.info("--- Step 8b 完了 (%.1f秒) ---", time.monotonic() - _t0)

    # --- Step 8c: 自車両軌跡生成 ---
    logging.info("--- Step 8c: 自車両軌跡生成 ---")
    _t0 = time.monotonic()
    run_python_script(os.path.join(trajectory_script_dir, 'generate_ego_vehicle_trajectory.py'), [
        '--input_road', xodr_road_coordinate_file,
        '--gps_csv', gps_coord_file,
        '--map_select', map_select_file,
        '--config_path', nearmiss_file,
        '--output_dir', scenario_dir,
    ])
    logging.info("--- Step 8c 完了 (%.1f秒) ---", time.monotonic() - _t0)

    # --- Step 8d: 他車両軌跡生成 ---
    logging.info("--- Step 8d: 他車両軌跡生成 ---")
    _t0 = time.monotonic()
    self_trajectory_csv = os.path.join(scenario_dir, 'vehicle_route_self.csv')
    run_python_script(os.path.join(trajectory_script_dir, 'generate_other_vehicle_trajectory.py'), [
        '--self_trajectory', self_trajectory_csv,
        '--input_json', infer_rel_coord_file,
        '--road_network', xodr_road_coordinate_file,
        '--output_dir', scenario_dir,
        '--fps', str(videos_fps),
    ])
    logging.info("--- Step 8d 完了 (%.1f秒) ---", time.monotonic() - _t0)

    # --- Step 8e: 他車両軌跡延長 + 追い越し防止 ---
    logging.info("--- Step 8e: 他車両軌跡延長・追い越し防止 ---")
    _t0 = time.monotonic()
    if extend_trajectory and os.path.isfile(self_trajectory_csv):
        # 最終フレームを取得
        df_self = pd.read_csv(self_trajectory_csv)
        end_frame = int(df_self.iloc[-1, 1]) if len(df_self) > 0 else 0

        for csv_file in natsorted(glob(os.path.join(scenario_dir, 'vehicle_route_*.csv'))):
            basename = os.path.basename(csv_file)
            if basename == 'vehicle_route_self.csv' or '_extended' in basename:
                continue
            obj_id = basename.replace('vehicle_route_', '').replace('.csv', '')
            output_file = os.path.join(scenario_dir, f'vehicle_route_{obj_id}_extended.csv')
            run_python_script(os.path.join(trajectory_script_dir, 'extend_other_vehicle_trajectory.py'), [
                '--input_csv', csv_file,
                '--output_csv', output_file,
                '--road_network', xodr_road_coordinate_file,
                '--start_frame', '0',
                '--end_frame', str(end_frame),
                '--fps', str(videos_fps),
                '--extend_before', '--extend_after',
            ])

    # 追い越し防止
    run_python_script(os.path.join(trajectory_script_dir, 'resolve_vehicle_collisions.py'), [
        '--trajectory_dir', scenario_dir,
        '--self_trajectory', self_trajectory_csv,
        '--fps', str(videos_fps),
        '--min_gap', '5.0',
        '--iterations', '10',
    ])
    logging.info("--- Step 8e 完了 (%.1f秒) ---", time.monotonic() - _t0)

    # --- Step 8f: 軌跡データまとめ ---
    logging.info("--- Step 8f: 軌跡データまとめ ---")
    _t0 = time.monotonic()
    summarize_flags = []
    if not extend_trajectory:
        summarize_flags = ['--no_prefer_extended', '--exclude_camera_outside']

    run_python_script(os.path.join(trajectory_script_dir, 'summarize_trajectories.py'), [
        '--detection_result', infer_rel_coord_file,
        '--trajectory_dir', scenario_dir,
        '--output_dir', summary_dir,
    ] + summarize_flags)

    run_python_script(os.path.join(trajectory_script_dir, 'plot_trajectories_summary.py'), [
        '--summary_json', os.path.join(summary_dir, 'trajectory_summary.json'),
        '--road_network', xodr_road_coordinate_file,
        '--output_dir', plot_dir,
        '--limit_normal', '70',
        '--skip_zoom',
    ])
    logging.info("--- Step 8f 完了 (%.1f秒) ---", time.monotonic() - _t0)

    # --- Step 8g: サマリー動画生成 ---
    logging.info("--- Step 8g: サマリー動画生成 ---")
    _t0 = time.monotonic()
    run_python_script(os.path.join(trajectory_script_dir, 'generate_summary_video.py'), [
        '--summary_json', os.path.join(summary_dir, 'trajectory_summary.json'),
        '--infer_dir', paths['image_segmentation'],
        '--distortion_dir', paths['image_distortion'],
        '--normal_dir', os.path.join(plot_dir, 'normal'),
        '--output_path', os.path.join(summary_dir, 'summary_video.mp4'),
    ])
    logging.info("--- Step 8g 完了 (%.1f秒) ---", time.monotonic() - _t0)

    # --- Step 8h: シナリオXML生成 ---
    logging.info("--- Step 8h: シナリオXML生成 ---")
    _t0 = time.monotonic()
    updated_detection_result = os.path.join(seg_front_dir, 'updated_detection_result.json')
    if not os.path.isfile(updated_detection_result):
        updated_detection_result = infer_rel_coord_file

    prefer_extended_flag = [] if extend_trajectory else ['--no_prefer_extended']

    run_python_script(os.path.join(scenario_script_dir, 'scenario_xml_initialize.py'), [
        '--abs_coord_file', updated_detection_result,
        '--base_scenario_xml', base_scenario_file,
        '--car_data_xml', car_object_data_file,
        '--output_dir', sdmg_dir,
    ])

    run_python_script(os.path.join(scenario_script_dir, 'set_map_to_scenario.py'), [
        '--scenario_xml_file', scenario_xml,
        '--xosc_config_json', xosc_config,
        '--map_info_file', map_select_file,
    ])

    run_python_script(os.path.join(scenario_script_dir, 'divp_scenario.py'), [
        '--scenario_xml_file', scenario_xml,
        '--xosc_config_json', xosc_config,
        '--car_routes_dir', scenario_dir,
        '--output_dir', scenario_dir,
    ] + prefer_extended_flag)

    run_python_script(os.path.join(scenario_script_dir, 'sdmg_scenario.py'), [
        '--scenario_xml_file', scenario_xml,
        '--car_routes_dir', scenario_dir,
        '--output_dir', scenario_dir,
    ] + prefer_extended_flag)

    run_python_script(os.path.join(scenario_script_dir, 'route2waypoint.py'), [
        '--scenario_xml_file', scenario_xml,
        '--car_routes_dir', scenario_dir,
        '--output_dir', scenario_dir,
    ] + prefer_extended_flag)

    # ROS設定JSON生成
    divp_route_csvs = natsorted(glob(os.path.join(scenario_dir, '*.csv')))
    if divp_route_csvs:
        run_python_script(os.path.join(scenario_script_dir, 'generate_ros_setting_json.py'), [
            '--divp_route_csv_file', divp_route_csvs[0],
            '--base_setting_json', setting_json,
            '--output_path', scenario_dir,
            '--camera_fps', '3',
        ])

    # OpenSCENARIO生成
    run_python_script(os.path.join(scenario_script_dir, 'xosc_generator.py'), [
        '--config', xosc_config,
        '--output', os.path.join(scenario_dir, 'xosc/scenario.xosc'),
        '--rotation', '90',
    ])

    logging.info("--- Step 8h 完了 (%.1f秒) ---", time.monotonic() - _t0)
    logging.info("=== シナリオ生成完了 ===")


if __name__ == '__main__':
    main()
