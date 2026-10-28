"""P9-07: your PC from WhatsApp. PC cards come with Approve/Reject; Approve runs it and the result comes back; a
file from your PC can be sent to you; a card approved on the dashboard still reports back on WhatsApp."""

import json

import httpx
import pytest
from agents.testing import ModelStep, assistant_message
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, function_call
from junior import whatsapp
from junior.computer import paths
from junior.config import get_settings
from junior.main import create_app
from junior.voice import FakeVoice
from test_whatsapp import OWNER, SECRET, message, signed, text, wait_for


@pytest.fixture
def wa(tmp_path, monkeypatch):
    """A connected WhatsApp with a pretend Meta (uploads of any file allowed), and a pretend PC."""
    for key, value in {"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_NUMBER_ID": "100200300", "WHATSAPP_VERIFY_TOKEN": "v",
                       "WHATSAPP_OWNER_NUMBER": OWNER, "META_APP_SECRET": SECRET}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    sent: list[dict] = []

    def meta(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/media"):
            sent.append({"upload": request.content})
            return httpx.Response(200, json={"id": "media-up-1"})
        if request.method == "POST":
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})
        return httpx.Response(404)

    monkeypatch.setattr(whatsapp, "TRANSPORT", httpx.MockTransport(meta))
    user = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads"):
        (user / name).mkdir(parents=True)
    monkeypatch.setattr(paths, "home", lambda: user)
    yield sent, user
    get_settings.cache_clear()


def app(model):
    return TestClient(create_app(model_provider=lambda: (lambda _n: model), voice=FakeVoice))


def tap(c, button_id, mid):
    signed(c, message({"from": OWNER, "id": mid, "type": "interactive",
                       "interactive": {"type": "button_reply", "button_reply": {"id": button_id, "title": "x"}}}))


def test_a_pc_change_from_whatsapp_comes_with_buttons_and_approve_does_it(wa):
    sent, user = wa
    model = ScriptedModel([
        ModelStep(output=[function_call("ask_computer_agent", {"task": "make todo.txt on my Desktop: call Ali"}, call_id="c1")]),
        ModelStep(output=[function_call("pc_write", {"file": "Desktop/todo.txt", "content": "call Ali\n"}, call_id="c2")]),
        ModelStep(output=[assistant_message("A card waits for their OK.")]),
        chunked_answer("It's ready: tap Approve and todo.txt is on your Desktop."),
    ])
    with app(model) as c:
        signed(c, text("Junior, make todo.txt on my Desktop: call Ali"))
        answer, card = wait_for(sent, 2)[:2]
        assert "tap Approve" in answer["text"]["body"]
        body = card["interactive"]["body"]["text"]
        assert body.startswith(f"Your PC: Create {user / 'Desktop' / 'todo.txt'}") and "call Ali" in body and "Approve creates it." in body
        buttons = card["interactive"]["action"]["buttons"]
        assert [b["reply"]["title"] for b in buttons] == ["Approve", "Reject"]
        assert not (user / "Desktop" / "todo.txt").exists()
        tap(c, buttons[0]["reply"]["id"], "wamid.tap")
        done = wait_for(sent, 3)[2]["text"]["body"]
        assert done.startswith("Done on your PC: Created:") and (user / "Desktop" / "todo.txt").read_text() == "call Ali\n"


@pytest.mark.parametrize("mode,expected", [("ask_all", "waiting"), ("rules", "posted")])
def test_whatsapp_own_mode_controls_action_independent_of_dashboard(wa, mode, expected):
    from junior.permissions import set_mode, set_rule
    from junior.settings_store import set_setting
    sent, user = wa
    model = ScriptedModel([
        ModelStep(output=[function_call("ask_computer_agent", {"task": "make mode.txt on my Desktop: hello"}, call_id="c1")]),
        ModelStep(output=[function_call("pc_write", {"file": "Desktop/mode.txt", "content": "hello"}, call_id="c2")]),
        ModelStep(output=[assistant_message("Action processed.")]),
        chunked_answer("Action processed."),
    ])
    with app(model) as c:
        set_mode("rules")
        set_rule("computer.write", "auto")
        set_setting("whatsapp_action_mode", mode)
        signed(c, text("Make mode.txt on my Desktop: hello"))
        wait_for(sent, 1)
        cards = c.get("/api/approvals?status=all").json()
        assert cards[0]["status"] == expected and cards[0]["meta"]["origin_channel"] == "whatsapp"
        assert (user / "Desktop" / "mode.txt").exists() == (expected == "posted")


def test_a_command_from_whatsapp_sends_its_output_back(wa):
    sent, user = wa
    model = ScriptedModel([
        ModelStep(output=[function_call("ask_computer_agent", {"task": "run echo on my Desktop"}, call_id="c1")]),
        ModelStep(output=[function_call("pc_run", {"command": "Write-Output 'hi from your PC'", "folder": "Desktop"}, call_id="c2")]),
        ModelStep(output=[assistant_message("A command card waits.")]),
        chunked_answer("Tap Approve to run it."),
    ])
    with app(model) as c:
        signed(c, text("Junior, run echo on my Desktop"))
        card = wait_for(sent, 2)[1]
        assert "Your PC: run this command in" in card["interactive"]["body"]["text"]
        assert "Approve runs it; the output comes back here." in card["interactive"]["body"]["text"]
        tap(c, card["interactive"]["action"]["buttons"][0]["reply"]["id"], "wamid.tap2")
        done = wait_for(sent, 3, seconds=30)[2]["text"]["body"]
        assert done.startswith("Done on your PC: Finished (exit code 0).") and "hi from your PC" in done


def test_reject_from_whatsapp_changes_nothing(wa):
    sent, user = wa
    model = ScriptedModel([
        ModelStep(output=[function_call("ask_computer_agent", {"task": "delete notes"}, call_id="c1")]),
        ModelStep(output=[function_call("pc_write", {"file": "Desktop/x.txt", "content": "x"}, call_id="c2")]),
        ModelStep(output=[assistant_message("Card made.")]),
        chunked_answer("Ready."),
    ])
    with app(model) as c:
        signed(c, text("Junior, make x.txt"))
        card = wait_for(sent, 2)[1]
        tap(c, card["interactive"]["action"]["buttons"][1]["reply"]["id"], "wamid.no")
        assert wait_for(sent, 3)[2]["text"]["body"].startswith("Rejected")
    assert not (user / "Desktop" / "x.txt").exists()


def test_approved_on_the_dashboard_the_result_still_goes_to_whatsapp(wa):
    sent, user = wa
    model = ScriptedModel([
        ModelStep(output=[function_call("ask_computer_agent", {"task": "make a.txt"}, call_id="c1")]),
        ModelStep(output=[function_call("pc_write", {"file": "Desktop/a.txt", "content": "a\n"}, call_id="c2")]),
        ModelStep(output=[assistant_message("Card made.")]),
        chunked_answer("Ready."),
    ])
    with app(model) as c:
        signed(c, text("Junior, make a.txt on my Desktop"))
        card = wait_for(sent, 2)[1]
        item_id = int(card["interactive"]["action"]["buttons"][0]["reply"]["id"].split(":")[1])
        c.post(f"/api/approvals/{item_id}/approve", json={})
        assert wait_for(sent, 3)[2]["text"]["body"].startswith("Done on your PC: Created:")


def test_send_me_a_file_from_my_pc(wa):
    sent, user = wa
    (user / "Downloads" / "CV.pdf").write_bytes(b"%PDF-1.4 my cv")
    model = ScriptedModel([
        ModelStep(output=[function_call("send_to_me", {
            "where": "whatsapp", "subject": "Your CV", "message": "Here's your CV.",
            "your_words": "WhatsApp me my CV from Downloads", "pc_file": "Downloads/CV.pdf"}, call_id="s1")]),
        chunked_answer("Sent your CV here."),
    ])
    with app(model) as c:
        # This test exercises the automatic delivery rule; WhatsApp now defaults to Manual.
        from junior.settings_store import set_setting
        set_setting("whatsapp_action_mode", "rules")
        signed(c, text("WhatsApp me my CV from Downloads"))
        got = wait_for(sent, 4)
        upload = next(m for m in got if "upload" in m)["upload"]
        assert b"%PDF-1.4 my cv" in upload and b"application/pdf" in upload
        document = next(m for m in got if m.get("type") == "document")
        assert document["document"]["filename"] == "CV.pdf"


def test_song_from_whatsapp_asks_once_and_starts_on_approval(wa, monkeypatch):
    sent, _ = wa
    monkeypatch.setenv("FAKE_AI", "true")
    get_settings.cache_clear()
    with app(ScriptedModel()) as c:
        c.put("/api/computer/browser", json={"enabled": True, "sites": ["*"]})
        signed(c, text("song play kro yr blue eyes yo yo honey sing wala"))
        got = wait_for(sent, 2)
        card = next(message for message in got if message.get("type") == "interactive")
        button = card["interactive"]["action"]["buttons"][0]["reply"]["id"]
        tap(c, button, "wamid.music-approve")
        assert any("Simulated playback" in message.get("text", {}).get("body", "") for message in wait_for(sent, 3))


def test_a_secret_or_outside_file_is_never_sent(wa):
    sent, user = wa
    (user / "Desktop" / ".env").write_text("KEY=1")
    model = ScriptedModel([
        ModelStep(output=[function_call("send_to_me", {
            "where": "whatsapp", "subject": "env", "message": "here", "your_words": "WhatsApp me the env file",
            "pc_file": "Desktop/.env"}, call_id="s1")]),
        chunked_answer("I can't send that one."),
    ])
    with app(model) as c:
        signed(c, text("WhatsApp me the env file"))
        got = wait_for(sent, 1)
    assert all("upload" not in m and m.get("type") != "document" for m in got)
    assert got[-1]["text"]["body"] == "I can't send that one."
