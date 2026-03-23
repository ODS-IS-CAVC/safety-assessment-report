//! SCT計算エンジン（プリビルドバイナリラッパー）
//!
//! 型定義とユーティリティ関数を提供し、
//! 計算アルゴリズムはプリビルドのcdylibをFFI経由で呼び出す。

pub mod types;
pub mod obb;
pub mod sct;
pub mod relative_position;

// 主要な型をルートから再エクスポート
pub use types::{VehiclePositionInput, BoundingBoxData, Point3D, Dimensions, DxDyResult};
pub use sct::{SCTParameters, RelativePosition, SCTRow};
pub use relative_position::{
    VehicleBBoxEntry, extract_vehicle_name, find_vehicle_bbox,
};

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::path::PathBuf;
use std::sync::OnceLock;

use libloading::{Library, Symbol};

// プリビルドライブラリのシングルトン
static LIBRARY: OnceLock<Library> = OnceLock::new();

/// プリビルドcdylibのパスを解決
fn find_prebuilt_library() -> PathBuf {
    // 1. 環境変数 SCT_CORE_LIB で指定されたパス
    if let Ok(path) = std::env::var("SCT_CORE_LIB") {
        let p = PathBuf::from(&path);
        if p.exists() {
            return p;
        }
    }

    // 2. 実行ファイルと同じディレクトリ
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let lib_path = exe_dir.join(lib_filename());
            if lib_path.exists() {
                return lib_path;
            }
        }
    }

    // 3. sct-core/prebuilt/<platform>/
    let prebuilt_dir = if cfg!(target_os = "windows") {
        "sct-core/prebuilt/win"
    } else if cfg!(target_os = "macos") {
        "sct-core/prebuilt/mac"
    } else {
        "sct-core/prebuilt/linux"
    };

    PathBuf::from(prebuilt_dir).join(lib_filename())
}

fn lib_filename() -> &'static str {
    if cfg!(target_os = "windows") {
        "sct_core.dll"
    } else if cfg!(target_os = "macos") {
        "libsct_core.dylib"
    } else {
        "libsct_core.so"
    }
}

fn get_library() -> &'static Library {
    LIBRARY.get_or_init(|| {
        let path = find_prebuilt_library();
        unsafe {
            Library::new(&path).unwrap_or_else(|e| {
                panic!(
                    "sct-core prebuiltライブラリの読み込みに失敗: {:?}\nパス: {:?}\n\
                     SCT_CORE_LIB環境変数でパスを指定するか、\n\
                     実行ファイルと同じディレクトリに配置してください。",
                    e, path
                )
            })
        }
    })
}

// ============================================================
// FFIラッパー関数
// ============================================================

/// sct_core_compute FFIを呼び出すヘルパー
fn call_ffi_compute(input_json: &str) -> Result<String, String> {
    let lib = get_library();

    unsafe {
        let compute: Symbol<unsafe extern "C" fn(*const c_char) -> *mut c_char> =
            lib.get(b"sct_core_compute")
                .map_err(|e| format!("sct_core_compute関数が見つかりません: {}", e))?;

        let free_string: Symbol<unsafe extern "C" fn(*mut c_char)> =
            lib.get(b"sct_core_free_string")
                .map_err(|e| format!("sct_core_free_string関数が見つかりません: {}", e))?;

        let c_input = CString::new(input_json)
            .map_err(|e| format!("入力JSON変換エラー: {}", e))?;

        let result_ptr = compute(c_input.as_ptr());
        if result_ptr.is_null() {
            return Err("sct_core_computeがnullを返しました".to_string());
        }

        let result_str = CStr::from_ptr(result_ptr)
            .to_str()
            .map_err(|e| format!("結果UTF-8変換エラー: {}", e))?
            .to_string();

        free_string(result_ptr);

        Ok(result_str)
    }
}

/// FFIレスポンスのデシリアライズ用
#[derive(serde::Deserialize)]
struct FfiResponse {
    success: bool,
    data: Option<serde_json::Value>,
    error: Option<String>,
}

/// SCT計算パイプライン（prebuilt cdylib経由）
///
/// calculate_relative_positions + calculate_sct_data を一括実行し、
/// SCTRowのベクタを返す。
pub fn calculate_sct_pipeline(
    ego_trajectory: &[VehiclePositionInput],
    target_trajectory: &[VehiclePositionInput],
    ego_bbox: &BoundingBoxData,
    target_bbox: Option<&BoundingBoxData>,
    params: &SCTParameters,
    dx_calculation_mode: &str,
    log_file_path: &str,
) -> Result<Vec<SCTRow>, String> {
    let input = serde_json::json!({
        "ego_trajectory": ego_trajectory,
        "target_trajectory": target_trajectory,
        "ego_bbox": ego_bbox,
        "target_bbox": target_bbox,
        "params": {
            "amax": params.amax,
            "tau": params.tau,
            "ego_width": params.ego_width,
            "dy_threshold_ratio": params.dy_threshold_ratio,
            "vy_threshold": params.vy_threshold,
        },
        "dx_calculation_mode": dx_calculation_mode,
        "log_file_path": log_file_path,
    });

    let input_json = serde_json::to_string(&input)
        .map_err(|e| format!("入力JSONシリアライズエラー: {}", e))?;

    let result_json = call_ffi_compute(&input_json)?;

    let response: FfiResponse = serde_json::from_str(&result_json)
        .map_err(|e| format!("レスポンスJSON解析エラー: {}", e))?;

    if !response.success {
        return Err(response.error.unwrap_or_else(|| "不明なエラー".to_string()));
    }

    let data = response.data
        .ok_or_else(|| "レスポンスにdataフィールドがありません".to_string())?;

    serde_json::from_value(data)
        .map_err(|e| format!("SCTRowデシリアライズエラー: {}", e))
}
