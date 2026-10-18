"""How he talks: "Junior ..." means work (Junior mode), anything else is a friend chatting; never emojis."""

import pytest
from fastapi.testclient import TestClient

from fake_ai import ScriptedModel, assistant_message
from junior.agent.builder import render_instructions
from junior.agent.style import FRIEND_MODE, JUNIOR_MODE, no_emojis, talk_mode
from junior.main import create_app
from junior.registry import load_registry
from junior.settings_store import all_settings


@pytest.mark.parametrize(
    "text",
    ["Junior send me my CV", "junior, add my exam", "  JUNIOR: do this", "hey junior find the invoice", "@junior read it",
     "[file 3: CV.pdf (PDF, 52 KB)]\njunior save it to my drive", "جونیئر میرا سی وی بھیجو"],
)
def test_junior_at_the_start_is_work(text):
    assert talk_mode(text) == "junior"


@pytest.mark.parametrize(
    "text",
    ["how are you yaar", "send me my CV", "my junior colleague said hi", "juniors are lucky", "",
     "[file 3: CV.pdf (PDF, 52 KB)]\n(I sent this file without saying what to do with it.)"],
)
def test_anything_else_is_a_friend_chatting(text):
    assert talk_mode(text) == "friend"


def test_the_mode_goes_into_his_instructions():
    spec = load_registry().get("junior_muneer")
    with TestClient(create_app()):
        settings = all_settings()
        assert JUNIOR_MODE in render_instructions(spec, settings, "Junior, make a doc")
        friendly = render_instructions(spec, settings, "kya haal hai")
        assert FRIEND_MODE in friendly and JUNIOR_MODE not in friendly
        assert "Never use emojis" in friendly


def test_emojis_are_removed_but_urdu_arrows_and_punctuation_stay():
    assert no_emojis("Done! 🎉 Your CV is sent ✅👍🏽") == "Done!  Your CV is sent "
    assert no_emojis("👨‍💻 coding ❤️ time") == " coding  time"
    assert no_emojis("سلام دوست → next step: 5 - 3 = 2 (ok)") == "سلام دوست → next step: 5 - 3 = 2 (ok)"


def test_his_answer_never_has_emojis():
    model = ScriptedModel([[assistant_message("Hey Muneer! 😄 All good here 🙌  How was your day?")]])
    with TestClient(create_app(model_provider=lambda: (lambda _n: model))) as c:
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "hey"})
            while (event := ws.receive_json())["type"] != "done":
                if event["type"] == "delta":
                    assert not any(ch in event["text"] for ch in "😄🙌")
        assert event["text"] == "Hey Muneer! All good here How was your day?"
