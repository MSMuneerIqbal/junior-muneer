"""Manual folder rename/delete retain originals, archived content, mirrors and stale-edit protection."""
import pytest

from junior.db import ClassNote, session_scope
from junior.files import save_received
from junior.notes.store import _storage_path
from test_notes import client, manual_note


def current(c, number):
    return next(f for f in c.get("/api/note-folders").json() if f["id"] == number)


def test_rename_keeps_contents_and_updates_markdown_mirrors(client, isolated_settings):
    note = manual_note()
    number, _ = save_received(b"Original", "Lecture.txt", "text/plain", "library", library_folder="NLP")
    before = current(client, note["folder_id"])
    result = client.put(f"/api/note-folders/{before['id']}", json={"name": " NLP lectures ", "revision": before["revision"]})
    assert result.status_code == 200, result.text
    renamed = result.json()
    assert renamed["name"] == "NLP lectures" and renamed["id"] == before["id"]
    assert renamed["total_notes"] == 1 and renamed["total_files"] == 1
    assert client.get(f"/api/library/files/{number}/download").content == b"Original"
    assert client.get(f"/api/notes/{note['id']}").json()["folder_name"] == "NLP lectures"
    paths = list((isolated_settings.data_path / "notes").rglob("*.md"))
    assert len(paths) == 1 and "NLP lectures" in paths[0].parent.name
    assert client.put(f"/api/note-folders/{before['id']}", json={"name": "Stale", "revision": before["revision"]}).status_code == 409


def test_folder_changes_refuse_duplicate_names_paths_missing_and_new_content(client):
    first = client.post("/api/note-folders", json={"name": "NLP"}).json()
    client.post("/api/note-folders", json={"name": "AI"})
    revision = current(client, first["id"])["revision"]
    for name, status in ((" ai ", 409), ("../Other", 422), ("C:\\Notes", 422), ("   ", 422)):
        assert client.put(f"/api/note-folders/{first['id']}", json={"name": name, "revision": revision}).status_code == status
    save_received(b"New upload", "Class.txt", "text/plain", "library", library_folder="NLP")
    assert client.request("DELETE", f"/api/note-folders/{first['id']}", json={"revision": revision}).status_code == 409
    assert client.put("/api/note-folders/999", json={"name": "Missing", "revision": revision}).status_code == 404


def test_deleting_folder_moves_all_contents_including_archived_and_preserves_exact_bytes(client, isolated_settings):
    note = manual_note()
    client.post(f"/api/notes/{note['id']}/archive", json={"archived": True, "revision": note["revision"]})
    number, _ = save_received(b"Keep these exact bytes", "Lecture.txt", "text/plain", "library", library_folder="NLP")
    row = client.get(f"/api/library/files/{number}").json()
    client.put(f"/api/library/files/{number}", json={"filename": row["filename"], "folder_id": row["folder_id"], "archived": True, "revision": row["revision"]})
    before = current(client, note["folder_id"])
    assert before["file_count"] == 0 and before["total_files"] == 1
    result = client.request("DELETE", f"/api/note-folders/{before['id']}", json={"revision": before["revision"]})
    assert result.status_code == 200, result.text
    assert result.json()["destination_name"] == "Unfiled"
    assert all(f["id"] != before["id"] for f in client.get("/api/note-folders").json())
    saved = client.get(f"/api/notes/{note['id']}").json()
    assert saved["folder_name"] == "Unfiled" and saved["archived"]
    file = client.get(f"/api/library/files/{number}").json()
    assert file["folder_name"] == "Unfiled" and file["archived"]
    assert client.get(f"/api/library/files/{number}/download").content == b"Keep these exact bytes"
    paths = list((isolated_settings.data_path / "notes").rglob("*.md"))
    assert len(paths) == 1 and paths[0].parent.name.startswith(f"{result.json()['destination_id']}-Unfiled")
    # A stale content editor must reopen after the move.
    assert client.post(f"/api/notes/{note['id']}/archive", json={"archived": False, "revision": note["revision"]}).status_code == 409


def test_empty_folder_deletion_and_deleting_unfiled_do_not_recreate_the_same_folder(client):
    empty = client.post("/api/note-folders", json={"name": "Empty"}).json()
    item = current(client, empty["id"])
    assert client.request("DELETE", f"/api/note-folders/{item['id']}", json={"revision": item["revision"]}).json()["destination_id"] is None
    assert client.get("/api/note-folders").json() == []
    note = manual_note(folder="Unfiled")
    item = current(client, note["folder_id"])
    response = client.request("DELETE", f"/api/note-folders/{item['id']}", json={"revision": item["revision"]})
    assert response.json()["destination_name"] == "Unfiled (2)"
    assert client.get(f"/api/notes/{note['id']}").json()["folder_name"] == "Unfiled (2)"


def test_failed_mirror_write_does_not_delete_or_rename_folder(client, monkeypatch):
    note = manual_note()
    folder = current(client, note["folder_id"])
    def fail(*args):
        raise OSError("Storage unavailable")
    monkeypatch.setattr("junior.notes.store._mirror", fail)
    with pytest.raises(OSError):
        client.put(f"/api/note-folders/{folder['id']}", json={"name": "Changed", "revision": folder["revision"]})
    with session_scope() as s:
        saved = s.get(ClassNote, note["id"])
        assert saved.folder.name == "NLP" and _storage_path(saved, "NLP").is_file()
