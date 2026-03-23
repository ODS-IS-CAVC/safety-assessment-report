//! 共有型定義（SCT計算で使用するデータ型）

use serde::{Deserialize, Serialize};

/// 車両位置データ（入力用）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VehiclePositionInput {
    pub timestamp: f64,
    #[serde(rename = "vehicleId")]
    pub vehicle_id: String,
    pub x: f64,
    pub y: f64,
    pub heading: f64,
    pub velocity: f64,
}

/// バウンディングボックスデータ
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BoundingBoxData {
    #[serde(rename = "Center")]
    pub center: Point3D,
    #[serde(rename = "Dimensions")]
    pub dimensions: Dimensions,
}

/// 3D座標点
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Point3D {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

/// 寸法
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Dimensions {
    pub length: f64,
    pub width: f64,
    pub height: f64,
}

/// P6仕様のdx/dy計算結果
pub struct DxDyResult {
    pub dx: f64,
    pub dy: f64,
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
