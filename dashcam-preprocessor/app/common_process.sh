# 共通カメラ処理スクリプト
# try_bravs/app/common_camera_process.sh

# カメラ方向リスト（拡張性のためfront/rear/left/right等を追加可能）
: "${CAMERA_DIRECTIONS:=front}"
# NearMiss_Infoファイルリスト（front/rear/left/rightに対応）
: "${NEAR_MISS_INFO_LIST:=NearMiss_Info.json}"


# 共通処理関数
define_common_functions() {
process_video2image() {
    local input_mp4=$1
    local output_dir=$2
    local frame_skip=$3
    local start_time=$4
    local end_time=$5
    mkdir -p ${output_dir}

    echo "python ${APP_DIR}/tool/video2image.py"
    echo "    --input_path ${input_mp4}"
    echo "    --output_path ${output_dir}"
    echo "    --frame_skip ${frame_skip}"
    echo "    --start_time ${start_time}"
    echo "    --end_time ${end_time}"

    python ${APP_DIR}/tool/video2image.py \
        --input_path ${input_mp4} \
        --output_path ${output_dir} \
        --frame_skip ${frame_skip} \
        --start_time ${start_time} \
        --end_time ${end_time}
}
process_image2video() {
    local input_dir=$1
    local output_mp4=$2
    local frame_skip=$3
    mkdir -p $(dirname "$output_mp4")
    [ -f "$output_mp4" ] && rm -f "$output_mp4"

    echo "python ${APP_DIR}/tool/image2video.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_path ${output_mp4}"
    echo "    --frame_skip ${frame_skip}"

    python ${APP_DIR}/tool/image2video.py \
        --input_dir ${input_dir} \
        --output_path ${output_mp4} \
        --frame_skip ${frame_skip}
}
process_distortion() {
    local input_dir=$1
    local output_dir=$2
    local camera_intrinsics_json=${3:-}
    mkdir -p "$output_dir"

    echo "python ${APP_DIR}/distortion/distortion_correction.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_dir ${output_dir}"

    # camera_intrinsics.jsonが指定されている場合はそれを使用
    if [ -n "$camera_intrinsics_json" ] && [ -f "$camera_intrinsics_json" ]; then
        echo "    --camera_intrinsics_json ${camera_intrinsics_json}"
        python ${APP_DIR}/distortion/distortion_correction.py \
            --input_dir ${input_dir} \
            --output_dir ${output_dir} \
            --camera_intrinsics_json ${camera_intrinsics_json}
    else
        # フォールバック: 従来のnpyファイルを使用
        echo "    --intrinsic_camera_matrix_path ${APP_DIR}/distortion/intrinsic_camera_matrix.npy"
        echo "    --dist_coeffs_path ${APP_DIR}/distortion/dist_coeffs.npy"
        python ${APP_DIR}/distortion/distortion_correction.py \
            --input_dir ${input_dir} \
            --output_dir ${output_dir} \
            --intrinsic_camera_matrix_path ${APP_DIR}/distortion/intrinsic_camera_matrix.npy \
            --dist_coeffs_path ${APP_DIR}/distortion/dist_coeffs.npy
    fi
}
process_segmentation() {
    local input_dir=$1
    local output_dir=$2
    mkdir -p ${output_dir}

    echo "python ${APP_DIR}/distortion/segmentation2d.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_dir ${output_dir}"

    python ${APP_DIR}/distortion/segmentation2d.py \
        --input_dir ${input_dir} \
        --output_dir ${output_dir}
}
process_segmentation_step() {
    local dir="$1"
    local image_dist_var=IMAGE_DISTORTION_${dir^^}
    local image_seg_var=IMAGE_SEGMENTATION_${dir^^}
    if [ -d "${!image_dist_var}" ]; then
        process_segmentation "${!image_dist_var}" "${!image_seg_var}"
    fi
}
process_seg_infer_step() {
    local dir="$1"
    local image_seg_var=IMAGE_SEGMENTATION_${dir^^}
    local seg_result_json="${!image_seg_var}/segmentation_results.json"
    local pos_est_setting_var=POS_EST_SETTING_${dir^^}

    # 各カメラ方向に対応した位置推定設定ファイルを使用
    local pos_est_setting_file="${!pos_est_setting_var}"

    # 設定ファイルが存在しない場合はデフォルトを使用
    if [ -z "$pos_est_setting_file" ] || [ ! -f "$pos_est_setting_file" ]; then
        pos_est_setting_file="${POS_EST_SETTING_FILE}"
        echo "Warning: ${dir}カメラ用の設定ファイルが見つかりません。デフォルト設定を使用します: ${pos_est_setting_file}"
    else
        echo "${dir}カメラ: ${pos_est_setting_file} を位置推定設定として使用"
    fi

    if [ -f "$seg_result_json" ]; then
        length=$(jq '.results | length' "$seg_result_json")
        if [ "$length" -eq 0 ]; then
            echo "${dir}: 車両未検出"
            return
        else
            echo "python ${APP_DIR}/distortion/infer_distance_to_segmentation.py"
            echo "    --input_dir "${!image_seg_var}""
            echo "    --output_dir "${!image_seg_var}""
            echo "    --pos_est_setting_file ${pos_est_setting_file}"
            echo "    --segmentation_result_json ${seg_result_json}"

            python ${APP_DIR}/distortion/infer_distance_to_segmentation.py \
                --input_dir "${!image_seg_var}" \
                --output_dir "${!image_seg_var}" \
                --pos_est_setting_file ${pos_est_setting_file} \
                --segmentation_result_json "$seg_result_json"
        fi
    fi
}
process_seg_infer_csv_step() {
    local dir="$1"
    local image_seg_var=IMAGE_SEGMENTATION_${dir^^}
    local detection_result_json="${!image_seg_var}/segmentation_detection_result.json"
    if [ -f "$detection_result_json" ]; then
        echo "python ${APP_DIR}/distortion/detect2csv_segmentation.py"
        echo "    --rel_coord_file "$detection_result_json""

        python ${APP_DIR}/distortion/detect2csv_segmentation.py \
            --rel_coord_file "$detection_result_json"
    fi
}
process_make_seg_mp4_step() {
    local dir="$1"
    local image_seg_var=IMAGE_SEGMENTATION_${dir^^}
    if [ -d "${!image_seg_var}" ]; then
        echo "python ${APP_DIR}/tool/image2video.py"
        echo "    --input_dir "${!image_seg_var}""
        echo "    --output_path "${!image_seg_var}/segmentation_cv.mp4""
        echo "    --frame_skip ${FRAME_SKIP}"

        python ${APP_DIR}/tool/image2video.py \
            --input_dir "${!image_seg_var}" \
            --output_path "${!image_seg_var}/segmentation_cv.mp4" \
            --frame_skip ${FRAME_SKIP}
    fi
}

process_infer_distance() {
    local input_dir=$1
    local output_dir=$2
    mkdir -p "$output_dir"

    echo "python ${APP_DIR}/camera_distance/infer_distance_to_car.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_dir ${output_dir}"
    echo "    --pos_est_setting_file ${POS_EST_SETTING_FILE}"

    python ${APP_DIR}/camera_distance/infer_distance_to_car.py \
        --input_dir ${input_dir} \
        --output_dir ${output_dir} \
        --pos_est_setting_file ${POS_EST_SETTING_FILE}
}

# kait用: zipアーカイブを作成（高速版）
# 使用法: create_archive_kait <work_dir> <job_uuid> <output_dir> [delete_original]
create_archive_kait() {
    local work_dir="$1"
    local job_uuid="$2"
    local output_dir="$3"
    local delete_original="${4:-false}"

    local zip_file="${output_dir}/${job_uuid}.zip"
    mkdir -p "${output_dir}"

    echo "Creating ${job_uuid}.zip archive..."

    # 一時ディレクトリにディレクトリ構造を作成
    local temp_dir=$(mktemp -d)
    local link_dir="${temp_dir}/${job_uuid}"
    mkdir -p "${link_dir}/camera_param"
    mkdir -p "${link_dir}/image_distortion/front"
    mkdir -p "${link_dir}/image_distortion/rear"
    mkdir -p "${link_dir}/segmentation/front"
    mkdir -p "${link_dir}/segmentation/rear"

    # camera_* ファイルをリンク（一括）
    ln -sf "${work_dir}"/camera_* "${link_dir}/camera_param/" 2>/dev/null || true

    # gsensor_gps_* ファイルをリンク（一括）
    ln -sf "${work_dir}"/gsensor_gps_* "${link_dir}/" 2>/dev/null || true

    # image_distortion のJPGファイルをリンク（find + xargs で高速化）
    for dir in front rear; do
        if [ -d "${work_dir}/image_distortion/${dir}" ]; then
            find "${work_dir}/image_distortion/${dir}" -maxdepth 1 -name "*.jpg" -print0 2>/dev/null | \
                xargs -0 -r ln -st "${link_dir}/image_distortion/${dir}/"
        fi
    done

    # segmentation のファイルをリンク
    for dir in front rear; do
        if [ -d "${work_dir}/segmentation/${dir}" ]; then
            for f in segmentation_cv.mp4 segmentation_detection_result.json segmentation_results.json tracking_info.txt; do
                [ -f "${work_dir}/segmentation/${dir}/$f" ] && \
                    ln -sf "${work_dir}/segmentation/${dir}/$f" "${link_dir}/segmentation/${dir}/"
            done
            ln -sf "${work_dir}/segmentation/${dir}"/segmentation_detection_*.csv "${link_dir}/segmentation/${dir}/" 2>/dev/null || true
        fi
    done

    # 無圧縮でzip作成（-0: JPGは既に圧縮済みなので再圧縮不要）
    (cd "${temp_dir}" && zip -q0r "${zip_file}" "${job_uuid}")

    # 一時ディレクトリを削除
    rm -rf "${temp_dir}"

    echo "Archive created: ${zip_file}"
    ls -lh "${zip_file}"

    # 処理済みデータの削除（オプション）
    if [ "$delete_original" = "true" ]; then
        echo "Deleting processed data in: ${work_dir}"
        rm -rf "${work_dir}/image_trim"
        rm -rf "${work_dir}/image_src"
        rm -rf "${work_dir}/image_distortion"
        rm -rf "${work_dir}/segmentation"
        rm -f "${work_dir}/job_status.json"
        rm -f "${work_dir}"/gsensor_gps_*.csv
        rm -f "${work_dir}"/pos_est_setting_*.json
        echo "Processed data deleted (input data preserved)"
    fi
}

# アーカイブステップ処理
process_archive_step() {
    local provide_root_dir="${PROVIDE_ROOT_DIR:-${WORK_ROOT}/kait_provide}"
    local delete_after_zip="${DELETE_AFTER_ZIP:-false}"

    # JOB_UUIDの生成（JOB_IDからUUIDを抽出）
    local job_uuid
    if [[ "$JOB_ID" == *"/"* ]]; then
        job_uuid=$(echo "$JOB_ID" | sed -E 's|.*/([^/]+)/result/Scene([0-9]+)|\1_Scene\2|')
    else
        job_uuid="${JOB_ID}"
    fi

    echo "アーカイブ作成: ${job_uuid}"
    create_archive_kait "${WORK_DIR}" "${job_uuid}" "${provide_root_dir}" "${delete_after_zip}"
}

}
define_common_functions
