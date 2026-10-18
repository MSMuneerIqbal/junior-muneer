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


GOOGLE_TOOLS = [google_doc_create, google_doc_read, google_sheet_create, google_sheet_read]
