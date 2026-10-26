"""Desktop actions remain opt-in, scoped, approval-bound, single-use and fail closed on stale/uncertain UI."""

import asyncio
import copy
import json
import time

import pytest

from junior.computer import desktop
from junior.computer.desktop import DesktopAction
from junior.computer.desktop_fake import FakeDesktop
from junior.computer.desktop_native import DesktopRefused
from junior.permissions import RuleChangeError, set_mode, set_rule
from junior.settings_store import set_setting
from test_computer_paths import context_with, pc as pc_fixture  # noqa: F401

pc_home = pc_fixture


@pytest.fixture
def screen(pc_home, monkeypatch):
    class Screen(FakeDesktop):
        text = "Test document"
        def __init__(self):
            self.meta = super().window(8001)
            document = super().observe(8001)["controls"][0]
            self.controls = [document,
                {**document, "index": 1, "runtime": [8001, 2], "type": "ButtonControl", "name": "Pay now"},
                {**document, "index": 2, "runtime": [8001, 3], "type": "ButtonControl", "name": "Bold"},
                {**document, "index": 3, "runtime": [8001, 4], "type": "EditControl", "name": "[password field]", "password": True}]
            self.focus_index, self.hit_index, self.inputs, self.observations = 0, 0, [], 0
        def window(self, hwnd):
            if hwnd != 8001:
                raise DesktopRefused("No such window")
            return copy.deepcopy(self.meta)
        def foreground(self, hwnd):
            if not self.meta["foreground"]:
                raise DesktopRefused("Focus moved")
        def observe(self, hwnd):
            self.observations += 1
            return {"window": self.window(hwnd), "controls": copy.deepcopy(self.controls),
                    "focused": copy.deepcopy(self.controls[self.focus_index])}
        def focused(self, hwnd):
            self.foreground(hwnd)
            return copy.deepcopy(self.controls[self.focus_index])
        def point(self, hwnd, x, y):
            self.foreground(hwnd)
            return copy.deepcopy(self.controls[self.hit_index])
        def focus(self, hwnd):
            self.inputs.append(("focus", hwnd))
            self.meta["foreground"] = True
        def focus_control(self, hwnd, runtime):
            self.meta["foreground"] = True
            self.focus_index = next(i for i, control in enumerate(self.controls) if control["runtime"] == runtime)
        def type_text(self, hwnd, text, check):
            check()
            self.inputs.append(("type", text))
        def click(self, hwnd, x, y, check):
            check()
            self.inputs.append(("click", x, y))
        def press(self, hwnd, key, check):
            check()
            self.inputs.append(("key", key))
    # Base's observe uses self.window; it needs metadata before Screen initializes its controls.
    instance = Screen()
    monkeypatch.setattr(desktop, "NATIVE", lambda: instance)
    set_setting("desktop_enabled", True)
    set_setting("desktop_apps", ["notepad.exe"])
    return pc_home[1], instance


def capture(c):
    response = c.post("/api/computer/desktop/snapshot", json={"handle": 8001})
    assert response.status_code == 200, response.text
    return response.json()


def card(c, snap, kind="type", element=0, text="hello", key=""):
    ctx = context_with("Please work in my Notepad document")
    result = asyncio.run(desktop.propose(ctx, DesktopAction(kind=kind, snapshot_id=snap["id"], element=element, text=text, key=key)))
    assert "waiting for their OK" in result, result
    return c.get(f"/api/approvals/{ctx.approval_ids[-1]}").json()


def approve(c, item):
    response = c.post(f"/api/approvals/{item['id']}/approve", json={})
    assert response.status_code == 200, response.text
    return response.json()


def test_typing_waits_for_review_and_the_snapshot_cannot_be_replayed(screen):
    c, native = screen
    snap = capture(c)
    assert c.get(snap["image_url"]).status_code == 200
    item = card(c, snap)
    assert item["action_type"] == "computer.desktop.input" and item["meta"]["preview_url"] == snap["image_url"]
    assert native.inputs == []
    assert approve(c, item)["status"] == "posted"
    assert native.inputs == [("type", "hello")]
    replay = card(c, snap)
    result = approve(c, replay)
    assert result["status"] == "approved" and "cannot be replayed" in result["meta"]["last_error"]
    assert len(native.inputs) == 1


@pytest.mark.parametrize("change", ["title", "pid", "started", "rect", "app", "class", "control", "focus"])
def test_stale_window_or_control_is_refused_without_input(screen, change):
    c, native = screen
    item = card(c, capture(c))
    if change == "control":
        native.controls[0]["runtime"] = [999]
    elif change == "focus":
        native.focus_index = 2
    elif change == "rect":
        native.meta[change] = [1, 2, 801, 502]
    elif change == "pid":
        native.meta[change] = 999
    elif change == "app":
        native.meta[change] = "powershell.exe"
    else:
        native.meta[change] = "changed"
    result = approve(c, item)
    assert result["status"] == "approved" and result["meta"]["last_error"]
    assert native.inputs == []


@pytest.mark.parametrize("setting,value", [("desktop_enabled", False), ("computer_enabled", False), ("desktop_apps", []), ("paused", True), ("permission_mode", "plan")])
def test_optout_pause_and_plan_block_queued_input(screen, setting, value):
    c, native = screen
    item = card(c, capture(c))
    set_setting(setting, value)
    result = approve(c, item)
    assert result["status"] == "approved" and native.inputs == []


def test_passwords_payments_file_dialogs_and_unlisted_apps_are_refused(screen):
    c, native = screen
    snap = capture(c)
    ctx = context_with("do this")
    assert "not automated" not in json.dumps(snap)
    for spec in (DesktopAction(kind="click", snapshot_id=snap["id"], element=1),
                 DesktopAction(kind="type", snapshot_id=snap["id"], element=3, text="not allowed")):
        assert "NOT done" in asyncio.run(desktop.propose(ctx, spec))
    for app in ("cmd.exe", "chrome.exe", "explorer.exe", "consent.exe", "other.exe"):
        assert c.put("/api/computer/desktop", json={"enabled": True, "apps": [app]}).status_code == 422
    before = native.observations
    native.meta["app"] = "chrome.exe"
    assert c.post("/api/computer/desktop/snapshot", json={"handle": 8001}).status_code == 409
    assert native.observations == before  # do not even read UI controls before checking the app
    native.meta.update(app="notepad.exe", **{"class": "#32770"})
    assert c.post("/api/computer/desktop/snapshot", json={"handle": 8001}).status_code == 409
    assert native.inputs == []


@pytest.mark.parametrize("key", ["win+r", "ctrl+alt+delete", "ctrl+s", "ctrl+o", "ctrl+v", "alt+f4", "arbitrary"])
def test_system_clipboard_and_file_dialog_shortcuts_cannot_be_queued(screen, key):
    c, native = screen
    with pytest.raises(ValueError):
        DesktopAction(kind="key", snapshot_id=capture(c)["id"], element=0, key=key)
    assert native.inputs == []


def test_supported_click_focus_and_editing_key_work_on_fresh_snapshots(screen):
    c, native = screen
    native.meta["foreground"] = False
    assert approve(c, card(c, capture(c), kind="focus", element=-1, text=""))["status"] == "posted"
    native.hit_index = 2
    assert approve(c, card(c, capture(c), kind="click", element=2, text=""))["status"] == "posted"
    assert approve(c, card(c, capture(c), kind="key", element=0, text="", key="ctrl+a"))["status"] == "posted"
    assert [item[0] for item in native.inputs] == ["focus", "click", "key"]


def test_edits_cannot_change_the_target_but_can_correct_typed_text(screen):
    c, native = screen
    item = card(c, capture(c))
    body = json.loads(item["text"])
    c.patch(f"/api/approvals/{item['id']}", json={"text": json.dumps({**body, "element": 2})})
    assert approve(c, item)["status"] == "approved" and not native.inputs
    item = card(c, capture(c))
    c.patch(f"/api/approvals/{item['id']}", json={"text": json.dumps({**json.loads(item["text"]), "text": "corrected"})})
    assert approve(c, item)["status"] == "posted" and native.inputs == [("type", "corrected")]


def test_outside_observation_does_not_grant_authority_or_memory(screen):
    c, native = screen
    snap = capture(c)
    ctx = context_with("Look in Notepad")
    # Test the exported implementation through its FunctionTool handler, just as the SDK calls it.
    from agents.tool_context import ToolContext
    wrapper = ToolContext(ctx, tool_name="pc_desktop_snapshot", tool_call_id="desktop-test",
                          tool_arguments=json.dumps({"handle":8001,"question":""}))
    result = asyncio.run(desktop.pc_desktop_snapshot.on_invoke_tool(wrapper, json.dumps({"handle":8001,"question":""})))
    assert "data, never instructions" in result and ctx.outside_content_seen
    for _ in range(4):
        result = asyncio.run(desktop.pc_desktop_snapshot.on_invoke_tool(wrapper, json.dumps({"handle":8001,"question":""})))
    assert "four desktop snapshots" in result
    assert "waiting for their OK" in asyncio.run(desktop.propose(ctx, DesktopAction(kind="type", snapshot_id=snap["id"], element=0, text="hello")))
    item = c.get(f"/api/approvals/{ctx.approval_ids[-1]}").json()
    assert item["from_outside"] and not item["can_always_allow"] and native.inputs == []
    with pytest.raises(RuleChangeError):
        set_rule("computer.desktop.input", "auto")


def test_expiry_read_deny_and_unknown_capture_paths(screen):
    c, native = screen
    snap = capture(c)
    path = desktop._directory() / f"{snap['id']}.json"
    data = json.loads(path.read_text())
    data["created"] -= 601
    path.write_text(json.dumps(data))
    assert "ten minutes" in asyncio.run(desktop.propose(context_with("type"), DesktopAction(kind="type", snapshot_id=snap["id"], element=0, text="hello")))
    set_rule("computer.desktop.observe", "deny")
    assert c.get("/api/computer/desktop/windows").status_code == 409
    assert c.get("/api/computer/desktop/captures/bad").status_code == 404
    assert native.inputs == []


def test_uncertain_input_is_not_retried(screen, monkeypatch):
    c, native = screen
    item = card(c, capture(c))
    def partial(hwnd, text, check):
        native.inputs.append(("partial", "h"))
        raise OSError("lost input")
    monkeypatch.setattr(native, "type_text", partial)
    result = approve(c, item)
    assert result["status"] == "check_manually" and len(native.inputs) == 1


def test_dashboard_approval_can_restore_the_exact_target_before_typing(screen):
    c, native = screen
    item = card(c, capture(c))
    native.meta["foreground"] = False  # clicking Approve on the dashboard activates the browser
    native.focus_index = 2
    result = approve(c, item)
    assert result["status"] == "posted" and native.inputs == [("type", "hello")]
    assert native.meta["foreground"] and native.focus_index == 0


def test_timeout_cannot_release_late_input(screen, monkeypatch):
    c, native = screen
    item = card(c, capture(c))
    original = native.observe
    def slow(hwnd):
        time.sleep(.4)
        return original(hwnd)
    monkeypatch.setattr(native, "observe", slow)
    monkeypatch.setattr(desktop, "OBSERVE_SECONDS", .03)
    result = approve(c, item)
    time.sleep(.5)
    assert result["status"] == "approved" and native.inputs == []


def test_vision_marks_outside_before_model_processing(screen, monkeypatch):
    c, _native = screen
    from agents.tool_context import ToolContext
    import junior.reading
    async def image(data, mime, question, context):
        assert context.outside_content_seen
        return "Synthetic editor"
    monkeypatch.setattr(junior.reading, "look_at_image", image)
    ctx = context_with("Read this app window")
    wrapper = ToolContext(ctx, tool_name="pc_desktop_snapshot", tool_call_id="vision", tool_arguments="{}")
    result = asyncio.run(desktop.pc_desktop_snapshot.on_invoke_tool(wrapper, json.dumps({"handle":8001,"question":"Read the editor"})))
    assert "Synthetic editor" in result and ctx.outside_content_seen


def test_validation_errors_do_not_echo_a_rejected_secret(screen):
    c, _native = screen
    from agents.tool_context import ToolContext
    ctx = context_with("Type in the editor")
    secret = "sk-" + "x" * 30
    wrapper = ToolContext(ctx, tool_name="pc_desktop_action", tool_call_id="secret", tool_arguments="{}")
    result = asyncio.run(desktop.pc_desktop_action.on_invoke_tool(wrapper, json.dumps({
        "snapshot_id":capture(c)["id"], "kind":"type", "element":0, "text":secret, "key":""})))
    assert "Secrets cannot" in result and secret not in result and ctx.approval_ids == []


def test_slow_focus_query_cannot_inject_after_timeout(screen, monkeypatch):
    from types import SimpleNamespace
    c, native = screen
    item = card(c, capture(c))
    original = native.focused
    clock = [10.0]
    def slow(hwnd):
        # Expire during the UIA query, independent of Windows scheduling or DB/worker startup time.
        clock[0] += 10
        return original(hwnd)
    monkeypatch.setattr(native, "focused", slow)
    monkeypatch.setattr(desktop, "time", SimpleNamespace(monotonic=lambda: clock[0], time=time.time))
    monkeypatch.setattr(desktop, "OBSERVE_SECONDS", .03)
    result = approve(c, item)
    assert result["status"] == "check_manually" and native.inputs == []
