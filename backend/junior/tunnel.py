"""A fixed public address for WhatsApp while the app runs on your PC (P8-04): `tunnel.bat`.

Uses ngrok's free account: your authtoken and your free static domain from ngrok's dashboard,
saved in backend/.env as NGROK_AUTHTOKEN and NGROK_DOMAIN. The address never changes, so Meta's
webhook is set once. Only the WhatsApp webhook answers on it (junior/hosts.py); the rest of the
app stays private. On the server you don't need this: Caddy gives the real address.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from junior.config import get_settings


def find_ngrok() -> str:
    found = shutil.which("ngrok")
    if found:
        return found
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    links = winget / "Links" / "ngrok.exe"
    if links.exists():
        return str(links)
    # Sometimes winget installs without the shortcut: look in its package folder.
    packages = sorted((winget / "Packages").glob("Ngrok.Ngrok*/ngrok.exe")) if (winget / "Packages").exists() else []
    return str(packages[0]) if packages else ""


def main() -> None:
    s = get_settings()
    if not s.ngrok_authtoken or not s.ngrok_domain:
        sys.exit("Add NGROK_AUTHTOKEN and NGROK_DOMAIN to backend/.env first (see TASK.md, P8-04).")
    ngrok = find_ngrok()
    if not ngrok:
        sys.exit("ngrok isn't installed. Run: winget install --id Ngrok.Ngrok")
    domain = s.ngrok_domain.removeprefix("https://").strip("/")
    print(f"WhatsApp webhook address (put it in Meta once): https://{domain}/api/whatsapp/webhook")
    print("Keep this window open while you use WhatsApp with Junior Muneer. Ctrl+C stops it.\n")
    env = {**os.environ, "NGROK_AUTHTOKEN": s.ngrok_authtoken}  # not on the command line
    subprocess.run([ngrok, "http", f"--domain={domain}", f"127.0.0.1:{s.backend_port}"], env=env, check=False)


if __name__ == "__main__":
    main()
