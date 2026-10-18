"""Google Drive, read-only: find your files by name, and send one to you (as it is, or Google's own files exported)."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from junior import mailer, whatsapp
from junior.agent.context import TurnContext
from junior.agent.tools import send_to_me_for
from junior.config import get_settings
from junior.db import Conversation, Message, session_scope
from junior.google import auth
from junior.google.drive import file_id, kind
from junior.google.fake import SCOPES, FakeGoogle
from junior.google.tools import drive_search_for
from junior.main import create_app
from junior.registry import load_registry
from junior.settings_store import all_settings


@pytest.fixture
def drive(monkeypatch):
    for name, value in {"GMAIL_ADDRESS": "me@example.com", "GMAIL_APP_PASSWORD": "pw", "WHATSAPP_TOKEN": "token",
                        "WHATSAPP_PHONE_NUMBER_ID": "100200300", "WHATSAPP_OWNER_NUMBER": "923001112233",
                        "GOOGLE_CLIENT_ID": "client-123", "GOOGLE_CLIENT_SECRET": "secret-xyz"}.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    emails, wa = [], {"sent": [], "uploads": []}

    def whatsapp_api(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            wa["uploads"].append(request.content)
            return httpx.Response(200, json={"id": "media-1"})
        wa["sent"].append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    google = FakeGoogle()
    monkeypatch.setattr(mailer, "SENDER", emails.append)
    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(whatsapp_api))
    monkeypatch.setattr(auth, "TRANSPORT", httpx.MockTransport(google))
    auth._access.clear()
    with TestClient(create_app()):
        auth._save("you@example.com", "fake-refresh", SCOPES)

        def said(words: str) -> TurnContext:
            with session_scope() as s:
                chat = Conversation(title="Drive")
                s.add(chat)
                s.flush()
                msg = Message(conversation_id=chat.id, role="user", source="user", content=words)
                s.add(msg)
                s.flush()
                ids = [msg.id]
            return TurnContext(conversation_id=None, settings=all_settings(), user_message_ids=ids)

        yield said, emails, wa, google
    get_settings.cache_clear()


def run(coro):
    return asyncio.run(coro)


def test_any_drive_link_gives_its_id():
    assert file_id("https://drive.google.com/file/d/1AbC_dEf-GhI/view?usp=sharing") == "1AbC_dEf-GhI"
    assert file_id("https://drive.google.com/open?id=1XyZ_987654") == "1XyZ_987654"
    assert file_id("https://docs.google.com/presentation/d/1Slides_123/edit") == "1Slides_123"
    assert kind("application/pdf") == "PDF" and kind("image/png") == "image"


def test_finding_your_cv_by_name(drive):
    said, *_ = drive
    context = said("see in my google drive there is my cv")
    found = run(drive_search_for(context, "muneer cv"))
    assert "Muneer Iqbal CV.pdf (PDF, changed 2026-10-01): https://drive.google.com/file/d/file-cv-2026/view" in found
    assert "Muneer Iqbal CV 2024.docx (Word file" in found
    assert "START OF THEIR TEXT" in found and context.outside_content_seen  # file names can be anyone's words
    assert run(drive_search_for(context, "passport")).startswith("No files in their Drive")


def test_sending_your_cv_on_whatsapp_as_the_pdf_it_is(drive):
    said, _, wa, _ = drive
    context = said("see in my google drive there is my cv, send me here please")
    answer = run(send_to_me_for(context, "whatsapp", "Your CV", "Here's your CV.", "send me here please",
                                "https://drive.google.com/file/d/file-cv-2026/view"))
    assert answer.startswith("Sent to their WhatsApp with the file 'Muneer Iqbal CV.pdf'")
    document = wa["sent"][1]["document"]
    assert document["filename"] == "Muneer Iqbal CV.pdf"
    assert b"%PDF-1.7 fake CV" in wa["uploads"][0] and b"application/pdf" in wa["uploads"][0]


def test_google_files_are_exported(drive):
    said, emails, _, _ = drive
    context = said("email me my research plan as a pdf")
    run(send_to_me_for(context, "gmail", "Plan", "Here it is.", "email me my research plan",
                                "https://docs.google.com/document/d/doc-plan/edit", as_pdf=True))
    [file] = list(emails[0].iter_attachments())
    assert file.get_filename() == "Research plan.pdf" and file.get_content_type() == "application/pdf"
    assert file.get_content().startswith(b"exported as application/pdf")
    run(send_to_me_for(context, "gmail", "Income", "Your sheet.", "email me my research plan",
                                "https://docs.google.com/spreadsheets/d/sheet-income/edit", as_pdf=True))
    [sheet] = list(emails[1].iter_attachments())
    assert sheet.get_filename() == "Income.xlsx"  # a sheet stays a spreadsheet


def test_a_folder_or_a_missing_file_sends_the_link_with_the_reason(drive):
    said, emails, _, _ = drive
    context = said("email me the work folder")
    answer = run(send_to_me_for(context, "gmail", "Work", "Here.", "email me the work folder",
                                "https://drive.google.com/drive/folders/x?id=folder-work"))
    assert "is a folder, not a file" in answer and "link was sent instead" in answer
    assert "folder-work" in emails[0].get_body(("plain",)).get_content()
    assert list(emails[0].iter_attachments()) == []


def test_without_the_drive_permission_it_says_connect_again(drive):
    said, *_ = drive
    auth._save("you@example.com", "fake-refresh", SCOPES.replace("https://www.googleapis.com/auth/drive.readonly ", ""))
    assert "didn't allow finding files in your Drive" in run(drive_search_for(said("find my cv"), "cv"))


def test_connect_asks_for_read_only_drive_never_full_drive(drive):
    assert "https://www.googleapis.com/auth/drive.readonly" in auth.SCOPES
    assert "https://www.googleapis.com/auth/drive" not in auth.SCOPES


def test_junior_muneer_has_drive_search():
    from junior.agent.tools import TOOL_FACTORIES

    assert "drive_search" in [t.name for t in TOOL_FACTORIES["google"]()]
    assert "google" in load_registry().get("junior_muneer").tools
