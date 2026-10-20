"""Junior Muneer's Google tools: Docs and Sheets (create, read). Every action goes through the gate (junior/gate.py);
everything read is fenced as outside text."""

from agents import RunContextWrapper, function_tool

from junior import gate
from junior.agent.context import TurnContext
from junior.google import auth
from junior.google.auth import GoogleError

Ctx = RunContextWrapper[TurnContext]

NEEDS = {
    "drive.file": "creating Docs and Sheets",
    "documents.readonly": "reading your Google Docs",
    "spreadsheets.readonly": "reading your Google Sheets",
    "calendar.events": "your calendar",
    "drive.readonly": "finding files in your Drive",
}


def _not_ready(scope: str) -> str | None:
    """Why this can't be used yet (Google not set up, not connected, or that permission not allowed)."""
    if not auth.configured():
        return "NOT done: Google isn't set up yet (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env)."
    if not auth.is_connected():
        return "NOT done: Google isn't connected. Tell the user to use Connect Google in Settings → Connections."
    if not auth.has_scope(scope):
        return (
            f"NOT done: when connecting Google, the user didn't allow {NEEDS[scope]}. "
            "They can use Connect again in Settings → Connections and tick it."
        )
    return None


# ---- Docs ------------------------------------------------------------------------------


async def doc_create_for(context: TurnContext, title: str, content: str, your_words: str) -> str:
    from junior.google.docs import create_doc

    from junior.writing.polish import polish

    action = "google.docs.create"
    if refusal := _not_ready("drive.file") or gate.check(context, action, your_words=your_words):
        return refusal
    content = await polish(content, "a Google Doc (keep its # headings and - lists)", context)
    try:
        _id, link = await create_doc(title, content)
    except GoogleError as e:
        gate.failed(context, action, str(e))
        return f"NOT done: {e}"
    gate.done(context, action, {"title": title[:200], "link": link, "characters": len(content)})
    return f"Created the Google Doc {title!r}: {link}\nGive the user this link."


async def doc_read_for(context: TurnContext, link: str) -> str:
    from junior.google.docs import read_doc

    if refusal := _not_ready("documents.readonly"):
        return refusal
    try:
        title, text = await read_doc(link)
    except GoogleError as e:
        return f"Couldn't read it: {e}"
    return gate.fence(context, text or "(the doc is empty)", f"the Google Doc {title!r}")


@function_tool
async def google_doc_create(ctx: Ctx, title: str, content: str, your_words: str) -> str:
    """Create a new Google Doc in the user's Drive with content you wrote (a research plan, notes, a draft...),
    and get its link. Write the full content first; it's put in as is.

    Args:
        title: The doc's title.
        content: The full text. Light markdown works: # Heading, ## Subheading, - bullets, 1. numbered, **bold**.
        your_words: The user's exact words asking for a doc (copied word for word), e.g. "make a google doc of it".
    """
    return await doc_create_for(ctx.context, title, content, your_words)


@function_tool
async def google_doc_read(ctx: Ctx, link: str) -> str:
    """Read one of the user's Google Docs by its link (docs.google.com/document/d/...), to answer from it,
    summarize it or use it.

    Args:
        link: The doc's link, as the user gave it.
    """
    return await doc_read_for(ctx.context, link)


# ---- Sheets ----------------------------------------------------------------------------


async def sheet_create_for(context: TurnContext, title: str, headers: list[str], rows: list[list[str]], your_words: str) -> str:
    from junior.google.sheets import create_sheet

    action = "google.sheets.create"
    if refusal := _not_ready("drive.file") or gate.check(context, action, your_words=your_words):
        return refusal
    try:
        _id, link = await create_sheet(title, headers, rows)
    except GoogleError as e:
        gate.failed(context, action, str(e))
        return f"NOT done: {e}"
    gate.done(context, action, {"title": title[:200], "link": link, "rows": len(rows), "columns": len(headers)})
    return f"Created the Google Sheet {title!r} with {len(rows)} rows: {link}\nGive the user this link."


async def sheet_read_for(context: TurnContext, link: str, tab: str = "") -> str:
    from junior.google.sheets import as_table, read_sheet

    if refusal := _not_ready("spreadsheets.readonly"):
        return refusal
    try:
        title, chosen, rows, tabs = await read_sheet(link, tab)
    except GoogleError as e:
        return f"Couldn't read it: {e}"
    note = f"Tabs: {', '.join(tabs)}. Read: {chosen!r}, {len(rows)} rows (row 1 is usually the header)."
    return note + "\n" + gate.fence(context, as_table(rows) or "(the tab is empty)", f"the Google Sheet {title!r}")


@function_tool
async def google_sheet_create(ctx: Ctx, title: str, headers: list[str], rows: list[list[str]], your_words: str) -> str:
    """Create a new Google Sheet in the user's Drive from a list you gathered (e.g. professors with their emails),
    and get its link. Only put in what you really found; add a column with each row's source link when it came
    from the web, and leave a cell empty (or "not listed") instead of guessing.

    Args:
        title: The sheet's title.
        headers: The column names, e.g. ["Name", "Department", "Email", "Source"].
        rows: One list per row, in the same order as the headers.
        your_words: The user's exact words asking for a sheet (copied word for word).
    """
    return await sheet_create_for(ctx.context, title, headers, rows, your_words)


@function_tool
async def google_sheet_read(ctx: Ctx, link: str, tab: str = "") -> str:
    """Read one of the user's Google Sheets by its link (docs.google.com/spreadsheets/d/...): its rows, to answer
    questions, add things up or find trends.

    Args:
        link: The sheet's link, as the user gave it.
        tab: Which tab to read (the first one if empty).
    """
    return await sheet_read_for(ctx.context, link, tab)


# ---- Calendar --------------------------------------------------------------------------


async def calendar_add_for(
    context: TurnContext,
    title: str,
    start: str,
    your_words: str,
    end: str = "",
    all_day: bool = False,
    location: str = "",
    notes: str = "",
    reminder_minutes: int | None = None,
) -> str:
    from junior.google.calendar import add_event, describe

    action = "google.calendar.create"
    if refusal := _not_ready("calendar.events") or gate.check(context, action, your_words=your_words):
        return refusal
    tz = context.settings["timezone"]
    try:
        event = await add_event(title, start, end, all_day, location, notes, reminder_minutes, tz)
    except GoogleError as e:
        gate.failed(context, action, str(e))
        return f"NOT done: {e}"
    when = describe(event, tz)
    gate.done(context, action, {"event": when, "link": event.get("htmlLink", "")})
    return f"Added to their Google Calendar: {when}. Link: {event.get('htmlLink', '')}\nTell them in one line, with the day and time."


async def calendar_list_for(context: TurnContext, days: int = 7, search: str = "") -> str:
    from junior.google.calendar import describe, upcoming

    if refusal := _not_ready("calendar.events"):
        return refusal
    tz = context.settings["timezone"]
    try:
        events = await upcoming(days, tz, query=search)
    except GoogleError as e:
        return f"Couldn't read the calendar: {e}"
    if not events:
        return f"Nothing on their Google Calendar in the next {days} day(s)" + (f" matching {search!r}." if search else ".")
    lines = "\n".join(f"- {describe(e, tz)}" for e in events)
    return gate.fence(context, lines, f"their Google Calendar, the next {days} day(s), in their time zone")


@function_tool
async def calendar_add_event(
    ctx: Ctx,
    title: str,
    start: str,
    your_words: str,
    end: str = "",
    all_day: bool = False,
    location: str = "",
    notes: str = "",
    reminder_minutes: int | None = None,
) -> str:
    """Add an event to the user's own Google Calendar when they ask ("add my exam on 5 Nov at 10am"). Nobody is
    invited. Work out the exact date from today's date; if the day or time is unclear, ask first instead.

    Args:
        title: What it is, e.g. "Data Mining exam".
        start: Their local time, "YYYY-MM-DD HH:MM" (or "YYYY-MM-DD" when all_day).
        your_words: The user's exact words asking for it (copied word for word).
        end: When it ends, same format; empty = one hour after the start (or the same day when all_day).
        all_day: True for a whole-day event (a deadline, a holiday, a trip).
        location: Where, if they said.
        notes: Anything else they said about it.
        reminder_minutes: A pop-up reminder this many minutes before, if they asked for one.
    """
    return await calendar_add_for(ctx.context, title, start, your_words, end, all_day, location, notes, reminder_minutes)


@function_tool
async def calendar_events(ctx: Ctx, days: int = 7, search: str = "") -> str:
    """What's on the user's Google Calendar from now on ("what's on tomorrow?", "when is my exam?").

    Args:
        days: How many days ahead to look (1 to 60). For "tomorrow" use 2; for "this week" use 7.
        search: Words to look for in the events, e.g. "exam" (empty for everything).
    """
    return await calendar_list_for(ctx.context, days, search)


# ---- Drive -----------------------------------------------------------------------------


async def drive_search_for(context: TurnContext, words: str) -> str:
    from junior.google.drive import kind, search

    if refusal := _not_ready("drive.readonly"):
        return refusal
    try:
        files = await search(words)
    except GoogleError as e:
        return f"Couldn't search the Drive: {e}"
    if not files:
        return f"No files in their Drive with {words!r} in the name. Try other words from the name."
    lines = "\n".join(
        f"- {f['name']} ({kind(f.get('mimeType', ''))}, changed {f.get('modifiedTime', '')[:10]}): {f.get('webViewLink', '')}"
        for f in files
    )
    return gate.fence(context, lines, "file names in their Google Drive, newest first")


@function_tool
async def drive_search(ctx: Ctx, words: str) -> str:
    """Find files in the user's Google Drive by name ("my CV", "the invoice from September"). Returns each file's
    name, type, date and link. To send one, pass its link to send_to_me as file_link.

    Args:
        words: A few words from the file's name, e.g. "cv" or "muneer iqbal cv". Fewer words find more.
    """
    return await drive_search_for(ctx.context, words)


async def drive_save_for(context: TurnContext, file_number: int, your_words: str, folder: str = "", new_name: str = "") -> str:
    from junior.files import mark_saved, received, safe_name
    from junior.google.drive import save_file

    action = "google.drive.save"
    if refusal := _not_ready("drive.file") or gate.check(context, action, your_words=your_words):
        return refusal
    got = received(file_number)
    if got is None:
        return f"NOT done: there's no file {file_number} (it may have been removed). Ask them to send it again."
    row, data = got
    name = safe_name(new_name) if new_name.strip() else row.filename
    if new_name.strip() and "." not in name and "." in row.filename:
        name += "." + row.filename.rsplit(".", 1)[1]  # keep its ending (.pdf, .jpg)
    try:
        saved, note = await save_file(name, data, row.mime, folder)
    except GoogleError as e:
        gate.failed(context, action, str(e))
        return f"NOT done: {e}"
    link = saved.get("webViewLink", "")
    mark_saved(file_number, link)
    gate.done(context, action, {"file": name, "folder": folder, "link": link})
    where = f" in {folder!r}" if folder and not note else ""
    return f"Saved {name!r} to their Google Drive{where}: {link}" + (f"\nNote: {note}" if note else "") + "\nGive them the link."


@function_tool
async def drive_save(ctx: Ctx, file_number: int, your_words: str, folder: str = "", new_name: str = "") -> str:
    """Save a file the user sent you (a message tagged "[file N: ...]") to their Google Drive, as a new file.

    Args:
        file_number: The N from the "[file N: ...]" tag.
        your_words: The user's exact words asking you to save it (copied word for word), e.g. "save it to my drive".
        folder: A folder to put it in, if they named one ("University", or "Work/Invoices"). Made if it doesn't exist.
        new_name: A new name for it, if they asked for one.
    """
    return await drive_save_for(ctx.context, file_number, your_words, folder, new_name)


async def drive_read_for(context: TurnContext, link: str, question: str = "") -> str:
    from junior.google.drive import for_reading
    from junior.reading import ReadError, extract_text, is_image, look_at_image

    if refusal := _not_ready("drive.readonly"):
        return refusal
    try:
        name, data, mime = await for_reading(link)
        if is_image(mime, name):
            text = await look_at_image(data, mime, question, context)
        else:
            text = extract_text(data, mime, name)
    except (GoogleError, ReadError) as e:
        return f"Couldn't read it: {e}"
    return gate.fence(context, text, f"the file {name!r} from their Google Drive")


@function_tool
async def drive_read(ctx: Ctx, link: str, question: str = "") -> str:
    """Read what's inside a file in the user's Google Drive, by its link (from drive_search or drive_folder):
    Google Docs, Sheets and Slides, PDFs, Word, Excel, CSV and text files, and photos (the text in them and what
    they show). Use it when they ask you to read, summarize or answer from a file; to send them the file itself,
    use send_to_me instead.

    Args:
        link: The file's Drive link.
        question: What they want to know from it, if they said (helps with photos).
    """
    return await drive_read_for(ctx.context, link, question)


async def drive_folder_for(context: TurnContext, name: str) -> str:
    from junior.google.drive import folder_contents, kind

    if refusal := _not_ready("drive.readonly"):
        return refusal
    try:
        found = await folder_contents(name)
    except GoogleError as e:
        return f"Couldn't look in the Drive: {e}"
    if not found:
        return f"No folder with {name!r} in its name in their Drive. Try other words, or drive_search for the file itself."
    blocks = []
    for folder, inside in found:
        lines = [
            f"- {f['name']} ({kind(f.get('mimeType', ''))}, changed {f.get('modifiedTime', '')[:10]}): {f.get('webViewLink', '')}"
            for f in inside
        ] or ["(empty)"]
        blocks.append(f"Folder {folder['name']!r} ({folder.get('webViewLink', '')}):\n" + "\n".join(lines))
    return gate.fence(context, "\n\n".join(blocks), "folders and file names in their Google Drive")


@function_tool
async def drive_folder(ctx: Ctx, name: str) -> str:
    """What's inside a folder in the user's Google Drive ("what's in my University folder?"): each file's name,
    type, date and link. Then read a file with drive_read, or send it with send_to_me.

    Args:
        name: Words from the folder's name, e.g. "University" or "semester 3".
    """
    return await drive_folder_for(ctx.context, name)


# ---- Gmail -------------------------------------------------------------------------------


def _gmail_ready(scope: str) -> str | None:
    if refusal := _not_ready("drive.file"):  # Google set up and connected at all
        return refusal
    if not auth.has_scope(scope):
        return "NOT done: Gmail isn't allowed yet. Tell the user to use Connect again in Settings → Connections and tick Gmail."
    return None


def _email_row(number: int):
    from junior.db import Email, session_scope

    with session_scope() as s:
        row = s.get(Email, number)
        if row is not None:
            s.expunge(row)
        return row


async def gmail_search_for(context: TurnContext, query: str, limit: int = 10) -> str:
    from junior.google.gmail import search

    if refusal := _gmail_ready("gmail.readonly"):
        return refusal
    try:
        found = await search(query, limit)
    except GoogleError as e:
        return f"Couldn't search Gmail: {e}"
    if not found:
        return f"No emails match {query!r}."
    lines = "\n".join(
        f"- [{m['id']}] {m['date'][:16].replace('T', ' ')} from {m['from_name'] or m['from_address']} <{m['from_address']}>: "
        f"{m['subject']} | {m['snippet'][:160]}"
        for m in found
    )
    return gate.fence(context, lines, "emails in their Gmail (id in brackets)")


async def gmail_read_for(context: TurnContext, email: str) -> str:
    from junior.google.gmail import read

    if refusal := _gmail_ready("gmail.readonly"):
        return refusal
    email = email.strip()
    if email.isdigit() and (row := _email_row(int(email))) is not None:
        email = row.gmail_id  # "email 12" from the inbox list or an alert
    try:
        m = await read(email)
    except GoogleError as e:
        return f"Couldn't read it: {e}"
    files = f"\nAttachments: {', '.join(m['attachments'])}" if m["attachments"] else ""
    text = (f"From: {m['from_name']} <{m['from_address']}>\nTo: {m['to']}\n" + (f"Cc: {m['cc']}\n" if m["cc"] else "")
            + f"Date: {m['date']}\nSubject: {m['subject']}{files}\n\n{m['body'] or m['snippet']}")
    return gate.fence(context, text, f"an email from {m['from_address']}") + f"\nOpen in Gmail: {m['link']}"


async def gmail_draft_for(
    context: TurnContext, to: str, subject: str, body: str, your_words: str, reply_to: str = "", cc: str = "",
    pc_file: str = "",
) -> str:
    from junior.approvals import ApprovalError, create_item
    from junior.google.gmail import make_draft, read, valid_addresses

    if refusal := _gmail_ready("gmail.compose") or gate.check(context, "gmail.draft", your_words=your_words):
        return refusal
    thread_id = in_reply_to = references = ""
    if reply_to.strip():
        if refusal := _gmail_ready("gmail.readonly"):
            return refusal
        target = reply_to.strip()
        if target.isdigit() and (row := _email_row(int(target))) is not None:
            target = row.gmail_id
        try:
            original = await read(target)
        except GoogleError as e:
            return f"NOT done: couldn't open the email to reply to ({e})."
        to = to.strip() or original["from_address"]
        subject = subject.strip() or original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        thread_id, in_reply_to, references = original["thread_id"], original["message_id_header"], original["references"]
    try:
        recipients = valid_addresses(to)
        valid_addresses(cc)
    except GoogleError as e:
        return f"NOT done: {e} Ask them for the right address."
    if not recipients:
        return "NOT done: who should it go to? Ask them for the email address."
    if len(recipients) + len(valid_addresses(cc)) > 10:
        return "NOT done: at most 10 people per email."
    attachments, attached = [], ""
    if pc_file.strip():
        from junior.agent.tools import _pc_file

        file, why = _pc_file(context, pc_file)
        if file is None:
            return f"NOT done: {why}. Nothing was drafted."
        attachments, attached = [file], str(context.last_pc_file)
    from junior.writing.polish import polish

    body = await polish(body, "an email" + (" reply" if reply_to.strip() else ""), context)
    try:
        draft_id = await make_draft(to, subject, body, cc, thread_id, in_reply_to, references, attachments)
    except GoogleError as e:
        gate.failed(context, "gmail.draft", str(e))
        return f"NOT done: {e}"
    reply = bool(reply_to.strip())
    try:
        item = create_item(
            kind="api", platform="email", item_type="reply" if reply else "email",
            action_type="gmail.reply" if reply else "gmail.send", text=body,
            title=f"To {', '.join(recipients)}: {subject}"[:200],
            from_outside=reply or context.outside_content_seen, conversation_id=context.conversation_id,
            meta={"to": to, "cc": cc, "subject": subject, "thread_id": thread_id, "in_reply_to": in_reply_to,
                  "references": references, "draft_id": draft_id, "reply_to": reply_to.strip(),
                  **({"pc_file": attached, "attachment": attachments[0][0]} if attached else {})},
        )
    except ApprovalError as e:
        return f"NOT done: {e}"
    gate.done(context, "gmail.draft", {"to": to, "subject": subject[:200], "item": item.id})
    if item.status == "approved":
        # Their rule for this kind of email is Auto: it goes out now, through the same Safety Guard and sender.
        from junior.senders.dispatch import SendError, send_item
        from junior.senders.registry import CURRENT

        try:
            item = await send_item(item.id, CURRENT)
        except SendError as e:
            context.approval_ids.append(item.id)
            context.pending_events.append({"type": "approval", "item": item.model_dump(mode="json")})
            return f"Their rule is Auto, but it wasn't sent: {e} It's in their Gmail Drafts and the card shows it. Tell them why in one line."
        context.approval_ids.append(item.id)
        context.pending_events.append({"type": "approval", "item": item.model_dump(mode="json")})
        if item.status == "posted":
            return f"Sent from their Gmail to {to} (their rule for new emails is Auto). Tell them in one line who it went to and the subject."
        return f"Their rule is Auto, but Gmail didn't confirm it: {item.meta.get('last_error', '')}. Tell them to check their Sent folder."
    context.approval_ids.append(item.id)
    context.pending_events.append({"type": "approval", "item": item.model_dump(mode="json")})
    return (
        f"Drafted (approval item {item.id}, also in their Gmail Drafts). It shows as a card with Approve and Reject; "
        "nothing is sent until they approve it. Tell them in one line who it's to and the subject; don't repeat the text."
    )


@function_tool
async def gmail_search(ctx: Ctx, query: str, limit: int = 10) -> str:
    """Search the user's Gmail ("emails from Ali", "unread this week", "the invoice from Acme"). Returns each email's
    id, date, sender, subject and a snippet. Read one in full with gmail_read.

    Args:
        query: A Gmail search, e.g. "from:ali@acme.com", "is:unread newer_than:3d", "subject:invoice", or plain words.
        limit: How many to show (1 to 25).
    """
    return await gmail_search_for(ctx.context, query, limit)


@function_tool
async def gmail_read(ctx: Ctx, email: str) -> str:
    """Read one email in full: from gmail_search (its id in brackets), or "email N" from an alert or the Inbox page.

    Args:
        email: The email's id, or its number N from "email N".
    """
    return await gmail_read_for(ctx.context, email)


@function_tool
async def gmail_draft(ctx: Ctx, to: str, subject: str, body: str, your_words: str, reply_to: str = "", cc: str = "",
                      pc_file: str = "") -> str:
    """Write an email for the user to someone else (any address they give), or a reply, with a file from their PC
    attached if they want. It goes into their Gmail Drafts and follows their "Send a new email" rule: Ask shows a card
    and waits for Approve; Auto sends it at once. Write the complete email, ready to send, signed with their name.

    Args:
        to: The recipient's email address (several separated by commas). For a reply, leave empty to answer the sender.
        subject: The subject. For a reply, leave empty to keep "Re: <their subject>".
        body: The full email text, ready to send. No placeholders like [name].
        your_words: The user's exact words asking for this email (copied word for word).
        reply_to: For a reply: the email's id from gmail_search, or its number N from "email N".
        cc: Anyone to copy, if they said.
        pc_file: A file on their PC to attach (its full path from pc_find / pc_list), e.g. their CV.
    """
    return await gmail_draft_for(ctx.context, to, subject, body, your_words, reply_to, cc, pc_file)


GOOGLE_TOOLS = [
    google_doc_create, google_doc_read, google_sheet_create, google_sheet_read, calendar_add_event, calendar_events,
    drive_search, drive_save, drive_read, drive_folder, gmail_search, gmail_read, gmail_draft,
]
