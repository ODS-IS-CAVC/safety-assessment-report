import argparse
import os
import shutil
import cv2
from tqdm import tqdm


def video_to_images(input_path, output_path, frame_skip=0, start_time=0, end_time=-1, ext="jpg"):
    """動画から画像を抽出する関数

    Args:
        input_path (str): 動画ファイルパス(タイプ：string）
        output_path (str): 出力フォルダパス(タイプ：string）
        frame_skip (int): frame-skipは任意. Defaults to 0.
        start_time (float): 動画からの画像抽出開始時間. Defaults to 0.
        end_time (float): 動画からの画像抽出終了時間. Defaults to -1.
    """

    # 出力フォルダ作成
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    os.makedirs(output_path, exist_ok=True)

    # 動画名を取得する
    file = os.path.basename(input_path)
    name = os.path.splitext(file)[0]

    # 動画をロードする
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"Error: Cannot open video file: {input_path}")
        return

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_frames / video_fps if video_fps > 0 else 0
    video_resolution = (video_width, video_height)

    print(f'Duration: {video_duration}\nFps: {video_fps}\nResolution: {video_resolution}')

    if (start_time < 0 or start_time >= video_duration):
        print('Warning: 指定した開始時間が不正です。')
        cap.release()
        return
    if ((end_time != -1) and (end_time <= 0 or end_time > video_duration)):
        print('Warning: 指定した終了時間が不正です。')
        cap.release()
        return

    start_idx = int(start_time * video_fps)
    end_idx = -1 if (end_time == -1) else int(end_time * video_fps)

    # 処理対象のフレーム数を計算
    if end_idx != -1:
        process_frames = min(total_frames, end_idx) - start_idx + 1
    else:
        process_frames = total_frames - start_idx

    # 開始フレームにシーク
    if start_idx > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_idx)

    progress_bar = tqdm(total=process_frames, dynamic_ncols=True, desc="video2image")

    frame_idx = start_idx
    using_skip_frame = (frame_skip != 0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if end_idx != -1 and frame_idx > end_idx:
            break

        # フレームスキップ判定
        if (frame_idx - start_idx) % (frame_skip + 1) == 0:
            output_fn = f"{name}_{frame_idx:05d}.{ext}"
            output_filepath = os.path.join(output_path, output_fn)
            cv2.imwrite(output_filepath, frame)

        frame_idx += 1
        progress_bar.update(1)

    progress_bar.close()
    cap.release()


def main():
    parser = argparse.ArgumentParser(description="動画からの画像切り出し機能")
    parser.add_argument(
        "--input_path",
        type=str,
        required=True,
        help="動画ファイルパス（タイプ：string）",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="出力フォルダパス（タイプ：string）",
    )
    parser.add_argument(
        "--frame_skip",
        type=int,
        required=False,
        default=0,
        help="frame-skipは任意（タイプ：int; default=0）",
    )
    parser.add_argument(
        "--start_time",
        type=float,
        required=False,
        default=0.0,
        help="動画からの画像抽出開始時間（タイプ：float; default=0.0）",
    )
    parser.add_argument(
        "--end_time",
        type=float,
        required=False,
        default=-1.0,
        help="動画からの画像抽出終了時間（タイプ：float; default=-1）",
    )
    parser.add_argument(
        "--ext",
        type=str,
        required=False,
        default="jpg",
        help="出力拡張子（タイプ：str; default=jpg）",
    )

    args = parser.parse_args()

    video_to_images(
        input_path=args.input_path,
        output_path=args.output_path,
        frame_skip=args.frame_skip,
        start_time=args.start_time,
        end_time=args.end_time,
        ext=args.ext
    )


if __name__ == "__main__":
    main()