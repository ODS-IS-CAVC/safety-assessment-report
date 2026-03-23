# SCT Viewer

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**SCT（Safety Cushion Time）算出・可視化ツール**

OpenDRIVE形式の道路データと車両軌跡CSVから、車両間の相対距離・相対速度を計算し、SCT（安全余裕時間）を算出・可視化するデスクトップアプリケーションです。

![Tech Stack](https://img.shields.io/badge/Tauri-2.x-blue)
![Tech Stack](https://img.shields.io/badge/Rust-2021-orange)
![Tech Stack](https://img.shields.io/badge/React-TypeScript-blue)

## 主な機能

- **OpenDRIVE読み込み** - 道路ネットワーク（.xodr）の読み込みと上面図表示
- **車両軌跡の可視化** - CSV形式の軌跡データを読み込み、車両の動きをアニメーション再生
- **SCT自動計算** - 縦方向・横方向のSCTを自動算出し、時系列グラフで表示
- **SCB衝突判定** - Safety Cushion Buffer（SD/SCB1/SCB2/SCB3）によるニアミス判定
- **CSV出力** - 計算結果（相対位置・速度・SCT・SCB等）をCSVエクスポート
- **高速レンダリング** - Path2Dキャッシュ、空間フィルタリング、30FPS制限による最適化

## スクリーンショット

<!-- TODO: スクリーンショットを追加 -->

## クイックスタート

### 必要な環境

- [Node.js](https://nodejs.org/) v18以上
- [Rust](https://www.rust-lang.org/tools/install) 1.70以上
- npm
- [Tauri 2.x の前提条件](https://v2.tauri.app/start/prerequisites/)

### セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/ODS-IS-CAVC/safety-assessment-report.git
cd safety-assessment-report/sct-viewer

# 依存関係のインストール
npm install

# 開発モードで起動
npm run tauri:dev
```

### ビルド

```bash
# リリースビルド
npm run tauri:build
```

## 使い方

1. **OpenDRIVEファイルの読み込み** - メニュー「ファイル」→「OpenDRIVEを読み込む」で `.xodr` ファイルを選択
2. **自車両軌跡の読み込み** - メニュー「ファイル」→「自車両軌跡を読み込む」でCSVファイルを選択
3. **対象車両軌跡の読み込み** - メニュー「ファイル」→「対象車両軌跡を読み込む」でCSVファイルを選択
4. **SCT計算・可視化** - 自動的にSCTが計算され、グラフとアニメーションで表示

詳細な使い方は [docs/USAGE.md](docs/USAGE.md) を参照してください。

## 入力データ形式

### OpenDRIVE（.xodr）

ASAM OpenDRIVE 1.4 / 1.5 / 1.6 に対応しています。

### 車両軌跡CSV

**必須カラム：**

| カラム名 | 型 | 説明 |
|---------|------|------|
| `timestamp` | f64 | タイムスタンプ（秒） |
| `pos_x` | f64 | X座標（m） |
| `pos_y` | f64 | Y座標（m） |

**オプショナルカラム：**

| カラム名 | 型 | 説明 |
|---------|------|------|
| `yaw_rad` | f64 | ヨー角（rad）。未指定時は軌跡から進行方向を自動計算 |
| `vel_x` | f64 | X方向速度（m/s） |
| `vel_y` | f64 | Y方向速度（m/s） |

その他のカラム（`pos_z`, `pitch_rad`, `roll_rad` 等）は無視されます。

## プロジェクト構造

```
safety-assessment-report/
└── sct-viewer/
    ├── src/                    # フロントエンド（React + TypeScript）
    │   ├── components/         # Reactコンポーネント
    │   ├── types/              # TypeScript型定義
    │   └── utils/              # ユーティリティ
    ├── src-tauri/              # バックエンド（Rust）
    │   └── src/
    │       ├── opendrive/      # OpenDRIVE解析
    │       ├── trajectory/     # 軌跡データ処理
    │       └── commands/       # Tauriコマンド
    ├── sct-core/               # SCT計算エンジン
    │   ├── src/                # FFIラッパー・型定義
    │   └── prebuilt/           # プリビルドバイナリ（dll/dylib/so）
    └── docs/                   # ドキュメント
```

## ドキュメント

| ドキュメント | 説明 |
|------------|------|
| [docs/USAGE.md](docs/USAGE.md) | 使用方法マニュアル |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | 開発者向けオンボーディングガイド |
| [docs/SCT_calculation.md](docs/SCT_calculation.md) | SCT算出アルゴリズム仕様 |
| [docs/requirements_specification.md](docs/requirements_specification.md) | 要求仕様書 |
| [docs/SETUP.md](docs/SETUP.md) | 環境セットアップ手順 |
| [docs/WINDOWS_BUILD.md](docs/WINDOWS_BUILD.md) | Windowsビルド手順 |

## 技術スタック

| 領域 | 技術 |
|------|------|
| フレームワーク | Tauri 2.x |
| バックエンド | Rust（Edition 2021） |
| フロントエンド | React + TypeScript |
| UI | Material-UI + Tailwind CSS |
| グラフ | Chart.js |
| 2Dレンダリング | HTML5 Canvas |
| 状態管理 | Zustand |
| ビルドツール | Vite |

## 開発

```bash
# 開発モードで起動
npm run tauri:dev

# フロントエンドのみビルド
npm run build

# Rustバックエンドのテスト
cd src-tauri && cargo test

# リリースビルド
npm run tauri:build
```

### システム要件

- **OS**: Windows 10/11（64bit）、macOS、Linux
- **メモリ**: 4GB以上推奨
- **ディスク**: 500MB以上の空き容量

## コントリビューション

コントリビューションを歓迎します。

1. [safety-assessment-report](https://github.com/ODS-IS-CAVC/safety-assessment-report) リポジトリをFork
2. フィーチャーブランチを作成（`git checkout -b feat/my-feature`）
3. 変更をコミット（`git commit -m 'feat: 機能の説明'`）
4. ブランチをPush（`git push origin feat/my-feature`）
5. Pull Requestを作成

### コミットメッセージ規約

```
<type>: <description>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`

## ライセンス

このプロジェクトは [Apache License 2.0](LICENSE) の下で公開されています。

## 謝辞

- [Tauri](https://tauri.app/) - クロスプラットフォームデスクトップアプリケーションフレームワーク
- [ASAM OpenDRIVE](https://www.asam.net/standards/detail/opendrive/) - 道路ネットワーク記述標準
- [esmini](https://github.com/esmini/esmini) - OpenDRIVE/OpenSCENARIOシミュレーターライブラリ
