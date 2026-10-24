"""Lets a tool ask a helper agent (e.g. the web researcher) to do a job.

The helper shares the turn's context, so its cost lands in the same turn,
the daily cap still applies, and its web searches are logged like any other.
"""

from dataclasses import dataclass
from typing import TypeVar

from junior.agent.builder import ModelProvider, build_agent
from junior.agent.context import TurnContext
from junior.agent.runner import run_once
from junior.costs import budget_left
from junior.models import get_router
from junior.registry import Registry

T = TypeVar("T")


@dataclass
class HelperRunner:
    registry: Registry
    model_provider: ModelProvider

    async def run(self, agent_name: str, prompt: str, context: TurnContext) -> str:
        return (await self._run(agent_name, prompt, context)).text

    async def run_structured(
        self, agent_name: str, prompt: str, context: TurnContext, output_type: type[T]
    ) -> T:
        """Run a helper whose answer is a structured object (e.g. the writing team)."""
        return (await self._run(agent_name, prompt, context, output_type)).output

    async def _run(self, agent_name: str, prompt: str, context: TurnContext, output_type=None):
        router = get_router()
        agent, model_name = build_agent(
            self.registry.get(agent_name), router, self.model_provider, output_type=output_type
        )
        budget = budget_left(context.settings)
        if context.task_budget_usd is not None:
            budget = min(budget, context.task_budget_usd)
        return await run_once(
            agent, model_name, router, [{"role": "user", "content": prompt}], context, budget
        )
