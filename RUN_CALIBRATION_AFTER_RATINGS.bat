@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "NO_PAUSE="
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"

echo Checking all 12 teacher ratings before calibration...
python -m speaking_evidence.post_rating
set "TASK_EXIT=%ERRORLEVEL%"

if not "%TASK_EXIT%"=="0" (
  echo.
  echo Calibration was safely stopped. Read the reason above; no score was created.
) else (
  echo.
  echo Calibration finished. Starting the local result page...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_teacher_rating.ps1" -NoBrowser
  if errorlevel 1 (
    echo Calibration artifacts are safe, but the result page could not be started.
    pause
    exit /b 1
  )
  start "" "http://127.0.0.1:8501/?mode=p22result"
)

echo.
if not defined NO_PAUSE pause
exit /b %TASK_EXIT%
