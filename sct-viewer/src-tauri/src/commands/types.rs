//! DTO型定義（フロントエンドとの通信用）
//!
//! SCT計算で使用する共通型はsct-coreから再エクスポート

use serde::Serialize;

// sct-coreの型を再エクスポート
pub use sct_core::{
    VehiclePositionInput, BoundingBoxData,
    VehicleBBoxEntry,
};

/// フロントエンド用のVehiclePosition（camelCase）
#[derive(Debug, Clone, Serialize)]
pub struct VehiclePositionDTO {
    pub timestamp: f64,
    #[serde(rename = "vehicleId")]
    pub vehicle_id: String,
    pub x: f64,
    pub y: f64,
    pub heading: f64,
    pub velocity: f64,
    pub vel_x: f64,
    pub vel_y: f64,
}
