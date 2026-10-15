"""Agent registry: loads every agent file in agents/.

An agent file is Markdown with a YAML header, like a Claude Code subagent:

    ---
    name: junior_muneer
    description: When Junior Muneer should call this agent.
    model: strong          # "strong", "small" or an exact model; agents/models.toml can override
    tools: [web_search]    # only tools the backend knows
    action_types: []       # outgoing actions it may request (Ask / Auto / Deny rules)
    ---
    The instructions, as plain text.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from junior.config import REPO_DIR

log = logging.getLogger(__name__)

AGENTS_DIR = REPO_DIR / "agents"
# Tools an agent file may ask for. Grows as tools are added.
KNOWN_TOOLS = frozenset({"web_search", "hosted_web_search", "database", "memory", "approvals", "writing"})
NOT_AGENT_FILES = {"README.md"}

_NAME = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
_ACTION_TYPE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_HEADER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_FIELDS = {"name", "description", "model", "tools", "action_types"}


class AgentFileError(Exception):
    """An agent file is broken. The message names the file and the problem."""


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    instructions: str
    model: str = "strong"
    tools: tuple[str, ...] = ()
    action_types: tuple[str, ...] = ()
    path: Path | None = field(default=None, compare=False)

    def render(self, **values: str) -> str:
        """Instructions with {{placeholders}} filled in. Unknown ones stay as they are."""
        return re.sub(
            r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), self.instructions
        )


def parse_agent_file(text: str, filename: str, known_tools=KNOWN_TOOLS) -> AgentSpec:
    def fail(msg: str) -> AgentFileError:
        return AgentFileError(f"agents/{filename}: {msg}")

    match = _HEADER.match(text.replace("\r\n", "\n"))
    if not match:
        raise fail("must start with a header between two '---' lines.")
    try:
        header = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise fail(f"the header is not valid YAML: {e}") from None
    if not isinstance(header, dict):
        raise fail("the header must be 'key: value' lines.")

    unknown = set(header) - _FIELDS
    if unknown:
        raise fail(f"unknown header field(s) {sorted(unknown)}; allowed: {sorted(_FIELDS)}.")

    name = header.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise fail("'name' must be lowercase letters, digits and _ (e.g. social_manager).")
    stem = Path(filename).stem
    if name != stem:
        raise fail(f"'name' is {name!r} but the file is called {filename}; they must match.")

    description = header.get("description")
    if not isinstance(description, str) or not description.strip():
        raise fail("'description' is required; Junior Muneer reads it to decide when to call.")

    model = header.get("model", "strong")
    if not isinstance(model, str) or not model.strip():
        raise fail("'model' must be 'strong', 'small' or a model name.")

    def str_list(key: str) -> tuple[str, ...]:
        value = header.get(key) or []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise fail(f"'{key}' must be a list, e.g. {key}: [a, b].")
        return tuple(value)

    tools = str_list("tools")
    bad_tools = sorted(set(tools) - set(known_tools))
    if bad_tools:
        raise fail(f"unknown tool(s) {bad_tools}; known tools: {sorted(known_tools)}.")

    action_types = str_list("action_types")
    bad_actions = [a for a in action_types if not _ACTION_TYPE.match(a)]
    if bad_actions:
        raise fail(f"bad action type(s) {bad_actions}; use dotted names like gmail.send.")

    instructions = match.group(2).strip()
    if not instructions:
        raise fail("the instructions (text below the header) are empty.")

    return AgentSpec(
        name=name,
        description=description.strip(),
        instructions=instructions,
        model=model.strip(),
        tools=tools,
        action_types=action_types,
    )


@dataclass(frozen=True)
class Registry:
    agents: dict[str, AgentSpec]

    def get(self, name: str) -> AgentSpec:
        try:
            return self.agents[name]
        except KeyError:
            raise KeyError(f"No agent called {name!r}. Known: {sorted(self.agents)}") from None

    def names(self) -> list[str]:
        return sorted(self.agents)


def load_registry(directory: Path = AGENTS_DIR, known_tools=KNOWN_TOOLS) -> Registry:
    """Load every agent file. One broken file stops loading with a clear error."""
    agents: dict[str, AgentSpec] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name in NOT_AGENT_FILES:
            continue
        spec = parse_agent_file(path.read_text(encoding="utf-8"), path.name, known_tools)
        agents[spec.name] = AgentSpec(**{**spec.__dict__, "path": path})
    if "junior_muneer" not in agents:
        raise AgentFileError(f"agents/junior_muneer.md is missing (looked in {directory}).")
    log.info("Agent registry loaded: %s", ", ".join(sorted(agents)))
    return Registry(agents)
