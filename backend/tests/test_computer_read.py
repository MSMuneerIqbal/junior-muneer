"""P9-02: reading tools - list a folder, find files, read a file. Only through the path guard and the computer.read
rule; secrets are hidden; what a file says is fenced as data."""

import asyncio

import pytest

from junior.computer import tools as pc
from junior.permissions import set_rule
from test_computer_paths import context_with, pc as pc_fixture  # noqa: F401 - the pretend PC

pc_home = pc_fixture


def read(ctx, file, **kw):
    return asyncio.run(pc.read_pc_file_for(ctx, file, **kw))


def test_list_shows_folders_then_files_and_hides_secrets(pc_home):
    user, _ = pc_home
    (user / "Desktop" / "Work").mkdir()
    out = pc.list_folder_for(context_with("hi"), "Desktop")
    lines = out.splitlines()
    assert lines[0].startswith(str(user / "Desktop"))
    assert lines[1].startswith("[folder] Work") and "notes.txt  5 bytes" in out
    assert ".env" not in out and "server.pem" not in out and "(2 item(s) not shown: they hold secrets)" in out


def test_list_outside_or_turned_off_is_refused(pc_home):
    user, _ = pc_home
    assert pc.list_folder_for(context_with("hi"), str(user / "Other")).startswith("NOT done:")
    set_rule("computer.read", "deny")
    assert "turned off" in pc.list_folder_for(context_with("hi"), "Desktop")


def test_find_by_name_and_by_words(pc_home):
    user, _ = pc_home
    (user / "Documents" / "Upwork proposal v2.txt").write_text("Rate: $25 an hour")
    (user / "Documents" / "old").mkdir()
    (user / "Documents" / "old" / "proposal-draft.md").write_text("nothing here")
    (user / "Documents" / "node_modules").mkdir()
    (user / "Documents" / "node_modules" / "proposal.js").write_text("skip me")
    ctx = context_with("hi")
    out = pc.find_files_for(ctx, "Documents", "proposal")
    assert "Upwork proposal v2.txt" in out and "proposal-draft.md" in out and "node_modules" not in out
    out = pc.find_files_for(ctx, "Documents", "*", words="$25 an hour")
    assert "Upwork proposal v2.txt" in out and "proposal-draft.md" not in out
    assert "Nothing in" in pc.find_files_for(ctx, "Documents", "*.pdf")


def test_find_never_returns_secret_files(pc_home):
    out = pc.find_files_for(context_with("hi"), "Desktop", "*")
    assert "notes.txt" in out and ".env" not in out and "server.pem" not in out


def test_read_a_text_file_with_line_numbers_fenced_as_data(pc_home):
    user, _ = pc_home
    ctx = context_with("hi")
    out = read(ctx, str(user / "Desktop" / "notes.txt"))
    assert "1: hello" in out and "START OF THEIR TEXT" in out and ctx.outside_content_seen


def test_long_files_are_read_in_parts(pc_home, monkeypatch):
    user, _ = pc_home
    monkeypatch.setattr(pc, "TEXT_CHARS", 100)
    (user / "Desktop" / "long.py").write_text("\n".join(f"line {n}" for n in range(1, 51)))
    ctx = context_with("hi")
    first = read(ctx, "Desktop/long.py")
    assert "1: line 1" in first and "read on with from_line=" in first
    nxt = int(first.split("from_line=")[1].split(")")[0])
    assert f"{nxt}: line {nxt}" in read(ctx, "Desktop/long.py", from_line=nxt)


def test_read_word_and_csv(pc_home):
    user, _ = pc_home
    from docx import Document

    doc = Document()
    doc.add_paragraph("Invoice 42: Rs 5,000")
    doc.save(user / "Documents" / "invoice.docx")
    (user / "Documents" / "rates.csv").write_text("client,rate\nAcme,25\n")
    ctx = context_with("hi")
    assert "Invoice 42: Rs 5,000" in read(ctx, "Documents/invoice.docx")
    assert "Acme" in read(ctx, "Documents/rates.csv")


def test_photos_go_to_the_vision_reader(pc_home, monkeypatch):
    user, _ = pc_home
    (user / "Downloads" / "receipt.png").write_bytes(b"\x89PNG fake")
    asked = {}

    async def look(data, mime, question, context):
        asked.update(mime=mime, question=question)
        return "Text: Total Rs 900"

    import junior.reading

    monkeypatch.setattr(junior.reading, "look_at_image", look)
    out = read(context_with("hi"), "Downloads/receipt.png", question="what's the total?")
    assert "Total Rs 900" in out and asked == {"mime": "image/png", "question": "what's the total?"}


def test_secrets_binaries_folders_and_huge_files_arent_read(pc_home, monkeypatch):
    user, _ = pc_home
    ctx = context_with(f"read {user / 'Desktop' / '.env'}")
    assert "secrets" in read(ctx, str(user / "Desktop" / ".env"))
    (user / "Desktop" / "tool.exe").write_bytes(b"MZ\x00\x00binary")
    assert "isn't a text file" in read(ctx, "Desktop/tool.exe")
    assert "is a folder" in read(ctx, "Desktop")
    assert "doesn't exist" in read(ctx, "Desktop/missing.txt")
    monkeypatch.setattr(pc, "MAX_READ_BYTES", 3)
    assert "aren't read" in read(ctx, "Desktop/notes.txt")


def test_reads_are_logged(pc_home):
    _, c = pc_home
    pc.list_folder_for(context_with("hi"), "Desktop")
    read(context_with("hi"), "Desktop/notes.txt")
    names = [a["name"] for a in c.get("/api/activity?kind=tool_call").json()]
    assert "pc_list" in names and "pc_read" in names
