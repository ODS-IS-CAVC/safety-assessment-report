import os
import sys

import cv2
import numpy as np
import matplotlib.pyplot as plt
import io
from PIL import Image
from scipy import stats

from commons.math_util import calc_line_weight


def read_image(image_path: str):
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    return image


def save_image(image_path: str, image, image_type='.jpg') -> bool:
    retval, buf_arr = cv2.imencode(image_type, image)
    if retval:
        buf_arr.tofile(image_path)
        return True
    return False


def show_image(img, winname=None):
    winname_ = winname if winname else 'image'
    cv2.imshow(winname_, img)
    cv2.moveWindow(winname_, 100, 100)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def get_center_coordinates(image_path):
    im = read_image(image_path)
    h, w, _ = im.shape
    c_x, c_y = w/2, h/2
    return c_x, c_y


def fig2image():
    # Create a bytes buffer to save the plot
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    
    # Open the PNG image from the buffer and convert it to a NumPy array
    rgb_image = np.array(Image.open(buf))

    # Convert BGR (opencv)
    bgr_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)

    # Close the buffer
    buf.close()

    return bgr_image


def adjust_brightness(img, value=30):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    lim = 255 - value
    v[v > lim] = 255
    v[v <= lim] += value

    final_hsv = cv2.merge((h, s, v))
    img = cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)
    return img


def clahe(bgr_img):
    lab = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
    lab_planes = list(cv2.split(lab))
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(100,100))
    lab_planes[0] = clahe.apply(lab_planes[0])
    lab = cv2.merge(lab_planes)
    bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return bgr


def is_in_image(coord, image_w, image_h):
    if (coord[0] >= 0 and coord[0] < image_w) and (coord[1] >= 0 and coord[1] < image_h):
        return True
    return False


def rgb2bgr(rgb_color):
    return [rgb_color[2], rgb_color[1], rgb_color[0]]


def get_contour_min_line(contour: np.ndarray, image_size: list):
    mask_img = np.zeros(image_size, dtype=np.uint8)
    mask_img = cv2.drawContours(mask_img, [contour], -1, 255, -1)
    contour_area_coords = np.where(mask_img == 255)
    contour_area_x_coords = contour_area_coords[1]
    contour_area_y_coords = contour_area_coords[0]
    contour_area_y_coords = image_size[1] - contour_area_y_coords
    result = stats.linregress(contour_area_x_coords, contour_area_y_coords)
    return result
