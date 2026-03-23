# esmini セットアップ完了

## 重要な注意事項

⚠️ **ビルド環境について**
- **Claude Code（WSL2/Ubuntu）**: コード編集、Git管理のみ
- **Windows環境**: ビルドとアプリケーション実行
- **理由**: Claude CodeはWindows環境では実行できないため

## 配置したファイル

✅ **esminiディレクトリ（WSL側）**: `./esmini/`
- bin/esminiLib.dll (15MB) - 実行時に必要な動的ライブラリ
- bin/esminiLib.lib (46KB) - リンク時に必要なインポートライブラリ
- EnvironmentSimulator/ - ヘッダーファイル等

✅ **開発環境用DLL（WSL側）**: `src-tauri/target/debug/esminiLib.dll`
- WSL側で自動コピー済み（参考用）
- **実際のビルドはWindows側で行うため、Windows側にもコピーが必要**

## 次のステップ

### Windows環境での作業

1. **esminiをWindows側にコピー**
   ```cmd
   # WSLのファイルシステムからWindowsにコピー
   # WSLパス: \\wsl$\Ubuntu\mnt\efs\sct_tool\esmini
   # Windowsパス: C:\path\to\sct_tool\esmini

   # または、esmini v2.53.0を直接Windowsにダウンロード
   # https://github.com/esmini/esmini/releases/tag/v2.53.0
   ```

2. **esminiLib.dllをターゲットディレクトリにコピー**
   ```cmd
   # 開発時
   copy esmini\bin\esminiLib.dll src-tauri\target\debug\

   # リリースビルド時
   copy esmini\bin\esminiLib.dll src-tauri\target\release\
   ```

3. **環境変数の設定（オプション）**
   ```cmd
   set ESMINI_LIB=C:\path\to\sct_tool\esmini
   ```

4. **ビルド実行**
   ```cmd
   npm run tauri dev
   # または
   npm run tauri build
   ```

### WSL環境での作業（Claude Code）

- コード編集とGit管理のみ
- FFIバインディングの実装（src-tauri/src/opendrive/esmini_ffi.rs）
- Tauriコマンドの実装
- ドキュメントの更新

## 環境変数（オプション）

デフォルトでは `../esmini` を参照します。
カスタムパスを使用する場合のみ設定：

```bash
# Windows
set ESMINI_LIB=C:\path\to\sct_tool\esmini

# WSL/Linux
export ESMINI_LIB=/mnt/efs/sct_tool/esmini
```

## 確認コマンド

```bash
# esminiディレクトリの確認
ls -lh esmini/bin/esminiLib.*

# 開発環境DLLの確認
ls -lh src-tauri/target/debug/esminiLib.dll

# バージョン確認
cat esmini/version.txt
```
