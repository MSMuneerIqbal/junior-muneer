"""Turns an agent file into a runnable OpenAI Agents SDK agent."""

from collections.abc import Callable

from agents import Agent, Model, OpenAIResponsesModel, RunContextWrapper
from openai import AsyncOpenAI

from junior.agent.context import TurnContext
from junior.agent.tools import build_tools
from junior.config import get_settings
from junior.memories import memories_for_prompt
from junior.models import ModelRouter
from junior.registry import AgentSpec
from junior.timeutil import local_now_text

# Gives the SDK model object for a model name. Tests swap in a fake one.
ModelProvider = Callable[[str], Model]

LANGUAGE_RULES = {
    "match": "match me: reply in the language and script of my latest message",
    "english": "always reply in English",
    "urdu": "always reply in Urdu, in the script I use (Urdu script or Roman Urdu)",
}


class NoApiKeyError(RuntimeError):
    pass


def openai_model_provider() -> ModelProvider:
    key = get_settings().openai_api_key
    if not key:
        raise NoApiKeyError(
            "No OpenAI API key yet. Paste it into backend/.env as OPENAI_API_KEY=... "
            "and restart the backend."
        )
    client = AsyncOpenAI(api_key=key)
    return lambda name: OpenAIResponsesModel(model=name, openai_client=client)


def build_agent(
    spec: AgentSpec, router: ModelRouter, model_provider: ModelProvider
) -> tuple[Agent[TurnContext], str]:
    """The SDK agent and the model name it uses."""
    model_name = router.model_for(spec.name, spec.model)

    def instructions(ctx: RunContextWrapper[TurnContext], _agent: Agent[TurnContext]) -> str:
        s = ctx.context.settings
        return spec.render(
            user_name=s["user_name"],
            language=LANGUAGE_RULES.get(s["language"], LANGUAGE_RULES["match"]),
            timezone=s["timezone"],
            now=local_now_text(s["timezone"]),
            memories=memories_for_prompt() if "memory" in spec.tools else "",
        )

    agent = Agent[TurnContext](
        name=spec.name,
        instructions=instructions,
        model=model_provider(model_name),
        tools=build_tools(spec.tools),
    )
    return agent, model_name
