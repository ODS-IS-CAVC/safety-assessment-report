import os
import sys
import shutil
import pandas as pd
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from tqdm import tqdm

def add_csv_data(csv_row_data, adding):
    if np.isnan(adding):
        return csv_row_data + ','
    return csv_row_data + ',' + str(adding)


def calc_txt_pos(x_ary, y_ary, target_y_ary, i):
    shift_x = -(np.nanmax(x_ary) - np.nanmin(x_ary)) / 20
    shift_y = (np.nanmax(y_ary) - np.nanmin(y_ary)) / 20
    return (x_ary[i] + shift_x, target_y_ary[i] + shift_y)


def do_plot(i, out_dir, f, t, gx, gx_ma, lat, lon, spd, spd_ma):

    t_max = 60

    frame = f[i]

    font_name = 'Yu Gothic'
    #font_name = 'Helvetica'
    #font_name = 'Arial'

    plt.plot(lon, lat)
    if i >= 0 and not np.isnan(lat[i]):
        plt.plot(lon[i], lat[i], 'o', color="blue")
        txt = str(lat[i]) + '\n' + str(lon[i])
        pos = calc_txt_pos(lon, lat, lat, i)
        plt.text(pos[0], pos[1], txt, fontsize=11)
        #plt.text(pos[0], pos[1], txt, fontsize=8)
    plt.xlabel('Longitude', fontsize=18)
    plt.ylabel('Latitude', fontsize=18)
    plt.title('Coordinate', fontsize=18)
    #plt.xlabel('Longitude', fontsize=14)
    #plt.ylabel('Latitude', fontsize=14)
    #plt.title('Coordinate', fontsize=14)

    if i >= 0:
        plt.savefig(os.path.join(out_dir, 'coord_' + str(frame) + '.png'))
    else:
        plt.savefig(os.path.join(out_dir, 'coord.png'))
    plt.cla()


    plt.xlim(0, t_max)
    #plt.ylim(-1.5, 1.5)
    plt.ylim(-1.0, 1.0)
    #plt.axhline(y=0, xmin=0, xmax=t_max, linestyle='dotted', color='black')
    plt.plot(t, gx, color='lightgray')
    plt.plot(t, gx_ma)
    if i >= 0 and not np.isnan(gx_ma[i]):
        plt.plot(t[i], gx_ma[i], 'o', color="blue")
        txt = "{:.2f} G".format(gx_ma[i])
        pos = calc_txt_pos(t, [-1, 1], gx_ma, i)
        plt.text(pos[0], pos[1], txt, fontsize=11)
        #plt.text(pos[0], pos[1], txt, fontsize=8)
    plt.xlabel('Time (s)', fontsize=18)
    plt.ylabel('G', fontsize=18)
    plt.title('G X', fontsize=18)
    #plt.xlabel('Time (s)', fontsize=14)
    #plt.ylabel('G', fontsize=14)
    #plt.title('G X', fontsize=14)

    if i >= 0:
        plt.savefig(os.path.join(out_dir, 'gx_' + str(frame) + '.png'))
    else:
        plt.savefig(os.path.join(out_dir, 'gx.png'))
    plt.cla()

    plt.xlim(0, t_max)
    plt.ylim(0, 120)
    #plt.axhline(y=0, xmin=0, xmax=t_max, linestyle='dotted', color='black')
    plt.plot(t, spd, color='lightgray')
    plt.plot(t, spd_ma)
    if i >= 0 and not np.isnan(spd_ma[i]):
        plt.plot(t[i], spd_ma[i], 'o', color="blue")
        txt = "{:.1f} km/h".format(spd_ma[i])
        pos = calc_txt_pos(t, [0, 120], spd_ma, i)
        plt.text(pos[0], pos[1], txt, fontsize=11)
        #plt.text(pos[0], pos[1], txt, fontsize=8)
    plt.xlabel('Time (s)', fontsize=18)
    plt.ylabel('Speed (km/h)', fontsize=18)
    plt.title('Speed', fontsize=18)
    #plt.xlabel('Time (s)', fontsize=14)
    #plt.ylabel('Speed (km/h)', fontsize=14)
    #plt.title('Speed', fontsize=14)

    if i >= 0:
        plt.savefig(os.path.join(out_dir, 'spd_' + str(frame) + '.png'))
    else:
        plt.savefig(os.path.join(out_dir, 'spd.png'))
    plt.cla()


# 各タイムステップごとのグラフを描画する
def do_process(ego_data_file, tmp_dir, out_dir):

    if not os.path.isfile(ego_data_file):
        return

    df = pd.read_csv(ego_data_file, header=0, index_col=False)

    fig = plt.figure()

    plt.tick_params(labelsize=14)
    plt.subplots_adjust(left=0.2, right=0.95, bottom=0.15, top=0.90)

    f = np.array(df['frame'])
    t = np.array(df['frame_time'])

    if 'speed' in df.columns:
        lat = np.array(df['latitude'])
        lon = np.array(df['longitude'])
        spd = np.array(df['speed'])
        spd_ma = np.array(df['speed_ma'])
        gx = np.array(df['gx_from_speed'])
        gx_ma = np.array(df['gx_from_speed_ma'])

        do_plot(-1, tmp_dir, f, t, gx, gx_ma, lat, lon, spd, spd_ma)

        bar = tqdm(total=len(f), dynamic_ncols=True, desc="plot graph")
        for i in range(0, len(f)):
            #print('===============================')
            #print(i)
            do_plot(i, out_dir, f, t, gx, gx_ma, lat, lon, spd, spd_ma)
            bar.update(1)
        bar.close()
    else:
        nan_array = np.full_like(f, np.nan, dtype=np.float64)
        gx = nan_array
        gx_ma = nan_array
        lat = nan_array
        lon = nan_array
        spd = nan_array
        spd_ma = nan_array

        do_plot(-1, tmp_dir, f, t, gx, gx_ma, lat, lon, spd, spd_ma)

