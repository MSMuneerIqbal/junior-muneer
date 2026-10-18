"""Email to yourself: anything Junior Muneer sends you by mail (news, drafts, notes, plans).

Sent through Gmail's own mail server (SMTP) with a Google App Password from backend/.env
(GMAIL_ADDRESS, GMAIL_APP_PASSWORD). The recipient is always that one address, yours: there is no
way to pass another one. Emailing other people is Phase 4 (Gmail API, always through approvals).
Callers check the permission rule first (`gmail.to_self`, `gmail.news_to_self`).
"""

import asyncio
import html
import re
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage

from junior.config import get_settings

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465

Sender = Callable[[EmailMessage], None]
SENDER: Sender | None = None  # tests put a fake here
FAKE_SENT: list[EmailMessage] = []  # FAKE_AI with GMAIL_APP_PASSWORD=fake: nothing leaves the PC


class MailError(Exception):
    """Why the email wasn't sent, in plain words."""


def configured() -> bool:
    s = get_settings()
    return bool(s.gmail_address.strip() and s.gmail_app_password.strip())


def my_address() -> str:
    return get_settings().gmail_address.strip()


def _smtp_send(message: EmailMessage) -> None:
    s = get_settings()
    password = s.gmail_app_password.replace(" ", "")  # Google shows it in groups of four
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(my_address(), password)
        smtp.send_message(message)


def _sender() -> Sender:
    if SENDER is not None:
        return SENDER
    s = get_settings()
    if s.fake_ai and s.gmail_app_password == "fake":
        return FAKE_SENT.append
    return _smtp_send


_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE = re.compile(r"(?<![\"'>=])(https?://[^\s<]+[^\s<.,;:!?)])")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def markdown_html(text: str) -> str:
    """A chat answer (light markdown) as simple email HTML: paragraphs, bold, headings, bullets and links."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        rendered = []
        for line in lines:
            safe = html.escape(line.strip(), quote=False)
            safe = _LINK.sub(lambda m: f'<a href="{m.group(2)}" style="color:#c96442">{m.group(1)}</a>', safe)
            safe = _BARE.sub(r'<a href="\1" style="color:#c96442">\1</a>', safe)
            safe = _BOLD.sub(r"<b>\1</b>", safe)
            if heading := re.match(r"^#{1,4}\s+(.*)$", safe):
                rendered.append(f'<div style="font-size:16px;font-weight:600;margin:8px 0 4px">{heading.group(1)}</div>')
            elif bullet := re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", safe):
                rendered.append(f'<div style="margin:2px 0 2px 12px">• {bullet.group(1)}</div>')
            else:
                rendered.append(safe)
        out.append('<p style="margin:0 0 12px;line-height:1.5">' + "<br>".join(rendered) + "</p>")
    return "".join(out)


def _wrap(body_html: str) -> str:
    return (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#222;font-size:14px">'
        f"{body_html}"
        '<p style="color:#888;font-size:12px;margin-top:16px">Sent by Junior Muneer, to you only.</p></div>'
    )


async def send_to_self(subject: str, text: str, body_html: str | None = None) -> str:
    """Email yourself. `text` is the plain version (light markdown is fine); HTML is made from it unless given.
    Raises MailError with the reason when it can't."""
    if not configured():
        raise MailError("Gmail isn't set up: add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to backend/.env, then restart.")
    subject = " ".join(subject.split())[:200] or "From Junior Muneer"
    if not text.strip():
        raise MailError("The email is empty.")
    address = my_address()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"Junior Muneer <{address}>"
    message["To"] = address
    message.set_content(text)
    message.add_alternative(_wrap(body_html or markdown_html(text)), subtype="html")
    try:
        await asyncio.to_thread(_sender(), message)
    except smtplib.SMTPAuthenticationError:
        raise MailError(
            "Gmail refused the login. Check GMAIL_ADDRESS, and that GMAIL_APP_PASSWORD is an App Password "
            "(myaccount.google.com/apppasswords), not your normal password."
        ) from None
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Couldn't send the email ({type(e).__name__}: {e}).") from None
    return address
