@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue; if (-not $listener) { $pythonExe = (Get-Command python).Source; Start-Process -FilePath $pythonExe -ArgumentList @('-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port','8501','--server.headless','true') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden }"
echo.
echo P2.2A da san sang.
echo Mo trinh duyet tich hop va vao:
echo http://127.0.0.1:8501/?mode=p22a
echo.
pause
