from fastapi.testclient import TestClient
import os
import uuid
from main import app


client = TestClient(app)

def test_same_idempotency_key(test_customer, test_subscription):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    key = str(uuid.uuid4())
    payload = {"event_type": test_subscription.event_types[0], "payload": {"k": "v"}}
    response1 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key})
    response2 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key})
    assert response1.status_code == 202 and response2.status_code == 202
    assert response1.json()["delivery_ids"] == response2.json()["delivery_ids"]
    assert response1.json()["event_id"] == response2.json()["event_id"]


def test_different_idempotency_key(test_customer, test_subscription):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    key1 = str(uuid.uuid4())
    key2 = str(uuid.uuid4())
    payload = {"event_type": test_subscription.event_types[0], "payload": {"k": "v"}}
    response1 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key1})
    response2 = client.post("/v1/events", json=payload, headers={**auth_headers, "Idempotency-Key": key2})
    assert response1.status_code == 202 and response2.status_code == 202
    assert len(response1.json()["delivery_ids"]) > 0
    assert response1.json()["delivery_ids"] != response2.json()["delivery_ids"]
    assert response1.json()["event_id"] != response2.json()["event_id"]