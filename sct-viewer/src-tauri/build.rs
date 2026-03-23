use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    // Tauriのビルド処理
    tauri_build::build();

    // esminiLibのセットアップ
    setup_esmini();

    // NOTE: sct-coreのprebuiltエクスポートはbuild.rsから削除
    // build.rs内でcargo buildを呼ぶとCargoロックのデッドロックが発生するため、
    // npm scriptの post-build ステップで実行する
}

fn setup_esmini() {
    // CARGO_MANIFEST_DIR は src-tauri ディレクトリを指す
    // esmini はプロジェクトルートにあるため、../esmini を使用
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());

    // 環境変数がなければデフォルトパスを使用
    let esmini_path = if let Ok(path) = env::var("ESMINI_LIB") {
        PathBuf::from(path)
    } else {
        manifest_dir.parent().unwrap().join("esmini")
    };

    // esminiディレクトリの存在チェック
    if !esmini_path.exists() {
        panic!(
            "\n\n❌ ERROR: esminiディレクトリが見つかりません！\n\
            パス: {:?}\n\n\
            セットアップ手順：\n\
            1. esminiをダウンロード: https://github.com/esmini/esmini/releases\n\
            2. プロジェクトルートに展開してください\n\
            または、ESMINI_LIB環境変数でパスを指定してください。\n\n",
            esmini_path
        );
    }

    let esmini_path_str = esmini_path.to_str().unwrap();
    println!("cargo:warning=esmini path: {}", esmini_path_str);
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed={}", esmini_path_str);

    // ライブラリサーチパスを追加
    let bin_path = esmini_path.join("bin");
    let lib_path = esmini_path.join("lib");

    println!("cargo:rustc-link-search=native={}", bin_path.to_str().unwrap());
    println!("cargo:rustc-link-search=native={}", lib_path.to_str().unwrap());

    // RoadManager APIを使用（OpenDRIVEのみを扱う軽量版）
    println!("cargo:rustc-link-lib=dylib=esminiRMLib");

    // OS固有の設定
    #[cfg(target_os = "macos")]
    setup_macos(&bin_path, &manifest_dir);

    #[cfg(target_os = "windows")]
    setup_windows(&bin_path, &manifest_dir);

    #[cfg(target_os = "linux")]
    setup_linux(&bin_path, &manifest_dir);
}

/// OUT_DIRからtarget/<profile>ディレクトリを逆算する（workspace構成対応）
fn resolve_target_profile_dir(manifest_dir: &PathBuf) -> PathBuf {
    let profile = env::var("PROFILE").unwrap_or_else(|_| "debug".to_string());
    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    out_dir
        .ancestors()
        .find(|p| p.ends_with(&profile))
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            env::var("CARGO_TARGET_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|_| manifest_dir.join("target"))
                .join(&profile)
        })
}

/// vehicle_bbox.jsonをtarget/<profile>にコピーする
fn copy_vehicle_bbox(manifest_dir: &PathBuf, target_profile_dir: &PathBuf) {
    let bbox_src = manifest_dir.parent().unwrap().join("docs").join("vehicle_bbox.json");
    let bbox_dst = target_profile_dir.join("vehicle_bbox.json");

    if bbox_src.exists() {
        if let Err(e) = fs::copy(&bbox_src, &bbox_dst) {
            println!("cargo:warning=⚠️ vehicle_bbox.json のコピーに失敗: {}", e);
        } else {
            println!("cargo:warning=✅ vehicle_bbox.json copied to {:?}", bbox_dst);
        }
    } else {
        println!("cargo:warning=⚠️ vehicle_bbox.json が見つかりません: {:?}", bbox_src);
    }
}

#[cfg(target_os = "macos")]
fn setup_macos(bin_path: &PathBuf, manifest_dir: &PathBuf) {
    // macOSでは実行時のライブラリ検索パスを設定
    println!("cargo:rustc-link-arg=-Wl,-rpath,{}", bin_path.to_str().unwrap());

    let dylibs = vec!["libesminiLib.dylib", "libesminiRMLib.dylib"];

    // dylibの存在確認
    for dylib_name in &dylibs {
        let dylib_path = bin_path.join(dylib_name);
        if !dylib_path.exists() {
            panic!(
                "\n\n❌ ERROR: {} が見つかりません！\n\
                パス: {:?}\n\n\
                esmini/bin/ ディレクトリに以下のファイルが必要です：\n\
                - libesminiLib.dylib\n\
                - libesminiRMLib.dylib\n\n\
                macOS版のesminiをダウンロード・展開してください。\n\n",
                dylib_name, dylib_path
            );
        }
        println!("cargo:warning=✅ {} found at {:?}", dylib_name, dylib_path);
    }

    // dylibとvehicle_bbox.jsonをtarget/<profile>にコピー
    let target_profile_dir = resolve_target_profile_dir(manifest_dir);
    println!("cargo:warning=📁 Copying dylibs and resources to {:?}", target_profile_dir);

    for dylib_name in &dylibs {
        let src = bin_path.join(dylib_name);
        let dst = target_profile_dir.join(dylib_name);
        if let Some(parent) = dst.parent() {
            fs::create_dir_all(parent).ok();
        }
        if let Err(e) = fs::copy(&src, &dst) {
            println!("cargo:warning=⚠️ {} のコピーに失敗: {}", dylib_name, e);
        } else {
            println!("cargo:warning=✅ {} copied to {:?}", dylib_name, dst);
        }
    }

    copy_vehicle_bbox(manifest_dir, &target_profile_dir);
}

#[cfg(target_os = "windows")]
fn setup_windows(bin_path: &PathBuf, manifest_dir: &PathBuf) {
    let dlls_to_copy = vec!["esminiLib.dll", "esminiRMLib.dll"];

    // DLLの存在チェック
    for dll_name in &dlls_to_copy {
        let dll_src = bin_path.join(dll_name);
        if !dll_src.exists() {
            panic!(
                "\n\n❌ ERROR: {} が見つかりません！\n\
                パス: {:?}\n\n\
                esmini/bin/ ディレクトリに以下のファイルが必要です：\n\
                - esminiLib.dll\n\
                - esminiRMLib.dll\n\n\
                esminiを正しくダウンロード・展開してください。\n\n",
                dll_name, dll_src
            );
        }
        println!("cargo:warning=✅ {} found at {:?}", dll_name, dll_src);
    }

    // DLLとvehicle_bbox.jsonをtarget/<profile>にコピー
    let target_profile_dir = resolve_target_profile_dir(manifest_dir);
    println!("cargo:warning=📁 Copying DLLs and resources to {:?}", target_profile_dir);

    for dll_name in &dlls_to_copy {
        let src = bin_path.join(dll_name);
        let dst = target_profile_dir.join(dll_name);
        if let Some(parent) = dst.parent() {
            fs::create_dir_all(parent).ok();
        }
        if let Err(e) = fs::copy(&src, &dst) {
            panic!(
                "\n\n❌ ERROR: {} のコピーに失敗しました！\n\
                エラー: {}\n\
                コピー元: {:?}\n\
                コピー先: {:?}\n\n",
                dll_name, e, src, dst
            );
        } else {
            println!("cargo:warning=✅ {} copied to {:?}", dll_name, dst);
        }
    }

    copy_vehicle_bbox(manifest_dir, &target_profile_dir);
}

#[cfg(target_os = "linux")]
fn setup_linux(bin_path: &PathBuf, manifest_dir: &PathBuf) {
    // Linuxでは実行時のライブラリ検索パスを設定
    println!("cargo:rustc-link-arg=-Wl,-rpath,{}", bin_path.to_str().unwrap());

    let so_files = vec!["libesminiLib.so", "libesminiRMLib.so"];

    // .soファイルの存在確認
    for so_name in &so_files {
        let so_path = bin_path.join(so_name);
        if !so_path.exists() {
            panic!(
                "\n\n❌ ERROR: {} が見つかりません！\n\
                パス: {:?}\n\n\
                esmini/bin/ ディレクトリに以下のファイルが必要です：\n\
                - libesminiLib.so\n\
                - libesminiRMLib.so\n\n\
                Linux版のesminiをダウンロード・展開してください。\n\n",
                so_name, so_path
            );
        }
        println!("cargo:warning=✅ {} found at {:?}", so_name, so_path);
    }

    // .soとvehicle_bbox.jsonをtarget/<profile>にコピー
    let target_profile_dir = resolve_target_profile_dir(manifest_dir);
    println!("cargo:warning=📁 Copying .so files and resources to {:?}", target_profile_dir);

    for so_name in &so_files {
        let src = bin_path.join(so_name);
        let dst = target_profile_dir.join(so_name);
        if let Some(parent) = dst.parent() {
            fs::create_dir_all(parent).ok();
        }
        if let Err(e) = fs::copy(&src, &dst) {
            println!("cargo:warning=⚠️ {} のコピーに失敗: {}", so_name, e);
        } else {
            println!("cargo:warning=✅ {} copied to {:?}", so_name, dst);
        }
    }

    copy_vehicle_bbox(manifest_dir, &target_profile_dir);
}

