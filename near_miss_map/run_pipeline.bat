@echo off
REM Safe wrapper: call PowerShell runner so Japanese filenames work.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_pipeline.ps1"

echo.
echo Done. Press any key to close.
pause >nul
