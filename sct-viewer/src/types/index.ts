// SCT算出ツールの型定義

// 車両の位置情報
export interface VehiclePosition {
  timestamp: number;
  vehicleId: string;
  x: number;
  y: number;
  heading: number; // ヨー角（ラジアン）
  velocity: number;
  vel_x?: number;  // X方向速度（グローバル座標系）
  vel_y?: number;  // Y方向速度（グローバル座標系）
}

// 車両バウンディングボックス情報
export interface VehicleBoundingBox {
  Center: {
    x: number;
    y: number;
    z: number;
  };
  Dimensions: {
    height: number;
    length: number;
    width: number;
  };
}

export interface VehicleBBoxData {
  name: string;
  BoundingBox: VehicleBoundingBox;
}

export interface VehicleBBoxConfig {
  vehicles: VehicleBBoxData[];
}

// SCT計算結果の行データ（CSVから読み込む）
export interface SCTRow {
  frame: number;
  timestamp: number;
  dx: number;
  dy: number;
  dx_ma: number | null;  // dx移動平均
  dy_ma: number | null;  // dy移動平均
  vx: number | null;
  vy: number | null;
  vx_ma: number | null;  // vx移動平均
  vy_ma: number | null;  // vy移動平均
  // 車両座標系での相対速度（新規追加）
  vx_ego_frame: number | null;      // 自車両座標系での相対速度X（縦方向）
  vy_ego_frame: number | null;      // 自車両座標系での相対速度Y（横方向）
  vx_ego_frame_ma: number | null;   // 自車両座標系での相対速度X（移動平均）
  vy_ego_frame_ma: number | null;   // 自車両座標系での相対速度Y（移動平均）
  vx_target_frame: number | null;   // 対象車両座標系での相対速度X（縦方向）
  vy_target_frame: number | null;   // 対象車両座標系での相対速度Y（横方向）
  vx_target_frame_ma: number | null;// 対象車両座標系での相対速度X（移動平均）
  vy_target_frame_ma: number | null;// 対象車両座標系での相対速度Y（移動平均）
  ttcx: number | null;
  ttcy: number | null;
  sctx: number | null;
  scty: number | null;
  sdx: number | null;
  scb1x: number | null;
  scb2x: number | null;
  scb3x: number | null;
  sdy: number | null;
  scb1y: number | null;
  scb2y: number | null;
  scb3y: number | null;
  // P6仕様のデバッグ用座標
  s1_x: number;
  s1_y: number;
  t1_x: number;
  t1_y: number;
  p0_x: number;
  p0_y: number;
  p1_x: number;
  p1_y: number;
  t2_x: number;
  t2_y: number;
  p2_x: number;
  p2_y: number;
  // 追加の速度・距離情報（docs/python/sct.csvに準拠）
  speed: number;              // 自車速度 (m/s)
  speed_kmh: number;          // 自車速度 (km/h)
  traveling_distance: number; // 移動距離 (m)
  // 各車両の絶対速度の車両座標系Y成分（レーンチェンジ判定用）
  ego_abs_vy_in_ego_frame: number | null;       // 自車の横方向絶対速度（自車座標系）
  target_abs_vy_in_target_frame: number | null; // 対象車の横方向絶対速度（対象車座標系）
  // OBB衝突判定結果（Rust側Parry2Dで計算）
  collision_level: number;    // 0: 車両衝突, 1: SCB1重複, 2: SCB2重複, 3: SCB3重複, 4: 安全
  // 自車SCB vs 対象車SCB の詳細衝突情報
  ego_scb1_vs_target_scb1: boolean;
  ego_scb1_vs_target_scb2: boolean;
  ego_scb1_vs_target_scb3: boolean;
  ego_scb2_vs_target_scb1: boolean;
  ego_scb2_vs_target_scb2: boolean;
  ego_scb2_vs_target_scb3: boolean;
  ego_scb3_vs_target_scb1: boolean;
  ego_scb3_vs_target_scb2: boolean;
  ego_scb3_vs_target_scb3: boolean;
  // 対象車SCB vs 自車SCB の詳細衝突情報
  target_scb1_vs_ego_scb1: boolean;
  target_scb1_vs_ego_scb2: boolean;
  target_scb1_vs_ego_scb3: boolean;
  target_scb2_vs_ego_scb1: boolean;
  target_scb2_vs_ego_scb2: boolean;
  target_scb2_vs_ego_scb3: boolean;
  target_scb3_vs_ego_scb1: boolean;
  target_scb3_vs_ego_scb2: boolean;
  target_scb3_vs_ego_scb3: boolean;
  dx_calculation_mode: string; // "heading" or "trajectory"
}

// SCT結果データセット（車両ペアごと）
export interface SCTDataset {
  egoVehicleId: string;
  targetVehicleId: string;
  data: SCTRow[];
}
