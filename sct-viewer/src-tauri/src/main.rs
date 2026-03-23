// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod opendrive;
mod trajectory;
mod calculation;

use commands::*;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            // OpenDRIVE関連
            load_opendrive,
            // 軌跡データ関連
            load_trajectory,
            // SCT計算関連
            calculate_sct,
            calculate_sct_all_pairs,
            calculate_sct_with_timestamp_folder,
            load_sct_result,
            load_sct_result_folder,
            // 車両バウンディングボックス関連
            load_vehicle_bbox,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
