from fastapi.testclient import TestClient
import os
from main import app

client = TestClient(app)

def test_no_authorization_header():
    response = client.get("/v1/events")
    assert response.status_code == 401


def test_wrong_api_key():
    response = client.get("/v1/events", headers={"Authorization": "Bearer not-the-real-key"})
    assert response.status_code == 401


def test_correct_api_key():
    correct = os.getenv("API_KEY")
    response = client.get("/v1/events", headers={"Authorization": f"Bearer {correct}"})
    assert response.status_code == 200

