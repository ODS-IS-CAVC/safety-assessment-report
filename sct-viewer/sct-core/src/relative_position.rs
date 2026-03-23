//! 相対位置計算モジュール（型定義・ユーティリティのみ）
//!
//! calculate_relative_positions はlib.rsのFFIラッパー経由で提供。

use crate::types::BoundingBoxData;

/// vehicle_idから車両名を抽出
pub fn extract_vehicle_name(vehicle_id: &str) -> String {
    let parts: Vec<&str> = vehicle_id.split('_').collect();

    for i in 0..parts.len() {
        if parts[i] == "Veh" && i + 1 < parts.len() {
            return parts[i + 1].to_string();
        }
    }

    for part in parts.iter() {
        if !part.is_empty()
            && part.chars().next().unwrap().is_uppercase()
            && !part.chars().all(|c| c.is_numeric())
            && *part != "CarMaker"
            && *part != "Veh"
            && !part.starts_with("scenario")
            && *part != "divp"
            && *part != "self"
            && *part != "rot"
        {
            return part.to_string();
        }
    }

    parts.first().unwrap_or(&"unknown").to_string()
}

/// vehicle_idに対応するBBoxを検索
pub fn find_vehicle_bbox<'a>(
    vehicle_id: &str,
    vehicle_bbox_data: &'a [VehicleBBoxEntry],
) -> Option<&'a VehicleBBoxEntry> {
    for bbox in vehicle_bbox_data.iter() {
        if vehicle_id.contains(&bbox.name) {
            return Some(bbox);
        }
    }

    let extracted_name = extract_vehicle_name(vehicle_id);
    for bbox in vehicle_bbox_data.iter() {
        if bbox.name == extracted_name {
            return Some(bbox);
        }
    }

    None
}

/// 車両バウンディングボックスエントリ（名前付きBBox）
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct VehicleBBoxEntry {
    pub name: String,
    #[serde(rename = "BoundingBox")]
    pub bounding_box: BoundingBoxData,
}
