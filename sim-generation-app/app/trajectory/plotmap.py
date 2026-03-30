import os
import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point, LineString
import matplotlib.pyplot as plt
import contextily as ctx
from tqdm import tqdm



def calc_txt_pos(x_ary, y_ary, target_y_ary, i):
    shift_x = -(np.nanmax(x_ary) - np.nanmin(x_ary)) / 20
    shift_y = (np.nanmax(y_ary) - np.nanmin(y_ary)) / 20
    return (x_ary[i] + shift_x, target_y_ary[i] + shift_y)


def do_plot(i, out_dir, f, t, latitudes, longitudes):

    t_max = 60

    # Pointsの作成
    points = [Point(lon, lat) for lon, lat in zip(longitudes, latitudes)]

    # GeoDataFrameを作成
    gdf = gpd.GeoDataFrame(geometry=points, crs="EPSG:4326")

    # 線を描画
    line = LineString(points)

    # プロットのサイズ調整
    fig, ax = plt.subplots(figsize=(6.4, 3.6))

    # GeoDataFrameを投影してプロット
    gdf = gdf.to_crs(epsg=3857)
    gpd.GeoSeries(line, crs="EPSG:4326").to_crs(epsg=3857).plot(ax=ax, color='blue', linewidth=2)

    if i >= 0 and not np.isnan(latitudes[i]):
        gdf.iloc[[i]].plot(ax=ax, color='red', markersize=100, zorder=5)

        #x, y = gdf.geometry.x.iloc[i], gdf.geometry.y.iloc[i]
        #lat, lon = latitudes[i], longitudes[i]
        #ax.annotate(f'({lat}, {lon})', xy=(x, y), xytext=(3, 3), textcoords='offset points', fontsize=8, color='black')

    # 地図の表示範囲をデータに合わせる
    xlim = [gdf.geometry.x.min() - 1000, gdf.geometry.x.max() + 1000]
    ylim = [gdf.geometry.y.min() - 1000, gdf.geometry.y.max() + 1000]
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)

    # OpenStreetMapの背景を追加
    #ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik, zoom=14)

    # 軸の非表示
    ax.set_axis_off()

    # サイズ調整
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    # 画像として保存
    if i >= 0:
        frame = f[i]
        #plt.savefig(out_dir + 'map_' + str(frame) + '.png', bbox_inches='tight', pad_inches=0, dpi=100)  # dpiを調整
        plt.savefig(os.path.join(out_dir, 'map_' + str(frame) + '.png'), pad_inches=0)
    else:
        #plt.savefig(out_dir + 'map.png', bbox_inches='tight', pad_inches=0, dpi=100)  # dpiを調整
        plt.savefig(os.path.join(out_dir, 'map.png'), pad_inches=0)
    plt.cla()

    # プロットをクリア
    plt.close()


# 各タイムステップごとのグラフを描画する
def do_process(ego_data_file, tmp_dir, out_dir):

    if not os.path.isfile(ego_data_file):
        return

    df_org = pd.read_csv(ego_data_file, header=0, index_col=False)

    df = df_org[df_org['latitude'] != 0]

    f = np.array(df['frame'])
    t = np.array(df['frame_time'])

    if len(f) > 0:
        if 'latitude' in df.columns:
            lat = np.array(df['latitude'])
            lon = np.array(df['longitude'])

            do_plot(-1, tmp_dir, f, t, lat, lon)

            bar = tqdm(total=len(f), dynamic_ncols=True, desc="plot map")
            for i in range(0, len(f), 15):
                #print('===============================')
                #print(i)
                do_plot(i, out_dir, f, t, lat, lon)
                bar.update(15)
            bar.close()

        #else:
        #    nan_array = np.full_like(f, np.nan, dtype=np.float64)
        #    lat = nan_array
        #    lon = nan_array
        #    do_plot(-1, tmp_dir, f, t, lat, lon)

