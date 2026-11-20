@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is required but was not found.
  echo Install Node.js 20 or newer, then run this file again.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo Preparing the presentation for first use...
  call corepack pnpm install
  if errorlevel 1 goto :failed
)

echo Opening DUET / SPEAK at http://127.0.0.1:4173/
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:4173/#/s01-f0'"
call corepack pnpm dev --host 127.0.0.1 --port 4173
exit /b %errorlevel%

:failed
echo.
echo The presentation could not be prepared. See the message above.
pause
exit /b 1
