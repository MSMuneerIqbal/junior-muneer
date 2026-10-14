"""Model router: reads agents/models.toml and says which model each agent uses."""

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from junior.config import REPO_DIR

log = logging.getLogger(__name__)

MODELS_FILE = REPO_DIR / "agents" / "models.toml"
TIERS = ("strong", "small")


class ModelConfigError(Exception):
    """agents/models.toml is missing or wrong. The message says how to fix it."""


@dataclass(frozen=True)
class Price:
    """US dollars per 1 million tokens."""

    input: float
    cached_input: float
    output: float

    def cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float:
        uncached = max(input_tokens - cached_input_tokens, 0)
        return (
            uncached * self.input
            + cached_input_tokens * self.cached_input
            + output_tokens * self.output
        ) / 1_000_000


@dataclass(frozen=True)
class ModelRouter:
    tiers: dict[str, str]
    agents: dict[str, str] = field(default_factory=dict)
    prices: dict[str, Price] = field(default_factory=dict)
    tool_prices: dict[str, float] = field(default_factory=dict)
    # Voice: which model does what (transcribe, speech, realtime), and their prices.
    audio: dict[str, str] = field(default_factory=dict)
    audio_prices: dict[str, dict[str, float]] = field(default_factory=dict)

    def audio_model(self, job: str) -> str:
        try:
            return self.audio[job]
        except KeyError:
            raise ModelConfigError(
                f'{MODELS_FILE.name}: [audio] needs {job} = "<model name>".'
            ) from None

    def audio_price(self, model: str) -> dict[str, float]:
        try:
            return self.audio_prices[model]
        except KeyError:
            raise ModelConfigError(
                f'No price for audio model "{model}" in {MODELS_FILE.name}. '
                f'Add an [audio_prices."{model}"] section.'
            ) from None

    def model_for(self, agent: str, default_tier: str = "strong") -> str:
        """The model for an agent: its override in [agents], else its own tier."""
        choice = self.agents.get(agent, default_tier)
        return self.tiers.get(choice, choice)

    def price(self, model: str) -> Price:
        try:
            return self.prices[model]
        except KeyError:
            raise ModelConfigError(
                f'No price for model "{model}" in {MODELS_FILE.name}. '
                f'Add a [prices."{model}"] section.'
            ) from None


def parse_router(text: str, source: str = MODELS_FILE.name) -> ModelRouter:
    """Read and check the router file. Raises ModelConfigError with a clear message."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ModelConfigError(f"{source} is not valid TOML: {e}") from None

    def fail(msg: str) -> ModelConfigError:
        return ModelConfigError(f"{source}: {msg}")

    tiers = data.get("tiers")
    if not isinstance(tiers, dict):
        raise fail("missing the [tiers] section (strong = ..., small = ...).")
    for tier in TIERS:
        if not isinstance(tiers.get(tier), str) or not tiers[tier].strip():
            raise fail(f'[tiers] needs {tier} = "<model name>".')
    unknown = set(tiers) - set(TIERS)
    if unknown:
        raise fail(f"[tiers] has unknown tier(s) {sorted(unknown)}; only {list(TIERS)} exist.")

    agents = data.get("agents", {})
    if not isinstance(agents, dict) or not all(
        isinstance(v, str) and v.strip() for v in agents.values()
    ):
        raise fail('every entry in [agents] must be  name = "strong", "small" or "<model>".')

    prices: dict[str, Price] = {}
    for model, p in data.get("prices", {}).items():
        try:
            prices[model] = Price(
                input=float(p["input"]),
                cached_input=float(p.get("cached_input", p["input"])),
                output=float(p["output"]),
            )
        except (KeyError, TypeError, ValueError):
            raise fail(f'[prices."{model}"] needs numbers for input and output.') from None

    tool_prices = {k: float(v) for k, v in data.get("tool_prices", {}).items()}
    audio = data.get("audio", {})
    if not isinstance(audio, dict) or not all(isinstance(v, str) and v for v in audio.values()):
        raise fail('[audio] entries must be  job = "<model name>".')
    try:
        audio_prices = {
            m: {k: float(v) for k, v in p.items()} for m, p in data.get("audio_prices", {}).items()
        }
    except (AttributeError, TypeError, ValueError):
        raise fail("[audio_prices] values must be numbers.") from None
    missing_audio = sorted(m for m in audio.values() if m not in audio_prices)
    if missing_audio:
        raise fail(f'no price for audio model(s) {missing_audio}. Add [audio_prices."<model>"].')
    router = ModelRouter(
        tiers=dict(tiers),
        agents=dict(agents),
        prices=prices,
        tool_prices=tool_prices,
        audio=dict(audio),
        audio_prices=audio_prices,
    )

    used = set(tiers.values()) | {router.model_for(a) for a in agents}
    missing = sorted(m for m in used if m not in prices)
    if missing:
        raise fail(
            f'no price for {missing}. Add a [prices."<model>"] section for each, '
            "so the daily cost cap works."
        )
    return router


class _RouterCache:
    """Re-reads the file when it changes, so edits apply without a restart."""

    def __init__(self) -> None:
        self._key: tuple[Path, float] | None = None
        self._router: ModelRouter | None = None

    def get(self, path: Path) -> ModelRouter:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            raise ModelConfigError(f"Model router file not found: {path}") from None
        if self._key != (path, mtime) or self._router is None:
            self._router = parse_router(path.read_text(encoding="utf-8"), path.name)
            self._key = (path, mtime)
            log.info("Model router loaded: %s", self._router.tiers)
        return self._router


_cache = _RouterCache()


def get_router(path: Path = MODELS_FILE) -> ModelRouter:
    return _cache.get(path)
