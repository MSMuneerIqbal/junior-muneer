"""Sending an approved email through your Gmail (Phase 4).

Plain code, never AI. The email's To, Cc, subject and thread were fixed when the draft was made (kept in the
item's meta); the body is exactly the text you approved. It goes out from your Gmail Drafts, so it shows in
your Sent folder like any email you send.
"""

from junior.google import auth
from junior.google.auth import GoogleError
from junior.senders.base import Outgoing, SendResult

ACTIONS = ("gmail.send", "gmail.reply")


class GmailSender:
    label = "Gmail"
    action_types = ACTIONS

    def is_connected(self) -> bool:
        return auth.configured() and auth.is_connected() and auth.has_scope("gmail.compose")

    async def send(self, out: Outgoing) -> SendResult:
        from junior.google.gmail import link, send_draft

        meta = out.meta
        if not meta.get("to"):
            return SendResult("failed", "The email has no recipient; nothing was sent.")
        try:
            sent = await send_draft(
                meta.get("draft_id", ""), meta["to"], meta.get("subject", ""), out.text, meta.get("cc", ""),
                meta.get("thread_id", ""), meta.get("in_reply_to", ""), meta.get("references", ""),
            )
        except GoogleError as e:
            reason = str(e)
            # Google clearly refused (bad address, no permission): nothing went out. Anything else: check.
            if any(w in reason for w in ("isn't an email address", "said no (400", "don't have access", "isn't connected", "expired")):
                return SendResult("failed", f"Gmail refused it: {reason}")
            return SendResult("unclear", f"Gmail had a problem ({reason}); check your Sent folder.")
        message_id = sent.get("id", "")
        return SendResult("sent", f"Sent from your Gmail to {meta['to']}.", remote_id=message_id, url=link(message_id) if message_id else "")
