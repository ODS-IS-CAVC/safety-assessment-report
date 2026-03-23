//! CSV入出力関連の関数

use sct_core::sct;
use std::fs::File;
use std::io::Write;
use std::path::Path;

/// 文字列をf64にパース（失敗時は0.0）
pub fn parse_f64(s: &str) -> f64 {
    s.parse::<f64>().unwrap_or(0.0)
}

/// 文字列をOption<f64>にパース（空文字列はNone）
pub fn parse_opt_f64(s: &str) -> Option<f64> {
    if s.is_empty() {
        None
    } else {
        s.parse::<f64>().ok()
    }
}

/// CSVカラムインデックス定数
pub mod csv_columns {
    pub const FRAME: usize = 2;
    pub const TIMESTAMP: usize = 3;
    pub const DX: usize = 4;
    pub const DY: usize = 5;
    pub const DX_MA: usize = 6;
    pub const DY_MA: usize = 7;
    pub const VX: usize = 8;
    pub const VY: usize = 9;
    pub const VX_MA: usize = 10;
    pub const VY_MA: usize = 11;
    pub const VX_EGO_FRAME: usize = 12;
    pub const VY_EGO_FRAME: usize = 13;
    pub const VX_EGO_FRAME_MA: usize = 14;
    pub const VY_EGO_FRAME_MA: usize = 15;
    pub const VX_TARGET_FRAME: usize = 16;
    pub const VY_TARGET_FRAME: usize = 17;
    pub const VX_TARGET_FRAME_MA: usize = 18;
    pub const VY_TARGET_FRAME_MA: usize = 19;
    pub const TTCX: usize = 20;
    pub const TTCY: usize = 21;
    pub const SCTX: usize = 22;
    pub const SCTY: usize = 23;
    pub const SDX: usize = 24;
    pub const SCB1X: usize = 25;
    pub const SCB2X: usize = 26;
    pub const SCB3X: usize = 27;
    pub const SDY: usize = 28;
    pub const SCB1Y: usize = 29;
    pub const SCB2Y: usize = 30;
    pub const SCB3Y: usize = 31;
    pub const S1_X: usize = 32;
    pub const S1_Y: usize = 33;
    pub const T1_X: usize = 34;
    pub const T1_Y: usize = 35;
    pub const P0_X: usize = 36;
    pub const P0_Y: usize = 37;
    pub const P1_X: usize = 38;
    pub const P1_Y: usize = 39;
    pub const T2_X: usize = 40;
    pub const T2_Y: usize = 41;
    pub const P2_X: usize = 42;
    pub const P2_Y: usize = 43;
    pub const SPEED: usize = 44;
    pub const SPEED_KMH: usize = 45;
    pub const TRAVELING_DISTANCE: usize = 46;
    pub const EGO_ABS_VY_IN_EGO_FRAME: usize = 47;
    pub const TARGET_ABS_VY_IN_TARGET_FRAME: usize = 48;
    pub const DX_CALCULATION_MODE: usize = 49;
}

/// CSVレコードからSCTRowをパース
pub fn parse_sct_row(record: &csv::StringRecord) -> sct::SCTRow {
    use csv_columns::*;

    sct::SCTRow {
        frame: parse_f64(&record[FRAME]) as usize,
        timestamp: parse_f64(&record[TIMESTAMP]),
        dx: parse_f64(&record[DX]),
        dy: parse_f64(&record[DY]),
        dx_ma: parse_opt_f64(&record[DX_MA]),
        dy_ma: parse_opt_f64(&record[DY_MA]),
        vx: parse_opt_f64(&record[VX]),
        vy: parse_opt_f64(&record[VY]),
        vx_ma: parse_opt_f64(&record[VX_MA]),
        vy_ma: parse_opt_f64(&record[VY_MA]),
        vx_ego_frame: parse_opt_f64(&record[VX_EGO_FRAME]),
        vy_ego_frame: parse_opt_f64(&record[VY_EGO_FRAME]),
        vx_ego_frame_ma: parse_opt_f64(&record[VX_EGO_FRAME_MA]),
        vy_ego_frame_ma: parse_opt_f64(&record[VY_EGO_FRAME_MA]),
        vx_target_frame: parse_opt_f64(&record[VX_TARGET_FRAME]),
        vy_target_frame: parse_opt_f64(&record[VY_TARGET_FRAME]),
        vx_target_frame_ma: parse_opt_f64(&record[VX_TARGET_FRAME_MA]),
        vy_target_frame_ma: parse_opt_f64(&record[VY_TARGET_FRAME_MA]),
        ttcx: parse_opt_f64(&record[TTCX]),
        ttcy: parse_opt_f64(&record[TTCY]),
        sctx: parse_opt_f64(&record[SCTX]),
        scty: parse_opt_f64(&record[SCTY]),
        sdx: parse_opt_f64(&record[SDX]),
        scb1x: parse_opt_f64(&record[SCB1X]),
        scb2x: parse_opt_f64(&record[SCB2X]),
        scb3x: parse_opt_f64(&record[SCB3X]),
        sdy: parse_opt_f64(&record[SDY]),
        scb1y: parse_opt_f64(&record[SCB1Y]),
        scb2y: parse_opt_f64(&record[SCB2Y]),
        scb3y: parse_opt_f64(&record[SCB3Y]),
        s1_x: if record.len() > S1_X { parse_f64(&record[S1_X]) } else { 0.0 },
        s1_y: if record.len() > S1_Y { parse_f64(&record[S1_Y]) } else { 0.0 },
        t1_x: if record.len() > T1_X { parse_f64(&record[T1_X]) } else { 0.0 },
        t1_y: if record.len() > T1_Y { parse_f64(&record[T1_Y]) } else { 0.0 },
        p0_x: if record.len() > P0_X { parse_f64(&record[P0_X]) } else { 0.0 },
        p0_y: if record.len() > P0_Y { parse_f64(&record[P0_Y]) } else { 0.0 },
        p1_x: if record.len() > P1_X { parse_f64(&record[P1_X]) } else { 0.0 },
        p1_y: if record.len() > P1_Y { parse_f64(&record[P1_Y]) } else { 0.0 },
        t2_x: if record.len() > T2_X { parse_f64(&record[T2_X]) } else { 0.0 },
        t2_y: if record.len() > T2_Y { parse_f64(&record[T2_Y]) } else { 0.0 },
        p2_x: if record.len() > P2_X { parse_f64(&record[P2_X]) } else { 0.0 },
        p2_y: if record.len() > P2_Y { parse_f64(&record[P2_Y]) } else { 0.0 },
        speed: if record.len() > SPEED { parse_f64(&record[SPEED]) } else { 0.0 },
        speed_kmh: if record.len() > SPEED_KMH { parse_f64(&record[SPEED_KMH]) } else { 0.0 },
        traveling_distance: if record.len() > TRAVELING_DISTANCE { parse_f64(&record[TRAVELING_DISTANCE]) } else { 0.0 },
        ego_abs_vy_in_ego_frame: if record.len() > EGO_ABS_VY_IN_EGO_FRAME { parse_opt_f64(&record[EGO_ABS_VY_IN_EGO_FRAME]) } else { None },
        target_abs_vy_in_target_frame: if record.len() > TARGET_ABS_VY_IN_TARGET_FRAME { parse_opt_f64(&record[TARGET_ABS_VY_IN_TARGET_FRAME]) } else { None },
        dx_calculation_mode: if record.len() > DX_CALCULATION_MODE { record[DX_CALCULATION_MODE].to_string() } else { "trajectory".to_string() },
    }
}

/// SCT結果をCSVに書き込む
pub fn write_sct_csv(
    path: &Path,
    results: &[sct::SCTRow],
    ego_vehicle_id: &str,
    target_vehicle_id: &str,
) -> Result<(), String> {
    let mut file = File::create(path)
        .map_err(|e| format!("ファイル作成エラー: {}", e))?;

    // ヘッダー
    writeln!(file, "ego_vehicle_id,target_vehicle_id,frame,timestamp,dx,dy,dx_ma,dy_ma,vx,vy,vx_ma,vy_ma,vx_ego_frame,vy_ego_frame,vx_ego_frame_ma,vy_ego_frame_ma,vx_target_frame,vy_target_frame,vx_target_frame_ma,vy_target_frame_ma,ttcx,ttcy,sctx,scty,sdx,scb1x,scb2x,scb3x,sdy,scb1y,scb2y,scb3y,s1_x,s1_y,t1_x,t1_y,p0_x,p0_y,p1_x,p1_y,t2_x,t2_y,p2_x,p2_y,speed,speed_kmh,traveling_distance,ego_abs_vy_in_ego_frame,target_abs_vy_in_target_frame,dx_calculation_mode")
        .map_err(|e| format!("書き込みエラー: {}", e))?;

    for row in results {
        write!(file, "{},{},{},{},{},{}", ego_vehicle_id, target_vehicle_id, row.frame, row.timestamp, row.dx, row.dy)
            .map_err(|e| format!("書き込みエラー: {}", e))?;

        for value in &[
            row.dx_ma, row.dy_ma,
            row.vx, row.vy,
            row.vx_ma, row.vy_ma,
            row.vx_ego_frame, row.vy_ego_frame,
            row.vx_ego_frame_ma, row.vy_ego_frame_ma,
            row.vx_target_frame, row.vy_target_frame,
            row.vx_target_frame_ma, row.vy_target_frame_ma,
            row.ttcx, row.ttcy, row.sctx, row.scty,
            row.sdx, row.scb1x, row.scb2x, row.scb3x,
            row.sdy, row.scb1y, row.scb2y, row.scb3y,
        ] {
            write!(file, ",{}", value.map_or(String::new(), |v| v.to_string()))
                .map_err(|e| format!("書き込みエラー: {}", e))?;
        }

        write!(file, ",{},{},{},{},{},{},{},{},{},{},{},{}",
            row.s1_x, row.s1_y, row.t1_x, row.t1_y,
            row.p0_x, row.p0_y, row.p1_x, row.p1_y,
            row.t2_x, row.t2_y, row.p2_x, row.p2_y)
            .map_err(|e| format!("書き込みエラー: {}", e))?;

        write!(file, ",{},{},{}", row.speed, row.speed_kmh, row.traveling_distance)
            .map_err(|e| format!("書き込みエラー: {}", e))?;

        write!(file, ",{},{}",
            row.ego_abs_vy_in_ego_frame.map_or(String::new(), |v| v.to_string()),
            row.target_abs_vy_in_target_frame.map_or(String::new(), |v| v.to_string()))
            .map_err(|e| format!("書き込みエラー: {}", e))?;

        write!(file, ",{}", row.dx_calculation_mode)
            .map_err(|e| format!("書き込みエラー: {}", e))?;

        writeln!(file).map_err(|e| format!("書き込みエラー: {}", e))?;
    }

    Ok(())
}
