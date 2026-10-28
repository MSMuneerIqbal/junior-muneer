"""P9-03: writing files and making folders through approval cards. Ask waits for Approve; Auto runs at once; outside
text makes it Ask; the path is checked again right before it runs; a replaced file goes to the Recycle Bin."""

import _winapi
import asyncio
import shutil

import pytest

from junior.computer import sender as pc_sender
from junior.computer import tools as pc
from junior.permissions import set_mode, set_rule
from junior.settings_store import set_setting
from test_computer_paths import context_with, pc as pc_fixture  # noqa: F401 - the pretend PC

pc_home = pc_fixture


@pytest.fixture
def bin_(pc_home, monkeypatch):
    """A pretend Recycle Bin, so tests never fill the real one."""
    user, _ = pc_home
    trash = user.parent / "recycle-bin"
    trash.mkdir()
    monkeypatch.setattr(pc_sender, "to_recycle_bin", lambda p: shutil.move(str(p), str(trash / p.name)))
    return trash


def write(ctx, file, content, replace=False):
    return asyncio.run(pc.write_file_for(ctx, file, content, replace))


def card(c, ctx):
    return c.get(f"/api/approvals/{ctx.approval_ids[-1]}").json()


def test_ask_makes_a_card_and_nothing_changes_until_approve(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("make notes.txt on my desktop")
    out = write(ctx, "Desktop/new-notes.txt", "Buy milk\nCall Ali\n")
    assert "NOT done yet - waiting for their OK" in out and not (user / "Desktop" / "new-notes.txt").exists()
    item = card(c, ctx)
    assert item["platform"] == "computer" and item["status"] == "waiting" and item["title"].startswith("Create ")
    done = c.post(f"/api/approvals/{item['id']}/approve", json={}).json()
    assert done["status"] == "posted" and done["meta"]["result"].startswith("Created:")
    assert (user / "Desktop" / "new-notes.txt").read_text() == "Buy milk\nCall Ali\n"


def test_auto_writes_at_once(pc_home, bin_):
    user, c = pc_home
    set_rule("computer.write", "auto")
    out = write(context_with("hi"), "Documents/todo.md", "- gym\n")
    assert out.startswith("Done (their rule is Auto)") and (user / "Documents" / "todo.md").read_text() == "- gym\n"


def test_disabling_all_drives_blocks_pending_out_of_scope_write(pc_home):
    user, c = pc_home
    set_setting("computer_all_files", True)
    ctx = context_with("make a note")
    destination = user / "Other" / "note.txt"
    write(ctx, str(destination), "hello")
    item = card(c, ctx)
    assert item["meta"]["requires_all_files"]
    set_setting("computer_all_files", False)
    result = c.post(f"/api/approvals/{item['id']}/approve", json={}).json()
    assert result["status"] != "posted" and not destination.exists()
    assert "turned off" in " ".join(result["meta"].get("blocked", []))


def test_outside_text_makes_it_ask_even_on_auto(pc_home, bin_):
    user, _ = pc_home
    set_rule("computer.write", "auto")
    ctx = context_with("hi")
    ctx.mark_outside()  # e.g. an email or a web page was read in this turn
    assert "NOT done yet - waiting for their OK" in write(ctx, "Desktop/x.txt", "from an email")
    assert not (user / "Desktop" / "x.txt").exists()


def test_changing_a_file_needs_replace_shows_the_change_and_keeps_the_old_one(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("hi")
    assert "already exists" in write(ctx, "Desktop/notes.txt", "hello world")
    write(ctx, "Desktop/notes.txt", "hello world", replace=True)
    item = card(c, ctx)
    assert item["title"].startswith("Change ") and "-hello" in item["meta"]["diff"] and "+hello world" in item["meta"]["diff"]
    c.post(f"/api/approvals/{item['id']}/approve", json={})
    assert (user / "Desktop" / "notes.txt").read_text() == "hello world"
    assert (bin_ / "notes.txt").read_text() == "hello"  # the old version, for undo


def test_a_file_changed_after_the_card_isnt_overwritten(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("hi")
    write(ctx, "Desktop/notes.txt", "my version", replace=True)
    (user / "Desktop" / "notes.txt").write_text("he edited it meanwhile")
    done = c.post(f"/api/approvals/{card(c, ctx)['id']}/approve", json={}).json()
    assert "changed since the card was made" in done["meta"]["last_error"]
    assert (user / "Desktop" / "notes.txt").read_text() == "he edited it meanwhile"


def test_you_can_edit_the_text_on_the_card_before_approving(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("hi")
    write(ctx, "Desktop/letter.txt", "Dear Sir, draft")
    item_id = card(c, ctx)["id"]
    c.patch(f"/api/approvals/{item_id}", json={"text": "Dear Ali, final"})
    c.post(f"/api/approvals/{item_id}/approve", json={})
    assert (user / "Desktop" / "letter.txt").read_text() == "Dear Ali, final"


def test_keys_never_get_written(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("hi")
    write(ctx, "Desktop/config.txt", "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456")
    done = c.post(f"/api/approvals/{card(c, ctx)['id']}/approve", json={})
    assert not (user / "Desktop" / "config.txt").exists()
    assert "API key" in c.get(f"/api/approvals/{card(c, ctx)['id']}").json()["meta"]["blocked"][0] or done.status_code >= 400


def test_code_with_todo_and_pwd_is_fine(pc_home, bin_):
    user, c = pc_home
    set_rule("computer.write", "auto")
    write(context_with("hi"), "Desktop/app.py", "import os\npwd = os.getcwd()  # TODO: tidy\n")
    assert "TODO" in (user / "Desktop" / "app.py").read_text()


def test_outside_allowed_folders_or_secret_files_are_refused(pc_home, bin_):
    user, _ = pc_home
    ctx = context_with("hi")
    assert "outside the allowed folders" in write(ctx, str(user / "Other" / "x.txt"), "x")
    assert "secrets" in write(ctx, "Desktop/.env", "A=1")
    assert "doesn't exist" in write(ctx, "Desktop/nope/x.txt", "x")
    assert "empty" in write(ctx, "Desktop/x.txt", "   ")


def test_make_a_folder(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("hi")
    asyncio.run(pc.make_folder_for(ctx, "Documents/Clients/Acme"))
    c.post(f"/api/approvals/{card(c, ctx)['id']}/approve", json={})
    assert (user / "Documents" / "Clients" / "Acme").is_dir()


def test_turned_off_before_approve_means_it_doesnt_run(pc_home, bin_):
    user, c = pc_home
    ctx = context_with("hi")
    write(ctx, "Desktop/late.txt", "x")
    set_setting("computer_enabled", False)
    c.post(f"/api/approvals/{card(c, ctx)['id']}/approve", json={})
    assert not (user / "Desktop" / "late.txt").exists()


def test_a_link_swapped_in_after_the_card_is_caught(pc_home, bin_):
    user, c = pc_home
    (user / "Desktop" / "work").mkdir()
    ctx = context_with("hi")
    write(ctx, "Desktop/work/plan.txt", "plan")
    (user / "Desktop" / "work").rmdir()
    _winapi.CreateJunction(str(user / "Other"), str(user / "Desktop" / "work"))  # now leads outside
    c.post(f"/api/approvals/{card(c, ctx)['id']}/approve", json={})
    assert not (user / "Other" / "plan.txt").exists()
    assert "leads somewhere else" in c.get(f"/api/approvals/{card(c, ctx)['id']}").json()["meta"]["last_error"]


def test_plan_mode_and_the_per_message_limit(pc_home, bin_, monkeypatch):
    ctx = context_with("hi")
    set_mode("plan")
    assert "Plan mode" in write(ctx, "Desktop/a.txt", "a")
    set_mode("rules")
    monkeypatch.setattr(pc, "MAX_ACTIONS_PER_TURN", 2)
    write(ctx, "Desktop/a.txt", "a")
    write(ctx, "Desktop/b.txt", "b")
    assert "at most 2 computer actions" in write(ctx, "Desktop/c.txt", "c")


# ---- P9-04: move and delete --------------------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


def test_rename_and_move_into_a_folder(pc_home, bin_):
    user, c = pc_home
    (user / "Documents" / "Archive").mkdir()
    ctx = context_with("hi")
    run(pc.move_for(ctx, "Desktop/notes.txt", "Desktop/old-notes.txt"))
    item = card(c, ctx)
    assert item["title"] == "Rename notes.txt" and item["item_type"] == "move" and item["status"] == "waiting"
    assert (user / "Desktop" / "notes.txt").exists()  # nothing until Approve
    c.post(f"/api/approvals/{item['id']}/approve", json={})
    assert (user / "Desktop" / "old-notes.txt").read_text() == "hello"
    run(pc.move_for(ctx, "Desktop/old-notes.txt", "Documents/Archive"))
    c.post(f"/api/approvals/{card(c, ctx)['id']}/approve", json={})
    assert (user / "Documents" / "Archive" / "old-notes.txt").exists()


def test_move_refuses_overwriting_outside_and_into_itself(pc_home, bin_):
    user, _ = pc_home
    (user / "Desktop" / "a.txt").write_text("a")
    (user / "Desktop" / "Box").mkdir()
    ctx = context_with("hi")
    assert "already exists" in run(pc.move_for(ctx, "Desktop/a.txt", "Desktop/notes.txt"))
    assert "outside" in run(pc.move_for(ctx, "Desktop/a.txt", str(user / "Other")))
    assert "inside itself" in run(pc.move_for(ctx, "Desktop/Box", "Desktop/Box/Inner"))
    assert "allowed folders" in run(pc.move_for(ctx, "Desktop", "Documents"))
    assert "secrets" in run(pc.move_for(ctx, "Desktop/.env", "Documents/env.txt"))  # can't move a secret out of hiding


def test_delete_goes_to_the_recycle_bin_after_approve(pc_home, bin_):
    user, c = pc_home
    (user / "Downloads" / "old.zip").write_bytes(b"x" * 2048)
    ctx = context_with("hi")
    run(pc.delete_for(ctx, "Downloads/old.zip"))
    item = card(c, ctx)
    assert "Delete the file" in item["text"] and "2.0 KB" in item["text"] and "Recycle Bin" in item["text"]
    assert (user / "Downloads" / "old.zip").exists()
    done = c.post(f"/api/approvals/{item['id']}/approve", json={}).json()
    assert done["status"] == "posted" and "Recycle Bin" in done["meta"]["result"]
    assert not (user / "Downloads" / "old.zip").exists() and (bin_ / "old.zip").exists()


def test_deleting_a_folder_says_how_much_is_in_it(pc_home, bin_):
    user, c = pc_home
    box = user / "Documents" / "Clients"
    (box / "Acme").mkdir(parents=True)
    for n in range(3):
        (box / "Acme" / f"f{n}.txt").write_text("x")
    ctx = context_with("hi")
    run(pc.delete_for(ctx, "Documents/Clients"))
    assert "(3 files" in card(c, ctx)["text"]


def test_allowed_folders_secrets_and_missing_things_cant_be_deleted(pc_home, bin_):
    user, _ = pc_home
    ctx = context_with("hi")
    assert "allowed folders" in run(pc.delete_for(ctx, "Desktop"))
    assert "secrets" in run(pc.delete_for(ctx, "Desktop/.env"))
    assert "doesn't exist" in run(pc.delete_for(ctx, "Desktop/nothing.txt"))
    assert "outside" in run(pc.delete_for(ctx, str(user / "Other" / "diary.txt")))


def test_delete_rule_auto_and_deny(pc_home, bin_):
    user, _ = pc_home
    set_rule("computer.delete", "auto")
    assert run(pc.delete_for(context_with("hi"), "Desktop/notes.txt")).startswith("Done")
    assert (bin_ / "notes.txt").exists()
    set_rule("computer.delete", "deny")
    (user / "Desktop" / "b.txt").write_text("b")
    assert "Never runs" in run(pc.delete_for(context_with("hi"), "Desktop/b.txt"))
    assert (user / "Desktop" / "b.txt").exists()
