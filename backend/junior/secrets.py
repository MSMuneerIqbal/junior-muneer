"""Encryption for tokens the app keeps (accounts you connect).

The key is made on first use and kept in the data folder (data/secret.key), which is never
committed. A copied database alone can't be read without it.
"""

from cryptography.fernet import Fernet, InvalidToken

from junior.config import get_settings


def _fernet() -> Fernet:
    path = get_settings().data_path / "secret.key"
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
    return Fernet(path.read_bytes().strip())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    """The text, or '' if it can't be read (a different key)."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
