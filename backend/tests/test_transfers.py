"""Real binary placement and ZIPs, exact destinations, approvals, permissions and private-link delivery."""
import asyncio
import _winapi
from io import BytesIO
import json
from pathlib import Path
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from junior import files, whatsapp
from junior.agent.context import TurnContext
from junior.agent.fake import fake_model_provider
from junior.computer import paths
from junior.config import get_settings
from junior.db import Conversation, Message, session_scope
from junior.google import auth
from junior.google.fake import FakeGoogle, SCOPES
from junior.main import create_app
from junior.permissions import set_mode, set_rule
from junior.settings_store import all_settings
from junior.transfers.tools import place_document_for, zip_folder_for


def run(work):
    return asyncio.run(work)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for key, value in {"GOOGLE_CLIENT_ID": "test-client", "GOOGLE_CLIENT_SECRET": "test-secret",
                       "WHATSAPP_TOKEN": "test-token", "WHATSAPP_PHONE_NUMBER_ID": "123456",
                       "WHATSAPP_OWNER_NUMBER": "923001112233", "META_APP_SECRET": "test-secret"}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    home = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)
    monkeypatch.setattr(paths, "home", lambda: home)
    google, sent = FakeGoogle(), []
    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(google))
    auth._access.clear()
    def meta(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.transfer-test"}]})
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(meta))
    with TestClient(create_app(model_provider=fake_model_provider)) as c:
        auth._save("you@example.com", "fake-refresh", SCOPES)
        def said(text):
            with session_scope() as s:
                chat = Conversation(title="Transfer test")
                s.add(chat); s.flush()
                message = Message(conversation_id=chat.id, role="user", source="user", content=text)
                s.add(message); s.flush()
                ctx = TurnContext(conversation_id=chat.id, settings=all_settings(), user_message_ids=[message.id], user_text=text)
            return ctx
        yield c, home, google, sent, said
    get_settings.cache_clear()


def card(c, ctx):
    return c.get(f"/api/approvals/{ctx.approval_ids[-1]}").json()


def approve(c, ctx):
    r = c.post(f"/api/approvals/{ctx.approval_ids[-1]}/approve", json={})
    assert r.status_code == 200, r.text
    return r.json()


def source(home):
    path = home / "Downloads" / "Lecture.pptx"
    path.write_bytes(b"PK\x03\x04 actual binary slide bytes\x00\xff")
    return path


def test_copy_preserves_binary_bytes_creates_folder_after_approval_and_keeps_source(setup):
    c, home, _, _, said = setup
    original = source(home)
    ctx = said("Copy my slides into Documents/NLP")
    answer = run(place_document_for(ctx, "Documents/NLP", ctx.user_text, pc_file=str(original), new_name="Lecture one"))
    dest = home / "Documents" / "NLP" / "Lecture one.pptx"
    assert "Waiting for Approve" in answer and not dest.parent.exists()
    done = approve(c, ctx)
    assert done["status"] == "posted" and dest.read_bytes() == original.read_bytes()
    assert c.post(f"/api/approvals/{done['id']}/approve", json={}).status_code == 409
    assert "already exists" in run(place_document_for(ctx, "Documents/NLP", ctx.user_text, pc_file=str(original), new_name="Lecture one"))


def test_uploaded_and_generated_documents_and_saved_notes_can_be_placed(setup):
    c, home, _, _, said = setup
    number, tag = files.save_received(b"%PDF uploaded", "Lesson.pdf", "application/pdf", "chat")
    ctx = said(tag + "\nPut this in Documents/Class")
    run(place_document_for(ctx, "Documents/Class", "Put this in Documents/Class", file_number=number))
    assert approve(c, ctx)["status"] == "posted"
    assert (home / "Documents/Class/Lesson.pdf").read_bytes() == b"%PDF uploaded"
    other = said("Place the generated report in Documents/Class")
    generated, _ = files.save_received(b"PK generated", "Report.docx", "application/octet-stream", "generated", other.conversation_id)
    run(place_document_for(other, "Documents/Class", other.user_text, file_number=generated))
    assert approve(c, other)["status"] == "posted"
    from junior.notes.store import save_note
    note = save_note(title="NLP", subject="AI", class_date="2026-10-24", summary="A class", body="## Tokens\nWords form tokens.",
                     source_text="A class", sources=[], warnings=[], context=other)
    run(place_document_for(other, "Documents/Class", other.user_text, note_id=note["id"]))
    assert approve(c, other)["status"] == "posted"
    assert "Words form tokens" in (home / "Documents/Class/2026-10-24 NLP.md").read_text()


def test_forged_source_quote_blocked_destination_and_snapshot_tampering_fail(setup):
    c, home, _, _, said = setup
    ctx = said("Put my slides in Documents")
    original = source(home)
    assert "quote" in run(place_document_for(ctx, "Documents", "Not the user's words", pc_file=str(original)))
    number, _ = files.save_received(b"private", "Private.txt", "text/plain", "chat")
    assert "wasn't supplied" in run(place_document_for(ctx, "Documents", ctx.user_text, file_number=number))
    assert "holds secrets" in run(place_document_for(ctx, "Documents", ctx.user_text, pc_file="Desktop/.env"))
    assert "outside" in run(place_document_for(ctx, str(home / "Other"), ctx.user_text, pc_file=str(original)))
    run(place_document_for(ctx, "Documents", ctx.user_text, pc_file=str(original)))
    item = card(c, ctx)
    row, _ = files.received(item["meta"]["snapshot_id"])
    (files.files_dir() / row.stored_as).write_bytes(b"different")
    done = approve(c, ctx)
    assert done["status"] != "posted" and not (home / "Documents/Lecture.pptx").exists()


def test_destination_collision_and_link_swap_after_preparation_never_overwrite(setup):
    c, home, _, _, said = setup
    original = source(home)
    ctx = said("Place my slides into Documents")
    run(place_document_for(ctx, "Documents", ctx.user_text, pc_file=str(original)))
    dest = home / "Documents/Lecture.pptx"
    dest.write_bytes(b"my existing version")
    assert approve(c, ctx)["status"] != "posted" and dest.read_bytes() == b"my existing version"
    ctx2 = said("Place slides into Documents/Target")
    run(place_document_for(ctx2, "Documents/Target", ctx2.user_text, pc_file=str(original)))
    _winapi.CreateJunction(str(home / "Downloads"), str(home / "Documents/Target"))
    assert approve(c, ctx2)["status"] != "posted"


def test_drive_exact_destination_missing_folders_full_scope_and_ambiguous_names(setup):
    c, home, google, _, said = setup
    original = source(home)
    ctx = said("Save my slides to Google Drive University/NLP")
    set_rule("google.drive.save", "ask")
    run(place_document_for(ctx, "University/NLP", ctx.user_text, "google_drive", pc_file=str(original)))
    assert not any(f["name"] == "University" for f in google.files.values())
    done = approve(c, ctx)
    assert done["status"] == "posted"
    saved = google.files[done["meta"]["remote_id"]]
    assert saved["data"] == original.read_bytes()
    assert google.files[saved["parents"][0]]["name"] == "NLP"
    auth._save("you@example.com", "fake-refresh", SCOPES + " " + auth.DRIVE_FOLDERS_SCOPE)
    ctx2 = said("Save slides into my existing Google Drive Work folder")
    run(place_document_for(ctx2, "https://drive.google.com/drive/folders/folder-work", ctx2.user_text, "google_drive", pc_file=str(original)))
    assert approve(c, ctx2)["status"] == "posted"
    assert google.files[card(c, ctx2)["meta"]["remote_id"]]["parents"] == ["folder-work"]
    google.files["folder-work-2"] = dict(google.files["folder-work"])
    ctx3 = said("Save slides to Work")
    run(place_document_for(ctx3, "Work", ctx3.user_text, "google_drive", pc_file=str(original)))
    assert "More than one" in approve(c, ctx3)["meta"]["last_error"]


def test_local_zip_contains_nested_files_empty_folders_and_real_download(setup):
    c, home, _, _, said = setup
    root = home / "Documents/NLP"
    (root / "empty").mkdir(parents=True)
    (root / "week1").mkdir()
    (root / "week1/lecture.txt").write_text("Tokenization class")
    ctx = said("Zip my Documents/NLP folder")
    result = run(zip_folder_for(ctx, str(root), ctx.user_text, send_whatsapp=False))
    assert "Download ZIP" in result and not ctx.approval_ids
    import re
    number = re.search(r"/api/files/(\d+)/download", result).group(1)
    data = c.get(f"/api/files/{number}/download")
    assert data.status_code == 200 and data.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(data.content)) as archive:
        assert "NLP/empty/" in archive.namelist()
        assert archive.read("NLP/week1/lecture.txt") == b"Tokenization class"


def test_zip_refuses_secrets_links_and_limits_instead_of_omitting(setup, monkeypatch):
    _, home, _, _, said = setup
    root = home / "Documents/Package"
    root.mkdir()
    ctx = said("Zip my Package folder")
    (root / ".env").write_text("SECRET=never")
    assert "secret" in run(zip_folder_for(ctx, str(root), ctx.user_text, send_whatsapp=False))
    (root / ".env").unlink()
    _winapi.CreateJunction(str(home / "Downloads"), str(root / "link"))
    assert "link" in run(zip_folder_for(ctx, str(root), ctx.user_text, send_whatsapp=False))
    (root / "link").rmdir()
    (root / "a.txt").write_text("A")
    (root / "b.txt").write_text("B")
    monkeypatch.setattr("junior.transfers.archives.MAX_ENTRIES", 1)
    assert "500 entries" in run(zip_folder_for(ctx, str(root), ctx.user_text, send_whatsapp=False))


def test_cloud_zip_preserves_subfolders_exports_native_docs_and_handles_pagination(setup):
    _, _, google, _, said = setup
    google.files["subfolder-test"] = {"name": "Week1", "mimeType": "application/vnd.google-apps.folder", "parents": ["folder-work"], "data": b""}
    for i in range(105):
        google.files[f"lecture-file-{i}"] = {"name": f"Lecture {i}.txt", "mimeType": "text/plain", "parents": ["subfolder-test"], "data": b"class"}
    google.docs["native-doc-test"] = {"title": "Native lecture", "text": "Tokenization"}
    google.files["native-doc-test"] = {"name": "Native lecture", "mimeType": "application/vnd.google-apps.document", "parents": ["subfolder-test"], "data": b""}
    ctx = said("Zip my Google Drive Work folder")
    result = run(zip_folder_for(ctx, "Work", ctx.user_text, "google_drive", False))
    assert "Download ZIP" in result, result
    import re
    number = int(re.search(r"/api/files/(\d+)/download", result).group(1))
    with zipfile.ZipFile(BytesIO(files.received(number)[1])) as archive:
        assert "Work/Week1/Lecture 104.txt" in archive.namelist()
        assert b"Tokenization" in archive.read("Work/Week1/Native lecture.docx")


def test_zip_delivery_waits_then_sends_private_link_once_and_honors_nested_rules(setup):
    c, home, google, sent, said = setup
    root = home / "Documents/Send"
    root.mkdir(); (root / "lesson.txt").write_text("Class material")
    ctx = said("Zip Documents/Send and WhatsApp it to me")
    result = run(zip_folder_for(ctx, str(root), ctx.user_text))
    assert "Waiting for Approve" in result and sent == []
    assert not any(k.startswith("upload-") for k in google.files)
    done = approve(c, ctx)
    assert done["status"] == "posted" and len(sent) == 1
    assert sent[0]["to"] == "923001112233" and sent[0]["type"] == "text"
    assert "https://drive.google.com/" in sent[0]["text"]["body"]
    saved = google.files[done["meta"]["remote_id"]]
    assert saved["parents"] == ["root"] and "permissions" not in saved
    assert c.post(f"/api/approvals/{done['id']}/send").status_code == 409
    assert len(sent) == 1
    ctx2 = said("Zip Send and WhatsApp me")
    run(zip_folder_for(ctx2, str(root), ctx2.user_text))
    set_rule("google.drive.save", "deny")
    blocked = approve(c, ctx2)
    assert blocked["status"] != "posted" and len(sent) == 1


def test_plan_pause_deny_outside_content_and_immutable_preview(setup):
    c, home, _, _, said = setup
    original = source(home)
    ctx = said("Put my slides into Documents")
    set_mode("plan")
    assert "Plan" in run(place_document_for(ctx, "Documents", ctx.user_text, pc_file=str(original)))
    set_mode("rules")
    set_rule("computer.write", "auto")
    ctx.mark_outside()
    assert "Waiting for Approve" in run(place_document_for(ctx, "Documents", ctx.user_text, pc_file=str(original)))
    item = card(c, ctx)
    assert c.patch(f"/api/approvals/{item['id']}", json={"text": "a different destination"}).status_code == 409
    set_rule("computer.read", "deny")
    other = said("Place slides elsewhere")
    assert "turned off" in run(place_document_for(other, "Documents/Other", other.user_text, pc_file=str(original)))


def test_optional_drive_scope_is_only_requested_explicitly(setup):
    c, _, _, _, _ = setup
    from urllib.parse import parse_qs, urlparse
    assert auth.DRIVE_FOLDERS_SCOPE not in parse_qs(urlparse(auth.consent_url()).query)["scope"][0].split()
    assert auth.DRIVE_FOLDERS_SCOPE in parse_qs(urlparse(auth.consent_url(True)).query)["scope"][0].split()
    assert c.get("/api/google/status").json()["drive_folder_access"] is False


def test_nested_ask_forces_approval_even_when_archive_rule_is_auto_and_pause_blocks_work(setup):
    _, home, _, sent, said = setup
    root = home / "Documents/Compound"
    root.mkdir(); (root / "class.txt").write_text("Material")
    set_rule("files.archive_whatsapp", "auto")
    set_rule("google.drive.save", "ask")
    ctx = said("Zip Compound and WhatsApp me")
    result = run(zip_folder_for(ctx, str(root), ctx.user_text))
    assert "Waiting for Approve" in result and sent == []
    from junior.pause import set_paused
    set_paused(True)
    blocked = said("Zip Compound again and WhatsApp me")
    assert "NOT done" in run(zip_folder_for(blocked, str(root), blocked.user_text))
    assert not blocked.approval_ids


def test_uncertain_whatsapp_delivery_keeps_upload_and_deliberate_retry_reuses_it(setup, monkeypatch):
    c, home, google, sent, said = setup
    root = home / "Documents/Retry"
    root.mkdir(); (root / "class.txt").write_text("Material")
    ctx = said("Zip Retry and send to WhatsApp")
    run(zip_folder_for(ctx, str(root), ctx.user_text))
    original_transport = whatsapp.TRANSPORT
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(lambda req: httpx.Response(500, json={"error": {"message": "temporary failure"}})))
    failed = approve(c, ctx)
    assert failed["status"] == "check_manually" and failed["meta"]["archive_drive_link"]
    assert len([k for k in google.files if k.startswith("upload-")]) == 1
    assert c.post(f"/api/approvals/{failed['id']}/send").status_code == 409
    monkeypatch.setattr(whatsapp, "TRANSPORT", original_transport)
    c.post(f"/api/approvals/{failed['id']}/resolve", json={"posted": False}).raise_for_status()
    success = c.post(f"/api/approvals/{failed['id']}/send").json()
    assert success["status"] == "posted" and len(sent) == 1
    assert len([k for k in google.files if k.startswith("upload-")]) == 1


def test_pause_between_upload_and_whatsapp_stops_the_second_action(setup, monkeypatch):
    c, home, google, sent, said = setup
    root = home / "Documents/Between"
    root.mkdir(); (root / "class.txt").write_text("Material")
    ctx = said("Zip Between and send to WhatsApp")
    run(zip_folder_for(ctx, str(root), ctx.user_text))
    from junior.google.drive import save_exact
    from junior.pause import set_paused
    async def save_then_pause(*args):
        result = await save_exact(*args)
        set_paused(True)
        return result
    monkeypatch.setattr("junior.google.drive.save_exact", save_then_pause)
    done = approve(c, ctx)
    assert done["status"] != "posted" and done["meta"]["archive_drive_link"]
    assert sent == [] and len([k for k in google.files if k.startswith("upload-")]) == 1


def test_google_copy_approved_on_whatsapp_returns_the_real_file_link(setup):
    c, home, _, _, said = setup
    ctx = said("Save my slides into Google Drive Class")
    set_rule("google.drive.save", "ask")
    run(place_document_for(ctx, "Class", ctx.user_text, "google_drive", pc_file=str(source(home))))
    result = run(whatsapp.on_button(f"approve:{ctx.approval_ids[-1]}", c.app))
    assert "https://drive.google.com/file/" in result and "requested Google Drive folder" in result


def test_unreadable_subfolder_fails_the_archive_instead_of_silently_omitting_it(setup, monkeypatch):
    _, home, _, _, said = setup
    root = home / "Documents/Unreadable"
    root.mkdir()
    def denied_walk(path, *, followlinks, onerror):
        onerror(PermissionError("A class subfolder is inaccessible"))
        return iter(())
    monkeypatch.setattr("junior.transfers.archives.os.walk", denied_walk)
    ctx = said("Zip my Unreadable folder")
    answer = run(zip_folder_for(ctx, str(root), ctx.user_text, send_whatsapp=False))
    assert "No incomplete archive was saved" in answer and "Download ZIP" not in answer
