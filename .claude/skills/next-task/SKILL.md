---
name: next-task
description: Do the next unticked task in TASK.md for Junior Muneer, end to end (build, safety tests, e2e, tick, commit, restart the app, report). Use when Muneer says "continue", "next", or names a task like P2-07.
---

# Do the next task

1. **Pick it.** Find the first `- [ ]` task in TASK.md (or the one Muneer named). Read its text, its
   "Done when", and the matching PLAN.md section. Read CLAUDE.md's safety rules.
2. **Look before building.** Read the files you'll change; reuse what exists (approvals, permissions,
   writing team, `TurnContext.emit` for live steps, fake AI triggers). Prototype code in `prototype/`
   may already solve part of it.
3. **Build it** in small steps. Agents are `agents/*.md` files (see the `new-agent` skill). Database
   changes need an Alembic migration in `backend/alembic/versions/` (the DB test checks models match).
4. **Tests with the task, not later:**
   - backend `tests/test_<feature>.py` with `ScriptedModel` from `tests/fake_ai.py` (no network);
     every safety rule the task touches gets a test (outside content → Ask, memory only from the
     user's words, locked types, Plan mode, budget);
   - a Playwright test in `frontend/e2e/` if there's UI (unique text per run: `${info.project.name}-${Date.now()}`);
   - run everything with the `run-tests` skill. All green before moving on.
5. **Look at the UI** for UI work: a throwaway `e2e/zz-shots.spec.ts` that saves screenshots to
   `test-results/`, read them, then delete the spec.
6. **Optional live check** with the real key: `live-check` skill (never on Muneer's own data).
7. **Finish:** tick the task in TASK.md (`- [x]`), update PLAN.md if the design changed (and its change
   log), commit with a clear message. Don't push unless Muneer asks.
8. **Restart his backend** (`restart-app` skill) so the new code is what he sees.
9. **Report** in short, plain words: what he can do now, how to try it, test results, cost if a live
   check ran, and what's next.
