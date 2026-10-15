@echo off
rem Connect your accounts (Phase 3). Tokens are saved in backend\.env, never in the browser or in Git.
rem   connect.bat meta    your Facebook Page (and later Instagram)
rem   connect.bat check   test the saved connections
cd /d "%~dp0backend" && .venv\Scripts\python -m junior.connect %*
