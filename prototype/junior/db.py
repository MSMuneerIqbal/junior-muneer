"""SQLite storage for posts, ideas and API usage. One short-lived connection per call, so it is safe across threads."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,
    topic         TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL,          -- generating | review | approved | ready | posted | rejected | failed
    text          TEXT NOT NULL DEFAULT '',
    visual_idea   TEXT NOT NULL DEFAULT '',
    score         INTEGER,
    issues        TEXT NOT NULL DEFAULT '[]',
    trace         TEXT NOT NULL DEFAULT '[]',
    feedback      TEXT NOT NULL DEFAULT '',
    previous_text TEXT NOT NULL DEFAULT '',
    error         TEXT NOT NULL DEFAULT '',
    scheduled_at  TEXT,                   -- local time, YYYY-MM-DDTHH:MM
    posted_at     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ideas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    platform   TEXT NOT NULL,
    title      TEXT NOT NULL,
    angle      TEXT NOT NULL DEFAULT '',
    why        TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'new',  -- new | used | dismissed
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    model         TEXT NOT NULL,
    agent         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);
"""

_POST_FIELDS = {
    "status", "text", "visual_idea", "score", "issues", "trace", "feedback",
    "previous_text", "error", "scheduled_at", "posted_at",
}
_JSON_FIELDS = {"issues", "trace"}

# USD per million tokens (input, output), for the rough cost shown on the dashboard.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        # Posts that were mid-way when the app stopped can't resume; let the owner retry them.
        c.execute(
            "UPDATE posts SET status='failed', error='The app stopped before this finished. Click Try again.'"
            " WHERE status='generating'"
        )


def _post(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    post = dict(row)
    for key in _JSON_FIELDS:
        post[key] = json.loads(post[key] or "[]")
    return post


# --- posts -------------------------------------------------------------------------------

def create_post(platform: str, topic: str, notes: str = "") -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO posts (platform, topic, notes, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'generating', ?, ?)",
            (platform, topic, notes, now(), now()),
        )
        return cur.lastrowid


def get_post(post_id: int) -> dict | None:
    with connect() as c:
        return _post(c.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())


def update_post(post_id: int, **values) -> None:
    unknown = set(values) - _POST_FIELDS
    if unknown:
        raise ValueError(f"Unknown post fields: {unknown}")
    for key in _JSON_FIELDS & set(values):
        values[key] = json.dumps(values[key], ensure_ascii=False)
    values["updated_at"] = now()
    columns = ", ".join(f"{key} = ?" for key in values)
    with connect() as c:
        c.execute(f"UPDATE posts SET {columns} WHERE id = ?", (*values.values(), post_id))


def list_posts(status: str, limit: int = 50) -> list[dict]:
    order = "scheduled_at ASC" if status == "approved" else "updated_at DESC"
    with connect() as c:
        rows = c.execute(
            f"SELECT * FROM posts WHERE status = ? ORDER BY {order} LIMIT ?", (status, limit)
        ).fetchall()
    return [_post(r) for r in rows]


def approved_examples(platform: str, exclude_id: int, limit: int = 3) -> list[str]:
    """Recent posts the owner approved on this platform; the writer uses them to copy the owner's voice."""
    with connect() as c:
        rows = c.execute(
            "SELECT text FROM posts WHERE platform = ? AND id != ? AND status IN ('approved', 'ready', 'posted')"
            " AND text != '' ORDER BY updated_at DESC LIMIT ?",
            (platform, exclude_id, limit),
        ).fetchall()
    return [r["text"] for r in rows]


def recent_topics(limit: int = 30) -> list[str]:
    with connect() as c:
        rows = c.execute(
            "SELECT topic FROM posts WHERE status != 'rejected' ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r["topic"] for r in rows]


def promote_due_posts() -> None:
    """Scheduled posts whose time has come move to 'ready'."""
    with connect() as c:
        c.execute(
            "UPDATE posts SET status = 'ready', updated_at = ? WHERE status = 'approved' AND scheduled_at <= ?",
            (now(), now()),
        )


# --- ideas -------------------------------------------------------------------------------

def add_ideas(ideas: list[dict]) -> None:
    with connect() as c:
        c.executemany(
            "INSERT INTO ideas (platform, title, angle, why, created_at) VALUES (?, ?, ?, ?, ?)",
            [(i["platform"], i["title"], i["angle"], i["why"], now()) for i in ideas],
        )


def list_ideas() -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM ideas WHERE status = 'new' ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_idea(idea_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    return dict(row) if row else None


def set_idea_status(idea_id: int, status: str) -> None:
    with connect() as c:
        c.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))


# --- usage -------------------------------------------------------------------------------

def log_usage(model: str, agent: str, input_tokens: int, output_tokens: int) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO usage (model, agent, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (model, agent, input_tokens, output_tokens, now()),
        )


def usage_this_month() -> dict:
    month = datetime.now().strftime("%Y-%m")
    with connect() as c:
        rows = c.execute(
            "SELECT model, COUNT(*) AS calls, SUM(input_tokens) AS inp, SUM(output_tokens) AS out"
            " FROM usage WHERE created_at LIKE ? GROUP BY model",
            (f"{month}%",),
        ).fetchall()
    calls = sum(r["calls"] for r in rows)
    cost = 0.0
    priced = True
    for r in rows:
        if r["model"] not in PRICES:
            priced = False
            continue
        price_in, price_out = PRICES[r["model"]]
        cost += (r["inp"] * price_in + r["out"] * price_out) / 1_000_000
    return {"calls": calls, "cost": round(cost, 2), "priced": priced}
