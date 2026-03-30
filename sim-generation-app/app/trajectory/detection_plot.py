"""
検出データの可視化

フィルタリング結果のイテレーション比較グラフを生成する。
"""

import json
import logging
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


COLORS = [
    'gray', 'blue', 'red', 'green', 'purple', 'orange',
    'brown', 'pink', 'cyan', 'magenta'
]


def _load_debug_data(debug_dir, obj_id):
    """
    デバッグファイルからフィルタステップデータを読み込む

    Args:
        debug_dir: デバッグディレクトリ
        obj_id: オブジェクトID

    Returns:
        ステップデータのリスト（ファイルが見つからない場合はNone）
    """
    debug_file = os.path.join(
        debug_dir, f"filter_debug_obj_{obj_id}_relative.json"
    )

    logger.debug("    Looking for debug data: %s", debug_file)
    if not os.path.exists(debug_file):
        logger.warning("    Debug file not found")
        return None

    with open(debug_file, 'r') as f:
        debug_data = json.load(f)

    steps = debug_data.get('steps', [])
    if not steps:
        logger.warning("    No steps found in debug data")
        return None

    return steps


def _find_step(steps, step_name):
    """ステップ名でステップデータを検索する"""
    for step in steps:
        if step.get('step') == step_name:
            return step
    return None


def _extract_initial_xy(initial_step):
    """初期データからX/Y値を抽出する"""
    initial_positions = initial_step.get('positions', [])
    if initial_positions:
        initial_x = [pos[0] for pos in initial_positions]
        initial_y = [pos[1] for pos in initial_positions]
    else:
        initial_x = initial_step.get('x_values', [])
        initial_y = initial_step.get('y_values', [])
    return initial_x, initial_y


def _extract_values(step, axis):
    """ステップデータからX/Y値を抽出する"""
    positions = step.get('positions', [])
    if positions:
        if axis == 'x':
            return [pos[0] for pos in positions]
        else:
            return [pos[1] for pos in positions]
    else:
        key = 'x_values' if axis == 'x' else 'y_values'
        return step.get(key, [])


def _plot_x_axis(ax, initial_frames, initial_x, steps, obj_id):
    """X軸のプロットを描画する"""
    ax.plot(
        initial_frames, initial_x, color='gray', alpha=0.5,
        linewidth=1.5,
        label=f'Original X ({len(initial_frames)} points)',
        zorder=0
    )

    x_filtered_step = _find_step(steps, 'after_x_filtering')
    if x_filtered_step:
        x_frames = x_filtered_step['frames']
        x_values = _extract_values(x_filtered_step, 'x')

        ax.plot(
            x_frames, x_values, color='blue', alpha=1.0,
            linewidth=2.5,
            label=f'X after 1 iteration ({len(x_frames)} points)',
            zorder=1
        )

    ax.set_xlabel('Frame', fontsize=12)
    ax.set_ylabel('distance_x (m)', fontsize=12)
    ax.set_title(
        f'Object {obj_id}: Relative Coordinate X (Left-Right from Camera)',
        fontsize=14, fontweight='bold'
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)


def _plot_y_axis(ax, initial_frames, initial_y, steps, obj_id):
    """Y軸のプロットを描画する"""
    ax.plot(
        initial_frames, initial_y, color='gray', alpha=0.5,
        linewidth=1.5,
        label=f'Original Y ({len(initial_frames)} points)',
        zorder=0
    )

    # Y軸の各イテレーション結果を探す
    y_iteration_steps = [
        step for step in steps
        if step.get('step', '').startswith('after_y_iteration_')
    ]

    logger.debug("    Found %d Y-axis iteration steps", len(y_iteration_steps))

    for i, step in enumerate(y_iteration_steps):
        iter_num = i + 1
        frames = step['frames']
        y_values = _extract_values(step, 'y')

        color = COLORS[iter_num % len(COLORS)]
        alpha = 0.7 if iter_num < len(y_iteration_steps) else 1.0
        linewidth = 1.8 if iter_num < len(y_iteration_steps) else 2.5

        ax.plot(
            frames, y_values, color=color, alpha=alpha,
            linewidth=linewidth,
            label=f'Y after {iter_num} iteration(s) ({len(frames)} points)',
            zorder=iter_num
        )

    ax.set_xlabel('Frame', fontsize=12)
    ax.set_ylabel('distance_y (m)', fontsize=12)
    ax.set_title(
        f'Object {obj_id}: Relative Coordinate Y (Front-Back from Camera)',
        fontsize=14, fontweight='bold'
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)


def plot_iteration_comparison(debug_dir, obj_id, output_path):
    """
    X軸とY軸それぞれのイテレーション比較グラフを生成
    X軸: 元 + 1回目の結果
    Y軸: 元 + 1~5回目の全イテレーション結果

    Args:
        debug_dir: デバッグディレクトリ (filter_debug_iter_1など)
        obj_id: オブジェクトID
        output_path: 出力ファイルパス
    """
    steps = _load_debug_data(debug_dir, obj_id)
    if steps is None:
        return

    initial_step = _find_step(steps, 'initial')
    if not initial_step:
        logger.warning("    Initial step not found in debug data")
        return

    initial_frames = initial_step['frames']
    initial_x, initial_y = _extract_initial_xy(initial_step)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12))
    _plot_x_axis(ax1, initial_frames, initial_x, steps, obj_id)
    _plot_y_axis(ax2, initial_frames, initial_y, steps, obj_id)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logger.info("  Saved comparison graph: %s", output_path)
