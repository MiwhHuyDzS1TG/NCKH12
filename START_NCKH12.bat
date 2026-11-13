@echo off
setlocal
chcp 65001 >nul
title NCKH12 Speaking Coach - Backend
cd /d "%~dp0"

if /I "%~1"=="--no-browser" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_nckh12.ps1" -NoBrowser
  if errorlevel 1 (
    echo.
    echo NCKH12 could not start. Read the error above.
    echo No unrelated process was stopped.
    pause
    exit /b 1
  )
  exit /b 0
)

rem The short bootstrap window exits immediately. One clearly titled PowerShell
rem terminal remains visible for backend activity and Ctrl+C shutdown.
start "NCKH12 Speaking Coach - Backend" powershell -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\start_nckh12.ps1"

endlocal
