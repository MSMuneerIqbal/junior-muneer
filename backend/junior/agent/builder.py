"""Turns an agent file into a runnable OpenAI Agents SDK agent."""

from collections.abc import Callable

from agents import Agent, Model, ModelSettings, OpenAIChatCompletionsModel, OpenAIResponsesModel, RunContextWrapper
from openai import AsyncOpenAI

from junior.agent.context import TurnContext
from junior.agent.style import mode_note
from junior.agent.tools import build_tools
from junior.ai_client import ai_client
from junior.config import get_settings
from junior.memories import memories_for_prompt
from junior.profile import profile_for_chat
from junior.models import ModelRouter, get_router
from junior.registry import AgentSpec
from junior.timeutil import local_now_text

# Gives the SDK model object for a model name. Tests swap in a fake one.
ModelProvider = Callable[[str], Model]

LANGUAGE_RULES = {
    "match": "match me: reply in the language and script of my latest message",
    "english": "reply in easy, everyday English (use Urdu only when I ask for it in that message)",
    "urdu": "always reply in Urdu, in the script I use (Urdu script or Roman Urdu)",
}


PAUSED_NOTE = (
    "PAUSE IS ON: {name} pressed 'Pause everything'. Background work and actions are "
    "stopped; chatting still works. Mention it briefly at the start of your answer, "
    "and say they can resume with the Pause button."
)
RUNNING_NOTE = "Status: running normally."
PLAN_NOTE = (
    "PLAN MODE IS ON: for anything beyond a simple answer (writing drafts, queueing items, "
    "multi-step tasks), first reply with a short numbered plan of what you'd do, and ask "
    "{name} to switch the mode under the message box to Auto or Manual to go ahead. Don't "
    "draft or queue anything yet. Chatting and answering questions work as usual."
)


class NoApiKeyError(RuntimeError):
    pass


class CountedChatModel(OpenAIChatCompletionsModel):
    """A non-OpenAI chat model that always asks for token counts while streaming.
    DeepSeek sends them anyway; Gemini only when asked, or its cost shows as $0."""

    @staticmethod
    def _counted(model_settings: ModelSettings) -> ModelSettings:
        if model_settings.include_usage is None:
            return model_settings.resolve(ModelSettings(include_usage=True))
        return model_settings

    async def get_response(self, system_instructions, input, model_settings, *args, **kwargs):
        return await super().get_response(system_instructions, input, self._counted(model_settings), *args, **kwargs)

    def stream_response(self, system_instructions, input, model_settings, *args, **kwargs):
        return super().stream_response(system_instructions, input, self._counted(model_settings), *args, **kwargs)


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
    openai_client = ai_client(key)
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
            clients[provider] = ai_client(provider_key, base_url=info["base_url"])
        return CountedChatModel(model=ModelRouter.bare(name), openai_client=clients[provider])

    return provide


def render_instructions(spec: AgentSpec, s: dict, query: str = "") -> str:
    """An agent's instructions with your name, language, time, memories and status filled in.
    `query` (your message) picks the older memories that fit it, when there are many."""
    return spec.render(
        user_name=s["user_name"],
        language=LANGUAGE_RULES.get(s["language"], LANGUAGE_RULES["match"]),
        timezone=s["timezone"],
        now=local_now_text(s["timezone"]),
        memories=memories_for_prompt(query, s["timezone"]) if "memory" in spec.tools else "",
        profile=profile_for_chat() if "{{profile}}" in spec.instructions else "",
        status=_status(s),
        mode=mode_note(query),
        skills=_skills_for(spec) if "{{skills}}" in spec.instructions else "",
    )


def _skills_for(spec: AgentSpec) -> str:
    from junior.skills import skills_list

    return skills_list(spec.name)


def _status(s: dict) -> str:
    notes = [PAUSED_NOTE if s.get("paused") else RUNNING_NOTE]
    if s.get("permission_mode") == "plan":
        notes.append(PLAN_NOTE)
    return "\n- ".join(n.format(name=s["user_name"]) for n in notes)


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
    spec: AgentSpec,
    router: ModelRouter,
    model_provider: ModelProvider,
    model_override: str | None = None,
    output_type: type | None = None,
) -> tuple[Agent[TurnContext], str]:
    """The SDK agent and the model name it uses (with a structured answer if output_type is set)."""
    model_name = model_override or chosen_model(spec, router)

    def instructions(ctx: RunContextWrapper[TurnContext], _agent: Agent[TurnContext]) -> str:
        return render_instructions(spec, ctx.context.settings, ctx.context.user_text)

    from junior.settings_store import get_setting
    agent = Agent[TurnContext](
        name=spec.name,
        instructions=instructions,
        model=model_provider(model_name),
        model_settings=ModelSettings(max_tokens=get_setting("max_output_tokens")),
        tools=build_tools(spec.tools, spec.name),
        output_type=output_type,
    )
    return agent, model_name
