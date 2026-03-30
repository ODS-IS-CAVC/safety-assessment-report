import logging
import os
import re
import argparse
import pandas as pd

logger = logging.getLogger(__name__)


def time_to_frame(time):
    frame = int(time * 30)
    if frame % 2 == 1:
        frame += 1
    return frame


def time_to_str_time(time:float):
    time_str = f"{time:.3f}"
    return time_str.replace('.',':')


def time_to_numeric(time_str):
    """時刻の文字列を数値に変換

    Args:
        time_str (str): HH:MM:SS.MSの文字列(タイプ:string)
    """
    hours, minutes, seconds = time_str.split(':')
    seconds, milliseconds = seconds.split('.')
    numeric_time = int(hours) * 10000 + int(minutes) * 100 + int(seconds) + float('0.' + milliseconds)
    return numeric_time


def get_time_substr_hhmm(time_str):
    # 小数点の前の部分（整数部分）のみを取得
    time_int_part = time_str.split('.')[0]
    hhmmss_str_length = len(time_int_part)

    if hhmmss_str_length < 6:
        substr_length = 4 - (6 - hhmmss_str_length)
        if substr_length <= 0:
            time_hm = 0
        else:
            time_hm = int(time_int_part[:substr_length])
    else:
        time_hm = int(time_int_part[:4])

    return time_hm


def extract_video_date_pattern(video_filepath):
    pattern = r'(\d{6}_\d{6})'
    match = re.search(pattern, video_filepath)
    
    if match:
        return match.group(1)
    else:
        return ""
    

def time_to_seconds(time_str):
    """時刻文字列を秒数に変換 (HH:MM:SS.MS -> total seconds)"""
    hours, minutes, seconds = time_str.split(':')
    seconds_float = float(seconds)
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + seconds_float
    return total_seconds


def conert_sensor_data_txt_to_csv(input_path, start_time=0, end_time=-1):
    if not os.path.exists(input_path):
        logger.error("%s が見つかりませんでした。", input_path)
        return

    sensor_df = pd.read_csv(input_path, encoding="utf-8")

    # Convert time strings to seconds since midnight
    time_seconds_list = []
    prev_seconds = None
    day_offset = 0

    for time_str in sensor_df['time']:
        seconds = time_to_seconds(time_str)

        # Detect midnight crossing (time goes backwards significantly)
        if prev_seconds is not None and seconds < prev_seconds - 3600:
            day_offset += 1

        # Add 24 hours for each day crossed
        adjusted_seconds = seconds + (day_offset * 86400)
        time_seconds_list.append(adjusted_seconds)
        prev_seconds = seconds

    # Normalize to zero-based timing
    first_time = time_seconds_list[0]
    zero_time_list = [t - first_time for t in time_seconds_list]

    start_index = None
    end_index = None

    for i, time in enumerate(zero_time_list):
        if start_index is None and time >= start_time:
            start_index = i
        if end_time != -1.0 and time >= end_time:
            end_index = i - 1
            break

    # no index beyond end_time is found
    if end_index is None:
        end_index = len(zero_time_list) - 1

    # triming
    trim_df = sensor_df.iloc[start_index:end_index + 1].copy()
    trim_time_seconds_list = time_seconds_list[start_index:end_index + 1]

    # lat, lon列にリネーム
    trim_df = trim_df.rename(columns={'latitude': 'lat'})
    trim_df = trim_df.rename(columns={'longitude': 'lon'})
    trim_df = trim_df.rename(columns={'time': 'jst_time'})

    # 時刻情報を一時的に追加
    trim_df['time_seconds'] = trim_time_seconds_list

    # 重複データ削除
    trim_df.drop_duplicates(subset=['lat', 'lon'], inplace=True)

    # 0データ削除
    trim_df = trim_df[(trim_df['lat'] != 0.0) & (trim_df['lon'] != 0.0)]

    # データが空かチェック
    if trim_df.empty:
        logger.warning("%s に有効なGPSデータ（lat/lonが0以外）が存在しません。", input_path)
        return

    # フィルタ後の時刻リストを取得して再正規化（1行目が0秒になるように）
    filtered_time_seconds = trim_df['time_seconds'].tolist()
    first_filtered_time = filtered_time_seconds[0]
    zero_time_list = [t - first_filtered_time for t in filtered_time_seconds]

    # time・frame列追加
    # 一時カラムを削除
    trim_df.drop(columns=['time_seconds'], inplace=True)

    # time列を文字列形式に変換して挿入
    time_str_list = [time_to_str_time(t) for t in zero_time_list]
    trim_df.insert(0, 'time', time_str_list)

    # frame列を計算して先頭に挿入
    frame_list = [time_to_frame(t) for t in zero_time_list]
    trim_df.insert(0, 'frame', frame_list)

    # output divp .csv
    file_name = extract_video_date_pattern(os.path.basename(input_path))
    output_file_path = os.path.join(os.path.dirname(input_path), f"gps_{file_name}.csv")
    trim_df.to_csv(output_file_path, index=False, encoding='utf-8')


def main():
    # 引数をパースする
    parser = argparse.ArgumentParser(description="gセンサーデータをトリミングしcsvに変換機能")
    parser.add_argument(
        "--input_path",
        type=str,
        required=True,
        help="gセンサーテキストファイルパス（タイプ：string）",
    )
    parser.add_argument(
        "--start_time",
        type=float,
        required=False,
        default=0.0,
        help="抽出開始時間（タイプ：float; default=0.0）",
    )
    parser.add_argument(
        "--end_time",
        type=float,
        required=False,
        default=-1.0,
        help="抽出終了時間（タイプ：float; default=-1）",
    )

    # 入力引数をパースする
    args = parser.parse_args()

    input_path = args.input_path
    assert isinstance(input_path, str)

    start_time = args.start_time
    assert isinstance(start_time, float)

    end_time = args.end_time
    assert isinstance(end_time, float)

    conert_sensor_data_txt_to_csv(
        input_path=input_path,
        start_time=start_time,
        end_time=end_time
    )


if __name__ == "__main__":
    main()
