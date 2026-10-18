@echo off
rem A fixed public address for WhatsApp while Junior Muneer runs on this PC (ngrok, free account).
rem Needs NGROK_AUTHTOKEN and NGROK_DOMAIN in backend\.env (see TASK.md, P8-04). Keep the window open.
title Junior Muneer - WhatsApp tunnel (ngrok)
cd /d "%~dp0backend" && .venv\Scripts\python -m junior.tunnel
