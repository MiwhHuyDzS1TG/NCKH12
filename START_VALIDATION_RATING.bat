@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "BROWSER_OPTION="
if /I "%~1"=="--no-browser" set "BROWSER_OPTION=-NoBrowser"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_validation_rating.ps1" %BROWSER_OPTION%
if errorlevel 1 (
  echo.
  echo Could not start Development Validation Rating. Read the reason above.
  pause
  exit /b 1
)

echo Development Validation Rating is ready.
echo Progress is saved after every Save ^& Next.
endlocal
