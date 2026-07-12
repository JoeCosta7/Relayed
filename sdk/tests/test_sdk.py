import json

import httpx
import pytest

from relayed import (
    RelayedClient,
    RelayedAuthError,
    RelayedNotFoundError,
    RelayedConflictError,
    RelayedClientError,
    RelayedServerError,
)

API_KEY = "test-api-key"
BASE_URL = "http://relayed.test"


def make_client(handler) -> RelayedClient:
    """Build a real RelayedClient but route its requests through a mock transport.

    Only the transport is swapped, so the client's own base_url and auth headers
    are still exercised (and can be asserted on).
    """
    client = RelayedClient(API_KEY, base_url=BASE_URL)
    client._client._transport = httpx.MockTransport(handler)
    return client


def test_send_event_sends_correct_request():
    """send_event POSTs the event body with the idempotency key and returns the parsed response."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(202, json={"event_id": "evt_1", "delivery_ids": ["d1", "d2"]})

    client = make_client(handler)
    result = client.send_event("test.event", {"message": "hi"}, idempotency_key="idem-1")

    req = captured["request"]
    assert req.method == "POST"
    assert req.url.path == "/v1/events"
    assert req.headers["Authorization"] == f"Bearer {API_KEY}"
    assert req.headers["idempotency-key"] == "idem-1"
    assert json.loads(req.content) == {"event_type": "test.event", "payload": {"message": "hi"}}
    assert result == {"event_id": "evt_1", "delivery_ids": ["d1", "d2"]}


def test_create_subscription_sends_correct_request():
    """create_subscription POSTs destination_url/event_types/description and returns the created subscription."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"id": "sub_1", "webhook_secret": "whsec_1"})

    client = make_client(handler)
    result = client.create_subscription(
        destination_url="https://example.com/hook",
        event_types=["test.event"],
        description="my hook",
    )

    req = captured["request"]
    assert req.method == "POST"
    assert req.url.path == "/v1/subscriptions"
    assert json.loads(req.content) == {
        "destination_url": "https://example.com/hook",
        "event_types": ["test.event"],
        "description": "my hook",
    }
    assert result == {"id": "sub_1", "webhook_secret": "whsec_1"}


def test_list_subscriptions_returns_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/subscriptions"
        return httpx.Response(200, json=[{"id": "sub_1"}, {"id": "sub_2"}])

    client = make_client(handler)
    assert client.list_subscriptions() == [{"id": "sub_1"}, {"id": "sub_2"}]


def test_get_subscription_uses_path_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/subscriptions/sub_1"
        return httpx.Response(200, json={"id": "sub_1"})

    client = make_client(handler)
    assert client.get_subscription("sub_1") == {"id": "sub_1"}


def test_delete_subscription_returns_none_on_204():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v1/subscriptions/sub_1"
        return httpx.Response(204)

    client = make_client(handler)
    assert client.delete_subscription("sub_1") is None


def test_list_dead_letters_returns_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/deadletter"
        return httpx.Response(200, json=[{"id": "dl_1"}])

    client = make_client(handler)
    assert client.list_dead_letters() == [{"id": "dl_1"}]


def test_replay_dead_letter_returns_first_delivery_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/deadletter/dl_1/replay"
        return httpx.Response(200, json={"delivery_ids": ["d_new"]})

    client = make_client(handler)
    assert client.replay_dead_letter("dl_1") == "d_new"


@pytest.mark.parametrize(
    "status, exc",
    [
        (401, RelayedAuthError),
        (403, RelayedAuthError),
        (404, RelayedNotFoundError),
        (409, RelayedConflictError),
        (400, RelayedClientError),
        (422, RelayedClientError),
        (500, RelayedServerError),
        (503, RelayedServerError),
    ],
)
def test_error_status_maps_to_exception(status, exc):
    """Non-2xx responses raise the mapped exception, preserving status_code and body."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="boom")

    client = make_client(handler)
    with pytest.raises(exc) as info:
        client.list_subscriptions()
    assert info.value.status_code == status
    assert info.value.response_body == "boom"


def test_context_manager_closes_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    with make_client(handler) as client:
        assert client.list_subscriptions() == []
    assert client._client.is_closed
