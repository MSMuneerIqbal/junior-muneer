@echo off
rem Stops Junior Muneer (the backend on port 8000 and the dashboard on port 3000).
pushd "%~dp0backend"
if exist ".venv\Scripts\python.exe" .venv\Scripts\python.exe -c "from junior.config import get_settings; p=get_settings().data_path/'updates'; (p/'stop').touch() if p.is_dir() else None" 2>nul
popd
ping -n 2 127.0.0.1 >nul
powershell -NoProfile -Command "foreach ($port in 8000, 3000) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
taskkill /fi "WINDOWTITLE eq Junior Muneer - backend*" /t /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Junior Muneer - dashboard*" /t /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Junior Muneer - WhatsApp tunnel*" /t /f >nul 2>nul
taskkill /im ngrok.exe /f >nul 2>nul
echo Junior Muneer stopped.
