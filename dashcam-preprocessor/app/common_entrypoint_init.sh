#!/bin/bash
# 共通初期化処理
# dashcam-preprocessor用

# 基本環境変数の設定
APP_DIR=${APP_DIR:-/app}
BASE_DIR=${BASE_DIR:-/mnt/data}

# 共通のライブラリパス設定
export PROJ_LIB=/usr/share/proj/

STATUS_FILE="${BASE_DIR}/job_status.json"

# 入力ディレクトリの設定
INPUT_DIR="${BASE_DIR}/input"
if [ ! -d "$INPUT_DIR" ]; then
    echo "ERROR: 入力ディレクトリが見つかりません: $INPUT_DIR"
    exit 1
fi

# camera_view_angles.jsonの存在確認
CAMERA_VIEW_ANGLES_FILE="${INPUT_DIR}/camera_view_angles.json"
USE_CAMERA_VIEW_ANGLES=false
if [ -f "$CAMERA_VIEW_ANGLES_FILE" ]; then
    USE_CAMERA_VIEW_ANGLES=true
    echo "新形式のcamera_view_angles.jsonを検出しました"
fi

# camera_intrinsics.jsonの存在確認
CAMERA_INTRINSICS_FILE="${INPUT_DIR}/camera_intrinsics.json"
if [ -f "$CAMERA_INTRINSICS_FILE" ]; then
    echo "camera_intrinsics.jsonを検出しました: ${CAMERA_INTRINSICS_FILE}"
else
    echo "camera_intrinsics.jsonが見つかりません。デフォルトのカメラパラメータを使用します。"
fi
export CAMERA_INTRINSICS_FILE

# カメラごとの変数設定
for dir in "${CAMERA_DIRECTIONS[@]}"; do
    # mp4ファイルの自動検出（*_trim.mp4 を除外して元動画のみセット）
    if ls "${INPUT_DIR}"/*.mp4 2>/dev/null | grep -i "${dir^}" | grep -vi '_trim\.mp4' > /dev/null 2>&1; then
        declare "MP4_${dir^^}=$(ls "${INPUT_DIR}"/*.mp4 | grep -i "${dir^}" | grep -vi '_trim\.mp4')"
    fi

    # 各処理ステップのディレクトリ設定
    declare "IMAGE_TRIM_${dir^^}=${BASE_DIR}/intermediate/image/trim/${dir}"
    declare "TRIM_MP4_${dir^^}=${INPUT_DIR}/${dir}_trim.mp4"
    declare "IMAGE_SRC_${dir^^}=${BASE_DIR}/intermediate/image/src/${dir}"
    declare "IMAGE_DISTORTION_${dir^^}=${BASE_DIR}/intermediate/image/distortion/${dir}"
    declare "IMAGE_SEGMENTATION_${dir^^}=${BASE_DIR}/intermediate/image/segmentation/${dir}"

    # camera_view_angles.jsonから各カメラの設定を抽出
    if [ "$USE_CAMERA_VIEW_ANGLES" = true ]; then
        pos_est_file="${BASE_DIR}/pos_est_setting_${dir}.json"
        declare "POS_EST_SETTING_${dir^^}=$pos_est_file"
        python "${APP_DIR}/tool/extract_camera_settings.py" \
            --camera_view_angles_file "$CAMERA_VIEW_ANGLES_FILE" \
            --camera_direction "$dir" \
            --output_file "$pos_est_file" \
            --nearmiss_info_file "${INPUT_DIR}/NearMiss_Info.json"
    else
        # 旧形式: カメラごとのNearMiss_Info.jsonを使用
        if [ "$dir" = "rear" ]; then
            declare "POS_EST_SETTING_${dir^^}=${INPUT_DIR}/Rear_NearMiss_Info.json"
        else
            declare "POS_EST_SETTING_${dir^^}=${INPUT_DIR}/NearMiss_Info.json"
        fi
    fi

    # 環境変数をエクスポート
    export "MP4_${dir^^}" "IMAGE_TRIM_${dir^^}" "TRIM_MP4_${dir^^}" \
        "IMAGE_SRC_${dir^^}" "IMAGE_DISTORTION_${dir^^}" \
        "IMAGE_SEGMENTATION_${dir^^}" "POS_EST_SETTING_${dir^^}"
done

# フレームスキップ設定
FRAME_SKIP=${FRAME_SKIP:-1}

# 外部スクリプトを読み込む
source job_status_utils.sh
source "$(dirname "$0")/common_process.sh"

# 前回のステップを読み込む
load_last_step

echo "共通初期化処理完了"
echo "BASE_DIR: $BASE_DIR"
echo "CAMERA_DIRECTIONS: ${CAMERA_DIRECTIONS[@]}"
