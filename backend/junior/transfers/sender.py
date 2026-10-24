"""Execute pinned transfer plans after approval. No model-generated programs and no silent overwrites."""
import os

from junior.computer.paths import recheck
from junior.db import ApprovalItem, session_scope
from junior.senders.base import SendResult
from junior.transfers.sources import pinned


def copy_to_pc(out):
    row, data = pinned(out.meta)
    path = recheck(out.meta["path"])
    if path.exists():
        return SendResult("failed", f"{path} already exists. Choose another filename; nothing was overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    recheck(str(path))
    try:
        with path.open("xb") as f:
            try:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            except BaseException:
                f.close()
                path.unlink(missing_ok=True)
                raise
    except FileExistsError:
        return SendResult("failed", "A file appeared at the destination. Nothing was overwritten.")
    return SendResult("sent", f"Copied the actual file to {path} ({len(data):,} bytes). The source was kept.")


async def save_to_drive(out):
    from junior.google.drive import save_exact
    row, data = pinned(out.meta)
    saved = await save_exact(out.meta["filename"], data, row.mime, out.meta["folder"])
    link = saved.get("webViewLink") or f"https://drive.google.com/file/d/{saved['id']}/view"
    return SendResult("sent", f"Saved {out.meta['filename']} in the requested Google Drive folder.", remote_id=saved["id"], url=link)


def remember(item_id, **values):
    with session_scope() as s:
        item = s.get(ApprovalItem, item_id)
        item.meta = {**item.meta, **values}


class ArchiveWhatsAppSender:
    label = "Your WhatsApp"
    action_types = ("files.archive_whatsapp",)

    def is_connected(self):
        from junior.google import auth
        from junior.whatsapp import configured
        return configured() and auth.is_connected() and auth.has_scope("drive.file")

    async def send(self, out):
        from junior.config import get_settings
        from junior.google.drive import save_exact
        from junior.whatsapp import client
        try:
            row, data = pinned(out.meta)
        except ValueError as e:
            return SendResult("failed", str(e))
        link = out.meta.get("archive_drive_link", "")
        remote_id = out.meta.get("archive_drive_id", "")
        if not link:
            try:
                saved = await save_exact(row.filename, data, "application/zip", "")
            except Exception as e:
                return SendResult("unclear", f"Drive did not confirm the ZIP upload ({e}). Check My Drive before retrying.")
            remote_id = saved["id"]
            link = saved.get("webViewLink") or f"https://drive.google.com/file/d/{remote_id}/view"
            # Persist the successful first stage so a deliberate retry never uploads a second copy.
            remember(out.item_id, archive_drive_link=link, archive_drive_id=remote_id)
        from junior.senders.guard import check
        with session_scope() as s:
            problems = check(s.get(ApprovalItem, out.item_id), out.text)
        if problems:
            return SendResult("failed", f"ZIP is saved at {link}. WhatsApp was held: {problems[0]}", remote_id=remote_id, url=link)
        try:
            await client().send_text(get_settings().whatsapp_owner_number,
                f"Your ZIP: {row.filename}\n{out.meta['entry_count']} folder entries · {len(data):,} bytes\n\n"
                f"Download from your private Google Drive:\n{link}\n\n"
                "WhatsApp's API does not accept ZIP attachments. Open this link with your connected Google account.")
        except Exception as e:
            return SendResult("unclear", f"ZIP is saved privately at {link}. WhatsApp did not confirm sending ({str(e)[:240]}). "
                              "Check your WhatsApp before retrying.", remote_id=remote_id, url=link)
        return SendResult("sent", f"Sent the private ZIP download link to your own WhatsApp. {link}", remote_id=remote_id, url=link)
