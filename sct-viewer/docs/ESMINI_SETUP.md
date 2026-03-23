# esmini セットアップガイド

このドキュメントでは、3つの環境（macOS、Windows、WSL2/Ubuntu）でesminiライブラリをセットアップする手順を説明します。

## 概要

esminiは、OpenDRIVE形式の道路データを高精度に解析するためのライブラリです。このプロジェクトでは、RoadManager APIを使用してOpenDRIVEファイルから車線情報を取得します。

## 環境別セットアップ

### 1. macOS

#### esminiのダウンロード

```bash
cd /path/to/sct_tool
curl -L -o /tmp/esmini-bin_macOS.zip https://github.com/esmini/esmini/releases/download/v2.54.0/esmini-bin_macOS.zip
unzip /tmp/esmini-bin_macOS.zip
```

#### ディレクトリ構造の確認

```bash
ls -la esmini/bin/
# 以下のファイルが存在することを確認：
# - libesminiLib.dylib
# - libesminiRMLib.dylib
```

#### ビルド

```bash
npm run tauri dev
# または
npm run tauri build
```

**注意**: macOSでは`rpath`が自動的に設定されるため、追加の設定は不要です。

---

### 2. Windows

#### esminiのダウンロード

```powershell
# PowerShellで実行
cd C:\path\to\sct_tool
Invoke-WebRequest -Uri "https://github.com/esmini/esmini/releases/download/v2.54.0/esmini-bin_Windows.zip" -OutFile "$env:TEMP\esmini-bin_Windows.zip"
Expand-Archive -Path "$env:TEMP\esmini-bin_Windows.zip" -DestinationPath .
```

#### ディレクトリ構造の確認

```powershell
dir esmini\bin\
# 以下のファイルが存在することを確認：
# - esminiLib.dll
# - esminiRMLib.dll
```

#### ビルド

```powershell
npm run tauri dev
# または
npm run tauri build
```

**注意**: Windowsでは、ビルド時に自動的にDLLが`target/debug/`または`target/release/`にコピーされます。

---

### 3. WSL2 (Ubuntu)

#### esminiのダウンロード

```bash
cd /path/to/sct_tool
wget https://github.com/esmini/esmini/releases/download/v2.54.0/esmini-bin_Linux.zip
unzip esmini-bin_Linux.zip
```

#### ディレクトリ構造の確認

```bash
ls -la esmini/bin/
# 以下のファイルが存在することを確認：
# - libesminiLib.so
# - libesminiRMLib.so
```

#### 依存関係のインストール

```bash
sudo apt-get update
sudo apt-get install -y \
  libwebkit2gtk-4.1-dev \
  build-essential \
  curl \
  wget \
  file \
  libssl-dev \
  libgtk-3-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev
```

#### ビルド

```bash
npm run tauri dev
# または
npm run tauri build
```

**注意**: WSL2では`rpath`が自動的に設定されますが、GUI表示にはX11サーバー（VcXsrv等）が必要です。

---

## トラブルシューティング

### ライブラリが見つからないエラー

#### macOS/Linux

```bash
# esminiディレクトリが正しい場所にあるか確認
ls -la esmini/bin/

# 環境変数で明示的にパスを指定
export ESMINI_LIB=/path/to/sct_tool/esmini
npm run tauri dev
```

#### Windows

```powershell
# esminiディレクトリが正しい場所にあるか確認
dir esmini\bin\

# 環境変数で明示的にパスを指定
$env:ESMINI_LIB="C:\path\to\sct_tool\esmini"
npm run tauri dev
```

### リンカーエラー

- **macOS**: Xcode Command Line Toolsがインストールされているか確認
  ```bash
  xcode-select --install
  ```

- **Windows**: Visual Studio Build Toolsがインストールされているか確認

- **Linux**: build-essentialがインストールされているか確認
  ```bash
  sudo apt-get install build-essential
  ```

### ビルド後の実行エラー

#### macOS

```bash
# Gatekeeperの警告が出る場合
xattr -r -d com.apple.quarantine esmini/bin/*.dylib
```

#### Windows

DLLが見つからない場合、手動でコピー：
```powershell
Copy-Item esmini\bin\*.dll src-tauri\target\debug\
```

#### Linux

```bash
# LD_LIBRARY_PATHを設定
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/esmini/bin
npm run tauri dev
```

---

## esminiのバージョン確認

```bash
cat esmini/version.txt
```

現在のバージョン: **v2.54.0**

---

## プロジェクト構造

```
sct_tool/
├── esmini/                    # esminiライブラリ（各環境で配置）
│   ├── bin/                   # 実行ファイル・ライブラリ
│   │   ├── libesminiLib.dylib # macOS
│   │   ├── libesminiRMLib.dylib
│   │   ├── esminiLib.dll      # Windows
│   │   ├── esminiRMLib.dll
│   │   ├── libesminiLib.so    # Linux
│   │   └── libesminiRMLib.so
│   └── version.txt
├── src-tauri/
│   ├── build.rs              # ビルド設定（3環境対応）
│   └── src/
│       └── opendrive/
│           └── esmini_ffi.rs # FFIバインディング
└── ...
```

---

## 参考リンク

- [esmini GitHub リポジトリ](https://github.com/esmini/esmini)
- [esmini ドキュメント](https://esmini.github.io/)
- [OpenDRIVE 仕様](https://www.asam.net/standards/detail/opendrive/)
