import shutil

import pytest

from junior.config import get_settings
from junior.db import init_db


@pytest.fixture(scope="session")
def migrated_db(tmp_path_factory):
    """Run the migrations once; each test starts from a copy (much faster)."""
    folder = tmp_path_factory.mktemp("template")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(folder))
    get_settings.cache_clear()
    init_db()
    mp.undo()
    get_settings.cache_clear()
    return folder / "junior.db"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch, migrated_db):
    """Every test gets its own data folder with a fresh database, and no real API key."""
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(migrated_db, data / "junior.db")
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()
