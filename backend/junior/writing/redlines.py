"""Upwork's and Fiverr's red lines, checked by code (P5-02).

Upwork and Fiverr ban accounts for taking contact or payment off the platform, and Fiverr reads
messages for it. These checks run on every Upwork and Fiverr draft: the Checker can't pass a draft
that breaks one, and the card warns before you copy (even after your own edits).

Common words ("signal", "zoom", "IMO", a crypto or banking project) aren't flagged on their own:
only in a contact or payment sense.
"""

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_CANDIDATE = re.compile(r"\+?\(?\d[\d\s().-]{7,}\d")
_APPS = re.compile(
    r"\b(whats\s?app|telegram|skype|discord|wechat|viber|signal app|on signal|zoom (call|meeting|link)|google meet)\b",
    re.IGNORECASE,
)
# Payment apps and services that only ever mean "pay me outside the platform", and payment phrases.
_PAYMENT = re.compile(
    r"\b(pay\s?pal|payoneer|western union|money\s?gram|wise\.com|jazz\s?cash|easy\s?paisa|sadapay|nayapay)\b|"
    r"\b(my|your) (bank account|bank details|iban|account number)\b|"
    r"\bpay(ment)? (via|by|through|with|in) (bank transfer|crypto|bitcoin|btc|usdt|ethereum)\b|"
    r"\b(crypto|bitcoin|btc|usdt|ethereum) (wallet|address)\b",
    re.IGNORECASE,
)
_OFF_PLATFORM = re.compile(
    r"\b(outside (of )?(upwork|fiverr|the platform)|off[- ](upwork|fiverr|platform)|pay (me )?directly|"
    r"directly to (me|my account)|(contact|reach|message|text) me (on|at|via) (?!upwork|fiverr)|add me on)",
    re.IGNORECASE,
)
_URL = re.compile(r"\bhttps?://[^\s<>()\"']+|\bwww\.[^\s<>()\"']+", re.IGNORECASE)
_REVIEW_SWAP = re.compile(
    r"\b(5|five)[- ]?stars?\b.{0,60}\b(discount|free|bonus|exchange|extra|refund)\b|"
    r"\b(discount|free|bonus|extra)\b.{0,60}\b(5|five)[- ]?stars?\b",
    re.IGNORECASE | re.DOTALL,
)

LABELS = {"upwork": "Upwork", "fiverr": "Fiverr"}


def _phones(text: str) -> list[str]:
    """Numbers that look like phone numbers (10 to 15 digits), not prices, years or dates."""
    found = []
    for m in _PHONE_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 15:
            found.append(m.group(0).strip())
    return found


def red_lines(text: str, platform: str) -> list[str]:
    """Plain-English problems for an Upwork or Fiverr text; empty when it keeps the rules."""
    if platform not in LABELS:
        return []
    site = LABELS[platform]
    problems = []
    if _EMAIL.search(text):
        problems.append(f"Has an email address: {site} doesn't allow sharing contact details. Talk through {site} messages.")
    if _phones(text):
        problems.append(f"Has a phone number: {site} doesn't allow sharing contact details.")
    app = _APPS.search(text)
    if app:
        problems.append(f"Mentions {app.group(0)}: keep the conversation on {site}.")
    pay = _PAYMENT.search(text)
    if pay:
        problems.append(f"Mentions “{pay.group(0)}”: all payments must go through {site}.")
    if _OFF_PLATFORM.search(text):
        problems.append(f"Suggests going outside {site}: keep everything on {site}.")
    if platform == "fiverr":
        outside = [u for u in _URL.findall(text) if "fiverr.com" not in u.lower()]
        if outside:
            problems.append("Has a link that leads off Fiverr: Fiverr flags these. Share work through Fiverr's attachments.")
        if _REVIEW_SWAP.search(text):
            problems.append("Offers something for a review: Fiverr doesn't allow that.")
    return problems
