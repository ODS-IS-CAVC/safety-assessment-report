import os
import sys
import cv2
import shutil
import glob
import re
from natsort import natsorted
import pandas as pd
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import Counter
from collections import deque
from tqdm import tqdm


def add_csv_data(csv_row_data, adding):
    if adding is None or np.isnan(adding):
        return csv_row_data + ','
    return csv_row_data + ',' + str(adding)

def add_csv_data_no_nan_check(csv_row_data, adding):
    if adding is None:
        return csv_row_data + ','
    return csv_row_data + ',' + str(adding)

class ObjectData:

    def __init__(self, vid, cls, frame, dx, dy_l, dy_r, sctx, scty, sdx, scb1x, scb2x, scb3x, sdy, scb1y, scb2y, scb3y):
        self.vid = vid
        self.cls = cls
        self.frame = frame
        self.dx = dx
        self.dy_l = dy_l
        self.dy_r = dy_r
        self.sctx = sctx
        self.scty = scty

        self.sdx = sdx
        self.scb1x = scb1x
        self.scb2x = scb2x
        self.scb3x = scb3x

        self.sdy = sdy
        self.scb1y = scb1y
        self.scb2y = scb2y
        self.scb3y = scb3y


def most_frequent(strings):
    if not strings:
        return None

    counter = Counter(strings)
    most_common = counter.most_common(1)

    return most_common[0][0] if most_common else None


def get_objects_size(od):
    if od.cls == 'Car':
        owidth = 1.8
        olength = 4.7
    elif od.cls == 'motorcycle':
        owidth = 1.0
        olength = 2.0
    elif od.cls == 'Truck' or od.cls == 'Bus' or od.cls == 'Van':
        owidth = 2.5
        olength = 12.0
    else:
        owidth = 1.0
        olength = 1.0

    return owidth, olength


def calc_objects_pos(od):

    owidth, olength = get_objects_size(od)

    if od.dx >= 0:
        min_x = od.dx
        max_x = od.dx + olength
    else:
        min_x = od.dx - olength
        max_x = od.dx

    if od.dy_l < 0:
        # 自車の右側
        max_y = od.dy_l
        min_y = od.dy_l - owidth
    else:
        # 自車の左側
        max_y = od.dy_r + owidth
        min_y = od.dy_r

    return min_x, max_x, min_y, max_y

class Lane:
    def __init__(self, frame, left_wl_p1_dx, left_wl_p1_dy, left_wl_p2_dx, left_wl_p2_dy, right_wl_p1_dx, right_wl_p1_dy, right_wl_p2_dx, right_wl_p2_dy, lane_width, heading, left2_wl_p1_dx, left2_wl_p1_dy, left2_wl_p2_dx, left2_wl_p2_dy, right2_wl_p1_dx, right2_wl_p1_dy, right2_wl_p2_dx, right2_wl_p2_dy):
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
        self.heading = heading
        self.left2_wl_p1_dx = left2_wl_p1_dx
        self.left2_wl_p1_dy = left2_wl_p1_dy
        self.left2_wl_p2_dx = left2_wl_p2_dx
        self.left2_wl_p2_dy = left2_wl_p2_dy
        self.right2_wl_p1_dx = right2_wl_p1_dx
        self.right2_wl_p1_dy = right2_wl_p1_dy
        self.right2_wl_p2_dx = right2_wl_p2_dx
        self.right2_wl_p2_dy = right2_wl_p2_dy


def rotate_points(points, center, theta):
    # 回転行列
    rotation_matrix = np.array([[np.cos(theta), -np.sin(theta)],
                                [np.sin(theta),  np.cos(theta)]])
    # 座標を回転
    translated_points = points - center
    rotated_points = translated_points.dot(rotation_matrix) + center
    
    return rotated_points

def is_ahead_car(width, od):
    ego_half_width = width / 2
    if -ego_half_width < od.dy_l and od.dy_l < ego_half_width:
        return True

    if -ego_half_width < od.dy_r and od.dy_r < ego_half_width:
        return True

    return False


def is_adjacent_car_l(width, od):

    if is_ahead_car(width, od):
        return False

    if od.dy_l > 0:
        # 自車の左側
        return True

    return False


def is_adjacent_car_r(width, od):

    if is_ahead_car(width, od):
        return False

    if od.dy_l < 0:
        # 自車の右側
        return True

    return False


#color_sd = 'darkred'
#color_scb1 = 'red'
#color_scb2 = 'orange'
#color_scb3 = 'green'
#alpha_scb = 0.5

color_sd = (255/255, 0/255, 0/255)
color_scb1 = (255/255, 178/255, 102/255)
color_scb2 = (255/255, 255/255, 0/255)
color_scb3 = (102/255, 178/255, 255/255)
alpha_scb = 1.0


def plot_scb_x(plt, ego_max_x, ego_min_y, ego_width, od, travel_dist):

    tmp_min_x = ego_max_x + travel_dist
    plt.gca().add_patch(patches.Rectangle((tmp_min_x, ego_min_y), od.sdx, ego_width, color=color_sd, alpha=alpha_scb))

    tmp_min_x = tmp_min_x + od.sdx
    plt.gca().add_patch(patches.Rectangle((tmp_min_x, ego_min_y), od.scb1x - od.sdx, ego_width, color=color_scb1, alpha=alpha_scb))

    tmp_min_x = tmp_min_x + od.scb1x - od.sdx
    plt.gca().add_patch(patches.Rectangle((tmp_min_x, ego_min_y), od.scb2x - od.scb1x, ego_width, color=color_scb2, alpha=alpha_scb))

    tmp_min_x = tmp_min_x + od.scb2x -  od.scb1x
    plt.gca().add_patch(patches.Rectangle((tmp_min_x, ego_min_y), od.scb3x - od.scb2x, ego_width, color=color_scb3, alpha=alpha_scb))


def plot_scb_yl(plt, od, travel_dist):

    # 他車の情報
    owidth, olength = get_objects_size(od)
    min_x, max_x, min_y, max_y = calc_objects_pos(od)

    # 自車の左側から接近
    tmp_min_y = min_y - od.sdy
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_min_y), olength, od.sdy, color=color_sd, alpha=alpha_scb))

    tmp_min_y = tmp_min_y - (od.scb1y - od.sdy)
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_min_y), olength, od.scb1y - od.sdy, color=color_scb1, alpha=alpha_scb))

    tmp_min_y = tmp_min_y - (od.scb2y - od.scb1y)
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_min_y), olength, od.scb2y - od.scb1y, color=color_scb2, alpha=alpha_scb))

    tmp_min_y = tmp_min_y - (od.scb3y - od.scb2y)
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_min_y), olength, od.scb3y - od.scb2y, color=color_scb3, alpha=alpha_scb))


def plot_scb_yr(plt, od, travel_dist):

    # 他車の情報
    owidth, olength = get_objects_size(od)
    min_x, max_x, min_y, max_y = calc_objects_pos(od)

    # 自車の右側から接近
    tmp_max_y = max_y
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_max_y), olength, od.sdy, color=color_sd, alpha=alpha_scb))

    tmp_max_y = tmp_max_y + od.sdy
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_max_y), olength, od.scb1y - od.sdy, color=color_scb1, alpha=alpha_scb))

    tmp_max_y = tmp_max_y + od.scb1y - od.sdy
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_max_y), olength, od.scb2y - od.scb1y, color=color_scb2, alpha=alpha_scb))

    tmp_max_y = tmp_max_y + od.scb2y -  od.scb1y
    plt.gca().add_patch(patches.Rectangle((min_x + travel_dist, tmp_max_y), olength, od.scb3y - od.scb2y, color=color_scb3, alpha=alpha_scb))

def plot_opponent(opo, dist):
    min_x, max_x, min_y, max_y = calc_objects_pos(opo)
    v_tmp_x = [min_x, min_x, max_x, max_x, min_x]
    v_tmp_y = [min_y, max_y, max_y, min_y, min_y]
    plt.plot(v_tmp_x + dist, v_tmp_y, color="blue")
    plt.text(min_x + dist, max_y + 0.3, str(opo.vid), fontsize=10)

    txt = ''
    if 0 <= opo.sctx and opo.sctx <= 8:
        txt = 'SCTx:{:.1f}'.format(opo.sctx) + '\n'
    else:
        txt = 'SCTx:---\n'
    txt_scty = 'SCTy:---'
    if 0 <= opo.scty and opo.scty <= 8:
        txt_scty = 'SCTy:{:.1f}'.format(opo.scty)
    txt += txt_scty
    plt.text(max_x+2 + dist, min_y-1, txt, fontsize=10)


def do_process(ego_data_file, front_lane_data_file, rear_lane_data_file, width, length, front_seg_json, rear_seg_json, objects_dir, out_graph_dir, near_vehicles_file_name):

    # 自車の座標リスト
    ego_max_x = 0
    ego_min_x = -length
    ego_max_y = width / 2
    ego_min_y = -width / 2

    ego_x = [ego_max_x, ego_max_x, ego_min_x, ego_min_x, ego_max_x]
    ego_y = [ego_min_y, ego_max_y, ego_max_y, ego_min_y, ego_min_y]

    df_ego = pd.read_csv(ego_data_file, header=0, index_col=False)
    f = np.array(df_ego['frame'])

    front_frame_wl_map = {}
    if os.path.isfile(front_lane_data_file):
        df_front_lane = pd.read_csv(front_lane_data_file, header=0, index_col=False)
        for index, row in df_front_lane.iterrows():
            frame = row['frame']
            lane = Lane(frame, 
                        row['left_wl_p1_dx'], -row['left_wl_p1_dy'], row['left_wl_p2_dx'], -row['left_wl_p2_dy'],
                        row['right_wl_p1_dx'], -row['right_wl_p1_dy'], row['right_wl_p2_dx'], -row['right_wl_p2_dy'],
                        row['lane_width'], row['heading'],
                        row['left2_wl_p1_dx'], -row['left2_wl_p1_dy'], row['left2_wl_p2_dx'], -row['left2_wl_p2_dy'],
                        row['right2_wl_p1_dx'], -row['right2_wl_p1_dy'], row['right2_wl_p2_dx'], -row['right2_wl_p2_dy'])

            front_frame_wl_map[frame] = lane


    rear_frame_wl_map = {}
    if os.path.isfile(rear_lane_data_file):
        df_rear_lane = pd.read_csv(rear_lane_data_file, header=0, index_col=False)
        for index, row in df_rear_lane.iterrows():
            frame = row['frame']
            lane = Lane(frame, 
                        -row['left_wl_p1_dx'], row['left_wl_p1_dy'], -row['left_wl_p2_dx'], row['left_wl_p2_dy'],
                        -row['right_wl_p1_dx'], row['right_wl_p1_dy'], -row['right_wl_p2_dx'], row['right_wl_p2_dy'],
                        row['lane_width'], row['heading'],
                        -row['left2_wl_p1_dx'], row['left2_wl_p1_dy'], -row['left2_wl_p2_dx'], row['left2_wl_p2_dy'],
                        -row['right2_wl_p1_dx'], row['right2_wl_p1_dy'], -row['right2_wl_p2_dx'], row['right2_wl_p2_dy'])
            rear_frame_wl_map[frame] = lane


    # 移動距離
    if 'traveling_distance' in df_ego.columns:
        dst = np.array(df_ego['traveling_distance'])
    else:
        dst = np.zeros_like(f)

    tmp_vid_class_map = {}

    if front_seg_json is not None:
        for val in front_seg_json['results']:
            seg_items = val.get('segmentations') or val.get('tensor_data') or []
            for item in seg_items:
                vid = 'f' + str(item.get('obj_id') or item.get('ID'))
                cls = item.get('vehicle_type') or item.get('Class')
                if vid not in tmp_vid_class_map:
                    tmp_vid_class_map[vid] = []
                tmp_vid_class_map[vid].append(cls)

    if rear_seg_json is not None:
        for val in rear_seg_json['results']:
            seg_items = val.get('segmentations') or val.get('tensor_data') or []
            for item in seg_items:
                vid = 'r' + str(item.get('obj_id') or item.get('ID'))
                cls = item.get('vehicle_type') or item.get('Class')
                if vid not in tmp_vid_class_map:
                    tmp_vid_class_map[vid] = []
                tmp_vid_class_map[vid].append(cls)

    vid_class_map = {}
    for oid, classes in tmp_vid_class_map.items():
        vid_class_map[oid] = most_frequent(classes)

    vid_odlist_map = {}
    frame_odlist_map = {}
    distance_files = natsorted(glob.glob(os.path.join(objects_dir, 'trajectory_*.csv')))
    for distance_file in distance_files:
        pattern = r'trajectory_(.+).csv'
        matches = re.findall(pattern, distance_file)
        vid = matches[0]
        #print(vid)

        df_dist = pd.read_csv(distance_file, header=0, index_col=False)

        #sct_file = objects_dir + 'sct_' + vid + '.csv'
        #df_sct = pd.read_csv(sct_file, header=0, index_col=False)

        cls = vid_class_map[vid]
        vfrm = np.array(df_dist['frame'])
        dx = np.array(df_dist['dx_from_front_ma'])
        dy_l = np.array(df_dist['dy_center_to_other_left_ma'])
        dy_r = np.array(df_dist['dy_center_to_other_right_ma'])

        sctx = np.array(df_dist['sctx'])
        scty = np.array(df_dist['scty'])

        sdx = np.array(df_dist['sdx'])
        scb1x = np.array(df_dist['scb1x'])
        scb2x = np.array(df_dist['scb2x'])
        scb3x = np.array(df_dist['scb3x'])

        sdy = np.array(df_dist['sdy'])
        scb1y = np.array(df_dist['scb1y'])
        scb2y = np.array(df_dist['scb2y'])
        scb3y = np.array(df_dist['scb3y'])

        odlist = []

        vid_odlist_map[vid] = odlist

        for i in range(0, len(vfrm)):
            od = ObjectData(vid, cls, vfrm[i], dx[i], dy_l[i], dy_r[i], sctx[i], scty[i], sdx[i], scb1x[i], scb2x[i], scb3x[i], sdy[i], scb1y[i], scb2y[i], scb3y[i])
            odlist.append(od)

            if not vfrm[i] in frame_odlist_map:
                frame_odlist_map[vfrm[i]] = []

            frame_odlist_map[vfrm[i]].append(od)

    fig = plt.figure()

    plt.tick_params(labelsize=14)
    plt.subplots_adjust(left=0.2, right=0.95, bottom=0.15, top=0.90)

    vid_traj_map = {}
    
    vid_traj_map['ego'] = deque(maxlen=120)

    #marker_size = 2**0.5
    marker_size = 1

    x_range = 50
    y_range = 15

    near_vehicles_file = open(near_vehicles_file_name, mode='w')
    near_vehicles_file.write('frame,ahead_id,ahead_sctx,ahead_scty,adjacent_l_id,adjacent_l_sctx,adjacent_l_scty,adjacent_r_id,adjacent_r_sctx,adjacent_r_scty\n')

    bar = tqdm(total=len(f), dynamic_ncols=True, desc="topview")
    for i in range(0, len(f)):
        #print('===============================')
        #print(i, f[i])

        plt.xlim(dst[i] - x_range, dst[i] + x_range)
        plt.ylim(-y_range, y_range)

        plt.plot(ego_x + dst[i], ego_y, color="red")

        #points = np.column_stack((ego_x + dst[i], ego_y))
        #print(points)
        #center = points.mean(axis=0)
        #print(center)
        #rotated = rotate_points(points, (dst[i]-length/2, 0), heading[i])
        #X, Y = rotated[:, 0], rotated[:, 1]
        #plt.plot(X, Y, color="green")

        rote_center_for_front = (dst[i], 0)
        rote_center_for_rear = (dst[i] - length, 0)

        traje_queue = vid_traj_map['ego']
        traje_queue.append([ego_min_x + dst[i], ego_min_y + (ego_max_y - ego_min_y)/2])
        for pos in reversed(traje_queue):
            #plt.plot(pos[0], pos[1], 'o', markersize=marker_size, color="red")
            plt.plot(pos[0], pos[1], '.', markersize=marker_size, color="salmon")

        near_ahead_car = None
        near_adjacent_car_l = None
        near_adjacent_car_r = None

        if f[i] in front_frame_wl_map:
            lane = front_frame_wl_map[f[i]]

            if not np.isnan(lane.left_wl_p1_dx):

                #plt.plot((lane.left_wl_p1_dx + dst[i], lane.left_wl_p2_dx + dst[i]), (lane.left_wl_p1_dy, lane.left_wl_p2_dy), color="gray")
                #plt.plot((lane.right_wl_p1_dx + dst[i], lane.right_wl_p2_dx + dst[i]), (lane.right_wl_p1_dy, lane.right_wl_p2_dy), color="gray")
                #plt.plot((lane.left2_wl_p1_dx + dst[i], lane.left2_wl_p2_dx + dst[i]), (lane.left2_wl_p1_dy, lane.left2_wl_p2_dy), color="gray")
                #plt.plot((lane.right2_wl_p1_dx + dst[i], lane.right2_wl_p2_dx + dst[i]), (lane.right2_wl_p1_dy, lane.right2_wl_p2_dy), color="gray")

                left_p1 = np.array((lane.left_wl_p1_dx + dst[i], lane.left_wl_p1_dy))
                left_p2 = np.array((lane.left_wl_p2_dx + dst[i], lane.left_wl_p2_dy))
                rotated_left_p1 = rotate_points(left_p1, rote_center_for_front, -lane.heading)
                rotated_left_p2 = rotate_points(left_p2, rote_center_for_front, -lane.heading)
                plt.plot((rotated_left_p1[0],rotated_left_p2[0]), (rotated_left_p1[1],rotated_left_p2[1]), color="lightgray")

                right_p1 = np.array((lane.right_wl_p1_dx + dst[i], lane.right_wl_p1_dy))
                right_p2 = np.array((lane.right_wl_p2_dx + dst[i], lane.right_wl_p2_dy))
                rotated_right_p1 = rotate_points(right_p1, rote_center_for_front, -lane.heading)
                rotated_right_p2 = rotate_points(right_p2, rote_center_for_front, -lane.heading)
                plt.plot((rotated_right_p1[0],rotated_right_p2[0]), (rotated_right_p1[1],rotated_right_p2[1]), color="lightgray")

                '''
                left2_p1 = np.array((lane.left2_wl_p1_dx + dst[i], lane.left2_wl_p1_dy))
                left2_p2 = np.array((lane.left2_wl_p2_dx + dst[i], lane.left2_wl_p2_dy))
                rotated_left2_p1 = rotate_points(left2_p1, rote_center_for_front, -lane.heading)
                rotated_left2_p2 = rotate_points(left2_p2, rote_center_for_front, -lane.heading)
                plt.plot((rotated_left2_p1[0],rotated_left2_p2[0]), (rotated_left2_p1[1],rotated_left2_p2[1]), color="gray")

                right2_p1 = np.array((lane.right2_wl_p1_dx + dst[i], lane.right2_wl_p1_dy))
                right2_p2 = np.array((lane.right2_wl_p2_dx + dst[i], lane.right2_wl_p2_dy))
                rotated_right2_p1 = rotate_points(right2_p1, rote_center_for_front, -lane.heading)
                rotated_right2_p2 = rotate_points(right2_p2, rote_center_for_front, -lane.heading)
                plt.plot((rotated_right2_p1[0],rotated_right2_p2[0]), (rotated_right2_p1[1],rotated_right2_p2[1]), color="gray")
                '''

        if f[i] in rear_frame_wl_map:
            lane = rear_frame_wl_map[f[i]]

            if not np.isnan(lane.left_wl_p1_dx):
                #plt.plot((lane.left_wl_p1_dx - length + dst[i], lane.left_wl_p2_dx - length + dst[i]), (lane.left_wl_p1_dy, lane.left_wl_p2_dy), color="gray")
                #plt.plot((lane.right_wl_p1_dx - length + dst[i], lane.right_wl_p2_dx - length + dst[i]), (lane.right_wl_p1_dy, lane.right_wl_p2_dy), color="gray")
                #plt.plot((lane.left2_wl_p1_dx - length + dst[i], lane.left2_wl_p2_dx - length + dst[i]), (lane.left2_wl_p1_dy, lane.left2_wl_p2_dy), color="gray")
                #plt.plot((lane.right2_wl_p1_dx - length + dst[i], lane.right2_wl_p2_dx - length + dst[i]), (lane.right2_wl_p1_dy, lane.right2_wl_p2_dy), color="gray")

                left_p1 = np.array((lane.left_wl_p1_dx - length + dst[i], lane.left_wl_p1_dy))
                left_p2 = np.array((lane.left_wl_p2_dx - length + dst[i], lane.left_wl_p2_dy))
                rotated_left_p1 = rotate_points(left_p1, rote_center_for_rear, -lane.heading)
                rotated_left_p2 = rotate_points(left_p2, rote_center_for_rear, -lane.heading)
                plt.plot((rotated_left_p1[0],rotated_left_p2[0]), (rotated_left_p1[1],rotated_left_p2[1]), color="lightgray")

                right_p1 = np.array((lane.right_wl_p1_dx - length + dst[i], lane.right_wl_p1_dy))
                right_p2 = np.array((lane.right_wl_p2_dx - length + dst[i], lane.right_wl_p2_dy))
                rotated_right_p1 = rotate_points(right_p1, rote_center_for_rear, -lane.heading)
                rotated_right_p2 = rotate_points(right_p2, rote_center_for_rear, -lane.heading)
                plt.plot((rotated_right_p1[0],rotated_right_p2[0]), (rotated_right_p1[1],rotated_right_p2[1]), color="lightgray")

                '''
                left2_p1 = np.array((lane.left2_wl_p1_dx - length + dst[i], lane.left2_wl_p1_dy))
                left2_p2 = np.array((lane.left2_wl_p2_dx - length + dst[i], lane.left2_wl_p2_dy))
                rotated_left2_p1 = rotate_points(left2_p1, rote_center_for_rear, -lane.heading)
                rotated_left2_p2 = rotate_points(left2_p2, rote_center_for_rear, -lane.heading)
                plt.plot((rotated_left2_p1[0],rotated_left2_p2[0]), (rotated_left2_p1[1],rotated_left2_p2[1]), color="gray")

                right2_p1 = np.array((lane.right2_wl_p1_dx - length + dst[i], lane.right2_wl_p1_dy))
                right2_p2 = np.array((lane.right2_wl_p2_dx - length + dst[i], lane.right2_wl_p2_dy))
                rotated_right2_p1 = rotate_points(right2_p1, rote_center_for_rear, -lane.heading)
                rotated_right2_p2 = rotate_points(right2_p2, rote_center_for_rear, -lane.heading)
                plt.plot((rotated_right2_p1[0],rotated_right2_p2[0]), (rotated_right2_p1[1],rotated_right2_p2[1]), color="gray")
                '''

        if f[i] in frame_odlist_map:

            for od in frame_odlist_map[f[i]]:
                #print(od.vid)

                if np.isnan(od.dx) or np.isnan(od.dy_l) or np.isnan(od.dy_r):
                    continue

                if od.dx < -x_range or x_range < od.dx:
                    continue

                if od.dy_l < -y_range or y_range < od.dy_r:
                    continue

                min_x, max_x, min_y, max_y = calc_objects_pos(od)

                v_tmp_x = [min_x, min_x, max_x, max_x, min_x]
                v_tmp_y = [min_y, max_y, max_y, min_y, min_y]

                if not od.vid in vid_traj_map:
                    vid_traj_map[od.vid] = deque(maxlen=120)

                traje_queue = vid_traj_map[od.vid]

                traje_queue.append([min_x + dst[i], min_y + (max_y - min_y)/2])


                disp_sct = False
                txt = ''
                if 0 <= od.sctx and od.sctx <= 8:
                    txt = 'SCTx:{:.1f}'.format(od.sctx) + '\n'
                    disp_sct = True
                else:
                    txt = 'SCTx:---\n'

                txt_scty = 'SCTy:---'
                if 0 <= od.scty and od.scty <= 8:
                    txt_scty = 'SCTy:{:.1f}'.format(od.scty)
                    disp_sct = True
                txt += txt_scty

                if disp_sct:
                    plt.text(max_x+2 + dst[i], min_y-1, txt, fontsize=10, color="skyblue")
                    #plt.text(max_x+2 + dst[i], min_y-1, txt, fontsize=9)

                    plt.plot(v_tmp_x + dst[i], v_tmp_y, color="skyblue")
                    plt.text(min_x + dst[i], max_y + 0.3, str(od.vid), fontsize=10, color="skyblue")

                    for pos in reversed(traje_queue):
                        #plt.plot(pos[0], pos[1], 'o', markersize=marker_size, color="steelblue")
                        plt.plot(pos[0], pos[1], '.', markersize=marker_size, color="lightgray")

                else:
                    plt.plot(v_tmp_x + dst[i], v_tmp_y, color="lightgray")
                    plt.text(min_x + dst[i], max_y + 0.3, str(od.vid), fontsize=10, color="lightgray")

                    for pos in reversed(traje_queue):
                        #plt.plot(pos[0], pos[1], 'o', markersize=marker_size, color="lightgray")
                        plt.plot(pos[0], pos[1], '.', markersize=marker_size, color="lightgray")


                if 0 < od.dx and od.dx < x_range:
                    # 先行車
                    if is_ahead_car(width, od):
                        if near_ahead_car is None:
                            near_ahead_car = od
                        else:
                            if near_ahead_car.dx > od.dx:
                                near_ahead_car = od

                    # 左側隣接車
                    elif is_adjacent_car_l(width, od):
                        if near_adjacent_car_l is None:
                            near_adjacent_car_l = od
                        else:
                            if near_adjacent_car_l.dx > od.dx:
                                near_adjacent_car_l = od

                    # 右側隣接車
                    elif is_adjacent_car_r(width, od):
                        if near_adjacent_car_r is None:
                            near_adjacent_car_r = od
                        else:
                            if near_adjacent_car_r.dx > od.dx:
                                near_adjacent_car_r = od


            #if near_ahead_car is not None:
            #    plt.text(near_ahead_car.dx + dst[i], near_ahead_car.dy_r, 'F', fontsize=10)
            #if near_adjacent_car_l is not None:
            #    plt.text(near_adjacent_car_l.dx + dst[i], near_adjacent_car_l.dy_r, 'L', fontsize=10)
            #if near_adjacent_car_r is not None:
            #    plt.text(near_adjacent_car_r.dx + dst[i], near_adjacent_car_r.dy_r, 'R', fontsize=10)

            ahead_car_sct_threshold = 3
            cutin_sct_threshold = 8

            # 先行車が存在する状況
            if near_ahead_car is not None:

                # 先行車と接近時は、先行車とのSCBを優先表示
                if 0 <= near_ahead_car.sctx and near_ahead_car.sctx <= ahead_car_sct_threshold:
                    plot_scb_x(plt, ego_max_x, ego_min_y, width, near_ahead_car, dst[i])
                    plot_opponent(near_ahead_car, dst[i])

                else:
                    # 左側隣接車が存在する。右側隣接車は存在しない
                    if near_adjacent_car_l is not None and near_adjacent_car_r is None:
                        # 左側隣接車の方が先行車より近い（隣接車が先行車より遠いと自車へのカットインはできないと考える）
                        if near_adjacent_car_l.dx < near_ahead_car.dx:
                            # 左側隣接車カットイン時はSCBを表示
                            if 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                                plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                                plot_opponent(near_adjacent_car_l, dst[i])
                                if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                                    plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

                    # 右側隣接車が存在する。左側隣接車は存在しない
                    elif near_adjacent_car_l is None and near_adjacent_car_r is not None:
                        # 右側隣接車の方が先行車より近い（隣接車が先行車より遠いと自車へのカットインはできないと考える）
                        if  near_adjacent_car_r.dx < near_ahead_car.dx:
                            # 右側隣接車カットイン時はSCBを表示
                            if 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                                plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                                plot_opponent(near_adjacent_car_r, dst[i])
                                if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                                    plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                    # 右側隣接車も左側隣接車も存在する
                    elif near_adjacent_car_l is not None and near_adjacent_car_r is not None:
                        # 左側隣接車は先行車より近いが、右側隣接車は先行車より遠い
                        if near_adjacent_car_l.dx < near_ahead_car.dx and near_adjacent_car_r.dx > near_ahead_car.dx:
                            # 左側隣接車カットイン時はSCBを表示（右側隣接車は、先行車より遠いので自車へのカットインはできないと考える）
                            if 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                                plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                                plot_opponent(near_adjacent_car_l, dst[i])
                                if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                                    plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

                        # 右側隣接車は先行車より近いが、左側隣接車は先行車より遠い
                        elif near_adjacent_car_l.dx > near_ahead_car.dx and near_adjacent_car_r.dx < near_ahead_car.dx:
                            # 右側隣接車カットイン時はSCBを表示（左側隣接車は、先行車より遠いので自車へのカットインはできないと考える）
                            if 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                                plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                                plot_opponent(near_adjacent_car_r, dst[i])
                                if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                                    plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                        # 左側隣接車も右側隣接車も先行車より近い（どちらもカットインしてくる可能性あり。近い方を優先する）
                        if near_adjacent_car_l.dx < near_ahead_car.dx and near_adjacent_car_r.dx < near_ahead_car.dx:
                            # 左側隣接車が右側隣接車より近い
                            if near_adjacent_car_l.dx < near_adjacent_car_r.dx:
                                # 左側隣接車カットイン時はSCBを優先表示
                                if 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                                    plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                                    plot_opponent(near_adjacent_car_l, dst[i])
                                    if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                                        plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

                                # 右側隣接車カットイン時はSCBを表示
                                elif 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                                    plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                                    plot_opponent(near_adjacent_car_r, dst[i])
                                    if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                                        plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                            # 右側隣接車が左側隣接車より近い
                            if near_adjacent_car_l.dx > near_adjacent_car_r.dx:
                                # 右側隣接車カットイン時はSCBを優先表示
                                if 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                                    plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                                    plot_opponent(near_adjacent_car_r, dst[i])
                                    if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                                        plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                                # 左側隣接車カットイン時はSCBを表示
                                elif 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                                    plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                                    plot_opponent(near_adjacent_car_l, dst[i])
                                    if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                                        plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

            # 先行車が存在しない状況
            else:

                # 左側隣接車が存在する。右側隣接車は存在しない
                if near_adjacent_car_l is not None and near_adjacent_car_r is None:
                    # 左側隣接車カットイン時はSCBを表示
                    if 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                        plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                        plot_opponent(near_adjacent_car_l, dst[i])
                        if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                            plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

                # 右側隣接車が存在する。左側隣接車は存在しない
                elif near_adjacent_car_l is None and near_adjacent_car_r is not None:
                    # 右側隣接車カットイン時はSCBを表示
                    if 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                        plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                        plot_opponent(near_adjacent_car_r, dst[i])
                        if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                            plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                # 右側隣接車も左側隣接車も存在する。両方ともカットインしてくる可能性あり。近い方を優先する
                elif near_adjacent_car_l is not None and near_adjacent_car_r is not None:

                    # 左側隣接車が右側隣接車より近い
                    if near_adjacent_car_l.dx < near_adjacent_car_r.dx:
                        # 左側隣接車カットイン時はSCBを優先表示
                        if 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                            plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                            plot_opponent(near_adjacent_car_l, dst[i])
                            if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                                plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

                        # 右側隣接車カットイン時はSCBを表示
                        elif 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                            plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                            plot_opponent(near_adjacent_car_r, dst[i])
                            if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                                plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                    # 右側隣接車が左側隣接車より近い
                    if near_adjacent_car_l.dx > near_adjacent_car_r.dx:
                        # 右側隣接車カットイン時はSCBを優先表示
                        if 0 <= near_adjacent_car_r.scty and near_adjacent_car_r.scty <= cutin_sct_threshold:
                            plot_scb_yr(plt, near_adjacent_car_r, dst[i])
                            plot_opponent(near_adjacent_car_r, dst[i])
                            if 0 <= near_adjacent_car_r.sctx and near_adjacent_car_r.sctx <= cutin_sct_threshold:
                                plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_r, dst[i])

                        # 左側隣接車カットイン時はSCBを表示
                        elif 0 <= near_adjacent_car_l.scty and near_adjacent_car_l.scty <= cutin_sct_threshold:
                            plot_scb_yl(plt, near_adjacent_car_l, dst[i])
                            plot_opponent(near_adjacent_car_l, dst[i])
                            if 0 <= near_adjacent_car_l.sctx and near_adjacent_car_l.sctx <= cutin_sct_threshold:
                                plot_scb_x(plt, ego_max_x, ego_min_y, width, near_adjacent_car_l, dst[i])

        row_data = str(f[i])
        if near_ahead_car is not None:
            row_data = add_csv_data_no_nan_check(row_data, near_ahead_car.vid)
            row_data = add_csv_data(row_data, near_ahead_car.sctx)
            row_data = add_csv_data(row_data, near_ahead_car.scty)
        else:
            row_data = add_csv_data_no_nan_check(row_data, None)
            row_data = add_csv_data(row_data, None)
            row_data = add_csv_data(row_data, None)

        if near_adjacent_car_l is not None:
            row_data = add_csv_data_no_nan_check(row_data, near_adjacent_car_l.vid)
            row_data = add_csv_data(row_data, near_adjacent_car_l.sctx)
            row_data = add_csv_data(row_data, near_adjacent_car_l.scty)
        else:
            row_data = add_csv_data(row_data, None)
            row_data = add_csv_data(row_data, None)
            row_data = add_csv_data(row_data, None)

        if near_adjacent_car_r is not None:
            row_data = add_csv_data_no_nan_check(row_data, near_adjacent_car_r.vid)
            row_data = add_csv_data(row_data, near_adjacent_car_r.sctx)
            row_data = add_csv_data(row_data, near_adjacent_car_r.scty)
        else:
            row_data = add_csv_data(row_data, None)
            row_data = add_csv_data(row_data, None)
            row_data = add_csv_data(row_data, None)

        near_vehicles_file.write(row_data + '\n')


        plt.xlabel('X [m]', fontsize=18)
        plt.ylabel('Y [m]', fontsize=18)
        plt.title('Top view', fontsize=18)

        plt.savefig(os.path.join(out_graph_dir, 'topview_' + str(f[i]) + '.png'))
        plt.cla()

        bar.update(1)

    bar.close()
    
    near_vehicles_file.close()

