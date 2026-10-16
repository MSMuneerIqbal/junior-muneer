"""Connect your accounts (Phase 3), from a terminal: `connect.bat meta` or `connect.bat check`.

Tokens never go through the browser: you paste them here, they're exchanged with the platform and
saved in backend/.env (which is never committed). Restart the backend afterwards.

    github  GitHub: a fine-grained personal access token (see TASK.md, P6-01)
    meta    Facebook Page (and, later, Instagram): app ID, app secret and a short-lived user token
            from Meta's Graph API Explorer -> a long-lived Page token
    check   tests the saved connections
"""

import asyncio
import getpass
import re
import sys
from pathlib import Path

import httpx

from junior.config import BACKEND_DIR, get_settings
from junior.github.connection import check_token, gh_login, gh_token
from junior.senders.facebook import GRAPH, FacebookPageSender, appsecret_proof

ENV_FILE = BACKEND_DIR / ".env"


def set_env(values: dict[str, str], path: Path | None = None, heading: str = "Facebook Page (written by connect.bat meta)") -> None:
    """Write KEY=value lines into backend/.env, replacing old ones and keeping everything else."""
    path = path or ENV_FILE
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done: set[str] = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            done.add(key)
        else:
            out.append(line)
    missing = [k for k in values if k not in done]
    if missing:
        out.append("")
        out.append(f"# {heading}")
        out.extend(f"{k}={values[k]}" for k in missing)
    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")


def masked(value: str) -> str:
    return value[:4] + "…" + value[-4:] if len(value) > 12 else "…"


async def exchange_meta(
    app_id: str, app_secret: str, short_token: str, version: str = "v26.0", transport: httpx.AsyncBaseTransport | None = None
) -> list[dict]:
    """Short-lived user token -> long-lived user token -> your Pages, each with its long-lived Page token."""
    async with httpx.AsyncClient(base_url=f"{GRAPH}/{version}/", timeout=30, transport=transport) as client:
        r = await client.get(
            "oauth/access_token",
            params={"grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret, "fb_exchange_token": short_token},
        )
        _raise(r)
        long_user = r.json()["access_token"]
        r = await client.get(
            "me/accounts",
            params={
                "access_token": long_user,
                "appsecret_proof": appsecret_proof(long_user, app_secret),
                "fields": "id,name,access_token,tasks,instagram_business_account{id,username}",
            },
        )
        _raise(r)
        return r.json().get("data", [])


def _raise(r: httpx.Response) -> None:
    if r.status_code >= 400:
        try:
            message = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            message = r.text[:200]
        raise SystemExit(f"Meta said no: {message}")


def connect_meta() -> None:
    print("Connect your Facebook Page (see TASK.md, P3-02, for how to get these).\n")
    app_id = input("Meta app ID: ").strip()
    app_secret = getpass.getpass("Meta app secret (hidden): ").strip()
    short = getpass.getpass("User token from the Graph API Explorer (hidden): ").strip()
    if not (re.fullmatch(r"\d{5,25}", app_id) and app_secret and short):
        raise SystemExit("The app ID must be digits, and the secret and token can't be empty.")
    version = get_settings().meta_graph_version
    pages = asyncio.run(exchange_meta(app_id, app_secret, short, version))
    pages = [p for p in pages if "CREATE_CONTENT" in p.get("tasks", ["CREATE_CONTENT"])]
    if not pages:
        raise SystemExit("No Page found that this account can post to. Check that you chose your Page when you made the token.")
    for n, p in enumerate(pages, start=1):
        ig = p.get("instagram_business_account") or {}
        extra = f" (Instagram: @{ig.get('username')})" if ig else ""
        print(f"  {n}. {p['name']}{extra}")
    choice = input(f"Which Page? [1-{len(pages)}] ").strip() or "1"
    if not choice.isdigit() or not 1 <= int(choice) <= len(pages):
        raise SystemExit("That's not one of the numbers.")
    page = pages[int(choice) - 1]
    values = {"META_APP_ID": app_id, "META_APP_SECRET": app_secret, "META_PAGE_ID": page["id"], "META_PAGE_TOKEN": page["access_token"]}
    ig = page.get("instagram_business_account") or {}
    if ig.get("id"):
        values["META_IG_USER_ID"] = ig["id"]
    set_env(values)
    print(f"\nSaved in backend/.env: Page “{page['name']}” (token {masked(page['access_token'])}).")
    print("Restart the backend (stop.bat, then start.bat), then check it in Settings → Connections.")


def connect_github() -> None:
    login = gh_login()
    if login:
        answer = input(f"Your GitHub CLI is logged in as @{login}. Use that login? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            result = asyncio.run(check_token(gh_token(login)))
            if not result.startswith("Connected"):
                raise SystemExit(f"{result} Nothing was saved.")
            set_env({"GITHUB_AUTH": "gh", "GITHUB_USER": login, "GITHUB_TOKEN": ""}, heading="GitHub (written by connect.bat github)")
            print(f"\n{result} Saved: use the GitHub CLI login @{login} (the token stays in Windows' store, not in .env).")
            print("Restart the backend (stop.bat, then start.bat), then check it in Settings → Connections.")
            return
    print("Connect GitHub with a fine-grained token (see TASK.md, P6-01, for how to make one).\n")
    token = getpass.getpass("Fine-grained token (hidden, starts with github_pat_): ").strip()
    if not re.fullmatch(r"(github_pat_|ghp_)[A-Za-z0-9_]{20,}", token):
        raise SystemExit("That doesn't look like a GitHub token (it starts with github_pat_). Nothing was saved.")
    result = asyncio.run(check_token(token))
    if not result.startswith("Connected"):
        raise SystemExit(f"{result} Nothing was saved.")
    set_env({"GITHUB_TOKEN": token, "GITHUB_AUTH": "", "GITHUB_USER": ""}, heading="GitHub (written by connect.bat github)")
    print(f"\n{result} Saved in backend/.env (token {masked(token)}).")
    print("Restart the backend (stop.bat, then start.bat), then check it in Settings → Connections.")


def check() -> None:
    s = get_settings()
    from junior.github.connection import saved_token

    print("GitHub:", asyncio.run(check_token(saved_token())))
    if not (s.meta_page_id and s.meta_page_token):
        print("Facebook Page: not connected. Run connect.bat meta.")
        return
    sender = FacebookPageSender(s.meta_page_id, s.meta_page_token, s.meta_app_secret, s.meta_graph_version)
    print("Facebook Page:", asyncio.run(sender.check()))


def main(argv: list[str]) -> None:
    command = argv[0] if argv else ""
    if command == "meta":
        connect_meta()
    elif command == "github":
        connect_github()
    elif command == "check":
        check()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
