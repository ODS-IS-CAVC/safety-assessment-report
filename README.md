# 安全性評価フレームワーク原案 関連ツール

## 1. 説明

本リポジトリは、NEDO（New Energy and Industrial Technology Development Organization）の公募案件にて、実証実験に向けて作成したものです。
リポジトリ内には、以下のアプリを格納しています。

1. **dashcam-preprocessor**：ドライブレコーダー動画の前処理コンテナ。動画ファイルから画像を抽出し、レンズ歪み補正とYOLOv8による車両検出・セグメンテーションを実行します（詳細は[README](dashcam-preprocessor)を参照ください。）
2. **sim-generation-app**：距離推定・車線検出・軌跡計算・安全指標（SCT/TTC）算出コンテナ。dashcam-preprocessorの出力を入力として、HybridNetsによる車線検出、車両間距離推定、SCT/TTC計算、およびOpenSCENARIOシナリオ生成を実行します（詳細は[README](sim-generation-app)を参照ください。）
3. **SCT Viewer**：SCT（Safety Cushion Time）算出・可視化ツール。OpenDRIVE形式の道路データと車両軌跡CSVから、車両間の相対距離・相対速度を計算し、SCT（安全余裕時間）を算出・可視化するデスクトップアプリケーションです（詳細は[README](sct-viewer)を参照ください。）
4. **ニアミス発生情報表示マップ**：車載ログデータとExcel管理データから、ニアミスインシデントを自動集計・可視化するWindows向けワンクリック解析パイプラインです（詳細は[README](near_miss_map)を参照ください。）

## 2. システム構成

```
ドラレコ動画
  → [dashcam-preprocessor]
    → 画像分解 → 歪み補正 → YOLO車両検出・セグメンテーション
  → [sim-generation-app]
    → 距離推定 → 車線検出 → 軌跡計算 → SCT/TTC算出
    → (オプション) シナリオ生成
  → [SCT Viewer]
    → 可視化・分析
```

dashcam-preprocessorとsim-generation-appは同一のデータディレクトリを共有し、前段の出力をそのまま後段が読み込みます。

## 3. 問い合わせ・要望の対応

本リポジトリに掲載しているソフトウェアは、アーカイブモードで提供しております。
公開しているアプリケーションおよびプログラムに関するお問い合わせや要望は受付できかねますので、ご留意ください。

## 4. ライセンス

| コンテナ/ツール | ライセンス | 備考 |
|---------------|-----------|------|
| dashcam-preprocessor | AGPL-3.0 | YOLOv8 (Ultralytics) 依存のため |
| sim-generation-app | Apache-2.0 | |
| SCT Viewer | Apache-2.0 | |
| ニアミス発生情報表示マップ | Apache-2.0 | |
