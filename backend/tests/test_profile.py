import pytest
from fastapi.testclient import TestClient

from junior.main import create_app
from junior.profile import ProfileMissing, profile_text


@pytest.fixture
def client():
    with TestClient(create_app(model_provider=lambda: (lambda n: None))) as c:
        yield c


def test_empty_profile_gives_a_clear_message(client):
    assert client.get("/api/profile").json()["headline"] == ""
    with pytest.raises(ProfileMissing, match="Fill it in on the Profile page"):
        profile_text()


def test_save_and_use_profile(client):
    saved = client.put(
        "/api/profile",
        json={
            "headline": "Full-stack developer (Next.js, Python)",
            "services": ["Next.js websites", "  ", "AI chatbots"],
            "proof": ["Built a shoe store in Next.js that cut page load from 4 s to 1 s"],
            "hashtags": ["nextjs", "#python"],
            "platforms": ["linkedin", "x", "myspace"],
        },
    ).json()
    assert saved["services"] == ["Next.js websites", "AI chatbots"]  # blanks removed
    assert saved["platforms"] == ["linkedin", "x"]  # unknown platforms removed
    text = profile_text()
    assert "Name: Muneer" in text
    assert "What I do: Full-stack developer" in text
    assert "the ONLY facts you may use" in text and "4 s to 1 s" in text
    assert "#nextjs #python" in text
    assert client.get("/api/profile").json()["headline"].startswith("Full-stack")
    assert "profile" not in client.get("/api/settings").json()  # not mixed into Settings
    assert client.get("/api/activity?kind=setting").json()[0]["name"] == "profile"


def test_too_long_is_refused(client):
    assert client.put("/api/profile", json={"headline": "x" * 201}).status_code == 422


def test_junior_muneer_knows_your_profile_in_chat(client):
    from fake_ai import ScriptedModel, chunked_answer

    client.put(
        "/api/profile",
        json={"headline": "Agentic AI Engineer", "proof": ["MS Data Science (in progress)"],
              "email": "me@example.com", "location": "Lahore, Pakistan", "languages": ["English", "Urdu"]},
    )
    model = ScriptedModel([chunked_answer("Sure!")])
    with TestClient(create_app(model_provider=lambda: (lambda n: model))) as c:
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"type": "message", "conversation_id": None, "text": "What should I study next?"})
            while ws.receive_json()["type"] not in ("done", "error"):
                pass
    prompt = model.last_call.system_instructions
    assert "Who Muneer is (their profile)" in prompt
    assert "What I do: Agentic AI Engineer" in prompt and "MS Data Science" in prompt
    assert "Location: Lahore, Pakistan" in prompt and "Languages: English, Urdu" in prompt
    assert "me@example.com" not in prompt  # contact details stay out of prompts


def test_without_a_profile_he_suggests_filling_it(client):
    from junior.profile import profile_for_chat

    assert "Profile page" in profile_for_chat()
