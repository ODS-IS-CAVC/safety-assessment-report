---
marp: true
theme: default
paginate: true
---

# SCT計算仕様

## 概要

Safety Cushion Time (SCT) は、車両間の安全余裕時間を表す指標です。本ドキュメントでは、SCT算出ツールで実装されている計算方法を詳細に説明します。

---

## パラメータ

### 固定パラメータ

- **amax**: 最大減速度 = 0.3G ≈ 2.94 m/s² (0.3 × 9.80665)
- **τ (tau)**: 反応時間 = 0.75秒

---

## 入力データ形式

### CSVフォーマット

#### 必須カラム（4個）

```
timestamp, pos_x, pos_y, yaw_rad
```

- **timestamp**: タイムスタンプ（秒、浮動小数点数）
- **pos_x**: X座標（メートル、浮動小数点数）
- **pos_y**: Y座標（メートル、浮動小数点数）
- **yaw_rad**: ヨー角（ラジアン、浮動小数点数）【必須】
  - **用途**:
    - OBB（回転した矩形）の計算
    - 自車両座標系への座標変換
    - SCB領域の描画
    - 車両の前端/後端位置の計算
  - **角度の基準**:
    - データソースの座標系に依存（一般的にはX軸正方向を0ラジアン、反時計回りが正）
    - OpenDRIVE座標系: 東(X+)が0rad、北(Y+)がπ/2 rad
  - **yaw_radがない場合**:
    - すべての車両が東向き（0ラジアン）として扱われる
    - OBB最短距離計算が正しく動作しない
    - dx/dy計算が不正確になる
    - **SCT計算結果が信頼できない**
  - **重要**: 正確なSCT計算のため、yaw_radカラムは必ず含めてください

#### オプショナルカラム（推奨）

```
vel_x, vel_y
```

- **vel_x**: X方向速度（m/s、浮動小数点数）
  - ない場合は0.0
  - 影響: `velocity`フィールドが0.0になる（SCT計算には影響なし、相対速度はdx/dyの時間変化から計算）
- **vel_y**: Y方向速度（m/s、浮動小数点数）
  - ない場合は0.0
  - 影響: `velocity`フィールドが0.0になる（SCT計算には影響なし）
- **velocity計算**: `velocity = sqrt(vel_x^2 + vel_y^2)`
  - CSV出力の`speed`, `speed_kmh`フィールドに使用される
  - SCT計算自体には使用されない（相対速度はdx/dyの時間変化から計算）

#### その他のカラム

CSVにはpos_z, pitch_rad, roll_rad, acc_x等の他のカラムが含まれていても構いません。これらは読み込まれますが、SCT計算には使用されません。

#### CSVサンプル

```csv
timestamp,pos_x,pos_y,pos_z,yaw_rad,pitch_rad,roll_rad,vel_x,vel_y,vel_z
0.0000000000,447.7110307834,1284.3971145112,53.7123904173,1.2421380967,-0.0061908260,-0.0316174600,7.5312342139,22.0840233963,0.1444516830
0.0166666667,447.8365336736,1284.7651797232,53.7147953975,1.2421795970,-0.0061960123,-0.0315927089,7.5303174722,22.0843352163,0.1445726944
```

#### 車両ID抽出（命名規則）

CSVファイル名から車両IDを自動抽出します。

**命名規則**:
```
*_Veh_<車両名>.csv
*_Tgt_<車両名>.csv
```

**例**:
- ファイル名: `scenario_1_divp_Veh_HinoProfia_self.csv`
- 抽出される車両ID: `HinoProfia_self`

**命名規則に合わない場合**:
- ファイル名全体（拡張子除く）が車両IDとして使用されます

---

### 車両情報（BoundingBoxサイズ）

#### vehicle_bbox.json

車両のバウンディングボックス情報を定義するJSONファイルです。

**配置場所**:
```
docs/vehicle_bbox.json
```

**フォーマット**:

```json
{
  "vehicles": [
    {
      "name": "HinoProfia",
      "BoundingBox": {
        "Center": {
          "x": 2.536,
          "y": 0.0,
          "z": 1.849
        },
        "Dimensions": {
          "height": 3.698,
          "length": 11.87,
          "width": 2.564
        }
      }
    },
    {
      "name": "HondaVezel",
      "BoundingBox": {
        "Center": {
          "x": 1.332,
          "y": 0.0,
          "z": 0.795
        },
        "Dimensions": {
          "height": 1.59,
          "length": 4.329,
          "width": 1.799
        }
      }
    }
  ]
}
```

#### BoundingBoxの定義

##### Center（中心位置）

- **x**: 車両後軸中央を原点(0,0,0)としたときの、BoundingBox中心のX座標（メートル）
  - 正の値：車両前方向
  - 0.0の場合、BoundingBox中心が後軸中央
  - **SDMGフォーマット準拠**: 車両基準点は後軸中央
- **y**: BoundingBox中心のY座標（メートル）
  - 通常は0.0（車両の左右中心）
- **z**: BoundingBox中心のZ座標（メートル、高さ方向）
  - 地面からの高さ

##### Dimensions（寸法）

- **length**: 車両の全長（メートル）
- **width**: 車両の全幅（メートル）
- **height**: 車両の全高（メートル）

#### BoundingBoxの4隅座標の計算方法

CSVの`pos_x`, `pos_y`（後軸中央位置）と`yaw_rad`（車両向き）から、BoundingBoxの4隅座標を以下の手順で計算します。

##### ステップ1: ローカル座標系での4隅を定義

後軸中央を原点として、車両のローカル座標系で4隅を定義します。
- **X軸**: 進行方向（前方が正）
- **Y軸**: 左方向（左が正）

```
half_length = Dimensions.length / 2.0
half_width = Dimensions.width / 2.0

ローカル座標（後軸中央からのオフセット）:
  前右: (Center.x + half_length, -half_width)
  前左: (Center.x + half_length,  half_width)
  後左: (Center.x - half_length,  half_width)
  後右: (Center.x - half_length, -half_width)
```

**例**（HinoProfia: vehicle_bbox.jsonから）:
- Center.x = 2.536m（後軸中央から車両中心までの前方オフセット）
- length = 11.87m（全長）
- width = 2.564m（全幅）

**計算**:
```
half_length = length / 2.0 = 11.87 / 2.0 = 5.935m
half_width = width / 2.0 = 2.564 / 2.0 = 1.282m
```

**ローカル座標（後軸中央からのオフセット）**:
```
前右: (Center.x + half_length, -half_width)
    = (2.536 + 5.935, -1.282)
    = (8.471, -1.282)

前左: (Center.x + half_length, half_width)
    = (2.536 + 5.935, 1.282)
    = (8.471, 1.282)

後左: (Center.x - half_length, half_width)
    = (2.536 - 5.935, 1.282)
    = (-3.399, 1.282)

後右: (Center.x - half_length, -half_width)
    = (2.536 - 5.935, -1.282)
    = (-3.399, -1.282)
```

**解釈**:
- 前端は後軸中央から8.471m前方
- 後端は後軸中央から3.399m後方（負の値）
- 合計: 8.471 + 3.399 = 11.87m（全長と一致）✓

##### ステップ2: グローバル座標系に変換

CSVの`pos_x`, `pos_y`（後軸中央のグローバル座標）と`yaw_rad`を使って回転変換します。

```
cos_h = cos(yaw_rad)
sin_h = sin(yaw_rad)

グローバル座標の計算（各ローカル座標(lx, ly)に対して）:
  global_x = pos_x + lx × cos_h - ly × sin_h
  global_y = pos_y + lx × sin_h + ly × cos_h
```

**数値例**（pos_x = 100.0, pos_y = 200.0, yaw_rad = π/4 ≈ 0.785 rad）:
```
cos_h = cos(π/4) ≈ 0.707
sin_h = sin(π/4) ≈ 0.707

前右 (8.471, -1.282):
  global_x = 100.0 + 8.471×0.707 - (-1.282)×0.707 ≈ 106.897
  global_y = 200.0 + 8.471×0.707 + (-1.282)×0.707 ≈ 205.079

前左 (8.471, 1.282):
  global_x = 100.0 + 8.471×0.707 - 1.282×0.707 ≈ 105.079
  global_y = 200.0 + 8.471×0.707 + 1.282×0.707 ≈ 206.897

後左 (-3.399, 1.282):
  global_x = 100.0 + (-3.399)×0.707 - 1.282×0.707 ≈ 96.691
  global_y = 200.0 + (-3.399)×0.707 + 1.282×0.707 ≈ 198.596

後右 (-3.399, -1.282):
  global_x = 100.0 + (-3.399)×0.707 - (-1.282)×0.707 ≈ 98.509
  global_y = 200.0 + (-3.399)×0.707 + (-1.282)×0.707 ≈ 196.778
```

##### 実装箇所

`src-tauri/src/calculation/obb.rs::calculate_obb_vertices()` (63-94行目)

#### 車両名のマッチング方法

CSVファイルから抽出された車両IDと`vehicle_bbox.json`の`name`フィールドを部分一致でマッチングします。

**例**:
- CSV車両ID: `HinoProfia_self`
- JSONのname: `HinoProfia`
- → マッチング成功（`HinoProfia_self`に`HinoProfia`が含まれる）

**マッチングしない場合**:
- デフォルトのBoundingBoxが使用されます
  - length: 4.5m
  - width: 1.8m
  - height: 1.5m
  - Center: (1.5, 0.0, 0.75)

---

## 座標系

### グローバル座標系
- OpenDRIVEおよび軌跡CSVで使用される絶対座標
- (x, y) で位置を表現

### 自車両座標系

自車両座標系の基準軸の設定方法には2種類があります（仕様書P3-P6準拠）。

#### 1. 自車進行方向基準（Vehicle Heading Based）

**定義**:
- 基準軸：自車の現在の向き（heading）
- dx：自車の進行方向への相対距離
- dy：自車の進行方向に直交する方向への相対距離

**特徴**:
- リアルタイムの車両向きを基準
- 自車視点でのインスタントな危険度評価に適している
- 用途：リアルタイム衝突回避システム

#### 2. 自車予想軌跡基準（Trajectory Based）【現在の実装】

**定義**:
- 基準軸：自車の軌跡の接線方向
- dx：自車両軌跡上の距離（P0とP1の軌跡上の距離）
- dy：自車両軌跡から対象車両までの垂直距離

**特徴**:
- 自車の計画経路（軌跡）を基準
- カーブ走行時も軌跡に沿った正確な距離評価
- 自車の計画経路からの逸脱を検出可能
- 用途：経路追従型の自動運転システム、カーブでの安全評価

**本プロジェクトでは「自車予想軌跡基準」を採用**しています。

**座標系の定義**:
- 自車両の進行方向を+dx（縦方向）
- 自車両の左方向を+dy（横方向）
- 車両基準点：後軸中央

---

## サンプリング間隔の処理

### 異なるサンプリング周波数への対応

**問題**:
自車両と対象車両の軌跡データがそれぞれ異なるサンプリング間隔（周波数）で記録されている場合があります。

**例**:
- 自車両: 100Hz（10ms間隔）
- 対象車両: 50Hz（20ms間隔）

### 処理方針

**基準**: **常に自車両のタイムスタンプを基準**とします。

**実装**: `src-tauri/src/commands.rs::calculate_relative_positions()` (391-398行目)

```rust
// 自車両の各フレームをループ（自車両が基準）
for (current_idx, ego_pos) in ego_trajectory.iter().enumerate() {
    if ego_pos.timestamp < start_time || ego_pos.timestamp > end_time {
        continue;
    }

    // 対象車両の対応する位置を線形補間で取得
    let target_pos = interpolate_position(target_trajectory, ego_pos.timestamp)
        .ok_or("対象車両の位置補間に失敗しました")?;
```

### 線形補間の実装

**実装**: `src-tauri/src/commands.rs::interpolate_position()` (1021-1051行目)

**処理手順**:
1. 自車両のタイムスタンプ`t`を挟む対象車両の前後2点（p1, p2）を探す
2. 補間係数を計算: `ratio = (t - p1.timestamp) / (p2.timestamp - p1.timestamp)`
3. すべての状態量を線形補間:
   ```rust
   x = p1.x + ratio * (p2.x - p1.x)
   y = p1.y + ratio * (p2.y - p1.y)
   heading = p1.heading + ratio * (p2.heading - p1.heading)
   velocity = p1.velocity + ratio * (p2.velocity - p1.velocity)
   ```

### パターン別の動作

#### パターン1: 自車両が細かい、対象車両が粗い
- 自車両: 100Hz（10ms間隔）
- 対象車両: 50Hz（20ms間隔）
- **結果**: 対象車両を線形補間（アップサンプリング）
- **例**: 自車両0.01sのタイムスタンプに対し、対象車両の0.00sと0.02sから補間

#### パターン2: 自車両が粗い、対象車両が細かい
- 自車両: 50Hz（20ms間隔）
- 対象車両: 100Hz（10ms間隔）
- **結果**: 対象車両のデータを間引き（ダウンサンプリング）
- **例**: 自車両0.02sのタイムスタンプのみ使用、対象車両の0.01sは無視

### 理論的根拠

**なぜ自車両を基準とするか**:
- SCT計算の目的は、**自車両の各時刻における相対距離・相対速度**を知ること
- 自車両の制御・意思決定に使用するため、自車両のタイムスタンプで評価するのが自然
- 相対速度の時間微分（dx, dyの変化）も自車両のフレーム間隔で計算される

### 境界条件の処理

**タイムスタンプが範囲外の場合**:
```rust
// 対象車両データより前のタイムスタンプ
if timestamp < trajectory[0].timestamp {
    return Some(trajectory[0].clone());  // 最初のデータを返す
}

// 対象車両データより後のタイムスタンプ
if timestamp > trajectory[trajectory.len() - 1].timestamp {
    return Some(trajectory[trajectory.len() - 1].clone());  // 最後のデータを返す
}
```

**共通時間範囲の決定**:
```rust
let start_time = ego_start.max(target_start);  // 両方のデータが存在する開始時刻
let end_time = ego_end.min(target_end);        // 両方のデータが存在する終了時刻
```

### 補間精度の考察

**線形補間の精度**:
- サンプリング間隔が十分小さい場合（< 100ms）、線形補間で十分な精度
- 高速な機動（急加速・急ハンドル）では誤差が大きくなる可能性
- より高精度が必要な場合は、スプライン補間やカルマンフィルタの使用を検討

**heading（方位角）の補間**:
- 現在は単純な線形補間
- 180度を跨ぐ場合（例: 179度 → -179度）は誤差が生じる
- **改善案**: 角度を正規化してから補間（将来の拡張）

---

## 計算フロー

### 1. OBB最近点の計算 (S1, T1)

#### S1, T1の定義
- **S1**: 自車OBBで対象車OBBに最も近い点
- **T1**: 対象車OBBで自車OBBに最も近い点

#### OBB最短距離計算（詳細版）

**実装**: `src-tauri/src/commands.rs::closest_points_between_obbs_detailed()`

**計算手順**:
1. **頂点間の距離**: 4×4 = 16通り
2. **自車頂点 vs 対象車辺**: 4頂点 × 4辺 = 16通り
3. **対象車頂点 vs 自車辺**: 4頂点 × 4辺 = 16通り
4. **辺 vs 辺**（オプション）: 4辺 × 4辺 = 16通り

**合計**: 最大64通り（辺vs辺を含む場合）、通常は48通り（頂点+辺のみ）

**計算量の評価**:
- **現在**: O(64) = 定数時間（OBBは常に4頂点）
- **最適化の余地**:
  - 辺vs辺の計算（16通り）は多くの場合不要（並走時のエッジケースのみ必要）
  - 早期終了（OBBが明らかに離れている場合）
  - しかし、実用上は定数時間なので最適化の優先度は低い

**正確性 vs パフォーマンスのトレードオフ**:
- 簡易版（16通り、頂点のみ）: 高速だが精度が低い
- 詳細版（64通り）: 精度が高いが計算コストがやや高い
- **現在は詳細版を使用**（精度を優先）

**辺と点の最短距離計算**:
```rust
// 辺: edge_start → edge_end, 点: point
let edge_vec = edge_end - edge_start;
let point_vec = point - edge_start;
let t = clamp(dot(point_vec, edge_vec) / dot(edge_vec, edge_vec), 0.0, 1.0);
let closest_on_edge = edge_start + t * edge_vec;
```

---

### 2. 軌跡上の最近点計算 (P0, P1, T2, P2)

#### P0の計算
**定義**: S1から自車進行方向にCenter.x分オフセットした点

**計算方法**:
```rust
let offset = ego_bbox.Center.x;  // SDMGでは通常0だが念のため
let cos_h = ego_heading.cos();
let sin_h = ego_heading.sin();

P0.x = S1.x + offset * cos_h;
P0.y = S1.y + offset * sin_h;
```

#### P1の計算
**定義**: 自車軌跡上でT1に最も近い点

**実装関数**: `project_point_onto_trajectory` (commands.rs:905)

**計算手順**:

1. **軌跡全体での最近点探索**
   ```rust
   let mut min_distance = f64::INFINITY;
   let mut closest_segment_idx = 0;
   let mut closest_t = 0.0;
   let mut closest_t_unclamped = 0.0;  // クランプ前のt値を保存

   for i in 0..ego_trajectory.len() - 1 {
       let seg_start = (ego_trajectory[i].x, ego_trajectory[i].y);
       let seg_end = (ego_trajectory[i + 1].x, ego_trajectory[i + 1].y);

       let (t, distance) = obb::closest_point_on_segment(
           seg_start.0, seg_start.1,
           seg_end.0, seg_end.1,
           t1.0, t1.1,
       );

       if distance < min_distance {
           min_distance = distance;
           closest_segment_idx = i;
           closest_t_unclamped = t;  // クランプ前の値を保存
           closest_t = t.max(0.0).min(1.0);
       }
   }
   ```

   **重要**: `closest_t_unclamped`（クランプ前の値）を保存することで、延長線の判定が可能になる
   - `t < 0.0`: 線分の開始点より前（後方延長）
   - `0.0 ≤ t ≤ 1.0`: 線分上
   - `t > 1.0`: 線分の終端より後（前方延長）

2. **後方延長判定**: T1が軌跡の最初のセグメントより後方にある場合
   ```rust
   let last_idx = ego_trajectory.len() - 1;

   if closest_segment_idx == 0 && closest_t_unclamped < 0.0 {
       // 後方延長：trajectory[0]から逆方向に延長
       let first_dir_x = ego_trajectory[1].x - ego_trajectory[0].x;
       let first_dir_y = ego_trajectory[1].y - ego_trajectory[0].y;
       let first_dir_len = (first_dir_x * first_dir_x + first_dir_y * first_dir_y).sqrt();
       let dir_x_norm = -first_dir_x / first_dir_len;
       let dir_y_norm = -first_dir_y / first_dir_len;
       let extension_dist = -closest_t_unclamped * first_dir_len;

       let p1 = (
           ego_trajectory[0].x + extension_dist * dir_x_norm,
           ego_trajectory[0].y + extension_dist * dir_y_norm,
       );
   }
   ```

3. **前方延長判定**: T1が軌跡の最後のセグメントより前方にある場合
   ```rust
   } else if closest_segment_idx == last_idx - 1 && closest_t_unclamped > 1.0 {
       // 前方延長：trajectory[last]から前方に延長
       let last_dir_x = ego_trajectory[last_idx].x - ego_trajectory[last_idx - 1].x;
       let last_dir_y = ego_trajectory[last_idx].y - ego_trajectory[last_idx - 1].y;
       let last_dir_len = (last_dir_x * last_dir_x + last_dir_y * last_dir_y).sqrt();
       let dir_x_norm = last_dir_x / last_dir_len;
       let dir_y_norm = last_dir_y / last_dir_len;
       let extension_dist = (closest_t_unclamped - 1.0) * last_dir_len;

       let p1 = (
           ego_trajectory[last_idx].x + extension_dist * dir_x_norm,
           ego_trajectory[last_idx].y + extension_dist * dir_y_norm,
       );
   }
   ```

4. **通常の場合**: 軌跡範囲内に射影
   ```rust
   } else {
       // 軌跡範囲内：最近点を使用
       let seg_start = (ego_trajectory[closest_segment_idx].x, ego_trajectory[closest_segment_idx].y);
       let seg_end = (ego_trajectory[closest_segment_idx + 1].x, ego_trajectory[closest_segment_idx + 1].y);

       let p1 = (
           seg_start.0 + closest_t * (seg_end.0 - seg_start.0),
           seg_start.1 + closest_t * (seg_end.1 - seg_start.1),
       );
   }
   ```

**修正履歴（2025-12-18）**:
- `closest_t`を0-1にクランプ後に延長判定していた問題を修正
- `closest_t_unclamped`を保存し、延長判定と距離計算に使用
- これにより、dx/dyの軌跡外計算が正確になった

#### T2, P2の計算
**定義**:
- **T2**: 対象車の現在位置
- **P2**: 自車軌跡上でT2に最も近い点

**実装関数**: `project_point_onto_trajectory` (commands.rs:905)

**計算方法**: P1と同様の手順でT2に対する最近点P2を探索
- P1計算と同じ`project_point_onto_trajectory`関数を使用
- T2を引数として渡し、軌跡上（または延長線上）の最近点P2を取得
- 後方延長・前方延長の判定ロジックもP1と同一

---

### 3. 相対位置の計算 (dx, dy)

#### dx (縦方向相対距離)

**計算方法**:
1. 自車の前端・後端位置を計算
   ```rust
   let ego_front_local = ego_bbox.Center.x + ego_bbox.Dimensions.length / 2.0;
   let ego_rear_local = ego_bbox.Center.x - ego_bbox.Dimensions.length / 2.0;
   ```

2. P1（T1を軌跡上に投影した点）を自車両座標系に変換
   ```rust
   let p1_relative = (P1.x - ego_pos.x, P1.y - ego_pos.y);
   let cos_h = ego_heading.cos();
   let sin_h = ego_heading.sin();

   let p1_dx_local = p1_relative.x * cos_h + p1_relative.y * sin_h;
   ```

3. dxの決定
   ```rust
   if p1_dx_local >= ego_rear_local && p1_dx_local <= ego_front_local {
       dx = f64::NAN;  // 衝突状態
   } else if p1_dx_local > ego_front_local {
       dx = p1_dx_local - ego_front_local;  // 前方
   } else {
       // 後方: 自車後端からP1までの直線距離（負の値）
       let ego_rear_global = (
           ego_pos.x + ego_rear_local * cos_h,
           ego_pos.y + ego_rear_local * sin_h
       );
       let dist = sqrt((P1.x - ego_rear_global.x)^2 + (P1.y - ego_rear_global.y)^2);
       dx = -dist;
   }
   ```

**dxの符号**:
- **正（dx > 0）**: 対象車が前方（値が大きい = 遠い）
  - 例: dx = 10m → 前方10m、dx = 20m → 前方20m（遠い）
- **負（dx < 0）**: 対象車が後方（絶対値が大きい = 遠い）
  - 例: dx = -10m → 後方10m、dx = -20m → 後方20m（遠い）
  - **注意**: dx = -2m → dx = -3m は、dxが減少（より負）= 後方からさらに離れる
  - **接近時**: dx = -10m → dx = -5m は、dxが増加（絶対値減少）= 後方から接近
- **NaN**: 衝突状態

#### dy (横方向相対距離)

**計算方法**:
```rust
// P2からT2までの距離を計算
let p2_to_t2_distance = sqrt((T2.x - P2.x)^2 + (T2.y - P2.y)^2);

// S1の自車両座標系での横方向位置（オフセット）
let s1_relative = (S1.x - ego_pos.x, S1.y - ego_pos.y);
let s1_dy_local = -s1_relative.x * sin_h + s1_relative.y * cos_h;
let s1_offset = |s1_dy_local|;

// dy距離の絶対値（offsetEndからT2まで）
let dy_magnitude = p2_to_t2_distance - s1_offset;

// T2の横方向位置で符号を決定
let t2_relative = (T2.x - ego_pos.x, T2.y - ego_pos.y);
let t2_dy_local = -t2_relative.x * sin_h + t2_relative.y * cos_h;
dy = dy_magnitude * sign(t2_dy_local);
```

**dyの意味**:
- P2からT2への距離から、S1オフセット分を除いた実質的な横方向相対距離
- 可視化での「緑の濃い線」の長さに対応

**dyの符号**:
- 正: 対象車が左側
- 負: 対象車が右側

---

### 4. 相対速度の計算 (vx, vy)

#### 計算方法: dx, dyの時間変化

**重要**: 相対速度は速度ベクトルの差分ではなく、**相対距離(dx, dy)の時間変化**から算出します。

**実装**: `src-tauri/src/calculation/sct.rs::calculate_sct_data()`

```rust
// フレームiでの計算
let dx_prev = relative_positions[i - 1].dx;
let dy_prev = relative_positions[i - 1].dy;
let dx_curr = relative_positions[i].dx;
let dy_curr = relative_positions[i].dy;

let dt = relative_positions[i].timestamp - relative_positions[i - 1].timestamp;

// 相対速度 = -Δdx/Δt （接近方向が正）
let vx = -(dx_curr - dx_prev) / dt;
let vy = -(dy_curr - dy_prev) / dt;
```

**符号規則**:
- **vx > 0**: dxが減少（対象車が接近）
- **vx < 0**: dxが増加（対象車が遠ざかる）
- **vy > 0**: dyが減少（横方向に接近）
- **vy < 0**: dyが増加（横方向に離れる）

**負号（-）の理由**:
- 仕様の要求：「自車に近づく方向が正(+)、遠ざかる方向が負(-)」
- dxが減少する方向（対象車両が接近する方向）を正の相対速度とするため、時間微分に負号を付ける

**検証例**:

**前方車両が接近する場合**:
- dx = 20m → dx = 15m（減少）
- Δdx = 15 - 20 = -5m
- vx = -(-5) / dt = 5 / dt > 0（正）✓

**前方車両が遠ざかる場合**:
- dx = 20m → dx = 25m（増加）
- Δdx = 25 - 20 = 5m
- vx = -(5) / dt = -5 / dt < 0（負）✓

**後方車両が接近する場合**:
- dx = -20m → dx = -15m（絶対値が減少）
- Δdx = -15 - (-20) = 5m
- vx = -(5) / dt = -5 / dt < 0（負）

⚠️ **注意**: 後方車両の場合、符号が逆転します。これは、dxが負の値から正の方向に変化するためです。

**注意**:
- 初回フレーム（i=0）では前フレームが存在しないため、vx, vyは`None`
- dt = 0の場合、vx, vyは`None`（ゼロ除算回避）

---

### 5. 移動平均の計算 (dx_ma, dy_ma, vx_ma, vy_ma)

#### 目的
生データのノイズを除去し、安定したSCT計算を実現

#### 移動平均パラメータ
- **ウィンドウサイズ**: 30フレーム
- **ラグ補償**: ウィンドウサイズの半分（15フレーム）だけ結果をシフト

#### 実装

**移動平均関数**:
```rust
fn moving_average(data: &[f64], window_size: usize) -> Vec<Option<f64>> {
    let mut result = vec![None; data.len()];
    let shift = window_size / 2;  // ラグ補償: 15フレーム

    for i in 0..data.len() {
        if i + 1 < window_size {
            continue;  // データ不足
        }

        let start = i + 1 - window_size;
        let end = i + 1;
        let sum: f64 = data[start..end].iter().sum();
        let avg = sum / window_size as f64;

        // シフト後のインデックス
        let target_index = i + shift;
        if target_index < data.len() {
            result[target_index] = Some(avg);
        }
    }

    result
}
```

**適用順序**:
1. dx, dyの移動平均 → dx_ma, dy_ma
2. vx, vyの移動平均 → vx_ma, vy_ma

**注意**:
- 最初の29フレーム: ウィンドウサイズ不足のため`None`
- ラグ補償により、さらに15フレーム後まで`None`
- **実質、最初の44フレーム（約0.7秒）は移動平均値が`None`**

#### SCT計算での使用
- **TTC, SCT計算**: 移動平均後の`vx_ma`, `vy_ma`を使用
- **SCB表示条件**: `vx_ma > 0`または`vy_ma > 0`のときのみ表示

---

### 6. TTC (Time To Collision)

**使用する速度**: 移動平均後の`vx_ma`, `vy_ma`

**TTC_x (縦方向)**:
```rust
// 前方車両（dx > 0, vx > 0）または後方車両（dx < 0, vx < 0）が接近している場合に計算
// 接近判定：dx * vx > 0（符号が同じ = 接近中）
if dx * vx_ma.unwrap() > 0.0 {
    TTC_x = |dx| / |vx_ma.unwrap()|
} else {
    TTC_x = None
}
```

**TTC_y (横方向)**:
```rust
// 左右方向も前方・後方と同様に、接近している場合に計算
// dy * vy > 0（符号が同じ = 接近中）
if dy * vy_ma.unwrap() > 0.0 {
    TTC_y = |dy| / |vy_ma.unwrap()|
} else {
    TTC_y = None
}
```

**接近判定条件**:
- **縦方向**:
  - 前方車両：dx > 0 かつ vx > 0（前方にいて接近中）
  - 後方車両：dx < 0 かつ vx < 0（後方にいて接近中）
  - 統一条件：**dx × vx > 0**（符号が同じ = 接近中）
- **横方向**:
  - dy × vy > 0（符号が同じ = 接近中）

**計算時の処理**:
- 距離・速度は絶対値を使用（|dx| / |vx|）
- 前方・後方問わず、接近している場合は同じロジックで計算

**意味**:
- 現在の相対速度で接近し続けた場合、何秒後に衝突するか
- None: 接近していない、または遠ざかっている

**後方車両の例**:
- dx = -20m（後方20m）、vx = -5 m/s（自車から遠ざかる = 対象車両が接近）
- dx × vx = (-20) × (-5) = 100 > 0 → **接近中**
- TTC_x = |-20| / |-5| = 4.0秒

---

### 7. SCT (Safety Cushion Time)

**使用する速度**: 移動平均後の`vx_ma`, `vy_ma`

**停止時間の計算**:
```rust
stop_time = v / (2 × amax)
```

これは等減速度運動の式から導出：
- v² = 2 × amax × s
- 停止までの時間 = v / (2 × amax)

**SCT_x (縦方向)**:
```rust
if TTC_x.is_some() && vx_ma.is_some() {
    let vx_calc = |vx_ma.unwrap()|;  // 絶対値を使用
    let stop_time = vx_calc / (2.0 * params.amax);
    SCT_x = TTC_x.unwrap() - stop_time - params.tau;
} else {
    SCT_x = None;
}
```

**SCT_y (横方向)**:
```rust
if TTC_y.is_some() && vy_ma.is_some() {
    let vy_calc = |vy_ma.unwrap()|;  // 絶対値を使用
    let stop_time = vy_calc / (2.0 * params.amax);
    SCT_y = TTC_y.unwrap() - stop_time - params.tau;
} else {
    SCT_y = None;
}
```

**前方・後方両方向への対応**:
- vx, vyの絶対値を使用することで、前方・後方問わず正しく計算
- 後方車両でもSCTが負の場合は危険と判定される

**意味**:
- **SCT > 0**: 安全（衝突前に停止可能）
- **SCT < 0**: 危険（衝突を回避できない可能性あり）
- **SCTが大きいほど安全**

---

### 8. SD (Stopping Distance) と SCB (Safety Cushion Boundary)

**使用する速度**: 移動平均後の`vx_ma`, `vy_ma`

#### 停止距離 (SD)

**計算式**:
```rust
SD = τ × v + v² / (2 × amax)
```

- **第1項**: 反応時間（τ = 0.75s）中の移動距離
- **第2項**: 制動距離

**縦方向 (SD_x)**:
```rust
// 前方車両（dx > 0, vx > 0）または後方車両（dx < 0, vx < 0）が接近している場合に計算
if dx * vx_ma.unwrap() > 0.0 {
    let vx_calc = |vx_ma.unwrap()|;  // 絶対値を使用
    SD_x = params.tau * vx_calc + (vx_calc * vx_calc) / (2.0 * params.amax);
} else {
    SD_x = None;
}
```

**横方向 (SD_y)**:
```rust
// 左右方向も接近している場合に計算
if dy * vy_ma.unwrap() > 0.0 {
    let vy_calc = |vy_ma.unwrap()|;  // 絶対値を使用
    SD_y = params.tau * vy_calc + (vy_calc * vy_calc) / (2.0 * params.amax);
} else {
    SD_y = None;
}
```

#### SCB (Safety Cushion Boundary)

**定義**: 将来の時間における安全境界
```rust
SCB1 = SD + v    // 1秒後の安全境界
SCB2 = SCB1 + v  // 2秒後の安全境界
SCB3 = SCB2 + v  // 3秒後の安全境界
```

**縦方向 (SCB_x)**:
```rust
if SD_x.is_some() && vx_ma.is_some() {
    let vx_calc = |vx_ma.unwrap()|;  // 絶対値を使用
    SCB1_x = SD_x.unwrap() + vx_calc;
    SCB2_x = SCB1_x + vx_calc;
    SCB3_x = SCB2_x + vx_calc;
} else {
    SCB1_x = SCB2_x = SCB3_x = None;
}
```

**横方向 (SCB_y)**:
```rust
if SD_y.is_some() && vy_ma.is_some() {
    let vy_calc = |vy_ma.unwrap()|;  // 絶対値を使用
    SCB1_y = SD_y.unwrap() + vy_calc;
    SCB2_y = SCB1_y + vy_calc;
    SCB3_y = SCB2_y + vy_calc;
} else {
    SCB1_y = SCB2_y = SCB3_y = None;
}
```

**前方・後方両対応**:
- 速度の絶対値を使用することで、前方・後方問わず正しく計算
- 後方車両でも、接近している場合（dx < 0, vx < 0）はSCBが計算される

#### SCBの描画位置とサイズ

**自車両の縦方向SCB（前後方向）**:
- **描画条件**: `dx * vx_ma > 0`（接近中）かつ SCB値が有効
- **基準点**:
  - 前方車両（dx > 0, vx > 0）：自車両の前端位置
  - 後方車両（dx < 0, vx < 0）：自車両の後端位置
- **描画位置**:
  - SD領域: 基準点から SD_x までの矩形
  - SCB1領域: SD_x から SCB1_x までの矩形
  - SCB2領域: SCB1_x から SCB2_x までの矩形
  - SCB3領域: SCB2_x から SCB3_x までの矩形
- **描画方向**:
  - 前方車両：前方向（+dx方向）
  - 後方車両：後方向（-dx方向）
- **色分け**:
  - SD: 赤色（最も危険）
  - SCB1: オレンジ色
  - SCB2: 黄色
  - SCB3: 緑色（最も安全）

**対象車両の横方向SCB（左右方向）**:
- **描画条件**: `vy_ma > 0`（接近中）かつ SCB値が有効
- **基準点**: 対象車両の中心位置
- **描画方向**: dyの符号に応じて左右に描画
  - dy > 0（左側）: 右方向（自車に近づく方向）に描画
  - dy < 0（右側）: 左方向（自車に近づく方向）に描画
- **サイズ**: 横方向のSCB値に応じた幅

**前方/後方による表示切り替え**:
- **dx > 0（対象車両が前方）**:
  - **対象車両**: 横方向SCBを表示（左右）- vy_ma > 0の場合
  - **自車両**: 前方SCBを表示（縦方向）- vx_ma > 0の場合
- **dx < 0（対象車両が後方）**:
  - **対象車両**: 前方SCBを表示（縦方向）- vx_ma > 0の場合
  - **自車両**: SCB表示なし

**実装**: `src/components/RenderingArea.tsx`
```typescript
// 対象車両のSCB（dx値に応じて切り替え）
if (sctRow.dx > 0) {
  // 前方：横方向SCB（対象車両の左右に表示）
  if (sctRow.vy_ma != null && sctRow.vy_ma > 0) {
    drawTargetSCBRegions(targetPos, sctRow.scb1y, sctRow.scb2y, sctRow.scb3y, sctRow.dy);
  }
  // 自車両の前方SCB（対象車両が前方にいる場合）
  if (sctRow.vx_ma != null && sctRow.vx_ma > 0) {
    drawEgoSCBRegions(egoPos, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x);
  }
} else if (sctRow.dx < 0) {
  // 後方：縦方向SCB（対象車両の前方に表示）
  if (sctRow.vx_ma != null && sctRow.vx_ma > 0) {
    drawEgoSCBRegions(targetPos, sctRow.scb1x, sctRow.scb2x, sctRow.scb3x);
  }
}
```

**意味**:
- **SD < dx**: 安全（現在の速度で停止可能）
- **SD > dx**: 危険（停止距離が足りない）
- **SCB領域**: 時間経過に伴う安全余裕の視覚化

---

### 9. 可視化仕様

#### 相対距離（dx, dy）の表示色

**dx（縦方向相対距離）の可視化**:
- **色**: 赤系（`rgba(255, 69, 0, 0.9)`, OrangeRed）
- **前方（dx >= 0）**: 自車前端からP1まで軌跡に沿った曲線で表示
- **後方（dx < 0）**: 自車後端からP1まで直線で表示
- **ラベル**: `dx: {値}m` を線の中間点に表示

**dy（横方向相対距離）の可視化**:
- **色**:
  - S1オフセット部分: 薄い緑（`rgba(34, 139, 34, 0.3)`）
  - 実際のdy距離部分: 濃い緑（`rgba(34, 139, 34, 0.9)`, ForestGreen）
- **描画**: P2からT2への線として表示
  - P2からoffsetEndまで: 薄い緑（S1オフセット分）
  - offsetEndからT2まで: 濃い緑（実際のdy距離）
- **ラベル**: `dy: {値}m` を実際の距離部分（濃い緑の線）の中間点に表示

#### 計算参照点マーカーの表示

**参照点表示ON/OFF**:
- ボタン「参照点」で切り替え可能
- デフォルト: ON

**各マーカーの色とスタイル**:
| マーカー | 色 | 説明 |
|---------|-----|------|
| S1 | ライムグリーン（`#32CD32`） | 自車OBB最近点（dy系統） |
| T1 | トマト色（`#FF6347`） | 対象車OBB最近点（dx系統） |
| P1 | クリムゾン（`#DC143C`） | 自車軌跡上のT1最近点（dx系統） |
| T2 | フォレストグリーン（`#228B22`） | S1から対象車OBBへの垂線の足（dy系統） |
| P2 | ミディアムシーグリーン（`#3CB371`） | 自車軌跡上のT2最近点（dy系統） |

**補助線**:
- S1-T1間: 薄いグレー点線（`rgba(255, 255, 255, 0.3)`）- OBB最短距離の確認用

**車両BBox頂点マーカー**:
- 自車両: 黄色（`rgba(255, 255, 0, 0.9)`）
- 対象車両: シアン（`rgba(0, 255, 255, 0.9)`）
- 各車両4頂点に小さな円で表示

---

## 出力ファイルとフォーマット

### ファイル構造

SCT算出を実行すると、以下のディレクトリ構造でファイルが生成されます：

```
<選択したディレクトリ>/sct/
├── sct_<自車両ID>_<対象車両1>.csv
├── sct_<自車両ID>_<対象車両2>.csv
└── sct_<自車両ID>_<対象車両3>.csv
```

**例**:
```
docs/sample_data/Scene01/sct/
├── sct_HinoProfia_self_HondaVezel_1.csv
├── sct_HinoProfia_self_HondaNbox_1.csv
└── sct_HinoProfia_self_ToyotaAqua_1.csv
```

### CSVファイルの読み込み

**アプリケーションでの読み込み**:
1. メニュー「ファイル」→「SCT結果読み込み」を選択
2. `sct/`フォルダを選択
3. 対象車両をドロップダウンから選択
4. グラフとレンダリング領域にSCTデータが表示される

**外部ツールでの読み込み**:
- Excel, Google Sheets: そのまま開く（CSVとして認識）
- Python pandas: `pd.read_csv('sct_*.csv')`
- R: `read.csv('sct_*.csv')`

---

### CSVフォーマット仕様

#### ヘッダー（1行目）
```
ego_vehicle_id,target_vehicle_id,frame,timestamp,
dx,dy,dx_ma,dy_ma,vx,vy,vx_ma,vy_ma,
ttcx,ttcy,sctx,scty,sdx,scb1x,scb2x,scb3x,sdy,scb1y,scb2y,scb3y,
s1_x,s1_y,t1_x,t1_y,p0_x,p0_y,p1_x,p1_y,t2_x,t2_y,p2_x,p2_y,
speed,speed_kmh,traveling_distance
```

#### フィールド定義

##### 基本情報
| フィールド | 型 | 単位 | 説明 |
|-----------|-----|------|------|
| ego_vehicle_id | 文字列 | - | 自車両ID（例: HinoProfia_self） |
| target_vehicle_id | 文字列 | - | 対象車両ID（例: HondaVezel_1） |
| frame | 整数 | - | フレーム番号（0から開始） |
| timestamp | 浮動小数点 | 秒 | タイムスタンプ |

##### 相対位置・速度
| フィールド | 型 | 単位 | 説明 | 空欄の意味 |
|-----------|-----|------|------|-----------|
| dx | 浮動小数点 | m | 縦方向相対距離（自車前端/後端からP1まで） | - |
| dy | 浮動小数点 | m | 横方向相対距離（符号: +左, -右） | - |
| dx_ma | 浮動小数点 | m | dxの移動平均（ウィンドウ30） | 最初の44フレーム |
| dy_ma | 浮動小数点 | m | dyの移動平均（ウィンドウ30） | 最初の44フレーム |
| vx | 浮動小数点 | m/s | 縦方向相対速度（+接近, -遠ざかる） | 初回フレーム |
| vy | 浮動小数点 | m/s | 横方向相対速度（+接近, -遠ざかる） | 初回フレーム |
| vx_ma | 浮動小数点 | m/s | vxの移動平均（ウィンドウ30） | 最初の44フレーム |
| vy_ma | 浮動小数点 | m/s | vyの移動平均（ウィンドウ30） | 最初の44フレーム |

##### TTC/SCT
| フィールド | 型 | 単位 | 説明 | 空欄の意味 |
|-----------|-----|------|------|-----------|
| ttcx | 浮動小数点 | 秒 | 縦方向TTC（vx_ma使用） | vx_ma≤0 または dx≤0 |
| ttcy | 浮動小数点 | 秒 | 横方向TTC（vy_ma使用） | vy_ma≤0 |
| sctx | 浮動小数点 | 秒 | 縦方向SCT（vx_ma使用） | ttcxが空欄 |
| scty | 浮動小数点 | 秒 | 横方向SCT（vy_ma使用） | ttcyが空欄 |

##### 停止距離・安全境界
| フィールド | 型 | 単位 | 説明 | 空欄の意味 |
|-----------|-----|------|------|-----------|
| sdx | 浮動小数点 | m | 縦方向停止距離（vx_ma使用） | vx_ma≤0 |
| scb1x | 浮動小数点 | m | 縦方向SCB（1秒後） | vx_ma≤0 |
| scb2x | 浮動小数点 | m | 縦方向SCB（2秒後） | vx_ma≤0 |
| scb3x | 浮動小数点 | m | 縦方向SCB（3秒後） | vx_ma≤0 |
| sdy | 浮動小数点 | m | 横方向停止距離（vy_ma使用） | vy_ma≤0 |
| scb1y | 浮動小数点 | m | 横方向SCB（1秒後） | vy_ma≤0 |
| scb2y | 浮動小数点 | m | 横方向SCB（2秒後） | vy_ma≤0 |
| scb3y | 浮動小数点 | m | 横方向SCB（3秒後） | vy_ma≤0 |

##### デバッグ用座標（グローバル座標系）
| フィールド | 型 | 単位 | 説明 |
|-----------|-----|------|------|
| s1_x, s1_y | 浮動小数点 | m | S1（自車OBBで対象車OBBに最も近い点） |
| t1_x, t1_y | 浮動小数点 | m | T1（対象車OBBで自車OBBに最も近い点） |
| p0_x, p0_y | 浮動小数点 | m | P0（S1から進行方向にCenter.xオフセット） |
| p1_x, p1_y | 浮動小数点 | m | P1（自車軌跡上でT1に最も近い点） |
| t2_x, t2_y | 浮動小数点 | m | T2（対象車の現在位置） |
| p2_x, p2_y | 浮動小数点 | m | P2（自車軌跡上でT2に最も近い点） |

##### 自車両速度・移動距離
| フィールド | 型 | 単位 | 説明 |
|-----------|-----|------|------|
| speed | 浮動小数点 | m/s | 自車速度 |
| speed_kmh | 浮動小数点 | km/h | 自車速度（km/h換算） |
| traveling_distance | 浮動小数点 | m | 累積移動距離 |

---

### データの読み方

#### 例: CSVの1行（フレーム0）
```csv
HinoProfia_self,HondaVezel_1,0,0,-3.40,1.79,5.56,-0.06,,,,,9.41,14.97,20.52,26.08,,,,,445.40,1281.59,435.99,1259.53,445.40,1281.59,438.89,1258.54,435.99,1259.53,438.89,1258.54
```

**解釈**:
- **フレーム0（時刻0秒）**
- **dx = -3.40m**: 対象車が自車後方3.4mにいる（負の値）
- **dy = 1.79m**: 対象車が自車左側1.79mにいる
- **vx = 5.56 m/s**: 相対速度5.56m/s（対象車が接近中）
- **vy = -0.06 m/s**: わずかに右に移動中
- **ttcx, ttcy, sctx, scty**: 空欄（dxが負のため計算されない）
- **sdx = 9.41m**: 停止距離9.41m（vxが正のため計算される）
- **SCB1x = 14.97m, SCB2x = 20.52m, SCB3x = 26.08m**: 安全境界
- **sdy以降**: 空欄（vyがほぼ0のため）

#### 空欄セルの扱い

**CSV表記**: カンマ間が空（例: `,,`）
**意味**: 計算不可能または意味がない
**理由**:
- 速度が0または負
- 距離が0または負
- 分母が0（除算不可）

**プログラムでの処理**:
- Python pandas: `NaN`として読み込まれる
- Excel: 空セルとして表示
- Rust: `None`（Option型）

---

### データ分析の例

#### Python (pandas)
```python
import pandas as pd

# CSVを読み込み
df = pd.read_csv('sct_HinoProfia_self_HondaVezel_1.csv')

# SCT_xが負の値（危険）を抽出
危険フレーム = df[df['sctx'] < 0]

# TTC_xの最小値（最も危険な瞬間）
最小TTC = df['ttcx'].min()

# 空欄を除いてSCT_xの平均値
平均SCT = df['sctx'].dropna().mean()
```

#### Excel
1. CSVファイルを開く
2. データタブ → フィルター
3. `sctx`列で「0より小さい」を選択 → 危険なフレームを抽出
4. グラフ作成: `timestamp`を横軸、`sctx`を縦軸に設定

### トラブルシューティング

**Q: CSVを開くと文字化けする**
- A: 文字エンコーディングをUTF-8に設定してください

**Q: 空欄が多すぎる**
- A: 対象車が後方にいる、または横方向の速度が0に近い場合は正常です

**Q: すべての値が空欄**
- A: 車両が離れすぎている、または速度データが不正確な可能性があります

---

## 計算例

### 例1: 前方車両への接近

**入力**:
- dx = 50.0 m（前方50m）
- vx_ma = 10.0 m/s（接近速度10m/s）
- amax = 2.94 m/s²
- τ = 0.75 s

**計算**:
```
1. 接近判定:
   dx × vx_ma = 50.0 × 10.0 = 500 > 0 ✓（接近中）

2. TTC_x:
   TTC_x = |50.0| / |10.0| = 5.0秒

3. 停止時間:
   stop_time_x = 10.0 / (2 × 2.94) = 10.0 / 5.88 = 1.70秒

4. SCT_x:
   SCT_x = 5.0 - 1.70 - 0.75 = 2.55秒

5. SD_x:
   SD_x = 0.75 × 10.0 + 10.0² / (2 × 2.94)
        = 7.5 + 100.0 / 5.88
        = 7.5 + 17.01
        = 24.51 m

6. SCB_x:
   SCB1_x = 24.51 + 10.0 = 34.51 m
   SCB2_x = 34.51 + 10.0 = 44.51 m
   SCB3_x = 44.51 + 10.0 = 54.51 m
```

**解釈**:
- **TTC = 5.0秒**: このままの速度で5秒後に衝突
- **停止時間 = 1.7秒**: ブレーキで停止するのに1.7秒必要
- **SCT = 2.55秒**: 安全余裕時間は2.55秒（正の値なので安全）
- **SD = 24.51m**: 停止距離24.51m < 現在距離50m → 停止可能
- **SCB1 = 34.51m**: 1秒後の安全境界 < 50m → 安全
- **現在状態**: 安全（SCT > 0）だが、注意が必要

---

### 例2: 危険な接近

**入力**:
- dx = 15.0 m（前方15m）
- vx_ma = 15.0 m/s（接近速度15m/s）
- amax = 2.94 m/s²
- τ = 0.75 s

**計算**:
```
1. TTC_x = 15.0 / 15.0 = 1.0秒

2. stop_time_x = 15.0 / (2 × 2.94) = 2.55秒

3. SCT_x = 1.0 - 2.55 - 0.75 = -2.3秒（負の値！）

4. SD_x = 0.75 × 15.0 + 15.0² / (2 × 2.94)
        = 11.25 + 38.27
        = 49.52 m
```

**解釈**:
- **SCT = -2.3秒**: 負の値 → **危険！**
- **SD = 49.52m > dx = 15m**: 停止距離が現在距離を超えている
- **このままでは衝突を回避できない**

---

### 例3: 横方向の接近

**入力**:
- dy = 3.0 m（左側3m）
- vy_ma = 2.0 m/s（横方向接近速度2m/s）
- amax = 2.94 m/s²
- τ = 0.75 s

**計算**:
```
1. 接近判定:
   dy × vy_ma = 3.0 × 2.0 = 6.0 > 0 ✓（接近中）

2. TTC_y = 3.0 / 2.0 = 1.5秒

3. stop_time_y = 2.0 / (2 × 2.94) = 0.34秒

4. SCT_y = 1.5 - 0.34 - 0.75 = 0.41秒

5. SD_y = 0.75 × 2.0 + 2.0² / (2 × 2.94)
        = 1.5 + 0.68
        = 2.18 m

6. SCB_y:
   SCB1_y = 2.18 + 2.0 = 4.18 m
```

**解釈**:
- **SCT_y = 0.41秒**: わずかに安全（正の値だが小さい）
- **SD = 2.18m < dy = 3m**: 停止可能
- **注意が必要な状況**

---

## SCB衝突判定（フロントエンド実装）

### 概要

SCB領域間の衝突判定は、フロントエンドでリアルタイムに実行されます。CSVには衝突判定結果を含めず、描画時に必要な場合のみ計算します。

**実装場所**: `src/utils/scbUtils.ts`, `src/utils/vehicleRenderer.ts`

### ニアミス判定ルール（仕様書P7準拠）

#### ニアミス判定マトリックス

車両間のSCB衝突レベルは、自車のSCBと対象車のSCBの組み合わせによって決定されます。

**4段階の安全余裕領域**:
- **SD（SCB0）**: 停止距離（Safety Distance）- 最も内側の安全領域
- **SCB1**: 1秒後の安全境界
- **SCB2**: 2秒後の安全境界
- **SCB3**: 3秒後の安全境界

| 自車SCB \ 対象車SCB | 車両本体 | SD   | SCB1 | SCB2 | SCB3 |
|---------------------|----------|------|------|------|------|
| **車両本体**        | 事故     | 大   | 大   | 中   | 小   |
| **SD (SCB0)**       | 大       | 大   | 大   | 中   | 小   |
| **SCB1**            | 大       | 大   | 大   | 中   | 小   |
| **SCB2**            | 中       | 中   | 中   | 中   | 小   |
| **SCB3**            | 小       | 小   | 小   | 小   | 小   |

#### ニアミスレベルの定義

- **事故**: 車両本体同士が衝突
  - 最も危険な状態、即座の回避行動が必要
  - UI表示：「衝突」

- **ニアミス大**: SD（SCB0）またはSCB1の衝突
  - 緊急レベル、強い警告が必要
  - UI表示：「ニアミス大」
  - 例：
    - 自車SD vs 対象車本体
    - 自車SD vs 対象車SD
    - 自車SCB1 vs 対象車本体
    - 自車SCB1 vs 対象車SCB1
    - 自車SCB1 vs 対象車SD

- **ニアミス中**: SCB2同士またはSCB2と車両本体/SCB1が衝突
  - 注意レベル、警告表示が必要
  - UI表示：「ニアミス中」
  - 例：
    - 自車SCB2 vs 対象車SCB2
    - 自車SCB2 vs 対象車SCB1
    - 自車SCB2 vs 対象車SD

- **ニアミス小**: SCB3同士またはSCB3と他のSCBが衝突
  - 軽微な接近、情報表示レベル
  - UI表示：「ニアミス小」
  - 例：
    - 自車SCB3 vs 対象車SCB3
    - 自車SCB3 vs 対象車SCB2
    - 自車SCB3 vs 対象車SD

- **安全**: 衝突なし
  - UI表示：なし（安全時は非表示）

**重要**: ニアミス判定はフロントエンドでリアルタイムに実行され、CSV出力には含まれません

#### 優先順位

複数のSCB衝突が同時に発生する場合、最も危険なレベルを採用します。

**優先順位**: 事故 > ニアミス大 > ニアミス中 > ニアミス小

**例**:
- 自車本体と対象車SCB1が衝突、かつ自車SCB2と対象車SCB2が衝突
  - → **ニアミス大**を採用（本体とSCB1の衝突が最も危険）

### 実装手順

**1. SCBポリゴンの生成**:

```typescript
const createSCBPolygon = (
  vehicleX: number,
  vehicleY: number,
  vehicleHeading: number,
  vehicleLength: number,
  vehicleWidth: number,
  centerOffsetX: number,
  scbValue: number,
  direction: 'forward' | 'backward' | 'left' | 'right'
): SAT.Polygon | null
```

**処理内容**:
1. SCB領域の矩形をローカル座標で定義
2. 車両の向き（heading）で回転
3. ワールド座標に変換
4. SAT.Polygon オブジェクトを生成

**2. 衝突判定の実行**:

```typescript
const checkSCBCollisions = (
  egoPos: VehiclePosition,
  targetPos: VehiclePosition,
  egoBbox: VehicleBoundingBox,
  targetBbox: VehicleBoundingBox,
  egoSCB1x, egoSCB2x, egoSCB3x: number,
  targetSCB1y, targetSCB2y, targetSCB3y: number,
  direction: 'forward' | 'backward',
  dy: number
): SCBOverlapResult
```

**処理内容**:
1. 各SCBポリゴンを生成:
   - 自車の縦方向SCB（前方または後方）
   - 対象車の横方向SCB（左または右）
2. SAT.jsを使用して衝突判定:
   - 自車本体 vs 対象車本体
   - 自車SCB1 vs 対象車SCB1
   - 自車SCB2 vs 対象車SCB2
   - 自車SCB3 vs 対象車SCB3
   - 各SCB vs 対方車両本体
3. ニアミスレベルを決定:
   - 車両本体衝突 → 「衝突」
   - SCB1衝突 → 「ニアミス大」
   - SCB2衝突 → 「ニアミス中」
   - SCB3衝突 → 「ニアミス小」
   - 衝突なし → 「安全」（非表示）

**ニアミスレベル**:
- **衝突**: 車両本体同士が衝突
- **ニアミス大**: SCB1レベルの衝突
- **ニアミス中**: SCB2レベルの衝突
- **ニアミス小**: SCB3レベルの衝突
- **安全**: 衝突なし

---

### SCB表示方法（仕様書P8準拠）

#### 2種類の表示基準

**1. 自車基準（Vehicle-based）**:
- **自車両**: 縦方向（前後）のSCBを表示
- **対象車両**: 横方向（左右）のSCBを表示
- **用途**: 自車視点での危険度評価

**2. 位置基準（Position-based）**【現在の実装】:
- **後方車両**: 縦方向（前方）のSCBを表示
- **前方車両**: 横方向（左右）のSCBを表示
- **用途**: 客観的な車間距離評価

本プロジェクトでは**位置基準（Position-based）**を採用しています。

#### SCB領域の描画仕様

**表示方法の切り替え**:
- **dx > 0（対象車両が前方）**:
  - **自車両**: 縦方向（前方）のSCBを表示
  - **対象車両**: 横方向（左右）のSCBを表示
- **dx < 0（対象車両が後方）**:
  - **対象車両**: 縦方向（前方）のSCBを表示
  - **自車両**: SCB表示なし

#### 描画スタイル

**通常時（衝突なし）**:
- 半透明（30%）で増分領域のみを描画
  - SD→SCB1、SCB1→SCB2、SCB2→SCB3の各区間
- `createIncrementalSCBPolygon`関数を使用
- 枠線なし

**衝突時**:
- 衝突しているSCBを不透明（100%）で最前面に描画
- 車両端からSCB値までの全領域を表示
- 濃い色の太い枠線で強調表示

**描画順序**:
1. OpenDRIVE道路網（最背面）
2. 通常SCB（半透明、増分領域のみ）
3. 衝突SCB（不透明、車両端からSCB値まで）
4. 車両本体（最前面）

**色分け**:
- **SCB1**: オレンジ（通常） / 濃いオレンジ `rgb(204, 102, 0)`（衝突時）
- **SCB2**: 黄色（通常） / 濃い黄色 `rgb(204, 204, 0)`（衝突時）
- **SCB3**: 水色（通常） / 濃い水色 `rgb(0, 102, 204)`（衝突時）
- **枠線の太さ**: 3px（衝突時のみ）

**車両本体の枠線**:
- 常に固定色（黒と白の二重枠線）
- 衝突レベルに関係なく同じ色を使用

#### 衝突判定と表示の分離

重要な設計として、衝突判定と表示で異なるポリゴンを使用します。

**衝突判定用**:
- `createSCBPolygon`関数を使用
- 車両端からSCB値までの全領域（0→scbValue）
- より保守的な判定（車両サイズの矩形）
- 目的：正確な衝突検出

**表示用**:
- `createIncrementalSCBPolygon`関数を使用
- 増分領域のみ（startOffset→endOffset）
- SD→SCB1、SCB1→SCB2、SCB2→SCB3を個別に描画
- 目的：視認性の向上

この分離により、正確な衝突判定と分かりやすい表示を両立しています。

### メリット

**CSVのシンプル化**:
- ファイルサイズの削減
- データ構造の簡素化
- メンテナンス性の向上

**柔軟性**:
- 衝突判定アルゴリズムの変更が容易
- 描画時のみ計算するため、計算コストの最適化が可能

**視認性**:
- 衝突時のSCBを最前面に表示
- 濃い色の使用により、衝突領域が明確に識別可能

---

## 仕様変更履歴

### 2025-01-28: dy計算方法の変更

- **従来**: T2の自車両座標系y座標をdyとして出力
- **新**: offsetEndからT2までの距離をdyとして出力
- **理由**: 可視化の「緑の濃い線」の長さと一致させるため

### 2025-01-23: SCB衝突判定のフロントエンド移行

- CSVから衝突判定フィールドを削除（19個→0個）
- フロントエンドでSAT.jsを使ってリアルタイム衝突判定
- SCB領域の視覚表現を改善（衝突時に濃い色の枠線）

### 2025-01-17: 相対速度計算方法の変更

- **従来**: 車両の速度ベクトルの差分から計算
- **新**: dx, dyの時間変化から計算
- **理由**: より直接的で正確な相対速度の算出

---

## 参考資料

- `docs/sct.py`: 元のPython実装
- `src-tauri/src/calculation/sct.rs`: Rust実装（バックエンド）
- `src/utils/scbUtils.ts`: SCB衝突判定（フロントエンド）
- `src/utils/vehicleRenderer.ts`: SCBビジュアライゼーション（フロントエンド）
- `docs/SCT_Tool_Spec.pdf`: UI/UX仕様書
