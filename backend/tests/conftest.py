import shutil

import pytest

from junior.config import get_settings
from junior.db import init_db
from junior.db.engine import close_all_connections


@pytest.fixture(scope="session")
def migrated_db(tmp_path_factory):
    """Run the migrations once; each test starts from a copy (much faster)."""
    folder = tmp_path_factory.mktemp("template")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(folder))
    get_settings.cache_clear()
    init_db()
    close_all_connections()
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
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    # Your real connections in backend/.env must never be used by tests.
    for key in ("ARTIFICIAL_ANALYSIS_API_KEY", "META_APP_ID", "META_APP_SECRET", "META_PAGE_ID",
                "META_PAGE_TOKEN", "META_IG_USER_ID", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_ID"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()
    yield get_settings()
    close_all_connections()
    get_settings.cache_clear()
