import pytest

from junior.registry import AgentFileError, load_registry, parse_agent_file

GOOD = """---
name: helper
description: Helps with things.
model: small
tools: [web_search]
action_types: [gmail.send]
---
Be helpful, {{user_name}}. Keep {{unknown}}.
"""


def test_real_registry_lists_junior_muneer():
    registry = load_registry()
    assert "junior_muneer" in registry.names()
    jm = registry.get("junior_muneer")
    assert jm.model == "strong"
    assert "web_search" in jm.tools
    assert "Junior Muneer" in jm.instructions


def test_parses_a_good_file():
    spec = parse_agent_file(GOOD, "helper.md")
    assert spec.name == "helper"
    assert spec.model == "small"
    assert spec.tools == ("web_search",)
    assert spec.action_types == ("gmail.send",)


def test_render_fills_placeholders():
    spec = parse_agent_file(GOOD, "helper.md")
    assert spec.render(user_name="Muneer") == "Be helpful, Muneer. Keep {{unknown}}."


def test_windows_line_endings_are_fine():
    assert parse_agent_file(GOOD.replace("\n", "\r\n"), "helper.md").name == "helper"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no header here", "must start with a header"),
        ("---\nname: [unclosed\n---\nx", "not valid YAML"),
        (GOOD.replace("name: helper", "name: Helper!"), "'name' must be"),
        (GOOD, "they must match"),  # parsed as other.md
        (GOOD.replace("description: Helps with things.", "description: ''"), "'description'"),
        (GOOD.replace("[web_search]", "[click_everything]"), "unknown tool"),
        (GOOD.replace("[gmail.send]", "[send]"), "bad action type"),
        (GOOD.replace("tools: [web_search]", "tools: web_search"), "must be a list"),
        (GOOD.replace("model: small", "colour: blue"), "unknown header field"),
        (GOOD.split("---\n", 2)[0] + "---\n" + GOOD.split("---\n", 2)[1] + "---\n  \n", "empty"),
    ],
)
def test_broken_files_give_a_clear_error(text, message):
    filename = "other.md" if message == "they must match" else "helper.md"
    with pytest.raises(AgentFileError) as err:
        parse_agent_file(text, filename)
    assert message in str(err.value)
    assert filename in str(err.value)


def test_a_broken_file_stops_loading(tmp_path):
    (tmp_path / "junior_muneer.md").write_text(GOOD.replace("helper", "junior_muneer"))
    (tmp_path / "broken.md").write_text("oops")
    with pytest.raises(AgentFileError, match="broken.md"):
        load_registry(tmp_path)


def test_junior_muneer_is_required(tmp_path):
    (tmp_path / "helper.md").write_text(GOOD)
    with pytest.raises(AgentFileError, match="junior_muneer.md is missing"):
        load_registry(tmp_path)


def test_readme_is_not_an_agent(tmp_path):
    (tmp_path / "junior_muneer.md").write_text(GOOD.replace("helper", "junior_muneer"))
    (tmp_path / "README.md").write_text("# Agents")
    assert load_registry(tmp_path).names() == ["junior_muneer"]
