import asyncio
import sqlite3

from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer
from junior import backup, scheduler
from junior.config import get_settings
from junior.main import create_app


def make_client(model):
    return TestClient(create_app(model_provider=lambda: (lambda _name: model)))


def chat(client, text):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": text})
        while ws.receive_json()["type"] not in ("done", "error"):
            pass


def titles(db_path) -> list[str]:
    con = sqlite3.connect(db_path)
    try:
        return [r[0] for r in con.execute("select title from conversations order by id")]
    finally:
        con.close()


def test_backup_file_appears_and_restore_brings_chats_back():
    model = ScriptedModel([chunked_answer("ok")])
    with make_client(model) as client:
        chat(client, "Remember this chat")
        made = client.post("/api/backups").json()
        assert made["file"] == f"junior-{backup.local_date()}.db"
        assert [b["file"] for b in client.get("/api/backups").json()] == [made["file"]]
        client.delete("/api/conversations/1")  # oops, deleted it
        assert client.get("/api/conversations").json() == []

    # Backend stopped: restore.
    restored_from = backup.backup_dir() / made["file"]
    backup.restore(restored_from)
    assert titles(get_settings().db_path) == ["Remember this chat"]
    with make_client(model) as client:
        assert [c["title"] for c in client.get("/api/conversations").json()] == [
            "Remember this chat"
        ]
    # The database from before the restore was kept, just in case.
    assert list(get_settings().data_path.glob("junior-before-restore-*.db"))


def test_only_the_last_14_are_kept():
    for day in range(1, 18):
        backup.make_backup(label=f"2026-09-{day:02d}")
    names = [p.name for p in backup.list_backups()]
    assert len(names) == 14
    assert names[0] == "junior-2026-09-17.db" and names[-1] == "junior-2026-09-04.db"


def test_scheduler_backs_up_once_a_day():
    asyncio.run(scheduler.run_due_jobs())
    asyncio.run(scheduler.run_due_jobs())
    assert [p.name for p in backup.list_backups()] == [f"junior-{backup.local_date()}.db"]


def test_a_failing_job_does_not_stop_the_scheduler(monkeypatch):
    calls = []

    def broken():
        raise RuntimeError("disk full")

    monkeypatch.setattr(scheduler, "JOBS", [("broken", broken), ("ok", lambda: calls.append(1))])
    asyncio.run(scheduler.run_due_jobs())
    assert calls == [1]
