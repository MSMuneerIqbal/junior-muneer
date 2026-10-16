"""Your GitHub connection (P6-01): GitHub's official MCP server, read-only, with your fine-grained token.

The token is saved in backend/.env by `connect.bat github` (never in the browser or in Git).
Two locks keep it read-only: GitHub's read-only endpoint, and a code filter that lets through
only tools that read (get_, list_, search_). Write actions come later through the Dev Executor,
always after your OK.
"""

from typing import Any

import httpx
from agents.mcp import MCPServerStreamableHttp

API = "https://api.github.com"
MCP_READONLY_URL = "https://api.githubcopilot.com/mcp/readonly"
# context: who you are; repos: files, commits, branches; issues; pull_requests.
TOOLSETS = "context,repos,issues,pull_requests"
READ_PREFIXES = ("get_", "list_", "search_")


def is_read_tool(name: str) -> bool:
    return name.startswith(READ_PREFIXES)


def _only_reads(_context: Any, tool: Any) -> bool:
    return is_read_tool(getattr(tool, "name", ""))


def github_mcp(token: str) -> MCPServerStreamableHttp:
    """The GitHub MCP server for the Developer Agent: read-only, your token."""
    if not token:
        raise ValueError("No GitHub token yet. Run connect.bat github.")
    return MCPServerStreamableHttp(
        params={
            "url": MCP_READONLY_URL,
            "headers": {
                "Authorization": f"Bearer {token}",
                "X-MCP-Readonly": "true",
                "X-MCP-Toolsets": TOOLSETS,
            },
            "timeout": 30,
        },
        name="GitHub (read-only)",
        cache_tools_list=True,
        client_session_timeout_seconds=60,
        tool_filter=_only_reads,
    )


async def check_token(token: str, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Whether the saved token works, and who it belongs to, in plain words."""
    if not token:
        return "Not connected. Run connect.bat github."
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        async with httpx.AsyncClient(base_url=API, headers=headers, timeout=15, transport=transport) as client:
            r = await client.get("/user")
    except httpx.HTTPError:
        return "Couldn't reach GitHub. Check the internet connection and try again."
    if r.status_code == 401:
        return "The token doesn't work (expired or revoked). Make a new one and run connect.bat github again."
    if r.status_code >= 400:
        return f"GitHub said no ({r.status_code}). Check the token's permissions."
    login = r.json().get("login", "?")
    expires = r.headers.get("github-authentication-token-expiration", "")
    return f"Connected as @{login}" + (f"; the token expires {expires}." if expires else ".")
