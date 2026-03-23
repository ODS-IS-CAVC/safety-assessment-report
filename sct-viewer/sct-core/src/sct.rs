//! SCT計算モジュール（型定義のみ）
//!
//! アルゴリズム実装はプリビルドバイナリに含まれる。
//! calculate_sct_data はlib.rsのFFIラッパー経由で提供。

use serde::{Deserialize, Serialize};

/// SCT計算のパラメータ
pub struct SCTParameters {
    pub amax: f64,
    pub tau: f64,
    pub ego_width: f64,
    pub dy_threshold_ratio: f64,
    pub vy_threshold: f64,
    pub dx_calculation_mode: String,
}

impl Default for SCTParameters {
    fn default() -> Self {
        Self {
            amax: 0.3 * 9.80665,
            tau: 0.75,
            ego_width: 2.0,
            dy_threshold_ratio: 0.5,
            vy_threshold: 0.1,
            dx_calculation_mode: "trajectory".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RelativePosition {
    pub frame: usize,
    pub timestamp: f64,
    pub dx: f64,
    pub dy: f64,
    pub ego_x: f64,
    pub ego_y: f64,
    pub target_x: f64,
    pub target_y: f64,
    pub ego_velocity: f64,
    pub ego_heading: f64,
    pub ego_vel_x: f64,
    pub ego_vel_y: f64,
    pub target_velocity: f64,
    pub target_heading: f64,
    pub target_vel_x: f64,
    pub target_vel_y: f64,
    pub s1_x: f64,
    pub s1_y: f64,
    pub t1_x: f64,
    pub t1_y: f64,
    pub p0_x: f64,
    pub p0_y: f64,
    pub p1_x: f64,
    pub p1_y: f64,
    pub t2_x: f64,
    pub t2_y: f64,
    pub p2_x: f64,
    pub p2_y: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SCTRow {
    pub frame: usize,
    pub timestamp: f64,
    pub dx: f64,
    pub dy: f64,
    pub dx_ma: Option<f64>,
    pub dy_ma: Option<f64>,
    pub vx: Option<f64>,
    pub vy: Option<f64>,
    pub vx_ma: Option<f64>,
    pub vy_ma: Option<f64>,
    pub vx_ego_frame: Option<f64>,
    pub vy_ego_frame: Option<f64>,
    pub vx_ego_frame_ma: Option<f64>,
    pub vy_ego_frame_ma: Option<f64>,
    pub vx_target_frame: Option<f64>,
    pub vy_target_frame: Option<f64>,
    pub vx_target_frame_ma: Option<f64>,
    pub vy_target_frame_ma: Option<f64>,
    pub ttcx: Option<f64>,
    pub ttcy: Option<f64>,
    pub sctx: Option<f64>,
    pub scty: Option<f64>,
    pub sdx: Option<f64>,
    pub scb1x: Option<f64>,
    pub scb2x: Option<f64>,
    pub scb3x: Option<f64>,
    pub sdy: Option<f64>,
    pub scb1y: Option<f64>,
    pub scb2y: Option<f64>,
    pub scb3y: Option<f64>,
    pub s1_x: f64,
    pub s1_y: f64,
    pub t1_x: f64,
    pub t1_y: f64,
    pub p0_x: f64,
    pub p0_y: f64,
    pub p1_x: f64,
    pub p1_y: f64,
    pub t2_x: f64,
    pub t2_y: f64,
    pub p2_x: f64,
    pub p2_y: f64,
    pub speed: f64,
    pub speed_kmh: f64,
    pub traveling_distance: f64,
    pub ego_abs_vy_in_ego_frame: Option<f64>,
    pub target_abs_vy_in_target_frame: Option<f64>,
    pub dx_calculation_mode: String,
}
