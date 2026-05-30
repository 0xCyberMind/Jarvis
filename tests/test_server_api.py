from fastapi.testclient import TestClient

from server import app


def test_health_endpoint():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    json = r.json()
    assert json.get("status") == "online"
