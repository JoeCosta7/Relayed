from fastapi.testclient import TestClient
import os
import uuid
from redis_client import r
from main import app
from database import TierEnum
from datetime import datetime, timezone, timedelta
from unittest import mock
import pytest

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_rate_limit_keys():
    yield
    for key in r.scan_iter("ratelimit:*"):
        r.delete(key)

def test_free_tier_denies_at_capacity(test_customer):
    """After 60 requests, the 61st is denied with 429 and Retry-After=1."""
    customer = test_customer["customer"]
    api_key = test_customer["api_key"]
    assert customer.tier == TierEnum.FREE

    frozen_now = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
    key = f"ratelimit:{customer.id}"

    r.hset(key, mapping={"tokens": 60, "last_refill": frozen_now.timestamp()})

    auth_headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"event_type": "test", "payload": {"k": "v"}}

    with mock.patch("rate_limit.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        for i in range(60):
            response = client.post(
                "/v1/events",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
                json=payload,
            )
            assert response.status_code == 202, f"Request {i+1} failed unexpectedly"
        response = client.post(
            "/v1/events",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"


def test_free_tier_recovers_after_refill(test_customer):
    """A customer at 0 tokens is denied, then recovers once enough time passes to refill."""
    customer = test_customer["customer"]
    api_key = test_customer["api_key"]
    assert customer.tier == TierEnum.FREE

    frozen_now = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
    key = f"ratelimit:{customer.id}"
    r.hset(key, mapping={"tokens": 0, "last_refill": frozen_now.timestamp()})

    auth_headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"event_type": "test", "payload": {"k": "v"}}

    with mock.patch("rate_limit.datetime") as mock_dt:
        mock_dt.now.return_value = frozen_now
        response = client.post(
            "/v1/events",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"
        mock_dt.now.return_value = frozen_now + timedelta(seconds=1)
        response = client.post(
            "/v1/events",
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert response.status_code == 202


