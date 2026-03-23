# Windows環境でのビルド手順

## 重要な前提

⚠️ **このプロジェクトの開発環境構成**
- **WSL2 (Ubuntu)**: Claude Codeによるコード編集とGit管理
- **Windows**: 実際のビルドとアプリケーション実行

**理由**: Claude CodeはWindows環境では動作しないため、コード編集はWSL、ビルドはWindowsで分離して実施

## 初回セットアップ

### 1. プロジェクトのクローン（Windows側）

```cmd
# Gitがインストールされていることを確認
git --version

# プロジェクトをクローン（または既存のWSLディレクトリを参照）
# 方法A: Windows側で新規クローン
git clone <repository-url> C:\path\to\sct_tool

# 方法B: WSLのディレクトリを直接参照（推奨）
# WSLパス: \\wsl$\Ubuntu\mnt\efs\sct_tool
```

### 2. Node.jsのインストール

```cmd
# Node.js v18以上をインストール
# https://nodejs.org/

node --version
npm --version
```

### 3. Rustのインストール

```cmd
# Rust公式インストーラーを使用
# https://www.rust-lang.org/tools/install

rustc --version
cargo --version
```

### 4. 依存関係のインストール

```cmd
cd C:\path\to\sct_tool

# npmパッケージのインストール
npm install

# Cargo依存関係のビルド（初回のみ時間がかかる）
cd src-tauri
cargo build
cd ..
```

### 5. esminiのセットアップ

```cmd
# 方法A: WSLからコピー
# WSLパス: \\wsl$\Ubuntu\mnt\efs\sct_tool\esmini
xcopy "\\wsl$\Ubuntu\mnt\efs\sct_tool\esmini" ".\esmini" /E /I

# 方法B: 直接ダウンロード
# https://github.com/esmini/esmini/releases/download/v2.53.0/esmini-bin_Windows.zip
# ダウンロード後、プロジェクトルートに展開

# DLLをターゲットディレクトリにコピー
copy esmini\bin\esminiLib.dll src-tauri\target\debug\
```

## ビルドコマンド

### 開発モード

```cmd
npm run tauri dev
```

**重要**: 初回起動時は自動的に `src-tauri/target/debug/` にexeとesminiLib.dllが配置されます。

### リリースビルド

```cmd
npm run tauri build
```

ビルド成果物:
- `src-tauri/target/release/sct-tool.exe`
- `src-tauri/target/release/bundle/` - インストーラー

**リリースビルド前に**:
```cmd
copy esmini\bin\esminiLib.dll src-tauri\target\release\
```

## トラブルシューティング

### esminiLib.dllが見つからないエラー

```
Error: The specified module could not be found. (os error 126)
```

**解決方法**:
```cmd
# DLLをexeと同じディレクトリにコピー
copy esmini\bin\esminiLib.dll src-tauri\target\debug\
```

### ビルドエラー: cargo metadata failed

**原因**: Rustがインストールされていない、またはPATHが通っていない

**解決方法**:
```cmd
# 環境変数PATHを確認
echo %PATH%

# Rustを再インストール
# https://www.rust-lang.org/tools/install
```

### npm install エラー

**解決方法**:
```cmd
# キャッシュをクリア
npm cache clean --force

# node_modulesを削除して再インストール
rmdir /s /q node_modules
npm install
```

## WSLとWindows間のファイル同期

### WSL → Windows

```cmd
# WSLのプロジェクトディレクトリを直接参照
cd \\wsl$\Ubuntu\mnt\efs\sct_tool
```

**または** WSL側でGit commitした後、Windows側でpull:

```cmd
# Windows側
git pull origin main
```

### Windows → WSL

Windows側でコードを編集した場合は、WSL側でpull:

```bash
# WSL側
git pull origin main
```

## 開発ワークフロー（推奨）

1. **WSL (Claude Code)**: コード編集
   ```bash
   # src-tauri/src/opendrive/esmini_ffi.rs など
   git add .
   git commit -m "FFIバインディング実装"
   git push
   ```

2. **Windows**: Git pull & ビルド
   ```cmd
   git pull
   npm run tauri dev
   ```

3. **Windows**: 動作確認とデバッグ

4. **WSL (Claude Code)**: 修正とドキュメント更新

5. 繰り返し

## 環境変数（オプション）

```cmd
# esminiのカスタムパスを指定する場合
set ESMINI_LIB=C:\custom\path\to\esmini

# 永続的に設定する場合（システム環境変数）
setx ESMINI_LIB "C:\custom\path\to\esmini"
```

## 参考情報

- Tauri Windows Setup: https://tauri.app/v1/guides/getting-started/prerequisites/#windows
- Rust Windows Setup: https://www.rust-lang.org/tools/install
- Node.js Windows: https://nodejs.org/en/download/
