#!/bin/bash
# 共通初期化処理
# dashcam-preprocessor用

# 基本環境変数の設定
APP_DIR=${APP_DIR:-/app}
BASE_DIR=${BASE_DIR:-/mnt/data}

# 共通のライブラリパス設定
export PROJ_LIB=/usr/share/proj/

# 作業ディレクトリの設定 (BASE_DIR直下を作業ディレクトリとする)
WORK_DIR="${BASE_DIR}"
IS_LOCAL=${IS_LOCAL:-false}
STATUS_FILE="${WORK_DIR}/job_status.json"

# 入力ディレクトリの設定
INPUT_DIR="${WORK_DIR}/input"
if [ ! -d "$INPUT_DIR" ]; then
    echo "ERROR: 入力ディレクトリが見つかりません: $INPUT_DIR"
    exit 1
fi

# カメラ方向リスト（各entrypointで設定済みのものを使用）
# CAMERA_DIRECTIONSは各entrypointで設定されている必要があります

# camera_view_angles.jsonの存在確認
CAMERA_VIEW_ANGLES_FILE="${INPUT_DIR}/camera_view_angles.json"
USE_CAMERA_VIEW_ANGLES=false
if [ -f "$CAMERA_VIEW_ANGLES_FILE" ]; then
    USE_CAMERA_VIEW_ANGLES=true
    echo "新形式のcamera_view_angles.jsonを検出しました"
fi

# camera_intrinsics.jsonの存在確認
CAMERA_INTRINSICS_FILE="${INPUT_DIR}/camera_intrinsics.json"
USE_CAMERA_INTRINSICS_JSON=false
if [ -f "$CAMERA_INTRINSICS_FILE" ]; then
    USE_CAMERA_INTRINSICS_JSON=true
    echo "camera_intrinsics.jsonを検出しました: ${CAMERA_INTRINSICS_FILE}"
else
    echo "camera_intrinsics.jsonが見つかりません。デフォルトのカメラパラメータを使用します。"
fi
export CAMERA_INTRINSICS_FILE
export USE_CAMERA_INTRINSICS_JSON

# カメラごとの変数設定
for idx in "${!CAMERA_DIRECTIONS[@]}"; do
    dir="${CAMERA_DIRECTIONS[$idx]}"
    DIR_UPPER=$(echo "$dir" | tr '[:lower:]' '[:upper:]')

    # mp4ファイルの自動検出（*_trim.mp4 を除外して元動画のみセット）
    if ls ${INPUT_DIR}/*.mp4 2>/dev/null | grep -i "${dir^}" | grep -vi '_trim\.mp4' > /dev/null 2>&1; then
        eval MP4_${DIR_UPPER}="$(ls ${INPUT_DIR}/*.mp4 | grep -i "${dir^}" | grep -vi '_trim\.mp4')"
    fi

    # 各処理ステップのディレクトリ設定
    eval IMAGE_TRIM_${DIR_UPPER}="${WORK_DIR}/intermediate/image/trim/${dir}"
    eval TRIM_MP4_${DIR_UPPER}="${INPUT_DIR}/${dir}_trim.mp4"
    eval IMAGE_SRC_${DIR_UPPER}="${WORK_DIR}/intermediate/image/src/${dir}"
    eval IMAGE_DISTORTION_${DIR_UPPER}="${WORK_DIR}/intermediate/image/distortion/${dir}"
    eval IMAGE_SEGMENTATION_${DIR_UPPER}="${WORK_DIR}/intermediate/image/segmentation/${dir}"

    # IMAGE_INFER (entrypoint.shで使用)
    if [ "${ENABLE_IMAGE_INFER:-false}" = true ]; then
        eval IMAGE_INFER_${DIR_UPPER}="${WORK_DIR}/intermediate/image/infer/${dir}"
    fi

    # 新形式: camera_view_angles.jsonから各カメラの設定を抽出
    if [ "$USE_CAMERA_VIEW_ANGLES" = true ]; then
        pos_est_file="${WORK_DIR}/pos_est_setting_${dir}.json"
        eval POS_EST_SETTING_${DIR_UPPER}="$pos_est_file"
        # 設定ファイルを生成
        python ${APP_DIR}/tool/extract_camera_settings.py \
            --camera_view_angles_file "$CAMERA_VIEW_ANGLES_FILE" \
            --camera_direction "$dir" \
            --output_file "$pos_est_file" \
            --nearmiss_info_file "${INPUT_DIR}/NearMiss_Info.json"
    else
        # 旧形式: カメラごとのNearMiss_Info.jsonを使用
        if [ "$dir" = "front" ]; then
            eval POS_EST_SETTING_${DIR_UPPER}="${INPUT_DIR}/NearMiss_Info.json"
        elif [ "$dir" = "rear" ]; then
            eval POS_EST_SETTING_${DIR_UPPER}="${INPUT_DIR}/Rear_NearMiss_Info.json"
        else
            # その他のカメラ方向の場合はNearMiss_Info.jsonを使用
            eval POS_EST_SETTING_${DIR_UPPER}="${INPUT_DIR}/NearMiss_Info.json"
        fi
    fi

    # 環境変数をエクスポート
    export MP4_${DIR_UPPER} IMAGE_TRIM_${DIR_UPPER} TRIM_MP4_${DIR_UPPER} \
        IMAGE_SRC_${DIR_UPPER} IMAGE_DISTORTION_${DIR_UPPER} \
        IMAGE_SEGMENTATION_${DIR_UPPER} POS_EST_SETTING_${DIR_UPPER}

    if [ "${ENABLE_IMAGE_INFER:-false}" = true ]; then
        export IMAGE_INFER_${DIR_UPPER}
    fi
done

# フレームスキップ設定
FRAME_SKIP=${FRAME_SKIP:-1}

# 外部スクリプトを読み込む
source job_status_utils.sh
source "$(dirname "$0")/common_process.sh"

# 前回のステップを読み込む
load_last_step

echo "共通初期化処理完了"
echo "WORK_DIR: $WORK_DIR"
echo "CAMERA_DIRECTIONS: ${CAMERA_DIRECTIONS[@]}"
