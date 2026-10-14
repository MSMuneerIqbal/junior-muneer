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
    # Optional: other providers' keys (see [providers] in agents/models.toml).
    deepseek_api_key: str = ""
    data_dir: Path = Path("data")
    log_level: str = "INFO"
    backend_host: str = "127.0.0.1"
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
