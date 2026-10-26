"""Manual deletion affects only the selected managed copy, with stale/busy/recycle failure guards."""
from pathlib import Path
import pytest

from junior.db import ApprovalItem, BackgroundTask, session_scope
from junior.files import received, save_received
from junior.library import register_cloud_file
from test_notes import client, manual_note


@pytest.fixture
def trash(monkeypatch):
    removed = []
    def recycle(path):
        removed.append((Path(path), Path(path).read_bytes())); Path(path).unlink()
    monkeypatch.setattr("junior.computer.sender.to_recycle_bin", recycle)
    return removed


def remove(c, number, revision):
    return c.request("DELETE", f"/api/library/files/{number}", json={"revision": revision})


def test_delete_file_removes_original_from_library_and_keeps_other_files(client, trash):
    number, _ = save_received(b"Exact selected copy", "Delete.txt", "text/plain", "chat")
    other, _ = save_received(b"Keep me", "Keep.txt", "text/plain", "chat")
    row = client.get(f"/api/library/files/{number}").json()
    assert remove(client, number, row["revision"]).status_code == 200
    assert trash[0][1] == b"Exact selected copy" and received(number) is None
    assert client.get(f"/api/library/files/{number}").status_code == 404
    assert client.get(f"/api/library/files/{other}/download").content == b"Keep me"
    assert remove(client, number, row["revision"]).status_code == 404


def test_delete_note_moves_mirror_to_bin_but_keeps_source_file(client, trash):
    number, _ = save_received(b"Class source", "Class.txt", "text/plain", "chat")
    note = manual_note()
    response = client.request("DELETE", f"/api/notes/{note['id']}", json={"revision": note["revision"]})
    assert response.status_code == 200 and len(trash) == 1
    assert "Tokenization" in trash[0][1].decode()
    assert client.get(f"/api/notes/{note['id']}").status_code == 404
    assert client.get(f"/api/library/files/{number}/download").content == b"Class source"


def test_delete_cloud_entry_does_not_call_google_or_touch_a_local_file(client, trash, monkeypatch):
    number = register_cloud_file("Cloud Doc", "application/vnd.google-apps.document", "https://docs.google.com/document/d/example/edit")
    row = client.get(f"/api/library/files/{number}").json()
    assert remove(client, number, row["revision"]).status_code == 200 and not trash


def test_stale_revision_hidden_snapshot_and_recycle_failure_are_refused(client, trash, monkeypatch):
    hidden, _ = save_received(b"Snapshot", "Internal.txt", "text/plain", "generated", index_in_library=False)
    assert remove(client, hidden, "a"*64).status_code == 404
    number, _ = save_received(b"Keep if failed", "Class.txt", "text/plain", "chat")
    row = client.get(f"/api/library/files/{number}").json()
    assert remove(client, number, "b"*64).status_code == 409
    def failure(*args): raise OSError("Recycle Bin unavailable")
    monkeypatch.setattr("junior.computer.sender.to_recycle_bin", failure)
    assert remove(client, number, row["revision"]).status_code == 409
    assert received(number)[1] == b"Keep if failed"


def test_delete_refuses_running_task_and_cancels_unsent_approval(client, trash):
    number, _ = save_received(b"Task source", "Class.txt", "text/plain", "chat")
    row = client.get(f"/api/library/files/{number}").json()
    with session_scope() as s:
        task = BackgroundTask(title="Read source", request=f"Read [file {number}: Class.txt]", status="running")
        s.add(task); s.flush(); task_id = task.id
    assert remove(client, number, row["revision"]).status_code == 409
    with session_scope() as s:
        s.get(BackgroundTask, task_id).status = "done"
        card = ApprovalItem(kind="api", platform="google", item_type="file_transfer", action_type="google.drive.save",
            title="Copy source", text="Copy source", original_text="Copy source", status="waiting", reason="Waiting", meta={"source_file_id": number})
        s.add(card); s.flush(); card_id = card.id
    assert remove(client, number, row["revision"]).status_code == 200
    with session_scope() as s:
        assert s.get(ApprovalItem, card_id).status == "rejected"
