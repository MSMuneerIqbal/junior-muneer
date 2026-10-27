"""Opt-in real researched PDF check on throwaway chats, with all outgoing services disabled."""
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with build_opener(ProxyHandler({})).open("http://127.0.0.1:8000/api/profile", timeout=5) as response:
        profile = json.load(response)
    with tempfile.TemporaryDirectory(prefix="junior-pdf-model-") as temp:
        os.environ.update(DATA_DIR=temp, SCHEDULER_ENABLED="false", LOG_LEVEL="WARNING",
                          WHATSAPP_TOKEN="", GMAIL_APP_PASSWORD="", GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
        from junior.config import get_settings
        get_settings.cache_clear()
        from fastapi.testclient import TestClient
        from junior.main import create_app
        from junior.db.engine import close_all_connections
        from pypdf import PdfReader
        try:
            with TestClient(create_app()) as c:
                c.put("/api/profile", json=profile).raise_for_status()
                c.patch("/api/settings", json={"task_budget_usd": .5, "task_timeout_seconds": 600}).raise_for_status()
                started = time.monotonic()
                with c.websocket_connect("/ws/chat") as ws:
                    ws.send_json({"type": "message", "conversation_id": None,
                        "text": "Junior, research reliable primary sources and make exactly 5 PDF slides introducing NLP to beginners. Cover what it is, two everyday examples, limitations, and sources. Give me the finished PDF here."})
                    while (event := ws.receive_json())["type"] not in ("done", "error"):
                        pass
                assert event["type"] == "done", "Chat did not finish."
                cid = event["conversation_id"]
                task = None
                while time.monotonic() - started < 650:
                    tasks = c.get(f"/api/tasks?conversation_id={cid}").json()
                    if tasks and tasks[0]["status"] in ("done", "failed", "cancelled"):
                        task = tasks[0]
                        break
                    time.sleep(1)
                assert task and task["status"] == "done", (task or {}).get("error", "No completed document job.")
                assert task["output_format"] == "slides_pdf"
                raw = c.get(f"/api/files/{task['file_ids'][0]}/download").content
                reader = PdfReader(BytesIO(raw))
                assert len(reader.pages) == 5
                assert "NLP" in " ".join(p.extract_text() for p in reader.pages)
                assert not c.get("/api/approvals").json()
                output = Path(__file__).resolve().parents[1] / ".pytest_cache/p1005-live"
                output.mkdir(parents=True, exist_ok=True)
                (output / "nlp.pdf").write_bytes(raw)
                import pypdfium2
                with pypdfium2.PdfDocument(raw) as pdf:
                    for i in range(len(pdf)):
                        page = pdf[i]
                        bitmap = page.render(scale=1.25)
                        bitmap.to_pil().save(output / f"page-{i + 1}.png")
                        bitmap.close()
                        page.close()
                print(json.dumps({"result": "passed", "seconds": round(time.monotonic() - started, 1),
                    "estimated_cost_usd": task["cost_usd"] + event.get("cost_usd", 0), "pages": len(reader.pages),
                    "external_files_created": False, "owner_chats_untouched": True}))
        finally:
            close_all_connections()
            get_settings.cache_clear()


if __name__ == "__main__":
    main()
