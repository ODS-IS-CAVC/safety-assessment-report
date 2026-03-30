"""
フィルタリングモジュール

他車両の検出データをフィルタリング・平滑化するための各種フィルタを提供します。
"""

import logging
import numpy as np
import math
from typing import List, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Filter(ABC):
    """フィルタの基底クラス"""

    @abstractmethod
    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """
        フィルタを適用する

        Args:
            frames: フレーム番号のリスト
            positions: (x, y) 座標のリスト

        Returns:
            フィルタ適用後のフレームと座標のタプル
        """
        pass


class OutlierFilter(Filter):
    """
    標準偏差ベースの外れ値除去フィルタ
    """

    def __init__(self, threshold: float = 5.0):
        """
        Args:
            threshold: 外れ値除去の閾値（標準偏差の倍数）
        """
        self.threshold = threshold

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """標準偏差ベースの外れ値除去を適用"""
        if len(positions) == 0:
            return [], []

        x_values = [p[0] for p in positions]
        y_values = [p[1] for p in positions]
        x_mean, x_std = np.mean(x_values), np.std(x_values)
        y_mean, y_std = np.mean(y_values), np.std(y_values)

        # 標準偏差が0の場合の処理
        if x_std == 0:
            x_std = 1.0
        if y_std == 0:
            y_std = 1.0

        # 外れ値でないインデックスを特定
        valid_indices = [
            i for i, (x, y) in enumerate(positions)
            if (abs(x - x_mean) <= self.threshold * x_std and
                abs(y - y_mean) <= self.threshold * y_std)
        ]

        return (
            [frames[i] for i in valid_indices],
            [positions[i] for i in valid_indices]
        )


class MedianFilter(Filter):
    """
    中央値フィルタ
    各点を前後N点の中央値で置き換えます
    """

    def __init__(self, window_size: int = 3):
        """
        Args:
            window_size: フィルタのウィンドウサイズ（奇数推奨）
        """
        self.window_size = window_size

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """中央値フィルタを適用"""
        if len(positions) < self.window_size:
            return frames, positions

        filtered_positions = []
        half_window = self.window_size // 2

        for i in range(len(positions)):
            # ウィンドウの範囲を決定
            start_idx = max(0, i - half_window)
            end_idx = min(len(positions), i + half_window + 1)

            # ウィンドウ内のx, y座標を取得
            window_x = [positions[j][0]
                        for j in range(start_idx, end_idx)]
            window_y = [positions[j][1]
                        for j in range(start_idx, end_idx)]

            # 中央値を計算
            median_x = np.median(window_x)
            median_y = np.median(window_y)

            filtered_positions.append((median_x, median_y))

        return frames, filtered_positions


class KalmanFilter(Filter):
    """
    カルマンフィルタ
    2次元位置の推定に使用します
    """

    def __init__(
        self,
        process_variance: float = 0.1,
        measurement_variance: float = 1.0
    ):
        """
        Args:
            process_variance: プロセスノイズの分散
            measurement_variance: 測定ノイズの分散
        """
        self.process_variance = process_variance
        self.measurement_variance = measurement_variance

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """カルマンフィルタを適用"""
        if len(positions) < 2:
            return frames, positions

        # 状態ベクトル: [x, vx, y, vy]（位置と速度）
        # x軸とy軸で独立にフィルタリング
        filtered_positions = []

        # x軸のフィルタリング
        x_values = [p[0] for p in positions]
        x_filtered = self._kalman_1d(x_values)

        # y軸のフィルタリング
        y_values = [p[1] for p in positions]
        y_filtered = self._kalman_1d(y_values)

        # 結果を統合
        filtered_positions = list(zip(x_filtered, y_filtered))

        return frames, filtered_positions

    def _kalman_1d(self, values: List[float]) -> List[float]:
        """1次元カルマンフィルタ"""
        n = len(values)

        # 状態推定値とその誤差共分散
        x_est = values[0]  # 初期位置
        v_est = 0.0  # 初期速度
        P = np.array([[1.0, 0.0], [0.0, 1.0]])  # 誤差共分散行列

        # プロセスモデル（等速度モデル）
        dt = 1.0  # フレーム間の時間（正規化）
        F = np.array([[1.0, dt], [0.0, 1.0]])  # 状態遷移行列
        H = np.array([[1.0, 0.0]])  # 観測行列
        Q = np.array([[self.process_variance, 0.0],
                      [0.0, self.process_variance]])  # プロセスノイズ
        R = np.array([[self.measurement_variance]])  # 測定ノイズ

        filtered_values = []

        for i in range(n):
            # 予測ステップ
            x_pred = np.array([[x_est], [v_est]])
            x_pred = F @ x_pred
            P = F @ P @ F.T + Q

            # 更新ステップ
            z = np.array([[values[i]]])  # 測定値
            y = z - H @ x_pred  # イノベーション
            S = H @ P @ H.T + R  # イノベーション共分散
            K = P @ H.T @ np.linalg.inv(S)  # カルマンゲイン

            x_updated = x_pred + K @ y
            P = (np.eye(2) - K @ H) @ P

            x_est = float(x_updated[0, 0])
            v_est = float(x_updated[1, 0])

            filtered_values.append(x_est)

        return filtered_values


class AngleBasedFilter(Filter):
    """
    角度ベースのフィルタ
    セグメント間の角度が閾値以上に折れている点を除去します
    """

    def __init__(
        self,
        max_angle_degrees: float = 45.0,
        min_points: int = 3
    ):
        """
        Args:
            max_angle_degrees: 許容する最大角度変化（度）
            min_points: フィルタリング後に保持する最小点数
        """
        self.max_angle_rad = math.radians(max_angle_degrees)
        self.min_points = min_points

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """角度ベースのフィルタを適用"""
        if len(positions) < 3:
            return frames, positions

        valid_indices = [0]  # 最初の点は常に保持

        for i in range(1, len(positions) - 1):
            prev_pos = positions[i - 1]
            curr_pos = positions[i]
            next_pos = positions[i + 1]

            # 前のセグメントと次のセグメントの角度を計算
            angle1 = math.atan2(
                curr_pos[1] - prev_pos[1],
                curr_pos[0] - prev_pos[0]
            )
            angle2 = math.atan2(
                next_pos[1] - curr_pos[1],
                next_pos[0] - curr_pos[0]
            )

            # 角度差を計算（-π ~ π の範囲に正規化）
            angle_diff = angle2 - angle1
            while angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            while angle_diff < -math.pi:
                angle_diff += 2 * math.pi

            # 角度差が閾値以下なら保持
            if abs(angle_diff) <= self.max_angle_rad:
                valid_indices.append(i)

        valid_indices.append(len(positions) - 1)  # 最後の点は常に保持

        # 最小点数を下回る場合は元のデータを返す
        if len(valid_indices) < self.min_points:
            msg = (f"Warning: AngleBasedFilter would reduce points to "
                   f"{len(valid_indices)}, keeping original data")
            logger.warning(msg)
            return frames, positions

        return (
            [frames[i] for i in valid_indices],
            [positions[i] for i in valid_indices]
        )


class DistanceBasedFilter(Filter):
    """
    距離ベースのフィルタ
    隣接点間の距離が閾値を超える点を除去します（突然のジャンプを検出）
    """

    def __init__(
        self,
        max_distance: float = 10.0,
        min_points: int = 3
    ):
        """
        Args:
            max_distance: 許容する最大移動距離（メートル）
            min_points: フィルタリング後に保持する最小点数
        """
        self.max_distance = max_distance
        self.min_points = min_points

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """距離ベースのフィルタを適用"""
        if len(positions) < 2:
            return frames, positions

        valid_indices = [0]  # 最初の点は常に保持

        for i in range(1, len(positions)):
            prev_pos = positions[valid_indices[-1]]  # 最後の有効な点
            curr_pos = positions[i]

            # 距離を計算
            dx = curr_pos[0] - prev_pos[0]
            dy = curr_pos[1] - prev_pos[1]
            distance = math.sqrt(dx**2 + dy**2)

            # 距離が閾値以下なら保持
            if distance <= self.max_distance:
                valid_indices.append(i)

        # 最小点数を下回る場合は元のデータを返す
        if len(valid_indices) < self.min_points:
            msg = (f"Warning: DistanceBasedFilter would reduce points to "
                   f"{len(valid_indices)}, keeping original data")
            logger.warning(msg)
            return frames, positions

        return (
            [frames[i] for i in valid_indices],
            [positions[i] for i in valid_indices]
        )


class FilterChain:
    """
    複数のフィルタを連鎖的に適用するクラス
    """

    def __init__(self, filters: List[Filter], debug_output_dir: str = None):
        """
        Args:
            filters: 適用するフィルタのリスト（順序が重要）
            debug_output_dir: デバッグ用の中間結果出力ディレクトリ（None の場合は出力しない）
        """
        self.filters = filters
        self.debug_output_dir = debug_output_dir
        self.intermediate_results = []

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """
        全てのフィルタを順番に適用する

        Args:
            frames: フレーム番号のリスト
            positions: (x, y) 座標のリスト

        Returns:
            フィルタ適用後のフレームと座標のタプル
        """
        current_frames = frames
        current_positions = positions

        # 初期状態を記録
        self.intermediate_results = [{
            "step": "initial",
            "filter_name": "None",
            "frames": current_frames.copy(),
            "positions": current_positions.copy(),
            "count": len(current_positions)
        }]

        for i, filter_obj in enumerate(self.filters):
            filter_name = filter_obj.__class__.__name__
            msg = f"Applying filter {i+1}/{len(self.filters)}: {filter_name}"
            logger.info(msg)
            logger.info("  Before: %d points", len(current_positions))
            current_frames, current_positions = filter_obj.apply(
                current_frames, current_positions
            )
            logger.info("  After: %d points", len(current_positions))

            # 中間結果を記録
            self.intermediate_results.append({
                "step": f"after_filter_{i+1}",
                "filter_name": filter_name,
                "frames": current_frames.copy(),
                "positions": current_positions.copy(),
                "count": len(current_positions)
            })

        return current_frames, current_positions

    def save_debug_results(self, obj_id: str):
        """
        デバッグ用に中間結果をJSONファイルに保存する

        Args:
            obj_id: オブジェクトID
        """
        if self.debug_output_dir is None:
            return

        import json
        import os

        os.makedirs(self.debug_output_dir, exist_ok=True)
        output_file = os.path.join(
            self.debug_output_dir,
            f"filter_debug_obj_{obj_id}.json"
        )

        debug_data = {
            "object_id": obj_id,
            "steps": []
        }

        for result in self.intermediate_results:
            debug_data["steps"].append({
                "step": result["step"],
                "filter_name": result["filter_name"],
                "point_count": result["count"],
                "frame_range": [
                    result["frames"][0] if result["frames"] else None,
                    result["frames"][-1] if result["frames"] else None
                ],
                "frames": result["frames"],
                "positions": result["positions"]
            })

        with open(output_file, 'w') as f:
            json.dump(debug_data, f, indent=2)

        logger.debug("Debug results saved to %s", output_file)


class MovingAverageFilter(Filter):
    """
    移動平均フィルタ
    各点を前後N点の平均で置き換えます
    """

    def __init__(self, window_size: int = 3):
        """
        Args:
            window_size: フィルタのウィンドウサイズ（奇数推奨）
        """
        self.window_size = window_size

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """移動平均フィルタを適用"""
        if len(positions) < self.window_size:
            return frames, positions

        filtered_positions = []
        half_window = self.window_size // 2

        for i in range(len(positions)):
            # ウィンドウの範囲を決定
            start_idx = max(0, i - half_window)
            end_idx = min(len(positions), i + half_window + 1)

            # ウィンドウ内のx, y座標を取得
            window_x = [positions[j][0]
                        for j in range(start_idx, end_idx)]
            window_y = [positions[j][1]
                        for j in range(start_idx, end_idx)]

            # 平均を計算
            mean_x = np.mean(window_x)
            mean_y = np.mean(window_y)

            filtered_positions.append((mean_x, mean_y))

        return frames, filtered_positions


class SeparateAxisFilterChain:
    """
    X軸とY軸を独立にフィルタリングするクラス
    各軸で異なる回数のイテレーションを実行できます
    """

    def __init__(
        self,
        x_filters: List[Filter],
        y_filters: List[Filter],
        x_iterations: int = 1,
        y_iterations: int = 1,
        debug_output_dir: str = None
    ):
        """
        Args:
            x_filters: X軸に適用するフィルタのリスト
            y_filters: Y軸に適用するフィルタのリスト
            x_iterations: X軸のフィルタリング繰り返し回数
            y_iterations: Y軸のフィルタリング繰り返し回数
            debug_output_dir: デバッグ用の中間結果出力ディレクトリ
        """
        self.x_filters = x_filters
        self.y_filters = y_filters
        self.x_iterations = x_iterations
        self.y_iterations = y_iterations
        self.debug_output_dir = debug_output_dir
        self.intermediate_results = []

    def apply(
        self,
        frames: List[int],
        positions: List[Tuple[float, float]]
    ) -> Tuple[List[int], List[Tuple[float, float]]]:
        """
        X軸とY軸を独立にフィルタリングする

        Args:
            frames: フレーム番号のリスト
            positions: (x, y) 座標のリスト

        Returns:
            フィルタ適用後のフレームと座標のタプル
        """
        if len(positions) == 0:
            return [], []

        # X座標とY座標を分離
        x_values = [p[0] for p in positions]
        y_values = [p[1] for p in positions]

        # 初期状態を記録
        self.intermediate_results = [{
            "step": "initial",
            "filter_name": "None",
            "frames": frames.copy(),
            "x_values": x_values.copy(),
            "y_values": y_values.copy(),
            "count": len(positions)
        }]

        # X軸をフィルタリング（複数イテレーション）
        current_x_frames = frames.copy()
        current_x_values = x_values.copy()

        for iter_num in range(self.x_iterations):
            logger.info("X軸フィルタリング - イテレーション %d/%d", iter_num + 1, self.x_iterations)
            for i, filter_obj in enumerate(self.x_filters):
                filter_name = filter_obj.__class__.__name__
                logger.info("  Applying X-filter %d/%d: %s", i+1, len(self.x_filters), filter_name)
                logger.info("    Before: %d points", len(current_x_values))

                # 1次元データとして処理するため、(x, 0.0)の形式に変換
                temp_positions = [(x, 0.0) for x in current_x_values]
                current_x_frames, temp_positions = filter_obj.apply(
                    current_x_frames, temp_positions
                )
                current_x_values = [p[0] for p in temp_positions]

                logger.info("    After: %d points", len(current_x_values))

        # 中間結果を記録
        self.intermediate_results.append({
            "step": "after_x_filtering",
            "filter_name": "X-axis filters",
            "frames": current_x_frames.copy(),
            "x_values": current_x_values.copy(),
            "y_values": None,
            "count": len(current_x_values)
        })

        # Y軸をフィルタリング（複数イテレーション）
        current_y_frames = frames.copy()
        current_y_values = y_values.copy()

        for iter_num in range(self.y_iterations):
            logger.info("Y軸フィルタリング - イテレーション %d/%d", iter_num + 1, self.y_iterations)
            for i, filter_obj in enumerate(self.y_filters):
                filter_name = filter_obj.__class__.__name__
                logger.info("  Applying Y-filter %d/%d: %s", i+1, len(self.y_filters), filter_name)
                logger.info("    Before: %d points", len(current_y_values))

                # 1次元データとして処理するため、(0.0, y)の形式に変換
                temp_positions = [(0.0, y) for y in current_y_values]
                current_y_frames, temp_positions = filter_obj.apply(
                    current_y_frames, temp_positions
                )
                current_y_values = [p[1] for p in temp_positions]

                logger.info("    After: %d points", len(current_y_values))

            # 各イテレーション後の中間結果を記録
            self.intermediate_results.append({
                "step": f"after_y_iteration_{iter_num + 1}",
                "filter_name": f"Y-axis iteration {iter_num + 1}",
                "frames": current_y_frames.copy(),
                "x_values": None,
                "y_values": current_y_values.copy(),
                "count": len(current_y_values)
            })

        # 最終のY軸フィルタリング結果を記録（後方互換性のため）
        self.intermediate_results.append({
            "step": "after_y_filtering",
            "filter_name": "Y-axis filters",
            "frames": current_y_frames.copy(),
            "x_values": None,
            "y_values": current_y_values.copy(),
            "count": len(current_y_values)
        })

        # X軸とY軸の結果を統合（両方で残ったフレームの共通部分）
        common_frames = sorted(
            set(current_x_frames) & set(current_y_frames)
        )

        if not common_frames:
            logger.warning("No common frames after X and Y filtering")
            return [], []

        # 共通フレームの座標を取得
        final_positions = []
        for frame in common_frames:
            x_idx = current_x_frames.index(frame)
            y_idx = current_y_frames.index(frame)
            final_positions.append(
                (current_x_values[x_idx], current_y_values[y_idx])
            )

        # 最終結果を記録
        self.intermediate_results.append({
            "step": "final",
            "filter_name": "Combined result",
            "frames": common_frames,
            "x_values": [p[0] for p in final_positions],
            "y_values": [p[1] for p in final_positions],
            "count": len(final_positions)
        })

        logger.info("統合結果: X軸フィルタ後=%d点, Y軸フィルタ後=%d点, 共通フレーム=%d点",
                    len(current_x_frames), len(current_y_frames), len(common_frames))

        return common_frames, final_positions

    def save_debug_results(self, obj_id: str):
        """
        デバッグ用に中間結果をJSONファイルに保存する

        Args:
            obj_id: オブジェクトID
        """
        if self.debug_output_dir is None:
            return

        import json
        import os

        os.makedirs(self.debug_output_dir, exist_ok=True)
        output_file = os.path.join(
            self.debug_output_dir,
            f"filter_debug_obj_{obj_id}.json"
        )

        debug_data = {
            "object_id": obj_id,
            "x_iterations": self.x_iterations,
            "y_iterations": self.y_iterations,
            "steps": []
        }

        for result in self.intermediate_results:
            step_data = {
                "step": result["step"],
                "point_count": result["count"],
                "frame_range": [
                    result["frames"][0] if result["frames"] else None,
                    result["frames"][-1] if result["frames"] else None
                ],
                "frames": result["frames"]
            }

            # X軸とY軸の値を保存
            if result["x_values"] is not None:
                step_data["x_values"] = result["x_values"]
            if result["y_values"] is not None:
                step_data["y_values"] = result["y_values"]

            # 後方互換性のため、x_valuesとy_valuesの両方がある場合は
            # positionsフィールドも生成
            if (result["x_values"] is not None and
                    result["y_values"] is not None):
                step_data["positions"] = list(
                    zip(result["x_values"], result["y_values"])
                )

            debug_data["steps"].append(step_data)

        with open(output_file, 'w') as f:
            json.dump(debug_data, f, indent=2)

        logger.debug("Debug results saved to %s", output_file)
