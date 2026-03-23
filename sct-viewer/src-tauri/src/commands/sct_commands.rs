//! SCT計算関連のTauriコマンド

use tauri::Emitter;
use sct_core::sct::SCTParameters;
use sct_core::calculate_sct_pipeline;
use super::types::{VehiclePositionInput, VehicleBBoxEntry};
use super::relative_position::{extract_vehicle_name, find_vehicle_bbox};
use super::csv_io::write_sct_csv;

/// 1ペアのSCT計算を実行する共通ヘルパー
fn compute_sct_for_pair(
    ego_trajectory: &[VehiclePositionInput],
    target_trajectory: &[VehiclePositionInput],
    ego_bbox: &super::types::BoundingBoxData,
    target_bbox: Option<&super::types::BoundingBoxData>,
    params: &SCTParameters,
    output_folder: &str,
) -> Result<String, String> {
    let log_file_path = format!("{}/obb_debug_{}_{}.log",
        output_folder,
        ego_trajectory[0].vehicle_id,
        target_trajectory[0].vehicle_id
    );

    let sct_results = calculate_sct_pipeline(
        ego_trajectory,
        target_trajectory,
        ego_bbox,
        target_bbox,
        params,
        &params.dx_calculation_mode,
        &log_file_path,
    )?;

    let ego_id = &ego_trajectory[0].vehicle_id;
    let target_id = &target_trajectory[0].vehicle_id;
    let output_filename = format!("sct_{}_{}.csv",
        ego_id.replace("/", "_"),
        target_id.replace("/", "_")
    );
    let output_path = std::path::Path::new(output_folder).join(&output_filename);

    write_sct_csv(&output_path, &sct_results, ego_id, target_id)?;

    println!("出力完了: {:?}", output_path);

    Ok(output_filename)
}

/// SCTパラメータを構築するヘルパー
fn build_sct_params(
    ego_width: f64,
    amax: Option<f64>,
    tau: Option<f64>,
    dx_calculation_mode: Option<String>,
) -> SCTParameters {
    let calc_mode = dx_calculation_mode.unwrap_or_else(|| "trajectory".to_string());
    if let (Some(a), Some(t)) = (amax, tau) {
        SCTParameters {
            amax: a,
            tau: t,
            ego_width,
            dy_threshold_ratio: 0.05,
            vy_threshold: 0.1,
            dx_calculation_mode: calc_mode,
        }
    } else {
        let mut default_params = SCTParameters::default();
        default_params.ego_width = ego_width;
        default_params.dx_calculation_mode = calc_mode;
        default_params
    }
}

// SCT計算コマンド
#[tauri::command]
pub async fn calculate_sct(
    ego_trajectory: Vec<VehiclePositionInput>,
    target_trajectories: Vec<Vec<VehiclePositionInput>>,
    vehicle_bbox_data: Vec<VehicleBBoxEntry>,
    output_folder: String,
    amax: Option<f64>,
    tau: Option<f64>,
) -> Result<String, String> {
    println!("SCT計算開始");
    println!("自車両軌跡: {} points", ego_trajectory.len());
    println!("対象車両: {} vehicles", target_trajectories.len());
    println!("出力フォルダ: {}", output_folder);

    if ego_trajectory.is_empty() {
        return Err("自車両軌跡がありません".to_string());
    }

    let ego_bbox = find_vehicle_bbox(&ego_trajectory[0].vehicle_id, &vehicle_bbox_data)
        .ok_or(format!("自車両 {} のバウンディングボックスが見つかりません。vehicle_id: {}",
            extract_vehicle_name(&ego_trajectory[0].vehicle_id),
            ego_trajectory[0].vehicle_id))?;

    let params = build_sct_params(
        ego_bbox.bounding_box.dimensions.width,
        amax,
        tau,
        None,
    );

    println!("横方向SCT閾値: |dy| > {:.3} m (自車両幅 {:.3} m の片側 {:.1}%), |vy| > {:.3} m/s",
        params.ego_width * params.dy_threshold_ratio, params.ego_width, params.dy_threshold_ratio * 100.0, params.vy_threshold);

    let mut output_files = Vec::new();

    for (idx, target_trajectory) in target_trajectories.iter().enumerate() {
        if target_trajectory.is_empty() {
            println!("Warning: 対象車両 {} の軌跡が空です", idx);
            continue;
        }

        if ego_trajectory[0].vehicle_id == target_trajectory[0].vehicle_id {
            println!("スキップ: 自車両対自車両のSCT計算は行いません ({})", ego_trajectory[0].vehicle_id);
            continue;
        }

        let target_bbox = find_vehicle_bbox(&target_trajectory[0].vehicle_id, &vehicle_bbox_data);

        let ego_vehicle_name = extract_vehicle_name(&ego_trajectory[0].vehicle_id);
        let target_vehicle_name = extract_vehicle_name(&target_trajectory[0].vehicle_id);
        println!("処理中: 自車両 {} vs 対象車両 {}", ego_vehicle_name, target_vehicle_name);

        let output_filename = compute_sct_for_pair(
            &ego_trajectory,
            target_trajectory,
            &ego_bbox.bounding_box,
            target_bbox.map(|b| &b.bounding_box),
            &params,
            &output_folder,
        )?;

        output_files.push(output_filename);
    }

    Ok(format!("SCT計算完了: {} ファイル出力", output_files.len()))
}

// SCT総当り計算コマンド（全車両ペアを計算）
#[tauri::command]
pub async fn calculate_sct_all_pairs(
    app_handle: tauri::AppHandle,
    all_trajectories: Vec<Vec<VehiclePositionInput>>,
    vehicle_bbox_data: Vec<VehicleBBoxEntry>,
    output_folder: String,
    amax: Option<f64>,
    tau: Option<f64>,
) -> Result<String, String> {
    println!("SCT総当り計算開始");
    println!("車両数: {}", all_trajectories.len());
    println!("出力フォルダ: {}", output_folder);

    if all_trajectories.len() < 2 {
        return Err("少なくとも2台の車両が必要です".to_string());
    }

    let total_possible_pairs = all_trajectories.len() * (all_trajectories.len() - 1);
    println!("総ペア数: {}", total_possible_pairs);

    let mut output_files = Vec::new();
    let mut completed_pairs = 0;

    for i in 0..all_trajectories.len() {
        let ego_trajectory = &all_trajectories[i];

        if ego_trajectory.is_empty() {
            println!("Warning: 車両 {} の軌跡が空です", i);
            continue;
        }

        let ego_bbox = find_vehicle_bbox(&ego_trajectory[0].vehicle_id, &vehicle_bbox_data)
            .ok_or(format!("車両 {} のバウンディングボックスが見つかりません。vehicle_id: {}",
                extract_vehicle_name(&ego_trajectory[0].vehicle_id),
                ego_trajectory[0].vehicle_id))?;

        let params = build_sct_params(
            ego_bbox.bounding_box.dimensions.width,
            amax,
            tau,
            None,
        );

        for j in 0..all_trajectories.len() {
            if i == j {
                continue;
            }

            let target_trajectory = &all_trajectories[j];

            if target_trajectory.is_empty() {
                println!("Warning: 車両 {} の軌跡が空です", j);
                continue;
            }

            let target_bbox = find_vehicle_bbox(&target_trajectory[0].vehicle_id, &vehicle_bbox_data);

            let ego_vehicle_name = extract_vehicle_name(&ego_trajectory[0].vehicle_id);
            let target_vehicle_name = extract_vehicle_name(&target_trajectory[0].vehicle_id);

            completed_pairs += 1;
            println!("処理中 ({}/{}): {} vs {}",
                completed_pairs, total_possible_pairs,
                ego_vehicle_name, target_vehicle_name);

            // 進捗イベントを送信
            let progress_percent = (completed_pairs as f64 / total_possible_pairs as f64 * 100.0) as i32;
            let _ = app_handle.emit("sct-progress", serde_json::json!({
                "current": completed_pairs,
                "total": total_possible_pairs,
                "percent": progress_percent,
                "message": format!("{} vs {} を計算中...", ego_vehicle_name, target_vehicle_name)
            }));
            println!("進捗: {}/{} ({}%) - {} vs {}",
                completed_pairs, total_possible_pairs, progress_percent,
                ego_vehicle_name, target_vehicle_name);

            let output_filename = compute_sct_for_pair(
                ego_trajectory,
                target_trajectory,
                &ego_bbox.bounding_box,
                target_bbox.map(|b| &b.bounding_box),
                &params,
                &output_folder,
            )?;

            output_files.push(output_filename);
        }
    }

    Ok(format!("SCT総当り計算完了: {} ペア、{} ファイル出力",
        completed_pairs, output_files.len()))
}

// タイムスタンプフォルダを作成してSCT計算を実行（選択された自車両のみ）
#[tauri::command]
pub async fn calculate_sct_with_timestamp_folder(
    app_handle: tauri::AppHandle,
    ego_vehicle_id: String,
    all_trajectories: Vec<Vec<VehiclePositionInput>>,
    vehicle_bbox_data: Vec<VehicleBBoxEntry>,
    scenario_root_folder: String,
    amax: Option<f64>,
    tau: Option<f64>,
    dx_calculation_mode: Option<String>,
) -> Result<String, String> {
    use std::fs;
    use chrono::Local;

    // タイムスタンプフォルダを作成（YYYYMMDD_HHmmss形式）
    let now = Local::now();
    let timestamp_folder_name = now.format("%Y%m%d_%H%M%S").to_string();
    let timestamp_folder_path = format!("{}/{}", scenario_root_folder, timestamp_folder_name);

    fs::create_dir_all(&timestamp_folder_path)
        .map_err(|e| format!("タイムスタンプフォルダの作成に失敗: {}", e))?;

    println!("タイムスタンプフォルダを作成: {}", timestamp_folder_path);
    println!("選択された自車両: {}", ego_vehicle_id);

    let ego_trajectory = all_trajectories.iter()
        .find(|traj| !traj.is_empty() && traj[0].vehicle_id == ego_vehicle_id)
        .ok_or(format!("自車両 {} が見つかりません", ego_vehicle_id))?;

    let ego_bbox = find_vehicle_bbox(&ego_trajectory[0].vehicle_id, &vehicle_bbox_data)
        .ok_or(format!("車両 {} のバウンディングボックスが見つかりません。vehicle_id: {}",
            extract_vehicle_name(&ego_trajectory[0].vehicle_id),
            ego_trajectory[0].vehicle_id))?;

    let params = build_sct_params(
        ego_bbox.bounding_box.dimensions.width,
        amax,
        tau,
        dx_calculation_mode,
    );

    let mut output_files = Vec::new();
    let mut completed_pairs = 0;

    let target_count = all_trajectories.iter()
        .filter(|traj| !traj.is_empty() && traj[0].vehicle_id != ego_vehicle_id)
        .count();

    println!("対象車両数: {}", target_count);

    for target_trajectory in all_trajectories.iter() {
        if target_trajectory.is_empty() || target_trajectory[0].vehicle_id == ego_vehicle_id {
            continue;
        }

        let target_bbox = find_vehicle_bbox(&target_trajectory[0].vehicle_id, &vehicle_bbox_data);

        let ego_vehicle_name = extract_vehicle_name(&ego_trajectory[0].vehicle_id);
        let target_vehicle_name = extract_vehicle_name(&target_trajectory[0].vehicle_id);

        completed_pairs += 1;
        println!("処理中 ({}/{}): {} vs {}",
            completed_pairs, target_count,
            ego_vehicle_name, target_vehicle_name);

        // 進捗イベントを送信
        let progress_percent = (completed_pairs as f64 / target_count as f64 * 100.0) as i32;
        let _ = app_handle.emit("sct-progress", serde_json::json!({
            "current": completed_pairs,
            "total": target_count,
            "percent": progress_percent,
            "message": format!("{} vs {} を計算中...", ego_vehicle_name, target_vehicle_name)
        }));
        println!("進捗: {}/{} ({}%) - {} vs {}",
            completed_pairs, target_count, progress_percent,
            ego_vehicle_name, target_vehicle_name);

        let output_filename = compute_sct_for_pair(
            ego_trajectory,
            target_trajectory,
            &ego_bbox.bounding_box,
            target_bbox.map(|b| &b.bounding_box),
            &params,
            &timestamp_folder_path,
        )?;

        output_files.push(output_filename);
    }

    let result = format!("SCT計算完了: {} ペア、{} ファイル出力", completed_pairs, output_files.len());
    Ok(format!("{}\n出力先: {}", result, timestamp_folder_path))
}
