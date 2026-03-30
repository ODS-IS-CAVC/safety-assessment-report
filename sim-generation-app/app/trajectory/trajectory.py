import os
import sys
import glob
import pathlib
import shutil
from natsort import natsorted
import re
import logging
import cv2
import csv
import json
import numpy as np
import time
import datetime
import pandas as pd
import numpy as np
import extact_image
import sensor
import table
import graph
import movie
import topview
import distance
import sct


# 各種セグメンテーション情報の読込
def read_seg(data_dir):
    tmp_results = natsorted(glob.glob(os.path.join(data_dir, '*front*/segmentation_detection_result.json')))
    if len(tmp_results) > 0:
        front_seg_detect_json_file = tmp_results[0]
        with open(front_seg_detect_json_file, 'r', encoding='utf-8') as file:
            front_seg_detect_json = json.load(file)
    else:
        front_seg_detect_json = None

    tmp_results = natsorted(glob.glob(os.path.join(data_dir, '*front*/segmentation_results.json')))
    if len(tmp_results) > 0:
        front_seg_json_file = tmp_results[0]
        with open(front_seg_json_file, 'r', encoding='utf-8') as file:
            front_seg_json = json.load(file)
    else:
        front_seg_json = None

    tmp_results = natsorted(glob.glob(os.path.join(data_dir, '*rear*/segmentation_detection_result.json')))
    if len(tmp_results) > 0:
        rear_seg_detect_json_file = tmp_results[0]
        with open(rear_seg_detect_json_file, 'r', encoding='utf-8') as file:
            rear_seg_detect_json = json.load(file)
    else:
        rear_seg_detect_json = None

    tmp_results = natsorted(glob.glob(os.path.join(data_dir, '*rear*/segmentation_results.json')))
    if len(tmp_results) > 0:
        rear_seg_json_file = tmp_results[0]
        with open(rear_seg_json_file, 'r', encoding='utf-8') as file:
            rear_seg_json = json.load(file)
    else:
        rear_seg_json = None

    return front_seg_detect_json, front_seg_json, rear_seg_detect_json, rear_seg_json


def main(args):

    data_root_dir = args[1] + '/'
    print(data_root_dir)

    # ロガー
    logging.basicConfig(
        filename='trajectory.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # コンソールハンドラーを追加
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)

    # 自車情報
    df_ego = pd.read_csv('egospec.csv', header=0, index_col=False)
    egoid = np.array(df_ego['id'])
    f_x = np.array(df_ego['f_x'])
    f_y = np.array(df_ego['f_y'])
    f_z = np.array(df_ego['f_z'])
    r_x = np.array(df_ego['r_x'])
    r_y = np.array(df_ego['r_y'])
    r_z = np.array(df_ego['r_z'])
    width = np.array(df_ego['width'])
    length = np.array(df_ego['length'])
    egoid_map = {}
    for egodata_id, w, l, fx, fy, fz, rx, ry, rz in zip(egoid, width, length, f_x, f_y, f_z, r_x, r_y, r_z):
        str_egodata_id = str(egodata_id).zfill(2)
        egoid_map[str_egodata_id] = [w, l, [ fx, fy, fz, rx, ry, rz]]

    # データフォルダ
    data_dirs = natsorted(glob.glob(os.path.join(data_root_dir, '*_*-*_Scene*')))
    data_ids = []
    for data_dir in data_dirs:
        print(data_dir)
        pattern = r'.+\\(.+_.+-.+_Scene.+)'
        matches = re.findall(pattern, data_dir)
        data_ids.append(matches[0])

    # データ毎の処理
    for data_id in data_ids:
        try:
            print(data_id)

            # 自車情報取得
            egoid = data_id[0:2]
            print(egoid)
            ego_width = egoid_map[egoid][0]
            ego_length = egoid_map[egoid][1]
            cam_pos = egoid_map[egoid][2]

            # 元データフォルダ
            data_dir = data_root_dir + data_id + '/'
            print(data_dir)

            # 各出力フォルダの作成
            #out_dir = data_id + '/'
            #os.makedirs(out_dir, exist_ok=True)
            out_dir = data_dir

            traj_dir = os.path.join(out_dir, 'trajectory')
            os.makedirs(traj_dir, exist_ok=True)

            tmp_dir = os.path.join(traj_dir, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)

            front_img_dir = os.path.join(tmp_dir, 'front_img')
            os.makedirs(front_img_dir, exist_ok=True)

            front_frame_file = os.path.join(tmp_dir, 'front_frame.csv')

            rear_img_dir = os.path.join(tmp_dir, 'rear_img')
            os.makedirs(rear_img_dir, exist_ok=True)

            rear_frame_file = os.path.join(tmp_dir, 'rear_frame.csv')

            graph_dir = os.path.join(tmp_dir, 'graph')
            os.makedirs(graph_dir, exist_ok=True)

            ego_data_file = os.path.join(traj_dir, 'ego.csv')

            # ドラレコ動画から画像抽出（フロントカメラ）
            front_img_file = natsorted(glob.glob(os.path.join(data_dir, '*front*/segmentation_cv.mp4')))
            if len(front_img_file) > 0:
                extact_image.extract(front_img_file[0], front_img_dir, front_frame_file)

            # ドラレコ動画から画像抽出（リアカメラ）
            rear_img_file = natsorted(glob.glob(os.path.join(data_dir, '*rear*/segmentation_cv.mp4')))
            if len(rear_img_file) > 0:
                extact_image.extract(rear_img_file[0], rear_img_dir, rear_frame_file)

            # 自車データファイルの構築
            # フロントカメラフレームをベースとする
            if os.path.isfile(front_frame_file):
                shutil.copyfile(front_frame_file, ego_data_file)
                df_frame = pd.read_csv(ego_data_file, header=0, index_col=False)
            else:
                logging.error("Unexpected error: no front dir " + data_id)
                # 一時フォルダの削除
                shutil.rmtree(tmp_dir)
                continue

            # センサーデータ読込
            original_sensor_file = glob.glob(os.path.join(data_dir, 'gsensor_gps_*.txt'))
            print(original_sensor_file)
            if len(original_sensor_file) == 1:
                original_sensor_file = original_sensor_file[0]
                df_sensor = pd.read_csv(original_sensor_file, header=0, index_col=False)
                df_sensor['datetime'] = pd.to_datetime(df_sensor['day'] + ' ' + df_sensor['time'])
                df_sensor['elapsed_time'] = (df_sensor['datetime'] - df_sensor['datetime'].iloc[0]).dt.total_seconds()
                df_sensor.rename(columns={'x': 'gx'}, inplace=True)
                df_sensor.rename(columns={'y': 'gy'}, inplace=True)
                df_sensor.rename(columns={'z': 'gz'}, inplace=True)
                print(df_sensor)
            else:
                print('no sensor_file')
                df_sensor = None

            # センサーデータを移動平均等加工して自車データファイルにマージ
            sensor.do_process(df_frame, df_sensor, ego_data_file)

            # 表作成
            table.do_process(ego_data_file, tmp_dir)

            # センサーデータのグラフ作成
            graph.do_process(ego_data_file, tmp_dir, graph_dir)

            # 各種セグメンテーション情報の読込
            front_seg_detect_json, front_seg_json, rear_seg_detect_json, rear_seg_json = read_seg(data_dir)

            # 上面視用距離とSCT計算処理（フロントカメラ）
            front_seg_detect_result_files = natsorted(glob.glob(os.path.join(data_dir, '*front*/segmentation_detection_result*.csv')))
            for seg_detect_result_file in front_seg_detect_result_files:
                # 上面視用距離計算
                distance.do_process(data_dir, seg_detect_result_file, ego_width, ego_length, cam_pos, tmp_dir, True)
                # SCT計算
                sct.do_process(data_dir, seg_detect_result_file, ego_width, ego_length, cam_pos, df_frame, ego_data_file, traj_dir, tmp_dir, True)

            # 上面視用距離とSCT計算処理（リアカメラ）
            rear_seg_detect_result_files = natsorted(glob.glob(os.path.join(data_dir, '*rear*/segmentation_detection_result*.csv')))
            for seg_detect_result_file in rear_seg_detect_result_files:
                # 上面視用距離計算
                distance.do_process(data_dir, seg_detect_result_file, ego_width, ego_length, cam_pos, tmp_dir, False)
                # SCT計算
                sct.do_process(data_dir, seg_detect_result_file, ego_width, ego_length, cam_pos, df_frame, ego_data_file, traj_dir, tmp_dir, False)

            # 上面視作成処理
            topview.do_process(ego_data_file, ego_width, ego_length, front_seg_json, rear_seg_json, traj_dir, graph_dir)

            # 動画ファイル作成
            movie_file = traj_dir + data_id + '.mp4'
            movie.make_movie(ego_data_file, front_img_dir, rear_img_dir, movie_file, tmp_dir, graph_dir)

            # 一時フォルダの削除
            shutil.rmtree(tmp_dir)

        except Exception as e:
            logging.error("Unexpected error: " + data_id)
            logging.error("Unexpected error", exc_info=True)


if __name__ == '__main__':
    main(sys.argv)
