"""Files you send (WhatsApp documents and photos, 📎 in the chat) and saving them to your Google Drive."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from junior import files, whatsapp
from junior.agent.context import TurnContext
from junior.config import get_settings
from junior.db import Conversation, Message, ReceivedFile, session_scope
from junior.google import auth
from junior.google.fake import SCOPES, FakeGoogle
from junior.google.tools import drive_save_for
from junior.main import create_app
from junior.permissions import set_rule
from junior.settings_store import all_settings


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-xyz")
    get_settings.cache_clear()
    google = FakeGoogle()
    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(google))
    auth._access.clear()
    with TestClient(create_app()) as client:
        auth._save("you@example.com", "fake-refresh", SCOPES)

        def said(words: str) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Files")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids = [msg.id]
            return TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=ids)

        yield client, said, google
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def uploaded(google: FakeGoogle) -> list[dict]:
    return [f for fid, f in google.files.items() if fid.startswith("upload-")]


def test_attaching_in_the_chat_keeps_the_file_and_gives_a_tag(app):
    client, _, _ = app
    r = client.post("/api/files", files={"file": ("My CV.pdf", b"%PDF-1.7 cv", "application/pdf")})
    assert r.status_code == 201
    body = r.json()
    assert body["tag"] == f"[file {body['id']}: My CV.pdf (PDF, 1 KB)]"
    row, data = files.received(body["id"])
    assert data == b"%PDF-1.7 cv" and row.source == "chat"
    assert row.stored_as.endswith(".pdf") and "CV" not in row.stored_as  # kept under a random name


def test_odd_names_and_empty_or_huge_files(app, monkeypatch):
    client, _, _ = app
    assert files.safe_name('../..\\evil:"name".pdf') == "evil name .pdf"
    assert client.post("/api/files", files={"file": ("empty.txt", b"", "text/plain")}).status_code == 400
    monkeypatch.setattr(files, "MAX_BYTES", 10)
    assert "too big" in client.post("/api/files", files={"file": ("big.bin", b"x" * 11, "application/octet-stream")}).json()["detail"]


def test_saving_to_your_drive(app):
    _, said, google = app
    number, _ = files.save_received(b"%PDF cv", "My CV.pdf", "application/pdf", "whatsapp")
    answer = run(drive_save_for(said("save this to my drive"), number, "save this to my drive"))
    assert answer.startswith("Saved 'My CV.pdf' to their Google Drive: https://drive.google.com/file/d/upload-")
    [saved] = uploaded(google)
    assert saved["name"] == "My CV.pdf" and saved["data"] == b"%PDF cv" and saved["parents"] == ["root"]
    with session_scope() as s:
        assert s.get(ReceivedFile, number).drive_link.startswith("https://drive.google.com/file/d/upload-")


def test_a_folder_is_made_once_and_reused(app):
    _, said, google = app
    context = said("put these in my University/Semester 3 folder")
    for name in ("a.pdf", "b.pdf"):
        number, _ = files.save_received(b"x", name, "application/pdf", "chat")
        answer = run(drive_save_for(context, number, "put these in my University", "University/Semester 3"))
        assert "in 'University/Semester 3'" in answer
    folders = [f for f in google.files.values() if f["mimeType"].endswith("folder") and f.get("app")]
    assert [f["name"] for f in folders] == ["University", "Semester 3"]  # not made twice
    assert {f["parents"][0] for f in uploaded(google)} == {next(k for k, f in google.files.items() if f["name"] == "Semester 3")}


def test_inaccessible_existing_folder_never_redirects_the_save(app):
    _, said, google = app
    number, _ = files.save_received(b"x", "invoice.pdf", "application/pdf", "chat")
    answer = run(drive_save_for(said("save it in my Work folder"), number, "save it in my Work folder", "Work"))
    assert "NOT done" in answer and "Allow existing Drive folders" in answer
    assert uploaded(google) == []
    assert google.files["folder-work"].get("app") is None  # yours, untouched


def test_a_new_name_keeps_the_ending(app):
    _, said, google = app
    number, _ = files.save_received(b"x", "IMG_2041.jpg", "image/jpeg", "whatsapp")
    run(drive_save_for(said("save it as Passport photo"), number, "save it as Passport photo", new_name="Passport photo"))
    assert uploaded(google)[0]["name"] == "Passport photo.jpg"


def test_only_when_you_ask_and_your_rule_allows(app):
    _, said, google = app
    number, _ = files.save_received(b"x", "a.pdf", "application/pdf", "chat")
    assert run(drive_save_for(said("what is this file?"), number, "save it to my drive")).startswith("NOT done")
    set_rule("google.drive.save", "deny")
    assert run(drive_save_for(said("save it to my drive"), number, "save it to my drive")).startswith("NOT done")
    assert run(drive_save_for(said("save file 999 to drive"), 999, "save file 999 to drive")).startswith("NOT done")
    assert uploaded(google) == []


def test_a_whatsapp_document_becomes_a_tagged_message(app, monkeypatch):
    def meta(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/doc-media-1"):
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/doc", "mime_type": "application/pdf"})
        return httpx.Response(200, content=b"%PDF from whatsapp")

    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(meta))
    wa = whatsapp.WhatsApp("token", "100200300", "v26.0", httpx.MockTransport(meta))
    msg = {"type": "document", "document": {"id": "doc-media-1", "filename": "Transcript.pdf", "mime_type": "application/pdf",
                                            "caption": "save this in University"}}
    text = run(whatsapp.received_file(wa, msg))
    first, caption = text.split("\n")
    assert first.startswith("[file ") and first.endswith(": Transcript.pdf (PDF, 1 KB)]") and caption == "save this in University"
    number = int(first.split()[1].rstrip(":"))
    assert files.received(number)[1] == b"%PDF from whatsapp"
    photo = {"type": "image", "image": {"id": "doc-media-1", "mime_type": "image/jpeg"}}
    assert "(I sent this file without saying what to do with it.)" in run(whatsapp.received_file(wa, photo))
