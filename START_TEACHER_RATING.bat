@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue; if (-not $listener) { $pythonExe = (Get-Command python -ErrorAction Stop).Source; Start-Process -FilePath $pythonExe -ArgumentList @('-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden; Start-Sleep -Seconds 2 }"

start "" "http://127.0.0.1:8501/?mode=teacher"
echo Teacher Rating - P2.2A is ready.
echo Progress is saved after every Save ^& Next.
endlocal
