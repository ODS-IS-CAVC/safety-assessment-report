# sim-generation-app

ドライブレコーダー動画の解析結果から、距離推定・車線検出・軌跡計算・安全指標（SCT/TTC）の算出を行うコンテナです。オプションでOpenSCENARIO形式のシナリオ生成も実行できます。

## ライセンス

Apache-2.0

## 処理概要

| Step | 処理 | 説明 |
|------|------|------|
| 1+2 | 距離推定 & 車線検出 | 並列実行。セグメンテーション結果から3D距離を推定、HybridNetsで車線検出 |
| 3 | 車線付き距離推定 | 車線位置を考慮した距離の再推定 |
| 4 | 画像抽出 | セグメンテーション動画からフレームを抽出 |
| 5 | 自車データ構築 | GPS/Gセンサーデータとの統合 |
| 6 | 自車-車線距離算出 | 自車両と車線境界との距離計算 |
| 7 | SCT/TTC計算 | Safety Cushion Time / Time-To-Collision の算出 |
| 8 | シナリオ生成（オプション） | 平滑化→軌跡生成→OpenSCENARIO出力 |

## 前提条件

**dashcam-preprocessor** コンテナによる前処理が完了していること。

## 入力データ

dashcam-preprocessorの出力がそのまま入力となります：

```
/mnt/data/
├── input/
│   ├── NearMiss_Info.json             # カメラパラメータ
│   └── gsensor_gps_*.txt              # GPS/Gセンサーデータ
├── image_distortion/{front,rear}/     # 歪み補正済み画像
└── segmentation/{front,rear}/
    ├── segmentation_results.json      # 検出結果
    └── segmentation_cv.mp4            # 可視化動画
```

## 出力データ

```
/mnt/data/
├── lane/{front,rear}/                 # 車線検出結果
│   └── lane_detection_results.json
├── lane/{front,rear}_lane.mp4         # 車線可視化動画
├── trajectory/
│   ├── ego.csv                        # 自車両データ（センサー統合済み）
│   ├── front_lane.csv                 # 前方車線位置
│   ├── rear_lane.csv                  # 後方車線位置
│   └── trajectory_f*.csv             # 車両ごとの軌跡・SCT/TTC
│
│  # 以下 --enable-scenario 指定時のみ
├── job/scenario/                      # シナリオ生成結果
├── job/sdmg/                          # SDMG形式シナリオ
├── job/xosc/scenario.xosc            # OpenSCENARIO
├── summary/trajectory_summary.json    # 軌跡サマリー
├── summary/summary_video.mp4          # サマリー動画
└── plot/                              # 軌跡プロット画像
```

## コンテナビルド

```bash
docker build -t sim-generation-app .
```

### ビルド要件

- Docker 20.10以上
- ビルド時にインターネット接続が必要（HybridNetsリポジトリのclone、重みファイルのダウンロード）
- マルチステージビルド: Stage 1でsct.soをコンパイル、Stage 2で実行環境を構築

### ビルドの流れ

1. **Stage 1 (sct-builder)**: Cythonで`trajectory/sct.py`をコンパイルし`.so`を生成
2. **Stage 2 (runtime)**: Python依存パッケージをインストール、HybridNetsをclone、アプリケーションコードをコピー、`.so`のみを配置

## 実行方法

```bash
# 基本実行（SCT/TTC計算まで）
docker run -v /path/to/data:/mnt/data sim-generation-app

# 自車両IDとFPSを指定
docker run -v /path/to/data:/mnt/data sim-generation-app \
  --ego-id 01 --fps 15

# シナリオ生成を有効化
docker run -v /path/to/data:/mnt/data \
  -e MAP_DATA_PATH=/path/to/map_data \
  sim-generation-app \
  --enable-scenario --videos-fps 30

# 軌跡延長を有効化したシナリオ生成
docker run -v /path/to/data:/mnt/data \
  -e MAP_DATA_PATH=/path/to/map_data \
  sim-generation-app \
  --enable-scenario --extend-trajectory --videos-fps 30
```

## 環境変数・引数

### 環境変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `BASE_DIR` | `/mnt/data` | データディレクトリのパス |
| `MAP_DATA_PATH` | なし | マップデータのパス（シナリオ生成時に必要） |

### コマンドライン引数

| 引数 | デフォルト | 説明 |
|------|-----------|------|
| `--base-dir` | 環境変数`BASE_DIR` | データディレクトリのパス |
| `--ego-id` | `01` | 自車両ID（egospec.csvに対応） |
| `--frame-step` | `2` | フレーム抽出間隔 |
| `--fps` | `15` | 処理FPS |
| `--enable-scenario` | `false` | シナリオ生成を有効化 |
| `--map-data-path` | 環境変数`MAP_DATA_PATH` | マップデータのパス |
| `--videos-fps` | `30` | 元動画のFPS（シナリオ生成用） |
| `--extend-trajectory` | `false` | 他車両軌跡のOpenDRIVE上での延長 |
