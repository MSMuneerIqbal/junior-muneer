"""P9-06: the Computer Agent. Junior hands it PC jobs; it shares the turn (its cards show in the chat, a path you
typed counts); only it has the tools that change things; Junior has the quick read-only ones."""

import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, chunked_answer, function_call
from junior.computer import paths
from junior.main import create_app
from junior.registry import load_registry
from junior.settings_store import set_setting
from agents.testing import ModelStep, assistant_message


@pytest.fixture
def home(tmp_path, monkeypatch):
    user = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads", "Projects/shop"):
        (user / name).mkdir(parents=True)
    (user / "Desktop" / "notes.txt").write_text("hello")
    monkeypatch.setattr(paths, "home", lambda: user)
    return user


def chat(client, text):
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "message", "conversation_id": None, "text": text})
        events = []
        while True:
            events.append(ws.receive_json())
            if events[-1]["type"] in ("done", "error"):
                return events


def step(*output):
    return ModelStep(output=list(output))


def test_junior_hands_a_change_to_the_computer_agent_and_the_card_shows_in_chat(home):
    model = ScriptedModel([
        step(function_call("ask_computer_agent", {"task": "make plan.txt on my Desktop saying gym at 6"}, call_id="c1")),
        step(function_call("pc_write", {"file": "Desktop/plan.txt", "content": "gym at 6\n"}, call_id="c2")),
        step(assistant_message("A card to create Desktop\\plan.txt waits for their OK.")),
        chunked_answer("I've made a card for plan.txt: press Approve and it's on your Desktop."),
    ])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as client:
        events = chat(client, "Junior, make plan.txt on my Desktop saying gym at 6")
        assert events[-1]["type"] == "done" and "press Approve" in events[-1]["text"]
        cards = [e["item"] for e in events if e["type"] == "approval"]
        assert len(cards) == 1 and cards[0]["platform"] == "computer" and cards[0]["text"] == "gym at 6\n"
        assert not (home / "Desktop" / "plan.txt").exists()  # nothing until Approve
        labels = [e.get("label") for e in events if e["type"] == "step"]
        assert "Asking the Computer Agent" in labels
        client.post(f"/api/approvals/{cards[0]['id']}/approve", json={})
        assert (home / "Desktop" / "plan.txt").read_text() == "gym at 6\n"


def test_a_path_you_typed_works_for_the_computer_agent_too(home):
    shop = home / "Projects" / "shop"
    model = ScriptedModel([
        step(function_call("ask_computer_agent", {"task": f"list {shop}"}, call_id="c1")),
        step(function_call("pc_list", {"folder": str(shop)}, call_id="c2")),
        step(assistant_message("It's empty.")),
        chunked_answer("That folder is empty."),
    ])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as client:
        events = chat(client, f"Junior, what's in {shop}?")
    assert events[-1]["text"] == "That folder is empty."
    tool_output = model.calls[2]  # the Computer Agent saw pc_list's answer
    assert "outside the allowed folders" not in str(tool_output)


def test_turned_off_means_the_agent_isnt_even_asked(home):
    model = ScriptedModel([
        step(function_call("ask_computer_agent", {"task": "list Desktop"}, call_id="c1")),
        chunked_answer("The computer tools are off."),
    ])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as client:
        set_setting("computer_enabled", False)
        events = chat(client, "Junior, list my Desktop")
    assert events[-1]["text"] == "The computer tools are off." and len(model.calls) == 2  # no Computer Agent run


def test_only_the_computer_agent_can_change_things_and_junior_can_only_look():
    registry = load_registry()
    agent = registry.get("computer_agent")
    assert agent.tools == ("computer", "skills")
    assert set(agent.action_types) == {"computer.write", "computer.move", "computer.delete", "computer.run"}
    junior = registry.get("junior_muneer")
    assert "computer_read" in junior.tools and "computer_agent" in junior.tools and "computer" not in junior.tools
    for name in registry.names():
        if name != "computer_agent":
            assert "computer" not in registry.get(name).tools, name  # least power: nobody else changes your PC
