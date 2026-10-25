"""Fresh sessions, byte-preserving save-only flows, visible original files and explicit Drive ACLs."""
import asyncio
from io import BytesIO
import json

import pytest
from fastapi.testclient import TestClient
from agents import RunContextWrapper

from fake_ai import ScriptedModel, chunked_answer
from junior.agent.context import TurnContext
from junior.agent.tools import read_file_for
from junior.chat.history import build_input
from junior.computer.tools import read_pc_file_for
from junior.db import ApprovalItem, BackgroundTask, Conversation, Message, session_scope
from junior.files import received, save_received
from junior.google.auth import GoogleError
from junior.google.tools import doc_create_for, drive_read_for
from junior.intents import storage_only
from junior.main import create_app
from junior.notes.tools import class_notes_for
from junior.permissions import set_rule
from junior.settings_store import all_settings, set_setting
from junior.transfers.tools import place_document_for, share_drive_file_for, zip_folder_for
from test_transfers import setup, approve, run
from test_whatsapp import wa, signed, text, wait_for


def chat(client, words, cid=None, paste=None):
    events = []
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": cid, "text": words, "paste": paste})
        while True:
            event = ws.receive_json(); events.append(event)
            if event["type"] in ("done", "error"):
                return events


@pytest.mark.parametrize("command", ["/clear", "CLS"])
def test_clear_is_free_removes_old_context_cancels_pending_work_and_retains_library(command):
    model = ScriptedModel([chunked_answer("Fresh answer")])
    with TestClient(create_app(model_provider=lambda: lambda _: model)) as c:
        with session_scope() as s:
            old = Conversation(title="Old session", summary="Old summary SENTINEL")
            s.add(old); s.flush(); old_id = old.id
            s.add(Message(conversation_id=old_id, role="user", source="user", content="Old history SENTINEL"))
            task = BackgroundTask(conversation_id=old_id, title="Old work", request="prepare work")
            card = ApprovalItem(conversation_id=old_id, kind="api", platform="google", item_type="document", action_type="google.docs.create", text="Draft", original_text="Draft", title="Draft", status="waiting", reason="Waiting")
            s.add_all([task, card]); s.flush(); task_id, card_id = task.id, card.id
        number, _ = save_received(b"Original class file", "Class.txt", "text/plain", "chat", old_id)
        set_setting("daily_cap_usd", 0.)
        events = chat(c, command, old_id)
        assert events[0]["type"] == "session_reset" and events[-1]["cost_usd"] == 0
        new_id = events[-1]["conversation_id"]
        assert new_id != old_id and not model.calls
        assert c.get(f"/api/conversations/{old_id}/messages").status_code == 404
        assert c.get(f"/api/library/files/{number}/download").content == b"Original class file"
        with session_scope() as s:
            assert s.get(BackgroundTask, task_id).status == "cancelled"
            assert s.get(ApprovalItem, card_id).status == "rejected"
            assert s.get(Conversation, new_id).summary == ""
        set_setting("daily_cap_usd", 5.)
        assert chat(c, "Hello in my fresh session", new_id)[-1]["type"] == "done"
        assert "SENTINEL" not in str(model.calls)


def test_whatsapp_clear_starts_a_fresh_session_without_old_carry_summary(wa):
    model = ScriptedModel([])
    with TestClient(create_app(model_provider=lambda: lambda _: model)) as c:
        with session_scope() as s:
            old = Conversation(title="WhatsApp · old", kind="whatsapp", summary="SECRET OLD CHAT")
            s.add(old); s.flush(); old_id = old.id
        signed(c, text("/clear", mid="wamid.clear.new"))
        assert "Fresh session started" in wait_for(wa, 1)[0]["text"]["body"]
        chats = [row for row in c.get("/api/conversations").json() if row["kind"] == "whatsapp"]
        assert len(chats) == 1 and chats[0]["id"] != old_id and not model.calls
        from junior.whatsapp import whatsapp_chat
        assert whatsapp_chat() == chats[0]["id"]
        with session_scope() as s:
            assert s.get(Conversation, chats[0]["id"]).summary == ""


def test_pasted_command_or_quoted_command_is_not_executed():
    model = ScriptedModel([chunked_answer("Explained")])
    with TestClient(create_app(model_provider=lambda: lambda _: model)) as c:
        cid = c.post("/api/conversations", json={}).json()["id"]
        events = chat(c, "What does /clear mean?", cid)
        assert all(e["type"] != "session_reset" for e in events)
        assert c.get(f"/api/conversations/{cid}/messages").status_code == 200


def test_storage_only_requests_refuse_model_reading_and_note_generation(setup, monkeypatch):
    _, _, _, _, said = setup
    ctx = said("Just upload this PDF into my NLP folder, don't read it")
    def unexpected(*args, **kwargs):
        pytest.fail("Save-only requests must not parse document content")
    monkeypatch.setattr("junior.reading.extract_text", unexpected)
    assert "NOT read" in run(read_file_for(ctx, 999))
    assert "NOT read" in run(read_pc_file_for(ctx, "Documents/Class.pdf"))
    assert "NOT read" in run(drive_read_for(ctx, "not-a-link"))
    assert "NOT read" in class_notes_for(ctx, ctx.user_text)
    assert ctx.usage == []
    assert not storage_only("Read this PDF and then save it to Google Drive")
    assert not storage_only("Make class notes from these slides and save them")


def test_upload_save_only_gallery_original_download_folder_move_and_preview(setup, monkeypatch):
    c, _, _, _, said = setup
    folder = c.post("/api/note-folders", json={"name": "NLP"}).json()
    def unexpected(*args, **kwargs):
        pytest.fail("Uploading/listing must not parse file content")
    original = __import__("junior.reading", fromlist=["extract_text"]).extract_text
    monkeypatch.setattr("junior.reading.extract_text", unexpected)
    raw = b"Class text: tokenization divides a sentence into tokens."
    saved = c.post("/api/files", data={"folder_id": str(folder["id"])}, files={"file": ("Lecture.txt", raw, "text/plain")}).json()
    row = c.get(f"/api/library/files/{saved['id']}").json()
    assert row["folder_name"] == "NLP"
    assert c.get(f"/api/library/files/{saved['id']}/download").content == raw
    assert c.get(f"/api/library/files?folder_id={folder['id']}").json()[0]["filename"] == "Lecture.txt"
    ctx = said(saved["tag"] + "\nJust save it in Week 2")
    result = run(place_document_for(ctx, "Week 2", "Just save it in Week 2", "notes", file_number=saved["id"]))
    assert "without reading" in result
    assert len(c.get("/api/library/files").json()) == 1
    monkeypatch.setattr("junior.reading.extract_text", original)
    assert "tokenization" in c.get(f"/api/library/files/{saved['id']}/preview").json()["text"]
    current = c.get(f"/api/library/files/{saved['id']}").json()
    body = {"filename": "Week 2.txt", "folder_id": current["folder_id"], "archived": True, "revision": current["revision"]}
    assert c.put(f"/api/library/files/{saved['id']}", json=body).status_code == 200
    assert c.get("/api/library/files").json() == []
    assert len(c.get("/api/library/files?archived=true").json()) == 1
    assert c.put(f"/api/library/files/{saved['id']}", json=body).status_code == 409


def test_generated_documents_visible_but_transfer_snapshots_hidden(setup):
    c, _, _, _, said = setup
    ctx = said("Just save this text")
    visible, _ = save_received(b"Text", "Report.md", "text/markdown", "generated", ctx.conversation_id)
    hidden, _ = save_received(b"Text", "Prepared.md", "text/markdown", "generated", ctx.conversation_id, index_in_library=False)
    assert [r["id"] for r in c.get("/api/library/files").json()] == [visible]
    assert c.get(f"/api/library/files/{hidden}").status_code == 404
    assert c.get(f"/api/library/files/{visible}/inline").status_code == 415


def test_raw_text_save_requires_exact_original_but_accepts_short_text(setup):
    c, _, _, _, said = setup
    from junior.library import save_text_to_library_for
    ctx = said("Just save this text in my Notes: NLP")
    assert "Saved" in save_text_to_library_for(ctx, "Term", "NLP", "Just save this text")
    row = c.get("/api/library/files").json()[0]
    assert c.get(f"/api/library/files/{row['id']}/download").content == b"NLP"
    assert "NOT saved" in save_text_to_library_for(ctx, "Changed", "nlp", "Just save this text")


def test_public_view_and_edit_require_sharing_approval_and_never_change_zip_privacy(setup):
    c, home, google, sent, said = setup
    set_setting("drive_share_default", "reader")
    number, tag = save_received(b"%PDF synthetic", "Class.pdf", "application/pdf", "chat")
    ctx = said(tag + "\nJust upload this document to Drive")
    result = run(place_document_for(ctx, "NLP", "Just upload this document to Drive", "google_drive", file_number=number))
    assert "Waiting for Approve" in result and not any(k.startswith("upload-") for k in google.files)
    done = approve(c, ctx)
    assert done["status"] == "posted"
    fid = done["meta"]["remote_id"]
    assert google.permissions[fid][0] == {"id": google.permissions[fid][0]["id"], "type": "anyone", "role": "reader", "allowFileDiscovery": False}
    edit = said("Make this document editable by anyone with the link")
    run(share_drive_file_for(edit, done["meta"]["post_url"], edit.user_text, "writer"))
    assert approve(c, edit)["status"] == "posted" and google.permissions[fid][0]["role"] == "writer"
    root = home / "Documents/Zip"
    root.mkdir(); (root / "Class.txt").write_text("Synthetic class")
    zip_ctx = said("Zip this folder and WhatsApp me")
    run(zip_folder_for(zip_ctx, str(root), zip_ctx.user_text))
    archive = approve(c, zip_ctx)
    assert archive["status"] == "posted" and not google.permissions.get(archive["meta"]["remote_id"])


def test_public_native_doc_is_queued_and_indexed_without_polishing_or_pre_reading(setup):
    c, _, google, _, said = setup
    set_setting("drive_share_default", "writer")
    ctx = said("Create a Google Doc with public edit access")
    result = run(doc_create_for(ctx, "NLP notes", "## Tokens\nTokenization divides text.", ctx.user_text))
    assert "Waiting for Approve" in result and len(google.docs) == 1
    done = approve(c, ctx)
    assert done["status"] == "posted" and google.permissions[done["meta"]["remote_id"]][0]["role"] == "writer"
    row = c.get("/api/library/files").json()[0]
    assert row["filename"] == "NLP notes" and not row["local"] and row["drive_link"]


def test_share_failure_retains_upload_for_deliberate_retry_and_deny_blocks_before_upload(setup, monkeypatch):
    c, _, google, _, said = setup
    set_setting("drive_share_default", "reader")
    number, tag = save_received(b"%PDF test", "Class.pdf", "application/pdf", "chat")
    ctx = said(tag + "\nUpload this PDF to Drive")
    run(place_document_for(ctx, "Class", "Upload this PDF to Drive", "google_drive", file_number=number))
    from junior.google.sharing import set_link_access
    async def refused(*args):
        raise GoogleError("Sharing policy refused it")
    monkeypatch.setattr("junior.google.sharing.set_link_access", refused)
    done = approve(c, ctx)
    assert done["status"] == "check_manually" and done["meta"]["uploaded_drive_id"]
    assert len([fid for fid in google.files if fid.startswith("upload-")]) == 1
    monkeypatch.setattr("junior.google.sharing.set_link_access", set_link_access)
    c.post(f"/api/approvals/{done['id']}/resolve", json={"posted": False})
    assert c.post(f"/api/approvals/{done['id']}/send").json()["status"] == "posted"
    assert len([fid for fid in google.files if fid.startswith("upload-")]) == 1
    set_rule("google.drive.share", "deny")
    other = said(tag + "\nUpload this PDF as public")
    assert "NOT done" in run(place_document_for(other, "Other", "Upload this PDF as public", "google_drive", file_number=number))
