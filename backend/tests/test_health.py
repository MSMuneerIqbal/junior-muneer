from fastapi.testclient import TestClient

from junior.main import create_app


def test_health_answers_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_data_dir_comes_from_settings(isolated_settings, tmp_path):
    assert isolated_settings.db_path == tmp_path / "data" / "junior.db"
