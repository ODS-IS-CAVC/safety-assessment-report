"""
esminiライブラリの検索・出力抑制ユーティリティ

try_tools/shared/esmini_utils.py ベース。
ESMINI_LIB_PATH環境変数と try_tools フォールバックパスを追加。
"""
import contextlib
import os
import platform
import sys
from typing import Optional


def find_esmini_lib(lib_name: Optional[str] = None) -> Optional[str]:
    """esminiライブラリを探す

    Args:
        lib_name: ライブラリファイル名。Noneの場合はプラットフォームに応じた
                  RoadManagerライブラリ名を使用。

    Returns:
        ライブラリの絶対パス。見つからない場合はNone。
    """
    if lib_name is None:
        system = platform.system()
        if system == "Darwin":
            lib_name = "libesminiRMLib.dylib"
        elif system == "Windows":
            lib_name = "esminiRMLib.dll"
        else:
            lib_name = "libesminiRMLib.so"

    # 呼び出し元スクリプトのディレクトリを基準に探索
    try:
        caller_file = sys._getframe(1).f_globals.get('__file__', '')
        caller_dir = os.path.dirname(os.path.abspath(caller_file)) if caller_file else os.getcwd()
    except (AttributeError, ValueError):
        caller_dir = os.getcwd()

    candidates = []

    # ESMINI_LIB_PATH 環境変数（直接ライブラリファイルを指す）
    esmini_lib_path = os.environ.get('ESMINI_LIB_PATH')
    if esmini_lib_path:
        candidates.append(esmini_lib_path)

    # ESMINI_PATH 環境変数（esminiルートディレクトリ）
    esmini_path = os.environ.get('ESMINI_PATH')
    if esmini_path:
        candidates.append(os.path.join(esmini_path, 'bin', lib_name))

    # 呼び出し元基準の探索パス
    candidates.extend([
        os.path.join(caller_dir, '..', 'esmini', 'bin', lib_name),
        os.path.join(caller_dir, 'esmini', 'bin', lib_name),
        os.path.join(caller_dir, '..', '..', 'esmini', 'bin', lib_name),
        os.path.join(os.getcwd(), 'esmini', 'bin', lib_name),
    ])

    # try_tools フォールバック
    candidates.append(
        os.path.join('/workspace', 'try_tools', 'esmini', 'bin', lib_name)
    )

    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path

    return None


@contextlib.contextmanager
def suppress_esmini_output():
    """esminiライブラリからの出力（stdout/stderr両方）を抑制するコンテキストマネージャ"""
    sys.stdout.flush()
    sys.stderr.flush()

    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)

    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(devnull)
        os.close(old_stdout)
        os.close(old_stderr)
