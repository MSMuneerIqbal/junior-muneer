# Junior Muneer

Your personal AI assistant and friend. He chats about anything in English and Urdu, remembers what you
tell him, searches the web, and (in later phases) helps with freelance work, social media, email and GitHub.
You decide what goes out: every outgoing action follows Ask / Auto / Deny permission rules.

No browser bots: data comes from official APIs, email alerts or text you paste in. Approved items go out
through an official API, or you copy and paste them yourself.

The full design is in [PLAN.md](PLAN.md); progress is tracked in [TASK.md](TASK.md).

## Status

**Phase 0 (foundation + text chat)** is built: live streaming chat, chat history, long-term memory,
web search, Activity log, spend tracking with a daily cap, Pause, daily backups, and the dashboard.

## Start it

Double-click **`start.bat`**. The first run sets everything up (a few minutes), then it opens
the dashboard at http://localhost:3000. **`stop.bat`** stops it.

You need your OpenAI API key once: open `backend\.env` (created on the first run) and paste it after
`OPENAI_API_KEY=`, then run `stop.bat` and `start.bat` again. To try the dashboard without a key, set
`FAKE_AI=true` in the same file: answers are then fake echoes and nothing is spent.

## Set it up on a new PC

1. Install **Python 3.13** (python.org, tick "Add to PATH") and **Node.js 22** (nodejs.org).
2. Get the code: `git clone https://github.com/MSMuneerIqbal/junior-muneer.git`
3. To bring your chats, memory and settings: copy the `data\` folder from the old PC
   (or a backup from `data\backups\`, renamed to `data\junior.db`).
4. Double-click `start.bat`, then paste your API key into `backend\.env` as above.

Run it on **one PC at a time**.

## Everyday things

| What | How |
|---|---|
| Change your name, language, time zone or daily cap | Dashboard → Settings |
| See or edit what he remembers | Dashboard → Memory |
| See everything he did, with costs | Dashboard → Activity |
| Stop all background work and actions | **Pause everything** in the Today panel |
| Change which AI model an agent uses | Edit `agents\models.toml` (applies on the next message) |
| Change his personality | Edit `agents\junior_muneer.md` |
| Backups | Automatic, daily, last 14 kept in `data\backups\` |
| Restore a backup | `stop.bat`, then in `backend\`: `.venv\Scripts\python -m junior.backup restore ..\data\backups\junior-YYYY-MM-DD.db` |
| Run all tests (no key needed, nothing spent) | Double-click `test.bat` |

## Folders

| Folder | What's in it |
|---|---|
| `backend/` | Python: FastAPI, OpenAI Agents SDK, database, tests |
| `frontend/` | Next.js dashboard |
| `agents/` | One file per agent (personality, instructions, model, tools) + `models.toml` |
| `playbooks/` | One expert file per platform (from phase 2) |
| `prototype/` | The early Claude SDK prototype, kept for reference only |
| `data/` | Database, backups, uploads (never in Git) |

## Privacy

Your chats are sent to OpenAI to be answered (by default OpenAI doesn't train on API data; check
its current policy). Everything else stays in `data\` on your PC. API keys live only in
`backend\.env`, which is never committed.
