from __future__ import annotations

from typing import Any

import httpx

from ._errors import (
    RelayedError,
    RelayedAuthError,
    RelayedNotFoundError,
    RelayedConflictError,
    RelayedClientError,
    RelayedServerError,
)


_STATUS_EXCEPTIONS: dict[int, type[RelayedError]] = {
    401: RelayedAuthError,
    403: RelayedAuthError,
    404: RelayedNotFoundError,
    409: RelayedConflictError,
}


class RelayedClient:

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0):
        self.api_key = api_key
        self.base_url = base_url
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RelayedClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        response = self._client.request(method, path, **kwargs)
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if 200 <= response.status_code < 300:
            return
        exc_cls = _STATUS_EXCEPTIONS.get(response.status_code)
        if exc_cls is None:
            exc_cls = RelayedServerError if response.status_code >= 500 else RelayedClientError
        raise exc_cls(
            f"Relayed API returned {response.status_code}: {response.text}",
            status_code=response.status_code,
            response_body=response.text,
        )

    def send_event(self, event_type: str, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        """Returns {"event_id": str, "delivery_ids": list[str]}.

        idempotency_key is required and not generated for you: if you retry after
        a dropped connection, reusing the same key is what makes the retry safe.
        Generating a fresh one per call would defeat that.
        """
        return self._request(
            "POST",
            "/v1/events",
            json={"event_type": event_type, "payload": payload},
            headers={"idempotency-key": idempotency_key},
        )

    def list_dead_letters(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/deadletter")

    def replay_dead_letter(self, dead_letter_id: str) -> str:
        """Returns the id of the new delivery created for the replay."""
        result = self._request("POST", f"/v1/deadletter/{dead_letter_id}/replay")
        return result["delivery_ids"][0]

    def create_subscription(
        self,
        destination_url: str,
        event_types: list[str],
        description: str | None = None,
    ) -> dict[str, Any]:
        """Returns the created subscription, including webhook_secret.

        webhook_secret is shown only here
        """
        return self._request(
            "POST",
            "/v1/subscriptions",
            json={
                "destination_url": destination_url,
                "event_types": event_types,
                "description": description,
            },
        )

    def list_subscriptions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/subscriptions")

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/subscriptions/{subscription_id}")

    def delete_subscription(self, subscription_id: str) -> None:
        self._request("DELETE", f"/v1/subscriptions/{subscription_id}")
