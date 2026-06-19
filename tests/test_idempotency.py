from fastapi.testclient import TestClient
import os
import uuid
from main import app

client = TestClient(app)
api_key = os.getenv("API_KEY")
auth_headers = {"Authorization": f"Bearer {api_key}"}


def test_same_idempotency_key():
    key = str(uuid.uuid4())
    payload = {"destination_url": "https://example.com/webhook", "event_type": "test", "payload": {"k": "v"}}
    response1 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key})
    response2 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key})
    assert response1.status_code == 202 and response2.status_code == 202
    assert response1.json()["id"] == response2.json()["id"]


def test_different_idempotency_key():
    key1 = str(uuid.uuid4())
    key2 = str(uuid.uuid4())
    payload = {"destination_url": "https://example.com/webhook", "event_type": "test", "payload": {"k": "v"}}
    response1 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key1})
    response2 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key2})
    assert response1.status_code == 202 and response2.status_code == 202
    assert response1.json()["id"] != response2.json()["id"]