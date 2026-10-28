---
name: restart-app
description: Restart, stop or check Junior Muneer's supervised Windows app on ports 8000 and 3000 after backend changes.
---

# Restart / stop the app

start.bat launches a supervisor that owns both backend and dashboard. Do not kill a port's process blindly: stopping one supervised child stops both servers. Preserve unrelated processes and the WhatsApp tunnel.

Check /health, /api/updates and the dashboard; before restarting, check for active background tasks, computer jobs and outgoing actions. Wait for active work rather than interrupting it unnecessarily.

For a supervised restart, create data/updates/stop, wait for both ports to become free, then start backend/.venv/Scripts/python.exe -m junior.maintenance.supervisor with working directory backend in a hidden window, with stdout and stderr redirected to distinct log files under data/updates. The supervisor removes the stop marker. Do not start a second supervisor if ports remain occupied. Verify backend health and revision, /api/updates supervised status and dashboard HTTP 200. Migrations run at backend startup.

If the app is not supervised, inspect the actual process ownership and use its normal stop procedure; do not adopt or terminate unrelated processes. start.bat and stop.bat are the user's normal launcher and stop controls.
