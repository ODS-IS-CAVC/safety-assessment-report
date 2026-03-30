import math
import numpy as np
from numpy.linalg import norm


def unit_v(vec: list):
    """単位ベクトルの計算
 
    Args:
        vec (list): 入力ベクトル
 
    Returns:
        list: 単位ベクトル
    """
    if (len(vec) < 2) or (vec[0] == 0 and vec[1] == 0):
        return -1
    vec_len = math.sqrt(vec[0]**2 + vec[1]**2)
    u_vec = [vec[0]/vec_len, vec[1]/vec_len]
    return u_vec


def get_perp_vec(vec: list, is_right_side: bool):
    """ベクトルと垂直なベクトルを計算
 
    Args:
        vec (list): 入力ベクトル
        is_right_side (bool): 垂直なベクトルが入力ベクトルの右側であるか
 
    Returns:
        list: 垂直なベクトル
    """
    perp_vec = [vec[1], -vec[0]] if is_right_side else [-vec[1], vec[0]]
    return perp_vec


def calc_line_weight(point1, point2):
    """Calculate line weights

    Args:
        point1 (list): first point coordinate
        point2 (list): second point coordinate

    Returns:
        (float, float): slope, y-intercept
    """
    x1, y1 = point1
    x2, y2 = point2
    if x1 == x2:
        return None, x1
    m = (y2 - y1) / (x2 - x1)
    b = y1 - m*x1
    return m, b


def find_two_line_intersect(point11, point12, point21, point22):
    """Find intersect point between two line

    Args:
        point11 (list): first point coordinate of line 1
        point12 (list): second point coordinate of line 1
        point21 (list): first point coordinate of line 2
        point22 (list): second point coordinate of line 2

    Returns:
        (float, float): x, y
    """
    m1, b1 = calc_line_weight(point11, point12)
    m2, b2 = calc_line_weight(point21, point22)
    intersect_x, intersect_y = find_two_line_intersect_from_weight(m1, b1, m2, b2)
    return intersect_x, intersect_y


def find_two_line_intersect_from_weight(m1, b1, m2, b2):
    """Find intersect point between two line

    Args:
        m1 (float): slope of line 1
        b1 (float): y-intercept of line 1
        m2 (float): slope of line 2
        b2 (float): y-intercept of line 2

    Returns:
        (float, float): x, y
    """
    if m1 == m2:
        return None, None
    
    if m1 is None:
        intersect_x = b1
        intersect_y = m2 * intersect_x + b2
    elif m2 is None:
        intersect_x = b2
        intersect_y = m1 * intersect_x + b1
    else:
        intersect_x = (b2 - b1) / (m1 - m2)
        intersect_y = m1 * intersect_x + b1
    
    return intersect_x, intersect_y


def get_distance_2d(point1, point2):
    """Get distance between two point 2D

    Args:
        point1 (list): coordinate of point 1
        point2 (list): coordinate of point 2

    Returns:
        float: distance
    """
    dist = math.sqrt((point2[0] - point1[0])**2 + (point2[1] - point1[1])**2)
    return dist


def get_angle_2d(dx, dy):
    """Calculate angle in standard Oxy coordinate system

    Args:
        dx (float): coordinates in the x direction
        dy (float): coordinates in the y direction

    Returns:
        float: angle (radian)
    """
    angle = math.atan2(dy, dx)
    return angle if angle >=0 else angle + math.pi * 2


def get_angle_2d_from_vec(vec1, vec2):
    """Calculate angle between two unit vector

    Args:
        vec1 (list): first vector
        vec2 (list): second vector
    """
    cos_theta = (vec1[0] * vec2[0] + vec1[1] * vec2[1])
    angle = None
    if (cos_theta >= 1.0):
        angle = 0.0
    elif (cos_theta <= -1.0):
        angle = math.pi
    else:
        angle = math.acos(cos_theta) #0..PI

    # vec2 is counterclockwise compared to vec1: 0..pi
    # vec2 is clockwise compared to vec1: -pi..0
    vec2_rot90CCW = [-vec2[1], vec2[0]]
    cos_theta2 = (vec1[0] * vec2_rot90CCW[0] + vec1[1] * vec2_rot90CCW[1])
    if (cos_theta2 < 0): # vec2 left vec1 (clockwise)
        angle = -angle

    return angle


def pixel2cartesian(pxl, img_h):
    x = pxl[0]
    y = img_h - pxl[1]
    return [x, y]


def cartesian2pixel(coord, img_h):
    x = coord[0]
    y = img_h - coord[1]
    return [x, y]


def calc_IoU(bbox1: list[float], bbox2: list[float]) -> float:
    """Calculate IoU between two bboxes(x_min, y_min, x_max, y_max)

    Args:
        bbox1 (list): first bbox
        bbox2 (list): second bbox
    """
    lx = max(bbox1[0], bbox2[0])
    rx = min(bbox1[2], bbox2[2])
    ly = max(bbox1[1], bbox2[1])
    ry = min(bbox1[3], bbox2[3])
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    intersection = ((rx - lx) if lx < rx else 0) * ((ry - ly) if ly < ry else 0)
    return intersection / (area1 + area2 - intersection)


def calc_cos_sim(vector1: np.ndarray, vector2: np.ndarray):
    """Calculate cosine similarity between two bectors

    Args:
        vector1 (list): first vector
        vector2 (list): second vector
    """
    if norm(vector1) * norm(vector2) == 0:
        return -1
    return np.dot(vector1, vector2) / (norm(vector1) * norm(vector2))
