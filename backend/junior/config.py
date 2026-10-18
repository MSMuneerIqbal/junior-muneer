"""Settings, loaded from backend/.env and the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = ""
    # An AI request that sends nothing back for this long gives up (and is tried once more).
    ai_timeout_seconds: float = 120.0
    # Optional: other providers' keys (see [providers] in agents/models.toml).
    deepseek_api_key: str = ""
    # Phase 3: your Facebook Page (written by connect.bat meta; never committed).
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_page_id: str = ""
    meta_page_token: str = ""
    meta_ig_user_id: str = ""
    meta_graph_version: str = "v26.0"
    # Phase 8: WhatsApp (written by connect.bat whatsapp; never committed). Uses META_APP_SECRET to check Meta's signature.
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_owner_number: str = ""  # only this number is answered (international format)
    # A fixed public address for WhatsApp on your PC (tunnel.bat): your free ngrok account.
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""
    # Phase 6: the app's GitHub OAuth App (public client ID, device flow on): people connect their
    # own GitHub in the app. Not a secret.
    github_client_id: str = ""
    # Or, for the owner's machine: a token from connect.bat github (never committed).
    github_token: str = ""
    # Or use your GitHub CLI login (gh): the token stays in Windows' own store, asked from gh when needed.
    github_auth: str = ""  # "gh" to use the GitHub CLI login
    github_user: str = ""
    # Your Gmail, to email yourself the daily top 5 AI news: the address and a Google App Password
    # (myaccount.google.com/apppasswords; never your real password, never committed).
    gmail_address: str = ""
    gmail_app_password: str = ""
    # Google Docs, Sheets and Calendar (your own Google Cloud project's OAuth client, "Web application").
    # You connect your Google account in the app (Settings → Connections); the login is kept encrypted.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Where Google sends you back after you approve; it must be listed in the OAuth client exactly.
    google_redirect_uri: str = "http://127.0.0.1:8000/api/google/callback"
    # Optional: Artificial Analysis's free API key, for "who's on top" rankings in AI news.
    artificial_analysis_api_key: str = ""
    data_dir: Path = Path("data")
    log_level: str = "INFO"
    backend_host: str = "127.0.0.1"
    # Addresses besides your PC that may use the whole backend: your server's domain (comma-separated).
    public_hosts: str = ""
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    # The background scheduler (daily backups). Tests switch it off.
    scheduler_enabled: bool = True
    # Use a fake AI (echoes your messages, no cost) to try the dashboard without a key.
    fake_ai: bool = False

    @property
    def data_path(self) -> Path:
        """Absolute data folder; relative paths are taken from the repo root."""
        path = self.data_dir if self.data_dir.is_absolute() else REPO_DIR / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> Path:
        return self.data_path / "junior.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
