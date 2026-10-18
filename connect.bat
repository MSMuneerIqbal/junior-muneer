@echo off
rem Connect your accounts (Phase 3). Tokens are saved in backend\.env, never in the browser or in Git.
rem   connect.bat meta    your Facebook Page (and later Instagram)
rem   connect.bat github    your GitHub fine-grained token (Phase 6)
rem   connect.bat whatsapp  WhatsApp, to chat with Junior Muneer (Phase 8)
rem   connect.bat check   test the saved connections
cd /d "%~dp0backend" && .venv\Scripts\python -m junior.connect %*
