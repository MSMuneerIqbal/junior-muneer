# Junior Muneer

A personal AI assistant and friend that helps manage freelance work (Upwork, Fiverr), social media
(LinkedIn, Facebook, Instagram, X) and email. You decide what goes out: every outgoing action follows
Ask / Auto / Deny permission rules.

No browser bots: data comes from official APIs, email alerts or text you paste in. Approved items go out
through an official API, or you copy and paste them yourself.

## Status

**Plan complete.** The full design is in [PLAN.md](PLAN.md), and the working checklist is in [TASK.md](TASK.md).
Development starts with Phase 0.

## Folders

| Folder | What's in it |
|---|---|
| `backend/` | Python: FastAPI, OpenAI Agents SDK, database, tests |
| `frontend/` | Next.js dashboard |
| `agents/` | One file per agent (personality, instructions, model, tools) |
| `playbooks/` | One expert file per platform |
| `prototype/` | The early Claude SDK prototype, kept for reference only |
| `data/` | Database, backups, uploads (never in Git) |
