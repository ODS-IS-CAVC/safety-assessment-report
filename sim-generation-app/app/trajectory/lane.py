import os
import sys
import glob
import pathlib
import cv2
import csv
import numpy as np
import time
import datetime
import pandas as pd
import numpy as np
import glob
import re
import math


def add_csv_data(csv_row_data, adding):
    if adding is None or np.isnan(adding):
        return csv_row_data + ','
    return csv_row_data + ',' + str(adding)


def add_csv_data_no_nan_check(csv_row_data, adding):
    return csv_row_data + ',' + str(adding)


# 外れ値を判定しマスクを生成
def detect_outliers(series, window_size, threshold):
    rolling_mean = series.rolling(window=window_size, min_periods=1).mean()
    rolling_std = series.rolling(window=window_size, min_periods=1).std()
    z_scores = np.abs((series - rolling_mean) / rolling_std)
    return z_scores > threshold

# 外れ値を除外して補完
def outlier_and_interp(x, y, window_size, threshold):

    data = {
        'x': x,
        'y': y
    }

    df = pd.DataFrame(data)

    # y軸に対して外れ値検出
    is_outlier = detect_outliers(df['y'], window_size, threshold)

    # 外れ値をNaNに置き換え
    df['y_no_outliers'] = df['y'].where(~is_outlier)

    # 欠損値を線形補完
    df['y_interpolated'] = df['y_no_outliers'].interpolate(method='linear', limit_direction='both')

    return np.array(df['y_interpolated'])


def calculate_heading_in_radians(x1, y1, x2, y2):
    """
    2つの座標点間の方位角をラジアンで計算します。

    Parameters:
    - x1, y1: 最初の点の座標
    - x2, y2: 2番目の点の座標

    Returns:
    - heading: ラジアンでの方位角（進行方向）
    """
    # 2点間の差分を計算
    delta_x = x2 - x1
    delta_y = y2 - y1

    # math.atan2は、x軸に対する方位角をラジアンで返す
    heading = math.atan2(delta_y, delta_x)

    return heading


# 移動平均（遅れ補正あり）
def moving_avg(data, window_size):

    series = pd.Series(data)

    # 移動平均を計算
    moving_average = series.rolling(window=window_size).mean()

    # 遅れ調整のために移動平均の結果をシフト
    shifted_moving_average = moving_average.shift(-(int(window_size/2)))

    # 直近の値でNaNを埋める
    series = pd.Series(shifted_moving_average)
    filled_series = series.ffill().bfill()

    # 結果を配列に戻す
    filled_array = filled_series.to_numpy()

    return filled_array


def do_process(df_front_frame, ego_lane_data_json, lane_data_file, fps):

    f = np.array(df_front_frame['frame'])

    frame_wl_map = {}
    for val in ego_lane_data_json['results']:
        frame = val['frame']

        left_wl_ok = False
        right_wl_ok = False

        id_wl_map = {}

        for val_2 in val['whiteline_distance']:
            whiteline_id = val_2['whiteline_id']
            p1_dx = val_2['accuracy_limit_point_dy']
            p1_dy = val_2['accuracy_limit_point_dx']
            p2_dx = val_2['image_bottom_point_dy']
            p2_dy = val_2['image_bottom_point_dx']

            wl_data = [p1_dx, p1_dy, p2_dx, p2_dy]
            id_wl_map[whiteline_id] = wl_data

            if whiteline_id == 0:
                if abs(p2_dy) < 4.0:
                    left_wl_ok = True
            elif whiteline_id == 1:
                if abs(p2_dy) < 4.0:
                    right_wl_ok = True

        if left_wl_ok and right_wl_ok:
            frame_wl_map[frame] = id_wl_map


    wl_data_ary = []

    # サイズを指定
    i, j = 3, 4

    # NaNで初期化
    wl_data_ary = [[np.nan for _ in range(16)] for _ in range(len(f))]
    #print(wl_data_ary)

    for i in range(0, len(f)):
        if f[i] in frame_wl_map:
            id_wl_map = frame_wl_map[f[i]]
            k = 0
            for j in range(-1, 3):
                if j in id_wl_map:
                    wl_data = id_wl_map[j]
                    wl_data_ary[i][k] = wl_data[0]
                    wl_data_ary[i][k+1] = wl_data[1]
                    wl_data_ary[i][k+2] = wl_data[2]
                    wl_data_ary[i][k+3] = wl_data[3]
                k += 4

    #print(wl_data_ary)

    no_outlier_ma_ary = []
    for j in range(0, 16):
        column = [row[j] for row in wl_data_ary]
        no_outlier = outlier_and_interp(f, column, fps, 0.8)
        #no_outlier_ma_ary.append(moving_avg(no_outlier, 15))
        no_outlier_ma_ary.append(moving_avg(no_outlier, int(fps * 3)))

    #print(no_outlier_ma_ary)

    #left_wl_p1_dx_ary = [row[4] for row in no_outlier_ma_ary]
    #left_wl_p1_dy_ary = [row[5] for row in no_outlier_ma_ary]
    #left_wl_p2_dx_ary = [row[6] for row in no_outlier_ma_ary]
    #left_wl_p2_dy_ary = [row[7] for row in no_outlier_ma_ary]
    #right_wl_p1_dx_ary = [row[8] for row in no_outlier_ma_ary]
    #right_wl_p1_dy_ary = [row[9] for row in no_outlier_ma_ary]
    #right_wl_p2_dx_ary = [row[10] for row in no_outlier_ma_ary]
    #right_wl_p2_dy_ary = [row[11] for row in no_outlier_ma_ary]

    left_wl_p1_dx_ary = no_outlier_ma_ary[4]
    left_wl_p1_dy_ary = no_outlier_ma_ary[5]
    left_wl_p2_dx_ary = no_outlier_ma_ary[6]
    left_wl_p2_dy_ary = no_outlier_ma_ary[7]
    right_wl_p1_dx_ary = no_outlier_ma_ary[8]
    right_wl_p1_dy_ary = no_outlier_ma_ary[9]
    right_wl_p2_dx_ary = no_outlier_ma_ary[10]
    right_wl_p2_dy_ary = no_outlier_ma_ary[11]

    #print(len(left_wl_p1_dx_ary))

    headings = []
    for i in range(0, len(f)):
        mid_point_p2_x = left_wl_p2_dx_ary[i] + (right_wl_p2_dx_ary[i] - left_wl_p2_dx_ary[i]) / 2
        mid_point_p2_y = left_wl_p2_dy_ary[i]
        mid_point_p1_x = left_wl_p1_dx_ary[i] + (right_wl_p1_dx_ary[i] - left_wl_p1_dx_ary[i]) / 2
        mid_point_p1_y = left_wl_p1_dy_ary[i]
        heading = calculate_heading_in_radians(mid_point_p2_x, mid_point_p2_y, mid_point_p1_x, mid_point_p1_y)
        headings.append(heading)

    out_csv_file = open(lane_data_file, mode='w')
    
    header = 'frame,left_wl_p1_dx,left_wl_p1_dy,left_wl_p2_dx,left_wl_p2_dy,right_wl_p1_dx,right_wl_p1_dy,right_wl_p2_dx,right_wl_p2_dy,lane_width,heading,'
    header += 'left2_wl_p1_dx,left2_wl_p1_dy,left2_wl_p2_dx,left2_wl_p2_dy,right2_wl_p1_dx,right2_wl_p1_dy,right2_wl_p2_dx,right2_wl_p2_dy\n'
    out_csv_file.write(header)

    for i in range(0, len(f)):
        #print(i)
        row_data = str(f[i])

        row_data = add_csv_data(row_data, left_wl_p1_dx_ary[i])
        row_data = add_csv_data(row_data, left_wl_p1_dy_ary[i])
        row_data = add_csv_data(row_data, left_wl_p2_dx_ary[i])
        row_data = add_csv_data(row_data, left_wl_p2_dy_ary[i])
        row_data = add_csv_data(row_data, right_wl_p1_dx_ary[i])
        row_data = add_csv_data(row_data, right_wl_p1_dy_ary[i])
        row_data = add_csv_data(row_data, right_wl_p2_dx_ary[i])
        row_data = add_csv_data(row_data, right_wl_p2_dy_ary[i])

        lane_width = right_wl_p2_dy_ary[i] - left_wl_p2_dy_ary[i]
        row_data = add_csv_data(row_data, lane_width)

        row_data = add_csv_data(row_data, headings[i])

        for j in range(0, 4):
            row_data = add_csv_data(row_data, no_outlier_ma_ary[j][i])

        for j in range(12, 16):
            row_data = add_csv_data(row_data, no_outlier_ma_ary[j][i])

        out_csv_file.write(row_data + '\n')

    out_csv_file.close()

