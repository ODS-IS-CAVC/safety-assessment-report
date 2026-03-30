import os
import sys
import shutil
import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.gridspec as gridspec
mpl.use('Agg')
import matplotlib.pyplot as plt

def do_process(sensor_file, out_dir):

    if not os.path.isfile(sensor_file):
        return

    df = pd.read_csv(sensor_file, header=0, index_col=False)

    if 'day' in df.columns:

        day_s = df['day'].iloc[0]
        day_e = df['day'].iloc[-1]
        time_s = df['time'].iloc[0]
        time_e = df['time'].iloc[-1]
        lat_s = df['latitude'].iloc[0]
        lat_e = df['latitude'].iloc[-1]
        lon_s = df['longitude'].iloc[0]
        lon_e = df['longitude'].iloc[-1]
        spd_s = df['speed'].iloc[0]
        spd_e = df['speed'].iloc[-1]

        max_spd = df['speed'].max()
        min_spd = df['speed'].min()
        mean_spd = df['speed'].mean()

        str_date = str(day_s) + ' ' + str(time_s) + ' - ' + str(day_e) + ' ' + str(time_e)
        str_lat = str(lat_s) + ' - ' + str(lat_e)
        str_lon = str(lon_s) + ' - ' + str(lon_e)
        str_spd_s = str(spd_s) + ' [km/h]'
        str_spd_e = str(spd_e) + ' [km/h]'
        str_max_spd = str(max_spd) + ' [km/h]'
        str_min_spd = str(min_spd) + ' [km/h]'
        str_mean_spd = '{:.1f} [km/h]'.format(mean_spd)

    else:
        str_date = ''
        str_lat = ''
        str_lon = ''
        str_spd_s = ''
        str_spd_e = ''
        str_max_spd = ''
        str_min_spd = ''
        str_mean_spd = ''

    data = {
        '項目': ['Date Time', 'Latitude', 'Longitude', 'Start speed', 'End speed', 'Max speed', 'Min speed', 'Mean speed'],
        '値': [str_date, str_lat, str_lon, str_spd_s, str_spd_e, str_max_spd, str_min_spd, str_mean_spd]
    }

    df = pd.DataFrame(data)

    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot()

    # 列見出しを表示しないようにテーブルを描画
    table = ax.table(cellText=df.values, loc='center', cellLoc='center', colWidths=[0.3, 0.7])
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    # 軸をオフに
    ax.axis('off')

    # プロットを表示
    plt.tight_layout()

    plt.savefig(os.path.join(out_dir, 'table.png'))



