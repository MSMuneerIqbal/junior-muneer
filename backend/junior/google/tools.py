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

    action = "google.docs.create"
    if refusal := _not_ready("drive.file") or gate.check(context, action, your_words=your_words):
        return refusal
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


GOOGLE_TOOLS = [
    google_doc_create, google_doc_read, google_sheet_create, google_sheet_read, calendar_add_event, calendar_events,
]
