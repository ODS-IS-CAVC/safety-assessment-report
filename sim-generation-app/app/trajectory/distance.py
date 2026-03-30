import os
import sys
import glob
import pathlib
import re
import csv
import time
import datetime
import numpy as np
import pandas as pd

def add_csv_data(csv_row_data, adding):
    if np.isnan(adding):
        return csv_row_data + ','
    return csv_row_data + ',' + str(adding)


# 移動平均（遅れ補正あり）
def moving_avg(data, window_size):

    series = pd.Series(data)

    # 移動平均を計算
    moving_average = series.rolling(window=window_size).mean()

    # 遅れ調整のために移動平均の結果をシフト
    shifted_moving_average = moving_average.shift(-(int(window_size/2)))

    return shifted_moving_average


def do_ma(distance_file, window_size):

    df = pd.read_csv(distance_file, header=0, index_col=False)

    frame = np.array(df['frame'])
    dx = np.array(df['dx_from_front'])
    dy_l = np.array(df['dy_center_to_other_left'])
    dy_r = np.array(df['dy_center_to_other_right'])

    if len(frame) == 0:
        out_csv_file = open(distance_file, mode='w')
        out_csv_file.write('frame,dx_from_front,dy_center_to_other_left,dy_center_to_other_right,dx_from_front_ma,dy_center_to_other_left_ma,dy_center_to_other_right_ma\n')
        out_csv_file.close()
        return

    if len(frame) == 1:
        all_frames = frame
    else:
        all_frames = list(range(frame[0], frame[-1], 2))
    #print(all_frame)

    all_frames = np.array(all_frames)

    # 欠損値線形補間処理
    dx_ary = np.interp(all_frames, frame, dx)
    dy_l_ary = np.interp(all_frames, frame, dy_l)
    dy_r_ary = np.interp(all_frames, frame, dy_r)

    # 移動平均 (距離)
    dx_ma_ary = moving_avg(dx_ary, window_size)
    dy_l_ma_ary = moving_avg(dy_l_ary, window_size)
    dy_r_ma_ary = moving_avg(dy_r_ary, window_size)

    out_csv_file = open(distance_file, mode='w')
    out_csv_file.write('frame,dx_from_front,dy_center_to_other_left,dy_center_to_other_right,dx_from_front_ma,dy_center_to_other_left_ma,dy_center_to_other_right_ma\n')

    for i in range(0, len(all_frames)):
        #print(i)
        row_data = str(all_frames[i])
        row_data = add_csv_data(row_data, dx_ary[i])
        row_data = add_csv_data(row_data, dy_l_ary[i])
        row_data = add_csv_data(row_data, dy_r_ary[i])
        row_data = add_csv_data(row_data, dx_ma_ary[i])
        row_data = add_csv_data(row_data, dy_l_ma_ary[i])
        row_data = add_csv_data(row_data, dy_r_ma_ary[i])

        out_csv_file.write(row_data + '\n')

    out_csv_file.close()

class Lane:
    def __init__(self, frame, left_wl_p1_dx, left_wl_p1_dy, left_wl_p2_dx, left_wl_p2_dy, right_wl_p1_dx, right_wl_p1_dy, right_wl_p2_dx, right_wl_p2_dy, lane_width):
        self.frame = frame
        self.left_wl_p1_dx = left_wl_p1_dx
        self.left_wl_p1_dy = left_wl_p1_dy
        self.left_wl_p2_dx = left_wl_p2_dx
        self.left_wl_p2_dy = left_wl_p2_dy
        self.right_wl_p1_dx = right_wl_p1_dx
        self.right_wl_p1_dy = right_wl_p1_dy
        self.right_wl_p2_dx = right_wl_p2_dx
        self.right_wl_p2_dy = right_wl_p2_dy
        self.lane_width = lane_width

def do_process(segmentation_detection_result_with_lane_json, width, length, cam_pos, ego_data_file, lane_data_file, out_dir, front, fps):

    f_x = cam_pos[0]
    f_y = cam_pos[1]
    f_z = cam_pos[2]
    r_x = cam_pos[3]
    r_y = cam_pos[4]
    r_z = cam_pos[5]

    frame_wl_map = {}

    if os.path.isfile(lane_data_file):
        df_lane = pd.read_csv(lane_data_file, header=0, index_col=False)
        for index, row in df_lane.iterrows():
            frame = row['frame']
            lane = Lane(frame, 
                        row['left_wl_p1_dx'], row['left_wl_p1_dy'], row['left_wl_p2_dx'], row['left_wl_p2_dy'],
                        row['right_wl_p1_dx'], row['right_wl_p1_dy'], row['right_wl_p2_dx'], row['right_wl_p2_dy'],
                        row['lane_width'])
            frame_wl_map[frame] = lane

    vid_data_map = {}

    if segmentation_detection_result_with_lane_json is not None:
        for data in segmentation_detection_result_with_lane_json['results']:
            frame = data['frame']

            for data_2 in data['segmentations']:
                vid = data_2['obj_id']

                if vid not in vid_data_map:
                     vid_data_map[vid] = []
                vid_data_list =vid_data_map[vid]

                distance_y = None
                left_distance_x = None
                right_distance_x = None

                for data_3 in data_2['calculate']:
                    pos = data_3['calculate_position']
                    if pos == 'BBox_center':
                        distance_y = data_3['distance'][1]
                    elif pos == 'Front_Bottom_Left':
                        left_distance_x = data_3['distance'][0]
                        left_distance_x_wl_0 = None
                        left_distance_x_wl_1 = None
                        for data_4 in data_3['whiteline_distance']:
                             wl_id = data_4['whiteline_id']
                             if wl_id == 0:
                                 left_distance_x_wl_0 = data_4['whiteline_dx']
                             elif wl_id == 1:
                                 left_distance_x_wl_1 = data_4['whiteline_dx']
                    elif pos == 'Rear_Bottom_Right':
                        right_distance_x = data_3['distance'][0]
                        right_distance_x_wl_0 = None
                        right_distance_x_wl_1 = None
                        for data_4 in data_3['whiteline_distance']:
                             wl_id = data_4['whiteline_id']
                             if wl_id == 0:
                                 right_distance_x_wl_0 = data_4['whiteline_dx']
                             elif wl_id == 1:
                                 right_distance_x_wl_1 = data_4['whiteline_dx']

                if distance_y is not None and left_distance_x is not None and right_distance_x is not None:
                    vid_data_list.append([frame, distance_y, left_distance_x, left_distance_x_wl_0, left_distance_x_wl_1, right_distance_x, right_distance_x_wl_0, right_distance_x_wl_1])

    if front:
        prefix = 'f'
    else:
        prefix = 'r'

    for vid, datas in vid_data_map.items():

        distance_file = os.path.join(out_dir, 'distance_' + prefix + str(vid) + '.csv')
        out_csv_file = open(distance_file, mode='w')
        out_csv_file.write('frame,dx_from_front,dy_center_to_other_left,dy_center_to_other_right\n')

        sorted_datas = sorted(datas, key=lambda point: datas[0])
        for data in sorted_datas:
            frame = data[0]
            distance_y = data[1]
            left_distance_x = data[2]
            left_distance_x_wl_0 = data[3]
            left_distance_x_wl_1 = data[4]
            right_distance_x = data[5]
            right_distance_x_wl_0 = data[6]
            right_distance_x_wl_1 = data[7]

            if right_distance_x_wl_0 is None or left_distance_x_wl_1 is None:
                continue

            if frame in frame_wl_map:
                lane = frame_wl_map[frame]
            else:
                continue

            if front:
                dx = distance_y - f_x

                ego_to_line_l = lane.left_wl_p2_dy - f_y
                ego_to_line_r = lane.right_wl_p2_dy - f_y

                if left_distance_x > 0:
                    if left_distance_x_wl_1 is None or right_distance_x_wl_1 is None:
                        continue
                    dy_center_to_l = ego_to_line_r + (left_distance_x - left_distance_x_wl_1)
                    dy_center_to_r = ego_to_line_r + (right_distance_x - right_distance_x_wl_1)
                else:
                    if left_distance_x_wl_0 is None or right_distance_x_wl_0 is None:
                        continue
                    dy_center_to_l = ego_to_line_l + (left_distance_x - left_distance_x_wl_0)
                    dy_center_to_r = ego_to_line_l + (right_distance_x - right_distance_x_wl_0)

                dy_center_to_l = -dy_center_to_l
                dy_center_to_r = -dy_center_to_r

            else:
                dx = -(distance_y - r_x) - length

                ego_to_line_l = lane.left_wl_p2_dy - r_y
                ego_to_line_r = lane.right_wl_p2_dy - r_y

                if left_distance_x > 0:
                    if left_distance_x_wl_1 is None or right_distance_x_wl_1 is None:
                        continue
                    dy_center_to_l = ego_to_line_r + (left_distance_x - left_distance_x_wl_1)
                    dy_center_to_r = ego_to_line_r + (right_distance_x - right_distance_x_wl_1)
                else:
                    if left_distance_x_wl_0 is None or right_distance_x_wl_0 is None:
                        continue
                    dy_center_to_l = ego_to_line_l + (left_distance_x - left_distance_x_wl_0)
                    dy_center_to_r = ego_to_line_l + (right_distance_x - right_distance_x_wl_0)

                tmp_dy_center_to_l = dy_center_to_l
                dy_center_to_l = dy_center_to_r
                dy_center_to_r = tmp_dy_center_to_l

            out_csv_file.write(str(frame) + ',' + str(dx) + ',' + str(dy_center_to_l) + ',' + str(dy_center_to_r) + '\n')

        out_csv_file.close()
        
        if len(sorted_datas) > 0:
            do_ma(distance_file, fps)

