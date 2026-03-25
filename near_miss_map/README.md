# ニアミス発生情報表示マップ

車載ログデータと Excel 管理データから、ニアミスインシデントを自動集計・可視化する  
Windows 向けワンクリック解析パイプラインです。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)](https://www.microsoft.com/windows)

---

## 概要

本パイプラインは以下の 5 ステップを順に自動実行します。

1. **car_week アローリスト生成** — 進捗管理データから対象の `car_week` 識別子一覧を抽出します。
2. **走行露出量スキャン** — ネットワーク共有上の車載ログ（CSV / TXT）を走査し、車両・car_week・道路ラベル単位の走行距離および走行時間を集計します。
3. **道路グループ別露出量集計** — 道路グループ分類（`route_group_main_v2`）に基づき、露出量データを道路カテゴリ単位で再集計します。
4. **ルートエクスポート** — 車両・car_week 単位の走行軌跡を GeoJSON 形式でエクスポートします。
5. **インタラクティブ HTML マップ生成** — [Leaflet.js](https://leafletjs.com/) ベースのリッチ UI マップ（チップパネル・フィルタ・サマリー表・露出量ダッシュボード）を単一 HTML ファイルとして出力します。

---

## 技術スタック

| カテゴリ | 使用技術 |
|---|---|
| 言語 | Python 3.9+ |
| データ処理 | [pandas](https://pandas.pydata.org/)、[NumPy](https://numpy.org/) |
| Excel 入出力 | [openpyxl](https://openpyxl.readthedocs.io/) |
| 測地計算 | [pyproj](https://pyproj4.github.io/pyproj/) (WGS84 楕円体) |
| HTTP クライアント | [requests](https://docs.python-requests.org/) |
| 地図 UI | [Leaflet.js](https://leafletjs.com/) |
| 道路名補完 | [OpenStreetMap Nominatim](https://nominatim.org/)、[Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) |
| ルートデータ | [GeoJSON](https://geojson.org/) |
| 自動化シェル | Windows PowerShell 5.1+ |

---

## 動作環境

| 項目 | 要件 |
|---|---|
| OS | Windows 10 / 11 |
| シェル | Windows PowerShell 5.1 以上 |
| Python | 3.9 以上（3.12 推奨） |
| ネットワーク | 車載ログが格納された共有ドライブ（UNC パス）へのアクセス |

依存パッケージは `requirements.txt` で管理されています。実行前に以下のコマンドでインストールしてください。

```powershell
python -m pip install -r requirements.txt
```

---

## リポジトリ構成

```
.
├── run_pipeline.bat                                    # ワンクリック起動スクリプト（BAT）
├── run_pipeline.ps1                                    # メイン PowerShell ランナー ★ 要設定
├── pipeline_config.txt                                 # 設定パラメータのテンプレート
├── generate_nearmiss_map_v67_richui_both_excels.py    # インタラクティブ HTML マップ生成
├── E1A_ab_dist_scan_v3_1_carweek_exposure.py          # 露出量スキャン・ルートエクスポート
├── make_allowlist_carweek_from_excel.py                # car_week アローリスト抽出
├── make_exposure_by_excel_routegroup_v1.py             # 道路グループ別露出量集計
└── requirements.txt                                    # Python 依存パッケージ一覧
```

---

## セットアップと実行手順

### 1. PowerShell ランナーを設定する

`run_pipeline.ps1` をテキストエディタで開き、以下の変数をご自身の環境に合わせて書き換えてください。

```powershell
# Python 実行ファイルのフルパス
$pythonExe = "C:\Path\To\python.exe"

# 車載ログが格納されたルートディレクトリ（UNC パス可）
$logsRoot = "\\YOUR_SERVER\share\mobility_logs"

# 進捗管理データ（car_week 一覧が含まれるファイル）
$jpExcel = ".\your_progress_data.xlsx"

# 全ポイント管理データ（道路グループ分類が含まれるファイル）
$legacyExcel = ".\your_allpoints_data.xlsx"
```

### 2. 入力データを配置する

以下のファイルをスクリプトと同じフォルダに配置してください。  
データファイルには個人・組織の機密情報が含まれるため、リポジトリには含まれていません。

| ファイル | 説明 |
|---|---|
| 進捗管理データ（`.xlsx`） | ニアミス抽出の進捗を管理するデータシート。`car_week` 識別子と座標情報を含む集計シートを使用します。 |
| 全ポイント管理データ（`.xlsx`） | 道路グループ分類済みの全観測ポイントを含むデータシート。`route_group_main_v2` 列による道路カテゴリ分類を使用します。 |

車載ログは以下のディレクトリ構造を想定しています。

```
<logsRoot>/
  <car_week>/
    csv/
      *.csv       # 車載ログ（緯度・経度・速度・タイムスタンプ）
      *.txt
```

### 3. パイプラインを実行する

エクスプローラーまたはコマンドラインから `run_pipeline.bat` をダブルクリックするだけで全ステップが自動実行されます。

```
run_pipeline.bat
```

PowerShell を直接使用する場合は以下を実行してください。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run_pipeline.ps1
```

---

## 出力ファイル

パイプライン実行後、`pipeline_out/` フォルダ以下に以下のファイルが生成されます。

| パス | 内容 |
|---|---|
| `pipeline_out/nearmiss_points_map.html` | インタラクティブ HTML マップ（ブラウザで直接開けます） |
| `pipeline_out/exposure_out/totals_by_carweek_label.csv` | car_week × 道路ラベル別の露出量集計 |
| `pipeline_out/exposure_out/exposure_by_roadgroup.csv` | 道路グループ別の露出量合計 |
| `pipeline_out/exposure_out/totals_overall.json` | 全体露出量サマリー（JSON） |
| `pipeline_out/routes_out/routes_by_carweek.geojson` | car_week 別の走行軌跡（GeoJSON） |
| `pipeline_out/_cache/` | ログマニフェスト・位置情報キャッシュ（再実行の高速化用） |

> **注意**: `pipeline_out/` 以下のファイルはすべて自動生成されます。バージョン管理への追加は不要です（`.gitignore` にて除外済み）。

---

## 道路名補完（OSM エンリッチメント）

座標情報は存在するが道路名が欠損しているレコードは、以下の優先順位でラベルを補完します。

1. `osm_label_cache.json` — ローカルに保存されたラベルキャッシュ
2. `osm_reverse_cache.json` — 逆ジオコーディング結果のキャッシュ
3. `osm_overpass_cache.json` — [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) 結果のキャッシュ
4. [Nominatim](https://nominatim.org/) / [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) へのライブリクエスト（`--osm-fetch-missing` 指定時のみ）

OSM のキャッシュファイルには組織内の位置情報が含まれる場合があるため、リポジトリには含めないでください（`.gitignore` にて除外済み）。

---

## セキュリティと公開前のチェックリスト

本リポジトリにはソースコードのみが含まれています。公開前に以下の点を必ずご確認ください。

- [x] Excel データファイル（`.xlsx`）がコミットされていないこと
- [x] `osm_*_cache.json` がコミットされていないこと
- [x] `run_pipeline.ps1` 内のサーバー IP・UNC パスがプレースホルダに置き換えられていること
- [x] `pipeline_out/` 以下の生成物がコミットされていないこと

---

## ライセンス

本プロジェクトは [Apache License 2.0](LICENSE) のもとで公開されています。

```
Copyright 2024 The Near-Miss Pipeline Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
