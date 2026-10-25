"""Create exactly the approved research document/sheet once, using Google's official APIs."""
import json
from junior.google import auth
from junior.google.auth import GoogleError
from junior.senders.base import Outgoing, SendResult


class GoogleWorkspaceSender:
    label = "Google Drive"
    action_types = ("google.docs.create", "google.sheets.create", "google.drive.save", "google.drive.share")

    def is_connected(self):
        return auth.configured() and auth.is_connected() and auth.has_scope("drive.file")

    async def send(self, out: Outgoing) -> SendResult:
        from junior.google.docs import create_doc
        from junior.google.sheets import create_sheet
        from junior.google.sharing import apply_prepared_sharing, set_link_access, sharing_label
        from junior.transfers.sender import remember
        try:
            if out.action_type == "google.drive.share":
                fid = out.meta["drive_file_id"]
                await set_link_access(fid, out.meta["sharing_role"])
                return SendResult("sent", sharing_label(out.meta["sharing_role"]) + ".", remote_id=fid, url=out.meta["source_url"])
            if out.action_type == "google.drive.save":
                from junior.transfers.sender import save_to_drive
                return await save_to_drive(out)
            if out.action_type == "google.docs.create":
                if out.meta.get("uploaded_drive_id"):
                    remote_id, link = out.meta["uploaded_drive_id"], out.meta["uploaded_drive_link"]
                else:
                    remote_id, link = await create_doc(out.meta.get("document_title") or out.text.splitlines()[0].lstrip("# ")[:160], out.text)
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
                if out.meta.get("uploaded_drive_id"):
                    remote_id, link = out.meta["uploaded_drive_id"], out.meta["uploaded_drive_link"]
                else:
                    remote_id, link = await create_sheet(data.get("title", "Research spreadsheet"), headers, rows)
            remember(out.item_id, uploaded_drive_id=remote_id, uploaded_drive_link=link)
            await apply_prepared_sharing(out, remote_id)
            from junior.library import register_cloud_file
            from junior.db import ApprovalItem, session_scope
            with session_scope() as s:
                parent_chat = s.get(ApprovalItem, out.item_id).conversation_id
            label = (out.meta.get("document_title") or out.text.splitlines()[0].lstrip("# ")[:120]) if out.action_type == "google.docs.create" else data.get("title", "Spreadsheet")
            register_cloud_file(label, "application/vnd.google-apps.document" if out.action_type == "google.docs.create" else "application/vnd.google-apps.spreadsheet", link, parent_chat)
        except ValueError as e:
            return SendResult("failed", str(e))
        except GoogleError as e:
            # Creating may succeed before formatting fails. Never silently create a second copy.
            return SendResult("unclear", f"Google couldn't confirm completion ({e}). Check Drive before trying again.")
        return SendResult("sent", "Created your approved file in Google Drive. " + sharing_label(out.meta.get("sharing_role", "private")) + ".", remote_id=remote_id, url=link)
