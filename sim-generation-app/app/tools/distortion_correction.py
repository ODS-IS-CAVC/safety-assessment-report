import os
import glob
import argparse
import shutil
import numpy as np
import cv2
from tqdm import tqdm


def distortion_correction(input_dir, output_dir, intrinsic_camera_matrix_path, dist_coeffs_path):
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    if intrinsic_camera_matrix_path is None:
        intrinsic_camera_matrix_path = os.path.join(curr_dir, 'intrinsic_camera_matrix.npy')
    calibration_matrix_P2_path = os.path.join(curr_dir, 'calibration_matrix_P2.npy')
    if dist_coeffs_path is None:
        dist_coeffs_path = os.path.join(curr_dir, 'dist_coeffs.npy')

    # Load the intrinsic matrix, P2 matrix, and distortion coefficients
    if os.path.exists(intrinsic_camera_matrix_path) and os.path.exists(calibration_matrix_P2_path) and os.path.exists(dist_coeffs_path):
        intrinsic_matrix = np.load(intrinsic_camera_matrix_path)
        P2 = np.load(calibration_matrix_P2_path)
        if P2.size != 12:
            raise ValueError("Invalid P2 matrix size.")
        P2 = P2.reshape(3, 4)
        dist_coeffs = np.load(dist_coeffs_path)
        print("Loaded intrinsic camera matrix, projection matrix (P2), and distortion coefficients:")
        print(intrinsic_matrix)
        print(P2)
        print(dist_coeffs)
    # else:
    #     assert()

    # フォルダ内の画像のファイルリストを取得する
    files = glob.glob(os.path.join(input_dir, '*.jpg'))
    files.sort()
    frames=len(files)
    assert frames != 0, 'not found image file'    # 画像ファイルが見つからない

    # 出力フォルダ作成
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 最初の画像の情報を取得する
    img = cv2.imread(files[0])
    h, w, channels = img.shape[:3]

    # プログレスバー
    bar = tqdm(total=frames, dynamic_ncols=True, desc="distortion")
    for f in files:
        # 画像を1枚ずつ読み込んで 補正画像を出力フォルダに保存する
        img = cv2.imread(f)
        undistorted_frame = cv2.undistort(img, intrinsic_matrix, dist_coeffs)

        name = os.path.splitext(os.path.basename(f))[0]
        # output_fn = name + "_correction.jpg"
        output_fn = name + ".jpg"
        output_path = os.path.join(output_dir, output_fn)
        cv2.imwrite(output_path, undistorted_frame)
        bar.update(1)
        
    bar.close()


def main():
    # 引数をパースする
    parser = argparse.ArgumentParser(description="画像の歪みを補正する")
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        default="input",
        help="入力画像フォルダパス",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        default="output",
        help="出力結果フォルダパス",
    )
    parser.add_argument(
        "--intrinsic_camera_matrix_path",
        type=str,
        default=None,
        help="出力結果フォルダパス",
    )
    parser.add_argument(
        "--dist_coeffs_path",
        type=str,
        default=None,
        help="出力結果フォルダパス",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    assert isinstance(input_dir, str)

    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    intrinsic_camera_matrix_path = args.intrinsic_camera_matrix_path
    assert isinstance(intrinsic_camera_matrix_path, str)
    
    dist_coeffs_path = args.dist_coeffs_path
    assert isinstance(dist_coeffs_path, str)
    
    distortion_correction(input_dir, output_dir, intrinsic_camera_matrix_path, dist_coeffs_path)


if __name__ == "__main__":
    main()
