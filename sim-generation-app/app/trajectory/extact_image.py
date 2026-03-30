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
from tqdm import tqdm

def add_csv_data(csv_row_data, adding):
    if np.isnan(adding):
        return csv_row_data + ','
    return csv_row_data + ',' + str(adding)


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

def extract(movie_file, out_img_dir, out_frame_file, frame_step, time_step):

    cap = cv2.VideoCapture(movie_file)

    frame_no = 0
    t = 0.0

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    f = open(out_frame_file, mode='w')
    f.write('frame,frame_time\n')

    bar = tqdm(total=frame_count, dynamic_ncols=True, desc="extract image")
    while True:
        ret, img = cap.read()
        if img is not None:
            #print(str(frame_no) + ' ' + str(t))
            imwrite(os.path.join(out_img_dir, str(frame_no) + '.png'), img)
            csv_row_data = str(frame_no)
            csv_row_data = add_csv_data(csv_row_data, t)
            f.write(csv_row_data + '\n')
            t += time_step
            frame_no += frame_step
            bar.update(1)
        else:
            break

    cap.release()

    f.close()
    
    bar.close()


