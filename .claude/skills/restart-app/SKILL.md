---
name: restart-app
description: Restart, stop or check Muneer's running Junior Muneer app (backend on port 8000, dashboard on 3000) on Windows. Use after backend changes so he sees the new code, or when he asks to close the servers.
---

# Restart / stop the app

His app runs from `start.bat` in two minimized windows: "Junior Muneer - backend" (uvicorn, 8000) and
"Junior Muneer - dashboard" (`npm run dev`, 3000, hot-reloads by itself). The backend does **not**
reload: restart it after backend changes, or new UI fails quietly (404 on new endpoints).

**Check what's running** (PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen -ErrorAction SilentlyContinue | Select LocalPort, OwningProcess
Invoke-RestMethod http://127.0.0.1:8000/health
```

**Restart only the backend** (PowerShell; run these as separate lines, not one long `;` chain, because
the safety check misreads `taskkill /fi` in chained commands):

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
& taskkill.exe /fi "WINDOWTITLE eq Junior Muneer - backend*" /t /f 2>$null | Out-Null   # close the old window too (else they pile up: 31 once)
Start-Process cmd.exe -ArgumentList '/k', 'title Junior Muneer - backend && cd /d "C:\Users\MUNEER IQBAL\Desktop\junior-muneer\backend" && .venv\Scripts\python -m uvicorn junior.main:app --host 127.0.0.1 --port 8000' -WindowStyle Minimized
for ($i = 0; $i -lt 40; $i++) { try { Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2 | Out-Null; "backend up"; break } catch { Start-Sleep -Seconds 2 } }
```

**Stop everything:** `& cmd.exe /c "`"C:\Users\MUNEER IQBAL\Desktop\junior-muneer\stop.bat`""`
(it frees both ports and closes the two windows).

**Start everything:** `Start-Process cmd.exe -ArgumentList '/c', '"C:\Users\MUNEER IQBAL\Desktop\junior-muneer\start.bat" nobrowser' -WindowStyle Minimized`

After a restart, check a new endpoint answers (e.g. `curl -s http://127.0.0.1:8000/api/permissions`).
Migrations run by themselves on startup.
