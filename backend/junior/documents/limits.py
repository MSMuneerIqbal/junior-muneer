"""Bound each task's model responses and retry only a failed read/model step, never the whole job."""
import json
from agents import Model, ModelSettings, WebSearchTool
from openai import APIConnectionError, InternalServerError, RateLimitError

from junior.background import progress
from junior.costs import BudgetExceeded, budget_left
from junior.models import get_router


class TaskModel(Model):
    def __init__(self, model, name, context):
        self.model, self.name, self.context = model, name, context
        # A task's retry policy owns retries. Disable the OpenAI client's hidden retries for this model instance.
        client = getattr(model, "_client", None)
        if client is not None and hasattr(client, "with_options"):
            model._client = client.with_options(max_retries=0)

    def settings_for(self, instructions, items, settings, tools, schema):
        self.context.check_task_limits()
        price = get_router().price(self.name)
        left = min(budget_left(), self.context.task_budget_usd) - sum(u.cost_usd for u in self.context.usage)
        # UTF-8 bytes are a conservative input-token allowance; include tool/schema overhead and unbilled cache misses.
        payload = str(instructions) + str(items) + str(schema)
        payload += json.dumps([getattr(t, "params_json_schema", {}) for t in tools], ensure_ascii=False)
        tokens = len(payload.encode("utf-8")) + 4096
        reserve = tokens * price.input / 1_000_000
        reserve += sum(get_router().tool_prices.get("web_search", 0) for t in tools if isinstance(t, WebSearchTool))
        output = int((left - reserve) * 1_000_000 / max(price.output, .01))
        if output < 512:
            raise BudgetExceeded("There isn't enough task allowance for another bounded AI call. Raise it in Settings → Background tasks.")
        return settings.resolve(ModelSettings(max_tokens=min(settings.max_tokens or 10000, output, 10000)))

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, *args, **kwargs):
        settings = self.settings_for(system_instructions, input, model_settings, tools, output_schema)
        return await self.model.get_response(system_instructions, input, settings, tools, output_schema, *args, **kwargs)

    async def stream_response(self, system_instructions, input, model_settings, tools, output_schema, *args, **kwargs):
        settings = self.settings_for(system_instructions, input, model_settings, tools, output_schema)
        async for event in self.model.stream_response(system_instructions, input, settings, tools, output_schema, *args, **kwargs):
            yield event


def task_provider(provider, context):
    return lambda name: TaskModel(provider(name), name, context)


async def retry_read(context, operation):
    while True:
        context.check_task_limits()
        try:
            return await operation()
        except (APIConnectionError, InternalServerError, RateLimitError):
            if context.task_retries_used >= context.task_max_retries:
                raise
            context.task_retries_used += 1
            progress(context.task_id, "Retrying a busy research service", 0, context)
