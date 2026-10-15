"""Who's on top, by field: Artificial Analysis's official API (free key; attribution required).

Rankings are taken from the API as they are: code sorts and copies them, no AI is involved,
so the numbers are exactly the published ones. Without ARTIFICIAL_ANALYSIS_API_KEY in
backend/.env there are no rankings (the digest says how to turn them on).
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from junior.config import get_settings
from junior.news.reader import TIMEOUT_SECONDS, USER_AGENT

log = logging.getLogger(__name__)

API = "https://artificialanalysis.ai/api/v2"
SITE = "https://artificialanalysis.ai/"
TOP_MODELS = 5
TOP_MEDIA = 3

# (key, title, the evaluation that ranks it)
LLM_BOARDS = [
    ("intelligence", "Overall intelligence (AA Intelligence Index)", "artificial_analysis_intelligence_index"),
    ("coding", "Coding (AA Coding Index)", "artificial_analysis_coding_index"),
    ("math", "Math (AA Math Index)", "artificial_analysis_math_index"),
]
MEDIA_BOARDS = [
    ("speech", "Text to speech (voice)", "text-to-speech"),
    ("image", "Text to image", "text-to-image"),
    ("video", "Text to video", "text-to-video"),
    ("image_editing", "Image editing", "image-editing"),
]


def _creator(row: dict) -> str:
    creator = row.get("model_creator") or {}
    return str(creator.get("name") or "")


async def fetch_leaderboards(transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any] | None:
    """The current rankings, or None when there's no API key. Errors are reported, not raised."""
    key = get_settings().artificial_analysis_api_key
    if not key:
        return None
    boards: list[dict] = []
    problems: list[str] = []
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        headers={"x-api-key": key, "User-Agent": USER_AGENT},
        follow_redirects=False,
        transport=transport,
    ) as client:
        try:
            r = await client.get(f"{API}/data/llms/models")
            r.raise_for_status()
            models = r.json().get("data", [])
            for board, title, field in LLM_BOARDS:
                scored = [m for m in models if isinstance((m.get("evaluations") or {}).get(field), (int, float))]
                scored.sort(key=lambda m: m["evaluations"][field], reverse=True)
                rows = [
                    {"rank": n, "model": m.get("name", ""), "creator": _creator(m), "score": round(m["evaluations"][field], 1)}
                    for n, m in enumerate(scored[:TOP_MODELS], start=1)
                ]
                if rows:
                    boards.append({"key": board, "title": title, "rows": rows})
        except (httpx.HTTPError, ValueError) as e:
            problems.append(f"language models: {_why(e)}")
        for board, title, path in MEDIA_BOARDS:
            try:
                r = await client.get(f"{API}/data/media/{path}")
                r.raise_for_status()
                rows_in = [m for m in r.json().get("data", []) if isinstance(m.get("elo"), (int, float))]
                rows_in.sort(key=lambda m: (m.get("rank") or 10_000, -m["elo"]))
                rows = [
                    {"rank": m.get("rank") or n, "model": m.get("name", ""), "creator": _creator(m), "score": round(m["elo"])}
                    for n, m in enumerate(rows_in[:TOP_MEDIA], start=1)
                ]
                if rows:
                    boards.append({"key": board, "title": f"{title} (Elo)", "rows": rows})
            except (httpx.HTTPError, ValueError) as e:
                problems.append(f"{title.lower()}: {_why(e)}")
    return {
        "source": "Artificial Analysis",
        "url": SITE,
        "fetched_at": datetime.now(UTC).isoformat(),
        "boards": boards,
        "problems": problems,
    }


def _why(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        return "the API key was refused" if code == 401 else "daily limit reached" if code == 429 else f"HTTP {code}"
    if isinstance(e, httpx.TimeoutException):
        return "timed out"
    return "couldn't be read"


def leaderboards_text(data: dict[str, Any] | None) -> str:
    """The rankings as plain lines, for the news agent's answers."""
    if not data:
        return "(No rankings: Artificial Analysis's free API key isn't set.)"
    lines = [f"Rankings from {data['source']} ({data['url']}), fetched {data['fetched_at'][:10]}:"]
    for b in data["boards"]:
        rows = "; ".join(f"#{r['rank']} {r['model']} ({r['creator']}) {r['score']}" for r in b["rows"])
        lines.append(f"- {b['title']}: {rows}")
    return "\n".join(lines)
