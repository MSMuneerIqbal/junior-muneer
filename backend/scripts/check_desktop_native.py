"""Explicit, no-model native desktop check on a disposable synthetic editor and isolated application database.

Run from backend: .venv/Scripts/python scripts/check_desktop_native.py
Never controls an existing user app. The child is owned by this script and closes on exit/after 60 seconds.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["FAKE_AI"] = "false"
for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "WHATSAPP_TOKEN", "GMAIL_APP_PASSWORD"):
    os.environ[key] = ""

from junior.computer.terminal import clean_env


def main():
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "desktop_window.py"
    proc = subprocess.Popen([sys.executable, "-u", str(fixture)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=clean_env(), creationflags=subprocess.CREATE_NO_WINDOW)
    tree = None
    try:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("Fixture didn't open: " + proc.stderr.read()[-1500:])
        info = json.loads(line)
        assert info["pid"] == proc.pid or info["parent_pid"] == proc.pid
        from junior.computer.owned_process import OwnedTree
        tree = OwnedTree()
        tree.assign(info["pid"])
        with tempfile.TemporaryDirectory(prefix="junior-desktop-native-") as data:
            os.environ["DATA_DIR"] = data
            from fastapi.testclient import TestClient
            from junior.computer import desktop
            from junior.computer.desktop_native import WindowsDesktop
            from junior.config import get_settings
            from junior.db.engine import close_all_connections
            from junior.main import create_app
            from junior.settings_store import set_setting
            get_settings.cache_clear()
            # Only this isolated check supports its synthetic Python window. Production never allows Python UI.
            desktop.APPS[Path(sys.executable).name.lower()] = "Synthetic desktop fixture"
            desktop.NATIVE = WindowsDesktop
            try:
                with TestClient(create_app()) as client:
                    set_setting("desktop_enabled", True)
                    set_setting("desktop_apps", [Path(sys.executable).name.lower()])
                    response = client.post("/api/computer/desktop/snapshot", json={"handle": info["handle"]})
                    assert response.status_code == 200, response.text
                    snap = response.json()
                    assert snap["window"]["pid"] == info["pid"]
                    from junior.approvals import create_item
                    def perform(spec, observed):
                        item = create_item(kind="api", platform="computer", item_type="desktop action", action_type="computer.desktop.input",
                                           text=json.dumps(spec.model_dump()), title="Synthetic desktop test", from_outside=False,
                                           meta={"op":"desktop", "desktop_spec":spec.model_dump(), "preview_url":observed["image_url"]})
                        result = client.post(f"/api/approvals/{item.id}/approve", json={}).json()
                        assert result["status"] == "posted", result
                    if not snap["window"]["foreground"]:
                        perform(desktop.DesktopAction(kind="focus", snapshot_id=snap["id"]), snap)
                        snap = client.post("/api/computer/desktop/snapshot", json={"handle":info["handle"]}).json()
                    focus = snap["focused"]
                    target = next((control for control in snap["controls"] if focus and control["runtime"] == focus["runtime"]
                                   and control["type"] == "EditControl"), None)
                    assert target, {"window":snap["window"], "focused":focus, "controls":snap["controls"]}
                    spec = desktop.DesktopAction(kind="type", snapshot_id=snap["id"], element=target["index"], text=" - native adapter verified")
                    def editor_value():
                        with WindowsDesktop() as native:
                            return native.auto.ControlFromHandle(info["editor"]).GetValuePattern().Value
                    before = editor_value()
                    assert "verified" not in before
                    # A dashboard approval changes the foreground app. Only our second disposable window is used.
                    with WindowsDesktop() as native:
                        native.focus(info["approval_window"])
                    perform(spec, snap)
                    until = time.monotonic() + 3
                    after = ""
                    while time.monotonic() < until:
                        after = editor_value()
                        if "native adapter verified" in after:
                            break
                        time.sleep(.05)
                    assert "native adapter verified" in after, after
                    preview = client.get(snap["image_url"])
                    assert preview.status_code == 200 and preview.content.startswith(b"\x89PNG")
                    print(json.dumps({"native_desktop":"passed", "isolated_data":True, "approval_wait_verified":True,
                                      "target_pid_verified":True, "capture_bytes":len(preview.content), "model_cost_usd":0}))
            finally:
                close_all_connections()
    finally:
        if tree:
            tree.close()
        if proc.poll() is None:
            proc.terminate()
        proc.communicate(timeout=10)


if __name__ == "__main__":
    main()
