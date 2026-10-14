"""Lets a tool ask a helper agent (e.g. the web researcher) to do a job.

The helper shares the turn's context, so its cost lands in the same turn,
the daily cap still applies, and its web searches are logged like any other.
"""

from dataclasses import dataclass

from junior.agent.builder import ModelProvider, build_agent
from junior.agent.context import TurnContext
from junior.agent.runner import run_once
from junior.costs import budget_left
from junior.models import get_router
from junior.registry import Registry


@dataclass
class HelperRunner:
    registry: Registry
    model_provider: ModelProvider

    async def run(self, agent_name: str, prompt: str, context: TurnContext) -> str:
        router = get_router()
        agent, model_name = build_agent(self.registry.get(agent_name), router, self.model_provider)
        spent_this_turn = sum(u.cost_usd for u in context.usage)
        budget = budget_left(context.settings) - spent_this_turn
        result = await run_once(
            agent, model_name, router, [{"role": "user", "content": prompt}], context, budget
        )
        return result.text
