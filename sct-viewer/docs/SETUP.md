# セットアップガイド

このガイドでは、SCT算出ツールの開発環境をセットアップする手順を説明します。

## 前提条件

- Ubuntu / WSL2 (Linux)
- Node.js 18以上
- Rust 1.70以上

## セットアップ手順

### 1. Rustのインストール（完了✓）

Rustは既にインストール済みです。次回シェルを起動する際は自動的にパスが通ります。

現在のセッションでRustを使用するには：
```bash
source "$HOME/.cargo/env"
```

バージョン確認：
```bash
rustc --version  # rustc 1.90.0
cargo --version  # cargo 1.90.0
```

### 2. システム依存関係のインストール（要手動実行）

Tauri開発に必要なシステムライブラリをインストールしてください：

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

### 3. npm依存関係のインストール（完了✓）

```bash
npm install
```

## 開発の開始

### 環境変数の設定

**重要**: 新しいターミナルセッションを開くたびに、以下を実行してください：

```bash
source "$HOME/.cargo/env"
```

または、`.bashrc` または `.zshrc` に追加して永続化：
```bash
echo 'source "$HOME/.cargo/env"' >> ~/.bashrc
source ~/.bashrc
```

### 開発サーバーの起動

```bash
# Rustのパスを読み込む（必要な場合）
source "$HOME/.cargo/env"

# 開発モードで起動
npm run tauri:dev
```

### ビルド

```bash
# リリースビルド
npm run tauri:build

# 生成されるインストーラー
# - Windows: src-tauri/target/release/bundle/msi/
# - Linux: src-tauri/target/release/bundle/deb/
# - macOS: src-tauri/target/release/bundle/dmg/
```

## WSL2でのGUI表示（オプション）

WSL2でTauriアプリケーションのGUIを表示するには、X11サーバーが必要です：

### Windowsホスト側の設定

1. **VcXsrv**または**X410**をインストール
2. X11サーバーを起動

### WSL2側の設定

```bash
# .bashrcに追加
export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0
export LIBGL_ALWAYS_INDIRECT=1
```

## トラブルシューティング

### Cargoが見つからない

```bash
# パスを読み込む
source "$HOME/.cargo/env"

# 確認
which cargo
```

### webkit2gtk-4.1が見つからない

```bash
# libwebkit2gtk-4.1-devをインストール
sudo apt-get install -y libwebkit2gtk-4.1-dev

# 利用可能なバージョンを確認
apt-cache search libwebkit2gtk

# 4.1が利用できない場合は4.0を試す
sudo apt-get install -y libwebkit2gtk-4.0-dev
```

### ビルドエラー：リンカーエラー

```bash
# build-essentialをインストール
sudo apt-get install -y build-essential
```

## 次のステップ

セットアップが完了したら：
1. `npm run tauri:dev` で開発サーバーを起動
2. `src/` でフロントエンド開発
3. `src-tauri/src/` でバックエンド開発
4. [開発ガイド](CLAUDE.md) を参照
