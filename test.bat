@echo off
rem Runs every test: backend (pytest), then dashboard lint, type check and end-to-end tests.
rem All with a fake AI: no API key needed, nothing is spent.
setlocal

echo === Backend tests ===
cd /d "%~dp0backend" || exit /b 1
.venv\Scripts\python -m pytest || goto :failed

echo === Dashboard lint ===
cd /d "%~dp0frontend" || exit /b 1
call npm run lint || goto :failed

echo === Dashboard type check ===
call npm run typecheck || goto :failed

echo === Dashboard end-to-end tests ===
call npm run test:e2e || goto :failed

echo.
echo All tests passed.
exit /b 0

:failed
echo.
echo TESTS FAILED (see above).
exit /b 1
