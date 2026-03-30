import os
import sys

# HybridNets リポジトリへのパス追加
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, os.pardir))
_HYBRIDNETS_DIR = os.path.join(_APP_DIR, 'hybridnets_repo')
if os.path.isdir(_HYBRIDNETS_DIR) and _HYBRIDNETS_DIR not in sys.path:
    sys.path.insert(0, _HYBRIDNETS_DIR)

import time
import torch
from torch.backends import cudnn
from backbone import HybridNetsBackbone
import cv2
import numpy as np
from glob import glob
from utils.utils import letterbox, scale_coords, postprocess, BBoxTransform, ClipBoxes, restricted_float, \
    boolean_string, Params
from utils.plot import STANDARD_COLORS, standard_to_bgr, get_index_label, plot_one_box
from torchvision import transforms
import argparse
from utils.constants import *
import logging
import re
import random
import json
from tqdm import tqdm
from natsort import natsorted
from sklearn.cluster import DBSCAN
from collections import defaultdict
from skimage.morphology import skeletonize
from skimage.morphology import skeletonize, remove_small_objects
from tools import video2image
from tools import image2video
from tools import distortion_correction


def exclude_smallest_n(points, N):
    
    if len(points) < N:
        return []

    # Yの値でソート
    sorted_points = sorted(points, key=lambda point: point[1])
    
    # Yの値が小さいN個を除外
    result_points = sorted_points[N:]
    
    return result_points


# points1の方がX軸上で大きい想定
def interpolate_wl(points1, points2, width, N):

    wls = []

    p1_1_x = points1[0][0]
    p1_2_x = points1[1][0]
    p2_1_x = points2[0][0]
    p2_2_x = points2[1][0]

    y_1 = points1[0][1]
    y_2 = points1[1][1]

    step_1 = (p1_1_x - p2_1_x) / (N + 1)
    step_2 = (p1_2_x - p2_2_x) / (N + 1)

    for i in range(1, N+1):
        x_1 = p1_1_x - (step_1 * i)
        x_2 = p1_2_x - (step_2 * i)
        x = [x_1, x_2]
        y = [y_1, y_2]

        # 一次関数でフィッティング
        coefficients = np.polyfit(y, x, 1)
        polynomial = np.poly1d(coefficients)
        p1 = (int(polynomial(y_1)), y_1)
        p2 = (int(polynomial(y_2)), y_2)
        offset = p2[0] - width / 2
        wl = WhiteLine(coefficients, polynomial, p1, p2, offset)
        wls.append(wl)

    return wls


class WhiteLine:

    def __init__(self, coefficients, polynomial, p1, p2, offset):
        self.coefficients = coefficients
        self.polynomial = polynomial
        self.p1 = p1
        self.p2 = p2
        self.offset = offset



def do_detect_lane(seg_image, org_copy, out_dir, img_file_name, lane_param):

    frame_data = []

    lane_width_pixel = int(lane_param[0])
    horizontal_line = int(lane_param[1])

    gray = cv2.cvtColor(seg_image, cv2.COLOR_BGR2GRAY)

    # 画像サイズを取得
    height, width = gray.shape

    # 基準線
    reference1_y = horizontal_line + (height - horizontal_line) / 8
    reference1_y = int(reference1_y)

    reference2_y = height - ((height - horizontal_line) / 4)
    reference2_y = int(reference2_y)

    # バイナリ画像を作成
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    # 画像サイズを取得
    height, width = binary.shape

    # 形態学的クロージングを実施
    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    #cv2.imwrite(out_dir + 'closed.jpg', closed)

    # スケルトン化
    skeleton = skeletonize(closed // 255).astype(np.uint8) * 255
    #cv2.imwrite(out_dir + "skeleton.png", skeleton)

    # 小さいオブジェクトを削除
    skeleton = remove_small_objects(skeleton, max_size=50)
    #cv2.imwrite(out_dir + 'cleaned_skeleton.jpg', skeleton)

    # スケルトンの点を取得
    skeleton_points = np.column_stack(np.nonzero(skeleton)[::-1])

    for point in skeleton_points:
        x, y = point.ravel()

    copied_points = skeleton_points.copy()
    copied_points = np.array([point for point in copied_points if point[1] >= reference1_y])
    copied_points = np.array([point for point in copied_points if point[1] <= reference2_y])

    whitelines = []

    while len(copied_points) > 0:

        clustering = DBSCAN(eps=25, min_samples=10).fit(copied_points)
        unique_labels = set(clustering.labels_)

        tmp_points = []

        for label in unique_labels:
            if label == -1:
                continue
            else:
                points = copied_points[clustering.labels_ == label]
                
                if len(points) < 70:
                    continue
                
                x = points[:, 0]
                y = points[:, 1]

                # 一次関数でフィッティング
                coefficients = np.polyfit(y, x, 1)
                polynomial = np.poly1d(coefficients)

                #coefficients = np.polyfit(x, y, 1)
                m, c = coefficients

                # フィッティング結果の計算
                x_fit = m * y + c

                # 誤差の計算 (RMSE)
                rmse = np.sqrt(np.mean((x - x_fit) ** 2))

                #print('rmse=' + str(rmse))

                if rmse < 30:
                    p1 = (int(polynomial(reference1_y)), reference1_y)
                    p2 = (int(polynomial(height-1)), height-1)
                    offset = p2[0] - width / 2
                    wl = WhiteLine(coefficients, polynomial, p1, p2, offset)
                    whitelines.append([wl, points])
                else:
                    new_points = exclude_smallest_n(points, 3)
                    tmp_points.extend(new_points)

        copied_points = np.array(tmp_points)


    tmp_whitelines = []

    for idx, val in enumerate(whitelines):
        wl = val[0]
        polynomial = wl.polynomial
        points = val[1]

        min_point = min(points, key=lambda point: point[1])
        max_point = max(points, key=lambda point: point[1])
        p1 = (int(polynomial(min_point[1])), min_point[1])
        p2 = (int(polynomial(max_point[1])), max_point[1])
        np1 = np.array(p1)
        np2 = np.array(p2)
        # 線の長さを計算して短いものを除外
        line_length = np.linalg.norm(np1 - np2)
        if line_length < 70:
            continue

        tmp_whitelines.append([wl, abs(wl.offset)])

    whitelines = tmp_whitelines
    whitelines = sorted(whitelines, key=lambda x: x[1])

    if len(whitelines) > 0:

        main_wl = whitelines[0][0]
        left_wls = []
        right_wls = []
        
        cur_left = main_wl
        cur_right = main_wl

        lane_width_2 = int(lane_width_pixel * 2.3)
        lane_width_3 = int(lane_width_pixel * 3.6)
        lane_width_4 = int(lane_width_pixel * 4.9)

        for i in range(1, len(whitelines)):
            
            wl = whitelines[i][0]
            
            if wl.offset < cur_left.offset:
                diff = abs(cur_left.offset - wl.offset)
                if lane_width_4 >= diff and diff >= lane_width_3:
                    interpolated = interpolate_wl((cur_left.p1, cur_left.p2), (wl.p1, wl.p2), width, 2)
                    left_wls.extend(interpolated)
                    cur_left = wl
                    left_wls.append(cur_left)
                elif lane_width_3 > diff and diff >= lane_width_2:
                    interpolated = interpolate_wl((cur_left.p1, cur_left.p2), (wl.p1, wl.p2), width, 1)
                    left_wls.extend(interpolated)
                    cur_left = wl
                    left_wls.append(cur_left)
                elif lane_width_2 > diff and diff >= lane_width_pixel:
                    cur_left = wl
                    left_wls.append(cur_left)

            elif wl.offset > cur_right.offset:
                diff = abs(wl.offset - cur_right.offset)
                if lane_width_4 >= diff and diff >= lane_width_3:
                    interpolated = interpolate_wl((wl.p1, wl.p2), (cur_right.p1, cur_right.p2), width, 2)
                    right_wls.extend(interpolated)
                    cur_right = wl
                    right_wls.append(cur_right)
                elif lane_width_3 > diff and diff >= lane_width_2:
                    interpolated = interpolate_wl((wl.p1, wl.p2), (cur_right.p1, cur_right.p2), width, 1)
                    right_wls.extend(interpolated)
                    cur_right = wl
                    right_wls.append(cur_right)
                elif lane_width_2 > diff and diff >= lane_width_pixel:
                    cur_right = wl
                    right_wls.append(cur_right)

        optimized_wls = []
        optimized_wls.append([main_wl, abs(main_wl.offset)])
        
        for wl in left_wls:
            optimized_wls.append([wl, abs(wl.offset)])

        for wl in right_wls:
            optimized_wls.append([wl, abs(wl.offset)])

        optimized_wls = sorted(optimized_wls, key=lambda x: x[1])

        whiteline_map = {}

        if len(optimized_wls) < 2:
            wl = optimized_wls[0][0]
            whiteline_map[0] = wl
        else:
            wl_1 = optimized_wls[0][0]
            wl_2 = optimized_wls[1][0]
            if wl_1.offset < wl_2.offset:
                whiteline_map[0] = wl_1
                whiteline_map[1] = wl_2
            else:
                whiteline_map[0] = wl_2
                whiteline_map[1] = wl_1

            cur_left_idx = 0
            cur_right_idx = 1

            for i in range(2, len(optimized_wls)):
                wl_1 = optimized_wls[cur_right_idx][0]
                wl_2 = optimized_wls[i][0]

                if wl_1.offset < wl_2.offset:
                    cur_right_idx += 1
                    whiteline_map[cur_right_idx] = wl_2
                else:
                    cur_left_idx -= 1
                    whiteline_map[cur_left_idx] = wl_2


        final_wls = whiteline_map.items()
        final_wls = sorted(final_wls, key=lambda x: x[0])

        for idx, wl in final_wls:

            frame_data.append({
                'ID': idx,
                'Coefficient_m': wl.coefficients[0],
                'Coefficient_c': wl.coefficients[1],
                'AccuracyLimitPoint_X': wl.p1[0],
                'AccuracyLimitPoint_Y': wl.p1[1],
                'ImageBottomPoint_X': wl.p2[0],
                'ImageBottomPoint_Y': wl.p2[1]
            })

            color = ( 255, 255, 255)
            if idx == 0:
                color = ( 0, 0, 255)
            elif idx == 1:
                color = ( 255, 0, 0)
            elif idx == 2:
                color = ( 255, 255, 0)
            elif idx == -1:
                color = ( 255, 0, 255)
            elif idx == -2:
                color = ( 0, 255, 255)
            cv2.line(org_copy, wl.p1, wl.p2, color, 2)


    cv2.imwrite(os.path.join(out_dir, img_file_name), org_copy)

    return frame_data



def detect_lane(in_dir, out_dir, lane_param):

    '''
    parser = argparse.ArgumentParser('HybridNets: End-to-End Perception Network - DatVu')
    parser.add_argument('-p', '--project', type=str, default='bdd100k', help='Project file that contains parameters')
    parser.add_argument('-bb', '--backbone', type=str, help='Use timm to create another backbone replacing efficientnet. '
                                                            'https://github.com/rwightman/pytorch-image-models')
    parser.add_argument('-c', '--compound_coef', type=int, default=3, help='Coefficient of efficientnet backbone')
    parser.add_argument('--source', type=str, default='demo/video', help='The demo video folder')
    parser.add_argument('--output', type=str, default='demo_result', help='Output folder')
    parser.add_argument('-w', '--load_weights', type=str, default='weights/hybridnets.pth')
    parser.add_argument('--conf_thresh', type=restricted_float, default='0.25')
    parser.add_argument('--iou_thresh', type=restricted_float, default='0.3')
    parser.add_argument('--cuda', type=boolean_string, default=True)
    parser.add_argument('--float16', type=boolean_string, default=True, help="Use float16 for faster inference")
    args = parser.parse_args()

    params = Params(f'projects/{args.project}.yml')
    color_list_seg = {}
    for seg_class in params.seg_list:
        # edit your color here if you wanna fix to your liking
        color_list_seg[seg_class] = list(np.random.choice(range(256), size=3))
    compound_coef = args.compound_coef
    source = args.source
    if source.endswith("/"):
        source = source[:-1]
    output = args.output
    if output.endswith("/"):
        output = output[:-1]
    weight = args.load_weights
    #video_srcs = glob(f'{source}/*.mp4')
    #os.makedirs(output, exist_ok=True)
    input_imgs = []
    shapes = []

    anchors_ratios = params.anchors_ratios
    anchors_scales = params.anchors_scales

    threshold = args.conf_thresh
    iou_threshold = args.iou_thresh

    use_cuda = args.cuda
    use_float16 = args.float16
    cudnn.fastest = True
    cudnn.benchmark = True
    '''

    params = Params(f'projects/bdd100k.yml')
    color_list_seg = {}
    for seg_class in params.seg_list:
        # edit your color here if you wanna fix to your liking
        color_list_seg[seg_class] = list(np.random.choice(range(256), size=3))
    compound_coef = 3
    weight = 'weights/hybridnets.pth'
    shapes = []

    anchors_ratios = params.anchors_ratios
    anchors_scales = params.anchors_scales

    threshold = 0.25
    iou_threshold = 0.3

    use_cuda = True
    use_float16 = True
    cudnn.fastest = True
    cudnn.benchmark = True

    obj_list = params.obj_list
    seg_list = params.seg_list

    color_list = standard_to_bgr(STANDARD_COLORS)
    resized_shape = params.model['image_size']
    if isinstance(resized_shape, list):
        resized_shape = max(resized_shape)
    normalize = transforms.Normalize(
        mean=params.mean, std=params.std
    )
    transform = transforms.Compose([
        transforms.ToTensor(),
        normalize,
    ])
    # print(x.shape)
    weight = torch.load(weight, map_location='cuda' if use_cuda else 'cpu')
    weight_last_layer_seg = weight.get('model', weight)['segmentation_head.0.weight']
    if weight_last_layer_seg.size(0) == 1:
        seg_mode = BINARY_MODE
    else:
        if params.seg_multilabel:
            seg_mode = MULTILABEL_MODE
            print("Sorry, we do not support multilabel video inference yet.")
            print("In image inference, we can give each class their own image.")
            print("But a video for each class is meaningless.")
            print("https://github.com/datvuthanh/HybridNets/issues/20")
            exit(0)
        else:
            seg_mode = MULTICLASS_MODE
    print("DETECTED SEGMENTATION MODE FROM WEIGHT AND PROJECT FILE:", seg_mode)

    model = HybridNetsBackbone(compound_coef=compound_coef, num_classes=len(obj_list), ratios=eval(anchors_ratios),
                               scales=eval(anchors_scales), seg_classes=len(seg_list), backbone_name=None,
                               seg_mode=seg_mode)
    model.load_state_dict(weight.get('model', weight))

    model.requires_grad_(False)
    model.eval()

    if use_cuda:
        model = model.cuda()
        if use_float16:
            model = model.half()

    regressBoxes = BBoxTransform()
    clipBoxes = ClipBoxes()

    img_files = natsorted(glob(os.path.join(in_dir, '*.jpg')))

    lane_detection_results = {"results": []}

    bar = tqdm(total=len(img_files), dynamic_ncols=True, desc="lane detection")
    for img_file in img_files:

        img_file_name = os.path.basename(img_file)
        name = os.path.splitext(img_file_name)[0]
        current_frame_no = int(name[-5:])  # ファイル名の末尾5文字をフレーム番号として使用

        frame = cv2.imread(img_file)

        #frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        h0, w0 = frame.shape[:2]  # orig hw
        r = resized_shape / max(h0, w0)  # resize image to img_size
        input_img = cv2.resize(frame, (int(w0 * r), int(h0 * r)), interpolation=cv2.INTER_AREA)
        h, w = input_img.shape[:2]

        (input_img, _), ratio, pad = letterbox((input_img, None), auto=False,
                                                  scaleup=True)

        shapes = ((h0, w0), ((h / h0, w / w0), pad))

        if use_cuda:
            x = transform(input_img).cuda()
        else:
            x = transform(input_img)

        x = x.to(torch.float16 if use_cuda and use_float16 else torch.float32)
        x.unsqueeze_(0)
        with torch.no_grad():
            features, regression, classification, anchors, seg = model(x)

            seg = seg[:, :, int(pad[1]):int(h+pad[1]), int(pad[0]):int(w+pad[0])]
            # (1, C, W, H) -> (1, W, H)
            if seg_mode == BINARY_MODE:
                seg_mask = torch.where(seg >= 0, 1, 0)
                seg_mask.squeeze_(1)
            else:
                _, seg_mask = torch.max(seg, 1)
            # (1, W, H) -> (W, H)
            seg_mask_ = seg_mask[0].squeeze().cpu().numpy()
            seg_mask_ = cv2.resize(seg_mask_, dsize=(w0, h0), interpolation=cv2.INTER_NEAREST)
            color_seg = np.zeros((seg_mask_.shape[0], seg_mask_.shape[1], 3), dtype=np.uint8)
            for index, seg_class in enumerate(params.seg_list):
                #print(index)
                #print(seg_class)
                color_seg[seg_mask_ == index+1] = color_list_seg[seg_class]
            color_seg = color_seg[..., ::-1]  # RGB -> BGR
            #cv2.imwrite(out_dir + 'seg_only.jpg', color_seg)
            # cv2.imwrite('seg_only_{}.jpg'.format(i), color_seg)

            #print(seg_mask_.shape[0])
            #print(seg_mask_.shape[1])

            lane_seg = np.zeros((seg_mask_.shape[0], seg_mask_.shape[1], 3), dtype=np.uint8)
            lane_seg[seg_mask_ == 2] = 255
            lane_seg = lane_seg[..., ::-1]  # RGB -> BGR
            #cv2.imwrite(out_dir + 'lane_only.jpg', lane_seg)

            # 白線抽出
            frame_data = do_detect_lane(lane_seg, frame.copy(), out_dir, img_file_name, lane_param)

            '''
            # numpy.float32型をPython floatに変換（再帰的に変換）
            def convert_numpy_types(obj):
                if isinstance(obj, np.float32):
                    return float(obj)
                elif isinstance(obj, np.int32):
                    return int(obj)
                elif isinstance(obj, np.int64):
                    return int(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(v) for v in obj]
                elif isinstance(obj, tuple):
                    return tuple(convert_numpy_types(v) for v in obj)
                return obj

            # frame_data全体を変換
            frame_data = convert_numpy_types(frame_data)
            '''

            # フレームデータを結果に追加
            lane_detection_results["results"].append(
                {"frame": current_frame_no, "file": os.path.join(out_dir, img_file_name), "lane_data": frame_data})


            '''
            color_mask = np.mean(color_seg, 2)  # (H, W, C) -> (H, W), check if any pixel is not background
            frame[color_mask != 0] = frame[color_mask != 0] * 0.5 + color_seg[color_mask != 0] * 0.5
            frame = frame.astype(np.uint8)
            # cv2.imwrite('seg_{}.jpg'.format(i), ori_img)

            out = postprocess(x,
                              anchors, regression, classification,
                              regressBoxes, clipBoxes,
                              threshold, iou_threshold)
            out = out[0]
            out['rois'] = scale_coords(frame[:2], out['rois'], shapes[0], shapes[1])
            for j in range(len(out['rois'])):
                x1, y1, x2, y2 = out['rois'][j].astype(int)
                obj = obj_list[out['class_ids'][j]]
                score = float(out['scores'][j])
                plot_one_box(frame, [x1, y1, x2, y2], label=obj, score=score,
                             color=color_list[get_index_label(obj, obj_list)])

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            #cv2.imwrite(out_dir + 'seg_' + img_file_name, frame)
            '''

        bar.update(1)

    bar.close()

    # 結果をJSON形式で保存
    with open(os.path.join(out_dir, "lane_detection_results.json"), "w", encoding="utf-8") as f:
        json.dump(lane_detection_results, f, ensure_ascii=False, indent=2)

