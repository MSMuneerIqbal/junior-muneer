"""Google Sheets: make a sheet from rows Junior Muneer gathered, and read one of yours by its link.

Cells are written as plain text (RAW), never as formulas: text from a web page can't become a formula in your sheet.
"""

import re
from urllib.parse import quote

from junior.google.auth import GoogleError, call

SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
MAX_ROWS = 500
MAX_COLUMNS = 26
MAX_READ_ROWS = 300
_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def sheet_id(link: str) -> str:
    link = link.strip()
    if m := _ID.search(link):
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
        return link
    raise GoogleError("That doesn't look like a Google Sheet link (docs.google.com/spreadsheets/d/...).")


def _cell(value: object) -> str:
    return " ".join(str(value).split())[:2000]


def _column(n: int) -> str:
    return chr(ord("A") + n - 1)


async def create_sheet(title: str, headers: list[str], rows: list[list[str]]) -> tuple[str, str]:
    """A new sheet in your Drive: a bold, frozen header row, then the rows. Returns (id, link)."""
    if not headers:
        raise GoogleError("A sheet needs at least one column header.")
    if len(headers) > MAX_COLUMNS:
        raise GoogleError(f"At most {MAX_COLUMNS} columns.")
    if len(rows) > MAX_ROWS:
        raise GoogleError(f"At most {MAX_ROWS} rows in one go.")
    width = len(headers)
    values = [[_cell(h) for h in headers]] + [[_cell(v) for v in (row + [""] * width)[:width]] for row in rows]
    created = await call(
        "POST",
        SHEETS,
        json={"properties": {"title": " ".join(title.split())[:200] or "Untitled"},
              "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "gridProperties": {"frozenRowCount": 1}}}]},
    )
    spreadsheet_id = created["spreadsheetId"]
    target = quote(f"Sheet1!A1:{_column(width)}{len(values)}", safe="!:")
    await call("PUT", f"{SHEETS}/{spreadsheet_id}/values/{target}", params={"valueInputOption": "RAW"}, json={"values": values})
    await call(
        "POST",
        f"{SHEETS}/{spreadsheet_id}:batchUpdate",
        json={"requests": [
            {"repeatCell": {"range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold"}},
            {"autoResizeDimensions": {"dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": width}}},
        ]},
    )
    link = created.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    return spreadsheet_id, link


async def read_sheet(link: str, tab: str = "") -> tuple[str, str, list[list[str]], list[str]]:
    """(sheet title, tab read, rows, all tab names) of a sheet you can open; at most MAX_READ_ROWS rows."""
    spreadsheet_id = sheet_id(link)
    info = await call("GET", f"{SHEETS}/{spreadsheet_id}", params={"fields": "properties.title,sheets.properties.title"})
    tabs = [s["properties"]["title"] for s in info.get("sheets", [])]
    if not tabs:
        raise GoogleError("That sheet has no tabs.")
    chosen = next((t for t in tabs if t.casefold() == tab.casefold()), tabs[0]) if tab else tabs[0]
    target = quote(f"'{chosen}'!A1:Z{MAX_READ_ROWS}", safe="!:'")
    got = await call("GET", f"{SHEETS}/{spreadsheet_id}/values/{target}")
    return info.get("properties", {}).get("title", "Untitled"), chosen, got.get("values", []), tabs


def as_table(rows: list[list[str]]) -> str:
    """Rows as a plain table for the agent: one line per row, cells split by ' | ', with row numbers."""
    return "\n".join(f"{n}: " + " | ".join(str(c) for c in row) for n, row in enumerate(rows, 1))
