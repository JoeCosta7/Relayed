from __future__ import annotations

class RelayedError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

class RelayedAuthError(RelayedError):
    """401/403 — missing or invalid API key."""

class RelayedNotFoundError(RelayedError):
    """404 — resource does not exist (or isn't owned by this customer)."""

class RelayedConflictError(RelayedError):
    """409 — e.g. dead letter already replayed, subscription no longer active."""

class RelayedClientError(RelayedError):
    """Other 4xx — e.g. 400/422 validation errors."""

class RelayedServerError(RelayedError):
    """5xx — something went wrong on Relayed's end."""

class RelayedTimestampError(RelayedError):
    """Raised when the timestamp of the webhook is outside the allowed tolerance."""

class RelayedSignatureError(RelayedError):
    """Raised when the signature of the webhook does not match the expected signature."""