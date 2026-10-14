from fastapi.testclient import TestClient

from junior.main import create_app


def test_health_answers_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_data_dir_comes_from_settings(isolated_settings, tmp_path):
    assert isolated_settings.db_path == tmp_path / "data" / "junior.db"


def test_closed_connection_noise_is_filtered():
    import logging

    from junior.logging_setup import setup_logging

    setup_logging()
    logger = logging.getLogger("asyncio")
    noise = logger.makeRecord("asyncio", logging.ERROR, __file__, 1, "x", (), (ConnectionResetError, ConnectionResetError(), None))
    real = logger.makeRecord("asyncio", logging.ERROR, __file__, 1, "x", (), (ValueError, ValueError(), None))
    assert not logger.filter(noise)
    assert logger.filter(real)
