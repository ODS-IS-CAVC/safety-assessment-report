// 軌跡データ型定義
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VehiclePosition {
    pub timestamp: f64,
    pub vehicle_id: String,
    pub x: f64,
    pub y: f64,
    pub heading: f64,
    pub velocity: f64,
    pub vel_x: f64,  // X方向速度（グローバル座標系） [m/s]
    pub vel_y: f64,  // Y方向速度（グローバル座標系） [m/s]
}


