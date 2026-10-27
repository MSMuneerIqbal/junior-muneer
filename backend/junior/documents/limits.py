"""Bound task/chat responses using the shared allowance; retry only failed read steps, never actions."""
import json
from agents import Model, ModelSettings, WebSearchTool
from openai import APIConnectionError, InternalServerError, RateLimitError

from junior.background import progress
from junior.costs import BudgetExceeded, budget_left
from junior.models import get_router


class TaskModel(Model):
    def __init__(self, model, name, context, router=None):
        self.model, self.name, self.context = model, name, context
        self.router = router or get_router()
        # A task's retry policy owns retries. Disable the OpenAI client's hidden retries for this model instance.
        client = getattr(model, "_client", None)
        if context.task_id is not None and client is not None and hasattr(client, "with_options"):
            model._client = client.with_options(max_retries=0)

    def settings_for(self, instructions, items, settings, tools, schema):
        self.context.check_task_limits()
        price = self.router.price(self.name)
        allowance = self.context.task_budget_usd
        if self.context.task_id is None:
            allowance = min(allowance if allowance is not None else float("inf"), self.context.settings.get("chat_budget_usd", .5))
        left = min(budget_left(), allowance) - sum(u.cost_usd for u in self.context.usage)
        # UTF-8 bytes are a conservative input-token allowance; include tool/schema overhead and unbilled cache misses.
        structured = schema is not None and hasattr(schema, "json_schema") and not (hasattr(schema, "is_plain_text") and schema.is_plain_text())
        schema_text = schema.json_schema() if structured else str(schema)
        payload = str(instructions) + str(items) + json.dumps(schema_text, ensure_ascii=False)
        payload += json.dumps([{"name": getattr(t, "name", ""), "description": getattr(t, "description", ""),
                                "parameters": getattr(t, "params_json_schema", {})} for t in tools], ensure_ascii=False)
        tokens = len(payload.encode("utf-8")) + 4096
        reserve = tokens * price.input / 1_000_000
        hosted = any(isinstance(t, WebSearchTool) for t in tools)
        reserve += self.router.tool_prices.get("web_search", 0) if hosted else 0
        output = int((left - reserve) * 1_000_000 / max(price.output, .01))
        if output < 512:
            section = "Background tasks" if self.context.task_id is not None else "Budget"
            raise BudgetExceeded(f"There isn't enough allowance for another bounded AI call. Use a smaller request or adjust Settings → {section}.")
        limit = self.context.settings.get("max_output_tokens", 10000)
        extra = {"max_tool_calls": 1} if hosted and self.router.provider_of(self.name) == "openai" else None
        return settings.resolve(ModelSettings(max_tokens=min(settings.max_tokens or limit, output, limit), extra_args=extra))

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, *args, **kwargs):
        settings = self.settings_for(system_instructions, input, model_settings, tools, output_schema)
        return await self.model.get_response(system_instructions, input, settings, tools, output_schema, *args, **kwargs)

    async def stream_response(self, system_instructions, input, model_settings, tools, output_schema, *args, **kwargs):
        settings = self.settings_for(system_instructions, input, model_settings, tools, output_schema)
        async for event in self.model.stream_response(system_instructions, input, settings, tools, output_schema, *args, **kwargs):
            yield event


def task_provider(provider, context, router=None):
    def bounded(name):
        model = provider(name)
        if isinstance(model, TaskModel) and model.context is context:
            if router is not None:
                model.router = router
            return model
        return TaskModel(model, name, context, router)
    return bounded


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
