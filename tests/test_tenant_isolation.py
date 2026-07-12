from uuid import uuid4
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from database import engine, Event, Delivery, DeadLetter, DeliveryStatusEnum, Subscription
from redis_client import r
from main import app

client = TestClient(app)

EVENT = {"event_type": "test", "payload": {"k": "v"}}


def auth(customer):
    return {"Authorization": f"Bearer {customer['api_key']}"}


def idem(customer):
    return {**auth(customer), "Idempotency-Key": str(uuid4())}


@pytest.fixture(autouse=True)
def clean_redis_keys():
    yield
    for pattern in ("ratelimit:*", "idempotency:*"):
        for key in r.scan_iter(pattern):
            r.delete(key)
    r.delete("relay:deliveries:pending")


def _seed_dead_letter(customer_id):
    """Create an un-replayed dead letter (plus its subscription/event/delivery) for a tenant."""
    with Session(engine) as session:
        subscription = Subscription(
            customer_id=customer_id,
            destination_url="https://example.com/hook",
            event_types=["test"],
        )
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        event = Event(event_type="test", payload={}, customer_id=customer_id)
        session.add(event)
        session.commit()
        session.refresh(event)

        delivery = Delivery(
            event_id=event.id,
            customer_id=customer_id,
            subscription_id=subscription.id,
            status=DeliveryStatusEnum.DEAD_LETTERED,
            attempts=5,
        )
        session.add(delivery)
        session.commit()
        session.refresh(delivery)

        dead_letter = DeadLetter(
            event_id=event.id,
            attempts=5,
            status_code=500,
            replayed_at=None,
            customer_id=customer_id,
            subscription_id=subscription.id,
            delivery_id=delivery.id,
        )
        session.add(dead_letter)
        session.commit()
        session.refresh(dead_letter)
        return dead_letter.id


def test_cannot_read_or_delete_another_tenants_subscription(create_test_customer):
    """B can neither fetch, list, nor delete A's subscription; A's copy is untouched."""
    a = create_test_customer()
    b = create_test_customer()
    sub_id = client.post(
        "/v1/subscriptions",
        headers=auth(a),
        json={"destination_url": "https://a.example/hook", "event_types": ["x"]},
    ).json()["id"]

    # 404 (not 403) so existence isn't leaked
    assert client.get(f"/v1/subscriptions/{sub_id}", headers=auth(b)).status_code == 404
    assert client.delete(f"/v1/subscriptions/{sub_id}", headers=auth(b)).status_code == 404
    # Never appears in B's listing
    assert all(s["id"] != sub_id for s in client.get("/v1/subscriptions", headers=auth(b)).json())
    # A's subscription survived B's delete attempt
    assert client.get(f"/v1/subscriptions/{sub_id}", headers=auth(a)).status_code == 200


def test_events_are_scoped_to_tenant(create_test_customer):
    """An event created by A is visible to A only, never to B."""
    a = create_test_customer()
    b = create_test_customer()
    client.post("/v1/events", headers=idem(a), json=EVENT)

    assert len(client.get("/v1/events", headers=auth(a)).json()) == 1
    assert client.get("/v1/events", headers=auth(b)).json() == []


def test_cannot_replay_another_tenants_dead_letter(create_test_customer):
    """B cannot see or replay A's dead letter; it stays replayable by A."""
    a = create_test_customer()
    b = create_test_customer()
    dl_id = _seed_dead_letter(a["customer"].id)

    assert client.post(f"/v1/deadletter/{dl_id}/replay", headers=auth(b)).status_code == 404
    assert client.get("/v1/deadletter", headers=auth(b)).json() == []
    # Untouched by B: A can still replay it successfully
    assert client.post(f"/v1/deadletter/{dl_id}/replay", headers=auth(a)).status_code == 202


def test_rate_limit_bucket_is_per_tenant(create_test_customer):
    """Exhausting A's rate-limit bucket does not affect B."""
    a = create_test_customer()
    b = create_test_customer()
    r.hset(
        f"ratelimit:{a['customer'].id}",
        mapping={"tokens": 0, "last_refill": datetime.now(timezone.utc).timestamp()},
    )

    assert client.post("/v1/events", headers=idem(a), json=EVENT).status_code == 429
    assert client.post("/v1/events", headers=idem(b), json=EVENT).status_code == 202


def test_idempotency_key_is_namespaced_per_tenant(create_test_customer):
    """The same idempotency key used by two tenants yields two independent events."""
    a = create_test_customer()
    b = create_test_customer()
    key = str(uuid4())

    ra = client.post("/v1/events", headers={**auth(a), "Idempotency-Key": key}, json=EVENT)
    rb = client.post("/v1/events", headers={**auth(b), "Idempotency-Key": key}, json=EVENT)

    assert ra.status_code == 202 and rb.status_code == 202
    assert ra.json()["event_id"] != rb.json()["event_id"]

def test_key_rotation_does_not_affect_other_tenants(create_test_customer):
    """B rotating their key leaves A's key completely intact."""
    a = create_test_customer()
    b = create_test_customer()
    
    a_original_key = a["api_key"]
    
    # B rotates their key
    response = client.post("/v1/keys/rotate", headers=auth(b))
    assert response.status_code == 200
    
    # A's key still works, no grace-period side effects
    ping = client.get("/v1/events", headers=auth(a))
    assert ping.status_code == 200

