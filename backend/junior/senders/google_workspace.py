"""Create exactly the approved research document/sheet once, using Google's official APIs."""
import json
import hashlib
from junior.google import auth
from junior.google.auth import GoogleError
from junior.senders.base import Outgoing, SendResult


class GoogleWorkspaceSender:
    label = "Google Drive"
    action_types = ("google.docs.create", "google.sheets.create", "google.slides.create", "google.drive.save", "google.drive.share")

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
            if out.action_type == "google.slides.create":
                from junior.google.slides import MIME, PresentationPayload, create_presentation
                try:
                    if len(out.text) > 120000:
                        raise ValueError("Presentation is too large.")
                    payload = PresentationPayload.model_validate_json(out.text)
                    payload.checked_sources()
                except ValueError:
                    if out.meta.get("uploaded_drive_id"):
                        return SendResult("unclear", "The edited content is invalid, and an earlier presentation already exists. Inspect it in Drive; no new copy was created.",
                                          remote_id=out.meta["uploaded_drive_id"], url=out.meta.get("uploaded_drive_link", ""))
                    return SendResult("failed", "The presentation content or citations are invalid; nothing was created.")
                if out.meta.get("uploaded_drive_id"):
                    remote_id, link = out.meta["uploaded_drive_id"], out.meta["uploaded_drive_link"]
                    if out.meta.get("slides_content_hash") != hashlib.sha256(out.text.encode()).hexdigest():
                        return SendResult("unclear", "This card changed after Google creation. Inspect the existing presentation; edited content was not applied.", remote_id=remote_id, url=link)
                    if not out.meta.get("slides_content_complete"):
                        return SendResult("unclear", "A presentation was created but its content was not confirmed. Inspect it in Drive; this action will not create another copy.", remote_id=remote_id, url=link)
                else:
                    from junior.google.sharing import allowed_after_creation
                    remote_id, link = await create_presentation(payload, lambda fid, url: remember(
                        out.item_id, uploaded_drive_id=fid, uploaded_drive_link=url,
                        slides_content_hash=hashlib.sha256(out.text.encode()).hexdigest()),
                        lambda: allowed_after_creation(out))
                    remember(out.item_id, slides_content_complete=True)
                label, mime = payload.document.title, MIME
            elif out.action_type == "google.docs.create":
                if out.meta.get("uploaded_drive_id"):
                    remote_id, link = out.meta["uploaded_drive_id"], out.meta["uploaded_drive_link"]
                else:
                    remote_id, link = await create_doc(out.meta.get("document_title") or out.text.splitlines()[0].lstrip("# ")[:160], out.text)
                label = out.meta.get("document_title") or out.text.splitlines()[0].lstrip("# ")[:120]
                mime = "application/vnd.google-apps.document"
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
                label, mime = data.get("title", "Spreadsheet"), "application/vnd.google-apps.spreadsheet"
            remember(out.item_id, uploaded_drive_id=remote_id, uploaded_drive_link=link)
            await apply_prepared_sharing(out, remote_id)
            from junior.library import register_cloud_file
            from junior.db import ApprovalItem, session_scope
            with session_scope() as s:
                parent_chat = s.get(ApprovalItem, out.item_id).conversation_id
            register_cloud_file(label, mime, link, parent_chat)
        except ValueError as e:
            return SendResult("failed", str(e))
        except GoogleError as e:
            # Creating may succeed before formatting fails. Never silently create a second copy.
            return SendResult("unclear", f"Google couldn't confirm completion ({e}). Check Drive before trying again.")
        return SendResult("sent", "Created your approved file in Google Drive. " + sharing_label(out.meta.get("sharing_role", "private")) + ".", remote_id=remote_id, url=link)
