"""Create exactly the approved research document/sheet once, using Google's official APIs."""
import json
from junior.google import auth
from junior.google.auth import GoogleError
from junior.senders.base import Outgoing, SendResult


class GoogleWorkspaceSender:
    label = "Google Drive"
    action_types = ("google.docs.create", "google.sheets.create", "google.drive.save")

    def is_connected(self):
        return auth.configured() and auth.is_connected() and auth.has_scope("drive.file")

    async def send(self, out: Outgoing) -> SendResult:
        from junior.google.docs import create_doc
        from junior.google.sheets import create_sheet
        try:
            if out.action_type == "google.drive.save":
                from junior.transfers.sender import save_to_drive
                return await save_to_drive(out)
            if out.action_type == "google.docs.create":
                remote_id, link = await create_doc(out.text.splitlines()[0].lstrip("# ")[:160], out.text)
            else:
                try:
                    data = json.loads(out.text)
                    headers, rows = data["headers"], data["rows"]
                    valid = (isinstance(data.get("title", "Research spreadsheet"), str) and
                             isinstance(headers, list) and 1 <= len(headers) <= 26 and all(isinstance(h, str) for h in headers)
                             and isinstance(rows, list) and len(rows) <= 500 and all(isinstance(row, list) and
                             len(row) == len(headers) and all(isinstance(c, str) for c in row) for row in rows))
                    if not valid:
                        raise ValueError("invalid rows")
                except (ValueError, TypeError, KeyError):
                    return SendResult("failed", "The approved sheet must contain JSON headers and rows; nothing was created.")
                remote_id, link = await create_sheet(data.get("title", "Research spreadsheet"), headers, rows)
        except ValueError as e:
            return SendResult("failed", str(e))
        except GoogleError as e:
            # Creating may succeed before formatting fails. Never silently create a second copy.
            return SendResult("unclear", f"Google couldn't confirm completion ({e}). Check Drive before trying again.")
        return SendResult("sent", "Created your approved file in Google Drive.", remote_id=remote_id, url=link)
