import os
import math


DEBUG = False

# 水平方向視野角
HORIZONTAL_FOV = 120  # 120°

# 地上からのカメラの高さ
CAMERA_DEFAULT_HEIGHT = 1.6  # 1.6(m)
CAMERA_HEIGHT_SETTINGS = {
    'car': 1.6,
    'bus': 3.0,
    'truck': 3.0
}

# threshold
CAMERA_ELEVATION_ANGLE_DIFF_THD = math.pi/180
MAX_ACC_TIME_THD = 1    # (s)
LANE_WIDTH_THD = 3.0    # (m)
VECTORS_ANGLE_THD = 45  # (degree)
DETECTION_YAW_THD = 10  # (degree)

# yolo settings
YOLO_V8_MODEL_FILE = os.path.abspath(os.path.join(os.path.abspath(__file__), "../../yolo/yolov8l.pt"))
# 対象とする検出クラス
TARGET_DETECTION_CLASS = ["car", "bus", "truck"]
DETECTION_CONF_THD = 0.6
DETECTION_IOU_THD = 0.45
DEPRICATE_IOU_THD = 0.97  # 物体検出後、重複物体とみなす閾値

# original tracking settings
MAX_DISTANCE_TRACKER = 300  # トラッキングで同一物体とみなす距離の最大値
MAX_DISSAPPEAR_FRAME_NUM_TRACKER = 40  # トラッキングで検出できなかった物体を保持する最大フレーム数
COS_SIM_THD_TRACKER = 0.55  # トラッキングで同一物体とみなすcos類似度の閾値
IOU_THD_TRACKER = 0.001  # トラッキングで同一物体とみなすIoUの閾値
MOVING_AVERAGE_WIDTH_TRACKER = 3  # トラッキングで移動平均を考えるときの幅

# output file name format
REL_COORD_IMG_SUFFIX = '_visualized_rel_coords'
ABS_COORD_IMG_SUFFIX = '_visualized_abs_coords'
REL_COORD_JSON_FILE_NAME = 'detection_distance_result.json'
GPS_CSV_SUFFIX = "_updated"
ABS_COORD_JSON_FILE_NAME = 'car_abs_pos_result.json'
ABS_COORD_JSON_SUFFIX = '_abs_coord'            # detection_distance_result_abs_coord.json
ABS_COORD_CORRECTED_JSON_SUFFIX = '_corrected'  # detection_distance_result_abs_coord_corrected.json
ROAD_CORRECT_TARGETS_FILE_NAME = 'road_correct_targets.json'

# visualize tool settings
VISUALIZE_IMG_SIZE = [540, 540]
METER_PER_PIXEL = 4.0
SELF_COORD_COLOR = (1, 0, 0)    # red
COORD_RADIUS = 6                # pixel
RANDOM_COLOR_VALUES = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
ZOOM_RANGE = 50  # m

# 座標系原点の経緯度
LAT_LONG_ORG = {
    "6669": {
        "name": "JGD 2011/1",
        "lon": "129度30分0秒0000",
        "lat": "33度0分0秒0000"
    },
    "6670": {
        "name": "JGD 2011/2",
        "lon": "131度 0分0秒0000",
        "lat": "33度0分0秒0000"
    },
    "6671": {
        "name": "JGD 2011/3",
        "lon": "132度10分0秒0000",
        "lat": "36度0分0秒0000"
    },
    "6672": {
        "name": "JGD 2011/4",
        "lon": "133度30分0秒0000",
        "lat": "33度0分0秒0000"
    },
    "6673": {
        "name": "JGD 2011/5",
        "lon": "134度20分0秒0000",
        "lat": "36度0分0秒0000"
    },
    "6674": {
        "name": "JGD 2011/6",
        "lon": "136度 0分0秒0000",
        "lat": "36度0分0秒0000"
    },
    "6675": {
        "name": "JGD 2011/7",
        "lon": "137度10分0秒0000",
        "lat": "36度0分0秒0000"
    },
    "6676": {
        "name": "JGD 2011/8",
        "lon": "138度30分0秒0000",
        "lat": "36度0分0秒0000"
    },
    "6677": {
        "name": "JGD 2011/9",
        "lon": "139度50分0秒0000",
        "lat": "36度0分0秒0000"
    },
    "6678": {
        "name": "JGD 2011/10",
        "lon": "140度50分0秒0000",
        "lat": "40度0分0秒0000"
    },
    "6679": {
        "name": "JGD 2011/11",
        "lon": "140度15分0秒0000",
        "lat": "44度0分0秒0000"
    },
    "6680": {
        "name": "JGD 2011/12",
        "lon": "142度15分0秒0000",
        "lat": "44度0分0秒0000"
    },
    "6681": {
        "name": "JGD 2011/13",
        "lon": "144度15分0秒0000",
        "lat": "44度0分0秒0000"
    },
    "6682": {
        "name": "JGD 2011/14",
        "lon": "142度 0分0秒0000",
        "lat": "26度0分0秒0000"
    },
    "6683": {
        "name": "JGD 2011/15",
        "lon": "127度30分0秒0000",
        "lat": "26度0分0秒0000"
    },
    "6684": {
        "name": "JGD 2011/16",
        "lon": "124度 0分0秒0000",
        "lat": "26度0分0秒0000"
    },
    "6685": {
        "name": "JGD 2011/17",
        "lon": "131度 0分0秒0000",
        "lat": "26度0分0秒0000"
    },
    "6686": {
        "name": "JGD 2011/18",
        "lon": "136度 0分0秒0000",
        "lat": "20度0分0秒0000"
    },
    "6687": {
        "name": "JGD 2011/19",
        "lon": "154度 0分0秒0000",
        "lat": "26度0分0秒0000"
    }
}

YOLOCLASSES = {
    "person": 0,
    "bicycle": 1,
    "car": 2,
    "motorcycle": 3,
    "airplane": 4,
    "bus": 5,
    "train": 6,
    "truck": 7,
    "boat": 8,
    "traffic light": 9,
    "fire hydrant": 10,
    "stop sign": 11,
    "parking meter": 12,
    "bench": 13,
    "bird": 14,
    "cat": 15,
    "dog": 16,
    "horse": 17,
    "sheep": 18,
    "cow": 19,
    "elephant": 20,
    "bear": 21,
    "zebra": 22,
    "giraffe": 23,
    "backpack": 24,
    "umbrella": 25,
    "handbag": 26,
    "tie": 27,
    "suitcase": 28,
    "frisbee": 29,
    "skis": 30,
    "snowboard": 31,
    "sports ball": 32,
    "kite": 33,
    "baseball bat": 34,
    "baseball glove": 35,
    "skateboard": 36,
    "surfboard": 37,
    "tennis racket": 38,
    "bottle": 39,
    "wine glass": 40,
    "cup": 41,
    "fork": 42,
    "knife": 43,
    "spoon": 44,
    "bowl": 45,
    "banana": 46,
    "apple": 47,
    "sandwich": 48,
    "orange": 49,
    "brocolli": 50,
    "carrot": 51,
    "hot dog": 52,
    "pizza": 53,
    "donut": 54,
    "cake": 55,
    "chair": 56,
    "couch": 57,
    "potted plant": 58,
    "bed": 59,
    "dining table": 60,
    "toilet": 61,
    "tv": 62,
    "laptop": 63,
    "mouse": 64,
    "remote": 65,
    "keyboard": 66,
    "cell phone": 67,
    "microwave": 68,
    "oven": 69,
    "toaster": 70,
    "sink": 71,
    "refrigerator": 72,
    "book": 73,
    "clock": 74,
    "vase": 75,
    "scissors": 76,
    "teddy bear": 77,
    "hair drier": 78,
    "toothbrush": 79
  }