import os
import sys
import cv2
import shutil
import pandas as pd
import numpy as np
from datetime import datetime
from tqdm import tqdm

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


def imread(filename, flags=cv2.IMREAD_COLOR, dtype=np.uint8):
    try:
        n = np.fromfile(filename, dtype)
        img = cv2.imdecode(n, flags)
        return img
    except Exception as e:
        print(e)
        return None


def imwrite(filename, img, params=None):
    try:
        ext = os.path.splitext(filename)[1]
        result, n = cv2.imencode(ext, img, params)
        
        if result:
            with open(filename, mode='w+b') as f:
                n.tofile(f)
            return True
        else:
            return False
    except Exception as e:
        print(e)
        return False

bgr_darkred = (0, 0, 139)
bgr_red = (0, 0, 255)
bgr_yellow = (0, 255, 255)
bgr_green = (0, 255, 0)
bgr_white = (255, 255, 255)

def get_color(sct):
    if 0 <= sct and sct <= 1:
        return bgr_red
    if 1 < sct and sct <= 2:
        return bgr_yellow
    if 2 < sct and sct <= 3:
        return bgr_green
    return bgr_white


def draw_colored_bar_v(image, value, max_value, position, max_length, bar_width):
    # 色の定義
    colors = [
        (0, 0, 255),    # Red
        (0, 255, 255),  # Yellow
        (0, 255, 0),    # Green
        (255, 255, 255) # White
    ]

    # 区間ごとに描画
    thresholds = [1, 2, 3, max_value]
    accumulated_value = 0

    for i, threshold in enumerate(thresholds):
        # 現在のセグメントの範囲を計算
        segment_value = min(value, threshold) - accumulated_value
        segment_height = (segment_value / max_value) *max_length

        # 下から上に伸びる線分を描画
        cv2.rectangle(
            image,
            (position[0], int(position[1] - segment_height)),
            (position[0] + bar_width, position[1]),
            colors[i],
            cv2.FILLED
        )

        # 次のセグメントの開始位置を更新
        position = (position[0], int(position[1] - segment_height))
        accumulated_value += segment_value

        if accumulated_value >= value:
            break


def draw_colored_bar_h(image, value, max_value, position, max_length, bar_height):
    # 色の定義
    colors = [
        (0, 0, 255),    # Red
        (0, 255, 255),  # Yellow
        (0, 255, 0),    # Green
        (255, 255, 255) # White
    ]

    # 区間ごとに描画
    thresholds = [1, 2, 3, max_value]
    accumulated_value = 0
    
    current_x = position[0]

    for i, threshold in enumerate(thresholds):
        # 現在のセグメントの範囲を計算
        segment_value = min(value, threshold) - accumulated_value
        segment_width = (segment_value / max_value) * max_length

        # 横に伸びる線分を描画
        cv2.rectangle(
            image,
            (int(current_x), position[1]),
            (int(current_x + segment_width), position[1] + bar_height),
            colors[i],
            cv2.FILLED
        )

        # 次のセグメントの開始位置を更新
        current_x += segment_width
        accumulated_value += segment_value

        if accumulated_value >= value:
            break


def make_movie(ego_data_file, front_lane_detection_results_json, rear_lane_detection_results_json, front_near_vehicles_file, front_seg_json, front_img_dir, rear_img_dir, movie_file, tmp_dir, out_graph_dir, fps):

    df = pd.read_csv(ego_data_file, header=0, index_col=False)
    f = np.array(df['frame'])
    t = np.array(df['frame_time'])

    day_vals = None
    time_vals = None
    if 'day' in df.columns:
        day_vals = np.array(df['day'])
        time_vals = np.array(df['time'])

    lat = None
    lon = None
    if 'lat' in df.columns:
        lat = np.array(df['latitude'])
        lon = np.array(df['longitude'])

    df_near = pd.read_csv(front_near_vehicles_file, header=0, index_col=False)
    frame = np.array(df_near['frame'])
    ahead_id = np.array(df_near['ahead_id'])
    ahead_sctx = np.array(df_near['ahead_sctx'])
    ahead_scty = np.array(df_near['ahead_scty'])
    adjacent_l_id = np.array(df_near['adjacent_l_id'])
    adjacent_l_sctx = np.array(df_near['adjacent_l_sctx'])
    adjacent_l_scty = np.array(df_near['adjacent_l_scty'])
    adjacent_r_id = np.array(df_near['adjacent_r_id'])
    adjacent_r_sctx = np.array(df_near['adjacent_r_sctx'])
    adjacent_r_scty = np.array(df_near['adjacent_r_scty'])

    front_frame_whiteline_map = {}
    for data in front_lane_detection_results_json['results']:
        frame = data['frame']
        whiteline_datas = data['lane_data']
        front_frame_whiteline_map[frame] = whiteline_datas

    rear_frame_whiteline_map = {}
    for data in rear_lane_detection_results_json['results']:
        frame = data['frame']
        whiteline_datas = data['lane_data']
        rear_frame_whiteline_map[frame] = whiteline_datas

    front_frame_vehicle_map = {}
    if front_seg_json is not None:
        for val in front_seg_json['results']:
            frame = val['frame']
            vid_data_map = {}
            front_frame_vehicle_map[frame] = vid_data_map
            tensor_datas = val['tensor_data']
            for tensor_data in tensor_datas:
                vid = 'f' + str(tensor_data['ID'])
                vid_data_map[vid] = tensor_data

    #fps = 15
    #fmt = cv2.VideoWriter_fourcc('H', '2', '6', '4')
    fmt = cv2.VideoWriter_fourcc('M', 'P', '4', 'V')

    writer = cv2.VideoWriter(movie_file, fmt, fps, (1920, 720))


    font = cv2.FONT_HERSHEY_SIMPLEX

    img1 = np.ones((640, 360, 3),np.uint8)*255
    img2 = np.ones((640, 360, 3),np.uint8)*255

    blank = np.ones((640, 360, 3),np.uint8)*255
    blank = cv2.resize(blank, (640, 360))

    #ahead_car_sct_threshold = 3
    #cutin_sct_threshold = 3
    ahead_car_sct_threshold = 8
    cutin_sct_threshold = 8

    cur_map = None
    if os.path.isfile(os.path.join(tmp_dir, 'map.png')):
        cur_map = imread(os.path.join(tmp_dir, 'map.png'))

    bar = tqdm(total=len(f), dynamic_ncols=True, desc="make movie")
    for i in range(0, len(f)):
        frame = f[i]

        front_img_file = front_img_dir + str(frame) + '.png'
        if os.path.isfile(front_img_file):
            img1 = imread(front_img_file)

            if frame in front_frame_whiteline_map:
                front_wl_datas = front_frame_whiteline_map[frame]
                for whiteline_data in front_wl_datas:
                    id = whiteline_data["ID"]
                    if id < -1 or 2 < id:
                        continue

                    p1_x = whiteline_data["AccuracyLimitPoint_X"]
                    p1_y = whiteline_data["AccuracyLimitPoint_Y"]
                    p2_x = whiteline_data["ImageBottomPoint_X"]
                    p2_y = whiteline_data["ImageBottomPoint_Y"]
                    #color = ( 0, 255, 255)
                    color = ( 0, 255, 0)
                    '''
                    if id == 0:
                        color = ( 0, 0, 255)
                    elif id == 1:
                        color = ( 255, 0, 0)
                    elif id == 2:
                        color = ( 255, 255, 0)
                    elif id == -1:
                        color = ( 255, 0, 255)
                    elif id == -2:
                        color = ( 0, 255, 255)
                    '''
                    cv2.line(img1, (p1_x, p1_y), (p2_x, p2_y), color, 3)

                    '''
                    if ahead_id[i] is not None:
                        if frame in front_frame_vehicle_map:
                            vid_data_map = front_frame_vehicle_map[frame]
                            if ahead_id[i] in vid_data_map:
                                tensor_data = vid_data_map[ahead_id[i]]
                                BBox_Xmin = int(tensor_data['BBox_Xmin'])
                                BBox_Xmax = int(tensor_data['BBox_Xmax'])
                                BBox_Ymin = int(tensor_data['BBox_Ymin'])
                                BBox_Ymax = int(tensor_data['BBox_Ymax'])
                                height = BBox_Ymax - BBox_Ymin
                                width = BBox_Xmax - BBox_Xmin

                                if 0 <= ahead_sctx[i] and ahead_sctx[i] <= ahead_car_sct_threshold:
                                    bar_width = int(width / 8)
                                    draw_colored_bar_v(img1, ahead_sctx[i], ahead_car_sct_threshold, (BBox_Xmin - bar_width, BBox_Ymax), height, bar_width)

                    if adjacent_l_id[i] is not None:
                        if frame in front_frame_vehicle_map:
                            vid_data_map = front_frame_vehicle_map[frame]
                            if adjacent_l_id[i] in vid_data_map:
                                tensor_data = vid_data_map[adjacent_l_id[i]]
                                BBox_Xmin = int(tensor_data['BBox_Xmin'])
                                BBox_Xmax = int(tensor_data['BBox_Xmax'])
                                BBox_Ymin = int(tensor_data['BBox_Ymin'])
                                BBox_Ymax = int(tensor_data['BBox_Ymax'])
                                width = BBox_Xmax - BBox_Xmin
                                height = BBox_Ymax - BBox_Ymin

                                if 0 <= adjacent_l_scty[i] and adjacent_l_scty[i] <= cutin_sct_threshold:
                                    bar_height = int(height / 8)
                                    draw_colored_bar_h(img1, adjacent_l_scty[i], cutin_sct_threshold, (BBox_Xmin, BBox_Ymax), width, bar_height)

                                    if 0 <= adjacent_l_sctx[i] and adjacent_l_sctx[i] <= cutin_sct_threshold:
                                        bar_width = int(width / 8)
                                        draw_colored_bar_v(img1, adjacent_l_sctx[i], cutin_sct_threshold, (BBox_Xmin - bar_width, BBox_Ymax), height, bar_width)

                    if adjacent_r_id[i] is not None:
                        if frame in front_frame_vehicle_map:
                            vid_data_map = front_frame_vehicle_map[frame]
                            if adjacent_r_id[i] in vid_data_map:
                                tensor_data = vid_data_map[adjacent_r_id[i]]
                                BBox_Xmin = int(tensor_data['BBox_Xmin'])
                                BBox_Xmax = int(tensor_data['BBox_Xmax'])
                                BBox_Ymin = int(tensor_data['BBox_Ymin'])
                                BBox_Ymax = int(tensor_data['BBox_Ymax'])
                                width = BBox_Xmax - BBox_Xmin
                                height = BBox_Ymax - BBox_Ymin

                                if 0 <= adjacent_r_scty[i] and adjacent_r_scty[i] <= cutin_sct_threshold:
                                    bar_height = int(height / 8)
                                    draw_colored_bar_h(img1, adjacent_r_scty[i], cutin_sct_threshold, (BBox_Xmin, BBox_Ymax), width, bar_height)

                                    if 0 <= adjacent_r_sctx[i] and adjacent_r_sctx[i] <= cutin_sct_threshold:
                                        bar_width = int(width / 8)
                                        draw_colored_bar_v(img1, adjacent_r_sctx[i], cutin_sct_threshold, (BBox_Xmin - bar_width, BBox_Ymax), height, bar_width)
                    '''


        rear_img_file = rear_img_dir + str(frame) + '.png'
        if os.path.isfile(rear_img_file):
            img2 = imread(rear_img_file)

            if frame in rear_frame_whiteline_map:
                rear_wl_datas = rear_frame_whiteline_map[frame]
                for whiteline_data in rear_wl_datas:
                    id = whiteline_data["ID"]
                    if id < -1 or 2 < id:
                        continue

                    p1_x = whiteline_data["AccuracyLimitPoint_X"]
                    p1_y = whiteline_data["AccuracyLimitPoint_Y"]
                    p2_x = whiteline_data["ImageBottomPoint_X"]
                    p2_y = whiteline_data["ImageBottomPoint_Y"]
                    #color = ( 0, 255, 255)
                    color = ( 0, 255, 0)
                    '''
                    if id == 0:
                        color = ( 0, 0, 255)
                    elif id == 1:
                        color = ( 255, 0, 0)
                    elif id == 2:
                        color = ( 255, 255, 0)
                    elif id == -1:
                        color = ( 255, 0, 255)
                    elif id == -2:
                        color = ( 0, 255, 255)
                    '''
                    cv2.line(img2, (p1_x, p1_y), (p2_x, p2_y), color, 3)

        img3 = blank
        if cur_map is not None:
            map_file = os.path.join(out_graph_dir, 'map_' + str(frame) + '.png')
            if os.path.isfile(map_file):
                img3 = imread(map_file)
                cur_map = img3
            else:
                img3 = cur_map
        else:
            coord_file = os.path.join(out_graph_dir, 'coord_' + str(frame) + '.png')
            if os.path.isfile(coord_file):
                img3 = imread(coord_file)
            else:
                if os.path.isfile(os.path.join(tmp_dir, 'coord.png')):
                    img3 = imread(os.path.join(tmp_dir, 'coord.png'))
                else:
                    img3 = blank

        gx_file = os.path.join(out_graph_dir, 'gx_' + str(frame) + '.png')
        if os.path.isfile(gx_file):
            img4 = imread(gx_file)
        else:
            if os.path.isfile(os.path.join(tmp_dir, 'gx.png')):
                img4 = imread(os.path.join(tmp_dir, 'gx.png'))
            else:
                img4 = blank

        spd_file = os.path.join(out_graph_dir, 'spd_' + str(frame) + '.png')
        if os.path.isfile(spd_file):
            img5 = imread(spd_file)
        else:
            if os.path.isfile(os.path.join(tmp_dir, 'spd.png')):
                img5 = imread(os.path.join(tmp_dir, 'spd.png'))
            else:
                img5 = blank

        #tbl_file = tmp_dir + 'table.png'
        #if os.path.isfile(tbl_file):
        #    img8 = imread(tbl_file)
        #else:
        #    img8 = blank

        topview_file = os.path.join(out_graph_dir, 'topview_' + str(frame) + '.png')
        if os.path.isfile(topview_file):
            img6 = imread(topview_file)
        else:
            img6 = blank

        img1 = cv2.resize(img1, (640, 360))
        img2 = cv2.resize(img2, (640, 360))
        img3 = cv2.resize(img3, (640, 360))
        img4 = cv2.resize(img4, (640, 360))
        img5 = cv2.resize(img5, (640, 360))
        img6 = cv2.resize(img6, (640, 360))

        im_h1 = cv2.hconcat([img1, img2, img3])
        im_h2 = cv2.hconcat([img5, img4, img6])

        im = cv2.vconcat([im_h1, im_h2])

        #font_scale = 1.0
        font_scale = 0.8

        if day_vals is not None:
            date_obj = datetime.strptime(day_vals[i], "%Y/%m/%d")
            #formatted_date = date_obj.strftime("%Y.%#m.%#d")
            formatted_date = date_obj.strftime("%Y-%m-%d")

            new_time_str = time_vals[i].split('.')[0]

            #txt = formatted_date + ' ' + new_time_str + ' ' + ' Lat:{:.5f} Long:{:.5f}'.format(lat[i],lon[i]) + ' Frame:' + str(f[i]) + ' Time:{:.3f}s'.format(t[i])
            txt = formatted_date + ' ' + new_time_str + ' ' + ' Frame:' + str(f[i]) + ' Time:{:.3f}s'.format(t[i])
        else:
            txt = 'Frame:' + str(f[i]) + ' Time:{:.3f}s'.format(t[i])

        # 白い輪郭を描く
        cv2.putText(im, txt, (10, 30), font, font_scale, (255, 255, 255), 5, cv2.LINE_AA)

        # 黒い文字を描く
        cv2.putText(im, txt, (10, 30), font, font_scale, (0, 0, 0), 2, cv2.LINE_AA)

        writer.write(im)

        bar.update(1)

    writer.release()

    bar.close()

