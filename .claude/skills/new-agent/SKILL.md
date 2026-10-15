---
name: new-agent
description: Add a new subagent or helper agent to Junior Muneer (agent file, tool for Junior Muneer to call it, model, fake-AI support, tests). Use for P2-07 Social Media Manager, the news agents (Phase 2b), and later subagents.
---

# Add an agent

1. **Agent file** `agents/<name>.md` (name = file name, lowercase with `_`):
   ```
   ---
   name: social_manager
   description: When Junior Muneer should call it (he reads this).
   model: strong            # or small; agents/models.toml [agents] can override
   tools: []                # only names in KNOWN_TOOLS (backend/junior/registry.py)
   action_types: []         # dotted types it may request, e.g. linkedin.post
   ---
   Instructions. Placeholders: {{user_name}} {{language}} {{timezone}} {{now}} {{profile}} {{memories}} {{status}}
   ```
   A broken file stops startup with a clear error (good). Add every new model to `[prices]`.
2. **Structured answers:** define a pydantic model and call it with
   `context.helpers.run_structured("<name>", prompt, context, Model)` (see `backend/junior/writing/team.py`).
   Plain text: `context.helpers.run(...)`. Helpers share the turn's budget and cost.
3. **A tool for Junior Muneer** in `backend/junior/agent/tools.py`: an `async` `<thing>_for(context, ...)`
   function with the logic (testable), a thin `@function_tool`, register it in `TOOL_FACTORIES["<group>"]`,
   add the group to `KNOWN_TOOLS` and to `tools:` in `agents/junior_muneer.md`, plus one line in his
   "What you can do" list. Add a `STEP_LABELS` entry in `agent/runner.py`.
4. **Safety in the tool:** refuse in Plan mode (`plan_mode_refusal()`); outside text (pastes, web pages,
   feeds) goes in fenced and calls `context.mark_outside()`; anything outgoing goes through
   `add_to_approvals_for` / `create_item` (never sends); facts only from the profile or fetched sources.
5. **Live progress:** report steps with `context.emit({"type": "step", "id": ..., "kind": "team",
   "label": ..., "status": "done", "detail": text, "notes": [...]})`; they show live and in Show work.
6. **Fake AI** (`backend/junior/agent/fake.py`): a message trigger word that calls the tool, and fake
   structured answers in `_team_answer` (keyed on the output model's name) so the dashboard works with
   `FAKE_AI=true` and e2e tests can drive it.
7. **Tests:** backend with `ScriptedModel` (scripted JSON answers per agent, in call order), including the
   safety rules above; e2e for the chat flow. Then the `live-check` skill once with the real key.
