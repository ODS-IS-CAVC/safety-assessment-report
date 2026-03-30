"""
ステップ1: 他車両検出データのフィルタリングと平滑化（相対座標のみ）

仕様:
1. 相対座標 (distance_x, distance_y) に対して外れ値除去・平滑化
"""

import argparse
import json
import os
from typing import Dict, List

from filters import (
    FilterChain, OutlierFilter, MedianFilter,
    MovingAverageFilter, SeparateAxisFilterChain
)
from detection_io import (
    convert_numpy_types, load_detection_data, update_segmentation_json
)
from filter_factory import (
    create_relative_filter_chain, create_relative_filter_chain_for_axis,
    load_filter_config, create_filters_from_stages
)
from detection_plot import plot_iteration_comparison

import logging

logger = logging.getLogger(__name__)


def parse_args():
    """コマンドライン引数を解析する"""
    parser = argparse.ArgumentParser(
        description='Step 1: Filter and smooth detection data '
                    '(relative coordinates only)')
    parser.add_argument('--input_json', required=True,
                        help='Path to detection_distance_result.json')
    parser.add_argument(
        '--output_json', required=True,
        help='Path to output filtered detections JSON'
    )
    parser.add_argument(
        '--debug_output_dir', type=str, default=None,
        help='Debug output directory for filter intermediate results'
    )
    parser.add_argument(
        '--config', type=str, default=None,
        help='Path to filter configuration JSON file'
    )

    # フィルタリングオプション
    # 相対座標での処理
    parser.add_argument(
        '--outlier_filter', default=False, action="store_true",
        help="Apply outlier filter on relative coords"
    )
    parser.add_argument(
        '--outlier_threshold', type=float, default=5.0,
        help='Outlier threshold (standard deviations)'
    )

    parser.add_argument(
        '--moving_average_filter', default=False, action="store_true",
        help="Apply moving average filter on relative coords"
    )
    parser.add_argument('--moving_average_window', type=int, default=9,
                        help='Window size for moving average filter')

    parser.add_argument('--median_filter', default=False, action="store_true",
                        help="Apply median filter on relative coords")
    parser.add_argument('--median_window', type=int, default=5,
                        help='Window size for median filter')

    # 絶対座標での処理
    parser.add_argument('--angle_filter', default=False, action="store_true",
                        help="Apply angle-based filter on absolute coords")
    parser.add_argument('--angle_threshold', type=float, default=45.0,
                        help='Maximum angle change threshold (degrees)')

    # 共通オプション
    parser.add_argument('--min_points', type=int, default=3,
                        help='Minimum points to keep after filtering')
    parser.add_argument(
        '--fully_contained_only', default=False, action="store_true",
        help="Only process objects with fully_contained=true"
    )
    parser.add_argument(
        '--skip_graph', default=False, action="store_true",
        help="Skip graph generation (for intermediate iterations)"
    )

    # X軸とY軸を独立にフィルタリングするオプション
    parser.add_argument(
        '--use_separate_axis_filtering', default=False, action="store_true",
        help="Filter X and Y axes independently"
    )
    parser.add_argument('--x_iterations', type=int, default=1,
                        help='Number of iterations for X-axis filtering')
    parser.add_argument('--y_iterations', type=int, default=10,
                        help='Number of iterations for Y-axis filtering')

    # X軸専用フィルタパラメータ
    parser.add_argument(
        '--outlier_threshold_x', type=float, default=None,
        help='Outlier threshold for X-axis (if not set, '
             'uses --outlier_threshold)'
    )
    parser.add_argument(
        '--moving_average_window_x', type=int, default=None,
        help='Moving average window for X-axis (if not set, '
             'uses --moving_average_window)'
    )
    parser.add_argument(
        '--median_window_x', type=int, default=None,
        help='Median window for X-axis (if not set, '
             'uses --median_window)'
    )

    # Y軸専用フィルタパラメータ
    parser.add_argument(
        '--outlier_threshold_y', type=float, default=None,
        help='Outlier threshold for Y-axis (if not set, '
             'uses --outlier_threshold)'
    )
    parser.add_argument(
        '--moving_average_window_y', type=int, default=None,
        help='Moving average window for Y-axis (if not set, '
             'uses --moving_average_window)'
    )
    parser.add_argument(
        '--median_window_y', type=int, default=None,
        help='Median window for Y-axis (if not set, '
             'uses --median_window)'
    )

    return parser.parse_args()


def apply_config_to_args(args, config: Dict):
    """
    設定ファイルの内容をコマンドライン引数に反映する
    （コマンドライン引数が優先）

    Args:
        args: argparseのNamespace
        config: 設定辞書
    """
    if config.get('options'):
        opts = config['options']
        if not args.fully_contained_only and opts.get('fully_contained_only'):
            args.fully_contained_only = opts['fully_contained_only']
        if not args.use_separate_axis_filtering and opts.get('use_separate_axis_filtering'):
            args.use_separate_axis_filtering = opts['use_separate_axis_filtering']
        if not args.outlier_filter and opts.get('outlier_filter'):
            args.outlier_filter = opts['outlier_filter']
        if not args.moving_average_filter and opts.get('moving_average_filter'):
            args.moving_average_filter = opts['moving_average_filter']
        if not args.median_filter and opts.get('median_filter'):
            args.median_filter = opts['median_filter']

    # イテレーション回数（x_axis_stagesから計算）
    if config.get('x_axis_stages'):
        total_x_iterations = sum(
            stage['repeat'] for stage in config['x_axis_stages']
        )
        # コマンドライン引数でx_iterationsが指定されていない場合のみ上書き
        if args.x_iterations == 1:  # デフォルト値の場合
            args.x_iterations = total_x_iterations

    # イテレーション回数（y_axis_stagesから計算）
    if config.get('y_axis_stages'):
        total_y_iterations = sum(
            stage['repeat'] for stage in config['y_axis_stages']
        )
        # コマンドライン引数でy_iterationsが指定されていない場合のみ上書き
        if args.y_iterations == 10:  # デフォルト値の場合
            args.y_iterations = total_y_iterations

    logger.info("  X軸イテレーション回数: %s", args.x_iterations)
    logger.info("  Y軸イテレーション回数: %s", args.y_iterations)
    logger.info("  独立軸フィルタリング: %s", args.use_separate_axis_filtering)


def build_filter_chain(args, config):
    """
    設定に基づいてフィルタチェーンを構築する

    Args:
        args: argparseのNamespace
        config: 設定辞書（Noneの場合あり）

    Returns:
        FilterChain または SeparateAxisFilterChain
    """
    if not args.use_separate_axis_filtering:
        return FilterChain(
            filters=create_relative_filter_chain(args).filters,
            debug_output_dir=args.debug_output_dir
        )

    # X軸: x_axis_stagesがあればそれを使用、なければデフォルト
    if config and config.get('x_axis_stages'):
        logger.info("Using x_axis_stages from config for X-axis")
        x_filters = create_filters_from_stages(config['x_axis_stages'], args)
        x_iterations = 1
    else:
        x_filters = create_relative_filter_chain_for_axis(args, 'x')
        x_iterations = args.x_iterations

    # Y軸: y_axis_stagesがあればそれを使用、なければデフォルト
    if config and config.get('y_axis_stages'):
        logger.info("Using y_axis_stages from config for Y-axis")
        y_filters = create_filters_from_stages(config['y_axis_stages'], args)
        y_iterations = 1
    else:
        y_filters = create_relative_filter_chain_for_axis(args, 'y')
        y_iterations = args.y_iterations

    return SeparateAxisFilterChain(
        x_filters=x_filters,
        y_filters=y_filters,
        x_iterations=x_iterations,
        y_iterations=y_iterations,
        debug_output_dir=args.debug_output_dir
    )


def collect_filter_metadata(filter_chain, use_separate_axis: bool) -> Dict:
    """
    フィルタチェーンからメタデータを収集する

    Args:
        filter_chain: フィルタチェーン
        use_separate_axis: 独立軸フィルタリングかどうか

    Returns:
        メタデータ辞書
    """
    metadata = {
        "filters_applied": {
            "relative_coords": []
        },
        "use_separate_axis_filtering": use_separate_axis
    }

    if not use_separate_axis:
        for filter_obj in filter_chain.filters:
            metadata["filters_applied"]["relative_coords"].append(
                _filter_to_info(filter_obj)
            )
        return metadata

    metadata["x_iterations"] = filter_chain.x_iterations
    metadata["y_iterations"] = filter_chain.y_iterations

    metadata["filters_applied"]["relative_coords_x"] = [
        _filter_to_info(f) for f in filter_chain.x_filters
    ]
    metadata["filters_applied"]["relative_coords_y"] = [
        _filter_to_info(f) for f in filter_chain.y_filters
    ]

    return metadata


def _filter_to_info(filter_obj) -> Dict:
    """フィルタオブジェクトから情報辞書を作成する"""
    info = {"type": filter_obj.__class__.__name__}
    if isinstance(filter_obj, OutlierFilter):
        info["threshold"] = filter_obj.threshold
    elif isinstance(filter_obj, (MedianFilter, MovingAverageFilter)):
        info["window_size"] = filter_obj.window_size
    return info


def process_object(
    obj_id, relative_positions: List[Dict],
    filter_chain, fully_contained_only: bool
) -> List[Dict]:
    """
    1つのオブジェクトに対してフィルタリングを実行する

    Args:
        obj_id: オブジェクトID
        relative_positions: 相対位置データのリスト
        filter_chain: フィルタチェーン
        fully_contained_only: fully_containedのみ処理するか

    Returns:
        フィルタリング後の検出データ（スキップ時は空リスト）
    """
    logger.info("Processing object %s...", obj_id)

    # fully_contained_only オプションのチェック
    if fully_contained_only:
        fully_contained_points = [
            item for item in relative_positions
            if item.get("fully_contained", False)
        ]
        if not fully_contained_points:
            logger.info("  Skipped: No fully_contained points")
            return []
        relative_positions = fully_contained_points

    # フレーム番号と相対座標を抽出
    frames = [item["frame"] for item in relative_positions]
    rel_coords = [item["distance"] for item in relative_positions]

    logger.info("  Original relative coords: %d points", len(frames))

    # 相対座標にフィルタを適用
    filtered_rel_frames, filtered_rel_coords = filter_chain.apply(
        frames, rel_coords
    )

    # デバッグ結果を保存
    filter_chain.save_debug_results(f"{obj_id}_relative")

    if len(filtered_rel_frames) < 2:
        logger.info("  Skipped: Insufficient data after relative filtering "
                     "(%d points)", len(filtered_rel_frames))
        return []

    logger.info("  After relative coord filtering: %d points",
                len(filtered_rel_frames))

    # フィルタリング結果を再構築（元のメタデータを保持）
    filtered_detections = []
    for frame, pos in zip(filtered_rel_frames, filtered_rel_coords):
        original = next(
            (d for d in relative_positions if d["frame"] == frame), None
        )
        if original:
            filtered_detections.append({
                "frame": frame,
                "vehicle_type": original["vehicle_type"],
                "distance": tuple(pos),
                "result_idx": original["result_idx"],
                "seg_idx": original["seg_idx"],
                "calc_idx": original["calc_idx"]
            })

    return filtered_detections


def save_and_generate_graphs(
    args, original_data: Dict, filtered_data: Dict
):
    """
    フィルタリング結果をJSONに保存し、比較グラフを生成する

    Args:
        args: argparseのNamespace
        original_data: 元のJSONデータ
        filtered_data: フィルタリング後のオブジェクトごとの検出データ
    """
    # 元のJSONデータを更新
    logger.info("元のJSONデータを更新しています...")
    output = update_segmentation_json(original_data, filtered_data)
    output = convert_numpy_types(output)

    os.makedirs(os.path.dirname(args.output_json) or '.', exist_ok=True)
    with open(args.output_json, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info("Filtered data saved to %s", args.output_json)
    logger.info("Total objects after filtering: %d", len(filtered_data))
    logger.info("Total frames: %d", len(output['results']))

    # デバッグ出力ディレクトリの準備
    logger.info("Graph generation check:")
    logger.info("  skip_graph: %s", args.skip_graph)
    logger.info("  debug_output_dir: %s", args.debug_output_dir)
    if args.debug_output_dir:
        logger.info("  debug_output_dir exists: %s",
                     os.path.exists(args.debug_output_dir))
        if not os.path.exists(args.debug_output_dir):
            logger.info("  Creating debug_output_dir: %s",
                         args.debug_output_dir)
            os.makedirs(args.debug_output_dir, exist_ok=True)

    # グラフ生成
    if not args.skip_graph and args.debug_output_dir:
        logger.info("Generating comparison graphs...")
        graph_output_dir = os.path.join(
            os.path.dirname(args.output_json), "comparison_graphs"
        )
        os.makedirs(graph_output_dir, exist_ok=True)

        logger.info("  debug_output_dir: %s", args.debug_output_dir)
        logger.info("  graph_output_dir: %s", graph_output_dir)
        logger.info("  filtered_data objects: %s", list(filtered_data.keys()))

        for obj_id in filtered_data.keys():
            graph_path = os.path.join(
                graph_output_dir,
                f"object_{obj_id}_iteration_comparison.png"
            )
            logger.info("  Generating graph for object %s...", obj_id)
            try:
                plot_iteration_comparison(
                    args.debug_output_dir, obj_id, graph_path
                )
                logger.info("    Saved: %s", graph_path)
            except Exception as e:
                logger.error("    Error: %s", e)
                import traceback
                traceback.print_exc()

        logger.info("Comparison graphs saved to %s", graph_output_dir)
    else:
        logger.info("  Graph generation skipped")
        if args.skip_graph:
            logger.info("    Reason: --skip_graph flag is set")
        if not args.debug_output_dir:
            logger.info("    Reason: --debug_output_dir is not set")


def main():
    args = parse_args()

    # 設定ファイルを読み込み
    config = load_filter_config(args.config)
    if config:
        logger.info("Loaded filter configuration")
        apply_config_to_args(args, config)

    # 検出データの読み込み
    original_data, object_trajectories, _is_refiltering, _input_metadata = (
        load_detection_data(args.input_json)
    )
    logger.info("Loaded detection data for %d objects",
                 len(object_trajectories))
    logger.info("Processing in relative coordinates only (smoothing)")

    # フィルタチェーンの作成
    filter_chain = build_filter_chain(args, config)

    # メタデータ収集
    metadata = collect_filter_metadata(
        filter_chain, args.use_separate_axis_filtering
    )

    # 各オブジェクトを処理
    filtered_data = {}
    for obj_id, relative_positions in object_trajectories.items():
        result = process_object(
            obj_id, relative_positions,
            filter_chain, args.fully_contained_only
        )
        if result:
            filtered_data[obj_id] = result

    # 出力保存とグラフ生成
    save_and_generate_graphs(args, original_data, filtered_data)


if __name__ == "__main__":
    main()
