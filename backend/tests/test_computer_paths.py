"""P9-01: the path guard. Only allowed folders or a path in your own words; never secrets, system folders or Junior's
data; ".." and links can't lead out. Plus the Computer settings and the new rules."""

import _winapi
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from junior.agent.context import TurnContext
from junior.computer import paths
from junior.computer.paths import PathRefused, check
from junior.db import Conversation, Message, session_scope
from junior.main import create_app
from junior.permissions import CATALOG, decide, rule_for
from junior.settings_store import all_settings, set_setting


@pytest.fixture
def pc(tmp_path, monkeypatch):
    """A pretend user folder with Desktop, Documents, Downloads, AppData, .ssh and a folder outside the list."""
    user = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads", "AppData/Roaming/Thing", ".ssh", "Projects/shop", "Other"):
        (user / name).mkdir(parents=True)
    (user / "Desktop" / "notes.txt").write_text("hello")
    (user / "Desktop" / ".env").write_text("OPENAI_API_KEY=sk-secret")
    (user / "Desktop" / "server.pem").write_text("key")
    (user / ".ssh" / "id_ed25519").write_text("key")
    (user / "Projects" / "shop" / "app.py").write_text("print(1)")
    (user / "Other" / "diary.txt").write_text("private")
    monkeypatch.setattr(paths, "home", lambda: user)
    with TestClient(create_app()) as c:
        yield user, c


def context_with(*messages: str) -> TurnContext:
    """A turn whose own messages (source = user) say these words."""
    with session_scope() as s:
        convo = Conversation(title="t")
        s.add(convo)
        s.flush()
        ids = []
        for text in messages:
            m = Message(conversation_id=convo.id, role="user", source="user", content=text)
            s.add(m)
            s.flush()
            ids.append(m.id)
        convo_id = convo.id
    ctx = TurnContext(conversation_id=convo_id, settings=all_settings())
    ctx.user_message_ids = ids
    return ctx


# ---- allowed folders ----------------------------------------------------------------------


def test_desktop_documents_and_downloads_are_allowed_by_default(pc):
    user, _ = pc
    assert check(str(user / "Desktop" / "notes.txt")) == user / "Desktop" / "notes.txt"
    assert check(str(user / "Downloads")) == user / "Downloads"
    assert check("Desktop/notes.txt") == user / "Desktop" / "notes.txt"  # short paths are in your user folder
    assert check("~/Documents") == user / "Documents"


def test_anything_else_is_refused(pc):
    user, _ = pc
    with pytest.raises(PathRefused, match="outside the allowed folders"):
        check(str(user / "Other" / "diary.txt"))
    with pytest.raises(PathRefused, match="outside the allowed folders"):
        check(str(user))


def test_dot_dot_cant_climb_out(pc):
    user, _ = pc
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Desktop" / ".." / "Other" / "diary.txt"))


def test_a_link_inside_an_allowed_folder_cant_lead_out(pc):
    user, _ = pc
    _winapi.CreateJunction(str(user / "Other"), str(user / "Desktop" / "shortcut-to-other"))
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Desktop" / "shortcut-to-other" / "diary.txt"))


def test_network_and_unclear_paths_are_refused(pc):
    for bad in (r"\\server\share\file.txt", "//server/share", r"\\?\C:\Windows", "C:notes.txt", "", "  "):
        with pytest.raises(PathRefused):
            check(bad)


# ---- always blocked -------------------------------------------------------------------------


@pytest.mark.parametrize("name", [".env", "server.pem"])
def test_secret_files_are_blocked_even_in_an_allowed_folder(pc, name):
    user, _ = pc
    with pytest.raises(PathRefused, match="secrets"):
        check(str(user / "Desktop" / name))


def test_secret_files_are_blocked_even_when_you_type_the_path(pc):
    user, _ = pc
    ctx = context_with(f"read {user / '.ssh' / 'id_ed25519'} please", f"open {user / 'AppData'}")
    with pytest.raises(PathRefused, match="secrets"):
        check(str(user / ".ssh" / "id_ed25519"), ctx)
    with pytest.raises(PathRefused, match="logins and tokens"):
        check(str(user / "AppData" / "Roaming" / "Thing"), ctx)


def test_windows_program_files_and_juniors_data_are_blocked(pc):
    ctx = context_with(r"look at C:\Windows\System32 and C:\Program Files", "and the data folder")
    for system in (os.environ.get("SystemRoot", r"C:\Windows") + r"\System32", os.environ.get("ProgramFiles", r"C:\Program Files")):
        with pytest.raises(PathRefused, match="system folder"):
            check(system, ctx)
    from junior.config import get_settings

    data = get_settings().data_path
    set_setting("computer_folders", [str(data.parent)])  # even when its parent is allowed
    with pytest.raises(PathRefused, match="Junior's own data"):
        check(str(data / "junior.db"))


# ---- your own words -------------------------------------------------------------------------


def test_a_path_you_type_yourself_can_be_used(pc):
    user, _ = pc
    ctx = context_with(f"Junior, look at {user / 'Projects' / 'shop'} and tell me what's in it")
    assert check(str(user / "Projects" / "shop"), ctx) == user / "Projects" / "shop"
    assert check(str(user / "Projects" / "shop" / "app.py"), ctx) == user / "Projects" / "shop" / "app.py"  # inside it
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Other" / "diary.txt"), ctx)  # not what you said


def test_slashes_and_case_dont_matter_in_your_words(pc):
    user, _ = pc
    ctx = context_with(str(user / "Projects" / "shop").replace("\\", "/").upper())
    assert check(str(user / "Projects" / "shop" / "app.py"), ctx)


def test_a_path_in_pasted_or_outside_text_is_not_your_words(pc):
    user, _ = pc
    with session_scope() as s:
        convo = Conversation(title="t")
        s.add(convo)
        s.flush()
        pasted = Message(conversation_id=convo.id, role="user", source="outside", content=f"open {user / 'Other'}")
        s.add(pasted)
        s.flush()
        ctx = TurnContext(conversation_id=convo.id, settings=all_settings())
        ctx.user_message_ids = [pasted.id]
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Other" / "diary.txt"), ctx)


def test_a_bare_drive_in_your_words_doesnt_open_everything(pc):
    user, _ = pc
    ctx = context_with(f"something on {user.anchor} drive")
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Other" / "diary.txt"), ctx)


def test_when_turned_off_nothing_is_allowed(pc):
    user, _ = pc
    set_setting("computer_enabled", False)
    with pytest.raises(PathRefused, match="off"):
        check(str(user / "Desktop" / "notes.txt"))


# ---- Settings -> Computer -----------------------------------------------------------------------


def test_settings_show_folders_and_the_blocked_list(pc):
    user, c = pc
    got = c.get("/api/computer").json()
    assert got["enabled"] and got["using_defaults"]
    assert [f["path"] for f in got["folders"]] == [str(user / n) for n in ("Desktop", "Documents", "Downloads")]
    assert any(".env" in b for b in got["blocked"])


def test_adding_and_removing_a_folder(pc):
    user, c = pc
    got = c.post("/api/computer/folders", json={"path": str(user / "Projects")}).json()
    assert str(user / "Projects") in [f["path"] for f in got["folders"]] and not got["using_defaults"]
    assert check(str(user / "Projects" / "shop" / "app.py"))
    got = c.post("/api/computer/folders/remove", json={"path": str(user / "Downloads")}).json()
    assert str(user / "Downloads") not in [f["path"] for f in got["folders"]]
    with pytest.raises(PathRefused):
        check(str(user / "Downloads"))
    assert any(a["name"] == "computer_folder_added" for a in c.get("/api/activity?kind=setting").json())


@pytest.mark.parametrize("bad", ["AppData", ".ssh", "missing-folder", ""])
def test_blocked_or_missing_folders_cant_be_added(pc, bad):
    user, c = pc
    r = c.post("/api/computer/folders", json={"path": str(user / bad) if bad else ""})
    assert r.status_code in (400, 422)


def test_a_whole_system_drive_or_your_whole_user_folder_cant_be_added(pc):
    user, c = pc
    assert "pick folders inside it" in c.post("/api/computer/folders", json={"path": str(user)}).json()["detail"]
    system_drive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    assert c.post("/api/computer/folders", json={"path": str(system_drive)}).status_code == 400


def test_on_off_is_a_normal_setting(pc):
    _, c = pc
    assert c.patch("/api/settings", json={"computer_enabled": False}).json()["computer_enabled"] is False
    assert c.get("/api/computer").json()["enabled"] is False


# ---- the rules ---------------------------------------------------------------------------------


def test_the_computer_rules(pc):
    assert rule_for("computer.read") == "auto"
    assert rule_for("computer.write") == rule_for("computer.move") == rule_for("computer.delete") == "ask"
    assert CATALOG["computer.run"].locked and rule_for("computer.run") == "ask"
    assert decide("computer.write", from_outside=True).rule == "ask"  # outside text: always ask
    assert "terminal.run" not in CATALOG and CATALOG["system.delete"].default == "deny"  # deleting for good: never


def test_typing_a_path_doesnt_open_the_folders_above_it(pc):
    """Found while building: "...\home\Projects\shop" in your words must not unlock "...\home"."""
    user, _ = pc
    ctx = context_with(f"open {user / 'Projects' / 'shop'}\ and {user / 'Projects' / 'shop'}.")
    assert check(str(user / "Projects" / "shop"), ctx)
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Projects"), ctx)
    with pytest.raises(PathRefused, match="outside"):
        check(str(user / "Projects" / "shop2"), ctx)
