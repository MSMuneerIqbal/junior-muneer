@echo off
rem Junior Muneer: double-click to start. The first run also sets everything up.
rem   start.bat            start and open the dashboard in your browser
rem   start.bat nobrowser  start without opening the browser
setlocal
set "ROOT=%~dp0"
title Junior Muneer

where python >nul 2>nul || (echo Python 3.13 is not installed. Get it from https://www.python.org & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js 22 is not installed. Get it from https://nodejs.org & pause & exit /b 1)

rem ---- first-run setup ----------------------------------------------------
if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo Setting up the backend, first run only. This takes a few minutes...
  python -m venv "%ROOT%backend\.venv" || goto :failed
  "%ROOT%backend\.venv\Scripts\python" -m pip install --upgrade pip -q
  "%ROOT%backend\.venv\Scripts\python" -m pip install -r "%ROOT%backend\requirements.txt" -q || goto :failed
)
if not exist "%ROOT%frontend\node_modules" (
  echo Setting up the dashboard, first run only. This takes a few minutes...
  pushd "%ROOT%frontend" && call npm install --no-audit --no-fund || (popd & goto :failed)
  popd
)
if not exist "%ROOT%backend\.env" (
  copy "%ROOT%backend\.env.example" "%ROOT%backend\.env" >nul
  echo.
  echo Created backend\.env. Open it and paste your OpenAI key after OPENAI_API_KEY=
  echo ^(Or set FAKE_AI=true there to try the dashboard without a key.^)
  echo.
)

rem ---- start ----------------------------------------------------------------
curl -s -o nul http://127.0.0.1:8000/health && (
  echo The backend is already running.
) || (
  start "Junior Muneer - backend" /min cmd /k "cd /d "%ROOT%backend" && .venv\Scripts\python -m uvicorn junior.main:app --host 127.0.0.1 --port 8000"
)
curl -s -o nul http://localhost:3000 && (
  echo The dashboard is already running.
) || (
  start "Junior Muneer - dashboard" /min cmd /k "cd /d "%ROOT%frontend" && npm run dev"
)

echo Waiting for Junior Muneer to start...
set /a tries=0
:wait_backend
curl -s -o nul http://127.0.0.1:8000/health && goto :wait_dashboard
set /a tries+=1
if %tries% geq 90 (echo The backend didn't start. Look at the "Junior Muneer - backend" window. & goto :failed)
ping -n 2 127.0.0.1 >nul
goto :wait_backend

:wait_dashboard
curl -s -o nul http://localhost:3000 && goto :ready
set /a tries+=1
if %tries% geq 180 (echo The dashboard didn't start. Look at the "Junior Muneer - dashboard" window. & goto :failed)
ping -n 2 127.0.0.1 >nul
goto :wait_dashboard

:ready
echo Junior Muneer is running: http://localhost:3000
if /i not "%~1"=="nobrowser" start "" http://localhost:3000
echo To stop it, run stop.bat (or close the two minimized windows).
exit /b 0

:failed
echo.
echo Something went wrong (see above).
pause
exit /b 1
