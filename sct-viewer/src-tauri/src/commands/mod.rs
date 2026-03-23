//! Tauriコマンドモジュール
//!
//! SCT計算ロジックはsct-coreクレートに分離。
//! このモジュールはTauriコマンドハンドラとCSV入出力を担当。

pub mod types;
pub mod csv_io;
pub mod relative_position;
pub mod sct_commands;

use crate::opendrive;
use crate::trajectory;
use sct_core::SCTRow;
use serde::Serialize;
use types::VehiclePositionDTO;
use csv_io::parse_sct_row;

// Re-export: Tauriコマンドとしてmain.rsから参照
pub use sct_commands::{calculate_sct, calculate_sct_all_pairs, calculate_sct_with_timestamp_folder};

// OpenDRIVE読み込みコマンド（esmini版）
#[tauri::command]
pub async fn load_opendrive(file_path: String) -> Result<String, String> {
    println!("OpenDRIVE読み込み開始（esmini）: {}", file_path);

    match opendrive::esmini_ffi::load_opendrive_with_esmini(&file_path) {
        Ok(road_network_data) => {
            let roads_count = road_network_data.roads.len();
            let total_lanes: usize = road_network_data.roads.iter()
                .map(|r| r.lanes.len())
                .sum();

            match serde_json::to_string(&road_network_data) {
                Ok(json_data) => {
                    println!("OpenDRIVE読み込み成功: {} roads, {} lanes", roads_count, total_lanes);
                    Ok(json_data)
                }
                Err(e) => Err(format!("JSON変換エラー: {}", e))
            }
        }
        Err(e) => Err(format!("OpenDRIVE読み込みエラー: {}", e))
    }
}

// 軌跡データ読み込みコマンド
#[tauri::command]
pub async fn load_trajectory(file_path: String, vehicle_type: String) -> Result<String, String> {
    println!("軌跡データ読み込み開始: {} ({})", file_path, vehicle_type);

    match trajectory::loader::load_trajectory_from_csv(&file_path) {
        Ok(positions) => {
            let count = positions.len();

            let dto_positions: Vec<VehiclePositionDTO> = positions.iter().map(|pos| {
                VehiclePositionDTO {
                    timestamp: pos.timestamp,
                    vehicle_id: pos.vehicle_id.clone(),
                    x: pos.x,
                    y: pos.y,
                    heading: pos.heading,
                    velocity: pos.velocity,
                    vel_x: pos.vel_x,
                    vel_y: pos.vel_y,
                }
            }).collect();

            match serde_json::to_string(&dto_positions) {
                Ok(json_data) => {
                    println!("軌跡データ読み込み成功: {} ({})", vehicle_type, count);
                    Ok(json_data)
                }
                Err(e) => Err(format!("JSON変換エラー: {}", e))
            }
        }
        Err(e) => Err(format!("軌跡データ読み込みエラー: {}", e))
    }
}

// 車両バウンディングボックス情報読み込みコマンド
#[tauri::command]
pub async fn load_vehicle_bbox() -> Result<String, String> {
    // exeと同じディレクトリのvehicle_bbox.jsonを読み込む
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("実行ファイルのパス取得エラー: {}", e))?
        .parent()
        .ok_or("親ディレクトリが見つかりません")?
        .to_path_buf();

    let json_path = exe_dir.join("vehicle_bbox.json");

    // ファイルが存在しない場合はdocsディレクトリから探す（開発環境用）
    let json_path = if json_path.exists() {
        json_path
    } else {
        let manifest_dir = std::env::var("CARGO_MANIFEST_DIR")
            .map_err(|e| format!("CARGO_MANIFEST_DIR取得エラー: {}", e))?;
        std::path::PathBuf::from(manifest_dir)
            .parent()
            .ok_or("親ディレクトリが見つかりません")?
            .join("docs")
            .join("vehicle_bbox.json")
    };

    let json_content = std::fs::read_to_string(&json_path)
        .map_err(|e| format!("ファイル読み込みエラー: {} (パス: {:?})", e, json_path))?;

    Ok(json_content)
}

// SCT結果ファイル読み込みコマンド
#[tauri::command]
pub async fn load_sct_result(file_path: String) -> Result<String, String> {
    println!("SCT結果ファイル読み込み開始: {}", file_path);

    use csv::ReaderBuilder;
    let mut reader = ReaderBuilder::new()
        .has_headers(true)
        .from_path(&file_path)
        .map_err(|e| format!("CSVファイル読み込みエラー: {}", e))?;

    let mut sct_rows = Vec::new();
    let mut ego_vehicle_id = String::new();
    let mut target_vehicle_id = String::new();

    for result in reader.records() {
        let record = result.map_err(|e| format!("CSV行読み込みエラー: {}", e))?;

        if record.len() < 24 {
            return Err(format!("CSVフォーマットエラー: 列数が不足しています (期待: 24列以上, 実際: {}列)", record.len()));
        }

        if ego_vehicle_id.is_empty() {
            ego_vehicle_id = record[0].to_string();
            target_vehicle_id = record[1].to_string();
        }

        sct_rows.push(parse_sct_row(&record));
    }

    println!("自車両ID: {}, 対象車両ID: {}", ego_vehicle_id, target_vehicle_id);

    #[derive(Serialize)]
    #[serde(rename_all = "camelCase")]
    struct SCTDataset {
        ego_vehicle_id: String,
        target_vehicle_id: String,
        data: Vec<SCTRow>,
    }

    let dataset = SCTDataset {
        ego_vehicle_id,
        target_vehicle_id,
        data: sct_rows,
    };

    let json_data = serde_json::to_string(&dataset)
        .map_err(|e| format!("JSON変換エラー: {}", e))?;

    println!("SCT結果読み込み完了: {} rows", dataset.data.len());

    Ok(json_data)
}

// SCT結果フォルダ読み込みコマンド（フォルダ内の全sct_*.csvを読み込む）
#[tauri::command]
pub async fn load_sct_result_folder(folder_path: String) -> Result<String, String> {
    println!("SCT結果フォルダ読み込み開始: {}", folder_path);

    let folder = std::path::Path::new(&folder_path);
    if !folder.is_dir() {
        return Err("指定されたパスはフォルダではありません".to_string());
    }

    let mut datasets = Vec::new();

    let entries = std::fs::read_dir(folder)
        .map_err(|e| format!("フォルダ読み込みエラー: {}", e))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("エントリ読み込みエラー: {}", e))?;
        let path = entry.path();

        if let Some(filename) = path.file_name() {
            let filename_str = filename.to_string_lossy();
            if filename_str.starts_with("sct_") && filename_str.ends_with(".csv") {
                println!("読み込み中: {} (フルパス: {})", filename_str, path.display());

                use csv::ReaderBuilder;
                let mut reader = ReaderBuilder::new()
                    .has_headers(true)
                    .from_path(&path)
                    .map_err(|e| format!("CSVファイル読み込みエラー: {}", e))?;

                let mut sct_rows = Vec::new();
                let mut ego_vehicle_id = String::new();
                let mut target_vehicle_id = String::new();

                for result in reader.records() {
                    let record = result.map_err(|e| format!("CSV行読み込みエラー: {}", e))?;

                    if record.len() < 24 {
                        println!("警告: {} - CSVフォーマットエラー: 列数が不足しています (期待: 24列以上, 実際: {}列)", filename_str, record.len());
                        continue;
                    }

                    if ego_vehicle_id.is_empty() {
                        ego_vehicle_id = record[0].to_string();
                        target_vehicle_id = record[1].to_string();
                    }

                    sct_rows.push(parse_sct_row(&record));
                }

                #[derive(Serialize)]
                #[serde(rename_all = "camelCase")]
                struct SCTDataset {
                    ego_vehicle_id: String,
                    target_vehicle_id: String,
                    data: Vec<SCTRow>,
                }

                let row_count = sct_rows.len();
                let dataset = SCTDataset {
                    ego_vehicle_id,
                    target_vehicle_id,
                    data: sct_rows,
                };

                datasets.push(dataset);
                println!("  自車両ID: {}, 対象車両ID: {}, {} rows 読み込み完了",
                    datasets.last().unwrap().ego_vehicle_id,
                    datasets.last().unwrap().target_vehicle_id,
                    row_count);
            }
        }
    }

    if datasets.is_empty() {
        return Err("フォルダ内にsct_*.csvファイルが見つかりませんでした".to_string());
    }

    let json_data = serde_json::to_string(&datasets)
        .map_err(|e| format!("JSON変換エラー: {}", e))?;

    println!("SCT結果フォルダ読み込み完了: {} ファイル", datasets.len());

    Ok(json_data)
}
