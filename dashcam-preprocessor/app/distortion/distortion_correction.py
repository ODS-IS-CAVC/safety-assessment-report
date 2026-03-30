import os
import glob
import argparse
import shutil
import json
import logging
import numpy as np
import cv2
from tqdm import tqdm

logger = logging.getLogger(__name__)


def load_camera_intrinsics_from_json(json_path):
    """
    camera_intrinsics.jsonからカメラパラメータを読み込む

    Args:
        json_path: camera_intrinsics.jsonのパス

    Returns:
        tuple: (intrinsic_matrix, dist_coeffs)
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    intrinsic_matrix = np.array(data['camera_matrix'], dtype=np.float64)
    dist_coeffs = np.array(data['distortion_coefficients'], dtype=np.float64)

    return intrinsic_matrix, dist_coeffs


def distortion_correction(input_dir, output_dir, intrinsic_camera_matrix_path, dist_coeffs_path, camera_intrinsics_json_path=None):
    curr_dir = os.path.dirname(os.path.abspath(__file__))

    intrinsic_matrix = None
    dist_coeffs = None

    # camera_intrinsics.jsonが指定されている場合は優先して使用
    if camera_intrinsics_json_path and os.path.exists(camera_intrinsics_json_path):
        logger.info("Loading camera parameters from JSON: %s", camera_intrinsics_json_path)
        intrinsic_matrix, dist_coeffs = load_camera_intrinsics_from_json(camera_intrinsics_json_path)
        logger.info("Loaded intrinsic camera matrix and distortion coefficients from JSON:")
        logger.info("intrinsic_matrix: %s", intrinsic_matrix)
        logger.info("dist_coeffs: %s", dist_coeffs)
    else:
        # 従来のnpyファイルからの読み込み（フォールバック）
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
            logger.info("Loaded intrinsic camera matrix, projection matrix (P2), and distortion coefficients from NPY:")
            logger.info("intrinsic_matrix: %s", intrinsic_matrix)
            logger.info("P2: %s", P2)
            logger.info("dist_coeffs: %s", dist_coeffs)
        else:
            raise FileNotFoundError("Camera parameters not found. Provide either camera_intrinsics.json or .npy files.")

    if intrinsic_matrix is None or dist_coeffs is None:
        raise ValueError("Failed to load camera parameters.")

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
        help="カメラ内部パラメータ行列のnpyファイルパス（camera_intrinsics_jsonが指定されていない場合に使用）",
    )
    parser.add_argument(
        "--dist_coeffs_path",
        type=str,
        default=None,
        help="歪み係数のnpyファイルパス（camera_intrinsics_jsonが指定されていない場合に使用）",
    )
    parser.add_argument(
        "--camera_intrinsics_json",
        type=str,
        default=None,
        help="camera_intrinsics.jsonのパス（優先して使用される）",
    )

    args = parser.parse_args()
    input_dir = args.input_dir
    assert isinstance(input_dir, str)

    output_dir = args.output_dir
    assert isinstance(output_dir, str)

    intrinsic_camera_matrix_path = args.intrinsic_camera_matrix_path
    dist_coeffs_path = args.dist_coeffs_path
    camera_intrinsics_json = args.camera_intrinsics_json

    distortion_correction(
        input_dir,
        output_dir,
        intrinsic_camera_matrix_path,
        dist_coeffs_path,
        camera_intrinsics_json
    )


if __name__ == "__main__":
    main()
