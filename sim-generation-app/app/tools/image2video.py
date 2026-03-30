import os
import glob
import argparse
from tqdm import tqdm
import cv2


def image_to_video(input_dir, output_path, frame_skip):
    # 出力フォルダ作成
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    # フォルダ内の画像のファイルリストを取得する
    #files  = glob.glob(os.path.join(input_dir, '*.png'))
    files = glob.glob(os.path.join(input_dir, '*.jpg'))
    files.sort()
    frames=len(files)
    assert frames != 0, 'not found image file'    # 画像ファイルが見つからない

    # 最初の画像の情報を取得する
    img = cv2.imread(files[0])
    h, w, channels = img.shape[:3]

    # 作成する動画
    codec = cv2.VideoWriter_fourcc(*'mp4v')
    #codec = cv2.VideoWriter_fourcc(*'avc1')
    fps = 30
    if frame_skip == 1:
        fps = 15

    writer = cv2.VideoWriter(output_path, codec, fps, (w, h),1)

    bar = tqdm(total=frames, dynamic_ncols=True, desc="image2video")
    for f in files:
        # 画像を1枚ずつ読み込んで 動画へ出力する
        img = cv2.imread(f)
        writer.write(img)   
        bar.update(1)
        
    bar.close()
    writer.release()


def main():
    # 引数をパースする
    parser = argparse.ArgumentParser(description="画像から動画にする")
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        default="input",
        help="入力画像フォルダパス",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        default="output",
        help="出力結果ファイルパス",
    )
    parser.add_argument(
        "--frame_skip",
        type=int,
        required=False,
        default=0,
        help="frame-skipは任意（タイプ：int; default=0）",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    assert isinstance(input_dir, str)

    output_path = args.output_path
    assert isinstance(output_path, str)
    frame_skip = args.frame_skip
    assert isinstance(frame_skip, int)

    image_to_video(input_dir, output_path, frame_skip)

if __name__ == "__main__":
    main()
