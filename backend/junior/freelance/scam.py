"""Scam signs in a job post, checked by code (P5-05).

A job showing any of these is marked "skip", whatever the AI thinks: the classic Upwork and Fiverr
scams all try to move you off the platform, take money first, or get your personal details.
Features a real job may describe ("reset your password", "check the deposit flow", a crypto app)
are not flagged: only the scam phrasing is.
"""

import re

from junior.writing.redlines import _APPS, _EMAIL, _phones

PATTERNS = [
    (_APPS, "Asks to talk outside the platform (on an app)."),
    (_EMAIL, "Gives an email address to contact them outside the platform."),
    (
        re.compile(
            r"\b(registration|training|onboarding|starter|activation|security) fee\b|\bpay (a |the |us )?(fee|deposit)\b|"
            r"\bbuy (a |the |our )?(course|kit|starter kit|equipment|laptop)\b|\bsend (us )?money\b|\bgift ?cards?\b",
            re.IGNORECASE,
        ),
        "Asks you to pay or buy something first.",
    ),
    (
        re.compile(
            r"\b(send|share|give|provide|email) (us |me )?(your )?(bank details|bank account|account number|iban|cnic|"
            r"passport|id card|ssn|social security number|login details|login credentials|password)\b",
            re.IGNORECASE,
        ),
        "Asks for bank or personal details.",
    ),
    (
        re.compile(r"\b(send|mail|post) (you )?a (check|cheque)\b|\b(check|cheque)\b.{0,60}\boverpa\w*", re.IGNORECASE | re.DOTALL),
        "Has a check or overpayment story.",
    ),
    (
        re.compile(r"\bpay(ment)? (in|via|with|through) (crypto|bitcoin|btc|usdt|ethereum)\b", re.IGNORECASE),
        "Wants to pay in crypto.",
    ),
    (
        re.compile(r"\b(outside (of )?(upwork|fiverr)|off[- ](upwork|fiverr)|pay(ing)? (you )?directly)\b", re.IGNORECASE),
        "Wants to work or pay outside the platform.",
    ),
]


def scam_signs(text: str) -> list[str]:
    """Scam signs found in a job post (plain words); empty when none."""
    signs = [why for pattern, why in PATTERNS if pattern.search(text)]
    if _phones(text):
        signs.insert(1, "Contains a phone number.")
    return signs
