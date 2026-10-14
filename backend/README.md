# Backend

Python 3.13: FastAPI, OpenAI Agents SDK, SQLite (SQLAlchemy + Alembic).

    .venv\Scripts\python -m uvicorn junior.main:app --reload   # http://127.0.0.1:8000 (API docs at /docs)
    .venv\Scripts\python -m pytest                             # all backend tests, fake AI, no cost
    .venv\Scripts\python -m junior.agent "Hi"                  # ask Junior Muneer one question (needs the key)
    .venv\Scripts\python -m junior.db                          # create or upgrade the database
    .venv\Scripts\python -m junior.backup now | list | restore FILE

Settings come from `backend/.env` (see `.env.example`).
