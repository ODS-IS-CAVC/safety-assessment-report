# 安全性評価フレームワーク原案 関連ツール

## 1. 説明

本リポジトリは、NEDO（New Energy and Industrial Technology Development Organization）の公募案件にて、実証実験に向けて作成したものです。
リポジトリ内には、以下のアプリを格納しています。

1. **SCT Viewer**： SCT（Safety Cushion Time）算出・可視化ツール。OpenDRIVE形式の道路データと車両軌跡CSVから、車両間の相対距離・相対速度を計算し、SCT（安全余裕時間）を算出・可視化するデスクトップアプリケーション（詳細は[**README**](sct-viewer)を参照ください。）
2. **ニアミス発生情報表示マップ**：車載ログデータとExcel管理データから、ニアミスインシデントを自動集計・可視化するWindows向けワンクリック解析パイプラインです。進捗管理データから対象のcar_week識別子を抽出し、ネットワーク共有上の車載ログを走査して走行距離・走行時間を集計したうえで、Leaflet.jsベースのインタラクティブHTMLマップとして出力します（詳細は[README](https://github.com/ODS-IS-CAVC/safety-assessment-report/tree/main/near_miss_map)を参照ください。）

## 2. 問い合わせ・要望の対応

本リポジトリに掲載しているソフトウェアは、アーカイブモードで提供しております。
公開しているアプリケーションおよびプログラムに関するお問い合わせや要望は受付できかねますので、ご留意ください。

## 3. ライセンス

1. **SCT Viewer**： Apache License, Version 2.0
