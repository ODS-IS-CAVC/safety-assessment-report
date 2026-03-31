# dashcam-preprocessor

ドライブレコーダー動画の前処理を行うコンテナです。動画ファイルから画像を抽出し、レンズ歪み補正とYOLOv8による車両検出・セグメンテーションを実行します。

## ライセンス

AGPL-3.0（YOLOv8 / Ultralytics の依存によるもの）

## 処理概要

1. **PREPARE** - GPS/Gセンサーデータの変換、動画トリミング
2. **VIDEO_TO_IMAGE** - 動画からフレーム画像を抽出
3. **DISTORTION** - カメラレンズの歪み補正
4. **SEGMENTATION** - YOLOv8x-segによる車両検出・インスタンスセグメンテーション
5. **MAKE_SEG_MP4** - セグメンテーション結果の可視化動画生成

## 入力データ

```
/mnt/data/input/
├── front.mp4                  # 前方カメラ動画（必須）
├── rear.mp4                   # 後方カメラ動画（任意）
├── gsensor_gps_*.txt          # GPS/Gセンサーデータ（任意）
├── camera_intrinsics.json     # カメラ内部パラメータ（任意）
└── NearMiss_Info.json         # カメラ設定パラメータ（任意）
```

## 出力データ

```
/mnt/data/intermediate/image/
├── src/{front,rear}/              # 抽出画像
├── distortion/{front,rear}/       # 歪み補正済み画像
└── segmentation/{front,rear}/
    ├── segmentation_results.json  # 検出結果（BBox, マスク, トラッキングID）
    ├── segmentation_cv.mp4        # 可視化動画
    └── *.jpg                      # セグメンテーション画像
```

## コンテナビルド

```bash
docker build -t dashcam-preprocessor .
```

### ビルド要件

- Docker 20.10以上
- ビルド時にインターネット接続が必要（Python 3.11のコンパイル、pipパッケージのインストール）
- ビルド時間: 約20〜30分（Python 3.11のソースビルドを含むため）

## 実行方法

```bash
# 基本実行
docker run -v /path/to/data:/mnt/data dashcam-preprocessor

# カメラ方向を指定
docker run -v /path/to/data:/mnt/data \
  -e CAMERA_DIRECTIONS="front rear" \
  dashcam-preprocessor

# フレームスキップ設定を変更
docker run -v /path/to/data:/mnt/data \
  -e FRAME_SKIP=2 \
  dashcam-preprocessor
```

## 環境変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `BASE_DIR` | `/mnt/data` | データディレクトリのパス |
| `CAMERA_DIRECTIONS` | `front rear` | 処理対象のカメラ方向 |
| `FRAME_SKIP` | `1` | フレーム抽出間隔 |

## 後段処理との連携

本コンテナの出力は **sim-generation-app** コンテナの入力となります。同じ `BASE_DIR` を共有することで、前段の出力をそのまま後段が読み込みます。

```bash
# 1. 前段処理
docker run -v /path/to/data:/mnt/data dashcam-preprocessor

# 2. 後段処理
docker run -v /path/to/data:/mnt/data sim-generation-app
```
