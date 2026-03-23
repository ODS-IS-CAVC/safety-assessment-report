use std::ffi::{CString, c_char, c_int, c_float};
use std::os::raw::c_uint;
use serde::{Serialize, Deserialize};

/// 非ASCII文字を含むパスをCStringに安全に変換する
/// Windows環境ではUTF-8からシステムのANSIコードページ（日本語WindowsではShift-JIS）に変換
fn path_to_cstring(path: &str) -> Result<CString, String> {
    // パスがASCIIのみならそのまま変換
    if path.is_ascii() {
        return CString::new(path)
            .map_err(|e| format!("Failed to convert path to CString: {}", e));
    }

    // Windows: UTF-8 → UTF-16 → ANSIコードページ（Shift-JIS等）に変換
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::ffi::OsStrExt;
        use std::ffi::OsStr;
        use windows_sys::Win32::Globalization::{WideCharToMultiByte, CP_ACP};

        // UTF-8 → UTF-16（null終端）
        let wide: Vec<u16> = OsStr::new(path)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();

        // 必要なバッファサイズを取得
        let len = unsafe {
            WideCharToMultiByte(
                CP_ACP,
                0,
                wide.as_ptr(),
                wide.len() as i32,
                std::ptr::null_mut(),
                0,
                std::ptr::null(),
                std::ptr::null_mut(),
            )
        };

        if len == 0 {
            return Err(format!(
                "WideCharToMultiByte size query failed for path: {}",
                path
            ));
        }

        let mut ansi_buf = vec![0u8; len as usize];
        let result = unsafe {
            WideCharToMultiByte(
                CP_ACP,
                0,
                wide.as_ptr(),
                wide.len() as i32,
                ansi_buf.as_mut_ptr(),
                len,
                std::ptr::null(),
                std::ptr::null_mut(),
            )
        };

        if result == 0 {
            return Err(format!(
                "WideCharToMultiByte conversion failed for path: {}",
                path
            ));
        }

        // null終端を除去してCStringに変換
        if let Some(null_pos) = ansi_buf.iter().position(|&b| b == 0) {
            ansi_buf.truncate(null_pos);
        }

        CString::new(ansi_buf)
            .map_err(|e| format!("Failed to create CString from ANSI bytes: {}", e))
    }

    // 非Windows: UTF-8をそのまま使用（Linux/macOSはUTF-8パスをネイティブサポート）
    #[cfg(not(target_os = "windows"))]
    {
        CString::new(path)
            .map_err(|e| format!("Failed to convert path to CString: {}", e))
    }
}

// OpenDRIVE 車線タイプ定数
const LANE_TYPE_SHOULDER: c_int = 3;
const LANE_TYPE_SIDEWALK: c_int = 5;
const LANE_TYPE_BORDER: c_int = 6;

// esminiRMLib (RoadManager) C API のFFI定義
// OpenDRIVEファイルを直接読み込む軽量なライブラリ
#[link(name = "esminiRMLib")]
extern "C" {
    fn RM_Init(odr_filename: *const c_char) -> c_int;
    fn RM_Close() -> c_int;
    fn RM_GetNumberOfRoads() -> c_int;
    fn RM_GetIdOfRoadFromIndex(index: c_uint) -> c_uint;
    fn RM_GetRoadLength(id: c_uint) -> c_float;
    fn RM_GetRoadNumberOfLanes(road_id: c_uint, s: c_float, type_mask: c_int) -> c_int;
    fn RM_GetLaneIdByIndex(road_id: c_uint, lane_index: c_int, s: c_float, type_mask: c_int, lane_id: *mut c_int) -> c_int;

    // Position object API
    fn RM_CreatePosition() -> c_int;
    fn RM_DeletePosition(handle: c_int) -> c_int;
    fn RM_SetLanePosition(handle: c_int, road_id: c_uint, lane_id: c_int, lane_offset: c_float, s: c_float, align: bool) -> c_int;
    fn RM_GetPositionData(handle: c_int, data: *mut RM_PositionData) -> c_int;
    fn RM_GetLaneType(road_id: c_uint, lane_id: c_int, s: c_float) -> c_int;
}

// RoadManager Position Data 構造体
#[repr(C)]
struct RM_PositionData {
    x: c_float,
    y: c_float,
    z: c_float,
    h: c_float,
    p: c_float,
    r: c_float,
    h_relative: c_float,
    road_id: c_uint,
    junction_id: c_uint,
    lane_id: c_int,
    lane_offset: c_float,
    s: c_float,
}

/// 道路の点データ
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoadPoint {
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub heading: f32,
    pub s: f32,
}

/// 車線データ
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LaneData {
    pub road_id: i32,
    pub lane_id: i32,
    pub points: Vec<RoadPoint>,
}

/// 道路ネットワークデータ
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoadNetworkData {
    pub roads: Vec<RoadData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoadData {
    pub road_id: i32,
    pub length: f32,
    pub lanes: Vec<LaneData>,
}

/// OpenDRIVEファイルから道路ネットワークデータを取得
///
/// 注意: esminiRMLibはログファイル(esminiRM_log.txt)を自動生成しますが、
/// 軽量版のためログ制御APIが提供されていません。
pub fn load_opendrive_with_esmini(xodr_path: &str) -> Result<RoadNetworkData, String> {
    // RoadManagerを初期化（日本語パス対応）
    let c_path = path_to_cstring(xodr_path)?;

    let result = unsafe { RM_Init(c_path.as_ptr()) };
    if result != 0 {
        return Err(format!("RM_Init failed with code: {}", result));
    }

    // 道路数を取得
    let num_roads = unsafe { RM_GetNumberOfRoads() };

    if num_roads <= 0 {
        unsafe { RM_Close() };
        return Err("No roads found in OpenDRIVE file".to_string());
    }

    let mut roads = Vec::new();

    // 各道路の情報を取得
    for road_idx in 0..num_roads as u32 {
        let road_id = unsafe { RM_GetIdOfRoadFromIndex(road_idx) };
        let road_length = unsafe { RM_GetRoadLength(road_id) };

        let mut lanes = Vec::new();

        // 道路の開始地点で車線数を取得（type_mask = -1 は全車線タイプ）
        let num_lanes = unsafe { RM_GetRoadNumberOfLanes(road_id, 0.0, -1) };

        for lane_idx in 0..num_lanes {
            let mut lane_id: c_int = 0;
            let result = unsafe { RM_GetLaneIdByIndex(road_id, lane_idx, 0.0, -1, &mut lane_id) };

            if result != 0 {
                continue; // このlaneはスキップ
            }

            // 車線タイプを取得して、shoulder、border、sidewalkを除外
            let lane_type = unsafe { RM_GetLaneType(road_id, lane_id, 0.0) };
            if lane_type == LANE_TYPE_SHOULDER || lane_type == LANE_TYPE_BORDER || lane_type == LANE_TYPE_SIDEWALK {
                continue; // 路肩、縁石、歩道はスキップ
            }

            // 車線中心線を1mステップでサンプリング
            let step = 1.0;
            let mut points = Vec::new();
            let mut s = 0.0;

            while s <= road_length {
                // Position objectを作成
                let pos_handle = unsafe { RM_CreatePosition() };
                if pos_handle < 0 {
                    break;
                }

                // Lane positionを設定
                let set_result = unsafe {
                    RM_SetLanePosition(pos_handle, road_id, lane_id, 0.0, s, true)
                };

                if set_result >= 0 {
                    // Position dataを取得
                    let mut pos_data = RM_PositionData {
                        x: 0.0, y: 0.0, z: 0.0,
                        h: 0.0, p: 0.0, r: 0.0,
                        h_relative: 0.0,
                        road_id: 0,
                        junction_id: 0,
                        lane_id: 0,
                        lane_offset: 0.0,
                        s: 0.0,
                    };

                    let get_result = unsafe { RM_GetPositionData(pos_handle, &mut pos_data) };
                    if get_result == 0 {
                        points.push(RoadPoint {
                            x: pos_data.x,
                            y: pos_data.y,
                            z: pos_data.z,
                            heading: pos_data.h,
                            s,
                        });
                    }
                }

                unsafe { RM_DeletePosition(pos_handle) };
                s += step;
            }

            if !points.is_empty() {
                lanes.push(LaneData {
                    road_id: road_id as i32,
                    lane_id,
                    points,
                });
            }
        }

        roads.push(RoadData {
            road_id: road_id as i32,
            length: road_length,
            lanes,
        });
    }

    // RoadManagerをクリーンアップ
    unsafe { RM_Close() };

    Ok(RoadNetworkData { roads })
}
