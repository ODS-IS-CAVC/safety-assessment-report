# 共通カメラ処理スクリプト

process_video2image() {
    local input_mp4=$1
    local output_dir=$2
    local frame_skip=$3
    local start_time=$4
    local end_time=$5
    mkdir -p "${output_dir}"

    echo "python ${APP_DIR}/tool/video2image.py"
    echo "    --input_path ${input_mp4}"
    echo "    --output_path ${output_dir}"
    echo "    --frame_skip ${frame_skip}"
    echo "    --start_time ${start_time}"
    echo "    --end_time ${end_time}"

    python "${APP_DIR}/tool/video2image.py" \
        --input_path "${input_mp4}" \
        --output_path "${output_dir}" \
        --frame_skip "${frame_skip}" \
        --start_time "${start_time}" \
        --end_time "${end_time}"
}

process_image2video() {
    local input_dir=$1
    local output_mp4=$2
    local frame_skip=$3
    mkdir -p "$(dirname "$output_mp4")"
    [ -f "$output_mp4" ] && rm -f "$output_mp4"

    echo "python ${APP_DIR}/tool/image2video.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_path ${output_mp4}"
    echo "    --frame_skip ${frame_skip}"

    python "${APP_DIR}/tool/image2video.py" \
        --input_dir "${input_dir}" \
        --output_path "${output_mp4}" \
        --frame_skip "${frame_skip}"
}

process_distortion() {
    local input_dir=$1
    local output_dir=$2
    local camera_intrinsics_json=${3:-}
    mkdir -p "$output_dir"

    echo "python ${APP_DIR}/distortion/distortion_correction.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_dir ${output_dir}"

    if [ -n "$camera_intrinsics_json" ] && [ -f "$camera_intrinsics_json" ]; then
        echo "    --camera_intrinsics_json ${camera_intrinsics_json}"
        python "${APP_DIR}/distortion/distortion_correction.py" \
            --input_dir "${input_dir}" \
            --output_dir "${output_dir}" \
            --camera_intrinsics_json "${camera_intrinsics_json}"
    else
        echo "    --intrinsic_camera_matrix_path ${APP_DIR}/distortion/intrinsic_camera_matrix.npy"
        echo "    --dist_coeffs_path ${APP_DIR}/distortion/dist_coeffs.npy"
        python "${APP_DIR}/distortion/distortion_correction.py" \
            --input_dir "${input_dir}" \
            --output_dir "${output_dir}" \
            --intrinsic_camera_matrix_path "${APP_DIR}/distortion/intrinsic_camera_matrix.npy" \
            --dist_coeffs_path "${APP_DIR}/distortion/dist_coeffs.npy"
    fi
}

process_segmentation() {
    local input_dir=$1
    local output_dir=$2
    mkdir -p "${output_dir}"

    echo "python ${APP_DIR}/distortion/segmentation2d.py"
    echo "    --input_dir ${input_dir}"
    echo "    --output_dir ${output_dir}"

    python "${APP_DIR}/distortion/segmentation2d.py" \
        --input_dir "${input_dir}" \
        --output_dir "${output_dir}"
}

process_segmentation_step() {
    local dir="$1"
    local image_dist_var=IMAGE_DISTORTION_${dir^^}
    local image_seg_var=IMAGE_SEGMENTATION_${dir^^}
    if [ -d "${!image_dist_var}" ]; then
        process_segmentation "${!image_dist_var}" "${!image_seg_var}"
    fi
}

process_make_seg_mp4_step() {
    local dir="$1"
    local image_seg_var=IMAGE_SEGMENTATION_${dir^^}
    if [ -d "${!image_seg_var}" ]; then
        echo "python ${APP_DIR}/tool/image2video.py"
        echo "    --input_dir ${!image_seg_var}"
        echo "    --output_path ${!image_seg_var}/segmentation_cv.mp4"
        echo "    --frame_skip ${FRAME_SKIP}"

        python "${APP_DIR}/tool/image2video.py" \
            --input_dir "${!image_seg_var}" \
            --output_path "${!image_seg_var}/segmentation_cv.mp4" \
            --frame_skip "${FRAME_SKIP}"
    fi
}
