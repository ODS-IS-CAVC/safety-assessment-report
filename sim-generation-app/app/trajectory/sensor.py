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


# 移動平均（遅れ補正あり）
def moving_avg(data, window_size):

    series = pd.Series(data)

    # 移動平均を計算
    moving_average = series.rolling(window=window_size).mean()

    # 遅れ調整のために移動平均の結果をシフト
    shifted_moving_average = moving_average.shift(-(int(window_size/2)))

    return shifted_moving_average


def do_process(df_front_frame, df_sensor, sensor_file, time_step, fps):

    if df_sensor is not None:
        df_merged = pd.merge_asof(df_front_frame, df_sensor, left_on='frame_time', right_on='elapsed_time', direction='nearest')
        df_merged.drop(columns=['elapsed_time'], inplace=True)
        df_merged.drop(columns=['datetime'], inplace=True)
        df_merged.to_csv(sensor_file, header=True, index=False)
    else:
        return

    df = pd.read_csv(sensor_file, header=0, index_col=False)

    f = np.array(df['frame'])
    ft = np.array(df['frame_time'])
    d = np.array(df['day'])
    t = np.array(df['time'])
    gx = np.array(df['gx'])
    gy = np.array(df['gy'])
    gz = np.array(df['gz'])
    lat = np.array(df['latitude'])
    lon = np.array(df['longitude'])
    spd = np.array(df['speed'])

    # 移動平均処理
    gx_ma_ary = moving_avg(gx, fps)
    gy_ma_ary = moving_avg(gy, fps)
    gz_ma_ary = moving_avg(gz, fps)
    spd_ma_ary = moving_avg(spd, fps)

    # 車速ベースの前後方向移動距離の計算
    spd_m_per_s = spd * (1000 / 3600)
    dst = np.cumsum(spd_m_per_s * time_step)

    # 車速ベースの前後方向加速度の計算
    spd_ma_m_per_s_ary = spd_ma_ary * (1000 / 3600)
    gx_from_speed_ary = []
    gx_from_speed_ary.append(np.nan)
    for i in range(0, len(spd_ma_m_per_s_ary)-1):
        tmp_gx = (spd_ma_m_per_s_ary[i+1] - spd_ma_m_per_s_ary[i]) / time_step
        gx_from_speed_ary.append(tmp_gx)
    gx_from_speed_ary = np.array(gx_from_speed_ary)
    gx_from_speed_ary = gx_from_speed_ary / 9.80665
    gx_from_speed_ma_ary = moving_avg(gx_from_speed_ary, fps)


    out_csv_file = open(sensor_file, mode='w')
    out_csv_file.write('frame,frame_time,day,time,gx,gy,gz,gx_ma,gy_ma,gz_ma,latitude,longitude,speed,speed_ma,gx_from_speed,gx_from_speed_ma,traveling_distance\n')

    for i in range(0, len(f)):
        #print(i)
        row_data = str(f[i])
        row_data = add_csv_data(row_data, ft[i])
        row_data = add_csv_data_no_nan_check(row_data, d[i])
        row_data = add_csv_data_no_nan_check(row_data, t[i])

        row_data = add_csv_data(row_data, gx[i])
        row_data = add_csv_data(row_data, gy[i])
        row_data = add_csv_data(row_data, gz[i])

        row_data = add_csv_data(row_data, gx_ma_ary[i])
        row_data = add_csv_data(row_data, gy_ma_ary[i])
        row_data = add_csv_data(row_data, gz_ma_ary[i])

        row_data = add_csv_data(row_data, lat[i])
        row_data = add_csv_data(row_data, lon[i])

        row_data = add_csv_data(row_data, spd[i])
        row_data = add_csv_data(row_data, spd_ma_ary[i])
        row_data = add_csv_data(row_data, gx_from_speed_ary[i])
        row_data = add_csv_data(row_data, gx_from_speed_ma_ary[i])
        row_data = add_csv_data(row_data, dst[i])

        out_csv_file.write(row_data + '\n')

    out_csv_file.close()

