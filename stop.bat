@echo off
rem Stops Junior Muneer (the backend on port 8000 and the dashboard on port 3000).
powershell -NoProfile -Command "foreach ($port in 8000, 3000) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
taskkill /fi "WINDOWTITLE eq Junior Muneer - backend*" /t /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Junior Muneer - dashboard*" /t /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Junior Muneer - WhatsApp tunnel*" /t /f >nul 2>nul
taskkill /im ngrok.exe /f >nul 2>nul
echo Junior Muneer stopped.
