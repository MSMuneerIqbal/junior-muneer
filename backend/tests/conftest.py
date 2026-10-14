import pytest

from junior.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Every test gets its own empty data folder and no real API key."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()
