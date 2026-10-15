---
name: live-check
description: Try a Junior Muneer feature once with the real OpenAI key and Muneer's profile, on a throwaway database so his chats, memory and approval queue are never touched. Use to check real model quality, speed and cost after building an AI feature.
---

# Live check (real key, throwaway data)

Costs real money (usually a few cents): say what you'll run, keep it to one or two messages.

1. Copy his profile from the running app (read only): `curl -s http://127.0.0.1:8000/api/profile > "$TEMP/prof_live.json"`
2. Write a script to `$TEMP/live_check.py` (Write tool, not a heredoc):
   ```python
   import json, os, shutil, time
   os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "jm-live")
   os.environ["SCHEDULER_ENABLED"] = "false"
   shutil.rmtree(os.environ["DATA_DIR"], ignore_errors=True)
   from fastapi.testclient import TestClient
   from junior.main import create_app
   with TestClient(create_app()) as c:   # real key from backend/.env
       c.put("/api/profile", json=json.load(open(os.path.join(os.environ["TEMP"], "prof_live.json"), encoding="utf-8")))
       t = time.time()
       with c.websocket_connect("/ws/chat") as ws:
           ws.send_json({"type": "message", "conversation_id": None, "text": "<the request>"})
           while (e := ws.receive_json())["type"] not in ("done", "error"):
               if e["type"] == "step": print(f"{time.time()-t:5.1f}s", e["label"], e.get("notes") or "")
       print(e["type"], e.get("message", ""), f"${e.get('cost_usd', 0):.4f}", f"{time.time()-t:.0f}s")
       print(e.get("text", ""))
   ```
3. Run from `backend/`: `PYTHONPATH=. .venv/Scripts/python "$TEMP/live_check.py" 2>&1 | grep -av " INFO "`
   (`-a`: output may contain Urdu or curly quotes).
4. Judge the result like Muneer would: facts only from his profile, simple natural English, right length,
   sensible score. Report time and cost. If quality is off, fix the agent file or model tier, re-run once.
5. Clean up: `rm -rf "$TEMP/jm-live" "$TEMP/live_check.py" "$TEMP/prof_live.json"`. Never print keys.
