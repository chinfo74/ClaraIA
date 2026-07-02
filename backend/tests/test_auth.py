import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.main import app

client = TestClient(app)
settings = get_settings()


def test_admin_is_protected():
    assert client.get("/admin").status_code in (401, 503)


def test_api_documents_is_protected():
    assert client.get("/api/documents").status_code in (401, 503)


def test_admin_with_correct_credentials():
    if not settings.admin_password:
        pytest.skip("ADMIN_PASSWORD non configuré")
    r = client.get("/admin", auth=(settings.admin_user, settings.admin_password))
    assert r.status_code == 200


def test_admin_with_wrong_credentials():
    if not settings.admin_password:
        pytest.skip("ADMIN_PASSWORD non configuré")
    assert client.get("/admin", auth=("admin", "mauvais")).status_code == 401


def test_chat_endpoint_is_public():
    assert client.post("/api/chat", json={"message": "Bonjour"}).status_code == 200


def test_health_is_public():
    assert client.get("/health").status_code == 200
