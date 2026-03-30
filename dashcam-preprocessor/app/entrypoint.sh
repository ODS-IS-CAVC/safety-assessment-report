#!/bin/bash
set -eu

# dashcam-preprocessor entrypoint
# 動画前処理: 画像分解・歪み補正・YOLOセグメンテーション
# License: AGPL-3.0

# カメラ方向の設定（デフォルト: front rear）
if [ -z "${CAMERA_DIRECTIONS+x}" ]; then
    CAMERA_DIRECTIONS=(front rear)
fi

# 共通初期化処理を読み込む
source "$(dirname "$0")/common_entrypoint_init.sh"

# 初回実行時、last_stepが未定義または空であれば"NOT_STARTED"として扱う
if [ -z "$last_step" ] || [ "$last_step" == "NOT_STARTED" ]; then
    last_step="NOT_STARTED"
    if [ "$IS_LOCAL" = true ]; then
        last_step="PREPARE"
    fi
fi

echo "前回のステップ: $last_step"

# PREPARE: 事前準備
if [ "$last_step" == "NOT_STARTED" ] || [ "$last_step" == "PREPARE" ]; then
    echo "事前準備"
    START_TIME=0
    END_TIME=-1

    # Gセンサーファイルの検索（エラーを無視）
    GSENSOR_TXT_FILE=$(ls ${INPUT_DIR}/*.txt 2>/dev/null | grep gsensor_gps || true)

    # GPSデータがない場合は警告を表示してスキップ
    if [ -z "$GSENSOR_TXT_FILE" ] || [ ! -f "$GSENSOR_TXT_FILE" ]; then
        echo "WARNING: GPSデータファイル (gsensor_gps*.txt) が見つかりません。GPS関連の処理をスキップします。"
    else
        # Gセンサーテキスト to csv
        echo python ${APP_DIR}/tool/convert_sensor_data_txt2csv.py
        echo     --input_path ${GSENSOR_TXT_FILE}
        echo     --start_time ${START_TIME}
        echo     --end_time ${END_TIME}

        python ${APP_DIR}/tool/convert_sensor_data_txt2csv.py \
            --input_path ${GSENSOR_TXT_FILE} \
            --start_time ${START_TIME} \
            --end_time ${END_TIME} || {
            echo "WARNING: GPS/Gセンサーデータの変換に失敗しましたが、処理を続行します。"
        }
    fi

    for dir in "${CAMERA_DIRECTIONS[@]}"; do
        mp4_var=MP4_${dir^^}
        image_trim_var=IMAGE_TRIM_${dir^^}
        trim_mp4_var=TRIM_MP4_${dir^^}
        if [ -n "${!mp4_var}" ]; then
            process_video2image "${!mp4_var}" "${!image_trim_var}" 0 "$START_TIME" "$END_TIME"
            process_image2video "${!image_trim_var}" "${!trim_mp4_var}" 0
            eval MP4_${dir^^}="${!trim_mp4_var}"
        fi
    done
    save_last_step "PREPARE"
    echo "完了: $last_step"
fi


# VIDEO_TO_IMAGE: 動画から画像を抽出
if [ "$last_step" == "PREPARE" ] || [ "$last_step" == "VIDEO_TO_IMAGE" ]; then
    echo "動画から画像を抽出"
    for dir in "${CAMERA_DIRECTIONS[@]}"; do
        mp4_var=MP4_${dir^^}
        image_src_var=IMAGE_SRC_${dir^^}
        if [ -n "${!mp4_var}" ]; then
            process_video2image "${!mp4_var}" "${!image_src_var}" "$FRAME_SKIP" 0 -1
        fi
    done
    save_last_step "VIDEO_TO_IMAGE"
    echo "完了: $last_step"
fi

# DISTORTION: 画像補正
if [ "$last_step" == "VIDEO_TO_IMAGE" ] || [ "$last_step" == "DISTORTION" ]; then
    echo "画像補正"
    for dir in "${CAMERA_DIRECTIONS[@]}"; do
        image_src_var=IMAGE_SRC_${dir^^}
        image_dist_var=IMAGE_DISTORTION_${dir^^}
        if [ -d "${!image_src_var}" ]; then
            # camera_intrinsics.jsonがあれば使用
            process_distortion "${!image_src_var}" "${!image_dist_var}" "${CAMERA_INTRINSICS_FILE}"
        fi
    done
    save_last_step "DISTORTION"
    echo "完了: $last_step"
fi

# SEGMENTATION: セグメンテーション
if [ "$last_step" == "DISTORTION" ] || [ "$last_step" == "SEGMENTATION" ]; then
    echo "セグメンテーション"
    for dir in "${CAMERA_DIRECTIONS[@]}"; do
        process_segmentation_step "$dir"
    done
    save_last_step "SEGMENTATION"
    echo "完了: $last_step"
fi

# MAKE_SEG_MP4: セグメンテーション動画生成
if [ "$last_step" == "SEGMENTATION" ] || [ "$last_step" == "MAKE_SEG_MP4" ]; then
    echo "セグメンテーション動画生成"
    for dir in "${CAMERA_DIRECTIONS[@]}"; do
        process_make_seg_mp4_step "$dir"
    done
    save_last_step "MAKE_SEG_MP4"
    echo "完了: $last_step"
fi

echo "=== dashcam-preprocessor 完了 ==="
