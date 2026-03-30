"""
車両間の追い越しを防止するスクリプト

推定軌跡（before_first_frame / after_last_frame）の速度を、
前方車両の速度以下に制限して追い越しを防止する。
"""

import argparse
import logging
import os
import pandas as pd
from math import sqrt
from glob import glob

logger = logging.getLogger(__name__)


def load_vehicles(trajectory_dir: str) -> dict:
    """車両軌跡CSVファイルを読み込む"""
    csv_files = glob(os.path.join(trajectory_dir, "vehicle_route_*_extended.csv"))
    if not csv_files:
        csv_files = glob(os.path.join(trajectory_dir, "vehicle_route_[0-9]*.csv"))
        csv_files = [f for f in csv_files if "_extended" not in f and "_self" not in f]

    vehicles = {}
    for csv_file in csv_files:
        basename = os.path.basename(csv_file)
        obj_id = basename.replace("vehicle_route_", "").replace("_extended.csv", "").replace(".csv", "")
        try:
            int(obj_id)
            vehicles[obj_id] = pd.read_csv(csv_file)
        except ValueError:
            continue
    return vehicles


def get_front_vehicle_info(vehicles: dict, self_df: pd.DataFrame,
                           obj_id: str, frame: int, lane: str, current_y: float) -> dict:
    """
    指定フレーム・車線で、現在位置より前方にいる最も近い車両の情報を取得

    Returns:
        dict: {'id': obj_id, 'y': pos_y, 'speed': speed} or None
    """
    front_vehicles = []

    # 自車両
    self_row = self_df[self_df['frame'] == frame]
    if not self_row.empty:
        row = self_row.iloc[0]
        if str(row.get('lane_id', '0')) == lane and row['pos_y'] > current_y:
            front_vehicles.append({
                'id': 'self',
                'y': row['pos_y'],
                'speed': row.get('speed', 0)
            })

    # 他車両
    for other_id, df in vehicles.items():
        if other_id == obj_id:
            continue
        row_df = df[df['frame'] == frame]
        if not row_df.empty:
            row = row_df.iloc[0]
            if str(row.get('lane_id', '0')) == lane and row['pos_y'] > current_y:
                front_vehicles.append({
                    'id': other_id,
                    'y': row['pos_y'],
                    'speed': row.get('speed', 0)
                })

    if front_vehicles:
        return min(front_vehicles, key=lambda v: v['y'])
    return None


def regenerate_trajectory_with_speed_limit(df: pd.DataFrame, vehicles: dict,
                                            self_df: pd.DataFrame, obj_id: str,
                                            source_type: str, fps: float,
                                            min_gap: float, max_speed_kmh: float) -> pd.DataFrame:
    """
    速度制限を適用して推定軌跡を再生成

    Args:
        df: 対象車両のDataFrame
        vehicles: 全車両の辞書
        self_df: 自車両のDataFrame
        obj_id: 対象車両ID
        source_type: 'before_first_frame' or 'after_last_frame'
        fps: フレームレート
        min_gap: 最小車間距離
        max_speed_kmh: 最大速度（km/h）
    """
    df = df.copy()
    dt = 1.0 / fps

    if source_type == 'before_first_frame':
        # 開始フレームから逆順に処理
        mask = df['source'] == source_type
        if not mask.any():
            return df

        # interpolated の最初のフレームを基準点とする
        interp_df = df[df['source'] == 'interpolated'].sort_values('frame')
        if interp_df.empty:
            return df

        base_row = interp_df.iloc[0]
        base_frame = int(base_row['frame'])
        base_y = base_row['pos_y']
        base_x = base_row['pos_x']
        base_speed = base_row.get('speed', 50)  # km/h

        # before_first_frame のフレームを逆順に処理
        before_frames = df[mask]['frame'].sort_values(ascending=False).tolist()

        prev_y = base_y
        prev_x = base_x

        for frame in before_frames:
            idx = df[df['frame'] == frame].index[0]
            lane = str(df.loc[idx, 'lane_id'])

            # 前方車両の情報を取得
            front_info = get_front_vehicle_info(vehicles, self_df, obj_id, frame, lane, prev_y - 100)

            # 使用する速度を決定
            if front_info and front_info['y'] - min_gap < prev_y:
                # 前方車両に近い場合、前方車両の速度以下に制限
                target_speed = min(base_speed, front_info['speed'], max_speed_kmh)
            else:
                target_speed = min(base_speed, max_speed_kmh)

            # 速度のみを更新（位置はOpenDRIVE軌跡を維持）
            df.loc[idx, 'speed'] = target_speed

            # 次のフレームの基準位置を更新
            prev_y = df.loc[idx, 'pos_y']
            prev_x = df.loc[idx, 'pos_x']

    elif source_type == 'after_last_frame':
        # 終了フレームから順方向に処理
        mask = df['source'] == source_type
        if not mask.any():
            return df

        # interpolated の最後のフレームを基準点とする
        interp_df = df[df['source'] == 'interpolated'].sort_values('frame')
        if interp_df.empty:
            return df

        base_row = interp_df.iloc[-1]
        base_frame = int(base_row['frame'])
        base_y = base_row['pos_y']
        base_x = base_row['pos_x']
        base_speed = base_row.get('speed', 50)  # km/h

        # after_last_frame のフレームを順方向に処理
        after_frames = df[mask]['frame'].sort_values(ascending=True).tolist()

        prev_y = base_y
        prev_x = base_x

        for frame in after_frames:
            idx = df[df['frame'] == frame].index[0]
            lane = str(df.loc[idx, 'lane_id'])

            # 前方車両の情報を取得
            front_info = get_front_vehicle_info(vehicles, self_df, obj_id, frame, lane, prev_y)

            # 使用する速度を決定
            if front_info:
                # 前方車両との距離
                gap = front_info['y'] - prev_y

                if gap <= min_gap:
                    # すでに最小距離以下：停止
                    target_speed = 0
                elif gap < min_gap * 3:
                    # 近い場合は前方車両の速度以下に制限
                    target_speed = min(base_speed, front_info['speed'], max_speed_kmh)
                else:
                    target_speed = min(base_speed, max_speed_kmh)
            else:
                target_speed = min(base_speed, max_speed_kmh)

            # 速度のみを更新（位置はOpenDRIVE軌跡を維持）
            df.loc[idx, 'speed'] = max(0, target_speed)

            # 次のフレームの基準位置を更新
            prev_y = df.loc[idx, 'pos_y']
            prev_x = df.loc[idx, 'pos_x']

    return df


def count_violations(vehicles: dict, self_df: pd.DataFrame, min_gap: float,
                     exclude_self: bool = True) -> int:
    """
    違反フレーム数をカウント

    Args:
        exclude_self: Trueの場合、自車両との違反はカウントしない（調整不可のため）
    """
    all_frames = set()
    for df in vehicles.values():
        all_frames.update(df['frame'].tolist())

    violation_count = 0
    tolerance = 0.01  # 浮動小数点誤差の許容範囲

    for frame in sorted(all_frames):
        positions = {}

        self_row = self_df[self_df['frame'] == frame]
        if not self_row.empty:
            row = self_row.iloc[0]
            positions['self'] = {
                'y': row['pos_y'],
                'lane': str(row.get('lane_id', '0'))
            }

        for obj_id, df in vehicles.items():
            row_df = df[df['frame'] == frame]
            if not row_df.empty:
                row = row_df.iloc[0]
                positions[obj_id] = {
                    'y': row['pos_y'],
                    'lane': str(row.get('lane_id', '0'))
                }

        obj_ids = list(positions.keys())
        for i in range(len(obj_ids)):
            for j in range(i + 1, len(obj_ids)):
                id1, id2 = obj_ids[i], obj_ids[j]
                pos1, pos2 = positions[id1], positions[id2]

                # 自車両との違反は除外オプション
                if exclude_self and (id1 == 'self' or id2 == 'self'):
                    continue

                if pos1['lane'] != pos2['lane']:
                    continue

                gap = abs(pos1['y'] - pos2['y'])
                if gap < min_gap - tolerance:
                    violation_count += 1

    return violation_count


def prevent_overtaking(trajectory_dir: str, self_trajectory_path: str,
                       fps: float = 30.0, min_gap: float = 5.0,
                       max_speed_kmh: float = 120.0, iterations: int = 5):
    """
    前方車両を追い越さないように速度を制限して軌跡を再生成

    Args:
        trajectory_dir: 車両軌跡CSVファイルのディレクトリ
        self_trajectory_path: 自車両軌跡CSVファイルのパス
        fps: フレームレート
        min_gap: 最小車間距離（メートル）
        max_speed_kmh: 最大速度（km/h）
        iterations: 繰り返し回数
    """
    # 自車両の軌跡を読み込み
    self_df = pd.read_csv(self_trajectory_path)
    self_df['source'] = 'normal'

    # 全車両のCSVを読み込む
    vehicles = load_vehicles(trajectory_dir)

    if not vehicles:
        logger.info("No vehicle trajectory files found")
        return

    logger.info("Preventing overtaking (%d vehicles)", len(vehicles))
    logger.info("Minimum gap: %sm, Max speed: %skm/h", min_gap, max_speed_kmh)

    for iteration in range(iterations):
        logger.info("Iteration %d", iteration + 1)

        # 各車両の推定軌跡を再生成
        for obj_id in list(vehicles.keys()):
            df = vehicles[obj_id]

            # before_first_frame を処理
            df = regenerate_trajectory_with_speed_limit(
                df, vehicles, self_df, obj_id, 'before_first_frame',
                fps, min_gap, max_speed_kmh)

            # after_last_frame を処理
            df = regenerate_trajectory_with_speed_limit(
                df, vehicles, self_df, obj_id, 'after_last_frame',
                fps, min_gap, max_speed_kmh)

            vehicles[obj_id] = df

        # 違反数をチェック
        violation_count = count_violations(vehicles, self_df, min_gap)
        logger.info("Violations remaining: %d", violation_count)

        if violation_count == 0:
            break

    # 結果を保存
    logger.info("Saving adjusted trajectories")
    for obj_id, df in vehicles.items():
        output_path = os.path.join(trajectory_dir, f"vehicle_route_{obj_id}_extended.csv")
        df.to_csv(output_path, index=False)
        logger.info("Saved: %s", output_path)

    # 結果の検証
    logger.info("Verification")
    verify_no_overtaking(vehicles, self_df, min_gap)


def verify_no_overtaking(vehicles: dict, self_df: pd.DataFrame, min_gap: float):
    """追い越しがないことを検証"""
    all_frames = set()
    for df in vehicles.values():
        all_frames.update(df['frame'].tolist())

    violation_count = 0
    violation_pairs = {}
    tolerance = 0.01

    for frame in sorted(all_frames):
        positions = {}

        # 自車両
        self_row = self_df[self_df['frame'] == frame]
        if not self_row.empty:
            row = self_row.iloc[0]
            positions['self'] = {
                'y': row['pos_y'],
                'lane': str(row.get('lane_id', '0'))
            }

        # 他車両
        for obj_id, df in vehicles.items():
            row_df = df[df['frame'] == frame]
            if not row_df.empty:
                row = row_df.iloc[0]
                positions[obj_id] = {
                    'y': row['pos_y'],
                    'lane': str(row.get('lane_id', '0'))
                }

        # 同一車線でのギャップチェック
        obj_ids = list(positions.keys())
        for i in range(len(obj_ids)):
            for j in range(i + 1, len(obj_ids)):
                id1, id2 = obj_ids[i], obj_ids[j]
                pos1, pos2 = positions[id1], positions[id2]

                if pos1['lane'] != pos2['lane']:
                    continue

                gap = abs(pos1['y'] - pos2['y'])
                if gap < min_gap - tolerance:
                    violation_count += 1
                    key = tuple(sorted([id1, id2]))
                    if key not in violation_pairs:
                        violation_pairs[key] = 0
                    violation_pairs[key] += 1

    logger.info("Frames with gap < %sm (excluding self): %d", min_gap, violation_count)
    if violation_pairs:
        logger.warning("Violation pairs:")
        for (v1, v2), count in sorted(violation_pairs.items(), key=lambda x: -x[1]):
            logger.warning("  %s-%s: %d frames", v1, v2, count)
    else:
        logger.info("No violations detected!")


def main():
    parser = argparse.ArgumentParser(
        description='Prevent vehicles from overtaking by limiting speeds')
    parser.add_argument('--trajectory_dir', required=True,
                        help='Directory containing vehicle trajectory CSV files')
    parser.add_argument('--self_trajectory', required=True,
                        help='Path to ego vehicle trajectory CSV file')
    parser.add_argument('--fps', type=float, default=30.0,
                        help='Frames per second')
    parser.add_argument('--min_gap', type=float, default=5.0,
                        help='Minimum gap between vehicles (meters)')
    parser.add_argument('--max_speed', type=float, default=120.0,
                        help='Maximum speed (km/h)')
    parser.add_argument('--iterations', type=int, default=5,
                        help='Number of iterations')

    args = parser.parse_args()

    prevent_overtaking(
        args.trajectory_dir,
        args.self_trajectory,
        args.fps,
        args.min_gap,
        args.max_speed,
        args.iterations
    )


if __name__ == "__main__":
    main()
