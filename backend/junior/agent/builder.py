"""Turns an agent file into a runnable OpenAI Agents SDK agent."""

from collections.abc import Callable

from agents import Agent, Model, OpenAIChatCompletionsModel, OpenAIResponsesModel, RunContextWrapper
from openai import AsyncOpenAI

from junior.agent.context import TurnContext
from junior.agent.tools import build_tools
from junior.config import get_settings
from junior.memories import memories_for_prompt
from junior.models import ModelRouter, get_router
from junior.registry import AgentSpec
from junior.timeutil import local_now_text

# Gives the SDK model object for a model name. Tests swap in a fake one.
ModelProvider = Callable[[str], Model]

LANGUAGE_RULES = {
    "match": "match me: reply in the language and script of my latest message",
    "english": "always reply in English",
    "urdu": "always reply in Urdu, in the script I use (Urdu script or Roman Urdu)",
}


PAUSED_NOTE = (
    "PAUSE IS ON: {name} pressed 'Pause everything'. Background work and actions are "
    "stopped; chatting still works. Mention it briefly at the start of your answer, "
    "and say they can resume with the Pause button."
)
RUNNING_NOTE = "Status: running normally."


class NoApiKeyError(RuntimeError):
    pass


def openai_model_provider() -> ModelProvider:
    """Gives the SDK model for any model name: OpenAI ones, or 'provider:model'
    (e.g. 'deepseek:deepseek-flash') through that provider's OpenAI-style API."""
    settings = get_settings()
    key = settings.openai_api_key
    if not key:
        raise NoApiKeyError(
            "No OpenAI API key yet. Paste it into backend/.env as OPENAI_API_KEY=... "
            "and restart the backend."
        )
    openai_client = AsyncOpenAI(api_key=key)
    clients: dict[str, AsyncOpenAI] = {}

    def provide(name: str) -> Model:
        provider = ModelRouter.provider_of(name)
        if provider == "openai":
            return OpenAIResponsesModel(model=name, openai_client=openai_client)
        info = get_router().providers.get(provider)
        if info is None:
            raise NoApiKeyError(f"Unknown model provider {provider!r} in agents/models.toml.")
        if provider not in clients:
            provider_key = getattr(settings, info["key_env"].lower(), "")
            if not provider_key:
                raise NoApiKeyError(
                    f"No {info.get('label', provider)} API key yet. Paste it into backend/.env as "
                    f"{info['key_env']}=... and restart the backend, or switch the model back "
                    "to OpenAI in Settings -> Models."
                )
            clients[provider] = AsyncOpenAI(api_key=provider_key, base_url=info["base_url"])
        return OpenAIChatCompletionsModel(model=ModelRouter.bare(name), openai_client=clients[provider])

    return provide


def render_instructions(spec: AgentSpec, s: dict) -> str:
    """An agent's instructions with your name, language, time, memories and status filled in."""
    return spec.render(
        user_name=s["user_name"],
        language=LANGUAGE_RULES.get(s["language"], LANGUAGE_RULES["match"]),
        timezone=s["timezone"],
        now=local_now_text(s["timezone"]),
        memories=memories_for_prompt() if "memory" in spec.tools else "",
        status=PAUSED_NOTE.format(name=s["user_name"]) if s.get("paused") else RUNNING_NOTE,
    )


# Agents whose model you can choose in Settings -> Models, and the setting for each.
CHOOSABLE = {"junior_muneer": "main_model", "summarizer": "helper_model"}


def chosen_model(spec: AgentSpec, router: ModelRouter) -> str:
    """Your choice in Settings if there is one, else agents/models.toml."""
    default = router.model_for(spec.name, spec.model)
    setting = CHOOSABLE.get(spec.name)
    if setting is None:
        return default
    from junior.settings_store import get_setting

    choice = get_setting(setting)
    return choice if choice and choice in router.prices else default


def build_agent(
    spec: AgentSpec, router: ModelRouter, model_provider: ModelProvider
) -> tuple[Agent[TurnContext], str]:
    """The SDK agent and the model name it uses."""
    model_name = chosen_model(spec, router)

    def instructions(ctx: RunContextWrapper[TurnContext], _agent: Agent[TurnContext]) -> str:
        return render_instructions(spec, ctx.context.settings)

    agent = Agent[TurnContext](
        name=spec.name,
        instructions=instructions,
        model=model_provider(model_name),
        tools=build_tools(spec.tools),
    )
    return agent, model_name
