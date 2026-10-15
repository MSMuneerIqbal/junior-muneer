---
name: run-tests
description: Run Junior Muneer's backend tests (pytest) and dashboard end-to-end tests (Playwright) and read the failures. Use after any change, before committing.
---

# Run the tests

**Backend** (in `backend/`, from Git Bash):

```bash
.venv/Scripts/python -m pytest -q            # all; add -x to stop at the first failure
.venv/Scripts/python -m pytest -q tests/test_approvals.py
```

- Every test gets its own copy of a migrated database and no API keys (`tests/conftest.py`).
- Chat tests use `ScriptedModel` (one scripted model serves every agent, in call order) and talk over
  `client.websocket_connect("/ws/chat")`. `model.calls` / `model.last_call` show what each agent got.
- `TestClient` cancels the server task when a socket closes, so "keeps running after the page closes"
  can only be tested against a real uvicorn server.

**Dashboard** (in `frontend/`):

```bash
npx tsc --noEmit && npx eslint src
npx playwright test                    # desktop + phone; starts a fake-AI backend on 8100 and a build on 3100
npx playwright test e2e/approvals.spec.ts --project=desktop
```

- On failure read `test-results/<test>/error-context.md`: it has the page's accessibility snapshot,
  which usually shows the real cause (wrong name, missing element, old data).
- The e2e backend is shared by both projects and keeps data for the run: use unique text per test and
  put shared settings (mode, pause, rules) back to defaults at the end of a test.
- `test.bat` at the root runs both suites.
