// 軌跡CSVローダー
use super::types::*;
use csv::ReaderBuilder;
use std::fs::File;
use std::path::Path;

/// ファイル名からvehicle_idを抽出
///
/// 命名規則: *_Veh_車両名 または *_Tgt_車両名
/// 例:
/// - "CarMaker_Veh_HinoProfia_self_rot.csv" → "HinoProfia_self_rot"
/// - "scenario_1_divp_Veh_HondaNbox_1.csv" → "HondaNbox_1"
/// - "scenario_1_divp_Tgt_Corolla.csv" → "Corolla"
pub(crate) fn extract_vehicle_id_from_filename(file_path: &str) -> String {
    Path::new(file_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .map(|s| {
            // "_Veh_" または "_Tgt_" の後ろ全体を vehicle_id として抽出
            if let Some(pos) = s.find("_Veh_") {
                s[pos + 5..].to_string()
            } else if let Some(pos) = s.find("_Tgt_") {
                s[pos + 5..].to_string()
            } else {
                s.to_string()
            }
        })
        .unwrap_or_else(|| "unknown".to_string())
}

pub fn load_trajectory_from_csv(file_path: &str) -> Result<Vec<VehiclePosition>, String> {
    println!("CSV読み込み開始: {}", file_path);

    let file = File::open(file_path)
        .map_err(|e| format!("ファイル読み込みエラー: {}", e))?;

    let mut reader = ReaderBuilder::new()
        .has_headers(true)
        .from_reader(file);

    let mut positions = Vec::new();

    // ヘッダーを確認
    let headers = reader.headers()
        .map_err(|e| format!("ヘッダー読み込みエラー: {}", e))?;

    println!("CSVヘッダー: {:?}", headers);

    // vehicle_idをファイル名から抽出
    let vehicle_id = extract_vehicle_id_from_filename(file_path);
    println!("Vehicle ID: {}", vehicle_id);

    // カラムインデックスを取得（ヘッダー名からマッピング）
    let mut timestamp_idx = None;
    let mut pos_x_idx = None;
    let mut pos_y_idx = None;
    let mut yaw_idx = None;
    let mut vel_x_idx = None;
    let mut vel_y_idx = None;

    for (i, header) in headers.iter().enumerate() {
        match header {
            "timestamp" => timestamp_idx = Some(i),
            "pos_x" => pos_x_idx = Some(i),
            "pos_y" => pos_y_idx = Some(i),
            "yaw_rad" => yaw_idx = Some(i),
            "vel_x" => vel_x_idx = Some(i),
            "vel_y" => vel_y_idx = Some(i),
            _ => {}
        }
    }

    // 必須カラムの確認
    if timestamp_idx.is_none() || pos_x_idx.is_none() || pos_y_idx.is_none() {
        return Err("必須カラム（timestamp, pos_x, pos_y）が見つかりません".to_string());
    }

    // yaw_radカラムが存在しない場合の警告
    let has_yaw = yaw_idx.is_some();
    if !has_yaw {
        println!("警告: yaw_radカラムが見つかりません。軌跡から進行方向を計算します。");
    }

    // 各レコードを読み込み
    for (i, result) in reader.records().enumerate() {
        match result {
            Ok(record) => {
                // 必須フィールドを取得
                let timestamp = record.get(timestamp_idx.unwrap())
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(0.0);

                let x = record.get(pos_x_idx.unwrap())
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(0.0);

                let y = record.get(pos_y_idx.unwrap())
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(0.0);

                // オプショナルフィールド
                // yaw_radがある場合はそれを使用、ない場合は後で計算
                let heading = yaw_idx
                    .and_then(|idx| record.get(idx))
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(0.0);

                let vel_x = vel_x_idx
                    .and_then(|idx| record.get(idx))
                    .and_then(|s| s.parse::<f64>().ok())
                    .unwrap_or(0.0);

                let vel_y = vel_y_idx
                    .and_then(|idx| record.get(idx))
                    .and_then(|s| s.parse::<f64>().ok())
                    .unwrap_or(0.0);

                // 速度ベクトルの大きさを計算
                let velocity = (vel_x * vel_x + vel_y * vel_y).sqrt();

                let position = VehiclePosition {
                    timestamp,
                    vehicle_id: vehicle_id.clone(),
                    x,
                    y,
                    heading,
                    velocity,
                    vel_x,
                    vel_y,
                };
                positions.push(position);
            }
            Err(e) => {
                println!("警告: 行{}の読み込みエラー: {}", i + 2, e);
            }
        }
    }

    // yaw_radがない場合、軌跡から進行方向を計算
    if !has_yaw && positions.len() > 1 {
        println!("軌跡から進行方向を計算中...");
        calculate_heading_from_trajectory(&mut positions);
    }

    // vel_x, vel_yがない場合、位置の時間微分から速度を計算
    let has_velocity = vel_x_idx.is_some() && vel_y_idx.is_some();
    if !has_velocity && positions.len() > 1 {
        println!("位置の時間微分から速度を計算中...");
        calculate_velocity_from_trajectory(&mut positions);
    }

    println!("CSV読み込み完了: {} points", positions.len());
    Ok(positions)
}

/// 軌跡の連続する2点から進行方向（heading）を計算
///
/// 各点について、次の点への方向をatan2で計算します。
/// - 最後の点は、前の点からの方向を使用
/// - heading = atan2(Δy, Δx)
fn calculate_heading_from_trajectory(positions: &mut Vec<VehiclePosition>) {
    let n = positions.len();
    if n < 2 {
        return;
    }

    // 各点について次の点への方向を計算
    for i in 0..n - 1 {
        let dx = positions[i + 1].x - positions[i].x;
        let dy = positions[i + 1].y - positions[i].y;

        // atan2(dy, dx) で進行方向を計算
        let heading = dy.atan2(dx);
        positions[i].heading = heading;
    }

    // 最後の点は前の点と同じheadingを使用
    positions[n - 1].heading = positions[n - 2].heading;
}

/// 軌跡の連続する2点から速度を計算
///
/// 位置の時間微分から速度ベクトル (vel_x, vel_y) と速度スカラー (velocity) を計算します。
/// - vel_x = Δx / Δt
/// - vel_y = Δy / Δt
/// - velocity = sqrt(vel_x^2 + vel_y^2)
/// - 最後の点は、前の点と同じ速度を使用
fn calculate_velocity_from_trajectory(positions: &mut Vec<VehiclePosition>) {
    let n = positions.len();
    if n < 2 {
        return;
    }

    // 各点について次の点との差分から速度を計算
    for i in 0..n - 1 {
        let dx = positions[i + 1].x - positions[i].x;
        let dy = positions[i + 1].y - positions[i].y;
        let dt = positions[i + 1].timestamp - positions[i].timestamp;

        if dt > 0.0 {
            let vel_x = dx / dt;
            let vel_y = dy / dt;
            let velocity = (vel_x * vel_x + vel_y * vel_y).sqrt();

            positions[i].vel_x = vel_x;
            positions[i].vel_y = vel_y;
            positions[i].velocity = velocity;
        }
    }

    // 最後の点は前の点と同じ速度を使用
    positions[n - 1].vel_x = positions[n - 2].vel_x;
    positions[n - 1].vel_y = positions[n - 2].vel_y;
    positions[n - 1].velocity = positions[n - 2].velocity;
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    // extract_vehicle_id_from_filename のテスト

    #[test]
    fn test_extract_veh_prefix() {
        let id = extract_vehicle_id_from_filename("scenario_1_divp_Veh_HinoProfia_self.csv");
        assert_eq!(id, "HinoProfia_self");
    }

    #[test]
    fn test_extract_tgt_prefix() {
        let id = extract_vehicle_id_from_filename("scenario_1_divp_Tgt_Corolla.csv");
        assert_eq!(id, "Corolla");
    }

    #[test]
    fn test_extract_no_prefix() {
        let id = extract_vehicle_id_from_filename("some_random_file.csv");
        assert_eq!(id, "some_random_file");
    }

    #[test]
    fn test_extract_with_path() {
        let id = extract_vehicle_id_from_filename("/path/to/CarMaker_Veh_HondaNbox_1.csv");
        assert_eq!(id, "HondaNbox_1");
    }

    #[test]
    fn test_extract_veh_with_rotation() {
        let id = extract_vehicle_id_from_filename("CarMaker_Veh_HinoProfia_self_rot.csv");
        assert_eq!(id, "HinoProfia_self_rot");
    }

    // load_trajectory_from_csv のテスト（一時ファイル使用）

    #[test]
    fn test_load_csv_basic() {
        let dir = std::env::temp_dir();
        let path = dir.join("test_Veh_TestCar.csv");
        {
            let mut f = File::create(&path).unwrap();
            writeln!(f, "timestamp,pos_x,pos_y,yaw_rad,vel_x,vel_y").unwrap();
            writeln!(f, "0.0,100.0,200.0,1.57,10.0,0.0").unwrap();
            writeln!(f, "0.0167,100.1,200.0,1.57,10.0,0.0").unwrap();
        }

        let result = load_trajectory_from_csv(path.to_str().unwrap());
        assert!(result.is_ok());
        let positions = result.unwrap();
        assert_eq!(positions.len(), 2);
        assert_eq!(positions[0].vehicle_id, "TestCar");
        assert!((positions[0].x - 100.0).abs() < 1e-10);
        assert!((positions[0].y - 200.0).abs() < 1e-10);
        assert!((positions[0].heading - 1.57).abs() < 1e-10);

        std::fs::remove_file(path).ok();
    }

    #[test]
    fn test_load_csv_missing_required_columns() {
        let dir = std::env::temp_dir();
        let path = dir.join("test_missing_cols.csv");
        {
            let mut f = File::create(&path).unwrap();
            writeln!(f, "time,x,y").unwrap();
            writeln!(f, "0.0,100.0,200.0").unwrap();
        }

        let result = load_trajectory_from_csv(path.to_str().unwrap());
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("必須カラム"));

        std::fs::remove_file(path).ok();
    }

    #[test]
    fn test_load_csv_without_yaw_calculates_heading() {
        let dir = std::env::temp_dir();
        let path = dir.join("test_Veh_NoYaw.csv");
        {
            let mut f = File::create(&path).unwrap();
            writeln!(f, "timestamp,pos_x,pos_y").unwrap();
            writeln!(f, "0.0,0.0,0.0").unwrap();
            writeln!(f, "0.1,1.0,0.0").unwrap();
            writeln!(f, "0.2,2.0,0.0").unwrap();
        }

        let result = load_trajectory_from_csv(path.to_str().unwrap());
        assert!(result.is_ok());
        let positions = result.unwrap();
        assert_eq!(positions.len(), 3);
        // 東方向（heading ≈ 0）
        assert!((positions[0].heading).abs() < 1e-10);

        std::fs::remove_file(path).ok();
    }

    #[test]
    fn test_load_csv_without_velocity_calculates_from_position() {
        let dir = std::env::temp_dir();
        let path = dir.join("test_Veh_NoVel.csv");
        {
            let mut f = File::create(&path).unwrap();
            writeln!(f, "timestamp,pos_x,pos_y,yaw_rad").unwrap();
            writeln!(f, "0.0,0.0,0.0,0.0").unwrap();
            writeln!(f, "0.1,1.0,0.0,0.0").unwrap();
        }

        let result = load_trajectory_from_csv(path.to_str().unwrap());
        assert!(result.is_ok());
        let positions = result.unwrap();
        // vel_x = Δx/Δt = 1.0/0.1 = 10.0
        assert!((positions[0].vel_x - 10.0).abs() < 1e-8);
        assert!((positions[0].velocity - 10.0).abs() < 1e-8);

        std::fs::remove_file(path).ok();
    }
}
